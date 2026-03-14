"""
TARS-AI Companion Server v2.0

Run on a powerful PC or server to offload heavy AI workloads from the Raspberry Pi.

Services:
  - STT:        Speech-to-text via faster-whisper (GPU, with Silero VAD pre-filtering)
  - TTS:        Text-to-speech via Piper ONNX (with response caching)
  - LLM:        Local language model (default: Qwen3-4B, with KV cache + token counting)
  - Vision:     Image captioning via BLIP or vision-capable LLM
  - ImageGen:   Image generation via diffusers (Automatic1111-compatible, scheduler selection)
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
        # os.execv on Windows spawns a new process but the parent continues — use subprocess + exit
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)
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
    datefmt="%H:%M:%S",
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
    "transformers", "diffusers", "huggingface_hub", "sentence_transformers",
    "filelock", "urllib3", "httpx", "torch", "ctranslate2", "safetensors",
):
    logging.getLogger(_lib).setLevel(logging.ERROR)

# Suppress Python deprecation / future warnings from ML libraries
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

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


def get_gpu_stats() -> dict:
    if DEVICE != "cuda":
        return {}
    try:
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        reserved = torch.cuda.memory_reserved(0) / 1024**3
        ded_pct = allocated / _VRAM_TOTAL_GB * 100 if _VRAM_TOTAL_GB > 0 else 0
        # Shared GPU memory (Windows WDDM: overflow from VRAM into system RAM)
        shared_used = max(0, reserved - _VRAM_TOTAL_GB)
        shared_pct = shared_used / _SHARED_TOTAL_GB * 100 if _SHARED_TOTAL_GB > 0 else 0
        return {
            "name": _GPU_NAME,
            "vram_total_gb": round(_VRAM_TOTAL_GB, 2),
            "vram_allocated_gb": round(allocated, 2),
            "vram_reserved_gb": round(reserved, 2),
            "vram_free_gb": round(max(_VRAM_TOTAL_GB - reserved, 0), 2),
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



def _ensure_llamacpp():
    """Install llama-cpp-python using pre-built wheels only — no compiler required.

    Strategy:
      1. Already installed with GPU support → do nothing.
      2. CUDA available → try matching CUDA pre-built wheel (--prefer-binary).
      3. Fall back to CPU pre-built wheel (--prefer-binary).
      4. Never attempt a source build — avoids Visual Studio / compiler requirements.

    Uses a stamp file so a failed install isn't retried on every startup.
    Delete .llamacpp_install_failed to force a retry.
    """
    import importlib
    import subprocess

    # Already installed — check for GPU support if on CUDA
    try:
        importlib.invalidate_caches()
        from llama_cpp import llama_supports_gpu_offload  # type: ignore[import]
        if DEVICE != "cuda" or llama_supports_gpu_offload():
            return  # Good to go
        # Installed but CPU-only and we have a GPU — fall through to reinstall
        log.info("llama-cpp-python installed but CPU-only — attempting GPU wheel upgrade...")
    except ImportError:
        log.info("llama-cpp-python not found — installing pre-built wheel...")

    stamp = Path(__file__).parent / ".llamacpp_install_failed"
    if stamp.exists():
        log.warning(
            "llama-cpp-python pre-built wheel install previously failed — skipping.\n"
            "  Delete .llamacpp_install_failed to retry.\n"
            "  GGUF models will not be available."
        )
        return

    def _try_wheel(label: str, index_url: str) -> bool:
        log.info(f"llama-cpp-python: trying {label} pre-built wheel...")
        rc = subprocess.call([
            sys.executable, "-m", "pip", "install", "llama-cpp-python",
            "--extra-index-url", index_url,
            "--prefer-binary",          # never compile from source
            "--force-reinstall",
            "--no-cache-dir",
            "--quiet",
        ])
        if rc != 0:
            return False
        # Verify the install actually worked
        try:
            importlib.invalidate_caches()
            import llama_cpp  # noqa: F401
            return True
        except ImportError:
            return False

    # Detect CUDA version from torch so we pick the right wheel index
    cuda_ver = None
    if DEVICE == "cuda":
        try:
            raw = torch.version.cuda  # e.g. "12.4"
            cuda_ver = "cu" + raw.replace(".", "")[:3]  # → "cu124"
        except Exception:
            pass

    installed = False

    if cuda_ver:
        gpu_index = f"https://abetlen.github.io/llama-cpp-python/whl/{cuda_ver}"
        installed = _try_wheel(f"CUDA {torch.version.cuda}", gpu_index)
        if not installed:
            # Try adjacent CUDA versions (wheels aren't published for every minor)
            for fallback in ("cu125", "cu123", "cu122"):
                if fallback != cuda_ver:
                    fb_index = f"https://abetlen.github.io/llama-cpp-python/whl/{fallback}"
                    installed = _try_wheel(f"CUDA fallback ({fallback})", fb_index)
                    if installed:
                        break

    if not installed:
        installed = _try_wheel("CPU", "https://abetlen.github.io/llama-cpp-python/whl/cpu")

    if installed:
        log.info("llama-cpp-python installed successfully. Restarting...")
        _restart_self()
    else:
        stamp.write_text("Pre-built wheel install failed — delete this file to retry.\n")
        log.warning(
            "llama-cpp-python could not be installed from pre-built wheels.\n"
            "  GGUF models will not be available.\n"
            "  Delete .llamacpp_install_failed to retry on next startup.\n"
            "  Manual install: pip install llama-cpp-python --prefer-binary "
            "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu"
        )

# _ensure_llamacpp() is called on-demand when LLM backend is "llamacpp"


def resolve_service_device(cfg_value: str) -> str:
    """Resolve per-service device. 'auto' uses the globally detected device."""
    if cfg_value in ("auto", ""):
        return DEVICE
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
                   "imagegen": "false", "embeddings": "false"},
    "stt":        {"whisper_model": "large-v3", "compute_type": "auto", "vad_filter": "true", "device": "auto"},
    "llm":        {"model": "Qwen/Qwen3-4B",
                   "dtype": "auto", "quantize": "none", "backend": "auto",
                   "n_ctx": "4096", "n_gpu_layers": "-1",
                   "n_batch": "2048", "flash_attn": "true",
                   "kv_cache_sessions": "2", "kv_cache_ttl": "300", "device": "auto"},
    "tts":        {"voices_dir": "", "default_voice": "", "cache_size": "100"},
    "vision":     {"model": "Salesforce/blip-image-captioning-base", "device": "auto"},
    "imagegen":   {"model": "stabilityai/stable-diffusion-xl-base-1.0", "default_steps": "20", "default_cfg": "7.0", "device": "auto"},
    "embeddings": {"model": "all-MiniLM-L6-v2", "device": "auto"},
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

    def record(self, endpoint: str, method: str, status: int, latency_ms: float, service: str = None):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "method": method,
            "endpoint": endpoint,
            "status": status,
            "latency_ms": round(latency_ms, 1),
        }
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

    def get_recent(self, n: int = 50) -> list:
        with self._lock:
            return list(self.history)[-n:]


TRACKER = RequestTracker()

# Map endpoint prefixes to service names for latency tracking
_ENDPOINT_SERVICE = {
    "/save_audio": "stt", "/transcribe": "stt", "/ws/stt": "stt",
    "/v1/chat/completions": "llm",
    "/tts/": "tts",
    "/caption": "vision",
    "/sdapi/": "imagegen", "/generate_image": "imagegen",
    "/v1/embeddings": "embeddings",
}


def _endpoint_to_service(path: str) -> Optional[str]:
    for prefix, svc in _ENDPOINT_SERVICE.items():
        if path.startswith(prefix):
            return svc
    return None


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------
SERVICES: dict = {}
START_TIME = time.time()
_LAUNCH_ARGS = None
_LLM_SEMAPHORE: asyncio.Semaphore = None  # initialized at startup

# ===================================================================
# STT Service (faster-whisper + Silero VAD)
# ===================================================================
class STTService:
    def __init__(self, model_size: str = "large-v3", compute_type: str = "auto",
                 vad_filter: bool = True, device: str = None):
        from faster_whisper import WhisperModel

        device = device or DEVICE
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        log.info(f"Loading Whisper model: {model_size} (compute: {compute_type}, device: {device})...")
        self.model_name = model_size
        whisper_dir = MODELS_DIR / "whisper"
        whisper_dir.mkdir(exist_ok=True)
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(whisper_dir),
        )
        log.info("Whisper model loaded.")

        # Silero VAD for pre-filtering
        self._vad_model = None
        self._vad_utils = None
        if vad_filter:
            self._load_vad()

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

    def has_speech(self, audio_bytes: BytesIO) -> bool:
        """Check if audio contains speech using Silero VAD."""
        if not self._vad_model:
            return True
        try:
            get_speech_ts = self._vad_utils[0]
            audio_bytes.seek(0)
            wav_tensor = self._wav_bytes_to_tensor(audio_bytes)
            if wav_tensor is None:
                return True
            # Low threshold — this is a pre-filter to skip silence, not a gate.
            # False negatives (missing speech) are far worse than false positives.
            timestamps = get_speech_ts(wav_tensor, self._vad_model,
                                       sampling_rate=16000, threshold=0.3,
                                       min_speech_duration_ms=100)
            return len(timestamps) > 0
        except Exception:
            return True  # On error, proceed with transcription

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
            # Decode based on sample width (handles 8/16/24/32-bit WAV)
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
                # 32-bit float (Audacity, modern DAWs) or 32-bit int
                samples = struct.unpack(f"<{n_samples}f", raw)
                tensor = torch.FloatTensor(samples)
                if tensor.isnan().any() or tensor.isinf().any() or tensor.abs().max() > 2.0:
                    samples = struct.unpack(f"<{n_samples}i", raw)
                    tensor = torch.FloatTensor(samples) / 2147483648.0
            else:
                return None
            if n_channels > 1:
                tensor = tensor[::n_channels]  # take first channel
            # Resample to 16kHz if needed
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

    def transcribe(self, audio_bytes: BytesIO, language: str = None) -> tuple[list[dict], object]:
        kwargs = {"beam_size": 1}  # greedy decoding — ~3x faster, negligible quality loss for speech
        if language:
            kwargs["language"] = language
        segments, info = self.model.transcribe(audio_bytes, **kwargs)
        results = [
            {"text": s.text.strip(), "start": round(s.start, 3), "end": round(s.end, 3)}
            for s in segments
        ]
        return results, info

    def unload(self):
        del self.model
        self.model = None
        self._vad_model = None


# ===================================================================
# TTS Service (Piper ONNX + cache)
# ===================================================================
class TTSService:
    _DEFAULT_VOICE_URLS = {
        "TARS.onnx": "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx",
        "TARS.onnx.json": "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx.json",
    }

    def __init__(self, voices_dir: str = None, cache_size: int = 100):
        self.voices_dir = Path(voices_dir) if voices_dir else Path(__file__).parent / "tts"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._voices: dict = {}
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._cache_max = cache_size
        self._ensure_default_voice()
        self._scan_voices()

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
        for onnx_file in self.voices_dir.rglob("*.onnx"):
            json_file = onnx_file.with_suffix(".onnx.json")
            if json_file.exists():
                name = onnx_file.stem
                self._voices[name] = {"model": str(onnx_file), "config": str(json_file)}
        log.info(f"Found {len(self._voices)} Piper voice(s): {list(self._voices.keys())}")

    def list_voices(self) -> list[str]:
        return list(self._voices.keys())

    def synthesize(self, text: str, voice: str = None, speed: float = 1.0) -> bytes:
        cache_key = hashlib.md5(f"{text}|{voice}|{speed}".encode()).hexdigest()
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        wav_bytes = self._do_synthesize(text, voice, speed)

        self._cache[cache_key] = wav_bytes
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

        return wav_bytes

    def _do_synthesize(self, text: str, voice: str, speed: float) -> bytes:
        import wave as wave_mod

        try:
            from piper.voice import PiperVoice
        except ImportError:
            raise RuntimeError("piper-tts not installed. Install with: pip install piper-tts")

        if not voice and self._voices:
            voice = list(self._voices.keys())[0]
        if voice not in self._voices:
            available = ", ".join(self._voices.keys()) if self._voices else "none"
            raise ValueError(f"Voice '{voice}' not found. Available: {available}")

        voice_info = self._voices[voice]
        piper_voice = PiperVoice.load(voice_info["model"])
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

    def unload(self):
        self._cache.clear()


# ===================================================================
# LLM Service (transformers + token counting + KV cache)
# ===================================================================
class LLMService:
    def __init__(self, model_name: str = "Qwen/Qwen3-4B", dtype: str = "auto",
                 quantize: str = "none",
                 kv_cache_sessions: int = 2, kv_cache_ttl: int = 300, device: str = None):
        from transformers import AutoModelForCausalLM, AutoTokenizer

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

        log.info(f"Loading LLM: {model_name} (dtype: {dtype}, device: {device}, quantize: {quantize})...")
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

        # Only use device_map="auto" for quantized models (BnB requires it).
        # For non-quantized, use explicit .to(device) — avoids accelerate dispatch overhead.
        _use_device_map = False
        load_kwargs = dict(
            trust_remote_code=True, cache_dir=str(llm_dir),
        )

        # Quantization (requires: pip install bitsandbytes)
        if quantize in ("4bit", "8bit") and device == "cuda":
            try:
                from transformers import BitsAndBytesConfig
                if quantize == "4bit":
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
                log.info(f"LLM quantization: {quantize}")
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

        # torch.compile + static KV cache for CUDA graphs (2-3x speedup on non-quantized)
        # Skipped on Windows: inductor backend requires Triton which is Linux-only
        self._compiled = False
        if device == "cuda" and quantize in ("none", "") and sys.platform != "win32":
            try:
                _orig_model = self.model
                self.model.generation_config.cache_implementation = "static"
                self.model = torch.compile(self.model, mode="reduce-overhead", fullgraph=True)
                # Test with actual inference to catch Triton/inductor errors early
                _warm = self.tokenizer("compile test", return_tensors="pt").input_ids.to(device)
                with torch.inference_mode():
                    self.model.generate(_warm, attention_mask=torch.ones_like(_warm),
                                        max_new_tokens=2, do_sample=False, use_cache=True)
                self._compiled = True
                log.info("LLM torch.compile enabled (reduce-overhead + static cache)")
            except Exception as e:
                log.info(f"torch.compile skipped: {e}")
                self.model = _orig_model
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

        # KV cache for prompt reuse
        self._kv_cache: dict = {}  # session_id -> (token_count, past_kv, timestamp)
        self._kv_max_sessions = kv_cache_sessions
        self._kv_ttl = kv_cache_ttl

        # Vision detection
        self.supports_vision = self._check_vision_support()
        if self.supports_vision:
            log.info("LLM has vision capability")
        log.info(f"LLM loaded: {model_name}")

    def _check_vision_support(self) -> bool:
        model_lower = self.model_name.lower()
        vision_indicators = ["vl", "vision", "llava", "cogvlm", "internvl", "minicpm-v"]
        if any(ind in model_lower for ind in vision_indicators):
            return True
        config = getattr(self.model, "config", None)
        if config and hasattr(config, "vision_config"):
            return True
        return False

    def caption_image(self, image_bytes: bytes, prompt: str = "Describe this image.") -> str:
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

        do_sample = temperature > 0
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
            outputs = self.model.generate(**gen_kwargs)

        # Save KV cache for this session
        if session_id and hasattr(outputs, "past_key_values") and outputs.past_key_values:
            self._save_kv(session_id, full_ids.shape[-1], outputs.past_key_values)

        prompt_tokens = full_ids.shape[-1]
        gen_sequence = outputs.sequences[0]
        new_tokens = gen_sequence[prompt_tokens:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return self._format_response(text, prompt_tokens, len(new_tokens))

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

        thread = Thread(target=self.model.generate, kwargs=gen_kwargs)
        thread.start()

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())
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
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return generate()

    def _try_reuse_kv(self, full_ids: torch.Tensor, session_id: str):
        """Try to reuse cached KV. Returns (input_ids_to_process, past_kv_or_None)."""
        if not session_id or session_id not in self._kv_cache:
            return full_ids, None

        cached_len, cached_kv, ts = self._kv_cache[session_id]
        if time.time() - ts > self._kv_ttl:
            del self._kv_cache[session_id]
            return full_ids, None

        # New input must be longer and start with the cached prefix
        if full_ids.shape[-1] > cached_len:
            return full_ids[:, cached_len:], cached_kv

        # Input changed (shorter or different), start fresh
        del self._kv_cache[session_id]
        return full_ids, None

    def _save_kv(self, session_id: str, prompt_len: int, past_kv):
        self._kv_cache[session_id] = (prompt_len, past_kv, time.time())
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

    def __init__(self, model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1,
                 n_batch: int = 2048, flash_attn: bool = True,
                 kv_cache_sessions: int = 2, kv_cache_ttl: int = 300):  # noqa: ARG002
        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python not installed. Run: pip install llama-cpp-python"
            )

        self.supports_vision = False

        # Determine load method:
        #   Local file:          C:\path\to\model.gguf  or  /path/to/model.gguf
        #   HF repo (auto GGUF): owner/repo-name
        #   HF repo + filename:  owner/repo-name::file.gguf
        if os.path.isfile(model_path):
            self.model_name = os.path.basename(model_path)
            log.info(f"Loading llama.cpp model: {self.model_name} (n_gpu_layers={n_gpu_layers}, n_ctx={n_ctx})...")
            self._llm = Llama(model_path=model_path, n_gpu_layers=n_gpu_layers,
                              n_ctx=n_ctx, n_batch=n_batch, flash_attn=flash_attn,
                              verbose=False)
        elif "::" in model_path:
            repo_id, filename = model_path.split("::", 1)
            self.model_name = filename
            log.info(f"Downloading GGUF from HuggingFace: {repo_id} / {filename} ...")
            self._llm = Llama.from_pretrained(repo_id=repo_id, filename=filename,
                                              n_gpu_layers=n_gpu_layers, n_ctx=n_ctx,
                                              n_batch=n_batch, flash_attn=flash_attn,
                                              verbose=False)
        elif "/" in model_path and not model_path.startswith(("C:", "D:", "/")):
            # HuggingFace repo ID — auto-pick best available GGUF (prefer Q4_K_M)
            self.model_name = model_path.split("/")[-1]
            log.info(f"Downloading GGUF from HuggingFace: {model_path} (searching for Q4_K_M.gguf) ...")
            for pattern in ("*Q4_K_M.gguf", "*Q4_K_S.gguf", "*Q5_K_M.gguf", "*.gguf"):
                try:
                    self._llm = Llama.from_pretrained(repo_id=model_path, filename=pattern,
                                                      n_gpu_layers=n_gpu_layers, n_ctx=n_ctx,
                                                      n_batch=n_batch, flash_attn=flash_attn,
                                                      verbose=False)
                    break
                except Exception:
                    continue
            else:
                raise FileNotFoundError(f"No GGUF file found in HuggingFace repo: {model_path}")
        else:
            raise FileNotFoundError(
                f"GGUF model not found: {model_path}\n"
                "  Local file: use full path ending in .gguf\n"
                "  HuggingFace: use  owner/repo  or  owner/repo::filename.gguf"
            )

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
            if not completion_tokens:
                try:
                    completion_tokens = len(self._llm.tokenize("".join(output_text).encode()))
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
            self.model_name, cache_dir=str(self._cache_dir), torch_dtype=self._dtype)
        self.model.to(self._device).eval()

    def _load_blip2(self):
        from transformers import Blip2Processor, Blip2ForConditionalGeneration
        self.processor = Blip2Processor.from_pretrained(self.model_name, cache_dir=str(self._cache_dir))
        self.model = Blip2ForConditionalGeneration.from_pretrained(
            self.model_name, cache_dir=str(self._cache_dir), torch_dtype=self._dtype)
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
        for attr in ("model", "processor", "tokenizer"):
            if hasattr(self, attr):
                delattr(self, attr)
        self.model = self.processor = None


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
    def __init__(self, model_name: str = "stabilityai/stable-diffusion-xl-base-1.0", device: str = None):
        device = device or DEVICE
        self._device = device
        log.info(f"Loading image generation model: {model_name} (device: {device})...")
        self.model_name = model_name
        cache_dir = MODELS_DIR / "imagegen"
        cache_dir.mkdir(exist_ok=True)
        from diffusers import AutoPipelineForText2Image
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.pipe = AutoPipelineForText2Image.from_pretrained(
            model_name, torch_dtype=dtype, cache_dir=str(cache_dir),
        )
        if device == "cuda":
            self.pipe.to("cuda")
        self._default_scheduler_config = self.pipe.scheduler.config
        log.info(f"Image generation model loaded: {model_name}")

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
                 width=1024, height=1024, seed=-1, sampler_name=None) -> bytes:
        self._set_scheduler(sampler_name)
        generator = torch.Generator(device=self._device).manual_seed(seed) if seed >= 0 else None
        gen_kwargs = {
            "prompt": prompt, "num_inference_steps": steps,
            "guidance_scale": cfg_scale, "width": width, "height": height,
            "generator": generator,
        }
        if negative_prompt:
            gen_kwargs["negative_prompt"] = negative_prompt
        result = self.pipe(**gen_kwargs)
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
        self.model = SentenceTransformer(model_name, cache_folder=str(cache_dir), device=device)
        log.info(f"Embeddings model loaded: {model_name}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def unload(self):
        del self.model
        self.model = None


# ===================================================================
# FastAPI app
# ===================================================================
app = FastAPI(
    title="TARS-AI Companion Server", version="2.0",
    description="Offload STT, TTS, LLM, Vision, ImageGen, and Embeddings from your Raspberry Pi.",
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": False},
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[],
)

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


# -- Auth middleware ---------------------------------------------------

# Pages that need a browser session cookie (web UI)
_WEB_PAGES = {"/", "/ui", "/playground"}
# API paths callable from the web UI — accept session cookie OR Bearer token
_WEB_API_PATHS = {
    "/api/tunnel", "/api/settings",
    "/v1",           # LLM chat completions + embeddings
    "/tts",          # TTS generate + voices
    "/save_audio", "/transcribe",  # STT
    "/caption", "/generate_image", "/sdapi",  # Vision + ImageGen
}
# Paths exempt from ALL auth (health check, login, static API schema)
_AUTH_EXEMPT = {"/health", "/login", "/logout", "/docs", "/openapi.json", "/redoc", "/ws/dashboard"}


def _session_token(api_key: str) -> str:
    import hmac as _hmac, hashlib as _hashlib
    return _hmac.new(api_key.encode(), b"tars-web-session", _hashlib.sha256).hexdigest()


def _is_web_authed(request: Request, api_key: str) -> bool:
    expected = _session_token(api_key)
    return request.cookies.get("tars_session") == expected


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = _active_config.get("server", "api_key", fallback="") if _active_config else ""
        if not api_key:
            return await call_next(request)

        path = request.url.path

        # Always allowed
        if any(path == ex or path.startswith(ex + "/") for ex in _AUTH_EXEMPT):
            return await call_next(request)

        # Web UI pages — require session cookie, redirect to /login if missing
        if any(path == p or path.startswith(p + "/") for p in _WEB_PAGES):
            if not _is_web_authed(request, api_key):
                return RedirectResponse(url=f"/login?next={path}", status_code=302)
            return await call_next(request)

        # Web-facing API paths — accept session cookie OR Bearer token
        if any(path == p or path.startswith(p + "/") for p in _WEB_API_PATHS):
            if _is_web_authed(request, api_key) or request.headers.get("authorization", "") == f"Bearer {api_key}":
                return await call_next(request)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        # API endpoints — require Bearer token
        if request.headers.get("authorization", "") != f"Bearer {api_key}":
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


_LOGIN_HTML = r"""<!DOCTYPE html>
<html><head><title>TARS-AI Login</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;background:#0a1220;display:flex;align-items:center;justify-content:center;font-family:'Share Tech Mono',monospace}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,0.003) 3px,rgba(0,229,255,0.003) 6px);pointer-events:none}
.card{position:relative;z-index:1;background:rgba(14,26,48,0.85);border:1px solid rgba(0,229,255,0.25);border-radius:14px;padding:40px 48px;width:100%;max-width:380px;box-shadow:0 16px 64px rgba(0,0,0,0.5)}
h1{font-family:'Orbitron',sans-serif;font-size:22px;font-weight:900;letter-spacing:.2em;background:linear-gradient(135deg,#00e5ff,#b44dff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-align:center;margin-bottom:8px}
.sub{text-align:center;font-size:11px;color:rgba(0,229,255,0.4);letter-spacing:.15em;text-transform:uppercase;margin-bottom:32px}
label{display:block;font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:#5a7a94;margin-bottom:6px}
input{width:100%;padding:12px 16px;background:rgba(0,229,255,0.04);border:1px solid rgba(0,229,255,0.18);border-radius:8px;color:#e2eaf2;font-family:'Share Tech Mono',monospace;font-size:14px;outline:none;transition:border-color .2s;margin-bottom:20px}
input:focus{border-color:rgba(0,229,255,0.5);box-shadow:0 0 12px rgba(0,229,255,0.08)}
button{width:100%;padding:13px;background:rgba(0,229,255,0.08);border:1px solid rgba(0,229,255,0.35);border-radius:8px;color:#00e5ff;font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;cursor:pointer;transition:all .2s}
button:hover{background:rgba(0,229,255,0.15);box-shadow:0 0 20px rgba(0,229,255,0.15)}
.err{color:#ff4444;font-size:12px;text-align:center;margin-top:16px;min-height:18px}
</style></head><body>
<div class="card">
  <h1>TARS-AI</h1>
  <div class="sub">Server Access</div>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{{NEXT}}">
    <label>API Key</label>
    <input type="password" name="password" placeholder="Enter your API key" autofocus autocomplete="current-password">
    <button type="submit">Authenticate</button>
  </form>
  <div class="err">{{ERROR}}</div>
</div>
</body></html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_get(next: str = "/"):
    return _LOGIN_HTML.replace("{{NEXT}}", next).replace("{{ERROR}}", "")


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, next: str = "/"):
    form = await request.form()
    password = form.get("password", "")
    next_url = form.get("next", next) or "/"
    api_key = _active_config.get("server", "api_key", fallback="") if _active_config else ""
    if password == api_key:
        token = _session_token(api_key)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie("tars_session", token, httponly=True, samesite="lax", max_age=86400 * 30)
        return response
    html = _LOGIN_HTML.replace("{{NEXT}}", next_url).replace("{{ERROR}}", "Invalid API key.")
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
        response = await call_next(request)
        latency_ms = (time.time() - start) * 1000
        path = request.url.path
        service = _endpoint_to_service(path)
        TRACKER.record(path, request.method, response.status_code, latency_ms, service)
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
        if name == "llm" and hasattr(svc, "supports_vision"):
            info["supports_vision"] = svc.supports_vision
        svc_info[name] = info
    return {
        "status": "ok", "uptime_seconds": uptime, "device": DEVICE,
        "gpu": gpu, "services": svc_info,
        "latency": TRACKER.get_latency_stats(),
    }


# -- Dashboard ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard page — connects to /ws/dashboard for live updates."""
    gpu = get_gpu_stats()
    gpu_name = gpu.get("name", "None (CPU)")
    return _DASHBOARD_HTML.replace("{{GPU_NAME}}", gpu_name)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>TARS-AI Server</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a1220;--bg2:#0e1830;--panel:rgba(14,26,48,0.55);--panel-solid:rgba(14,26,48,0.78);--border:rgba(0,229,255,0.18);--border-hi:rgba(0,229,255,0.45);--cyan:#00e5ff;--cyan-dim:rgba(0,229,255,0.5);--green:#39ff14;--orange:#ffb700;--red:#ff4444;--purple:#b44dff;--magenta:#ff2d8a;--text:#e2eaf2;--text-dim:#5a7a94;--font-mono:'Share Tech Mono',monospace;--font-hud:'Orbitron',sans-serif;--font-body:'Rajdhani',sans-serif;--radius:14px;--radius-sm:8px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;min-height:100vh;background:var(--bg);color:var(--text);font-family:var(--font-mono);-webkit-font-smoothing:antialiased}
body{padding:0;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,0,0,0.35) 100%);pointer-events:none;z-index:0}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,0.003) 3px,rgba(0,229,255,0.003) 6px);pointer-events:none;z-index:9999}
.nebula-layer{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.nebula-blob{position:absolute;border-radius:50%;filter:blur(90px);will-change:transform,opacity}
.nb-1{width:500px;height:500px;background:radial-gradient(circle,rgba(120,40,200,0.35) 0%,rgba(80,20,160,0.1) 50%,transparent 70%);top:5%;left:-5%;animation:nd1 55s ease-in-out infinite}
.nb-2{width:450px;height:450px;background:radial-gradient(circle,rgba(0,180,240,0.25) 0%,rgba(0,120,200,0.08) 50%,transparent 70%);top:50%;right:-10%;animation:nd2 65s ease-in-out infinite}
.nb-3{width:400px;height:400px;background:radial-gradient(circle,rgba(160,30,220,0.30) 0%,rgba(100,20,180,0.08) 50%,transparent 70%);bottom:0;left:25%;animation:nd3 60s ease-in-out infinite}
@keyframes nd1{0%{transform:translate(0,0) scale(1);opacity:.6}25%{transform:translate(10vw,12vh) scale(1.2);opacity:.8}50%{transform:translate(18vw,5vh) scale(.95);opacity:.5}75%{transform:translate(5vw,-8vh) scale(1.1);opacity:.7}100%{transform:translate(0,0) scale(1);opacity:.6}}
@keyframes nd2{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-12vw,-6vh) scale(1.15);opacity:.7}50%{transform:translate(-8vw,10vh) scale(.9);opacity:.6}75%{transform:translate(5vw,8vh) scale(1.1);opacity:.4}100%{transform:translate(0,0) scale(1);opacity:.5}}
@keyframes nd3{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-8vw,-10vh) scale(1.1);opacity:.7}50%{transform:translate(10vw,-5vh) scale(1.2);opacity:.6}75%{transform:translate(15vw,8vh) scale(.95);opacity:.8}100%{transform:translate(0,0) scale(1);opacity:.5}}
.wrap{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:28px 32px 40px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media(max-width:960px){.grid-2{grid-template-columns:1fr}.wrap{padding:20px 16px 32px}}
.top-bar{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;background:var(--panel-solid);backdrop-filter:blur(28px) saturate(1.4);border:1px solid rgba(0,229,255,0.25);border-radius:var(--radius);margin-bottom:20px;box-shadow:0 12px 48px rgba(0,0,0,0.3),0 4px 12px rgba(0,0,0,0.15)}
.top-bar h1{font-family:var(--font-hud);font-size:20px;font-weight:900;letter-spacing:.2em;background:linear-gradient(135deg,var(--cyan),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.top-bar .meta{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:14px}
.live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 1.4s ease-in-out infinite;flex-shrink:0}
.live-dot.off{background:var(--red);box-shadow:0 0 8px var(--red);animation:none}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.65)}}
.glass{position:relative;background:var(--panel);backdrop-filter:blur(22px) saturate(1.3);border:1px solid rgba(0,229,255,0.2);border-radius:var(--radius);box-shadow:0 8px 32px rgba(0,0,0,0.25),inset 0 1px 0 rgba(255,255,255,0.1);padding:18px 20px;margin-bottom:16px}
.glass::before{content:'';position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,0.09) 0%,rgba(255,255,255,0.03) 40%,transparent 60%,rgba(0,229,255,0.04) 100%);pointer-events:none;z-index:0}
.glass>*{position:relative;z-index:1}
h2{font-family:var(--font-hud);font-size:11px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--cyan);margin-bottom:12px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 14px;font-size:13px}
th{font-family:var(--font-hud);font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim);border-bottom:1px solid var(--border)}
td{border-bottom:1px solid rgba(0,229,255,0.06);color:var(--text)}
.svc-name{font-family:var(--font-hud);font-weight:700;font-size:12px;letter-spacing:.1em}
.status-ready{color:var(--green);font-size:12px}
.status-ready::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);margin-right:6px;vertical-align:middle}
.bar-bg{background:rgba(0,229,255,0.06);border:1px solid var(--border);border-radius:6px;height:26px;position:relative;overflow:hidden}
.bar-fg{height:100%;border-radius:5px;transition:width .5s cubic-bezier(.4,0,.2,1);position:relative}
.bar-fg::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);animation:shimmer 2s ease-in-out infinite}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.bar-label{position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;font-family:var(--font-hud);font-size:10px;letter-spacing:.1em;color:#fff;text-shadow:0 1px 4px rgba(0,0,0,0.5)}
.log-area{max-height:320px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(0,229,255,0.2) transparent}
.log-entry{font-size:12px;color:var(--text-dim);padding:5px 0;border-bottom:1px solid rgba(0,229,255,0.04);display:flex;gap:10px}
.log-entry .le-time{color:rgba(0,229,255,0.4);min-width:60px}
.log-entry .le-method{color:var(--purple);min-width:36px;font-weight:700}
.log-entry .le-path{color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.log-entry .le-status{min-width:30px;text-align:right}
.log-entry .le-status.s2{color:var(--green)}.log-entry .le-status.s4,.log-entry .le-status.s5{color:var(--red)}
.log-entry .le-ms{color:var(--text-dim);min-width:60px;text-align:right}
.hud-btn-sm{display:inline-flex;align-items:center;padding:6px 14px;border-radius:var(--radius-sm);font-family:var(--font-hud);font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;cursor:pointer;transition:all .25s;border:1px solid rgba(0,229,255,0.3);background:rgba(0,229,255,0.06);color:var(--cyan);text-shadow:0 0 6px rgba(0,229,255,0.2);backdrop-filter:blur(8px)}
.hud-btn-sm:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi);box-shadow:0 0 16px rgba(0,229,255,0.15)}
.hud-btn-sm.danger{border-color:rgba(255,68,68,0.3);color:var(--red);background:rgba(255,68,68,0.06)}
.hud-btn-sm.danger:hover{background:rgba(255,68,68,0.12);border-color:rgba(255,68,68,0.5)}
.nav-links{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}
.nav-links a{font-family:var(--font-hud);font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.2);border-radius:var(--radius-sm);color:var(--cyan);text-decoration:none;transition:all .25s}
.nav-links a:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi);box-shadow:0 0 16px rgba(0,229,255,0.15);text-shadow:0 0 8px rgba(0,229,255,0.4)}
</style></head><body>
<div class="nebula-layer" aria-hidden="true"><div class="nebula-blob nb-1"></div><div class="nebula-blob nb-2"></div><div class="nebula-blob nb-3"></div></div>
<div class="wrap">
<div class="top-bar">
  <h1>TARS SERVER</h1>
  <div class="meta"><span class="live-dot" id="connDot"></span><span>{{GPU_NAME}}</span><span id="uptime">--</span></div>
