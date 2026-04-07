"""
TARS-AI Companion Server v2.0

Run on a powerful PC or server to offload heavy AI workloads from the Raspberry Pi.

Services:
  - STT:        Speech-to-text via faster-whisper (GPU, with Silero VAD pre-filtering)
  - TTS:        Text-to-speech via Piper ONNX (with response caching)
  - LLM:        Local language model (default: Qwen3-4B, with KV cache + token counting)
  - Vision:     Image captioning via BLIP or vision-capable LLM
  - ImageGen:   Image generation via diffusers (Automatic1111-compatible, scheduler selection)
  - MusicGen:   Music generation from text prompts (facebook/musicgen via transformers)
  - Embeddings: Sentence embeddings for RAG/memory (sentence-transformers)

Security:
  Set api_key in config-server.ini to require Authorization: Bearer <key> on all requests.
  The RPi already sends this header, so it's zero-config on the client side.

Usage:
  python app-server.py                                    # All services, auto GPU
  python app-server.py --services stt llm                 # Only STT + LLM
  python app-server.py --llm-model Qwen/Qwen3-8B         # Larger LLM
  python app-server.py --ssl-cert cert.pem --ssl-key key.pem  # HTTPS

Configure your TARS RPi to point at this server:
  [STT]              stt_processor = external       external_url = http://<server-ip>:5678
  [LLM]              llm_backend = other            base_url = http://<server-ip>:5678
  [TTS]              ttsoption = other               ttsurl = http://<server-ip>:5678
  [VISION]           vision_processor = server_hosted base_url = http://<server-ip>:5678
  [STABLE_DIFFUSION] service = automatic1111         url = http://<server-ip>:5678
"""

import argparse
import asyncio
import base64
import collections
import configparser
import contextlib
import gc
import hashlib
import json
import logging
import logging.handlers
import os
import signal
import struct
import sys
import time
import traceback
import uuid
import warnings
import wave
from datetime import datetime
import io
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from typing import Optional

# ---------------------------------------------------------------------------
# Auto-install dependencies on first run (works on ANY PC, no manual setup)
# ---------------------------------------------------------------------------
def _has_nvidia_gpu() -> bool:
    """Detect NVIDIA GPU before torch is installed (uses nvidia-smi)."""
    import subprocess as _sp
    try:
        return _sp.run(["nvidia-smi"], capture_output=True, timeout=10).returncode == 0
    except (FileNotFoundError, _sp.TimeoutExpired):
        return False


def _restart_self():
    """Restart the current script (cross-platform)."""
    if sys.platform == "win32":
        # os.execv on Windows spawns a new process but the parent continues.
        # Use subprocess.call (blocking) so the parent holds the port until the
        # child finishes startup, then exit cleanly.
        import subprocess
        rc = subprocess.call([sys.executable] + sys.argv)
        sys.exit(rc)
    else:
        os.execv(sys.executable, [sys.executable] + sys.argv)


def _bootstrap_deps():
    """Auto-install all dependencies. Works with or without requirements-server.txt."""
    import importlib.util
    import subprocess

    # Check core packages — if all present, skip
    _CORE = ["torch", "fastapi", "uvicorn", "transformers", "accelerate"]
    missing = [p for p in _CORE if importlib.util.find_spec(p) is None]
    if not missing:
        return

    print(f"[TARS] Missing packages: {', '.join(missing)}")
    print("[TARS] First run — installing dependencies. This may take several minutes...")

    # Prefer requirements-server.txt if it exists
    req_file = Path(__file__).parent / "requirements-server.txt"
    if req_file.exists():
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        if rc != 0:
            print(f"[TARS] pip install failed (exit {rc}). Run manually:\n  pip install -r {req_file}")
            sys.exit(rc)
        print("[TARS] Dependencies installed. Restarting...")
        _restart_self()

    # No requirements file — install from embedded list
    has_gpu = _has_nvidia_gpu()
    pip_cmd = [sys.executable, "-m", "pip", "install"]
    if has_gpu:
        print("[TARS] NVIDIA GPU detected — installing CUDA-accelerated packages")
        pip_cmd += ["--index-url", "https://download.pytorch.org/whl/cu124",
                    "--extra-index-url", "https://pypi.org/simple"]
    else:
        print("[TARS] No NVIDIA GPU detected — installing CPU packages")

    packages = [
        "torch", "fastapi>=0.104.0", "uvicorn[standard]>=0.24.0",
        "transformers>=4.44.0", "accelerate>=0.27.0",
        "Pillow>=10.0.0", "python-multipart",
        # Service-specific packages
        "faster-whisper>=1.0.0",    # STT
        "piper-tts>=1.2.0",         # TTS
        "diffusers>=0.27.0",        # ImageGen
        "sentence-transformers>=2.2.0",  # Embeddings
        "qrcode[pil]>=7.0",         # Tunnel QR codes
        "psutil>=5.9.0",             # System stats (CPU/RAM)
    ]
    if has_gpu:
        packages.append("bitsandbytes>=0.43.0")
        packages.append("torchaudio")  # VAD for STT

    rc = subprocess.call(pip_cmd + packages)
    if rc != 0:
        print(f"[TARS] pip install failed (exit {rc}).")
        print("[TARS] Try manually: pip install torch transformers fastapi uvicorn accelerate")
        sys.exit(rc)

    # llama-cpp-python is installed on-demand at runtime (see _ensure_llamacpp)
    # to avoid compiler requirements. Skipping it here.

    print("[TARS] Dependencies installed. Restarting...")
    _restart_self()

_bootstrap_deps()

import torch
import uvicorn
from fastapi import (
    FastAPI, File, Form, HTTPException, Request, UploadFile,
    WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Logging (console + rolling file)
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "server.log", maxBytes=5_000_000, backupCount=3
        ),
    ],
)
log = logging.getLogger("tars-server")

# Silence noisy third-party libraries (tied-weights warnings, generation flags, etc.)
for _lib in (
    "transformers", "diffusers", "huggingface_hub", "huggingface_hub.utils",
    "huggingface_hub.file_download", "sentence_transformers", "accelerate",
    "filelock", "urllib3", "httpx", "torch", "ctranslate2", "safetensors",
    "uvicorn", "uvicorn.error", "uvicorn.protocols", "websockets", "asyncio",
):
    logging.getLogger(_lib).setLevel(logging.ERROR)

# Suppress Python deprecation / future warnings from ML libraries
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Tell HuggingFace Hub to stay quiet
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

@contextlib.contextmanager
def _mute_output():
    """Suppress stdout/stderr at both Python and C/fd level during noisy model loading."""
    null_fd = -1
    saved_out = saved_err = -1
    devnull_py = None
    old_out, old_err = sys.stdout, sys.stderr
    try:
        null_fd = os.open(os.devnull, os.O_WRONLY)
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        os.dup2(null_fd, 1)
        os.dup2(null_fd, 2)
        os.close(null_fd)
        null_fd = -1
        devnull_py = open(os.devnull, "w")
        sys.stdout = sys.stderr = devnull_py
        yield
    finally:
        if devnull_py is not None:
            devnull_py.close()
        sys.stdout, sys.stderr = old_out, old_err
        if saved_out >= 0:
            os.dup2(saved_out, 1)
            os.close(saved_out)
        if saved_err >= 0:
            os.dup2(saved_err, 2)
            os.close(saved_err)
        if null_fd >= 0:
            os.close(null_fd)

# Silence ACE-Step loguru INFO spam (save_path, GPU memory, model loaded, etc.)
try:
    from loguru import logger as _loguru_logger
    _loguru_logger.remove()
    _loguru_logger.add(sys.stderr, level="WARNING")
except ImportError:
    pass


# ---------------------------------------------------------------------------
# GPU / Device helpers
# ---------------------------------------------------------------------------
def detect_device():
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        log.info(f"GPU detected: {name} ({vram:.1f} GB VRAM)")
        # TF32 gives ~20% free speedup on Ampere/Ada (RTX 30xx/40xx) with negligible precision loss
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        return "cuda"
    # Warn if NVIDIA GPU exists but torch lacks CUDA
    if _has_nvidia_gpu():
        log.warning(
            "NVIDIA GPU found but PyTorch lacks CUDA support!\n"
            "  Reinstall with: pip install torch --index-url https://download.pytorch.org/whl/cu124\n"
            "  Running on CPU for now (much slower)."
        )
    else:
        log.info("No GPU detected, using CPU")
    return "cpu"


DEVICE = detect_device()

# Cache static GPU info (these never change at runtime)
_GPU_NAME = torch.cuda.get_device_name(0) if DEVICE == "cuda" else ""
_VRAM_TOTAL_GB = torch.cuda.get_device_properties(0).total_memory / 1024**3 if DEVICE == "cuda" else 0
try:
    import psutil as _psutil
    _SHARED_TOTAL_GB = _psutil.virtual_memory().total / 1024**3 / 2  # Windows WDDM default
except Exception:
    _SHARED_TOTAL_GB = 0


_pynvml_handle = None

def _init_pynvml():
    """Initialize pynvml for fast GPU queries (no subprocess). Falls back to nvidia-smi."""
    global _pynvml_handle
    try:
        import pynvml
        pynvml.nvmlInit()
        _pynvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        log.info("pynvml initialized for GPU monitoring")
    except Exception:
        _pynvml_handle = None

if DEVICE == "cuda":
    _init_pynvml()

_smi_cache = {"result": None, "ts": 0.0}

def _gpu_vram():
    """Query GPU VRAM usage. Returns (used_gb, free_gb) or None.
    Prefers pynvml (direct driver query, ~100x faster than nvidia-smi subprocess).
    Falls back to nvidia-smi, cached for 3s."""
    # Fast path: pynvml
    if _pynvml_handle is not None:
        try:
            import pynvml
            info = pynvml.nvmlDeviceGetMemoryInfo(_pynvml_handle)
            return (info.used / 1024**3, info.free / 1024**3)
        except Exception:
            pass
    # Fallback: nvidia-smi subprocess (cached)
    now = time.time()
    if _smi_cache["result"] is not None and now - _smi_cache["ts"] < 3.0:
        return _smi_cache["result"]
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            used_mb, free_mb = float(parts[0].strip()), float(parts[1].strip())
            val = (used_mb / 1024, free_mb / 1024)
            _smi_cache["result"] = val
            _smi_cache["ts"] = now
            return val
    except Exception:
        pass
    return None


def get_gpu_stats() -> dict:
    if DEVICE != "cuda":
        return {}
    try:
        # pynvml / nvidia-smi sees ALL GPU consumers (torch + llama.cpp + others).
        # torch.cuda.memory_allocated only reports PyTorch's own allocations.
        vram = _gpu_vram()
        if vram is not None:
            allocated = vram[0]
            vram_free = vram[1]
            reserved = allocated
        else:
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            vram_free = max(_VRAM_TOTAL_GB - reserved, 0)

        ded_pct = allocated / _VRAM_TOTAL_GB * 100 if _VRAM_TOTAL_GB > 0 else 0
        # Shared GPU memory (Windows WDDM: overflow from VRAM into system RAM)
        shared_used = max(0, allocated - _VRAM_TOTAL_GB)
        shared_pct = shared_used / _SHARED_TOTAL_GB * 100 if _SHARED_TOTAL_GB > 0 else 0
        return {
            "name": _GPU_NAME,
            "vram_total_gb": round(_VRAM_TOTAL_GB, 2),
            "vram_allocated_gb": round(allocated, 2),
            "vram_reserved_gb": round(reserved, 2),
            "vram_free_gb": round(vram_free, 2),
            "vram_percent": round(min(ded_pct, 100), 1),
            "shared_total_gb": round(_SHARED_TOTAL_GB, 2),
            "shared_used_gb": round(shared_used, 2),
            "shared_percent": round(min(shared_pct, 100), 1),
        }
    except Exception:
        return {}


