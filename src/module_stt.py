#!/usr/bin/env python3
"""
module_stt.py

Speech-to-Text (STT) Module for TARS-AI Application.

This module integrates both local and server-based transcription, wake word detection,
and voice command handling. It supports custom callbacks to trigger actions upon 
detecting speech or specific keywords.

This version supports loading the Silero VAD model using its ONNX version when configured.
"""

# === Standard Libraries ===
import os
import random
import threading
import time
import wave
import json
import sys
from io import BytesIO
from typing import Callable, Optional
import torch
import torchaudio  # Faster than librosa for resampling
import torchaudio.functional as F
import librosa

import numpy as np
import sounddevice as sd
import soundfile as sf

from vosk import Model, KaldiRecognizer, SetLogLevel
from pocketsphinx import LiveSpeech
import whisper
from faster_whisper import WhisperModel
import requests
from silero_vad import load_silero_vad, get_speech_timestamps

# Suppress Vosk logs and parallelism warnings
SetLogLevel(-1)
os.environ["TOKENIZERS_PARALLELISM"] = "false"


class STTManager:
    WAKE_WORD_RESPONSES = [
        "Oh! You called?",
        "Took you long enough. Yes?",
        "Finally!",
        "Oh? Did you need me?",
        "Anything you need just ask.",
        "O yea, Now, what do you need?",
        "You have my full attention.",
        "You rang?",
        "hum yea?",
        "Finally, I was about to lose my mind.",
    ]

    def __init__(self, config, shutdown_event: threading.Event, amp_gain: float = 4.0):
        """
        Initialize the STTManager.

        Args:
            config (dict): Configuration dictionary.
            shutdown_event (threading.Event): Event to signal stopping the assistant.
            amp_gain (float): Amplification gain factor for audio data.
        """
        self.config = config
        self.shutdown_event = shutdown_event
        self.running = False

        # Audio settings - Set sample rate based on VAD configuration
        if self.config["STT"].get("vad_enabled", False):
            # If VAD is enabled, force 16000 Hz sample rate
            self.SAMPLE_RATE = 16000
            self.DEFAULT_SAMPLE_RATE = 16000
            print("INFO: Using 16000 Hz sample rate for VAD compatibility")
        else:
            # If VAD is disabled, use system default
            self.DEFAULT_SAMPLE_RATE = 16000
            self.SAMPLE_RATE = self.find_default_mic_sample_rate()

        self.amp_gain = amp_gain
        self.silence_margin = 3.5  # Multiplier for noise floor
        self.wake_silence_threshold = None
        self.silence_threshold = None  # Updated after measuring background noise
        self.DEFAULT_SAMPLE_RATE = 16000
        self.MAX_RECORDING_FRAMES = 100  # ~12.5 seconds
        self.MAX_SILENT_FRAMES = 10      # ~1.25 seconds of silence

        # Callbacks for wake word detection and utterance processing
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.post_utterance_callback: Optional[Callable[[], None]] = None

        # Wake word and model settings
        self.WAKE_WORD = config.get("STT", {}).get("wake_word", "default_wake_word")
        self.vosk_model = None
        self.whisper_model = None
        self.silero_model = None  # For Silero STT (if used)
        self.silero_vad_model = None
        self.get_speech_timestamps = None

        # Initialize models and measure background noise
        self._initialize_models()

    def _initialize_models(self):
        """Measure background noise and load the selected STT model(s)."""
        self._measure_background_noise()
        stt_processor = self.config.get("STT", {}).get("stt_processor", "vosk")
        if stt_processor == "whisper":
            self._load_whisper_model()
        if stt_processor == "faster-whisper":
            self._load_fasterwhisper_model()
        if stt_processor == "silero":
            self._load_silero_model()
        elif stt_processor == "vosk":
            self._load_vosk_model()

        # Use Silero VAD instead of RMS (if configured)
        if self.config["STT"].get("vad_enabled", False):
            self._load_silero_vad()

    def start(self):
        """Start the STT processing loop in a separate thread."""
        self.running = True
        self.thread = threading.Thread(target=self._stt_processing_loop, name="STTThread", daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the STT processing loop."""
        self.running = False
        self.shutdown_event.set()
        self.thread.join()

    def _load_vosk_model(self):
        """Load the Vosk model from the configured path."""
        model_path = os.path.join("..", "stt", self.config.get("STT", {}).get("vosk_model", "default_vosk_model"))
        if not os.path.exists(model_path):
            print("ERROR: Vosk model not found.")
            return
        self.vosk_model = Model(model_path)
        print("INFO: Vosk model loaded successfully.")

    def _load_silero_model(self):
        """Load Silero STT model."""
        self.silero_model, self.decoder, self.utils = torch.hub.load(
            "snakers4/silero-models", model="silero_stt", language="en", device="cpu"
        )
        (self.read_batch, self.split_into_batches, self.read_audio, self.prepare_model_input) = self.utils
        print("INFO: Silero model loaded successfully.")

    def _load_whisper_model(self):
        """Load the Whisper model for local transcription."""
        try:
            import torch
            import warnings
            # Suppress future warnings from torch
            warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
            _original_torch_load = torch.load

            def _patched_torch_load(fp, map_location, *args, **kwargs):
                return _original_torch_load(fp, map_location=map_location, weights_only=True, *args, **kwargs)

            torch.load = _patched_torch_load

            model_size = self.config["STT"].get("whisper_model", "tiny")
            print(f"INFO: Loading Whisper model '{model_size}'...")
            self.whisper_model = whisper.load_model(model_size)
            if not hasattr(self.whisper_model, 'device'):
                raise ValueError("Whisper model did not load correctly.")
            print("INFO: Whisper model loaded successfully.")
        except Exception as e:
            print(f"ERROR: Failed to load Whisper model: {e}")
            self.whisper_model = None
        finally:
            torch.load = _original_torch_load

    def _load_fasterwhisper_model(self):
        """Load the Whisper model for local transcription."""
        try:
            import torch
            import warnings
            # Suppress future warnings from torch
            warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
            _original_torch_load = torch.load

            def _patched_torch_load(fp, map_location, *args, **kwargs):
                return _original_torch_load(fp, map_location=map_location, weights_only=True, *args, **kwargs)

            torch.load = _patched_torch_load

            model_size = self.config["STT"].get("whisper_model", "tiny")
            print(f"INFO: Loading faster-Whisper model '{model_size}'...")

            if not hasattr(self, "faster_whisper_model"):
                model_size = self.config["STT"].get("whisper_model", "tiny")

                self.faster_whisper_model = WhisperModel(
                    model_size, device="cpu", compute_type="int8", num_workers=4
                )
             
            print("INFO: Whisper model loaded successfully.")
        except Exception as e:
            print(f"ERROR: Failed to load Whisper model: {e}")
            self.whisper_model = None
        finally:
            torch.load = _original_torch_load

    def _load_silero_vad(self):
        """
        Load the Silero VAD model using the pip package and optional ONNX support.
        This loads the get_speech_timestamps function (instead of get_speech_ts).
        """
        # You can set these values as needed.
        USE_PIP = True  # download model using pip package
        USE_ONNX = False

        if USE_PIP:
            try:
                from silero_vad import load_silero_vad, get_speech_timestamps
                self.silero_vad_model = load_silero_vad(onnx=USE_ONNX)
                self.get_speech_timestamps = get_speech_timestamps
                print("INFO: Silero VAD loaded successfully using pip package.")
            except Exception as e:
                print(f"ERROR: Failed to load Silero VAD with pip: {e}")
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
                print("INFO: Silero VAD loaded successfully using torch.hub.")
            except Exception as e:
                print(f"ERROR: Failed to load Silero VAD with torch.hub: {e}")

    def _measure_background_noise(self):
        """Measure background noise over several frames and set the silence threshold."""
        print("INFO: Measuring background noise...")
        background_rms_values = []
        total_frames = 20  # ~2-3 seconds

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
            for _ in range(total_frames):
                data, _ = stream.read(4000)

                # Option 1: Use raw data with a noise floor multiplier
                #rms = self.prepare_audio_data(data) * self.silence_margin #(2.5%)

                rms = self.prepare_audio_data(data) #no amp

                # Option 2 (alternative): Apply amplification first and then compute RMS
                # rms = self.prepare_audio_data(self.amplify_audio(data))
                
                if rms is not None:
                    background_rms_values.append(rms)
                    #print("Current RMS values:", background_rms_values)
                time.sleep(0.1)

        if background_rms_values:
            # Convert the list to a NumPy array for further processing.
            background_rms_values = np.array(background_rms_values)

            # Use the median to set a baseline for the silence threshold.
            median_rms = np.median(background_rms_values)
            self.silence_threshold = max(median_rms, 10)
            #print(f"INFO: Silence threshold set to: {self.silence_threshold:.2f} (raw value)")

            # Calculate the 25th (Q1) and 75th (Q3) percentiles.
            q1 = np.percentile(background_rms_values, 25)
            q3 = np.percentile(background_rms_values, 75)
            iqr = q3 - q1

            # Define lower and upper bounds (using a multiplier of 1.5 is standard).
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            debug = False
            if debug == True:
                print("Q1:", q1)
                print("Q3:", q3)
                print("IQR:", iqr)
                print("Lower Bound:", lower_bound)
                print("Upper Bound:", upper_bound)

            # Filter out the outliers using the computed bounds.
            filtered_values = background_rms_values[
                (background_rms_values >= lower_bound) & (background_rms_values <= upper_bound)
            ]

            # Compute the maximum value from the filtered dataset.
            self.wake_silence_threshold = np.max(filtered_values)
            
            self.silence_threshold = self.wake_silence_threshold * self.silence_margin #(2.5%)

            #print("Maximum after removing outliers:", self.silence_threshold)

            # Optionally, calculate the threshold in decibels.
            db = 20 * np.log10(self.silence_threshold)
            print(f"INFO: Silence threshold: {db:.2f} dB and {self.silence_threshold}")
        else:
            print("WARNING: Background noise measurement failed; using default threshold.")

    def _stt_processing_loop(self):
        """Main loop that detects the wake word and transcribes utterances."""
        print("INFO: Starting STT processing loop...")
        while self.running and not self.shutdown_event.is_set():
            if self._detect_wake_word():
                self._transcribe_utterance()
        print("INFO: STT Manager stopped.")

    def _detect_wake_word(self) -> bool:
        """
        Detect the wake word using enhanced false-positive filtering.
        """
        if self.config["STT"].get("use_indicators"):
            self.play_beep(400, 0.1, 44100, 0.6)
        
        character_path = self.config.get("CHAR", {}).get("character_card_path")
        character_name = os.path.splitext(os.path.basename(character_path))[0] if character_path else "TARS"
        print(f"{character_name}: Sleeping...")

        try:
            requests.get("http://127.0.0.1:5012/stop_talking", timeout=1)
        except Exception:
            pass

        silent_frames = 0
        max_iterations = 100 # Prevent infinite loops

        try:
            threshold_map = {
                1: 1e-20,   # Extremely sensitive (lowest threshold)
                2: 1e-18,   # Very sensitive
                3: 1e-16,   # Sensitive
                4: 1e-14,   # Moderately sensitive
                5: 1e-12,   # Normal sensitivity
                6: 1e-10,   # Slightly strict
                7: 1e-8,    # Strict
                8: 1e-6,    # Very strict
                9: 1e-4,    # Extremely strict
                10: 1e-2    # Maximum strictness (highest threshold)
            }
            kws_threshold = threshold_map.get(int(self.config['STT']['sensitivity']), 1)
            speech = LiveSpeech(lm=False, keyphrase=self.WAKE_WORD, kws_threshold=kws_threshold)

            for phrase in speech:
                text = phrase.hypothesis().lower()
                if self.WAKE_WORD.lower() in text:
                    silent_frames = 0
                    if self.config['STT']['use_indicators']:
                        self.play_beep(1200, 0.1, 44100, 0.8)
                    try:
                        requests.get("http://127.0.0.1:5012/start_talking", timeout=1)
                    except Exception:
                        pass
                    wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                    print(f"{character_name}: {wake_response}")
                    if self.wake_word_callback:
                        self.wake_word_callback(wake_response)
                    return True

                with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                    data, _ = stream.read(4000)
                    is_silence, _, silent_frames = self._is_silence_detected(data, False, silent_frames, self.MAX_SILENT_FRAMES)
                    if silent_frames > self.MAX_SILENT_FRAMES:
                        break

        except Exception as e:
            print(f"ERROR: Wake word detection failed: {e}")
            import traceback
            traceback.print_exc()

        return False

    def _transcribe_utterance(self):
        """Transcribe the user's utterance using the selected STT processor."""
        try:
            processor = self.config["STT"].get("stt_processor", "vosk")
            if processor == "whisper":
                result = self._transcribe_with_whisper()
            elif processor == "faster-whisper":
                result = self._transcribe_with_faster_whisper()
            elif processor == "silero":
                result = self._transcribe_silero()
            elif processor == "external":
                result = self._transcribe_with_server()
            else:
                result = self._transcribe_with_vosk()

            if self.post_utterance_callback and result:
                self.post_utterance_callback()
        except Exception as e:
            print(f"ERROR: Transcription failed: {e}")
            import traceback
            traceback.print_exc()

    def _transcribe_with_vosk(self):
        """Transcribe audio using the local Vosk model."""
        # Make sure the Vosk model is loaded
        if self.vosk_model is None:
            print("ERROR: Vosk model is not loaded.")
            return None

        try:
            recognizer = KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
        except Exception as e:
            print(f"ERROR: Failed to initialize KaldiRecognizer: {e}")
            return None

        recognizer.SetWords(False)  # Disable word-level output for speed
        recognizer.SetPartialWords(False)  # Disable partial results

        detected_speech = False
        silent_frames = 0
        max_silent_frames = self.MAX_SILENT_FRAMES

        with sd.InputStream(samplerate=self.SAMPLE_RATE,
                            channels=1, dtype="int16",
                            blocksize=4000, latency='high') as stream:
            for _ in range(50):  # Limit recording duration (~12.5 seconds)
                data, _ = stream.read(4000)
                data = self.amplify_audio(data)
                is_silence, detected_speech, silent_frames = self._is_silence_detected(
                    data, detected_speech, silent_frames, max_silent_frames
                )
                if is_silence:
                    if not detected_speech:
                        return None
                    break
                if recognizer.AcceptWaveform(data.tobytes()):
                    result = recognizer.Result()
                    if self.utterance_callback:
                        self.utterance_callback(result)
                    return result
        return None

    def _transcribe_with_whisper(self):
        """Transcribe audio using the local Whisper model."""
        if not self.whisper_model:
            print("ERROR: Whisper model not loaded.")
            return None
        try:
            audio_buffer = BytesIO()
            detected_speech = False
            silent_frames = 0
            max_silent_frames = self.MAX_SILENT_FRAMES

            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream, \
                 wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                for _ in range(100):  # Limit duration (~12.5 seconds)
                    data, _ = stream.read(4000)
                    wf.writeframes(data.tobytes())
                    is_silence, detected_speech, silent_frames = self._is_silence_detected(
                        data, detected_speech, silent_frames, max_silent_frames
                    )
                    if is_silence:
                        if not detected_speech:
                            return None
                        break

            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                print("ERROR: No audio recorded.")
                return None

            audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")
            audio_data = np.clip(audio_data, -1.0, 1.0)
            if sample_rate != self.DEFAULT_SAMPLE_RATE:
                #audio_data = F.resample(torch.tensor(audio_data), orig_freq=sample_rate, new_freq=16000).numpy()
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

            audio_data = whisper.pad_or_trim(audio_data)
            mel = whisper.log_mel_spectrogram(audio_data).to(self.whisper_model.device)
            options = whisper.DecodingOptions(fp16=False)
            result = whisper.decode(self.whisper_model, mel, options)
            
            if hasattr(result, "text") and result.text:
                transcribed_text = result.text.strip()
                formatted_result = {"text": transcribed_text}
                if self.utterance_callback:
                    self.utterance_callback(json.dumps(formatted_result))
                return formatted_result
            else:
                print("ERROR: Whisper produced no transcription.")
                return None
        except Exception as e:
            print(f"ERROR: Whisper transcription failed: {e}")
            return None

    def _transcribe_with_faster_whisper(self):
        """Transcribe audio using Faster-Whisper for optimized performance."""
        audio_buffer = BytesIO()
        detected_speech = False
        silent_frames = 0
        max_silent_frames = self.MAX_SILENT_FRAMES

        try:
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream, \
                wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)

                for _ in range(self.MAX_RECORDING_FRAMES):
                    data, _ = stream.read(4000)
                    wf.writeframes(data.tobytes())

                    if self.config["STT"]["vad_enabled"]:
                        audio_norm = data.astype(np.float32) / 32768.0
                        audio_tensor = torch.from_numpy(audio_norm).squeeze()
                        speech_ts = self.get_speech_timestamps(
                            audio_tensor,
                            self.silero_vad_model,
                            sampling_rate=self.SAMPLE_RATE,
                            threshold=0.3,
                            min_speech_duration_ms=100,
                            return_seconds=True
                        )
                        sys.stdout.flush()

                    is_silence, detected_speech, silent_frames = self._is_silence_detected(
                        data, detected_speech, silent_frames, max_silent_frames
                    )
                    if is_silence:
                        if not detected_speech:
                            return None
                        break

            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                return None

            # Read and preprocess audio
            audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")
            audio_data = np.clip(audio_data, -1.0, 1.0)

            if sample_rate != 16000:
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

            segments, _ = self.faster_whisper_model.transcribe(
                audio_data, 
                temperature=0.0, 
                beam_size=1, 
                language="en"
            )
            
            transcribed_text = " ".join(segment.text for segment in segments).strip()

            if transcribed_text:
                formatted_result = {"text": transcribed_text}
                if self.utterance_callback:
                    self.utterance_callback(json.dumps(formatted_result))
                return formatted_result
            else:
                print("WARNING: No transcription output")
                return None
                
        except Exception as e:
            print(f"ERROR: Transcription error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _transcribe_silero(self):
        """Transcribe audio using Silero STT with optimized in-memory processing."""
        audio_buffer = BytesIO()
        detected_speech = False
        silent_frames = 0

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16", blocksize=4000) as stream, \
            wave.open(audio_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)

            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
                wf.writeframes(data.tobytes())

                is_silence, detected_speech, silent_frames = self._is_silence_detected(
                    data, detected_speech, silent_frames, self.MAX_SILENT_FRAMES
                )
                if is_silence:
                    if not detected_speech:
                        return None
                    break

        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0:
            print("ERROR: No audio recorded.")
            return None

        # Read audio directly from BytesIO into a tensor
        audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")

        # Optimize resampling
        if sample_rate != 16000:
            #audio_data = torchaudio.functional.resample(torch.tensor(audio_data), orig_freq=sample_rate, new_freq=16000)
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

        # Prepare model input
        input_audio = self.prepare_model_input([torch.tensor(audio_data)], device="cpu")
        

        # Run STT
        silero_output = self.silero_model(input_audio)[0]
        decoded_text = self.decoder(silero_output.cpu())
        
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
            max_silent_frames = self.MAX_SILENT_FRAMES

            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream, \
                 wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                for _ in range(self.MAX_RECORDING_FRAMES):
                    data, _ = stream.read(4000)
                    rms = self.prepare_audio_data(self.amplify_audio(data))
                    if rms and rms > self.silence_threshold:
                        silent_frames = 0
                        wf.writeframes(data.tobytes())
                    else:
                        silent_frames += 1
                        if silent_frames > max_silent_frames:
                            break

            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                print("ERROR: No audio recorded for server transcription.")
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
            print(f"ERROR: Server transcription request failed: {e}")
        return None

    def _init_progress_bar(self):
        """Initialize progress bar settings and functions"""
        bar_length = 10  
        show_progress = self.config["STT"].get("stt_processor") != "vosk"

        def update_progress_bar(frames, max_frames):
            if show_progress:
                progress = int((frames / max_frames) * bar_length)
                filled = "#" * progress
                empty = "-" * (bar_length - progress)
                
                bar = f"\r[SILENCE: {filled}{empty}] {frames}/{max_frames}"
                sys.stdout.write(bar)
                sys.stdout.flush()

        def clear_progress_bar():
            if show_progress:
                sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
                sys.stdout.flush()

        return update_progress_bar, clear_progress_bar

    def _is_silence_detected(self, data, detected_speech, silent_frames, max_silent_frames):
        """
        Check if the provided audio data represents silence using either VAD or RMS.
        """
        update_bar, clear_bar = self._init_progress_bar()
        self.DEBUG = False

        # Silero VAD-based detection
        if self.silero_vad_model is not None and self.get_speech_timestamps is not None:
            try:
                audio_norm = data.astype(np.float32) / 32768.0
                audio_tensor = torch.from_numpy(audio_norm).squeeze()
                
                if hasattr(self.silero_vad_model, 'reset_states'):
                    self.silero_vad_model.reset_states()
                    
                speech_ts = self.get_speech_timestamps(
                    audio_tensor, 
                    self.silero_vad_model,
                    sampling_rate=self.SAMPLE_RATE,
                    threshold=0.3,  # Lower threshold
                    min_speech_duration_ms=100,  # More sensitive to short utterances
                    return_seconds=True
                )
                
                if len(speech_ts) > 0:
                    if self.DEBUG:
                        print(f"DEBUG: Speech detected at: {speech_ts}")
                    detected_speech = True
                    silent_frames = 0
                    clear_bar()
                else:
                    silent_frames += 1
                    if self.DEBUG:
                        print(f"DEBUG: No speech in frame {silent_frames}")
                    update_bar(silent_frames, max_silent_frames)

                if silent_frames > max_silent_frames:
                    clear_bar()
                    return True, detected_speech, silent_frames
                return False, detected_speech, silent_frames
                    
            except Exception as e:
                print(f"ERROR: VAD error, falling back to RMS: {e}")
                return self._is_silence_detected_rms(data, detected_speech, silent_frames, max_silent_frames)

    def _is_silence_detected_rms(self, data, detected_speech, silent_frames, max_silent_frames):
        """RMS-based silence detection with visual progress bar"""
        update_bar, clear_bar = self._init_progress_bar()
        self.DEBUG = False
        rms = self.prepare_audio_data(self.amplify_audio(data))
        self.silence_threshold_margin = self.silence_threshold * self.silence_margin

        if rms is None:
            return False, detected_speech, silent_frames

        if rms > self.silence_threshold_margin:
            detected_speech = True
            silent_frames = 0
            
            if self.DEBUG:
                print(f"AUDIO: {rms:.2f}/{self.silence_threshold:.2f}/{self.silence_threshold_margin:.2f}")
            
            clear_bar()
        else:
            silent_frames += 1
            
            if self.DEBUG:
                print(f"SILENT: {rms:.2f}/{self.silence_threshold:.2f}/{self.silence_threshold_margin:.2f}")
            
            update_bar(silent_frames, max_silent_frames)

            if silent_frames > max_silent_frames:
                clear_bar()
                return True, detected_speech, silent_frames

        return False, detected_speech, silent_frames

    def prepare_audio_data(self, data: np.ndarray) -> Optional[float]:
        """
        Sanitize and compute the RMS of the audio data.
        Returns:
            float: RMS value or None if data is invalid.
        """
        if data.size == 0:
            print("WARNING: Empty audio data received.")
            return None
        data = data.reshape(-1).astype(np.float64)
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        data = np.clip(data, -32000, 32000)
        if np.all(data == 0):
            print("WARNING: Audio data is silent or all zeros.")
            return None
        try:
            return np.sqrt(np.mean(np.square(data)))
        except Exception as e:
            print(f"ERROR: RMS calculation failed: {e}")
            return None

    def amplify_audio(self, data: np.ndarray) -> np.ndarray:
        """
        Amplify the input audio data using the set amplification gain.
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
            return int(device_info.get("default_samplerate", self.DEFAULT_SAMPLE_RATE))
        except Exception as e:
            print(f"ERROR: {e}")
            return self.DEFAULT_SAMPLE_RATE

    def play_beep(self, frequency: int, duration: float, sample_rate: int, volume: float):
        """
        Play a beep sound to indicate state changes.
        """
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        sine_wave = volume * np.sin(2 * np.pi * frequency * t)
        sd.play(sine_wave, samplerate=sample_rate)
        sd.wait()

    # === Callback Setters ===
    def set_wake_word_callback(self, callback: Callable[[str], None]):
        """
        Sets the callback function to be called when the wake word is detected.
        The callback receives a string response as its parameter.
        """
        self.wake_word_callback = callback
        print("INFO: Wake word callback has been set.")

    def set_utterance_callback(self, callback: Callable[[str], None]):
        """
        Sets the callback function to be called after an utterance is transcribed.
        The callback receives the transcription result as a JSON string.
        """
        self.utterance_callback = callback
        print("INFO: Utterance callback has been set.")

    def set_post_utterance_callback(self, callback: Callable[[], None]):
        """
        Sets a post-utterance callback to be executed once transcription is complete.
        """
        self.post_utterance_callback = callback
        print("INFO: Post-utterance callback has been set.")