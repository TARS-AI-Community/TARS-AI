#!/usr/bin/env python3
"""
module_stt.py

Speech-to-Text (STT) Module for TARS-AI Application.

This module integrates both local and server-based transcription, wake word detection,
and voice command handling. It supports custom callbacks to trigger actions upon
detecting speech or specific keywords.
"""

import os
import re
import random
import threading
import time
import wave
import json
import sys
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

# Conditional heavy imports based on device capabilities
torch = None
torchaudio = None
librosa = None
get_stt_model = None
Model = None
OpenAI = None
WakeWordSystem = None

# Torch and related (Pi5 only for Silero VAD)
if CAPABILITIES is None or CAPABILITIES.can_use_embeddings:
    try:
        import torch as _torch
        torch = _torch
    except ImportError:
        pass
    
    try:
        import torchaudio as _torchaudio
        torchaudio = _torchaudio
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
sherpa_onnx = None
if CAPABILITIES is None or (CAPABILITIES.allowed_stt and "sherpa-onnx" in CAPABILITIES.allowed_stt):
    try:
        import sherpa_onnx as _sherpa_onnx
        sherpa_onnx = _sherpa_onnx
    except ImportError:
        pass

# Pre-compiled regex for stripping SenseVoice tags (language: <|en|>, emotion: <|HAPPY|>, event: <|Speech|>, etc.)
_SENSEVOICE_TAG_RE = re.compile(r'<\|[A-Za-z]+\|>')

# Suppress parallelism warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Global STT manager instance
_stt_manager_instance = None

def get_stt_manager():
    """Get the global STT manager instance."""
    global _stt_manager_instance
    return _stt_manager_instance