</div>
<div id="stats-section" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px"></div>
<div class="grid-2">
  <div class="glass">
    <h2>Active Services</h2>
    <table><thead><tr><th>Service</th><th>Status</th><th>Model</th><th>Avg Latency</th></tr></thead>
    <tbody id="svc-table"><tr><td colspan="4" style="color:var(--text-dim)">Connecting...</td></tr></tbody></table>
  </div>
  <div class="glass">
    <h2>Remote Access</h2>
    <div id="tunnel-panel">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span id="tunnel-status" style="font-size:13px;color:var(--text-dim)">Checking...</span>
        <button class="hud-btn-sm" id="tunnel-btn" onclick="toggleTunnel()">Open Tunnel</button>
      </div>
      <div id="tunnel-url" style="display:none;margin-top:14px">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <a id="tunnel-link" href="#" target="_blank" style="font-family:var(--font-mono);font-size:13px;color:var(--cyan);word-break:break-all"></a>
          <button class="hud-btn-sm" onclick="copyTunnelUrl()">Copy</button>
        </div>
        <div style="margin-top:12px;text-align:center"><img id="tunnel-qr" style="max-width:200px;border-radius:var(--radius-sm);border:1px solid var(--border);display:none"></div>
      </div>
    </div>
  </div>
</div>
<div class="glass">
  <h2>Request Log</h2>
  <div class="log-area" id="log-area"></div>