def get_system_stats() -> dict:
    """Return CPU and RAM usage stats (requires psutil)."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
            "ram_total_gb": round(vm.total / 1024**3, 2),
            "ram_used_gb": round(vm.used / 1024**3, 2),
            "ram_percent": round(vm.percent, 1),
        }
    except Exception:
        return {}



_LLAMACPP_MIN_VERSION = "0.3.8"  # Gemma 4 support requires ≥0.3.8


def _ensure_llamacpp():
    """Install llama-cpp-python with GPU support.

    Strategy:
      1. Already installed with GPU support AND meets min version → do nothing.
      2. Try bundled wheels in wheels/ directory (ships with the project).
      3. Try pre-built CUDA wheels from abetlen's index.
      4. Fall back to CPU pre-built wheel.
      No source builds — everything is pre-compiled.

    Uses a stamp file so a failed install isn't retried on every startup.
    Delete .llamacpp_install_failed to force a retry.
    """
    import importlib
    import subprocess
    from packaging.version import Version

    def _get_installed_version():
        try:
            importlib.invalidate_caches()
            import llama_cpp  # noqa: F401
            return getattr(llama_cpp, "__version__", None)
        except ImportError:
            return None

    def _has_gpu_support():
        try:
            from llama_cpp import llama_supports_gpu_offload
            return llama_supports_gpu_offload()
        except (ImportError, Exception):
            return False

    # Check current install
    ver = _get_installed_version()
    if ver:
        meets_version = Version(ver) >= Version(_LLAMACPP_MIN_VERSION)
        has_gpu = _has_gpu_support()
        if meets_version and (DEVICE != "cuda" or has_gpu):
            return  # Good to go
        if not meets_version:
            log.info(f"llama-cpp-python {ver} is too old (need >={_LLAMACPP_MIN_VERSION}) — upgrading...")
        elif not has_gpu:
            log.info("llama-cpp-python installed but CPU-only — attempting GPU upgrade...")
    else:
        log.info("llama-cpp-python not found — installing...")

    stamp = Path(__file__).parent / ".llamacpp_install_failed"
    if stamp.exists():
        log.warning(
            "llama-cpp-python install previously failed — skipping.\n"
            "  Delete .llamacpp_install_failed to retry.\n"
            "  GGUF models will not be available."
        )
        return

    def _uninstall():
        subprocess.call([sys.executable, "-m", "pip", "uninstall", "llama-cpp-python", "-y", "--quiet"])
        # Remove stale files that pip sometimes leaves behind on Windows
        import site, shutil
        for site_dir in site.getsitepackages():
            sp = Path(site_dir)
            if not sp.exists():
                continue
            for pattern in ("llama_cpp", "llama_cpp_python*"):
                for p in sp.glob(pattern):
                    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    def _try_local_wheels():
        """Install from bundled wheels in the wheels/ directory."""
        wheels_dir = Path(__file__).parent / "wheels"
        if not wheels_dir.exists():
            return False

        # Find matching wheel for this platform
        import platform
        py_ver = f"cp{sys.version_info.major}{sys.version_info.minor}"  # e.g. "cp311"
        plat = "win_amd64" if sys.platform == "win32" else "linux_x86_64"
        if platform.machine() == "aarch64":
            plat = "linux_aarch64"

        # Prefer CUDA wheels, then any wheel matching platform
        candidates = []
        for whl in sorted(wheels_dir.glob("llama_cpp_python-*.whl"), reverse=True):
            name = whl.name
            # Check Python version compatibility (py3-none or cpXYY)
            py_compat = (f"-{py_ver}-" in name or "-py3-none-" in name)
            plat_compat = plat in name
            if py_compat and plat_compat:
                candidates.append(whl)

        for whl in candidates:
            log.info(f"llama-cpp-python: installing bundled wheel {whl.name}...")
            rc = subprocess.call([
                sys.executable, "-m", "pip", "install", str(whl),
                "--force-reinstall", "--quiet",
            ])
            if rc == 0:
                return True
        return False

    def _try_remote_wheel(label, index_url, min_ver=None):
        log.info(f"llama-cpp-python: trying {label} pre-built wheel...")
        pkg = f"llama-cpp-python>={min_ver}" if min_ver else "llama-cpp-python"
        rc = subprocess.call([
            sys.executable, "-m", "pip", "install", pkg,
            "--extra-index-url", index_url,
            "--only-binary", ":all:",   # never compile from source
            "--force-reinstall",
            "--no-cache-dir",
            "--quiet",
        ])
        return rc == 0

    # Detect CUDA version from torch so we pick the right wheel index
    cuda_ver = None
    if DEVICE == "cuda":
        try:
            raw = torch.version.cuda  # e.g. "12.4"
            cuda_ver = "cu" + raw.replace(".", "")[:3]  # → "cu124"
        except Exception:
            pass

    _uninstall()
    installed = False

    # Step 1: Try bundled wheels (fastest, no network, no compiler)
    installed = _try_local_wheels()

    # Step 2: Try pre-built CUDA wheels from abetlen's index
    if not installed and cuda_ver:
        gpu_index = f"https://abetlen.github.io/llama-cpp-python/whl/{cuda_ver}"
        installed = _try_remote_wheel(f"CUDA {torch.version.cuda}", gpu_index, _LLAMACPP_MIN_VERSION)
        if not installed:
            installed = _try_remote_wheel(f"CUDA {torch.version.cuda} (any version)", gpu_index)
        if not installed:
            for fallback in ("cu128", "cu125", "cu124", "cu123", "cu122"):
                if fallback != cuda_ver:
                    fb_index = f"https://abetlen.github.io/llama-cpp-python/whl/{fallback}"
                    installed = _try_remote_wheel(f"CUDA fallback ({fallback})", fb_index)
                    if installed:
                        break

    # Step 3: Fall back to CPU wheel
    if not installed:
        _uninstall()
        installed = _try_remote_wheel("CPU", "https://abetlen.github.io/llama-cpp-python/whl/cpu")

    if installed:
        ver = _get_installed_version()
        log.info(f"llama-cpp-python {ver} installed successfully. Restarting...")
        _restart_self()
    else:
        stamp.write_text("Install failed — delete this file to retry.\n")
        log.warning(
            "llama-cpp-python could not be installed.\n"
            "  GGUF models will not be available.\n"
            "  Delete .llamacpp_install_failed to retry on next startup."
        )

# _ensure_llamacpp() is called on-demand when LLM backend is "llamacpp"


def resolve_service_device(cfg_value: str) -> str:
    """Resolve per-service device. 'auto' uses the globally detected device.
    Supports 'cuda:0', 'cuda:1', etc. for multi-GPU setups."""
    if cfg_value in ("auto", ""):
        return DEVICE
    # Validate cuda:N device exists
    if cfg_value.startswith("cuda:"):
        try:
            idx = int(cfg_value.split(":")[1])
            if torch.cuda.is_available() and idx < torch.cuda.device_count():
                return cfg_value
            else:
                log.warning(f"Device {cfg_value} not available (have {torch.cuda.device_count()} GPUs), falling back to {DEVICE}")
                return DEVICE
        except (ValueError, IndexError):
            pass
    return cfg_value


# ---------------------------------------------------------------------------
# Models directory
# ---------------------------------------------------------------------------
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_FILE = Path(__file__).parent / "config-server.ini"

_CONFIG_DEFAULTS = {
    "server":     {"port": "5678", "api_key": ""},
    "services":   {"stt": "true", "tts": "true", "llm": "true", "vision": "true",
                   "imagegen": "true", "musicgen": "false", "embeddings": "true"},
    "stt":        {"whisper_model": "large-v3", "compute_type": "auto", "vad_filter": "true", "device": "auto", "engine": "auto"},
    "llm":        {"model": "unsloth/gemma-4-E4B-it-GGUF",
                   "dtype": "auto", "quantize": "none", "kv_cache_quant_bits": "4",
                   "backend": "llamacpp",
                   "n_ctx": "16384", "n_gpu_layers": "-1",
                   "n_batch": "4096", "flash_attn": "true", "cache_type_k": "q8_0", "cache_type_v": "q8_0",
                   "kv_cache_sessions": "2", "kv_cache_ttl": "300", "device": "auto"},
    "tts":        {"voices_dir": "", "default_voice": "", "cache_size": "100"},
    "vision":     {"model": "Salesforce/blip-image-captioning-base", "device": "auto"},
    "imagegen":   {"model": "Lykon/dreamshaper-8", "default_steps": "15", "default_cfg": "7.0", "device": "auto"},
    "musicgen":   {"model": "ACE-Step/ACE-Step-v1-3.5B", "default_duration": "60", "default_steps": "60", "default_cfg": "15.0", "default_scheduler": "euler", "default_cfg_type": "apg", "default_omega_scale": "10.0", "default_guidance_interval": "0.5", "default_min_guidance": "3.0", "device": "auto"},
    "embeddings": {"model": "all-MiniLM-L6-v2", "device": "cpu"},
}

_active_config: configparser.ConfigParser = None


def load_config() -> configparser.ConfigParser:
    global _active_config
    cfg = configparser.ConfigParser()
    for section, values in _CONFIG_DEFAULTS.items():
        cfg[section] = values
    is_new = not CONFIG_FILE.exists()
    if CONFIG_FILE.exists():
        cfg.read(CONFIG_FILE)
    # Auto-generate API key on first boot
    if is_new and not cfg.get("server", "api_key", fallback=""):
        import secrets
        cfg["server"]["api_key"] = secrets.token_urlsafe(24)
        save_config(cfg)
        log.info(f"First boot — generated API key: {cfg['server']['api_key']}")
    _active_config = cfg
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    with open(CONFIG_FILE, "w") as f:
        cfg.write(f)
    log.info(f"Config saved to {CONFIG_FILE}")


# ---------------------------------------------------------------------------
# Request tracking (latency + history)
# ---------------------------------------------------------------------------
class RequestTracker:
    def __init__(self, max_history: int = 200):
        self.history: collections.deque = collections.deque(maxlen=max_history)
        self._service_stats: dict = {}  # service -> {"count": int, "total_ms": float}
        self._lock = Lock()

    def record(self, endpoint: str, method: str, status: int, latency_ms: float,
               service: str = None, llm_info: dict = None):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "method": method,
            "endpoint": endpoint,
            "status": status,
            "latency_ms": round(latency_ms, 1),
        }
        if llm_info:
            entry["llm"] = llm_info
        with self._lock:
            self.history.append(entry)
            if service:
                if service not in self._service_stats:
                    self._service_stats[service] = {"count": 0, "total_ms": 0.0}
                self._service_stats[service]["count"] += 1
                self._service_stats[service]["total_ms"] += latency_ms

    def get_latency_stats(self) -> dict:
        with self._lock:
            result = {}
            for svc, stats in self._service_stats.items():
                avg = stats["total_ms"] / stats["count"] if stats["count"] > 0 else 0
                result[svc] = {
                    "requests": stats["count"],
                    "avg_latency_ms": round(avg, 1),
                }
            return result

    def update_last_llm_info(self, llm_info: dict):
        """Attach LLM metrics to the most recent LLM entry that has none yet."""
        with self._lock:
            for entry in reversed(self.history):
                if "/v1/chat/completions" in entry.get("endpoint", "") and "llm" not in entry:
                    entry["llm"] = llm_info
                    break

    def get_recent(self, n: int = 50) -> list:
        with self._lock:
            if n >= len(self.history):
                return list(self.history)
            return [self.history[i] for i in range(len(self.history) - n, len(self.history))]


TRACKER = RequestTracker()


class LLMMetrics:
    """Tracks LLM inference metrics (tokens/sec, TTFT, request counts)."""

    def __init__(self, max_samples: int = 100):
        self._lock = Lock()
        self._samples: collections.deque = collections.deque(maxlen=max_samples)
        self._total_requests = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._errors = 0
        self._last = None

    def pop_last(self):
        """Return and clear the last recorded LLM info (for attaching to request log)."""
        with self._lock:
            info = self._last
            self._last = None
            return info

    def record(self, prompt_tokens: int, completion_tokens: int, decode_ms: float, ttft_ms: float = 0):
        tps = completion_tokens / (decode_ms / 1000) if decode_ms > 0 else 0
        info = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "decode_ms": round(decode_ms, 1),
            "ttft_ms": round(ttft_ms, 1),
            "tokens_per_sec": round(tps, 1),
        }
        with self._lock:
            self._samples.append({"time": datetime.now().strftime("%H:%M:%S"), **info})
            self._total_requests += 1
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._last = info

    def record_error(self):
        with self._lock:
            self._errors += 1

    def get_stats(self) -> dict:
        with self._lock:
            if not self._samples:
                return {"requests": 0}
            recent = list(self._samples)
            tps_vals = [s["tokens_per_sec"] for s in recent if s["tokens_per_sec"] > 0]
            ttft_vals = [s["ttft_ms"] for s in recent if s["ttft_ms"] > 0]
            return {
                "requests": self._total_requests,
                "errors": self._errors,
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "avg_tokens_per_sec": round(sum(tps_vals) / len(tps_vals), 1) if tps_vals else 0,
                "p50_tokens_per_sec": round(sorted(tps_vals)[len(tps_vals) // 2], 1) if tps_vals else 0,
                "avg_ttft_ms": round(sum(ttft_vals) / len(ttft_vals), 1) if ttft_vals else 0,
                "p50_ttft_ms": round(sorted(ttft_vals)[len(ttft_vals) // 2], 1) if ttft_vals else 0,
                "last_10": recent[-10:],
            }


LLM_METRICS = LLMMetrics()

# Map endpoint prefixes to service names for latency tracking
_ENDPOINT_SERVICE = {
    "/save_audio": "stt", "/transcribe": "stt", "/ws/stt": "stt",
    "/v1/chat/completions": "llm",
    "/tts/": "tts",
    "/caption": "vision",
    "/sdapi/": "imagegen", "/generate_image": "imagegen",
    "/generate_music": "musicgen", "/musicgen_gallery": "musicgen",
    "/v1/embeddings": "embeddings",
}


def _endpoint_to_service(path: str) -> Optional[str]:
    # Fast path: check first path segment (covers most cases without full scan)
    for prefix, svc in _ENDPOINT_SERVICE.items():
        if path.startswith(prefix):
            return svc
    return None


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------
SERVICES: dict = {}
_SERVICE_VRAM: dict = {}  # service_name -> vram_gb (measured delta at load time)
START_TIME = time.time()
_LAUNCH_ARGS = None
_LLM_SEMAPHORE: asyncio.Semaphore = None  # initialized at startup
_llm_oom_count = 0          # consecutive OOM restarts (reset after 60s quiet)
_llm_oom_last = 0.0         # timestamp of last OOM

# Dedicated thread pool for ML inference — default pool is too small (min(32, os.cpu_count()+4))
from concurrent.futures import ThreadPoolExecutor
_INFERENCE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tars-inference")

# ===================================================================
# STT Service (sherpa-onnx preferred, faster-whisper fallback + Silero VAD)
# ===================================================================

_SENSEVOICE_MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
_SENSEVOICE_DIR_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
_SILERO_VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"

import re as _re
_SENSEVOICE_TAG_RE = _re.compile(r"<\|[^|]*\|>")


class STTService:
    def __init__(self, model_size: str = "large-v3", compute_type: str = "auto",
                 vad_filter: bool = True, device: str = None, engine: str = "auto"):
        device = device or DEVICE
        self.model_name = model_size
        self._engine = self._resolve_engine(engine)
        log.info(f"STT engine: {self._engine}")

        self.model = None
        self._recognizer = None
        self._vad_model = None
        self._vad_utils = None
        self._vad_lock = Lock()

        if self._engine == "llm":
            # No separate STT model — transcription routed to LLM at request time
            self.model_name = "via LLM"
            log.info("STT: using LLM for transcription (no separate STT model loaded)")
        elif self._engine == "sherpa-onnx":
            self._init_sherpa()
        else:
            self._init_faster_whisper(model_size, compute_type, device)

        # Silero VAD for pre-filtering
        if vad_filter and self._engine != "llm":
            if self._engine == "sherpa-onnx":
                self._load_sherpa_vad()
            else:
                self._load_vad()

    @staticmethod
    def _resolve_engine(engine: str) -> str:
        if engine == "llm":
            return "llm"
        if engine == "sherpa-onnx":
            return "sherpa-onnx"
        if engine in ("faster-whisper", "faster_whisper"):
            return "faster-whisper"
        # auto: prefer sherpa-onnx (cross-platform, no CTranslate2), fall back to faster-whisper
        try:
            import sherpa_onnx  # noqa: F401
            return "sherpa-onnx"
        except ImportError:
            pass
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            return "faster-whisper"
        except ImportError:
            pass
        # Neither installed — try sherpa-onnx first
        import subprocess as _sp
        log.info("STT: installing sherpa-onnx...")
        rc = _sp.call([sys.executable, "-m", "pip", "install", "sherpa-onnx", "--quiet"])
        if rc == 0:
            return "sherpa-onnx"
        return "faster-whisper"

    # -- sherpa-onnx init (SenseVoiceTiny — same as TARS client) -----------

    def _init_sherpa(self):
        import sherpa_onnx

        stt_dir = MODELS_DIR / "stt"
        stt_dir.mkdir(exist_ok=True)
        model_dir = stt_dir / _SENSEVOICE_DIR_NAME

        # Auto-download SenseVoiceTiny if not present
        if not model_dir.exists() or not (model_dir / "model.int8.onnx").exists():
            self._download_sensevoice(stt_dir)

        model_file = str(model_dir / "model.int8.onnx")
        tokens_file = str(model_dir / "tokens.txt")

        if not os.path.isfile(model_file):
            raise RuntimeError(f"SenseVoice model not found: {model_file}")

        num_threads = min(4, os.cpu_count() or 2)
        log.info(f"Loading sherpa-onnx SenseVoiceTiny (threads={num_threads})...")

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_file,
            tokens=tokens_file,
            num_threads=num_threads,
            use_itn=True,
            debug=False,
        )
        self.model = self._recognizer
        self.model_name = "SenseVoiceTiny"
        log.info("sherpa-onnx SenseVoiceTiny loaded.")

    def _download_sensevoice(self, stt_dir: Path):
        """Download and extract SenseVoiceTiny model."""
        import urllib.request, tarfile
        archive_path = stt_dir / "sensevoice.tar.bz2"
        log.info("Downloading SenseVoiceTiny model (~1GB)...")
        try:
            urllib.request.urlretrieve(_SENSEVOICE_MODEL_URL, str(archive_path))
            log.info("Extracting SenseVoiceTiny...")
            with tarfile.open(str(archive_path), "r:bz2") as tar:
                tar.extractall(path=str(stt_dir))
            archive_path.unlink(missing_ok=True)
            log.info("SenseVoiceTiny model installed.")
        except Exception as e:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download SenseVoiceTiny: {e}")

    def _load_sherpa_vad(self):
        """Load Silero VAD via sherpa-onnx's native implementation."""
        try:
            import sherpa_onnx
            vad_path = MODELS_DIR / "stt" / "silero_vad.onnx"
            if not vad_path.exists():
                import urllib.request
                log.info("Downloading Silero VAD for sherpa-onnx...")
                urllib.request.urlretrieve(_SILERO_VAD_URL, str(vad_path))

            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = str(vad_path)
            vad_config.silero_vad.threshold = 0.3
            vad_config.silero_vad.min_speech_duration = 0.1
            vad_config.silero_vad.min_silence_duration = 0.3
            vad_config.sample_rate = 16000

            self._sherpa_vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)
            log.info("Silero VAD loaded (sherpa-onnx native)")
        except Exception as e:
            self._sherpa_vad = None
            log.warning(f"sherpa-onnx VAD not available ({e}), skipping pre-filter")

    # -- faster-whisper init -----------------------------------------------

    def _init_faster_whisper(self, model_size: str, compute_type: str, device: str):
        from faster_whisper import WhisperModel

        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        log.info(f"Loading Whisper model: {model_size} (compute: {compute_type}, device: {device})...")
        whisper_dir = MODELS_DIR / "whisper"
        whisper_dir.mkdir(exist_ok=True)
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(whisper_dir),
        )
        self._recognizer = None
        log.info("Whisper model loaded.")

    # -- VAD ---------------------------------------------------------------

    def _load_vad(self):
        try:
            with open(os.devnull, "w") as _devnull, \
                 contextlib.redirect_stdout(_devnull), \
                 contextlib.redirect_stderr(_devnull):
                model, utils = torch.hub.load(
                    "snakers4/silero-vad", "silero_vad",
                    trust_repo=True, verbose=False,
                )
            self._vad_model = model
            self._vad_utils = utils
            log.info("Silero VAD loaded for speech pre-filtering")
        except Exception as e:
            log.warning(f"Silero VAD not available ({e}), skipping pre-filter")

    def has_speech(self, audio_bytes: BytesIO, samples=None) -> bool:
        """Check if audio contains speech using Silero VAD.
        If `samples` (float32 numpy array at 16kHz) is provided, skip re-decoding.
        """
        if self._engine == "llm":
            return True  # let the LLM decide
        # sherpa-onnx native VAD (locked — not thread-safe)
        if self._engine == "sherpa-onnx" and getattr(self, "_sherpa_vad", None):
            try:
                if samples is None:
                    samples = self._wav_to_float32(audio_bytes)
                if samples is None:
                    return True
                with self._vad_lock:
                    self._sherpa_vad.accept_waveform(samples)
                    self._sherpa_vad.flush()
                    has = not self._sherpa_vad.empty()
                    while not self._sherpa_vad.empty():
                        self._sherpa_vad.pop()
                    self._sherpa_vad.reset()
                return has
            except Exception:
                return True
        # torch-based Silero VAD (for faster-whisper engine)
        if not self._vad_model:
            return True
        try:
            get_speech_ts = self._vad_utils[0]
            if samples is not None:
                wav_tensor = torch.from_numpy(samples)
            else:
                audio_bytes.seek(0)
                wav_tensor = self._wav_bytes_to_tensor(audio_bytes)
            if wav_tensor is None:
                return True
            timestamps = get_speech_ts(wav_tensor, self._vad_model,
                                       sampling_rate=16000, threshold=0.3,
                                       min_speech_duration_ms=100)
            return len(timestamps) > 0
        except Exception:
            return True

    @staticmethod
    def _wav_to_float32(audio_bytes: BytesIO):
        """Convert audio BytesIO (any format) to float32 numpy array at 16kHz."""
        import numpy as np
        audio_bytes.seek(0)
        # Try WAV first (fast, no ffmpeg dependency)
        try:
            with wave.open(audio_bytes, "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw = wf.readframes(n_frames)
            if n_frames > 0 and raw and sampwidth in (1, 2, 4):
                if sampwidth == 2:
                    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                if n_channels > 1:
                    samples = samples[::n_channels]
                if sr != 16000:
                    new_len = int(len(samples) * 16000 / sr)
                    if new_len < 1:
                        return None
                    indices = np.linspace(0, len(samples) - 1, new_len)
                    samples = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)
                audio_bytes.seek(0)
                return samples
        except Exception:
            pass
        # Fallback: use faster-whisper's ffmpeg-based decoder (handles WebM, Opus, etc.)
        audio_bytes.seek(0)
        try:
            from faster_whisper.audio import decode_audio
            samples = decode_audio(audio_bytes)
            audio_bytes.seek(0)
            return samples
        except Exception:
            pass
        audio_bytes.seek(0)
        return None

    def _wav_bytes_to_tensor(self, audio_bytes: BytesIO) -> Optional[torch.Tensor]:
        """Convert WAV BytesIO to a float32 tensor at 16kHz."""
        try:
            audio_bytes.seek(0)
            with wave.open(audio_bytes, "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                raw = wf.readframes(n_frames)
            if n_frames == 0 or not raw:
                return None
            n_samples = n_frames * n_channels
            if sampwidth == 1:
                samples = struct.unpack(f"<{n_samples}B", raw)
                tensor = (torch.FloatTensor(samples) - 128.0) / 128.0
            elif sampwidth == 2:
                samples = struct.unpack(f"<{n_samples}h", raw)
                tensor = torch.FloatTensor(samples) / 32768.0
            elif sampwidth == 3:
                import numpy as np
                a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
                i32 = (a[:, 0].astype(np.int32)
                       | (a[:, 1].astype(np.int32) << 8)
                       | (a[:, 2].astype(np.int32) << 16))
                i32[i32 >= 0x800000] -= 0x1000000
                tensor = torch.from_numpy(i32.astype(np.float32)) / 8388608.0
            elif sampwidth == 4:
                samples = struct.unpack(f"<{n_samples}f", raw)
                tensor = torch.FloatTensor(samples)
                if tensor.isnan().any() or tensor.isinf().any() or tensor.abs().max() > 2.0:
                    samples = struct.unpack(f"<{n_samples}i", raw)
                    tensor = torch.FloatTensor(samples) / 2147483648.0
            else:
                return None
            if n_channels > 1:
                tensor = tensor[::n_channels]
            if sr != 16000:
                import numpy as np
                ratio = 16000 / sr
                new_len = int(len(tensor) * ratio)
                if new_len < 1:
                    return None
                indices = torch.linspace(0, len(tensor) - 1, new_len)
                tensor = torch.from_numpy(
                    np.interp(indices.numpy(), np.arange(len(tensor)), tensor.numpy())
                ).float()
            audio_bytes.seek(0)
            return tensor
        except Exception:
            audio_bytes.seek(0)
            return None

    # -- Transcription dispatch --------------------------------------------

    def transcribe(self, audio_bytes: BytesIO, language: str = None, samples=None):
        if self._engine == "sherpa-onnx":
            return self._transcribe_sherpa(audio_bytes, language, samples=samples)
        return self._transcribe_faster_whisper(audio_bytes, language)

    def _transcribe_llm(self, audio_bytes: BytesIO, language: str = None):
        """Transcribe using the loaded LLM. Returns (results, info).

        Delegates to llm.transcribe_audio() — the implementation varies by backend:
          - LLMService (transformers): direct audio-to-text via AutoProcessor
          - LlamaCppService: two-stage pipeline (sherpa-onnx raw STT → LLM cleanup)
        """
        if "llm" not in SERVICES:
            return [], _SherpaInfo("", 0.0)
        llm = SERVICES["llm"]
        if not hasattr(llm, "transcribe_audio"):
            raise RuntimeError(
                "STT is set to 'Use LLM' but the loaded LLM backend has no transcribe_audio method."
            )
        text = llm.transcribe_audio(audio_bytes, language)
        if not text:
            return [], _SherpaInfo("", 0.0)
        # Estimate duration from audio
        samples = self._wav_to_float32(audio_bytes)
        duration = len(samples) / 16000.0 if samples is not None else 0.0
        segments = [{"text": text, "start": 0.0, "end": round(duration, 3)}]
        return segments, _SherpaInfo(language or "en", 1.0)

    def _transcribe_sherpa(self, audio_bytes: BytesIO, language: str = None, samples=None):
        """Transcribe using sherpa-onnx SenseVoice. Returns (results, info) matching faster-whisper interface."""
        if samples is None:
            samples = self._wav_to_float32(audio_bytes)
        if samples is None:
            log.warning("sherpa-onnx STT: _wav_to_float32 returned None")
            return [], _SherpaInfo("", 0.0)

        log.info(f"sherpa-onnx STT: {len(samples)} samples ({len(samples)/16000:.1f}s), "
                 f"dtype={samples.dtype}, range=[{samples.min():.3f}, {samples.max():.3f}]")

        s = self._recognizer.create_stream()
        s.accept_waveform(16000, samples)
        self._recognizer.decode_stream(s)

        raw_text = s.result.text.strip()
        log.info(f"sherpa-onnx STT raw: [{raw_text}]")
        del s  # free native stream

        # Detect language from SenseVoice tags like <|en|>, <|HAPPY|>, <|Speech|>
        detected_lang = ""
        lang_match = _re.search(r"<\|(\w{2})\|>", raw_text)
        if lang_match:
            detected_lang = lang_match.group(1)

        # Strip all SenseVoice tags
        text = _SENSEVOICE_TAG_RE.sub("", raw_text).strip()

        if not text:
            return [], _SherpaInfo("", 0.0)

        duration = len(samples) / 16000.0
        segments = [{"text": text, "start": 0.0, "end": round(duration, 3)}]
        return segments, _SherpaInfo(detected_lang or "en", 1.0 if detected_lang else 0.5)

    def _transcribe_faster_whisper(self, audio_bytes: BytesIO, language: str = None):
        kwargs = {"beam_size": 1}
        if language:
            kwargs["language"] = language
        segments, info = self.model.transcribe(audio_bytes, **kwargs)
        results = [
            {"text": s.text.strip(), "start": round(s.start, 3), "end": round(s.end, 3)}
            for s in segments
        ]
        return results, info

    def unload(self):
        self.model = None
        self._recognizer = None
        self._vad_model = None
        self._vad_utils = None
        if hasattr(self, "_sherpa_vad"):
            self._sherpa_vad = None


class _SherpaInfo:
    """Minimal info object matching faster-whisper's transcription info interface."""
    def __init__(self, language: str, language_probability: float):
        self.language = language
        self.language_probability = language_probability


# ===================================================================
# TTS Service (Piper ONNX + cache)
# ===================================================================
class TTSService:
    _DEFAULT_VOICE_URLS = {
        "TARS.onnx": "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx",
        "TARS.onnx.json": "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx.json",
    }

    def __init__(self, voices_dir: str = None, cache_size: int = 100, engine: str = "auto"):
        self.voices_dir = Path(voices_dir) if voices_dir else Path(__file__).parent / "models" / "tts"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._voices: dict = {}
        self._loaded_voices: dict = {}
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._cache_max = cache_size
        self.engine = "piper"
        self._ensure_default_voice()
        self._scan_voices()
        # Pre-load the default voice so first TTS request is fast
        if self._voices:
            default = list(self._voices.keys())[0]
            try:
                self._get_piper_voice(default)
                log.info(f"Pre-loaded default Piper voice: {default}")
            except Exception as e:
                log.warning(f"Failed to pre-load default voice: {e}")

    def _ensure_default_voice(self):
        """Download the default TARS Piper voice if no .onnx files exist yet."""
        if any(self.voices_dir.rglob("*.onnx")):
            return

        import urllib.request
        for filename, url in self._DEFAULT_VOICE_URLS.items():
            dest = self.voices_dir / filename
            if dest.exists():
                continue
            log.info(f"Downloading default Piper voice: {filename} ...")
            try:
                urllib.request.urlretrieve(url, str(dest))
                log.info(f"  -> saved to {dest}")
            except Exception as e:
                log.warning(f"Failed to download {filename}: {e}")
                if dest.exists():
                    dest.unlink()  # remove partial download

    def _scan_voices(self):
        self._voices = {}

        # Collect all directories to scan: primary voices_dir + src/character/*/voice/
        scan_dirs = [self.voices_dir]
        char_root = Path(__file__).parent.parent / "src" / "character"
        if char_root.exists():
            for voice_dir in sorted(char_root.glob("*/voice")):
                if voice_dir.is_dir():
                    scan_dirs.append(voice_dir)

        for scan_dir in scan_dirs:
            for json_file in scan_dir.glob("*.onnx.json"):
                onnx_file = json_file.parent / json_file.name[:-5]  # "Name.onnx.json" -> "Name.onnx"
                if not onnx_file.exists():
                    continue  # .onnx not present — skip silently
                name = onnx_file.stem
                if name not in self._voices:
                    self._voices[name] = {"model": str(onnx_file), "config": str(json_file)}

        log.info(f"Found {len(self._voices)} Piper voice(s): {list(self._voices.keys())}")

    def list_voices(self) -> list[str]:
        return list(self._voices.keys())

    def synthesize(self, text: str, voice: str = None, speed: float = 1.0) -> bytes:
        cache_key = hashlib.sha256(f"{text}|{voice}|{speed}".encode()).hexdigest()
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        wav_bytes = self._do_synthesize(text, voice, speed)

        self._cache[cache_key] = wav_bytes
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

        return wav_bytes

    def _get_piper_voice(self, voice: str):
        """Get or load a PiperVoice model — cached in memory after first load."""
        if voice in self._loaded_voices:
            return self._loaded_voices[voice]
        try:
            from piper.voice import PiperVoice
        except ImportError:
            raise RuntimeError("piper-tts not installed. Install with: pip install piper-tts")
        voice_info = self._voices[voice]
        log.info(f"Loading Piper voice into memory: {voice}")
        piper_voice = PiperVoice.load(voice_info["model"])
        self._loaded_voices[voice] = piper_voice
        return piper_voice

    def _do_synthesize(self, text: str, voice: str, speed: float) -> bytes:
        import wave as wave_mod

        if not voice and self._voices:
            voice = list(self._voices.keys())[0]
        if voice not in self._voices:
            available = ", ".join(self._voices.keys()) if self._voices else "none"
            raise ValueError(f"Voice '{voice}' not found. Available: {available}")

        piper_voice = self._get_piper_voice(voice)
        wav_buf = BytesIO()
        with wave_mod.open(wav_buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(piper_voice.config.sample_rate)
            synth_kwargs = {}
            if speed != 1.0:
                synth_kwargs["length_scale"] = 1.0 / speed
            try:
                if hasattr(piper_voice, "synthesize_wav"):
                    piper_voice.synthesize_wav(text, wav_file, **synth_kwargs)
                else:
                    piper_voice.synthesize(text, wav_file, **synth_kwargs)
            except TypeError:
                # Older piper-tts without length_scale param
                if hasattr(piper_voice, "synthesize_wav"):
                    piper_voice.synthesize_wav(text, wav_file)
                else:
                    piper_voice.synthesize(text, wav_file)
        return wav_buf.getvalue()

    def synthesize_streaming(self, text: str, voice: str = None, speed: float = 1.0):
        """Split text on sentence boundaries and yield WAV bytes per sentence.
        Callers get the first audio chunk in ~50ms instead of waiting for the full response.
        """
        import re as _re_tts
        # Split on sentence-ending punctuation followed by whitespace (or end of string)
        sentences = [s.strip() for s in _re_tts.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not sentences:
            return
        for sentence in sentences:
            yield self.synthesize(sentence, voice=voice, speed=speed)

    def unload(self):
        self._cache.clear()
        self._loaded_voices.clear()


# ===================================================================
# LLM Service (transformers + token counting + KV cache)
# ===================================================================
class LLMService:
    def __init__(self, model_name: str = "Qwen/Qwen3-4B", dtype: str = "auto",
                 quantize: str = "none", kv_cache_quant_bits: int = 4,
                 kv_cache_sessions: int = 2, kv_cache_ttl: int = 300, device: str = None):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # Parse combined quantize modes: "turbo", "turbo+4bit", "turbo+8bit", "4bit", "8bit", "none"
        use_turboquant = False
        weight_quant = "none"
        if "turbo" in quantize:
            use_turboquant = True
            if "4bit" in quantize:
                weight_quant = "4bit"
            elif "8bit" in quantize:
                weight_quant = "8bit"
        elif quantize in ("4bit", "8bit"):
            weight_quant = quantize

        device = device or DEVICE

        if dtype == "auto":
            # Prefer bfloat16 on Ampere+ (RTX 30xx/40xx) for better numerics at same speed
            if device == "cuda" and torch.cuda.is_bf16_supported():
                dtype = torch.bfloat16
            elif device == "cuda":
                dtype = torch.float16
            else:
                dtype = torch.float32
        elif dtype == "float16":
            dtype = torch.float16
        elif dtype == "bfloat16":
            dtype = torch.bfloat16
        else:
            dtype = torch.float32

        log.info(f"Loading LLM: {model_name} (dtype: {dtype}, device: {device}, quantize: {quantize}"
                 f"{f', kv_cache_quant_bits: {kv_cache_quant_bits}' if use_turboquant else ''})...")
        self.model_name = model_name
        self._dtype = dtype
        llm_dir = MODELS_DIR / "llm"
        llm_dir.mkdir(exist_ok=True)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, trust_remote_code=True, cache_dir=str(llm_dir)
        )
        if device == "cuda" and not torch.cuda.is_available():
            log.warning("CUDA requested but torch.cuda.is_available() = False. "
                        "Install CUDA PyTorch: pip install torch --index-url https://download.pytorch.org/whl/cu124")
            device = "cpu"
            dtype = torch.float32
            quantize = "none"
            use_turboquant = False
            weight_quant = "none"

        # Only use device_map="auto" for quantized models (BnB requires it).
        # For non-quantized, use explicit .to(device) — avoids accelerate dispatch overhead.
        _use_device_map = False
        load_kwargs = dict(
            trust_remote_code=True, cache_dir=str(llm_dir),
        )

        # Weight quantization (requires: pip install bitsandbytes)
        if weight_quant in ("4bit", "8bit") and device == "cuda":
            try:
                from transformers import BitsAndBytesConfig
                if weight_quant == "4bit":
                    load_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=dtype,
                        bnb_4bit_use_double_quant=True,
                        bnb_4bit_quant_type="nf4",
                    )
                else:
                    load_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
                load_kwargs["device_map"] = "auto"  # Required for BnB
                _use_device_map = True
                log.info(f"LLM weight quantization: {weight_quant}")
            except ImportError:
                log.warning("bitsandbytes not installed — quantization skipped. pip install bitsandbytes")
                load_kwargs["dtype"] = dtype
        else:
            load_kwargs["dtype"] = dtype


        # Try attention backends from fastest to most compatible
        attn_impls = (["flash_attention_2", "sdpa"] if device == "cuda" else ["sdpa"])
        self.model = None
        last_exc = None
        for attn in attn_impls + [None]:
            try:
                kw = {**load_kwargs, **({"attn_implementation": attn} if attn else {})}
                self.model = AutoModelForCausalLM.from_pretrained(model_name, **kw)
                if attn:
                    log.info(f"LLM attention: {attn}")
                break
            except Exception as e:
                last_exc = e
                log.debug(f"LLM load attempt (attn={attn}) failed: {e}")
                continue
        if self.model is None:
            raise RuntimeError(f"LLM failed to load: {last_exc}") from last_exc
        # Place model on device — skip if accelerate already did it (device_map="auto")
        if not _use_device_map:
            self.model = self.model.to(device)
        self.model.eval()

        # Log actual device after load
        try:
            first_param = next(self.model.parameters())
            actual_device = first_param.device
            log.info(f"LLM loaded — actual device: {actual_device} | dtype: {first_param.dtype}")
            if device == "cuda" and actual_device.type != "cuda":
                log.warning("LLM ended up on CPU despite CUDA request! "
                            "Run: pip install torch --index-url https://download.pytorch.org/whl/cu124")
        except Exception:
            pass

        # torch.compile: on Linux use reduce-overhead+static cache (CUDA graphs, 2-3x speedup).
        # On Windows, Triton is unavailable so inductor falls back to "default" mode (~10-15%
        # speedup via kernel fusion, no CUDA graphs). Both paths are worth enabling.
        self._compiled = False
        if device == "cuda" and weight_quant in ("none", ""):
            try:
                _orig_model = self.model
                if sys.platform != "win32":
                    self.model.generation_config.cache_implementation = "static"
                    compile_mode = "reduce-overhead"
                    compile_fullgraph = True
                else:
                    compile_mode = "default"
                    compile_fullgraph = False
                self.model = torch.compile(self.model, mode=compile_mode, fullgraph=compile_fullgraph)
                # Test with actual inference to catch compile errors early
                _warm = self.tokenizer("compile test", return_tensors="pt").input_ids.to(device)
                with torch.inference_mode():
                    self.model.generate(_warm, attention_mask=torch.ones_like(_warm),
                                        max_new_tokens=2, do_sample=False, use_cache=True)
                self._compiled = True
                log.info(f"LLM torch.compile enabled (mode={compile_mode})")
            except Exception as e:
                log.info(f"torch.compile skipped: {e}")
                self.model = _orig_model
                if sys.platform != "win32":
                    self.model.generation_config.cache_implementation = None

        # Warmup: run a forward pass to pre-allocate CUDA memory
        if device == "cuda":
            try:
                _warm = self.tokenizer("warmup", return_tensors="pt").input_ids.to(self.model.device)
                with torch.inference_mode():
                    self.model.generate(_warm, attention_mask=torch.ones_like(_warm),
                                        max_new_tokens=2, do_sample=False, use_cache=True)
                log.info("LLM warmup complete")
            except Exception as e:
                log.debug(f"Warmup issue: {e}")

        # TurboQuant KV cache compression (reduces VRAM for long-context models)
        self._turboquant_active = False
        self._turboquant_bits = kv_cache_quant_bits
        if use_turboquant and device == "cuda":
            try:
                # NumPy 2.0 removed np.trapz → np.trapezoid; turboquant still uses the old name
                import numpy as _np
                if not hasattr(_np, "trapz") and hasattr(_np, "trapezoid"):
                    _np.trapz = _np.trapezoid
                from turboquant import TurboQuantCache
                # Test that we can create a cache (validates install)
                _test = TurboQuantCache(bits=kv_cache_quant_bits)
                del _test
                self._turboquant_active = True
                log.info(f"TurboQuant KV cache compression enabled ({kv_cache_quant_bits}-bit)")
            except ImportError:
                log.warning("turboquant not installed — KV cache compression skipped. "
                            "pip install turboquant")
            except Exception as e:
                log.warning(f"TurboQuant init failed: {e}")

        # KV cache for prompt reuse
        self._kv_cache: dict = {}  # session_id -> (token_count, past_kv, timestamp, prefix_list)
        self._kv_max_sessions = kv_cache_sessions
        self._kv_ttl = kv_cache_ttl
        self._kv_lock = Lock()

        # System-prompt prefix cache: caches the KV states for just the system prompt so that
        # the first user turn doesn't need to re-prefill the entire system prompt.
        # Key: sha256 of the system prompt text; Value: (token_count, past_kv, token_ids_list)
        self._sys_prefix_cache: dict = {}  # hash -> (token_len, past_kv, token_ids)
        self._sys_prefix_lock = Lock()

        # Multimodal detection
        self.supports_vision = self._check_vision_support()
        if self.supports_vision:
            log.info("LLM has vision capability")
        log.info(f"LLM loaded: {model_name}")

    def _make_turboquant_cache(self):
        """Create a fresh TurboQuantCache if turbo mode is active."""
        if not self._turboquant_active:
            return None
        from turboquant import TurboQuantCache
        return TurboQuantCache(bits=self._turboquant_bits)

    def _get_system_prompt(self, messages: list) -> str:
        """Extract the system prompt text from a messages list, or '' if absent."""
        for m in messages:
            if m.get("role") == "system":
                return m.get("content", "")
        return ""

    def _prime_sys_prefix(self, sys_text: str):
        """Prefill and cache KV states for `sys_text` if not already cached.
        Returns (cached_len, past_kv) or (0, None) if unavailable/unsupported.
        """
        if not sys_text:
            return 0, None
        key = hashlib.sha256(sys_text.encode()).hexdigest()
        with self._sys_prefix_lock:
            if key in self._sys_prefix_cache:
                return self._sys_prefix_cache[key][0], self._sys_prefix_cache[key][1]

        # Build a minimal single-message chat for the system prompt only
        try:
            template_kwargs = dict(return_tensors="pt", add_generation_prompt=False)
            try:
                result = self.tokenizer.apply_chat_template(
                    [{"role": "system", "content": sys_text}],
                    enable_thinking=False, **template_kwargs
                )
            except TypeError:
                result = self.tokenizer.apply_chat_template(
                    [{"role": "system", "content": sys_text}], **template_kwargs
                )
            sys_ids = (result if isinstance(result, torch.Tensor) else result["input_ids"]).to(self.model.device)

            with torch.inference_mode():
                out = self.model(input_ids=sys_ids, use_cache=True, return_dict=True)
            past_kv = out.past_key_values
            token_len = sys_ids.shape[-1]
            token_ids = sys_ids[0].tolist()
            with self._sys_prefix_lock:
                self._sys_prefix_cache[key] = (token_len, past_kv, token_ids)
            log.info(f"LLM system-prefix cached ({token_len} tokens, key={key[:8]})")
            return token_len, past_kv
        except Exception as e:
            log.debug(f"System-prefix cache skipped: {e}")
            return 0, None

    def _try_reuse_sys_prefix(self, full_ids: torch.Tensor, messages: list):
        """Try to reuse the cached system-prompt KV for a fresh (no session) request.
        Returns (input_ids_to_process, past_kv_or_None).
        """
        sys_text = self._get_system_prompt(messages)
        if not sys_text:
            return full_ids, None
        key = hashlib.sha256(sys_text.encode()).hexdigest()
        with self._sys_prefix_lock:
            entry = self._sys_prefix_cache.get(key)
        if entry is None:
            # Not cached yet — prime it in background for next request
            Thread(target=self._prime_sys_prefix, args=(sys_text,), daemon=True).start()
            return full_ids, None
        cached_len, past_kv, cached_ids = entry
        # Verify the prefix tokens match (tokeniser may differ between calls)
        if full_ids.shape[-1] > cached_len and full_ids[0, :cached_len].tolist() == cached_ids:
            return full_ids[:, cached_len:], past_kv
        return full_ids, None

    def _check_vision_support(self) -> bool:
        model_lower = self.model_name.lower()
        vision_indicators = ["vl", "vision", "llava", "cogvlm", "internvl", "minicpm-v"]
        if any(ind in model_lower for ind in vision_indicators):
            return True
        config = getattr(self.model, "config", None)
        if config and hasattr(config, "vision_config"):
            return True
        return False

    def caption_image(self, image_bytes: bytes, prompt: str = None) -> str:
        prompt = prompt or "Describe this image."
        if not self.supports_vision:
            raise RuntimeError("This LLM does not support vision")
        from PIL import Image
        from transformers import AutoProcessor
        processor = AutoProcessor.from_pretrained(
            self.model_name, trust_remote_code=True, cache_dir=str(MODELS_DIR / "llm"),
        )
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ]}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=text, images=image, return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            output_ids = self.model.generate(**inputs, max_new_tokens=200)
        output_ids = output_ids[:, inputs.input_ids.shape[1]:]
        return processor.decode(output_ids[0], skip_special_tokens=True)

    def transcribe_audio(self, audio_bytes: BytesIO, language: str = None) -> str:
        """Audio transcription via Gemma4 transformers (native audio encoder).

        Uses apply_chat_template with tokenize=True to process audio embeddings
        directly — Gemma4's processor handles audio within the chat template,
        NOT via a separate processor(audios=...) call.
        """
        # Lazy-load and cache processor (avoid reloading on every call)
        if not hasattr(self, "_audio_processor"):
            from transformers import AutoProcessor
            log.info(f"Loading audio processor for {self.model_name}...")
            self._audio_processor = AutoProcessor.from_pretrained(
                self.model_name, trust_remote_code=True, cache_dir=str(MODELS_DIR / "llm"),
            )

        # Load audio as mono float32 @ 16kHz (required by Gemma4 audio encoder)
        import librosa
        audio_bytes.seek(0)
        audio_array, _ = librosa.load(audio_bytes, sr=16000, mono=True)

        # Gemma4 best-practice prompt for ASR (from model card)
        # Audio BEFORE text for optimal performance
        lang = language or "English"
        messages = [{"role": "user", "content": [
            {"type": "audio", "audio": audio_array},
            {"type": "text", "text": (
                f"Transcribe the following speech segment in {lang} into {lang} text.\n\n"
                "Follow these specific instructions for formatting the answer:\n"
                "* Only output the transcription, with no newlines.\n"
                "* When transcribing numbers, write the digits, i.e. write 1.7 and not "
                "one point seven, and write 3 instead of three."
            )},
        ]}]

        # apply_chat_template with tokenize=True handles audio embedding directly
        inputs = self._audio_processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        input_len = inputs["input_ids"].shape[-1]

        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
            )

        return self._audio_processor.decode(
            output_ids[0][input_len:], skip_special_tokens=True
        ).strip()

    def chat(self, messages, max_tokens=512, temperature=0.7, top_p=0.95,
             stream=False, session_id=None):
        if stream:
            return self._stream_chat(messages, max_tokens, temperature, top_p, session_id)
        else:
            return self._batch_chat(messages, max_tokens, temperature, top_p, session_id)

    def _batch_chat(self, messages, max_tokens, temperature, top_p, session_id=None) -> dict:
        # Disable thinking/reasoning for models that support it (Qwen3, etc.)
        template_kwargs = dict(return_tensors="pt", add_generation_prompt=True)
        try:
            result = self.tokenizer.apply_chat_template(
                messages, enable_thinking=False, **template_kwargs
            )
        except TypeError:
            result = self.tokenizer.apply_chat_template(messages, **template_kwargs)
        full_ids = (result if isinstance(result, torch.Tensor) else result["input_ids"]).to(self.model.device)

        input_ids, past_kv = self._try_reuse_kv(full_ids, session_id)
        # No session KV hit — try system-prompt prefix cache for faster first-turn prefill
        if past_kv is None:
            input_ids, past_kv = self._try_reuse_sys_prefix(full_ids, messages)

        do_sample = temperature > 0
        gen_start = time.perf_counter()
        with torch.inference_mode():
            gen_kwargs = {
                "input_ids": input_ids,
                "attention_mask": torch.ones_like(input_ids),
                "max_new_tokens": max_tokens,
                "max_length": None,
                "do_sample": do_sample,
                "use_cache": True,
                "pad_token_id": self.tokenizer.eos_token_id,
                "return_dict_in_generate": True,
            }
            if do_sample:
                gen_kwargs["temperature"] = max(temperature, 0.01)
                gen_kwargs["top_p"] = top_p
            if past_kv is not None:
                gen_kwargs["past_key_values"] = past_kv
            elif self._turboquant_active:
                gen_kwargs["past_key_values"] = self._make_turboquant_cache()
            outputs = self.model.generate(**gen_kwargs)
        decode_ms = max(1, int((time.perf_counter() - gen_start) * 1000))

        # Save KV cache for this session
        if session_id and hasattr(outputs, "past_key_values") and outputs.past_key_values:
            self._save_kv(session_id, full_ids.shape[-1], outputs.past_key_values, full_ids)

        prompt_tokens = full_ids.shape[-1]
        gen_sequence = outputs.sequences[0]
        new_tokens = gen_sequence[prompt_tokens:]
        completion_tokens = len(new_tokens)
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        # Record metrics for non-streaming requests (streaming records in generator)
        LLM_METRICS.record(prompt_tokens, completion_tokens, decode_ms, 0)
        TRACKER.update_last_llm_info(LLM_METRICS.pop_last())
        return self._format_response(text, prompt_tokens, completion_tokens)

    def _stream_chat(self, messages, max_tokens, temperature, top_p, session_id=None):
        from transformers import TextIteratorStreamer

        # Disable thinking/reasoning for models that support it (Qwen3, etc.)
        template_kwargs = dict(return_tensors="pt", add_generation_prompt=True)
        try:
            result = self.tokenizer.apply_chat_template(
                messages, enable_thinking=False, **template_kwargs
            )
        except TypeError:
            result = self.tokenizer.apply_chat_template(messages, **template_kwargs)
        full_ids = (result if isinstance(result, torch.Tensor) else result["input_ids"]).to(self.model.device)

        input_ids, past_kv = self._try_reuse_kv(full_ids, session_id)
        # No session KV hit — try system-prompt prefix cache for faster first-turn prefill
        if past_kv is None:
            input_ids, past_kv = self._try_reuse_sys_prefix(full_ids, messages)
        prompt_tokens = full_ids.shape[-1]

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        do_sample = temperature > 0
        gen_kwargs = {
            "input_ids": input_ids,
            "attention_mask": torch.ones_like(input_ids),
            "max_new_tokens": max_tokens,
            "max_length": None,
            "do_sample": do_sample,
            "use_cache": True,
            "streamer": streamer,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = max(temperature, 0.01)
            gen_kwargs["top_p"] = top_p
        if past_kv is not None:
            gen_kwargs["past_key_values"] = past_kv
        elif self._turboquant_active:
            gen_kwargs["past_key_values"] = self._make_turboquant_cache()

        thread = Thread(target=self.model.generate, kwargs=gen_kwargs)
        thread.start()

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
        gen_start = time.perf_counter()
        output_text = []
        decode_start = None  # set on first token — excludes prefill

        def generate():
            nonlocal decode_start
            for token_text in streamer:
                if not token_text:
                    continue
                if decode_start is None:
                    decode_start = time.perf_counter()  # first token = prefill done
                output_text.append(token_text)
                chunk = {
                    "id": completion_id, "object": "chat.completion.chunk",
                    "created": created, "model": self.model_name,
                    "choices": [{"index": 0, "delta": {"content": token_text}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"

            # decode_ms = time from first token to last token (pure decode speed)
            elapsed_ms = max(1, int((time.perf_counter() - (decode_start or time.perf_counter())) * 1000))
            # count real tokens by encoding the full generated text
            try:
                completion_tokens = len(self.tokenizer.encode("".join(output_text), add_special_tokens=False))
            except Exception:
                completion_tokens = len(output_text)
            final = {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": self.model_name,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "elapsed_ms": elapsed_ms,
                },
            }
            ttft_ms = int((decode_start - gen_start) * 1000) if decode_start else 0
            LLM_METRICS.record(prompt_tokens, completion_tokens, elapsed_ms, ttft_ms)
            TRACKER.update_last_llm_info(LLM_METRICS.pop_last())
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return generate()

    def _try_reuse_kv(self, full_ids: torch.Tensor, session_id: str):
        """Try to reuse cached KV. Returns (input_ids_to_process, past_kv_or_None)."""
        if not session_id:
            return full_ids, None
        with self._kv_lock:
            if session_id not in self._kv_cache:
                return full_ids, None

            cached_len, cached_kv, ts, cached_prefix = self._kv_cache[session_id]
            if time.time() - ts > self._kv_ttl:
                del self._kv_cache[session_id]
                return full_ids, None

            # New input must be longer and the prefix tokens must match exactly
            if full_ids.shape[-1] > cached_len:
                current_prefix = full_ids[0, :cached_len].tolist()
                if current_prefix == cached_prefix:
                    return full_ids[:, cached_len:], cached_kv

            # Input changed (shorter, different prefix, or same length), start fresh
            del self._kv_cache[session_id]
            return full_ids, None

    def _save_kv(self, session_id: str, prompt_len: int, past_kv, full_ids: torch.Tensor = None):
        prefix = full_ids[0, :prompt_len].tolist() if full_ids is not None else []
        with self._kv_lock:
            self._kv_cache[session_id] = (prompt_len, past_kv, time.time(), prefix)
            # Evict oldest if over limit
            while len(self._kv_cache) > self._kv_max_sessions:
                oldest = min(self._kv_cache, key=lambda k: self._kv_cache[k][2])
                del self._kv_cache[oldest]

    def _format_response(self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> dict:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_name,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    def unload(self):
        with self._kv_lock:
            self._kv_cache.clear()
        del self.model
        del self.tokenizer
        self.model = None
        self.tokenizer = None


# ===================================================================
# LLM Service — llama.cpp backend (GGUF models)
# ===================================================================
class LlamaCppService:
    """Fast LLM inference via llama.cpp using GGUF models (same engine as LM Studio)."""

    # GGML type enum values for KV cache quantization
    _GGML_TYPES = {"f16": 1, "q8_0": 8, "q5_0": 6, "q5_1": 7, "q4_0": 2, "q4_1": 3}

    def __init__(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1,
                 n_batch: int = 2048, flash_attn: bool = True,
                 cache_type_k: str = "q8_0", cache_type_v: str = "q8_0",
                 kv_cache_sessions: int = 2, kv_cache_ttl: int = 300):  # noqa: ARG002
        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python not installed. Run: pip install llama-cpp-python"
            )


        # Common kwargs for all load paths
        type_k = self._GGML_TYPES.get(cache_type_k, 8)
        type_v = self._GGML_TYPES.get(cache_type_v, 8)
        log.info(f"KV cache type: keys={cache_type_k}({type_k}), values={cache_type_v}({type_v})")
        # n_threads: CPU threads for token generation (each new token).
        # n_threads_batch: CPU threads for prompt prefill (parallel over the prompt).
        # Default llama-cpp is 1 thread — on multi-core CPUs this is a major bottleneck.
        _n_threads = min(max(os.cpu_count() or 4, 1), 8)
        llama_kwargs = dict(
            n_gpu_layers=n_gpu_layers, n_ctx=n_ctx,
            n_batch=n_batch, flash_attn=flash_attn,
            verbose=False,
            type_k=type_k,
            type_v=type_v,
            n_threads=_n_threads,
            n_threads_batch=_n_threads,
        )
        log.info(f"llama.cpp CPU threads: n_threads={_n_threads}, n_threads_batch={_n_threads}")

        # Determine load method:
        #   Local file:          C:\path\to\model.gguf  or  /path/to/model.gguf
        #   HF repo (auto GGUF): owner/repo-name
        #   HF repo + filename:  owner/repo-name::file.gguf
        if os.path.isfile(model_path):
            self.model_name = os.path.basename(model_path)
            log.info(f"Loading llama.cpp model: {self.model_name} (n_gpu_layers={n_gpu_layers}, n_ctx={n_ctx})...")
            with _mute_output():
                self._llm = Llama(model_path=model_path, **llama_kwargs)
        elif "::" in model_path:
            repo_id, filename = model_path.split("::", 1)
            self.model_name = filename
            log.info(f"Downloading GGUF from HuggingFace: {repo_id} / {filename} ...")
            llm_dir = MODELS_DIR / "llm"
            llm_dir.mkdir(exist_ok=True)
            _task_id = f"{repo_id.replace('/', '--')}::{filename}"
            _download_progress[_task_id] = {"status": "downloading", "pct": 0, "speed_mbps": 0.0, "file": filename}
            try:
                from huggingface_hub import hf_hub_download as _hf_dl
                _local_path = _hf_dl(repo_id=repo_id, filename=filename, cache_dir=str(llm_dir))
                _download_progress[_task_id] = {"status": "complete", "pct": 100, "speed_mbps": 0.0, "file": filename}
            except Exception:
                _download_progress.pop(_task_id, None)
                raise
            with _mute_output():
                self._llm = Llama(model_path=_local_path, **llama_kwargs)
        elif "/" in model_path and not model_path.startswith(("C:", "D:", "/")):
            # HuggingFace repo ID — auto-pick best available GGUF (prefer Q4_K_M)
            # List repo files first, then pick the single best match to avoid downloading extras
            self.model_name = model_path.split("/")[-1]
            log.info(f"Downloading GGUF from HuggingFace: {model_path} (searching for Q4_K_M) ...")
            from huggingface_hub import list_repo_files, hf_hub_download as _hf_dl
            try:
                all_files = [f for f in list_repo_files(model_path) if f.endswith(".gguf")]
            except Exception:
                all_files = []
            chosen = None
            for suffix in ("Q4_K_M.gguf", "Q4_K_S.gguf", "Q5_K_M.gguf"):
                matches = [f for f in all_files if f.endswith(suffix)]
                if matches:
                    chosen = matches[0]
                    break
            if not chosen and all_files:
                chosen = all_files[0]
            if not chosen:
                raise FileNotFoundError(f"No GGUF file found in HuggingFace repo: {model_path}")
            log.info(f"Selected GGUF: {chosen}")
            llm_dir = MODELS_DIR / "llm"
            llm_dir.mkdir(exist_ok=True)
            _task_id = f"{model_path.replace('/', '--')}::{chosen}"
            _download_progress[_task_id] = {"status": "downloading", "pct": 0, "speed_mbps": 0.0, "file": chosen}
            try:
                _local_path = _hf_dl(repo_id=model_path, filename=chosen, cache_dir=str(llm_dir))
                _download_progress[_task_id] = {"status": "complete", "pct": 100, "speed_mbps": 0.0, "file": chosen}
            except Exception:
                _download_progress.pop(_task_id, None)
                raise
            with _mute_output():
                self._llm = Llama(model_path=_local_path, **llama_kwargs)
        else:
            raise FileNotFoundError(
                f"GGUF model not found: {model_path}\n"
                "  Local file: use full path ending in .gguf\n"
                "  HuggingFace: use  owner/repo  or  owner/repo::filename.gguf"
            )

        # Warmup: single short inference to pre-allocate CUDA scratch buffers.
        try:
            t0 = time.perf_counter()
            self._llm.create_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=4, temperature=0, stream=False,
            )
            log.info(f"llama.cpp warmup complete ({time.perf_counter() - t0:.1f}s)")
        except Exception as e:
            log.debug(f"llama.cpp warmup issue: {e}")

        log.info(f"llama.cpp model loaded: {self.model_name}")

    def chat(self, messages, max_tokens=512, temperature=0.7, top_p=0.95,
             stream=False, session_id=None):  # noqa: ARG002
        if stream:
            return self._stream_chat(messages, max_tokens, temperature, top_p)
        return self._batch_chat(messages, max_tokens, temperature, top_p)

    def _batch_chat(self, messages, max_tokens, temperature, top_p) -> dict:
        do_sample = temperature > 0
        output = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=max(temperature, 0.01) if do_sample else 0.0,
            top_p=top_p if do_sample else 1.0,
            stream=False,
        )
        text = output["choices"][0]["message"]["content"] or ""
        usage = output.get("usage", {})
        return self._format_response(text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    def _stream_chat(self, messages, max_tokens, temperature, top_p):
        do_sample = temperature > 0
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        def generate():
            gen_start = time.perf_counter()
            decode_start = None
            output_text = []
            prompt_tokens = 0
            completion_tokens = 0

            for chunk in self._llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=max(temperature, 0.01) if do_sample else 0.0,
                top_p=top_p if do_sample else 1.0,
                stream=True,
            ):
                choice = chunk["choices"][0]
                token_text = choice.get("delta", {}).get("content", "")
                finish_reason = choice.get("finish_reason")

                if token_text:
                    if decode_start is None:
                        decode_start = time.perf_counter()
                    output_text.append(token_text)
                    yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': self.model_name, 'choices': [{'index': 0, 'delta': {'content': token_text}, 'finish_reason': None}]})}\n\n"

                if finish_reason is not None:
                    usage = chunk.get("usage") or {}
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    break

            elapsed_ms = max(1, int((time.perf_counter() - (decode_start or time.perf_counter())) * 1000))
            ttft_ms = int((decode_start - gen_start) * 1000) if decode_start else 0
            if not completion_tokens:
                try:
                    completion_tokens = len(self._llm.tokenize("".join(output_text).encode()))
                except Exception:
                    completion_tokens = len(output_text)

            LLM_METRICS.record(prompt_tokens, completion_tokens, elapsed_ms, ttft_ms)
            TRACKER.update_last_llm_info(LLM_METRICS.pop_last())
            final = {
                "id": completion_id, "object": "chat.completion.chunk",
                "created": created, "model": self.model_name,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "elapsed_ms": elapsed_ms,
                },
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return generate()

    def _format_response(self, text: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> dict:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_name,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    def unload(self):
        del self._llm
        self._llm = None


# ===================================================================
# Vision Service (multi-backend: BLIP, BLIP-2, Moondream, Florence-2, generic)
# ===================================================================
class VisionService:
    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base", device: str = None):
        device = device or DEVICE
        self._device = device
        self._dtype = torch.float16 if ("cuda" in str(device)) else torch.float32
        self._cache_dir = MODELS_DIR / "vision"
        self._cache_dir.mkdir(exist_ok=True)
        self.model_name = model_name
        self.backend = self._detect_backend(model_name)
        log.info(f"Loading vision model: {model_name} (backend: {self.backend}, device: {device})...")
        loader = {"blip": self._load_blip, "blip2": self._load_blip2,
                  "moondream": self._load_moondream, "florence": self._load_florence,
                  "generic": self._load_generic}
        with _mute_output():
            loader[self.backend]()
        log.info(f"Vision model loaded ({self.backend}).")

    @staticmethod
    def _detect_backend(name: str) -> str:
        n = name.lower()
        if "moondream" in n:   return "moondream"
        if "florence" in n:    return "florence"
        if "blip-2" in n or "blip2" in n: return "blip2"
        if "blip" in n:       return "blip"
        return "generic"

    # -- loaders -----------------------------------------------------------
    def _load_blip(self):
        from transformers import BlipProcessor, BlipForConditionalGeneration
        self.processor = BlipProcessor.from_pretrained(self.model_name, cache_dir=str(self._cache_dir))
        self.model = BlipForConditionalGeneration.from_pretrained(
            self.model_name, cache_dir=str(self._cache_dir), torch_dtype=self._dtype,
            use_safetensors=False)
        self.model.to(self._device).eval()

    def _load_blip2(self):
        from transformers import Blip2Processor, Blip2ForConditionalGeneration
        self.processor = Blip2Processor.from_pretrained(self.model_name, cache_dir=str(self._cache_dir))
        self.model = Blip2ForConditionalGeneration.from_pretrained(
            self.model_name, cache_dir=str(self._cache_dir), torch_dtype=self._dtype,
            use_safetensors=False)
        self.model.to(self._device).eval()

    def _load_moondream(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, cache_dir=str(self._cache_dir))
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name, cache_dir=str(self._cache_dir),
            torch_dtype=self._dtype, trust_remote_code=True)
        self.model.to(self._device).eval()
        self.processor = None

    def _load_florence(self):
        from transformers import AutoProcessor, AutoModelForCausalLM
        self.processor = AutoProcessor.from_pretrained(self.model_name, cache_dir=str(self._cache_dir),
                                                       trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name, cache_dir=str(self._cache_dir),
            torch_dtype=self._dtype, trust_remote_code=True)
        self.model.to(self._device).eval()

    def _load_generic(self):
        from transformers import AutoProcessor, AutoModelForVision2Seq
        self.processor = AutoProcessor.from_pretrained(self.model_name, cache_dir=str(self._cache_dir),
                                                       trust_remote_code=True)
        try:
            self.model = AutoModelForVision2Seq.from_pretrained(
                self.model_name, cache_dir=str(self._cache_dir),
                torch_dtype=self._dtype, trust_remote_code=True)
        except Exception:
            from transformers import AutoModelForCausalLM
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, cache_dir=str(self._cache_dir),
                torch_dtype=self._dtype, trust_remote_code=True)
        self.model.to(self._device).eval()

    # -- caption dispatch --------------------------------------------------
    def caption(self, image_bytes: bytes, prompt: str = None) -> str:
        from PIL import Image
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        fn = {"blip": self._caption_blip, "blip2": self._caption_blip,
              "moondream": self._caption_moondream, "florence": self._caption_florence,
              "generic": self._caption_generic}
        return fn[self.backend](image, prompt)

    def _caption_blip(self, image, prompt):
        inputs = (self.processor(image, prompt, return_tensors="pt") if prompt
                  else self.processor(image, return_tensors="pt"))
        inputs = inputs.to(self._device)
        with torch.inference_mode():
            outputs = self.model.generate(**inputs, max_new_tokens=100, num_beams=3)
        return self.processor.decode(outputs[0], skip_special_tokens=True)

    def _caption_moondream(self, image, prompt):
        enc_img = self.model.encode_image(image)
        question = prompt or "Describe this image."
        return self.model.answer_question(enc_img, question, self.tokenizer)

    def _caption_florence(self, image, prompt):
        task = "<MORE_DETAILED_CAPTION>" if (prompt and "detail" in prompt.lower()) else "<CAPTION>"
        inputs = self.processor(text=task, images=image, return_tensors="pt").to(self._device)
        with torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=200, num_beams=3)
        text = self.processor.batch_decode(ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(text, task=task, image_size=(image.width, image.height))
        return parsed.get(task, text).strip()

    def _caption_generic(self, image, prompt):
        text_input = prompt or "Describe this image."
        inputs = self.processor(images=image, text=text_input, return_tensors="pt").to(self._device)
        with torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=200)
        return self.processor.batch_decode(ids, skip_special_tokens=True)[0].strip()

    def unload(self):
        self.model = None
        self.processor = None
        if hasattr(self, "tokenizer"):
            self.tokenizer = None


