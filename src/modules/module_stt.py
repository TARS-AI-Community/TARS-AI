#!/usr/bin/env python3
"""
module_stt.py

Speech-to-Text (STT) Module for TARS-AI Application.

Integrates local and cloud-based transcription, wake word detection,
voice command handling, and barge-in detection during TTS playback.
"""

import os
import re
import random
import threading
import time
from collections import deque
import wave
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, Future
from difflib import SequenceMatcher
from io import BytesIO
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import requests

from modules.module_mic import ResamplingInputStream, get_native_rate

from modules.module_messageQue import queue_message
from modules.module_config import load_config, get_capabilities
from modules.module_tts import is_tts_playing
from modules.module_state import set_tars_state, get_tars_state, TarsState

CONFIG = load_config()
CAPABILITIES = get_capabilities()

# --- Conditional heavy imports based on device capabilities ---
torch = None
librosa = None
get_stt_model = None
OpenAI = None
WakeWordSystem = None
sherpa_onnx = None

# Torch and related (requires can_use_embeddings — Pi5 only)
if CAPABILITIES is None or CAPABILITIES.can_use_embeddings:
    try:
        import torch as _torch
        torch = _torch
    except ImportError:
        pass
    try:
        import librosa as _librosa
        librosa = _librosa
    except ImportError:
        pass

# FastRTC (Pi5 only)
if CAPABILITIES is None or (CAPABILITIES.allowed_stt and "fastrtc" in CAPABILITIES.allowed_stt):
    try:
        from fastrtc import get_stt_model as _get_stt_model
        get_stt_model = _get_stt_model
    except ImportError:
        pass

# OpenAI (all devices for cloud STT)
try:
    from openai import OpenAI as _OpenAI
    OpenAI = _OpenAI
except ImportError:
    pass

# Atomik wake word (Pi5, Pi4, Pi3)
if CAPABILITIES is None or (CAPABILITIES.allowed_wake and "atomik" in CAPABILITIES.allowed_wake):
    try:
        from modules.module_atomik import WakeWordSystem as _WakeWordSystem
        WakeWordSystem = _WakeWordSystem
    except ImportError:
        pass

# Sherpa-ONNX (Pi5, Pi4)
if CAPABILITIES is None or (CAPABILITIES.allowed_stt and "sherpa-onnx" in CAPABILITIES.allowed_stt):
    try:
        import sherpa_onnx as _sherpa_onnx
        sherpa_onnx = _sherpa_onnx
    except ImportError:
        pass

# Pre-compiled regex for stripping SenseVoice tags (language: <|en|>, emotion: <|HAPPY|>, event: <|Speech|>, etc.)
_SENSEVOICE_TAG_RE = re.compile(r'<\|[A-Za-z]+\|>')
_NON_ALNUM_RE = re.compile(r'[^\w]')
_NON_ALNUM_SPACE_RE = re.compile(r'[^a-zA-Z0-9\s]')

# Suppress parallelism warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Noise artifacts commonly produced by STT models for non-speech audio
_NOISE_ARTIFACTS = frozenset({
    'uh', 'um', 'hm', 'hmm', 'mm', 'mhm', 'ah', 'oh', 'eh',
    'huh', 'ha', 'sh', 'shh', 'ss', 'tt', 'ts',
})

# Common filler/noise words for barge-in filtering
_BARGEIN_NOISE_WORDS = frozenset({
    '', 'a', 'i', 'uh', 'um', 'ah', 'oh', 'hm', 'hmm', 'mm',
    'the', 'is', 'it', 'to', 'and', 'of', 'in', 'that', 'thats',
    'an', 'or', 'so', 'do', 'no', 'my', 'me', 'we', 'he', 'she',
    'be', 'at', 'by', 'if', 'up', 'as', 'on', 'you', 'not', 'but',
    'can', 'got', 'has', 'had', 'was', 'are', 'for', 'too', 'its',
    'all', 'his', 'her', 'him', 'our', 'who', 'how', 'did', 'get',
    'let', 'may', 'new', 'now', 'old', 'one', 'out', 'own', 'say',
    'set', 'try', 'two', 'way', 'yet', 'any', 'few', 'per', 'put',
})

# Global STT manager instance
_stt_manager_instance = None

def get_stt_manager():
    global _stt_manager_instance
    return _stt_manager_instance