</div>
<div class="nav-links">
  <a href="/playground">Playground</a>
  <a href="/docs">API Docs</a>
  <a href="/ui">Settings</a>
  <a href="/logout" style="border-color:rgba(255,68,68,0.3);color:#ff6666">Logout</a>
</div>
</div>
<script>
function fmtUptime(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60),ss=s%60;return h+'h '+m+'m '+ss+'s'}
function connect(){
  const dot=document.getElementById('connDot');
  const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/dashboard');
  ws.onopen=function(){dot.className='live-dot'};
  ws.onmessage=function(e){
    const d=JSON.parse(e.data);
    document.getElementById('uptime').textContent=fmtUptime(d.uptime);
    const ss=document.getElementById('stats-section');let bars='';
    function mkBar(title,pct,label,extra){const c=pct<70?'var(--cyan)':pct<90?'var(--orange)':'var(--red)';const g='linear-gradient(90deg,'+c+',rgba(180,77,255,0.5))';return '<div class="glass" style="margin:0;'+(extra||'')+'"><h2>'+title+'</h2><div class="bar-bg"><div class="bar-fg" style="background:'+g+';width:'+Math.min(pct,100)+'%"></div><span class="bar-label">'+label+'</span></div></div>';}
    if(d.system&&d.system.cpu_percent!==undefined){bars+=mkBar('CPU',d.system.cpu_percent,d.system.cpu_percent+'%');}
    if(d.system&&d.system.ram_percent!==undefined){bars+=mkBar('RAM',d.system.ram_percent,d.system.ram_used_gb.toFixed(1)+' / '+d.system.ram_total_gb.toFixed(1)+' GB ('+d.system.ram_percent+'%)');}
    if(d.gpu&&d.gpu.vram_percent!==undefined){bars+=mkBar('Dedicated GPU',d.gpu.vram_percent,d.gpu.vram_allocated_gb.toFixed(1)+' / '+d.gpu.vram_total_gb.toFixed(1)+' GB ('+d.gpu.vram_percent+'%)');}
    if(d.gpu&&d.gpu.shared_percent!==undefined){bars+=mkBar('Shared GPU',d.gpu.shared_percent,d.gpu.shared_used_gb.toFixed(1)+' / '+d.gpu.shared_total_gb.toFixed(1)+' GB ('+d.gpu.shared_percent+'%)');}
    ss.innerHTML=bars;
    const tb=document.getElementById('svc-table');let rows='';
    for(const[n,s]of Object.entries(d.services)){
      const lat=d.latency[n]?d.latency[n].avg_latency_ms.toFixed(0)+'ms <span style="color:var(--text-dim)">('+d.latency[n].requests+')</span>':'<span style="color:var(--text-dim)">-</span>';
      const det=s.model||(n==='tts'?'Piper':'ready');
      rows+='<tr><td class="svc-name">'+n.toUpperCase()+'</td><td class="status-ready">Online</td><td style="color:var(--text-dim)">'+det+'</td><td>'+lat+'</td></tr>';
    }
    tb.innerHTML=rows||'<tr><td colspan="4" style="color:var(--text-dim)">No services loaded</td></tr>';
    const la=document.getElementById('log-area');
    if(d.recent_logs&&d.recent_logs.length){
      la.innerHTML=d.recent_logs.map(l=>{
        const sc=l.status<400?'s2':l.status<500?'s4':'s5';
        return '<div class="log-entry"><span class="le-time">'+l.time+'</span><span class="le-method">'+l.method+'</span><span class="le-path">'+l.endpoint+'</span><span class="le-status '+sc+'">'+l.status+'</span><span class="le-ms">'+l.latency_ms+'ms</span></div>';
      }).join('');
      la.scrollTop=la.scrollHeight;
    }
  };
  ws.onclose=function(){dot.className='live-dot off';setTimeout(connect,3000)};
  ws.onerror=function(){ws.close()};
}
connect();