# ===================================================================
# Image Generation Service (diffusers + scheduler selection)
# ===================================================================
_SCHEDULER_MAP = {
    "DPM++ 2M":        "DPMSolverMultistepScheduler",
    "DPM++ 2M Karras":  "DPMSolverMultistepScheduler",  # + use_karras_sigmas
    "Euler":            "EulerDiscreteScheduler",
    "Euler a":          "EulerAncestralDiscreteScheduler",
    "DDIM":             "DDIMScheduler",
    "LMS":              "LMSDiscreteScheduler",
    "PNDM":             "PNDMScheduler",
}


class ImageGenService:
    _progress = {}  # {task_id: {"step": int, "total": int}}

    # SD 1.5 models default to 512x512, SDXL models to 1024x1024
    _SD15_INDICATORS = ("v1-5", "v1.5", "dreamshaper-8", "sd-1", "stable-diffusion-v1")

    def __init__(self, model_name: str = "stabilityai/stable-diffusion-xl-base-1.0", device: str = None):
        device = device or DEVICE
        self._device = device
        log.info(f"Loading image generation model: {model_name} (device: {device})...")
        self.model_name = model_name
        cache_dir = MODELS_DIR / "imagegen"
        cache_dir.mkdir(exist_ok=True)

        # Detect if this is an SD 1.5 model (512x512) vs SDXL (1024x1024)
        model_lower = model_name.lower()
        self.is_sd15 = any(ind in model_lower for ind in self._SD15_INDICATORS)
        self.default_size = 512 if self.is_sd15 else 1024

        from diffusers import AutoPipelineForText2Image
        dtype = torch.float16 if device == "cuda" else torch.float32
        load_kwargs = dict(torch_dtype=dtype, cache_dir=str(cache_dir))
        # Disable safety checker for faster inference (adds ~200ms per image)
        load_kwargs["safety_checker"] = None
        load_kwargs["requires_safety_checker"] = False
        # Patch any cached preprocessor_config.json files that still reference the
        # deprecated CLIPFeatureExtractor name (triggers a warning on every load).
        for _cfg in cache_dir.rglob("preprocessor_config.json"):
            try:
                _txt = _cfg.read_text(encoding="utf-8")
                if "CLIPFeatureExtractor" in _txt:
                    _cfg.write_text(_txt.replace("CLIPFeatureExtractor", "CLIPImageProcessor"), encoding="utf-8")
            except Exception:
                pass
        with _mute_output():
            self.pipe = AutoPipelineForText2Image.from_pretrained(model_name, **load_kwargs)
        if device == "cuda":
            # CPU offload: weights stay in RAM, each component moves to GPU only during its
            # forward pass. Uses near-zero idle VRAM (~0 GB) vs ~2+ GB with .to("cuda").
            # Slightly slower per-image (~1-2s overhead) but frees VRAM for LLM/other services.
            self.pipe.enable_model_cpu_offload()
            self.pipe.enable_vae_slicing()
            self.pipe.enable_vae_tiling()
            try:
                self.pipe.enable_xformers_memory_efficient_attention()
                log.info("ImageGen: xformers memory-efficient attention enabled")
            except Exception:
                pass
        self._default_scheduler_config = self.pipe.scheduler.config
        log.info(f"Image generation model loaded: {model_name} ({'SD 1.5' if self.is_sd15 else 'SDXL'}, {self.default_size}x{self.default_size})")

    def _set_scheduler(self, name: str):
        if not name or name not in _SCHEDULER_MAP:
            return
        import diffusers
        cls_name = _SCHEDULER_MAP[name]
        cls = getattr(diffusers, cls_name, None)
        if cls is None:
            return
        kwargs = {}
        if "Karras" in name:
            kwargs["use_karras_sigmas"] = True
        self.pipe.scheduler = cls.from_config(self._default_scheduler_config, **kwargs)

    def generate(self, prompt, negative_prompt="", steps=20, cfg_scale=7.0,
                 width=1024, height=1024, seed=-1, sampler_name=None,
                 task_id=None) -> bytes:
        self._set_scheduler(sampler_name)
        generator = torch.Generator(device=self._device).manual_seed(seed) if seed >= 0 else None
        gen_kwargs = {
            "prompt": prompt, "num_inference_steps": steps,
            "guidance_scale": cfg_scale, "width": width, "height": height,
            "generator": generator,
        }
        if negative_prompt:
            gen_kwargs["negative_prompt"] = negative_prompt
        if task_id:
            ImageGenService._progress[task_id] = {"step": 0, "total": steps}
            def _on_step(pipe, step_index, timestep, callback_kwargs):
                ImageGenService._progress[task_id] = {"step": step_index + 1, "total": steps}
                return callback_kwargs
            gen_kwargs["callback_on_step_end"] = _on_step
        try:
            result = self.pipe(**gen_kwargs)
        finally:
            ImageGenService._progress.pop(task_id, None)
        buf = BytesIO()
        result.images[0].save(buf, format="PNG")
        return buf.getvalue()

    def unload(self):
        del self.pipe
        self.pipe = None