class STTManager:
    """
    Manages Speech-to-Text processing for TARS-AI.
    """

    WAKE_WORD_RESPONSES = [
        "Oh! You called?",
        "Took you long enough. Yes?",
        "Finally!",
    ]
    
    try:
        responses_config = CONFIG["CHAR"]['responses']
        if responses_config and responses_config.strip() and responses_config.strip() != '[]':
            parsed = json.loads(responses_config)
            if isinstance(parsed, list) and len(parsed) > 0:
                WAKE_WORD_RESPONSES = parsed
    except (json.JSONDecodeError, Exception) as e:
        pass


    def __init__(self, config, shutdown_event: threading.Event, ui_manager, amp_gain: float = 4.0):
        """
        Initialize the STTManager.

        Args:
            config (dict): Configuration dictionary.
            shutdown_event (threading.Event): Event to signal when to stop.
            amp_gain (float): Amplification gain for audio data.
        """
        global _stt_manager_instance
        _stt_manager_instance = self  # Set global instance
        
        self.ui_manager = ui_manager
        self.config = config
        self.shutdown_event = shutdown_event
        self.running = False
        
        # Pause/resume functionality for video playback
        self.paused = False
        self.cancelled = False
        self.pause_lock = threading.Lock()

        # Audio settings - Set sample rate based on VAD configuration
        if self.config["STT"].get("vad_enabled", False):
            # If VAD is enabled, force 16000 Hz sample rate
            self.SAMPLE_RATE = 16000
            self.DEFAULT_SAMPLE_RATE = 16000
            queue_message("INFO: Using 16000 Hz sample rate for VAD compatibility")
        else:
            # If VAD is disabled, use system default
            self.DEFAULT_SAMPLE_RATE = 16000
            self.SAMPLE_RATE = self.find_default_mic_sample_rate()

        self.amp_gain = amp_gain  # Microphone amplification multiplier
        self.silence_margin = 3.5  # Noise floor multiplier
        self.wake_silence_threshold = None
        self.silence_threshold = None  # Updated after measuring background noise
        self.MAX_RECORDING_FRAMES = 100   # ~12.5 seconds
        self.MAX_SILENT_FRAMES = CONFIG['STT']['speechdelay']
        
        # Callbacks
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.post_utterance_callback: Optional[Callable[[], None]] = None

        # Wake word and model settings
        self.WAKE_WORD = config.get("STT", {}).get("wake_word", "hey tar").lower()
        self.fastrtc_model = None
        self.silero_model = None  # For Silero STT (if used)
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

        self._initialize_models()
        self.vadmethod = CONFIG['STT']['vad_method']
        self.DEBUG = False

        # Cache progress bar and threshold margin so they aren't recreated per frame
        self._progress_bar_funcs = None
        self.silence_threshold_margin = None

    def _initialize_models(self):
        """Measure background noise and load the selected STT model."""
        self._measure_background_noise()
        stt_processor = self.config.get("STT", {}).get("stt_processor", "fastrtc")

        if stt_processor == "fastrtc":
            self._load_fastrtc_model()
        elif stt_processor == "silero":
            self._load_silero_model()
        elif stt_processor == "sherpa-onnx":
            self._load_sherpa_onnx_model()

        # Wake word processor initialization
        wake_word_processor = self.config["STT"].get("wake_word_processor", "atomik")
        if wake_word_processor == "fastrtc" and not self.fastrtc_model:
            self._load_fastrtc_model()
        elif wake_word_processor == "atomik":
            self._load_atomik_model()
        elif wake_word_processor == "sherpa-onnx" and not self.sherpa_recognizer:
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

    def start(self):
        """Start the STT processing loop in a separate thread."""
        self.running = True
        self.thread = threading.Thread(
            target=self._stt_processing_loop, name="STTThread", daemon=True
        )
        self.thread.start()

    def stop(self):
        """Stop the STT processing loop."""
        self.running = False
        self.shutdown_event.set()
        self.thread.join(timeout=3)
    
    def pause(self):
        """Pause STT processing (e.g., during video playback or servo movement)."""
        with self.pause_lock:
            self.paused = True

    def cancel(self):
        """Pause STT and flag in-flight LLM/TTS to be discarded."""
        with self.pause_lock:
            self.paused = True
            self.cancelled = True

    def resume(self):
        """Resume STT processing."""
        with self.pause_lock:
            self.paused = False

    def is_paused(self):
        """Check if STT is currently paused."""
        with self.pause_lock:
            return self.paused

    def is_cancelled(self):
        """Check and clear the cancellation flag (one-shot)."""
        with self.pause_lock:
            was = self.cancelled
            self.cancelled = False
            return was

    # === Model Loading Methods ===

    def _load_atomik_model(self):
        if WakeWordSystem is None:
            queue_message("WARNING: Atomik wake word not available")
            return
        detector = WakeWordSystem(self.WAKE_WORD)
        detector.createModel()

    def _load_silero_model(self):
        """Load Silero STT model via Torch Hub into the stt folder (without a hub subfolder)."""
        if torch is None:
            queue_message("WARNING: Silero STT not available (torch not installed)")
            return
            
        try:
            # Go one level up from the current directory
            parent_dir = os.path.dirname(os.getcwd())
            stt_folder = os.path.join(parent_dir, "stt")
            os.makedirs(stt_folder, exist_ok=True)
            # Override torch.hub.get_dir to return stt_folder directly.
            import torch.hub
            torch.hub.get_dir = lambda: stt_folder

            self.silero_model, self.decoder, self.utils = torch.hub.load(
                "snakers4/silero-models", model="silero_stt", language="en", device="cpu"
            )
            (
                self.read_batch,
                self.split_into_batches,
                self.read_audio,
                self.prepare_model_input,
            ) = self.utils
            queue_message("INFO: Silero model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load Silero model: {e}")

    def _load_silero_vad(self):
        """
        Load the Silero VAD model using the pip package and optional ONNX support.
        This loads the get_speech_timestamps function (instead of get_speech_ts).
        """
        if torch is None:
            queue_message("WARNING: Silero VAD not available (torch not installed)")
            return
            
        # You can set these values as needed.
        USE_PIP = True  # download model using pip package
        USE_ONNX = False

        if USE_PIP:
            try:
                from silero_vad import load_silero_vad, get_speech_timestamps
                self.silero_vad_model = load_silero_vad(onnx=USE_ONNX)
                self.get_speech_timestamps = get_speech_timestamps
                queue_message("INFO: Silero VAD loaded successfully using pip package.")
            except Exception as e:
                queue_message(f"ERROR: Failed to load Silero VAD with pip: {e}")
        else:
            try:
                self.silero_vad_model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=True,
                    onnx=USE_ONNX
                )
                (get_speech_timestamps,
                 save_audio,
                 read_audio,
                 VADIterator,
                 collect_chunks) = utils
                self.get_speech_timestamps = get_speech_timestamps
                queue_message("INFO: Silero VAD loaded successfully using torch.hub.")
            except Exception as e:
                queue_message(f"ERROR: Failed to load Silero VAD with torch.hub: {e}")

    def _load_fastrtc_model(self):
        """
        Initialize FastRTC STT model.
        """
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
        """Load sherpa-onnx SenseVoiceTiny model for STT."""
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available (not installed)")
            return

        try:
            model_path = self.config.get("STT", {}).get(
                "sherpa_onnx_model_path", "stt/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
            )
            if not os.path.isabs(model_path):
                model_path = os.path.join(os.path.dirname(os.getcwd()), model_path)

            model_file = os.path.join(model_path, "model.int8.onnx")
            tokens_file = os.path.join(model_path, "tokens.txt")

            if not os.path.exists(model_file):
                queue_message(f"ERROR: SenseVoiceTiny model not found at {model_file}")
                queue_message("INFO: Download from https://github.com/k2-fsa/sherpa-onnx/releases (sherpa-onnx-sense-voice)")
                return

            # Use more threads on Pi5 (4 cores) vs Pi4 (4 cores but less headroom)
            pi_version = self.config.get("_device", {}).get("raspberry_version", "pi5")
            threads = 4 if pi_version == "pi5" else 2

            self.sherpa_recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_file,
                tokens=tokens_file,
                num_threads=threads,
                use_itn=True,
                debug=False,
            )
            queue_message("INFO: sherpa-onnx SenseVoiceTiny model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx model: {e}")
            self.sherpa_recognizer = None

    def _load_sherpa_vad(self):
        """Load sherpa-onnx Silero VAD model (no torch required)."""
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for VAD")
            return

        try:
            # Look for silero_vad.onnx in the stt directory
            stt_dir = os.path.join(os.path.dirname(os.getcwd()), "stt")
            model_path = os.path.join(stt_dir, "silero_vad.onnx")

            if not os.path.exists(model_path):
                queue_message(f"ERROR: Silero VAD ONNX model not found at {model_path}")
                queue_message("INFO: Download from https://github.com/k2-fsa/sherpa-onnx/releases (silero_vad.onnx)")
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
        """Load sherpa-onnx speech denoiser (GTCRN model)."""
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for denoising")
            return

        try:
            stt_dir = os.path.join(os.path.dirname(os.getcwd()), "stt")
            model_path = os.path.join(stt_dir, "gtcrn_simple.onnx")

            if not os.path.exists(model_path):
                queue_message(f"ERROR: Denoiser model not found at {model_path}")
                queue_message("INFO: Download gtcrn_simple.onnx from sherpa-onnx releases")
                return

            gtcrn_config = sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=model_path)
            model_config = sherpa_onnx.OfflineSpeechDenoiserModelConfig(gtcrn=gtcrn_config)
            denoiser_config = sherpa_onnx.OfflineSpeechDenoiserConfig(model=model_config)
            self.sherpa_denoiser = sherpa_onnx.OfflineSpeechDenoiser(config=denoiser_config)
            queue_message("INFO: sherpa-onnx speech denoiser loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx denoiser: {e}")
            self.sherpa_denoiser = None

    def _load_sherpa_punctuation(self):
        """Load sherpa-onnx punctuation restoration model."""
        if sherpa_onnx is None:
            queue_message("WARNING: sherpa-onnx not available for punctuation")
            return

        try:
            stt_dir = os.path.join(os.path.dirname(os.getcwd()), "stt")
            model_dir = os.path.join(stt_dir, "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12")

            if not os.path.isdir(model_dir):
                queue_message(f"ERROR: Punctuation model not found at {model_dir}")
                queue_message("INFO: Download from sherpa-onnx releases (punct-ct-transformer)")
                return

            model_path = os.path.join(model_dir, "model.onnx")
            config = sherpa_onnx.OfflinePunctuationModelConfig(
                ct_transformer=model_path
            )
            punct_config = sherpa_onnx.OfflinePunctuationConfig(model=config)
            self.sherpa_punctuator = sherpa_onnx.OfflinePunctuation(punct_config)
            queue_message("INFO: sherpa-onnx punctuation model loaded successfully.")
        except Exception as e:
            queue_message(f"ERROR: Failed to load sherpa-onnx punctuation: {e}")
            self.sherpa_punctuator = None

    def _load_smart_turn(self):
        """Load Pipecat Smart Turn v3.2 ONNX model for semantic turn detection."""
        try:
            import onnxruntime as ort
            from transformers import WhisperFeatureExtractor

            stt_dir = os.path.join(os.path.dirname(os.getcwd()), "stt")
            model_path = os.path.join(stt_dir, "smart-turn-v3.2-cpu.onnx")

            if not os.path.isfile(model_path):
                queue_message(f"ERROR: Smart Turn model not found at {model_path}")
                queue_message("INFO: Download from huggingface.co/pipecat-ai/smart-turn-v3")
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

    def _denoise_audio(self, audio_data, sample_rate=16000):
        """Denoise audio using sherpa-onnx GTCRN model. Input: float32 array. Returns: float32 array."""
        if self.sherpa_denoiser is None:
            return audio_data
        try:
            result = self.sherpa_denoiser.run(audio_data.tolist(), sample_rate)
            return np.array(result.samples, dtype=np.float32)
        except Exception as e:
            queue_message(f"WARNING: Denoising failed, using original audio: {e}")
            return audio_data

    def _add_punctuation(self, text):
        """Add punctuation to transcribed text using sherpa-onnx."""
        if self.sherpa_punctuator is None or not text:
            return text
        try:
            return self.sherpa_punctuator.add_punctuation(text)
        except Exception as e:
            queue_message(f"WARNING: Punctuation restoration failed: {e}")
            return text

    # === Transcription Methods ===

    def _transcribe_utterance(self):
        """Transcribe the user's utterance using the selected STT processor."""
        try:
            # Skip if paused
            if self.is_paused():
                return None
            
            processor = self.config["STT"].get("stt_processor", "fastrtc")  # Default to fastrtc
            #queue_message(f"DEBUG: Selected STT processor: {processor}")

            if processor == "fastrtc":
                result = self._transcribe_with_fastrtc()
            elif processor == "silero":
                result = self._transcribe_silero()
            elif processor == "external":
                result = self._transcribe_with_server()
            elif processor == "openai":
                result = self._transcribe_with_openAi()
            elif processor == "sherpa-onnx":
                result = self._transcribe_with_sherpa_onnx()
            else:
                queue_message(f"WARNING: Unknown STT processor '{processor}', falling back to FastRTC")
                result = self._transcribe_with_fastrtc()

            if self.post_utterance_callback and result:
                self.post_utterance_callback()
            return result
        except Exception as e:
            queue_message(f"ERROR: Transcription failed: {e}")
            return None

    def _transcribe_with_fastrtc(self):
        """Transcribe audio using FastRTC STT with improved speech detection."""
        FASTRTC_RATE = 16000  # FastRTC/Moonshine expects 16 kHz audio
        audio_buffer = BytesIO()
        detected_speech = False
        silent_frames = 0
        speech_frames = 0
        pre_roll_buffer = []
        PRE_ROLL_FRAMES = 10
        MIN_SPEECH_FRAMES = 5
        MAX_SILENT_FRAMES = 20

        with sd.InputStream(
            samplerate=FASTRTC_RATE, channels=1, dtype="int16"
        ) as stream, wave.open(audio_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(FASTRTC_RATE)

            for frame_idx in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)

                is_silence, detected_speech, silent_frames = self.voice_activity_detection_main(
                    data, detected_speech, silent_frames
                )
                silent_frames = min(silent_frames, MAX_SILENT_FRAMES)

                # Add the same early exit check as other functions
                if is_silence:
                    if not detected_speech:
                        return None  # Exit early if silence detected before any speech
                    # If speech was detected, check if we should stop recording
                    if speech_frames >= MIN_SPEECH_FRAMES and silent_frames >= MAX_SILENT_FRAMES:
                        print()
                        break

                if not detected_speech:
                    pre_roll_buffer.append(data.tobytes())
                    if len(pre_roll_buffer) > PRE_ROLL_FRAMES:
                        pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0:
                        for pre_roll_data in pre_roll_buffer:
                            wf.writeframes(pre_roll_data)
                        pre_roll_buffer = []

                    wf.writeframes(data.tobytes())

                    if not is_silence:
                        speech_frames += 1

            if speech_frames < MIN_SPEECH_FRAMES:
                return None

        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0:
            return None

        audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")

        # Resample to 16 kHz if needed (safety net)
        if sample_rate != FASTRTC_RATE and librosa is not None:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=FASTRTC_RATE)

        audio_max = np.abs(audio_data).max()
        if audio_max < 0.1:
            audio_data = audio_data * (0.3 / max(audio_max, 0.001))

        audio_data = np.clip(audio_data, -1.0, 1.0)

        transcript = self.fastrtc_model.stt((FASTRTC_RATE, audio_data)).strip()

        if transcript:
            formatted_result = {"text": transcript}
            if self.utterance_callback:
                self.utterance_callback(json.dumps(formatted_result))
            return formatted_result
        else:
            return None
        
        
    def _transcribe_with_sherpa_onnx(self):
        """Transcribe audio using sherpa-onnx SenseVoiceTiny."""
        if not self.sherpa_recognizer:
            queue_message("ERROR: sherpa-onnx recognizer not loaded.")
            return None

        SHERPA_RATE = 16000
        detected_speech = False
        silent_frames = 0
        speech_frames = 0
        pre_roll_buffer = []
        audio_chunks = []
        PRE_ROLL_FRAMES = 10
        MIN_SPEECH_FRAMES = 5
        MAX_SILENT_FRAMES = 20

        with sd.InputStream(
            samplerate=SHERPA_RATE, channels=1, dtype="int16"
        ) as stream:
            for frame_idx in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)

                is_silence, detected_speech, silent_frames = self.voice_activity_detection_main(
                    data, detected_speech, silent_frames
                )
                silent_frames = min(silent_frames, MAX_SILENT_FRAMES)

                if is_silence:
                    if not detected_speech:
                        return None
                    if speech_frames >= MIN_SPEECH_FRAMES and silent_frames >= MAX_SILENT_FRAMES:
                        break

                if not detected_speech:
                    pre_roll_buffer.append(data)
                    if len(pre_roll_buffer) > PRE_ROLL_FRAMES:
                        pre_roll_buffer.pop(0)
                else:
                    if speech_frames == 0:
                        audio_chunks.extend(pre_roll_buffer)
                        pre_roll_buffer = []

                    audio_chunks.append(data)

                    if not is_silence:
                        speech_frames += 1

            if speech_frames < MIN_SPEECH_FRAMES:
                return None

        if not audio_chunks:
            return None

        # Convert directly to float32 — no WAV roundtrip needed
        audio_data = np.concatenate(audio_chunks).astype(np.float32) / 32768.0
        audio_data = audio_data.flatten()

        # Denoise if enabled
        audio_data = self._denoise_audio(audio_data, SHERPA_RATE)

        try:
            s = self.sherpa_recognizer.create_stream()
            s.accept_waveform(SHERPA_RATE, audio_data)
            self.sherpa_recognizer.decode_stream(s)
            transcript = s.result.text.strip()
            # Strip SenseVoice language tags like <|en|>, <|zh|>, etc.
            transcript = _SENSEVOICE_TAG_RE.sub('', transcript).strip()
            # Add punctuation if enabled
            transcript = self._add_punctuation(transcript)
            del s  # Free native stream to prevent heap corruption
        except Exception as e:
            queue_message(f"ERROR: sherpa-onnx transcription failed: {e}")
            return None

        if transcript:
            formatted_result = {"text": transcript}
            if self.utterance_callback:
                self.utterance_callback(json.dumps(formatted_result))
            return formatted_result
        else:
            return None

    def _transcribe_with_openAi(self):
        """Transcribe and translate audio using OpenAI's Whisper API."""

        language = CONFIG['STT']['language']
        client = OpenAI(api_key=CONFIG["TTS"]["openai_api_key"])

        detected_speech = False
        silent_frames = 0
        audio_buffer = []  # Store audio chunks

        with sd.InputStream(samplerate=self.SAMPLE_RATE,
                            channels=1, dtype="int16",
                            blocksize=4000, latency='high') as stream:
            for _ in range(self.MAX_RECORDING_FRAMES):  # Limit recording duration
                data, _ = stream.read(4000)

                is_silence, detected_speech, silent_frames = self._is_silence_detected_rms(
                    data, detected_speech, silent_frames
                )

                if is_silence:
                    if not detected_speech:
                        return None
                    break

                # Amplify and store audio data
                data = self.amplify_audio(data)
                audio_buffer.append(data)

        if not audio_buffer:
            return None

        # Combine all audio chunks
        audio_data = np.concatenate(audio_buffer)

        # Reject near-silent recordings before sending to API
        rms = np.sqrt(np.mean(audio_data.astype(np.float64) ** 2))
        if rms < self.silence_threshold * self.silence_margin:
            return None

        # Save to temporary WAV file (OpenAI requires a file)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            with wave.open(temp_audio.name, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())

            # Transcribe with OpenAI Whisper (verbose_json gives no_speech_prob)
            try:
                with open(temp_audio.name, 'rb') as audio_file:
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json"
                    )
            finally:
                # Clean up temp file
                os.unlink(temp_audio.name)

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
        if language and language.lower() not in ["english", "anglais"]:
            translation = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Translate the following text to {language}. Only provide the translation, nothing else."},
                    {"role": "user", "content": transcription}
                ]
            )
            result_text = translation.choices[0].message.content
        else:
            result_text = transcription

        # Format result to match your existing format
        formatted_result = {"text": result_text}

        # Call utterance callback if it exists
        if self.utterance_callback:
            self.utterance_callback(json.dumps(formatted_result))

        return formatted_result

    def _transcribe_silero(self):
        """Transcribe audio using Silero STT."""
        audio_buffer = BytesIO()
        detected_speech = False
        silent_frames = 0

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE, channels=1, dtype="int16", blocksize=4000
        ) as stream, wave.open(audio_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)

            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
                

                is_silence, detected_speech, silent_frames = self.voice_activity_detection_main(data, detected_speech, silent_frames)
                if is_silence:
                    if not detected_speech:
                        return None
                    break
                
                #write the audio data
                wf.writeframes(data.tobytes())
    
        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0:
            queue_message("ERROR: No audio recorded.")
            return None

        # Convert recorded audio for STT model
        audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")
        if sample_rate != self.DEFAULT_SAMPLE_RATE:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=self.DEFAULT_SAMPLE_RATE)
            #queue_message("INFO: Resampled Audio.")

        # Run STT Model
        input_audio = self.prepare_model_input([torch.tensor(audio_data)], device="cpu")
        silero_output = self.silero_model(input_audio)[0]
        decoded_text = self.decoder(silero_output.cpu())

        # Return transcription result
        if decoded_text:
            formatted_result = {"text": decoded_text}
            if self.utterance_callback:
                self.utterance_callback(json.dumps(formatted_result))
            return formatted_result

    def _transcribe_with_server(self):
        """Transcribe audio by sending it to an external server."""
        try:
            audio_buffer = BytesIO()
            silent_frames = 0
            detected_speech = False

            with sd.InputStream(
                samplerate=self.SAMPLE_RATE, channels=1, dtype="int16"
            ) as stream, wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                for _ in range(self.MAX_RECORDING_FRAMES):
                    data, _ = stream.read(4000)


                    is_silence, detected_speech, silent_frames = self.voice_activity_detection_main(data, detected_speech, silent_frames)
                    if is_silence:
                        if not detected_speech:
                            return None
                        break

                    wf.writeframes(data.tobytes())

            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                queue_message("ERROR: No audio recorded for server transcription.")
                return None

            files = {"audio": ("audio.wav", audio_buffer, "audio/wav")}
            response = requests.post(
                f"{self.config['STT'].get('external_url')}/save_audio",
                files=files, timeout=10
            )
            if response.status_code == 200:
                transcription = response.json().get("transcription", [])
                if transcription:
                    raw_text = transcription[0].get("text", "").strip()
                    formatted_result = {
                        "text": raw_text,
                        "result": [
                            {
                                "conf": 1.0,
                                "start": seg.get("start", 0),
                                "end": seg.get("end", 0),
                                "word": seg.get("text", ""),
                            }
                            for seg in transcription
                        ],
                    }
                    if self.utterance_callback:
                        self.utterance_callback(json.dumps(formatted_result))
                    return formatted_result
        except requests.RequestException as e:
            queue_message(f"ERROR: Server transcription request failed: {e}")
        return None

    # === Helper Methods ===

    def _stt_processing_loop(self):
        """Main loop that detects the wake word and transcribes utterances."""
        queue_message("INFO: Starting STT processing loop...")
        while self.running and not self.shutdown_event.is_set():
            # Skip processing if paused (e.g., during video playback)
            if self.is_paused():
                time.sleep(0.1)  # Sleep while paused to avoid busy waiting
                continue
            
            if self._detect_wake_word():
                # Reset sherpa VAD state to prevent heap corruption from stale native buffers
                if self.sherpa_vad is not None:
                    self.sherpa_vad.reset()
                # Check again if paused before transcribing
                if not self.is_paused():
                    self._transcribe_utterance()
        queue_message("INFO: STT Manager stopped.")

    def _detect_wake_word(self) -> bool:
        if self.config["STT"]["use_indicators"]:
            self.play_wav("../stt/beep_off.wav")

        character_path = self.config.get("CHAR", {}).get("character_card_path")
        character_name = os.path.splitext(os.path.basename(character_path))[0] if character_path else "TARS"
        queue_message(f"{character_name}: Sleeping...")

        wake_word_processor = self.config["STT"].get("wake_word_processor", "atomik")
        if wake_word_processor == "fastrtc":
            return self._detect_wake_word_fastrtc()
        elif wake_word_processor == "sherpa-onnx":
            return self._detect_wake_word_sherpa_onnx()
        else:
            return self._detect_wake_word_atomik()

    def _detect_wake_word_fastrtc(self) -> bool:
        """
        Detect the wake word using FastRTC STT by transcribing short audio chunks.
        """
        if not self.fastrtc_model:
            queue_message("ERROR: FastRTC model not loaded for wake word detection.")
            return False

        try:
            requests.get(f"http://127.0.0.1:{CONFIG['UI'].get('webui_port', 80)}/stop_talking", timeout=1)
        except Exception:
            pass

        FASTRTC_RATE = 16000  # FastRTC/Moonshine expects 16 kHz audio
        chunk_duration = 2.0  # Process 2-second chunks
        frames_per_chunk = int(FASTRTC_RATE * chunk_duration)
        silent_frames = 0
        max_iterations = 100  # Prevent infinite loops

        with sd.InputStream(samplerate=FASTRTC_RATE, channels=1, dtype="int16") as stream:
            for iteration in range(max_iterations):
                if not self.running or self.shutdown_event.is_set():
                    break

                # Read a short audio chunk
                data, _ = stream.read(frames_per_chunk)
                data = self.amplify_audio(data)  # Apply amplification

                # Check for silence
                is_silence, _, silent_frames = self.voice_activity_detection_main(data, False, silent_frames)
                if is_silence:
                    silent_frames += 1
                    if silent_frames > self.MAX_SILENT_FRAMES:
                        queue_message("DEBUG: Silence timeout reached in FastRTC wake word detection.")
                        break
                    continue
                else:
                    silent_frames = 0

                # Convert to format expected by FastRTC (float32)
                audio_data = data.astype(np.float32) / 32768.0
                # Ensure 1D array: flatten from (44100,) to [44100]
                audio_data = audio_data.flatten()
                #queue_message(f"DEBUG: audio_data shape: {audio_data.shape}, sample_rate: {self.SAMPLE_RATE}")

                try:
                    transcript = self.fastrtc_model.stt((FASTRTC_RATE, audio_data)).strip().lower()
                except Exception as e:
                    queue_message(f"ERROR: FastRTC STT failed: {e}")
                    continue

                if self.DEBUG:
                    queue_message(f"DEBUG: FastRTC Wake Word Transcript: '{transcript}'")

                if self.WAKE_WORD in transcript:
                    if self.config["STT"].get("use_indicators"):
                        self.play_wav("../stt/beep_on.wav")
                    try:
                        requests.get(f"http://127.0.0.1:{CONFIG['UI'].get('webui_port', 80)}/start_talking", timeout=1)
                    except Exception:
                        pass
                    if self.WAKE_WORD_RESPONSES and len(self.WAKE_WORD_RESPONSES) > 0:
                        wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                        character_name = os.path.splitext(os.path.basename(
                            self.config.get("CHAR", {}).get("character_card_path", "TARS")
                        ))[0]
                        queue_message(f"{character_name}: {wake_response}", stream=True)
                        if self.wake_word_callback:
                            self.wake_word_callback(wake_response)
                    return True

        return False
    

    def _detect_wake_word_atomik(self) -> bool:
        sensitivity = float(CONFIG["STT"]["sensitivity"]) 
        norm = (sensitivity - 1) / 9
        curve = norm ** 1.6
        threshold = 0.2 + curve * (0.7 - 0.2)
        threshold = round(max(0.2, min(threshold, 0.7)), 2)
        #print("Atomik sensitivity:", threshold)
        detector = WakeWordSystem(self.WAKE_WORD, 16000, threshold)
        detector.createModel()
        if detector.listenForWakeWord():
            if self.config["STT"].get("use_indicators"):
                self.play_wav("../stt/beep_on.wav")
            try:
                requests.get(f"http://127.0.0.1:{CONFIG['UI'].get('webui_port', 80)}/start_talking", timeout=1)
            except Exception:
                pass
            if self.WAKE_WORD_RESPONSES and len(self.WAKE_WORD_RESPONSES) > 0:
                wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                character_name = os.path.splitext(os.path.basename(
                    self.config.get("CHAR", {}).get("character_card_path", "TARS")
                ))[0]
                queue_message(f"{character_name}: {wake_response}", stream=True)
                if self.wake_word_callback:
                    self.wake_word_callback(wake_response)
            return True
        

    @staticmethod
    def _fuzzy_wake_word_match(transcript: str, wake_word: str, threshold: float = 0.6) -> bool:
        """Check if transcript contains a fuzzy match for the wake word."""
        wake_words = wake_word.split()
        transcript_words = transcript.split()

        if len(transcript_words) < len(wake_words):
            return False

        # Slide a window of wake_word length across transcript words
        for i in range(len(transcript_words) - len(wake_words) + 1):
            window = transcript_words[i:i + len(wake_words)]
            matches = 0
            for tw, ww in zip(window, wake_words):
                ratio = SequenceMatcher(None, tw, ww).ratio()
                if ratio >= threshold:
                    matches += 1
            if matches == len(wake_words):
                return True

        return False

    @staticmethod
    def _fire_and_forget_get(url):
        """Non-blocking HTTP GET — runs in a daemon thread."""
        threading.Thread(target=lambda: requests.get(url, timeout=1), daemon=True).start()

    def _detect_wake_word_sherpa_onnx(self) -> bool:
        """Detect wake word using sherpa-onnx with a pre-allocated circular buffer."""
        if not self.sherpa_recognizer:
            queue_message("ERROR: sherpa-onnx recognizer not loaded for wake word detection.")
            return False

        try:
            self._fire_and_forget_get(f"http://127.0.0.1:{CONFIG['UI'].get('webui_port', 80)}/stop_talking")
        except Exception:
            pass

        SHERPA_RATE = 16000
        chunk_duration = 2.0
        overlap_duration = 0.5
        frames_per_chunk = int(SHERPA_RATE * chunk_duration)
        overlap_frames = int(SHERPA_RATE * overlap_duration)
        read_frames = frames_per_chunk - overlap_frames
        silent_frames = 0

        # Pre-allocate circular buffer to avoid np.concatenate memory fragmentation
        audio_buffer = np.zeros(frames_per_chunk, dtype=np.int16)

        with sd.InputStream(samplerate=SHERPA_RATE, channels=1, dtype="int16") as stream:
            # Prime buffer with first full chunk
            data, _ = stream.read(frames_per_chunk)
            audio_buffer[:] = data.flatten()

            while self.running and not self.shutdown_event.is_set():
                # Use RMS for silence gating during wake word detection to avoid
                # concurrent sherpa-onnx native calls (VAD + recognizer) which
                # cause heap corruption.
                is_silence, _, silent_frames = self._is_silence_detected_rms(audio_buffer, False, silent_frames)
                if is_silence:
                    silent_frames += 1
                    if silent_frames > self.MAX_SILENT_FRAMES:
                        break
                else:
                    silent_frames = 0

                    # Amplify and convert for transcription (skip denoising — not needed for wake word matching)
                    transcode_data = (audio_buffer.astype(np.float32) * self.amp_gain) / 32768.0

                    try:
                        s = self.sherpa_recognizer.create_stream()
                        s.accept_waveform(SHERPA_RATE, transcode_data)
                        self.sherpa_recognizer.decode_stream(s)
                        transcript = s.result.text.strip().lower()
                        # Strip SenseVoice language tags
                        transcript = _SENSEVOICE_TAG_RE.sub('', transcript).strip()
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
                        # Non-blocking indicator so user speech isn't clipped
                        if self.config["STT"].get("use_indicators"):
                            threading.Thread(target=lambda: self.play_wav("../stt/beep_on.wav"), daemon=True).start()
                        try:
                            self._fire_and_forget_get(f"http://127.0.0.1:{CONFIG['UI'].get('webui_port', 80)}/start_talking")
                        except Exception:
                            pass
                        if self.WAKE_WORD_RESPONSES and len(self.WAKE_WORD_RESPONSES) > 0:
                            wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                            character_name = os.path.splitext(os.path.basename(
                                self.config.get("CHAR", {}).get("character_card_path", "TARS")
                            ))[0]
                            queue_message(f"{character_name}: {wake_response}", stream=True)
                            if self.wake_word_callback:
                                self.wake_word_callback(wake_response)
                        return True

                # Roll buffer: shift overlap to front, read new frames into remainder
                audio_buffer[:overlap_frames] = audio_buffer[-overlap_frames:]
                new_data, _ = stream.read(read_frames)
                audio_buffer[overlap_frames:] = new_data.flatten()

        return False

    def _get_progress_bar(self):
        """Get cached progress bar functions (created once, reused per frame)."""
        if self._progress_bar_funcs is None:
            bar_length = 10
            show_console = not self.ui_manager.__class__.__name__ == 'UIManagerLite'

            def update_progress_bar(frames, max_frames):
                self.ui_manager.silence(frames)
                if show_console:
                    progress = int((frames / max_frames) * bar_length)
                    filled = "#" * progress
                    empty = "-" * (bar_length - progress)
                    sys.stdout.write(f"\r[SILENCE: {filled}{empty}] {frames}/{max_frames}")
                    sys.stdout.flush()

            def clear_progress_bar():
                self.ui_manager.silence(0)
                if show_console:
                    sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
                    sys.stdout.flush()

            self._progress_bar_funcs = (update_progress_bar, clear_progress_bar)
        return self._progress_bar_funcs
    
    # === VAD Methods ===

    def voice_activity_detection_main(self, data, detected_speech, silent_frames=0):
        """
        Determines if the current audio frame contains silence using VAD or RMS.
        Returns a tuple: (is_silence, detected_speech, silent_frames)
        """
        # Get the vad_method from the configuration, defaulting to "rms" if not set.
        #print(self.vadmethod)
    
        if self.vadmethod == "silero":
            return self._is_silence_detected_silero(data, detected_speech, silent_frames)
        elif self.vadmethod == "sherpa-onnx":
            return self._is_silence_detected_sherpa_onnx(data, detected_speech, silent_frames)
        elif self.vadmethod == "smart-turn":
            return self._is_silence_detected_smart_turn(data, detected_speech, silent_frames)
        elif self.vadmethod == "rms":
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)
        else:
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    def _is_silence_detected_silero(self, data, detected_speech, silent_frames):
        """
        Check if the provided audio data represents silence using VAD.
        Always returns a tuple of (is_silence, detected_speech, silent_frames).
        """
        update_bar, clear_bar = self._get_progress_bar()

        try:
            # Silero VAD-based detection
            if torch is not None and self.silero_vad_model is not None and self.get_speech_timestamps is not None:
                try:
                    audio_norm = data.astype(np.float32) / 32768.0
                    audio_tensor = torch.from_numpy(audio_norm).squeeze()
                    
                    if hasattr(self.silero_vad_model, 'reset_states'):
                        self.silero_vad_model.reset_states()
                    
                    # Get VAD configuration with defaults

                    noise_gate = 0.01 * self.silence_threshold #adjust for bgnoise

                    # Skip very low amplitude signals 
                    #if np.max(np.abs(audio_norm)) < noise_gate:
                        #return True, detected_speech, silent_frames

                    speech_ts = self.get_speech_timestamps(
                        audio_tensor, 
                        self.silero_vad_model,
                        sampling_rate=self.SAMPLE_RATE,
                        threshold=0.3,
                        min_speech_duration_ms=100,
                        return_seconds=True
                    ) or []
                    
             

                    if len(speech_ts) > 0:
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
            
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)
            
        
        except Exception as e:
            queue_message(f"ERROR: Silence detection failed: {e}")
            # Return safe default values
            return False, detected_speech, silent_frames

    def _is_silence_detected_rms(self, data, detected_speech, silent_frames):
        """RMS-based silence detection with visual progress bar"""
        try:
            update_bar, clear_bar = self._get_progress_bar()
            rms = self.prepare_audio_data(self.amplify_audio(data))
            if self.silence_threshold_margin is None:
                self.silence_threshold_margin = self.silence_threshold * self.silence_margin

            if rms is None:
                # Even if RMS calculation fails, return proper tuple
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
        
        except Exception as e:
            queue_message(f"ERROR: RMS silence detection failed: {e}")
            # Return safe default values
            return False, detected_speech, silent_frames
  
    def _is_silence_detected_sherpa_onnx(self, data, detected_speech, silent_frames):
        """Sherpa-onnx Silero VAD-based silence detection (no torch required)."""
        update_bar, clear_bar = self._get_progress_bar()

        try:
            if self.sherpa_vad is None:
                return self._is_silence_detected_rms(data, detected_speech, silent_frames)

            audio_float = data.astype(np.float32).flatten() / 32768.0

            self.sherpa_vad.accept_waveform(audio_float)

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
            rms = self.prepare_audio_data(self.amplify_audio(data))
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
            else:
                # Silence detected
                silent_frames += 1
                update_bar(silent_frames, self.MAX_SILENT_FRAMES)

            # Only run Smart Turn after some silence and if we have speech buffered
            if silent_frames >= 3 and detected_speech and len(self.smart_turn_audio_buffer) > 0:
                try:
                    # Concatenate buffered audio
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
                    input_features = inputs.input_features.astype(np.float32)

                    # Run inference
                    outputs = self.smart_turn_session.run(None, {"input_features": input_features})
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

            # Safety fallback: force end if silence way too long
            if silent_frames > self.MAX_SILENT_FRAMES * 2:
                clear_bar()
                self.smart_turn_audio_buffer.clear()
                return True, detected_speech, silent_frames

            return False, detected_speech, silent_frames

        except Exception as e:
            queue_message(f"WARNING: Smart Turn VAD error, falling back to RMS: {e}")
            self.smart_turn_audio_buffer.clear()
            return self._is_silence_detected_rms(data, detected_speech, silent_frames)

    # === Audio adjustments ===

    def _measure_background_noise(self):
        """Measure background noise and set the silence threshold."""
        queue_message("INFO: Measuring background noise...")
        background_rms_values = []
        total_frames = 20  # ~2-3 seconds

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE, channels=1, dtype="int16"
        ) as stream:
            for _ in range(total_frames):
                data, _ = stream.read(4000)
                rms = self.prepare_audio_data(data)
                if rms is not None:
                    background_rms_values.append(rms)
                time.sleep(0.1)

        if background_rms_values:
            background_rms = np.array(background_rms_values)
            median_rms = np.median(background_rms)
            self.silence_threshold = max(median_rms, 10)

            # Remove outliers using IQR
            q1, q3 = np.percentile(background_rms, [25, 75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            filtered = background_rms[(background_rms >= lower_bound) & (background_rms <= upper_bound)]
            self.wake_silence_threshold = np.max(filtered)
            self.silence_threshold = self.wake_silence_threshold * self.silence_margin
            self.silence_threshold_margin = self.silence_threshold * self.silence_margin

            db = 20 * np.log10(self.silence_threshold)
            queue_message(f"INFO: Silence threshold: {db:.2f} dB and {self.silence_threshold}")
        else:
            queue_message("WARNING: Background noise measurement failed; using default threshold.")

    def prepare_audio_data(self, data: np.ndarray) -> Optional[float]:
        """
        Compute the RMS of the audio data.
        Returns:
            float or None: RMS value or None if invalid.
        """
        if data.size == 0:
            queue_message("WARNING: Empty audio data received.")
            return None
        data = data.reshape(-1).astype(np.float64)
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        data = np.clip(data, -32000, 32000)
        if np.all(data == 0):
            queue_message("WARNING: Audio data is silent or all zeros.")
            return None
        try:
            return np.sqrt(np.mean(np.square(data)))
        except Exception as e:
            queue_message(f"ERROR: RMS calculation failed: {e}")
            return None

    def amplify_audio(self, data: np.ndarray) -> np.ndarray:
        """
        Amplify the input audio data using the configured amplification gain.
        """
        return np.clip(data * self.amp_gain, -32768, 32767).astype(np.int16)

    def find_default_mic_sample_rate(self):
        """
        Retrieve the default microphone's sample rate.
        Returns:
            int: The sample rate.
        """
        try:
            default_index = sd.default.device[0]
            if default_index is None:
                raise ValueError("No default microphone detected.")
            device_info = sd.query_devices(default_index, kind="input")
            return int(device_info.get("default_samplerate", 16000))
        except Exception as e:
            queue_message(f"ERROR: {e}")
            return self.DEFAULT_SAMPLE_RATE


    def play_wav(self, filename):
        try:
            data, sample_rate = sf.read(filename)
            data = data * 0.5
            sd.play(data, samplerate=sample_rate)
            sd.wait()
        except Exception as e:
            print(f"Error playing sound file: {e}")



    # === Callback Setters ===

    def set_wake_word_callback(self, callback: Callable[[str], None]):
        self.wake_word_callback = callback

    def set_utterance_callback(self, callback: Callable[[str], None]):
        self.utterance_callback = callback

    def set_post_utterance_callback(self, callback: Callable[[], None]):
        self.post_utterance_callback = callback