// Tunnel controls
let tunnelActive=false;
function checkTunnel(){
  fetch('/api/tunnel/status').then(r=>r.json()).then(d=>{
    const st=document.getElementById('tunnel-status');
    const btn=document.getElementById('tunnel-btn');
    const urlDiv=document.getElementById('tunnel-url');
    if(d.state==='active'){
      tunnelActive=true;
      st.innerHTML='<span style="color:var(--green)">Active</span>';
      btn.textContent='Close Tunnel';btn.className='hud-btn-sm danger';
      document.getElementById('tunnel-link').href=d.url;
      document.getElementById('tunnel-link').textContent=d.url;
      const qr=document.getElementById('tunnel-qr');
      qr.src='/api/tunnel/qr?url='+encodeURIComponent(d.url);qr.style.display='block';
      urlDiv.style.display='block';
    }else if(d.state==='starting'){
      st.innerHTML='<span style="color:var(--orange)">Starting...</span>';
      btn.disabled=true;setTimeout(checkTunnel,2000);
    }else if(d.state==='error'){
      tunnelActive=false;
      st.innerHTML='<span style="color:var(--red)">Error: '+d.error+'</span>';
      btn.textContent='Retry';btn.className='hud-btn-sm';btn.disabled=false;
      urlDiv.style.display='none';
    }else{
      tunnelActive=false;
      st.textContent=d.installed?'Inactive':'cloudflared not installed (will auto-install)';
      btn.textContent='Open Tunnel';btn.className='hud-btn-sm';btn.disabled=false;
      urlDiv.style.display='none';
    }
  }).catch(()=>{});
}
function toggleTunnel(){
  const btn=document.getElementById('tunnel-btn');btn.disabled=true;
  if(tunnelActive){
    fetch('/api/tunnel/stop',{method:'POST'}).then(()=>{checkTunnel()});
  }else{
    document.getElementById('tunnel-status').innerHTML='<span style="color:var(--orange)">Starting...</span>';
    fetch('/api/tunnel/start',{method:'POST'}).then(()=>{setTimeout(checkTunnel,3000)});
  }
}
function copyTunnelUrl(){
  const url=document.getElementById('tunnel-link').textContent;
  navigator.clipboard.writeText(url).then(()=>{
    const btn=event.target;btn.textContent='Copied!';setTimeout(()=>{btn.textContent='Copy'},1500);
  });
}
checkTunnel();
</script></body></html>"""


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            uptime = int(time.time() - START_TIME)
            gpu = get_gpu_stats()
            svc_info = {}
            for name, svc in SERVICES.items():
                info = {"status": "ready"}
                if hasattr(svc, "model_name"):
                    info["model"] = svc.model_name
                svc_info[name] = info
            data = {
                "uptime": uptime, "gpu": gpu, "system": get_system_stats(),
                "services": svc_info,
                "latency": TRACKER.get_latency_stats(),
                "recent_logs": TRACKER.get_recent(20),
            }
            await ws.send_json(data)
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
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
    loop = asyncio.get_event_loop()
    try:
        has_speech = await loop.run_in_executor(None, SERVICES["stt"].has_speech, audio_bytes)
        if not has_speech:
            log.info("STT: VAD filtered (no speech detected)")
            return {"transcription": []}
        audio_bytes.seek(0)
        transcription, info = await loop.run_in_executor(None, SERVICES["stt"].transcribe, audio_bytes)
        full_text = " ".join(t["text"] for t in transcription).strip()
        log.info(f"STT: \"{full_text}\" (lang={info.language}, prob={info.language_probability:.2f})")
        return {"transcription": transcription}
    except Exception as e:
        log.error(f"STT error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.post("/transcribe")
async def stt_transcribe_v2(audio: UploadFile = File(...), language: Optional[str] = Form(None)):
    if "stt" not in SERVICES:
        raise HTTPException(503, "STT service not loaded")
    audio_bytes = BytesIO(await audio.read())
    loop = asyncio.get_event_loop()
    try:
        has_speech = await loop.run_in_executor(None, SERVICES["stt"].has_speech, audio_bytes)
        if not has_speech:
            return {"text": "", "segments": [], "language": None, "language_probability": 0}
        audio_bytes.seek(0)
        transcription, info = await loop.run_in_executor(
            None, lambda: SERVICES["stt"].transcribe(audio_bytes, language=language)
        )
        full_text = " ".join(t["text"] for t in transcription).strip()
        log.info(f"STT: \"{full_text}\"")
        return {"text": full_text, "segments": transcription,
                "language": info.language, "language_probability": round(info.language_probability, 3)}
    except Exception as e:
        log.error(f"STT error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.websocket("/ws/stt")
async def websocket_stt(ws: WebSocket):
    if "stt" not in SERVICES:
        await ws.close(code=1013, reason="STT service not loaded")
        return
    await ws.accept()
    audio_buffer = BytesIO()
    log.info("WebSocket STT: client connected")
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
                        audio_buffer.seek(0)
                        try:
                            transcription, info = SERVICES["stt"].transcribe(audio_buffer)
                            full_text = " ".join(t["text"] for t in transcription).strip()
                            log.info(f"WS-STT: \"{full_text}\"")
                            await ws.send_json({"text": full_text, "segments": transcription,
                                                "language": info.language, "is_final": True})
                        except Exception as e:
                            await ws.send_json({"error": str(e), "is_final": True})
                        audio_buffer = BytesIO()
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

        if stream:
            generator = SERVICES["llm"].chat(
                messages, max_tokens, temperature, top_p, stream=True, session_id=session_id
            )
            return StreamingResponse(
                generator, media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: SERVICES["llm"].chat(
                    messages, max_tokens, temperature, top_p, stream=False, session_id=session_id
                ))
            return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"LLM error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))
    finally:
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
        loop = asyncio.get_event_loop()
        wav_bytes = await loop.run_in_executor(None, lambda: SERVICES["tts"].synthesize(text, voice=voice, speed=speed))
        log.info(f"TTS: \"{text[:60]}\" voice={voice}")
        return StreamingResponse(BytesIO(wav_bytes), media_type="audio/wav",
                                 headers={"Content-Disposition": "attachment; filename=speech.wav"})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        log.error(f"TTS error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


@app.get("/tts/voices")
async def tts_voices():
    if "tts" not in SERVICES:
        raise HTTPException(503, "TTS service not loaded")
    return {"voices": SERVICES["tts"].list_voices()}


# -- Vision Routes -----------------------------------------------------

@app.post("/caption")
async def vision_caption(image: UploadFile = File(...), prompt: str = Form(None)):
    image_bytes = await image.read()
    loop = asyncio.get_event_loop()
    if "vision" in SERVICES:
        try:
            svc = SERVICES["vision"]
            caption = await loop.run_in_executor(None, lambda: svc.caption(image_bytes, prompt=prompt or None))
            log.info(f"Vision ({svc.backend}): \"{caption}\"")
            return {"caption": caption}
        except Exception:
            log.error(f"Vision error: {traceback.format_exc()}")
    if "llm" in SERVICES and getattr(SERVICES["llm"], "supports_vision", False):
        try:
            caption = await loop.run_in_executor(None, lambda: SERVICES["llm"].caption_image(image_bytes, prompt=prompt or None))
            log.info(f"Vision (VLM): \"{caption}\"")
            return {"caption": caption}
        except Exception:
            log.error(f"VLM error: {traceback.format_exc()}")
    if "vision" not in SERVICES:
        raise HTTPException(503, "Vision service not loaded")
    raise HTTPException(500, "Vision captioning failed")


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
        loop = asyncio.get_event_loop()
        gen_kwargs = dict(
            prompt=prompt, negative_prompt=body.get("negative_prompt", ""),
            steps=int(body.get("steps", 20)), cfg_scale=float(body.get("cfg_scale", 7.0)),
            width=int(body.get("width", 1024)), height=int(body.get("height", 1024)),
            seed=int(body.get("seed", -1)), sampler_name=body.get("sampler_name"),
        )
        image_bytes = await loop.run_in_executor(None, lambda: SERVICES["imagegen"].generate(**gen_kwargs))
        log.info(f"ImageGen: \"{prompt[:60]}\"")
        return {"images": [base64.b64encode(image_bytes).decode()], "parameters": body, "info": ""}
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
        loop = asyncio.get_event_loop()
        gen_kwargs = dict(
            prompt=prompt, negative_prompt=body.get("negative_prompt", ""),
            steps=int(body.get("steps", 20)), cfg_scale=float(body.get("cfg_scale", 7.0)),
            width=int(body.get("width", 1024)), height=int(body.get("height", 1024)),
            seed=int(body.get("seed", -1)), sampler_name=body.get("sampler_name"),
        )
        image_bytes = await loop.run_in_executor(None, lambda: SERVICES["imagegen"].generate(**gen_kwargs))
        log.info(f"ImageGen: \"{prompt[:60]}\"")
        return StreamingResponse(BytesIO(image_bytes), media_type="image/png")
    except Exception as e:
        log.error(f"ImageGen error: {traceback.format_exc()}")
        raise HTTPException(500, str(e))


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
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(None, SERVICES["embeddings"].embed, inp)
        data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
        return {"object": "list", "data": data, "model": SERVICES["embeddings"].model_name,
                "usage": {"prompt_tokens": sum(len(t.split()) for t in inp), "total_tokens": sum(len(t.split()) for t in inp)}}
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
        if name == "llm" and hasattr(svc, "supports_vision"):
            info["supports_vision"] = svc.supports_vision
        if name == "tts" and hasattr(svc, "list_voices"):
            info["voices"] = svc.list_voices()
        models[name] = info
    return {"gpu": gpu, "models": models}


@app.post("/models/{service}/unload")
async def unload_model(service: str):
    if service not in SERVICES:
        raise HTTPException(404, f"Service '{service}' not loaded")
    svc = SERVICES[service]
    svc_name = getattr(svc, "model_name", service)
    if hasattr(svc, "unload"):
        svc.unload()
    del SERVICES[service]
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
        gc.collect()
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
    try:
        _load_single_service(service, _LAUNCH_ARGS)
    except Exception:
        log.error(f"Failed to reload {service.upper()}:\n{traceback.format_exc()}")
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
import re as _re
import platform as _platform

_tunnel_process = None
_tunnel_url = None
_tunnel_error = None
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
        global _tunnel_error
        if not _cloudflared_bin():
            ok, err = _install_cloudflared()
            if not ok:
                _tunnel_error = err
                return
        ok, result = _start_tunnel(port)
        if not ok:
            _tunnel_error = result

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
    return _PLAYGROUND_HTML


_PLAYGROUND_HTML = r"""<!DOCTYPE html>
<html><head><title>TARS-AI Playground</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a1220;--bg2:#0e1830;--panel:rgba(14,26,48,0.55);--panel-solid:rgba(14,26,48,0.78);--border:rgba(0,229,255,0.18);--border-hi:rgba(0,229,255,0.45);--cyan:#00e5ff;--cyan-dim:rgba(0,229,255,0.5);--green:#39ff14;--orange:#ffb700;--red:#ff4444;--purple:#b44dff;--magenta:#ff2d8a;--text:#e2eaf2;--text-dim:#5a7a94;--font-mono:'Share Tech Mono',monospace;--font-hud:'Orbitron',sans-serif;--font-body:'Rajdhani',sans-serif;--radius:14px;--radius-sm:8px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;min-height:100vh;background:var(--bg);color:var(--text);font-family:var(--font-mono);-webkit-font-smoothing:antialiased}
body{padding:0;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,0,0,0.35) 100%);pointer-events:none;z-index:0}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,0.003) 3px,rgba(0,229,255,0.003) 6px);pointer-events:none;z-index:9999}
.nebula-layer{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.nebula-blob{position:absolute;border-radius:50%;filter:blur(90px);will-change:transform,opacity}
.nb-1{width:500px;height:500px;background:radial-gradient(circle,rgba(120,40,200,0.35) 0%,rgba(80,20,160,0.1) 50%,transparent 70%);top:5%;left:-5%;animation:nd1 55s ease-in-out infinite}
.nb-2{width:450px;height:450px;background:radial-gradient(circle,rgba(0,180,240,0.25) 0%,rgba(0,120,200,0.08) 50%,transparent 70%);top:50%;right:-10%;animation:nd2 65s ease-in-out infinite}
.nb-3{width:400px;height:400px;background:radial-gradient(circle,rgba(160,30,220,0.30) 0%,rgba(100,20,180,0.08) 50%,transparent 70%);bottom:0;left:25%;animation:nd3 60s ease-in-out infinite}
@keyframes nd1{0%{transform:translate(0,0) scale(1);opacity:.6}25%{transform:translate(10vw,12vh) scale(1.2);opacity:.8}50%{transform:translate(18vw,5vh) scale(.95);opacity:.5}75%{transform:translate(5vw,-8vh) scale(1.1);opacity:.7}100%{transform:translate(0,0) scale(1);opacity:.6}}
@keyframes nd2{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-12vw,-6vh) scale(1.15);opacity:.7}50%{transform:translate(-8vw,10vh) scale(.9);opacity:.6}75%{transform:translate(5vw,8vh) scale(1.1);opacity:.4}100%{transform:translate(0,0) scale(1);opacity:.5}}
@keyframes nd3{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-8vw,-10vh) scale(1.1);opacity:.7}50%{transform:translate(10vw,-5vh) scale(1.2);opacity:.6}75%{transform:translate(15vw,8vh) scale(.95);opacity:.8}100%{transform:translate(0,0) scale(1);opacity:.5}}
.wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:28px 32px 40px}
@media(max-width:900px){.wrap{padding:20px 16px 32px}}
.top-bar{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;background:var(--panel-solid);backdrop-filter:blur(28px) saturate(1.4);border:1px solid rgba(0,229,255,0.25);border-radius:var(--radius);margin-bottom:20px;box-shadow:0 12px 48px rgba(0,0,0,0.3),0 4px 12px rgba(0,0,0,0.15)}
.top-bar h1{font-family:var(--font-hud);font-size:20px;font-weight:900;letter-spacing:.2em;background:linear-gradient(135deg,var(--cyan),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.top-bar a{font-family:var(--font-hud);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--cyan);text-decoration:none;opacity:.6;transition:opacity .2s}
.top-bar a:hover{opacity:1}
.key-bar{display:flex;gap:10px;align-items:center;margin-bottom:16px}
.key-bar span{font-family:var(--font-hud);font-size:11px;letter-spacing:.1em;color:var(--text-dim);text-transform:uppercase}
.key-bar input{flex:1;max-width:320px;padding:8px 12px;background:rgba(0,229,255,0.04);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-family:var(--font-mono);font-size:12px;outline:none;transition:border-color .2s}
.key-bar input:focus{border-color:var(--border-hi)}
.glass{position:relative;background:var(--panel);backdrop-filter:blur(22px) saturate(1.3);border:1px solid rgba(0,229,255,0.2);border-radius:var(--radius);box-shadow:0 8px 32px rgba(0,0,0,0.25),inset 0 1px 0 rgba(255,255,255,0.1);padding:18px 20px;margin-bottom:16px}
.glass::before{content:'';position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,0.09) 0%,rgba(255,255,255,0.03) 40%,transparent 60%,rgba(0,229,255,0.04) 100%);pointer-events:none;z-index:0}
.glass>*{position:relative;z-index:1}
.tabs{display:flex;gap:2px;margin-bottom:16px;background:rgba(10,18,32,0.55);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;backdrop-filter:blur(20px)}
.tab{flex:1;padding:12px 16px;text-align:center;font-family:var(--font-hud);font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim);cursor:pointer;transition:all .25s;border:none;background:transparent;position:relative}
.tab:hover{color:rgba(0,229,255,0.8);background:rgba(0,229,255,0.04)}
.tab.active{color:var(--cyan);background:rgba(0,229,255,0.08);box-shadow:inset 0 -2px 0 var(--cyan);text-shadow:0 0 12px rgba(0,229,255,0.4)}
.tab.disabled{opacity:.25;cursor:not-allowed;pointer-events:none}
.panel{display:none}
.panel.active{display:block}
textarea,input[type=text],select{width:100%;padding:12px 16px;background:rgba(0,229,255,0.04);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-family:var(--font-mono);font-size:13px;margin:6px 0;outline:none;transition:border-color .2s}
textarea{height:110px;resize:vertical}
textarea:focus,input[type=text]:focus,select:focus{border-color:var(--border-hi);box-shadow:0 0 12px rgba(0,229,255,0.08)}
select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300e5ff'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center;padding-right:32px}
select option{background:var(--bg2);color:var(--text)}
label{font-family:var(--font-hud);font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim);display:block;margin-top:10px}
.hud-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 24px;border-radius:var(--radius-sm);font-family:var(--font-hud);font-size:11px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;cursor:pointer;transition:all .25s;border:1px solid rgba(0,229,255,0.3);background:rgba(0,229,255,0.06);color:var(--cyan);text-shadow:0 0 8px rgba(0,229,255,0.2);margin:6px 4px 6px 0;backdrop-filter:blur(12px)}
.hud-btn:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi);box-shadow:0 0 20px rgba(0,229,255,0.15);text-shadow:0 0 12px rgba(0,229,255,0.5)}
.hud-btn.danger{border-color:rgba(255,68,68,0.3);color:var(--red);background:rgba(255,68,68,0.06);text-shadow:0 0 8px rgba(255,68,68,0.2)}
.hud-btn.danger:hover{background:rgba(255,68,68,0.12);border-color:rgba(255,68,68,0.5);box-shadow:0 0 20px rgba(255,68,68,0.15)}
.hud-btn.recording{border-color:rgba(255,68,68,0.6);color:var(--red);background:rgba(255,68,68,0.1);animation:recPulse 1s ease-in-out infinite}
@keyframes recPulse{0%,100%{box-shadow:0 0 8px rgba(255,68,68,0.2)}50%{box-shadow:0 0 20px rgba(255,68,68,0.5)}}
.output{background:rgba(0,0,0,0.3);border:1px solid rgba(0,229,255,0.1);border-radius:var(--radius-sm);padding:16px 18px;margin-top:12px;min-height:140px;max-height:500px;overflow-y:auto;font-size:15px;color:var(--text-dim);scrollbar-width:thin;scrollbar-color:rgba(0,229,255,0.2) transparent;white-space:pre-wrap}
.msg{margin:6px 0;padding:8px 12px;border-radius:var(--radius-sm);line-height:1.5}
.msg.user{background:rgba(0,229,255,0.06);border-left:2px solid var(--cyan);color:var(--cyan)}
.msg.assistant{background:rgba(180,77,255,0.06);border-left:2px solid var(--purple);color:var(--text)}
.msg.error{background:rgba(255,68,68,0.06);border-left:2px solid var(--red);color:var(--red)}
audio{width:100%;margin-top:12px;border-radius:var(--radius-sm);outline:none}
audio::-webkit-media-controls-panel{background:var(--bg2)}
img.preview{max-width:100%;max-height:400px;margin-top:12px;border:1px solid var(--border);border-radius:var(--radius-sm)}
input[type=file]{font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}
input[type=file]::file-selector-button{font-family:var(--font-hud);font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:8px 16px;border:1px solid rgba(0,229,255,0.3);border-radius:var(--radius-sm);background:rgba(0,229,255,0.06);color:var(--cyan);cursor:pointer;margin-right:10px;transition:all .2s}
input[type=file]::file-selector-button:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi)}
</style></head><body>
<div class="nebula-layer" aria-hidden="true"><div class="nebula-blob nb-1"></div><div class="nebula-blob nb-2"></div><div class="nebula-blob nb-3"></div></div>
<div class="wrap">
<div class="top-bar">
  <h1>PLAYGROUND</h1>
  <a href="/">Dashboard</a>