# ===================================================================
# Embeddings Service (sentence-transformers)
# ===================================================================
class EmbeddingsService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = None):
        device = device or DEVICE
        log.info(f"Loading embeddings model: {model_name} (device: {device})...")
        cache_dir = MODELS_DIR / "embeddings"
        cache_dir.mkdir(exist_ok=True)
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        with _mute_output():
            self.model = SentenceTransformer(model_name, cache_folder=str(cache_dir), device=device)
        log.info(f"Embeddings model loaded: {model_name}")

    def embed(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Encode texts with automatic batching to avoid OOM on large inputs."""
        if len(texts) <= batch_size:
            embeddings = self.model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        # Process in chunks
        import numpy as np
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i + batch_size]
            batch_emb = self.model.encode(chunk, normalize_embeddings=True)
            all_embeddings.append(batch_emb)
        return np.vstack(all_embeddings).tolist()

    def unload(self):
        del self.model
        self.model = None


# ===================================================================
# MusicGen Service (ACE-Step — music with vocals/lyrics)
# ===================================================================
class MusicGenService:
    _progress = {}  # {task_id: {"status": str, "pct": int}}

    def __init__(self, model_name: str = "ACE-Step/ACE-Step-v1-3.5B", device: str = None):
        device = device or DEVICE
        self._device = device
        log.info(f"Loading ACE-Step music generation model (device: {device})...")
        self.model_name = model_name
        cache_dir = MODELS_DIR / "musicgen"
        cache_dir.mkdir(exist_ok=True)
        from acestep.pipeline_ace_step import ACEStepPipeline
        device_id = 0 if device == "cuda" else -1
        # Always enable cpu_offload — ACE-Step is 6+ GB and would starve other services.
        # With cpu_offload, weights live in RAM and are moved to GPU only during generation.
        self.pipe = ACEStepPipeline(
            checkpoint_dir=str(cache_dir),
            device_id=device_id if device == "cuda" else 0,
            dtype="bfloat16" if device == "cuda" else "float32",
            cpu_offload=True,
        )
        # ACEStepPipeline.__init__ only configures — weights are lazy-loaded on first
        # __call__ which re-scans HuggingFace cache every time. Pre-load them now so
        # the first request is fast and subsequent restarts don't re-fetch file listings.
        if not self.pipe.loaded:
            log.info("ACE-Step: pre-loading checkpoint into memory...")
            self.pipe.load_checkpoint(str(cache_dir))
            log.info("ACE-Step checkpoint loaded")
        log.info("ACE-Step music generation model loaded")

    def generate(self, prompt: str, lyrics: str = "", duration_sec: float = 30.0,
                 infer_steps: int = 60, guidance_scale: float = 15.0,
                 seed: int = -1, task_id: str = None,
                 scheduler_type: str = "euler", cfg_type: str = "apg",
                 omega_scale: float = 10.0, guidance_interval: float = 0.5,
                 min_guidance_scale: float = 3.0,
                 batch_size: int = 1) -> list:
        """Generate music with vocals from prompt + lyrics. Returns list of OGG bytes."""
        if task_id:
            MusicGenService._progress[task_id] = {"status": "processing", "pct": 0}

        try:
            if task_id:
                MusicGenService._progress[task_id] = {"status": "generating", "pct": 10}

            manual_seeds = [seed] if seed >= 0 else None
            # Use [inst] tag if no lyrics provided
            actual_lyrics = lyrics.strip() if lyrics.strip() else "[inst]"

            out_dir = str(Path(__file__).parent / "output" / "musicgen")
            os.makedirs(out_dir, exist_ok=True)
            result = self.pipe(
                prompt=prompt,
                lyrics=actual_lyrics,
                audio_duration=duration_sec,
                infer_step=infer_steps,
                guidance_scale=guidance_scale,
                scheduler_type=scheduler_type,
                cfg_type=cfg_type,
                omega_scale=omega_scale,
                guidance_interval=guidance_interval,
                min_guidance_scale=min_guidance_scale,
                manual_seeds=manual_seeds,
                batch_size=batch_size,
                format="wav",
                save_path=out_dir,
            )

            if task_id:
                MusicGenService._progress[task_id] = {"status": "encoding", "pct": 90}

            # Result is a list: [filepath1, ..., filepathN, params_dict]
            audio_paths = [r for r in result if isinstance(r, str) and os.path.isfile(r)]
            ogg_list = []
            for audio_path in audio_paths:
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass
                ogg_list.append(self._wav_to_ogg(audio_bytes))
            return ogg_list
        finally:
            if task_id:
                MusicGenService._progress.pop(task_id, None)

    @staticmethod
    def _wav_to_ogg(wav_bytes: bytes) -> bytes:
        """Convert WAV bytes to OGG Vorbis using soundfile (no ffmpeg needed).
        Writes in chunks to avoid stack overflow in libsndfile's OGG encoder on Windows."""
        import soundfile as sf
        buf_in = io.BytesIO(wav_bytes)
        data, samplerate = sf.read(buf_in)
        buf_out = io.BytesIO()
        channels = data.shape[1] if data.ndim > 1 else 1
        chunk_samples = samplerate * 10  # 10-second chunks
        with sf.SoundFile(buf_out, mode="w", samplerate=samplerate,
                          channels=channels, format="OGG", subtype="VORBIS") as f:
            for i in range(0, len(data), chunk_samples):
                f.write(data[i:i + chunk_samples])
        return buf_out.getvalue()

    def unload(self):
        del self.pipe
        self.pipe = None


# ===================================================================
# FastAPI app
# ===================================================================
app = FastAPI(
    title="TARS-AI Companion Server", version="2.0",
    description="Offload STT, TTS, LLM, Vision, ImageGen, MusicGen, and Embeddings from your Raspberry Pi.",
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": False},
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[],
)

# Install Windows ConnectionResetError suppressor on uvicorn's event loop
if sys.platform == "win32":
    @app.on_event("startup")
    async def _install_win_exception_handler():
        loop = asyncio.get_running_loop()
        def _handler(loop, context):
            exc = context.get("exception")
            if isinstance(exc, ConnectionResetError):
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(_handler)

# Inject Bearer security scheme into OpenAPI spec so /docs shows the Authorize button
from fastapi.openapi.utils import get_openapi as _get_openapi
def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = _get_openapi(
        title=app.title, version=app.version,
        description=app.description, routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http", "scheme": "bearer",
    }
    for path in schema.get("paths", {}).values():
        for op in path.values():
            op.setdefault("security", [{"BearerAuth": []}])
    app.openapi_schema = schema
    return schema
app.openapi = _custom_openapi
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# GZip compression — huge win for embeddings vectors, base64 images, gallery JSON
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress responses >1KB

# Serve static www files (CSS, JS)
from starlette.staticfiles import StaticFiles as _StaticFiles
_www_dir = Path(__file__).parent / "www"
if _www_dir.exists():
    app.mount("/www", _StaticFiles(directory=str(_www_dir)), name="www")

def _read_www(filename: str, **replacements) -> str:
    """Read an HTML file from www/ and optionally replace template placeholders."""
    fpath = Path(__file__).parent / "www" / filename
    content = fpath.read_text(encoding="utf-8")
    for key, val in replacements.items():
        content = content.replace("{{" + key + "}}", val)
    return content


# -- Auth middleware ---------------------------------------------------

# Pages that need a browser session cookie (web UI)
_WEB_PAGES = {"/", "/ui", "/playground"}
# API paths callable from the web UI — accept session cookie OR Bearer token
_WEB_API_PATHS = {
    "/api/tunnel", "/api/settings", "/models",
    "/v1",           # LLM chat completions + embeddings
    "/tts",          # TTS generate + voices
    "/save_audio", "/transcribe",  # STT
    "/caption", "/generate_image", "/sdapi", "/imagegen_progress", "/imagegen_gallery",  # Vision + ImageGen
    "/generate_music", "/musicgen_progress", "/musicgen_gallery",  # MusicGen
}
# Paths exempt from ALL auth (health check, login, static API schema)
_AUTH_EXEMPT = {"/health", "/login", "/logout", "/docs", "/openapi.json", "/redoc", "/ws/dashboard", "/www"}


def _session_token(api_key: str) -> str:
    import hmac as _hmac, hashlib as _hashlib
    return _hmac.new(api_key.encode(), b"tars-web-session", _hashlib.sha256).hexdigest()


def _is_web_authed(request: Request, api_key: str) -> bool:
    expected = _session_token(api_key)
    return request.cookies.get("tars_session") == expected


def _path_matches(path: str, path_set: set) -> bool:
    """Fast path matching — exact match or starts with prefix/."""
    if path in path_set:
        return True
    # Check if any prefix matches (e.g., /www/css/style.css matches /www)
    for p in path_set:
        if path.startswith(p + "/"):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = _active_config.get("server", "api_key", fallback="") if _active_config else ""
        if not api_key:
            return await call_next(request)

        path = request.url.path

        # Always allowed
        if _path_matches(path, _AUTH_EXEMPT):
            return await call_next(request)

        # Web UI pages — require session cookie, redirect to /login if missing
        if _path_matches(path, _WEB_PAGES):
            if not _is_web_authed(request, api_key):
                return RedirectResponse(url=f"/login?next={path}", status_code=302)
            return await call_next(request)

        # Web-facing API paths — accept session cookie OR Bearer token
        if _path_matches(path, _WEB_API_PATHS):
            if _is_web_authed(request, api_key) or request.headers.get("authorization", "") == f"Bearer {api_key}":
                return await call_next(request)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        # API endpoints — require Bearer token
        if request.headers.get("authorization", "") != f"Bearer {api_key}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)





@app.get("/login", response_class=HTMLResponse)
async def login_get(next: str = "/"):
    return _read_www("login.html", NEXT=next, ERROR="")


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, next: str = "/"):
    form = await request.form()
    password = form.get("password", "")
    next_url = form.get("next", next) or "/"
    api_key = _active_config.get("server", "api_key", fallback="") if _active_config else ""
    if password == api_key:
        token = _session_token(api_key)
        response = RedirectResponse(url=next_url, status_code=302)
        response.set_cookie("tars_session", token, httponly=True, samesite="lax", max_age=86400 * 30)
        return response
    html = _read_www("login.html", NEXT=next_url, ERROR="Invalid API key.")
    return HTMLResponse(html, status_code=401)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("tars_session")
    return response


