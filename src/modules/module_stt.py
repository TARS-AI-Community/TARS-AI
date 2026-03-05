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
import wave
import json
import sys
import tempfile
from difflib import SequenceMatcher
from io import BytesIO
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import requests

from modules.module_messageQue import queue_message
from modules.module_config import load_config, get_capabilities

CONFIG = load_config()
CAPABILITIES = get_capabilities()

# --- Conditional heavy imports based on device capabilities ---
torch = None
librosa = None
get_stt_model = None
OpenAI = None
WakeWordSystem = None
sherpa_onnx = None

# Torch and related (Pi5 only for Silero VAD)
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
})

# Global STT manager instance
_stt_manager_instance = None

def get_stt_manager():
    global _stt_manager_instance
    return _stt_manager_instance


def _stt_dir():
    """Return the path to the stt models directory (one level up from cwd)."""
    return os.path.join(os.path.dirname(os.getcwd()), "stt")


class STTManager:
    """Manages Speech-to-Text processing for TARS-AI."""

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

    def __init__(self, config, shutdown_event: threading.Event, ui_manager, amp_gain: float = 4.0):
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

        # Audio settings - Set sample rate based on VAD configuration
        self.DEFAULT_SAMPLE_RATE = 16000
        if self.config["STT"].get("vad_enabled", False):
            # If VAD is enabled, force 16000 Hz sample rate
            self.SAMPLE_RATE = 16000
            queue_message("INFO: Using 16000 Hz sample rate for VAD compatibility")
        else:
            # If VAD is disabled, use system default
            self.SAMPLE_RATE = self._find_default_mic_sample_rate()

        self.amp_gain = amp_gain  # Microphone amplification multiplier
        self.silence_margin = 3.5  # Noise floor multiplier
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
        self.smart_turn_audio_buffer = []

        # Barge-in monitoring
        self._bargein_active = False
        self._bargein_thread = None

        # Cache progress bar, webui port, and character name so they aren't recreated per frame
        self._progress_bar_funcs = None
        self._webui_port = CONFIG['UI'].get('webui_port', 80)
        self._character_name = self._resolve_character_name()

        self._initialize_models()
        self.vadmethod = CONFIG['STT']['vad_method']
        self.DEBUG = False

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
        WakeWordSystem(self.WAKE_WORD).createModel()

    def _load_silero_model(self):
        """Load Silero STT model via Torch Hub into the stt folder."""
        if torch is None:
            queue_message("WARNING: Silero STT not available (torch not installed)")
            return
        try:
            # Go one level up from the current directory
            stt_folder = _stt_dir()
            os.makedirs(stt_folder, exist_ok=True)
            # Override torch.hub.get_dir to return stt_folder directly
            import torch.hub
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
            queue_message("INFO: Smart Turn v3.2 model loaded successfully.")
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

    def _find_default_mic_sample_rate(self):
        try:
            idx = sd.default.device[0]
            if idx is None:
                raise ValueError("No default microphone detected.")
            return int(sd.query_devices(idx, kind="input").get("default_samplerate", 16000))
        except Exception as e:
            queue_message(f"ERROR: {e}")
            return self.DEFAULT_SAMPLE_RATE

    def play_wav(self, filename):
        try:
            data, sr = sf.read(filename)
            sd.play(data * 0.5, samplerate=sr)
            sd.wait()
        except Exception as e:
            queue_message(f"ERROR: Playing sound file failed: {e}")

    def _is_quiet(self, data):
        """Quick RMS silence gate check. Returns True if below threshold."""
        rms = self._compute_rms(self.amplify_audio(data))
        if rms is None:
            return True
        threshold = self.silence_threshold_margin or (
            self.silence_threshold * self.silence_margin if self.silence_threshold else None
        )
        return threshold is not None and rms <= threshold

    # === Shared Recording ===

    def _record_audio_chunks(self, sample_rate=16000, use_pre_roll=True, min_speech_frames=5,
                             pre_roll_frames=10, vad_method=None):
        """Record audio until end-of-speech detected.

        Returns (audio_chunks, speech_frames) where audio_chunks is a list of
        int16 numpy arrays, or (None, 0) if no speech detected.
        """
        detected_speech = False
        silent_frames = 0
        speech_frames = 0
        pre_roll_buffer = []
        audio_chunks = []
        max_silent = self.MAX_SILENT_FRAMES

        # Select VAD method
        if vad_method is None:
            vad_func = self.voice_activity_detection_main
        elif vad_method == "rms":
            vad_func = self._is_silence_detected_rms
        elif vad_method == "smart-turn" and self.smart_turn_session is not None:
            vad_func = self._is_silence_detected_smart_turn
        else:
            vad_func = self._is_silence_detected_rms

        with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
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

                # Smart Turn early exit
                if (is_silence and vad_method == "smart-turn" and speech_frames >= min_speech_frames
                        and silent_frames >= 3 and len(self.smart_turn_audio_buffer) == 0):
                    queue_message("INFO: Smart Turn detected end of turn")
                    break

                if not detected_speech:
                    if use_pre_roll:
                        pre_roll_buffer.append(data)
                        if len(pre_roll_buffer) > pre_roll_frames:
                            pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0 and pre_roll_buffer:
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
        """Build formatted result dict, fire utterance callback, return result."""
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

            result = transcribe_fn()

            # Filter non-speech noise
            if result and not self._is_meaningful_text(result.get("text", "")):
                queue_message(f"INFO: STT filtered non-speech noise: '{result.get('text', '')}'")
                return None

            if self.post_utterance_callback and result:
                self.post_utterance_callback()
            return result
        except Exception as e:
            queue_message(f"ERROR: Transcription failed: {e}")
            return None

    # === Transcription Backends ===

    def _transcribe_with_fastrtc(self):
        """Transcribe audio using FastRTC STT."""
        RATE = 16000  # FastRTC/Moonshine expects 16 kHz audio
        chunks, speech_frames = self._record_audio_chunks(sample_rate=RATE)
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
        chunks, _ = self._record_audio_chunks(sample_rate=self.SAMPLE_RATE)
        if chunks is None:
            return None

        wav_buf = self._chunks_to_wav_buffer(chunks, self.SAMPLE_RATE)
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
            chunks, _ = self._record_audio_chunks(sample_rate=self.SAMPLE_RATE)
            if chunks is None:
                return None

            wav_buf = self._chunks_to_wav_buffer(chunks, self.SAMPLE_RATE)
            files = {"audio": ("audio.wav", wav_buf, "audio/wav")}
            response = requests.post(
                f"{self.config['STT'].get('external_url')}/save_audio",
                files=files, timeout=10
            )
            if response.status_code == 200:
                transcription = response.json().get("transcription", [])
                if transcription:
                    raw_text = transcription[0].get("text", "").strip()
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

        # Record with simple RMS VAD
        detected_speech = False
        silent_frames = 0
        audio_buffer = []

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=4000, latency='high') as stream:
            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
                is_silence, detected_speech, silent_frames = self._is_silence_detected_rms(
                    data, detected_speech, silent_frames
                )
                if is_silence:
                    if not detected_speech:
                        return None
                    break
                audio_buffer.append(self.amplify_audio(data))

        if not audio_buffer:
            return None

        # Combine all audio chunks
        audio_data = np.concatenate(audio_buffer)

        # Reject near-silent recordings before sending to API
        rms = np.sqrt(np.mean(audio_data.astype(np.float64) ** 2))
        if rms < self.silence_threshold * self.silence_margin:
            return None

        # Save to temporary WAV file (OpenAI requires a file)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
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

        # Speculative transcription — kicked off when silence first starts
        spec_thread = None
        spec_result = [None]  # Mutable container for thread result
        spec_snapshot_len = 0  # How many chunks were in the snapshot

        # Preemptive LLM generation — fired when spec transcript looks like a complete sentence
        preemptive_thread = None
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

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
                is_silence, detected_speech, silent_frames = vad_func(data, detected_speech, silent_frames)

                # Pre-speech timeout: if no speech detected and silence exceeds threshold, exit early
                if not detected_speech and silent_frames >= MAX_SILENT:
                    _, clear_bar = self._get_progress_bar()
                    clear_bar()
                    return None

                if is_silence:
                    if speech_frames >= MIN_SPEECH and silent_frames >= MAX_SILENT:
                        _, clear_bar = self._get_progress_bar()
                        clear_bar()
                        break
                    # Smart Turn can signal turn-complete with fewer silent frames
                    # (it clears its audio buffer when prob > 0.5, so check that)
                    if (self.vadmethod == "smart-turn" and speech_frames >= MIN_SPEECH
                            and silent_frames >= 3 and not self.smart_turn_audio_buffer):
                        queue_message("INFO: Smart Turn detected end of turn")
                        break

                if not detected_speech:
                    pre_roll_buffer.append(data)
                    if len(pre_roll_buffer) > PRE_ROLL:
                        pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0 and pre_roll_buffer:
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
                    preemptive_thread.start()
                    queue_message(f"INFO: Preemptive LLM fired for: {spec_result[0][:60]}...")

            if speech_frames < MIN_SPEECH:
                return None

        if not audio_chunks:
            return None

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
            return None

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

        return self._emit_result(transcript, extra)

    # === Wake Word Detection ===

    def _detect_wake_word(self) -> bool:
        if not STTManager._last_status_was_sleeping:
            if self.config["STT"]["use_indicators"]:
                self.play_wav("../stt/beep_off.wav")
            print()
            queue_message(f"{self._character_name}: Sleeping...")
            STTManager._last_status_was_sleeping = True

        processors = {
            "fastrtc": self._detect_wake_word_fastrtc,
            "sherpa-onnx": self._detect_wake_word_sherpa_onnx,
        }
        wake_proc = self.config["STT"].get("wake_word_processor", "atomik")
        return processors.get(wake_proc, self._detect_wake_word_atomik)()

    def _handle_wake_detected(self):
        """Common actions after wake word is detected: beep, notify UI, send response."""
        if self.config["STT"].get("use_indicators"):
            self.play_wav("../stt/beep_on.wav")
        self._fire_and_forget_get(f"http://127.0.0.1:{self._webui_port}/start_talking")
        if self.WAKE_WORD_RESPONSES:
            wake_response = random.choice(self.WAKE_WORD_RESPONSES)
            queue_message(f"{self._character_name}: {wake_response}", stream=True)
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

        RATE = 16000
        frames_per_chunk = int(RATE * 2.0)
        self.smart_turn_audio_buffer.clear()

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
            for _ in range(100):
                if not self.running or self.shutdown_event.is_set():
                    break

                data, _ = stream.read(frames_per_chunk)
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
                    self._handle_wake_detected()
                    return True

        return False

    def _detect_wake_word_atomik(self) -> bool:
        sensitivity = float(CONFIG["STT"]["sensitivity"])
        norm = (sensitivity - 1) / 9
        curve = norm ** 1.6
        threshold = round(max(0.2, min(0.2 + curve * 0.5, 0.7)), 2)
        detector = WakeWordSystem(self.WAKE_WORD, 16000, threshold)
        detector.createModel()
        if detector.listenForWakeWord():
            self._handle_wake_detected()
            return True
        return False

    def _detect_wake_word_sherpa_onnx(self) -> bool:
        """Detect wake word using sherpa-onnx with a pre-allocated circular buffer."""
        if not self.sherpa_recognizer:
            queue_message("ERROR: sherpa-onnx recognizer not loaded for wake word detection.")
            return False

        self._fire_and_forget_get(f"http://127.0.0.1:{self._webui_port}/stop_talking")

        RATE = 16000
        frames_per_chunk = int(RATE * 2.0)
        overlap_frames = int(RATE * 0.5)
        read_frames = frames_per_chunk - overlap_frames
        wake_detected = False

        # Pre-allocate circular buffer to avoid np.concatenate memory fragmentation
        audio_buffer = np.zeros(frames_per_chunk, dtype=np.int16)

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
            # Prime buffer with first full chunk
            data, _ = stream.read(frames_per_chunk)
            audio_buffer[:] = data.flatten()

            while self.running and not self.shutdown_event.is_set():
                # Simple RMS silence gate — skip transcription when quiet to save CPU
                if self._is_quiet(audio_buffer):
                    audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                    new_data, _ = stream.read(read_frames)
                    audio_buffer[overlap_frames:] = new_data.flatten()
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
                    new_data, _ = stream.read(read_frames)
                    audio_buffer[overlap_frames:] = new_data.flatten()
                    continue
                finally:
                    del s  # Free native stream to prevent heap corruption

                if self.DEBUG and transcript:
                    queue_message(f"DEBUG: Sherpa Wake Word Transcript: '{transcript}'")

                if self.WAKE_WORD in transcript or self._fuzzy_wake_word_match(transcript, self.WAKE_WORD):
                    # Break out of the loop first — the wake response callback
                    # plays TTS audio (sd.play + sd.wait) which deadlocks if
                    # the sd.InputStream is still open.
                    wake_detected = True
                    break

                # Roll buffer: shift overlap to front, read new frames into remainder
                audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                new_data, _ = stream.read(read_frames)
                audio_buffer[overlap_frames:] = new_data.flatten()

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
            show_console = self.ui_manager.__class__.__name__ != 'UIManagerLite'

            def update(frames, max_frames):
                self.ui_manager.silence(frames)
                if show_console:
                    progress = int((frames / max_frames) * bar_length)
                    sys.stdout.write(f"\r[SILENCE: {'#' * progress}{'-' * (bar_length - progress)}] {frames}/{max_frames}")
                    sys.stdout.flush()

            def clear():
                self.ui_manager.silence(0)
                if show_console:
                    sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
                    sys.stdout.flush()

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
                sampling_rate=self.SAMPLE_RATE, threshold=0.3,
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
        rms = self._compute_rms(self.amplify_audio(data))
        if self.silence_threshold_margin is None:
            self.silence_threshold_margin = self.silence_threshold * self.silence_margin

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

    def _is_silence_detected_smart_turn(self, data, detected_speech, silent_frames):
        """Hybrid RMS + Smart Turn semantic turn detection.

        Uses RMS to detect per-frame silence, then runs the Smart Turn model
        on accumulated audio during pauses to determine if the speaker has
        finished their turn (vs just pausing mid-sentence).
        """
        update_bar, clear_bar = self._get_progress_bar()
        try:
            if self.smart_turn_session is None or self.smart_turn_extractor is None:
                return self._is_silence_detected_rms(data, detected_speech, silent_frames)

            # RMS check on current frame
            rms = self._compute_rms(self.amplify_audio(data))
            if self.silence_threshold_margin is None:
                self.silence_threshold_margin = self.silence_threshold * self.silence_margin
            if rms is None:
                return False, detected_speech, silent_frames

            if rms > self.silence_threshold_margin:
                # Speech detected — accumulate audio
                detected_speech = True
                silent_frames = 0
                self.smart_turn_audio_buffer.append(data.astype(np.float32).flatten() / 32768.0)
                clear_bar()
                return False, detected_speech, silent_frames

            # Silence detected
            silent_frames += 1
            update_bar(silent_frames, self.MAX_SILENT_FRAMES)

            # Safety fallback FIRST: force end if silence exceeds configured threshold
            # This must be checked before smart-turn to prevent runaway frame counts
            if silent_frames > self.MAX_SILENT_FRAMES:
                clear_bar()
                self.smart_turn_audio_buffer.clear()
                return True, detected_speech, silent_frames

            # Only run Smart Turn after some silence and if we have speech buffered
            if silent_frames >= 3 and detected_speech and self.smart_turn_audio_buffer:
                try:
                    audio = np.concatenate(self.smart_turn_audio_buffer)
                    # Truncate/pad to 8 seconds at 16kHz
                    max_samples = 8 * 16000
                    if len(audio) > max_samples:
                        audio = audio[-max_samples:]  # Keep most recent 8s

                    # Extract mel features
                    inputs = self.smart_turn_extractor(
                        audio, sampling_rate=16000, return_tensors="np",
                        padding="max_length", max_length=max_samples,
                        truncation=True, do_normalize=True
                    )
                    # Run inference
                    outputs = self.smart_turn_session.run(None, {
                        "input_features": inputs.input_features.astype(np.float32)
                    })
                    probability = outputs[0][0].item()

                    if self.DEBUG:
                        queue_message(f"DEBUG: Smart Turn probability: {probability:.3f}")
                    if probability > 0.5:
                        # Turn is complete
                        clear_bar()
                        self.smart_turn_audio_buffer.clear()
                        return True, detected_speech, silent_frames
                except Exception as e:
                    queue_message(f"WARNING: Smart Turn inference error: {e}")

            return False, detected_speech, silent_frames

        except Exception as e:
            queue_message(f"WARNING: Smart Turn VAD error, falling back to RMS: {e}")
            self.smart_turn_audio_buffer.clear()
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    # === Background Noise Measurement ===

    def _measure_background_noise(self):
        """Measure background noise and set the silence threshold."""
        queue_message("INFO: Measuring background noise...")
        rms_values = []

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
            for _ in range(20):
                data, _ = stream.read(4000)
                rms = self._compute_rms(data)
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
            self.silence_threshold_margin = self.silence_threshold * self.silence_margin
            db = 20 * np.log10(self.silence_threshold)
            queue_message(f"INFO: Silence threshold: {db:.2f} dB and {self.silence_threshold}")
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
        Uses speech recognition to detect words NOT in the TTS response,
        which means a human is speaking over TARS.

        Uses a sliding window over the TTS text synced to estimated playback
        position to aggressively filter out speaker bleed.

        Args:
            tts_text: The text TARS is currently saying, used to filter out
                      words that are just echo/bleed from the speaker.
        """
        if self.silence_threshold is None:
            return  # Can't monitor without a noise floor
        if self.sherpa_recognizer is None:
            queue_message("WARN: Barge-in requires sherpa-onnx recognizer, skipping")
            return
        self._bargein_active = True

        # Build ordered word list for sliding window + full set for broad matching
        tts_word_list = []
        tts_words_all = set()
        if tts_text:
            cleaned = _NON_ALNUM_SPACE_RE.sub('', tts_text.lower())
            tts_word_list = cleaned.split()
            tts_words_all = set(tts_word_list)

        def _monitor():
            from modules.module_tts import stop_tts_playback
            bargein_threshold = self.silence_threshold * self.silence_margin
            audio_buf = []
            TRANSCRIBE_EVERY = 8  # Transcribe every ~1s (8 x 125ms frames)
            frame_count = 0
            start_time = time.time()
            WORDS_PER_SEC = 3.0  # Estimated TTS speaking rate
            WINDOW_PAD = 4       # Extra words before/after estimated position

            try:
                with sd.InputStream(samplerate=16000, channels=1, dtype="int16") as stream:
                    while self._bargein_active:
                        data, _ = stream.read(2000)  # ~125ms frame
                        frame_count += 1

                        # Always collect audio with speech energy
                        rms = self._compute_rms(self.amplify_audio(data))
                        if rms and rms > bargein_threshold:
                            audio_buf.append(data.copy())

                        # Periodically transcribe what we've collected
                        if frame_count % TRANSCRIBE_EVERY == 0 and len(audio_buf) >= 2:
                            transcript = self._bargein_transcribe(audio_buf)
                            audio_buf.clear()
                            if transcript:
                                # Build sliding window of TTS words near current playback position
                                elapsed = time.time() - start_time
                                pos = int(elapsed * WORDS_PER_SEC)
                                win_start = max(0, pos - WINDOW_PAD)
                                win_end = min(len(tts_word_list), pos + WINDOW_PAD + 1)
                                window_words = set(tts_word_list[win_start:win_end])

                                novel = self._find_novel_words(transcript, tts_words_all, window_words)
                                if self.DEBUG:
                                    queue_message(f"DEBUG: Barge-in: '{transcript}' window={window_words} novel={novel}")
                                if novel:
                                    queue_message(f"INFO: Barge-in detected! Heard: '{transcript}' (novel: {novel})")
                                    stop_tts_playback()
                                    break
            except Exception as e:
                queue_message(f"WARN: Barge-in monitor error: {e}")

        self._bargein_thread = threading.Thread(target=_monitor, daemon=True)
        self._bargein_thread.start()

    def _bargein_transcribe(self, audio_buffer):
        """Quick transcription of buffered audio for barge-in detection."""
        try:
            audio_data = self._chunks_to_float32(audio_buffer)
            s = self.sherpa_recognizer.create_stream()
            s.accept_waveform(16000, audio_data)
            self.sherpa_recognizer.decode_stream(s)
            transcript = _SENSEVOICE_TAG_RE.sub('', s.result.text.strip()).strip()
            del s
            return transcript or None
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
            if w in _BARGEIN_NOISE_WORDS or len(w) <= 2 or w in tts_words_all:
                continue

            matched = False
            # Check substring containment (catches "under" in "underway", etc.)
            for tts_w in tts_words_all:
                if w in tts_w or tts_w in w:
                    matched = True
                    break

            # Broad fuzzy match against all TTS words
            if not matched:
                for tts_w in tts_words_all:
                    if SequenceMatcher(None, w, tts_w).ratio() >= 0.5:
                        matched = True
                        break

            # Aggressive fuzzy match against sliding window words (currently being spoken)
            # Speaker bleed produces heavily distorted transcriptions
            if not matched and window_words:
                for tts_w in window_words:
                    if SequenceMatcher(None, w, tts_w).ratio() >= 0.35:
                        matched = True
                        break
                    # Shared prefix match (3+ chars) — catches "mind"/"mine", "under"/"until"
                    if len(w) >= 3 and len(tts_w) >= 3 and w[:3] == tts_w[:3]:
                        matched = True
                        break

            if not matched:
                novel.append(w)

        # Require at least 2 novel words — single novel words are almost always
        # mis-transcribed speaker bleed
        return novel if len(novel) >= 2 else []

    def stop_bargein_monitor(self):
        """Stop the barge-in monitor thread."""
        self._bargein_active = False
        if self._bargein_thread is not None:
            self._bargein_thread.join(timeout=2)
            self._bargein_thread = None