</div>
<div class="tabs">
  <div class="tab active" data-svc="llm" onclick="switchTab('chat')">Chat</div>
  <div class="tab" data-svc="stt" onclick="switchTab('stt')">STT</div>
  <div class="tab" data-svc="tts" onclick="switchTab('tts')">TTS</div>
  <div class="tab" data-svc="vision" onclick="switchTab('vis')">Vision</div>
  <div class="tab" data-svc="imagegen" onclick="switchTab('img')">Image Gen</div>
</div>
<div id="p-chat" class="panel active"><div class="glass" style="display:flex;flex-direction:column;gap:0;padding:0;overflow:hidden">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid var(--border)">
    <span style="font-family:var(--font-hud);font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim)">Chat</span>
    <button class="hud-btn danger" style="padding:4px 12px;font-size:9px;margin:0" onclick="document.getElementById('chat-out').innerHTML=''">Clear</button>
  </div>
  <div class="output" id="chat-out" style="flex:1;min-height:300px;max-height:460px;border:none;border-radius:0;margin:0;padding:14px 16px"></div>
  <div style="display:flex;gap:8px;align-items:flex-end;padding:10px 14px;border-top:1px solid var(--border);background:rgba(0,0,0,0.15)">
    <textarea id="chat-input" placeholder="Type a message..." style="flex:1;height:44px;min-height:44px;max-height:120px;resize:vertical;margin:0;padding:10px 14px;font-size:15px"></textarea>
    <button class="hud-btn" style="margin:0;height:44px;padding:0 20px;flex-shrink:0" onclick="sendChat()">Send</button>
  </div>
</div></div>
<div id="p-stt" class="panel"><div class="glass">
  <input type="file" id="stt-file" accept="audio/*">
  <div style="margin-top:10px">
    <button class="hud-btn" onclick="transcribeFile()">Transcribe File</button>
    <button class="hud-btn" id="rec-btn" onclick="toggleRecord()">Record</button>
  </div>
  <div class="output" id="stt-out">Upload an audio file or click Record.</div>
</div></div>
<div id="p-tts" class="panel"><div class="glass" style="display:flex;flex-direction:column;gap:0;padding:0;overflow:hidden">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid var(--border)">
    <span style="font-family:var(--font-hud);font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--text-dim)">Text to Speech</span>
    <span id="tts-status" style="font-family:var(--font-hud);font-size:10px;letter-spacing:.1em;color:var(--text-dim)"></span>
  </div>
  <div style="padding:16px 18px;display:flex;flex-direction:column;gap:12px">
    <textarea id="tts-input" placeholder="Type something to hear it spoken..." style="height:90px;margin:0"></textarea>
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
      <div style="min-width:140px"><label>Voice</label><select id="tts-voice" style="margin-top:4px"></select></div>
      <button class="hud-btn" style="margin:0;height:42px;padding:0 24px;flex-shrink:0" id="tts-btn" onclick="synthesize()">Speak</button>
    </div>
    <div id="tts-player" style="display:none;gap:10px;align-items:center;background:rgba(0,120,255,0.12);border:1px solid rgba(0,150,255,0.35);border-radius:var(--radius-sm);padding:8px 12px">
      <audio id="tts-audio" controls style="flex:1;outline:none;height:40px"></audio>
      <button class="hud-btn" style="margin:0;padding:6px 14px;font-size:9px;height:36px;flex-shrink:0" onclick="const a=document.getElementById('tts-audio');if(a.src){const l=document.createElement('a');l.href=a.src;l.download='tts_output.wav';l.click()}">Save</button>
    </div>
  </div>
<style>#tts-audio::-webkit-media-controls-panel{background:linear-gradient(135deg,#1a3a5c,#0d2240);border-radius:8px}#tts-audio::-webkit-media-controls-current-time-display,#tts-audio::-webkit-media-controls-time-remaining-display{color:#7cb8ff}#tts-audio::-webkit-media-controls-play-button{filter:brightness(2)}#tts-audio::-webkit-media-controls-timeline{filter:hue-rotate(200deg) brightness(1.4)}</style>
</div></div>
<div id="p-vis" class="panel"><div class="glass">
  <label>Image</label>
  <input type="file" id="vis-file" accept="image/*">
  <div id="vis-drop" style="margin:8px 0;padding:28px;text-align:center;border:2px dashed var(--border);border-radius:var(--radius-sm);color:var(--text-dim);font-size:12px;cursor:pointer;transition:border-color .2s,background .2s">Drop image here or click browse above</div>
  <img class="preview" id="vis-preview" style="display:none;max-height:260px;margin-bottom:8px">
  <label>Prompt <span style="opacity:.5;font-weight:400;text-transform:none;letter-spacing:0">(optional \u2013 guide the caption)</span></label>
  <input type="text" id="vis-prompt" placeholder='e.g. "a photo of" or "describe the objects in"'>
  <button class="hud-btn" onclick="captionImg()">Caption</button>
  <div class="output" id="vis-out">Upload an image and click Caption.</div>
</div></div>
<div id="p-img" class="panel"><div class="glass">
  <textarea id="img-prompt" placeholder="Image prompt..."></textarea>
  <label>Negative prompt</label><input type="text" id="img-neg" placeholder="optional">
  <button class="hud-btn" onclick="generateImg()">Generate</button>
  <div class="output" id="img-out">Enter a prompt and click Generate.</div>
  <img class="preview" id="img-preview" style="display:none">
</div></div>
<div style="display:flex;gap:10px;margin-bottom:8px;flex-wrap:wrap">
  <a href="/" style="font-family:'Orbitron',sans-serif;font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.2);border-radius:8px;color:#00e5ff;text-decoration:none">Dashboard</a>
  <a href="/ui" style="font-family:'Orbitron',sans-serif;font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.2);border-radius:8px;color:#00e5ff;text-decoration:none">Settings</a>
  <a href="/docs" style="font-family:'Orbitron',sans-serif;font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.2);border-radius:8px;color:#00e5ff;text-decoration:none">API Docs</a>
  <a href="/logout" style="font-family:'Orbitron',sans-serif;font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(255,68,68,0.06);border:1px solid rgba(255,68,68,0.3);border-radius:8px;color:#ff6666;text-decoration:none">Logout</a>
</div>
</div>
<script>
const base='';
function hdr(){return {'Content-Type':'application/json'}}
function hdrForm(){return {}}

function switchTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const map={chat:0,stt:1,tts:2,vis:3,img:4};
  document.querySelectorAll('.tab')[map[name]].classList.add('active');
  document.getElementById('p-'+name).classList.add('active');
  if(name==='tts')loadVoices();
}

async function sendChat(){
  const input=document.getElementById('chat-input');const out=document.getElementById('chat-out');
  const text=input.value.trim();if(!text)return;
  input.value='';
  const userDiv=document.createElement('div');userDiv.className='msg user';userDiv.textContent=text;out.appendChild(userDiv);
  const msgDiv=document.createElement('div');msgDiv.className='msg assistant';out.appendChild(msgDiv);
  try{
    const resp=await fetch(base+'/v1/chat/completions',{method:'POST',headers:hdr(),
      body:JSON.stringify({messages:[{role:'user',content:text}],stream:true,max_tokens:512})});
    if(!resp.ok){msgDiv.className='msg error';msgDiv.textContent='Error: '+resp.status+' '+resp.statusText;out.scrollTop=out.scrollHeight;return;}
    const reader=resp.body.getReader();const dec=new TextDecoder();let buf='';
    while(true){
      const{done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data: ')||line==='data: [DONE]')continue;
        try{
          const c=JSON.parse(line.slice(6));
          const t=c.choices[0].delta.content||'';
          if(t)msgDiv.textContent+=t;
          if(c.choices[0].finish_reason==='stop'&&c.usage){
            const u=c.usage;const ms=u.elapsed_ms||1;
            const tps=(u.completion_tokens/(ms/1000)).toFixed(1);
            const stat=document.createElement('div');
            stat.style.cssText='text-align:right;font-size:11px;color:var(--text-dim);margin-top:4px;font-family:var(--font-hud);letter-spacing:.08em';
            stat.textContent=u.completion_tokens+' tokens · '+tps+' t/s';
            out.appendChild(stat);
          }
        }catch(e){}
      }
    }
  }catch(e){msgDiv.className='msg error';msgDiv.textContent='Error: '+e;}
  out.scrollTop=out.scrollHeight;
}