# -- Request tracking middleware ----------------------------------------

class TrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
        except RuntimeError as e:
            if "no response returned" in str(e).lower():
                response = JSONResponse({"error": "Internal Server Error"}, status_code=500)
            else:
                raise
        latency_ms = (time.time() - start) * 1000
        path = request.url.path
        service = _endpoint_to_service(path)
        llm_info = LLM_METRICS.pop_last() if service == "llm" else None
        TRACKER.record(path, request.method, response.status_code, latency_ms, service, llm_info)
        return response


app.add_middleware(TrackingMiddleware)
app.add_middleware(AuthMiddleware)


# -- Health ------------------------------------------------------------

@app.get("/health")
async def health():
    uptime = int(time.time() - START_TIME)
    gpu = get_gpu_stats()
    svc_info = {}
    for name, svc in SERVICES.items():
        info = {"status": "ready"}
        if hasattr(svc, "model_name"):
            info["model"] = svc.model_name
        if name in _SERVICE_VRAM:
            info["vram_gb"] = _SERVICE_VRAM[name]
        svc_info[name] = info
    return {
        "status": "ok", "uptime_seconds": uptime, "device": DEVICE,
        "gpu": gpu, "services": svc_info,
        "latency": TRACKER.get_latency_stats(),
        "llm_metrics": LLM_METRICS.get_stats(),
    }


# -- Dashboard ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard page — connects to /ws/dashboard for live updates."""
    gpu = get_gpu_stats()
    gpu_name = gpu.get("name", "None (CPU)")
    return _read_www("dashboard.html", GPU_NAME=gpu_name)





@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    _last_hash = None
    try:
        while True:
            uptime = int(time.time() - START_TIME)
            gpu = get_gpu_stats()
            svc_info = {}
            for name, svc in SERVICES.items():
                info = {"status": "ready"}
                if hasattr(svc, "model_name"):
                    info["model"] = svc.model_name
                if name in _SERVICE_VRAM:
                    info["vram_gb"] = _SERVICE_VRAM[name]
                svc_info[name] = info
            data = {
                "uptime": uptime, "gpu": gpu, "system": get_system_stats(),
                "services": svc_info,
                "latency": TRACKER.get_latency_stats(),
                "llm_metrics": LLM_METRICS.get_stats(),
                "recent_logs": TRACKER.get_recent(20),
            }
            # Skip sending if nothing changed (saves bandwidth for multi-tab users)
            payload = json.dumps(data, sort_keys=True)
            payload_hash = hash(payload)
            if payload_hash != _last_hash:
                _last_hash = payload_hash
                try:
                    await ws.send_text(payload)
                except Exception:
                    break
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# -- Logs endpoint -----------------------------------------------------

@app.get("/logs")
async def get_logs(n: int = 50):
    return {"logs": TRACKER.get_recent(n)}


# -- STT Routes --------------------------------------------------------

