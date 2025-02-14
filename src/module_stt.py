#!/usr/bin/env python3
"""
module_stt.py

Speech-to-Text (STT) Module for TARS-AI Application.

This module integrates both local and server-based transcription, wake word detection,
and voice command handling. It supports custom callbacks to trigger actions upon
detecting speech or specific keywords.
"""

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
import torchaudio 
import torchaudio.functional as F
import librosa

import numpy as np
import sounddevice as sd
import soundfile as sf

from vosk import Model, KaldiRecognizer, SetLogLevel
from pocketsphinx import LiveSpeech
import whisper
from faster_whisper import WhisperModel
import onnxruntime
from silero_vad import load_silero_vad, get_speech_timestamps
import requests

# Suppress Vosk logs and parallelism warnings
SetLogLevel(-1)
os.environ["TOKENIZERS_PARALLELISM"] = "false"


class STTManager:
    # Predefined responses to the wake word
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
            shutdown_event (threading.Event): Event to signal when to stop.
            amp_gain (float): Amplification gain for audio data.
        """
        self.config = config
        self.shutdown_event = shutdown_event
        self.running = False

        # Audio settings
        self.DESIRED_SAMPLE_RATE = 16000  # Rate expected by Silero VAD and transcription models
        self.DEFAULT_SAMPLE_RATE = self.DESIRED_SAMPLE_RATE
        self.SAMPLE_RATE = self.find_default_mic_sample_rate()
        self.amp_gain = amp_gain  # Multiplier for mic
        self.silence_margin = 3.5  # Multiplier for noise floor
        self.wake_silence_threshold = None
        self.silence_threshold = None  # Updated after measuring background noise
        self.MAX_RECORDING_FRAMES = 100   # ~12.5 seconds
        self.MAX_SILENT_FRAMES = 20       # ~1.25 seconds of silence
        self.speech_buffer_frames = 20    # Buffer for natural speech pauses
        self.vad_threshold = 0.3          # Lower threshold for more sensitive speech detection

        # Callbacks
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.post_utterance_callback: Optional[Callable[[], None]] = None

        # Wake word and model settings
        self.WAKE_WORD = config.get("STT", {}).get("wake_word", "default_wake_word")
        self.vosk_model = None
        self.whisper_model = None
        self.silero_model = None

        # Silero VAD settings
        self.vad_model = None
        self.speech_buffer = []  # Store recent speech detection results
        self.init_silero_vad()
        
        self._initialize_models()

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

    def init_silero_vad(self):
        """Initialize Silero VAD."""
        try:
            torch.set_num_threads(1)
            self.vad_model = load_silero_vad()
            print("INFO: Silero VAD model loaded successfully")
        except Exception as e:
            print(f"ERROR: Failed to load Silero VAD model: {e}")
            self.vad_model = None

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
            import warnings
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
        """Load the Whisper model for local transcription using Faster-Whisper."""
        try:
            import warnings
            warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
            _original_torch_load = torch.load

            def _patched_torch_load(fp, map_location, *args, **kwargs):
                return _original_torch_load(fp, map_location=map_location, weights_only=True, *args, **kwargs)

            torch.load = _patched_torch_load

            model_size = self.config["STT"].get("whisper_model", "tiny")
            print(f"INFO: Loading faster-Whisper model '{model_size}'...")

            if not hasattr(self, "faster_whisper_model"):
                self.faster_whisper_model = WhisperModel(
                    model_size, device="cpu", compute_type="int8", num_workers=4
                )
            print("INFO: Whisper model loaded successfully.")
        except Exception as e:
            print(f"ERROR: Failed to load Whisper model: {e}")
            self.whisper_model = None
        finally:
            torch.load = _original_torch_load

    def _measure_background_noise(self):
        """Measure background noise and set the silence threshold."""
        print("INFO: Measuring background noise...")
        background_rms_values = []
        total_frames = 20  # ~2-3 seconds

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
            for _ in range(total_frames):
                data, _ = stream.read(4000)
                rms = self.prepare_audio_data(data)  # No amplification applied here
                if rms is not None:
                    background_rms_values.append(rms)
                time.sleep(0.1)

        if background_rms_values:
            background_rms_values = np.array(background_rms_values)
            median_rms = np.median(background_rms_values)
            self.silence_threshold = max(median_rms, 10)
            q1 = np.percentile(background_rms_values, 25)
            q3 = np.percentile(background_rms_values, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            filtered_values = background_rms_values[
                (background_rms_values >= lower_bound) & (background_rms_values <= upper_bound)
            ]

            self.wake_silence_threshold = np.max(filtered_values)
            self.silence_threshold = self.wake_silence_threshold * self.silence_margin

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
        Detect the wake word with improved pause handling.
        Uses Silero VAD if available.
        """
        if self.config["STT"].get("use_indicators"):
            # Placeholder for actual indicator logic (e.g., playing a beep)
            pass
        
        character_name = os.path.splitext(os.path.basename(self.config.get("CHAR", {}).get("character_card_path", "character")))[0]
        print(f"{character_name}: Sleeping...")

        try:
            requests.get("http://127.0.0.1:5012/stop_talking", timeout=1)
        except Exception:
            pass

        silent_frames = 0
        continuous_speech_frames = 0

        # Initialize LiveSpeech with a lenient threshold
        threshold_map = {
            1: 1e-20, 2: 1e-18, 3: 1e-16, 4: 1e-14, 5: 1e-12,
            6: 1e-10, 7: 1e-8, 8: 1e-6, 9: 1e-4, 10: 1e-2
        }
        kws_threshold = threshold_map.get(int(self.config['STT']['sensitivity']), 1e-18)

        speech = LiveSpeech(lm=False, keyphrase=self.WAKE_WORD, kws_threshold=kws_threshold)

        try:
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while not self.shutdown_event.is_set():
                    data, _ = stream.read(4000)
                    
                    # Resample if mic's sample rate differs from the desired rate
                    if self.SAMPLE_RATE != self.DESIRED_SAMPLE_RATE:
                        data = librosa.resample(data.astype(np.float32), self.SAMPLE_RATE, self.DESIRED_SAMPLE_RATE)
                        data = data.astype("int16")
                    
                    if self.vad_model:
                        float_data = data.astype(np.float32) / 32768.0
                        float_data = np.squeeze(float_data)
                        audio_tensor = torch.from_numpy(float_data)
                        
                        speech_timestamps = get_speech_timestamps(
                            audio_tensor,
                            self.vad_model,
                            sampling_rate=self.DESIRED_SAMPLE_RATE,
                            threshold=self.vad_threshold,
                            min_speech_duration_ms=100,
                            min_silence_duration_ms=200,
                            return_seconds=True
                        )
                        
                        self.speech_buffer.append(len(speech_timestamps) > 0)
                        if len(self.speech_buffer) > self.speech_buffer_frames:
                            self.speech_buffer.pop(0)
                        
                        recent_speech = any(self.speech_buffer)
                        if recent_speech:
                            silent_frames = max(0, silent_frames - 2)
                            continuous_speech_frames += 1
                        else:
                            silent_frames += 1
                            continuous_speech_frames = max(0, continuous_speech_frames - 1)
                    else:
                        rms = self.prepare_audio_data(self.amplify_audio(data))
                        if rms > self.silence_threshold * 0.8:
                            silent_frames = max(0, silent_frames - 2)
                            continuous_speech_frames += 1
                        else:
                            silent_frames += 1
                            continuous_speech_frames = max(0, continuous_speech_frames - 1)

                    for phrase in speech:
                        if self.WAKE_WORD.lower() in phrase.hypothesis().lower():
                            wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                            print(f"{character_name}: {wake_response}")
                            if self.wake_word_callback:
                                self.wake_word_callback(wake_response)
                            return True

                    if silent_frames > self.MAX_SILENT_FRAMES and continuous_speech_frames < 5:
                        return False

                    if self.config["STT"].get("show_silence_progress", True):
                        bar_length = 20
                        progress = int((silent_frames / self.MAX_SILENT_FRAMES) * bar_length)
                        bar = "#" * progress + "-" * (bar_length - progress)
                        sys.stdout.write(f"\r[SILENCE: {bar}] {silent_frames}/{self.MAX_SILENT_FRAMES}")
                        sys.stdout.flush()
        except Exception as e:
            print(f"ERROR: Wake word detection failed: {e}")
            return False

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

    def _transcribe_with_vosk(self):
        """Transcribe audio using the local Vosk model."""
        recognizer = KaldiRecognizer(self.vosk_model, self.DESIRED_SAMPLE_RATE)
        recognizer.SetWords(False)
        recognizer.SetPartialWords(False)

        detected_speech = False
        silent_frames = 0
        max_silent_frames = self.MAX_SILENT_FRAMES

        with sd.InputStream(samplerate=self.SAMPLE_RATE,
                            channels=1, dtype="int16",
                            blocksize=4000, latency='high') as stream:
            for _ in range(50):
                data, _ = stream.read(4000)
                data = self.amplify_audio(data)
                if self.SAMPLE_RATE != self.DESIRED_SAMPLE_RATE:
                    data = librosa.resample(data.astype(np.float32), self.SAMPLE_RATE, self.DESIRED_SAMPLE_RATE)
                    data = data.astype("int16")
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
                for _ in range(100):
                    data, _ = stream.read(4000)
                    if self.SAMPLE_RATE != self.DESIRED_SAMPLE_RATE:
                        data = librosa.resample(data.astype(np.float32), self.SAMPLE_RATE, self.DESIRED_SAMPLE_RATE)
                        data = data.astype("int16")
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
            if sample_rate != self.DESIRED_SAMPLE_RATE:
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=self.DESIRED_SAMPLE_RATE)

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

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream, \
            wave.open(audio_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            for _ in range(self.MAX_RECORDING_FRAMES):
                data, _ = stream.read(4000)
                if self.SAMPLE_RATE != self.DESIRED_SAMPLE_RATE:
                    data = librosa.resample(data.astype(np.float32), self.SAMPLE_RATE, self.DESIRED_SAMPLE_RATE)
                    data = data.astype("int16")
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
        if sample_rate != self.DESIRED_SAMPLE_RATE:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=self.DESIRED_SAMPLE_RATE)

        segments, _ = self.faster_whisper_model.transcribe(audio_data, temperature=0.0, beam_size=1, language="en")
        transcribed_text = " ".join(segment.text for segment in segments).strip()

        if transcribed_text:
            formatted_result = {"text": transcribed_text}
            if self.utterance_callback:
                self.utterance_callback(json.dumps(formatted_result))
            return formatted_result
        else:
            print("ERROR: No transcription from Faster-Whisper.")
            return None

    def _transcribe_silero(self):
        """Transcribe audio using Silero STT."""
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
                if self.SAMPLE_RATE != self.DESIRED_SAMPLE_RATE:
                    data = librosa.resample(data.astype(np.float32), self.SAMPLE_RATE, self.DESIRED_SAMPLE_RATE)
                    data = data.astype("int16")
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

        audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")
        if sample_rate != self.DESIRED_SAMPLE_RATE:
            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=self.DESIRED_SAMPLE_RATE)
        input_audio = self.prepare_model_input([torch.tensor(audio_data)], device="cpu")
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

    def _is_silence_detected(self, data, detected_speech, silent_frames, max_silent_frames):
        """
        Detect silence using Silero VAD if available,
        and fall back to RMS-based detection otherwise.
        """
        if self.vad_model is not None:
            try:
                float_data = data.astype(np.float32) / 32768.0
                float_data = np.squeeze(float_data)
                speech_timestamps = get_speech_timestamps(
                    float_data,
                    self.vad_model,
                    sampling_rate=self.DESIRED_SAMPLE_RATE,
                    threshold=0.5,
                    min_speech_duration_ms=250,
                    min_silence_duration_ms=100
                )
                if speech_timestamps:
                    detected_speech = True
                    silent_frames = 0
                else:
                    silent_frames += 1

                bar_length = 20
                if self.config["STT"].get("stt_processor") != "vosk":
                    progress = int((silent_frames / max_silent_frames) * bar_length)
                    bar = "#" * progress + "-" * (bar_length - progress)
                    sys.stdout.write(f"\r[SILENCE: {bar}] {silent_frames}/{max_silent_frames}\n")
                    sys.stdout.flush()
                
                if silent_frames > max_silent_frames:
                    sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
                    sys.stdout.flush()
                    return True, detected_speech, silent_frames
                
                return False, detected_speech, silent_frames
                
            except Exception as e:
                print(f"WARNING: Silero VAD failed, falling back: {e}")
                return self._is_silence_detected_rms(data, detected_speech, silent_frames, max_silent_frames)
        else:
            return self._is_silence_detected_rms(data, detected_speech, silent_frames, max_silent_frames)

    def _is_silence_detected_rms(self, data, detected_speech, silent_frames, max_silent_frames):
        rms = self.prepare_audio_data(self.amplify_audio(data))
        silence_threshold_margin = self.silence_threshold * self.silence_margin
        bar_length = 20
        DEBUG = False

        if rms is None:
            return False, detected_speech, silent_frames
        if rms > silence_threshold_margin:
            detected_speech = True
            silent_frames = 0
            if DEBUG:
                print(f"AUDIO: {rms}/{self.silence_threshold}/{silence_threshold_margin}")  
            sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
            sys.stdout.flush() 
        else:
            silent_frames += 1
            if DEBUG:
                print(f"SILENT: {rms}/{self.silence_threshold}/{silence_threshold_margin}")     
            progress = int((silent_frames / max_silent_frames) * bar_length)
            bar = "#" * progress + "-" * (bar_length - progress)
            sys.stdout.write(f"\r[SILENCE: {bar}] {silent_frames}/{max_silent_frames}\n")
            sys.stdout.flush()
            
            if silent_frames > max_silent_frames:
                sys.stdout.write("\r" + " " * (bar_length + 30) + "\r")
                sys.stdout.flush()
                return True, detected_speech, silent_frames

        return False, detected_speech, silent_frames

    def prepare_audio_data(self, data: np.ndarray) -> Optional[float]:
        """
        Compute the RMS of the audio data.
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
        Amplify input audio data using the specified amplification gain.
        """
        return np.clip(data * self.amp_gain, -32768, 32767).astype(np.int16)

    def find_default_mic_sample_rate(self):
        """
        Retrieve the desired sample rate from configuration (if specified),
        otherwise query the default microphone's sample rate.
        Returns:
            int: The sample rate.
        """
        sample_rate = self.config.get("STT", {}).get("sample_rate")
        if sample_rate:
            print(f"INFO: Using configured sample rate: {sample_rate}")
            return int(sample_rate)
        try:
            default_index = sd.default.device[0]
            if default_index is None:
                raise ValueError("No default microphone detected.")
            device_info = sd.query_devices(default_index, kind="input")
            rate = int(device_info.get("default_samplerate", self.DEFAULT_SAMPLE_RATE))
            if rate != 8000 and (rate % 16000) != 0:
                print(f"WARNING: Reported sample rate {rate} not supported by Silero VAD. Falling back to {self.DEFAULT_SAMPLE_RATE}.")
                rate = self.DEFAULT_SAMPLE_RATE
            print(f"INFO: Using detected sample rate: {rate}")
            return rate
        except Exception as e:
            print(f"ERROR: Unable to determine sample rate: {e}")
            return self.DEFAULT_SAMPLE_RATE