async function transcribeFile(){
  const file=document.getElementById('stt-file').files[0];
  if(!file){document.getElementById('stt-out').textContent='Select a file first.';return}
  const fd=new FormData();fd.append('audio',file);
  document.getElementById('stt-out').textContent='Transcribing...';
  try{
    const resp=await fetch(base+'/save_audio',{method:'POST',headers:hdrForm(),body:fd});
    const d=await resp.json();
    const text=d.transcription?d.transcription.map(s=>s.text).join(' '):'(empty)';
    document.getElementById('stt-out').textContent=text;
  }catch(e){document.getElementById('stt-out').textContent='Error: '+e}
}

let mediaRec=null,audioChunks=[];
function toggleRecord(){
  const btn=document.getElementById('rec-btn');
  if(mediaRec&&mediaRec.state==='recording'){
    mediaRec.stop();btn.textContent='Record';btn.className='hud-btn';return;
  }
  navigator.mediaDevices.getUserMedia({audio:true}).then(stream=>{
    mediaRec=new MediaRecorder(stream);audioChunks=[];
    mediaRec.ondataavailable=e=>audioChunks.push(e.data);
    mediaRec.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop());
      const blob=new Blob(audioChunks,{type:'audio/wav'});
      const fd=new FormData();fd.append('audio',blob,'recording.wav');
      document.getElementById('stt-out').textContent='Transcribing...';
      try{
        const resp=await fetch(base+'/save_audio',{method:'POST',headers:hdrForm(),body:fd});
        const d=await resp.json();
        document.getElementById('stt-out').textContent=d.transcription?d.transcription.map(s=>s.text).join(' '):'(empty)';
      }catch(e){document.getElementById('stt-out').textContent='Error: '+e}
    };
    mediaRec.start();btn.textContent='Stop Recording';btn.className='hud-btn recording';
  });
}

async function loadVoices(){
  try{
    const resp=await fetch(base+'/tts/voices',{headers:hdrForm()});
    const d=await resp.json();const sel=document.getElementById('tts-voice');
    sel.innerHTML='';
    (d.voices||[]).forEach(v=>{const o=document.createElement('option');o.value=v;o.text=v;sel.add(o)});
  }catch(e){}
}

async function synthesize(){
  const text=document.getElementById('tts-input').value.trim();if(!text)return;
  const voice=document.getElementById('tts-voice').value||undefined;
  const btn=document.getElementById('tts-btn');
  const status=document.getElementById('tts-status');
  const player=document.getElementById('tts-player');
  btn.textContent='Generating...';btn.style.pointerEvents='none';btn.style.opacity='.5';
  try{
    const t0=performance.now();
    const resp=await fetch(base+'/tts/generate',{method:'POST',headers:hdr(),
      body:JSON.stringify({text,voice})});
    if(!resp.ok){status.textContent='Error: '+resp.status;status.style.color='var(--red)';player.style.display='block';return}
    const blob=await resp.blob();const url=URL.createObjectURL(blob);
    const audio=document.getElementById('tts-audio');audio.src=url;
    player.style.display='flex';
    const ms=Math.round(performance.now()-t0);
    status.style.color='var(--text-dim)';
    status.textContent='Generated in '+ms+'ms \u00B7 '+(blob.size/1024).toFixed(1)+' KB';
    audio.play();
  }catch(e){status.textContent='Error: '+e;status.style.color='var(--red)';player.style.display='flex'}
  finally{btn.textContent='Speak';btn.style.pointerEvents='';btn.style.opacity=''}
}

async function captionImg(){
  const file=document.getElementById('vis-file').files[0];
  if(!file){document.getElementById('vis-out').textContent='Select an image first.';return}
  const prompt=document.getElementById('vis-prompt').value.trim();
  document.getElementById('vis-out').textContent='Captioning...';
  const fd=new FormData();fd.append('image',file);
  if(prompt)fd.append('prompt',prompt);
  try{
    const t0=performance.now();
    const resp=await fetch(base+'/caption',{method:'POST',body:fd});
    if(!resp.ok){document.getElementById('vis-out').textContent='Error: '+resp.status+' '+resp.statusText;return}
    const d=await resp.json();
    const ms=Math.round(performance.now()-t0);
    document.getElementById('vis-out').textContent=d.caption+'\n\n('+ms+'ms)';
  }catch(e){document.getElementById('vis-out').textContent='Error: '+e}
}

async function generateImg(){
  const prompt=document.getElementById('img-prompt').value.trim();if(!prompt)return;
  const neg=document.getElementById('img-neg').value.trim();
  document.getElementById('img-out').textContent='Generating...';
  document.getElementById('img-preview').style.display='none';
  try{
    const resp=await fetch(base+'/generate_image',{method:'POST',headers:hdr(),
      body:JSON.stringify({prompt,negative_prompt:neg,steps:20})});
    const blob=await resp.blob();const url=URL.createObjectURL(blob);
    const img=document.getElementById('img-preview');img.src=url;img.style.display='block';
    document.getElementById('img-out').textContent='Done.';
  }catch(e){document.getElementById('img-out').textContent='Error: '+e}
}

document.getElementById('chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat()}});
loadVoices();

// Vision: image preview + drag-and-drop
(function(){
  const inp=document.getElementById('vis-file'),drop=document.getElementById('vis-drop'),prev=document.getElementById('vis-preview');
  function showPreview(file){
    const url=URL.createObjectURL(file);prev.src=url;prev.style.display='block';
    prev.onload=()=>URL.revokeObjectURL(url);
  }
  inp.addEventListener('change',()=>{if(inp.files[0])showPreview(inp.files[0])});
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.style.borderColor='var(--cyan)';drop.style.background='rgba(0,229,255,0.06)'});
  drop.addEventListener('dragleave',()=>{drop.style.borderColor='';drop.style.background=''});
  drop.addEventListener('drop',e=>{
    e.preventDefault();drop.style.borderColor='';drop.style.background='';
    const file=e.dataTransfer.files[0];
    if(file&&file.type.startsWith('image/')){
      const dt=new DataTransfer();dt.items.add(file);inp.files=dt.files;
      showPreview(file);
    }
  });
})();

// Dim tabs for services that aren't loaded, auto-select first available
fetch(base+'/health').then(r=>r.json()).then(d=>{
  const active=Object.keys(d.services||{});
  const tabs=document.querySelectorAll('.tab[data-svc]');
  let firstAvail=null;
  tabs.forEach(tab=>{
    if(!active.includes(tab.dataset.svc)){
      tab.classList.add('disabled');
      tab.classList.remove('active');
    }else if(!firstAvail){firstAvail=tab}
  });
  // If current active tab is disabled, switch to first available
  const cur=document.querySelector('.tab.active');
  if(!cur||cur.classList.contains('disabled')){
    if(firstAvail){
      const map={llm:'chat',stt:'stt',tts:'tts',vision:'vis',imagegen:'img'};
      switchTab(map[firstAvail.dataset.svc]||'chat');
    }
  }
}).catch(()=>{});
</script>
</body></html>"""


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
    cfg = configparser.ConfigParser()
    for section in _CONFIG_DEFAULTS:
        if section in body:
            cfg[section] = {k: str(v) for k, v in body[section].items()}
        else:
            cfg[section] = dict(_CONFIG_DEFAULTS[section])
    save_config(cfg)
    load_config()
    return {"status": "saved", "message": "Settings saved. Restart server for model changes to take effect."}


@app.get("/ui", response_class=HTMLResponse)
async def settings_page():
    return _SETTINGS_HTML


_SETTINGS_HTML = r"""<!DOCTYPE html>
<html><head><title>TARS-AI Server Settings</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0a1220;--bg2:#0e1830;--panel:rgba(14,26,48,0.55);--panel-solid:rgba(14,26,48,0.78);--border:rgba(0,229,255,0.18);--border-hi:rgba(0,229,255,0.45);--cyan:#00e5ff;--cyan-dim:rgba(0,229,255,0.5);--green:#39ff14;--orange:#ffb700;--red:#ff4444;--purple:#b44dff;--text:#e2eaf2;--text-dim:#5a7a94;--font-mono:'Share Tech Mono',monospace;--font-hud:'Orbitron',sans-serif;--font-body:'Rajdhani',sans-serif;--radius:14px;--radius-sm:8px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;min-height:100vh;background:var(--bg);color:var(--text);font-family:var(--font-mono);-webkit-font-smoothing:antialiased}
body{padding:0;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(0,0,0,0.35) 100%);pointer-events:none;z-index:0}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,229,255,0.003) 3px,rgba(0,229,255,0.003) 6px);pointer-events:none;z-index:9999}
.nebula-layer{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.nebula-blob{position:absolute;border-radius:50%;filter:blur(90px);will-change:transform,opacity}
.nb-1{width:500px;height:500px;background:radial-gradient(circle,rgba(120,40,200,0.35) 0%,rgba(80,20,160,0.1) 50%,transparent 70%);top:5%;left:-5%;animation:nd1 55s ease-in-out infinite}
.nb-2{width:450px;height:450px;background:radial-gradient(circle,rgba(0,180,240,0.25) 0%,rgba(0,120,200,0.08) 50%,transparent 70%);top:50%;right:-10%;animation:nd2 65s ease-in-out infinite}
.nb-3{width:400px;height:400px;background:radial-gradient(circle,rgba(160,30,220,0.30) 0%,rgba(100,20,180,0.08) 50%,transparent 70%);bottom:0;left:25%;animation:nd3 60s ease-in-out infinite}
@keyframes nd1{0%{transform:translate(0,0) scale(1);opacity:.6}25%{transform:translate(10vw,12vh) scale(1.2);opacity:.8}50%{transform:translate(18vw,5vh) scale(.95);opacity:.5}75%{transform:translate(5vw,-8vh) scale(1.1);opacity:.7}100%{transform:translate(0,0) scale(1);opacity:.6}}
@keyframes nd2{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-12vw,-6vh) scale(1.15);opacity:.7}50%{transform:translate(-8vw,10vh) scale(.9);opacity:.6}75%{transform:translate(5vw,8vh) scale(1.1);opacity:.4}100%{transform:translate(0,0) scale(1);opacity:.5}}
@keyframes nd3{0%{transform:translate(0,0) scale(1);opacity:.5}25%{transform:translate(-8vw,-10vh) scale(1.1);opacity:.7}50%{transform:translate(10vw,-5vh) scale(1.2);opacity:.6}75%{transform:translate(15vw,8vh) scale(.95);opacity:.8}100%{transform:translate(0,0) scale(1);opacity:.5}}
.wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:28px 32px 40px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media(max-width:960px){.grid-2{grid-template-columns:1fr}.wrap{padding:20px 16px 32px}}
.top-bar{display:flex;align-items:center;justify-content:space-between;padding:16px 24px;background:var(--panel-solid);backdrop-filter:blur(28px) saturate(1.4);border:1px solid rgba(0,229,255,0.25);border-radius:var(--radius);margin-bottom:20px;box-shadow:0 12px 48px rgba(0,0,0,0.3),0 4px 12px rgba(0,0,0,0.15)}
.top-bar h1{font-family:var(--font-hud);font-size:20px;font-weight:900;letter-spacing:.2em;background:linear-gradient(135deg,var(--cyan),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.top-bar a{font-family:var(--font-hud);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--cyan);text-decoration:none;opacity:.6;transition:opacity .2s}
.top-bar a:hover{opacity:1}
.glass{position:relative;background:var(--panel);backdrop-filter:blur(22px) saturate(1.3);border:1px solid rgba(0,229,255,0.2);border-radius:var(--radius);box-shadow:0 8px 32px rgba(0,0,0,0.25),inset 0 1px 0 rgba(255,255,255,0.1);padding:20px 24px;margin-bottom:16px}
.glass::before{content:'';position:absolute;inset:0;border-radius:inherit;background:linear-gradient(135deg,rgba(255,255,255,0.09) 0%,rgba(255,255,255,0.03) 40%,transparent 60%,rgba(0,229,255,0.04) 100%);pointer-events:none;z-index:0}
.glass>*{position:relative;z-index:1}
h2{font-family:var(--font-hud);font-size:12px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--cyan);margin-bottom:14px}
.form-row{display:flex;align-items:center;gap:14px;margin:10px 0;flex-wrap:wrap}
.form-row label{font-family:var(--font-hud);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-dim);min-width:160px;flex-shrink:0}
input[type=text],input[type=number],input[type=password],select{padding:10px 14px;background:rgba(0,229,255,0.04);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);font-family:var(--font-mono);font-size:13px;outline:none;transition:border-color .2s}
input[type=text]:focus,input[type=number]:focus,input[type=password]:focus,select:focus{border-color:var(--border-hi);box-shadow:0 0 12px rgba(0,229,255,0.08)}
input[type=text],input[type=password]{flex:1;max-width:500px}
input[type=number]{width:120px}
select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2300e5ff'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center;padding-right:30px;min-width:140px}
select option{background:var(--bg2);color:var(--text)}
input[type=checkbox]{appearance:none;width:20px;height:20px;border:1px solid var(--border);border-radius:4px;background:rgba(0,229,255,0.04);cursor:pointer;position:relative;flex-shrink:0}
input[type=checkbox]:checked{background:rgba(0,229,255,0.15);border-color:var(--cyan)}
input[type=checkbox]:checked::after{content:'\2713';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:var(--cyan);font-size:14px;font-weight:700}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 14px;font-size:13px}
th{font-family:var(--font-hud);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--text-dim);border-bottom:1px solid var(--border)}
td{border-bottom:1px solid rgba(0,229,255,0.06);color:var(--text)}
.svc-name{font-family:var(--font-hud);font-weight:700;font-size:12px;letter-spacing:.1em}
.hud-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 24px;border-radius:var(--radius-sm);font-family:var(--font-hud);font-size:11px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;cursor:pointer;transition:all .25s;border:1px solid rgba(0,229,255,0.3);background:rgba(0,229,255,0.06);color:var(--cyan);text-shadow:0 0 8px rgba(0,229,255,0.2);backdrop-filter:blur(12px)}
.hud-btn:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi);box-shadow:0 0 20px rgba(0,229,255,0.15)}
.hud-btn-sm{display:inline-flex;align-items:center;padding:6px 14px;border-radius:var(--radius-sm);font-family:var(--font-hud);font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;cursor:pointer;transition:all .25s;border:1px solid rgba(0,229,255,0.3);background:rgba(0,229,255,0.06);color:var(--cyan);backdrop-filter:blur(8px)}
.hud-btn-sm:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi)}
.hud-btn-sm.danger{border-color:rgba(255,68,68,0.3);color:var(--red);background:rgba(255,68,68,0.06)}
.hud-btn-sm.danger:hover{background:rgba(255,68,68,0.12);border-color:rgba(255,68,68,0.5)}
.save-bar{display:flex;align-items:center;gap:16px;margin-top:8px}
.save-status{font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}
.save-status.ok{color:var(--green)}.save-status.err{color:var(--red)}
.hint{font-size:10px;color:var(--text-dim);margin-top:2px}
.section-note{font-size:11px;color:var(--text-dim);margin-bottom:10px}
.info-i{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;border:1px solid var(--cyan-dim);color:var(--cyan);font-family:var(--font-body);font-size:11px;font-weight:700;font-style:italic;cursor:help;flex-shrink:0;position:relative;opacity:.7;transition:opacity .2s}
.info-i:hover{opacity:1}
.info-i .tip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);width:280px;padding:10px 14px;background:var(--bg2);border:1px solid var(--border-hi);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:11px;font-style:normal;font-weight:400;color:var(--text);line-height:1.5;z-index:100;box-shadow:0 8px 32px rgba(0,0,0,0.5);pointer-events:none;white-space:normal}
.info-i:hover .tip{display:block}
.info-i .tip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--border-hi)}
.nav-links{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}
.nav-links a{font-family:var(--font-hud);font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:8px 16px;background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.2);border-radius:var(--radius-sm);color:var(--cyan);text-decoration:none;transition:all .25s}
.nav-links a:hover{background:rgba(0,229,255,0.12);border-color:var(--border-hi)}
</style></head><body>
<div class="nebula-layer" aria-hidden="true"><div class="nebula-blob nb-1"></div><div class="nebula-blob nb-2"></div><div class="nebula-blob nb-3"></div></div>
<div class="wrap">
<div class="top-bar">
  <h1>SETTINGS</h1>
  <a href="/">Dashboard</a>