@app.post("/save_audio")
async def stt_transcribe(audio: UploadFile = File(...)):
    if "stt" not in SERVICES:
        raise HTTPException(503, "STT service not loaded")
    audio_bytes = BytesIO(await audio.read())
    loop = asyncio.get_running_loop()
    try:
        # Decode once, pass samples to both VAD and transcription
        samples = await loop.run_in_executor(_INFERENCE_POOL, SERVICES["stt"]._wav_to_float32, audio_bytes)
        has_speech = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["stt"].has_speech(audio_bytes, samples=samples))
        if not has_speech:
            log.info("STT: VAD filtered (no speech detected)")
            return {"transcription": []}
        audio_bytes.seek(0)
        transcription, info = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["stt"].transcribe(audio_bytes, samples=samples))
        full_text = " ".join(t["text"] for t in transcription).strip()
        log.info(f"STT: \"{full_text}\" (lang={info.language}, prob={info.language_probability:.2f})")
        return {"transcription": transcription}
    except RuntimeError as e:
        log.warning(f"STT: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error(f"STT error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/transcribe")
async def stt_transcribe_v2(audio: UploadFile = File(...), language: Optional[str] = Form(None)):
    if "stt" not in SERVICES:
        raise HTTPException(503, "STT service not loaded")
    audio_bytes = BytesIO(await audio.read())
    loop = asyncio.get_running_loop()
    try:
        # Decode once, pass samples to both VAD and transcription
        samples = await loop.run_in_executor(_INFERENCE_POOL, SERVICES["stt"]._wav_to_float32, audio_bytes)
        has_speech = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["stt"].has_speech(audio_bytes, samples=samples))
        if not has_speech:
            return {"text": "", "segments": [], "language": None, "language_probability": 0}
        audio_bytes.seek(0)
        transcription, info = await loop.run_in_executor(
            _INFERENCE_POOL, lambda: SERVICES["stt"].transcribe(audio_bytes, language=language, samples=samples)
        )
        full_text = " ".join(t["text"] for t in transcription).strip()
        log.info(f"STT: \"{full_text}\"")
        return {"text": full_text, "segments": transcription,
                "language": info.language, "language_probability": round(info.language_probability, 3)}
    except RuntimeError as e:
        log.warning(f"STT: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error(f"STT error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.websocket("/ws/stt")
async def websocket_stt(ws: WebSocket):
    """WebSocket STT endpoint.

    Protocol:
      - Send binary frames: raw audio bytes appended to buffer.
      - Send text "end":     transcribe full buffer, return {is_final: true}, clear buffer.
      - Send text "partial": transcribe current buffer snapshot, return {is_final: false}.
                             Buffer is NOT cleared — keep streaming audio after partial requests.
                             Use this every ~1s to get interim results while audio is still coming.
      - Send text "reset":   clear buffer without transcribing.
    """
    if "stt" not in SERVICES:
        await ws.close(code=1013, reason="STT service not loaded")
        return
    await ws.accept()
    audio_buffer = BytesIO()
    loop = asyncio.get_running_loop()
    log.info("WebSocket STT: client connected")

    async def _transcribe_buffer(buf: BytesIO, is_final: bool) -> dict:
        """Run transcription on a copy of the buffer in the inference pool."""
        buf.seek(0)
        snapshot = BytesIO(buf.read())
        snapshot.seek(0)
        try:
            samples = await loop.run_in_executor(
                _INFERENCE_POOL, SERVICES["stt"]._wav_to_float32, snapshot
            )
            has_speech = await loop.run_in_executor(
                _INFERENCE_POOL, lambda: SERVICES["stt"].has_speech(snapshot, samples=samples)
            )
            if not has_speech:
                return {"text": "", "segments": [], "is_final": is_final}
            snapshot.seek(0)
            transcription, info = await loop.run_in_executor(
                _INFERENCE_POOL,
                lambda: SERVICES["stt"].transcribe(snapshot, samples=samples)
            )
            full_text = " ".join(t["text"] for t in transcription).strip()
            return {"text": full_text, "segments": transcription,
                    "language": info.language, "is_final": is_final}
        except Exception as e:
            return {"error": str(e), "is_final": is_final}

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.receive":
                if "bytes" in message and message["bytes"]:
                    audio_buffer.write(message["bytes"])
                elif "text" in message and message["text"]:
                    cmd = message["text"].strip().lower()
                    if cmd == "end":
                        if audio_buffer.tell() == 0:
                            await ws.send_json({"text": "", "segments": [], "is_final": True})
                            continue
                        result = await _transcribe_buffer(audio_buffer, is_final=True)
                        log.info(f"WS-STT (final): \"{result.get('text', '')}\"")
                        await ws.send_json(result)
                        audio_buffer = BytesIO()
                    elif cmd == "partial":
                        if audio_buffer.tell() == 0:
                            await ws.send_json({"text": "", "segments": [], "is_final": False})
                            continue
                        result = await _transcribe_buffer(audio_buffer, is_final=False)
                        log.debug(f"WS-STT (partial): \"{result.get('text', '')}\"")
                        await ws.send_json(result)
                        # Buffer intentionally NOT cleared — audio keeps accumulating
                    elif cmd == "reset":
                        audio_buffer = BytesIO()
                        await ws.send_json({"status": "buffer_cleared"})
            elif message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        log.info("WebSocket STT: client disconnected")


# -- LLM Routes -------------------------------------------------------

@app.post("/v1/chat/completions")
async def llm_chat(request: Request):
    if "llm" not in SERVICES:
        raise HTTPException(503, "LLM service not loaded")

    # Request queue — serialize LLM requests
    if not _LLM_SEMAPHORE.locked():
        pass  # fast path
    else:
        log.info("LLM: request queued (GPU busy)")

    try:
        await asyncio.wait_for(_LLM_SEMAPHORE.acquire(), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(429, "LLM busy — too many concurrent requests")

    released = False
    try:
        body = await request.json()
        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(400, "messages is required")

        max_tokens = body.get("max_tokens", 512)
        temperature = body.get("temperature", 0.7)
        top_p = body.get("top_p", 0.95)
        stream = body.get("stream", False)
        session_id = request.headers.get("x-session-id")

        # Apply named prompt template if requested (injects system prompt + default params)
        template_name = body.get("template")
        if template_name:
            tmpl = _load_templates().get(template_name)
            if tmpl:
                if not any(m.get("role") == "system" for m in messages):
                    messages = [{"role": "system", "content": tmpl["system_prompt"]}] + messages
                max_tokens = body.get("max_tokens", tmpl.get("max_tokens", max_tokens))
                temperature = body.get("temperature", tmpl.get("temperature", temperature))
                log.debug(f"LLM: applied template '{template_name}'")

        if stream:
            generator = SERVICES["llm"].chat(
                messages, max_tokens, temperature, top_p, stream=True, session_id=session_id
            )
            # Wrap generator to hold semaphore until streaming is done.
            _stream_started = False

            def _guarded_stream(gen):
                nonlocal _stream_started
                _stream_started = True
                try:
                    yield from gen
                finally:
                    _LLM_SEMAPHORE.release()

            released = True  # _guarded_stream will release it

            # Safety: background task releases semaphore if the response is discarded
            # without being iterated (e.g. client disconnects before first byte arrives).
            # asyncio.create_task is reliable; weakref.finalize is not (GC timing).
            async def _stream_start_watchdog():
                await asyncio.sleep(30)
                if not _stream_started:
                    log.warning("LLM stream watchdog: response discarded without iteration — releasing semaphore")
                    try:
                        _LLM_SEMAPHORE.release()
                    except Exception:
                        pass

            asyncio.create_task(_stream_start_watchdog())
            return StreamingResponse(
                _guarded_stream(generator), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _INFERENCE_POOL, lambda: SERVICES["llm"].chat(
                    messages, max_tokens, temperature, top_p, stream=False, session_id=session_id
                ))
            return JSONResponse(result)
    except HTTPException:
        raise
    except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
        is_oom = isinstance(e, torch.cuda.OutOfMemoryError) or "out of memory" in str(e).lower()
        if is_oom:
            global _llm_oom_count, _llm_oom_last
            LLM_METRICS.record_error()
            now = time.time()
            if now - _llm_oom_last > 60:
                _llm_oom_count = 0  # reset counter after 60s without OOM
            _llm_oom_count += 1
            _llm_oom_last = now
            gc.collect()
            torch.cuda.empty_cache()
            if _llm_oom_count <= 3:
                log.error(f"LLM: GPU out of memory (OOM #{_llm_oom_count}) — restarting LLM service...")
                # Auto-restart: unload and reload the LLM service
                try:
                    if "llm" in SERVICES:
                        SERVICES["llm"].unload()
                        del SERVICES["llm"]
                        _SERVICE_VRAM.pop("llm", None)
                    gc.collect()
                    torch.cuda.empty_cache()
                    _load_single_service("llm", _LAUNCH_ARGS)
                    log.info("LLM service restarted after OOM")
                except Exception as reload_err:
                    log.error(f"LLM service restart failed: {reload_err}")
            else:
                log.error(
                    f"LLM: GPU OOM limit reached ({_llm_oom_count} consecutive) — "
                    "skipping auto-restart to prevent infinite loop. "
                    "Reduce n_gpu_layers or unload other services, then restart the server."
                )
            raise HTTPException(503, "GPU out of memory — LLM service restarted. Please retry.")
        raise  # re-raise non-OOM RuntimeErrors
    except Exception as e:
        LLM_METRICS.record_error()
        log.error(f"LLM error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))
    finally:
        if not released:
            _LLM_SEMAPHORE.release()


@app.get("/v1/models")
async def list_models():
    models = []
    if "llm" in SERVICES:
        models.append({"id": SERVICES["llm"].model_name, "object": "model", "owned_by": "local"})
    return {"object": "list", "data": models}


# -- TTS Routes --------------------------------------------------------

@app.post("/tts/generate")
async def tts_generate(request: Request):
    if "tts" not in SERVICES:
        raise HTTPException(503, "TTS service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    voice = body.get("voice", None)
    speed = float(body.get("speed", 1.0))
    try:
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["tts"].synthesize(text, voice=voice, speed=speed))
        log.info(f"TTS: \"{text[:60]}\" voice={voice}")
        return StreamingResponse(BytesIO(wav_bytes), media_type="audio/wav",
                                 headers={"Content-Disposition": "attachment; filename=speech.wav",
                                          "Content-Length": str(len(wav_bytes))})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        log.error(f"TTS error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/tts/generate/stream")
async def tts_generate_stream(request: Request):
    """Stream TTS audio sentence-by-sentence. Returns audio/wav chunks as they're synthesized.
    Clients receive the first audio ~50ms after the request instead of waiting for the full text.
    Each chunk is a complete, independently playable WAV file.
    """
    if "tts" not in SERVICES:
        raise HTTPException(503, "TTS service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    voice = body.get("voice", None)
    speed = float(body.get("speed", 1.0))

    loop = asyncio.get_running_loop()

    async def _generate():
        try:
            sentences = list(SERVICES["tts"].synthesize_streaming.__func__.__code__.co_consts)
        except Exception:
            pass
        # Run each sentence synthesis in the inference pool, yield chunks as they complete
        import re as _re_tts
        parts = [s.strip() for s in _re_tts.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not parts:
            parts = [text]
        for part in parts:
            try:
                wav = await loop.run_in_executor(
                    _INFERENCE_POOL, lambda p=part: SERVICES["tts"].synthesize(p, voice=voice, speed=speed)
                )
                yield wav
            except Exception as e:
                log.warning(f"TTS stream chunk error: {e}")

    log.info(f"TTS stream: \"{text[:60]}\" voice={voice}")
    return StreamingResponse(_generate(), media_type="audio/wav",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.get("/tts/voices")
async def tts_voices():
    if "tts" not in SERVICES:
        raise HTTPException(503, "TTS service not loaded")
    return {"voices": SERVICES["tts"].list_voices()}


# -- Vision Routes -----------------------------------------------------

@app.post("/caption")
async def vision_caption(image: UploadFile = File(...), prompt: str = Form(None)):
    image_bytes = await image.read()
    loop = asyncio.get_running_loop()
    if "vision" in SERVICES:
        try:
            svc = SERVICES["vision"]
            caption = await loop.run_in_executor(_INFERENCE_POOL, lambda: svc.caption(image_bytes, prompt=prompt or None))
            log.info(f"Vision ({svc.backend}): \"{caption}\"")
            return {"caption": caption}
        except torch.cuda.OutOfMemoryError:
            gc.collect()
            torch.cuda.empty_cache()
            log.error("Vision: GPU out of memory during captioning")
            raise HTTPException(503, "GPU out of memory — try a smaller image or lighter vision model.")
        except Exception:
            log.error(f"Vision error: {traceback.format_exc()}")
            raise HTTPException(500, "Vision captioning failed")
    raise HTTPException(503, "Vision service not loaded")


# -- Image Generation Routes -------------------------------------------

@app.post("/sdapi/v1/txt2img")
async def sdapi_txt2img(request: Request):
    if "imagegen" not in SERVICES:
        raise HTTPException(503, "Image generation service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt is required")
    try:
        loop = asyncio.get_running_loop()
        dsz = SERVICES["imagegen"].default_size
        gen_kwargs = dict(
            prompt=prompt, negative_prompt=body.get("negative_prompt", ""),
            steps=int(body.get("steps", 20)), cfg_scale=float(body.get("cfg_scale", 7.0)),
            width=int(body.get("width", dsz)), height=int(body.get("height", dsz)),
            seed=int(body.get("seed", -1)), sampler_name=body.get("sampler_name"),
        )
        image_bytes = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["imagegen"].generate(**gen_kwargs))
        log.info(f"ImageGen: \"{prompt[:60]}\"")
        return {"images": [base64.b64encode(image_bytes).decode()], "parameters": body, "info": ""}
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        torch.cuda.empty_cache()
        log.error("ImageGen: GPU out of memory. Try smaller resolution or fewer steps.")
        raise HTTPException(503, "GPU out of memory — try smaller width/height or fewer steps.")
    except Exception as e:
        log.error(f"ImageGen error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/generate_image")
async def generate_image_simple(request: Request):
    if "imagegen" not in SERVICES:
        raise HTTPException(503, "Image generation service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt is required")
    try:
        task_id = body.get("task_id")
        dsz = SERVICES["imagegen"].default_size
        loop = asyncio.get_running_loop()
        gen_kwargs = dict(
            prompt=prompt, negative_prompt=body.get("negative_prompt", ""),
            steps=int(body.get("steps", 20)), cfg_scale=float(body.get("cfg_scale", 7.0)),
            width=int(body.get("width", dsz)), height=int(body.get("height", dsz)),
            seed=int(body.get("seed", -1)), sampler_name=body.get("sampler_name"),
            task_id=task_id,
        )
        image_bytes = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["imagegen"].generate(**gen_kwargs))
        log.info(f"ImageGen: \"{prompt[:60]}\"")
        # Save to output folder with timestamp metadata
        out_dir = Path(__file__).parent / "output" / "imagegen"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{uuid.uuid4().hex[:8]}.png"
        fpath = out_dir / fname
        with open(str(fpath), "wb") as f:
            f.write(image_bytes)
        # Save JSON sidecar for fast gallery listing (no need to re-open every PNG)
        meta = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": prompt,
            "negative_prompt": body.get("negative_prompt", ""),
            "steps": str(gen_kwargs["steps"]),
            "cfg_scale": str(gen_kwargs["cfg_scale"]),
            "width": str(gen_kwargs["width"]),
            "height": str(gen_kwargs["height"]),
            "seed": str(gen_kwargs["seed"]),
        }
        with open(str(fpath.with_suffix(".json")), "w") as f:
            json.dump(meta, f)
        return StreamingResponse(BytesIO(image_bytes), media_type="image/png",
                                 headers={"X-Image-Filename": fname})
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        torch.cuda.empty_cache()
        log.error("ImageGen: GPU out of memory. Try smaller resolution or fewer steps.")
        raise HTTPException(503, "GPU out of memory — try smaller width/height or fewer steps.")
    except Exception as e:
        log.error(f"ImageGen error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.get("/imagegen_gallery")
async def imagegen_gallery_list():
    out_dir = Path(__file__).parent / "output" / "imagegen"
    if not out_dir.exists():
        return {"images": []}
    files = sorted(out_dir.glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    results = []
    for f in files:
        meta = {}
        json_path = str(f.with_suffix(".json"))
        if os.path.exists(json_path):
            try:
                with open(json_path) as jf:
                    meta = json.load(jf)
            except Exception:
                pass
        results.append({"filename": f.name, "meta": meta})
    return {"images": results}


@app.get("/imagegen_gallery/file/{filename}")
async def imagegen_gallery_file(filename: str):
    if not _RE_PNG_FILENAME.match(filename):
        raise HTTPException(400, "Invalid filename")
    fpath = Path(__file__).parent / "output" / "imagegen" / filename
    if not fpath.exists():
        raise HTTPException(404, "File not found")
    from starlette.responses import FileResponse
    return FileResponse(str(fpath), media_type="image/png")


@app.delete("/imagegen_gallery/{filename}")
async def imagegen_gallery_delete(filename: str):
    if not _RE_PNG_FILENAME.match(filename):
        raise HTTPException(400, "Invalid filename")
    fpath = Path(__file__).parent / "output" / "imagegen" / filename
    if not fpath.exists():
        raise HTTPException(404, "File not found")
    fpath.unlink()
    json_path = fpath.with_suffix(".json")
    if json_path.exists():
        json_path.unlink()
    return {"ok": True}


@app.get("/imagegen_progress/{task_id}")
async def imagegen_progress(task_id: str):
    info = ImageGenService._progress.get(task_id)
    if info is None:
        return {"step": 0, "total": 0, "active": False}
    return {"step": info["step"], "total": info["total"], "active": True}


# -- MusicGen Routes ---------------------------------------------------

@app.post("/generate_music")
async def generate_music(request: Request):
    if "musicgen" not in SERVICES:
        raise HTTPException(503, "Music generation service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt is required")
    try:
        task_id = body.get("task_id")
        lyrics = body.get("lyrics", "")
        loop = asyncio.get_running_loop()
        batch_size = max(1, min(16, int(body.get("batch_size", 1))))
        gen_kwargs = dict(
            prompt=prompt,
            lyrics=lyrics,
            duration_sec=float(body.get("duration", 30)),
            infer_steps=int(body.get("steps", 60)),
            guidance_scale=float(body.get("guidance_scale", 15.0)),
            seed=int(body.get("seed", -1)),
            task_id=task_id,
            scheduler_type=body.get("scheduler_type", "euler"),
            cfg_type=body.get("cfg_type", "apg"),
            omega_scale=float(body.get("omega_scale", 10.0)),
            guidance_interval=float(body.get("guidance_interval", 0.5)),
            min_guidance_scale=float(body.get("min_guidance_scale", 3.0)),
            batch_size=batch_size,
        )
        ogg_list = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["musicgen"].generate(**gen_kwargs))
        log.info(f"MusicGen: \"{prompt[:60]}\" (batch={batch_size}, got {len(ogg_list)})")
        # Save all outputs to gallery with JSON sidecar metadata
        out_dir = Path(__file__).parent / "output" / "musicgen"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        filenames = []
        meta_base = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": prompt,
            "lyrics": lyrics,
            "duration": gen_kwargs["duration_sec"],
            "steps": gen_kwargs["infer_steps"],
            "guidance_scale": gen_kwargs["guidance_scale"],
            "seed": gen_kwargs["seed"],
            "scheduler_type": gen_kwargs["scheduler_type"],
            "cfg_type": gen_kwargs["cfg_type"],
            "omega_scale": gen_kwargs["omega_scale"],
            "guidance_interval": gen_kwargs["guidance_interval"],
            "min_guidance_scale": gen_kwargs["min_guidance_scale"],
            "batch_size": batch_size,
        }
        for i, audio_bytes in enumerate(ogg_list):
            fname = f"{ts}_{uuid.uuid4().hex[:8]}.ogg"
            fpath = out_dir / fname
            with open(str(fpath), "wb") as f:
                f.write(audio_bytes)
            meta = {**meta_base, "batch_index": i}
            with open(str(fpath.with_suffix(".json")), "w") as f:
                json.dump(meta, f)
            filenames.append(fname)
        # For batch=1, return audio stream directly (backwards compatible)
        if batch_size == 1:
            return StreamingResponse(BytesIO(ogg_list[0]), media_type="audio/ogg",
                                     headers={"X-Audio-Filename": filenames[0]})
        # For batch>1, return JSON with filenames so the UI can load from gallery
        return JSONResponse({"filenames": filenames, "count": len(filenames)})
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        torch.cuda.empty_cache()
        log.error("MusicGen: GPU out of memory. Try shorter duration or fewer steps.")
        raise HTTPException(503, "GPU out of memory — try shorter duration or fewer steps.")
    except Exception as e:
        log.error(f"MusicGen error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.get("/musicgen_gallery")
async def musicgen_gallery_list():
    out_dir = Path(__file__).parent / "output" / "musicgen"
    if not out_dir.exists():
        return {"tracks": []}
    files = sorted(
        [f for f in out_dir.iterdir() if f.suffix in (".ogg", ".wav") and not f.name.startswith(".")],
        key=lambda f: f.stat().st_mtime, reverse=True)
    results = []
    for f in files:
        meta = {}
        json_path = str(f.with_suffix(".json"))
        if os.path.exists(json_path):
            try:
                with open(json_path) as jf:
                    meta = json.load(jf)
            except Exception:
                pass
        results.append({"filename": f.name, "meta": meta})
    return {"tracks": results}


@app.get("/musicgen_gallery/file/{filename}")
async def musicgen_gallery_file(filename: str):
    if not _RE_AUDIO_FILENAME.match(filename):
        raise HTTPException(400, "Invalid filename")
    fpath = Path(__file__).parent / "output" / "musicgen" / filename
    if not fpath.exists():
        raise HTTPException(404, "File not found")
    from starlette.responses import FileResponse
    media = "audio/ogg" if fpath.suffix == ".ogg" else "audio/wav"
    return FileResponse(str(fpath), media_type=media)


@app.delete("/musicgen_gallery/{filename}")
async def musicgen_gallery_delete(filename: str):
    if not _RE_AUDIO_FILENAME.match(filename):
        raise HTTPException(400, "Invalid filename")
    fpath = Path(__file__).parent / "output" / "musicgen" / filename
    if not fpath.exists():
        raise HTTPException(404, "File not found")
    # Retry unlink in case the browser hasn't fully released the file handle yet (Windows)
    import time as _time
    for _attempt in range(5):
        try:
            fpath.unlink()
            break
        except PermissionError:
            if _attempt == 4:
                raise HTTPException(423, "File is locked — try again in a moment")
            _time.sleep(0.3)
    json_path = fpath.with_suffix(".json")
    if json_path.exists():
        json_path.unlink()
    return {"ok": True}


@app.get("/musicgen_progress/{task_id}")
async def musicgen_progress(task_id: str):
    info = MusicGenService._progress.get(task_id)
    if info is None:
        return {"status": "idle", "pct": 0, "active": False}
    return {"status": info["status"], "pct": info["pct"], "active": True}


# -- Embeddings Routes -------------------------------------------------

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    if "embeddings" not in SERVICES:
        raise HTTPException(503, "Embeddings service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    inp = body.get("input", [])
    if isinstance(inp, str):
        inp = [inp]
    if not inp:
        raise HTTPException(400, "input is required")
    try:
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(_INFERENCE_POOL, SERVICES["embeddings"].embed, inp)
        data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
        # Estimate token count: ~1.3 tokens per word (closer to BPE reality than raw word count)
        est_tokens = int(sum(len(t.split()) for t in inp) * 1.3)
        return {"object": "list", "data": data, "model": SERVICES["embeddings"].model_name,
                "usage": {"prompt_tokens": est_tokens, "total_tokens": est_tokens}}
    except Exception as e:
        log.error(f"Embeddings error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


# -- Model Management --------------------------------------------------

@app.get("/models/status")
async def models_status():
    gpu = get_gpu_stats()
    models = {}
    for name, svc in SERVICES.items():
        info = {"status": "loaded"}
        if hasattr(svc, "model_name"):
            info["model"] = svc.model_name
        if name == "tts" and hasattr(svc, "list_voices"):
            info["voices"] = svc.list_voices()
        models[name] = info
    return {"gpu": gpu, "models": models}


@app.post("/models/{service}/unload")
async def unload_model(service: str):
    if service not in SERVICES:
        return JSONResponse(status_code=404, content={"error": f"Service '{service}' not loaded"})
    svc = SERVICES[service]
    svc_name = getattr(svc, "model_name", service)
    if hasattr(svc, "unload"):
        svc.unload()
    del SERVICES[service]
    _SERVICE_VRAM.pop(service, None)
    gc.collect()
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    log.info(f"Unloaded {service.upper()} ({svc_name})")
    return {"status": "unloaded", "service": service, "gpu": get_gpu_stats()}


@app.post("/models/{service}/reload")
async def reload_model(service: str):
    if _LAUNCH_ARGS is None:
        raise HTTPException(500, "Launch args not available")
    if service in SERVICES:
        svc = SERVICES[service]
        if hasattr(svc, "unload"):
            svc.unload()
        del SERVICES[service]
        _SERVICE_VRAM.pop(service, None)
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
    _load_service_safe(service, _LAUNCH_ARGS)
    if service not in SERVICES:
        raise HTTPException(500, f"Failed to reload {service}")
    log.info(f"Reloaded {service.upper()}")
    return {"status": "loaded", "service": service, "gpu": get_gpu_stats()}


# -- Config hot-reload -------------------------------------------------

@app.post("/config/reload")
async def config_reload():
    """Reload config-server.ini without restarting. Affects auth, rate limits, non-model settings."""
    load_config()
    log.info("Config reloaded from disk")
    return {"status": "reloaded", "file": str(CONFIG_FILE)}


# -- Cloudflare Tunnel (remote access) ---------------------------------

import subprocess as _sp
import shutil
import platform as _platform

# Pre-compiled regex for gallery filename validation (used on every gallery request)
_RE_PNG_FILENAME = _re.compile(r'^[\w\-]+\.png$')
_RE_AUDIO_FILENAME = _re.compile(r'^[\w\-]+\.(ogg|wav)$')

_tunnel_process = None
_tunnel_url = None
_tunnel_error = None
_tunnel_starting = False
_tunnel_lock = Lock()
_CLOUDFLARED_DIR = Path(__file__).parent / "bin"


def _cloudflared_bin():
    """Return path to cloudflared binary — checks system PATH then local download."""
    found = shutil.which("cloudflared")
    if found:
        return found
    _CLOUDFLARED_DIR.mkdir(exist_ok=True)
    local = _CLOUDFLARED_DIR / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared")
    if local.exists():
        return str(local)
    return None


def _install_cloudflared():
    """Download cloudflared binary for the current platform (cross-platform)."""
    import urllib.request

    _CLOUDFLARED_DIR.mkdir(exist_ok=True)
    base_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    arch = _platform.machine().lower()

    if sys.platform == "win32":
        filename = "cloudflared-windows-amd64.exe"
        local_name = "cloudflared.exe"
    elif sys.platform == "darwin":
        suffix = "arm64" if arch in ("arm64", "aarch64") else "amd64"
        filename = f"cloudflared-darwin-{suffix}.tgz"
        local_name = "cloudflared"
    else:
        if arch in ("aarch64", "arm64"):
            filename = "cloudflared-linux-arm64"
        elif arch in ("armv7l", "armhf"):
            filename = "cloudflared-linux-arm"
        else:
            filename = "cloudflared-linux-amd64"
        local_name = "cloudflared"

    dest = _CLOUDFLARED_DIR / local_name
    url = base_url + filename
    try:
        log.info(f"Downloading cloudflared: {filename} ...")
        urllib.request.urlretrieve(url, str(dest))

        # macOS tgz needs extraction
        if filename.endswith(".tgz"):
            import tarfile
            with tarfile.open(str(dest), "r:gz") as tar:
                tar.extractall(path=str(_CLOUDFLARED_DIR))
            dest.unlink()
            dest = _CLOUDFLARED_DIR / "cloudflared"

        if sys.platform != "win32":
            os.chmod(str(dest), 0o755)

        log.info(f"cloudflared installed to {dest}")
        return True, ""
    except Exception as e:
        log.error(f"Failed to install cloudflared: {e}")
        if dest.exists():
            dest.unlink()
        return False, str(e)


def _start_tunnel(port: int):
    global _tunnel_process, _tunnel_url
    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return True, _tunnel_url
        _stop_tunnel_internal()
        bin_path = _cloudflared_bin()
        if not bin_path:
            return False, "cloudflared not installed"
        try:
            popen_kwargs = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
            proc = _sp.Popen(
                [bin_path, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=_sp.PIPE, stderr=_sp.PIPE, text=True,
                **popen_kwargs,
            )
        except Exception as e:
            return False, str(e)
        url = None
        url_pattern = _re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            match = url_pattern.search(line)
            if match:
                url = match.group(0)
                break
        if not url:
            proc.kill()
            return False, "Could not get tunnel URL (cloudflared may have failed to start)"
        _tunnel_process = proc
        _tunnel_url = url

        def _drain():
            try:
                for _ in proc.stderr:
                    pass
            except Exception:
                pass
        Thread(target=_drain, daemon=True).start()
        log.info(f"Tunnel active: {url}")
        return True, url


def _stop_tunnel_internal():
    global _tunnel_process, _tunnel_url
    if _tunnel_process:
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=5)
        except Exception:
            try:
                _tunnel_process.kill()
            except Exception:
                pass
        _tunnel_process = None
    _tunnel_url = None


def _stop_tunnel():
    with _tunnel_lock:
        _stop_tunnel_internal()


def _get_tunnel_status():
    global _tunnel_process
    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return {"state": "active", "url": _tunnel_url}
        if _tunnel_process:
            _tunnel_process = None
        if _tunnel_starting:
            return {"state": "starting"}
        return {"state": "inactive"}


@app.get("/api/tunnel/status")
async def tunnel_status():
    info = _get_tunnel_status()
    info["installed"] = _cloudflared_bin() is not None
    if info["state"] == "inactive" and _tunnel_error:
        info["state"] = "error"
        info["error"] = _tunnel_error
    return info


@app.post("/api/tunnel/start")
async def tunnel_start():
    global _tunnel_error
    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return {"state": "active", "url": _tunnel_url}
    _tunnel_error = None
    port = int(_active_config.get("server", "port", fallback="5678")) if _active_config else 5678

    def _bg_start():
        global _tunnel_error, _tunnel_starting
        _tunnel_starting = True
        try:
            if not _cloudflared_bin():
                ok, err = _install_cloudflared()
                if not ok:
                    _tunnel_error = err
                    return
            ok, result = _start_tunnel(port)
            if not ok:
                _tunnel_error = result
        finally:
            _tunnel_starting = False

    Thread(target=_bg_start, daemon=True).start()
    return {"state": "starting"}


@app.post("/api/tunnel/stop")
async def tunnel_stop():
    _stop_tunnel()
    return {"state": "inactive"}


@app.get("/api/tunnel/qr")
async def tunnel_qr(url: str = ""):
    if not url:
        raise HTTPException(400, "No URL")
    try:
        import qrcode
    except ImportError:
        raise HTTPException(500, "qrcode not installed — pip install qrcode[pil]")
    buf = BytesIO()
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#c0c0c0", back_color="#0a1220")
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# -- Playground --------------------------------------------------------

@app.get("/playground", response_class=HTMLResponse)
async def playground():
    return _read_www("playground.html")





# -- Per-service health endpoints (Feature 1) -------------------------

@app.get("/health/{service}")
async def service_health(service: str):
    """Per-service health check with model info, VRAM, and latency."""
    if service not in SERVICES:
        # Check if it's a known service that's just disabled
        all_svcs = ["stt", "tts", "llm", "vision", "imagegen", "musicgen", "embeddings"]
        if service in all_svcs:
            return JSONResponse({"status": "disabled", "service": service}, status_code=200)
        raise HTTPException(404, f"Unknown service: {service}")
    svc = SERVICES[service]
    info = {"status": "ready", "service": service}
    if hasattr(svc, "model_name"):
        info["model"] = svc.model_name
    if service in _SERVICE_VRAM:
        info["vram_gb"] = _SERVICE_VRAM[service]
    latency = TRACKER.get_latency_stats()
    if service in latency:
        info["latency"] = latency[service]
    return info


# -- TTS Streaming endpoint (Feature 2) -------------------------------

@app.post("/tts/stream")
async def tts_stream(request: Request):
    """Stream TTS audio sentence-by-sentence for lower time-to-first-audio."""
    if "tts" not in SERVICES:
        raise HTTPException(503, "TTS service not loaded")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    voice = body.get("voice", None)
    speed = float(body.get("speed", 1.0))

    # Split into sentences for chunked streaming
    import re as _sentence_re
    sentences = _sentence_re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    loop = asyncio.get_running_loop()

    async def _stream_sentences():
        for sentence in sentences:
            try:
                wav_bytes = await loop.run_in_executor(
                    _INFERENCE_POOL,
                    lambda s=sentence: SERVICES["tts"].synthesize(s, voice=voice, speed=speed)
                )
                # Send length-prefixed WAV chunks so the client knows boundaries
                yield struct.pack("<I", len(wav_bytes)) + wav_bytes
            except Exception as e:
                log.error(f"TTS stream error on sentence: {e}")
                break

    log.info(f"TTS stream: \"{text[:60]}\" ({len(sentences)} chunks) voice={voice}")
    return StreamingResponse(
        _stream_sentences(),
        media_type="application/octet-stream",
        headers={"X-TTS-Chunks": str(len(sentences))},
    )


# -- Model download progress (Feature 3) ------------------------------

_download_progress: dict = {}  # task_id -> {"status": str, "pct": int, "speed_mbps": float, "file": str}


@app.get("/models/download-progress")
async def model_download_progress():
    """SSE endpoint streaming download progress for active model downloads."""
    async def _event_stream():
        while True:
            if _download_progress:
                for task_id, info in list(_download_progress.items()):
                    yield f"data: {json.dumps({'task_id': task_id, **info})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'idle'})}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/models/download-progress/{task_id}")
async def model_download_progress_single(task_id: str):
    """Poll-based download progress for a specific task."""
    info = _download_progress.get(task_id)
    if info is None:
        return {"status": "idle", "pct": 0, "active": False}
    return {**info, "active": True}


# -- Multi-GPU device listing (Feature 4) -----------------------------

@app.get("/api/devices")
async def list_devices():
    """List available compute devices (for multi-GPU selection in settings)."""
    devices = [{"id": "cpu", "name": "CPU", "type": "cpu"}]
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            devices.append({
                "id": f"cuda:{i}",
                "name": props.name,
                "type": "cuda",
                "vram_gb": round(props.total_memory / 1024**3, 2),
            })
    return {"devices": devices}


# -- Batch embeddings with chunking (Feature 6) -----------------------
# (Integrated into existing /v1/embeddings — see EmbeddingsService.embed_batched below)


# -- Webhook/callback for async tasks (Feature 7) --------------------

_async_tasks: dict = {}  # task_id -> {"status": str, "result": any, "created": float}
_ASYNC_TASK_TTL = 600   # seconds — completed/errored tasks evicted after 10 min (results can be 3MB+ base64)


def _evict_old_tasks():
    """Remove completed/errored tasks older than _ASYNC_TASK_TTL. Called on each new submission."""
    cutoff = time.time() - _ASYNC_TASK_TTL
    stale = [tid for tid, t in _async_tasks.items()
             if t.get("status") in ("done", "error") and t.get("created", 0) < cutoff]
    for tid in stale:
        del _async_tasks[tid]
    if stale:
        log.debug(f"Evicted {len(stale)} stale async task(s)")


@app.post("/tasks/submit")
async def submit_async_task(request: Request):
    """Submit a long-running task (musicgen, imagegen) with optional callback_url.
    Returns immediately with a task_id for polling or webhook delivery."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    task_type = body.get("type", "")
    callback_url = body.get("callback_url", None)
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    _evict_old_tasks()
    _async_tasks[task_id] = {"status": "queued", "result": None, "created": time.time()}

    async def _run_task():
        try:
            _async_tasks[task_id]["status"] = "running"
            loop = asyncio.get_running_loop()
            if task_type == "imagegen" and "imagegen" in SERVICES:
                dsz = SERVICES["imagegen"].default_size
                gen_kwargs = dict(
                    prompt=body.get("prompt", ""),
                    negative_prompt=body.get("negative_prompt", ""),
                    steps=int(body.get("steps", 20)),
                    cfg_scale=float(body.get("cfg_scale", 7.0)),
                    width=int(body.get("width", dsz)),
                    height=int(body.get("height", dsz)),
                    seed=int(body.get("seed", -1)),
                    task_id=task_id,
                )
                image_bytes = await loop.run_in_executor(
                    _INFERENCE_POOL, lambda: SERVICES["imagegen"].generate(**gen_kwargs))
                result_b64 = base64.b64encode(image_bytes).decode()
                _async_tasks[task_id] = {"status": "done", "result": {"image_b64": result_b64}, "created": _async_tasks[task_id]["created"]}
            elif task_type == "musicgen" and "musicgen" in SERVICES:
                gen_kwargs = dict(
                    prompt=body.get("prompt", ""),
                    lyrics=body.get("lyrics", ""),
                    duration_sec=float(body.get("duration", 30)),
                    infer_steps=int(body.get("steps", 60)),
                    guidance_scale=float(body.get("guidance_scale", 15.0)),
                    seed=int(body.get("seed", -1)),
                    task_id=task_id,
                )
                ogg_list = await loop.run_in_executor(
                    _INFERENCE_POOL, lambda: SERVICES["musicgen"].generate(**gen_kwargs))
                result_b64 = [base64.b64encode(o).decode() for o in ogg_list]
                _async_tasks[task_id] = {"status": "done", "result": {"audio_b64": result_b64}, "created": _async_tasks[task_id]["created"]}
            else:
                _async_tasks[task_id]["status"] = "error"
                _async_tasks[task_id]["result"] = {"error": f"Unknown task type or service not loaded: {task_type}"}
                return
            # Deliver webhook if requested
            if callback_url:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10) as _hc:
                        await _hc.post(callback_url, json={"task_id": task_id, **_async_tasks[task_id]})
                except Exception as e:
                    log.warning(f"Webhook delivery failed for {task_id}: {e}")
        except Exception as e:
            _async_tasks[task_id] = {"status": "error", "result": {"error": str(e)}, "created": _async_tasks.get(task_id, {}).get("created", 0)}

    asyncio.create_task(_run_task())
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    info = _async_tasks.get(task_id)
    if info is None:
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, **info}


# -- LLM prompt templates (Feature 8) ---------------------------------

_TEMPLATES_FILE = Path(__file__).parent / "prompt_templates.json"


def _load_templates() -> dict:
    if _TEMPLATES_FILE.exists():
        try:
            return json.loads(_TEMPLATES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_templates(templates: dict):
    _TEMPLATES_FILE.write_text(json.dumps(templates, indent=2), encoding="utf-8")


@app.get("/api/templates")
async def list_templates():
    return {"templates": _load_templates()}


@app.post("/api/templates")
async def save_template(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    templates = _load_templates()
    templates[name] = {
        "system_prompt": body.get("system_prompt", ""),
        "description": body.get("description", ""),
        "temperature": body.get("temperature", 0.7),
        "max_tokens": body.get("max_tokens", 512),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_templates(templates)
    return {"status": "saved", "name": name}


@app.delete("/api/templates/{name}")
async def delete_template(name: str):
    templates = _load_templates()
    if name not in templates:
        raise HTTPException(404, f"Template '{name}' not found")
    del templates[name]
    _save_templates(templates)
    return {"status": "deleted", "name": name}


# -- Application log streaming (Feature 9) ----------------------------

class _WebSocketLogHandler(logging.Handler):
    """Logging handler that broadcasts log records to connected WebSocket clients."""
    def __init__(self):
        super().__init__()
        self._clients: list = []
        self._lock = Lock()
        self._buffer: collections.deque = collections.deque(maxlen=200)

    def add_client(self, q):
        with self._lock:
            self._clients.append(q)

    def remove_client(self, q):
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def emit(self, record):
        entry = {
            "time": self.format(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        with self._lock:
            self._buffer.append(entry)
            for q in self._clients:
                try:
                    q.append(entry)
                except Exception:
                    pass

    def get_recent(self, n=50):
        with self._lock:
            return list(self._buffer)[-n:]


_ws_log_handler = _WebSocketLogHandler()
_ws_log_handler.setFormatter(logging.Formatter("%(asctime)s", datefmt="%H:%M:%S"))
_ws_log_handler.setLevel(logging.INFO)
logging.getLogger("tars-server").addHandler(_ws_log_handler)


@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    """Stream application logs in real-time."""
    await ws.accept()
    client_buffer = collections.deque(maxlen=100)
    _ws_log_handler.add_client(client_buffer)
    try:
        # Send recent history first
        for entry in _ws_log_handler.get_recent(50):
            await ws.send_json(entry)
        while True:
            while client_buffer:
                entry = client_buffer.popleft()
                try:
                    await ws.send_json(entry)
                except Exception:
                    return
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ws_log_handler.remove_client(client_buffer)
        try:
            await ws.close()
        except Exception:
            pass


# -- VRAM budget per service (Feature 11) ------------------------------

def _get_vram_budget(service: str) -> float:
    """Get VRAM budget in GB for a service (0 = unlimited)."""
    cfg = _active_config or load_config()
    return cfg.getfloat(service, "vram_limit_gb", fallback=0.0)


def _check_vram_budget(service: str) -> bool:
    """Check if loading a service would exceed VRAM budget. Returns True if OK to load."""
    budget = _get_vram_budget(service)
    if budget <= 0:
        return True  # no limit configured
    vram = _gpu_vram()
    if vram is None:
        return True  # can't check, allow
    free_gb = vram[1]
    if free_gb < budget:
        log.warning(
            f"{service.upper()}: insufficient VRAM — need {budget:.1f} GB budget but only "
            f"{free_gb:.1f} GB free. Skipping load. Set vram_limit_gb=0 to disable this check."
        )
        return False
    if free_gb < budget * 1.25:
        log.warning(f"{service.upper()}: VRAM is tight — {free_gb:.1f} GB free for {budget:.1f} GB budget")
    return True


# -- OpenAI-compatible STT endpoint (Feature 12) ----------------------

@app.post("/v1/audio/transcriptions")
async def openai_stt(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: Optional[str] = Form(None),
    response_format: str = Form("json"),
):
    """OpenAI Whisper-compatible transcription endpoint.
    Accepts the same parameters as https://platform.openai.com/docs/api-reference/audio/createTranscription
    """
    if "stt" not in SERVICES:
        raise HTTPException(503, "STT service not loaded")
    audio_bytes = BytesIO(await file.read())
    loop = asyncio.get_running_loop()
    try:
        samples = await loop.run_in_executor(_INFERENCE_POOL, SERVICES["stt"]._wav_to_float32, audio_bytes)
        has_speech = await loop.run_in_executor(_INFERENCE_POOL, lambda: SERVICES["stt"].has_speech(audio_bytes, samples=samples))
        if not has_speech:
            if response_format == "text":
                return HTMLResponse("")
            return {"text": ""}
        audio_bytes.seek(0)
        transcription, info = await loop.run_in_executor(
            _INFERENCE_POOL, lambda: SERVICES["stt"].transcribe(audio_bytes, language=language, samples=samples)
        )
        full_text = " ".join(t["text"] for t in transcription).strip()
        log.info(f"STT (OpenAI compat): \"{full_text}\"")
        if response_format == "text":
            return HTMLResponse(full_text, media_type="text/plain")
        elif response_format == "verbose_json":
            return {
                "task": "transcribe",
                "language": info.language,
                "duration": transcription[-1]["end"] if transcription else 0,
                "text": full_text,
                "segments": transcription,
            }
        else:
            return {"text": full_text}
    except Exception as e:
        log.error(f"STT error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


# ===================================================================
# Settings API + HUD-themed Settings Page
# ===================================================================
@app.get("/api/settings")
async def api_get_settings():
    cfg = _active_config or load_config()
    result = {}
    for section in _CONFIG_DEFAULTS:
        result[section] = {}
        for key in _CONFIG_DEFAULTS[section]:
            result[section][key] = cfg.get(section, key, fallback=_CONFIG_DEFAULTS[section][key])
    result["_meta"] = {"has_cuda": torch.cuda.is_available(), "global_device": DEVICE}
    return result


@app.post("/api/settings")
async def api_save_settings(request: Request):
    body = await request.json()

    # Snapshot current service states BEFORE saving
    old_cfg = _active_config or load_config()
    _ALL_SERVICES = ["stt", "tts", "llm", "vision", "imagegen", "musicgen", "embeddings"]
    old_enabled = {s: old_cfg.getboolean("services", s, fallback=False) for s in _ALL_SERVICES}

    # Save new config
    cfg = configparser.ConfigParser()
    for section in _CONFIG_DEFAULTS:
        if section in body:
            cfg[section] = {k: str(v) for k, v in body[section].items()}
        else:
            cfg[section] = dict(_CONFIG_DEFAULTS[section])
    save_config(cfg)
    load_config()

    # Detect which services changed enabled/disabled
    new_enabled = {s: cfg.getboolean("services", s, fallback=False) for s in _ALL_SERVICES}
    unloaded = []
    loaded = []
    load_errors = []
    needs_restart = []

    for svc in _ALL_SERVICES:
        was_on = old_enabled[svc]
        now_on = new_enabled[svc]

        if was_on and not now_on:
            # Service was disabled — unload it immediately
            if svc in SERVICES:
                try:
                    s = SERVICES[svc]
                    if hasattr(s, "unload"):
                        s.unload()
                    del SERVICES[svc]
                    _SERVICE_VRAM.pop(svc, None)
                    gc.collect()
                    if DEVICE == "cuda":
                        torch.cuda.empty_cache()
                    unloaded.append(svc.upper())
                    log.info(f"Settings: unloaded {svc.upper()} (disabled by user)")
                except Exception as e:
                    log.error(f"Settings: failed to unload {svc.upper()}: {e}")

        elif not was_on and now_on:
            # Service was enabled — load it now
            if svc not in SERVICES and _LAUNCH_ARGS:
                try:
                    _load_service_safe(svc, _LAUNCH_ARGS)
                    if svc in SERVICES:
                        loaded.append(svc.upper())
                        log.info(f"Settings: loaded {svc.upper()} (enabled by user)")
                    else:
                        load_errors.append(f"{svc.upper()} (not enough GPU memory?)")
                except torch.cuda.OutOfMemoryError:
                    _cleanup_failed_service(svc)
                    load_errors.append(f"{svc.upper()} (GPU out of memory)")
                    log.error(f"Settings: GPU OOM loading {svc.upper()}")
                except Exception as e:
                    load_errors.append(svc.upper())
                    log.error(f"Settings: failed to load {svc.upper()}: {e}")
            elif not _LAUNCH_ARGS:
                needs_restart.append(svc.upper())

    # Build response message
    parts = []
    if unloaded:
        parts.append(f"Unloaded: {', '.join(unloaded)}")
    if loaded:
        parts.append(f"Loaded: {', '.join(loaded)}")
    if load_errors:
        parts.append(f"Failed to load: {', '.join(load_errors)}")
    if needs_restart:
        parts.append(f"Restart needed for: {', '.join(needs_restart)}")
    if not parts:
        parts.append("Settings saved")

    # Auto-reload services whose model config changed (not just enable/disable)
    _RELOAD_KEYS = {
        "llm": ("model", "backend", "dtype", "quantize", "n_ctx", "cache_type_k", "cache_type_v"),
        "stt": ("whisper_model", "compute_type", "engine"),
        "vision": ("model",),
        "imagegen": ("model",),
        "musicgen": ("model",),
        "embeddings": ("model",),
    }
    reloaded = []
    for svc, keys in _RELOAD_KEYS.items():
        if svc in SERVICES and new_enabled.get(svc) and _LAUNCH_ARGS:
            changed = any(
                old_cfg.get(svc, k, fallback="") != cfg.get(svc, k, fallback="")
                for k in keys
            )
            if changed:
                try:
                    old_svc = SERVICES[svc]
                    if hasattr(old_svc, "unload"):
                        old_svc.unload()
                    del SERVICES[svc]
                    _SERVICE_VRAM.pop(svc, None)
                    gc.collect()
                    if DEVICE == "cuda":
                        torch.cuda.empty_cache()
                    _load_service_safe(svc, _LAUNCH_ARGS)
                    if svc in SERVICES:
                        reloaded.append(svc.upper())
                        log.info(f"Settings: reloaded {svc.upper()} (config changed)")
                    else:
                        load_errors.append(f"{svc.upper()} (reload failed)")
                except Exception as e:
                    load_errors.append(f"{svc.upper()} (reload error)")
                    log.error(f"Settings: failed to reload {svc.upper()}: {e}")

    if reloaded:
        parts.append(f"Reloaded: {', '.join(reloaded)}")

    msg = ". ".join(parts) + "."
    return {"status": "saved", "message": msg, "unloaded": unloaded, "loaded": loaded,
            "reloaded": reloaded, "errors": load_errors, "gpu": get_gpu_stats()}


@app.get("/ui", response_class=HTMLResponse)
async def settings_page():
    return _read_www("settings.html")





# ===================================================================
# CLI + Startup
# ===================================================================
BANNER = (
    # Cyberpunk palette
    # R = Reset, C = Cyan, P = Purple, B = Blue, W = Bold white, D = Dim gray, Y = Yellow/gold
    "\n"
    "\033[38;5;240m        \u250c\u2500\033[38;5;135m\u2593\u2593\033[38;5;240m\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\033[38;5;135m\u2593\u2593\033[38;5;240m\u2500\u2510\033[0m\n"
    "\033[38;5;240m        \u2502\033[38;5;135m\u2591\u2592\u2593\033[38;5;240m                                             \033[38;5;135m\u2593\u2592\u2591\033[38;5;240m\u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[38;5;51m      \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[38;5;51m      \u255a\u2550\u2550\u2588\u2588\u2551\u2550\u2550\u255d\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[1;97m         \u2588\u2588\u2551   \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[38;5;63m         \u2588\u2588\u2551   \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u255a\u2550\u2550\u2550\u2550\u2588\u2588\u2551\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[38;5;135m         \u2588\u2588\u2551   \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502  \033[38;5;135m         \u255a\u2550\u255d   \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d\033[38;5;240m          \u2502\033[0m\n"
    "\033[38;5;240m        \u2502\033[38;5;135m\u2591\u2592\u2593\033[38;5;240m                                             \033[38;5;135m\u2593\u2592\u2591\033[38;5;240m\u2502\033[0m\n"
    "\033[38;5;240m        \u251c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2524\033[0m\n"
    "\033[38;5;240m        \u2502         \033[1;97mT A R S  \033[38;5;240m//  \033[38;5;51mSERVER \033[38;5;240m:  \033[38;5;220mA M E L I A\033[38;5;240m        \u2502\033[0m\n"
    "\033[38;5;240m        \u2514\u2500\033[38;5;135m\u2593\u2593\033[38;5;240m\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\033[38;5;135m\u2593\u2593\033[38;5;240m\u2500\u2518\033[0m\n"
)

def parse_args():
    cfg = load_config()
    p = argparse.ArgumentParser(
        description="TARS-AI Companion Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", type=int, default=int(cfg["server"]["port"]))
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--services", nargs="+", choices=["stt", "tts", "llm", "vision", "imagegen", "musicgen", "embeddings"], default=None)
    p.add_argument("--no-stt", action="store_true", default=not cfg.getboolean("services", "stt"))
    p.add_argument("--no-tts", action="store_true", default=not cfg.getboolean("services", "tts"))
    p.add_argument("--no-llm", action="store_true", default=not cfg.getboolean("services", "llm"))
    p.add_argument("--no-vision", action="store_true", default=not cfg.getboolean("services", "vision"))
    p.add_argument("--no-imagegen", action="store_true", default=not cfg.getboolean("services", "imagegen"))
    p.add_argument("--no-musicgen", action="store_true", default=not cfg.getboolean("services", "musicgen"))
    p.add_argument("--no-embeddings", action="store_true", default=not cfg.getboolean("services", "embeddings"))
    p.add_argument("--whisper-model", default=cfg["stt"]["whisper_model"])
    p.add_argument("--whisper-compute", default=cfg["stt"]["compute_type"])
    p.add_argument("--voices-dir", default=cfg["tts"]["voices_dir"] or None)
    p.add_argument("--llm-model", default=cfg["llm"]["model"])
    p.add_argument("--llm-dtype", default=cfg["llm"]["dtype"], choices=["auto", "float16", "bfloat16", "float32"])
    p.add_argument("--vision-model", default=cfg["vision"]["model"])
    p.add_argument("--imagegen-model", default=cfg["imagegen"]["model"])
    p.add_argument("--musicgen-model", default=cfg["musicgen"]["model"])
    p.add_argument("--embeddings-model", default=cfg["embeddings"]["model"])
    p.add_argument("--ssl-cert", default=None, help="Path to SSL certificate for HTTPS")
    p.add_argument("--ssl-key", default=None, help="Path to SSL private key for HTTPS")
    return p.parse_args()


def resolve_services(args) -> list[str]:
    if args.services:
        return args.services
    services = ["stt", "tts", "llm", "vision", "imagegen", "musicgen", "embeddings"]
    if args.no_stt: services.remove("stt")
    if args.no_tts: services.remove("tts")
    if args.no_llm: services.remove("llm")
    if args.no_vision: services.remove("vision")
    if args.no_imagegen: services.remove("imagegen")
    if args.no_musicgen: services.remove("musicgen")
    if args.no_embeddings: services.remove("embeddings")
    return services


def _detect_llm_backend(model_path: str) -> str:
    """Auto-detect best LLM backend based on model format."""
    model_lower = model_path.lower()
    # Explicit GGUF file or repo::file.gguf syntax
    if model_lower.endswith(".gguf") or "::" in model_path:
        return "llamacpp"
    # Local file (assumed GGUF)
    if os.path.isfile(model_path):
        return "llamacpp"
    # HF repo name contains GGUF
    if "gguf" in model_lower:
        return "llamacpp"
    # BnB / quantization format indicators -> needs transformers
    if any(hint in model_lower for hint in ("bnb", "4bit", "8bit", "gptq", "awq")):
        return "transformers"
    # Default: llamacpp (fastest for most models — auto-downloads GGUF from HF repos)
    return "llamacpp"


def _load_single_service(name: str, args):
    cfg = _active_config or load_config()
    if name == "stt":
        vad = cfg.getboolean("stt", "vad_filter", fallback=True)
        dev = resolve_service_device(cfg.get("stt", "device", fallback="auto"))
        stt_engine = cfg.get("stt", "engine", fallback="auto")
        SERVICES["stt"] = STTService(model_size=args.whisper_model, compute_type=args.whisper_compute,
                                     vad_filter=vad, device=dev, engine=stt_engine)
    elif name == "tts":
        cache_size = cfg.getint("tts", "cache_size", fallback=100)
        SERVICES["tts"] = TTSService(voices_dir=args.voices_dir, cache_size=cache_size)
    elif name == "llm":
        kvs = cfg.getint("llm", "kv_cache_sessions", fallback=2)
        kvt = cfg.getint("llm", "kv_cache_ttl", fallback=300)
        dev = resolve_service_device(cfg.get("llm", "device", fallback="auto"))
        backend = cfg.get("llm", "backend", fallback="auto")
        if backend == "auto":
            backend = _detect_llm_backend(args.llm_model)
        n_ctx = cfg.getint("llm", "n_ctx", fallback=4096)
        n_gpu = cfg.getint("llm", "n_gpu_layers", fallback=-1)
        n_batch = cfg.getint("llm", "n_batch", fallback=2048)
        flash_attn = cfg.getboolean("llm", "flash_attn", fallback=True)

        if backend == "llamacpp":
            _ensure_llamacpp()
            ctk = cfg.get("llm", "cache_type_k", fallback="q8_0")
            ctv = cfg.get("llm", "cache_type_v", fallback="q8_0")
            SERVICES["llm"] = LlamaCppService(
                model_path=args.llm_model, n_ctx=n_ctx, n_gpu_layers=n_gpu,
                n_batch=n_batch, flash_attn=flash_attn,
                cache_type_k=ctk, cache_type_v=ctv,
                kv_cache_sessions=kvs, kv_cache_ttl=kvt)
        else:
            quant = cfg.get("llm", "quantize", fallback="none")
            kv_bits = cfg.getint("llm", "kv_cache_quant_bits", fallback=4)
            SERVICES["llm"] = LLMService(
                model_name=args.llm_model, dtype=cfg.get("llm", "dtype", fallback="auto"),
                quantize=quant, kv_cache_quant_bits=kv_bits,
                kv_cache_sessions=kvs, kv_cache_ttl=kvt, device=dev)
    elif name == "vision":
        vision_model = cfg.get("vision", "model", fallback=args.vision_model)
        if vision_model == "llm":
            vision_model = "Salesforce/blip-image-captioning-base"
        dev = resolve_service_device(cfg.get("vision", "device", fallback="auto"))
        SERVICES["vision"] = VisionService(model_name=vision_model, device=dev)
    elif name == "imagegen":
        dev = resolve_service_device(cfg.get("imagegen", "device", fallback="auto"))
        SERVICES["imagegen"] = ImageGenService(model_name=args.imagegen_model, device=dev)
    elif name == "musicgen":
        dev = resolve_service_device(cfg.get("musicgen", "device", fallback="auto"))
        SERVICES["musicgen"] = MusicGenService(model_name=args.musicgen_model, device=dev)
    elif name == "embeddings":
        dev = resolve_service_device(cfg.get("embeddings", "device", fallback="auto"))
        SERVICES["embeddings"] = EmbeddingsService(model_name=args.embeddings_model, device=dev)


_SERVICE_PACKAGES = {
    "stt":        ["sherpa-onnx", "huggingface_hub"],
    "tts":        ["piper-tts>=1.2.0"],
    "imagegen":   ["diffusers>=0.27.0"],
    "musicgen":    [
        "loguru", "soundfile", "librosa", "py3langid", "pypinyin",
        "cutlet", "fugashi[unidic-lite]", "hangul-romanize", "num2words",
        "spacy",
        "ace-step @ git+https://github.com/ace-step/ACE-Step.git",
    ],
    "embeddings": ["sentence-transformers>=2.2.0"],
}

def _cleanup_stale_pip_dirs():
    """Remove ~* temp directories left by pip when it can't rename locked packages on Windows."""
    if sys.platform != "win32":
        return
    import site, shutil
    for sp in site.getsitepackages():
        sp = Path(sp)
        if not sp.is_dir():
            continue
        for entry in sp.iterdir():
            if entry.name.startswith("~") and entry.is_dir():
                try:
                    shutil.rmtree(entry)
                    log.info(f"Cleaned up stale pip temp dir: {entry.name}")
                except Exception:
                    pass

def _try_install_service_deps(name: str) -> bool:
    """Auto-install missing packages for a service. Returns True if something was installed.
    On Windows, retries with --force-reinstall if the first attempt leaves stale temp dirs."""
    import subprocess as _sp
    pkgs = _SERVICE_PACKAGES.get(name)
    if not pkgs:
        return False
    log.info(f"Installing missing packages for {name.upper()}: {', '.join(pkgs)}")
    env = {**os.environ, "PYTHONUTF8": "1"}
    # Suppress pip's noisy dependency-resolver warnings (stderr)
    _pip_stderr = _sp.DEVNULL if name == "musicgen" else None
    if name == "musicgen":
        # Install lightweight deps first, then ace-step with --no-deps
        # to prevent it from downgrading transformers/torch/accelerate
        no_deps_pkgs = [p for p in pkgs if "ace-step" in p.lower() or "ACE-Step" in p]
        normal_pkgs = [p for p in pkgs if p not in no_deps_pkgs]
        rc = 0
        # Install torchvision from the same index as torch (CUDA or CPU)
        try:
            import torchvision  # noqa: F401
        except ImportError:
            tv_cmd = [sys.executable, "-m", "pip", "install", "--quiet", "torchvision"]
            try:
                import torch as _t
                if hasattr(_t.version, 'cuda') and _t.version.cuda:
                    cuda_ver = _t.version.cuda.replace(".", "")
                    tv_cmd += ["--index-url", f"https://download.pytorch.org/whl/cu{cuda_ver}"]
            except Exception:
                pass
            _sp.call(tv_cmd, env=env, stderr=_pip_stderr)
        if normal_pkgs:
            rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet"] + normal_pkgs, env=env, stderr=_pip_stderr)
        if rc == 0 and no_deps_pkgs:
            rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps"] + no_deps_pkgs, env=env, stderr=_pip_stderr)
    else:
        rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet"] + pkgs, env=env)
    if rc == 0:
        # Clean up any ~* leftovers and verify the module is actually importable
        _cleanup_stale_pip_dirs()
        # Invalidate import caches so Python sees newly installed packages
        import importlib
        importlib.invalidate_caches()
        return True
    # First attempt failed — clean up stale dirs and force reinstall
    _cleanup_stale_pip_dirs()
    log.info(f"Retrying install for {name.upper()} with --force-reinstall...")
    if name == "musicgen":
        no_deps_pkgs = [p for p in pkgs if "ace-step" in p.lower() or "ACE-Step" in p]
        normal_pkgs = [p for p in pkgs if p not in no_deps_pkgs]
        rc = 0
        if normal_pkgs:
            rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet", "--force-reinstall"] + normal_pkgs, env=env)
        if rc == 0 and no_deps_pkgs:
            rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet", "--force-reinstall", "--no-deps"] + no_deps_pkgs, env=env)
    else:
        rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet", "--force-reinstall"] + pkgs, env=env)
    _cleanup_stale_pip_dirs()
    import importlib
    importlib.invalidate_caches()
    return rc == 0

def _cleanup_failed_service(name: str):
    """Clean up GPU memory after a failed service load."""
    _SERVICE_VRAM.pop(name, None)
    if name in SERVICES:
        try:
            svc = SERVICES[name]
            if hasattr(svc, "unload"):
                svc.unload()
        except Exception:
            pass
        del SERVICES[name]
    gc.collect()
    if DEVICE == "cuda":
        torch.cuda.empty_cache()


def _get_vram_used_gb():
    """Get current VRAM usage in GB (for measuring per-service deltas)."""
    vram = _gpu_vram()
    if vram is not None:
        return vram[0]
    if DEVICE == "cuda":
        return torch.cuda.memory_allocated(0) / 1024**3
    return 0.0


def _load_service_safe(name: str, args):
    """Load a single service with error handling, OOM recovery, and auto-install retry."""
    # Check VRAM budget before attempting load
    if DEVICE == "cuda" and not _check_vram_budget(name):
        return
    # Snapshot VRAM before loading (invalidate cache for fresh reading)
    _smi_cache["ts"] = 0.0
    vram_before = _get_vram_used_gb() if DEVICE == "cuda" else 0.0
    try:
        _load_single_service(name, args)
    except (ImportError, ModuleNotFoundError):
        if _try_install_service_deps(name):
            try:
                _load_single_service(name, args)
            except (ImportError, ModuleNotFoundError) as retry_exc:
                _cleanup_stale_pip_dirs()
                missing_mod = getattr(retry_exc, 'name', None) or str(retry_exc)
                log.warning(f"{name.upper()}: missing module '{missing_mod}' after install — install it manually and restart")
                import importlib
                importlib.invalidate_caches()
                _cleanup_failed_service(name)
                return
            except Exception:
                _cleanup_failed_service(name)
                return
        else:
            log.error(f"Failed to load {name.upper()}:\n{traceback.format_exc()}")
            log.warning(f"Continuing without {name.upper()}")
            return
    except torch.cuda.OutOfMemoryError:
        _cleanup_failed_service(name)
        log.error(f"GPU out of memory loading {name.upper()} — skipping. "
                   f"Free VRAM by disabling other services or using quantization.")
        log.warning(f"Continuing without {name.upper()}")
        return
    except Exception:
        _cleanup_failed_service(name)
        log.error(f"Failed to load {name.upper()}:\n{traceback.format_exc()}")
        log.warning(f"Continuing without {name.upper()}")
        return
    # Success — measure VRAM used by this service
    if DEVICE == "cuda" and name in SERVICES:
        _smi_cache["ts"] = 0.0  # invalidate cache for fresh reading
        vram_after = _get_vram_used_gb()
        delta = round(vram_after - vram_before, 2)
        if delta > 0.01:
            _SERVICE_VRAM[name] = delta


def load_services(args):
    to_load = resolve_services(args)
    log.info(f"Services to load: {', '.join(s.upper() for s in to_load)}")

    # CPU-only services can load in parallel with GPU services
    _CPU_SERVICES = {"tts"}  # Piper uses ONNX on CPU, no GPU contention
    cpu_services = [s for s in to_load if s in _CPU_SERVICES]
    gpu_services = [s for s in to_load if s not in _CPU_SERVICES]

    # Load CPU services in background threads while GPU services load sequentially
    cpu_threads = []
    for name in cpu_services:
        t = Thread(target=_load_service_safe, args=(name, args), name=f"load-{name}")
        t.start()
        cpu_threads.append(t)

    # GPU services must load sequentially (VRAM allocation)
    for name in gpu_services:
        _load_service_safe(name, args)

    # Wait for CPU services to finish
    for t in cpu_threads:
        t.join()

    if not SERVICES:
        log.error("No services loaded!")
        sys.exit(1)


# -- Graceful shutdown -------------------------------------------------

_shutting_down = False

def _shutdown_handler(signum, frame):
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    log.info("Shutdown signal received — cleaning up...")
    _stop_tunnel()
    for name, svc in list(SERVICES.items()):
        try:
            if hasattr(svc, "unload"):
                svc.unload()
            log.info(f"Unloaded {name.upper()}")
        except Exception:
            pass
    gc.collect()
    if DEVICE == "cuda":
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    log.info("Cleanup complete. Exiting.")
    os._exit(0)


# ===================================================================
# Main
# ===================================================================
if __name__ == "__main__":
    args = parse_args()
    _LAUNCH_ARGS = args
    _LLM_SEMAPHORE = asyncio.Semaphore(1)

    # Register shutdown handlers
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    load_services(args)

    gpu = get_gpu_stats()
    api_key = _active_config.get("server", "api_key", fallback="") if _active_config else ""
    proto = "https" if args.ssl_cert else "http"

    # Resolve display address — replace 0.0.0.0 with the actual LAN IP
    import socket as _socket
    display_host = args.host
    if args.host in ("0.0.0.0", ""):
        try:
            # Connect to an external address (doesn't send data) to find the
            # outbound interface IP — works on Windows, macOS, and Linux
            with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as _s:
                _s.connect(("8.8.8.8", 80))
                display_host = _s.getsockname()[0]
        except Exception:
            display_host = "localhost"

    base_url = f"{proto}://{display_host}:{args.port}"

    try:
        print(BANNER)
    except UnicodeEncodeError:
        print("[ TARS-AI SERVER MODULE ]")
        print("=" * 37)

    log.info("=" * 50)
    log.info(f"TARS-AI Server ready on {base_url}")
    log.info(f"Services: {', '.join(s.upper() for s in SERVICES)}")
    if gpu:
        log.info(f"GPU: {gpu['name']} — {gpu['vram_allocated_gb']:.1f}/{gpu['vram_total_gb']:.1f} GB VRAM")
    if api_key:
        log.info(f"Auth: API key enabled ({api_key[:6]}...)")
    else:
        log.info(f"Auth: OPEN (no API key set — set one in Settings or config-server.ini)")
    log.info(f"Dashboard:  {base_url}/")
    log.info(f"Settings:   {base_url}/ui")
    log.info(f"Playground: {base_url}/playground")
    if api_key:
        log.info(f"API Key:    {api_key}")
    else:
        log.info(f"API Key:    none (open access)")
    log.info("=" * 50)

    uvicorn_kwargs = {
        "host": args.host, "port": args.port, "log_level": "warning",
    }
    if args.ssl_cert and args.ssl_key:
        uvicorn_kwargs["ssl_certfile"] = args.ssl_cert
        uvicorn_kwargs["ssl_keyfile"] = args.ssl_key

    uvicorn.run(app, **uvicorn_kwargs)