def _stt_dir():
    """Return the path to the stt models directory (src/stt/)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt")


class STTManager:
    """Manages Speech-to-Text processing for TARS-AI."""

    MODEL_RATE = 16000  # Sample rate required by all ML models (VAD, STT, speaker ID)

    WAKE_WORD_RESPONSES = [
        "Oh! You called?",
        "Took you long enough. Yes?",
        "Finally!",
    ]

    try:
        _resp = CONFIG["CHAR"]['responses']
        if _resp and _resp.strip() and _resp.strip() != '[]':
            _parsed = json.loads(_resp)
            if isinstance(_parsed, list) and _parsed:
                WAKE_WORD_RESPONSES = _parsed
    except Exception:
        pass

    def __init__(self, config, shutdown_event: threading.Event, ui_manager):
        global _stt_manager_instance
        _stt_manager_instance = self

        self.ui_manager = ui_manager
        self.config = config
        self.shutdown_event = shutdown_event
        self.running = False

        # Pause/resume functionality for video playback
        self.paused = False
        self.cancelled = False
        self.pause_lock = threading.Lock()

        # Audio settings — always open mic at its native rate, resample to MODEL_RATE
        self.DEFAULT_SAMPLE_RATE = 16000
        self.DEVICE_SAMPLE_RATE = get_native_rate()
        self.SAMPLE_RATE = self.DEVICE_SAMPLE_RATE  # backward compat alias
        if self.DEVICE_SAMPLE_RATE != self.MODEL_RATE:
            queue_message(f"INFO: Mic native rate {self.DEVICE_SAMPLE_RATE} Hz — will resample to {self.MODEL_RATE} Hz")

        self.amp_gain = CONFIG['STT'].get('mic_amp_gain', 10.0)
        self.silence_margin = CONFIG['STT'].get('silence_margin', 3.0)
        self.wake_silence_threshold = None
        self.silence_threshold = None  # Updated after measuring background noise
        self.silence_threshold_margin = None
        self.MAX_RECORDING_FRAMES = 100   # ~12.5 seconds
        self.MAX_SILENT_FRAMES = CONFIG['STT']['speechdelay']

        # Callbacks
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.post_utterance_callback: Optional[Callable[[], None]] = None
        self.preemptive_llm_callback: Optional[Callable[[str], object]] = None  # fires LLM early

        # Wake word and model settings
        self.WAKE_WORD = config.get("STT", {}).get("wake_word", "hey tar").lower()

        # Models (loaded lazily based on config)
        self.fastrtc_model = None
        self.silero_model = None
        self.silero_vad_model = None
        self.get_speech_timestamps = None
        self.sherpa_recognizer = None
        self.sherpa_vad = None
        self.sherpa_denoiser = None
        self.sherpa_punctuator = None
        # Smart Turn semantic turn detection
        self.smart_turn_session = None
        self.smart_turn_extractor = None
        self.smart_turn_audio_buffer = deque(maxlen=32)
        self._smart_turn_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SmartTurn")
        self._smart_turn_future = None  # pending inference Future
        self._smart_turn_last_buf_len = 0  # buffer size at last inference submission

        # Barge-in monitoring
        self._bargein_active = False
        self._bargein_thread = None
        self._bargein_tts_data = {'word_list': [], 'words_all': set()}  # shared with monitor thread
        # Barge-in audio capture (full-duplex) — raw chunks fed as pre-roll into normal pipeline
        self._bargein_audio_chunks = None
        self._bargein_ready = threading.Event()
        self._bargein_enabled = CONFIG['STT'].get('enable_bargein', True)
        if isinstance(self._bargein_enabled, str):
            self._bargein_enabled = self._bargein_enabled.lower() in ('true', '1', 'yes')
        self._bargein_mode = CONFIG['STT'].get('bargein_mode', 'fuzzy')
        sensitivity = max(1, min(10, int(CONFIG['STT'].get('bargein_sensitivity', 5))))
        t = (sensitivity - 1) / 9.0  # 0.0 (sens=1, hard to interrupt) to 1.0 (sens=10, easy)
        # RMS gate: higher sensitivity = lower multiplier on silence_threshold
        # sens=1: 1.0x (same as normal), sens=10: 0.4x (very sensitive)
        self._bargein_rms_scale = 1.0 - t * 0.6
        # Fuzzy mode: higher sensitivity = lower threshold = fewer words matched as echo
        self._bargein_broad_threshold = 0.80 - t * 0.10   # 0.80 (sens=1) to 0.70 (sens=10)
        self._bargein_min_novel = 3 if sensitivity <= 3 else 2
        # Voiceprint mode: higher sensitivity = lower confidence required to match
        # Bleed scores 0.50-0.65, mixed voice+bleed scores 0.58-0.82
        self._bargein_voiceprint_threshold = 0.90 - t * 0.25  # 0.90 (sens=1) to 0.65 (sens=10)

        # Last recorded audio for speaker ID (set by transcription backends)
        self._last_audio_float32 = None

        # Cache progress bar, webui port, and character name so they aren't recreated per frame
        self._progress_bar_funcs = None
        self._webui_port = CONFIG['ACCESS'].get('webui_port', 80)
        self._character_name = self._resolve_character_name()

        self.DEBUG = False
        self._initialize_models()
        self.vadmethod = CONFIG['STT']['vad_method']

    # === Initialization ===

    def _resolve_character_name(self):
        char_path = self.config.get("CHAR", {}).get("character_card_path")
        return os.path.splitext(os.path.basename(char_path))[0] if char_path else "TARS"

    def _initialize_models(self):
        """Measure background noise and load the selected STT model."""
        self._measure_background_noise()
        stt_proc = self.config.get("STT", {}).get("stt_processor", "fastrtc")

        loaders = {
            "fastrtc": self._load_fastrtc_model,
            "silero": self._load_silero_model,
            "sherpa-onnx": self._load_sherpa_onnx_model,
        }
        if stt_proc in loaders:
            loaders[stt_proc]()

        # Wake word processor initialization
        wake_proc = self.config["STT"].get("wake_word_processor", "atomik")
        if wake_proc == "fastrtc" and not self.fastrtc_model:
            self._load_fastrtc_model()
        elif wake_proc == "atomik":
            self._load_atomik_model()
        elif wake_proc == "sherpa-onnx" and not self.sherpa_recognizer:
            self._load_sherpa_onnx_model()

        if self.config["STT"].get("vad_enabled", False):
            self._load_silero_vad()

        # Load VAD model if needed
        vad_method = CONFIG['STT'].get('vad_method', 'rms')
        if vad_method == "sherpa-onnx":
            self._load_sherpa_vad()
        elif vad_method == "smart-turn":
            self._load_smart_turn()

        # Load optional sherpa-onnx denoiser
        if self.config["STT"].get("sherpa_onnx_denoise", "False").lower() == "true":
            self._load_sherpa_denoiser()
        # Load optional sherpa-onnx punctuation
        if self.config["STT"].get("sherpa_onnx_punctuation", "False").lower() == "true":
            self._load_sherpa_punctuation()

    # === Start/Stop/Pause ===

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._stt_processing_loop, name="STTThread", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.shutdown_event.set()
        self.thread.join(timeout=3)
        self._smart_turn_executor.shutdown(wait=False)

    def pause(self):
        with self.pause_lock:
            self.paused = True

    def cancel(self):
        with self.pause_lock:
            self.paused = True
            self.cancelled = True

    def resume(self):
        with self.pause_lock:
            self.paused = False

    def is_paused(self):
        with self.pause_lock:
            return self.paused

    def is_cancelled(self):
        with self.pause_lock:
            was = self.cancelled
            self.cancelled = False
            return was

    # === Model Loading ===

    def _load_atomik_model(self):
        if WakeWordSystem is None:
            queue_message("WARNING: Atomik wake word not available")
            return
        atomik_mode = CONFIG['STT'].get('atomik_mode', 'auto').strip().lower()
        mode = None if atomik_mode == 'auto' else atomik_mode
        WakeWordSystem(self.WAKE_WORD, mode=mode).createModel()

    def _load_silero_model(self):
        """Load Silero STT model via Torch Hub into the stt folder."""
        global torch
        if torch is None:
            queue_message("WARNING: Silero STT not available (torch not installed)")
            return
        try:
            # Go one level up from the current directory
            stt_folder = _stt_dir()
            os.makedirs(stt_folder, exist_ok=True)
            # Override torch.hub.get_dir to return stt_folder directly
            torch.hub.get_dir = lambda: stt_folder

            self.silero_model, self.decoder, self.utils = torch.hub.load(
                "snakers4/silero-models", model="silero_stt", language="en", device="cpu"
            )
            self.read_batch, self.split_into_batches, self.read_audio, self.prepare_model_input = self.utils
            queue_message("INFO: Silero model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load Silero model: {e}")

    def _load_silero_vad(self):
        """Load the Silero VAD model using the pip package."""
        if torch is None:
            queue_message("WARNING: Silero VAD not available (torch not installed)")
            return
        try:
            from silero_vad import load_silero_vad, get_speech_timestamps
            self.silero_vad_model = load_silero_vad(onnx=False)
            self.get_speech_timestamps = get_speech_timestamps
            queue_message("INFO: Silero VAD loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load Silero VAD: {e}")

    def _load_fastrtc_model(self):
        if get_stt_model is None:
            queue_message("WARNING: FastRTC not available (not installed)")
            self.fastrtc_model = None
            return
        try:
            self.fastrtc_model = get_stt_model()
            queue_message("INFO: FastRTC STT model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load FastRTC STT model: {e}")
            self.fastrtc_model = None

    def _load_sherpa_onnx_model(self):
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available (not installed)")
            return
        try:
            model_path = os.path.join(_stt_dir(), "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17")
            model_file = os.path.join(model_path, "model.int8.onnx")
            tokens_file = os.path.join(model_path, "tokens.txt")

            if not os.path.exists(model_file):
                queue_message(f"ERROR: SenseVoiceTiny model not found at {model_file}")
                return

            # Use more threads on Pi5 (4 cores) vs Pi4 (4 cores but less headroom)
            pi_version = self.config.get("_device", {}).get("raspberry_version", "pi5")
            threads = 4 if pi_version == "pi5" else 2

            self.sherpa_recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_file, tokens=tokens_file, num_threads=threads, use_itn=True, debug=False,
            )
            queue_message("INFO: sherpa-onnx SenseVoiceTiny model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx model: {e}")
            self.sherpa_recognizer = None

    def _load_sherpa_vad(self):
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for VAD")
            return
        try:
            model_path = os.path.join(_stt_dir(), "silero_vad.onnx")
            if not os.path.exists(model_path):
                queue_message(f"ERROR: Silero VAD ONNX model not found at {model_path}")
                return

            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = model_path
            vad_config.silero_vad.threshold = 0.3
            vad_config.silero_vad.min_speech_duration = 0.1
            vad_config.silero_vad.min_silence_duration = 0.3
            vad_config.sample_rate = 16000

            self.sherpa_vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)
            queue_message("INFO: sherpa-onnx Silero VAD loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx VAD: {e}")
            self.sherpa_vad = None

    def _load_sherpa_denoiser(self):
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for denoising")
            return
        try:
            model_path = os.path.join(_stt_dir(), "gtcrn_simple.onnx")
            if not os.path.exists(model_path):
                queue_message(f"ERROR: Denoiser model not found at {model_path}")
                return

            gtcrn = sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=model_path)
            model_cfg = sherpa_onnx.OfflineSpeechDenoiserModelConfig(gtcrn=gtcrn)
            self.sherpa_denoiser = sherpa_onnx.OfflineSpeechDenoiser(
                config=sherpa_onnx.OfflineSpeechDenoiserConfig(model=model_cfg)
            )
            queue_message("INFO: sherpa-onnx speech denoiser loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx denoiser: {e}")
            self.sherpa_denoiser = None

    def _load_sherpa_punctuation(self):
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for punctuation")
            return
        try:
            model_dir = os.path.join(
                _stt_dir(), "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12"
            )
            if not os.path.isdir(model_dir):
                queue_message(f"ERROR: Punctuation model not found at {model_dir}")
                return

            model_cfg = sherpa_onnx.OfflinePunctuationModelConfig(
                ct_transformer=os.path.join(model_dir, "model.onnx")
            )
            self.sherpa_punctuator = sherpa_onnx.OfflinePunctuation(
                sherpa_onnx.OfflinePunctuationConfig(model=model_cfg)
            )
            queue_message("INFO: sherpa-onnx punctuation model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx punctuation: {e}")
            self.sherpa_punctuator = None

    def _load_smart_turn(self):
        """Load Pipecat Smart Turn v3.2 ONNX model for semantic turn detection."""
        try:
            import onnxruntime as ort
            from transformers import WhisperFeatureExtractor

            model_path = os.path.join(_stt_dir(), "smart-turn-v3.2-cpu.onnx")
            if not os.path.isfile(model_path):
                queue_message(f"ERROR: Smart Turn model not found at {model_path}")
                return

            so = ort.SessionOptions()
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            so.inter_op_num_threads = 1
            so.intra_op_num_threads = 1

            self.smart_turn_session = ort.InferenceSession(model_path, sess_options=so)
            self.smart_turn_extractor = WhisperFeatureExtractor(chunk_length=8)
            # Pre-warm: run dummy inference to eliminate first-utterance latency spike
            dummy = np.zeros(16000, dtype=np.float32)  # 1s silence
            self._smart_turn_infer(dummy)
            queue_message("INFO: Smart Turn v3.2 model loaded and pre-warmed.")
        except ImportError as e:
            queue_message(f"ERROR: Smart Turn requires onnxruntime and transformers: {e}")
            self.smart_turn_session = None
            self.smart_turn_extractor = None
        except Exception as e:
            queue_message(f"ERROR: Failed to load Smart Turn model: {e}")
            self.smart_turn_session = None
            self.smart_turn_extractor = None

    # === Audio Helpers ===

    def _denoise_audio(self, audio_data, sample_rate=16000):
        if self.sherpa_denoiser is None:
            return audio_data
        try:
            result = self.sherpa_denoiser.run(audio_data.tolist(), sample_rate)
            return np.array(result.samples, dtype=np.float32)
        except Exception as e:
            queue_message(f"WARNING: Denoising failed: {e}")
            return audio_data

    def _add_punctuation(self, text):
        if self.sherpa_punctuator is None or not text:
            return text
        try:
            return self.sherpa_punctuator.add_punctuation(text)
        except Exception as e:
            queue_message(f"WARNING: Punctuation restoration failed: {e}")
            return text

    @staticmethod
    def _compute_rms(data):
        """Fast RMS computation for int16 audio data. Returns float or None."""
        if data.size == 0:
            return None
        flat = data.reshape(-1).astype(np.float64)
        if np.all(flat == 0):
            return None
        return np.sqrt(np.mean(np.square(flat)))

    def amplify_audio(self, data: np.ndarray) -> np.ndarray:
        return np.clip(data * self.amp_gain, -32768, 32767).astype(np.int16)

    def _compute_rms_fast(self, data):
        """Compute RMS with amplification in one pass — no int16 round-trip."""
        if data.size == 0:
            return None
        flat = data.reshape(-1).astype(np.float64) * self.amp_gain
        if np.all(flat == 0):
            return None
        return np.sqrt(np.mean(np.square(flat)))

    def play_wav(self, filename):
        try:
            from modules.module_tts import _resolve_output_device, _output_device
            _resolve_output_device()
            data, sr = sf.read(filename)
            sd.play(data * 0.5, samplerate=sr, device=_output_device)
            sd.wait()
        except Exception as e:
            queue_message(f"ERROR: Playing sound file failed: {e}")

    def _is_quiet(self, data):
        """Quick RMS silence gate check. Returns True if below threshold."""
        rms = self._compute_rms_fast(data)
        if rms is None:
            return True
        threshold = self.silence_threshold_margin or self.silence_threshold
        return threshold is not None and rms <= threshold

    # === Shared Recording ===

    def _record_audio_chunks(self, use_pre_roll=True, min_speech_frames=5,
                             pre_roll_frames=10, vad_method=None):
        """Record audio until end-of-speech detected.

        Returns (audio_chunks, speech_frames) where audio_chunks is a list of
        int16 numpy arrays, or (None, 0) if no speech detected.
        """
        detected_speech = False
        silent_frames = 0
        speech_frames = 0
        pre_roll_buffer = []
        pre_roll_added = 0
        audio_chunks = []
        max_silent = self.MAX_SILENT_FRAMES

        # Select VAD method — resolve once, not per frame
        if vad_method is None:
            vad_method = self.vadmethod
        vad_dispatch = {
            "silero": self._is_silence_detected_silero,
            "sherpa-onnx": self._is_silence_detected_sherpa_onnx,
            "smart-turn": self._is_silence_detected_smart_turn if self.smart_turn_session is not None else self._is_silence_detected_rms,
        }
        vad_func = vad_dispatch.get(vad_method, self._is_silence_detected_rms)

        # Reset Smart Turn state to prevent stale inference from previous round
        self.smart_turn_audio_buffer.clear()
        self._smart_turn_future = None

        with ResamplingInputStream(dtype="int16") as mic:
            # Flush stale mic audio that may contain the robot's own TTS voice.
            try:
                from modules.module_tts import needs_mic_flush, clear_mic_flush
                if needs_mic_flush():
                    if not self._bargein_ready.is_set():
                        queue_message("DEBUG: Flushing mic audio after TTS playback")
                        mic.flush()
                        clear_mic_flush()
                    else:
                        clear_mic_flush()
            except Exception:
                pass

            # Inject barge-in audio as pre-seeded speech chunks
            if self._bargein_ready.is_set():
                bargein_chunks = self._bargein_audio_chunks or []
                self._bargein_audio_chunks = None
                self._bargein_ready.clear()
                if bargein_chunks:
                    audio_chunks.extend(bargein_chunks)
                    speech_frames = len(bargein_chunks)
                    detected_speech = True
                    queue_message(f"DEBUG: Injected {len(bargein_chunks)} barge-in chunks as pre-roll ({use_pre_roll=})")

            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = mic.read(4000)

                # Abort recording if TTS just started — don't pick up TARS's own voice
                if is_tts_playing():
                    set_tars_state(TarsState.STANDBY)
                    return None, 0

                is_silence, detected_speech, silent_frames = vad_func(data, detected_speech, silent_frames)

                # Pre-speech timeout: if no speech detected and silence exceeds threshold, exit early
                if not detected_speech and silent_frames >= max_silent:
                    _, clear_bar = self._get_progress_bar()
                    clear_bar()
                    return None, 0

                # Post-speech: VAD signaled end of turn
                if is_silence and detected_speech and speech_frames >= min_speech_frames:
                    _, clear_bar = self._get_progress_bar()
                    clear_bar()
                    break

                # Smart Turn early exit — buffer is empty when inference signaled turn-complete
                active_vad = vad_method or self.vadmethod
                if (is_silence and active_vad == "smart-turn" and speech_frames >= min_speech_frames
                        and silent_frames >= 3 and not self.smart_turn_audio_buffer):
                    queue_message("INFO: Smart Turn detected end of turn")
                    break

                if not detected_speech:
                    if use_pre_roll:
                        pre_roll_buffer.append(data)
                        if len(pre_roll_buffer) > pre_roll_frames:
                            pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0 and pre_roll_buffer:
                        pre_roll_added = len(pre_roll_buffer)
                        audio_chunks.extend(pre_roll_buffer)
                        pre_roll_buffer = []
                    audio_chunks.append(data)
                    if not is_silence:
                        speech_frames += 1
            else:
                # Loop completed without break
                if speech_frames < min_speech_frames:
                    return None, 0

        if speech_frames < min_speech_frames or not audio_chunks:
            return None, 0
        # Stash float32 audio for speaker ID — exclude pre-roll chunks which
        # may contain TARS's own TTS response (using the user's voice model),
        # contaminating the speaker embedding with the wrong voice.
        speech_only = audio_chunks[pre_roll_added:] if pre_roll_added else audio_chunks
        self._last_audio_float32 = self._chunks_to_float32(speech_only) if speech_only else self._chunks_to_float32(audio_chunks)
        return audio_chunks, speech_frames

    def _chunks_to_wav_buffer(self, chunks, sample_rate):
        """Convert list of int16 numpy chunks to a WAV BytesIO buffer."""
        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for chunk in chunks:
                wf.writeframes(chunk.tobytes())
        buf.seek(0)
        return buf

    def _chunks_to_float32(self, chunks):
        """Convert list of int16 numpy chunks to a single float32 array."""
        return np.concatenate(chunks).astype(np.float32).flatten() / 32768.0

    # === Result Emission ===

    def _emit_result(self, text, extra=None):
        """Build formatted result dict, fire utterance callback, return result.

        Submits audio for speaker identification BEFORE firing the utterance
        callback, so the background observer can process the embedding while
        the LLM/TTS pipeline runs.  This ensures the ROUND log at the end of
        utterance_callback can wait on the speaker ID result instead of reading
        stale state from the previous round.
        """
        if not self._is_meaningful_text(text):
            queue_message(f"INFO: STT filtered non-speech noise: '{text}'")
            return None

        # Submit audio for speaker ID before the utterance callback blocks
        if self._last_audio_float32 is not None:
            try:
                from modules.module_speaker_id import get_speaker_id_manager
                sid = get_speaker_id_manager()
                if sid is not None:
                    sid.submit_audio(self._last_audio_float32, 16000)
            except Exception:
                pass

        result = {"text": text}
        if extra:
            result.update(extra)
        if self.utterance_callback:
            self.utterance_callback(json.dumps(result))
        return result

    @staticmethod
    def _is_meaningful_text(text: str) -> bool:
        """Check if transcribed text contains actual words, not just noise artifacts."""
        if not text:
            return False
        # Strip punctuation/symbols to get only alphanumeric characters
        cleaned = _NON_ALNUM_RE.sub('', text)
        # Require at least 2 meaningful characters
        if len(cleaned) < 2:
            return False
        # Check against known noise transcription artifacts
        if cleaned.lower() in _NOISE_ARTIFACTS:
            return False
        return True

    # === Main Processing Loop ===

    _last_status_was_sleeping = False

    def _stt_processing_loop(self):
        queue_message("INFO: Starting STT processing loop...")
        while self.running and not self.shutdown_event.is_set():
            # Skip processing if paused (e.g., during video playback)
            if self.is_paused():
                time.sleep(0.1)
                continue
            if self._detect_wake_word():
                if self.DEBUG:
                    queue_message("DEBUG: Wake word detected, starting transcription")
                STTManager._last_status_was_sleeping = False
                # Reset sherpa VAD state to prevent heap corruption from stale native buffers
                if self.sherpa_vad is not None:
                    self.sherpa_vad.reset()
                # Check again if paused before transcribing
                if not self.is_paused():
                    self._transcribe_utterance()
        queue_message("INFO: STT Manager stopped.")

    # === Transcription Dispatch ===

    def _transcribe_utterance(self):
        """Transcribe the user's utterance using the selected STT processor."""
        try:
            if self.is_paused():
                return None

            processors = {
                "fastrtc": self._transcribe_with_fastrtc,
                "silero": self._transcribe_silero,
                "external": self._transcribe_with_server,
                "openai": self._transcribe_with_openai,
                "sherpa-onnx": self._transcribe_with_sherpa_onnx,
            }
            processor = self.config["STT"].get("stt_processor", "fastrtc")
            transcribe_fn = processors.get(processor)
            if transcribe_fn is None:
                queue_message(f"WARNING: Unknown STT processor '{processor}', falling back to FastRTC")
                transcribe_fn = self._transcribe_with_fastrtc

            import modules.module_speed as speed
            speed.start('stt')
            result = transcribe_fn()
            stt_dur = speed.stop('stt')

            # Speaker ID submission now happens inside _emit_result() so it
            # runs BEFORE utterance_callback blocks for the full LLM/TTS pipeline.

            if result:
                speed.log(f"stt:{processor}({speed.fmt(stt_dur)})")
                speed.start('stt_to_llm')  # Measure gap from STT done to LLM start

            if self.post_utterance_callback and result:
                self.post_utterance_callback()
            return result
        except Exception as e:
            queue_message(f"ERROR: Transcription failed: {e}")
            return None

    # === Wake Word Gates ===

    def _build_wake_gates(self):
        """Build speaker + presence gate dependencies. Used by all wake word engines.
        Returns (speaker_id_mgr, speaker_mode, speaker_threshold, presence_mode, identity_mgr).
        """
        stt_cfg = CONFIG.get('STT', {})
        speaker_id_mgr = None
        speaker_mode = 'any'
        speaker_threshold = float(stt_cfg.get('speaker_id_threshold', '0.75'))
        presence_mode = 'off'
        identity_mgr = None

        raw_speaker = stt_cfg.get('vad_speaker_verify', 'off').strip().lower()
        if raw_speaker != 'off':
            try:
                from modules.module_speaker_id import get_speaker_id_manager
                speaker_id_mgr = get_speaker_id_manager()
                speaker_mode = raw_speaker
            except Exception:
                pass

        raw_presence = stt_cfg.get('vad_presence_gate', 'off').strip().lower()
        if raw_presence in ('any', 'known'):
            try:
                from modules.module_identity import get_identity_manager
                identity_mgr = get_identity_manager()
                if identity_mgr is not None:
                    presence_mode = raw_presence
                    identity_mgr.enable_background_detection()
            except Exception:
                pass

        return speaker_id_mgr, speaker_mode, speaker_threshold, presence_mode, identity_mgr

    def _run_wake_gates(self, audio_float32: np.ndarray, transcript_verify_fn=None) -> bool:
        """Run post-detection gates synchronously after wake word is detected.
        Returns True if all enabled gates pass (or have no applicable speakers/faces enrolled).
        transcript_verify_fn: optional callable(audio, rate)->str for transcript verification gate.
        """
        speaker_id_mgr, speaker_mode, speaker_threshold, presence_mode, identity_mgr = \
            self._build_wake_gates()

        # Speaker gate
        if speaker_id_mgr is not None:
            try:
                enrolled = speaker_id_mgr.get_enrolled_speakers()
                named = [s for s in enrolled if not s.startswith('Unknown_')]
                target = None if speaker_mode == 'any' else speaker_mode.lower()
                applicable = named if target is None else [s for s in named if s.lower() == target]
                if applicable and len(audio_float32) >= int(self.MODEL_RATE * 0.5):
                    emb = speaker_id_mgr.extract_embedding(audio_float32, self.MODEL_RATE)
                    if emb is not None:
                        best_name, best_score = speaker_id_mgr.identify_speaker(emb, skip_margin=True)
                        if best_name and best_name.startswith('Unknown_'):
                            best_name = ''
                        passed = (best_name and best_score >= speaker_threshold and
                                  (target is None or best_name.lower() == target))
                        if not passed:
                            if self.DEBUG:
                                queue_message(f"DEBUG: Wake gate REJECT speaker: '{best_name}' score={best_score:.3f}")
                            return False
            except Exception:
                pass

        # Presence gate
        if presence_mode != 'off' and identity_mgr is not None:
            try:
                faces = identity_mgr.get_recognized_faces()
                if not faces:
                    if self.DEBUG:
                        queue_message("DEBUG: Wake gate REJECT presence: no faces detected")
                    return False
                if presence_mode == 'known':
                    known = [f for f in faces if f.get('name', 'UNKNOWN') != 'UNKNOWN']
                    if not known:
                        if self.DEBUG:
                            queue_message("DEBUG: Wake gate REJECT presence: no known faces")
                        return False
            except Exception:
                pass

        # Transcript verify gate
        if transcript_verify_fn is not None and audio_float32 is not None and len(audio_float32) > 0:
            try:
                text = transcript_verify_fn(audio_float32, self.MODEL_RATE)
                if text:
                    words = _NON_ALNUM_SPACE_RE.sub('', text.lower()).split()
                    wake_words = _NON_ALNUM_RE.sub('', self.WAKE_WORD.lower()).split()
                    joined = ' '.join(words)
                    # Accept if any wake word token appears or fuzzy match passes
                    exact = any(w in words for w in wake_words)
                    fuzzy = self._fuzzy_wake_word_match(joined, self.WAKE_WORD)
                    if not exact and not fuzzy:
                        queue_message(f"INFO: Wake gate REJECT transcript: '{text}'")
                        return False
                    queue_message(f"INFO: Wake gate PASS transcript: '{text}'")
            except Exception:
                pass

        return True

    # === Transcription Backends ===

    def _build_transcript_verify_fn(self):
        """Return a callable(audio_float32, sample_rate) -> str|None for wake word gate verification.

        Uses the primary STT processor if it supports direct audio input (sherpa-onnx, fastrtc).
        Remote processors (openai, external) fall back to whichever local model is loaded.
        Returns None if no suitable model is available (gate will be skipped).
        """
        stt_proc = self.config.get('STT', {}).get('stt_processor', '')

        # Pick the best model: prefer primary when it's a local processor, else take whatever is loaded
        if stt_proc == 'sherpa-onnx':
            recognizer, fastrtc = self.sherpa_recognizer, None
        elif stt_proc == 'fastrtc':
            recognizer, fastrtc = None, self.fastrtc_model
        else:
            recognizer, fastrtc = self.sherpa_recognizer, self.fastrtc_model

        if recognizer is not None:
            def _fn(audio_float32, sample_rate):
                try:
                    s = recognizer.create_stream()
                    s.accept_waveform(sample_rate, audio_float32)
                    recognizer.decode_stream(s)
                    text = _SENSEVOICE_TAG_RE.sub('', s.result.text).strip()
                    del s
                    return text or None
                except Exception:
                    return None
            return _fn

        if fastrtc is not None:
            def _fn(audio_float32, sample_rate):
                try:
                    return fastrtc.stt((sample_rate, audio_float32)).strip() or None
                except Exception:
                    return None
            return _fn

        queue_message(
            f"WARN: Atomik transcript verify enabled but no local STT model is loaded "
            f"(stt_processor={stt_proc}). Gate will be skipped. "
            "Use sherpa-onnx or fastrtc as your STT processor to enable transcript verification."
        )
        return None

    def _transcribe_with_fastrtc(self):
        """Transcribe audio using FastRTC STT."""
        RATE = 16000  # FastRTC/Moonshine expects 16 kHz audio
        chunks, speech_frames = self._record_audio_chunks()
        if chunks is None:
            return None

        wav_buf = self._chunks_to_wav_buffer(chunks, RATE)
        audio_data, sr = sf.read(wav_buf, dtype="float32")

        # Resample to 16 kHz if needed (safety net)
        if sr != RATE and librosa is not None:
            audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=RATE)

        audio_max = np.abs(audio_data).max()
        if audio_max < 0.1:
            audio_data = audio_data * (0.3 / max(audio_max, 0.001))
        audio_data = np.clip(audio_data, -1.0, 1.0)

        transcript = self.fastrtc_model.stt((RATE, audio_data)).strip()
        return self._emit_result(transcript) if transcript else None

    def _transcribe_silero(self):
        """Transcribe audio using Silero STT."""
        chunks, _ = self._record_audio_chunks()
        if chunks is None:
            return None

        wav_buf = self._chunks_to_wav_buffer(chunks, self.MODEL_RATE)
        audio_data, sr = sf.read(wav_buf, dtype="float32")
        if sr != self.DEFAULT_SAMPLE_RATE and librosa is not None:
            audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=self.DEFAULT_SAMPLE_RATE)

        input_audio = self.prepare_model_input([torch.tensor(audio_data)], device="cpu")
        silero_output = self.silero_model(input_audio)[0]
        decoded_text = self.decoder(silero_output.cpu())
        return self._emit_result(decoded_text) if decoded_text else None

    def _transcribe_with_server(self):
        """Transcribe audio by sending it to an external server."""
        try:
            chunks, _ = self._record_audio_chunks()
            if chunks is None:
                if self.DEBUG:
                    queue_message("DEBUG STT: No speech recorded (silence timeout)")
                return None

            external_url = self.config['STT'].get('external_url', '')
            if self.DEBUG:
                total_samples = sum(len(c) for c in chunks)
                queue_message(f"DEBUG STT: Sending {total_samples} samples to {external_url}/save_audio")

            wav_buf = self._chunks_to_wav_buffer(chunks, self.MODEL_RATE)
            files = {"audio": ("audio.wav", wav_buf, "audio/wav")}
            headers = {}
            api_key = os.environ.get('EXTERNAL_API_KEY', '')
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = requests.post(
                f"{external_url}/save_audio",
                files=files, headers=headers, timeout=10
            )
            if response.status_code != 200:
                queue_message(f"ERROR: Server STT returned {response.status_code}: {response.text[:200]}")
                return None

            transcription = response.json().get("transcription", [])
            if not transcription:
                if self.DEBUG:
                    queue_message("DEBUG STT: Server returned empty transcription (VAD filtered or no speech)")
                return None

            raw_text = transcription[0].get("text", "").strip()
            if self.DEBUG:
                queue_message(f"DEBUG STT: Server transcribed: '{raw_text}'")
            extra = {
                "result": [
                    {"conf": 1.0, "start": seg.get("start", 0),
                     "end": seg.get("end", 0), "word": seg.get("text", "")}
                    for seg in transcription
                ]
            }
            return self._emit_result(raw_text, extra)
        except requests.RequestException as e:
            queue_message(f"ERROR: Server transcription request failed: {e}")
        return None

    def _transcribe_with_openai(self):
        """Transcribe and translate audio using OpenAI's Whisper API."""
        language = CONFIG['STT']['language']
        client = OpenAI(api_key=CONFIG["TTS"]["openai_api_key"])

        RATE = 16000
        chunks, speech_frames = self._record_audio_chunks()
        if chunks is None:
            return None

        # Combine and amplify all audio chunks
        audio_data = np.concatenate([self.amplify_audio(c) for c in chunks])

        # Reject near-silent recordings before sending to API
        rms = np.sqrt(np.mean(audio_data.astype(np.float64) ** 2))
        if rms < self.silence_threshold:
            return None

        # Save to temporary WAV file (OpenAI requires a file)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(RATE)
                wf.writeframes(audio_data.tobytes())

        try:
            with open(tmp_path, 'rb') as f:
                response = client.audio.transcriptions.create(
                    model="whisper-1", file=f, response_format="verbose_json"
                )
        finally:
            os.unlink(tmp_path)

        # Check no_speech_prob — reject if Whisper thinks there's no real speech
        if hasattr(response, 'segments') and response.segments:
            avg_no_speech = sum(
                seg.get('no_speech_prob', 0) if isinstance(seg, dict)
                else getattr(seg, 'no_speech_prob', 0)
                for seg in response.segments
            ) / len(response.segments)
            if avg_no_speech > 0.5:
                return None

        transcription = response.text.strip() if hasattr(response, 'text') else ""
        if not transcription:
            return None

        # Translate to target language if not English
        if language and language.lower() not in ("english", "anglais"):
            translation = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Translate the following text to {language}. Only provide the translation, nothing else."},
                    {"role": "user", "content": transcription}
                ]
            )
            transcription = translation.choices[0].message.content

        return self._emit_result(transcription)

    def _sherpa_transcribe_audio(self, audio_chunks, sample_rate=16000):
        """Denoise + transcribe int16 audio chunks with sherpa-onnx. Returns transcript string or None."""
        if not audio_chunks:
            return None
        audio_data = self._chunks_to_float32(audio_chunks)
        audio_data = self._denoise_audio(audio_data, sample_rate)
        try:
            s = self.sherpa_recognizer.create_stream()
            s.accept_waveform(sample_rate, audio_data)
            self.sherpa_recognizer.decode_stream(s)
            transcript = s.result.text.strip()
            transcript = _SENSEVOICE_TAG_RE.sub('', transcript).strip()
            transcript = self._add_punctuation(transcript)
            del s
            return transcript
        except Exception as e:
            queue_message(f"ERROR: sherpa-onnx transcription failed: {e}")
            return None

    @staticmethod
    def _looks_like_complete_sentence(text):
        if not text:
            return False
        text = text.strip()
        words = text.split()
        if len(words) < 2:
            return False
        return text[-1] in '.!?' or len(words) >= 5

    def _transcribe_with_sherpa_onnx(self):
        """Transcribe with sherpa-onnx using speculative pre-transcription and preemptive LLM."""
        if not self.sherpa_recognizer:
            queue_message("ERROR: sherpa-onnx recognizer not loaded.")
            return None

        RATE = 16000
        detected_speech = False
        silent_frames = 0
        speech_frames = 0
        pre_roll_buffer = []
        audio_chunks = []
        PRE_ROLL = 10
        MIN_SPEECH = 5
        MAX_SILENT = self.MAX_SILENT_FRAMES

        # Track how many pre-roll chunks get prepended to audio_chunks.
        # Pre-roll may contain TARS's own TTS response (which uses the user's
        # voice model), contaminating speaker ID embeddings with the wrong voice.
        pre_roll_added = 0

        # Speculative transcription — kicked off when silence first starts
        spec_thread = None
        spec_result = [None]  # Mutable container for thread result
        spec_snapshot_len = 0  # How many chunks were in the snapshot

        # Preemptive LLM generation — fired when spec transcript looks like a complete sentence
        preemptive_thread = None
        preemptive_thread_ref = [None]  # Persistent ref — survives invalidation for join at end
        preemptive_result = [None]  # Mutable container for LLM result
        preemptive_transcript = [None]  # The transcript the LLM was fired with
        preemptive_fired = False

        def _spec_transcribe(snapshot):
            spec_result[0] = self._sherpa_transcribe_audio(snapshot, RATE)

        def _preemptive_llm(text):
            try:
                preemptive_result[0] = self.preemptive_llm_callback(text)
            except Exception as e:
                queue_message(f"WARN: Preemptive LLM failed: {e}")
                preemptive_result[0] = None

        # Use RMS or Smart Turn for silence gating during recording.
        # Avoid sherpa-onnx VAD here to prevent concurrent native calls (heap corruption).
        if self.vadmethod == "smart-turn" and self.smart_turn_session is not None:
            vad_func = self._is_silence_detected_smart_turn
        else:
            vad_func = self._is_silence_detected_rms

        # Reset Smart Turn state to prevent stale inference results from the
        # previous recording round from triggering an immediate "end of turn".
        had_stale_future = self._smart_turn_future is not None
        had_stale_buffer = len(self.smart_turn_audio_buffer) > 0
        self.smart_turn_audio_buffer.clear()
        self._smart_turn_future = None
        self._smart_turn_last_buf_len = 0
        if had_stale_future or had_stale_buffer:
            queue_message(f"DEBUG: Reset stale Smart Turn state (future={had_stale_future}, buf_chunks={had_stale_buffer})")

        with ResamplingInputStream(dtype="int16") as mic:
            # Flush stale mic audio that may contain the robot's own TTS voice.
            # Uses a persistent flag (not a time window) so it works even if
            # the LLM+TTS pipeline took many seconds before we get here.
            try:
                from modules.module_tts import needs_mic_flush, clear_mic_flush
                if needs_mic_flush():
                    if not self._bargein_ready.is_set():
                        queue_message("DEBUG: Flushing mic audio after TTS playback")
                        mic.flush()
                        clear_mic_flush()
                        time.sleep(0.3)
                        mic.flush()
                    else:
                        clear_mic_flush()
            except Exception:
                pass

            # Inject barge-in audio as pre-seeded speech chunks
            if self._bargein_ready.is_set():
                bargein_chunks = self._bargein_audio_chunks or []
                self._bargein_audio_chunks = None
                self._bargein_ready.clear()
                if bargein_chunks:
                    audio_chunks.extend(bargein_chunks)
                    speech_frames = len(bargein_chunks)
                    detected_speech = True
                    queue_message(f"DEBUG: Injected {len(bargein_chunks)} barge-in chunks as pre-roll into sherpa pipeline")

            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = mic.read(4000)

                # Abort recording if TTS just started — don't pick up TARS's own voice
                if is_tts_playing():
                    set_tars_state(TarsState.STANDBY)
                    return None, 0

                is_silence, detected_speech, silent_frames = vad_func(data, detected_speech, silent_frames)

                # Pre-speech timeout: if no speech detected and silence exceeds threshold, exit early
                if not detected_speech and silent_frames >= MAX_SILENT:
                    _, clear_bar = self._get_progress_bar()
                    clear_bar()
                    if self.DEBUG:
                        queue_message(f"DEBUG: Recording exit: pre-speech timeout (no speech after {silent_frames} silent frames)")
                    return None

                if is_silence:
                    if speech_frames >= MIN_SPEECH and silent_frames >= MAX_SILENT:
                        _, clear_bar = self._get_progress_bar()
                        clear_bar()
                        if self.DEBUG:
                            queue_message(f"DEBUG: Recording exit: silence timeout (speech={speech_frames}, silent={silent_frames}, chunks={len(audio_chunks)})")
                        break
                    # Smart Turn can signal turn-complete with fewer silent frames
                    # (it clears its audio buffer when prob > 0.5, so check that)
                    if (self.vadmethod == "smart-turn" and speech_frames >= MIN_SPEECH
                            and silent_frames >= 3 and not self.smart_turn_audio_buffer):
                        queue_message(f"INFO: Smart Turn detected end of turn (speech={speech_frames}, silent={silent_frames}, chunks={len(audio_chunks)})")
                        break

                if not detected_speech:
                    pre_roll_buffer.append(data)
                    if len(pre_roll_buffer) > PRE_ROLL:
                        pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0 and pre_roll_buffer:
                        pre_roll_added = len(pre_roll_buffer)
                        audio_chunks.extend(pre_roll_buffer)
                        pre_roll_buffer = []
                    audio_chunks.append(data)

                    if not is_silence:
                        speech_frames += 1
                        # Speech resumed — invalidate speculative + preemptive
                        if spec_thread is not None:
                            spec_thread = None
                            spec_result[0] = None
                            spec_snapshot_len = 0
                        if preemptive_fired:
                            preemptive_thread = None
                            preemptive_result[0] = None
                            preemptive_transcript[0] = None
                            preemptive_fired = False

                # Kick off speculative transcription on first silence after speech
                if (detected_speech and silent_frames >= 3 and speech_frames >= MIN_SPEECH
                        and spec_thread is None and audio_chunks):
                    spec_snapshot_len = len(audio_chunks)
                    spec_thread = threading.Thread(
                        target=_spec_transcribe, args=(list(audio_chunks),), daemon=True
                    )
                    spec_thread.start()

                # Check if speculative transcript is ready and fire preemptive LLM
                if (spec_thread is not None and not preemptive_fired
                        and self.preemptive_llm_callback is not None
                        and spec_result[0] is not None
                        and self._looks_like_complete_sentence(spec_result[0])):
                    preemptive_transcript[0] = spec_result[0]
                    preemptive_fired = True
                    preemptive_thread = threading.Thread(
                        target=_preemptive_llm, args=(spec_result[0],), daemon=True
                    )
                    preemptive_thread_ref[0] = preemptive_thread
                    preemptive_thread.start()
                    if self.DEBUG:
                        queue_message(f"DEBUG: Preemptive LLM fired for: {spec_result[0][:60]}...")

            if speech_frames < MIN_SPEECH:
                if self.DEBUG:
                    queue_message(f"DEBUG: Recording discarded: not enough speech ({speech_frames}<{MIN_SPEECH})")
                return None

        if not audio_chunks:
            return None

        # Stash float32 audio for speaker ID — exclude pre-roll chunks which
        # may contain TARS's own TTS response (using the user's voice model),
        # contaminating the speaker embedding with the wrong voice.
        speech_only = audio_chunks[pre_roll_added:] if pre_roll_added else audio_chunks
        self._last_audio_float32 = self._chunks_to_float32(speech_only) if speech_only else self._chunks_to_float32(audio_chunks)

        # Check if speculative transcription covers all audio
        if spec_thread is not None and spec_snapshot_len == len(audio_chunks):
            spec_thread.join(timeout=5)
            transcript = spec_result[0]
        else:
            # More audio came after the snapshot — do a full transcription
            if spec_thread is not None:
                spec_thread.join(timeout=5)  # Wait for it to finish to avoid concurrent native calls
            transcript = self._sherpa_transcribe_audio(audio_chunks, RATE)

        if not transcript:
            if self.DEBUG:
                queue_message(f"DEBUG: Transcription returned empty (chunks={len(audio_chunks)}, speech_frames={speech_frames})")
            return None

        audio_duration = len(audio_chunks) * 4000 / RATE
        queue_message(f"DEBUG: Transcribed: '{transcript}' (speech={speech_frames}, chunks={len(audio_chunks)}, ~{audio_duration:.1f}s audio)")

        # Check if preemptive LLM result is valid (transcript matches)
        extra = None
        if preemptive_fired and preemptive_transcript[0] == transcript and preemptive_thread is not None:
            preemptive_thread.join(timeout=10)
            if preemptive_result[0] is not None:
                extra = {"preemptive_llm_result": preemptive_result[0]}
                queue_message("INFO: Using preemptive LLM result (transcript matched)")
            else:
                queue_message("INFO: Preemptive LLM returned None, falling back to normal")
        elif preemptive_fired:
            queue_message("INFO: Preemptive LLM discarded (transcript changed)")

        # Always wait for preemptive thread to finish before proceeding to
        # _emit_result → utterance_callback.  Both the preemptive and main
        # LLM calls use the same _reply_chunk_callback global, so they must
        # not run concurrently or chunks from both streams will be interleaved.
        if preemptive_thread_ref[0] is not None:
            preemptive_thread_ref[0].join(timeout=10)
            preemptive_thread_ref[0] = None

        return self._emit_result(transcript, extra)

    # === Wake Word Detection ===

    def _detect_wake_word(self) -> bool:
        if not STTManager._last_status_was_sleeping:
            if self.config["STT"]["use_indicators"]:
                self.play_wav(os.path.join(_stt_dir(), "beep_off.wav"))
            queue_message(f"{self._character_name}: Sleeping...")
            print()
            STTManager._last_status_was_sleeping = True
            set_tars_state(TarsState.STANDBY)

        processors = {
            "fastrtc": self._detect_wake_word_fastrtc,
            "sherpa-onnx": self._detect_wake_word_sherpa_onnx,
        }
        wake_proc = self.config["STT"].get("wake_word_processor", "atomik")
        return processors.get(wake_proc, self._detect_wake_word_atomik)()

    def _handle_wake_detected(self):
        """Common actions after wake word is detected: beep, notify UI, send response."""
        if self.config["STT"].get("use_indicators"):
            self.play_wav(os.path.join(_stt_dir(), "beep_on.wav"))
        self._fire_and_forget_get(f"http://127.0.0.1:{self._webui_port}/start_talking")
        if self.WAKE_WORD_RESPONSES:
            wake_response = random.choice(self.WAKE_WORD_RESPONSES)
            if self.wake_word_callback:
                self.wake_word_callback(wake_response)

    def _detect_wake_word_fastrtc(self) -> bool:
        """Detect the wake word using FastRTC STT by transcribing short audio chunks."""
        if not self.fastrtc_model:
            queue_message("ERROR: FastRTC model not loaded for wake word detection.")
            return False

        try:
            requests.get(f"http://127.0.0.1:{self._webui_port}/stop_talking", timeout=1)
        except Exception:
            pass

        # Transcript verify gate
        transcript_verify_fn = None
        stt_cfg = CONFIG.get('STT', {})
        if stt_cfg.get('vad_transcript_verify', 'False').strip() == 'True':
            transcript_verify_fn = self._build_transcript_verify_fn()

        RATE = self.MODEL_RATE
        frames_per_chunk = int(RATE * 2.0)
        self.smart_turn_audio_buffer.clear()
        self._smart_turn_future = None

        with ResamplingInputStream(dtype="int16") as mic:
            # Flush stale mic audio after TTS playback
            try:
                from modules.module_tts import needs_mic_flush, clear_mic_flush
                if needs_mic_flush():
                    queue_message("DEBUG: Flushing mic audio after TTS playback")
                    mic.flush()
                    clear_mic_flush()
            except Exception:
                pass

            for _ in range(100):
                if not self.running or self.shutdown_event.is_set():
                    break

                # Abort wake word detection if TTS started
                if is_tts_playing():
                    break

                data, _ = mic.read(frames_per_chunk)
                data = self.amplify_audio(data)

                # Simple RMS silence gate — skip transcription when quiet to save CPU
                if self._is_quiet(data):
                    continue

                # Convert to float32 for FastRTC
                audio_data = data.astype(np.float32).flatten() / 32768.0
                try:
                    transcript = self.fastrtc_model.stt((RATE, audio_data)).strip().lower()
                except Exception as e:
                    queue_message(f"ERROR: FastRTC STT failed: {e}")
                    continue

                if self.DEBUG:
                    queue_message(f"DEBUG: FastRTC Wake Word Transcript: '{transcript}'")

                if self.WAKE_WORD in transcript:
                    if not self._run_wake_gates(audio_data, transcript_verify_fn=transcript_verify_fn):
                        continue
                    self._handle_wake_detected()
                    return True

        return False

    def _detect_wake_word_atomik(self) -> bool:
        sensitivity = float(CONFIG["STT"]["sensitivity"])
        norm = (sensitivity - 1) / 9
        atomik_mode = CONFIG['STT'].get('atomik_mode', 'auto').strip().lower()
        mode = None if atomik_mode == 'auto' else atomik_mode

        if atomik_mode == 'template':
            # Template mode: cosine similarity scores range ~0.4-0.9
            # Higher sensitivity = lower threshold = easier to trigger
            # sens 1 → 0.70, sens 5 → 0.55, sens 10 → 0.40
            curve = norm ** 1.3
            threshold = round(max(0.35, min(0.70 - curve * 0.35, 0.70)), 2)
        else:
            # Model mode: CNN/ONNX outputs 0-1 probability
            # sens 1 → 0.80, sens 5 → 0.68, sens 10 → 0.40
            curve = norm ** 1.6
            threshold = round(max(0.40, min(0.80 - curve * 0.4, 0.80)), 2)

        # Transcript verify gate
        transcript_verify_fn = None
        stt_cfg = CONFIG.get('STT', {})
        if stt_cfg.get('vad_transcript_verify', 'False').strip() == 'True':
            transcript_verify_fn = self._build_transcript_verify_fn()

        detector = WakeWordSystem(self.WAKE_WORD, self.MODEL_RATE, threshold, debug=self.DEBUG, mode=mode)
        detector.createModel()
        # Wait for TTS to finish before entering blocking wake word listener
        while is_tts_playing():
            time.sleep(0.05)
        while True:
            detector.listenForWakeWord()
            audio_window = np.array(list(detector.buffer)[-int(self.MODEL_RATE * 2):], dtype=np.float32)
            if self._run_wake_gates(audio_window, transcript_verify_fn=transcript_verify_fn):
                self._handle_wake_detected()
                return True

    def _detect_wake_word_sherpa_onnx(self) -> bool:
        """Detect wake word using sherpa-onnx with a pre-allocated circular buffer."""
        if not self.sherpa_recognizer:
            queue_message("ERROR: sherpa-onnx recognizer not loaded for wake word detection.")
            return False

        self._fire_and_forget_get(f"http://127.0.0.1:{self._webui_port}/stop_talking")

        # Transcript verify gate
        transcript_verify_fn = None
        stt_cfg = CONFIG.get('STT', {})
        if stt_cfg.get('vad_transcript_verify', 'False').strip() == 'True':
            transcript_verify_fn = self._build_transcript_verify_fn()

        RATE = self.MODEL_RATE
        frames_per_chunk = int(RATE * 2.0)
        overlap_frames = int(RATE * 0.5)
        read_frames = frames_per_chunk - overlap_frames
        wake_detected = False

        # Pre-allocate circular buffer in MODEL_RATE space
        audio_buffer = np.zeros(frames_per_chunk, dtype=np.int16)

        try:
          with ResamplingInputStream(dtype="int16") as mic:
            # Flush stale mic audio after TTS playback to avoid detecting
            # the robot's own voice as a wake word.
            try:
                from modules.module_tts import needs_mic_flush, clear_mic_flush
                if needs_mic_flush():
                    queue_message("DEBUG: Flushing mic audio after TTS playback")
                    mic.flush()
                    clear_mic_flush()
            except Exception:
                pass

            # Prime buffer with first full chunk
            buf, _ = mic.read_exact(frames_per_chunk)
            audio_buffer[:] = buf.flatten()

            while self.running and not self.shutdown_event.is_set():
                # Abort wake word detection if TTS started
                if is_tts_playing():
                    break

                # Simple RMS silence gate — skip transcription when quiet to save CPU
                if self._is_quiet(audio_buffer):
                    audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                    buf, _ = mic.read_exact(read_frames)
                    audio_buffer[overlap_frames:] = buf.flatten()
                    continue

                # Amplify and convert for transcription (skip denoising — not needed for wake word matching)
                transcode_data = (audio_buffer.astype(np.float32) * self.amp_gain) / 32768.0
                try:
                    s = self.sherpa_recognizer.create_stream()
                    s.accept_waveform(RATE, transcode_data)
                    self.sherpa_recognizer.decode_stream(s)
                    transcript = _SENSEVOICE_TAG_RE.sub('', s.result.text.strip().lower()).strip()
                except Exception as e:
                    queue_message(f"ERROR: sherpa-onnx STT failed: {e}")
                    # Roll buffer forward and continue
                    audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                    buf, _ = mic.read_exact(read_frames)
                    audio_buffer[overlap_frames:] = buf.flatten()
                    continue
                finally:
                    del s  # Free native stream to prevent heap corruption

                if self.DEBUG and transcript:
                    queue_message(f"DEBUG: Sherpa Wake Word Transcript: '{transcript}'")

                if self.WAKE_WORD in transcript or self._fuzzy_wake_word_match(transcript, self.WAKE_WORD):
                    if not self._run_wake_gates(transcode_data, transcript_verify_fn=transcript_verify_fn):
                        # Gate failed — roll buffer forward and keep listening
                        audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                        buf, _ = mic.read_exact(read_frames)
                        audio_buffer[overlap_frames:] = buf.flatten()
                        continue
                    # Break out of the loop first — the wake response callback
                    # plays TTS audio (sd.play + sd.wait) which deadlocks if
                    # the ResamplingInputStream is still open.
                    wake_detected = True
                    break

                # Roll buffer: shift overlap to front, read new frames into remainder
                audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                buf, _ = mic.read_exact(read_frames)
                audio_buffer[overlap_frames:] = buf.flatten()
        except sd.PortAudioError as e:
            queue_message(f"WARNING: Audio device error in wake word detection, retrying in 2s: {e}")
            time.sleep(2)
            return False

        # InputStream is now closed — safe to play audio via sd.play
        if wake_detected:
            self._handle_wake_detected()
            return True
        return False

    @staticmethod
    def _fuzzy_wake_word_match(transcript: str, wake_word: str, threshold: float = 0.6) -> bool:
        wake_words = wake_word.split()
        transcript_words = transcript.split()
        if len(transcript_words) < len(wake_words):
            return False
        for i in range(len(transcript_words) - len(wake_words) + 1):
            window = transcript_words[i:i + len(wake_words)]
            if all(SequenceMatcher(None, tw, ww).ratio() >= threshold for tw, ww in zip(window, wake_words)):
                return True
        return False

    @staticmethod
    def _fire_and_forget_get(url):
        threading.Thread(target=lambda: requests.get(url, timeout=1), daemon=True).start()

    # === Progress Bar ===

    def _get_progress_bar(self):
        if self._progress_bar_funcs is None:
            bar_length = 10
            show_console = self.ui_manager.__class__.__name__ not in ('UIManagerLite', 'UIManagerStub')

            def update(frames, max_frames):
                self.ui_manager.silence(frames)

            def clear():
                self.ui_manager.silence(0)

            self._progress_bar_funcs = (update, clear)
        return self._progress_bar_funcs

    # === VAD Methods ===

    def voice_activity_detection_main(self, data, detected_speech, silent_frames=0):
        vad_dispatch = {
            "silero": self._is_silence_detected_silero,
            "sherpa-onnx": self._is_silence_detected_sherpa_onnx,
            "smart-turn": self._is_silence_detected_smart_turn,
        }
        return vad_dispatch.get(self.vadmethod, self._is_silence_detected_rms)(data, detected_speech, silent_frames)

    def _is_silence_detected_silero(self, data, detected_speech, silent_frames):
        """Check if the provided audio data represents silence using Silero VAD.
        Always returns a tuple of (is_silence, detected_speech, silent_frames)."""
        update_bar, clear_bar = self._get_progress_bar()
        try:
            if torch is None or self.silero_vad_model is None or self.get_speech_timestamps is None:
                return self._is_silence_detected_rms(data, detected_speech, silent_frames)

            audio_tensor = torch.from_numpy(data.astype(np.float32) / 32768.0).squeeze()
            if hasattr(self.silero_vad_model, 'reset_states'):
                self.silero_vad_model.reset_states()

            speech_ts = self.get_speech_timestamps(
                audio_tensor, self.silero_vad_model,
                sampling_rate=self.MODEL_RATE, threshold=0.3,
                min_speech_duration_ms=100, return_seconds=True
            ) or []

            if speech_ts:
                detected_speech = True
                silent_frames = 0
                clear_bar()
            else:
                silent_frames += 1
                update_bar(silent_frames, self.MAX_SILENT_FRAMES)

            if silent_frames > self.MAX_SILENT_FRAMES:
                clear_bar()
                return True, detected_speech, silent_frames
            return False, detected_speech, silent_frames

        except Exception as e:
            queue_message(f"WARNING: VAD error, falling back to RMS: {e}")
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    def _is_silence_detected_rms(self, data, detected_speech, silent_frames):
        """RMS-based silence detection with visual progress bar."""
        update_bar, clear_bar = self._get_progress_bar()
        rms = self._compute_rms_fast(data)
        if self.silence_threshold_margin is None:
            self.silence_threshold_margin = self.silence_threshold

        if rms is None:
            return False, detected_speech, silent_frames

        if rms > self.silence_threshold_margin:
            detected_speech = True
            silent_frames = 0
            if self.DEBUG:
                queue_message(f"AUDIO: {rms:.2f}/{self.silence_threshold:.2f}/{self.silence_threshold_margin:.2f}")
            clear_bar()
        else:
            silent_frames += 1
            if self.DEBUG:
                queue_message(f"SILENT: {rms:.2f}/{self.silence_threshold:.2f}/{self.silence_threshold_margin:.2f}")
            update_bar(silent_frames, self.MAX_SILENT_FRAMES)
            if silent_frames > self.MAX_SILENT_FRAMES:
                clear_bar()
                return True, detected_speech, silent_frames

        return False, detected_speech, silent_frames

    def _is_silence_detected_sherpa_onnx(self, data, detected_speech, silent_frames):
        """Sherpa-onnx Silero VAD-based silence detection (no torch required)."""
        update_bar, clear_bar = self._get_progress_bar()
        try:
            if self.sherpa_vad is None:
                return self._is_silence_detected_rms(data, detected_speech, silent_frames)

            self.sherpa_vad.accept_waveform(data.astype(np.float32).flatten() / 32768.0)

            if self.sherpa_vad.is_speech_detected():
                detected_speech = True
                silent_frames = 0
                clear_bar()
                # Flush detected segments to prevent buffer buildup
                while not self.sherpa_vad.empty():
                    self.sherpa_vad.pop()
            else:
                silent_frames += 1
                update_bar(silent_frames, self.MAX_SILENT_FRAMES)

            if silent_frames > self.MAX_SILENT_FRAMES:
                clear_bar()
                self.sherpa_vad.reset()
                return True, detected_speech, silent_frames
            return False, detected_speech, silent_frames

        except Exception as e:
            queue_message(f"WARNING: sherpa-onnx VAD error, falling back to RMS: {e}")
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    def _smart_turn_infer(self, audio):
        """Run Smart Turn inference in background thread. Returns probability float."""
        max_samples = 8 * 16000
        if len(audio) > max_samples:
            audio = audio[-max_samples:]
        inputs = self.smart_turn_extractor(
            audio, sampling_rate=16000, return_tensors="np",
            padding="max_length", max_length=max_samples,
            truncation=True, do_normalize=True
        )
        outputs = self.smart_turn_session.run(None, {
            "input_features": inputs.input_features.astype(np.float32)
        })
        prob = outputs[0][0].item()
        if self.DEBUG:
            queue_message(f"DEBUG: Smart Turn infer done: prob={prob:.3f}, audio_len={len(audio)}")
        return prob

    def _is_silence_detected_smart_turn(self, data, detected_speech, silent_frames):
        """Hybrid RMS + Smart Turn semantic turn detection.

        Uses RMS to detect per-frame silence, then runs the Smart Turn model
        asynchronously on accumulated audio during pauses to determine if the
        speaker has finished their turn (vs just pausing mid-sentence).
        Inference runs in a background thread so it never blocks audio reads.
        """
        update_bar, clear_bar = self._get_progress_bar()
        try:
            if self.smart_turn_session is None or self.smart_turn_extractor is None:
                return self._is_silence_detected_rms(data, detected_speech, silent_frames)

            # RMS check on current frame
            rms = self._compute_rms_fast(data)
            if self.silence_threshold_margin is None:
                self.silence_threshold_margin = self.silence_threshold
            if rms is None:
                return False, detected_speech, silent_frames

            if rms > self.silence_threshold_margin:
                # Speech detected — accumulate audio and cancel any pending inference
                detected_speech = True
                silent_frames = 0
                self.smart_turn_audio_buffer.append(data.astype(np.float32).flatten() / 32768.0)
                self._smart_turn_future = None  # discard stale result if speaker resumed
                self._smart_turn_last_buf_len = 0  # reset cache so next silence triggers inference
                clear_bar()
                return False, detected_speech, silent_frames

            # Silence detected
            silent_frames += 1
            update_bar(silent_frames, self.MAX_SILENT_FRAMES)

            # Safety fallback FIRST: force end if silence exceeds configured threshold
            if silent_frames > self.MAX_SILENT_FRAMES:
                clear_bar()
                self.smart_turn_audio_buffer.clear()
                self._smart_turn_future = None
                return True, detected_speech, silent_frames

            # Check if a previous inference completed
            if self._smart_turn_future is not None and self._smart_turn_future.done():
                try:
                    probability = self._smart_turn_future.result()
                    self._smart_turn_future = None
                    if self.DEBUG:
                        queue_message(f"DEBUG: Smart Turn probability: {probability:.3f}    ")
                    if probability > 0.5:
                        if self.DEBUG:
                            queue_message(f"DEBUG: Smart Turn -> end of turn (prob={probability:.3f}, detected_speech={detected_speech}, silent={silent_frames}, buf={len(self.smart_turn_audio_buffer)})")
                        clear_bar()
                        self.smart_turn_audio_buffer.clear()
                        return True, detected_speech, silent_frames
                except Exception as e:
                    queue_message(f"WARNING: Smart Turn inference error: {e}")
                    self._smart_turn_future = None

            # Kick off inference if not already running and buffer has new audio
            _cur_buf_len = len(self.smart_turn_audio_buffer)
            if (silent_frames >= 3 and detected_speech
                    and self.smart_turn_audio_buffer
                    and self._smart_turn_future is None
                    and _cur_buf_len != self._smart_turn_last_buf_len):
                audio_snapshot = np.concatenate(list(self.smart_turn_audio_buffer))
                self._smart_turn_last_buf_len = _cur_buf_len
                if self.DEBUG:
                    queue_message(f"DEBUG: Smart Turn submitting inference (silent={silent_frames}, buf_chunks={_cur_buf_len}, samples={len(audio_snapshot)})")
                self._smart_turn_future = self._smart_turn_executor.submit(
                    self._smart_turn_infer, audio_snapshot
                )

            return False, detected_speech, silent_frames

        except Exception as e:
            queue_message(f"WARNING: Smart Turn VAD error, falling back to RMS: {e}")
            self.smart_turn_audio_buffer.clear()
            self._smart_turn_future = None
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    # === Background Noise Measurement ===

    def _measure_background_noise(self):
        """Measure background noise and set the silence threshold."""
        queue_message("INFO: Measuring background noise...")
        rms_values = []

        with ResamplingInputStream(dtype="int16") as mic:
            for _ in range(20):
                data, _ = mic.read(4000)
                rms = self._compute_rms_fast(data)
                if rms is not None:
                    rms_values.append(rms)
                time.sleep(0.1)

        if rms_values:
            bg_rms = np.array(rms_values)
            # Remove outliers using IQR
            q1, q3 = np.percentile(bg_rms, [25, 75])
            iqr = q3 - q1
            filtered = bg_rms[(bg_rms >= q1 - 1.5 * iqr) & (bg_rms <= q3 + 1.5 * iqr)]
            self.wake_silence_threshold = np.max(filtered) if filtered.size > 0 else np.median(bg_rms)
            self.silence_threshold = self.wake_silence_threshold * self.silence_margin
            self.silence_threshold_margin = self.silence_threshold
            db = 20 * np.log10(self.silence_threshold) if self.silence_threshold > 0 else -999
            queue_message(f"INFO: Silence threshold: {db:.2f} dB (rms={self.silence_threshold:.1f}, bg_noise={self.wake_silence_threshold:.1f}, margin={self.silence_margin}x, amp_gain={self.amp_gain}x)")
        else:
            queue_message("WARNING: Background noise measurement failed; using default threshold.")

    # Backward compatibility alias
    def prepare_audio_data(self, data):
        return self._compute_rms(data)

    # === Callback Setters ===

    def set_wake_word_callback(self, callback: Callable[[str], None]):
        self.wake_word_callback = callback

    def set_utterance_callback(self, callback: Callable[[str], None]):
        self.utterance_callback = callback

    def set_post_utterance_callback(self, callback: Callable[[], None]):
        self.post_utterance_callback = callback

    def set_preemptive_llm_callback(self, callback: Callable[[str], object]):
        self.preemptive_llm_callback = callback

    # === Barge-In Monitoring ===

    def start_bargein_monitor(self, tts_text=""):
        """Start monitoring mic for barge-in during TTS playback.

        Two modes:
        - fuzzy: Transcribes mic audio and checks for words NOT in the TTS text.
        - voiceprint: Extracts speaker embedding and checks if it matches a known user.

        Args:
            tts_text: The text TARS is currently saying (used by fuzzy mode).
        """
        if not self._bargein_enabled:
            return
        if self.silence_threshold is None:
            return  # Can't monitor without a noise floor

        mode = self._bargein_mode

        if mode in ('voiceprint', 'hybrid'):
            # Voiceprint/hybrid mode needs speaker ID
            try:
                from modules.module_speaker_id import get_speaker_id_manager
                sid = get_speaker_id_manager()
                if sid is None or sid._manager is None or sid._manager.num_speakers == 0:
                    queue_message(f"WARN: Barge-in {mode} mode requires Speaker ID with enrolled speakers, falling back to fuzzy")
                    mode = 'fuzzy'
            except Exception as e:
                queue_message(f"WARN: Speaker ID not available ({e}), falling back to fuzzy barge-in")
                mode = 'fuzzy'

        if mode == 'hybrid' and self.sherpa_recognizer is None and self.fastrtc_model is None:
            queue_message("WARN: Barge-in hybrid mode requires sherpa-onnx or fastrtc for fuzzy check, falling back to voiceprint")
            mode = 'voiceprint'

        if mode == 'fuzzy' and self.sherpa_recognizer is None and self.fastrtc_model is None:
            queue_message("WARN: Barge-in fuzzy mode requires sherpa-onnx or fastrtc, skipping")
            return

        self._bargein_active = True
        # Clear any stale barge-in audio from previous round
        self._bargein_audio_chunks = None
        self._bargein_ready.clear()

        if mode == 'voiceprint':
            self._start_bargein_voiceprint()
        elif mode == 'hybrid':
            self._start_bargein_hybrid(tts_text)
        else:
            self._start_bargein_fuzzy(tts_text)

    def _start_bargein_fuzzy(self, tts_text):
        """Fuzzy word-matching barge-in monitor."""
        from modules.module_tts import stop_tts_playback, is_tts_playing

        # Build initial word list from whatever text we have; during streaming
        # this may be empty and will be updated via update_bargein_tts_text().
        if tts_text:
            cleaned = _NON_ALNUM_SPACE_RE.sub('', tts_text.lower())
            self._bargein_tts_data = {
                'word_list': cleaned.split(),
                'words_all': set(cleaned.split()),
            }
        else:
            self._bargein_tts_data = {'word_list': [], 'words_all': set()}

        tts_data = self._bargein_tts_data  # local ref for monitor thread

        def _monitor():
            bargein_threshold = self.silence_threshold * self._bargein_rms_scale
            audio_buf = []
            all_speech_chunks = []  # Accumulate ALL speech frames for final transcript
            TRANSCRIBE_EVERY = 8  # Transcribe every ~1s (8 x 125ms frames)
            frame_count = 0
            start_time = time.time()
            WORDS_PER_SEC = 3.0  # Estimated TTS speaking rate
            WINDOW_PAD = 4       # Extra words before/after estimated position
            accumulated_novel = []  # Novel words across consecutive frames
            no_novel_streak = 0     # Reset accumulator after 2 empty frames
            ECHO_GRACE_FRAMES = 2   # Skip ~250ms after TTS stops to let echo die
            grace_remaining = 0     # Countdown frames after TTS stops playing
            bargein_fired = False

            try:
                with ResamplingInputStream(dtype="int16") as mic:
                    # Flush stale audio from OS buffer (discard first ~0.5s)
                    mic.flush()

                    while self._bargein_active:
                        data, _ = mic.read(2000)  # ~125ms frame
                        frame_count += 1

                        tts_active = is_tts_playing()

                        # Collect audio with speech energy
                        rms = self._compute_rms_fast(data)
                        if rms and rms > bargein_threshold:
                            audio_buf.append(data)
                            # Only save for transcript when TTS is silent —
                            # during playback, AEC residual contaminates the audio
                            if not tts_active:
                                all_speech_chunks.append(data)

                        # Periodically transcribe what we've collected
                        if frame_count % TRANSCRIBE_EVERY == 0:
                            if len(audio_buf) < 2:
                                if self.DEBUG:
                                    queue_message(f"DEBUG: Barge-in: no speech frames ({len(audio_buf)}/8 above threshold)")
                        if frame_count % TRANSCRIBE_EVERY == 0 and len(audio_buf) >= 2:
                            transcript = self._bargein_transcribe(audio_buf)
                            buf_len = len(audio_buf)
                            audio_buf.clear()
                            if transcript:
                                # Read current TTS words (may be updated by streaming thread)
                                tts_word_list = tts_data['word_list']
                                tts_words_all = tts_data['words_all']

                                # Build sliding window of TTS words near current playback position
                                elapsed = time.time() - start_time
                                pos = int(elapsed * WORDS_PER_SEC)
                                win_start = max(0, pos - WINDOW_PAD)
                                win_end = min(len(tts_word_list), pos + WINDOW_PAD + 1)
                                window_words = set(tts_word_list[win_start:win_end])

                                novel = self._find_novel_words(transcript, tts_words_all, window_words)
                                if novel:
                                    accumulated_novel.extend(novel)
                                    no_novel_streak = 0
                                else:
                                    no_novel_streak += 1
                                    if no_novel_streak >= 2:
                                        accumulated_novel.clear()

                                if self.DEBUG:
                                    queue_message(f"DEBUG: Barge-in: '{transcript}' window={window_words} novel={novel} accumulated={accumulated_novel} (frames={buf_len})")
                                if len(accumulated_novel) >= self._bargein_min_novel:
                                    if self.DEBUG:
                                        queue_message(f"DEBUG: Barge-in detected! Heard: '{transcript}' (novel: {accumulated_novel})")
                                    stop_tts_playback()
                                    bargein_fired = True
                                    break

                    # Save accumulated speech audio for the normal pipeline to use as pre-roll
                    if bargein_fired and all_speech_chunks:
                        self._bargein_audio_chunks = all_speech_chunks
                        self._bargein_ready.set()

            except Exception as e:
                queue_message(f"WARN: Barge-in monitor error: {e}")

        self._bargein_thread = threading.Thread(target=_monitor, daemon=True)
        self._bargein_thread.start()

    def _start_bargein_voiceprint(self):
        """Voiceprint-based barge-in monitor. Checks if detected speech matches a known speaker."""
        from modules.module_tts import stop_tts_playback, is_tts_playing
        from modules.module_speaker_id import get_speaker_id_manager

        def _monitor():
            bargein_threshold = self.silence_threshold * self._bargein_rms_scale
            speech_buf = []       # Rolling buffer of speech frames (kept across checks)
            all_speech_chunks = []  # Accumulate ALL speech frames for final transcript
            MAX_BUF = 16          # Keep last ~2s of speech frames (16 x 125ms)
            CHECK_EVERY = 4       # Check every ~0.5s (4 x 125ms)
            MIN_SPEECH = 8        # Need >=8 speech frames (~1s) for usable embedding
            frame_count = 0
            ECHO_GRACE_FRAMES = 2   # Skip ~250ms after TTS stops to let echo die
            grace_remaining = 0     # Countdown frames after TTS stops playing
            bargein_fired = False

            try:
                with ResamplingInputStream(dtype="int16") as mic:
                    # Flush stale audio from OS buffer (discard first ~0.5s)
                    mic.flush()

                    while self._bargein_active:
                        data, _ = mic.read(2000)  # ~125ms frame
                        frame_count += 1

                        tts_active = is_tts_playing()

                        # Collect frames with speech energy
                        rms = self._compute_rms_fast(data)
                        if rms and rms > bargein_threshold:
                            speech_buf.append(data)
                            # Only save for transcript when TTS is silent
                            if not tts_active:
                                all_speech_chunks.append(data)
                            if len(speech_buf) > MAX_BUF:
                                speech_buf = speech_buf[-MAX_BUF:]

                        if frame_count % CHECK_EVERY == 0:
                            if len(speech_buf) < MIN_SPEECH:
                                continue

                            # Use last MIN_SPEECH..MAX_BUF speech frames for embedding
                            audio_int16 = np.concatenate(speech_buf[-MAX_BUF:])
                            audio_float32 = audio_int16.astype(np.float32).flatten() / 32768.0

                            sid = get_speaker_id_manager()
                            if sid is None:
                                continue

                            embedding = sid.extract_embedding(audio_float32, 16000)
                            if embedding is None:
                                continue

                            # Identify speaker (skip normal margin check — we do our own below)
                            name, confidence = sid.identify_speaker(embedding, skip_margin=True)

                            # Ignore Unknown_* profiles — they may be TARS bleed
                            # that got auto-enrolled. Only named speakers matter.
                            if name and name.startswith("Unknown_"):
                                name = ""
                                confidence = 0.0

                            # Bleed filter: TTS audio bleeds into mic and can weakly
                            # match enrolled speakers. Real speech has a clear margin
                            # over runner-up; bleed does not.
                            margin = 1.0  # default if only one speaker enrolled
                            if name and confidence > 0:
                                enrolled = sid.get_enrolled_speakers()
                                if len(enrolled) > 1:
                                    runner_up = 0.0
                                    for spk in enrolled:
                                        if spk != name:
                                            s = sid._compute_best_score(embedding, spk)
                                            if s > runner_up:
                                                runner_up = s
                                    margin = confidence - runner_up

                            if self.DEBUG and name and confidence > 0.01:
                                queue_message(f"DEBUG: Barge-in voiceprint: speaker='{name}' confidence={confidence:.2f} threshold={self._bargein_voiceprint_threshold:.2f} margin={margin:.3f}")

                            # Match requires: above threshold AND margin > 0.05
                            # (bleed typically has margin < 0.04, real speech > 0.10)
                            matched = bool(name and confidence >= self._bargein_voiceprint_threshold and margin > 0.05)

                            if matched:
                                if self.DEBUG:
                                    queue_message(f"DEBUG: Barge-in detected! Voice matched '{name}' (confidence: {confidence:.2f}, margin: {margin:.3f})")
                                stop_tts_playback()
                                bargein_fired = True
                                break

                    # Save accumulated speech audio for the normal pipeline to use as pre-roll
                    if bargein_fired and all_speech_chunks:
                        self._bargein_audio_chunks = all_speech_chunks
                        self._bargein_ready.set()

            except Exception as e:
                queue_message(f"WARN: Barge-in voiceprint monitor error: {e}")

        self._bargein_thread = threading.Thread(target=_monitor, daemon=True)
        self._bargein_thread.start()

    def _start_bargein_hybrid(self, tts_text):
        """Hybrid barge-in: voiceprint + fuzzy word matching.

        Combines both checks — requires voice match AND novel words for
        robust detection that filters both AEC residual and background noise.
        High-confidence voiceprint alone can also trigger (clear user speech).
        """
        from modules.module_tts import stop_tts_playback, is_tts_playing
        from modules.module_speaker_id import get_speaker_id_manager

        # Build TTS word list for fuzzy matching
        if tts_text:
            cleaned = _NON_ALNUM_SPACE_RE.sub('', tts_text.lower())
            self._bargein_tts_data = {
                'word_list': cleaned.split(),
                'words_all': set(cleaned.split()),
            }
        else:
            self._bargein_tts_data = {'word_list': [], 'words_all': set()}

        tts_data = self._bargein_tts_data

        def _monitor():
            bargein_threshold = self.silence_threshold * self._bargein_rms_scale
            speech_buf = []       # Rolling buffer for voiceprint
            audio_buf = []        # Buffer for fuzzy transcription
            all_speech_chunks = []
            pre_speech_buf = []   # Rolling buffer of frames before speech detected
            PRE_SPEECH_MAX = 8    # ~1s of pre-speech audio to capture word onsets
            speech_started = False
            MAX_BUF = 16
            CHECK_EVERY = 4       # Voiceprint check every ~0.5s
            TRANSCRIBE_EVERY = 8  # Fuzzy transcribe every ~1s
            MIN_SPEECH = 8
            frame_count = 0
            start_time = time.time()
            WORDS_PER_SEC = 3.0
            WINDOW_PAD = 4
            bargein_fired = False

            # Track both signals
            voiceprint_matched = False
            voiceprint_confidence = 0.0
            fuzzy_novel_count = 0
            accumulated_novel = []
            no_novel_streak = 0

            # High-confidence voiceprint threshold — triggers alone without fuzzy
            HIGH_CONFIDENCE = 0.85

            try:
                with ResamplingInputStream(dtype="int16") as mic:
                    mic.flush()

                    while self._bargein_active:
                        data, _ = mic.read(2000)
                        frame_count += 1
                        tts_active = is_tts_playing()

                        rms = self._compute_rms_fast(data)
                        if rms and rms > bargein_threshold:
                            speech_buf.append(data)
                            audio_buf.append(data)
                            # On first speech frame, prepend the pre-speech buffer
                            # so we capture the onset of the user's first word
                            if not speech_started:
                                speech_started = True
                                all_speech_chunks.extend(pre_speech_buf)
                                pre_speech_buf.clear()
                            all_speech_chunks.append(data)
                            if len(speech_buf) > MAX_BUF:
                                speech_buf = speech_buf[-MAX_BUF:]
                        else:
                            # Keep a rolling buffer of recent frames before speech
                            if not speech_started:
                                pre_speech_buf.append(data)
                                if len(pre_speech_buf) > PRE_SPEECH_MAX:
                                    pre_speech_buf.pop(0)

                        # --- Voiceprint check ---
                        if frame_count % CHECK_EVERY == 0 and len(speech_buf) >= MIN_SPEECH:
                            audio_int16 = np.concatenate(speech_buf[-MAX_BUF:])
                            audio_float32 = audio_int16.astype(np.float32).flatten() / 32768.0
                            sid = get_speaker_id_manager()
                            if sid:
                                embedding = sid.extract_embedding(audio_float32, 16000)
                                if embedding is not None:
                                    name, confidence = sid.identify_speaker(embedding, skip_margin=True)
                                    if name and name.startswith("Unknown_"):
                                        name = ""
                                        confidence = 0.0

                                    margin = 1.0
                                    if name and confidence > 0:
                                        enrolled = sid.get_enrolled_speakers()
                                        if len(enrolled) > 1:
                                            runner_up = max(
                                                (sid._compute_best_score(embedding, spk) for spk in enrolled if spk != name),
                                                default=0.0
                                            )
                                            margin = confidence - runner_up

                                    voiceprint_matched = bool(name and confidence >= self._bargein_voiceprint_threshold and margin > 0.05)
                                    voiceprint_confidence = confidence if name else 0.0

                                    if self.DEBUG and name and confidence > 0.01:
                                        queue_message(f"DEBUG: Hybrid voiceprint: speaker='{name}' conf={confidence:.2f} thr={self._bargein_voiceprint_threshold:.2f} margin={margin:.3f}")

                                    # High-confidence voiceprint alone triggers immediately
                                    if voiceprint_matched and confidence >= HIGH_CONFIDENCE:
                                        if self.DEBUG:
                                            queue_message(f"DEBUG: Hybrid barge-in (voiceprint only)! '{name}' conf={confidence:.2f}")
                                        stop_tts_playback()
                                        bargein_fired = True
                                        break

                        # --- Fuzzy word check ---
                        if frame_count % TRANSCRIBE_EVERY == 0 and len(audio_buf) >= 2:
                            transcript = self._bargein_transcribe(audio_buf)
                            buf_len = len(audio_buf)
                            audio_buf.clear()
                            if transcript:
                                tts_word_list = tts_data['word_list']
                                tts_words_all = tts_data['words_all']
                                elapsed = time.time() - start_time
                                pos = int(elapsed * WORDS_PER_SEC)
                                win_start = max(0, pos - WINDOW_PAD)
                                win_end = min(len(tts_word_list), pos + WINDOW_PAD + 1)
                                window_words = set(tts_word_list[win_start:win_end])

                                novel = self._find_novel_words(transcript, tts_words_all, window_words)
                                if novel:
                                    accumulated_novel.extend(novel)
                                    no_novel_streak = 0
                                else:
                                    no_novel_streak += 1
                                    if no_novel_streak >= 2:
                                        accumulated_novel.clear()

                                if self.DEBUG:
                                    queue_message(f"DEBUG: Hybrid fuzzy: '{transcript}' novel={novel} accumulated={accumulated_novel} vp={voiceprint_matched} (frames={buf_len})")

                                # Combined trigger: voiceprint match + novel words
                                if voiceprint_matched and len(accumulated_novel) >= 1:
                                    if self.DEBUG:
                                        queue_message(f"DEBUG: Hybrid barge-in (voice+words)! novel={accumulated_novel} conf={voiceprint_confidence:.2f}")
                                    stop_tts_playback()
                                    bargein_fired = True
                                    break

                                # Fuzzy alone with enough novel words (fallback)
                                if len(accumulated_novel) >= self._bargein_min_novel:
                                    if self.DEBUG:
                                        queue_message(f"DEBUG: Hybrid barge-in (fuzzy only)! novel={accumulated_novel}")
                                    stop_tts_playback()
                                    bargein_fired = True
                                    break

                    if bargein_fired and all_speech_chunks:
                        self._bargein_audio_chunks = all_speech_chunks
                        self._bargein_ready.set()

            except Exception as e:
                queue_message(f"WARN: Barge-in hybrid monitor error: {e}")

        self._bargein_thread = threading.Thread(target=_monitor, daemon=True)
        self._bargein_thread.start()

    def _bargein_transcribe(self, audio_buffer):
        """Quick transcription of buffered audio for barge-in detection."""
        try:
            audio_data = self._chunks_to_float32(audio_buffer)
            if self.sherpa_recognizer is not None:
                s = self.sherpa_recognizer.create_stream()
                s.accept_waveform(16000, audio_data)
                self.sherpa_recognizer.decode_stream(s)
                transcript = _SENSEVOICE_TAG_RE.sub('', s.result.text.strip()).strip()
                del s
            elif self.fastrtc_model is not None:
                transcript = self.fastrtc_model.stt((16000, audio_data)).strip()
            else:
                return None
            if not transcript:
                return None
            # Filter out non-Latin hallucinations (SenseVoiceTiny outputs CJK on noise)
            ascii_chars = sum(1 for c in transcript if c.isascii())
            if ascii_chars < len(transcript) * 0.5:
                return None
            return transcript
        except Exception as e:
            queue_message(f"WARN: Barge-in transcribe error: {e}")
            return None

    def _find_novel_words(self, transcript, tts_words_all, window_words=None):
        """Find words in transcript that are NOT in the TTS text.

        Uses a two-tier fuzzy matching approach:
        1. Broad match against ALL TTS words (moderate threshold)
        2. Aggressive match against the sliding window of words currently
           being spoken (low threshold — speaker bleed is heavily distorted)

        Also checks substring containment and shared-prefix matching to catch
        common mis-transcriptions (e.g. "under" from "on your", "worries" from "warriors").

        Returns list of novel words, or empty list if all words match TTS."""
        cleaned = _NON_ALNUM_SPACE_RE.sub('', transcript.lower())
        heard_words = cleaned.split()
        if not heard_words:
            return []

        if window_words is None:
            window_words = set()

        novel = []
        for w in heard_words:
            # Filter out common filler/noise transcription artifacts and short words
            if w in _BARGEIN_NOISE_WORDS or len(w) <= 2:
                continue

            # Exact match against all TTS words
            if w in tts_words_all:
                continue

            # Check if word is in the sliding window (currently being spoken — likely bleed)
            if w in window_words:
                continue

            matched = False

            # Fuzzy match: only for 4+ char words with similar length, high threshold
            # Catches bleed misspellings like "yard"/"yarn", "satelite"/"satellite"
            if len(w) >= 4:
                compare_set = window_words | tts_words_all
                for tts_w in compare_set:
                    if len(tts_w) >= 4 and abs(len(w) - len(tts_w)) <= 2:
                        ratio = SequenceMatcher(None, w, tts_w).ratio()
                        if ratio >= self._bargein_broad_threshold:
                            matched = True
                            break

            if not matched:
                novel.append(w)

        # Require minimum novel words — fewer = more sensitive to interrupts
        return novel if len(novel) >= self._bargein_min_novel else []

    def update_bargein_tts_text(self, tts_text):
        """Update the TTS text used by the fuzzy barge-in monitor.

        Called during streaming TTS to feed newly-generated text so the
        monitor can distinguish speaker bleed from real user speech."""
        if not self._bargein_active:
            return
        cleaned = _NON_ALNUM_SPACE_RE.sub('', tts_text.lower())
        word_list = cleaned.split()
        self._bargein_tts_data['word_list'] = word_list
        self._bargein_tts_data['words_all'] = set(word_list)

    def stop_bargein_monitor(self):
        """Stop the barge-in monitor thread and wait for mic stream to close."""
        self._bargein_active = False
        if self._bargein_thread is not None:
            self._bargein_thread.join(timeout=5)
            if self._bargein_thread.is_alive():
                queue_message("WARN: Barge-in monitor thread did not exit cleanly")
            self._bargein_thread = None
        # If no barge-in fired, clear state so normal pipeline isn't confused
        if not self._bargein_ready.is_set():
            self._bargein_audio_chunks = None
            self._bargein_ready.clear()