</div>

<!-- Access & Security -->
<div class="glass">
  <h2>Access &amp; Security</h2>
  <div class="form-row">
    <label>API Key <span class="info-i">i<span class="tip">Bearer token required for all API requests. Auto-generated on first boot. Copy this to your TARS RPi .env file as EXTERNAL_API_KEY so it can authenticate with this server.</span></span></label>
    <input type="password" id="s-apikey" placeholder="auto-generated on first boot">
    <button class="hud-btn-sm" onclick="const i=document.getElementById('s-apikey');i.type=i.type==='password'?'text':'password'">Show</button>
  </div>
  <div class="hint" style="margin-left:162px">Used for Bearer token auth on all endpoints. Share this with your RPi config.</div>
</div>

<!-- Services & Devices -->
<div class="glass">
  <h2>Services &amp; Devices</h2>
  <div class="section-note">Enable/disable services and choose CPU or GPU per service. Restart required. <span class="info-i">i<span class="tip">Each service runs independently. Disable unused services to save GPU memory and speed up startup. Device 'auto' uses GPU if available, falls back to CPU.</span></span></div>
  <table>
    <thead><tr><th>Service</th><th>Enabled</th><th>Device</th></tr></thead>
    <tbody>
      <tr><td class="svc-name">STT <span class="info-i">i<span class="tip">Speech-to-Text: Transcribes audio to text using Faster-Whisper. Your TARS RPi sends recorded audio here for transcription.</span></span></td><td><input type="checkbox" id="svc-stt"></td><td><select id="dev-stt"><option value="auto">auto</option><option value="cuda">cuda (GPU)</option><option value="cpu">cpu</option></select></td></tr>
      <tr><td class="svc-name">TTS <span class="info-i">i<span class="tip">Text-to-Speech: Converts text to spoken audio using Piper ONNX voices. Runs on CPU only. Supports response caching for instant repeat playback.</span></span></td><td><input type="checkbox" id="svc-tts"></td><td><span style="color:var(--text-dim);font-size:11px">CPU only (Piper ONNX)</span></td></tr>
      <tr><td class="svc-name">LLM <span class="info-i">i<span class="tip">Large Language Model: Runs a local AI model for chat responses. Supports HuggingFace transformers or llama.cpp GGUF models. Most GPU-intensive service.</span></span></td><td><input type="checkbox" id="svc-llm"></td><td><select id="dev-llm"><option value="auto">auto</option><option value="cuda">cuda (GPU)</option><option value="cpu">cpu</option></select></td></tr>
      <tr><td class="svc-name">Vision <span class="info-i">i<span class="tip">Image captioning: Analyzes images and generates text descriptions. Supports BLIP, BLIP-2, Moondream, Florence-2, and other HuggingFace vision models.</span></span></td><td><input type="checkbox" id="svc-vision"></td><td><select id="dev-vision"><option value="auto">auto</option><option value="cuda">cuda (GPU)</option><option value="cpu">cpu</option></select></td></tr>
      <tr><td class="svc-name">ImageGen <span class="info-i">i<span class="tip">Image generation: Creates images from text prompts using Stable Diffusion. Very GPU-intensive — requires significant VRAM.</span></span></td><td><input type="checkbox" id="svc-imagegen"></td><td><select id="dev-imagegen"><option value="auto">auto</option><option value="cuda">cuda (GPU)</option><option value="cpu">cpu</option></select></td></tr>
      <tr><td class="svc-name">Embeddings <span class="info-i">i<span class="tip">Text embeddings: Converts text into numerical vectors for semantic search. Used by TARS memory system (RAG). Lightweight — works well on CPU.</span></span></td><td><input type="checkbox" id="svc-embeddings"></td><td><select id="dev-embeddings"><option value="auto">auto</option><option value="cuda">cuda (GPU)</option><option value="cpu">cpu</option></select></td></tr>
    </tbody>
  </table>
</div>

<div class="grid-2">
  <div>
    <!-- Server -->
    <div class="glass">
      <h2>Server</h2>
      <div class="form-row"><label>Port <span class="info-i">i<span class="tip">Network port the server listens on. Default is 5678. Make sure this matches the port in your TARS RPi configuration URLs (e.g. http://server-ip:5678).</span></span></label><input type="number" id="s-port"></div>
    </div>
    <!-- STT Config -->
    <div class="glass">
      <h2>STT Configuration</h2>
      <div class="form-row"><label>Whisper Model <span class="info-i">i<span class="tip">Larger models are more accurate but use more memory and are slower. 'large-v3' is best for accuracy, 'base' or 'small' for lower-resource systems. Model is downloaded automatically on first use.</span></span></label><select id="s-stt-model"><option>tiny</option><option>base</option><option>small</option><option>medium</option><option>large-v2</option><option>large-v3</option></select></div>
      <div class="form-row"><label>Compute Type <span class="info-i">i<span class="tip">Precision for inference. 'auto' picks the best for your hardware. 'float16' is fast on GPU, 'int8' uses less memory, 'int8_float16' balances both, 'float32' is most compatible but slowest.</span></span></label><select id="s-stt-compute"><option>auto</option><option>float16</option><option>int8</option><option>int8_float16</option><option>float32</option></select></div>
      <div class="form-row"><label>VAD Pre-filter <span class="info-i">i<span class="tip">Voice Activity Detection. Skips silent audio chunks before running Whisper, reducing unnecessary processing and improving speed. Recommended ON.</span></span></label><input type="checkbox" id="s-stt-vad"></div>
    </div>
    <!-- LLM Config -->
    <div class="glass">
      <h2>LLM Configuration</h2>
      <div class="form-row"><label>Backend <span class="info-i">i<span class="tip">'transformers' loads HuggingFace models with GPU acceleration and optional quantization. 'llamacpp' loads pre-quantized GGUF files — very fast and memory efficient.</span></span></label><select id="s-llm-backend" onchange="toggleLlmBackend()"><option value="transformers">transformers (HuggingFace)</option><option value="llamacpp">llamacpp (GGUF — fast)</option></select></div>
      <div class="form-row"><label id="s-llm-model-lbl">Model <span class="info-i">i<span class="tip">For transformers: a HuggingFace model ID (e.g. 'Qwen/Qwen3-4B'). For llamacpp: path to a .gguf file. Model is downloaded automatically on first use.</span></span></label><input type="text" id="s-llm-model"></div>
      <div id="llm-transformers-opts">
        <div class="form-row"><label>dtype <span class="info-i">i<span class="tip">Model precision. 'auto' picks the best for your GPU. 'float16' for most GPUs, 'bfloat16' for newer GPUs (Ampere+, RTX 30/40 series), 'float32' for CPU-only (slowest).</span></span></label><select id="s-llm-dtype"><option>auto</option><option>float16</option><option>bfloat16</option><option>float32</option></select></div>
        <div class="form-row"><label>Quantize <span class="info-i">i<span class="tip">Reduces model size and memory usage. '4-bit' is smallest and fastest (requires bitsandbytes). '8-bit' is a balanced middle ground. 'none' loads at full precision — best quality but most VRAM.</span></span></label><select id="s-llm-quantize"><option value="none">none</option><option value="4bit">4-bit (fastest, needs bitsandbytes)</option><option value="8bit">8-bit (balanced, needs bitsandbytes)</option></select></div>
      </div>
      <div id="llm-llamacpp-opts" style="display:none">
        <div class="form-row"><label>Context Length <span class="info-i">i<span class="tip">Maximum tokens the model can process at once. Higher values allow longer conversations but use more memory. 4096 is a good default, increase if conversations get cut off.</span></span></label><input type="number" id="s-llm-nctx" min="512" step="512"></div>
        <div class="form-row"><label>GPU Layers <span class="info-i">i<span class="tip">Number of model layers to offload to GPU. -1 = all layers on GPU (fastest). 0 = CPU only. Reduce if you run out of VRAM — each layer freed saves memory at the cost of speed.</span></span></label><input type="number" id="s-llm-ngpu" min="-1"></div>
      </div>
      <div class="form-row"><label>KV Cache Sessions <span class="info-i">i<span class="tip">Number of conversation contexts to keep cached in memory. Each session preserves the conversation state so follow-up requests are faster. Higher values use more RAM/VRAM.</span></span></label><input type="number" id="s-llm-kvs"></div>
      <div class="form-row"><label>KV Cache TTL (sec) <span class="info-i">i<span class="tip">Seconds before an idle cached session expires and is freed from memory. Default 300 (5 minutes). Set higher if conversations have long pauses between messages.</span></span></label><input type="number" id="s-llm-kvt"></div>
    </div>
  </div>
  <div>
    <!-- TTS Config -->
    <div class="glass">
      <h2>TTS Configuration</h2>
      <div class="form-row"><label>Voice Model <span class="info-i">i<span class="tip">Piper ONNX voice to use for speech synthesis. Place .onnx voice files in the voices directory to add more options. The default TARS voice is downloaded automatically.</span></span></label><select id="s-tts-voice"><option value="">Loading...</option></select></div>
      <div class="form-row"><label>Cache Size <span class="info-i">i<span class="tip">Number of generated audio clips to keep cached in memory. Cached responses are served instantly on repeat requests. Higher values use more RAM but improve response time for repeated phrases.</span></span></label><input type="number" id="s-tts-cache"></div>
    </div>
    <!-- Vision Config -->
    <div class="glass">
      <h2>Vision Configuration</h2>
      <div class="form-row"><label>Model <span class="info-i">i<span class="tip">HuggingFace model ID for image captioning. Supports BLIP, BLIP-2, Moondream, Florence-2, or any compatible vision model. Downloaded automatically on first use. Larger models give better descriptions but use more VRAM.</span></span></label><input type="text" id="s-vision-model"></div>
    </div>
    <!-- ImageGen Config -->
    <div class="glass">
      <h2>ImageGen Configuration</h2>
      <div class="form-row"><label>Diffusers Model <span class="info-i">i<span class="tip">HuggingFace model ID for image generation (e.g. 'stabilityai/stable-diffusion-xl-base-1.0'). Downloaded automatically on first use. Requires significant VRAM (4-8+ GB).</span></span></label><input type="text" id="s-imagegen-model"></div>
      <div class="form-row"><label>Default Steps <span class="info-i">i<span class="tip">Number of diffusion steps per image. More steps = higher quality but slower generation. 20-30 is typical for good results. Can be overridden per request via the API.</span></span></label><input type="number" id="s-imagegen-steps"></div>
      <div class="form-row"><label>Default CFG <span class="info-i">i<span class="tip">Classifier-free guidance scale. Higher values follow the text prompt more closely but can look artificial. Lower values are more creative but may drift from the prompt. 7-8 is a good default.</span></span></label><input type="number" id="s-imagegen-cfg" step="0.1"></div>
    </div>
    <!-- Embeddings Config -->
    <div class="glass">
      <h2>Embeddings Configuration</h2>
      <div class="form-row"><label>Model <span class="info-i">i<span class="tip">Sentence-transformers model for generating text embeddings. Used by TARS memory system for semantic search and similarity matching. The default 'all-MiniLM-L6-v2' is lightweight and fast. Changing this requires rebuilding memory databases.</span></span></label><input type="text" id="s-embeddings-model"></div>
    </div>
  </div>
</div>

<!-- Save -->
<div class="save-bar">
  <button class="hud-btn" onclick="saveSettings()">Save Settings</button>
  <span id="save-status" class="save-status"></span>
</div>

<div class="nav-links" style="margin-top:16px">
  <a href="/">Dashboard</a>
  <a href="/playground">Playground</a>
  <a href="/docs">API Docs</a>
  <a href="/logout" style="border-color:rgba(255,68,68,0.3);color:#ff6666">Logout</a>
</div>
</div>
<script>
// Load settings from API
async function loadSettings(){
  try{
    const r=await fetch('/api/settings');const d=await r.json();
    document.getElementById('s-apikey').value=d.server.api_key||'';
    document.getElementById('s-port').value=d.server.port||'5678';
    document.getElementById('svc-stt').checked=d.services.stt==='true';
    document.getElementById('svc-tts').checked=d.services.tts==='true';
    document.getElementById('svc-llm').checked=d.services.llm==='true';
    document.getElementById('svc-vision').checked=d.services.vision==='true';
    document.getElementById('svc-imagegen').checked=d.services.imagegen==='true';
    document.getElementById('svc-embeddings').checked=d.services.embeddings==='true';
    setSelect('dev-stt',d.stt.device||'auto');
    setSelect('dev-llm',d.llm.device||'auto');
    setSelect('dev-vision',d.vision.device||'auto');
    setSelect('dev-imagegen',d.imagegen.device||'auto');
    setSelect('dev-embeddings',d.embeddings.device||'auto');
    setSelect('s-stt-model',d.stt.whisper_model);
    setSelect('s-stt-compute',d.stt.compute_type);
    document.getElementById('s-stt-vad').checked=d.stt.vad_filter==='true';
    setSelect('s-llm-backend',d.llm.backend||'transformers');
    toggleLlmBackend();
    document.getElementById('s-llm-model').value=d.llm.model;
    setSelect('s-llm-dtype',d.llm.dtype);
    setSelect('s-llm-quantize',d.llm.quantize||'none');
    document.getElementById('s-llm-nctx').value=d.llm.n_ctx||4096;
    document.getElementById('s-llm-ngpu').value=d.llm.n_gpu_layers||-1;
    document.getElementById('s-llm-kvs').value=d.llm.kv_cache_sessions;
    document.getElementById('s-llm-kvt').value=d.llm.kv_cache_ttl;
    window._ttsVoicesDir=d.tts.voices_dir||'';
    document.getElementById('s-tts-cache').value=d.tts.cache_size;
    try{const vr=await fetch('/tts/voices');const vd=await vr.json();const sel=document.getElementById('s-tts-voice');sel.innerHTML='';(vd.voices||[]).forEach(v=>{const o=document.createElement('option');o.value=v;o.text=v;sel.add(o)});if(d.tts.default_voice)setSelect('s-tts-voice',d.tts.default_voice)}catch(e){document.getElementById('s-tts-voice').innerHTML='<option value="">TTS not loaded</option>'}
    document.getElementById('s-vision-model').value=d.vision.model;
    document.getElementById('s-imagegen-model').value=d.imagegen.model;
    document.getElementById('s-imagegen-steps').value=d.imagegen.default_steps;
    document.getElementById('s-imagegen-cfg').value=d.imagegen.default_cfg;
    document.getElementById('s-embeddings-model').value=d.embeddings.model;
    // Disable cuda options if no GPU
    if(!d._meta.has_cuda){
      document.querySelectorAll('select[id^="dev-"]').forEach(s=>{
        for(const o of s.options){if(o.value==='cuda')o.disabled=true}
      });
    }
  }catch(e){console.error('Failed to load settings',e)}
}
function setSelect(id,val){const s=document.getElementById(id);for(let i=0;i<s.options.length;i++){if(s.options[i].value===val){s.selectedIndex=i;return}}}
function toggleLlmBackend(){
  const isLlamaCpp=document.getElementById('s-llm-backend').value==='llamacpp';
  document.getElementById('llm-transformers-opts').style.display=isLlamaCpp?'none':'';
  document.getElementById('llm-llamacpp-opts').style.display=isLlamaCpp?'':'none';
  document.getElementById('s-llm-model-lbl').textContent=isLlamaCpp?'GGUF Path':'Model';
}

async function saveSettings(){
  const st=document.getElementById('save-status');
  st.textContent='Saving...';st.className='save-status';
  const body={
    server:{port:document.getElementById('s-port').value,api_key:document.getElementById('s-apikey').value},
    services:{stt:document.getElementById('svc-stt').checked?'true':'false',tts:document.getElementById('svc-tts').checked?'true':'false',llm:document.getElementById('svc-llm').checked?'true':'false',vision:document.getElementById('svc-vision').checked?'true':'false',imagegen:document.getElementById('svc-imagegen').checked?'true':'false',embeddings:document.getElementById('svc-embeddings').checked?'true':'false'},
    stt:{whisper_model:document.getElementById('s-stt-model').value,compute_type:document.getElementById('s-stt-compute').value,vad_filter:document.getElementById('s-stt-vad').checked?'true':'false',device:document.getElementById('dev-stt').value},
    llm:{model:document.getElementById('s-llm-model').value,backend:document.getElementById('s-llm-backend').value,dtype:document.getElementById('s-llm-dtype').value,quantize:document.getElementById('s-llm-quantize').value,n_ctx:document.getElementById('s-llm-nctx').value,n_gpu_layers:document.getElementById('s-llm-ngpu').value,kv_cache_sessions:document.getElementById('s-llm-kvs').value,kv_cache_ttl:document.getElementById('s-llm-kvt').value,device:document.getElementById('dev-llm').value},
    tts:{default_voice:document.getElementById('s-tts-voice').value,voices_dir:window._ttsVoicesDir||'',cache_size:document.getElementById('s-tts-cache').value},
    vision:{model:document.getElementById('s-vision-model').value,device:document.getElementById('dev-vision').value},
    imagegen:{model:document.getElementById('s-imagegen-model').value,default_steps:document.getElementById('s-imagegen-steps').value,default_cfg:document.getElementById('s-imagegen-cfg').value,device:document.getElementById('dev-imagegen').value},
    embeddings:{model:document.getElementById('s-embeddings-model').value,device:document.getElementById('dev-embeddings').value}
  };
  try{
    const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    st.textContent=d.message||'Saved!';st.className='save-status ok';
  }catch(e){st.textContent='Error: '+e;st.className='save-status err'}
}

loadSettings();
</script></body></html>"""


# ===================================================================
# CLI + Startup
# ===================================================================
BANNER = r"""
 ████████╗ █████╗ ██████╗ ███████╗
 ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
    ██║   ███████║██████╔╝███████╗
    ██║   ██╔══██║██╔══██╗╚════██║
    ██║   ██║  ██║██║  ██║███████║
    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
   [ TARS-AI SERVER MODULE  v2.0 ]
=====================================
"""

def parse_args():
    cfg = load_config()
    p = argparse.ArgumentParser(
        description="TARS-AI Companion Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", type=int, default=int(cfg["server"]["port"]))
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--services", nargs="+", choices=["stt", "tts", "llm", "vision", "imagegen", "embeddings"], default=None)
    p.add_argument("--no-stt", action="store_true", default=not cfg.getboolean("services", "stt"))
    p.add_argument("--no-tts", action="store_true", default=not cfg.getboolean("services", "tts"))
    p.add_argument("--no-llm", action="store_true", default=not cfg.getboolean("services", "llm"))
    p.add_argument("--no-vision", action="store_true", default=not cfg.getboolean("services", "vision"))
    p.add_argument("--no-imagegen", action="store_true", default=not cfg.getboolean("services", "imagegen"))
    p.add_argument("--no-embeddings", action="store_true", default=not cfg.getboolean("services", "embeddings"))
    p.add_argument("--whisper-model", default=cfg["stt"]["whisper_model"])
    p.add_argument("--whisper-compute", default=cfg["stt"]["compute_type"])
    p.add_argument("--voices-dir", default=cfg["tts"]["voices_dir"] or None)
    p.add_argument("--llm-model", default=cfg["llm"]["model"])
    p.add_argument("--llm-dtype", default=cfg["llm"]["dtype"], choices=["auto", "float16", "bfloat16", "float32"])
    p.add_argument("--vision-model", default=cfg["vision"]["model"])
    p.add_argument("--imagegen-model", default=cfg["imagegen"]["model"])
    p.add_argument("--embeddings-model", default=cfg["embeddings"]["model"])
    p.add_argument("--ssl-cert", default=None, help="Path to SSL certificate for HTTPS")
    p.add_argument("--ssl-key", default=None, help="Path to SSL private key for HTTPS")
    return p.parse_args()


def resolve_services(args) -> list[str]:
    if args.services:
        return args.services
    services = ["stt", "tts", "llm", "vision", "imagegen", "embeddings"]
    if args.no_stt: services.remove("stt")
    if args.no_tts: services.remove("tts")
    if args.no_llm: services.remove("llm")
    if args.no_vision: services.remove("vision")
    if args.no_imagegen: services.remove("imagegen")
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
    # Default: transformers (handles the widest range of HF models)
    return "transformers"


def _load_single_service(name: str, args):
    cfg = _active_config or load_config()
    if name == "stt":
        vad = cfg.getboolean("stt", "vad_filter", fallback=True)
        dev = resolve_service_device(cfg.get("stt", "device", fallback="auto"))
        SERVICES["stt"] = STTService(model_size=args.whisper_model, compute_type=args.whisper_compute,
                                     vad_filter=vad, device=dev)
    elif name == "tts":
        cache_size = cfg.getint("tts", "cache_size", fallback=100)
        SERVICES["tts"] = TTSService(voices_dir=args.voices_dir, cache_size=cache_size)
    elif name == "llm":
        kvs = cfg.getint("llm", "kv_cache_sessions", fallback=2)
        kvt = cfg.getint("llm", "kv_cache_ttl", fallback=300)
        dev = resolve_service_device(cfg.get("llm", "device", fallback="auto"))
        backend = cfg.get("llm", "backend", fallback="auto")
        n_ctx = cfg.getint("llm", "n_ctx", fallback=4096)
        n_gpu = cfg.getint("llm", "n_gpu_layers", fallback=-1)
        n_batch = cfg.getint("llm", "n_batch", fallback=2048)
        flash_attn = cfg.getboolean("llm", "flash_attn", fallback=True)

        if backend == "auto":
            backend = _detect_llm_backend(args.llm_model)
            log.info(f"LLM backend auto-detected: {backend}")

        if backend == "llamacpp":
            _ensure_llamacpp()
            SERVICES["llm"] = LlamaCppService(
                model_path=args.llm_model, n_ctx=n_ctx, n_gpu_layers=n_gpu,
                n_batch=n_batch, flash_attn=flash_attn,
                kv_cache_sessions=kvs, kv_cache_ttl=kvt)
        else:
            quant = cfg.get("llm", "quantize", fallback="none")
            SERVICES["llm"] = LLMService(model_name=args.llm_model, dtype=args.llm_dtype,
                                          quantize=quant, kv_cache_sessions=kvs, kv_cache_ttl=kvt, device=dev)
    elif name == "vision":
        dev = resolve_service_device(cfg.get("vision", "device", fallback="auto"))
        SERVICES["vision"] = VisionService(model_name=args.vision_model, device=dev)
    elif name == "imagegen":
        dev = resolve_service_device(cfg.get("imagegen", "device", fallback="auto"))
        SERVICES["imagegen"] = ImageGenService(model_name=args.imagegen_model, device=dev)
    elif name == "embeddings":
        dev = resolve_service_device(cfg.get("embeddings", "device", fallback="auto"))
        SERVICES["embeddings"] = EmbeddingsService(model_name=args.embeddings_model, device=dev)


_SERVICE_PACKAGES = {
    "stt":        ["faster-whisper>=1.0.0"],
    "tts":        ["piper-tts>=1.2.0"],
    "imagegen":   ["diffusers>=0.27.0"],
    "embeddings": ["sentence-transformers>=2.2.0"],
}

def _try_install_service_deps(name: str) -> bool:
    """Auto-install missing packages for a service. Returns True if something was installed."""
    import subprocess as _sp
    pkgs = _SERVICE_PACKAGES.get(name)
    if not pkgs:
        return False
    log.info(f"Installing missing packages for {name.upper()}: {', '.join(pkgs)}")
    rc = _sp.call([sys.executable, "-m", "pip", "install", "--quiet"] + pkgs)
    return rc == 0

def load_services(args):
    to_load = resolve_services(args)
    log.info(f"Services to load: {', '.join(s.upper() for s in to_load)}")
    for name in to_load:
        try:
            # Redirect stdout to suppress safetensors LOAD REPORT print() noise.
            # Our logs (stderr) and tqdm progress bars (stderr) are unaffected.
            with contextlib.redirect_stdout(io.StringIO()):
                _load_single_service(name, args)
        except (ImportError, ModuleNotFoundError):
            # Missing package — try to auto-install and retry once
            if _try_install_service_deps(name):
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        _load_single_service(name, args)
                    continue
                except Exception:
                    pass
            log.error(f"Failed to load {name.upper()}:\n{traceback.format_exc()}")
            log.warning(f"Continuing without {name.upper()}")
        except Exception:
            log.error(f"Failed to load {name.upper()}:\n{traceback.format_exc()}")
            log.warning(f"Continuing without {name.upper()}")
    if not SERVICES:
        log.error("No services loaded!")
        sys.exit(1)


# -- Graceful shutdown -------------------------------------------------

def _shutdown_handler(signum, frame):
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
        torch.cuda.empty_cache()
    log.info("Cleanup complete. Exiting.")
    sys.exit(0)


# ===================================================================
# Main
# ===================================================================
if __name__ == "__main__":
    try:
        print(BANNER)
    except UnicodeEncodeError:
        print("[ TARS-AI SERVER MODULE v2.0 ]")
        print("=" * 37)
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