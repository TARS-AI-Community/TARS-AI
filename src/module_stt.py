"""
module_stt.py

Speech-to-Text (STT) Module for TARS-AI Application.

This module integrates both local and server-based transcription, wake word detection, 
and voice command handling. It supports custom callbacks to trigger actions upon 
detecting speech or specific keywords.
"""

# === Standard Libraries ===
import os
import random
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from pocketsphinx import LiveSpeech
import threading
import requests
from io import BytesIO
import time
import wave
import numpy as np
import json
from typing import Callable, Optional
from vosk import SetLogLevel
import librosa
import soundfile as sf
import whisper

# Suppress Vosk logs by setting the log level to 0 (ERROR and above)
SetLogLevel(-1)  # Adjust to 0 for minimal output or -1 to suppress all logs

#needed to supress warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# === Class Definition ===
class STTManager:
    DEFAULT_SAMPLE_RATE = 16000
    SILENCE_MARGIN = 2.5  # Multiplier for noise threshold
    MAX_RECORDING_FRAMES = 100  # ~12.5 seconds
    MAX_SILENT_FRAMES = 20  # ~1.25 seconds of silence

    WAKE_WORD_RESPONSES = [
        "Yes, Whats the plan?",
        "Standing by for duty.",
        "Go ahead. Im all ears.",
        "Ready when you are.",
        "Whats the mission?",
        "Listening. Try me.",
        "Here. Just say the word.",
        "Yes? Lets keep it professional.",
        "Standing by. Dont keep me waiting.",
        "Online. Ready for the next adventure."
    ]

    def __init__(self, config, shutdown_event: threading.Event, amp_gain: float = 4.0):
        """
        Initialize the STTManager.

        Parameters:
        - config (dict): Configuration dictionary.
        - shutdown_event (Event): Event to signal stopping the assistant.
        - amp_gain (float): Amplification gain factor for audio data.
        """
        self.config = config
        self.shutdown_event = shutdown_event
        self.running = False

        # Audio settings
        self.SAMPLE_RATE = self.find_default_mic_sample_rate()
        self.amp_gain = amp_gain
        self.silence_threshold = 10  # Default threshold

        # Callbacks
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.post_utterance_callback: Optional[Callable[[], None]] = None

        # Wake word and model handling
        self.WAKE_WORD = config.get("STT", {}).get("wake_word", "default_wake_word")
        self.vosk_model = None
        self.whisper_model = None
        self._initialize_models()

    def _initialize_models(self):
        """Initialize all required models based on the configuration."""
        self._load_vosk_model()
        self._measure_background_noise()
        if self.config.get("STT", {}).get("stt_processor") == "whisper":
            self._load_whisper_model()

    def start(self):
        """Start the STTManager in a separate thread."""
        self.running = True
        self.thread = threading.Thread(target=self._stt_processing_loop, name="STTThread", daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the STTManager."""
        self.running = False
        self.shutdown_event.set()
        self.thread.join()

    def _load_vosk_model(self):
        """Load the Vosk model."""
        vosk_model_path = os.path.join("stt", self.config.get("STT", {}).get("vosk_model", "default_vosk_model"))
        if not os.path.exists(vosk_model_path):
            print("ERROR: Vosk model not found.")
            return
        self.vosk_model = Model(vosk_model_path)
        print("INFO: Vosk model loaded successfully.")

    def _load_whisper_model(self):
        """
        Load the Whisper model for local transcription.
        """
        try:
            import torch
            import warnings
            # Suppress future warnings from torch
            warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
            # Monkey patch torch.load for Whisper only
            _original_torch_load = torch.load
            def _patched_torch_load(fp, map_location, *args, **kwargs):
                return _original_torch_load(fp, map_location=map_location, weights_only=True, *args, **kwargs)

            torch.load = _patched_torch_load

            # Load the Whisper model
            whisper_model_size = self.config['STT'].get('whisper_model', 'base')
            print(f"INFO: Attempting to load Whisper model '{whisper_model_size}'...")
            self.whisper_model = whisper.load_model(whisper_model_size)

            if not hasattr(self.whisper_model, 'device'):
                raise ValueError("Whisper model did not load correctly.")
            print("INFO: Whisper model loaded successfully.")
        except Exception as e:
            print(f"ERROR: Failed to load Whisper model: {e}")
            self.whisper_model = None
        finally:
            # Restore the original torch.load after Whisper model is loaded
            torch.load = _original_torch_load

    def _measure_background_noise(self):
        """Measure and set the silence threshold based on background noise."""
        print("INFO: Measuring background noise...")
        background_rms_values = []

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
            for _ in range(20):  # 20 frames for ~2 seconds
                data, _ = stream.read(4000)
                rms = self._calculate_rms(data)
                if rms:
                    background_rms_values.append(rms)

        if background_rms_values:
            avg_rms = np.mean(background_rms_values)
            self.silence_threshold = max(avg_rms * self.SILENCE_MARGIN, 10)
            print(f"INFO: Silence threshold set to: {self.silence_threshold:.2f}")

    def _stt_processing_loop(self):
        """
        Main loop to detect wake words and process utterances with continuous stream processing.
        """
        try:
            print("INFO: Starting continuous stream processing...")
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                while self.running:
                    if self.shutdown_event.is_set():
                        break

                    # Read audio data
                    data, _ = stream.read(4000)
                    rms = self.prepare_audio_data(self.amplify_audio(data))

                    if rms > self.silence_threshold:
                        if self._detect_wake_word():
                            self._transcribe_utterance()
        except Exception as e:
            print(f"ERROR: Error in STT processing loop: {e}")
        finally:
            print("INFO: STT Manager stopped.")

    def _transcribe_utterance(self):
        """Transcribe the user's utterance."""
        try:
            processor = self.config.get("STT", {}).get("stt_processor")
            if processor == "whisper":
                self._transcribe_with_whisper()
            elif processor == "vosk":
                self._transcribe_with_vosk()
        except Exception as e:
            print(f"ERROR: Utterance transcription failed: {e}")

    def set_wake_word_callback(self, callback: Callable[[str], None]):
        """Set the callback function for wake word detection."""
        self.wake_word_callback = callback

    def set_utterance_callback(self, callback: Callable[[str], None]):
        """Set the callback function for user utterance transcription."""
        self.utterance_callback = callback

    def set_post_utterance_callback(self, callback: Callable[[], None]):
        """Set a callback to execute after utterance processing."""
        self.post_utterance_callback = callback

#Main Loop
    def _stt_processing_loop(self):
        """
        Main loop to detect wake words and process utterances.
        """
        try:
            while self.running:
                if self.shutdown_event.is_set():
                    break

                if self._detect_wake_word():
                    self._transcribe_utterance()

        except Exception as e:
            print(f"ERROR: Error in STT processing loop: {e}")
        finally:
            print(f"INFO: STT Manager stopped.")

    # Detect Wake
    def _detect_wake_word(self) -> bool:
        """
        Detect the wake word using enhanced false-positive filtering.
        """

        # Play the "sleeping" tone if indicators are enabled
        if self.config['STT']['use_indicators']:
            self.play_beep(400, 0.1, 44100, 0.6)
        print("TARS: Sleeping...")

        detected_speech = False
        silent_frames = 0
        max_iterations = 100  # Prevent infinite loops

        try:
            threshold_map = {
                1: 2,            # Extremely Lenient (2)
                2: 1,            # Very Lenient (1)
                3: 0,            # Lenient (0)
                4: 1e-1,         # Moderately Lenient (0.1)
                5: 1e-2,         # Moderate (0.01)
                6: 1e-3,         # Slightly Strict (0.001)
                7: 1e-4,         # Strict (0.0001)
                8: 1e-5,         # Very Strict (0.00001)
                9: 1e-6,         # Extremely Strict (0.000001)
                10: 1e-10        # Maximum Strictness (0.0000000001)
            }

            # Use default sensitivity of 2 if misconfigured
            kws_threshold = threshold_map.get(int(self.config['STT']['sensitivity']), 2)

            # Initialize LiveSpeech for detection
            speech = LiveSpeech(lm=False, keyphrase=self.WAKE_WORD, kws_threshold=kws_threshold)

            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                for iteration, phrase in enumerate(speech):
                    if iteration >= max_iterations:
                        print("DEBUG: Maximum iterations reached for wake word detection.")
                        break

                    # Convert raw audio to RMS
                    data, _ = stream.read(4000)
                    rms = self.prepare_audio_data(self.amplify_audio(data))

                    if rms > self.silence_threshold:  # Speech detected
                        detected_speech = True
                        silent_frames = 0  # Reset silent frames
                    else:
                        silent_frames += 1

                    if silent_frames > self.MAX_SILENT_FRAMES:  # Too much silence
                        print("DEBUG: Exiting due to extended silence.")
                        break

                    # Process wake word
                    if self.WAKE_WORD in phrase.hypothesis().lower():
                        # Reset states before returning
                        detected_speech = False
                        silent_frames = 0

                        if self.config['STT']['use_indicators']:
                            self.play_beep(1200, 0.1, 44100, 0.8)  # Wake tone

                        wake_response = random.choice(self.WAKE_WORD_RESPONSES)
                        print(f"TARS: {wake_response}")

                        #clear the variable if it matters...
                        speech = ''

                        # Trigger callback if defined
                        if self.wake_word_callback:
                            self.wake_word_callback(wake_response)

                        return True

        except Exception as e:
            print(f"ERROR: Wake word detection failed: {e}")

        return False

#Transcripe functions
    def _transcribe_utterance(self):
        """
        Process a user utterance after wake word detection.
        """
        #print(f"STAT: Listening...")
        try:
            if self.config['STT']['stt_processor'] == 'whisper':
                result = self._transcribe_with_whisper()
            elif self.config['STT']['stt_processor'] == 'external':
                result = self._transcribe_with_server()
            else:
                result = self._transcribe_with_vosk()
                
            # Call post-utterance callback if utterance was detected recently, otherwise return to wake word detection
            if self.post_utterance_callback and result:
                if not hasattr(self, 'loopcheck'):
                    self.loopcheck = 0 

                self.loopcheck += 1
                if self.loopcheck > 10:
                    print(f"\r{' ' * 40}\r", end="", flush=True)  # Clear the last line
                    self._detect_wake_word()
                    return
                
                self.post_utterance_callback()

        except Exception as e:
            print(f"ERROR: Utterance transcription failed: {e}")

    def _transcribe_with_vosk(self):
        """
        Transcribe audio using the local Vosk model.
        """
        recognizer = KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
        detected_speech = False
        silent_frames = 0
        max_silent_frames = 20  # Adjust based on desired duration (~1.25 seconds)

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=8000,  # Larger block size
            latency='high'
        ) as stream:
            for _ in range(50):  # Limit duration (~12.5 seconds)
                data, _ = stream.read(4000)
                data = self.amplify_audio(data)  # Apply amplification

                is_silence, detected_speech, silent_frames = self._is_silence_detected(
                    data, detected_speech, silent_frames, max_silent_frames
                )
                if is_silence:
                    break

                if recognizer.AcceptWaveform(data.tobytes()):
                    result = recognizer.Result()
                    if self.utterance_callback:
                        self.utterance_callback(result)
                    return result

        #print(f"INFO: No transcription within duration limit.")
        return None

    def _transcribe_with_whisper(self):
        """
        Transcribe audio using the Whisper model with optimized preprocessing and error handling.
        """
        if not self.whisper_model:
            print("ERROR: Whisper model not loaded. Transcription cannot proceed.")
            return None

        try:
            # Initialize audio buffer
            audio_buffer = BytesIO()
            detected_speech = False
            silent_frames = 0
            max_silent_frames = 20  # ~1.25 seconds of silence

            # Record audio stream
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                with wave.open(audio_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.SAMPLE_RATE)

                    for _ in range(100):  # Limit maximum recording duration (~12.5 seconds)
                        data, _ = stream.read(4000)
                        wf.writeframes(data.tobytes())

                        # Check for silence
                        is_silence, detected_speech, silent_frames = self._is_silence_detected(
                            data, detected_speech, silent_frames, max_silent_frames
                        )
                        if is_silence:
                            if not detected_speech:
                                #print("INFO: Silence detected without speech. Exiting transcription.")
                                return None  # Return to wake word detection
                            break  # End recording if silence follows speech

            # Validate audio buffer
            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                print("ERROR: Audio buffer is empty. No audio recorded.")
                return None

            # Decode and preprocess audio data
            audio_buffer.seek(0)
            audio_data, sample_rate = sf.read(audio_buffer, dtype="float32")
            #print(f"DEBUG: Audio data shape: {audio_data.shape}, Sample rate: {sample_rate}")

            # Normalize and resample audio if necessary
            audio_data = np.clip(audio_data, -1.0, 1.0)
            if sample_rate != 16000:
                #print("DEBUG: Resampling audio to 16 kHz.")
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

            # Trim or pad audio to Whisper's requirements
            audio_data = whisper.pad_or_trim(audio_data)

            # Generate Mel spectrogram
            mel = whisper.log_mel_spectrogram(audio_data).to(self.whisper_model.device)

            # Perform transcription
            options = whisper.DecodingOptions(fp16=False)  # Disable fp16 for CPU inference
            result = whisper.decode(self.whisper_model, mel, options)

            # Process and return transcription
            if hasattr(result, "text") and result.text:
                transcribed_text = result.text.strip()
                formatted_result = {"text": transcribed_text}
                #print(f"INFO: Transcription completed: {transcribed_text}")

                # Trigger callback if available
                if self.utterance_callback:
                    self.utterance_callback(json.dumps(formatted_result))  # Send JSON string to the callback
                return formatted_result
            else:
                print("ERROR: No transcribed text received from Whisper.")
                return None

        except Exception as e:
            print(f"ERROR: Whisper transcription failed: {e}")
            return None

    def _transcribe_with_server(self):
        """
        Transcribe audio by sending it to a server for processing.
        """
        try:
            audio_buffer = BytesIO()
            silent_frames = 0
            max_silent_frames = self.MAX_SILENT_FRAMES  # Use the configured silent frame threshold

            #print(f"STAT: Starting audio recording...")
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                with wave.open(audio_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.SAMPLE_RATE)

                    for _ in range(self.MAX_RECORDING_FRAMES):  # Limit maximum recording duration
                        data, _ = stream.read(4000)
                        rms = self.prepare_audio_data(self.amplify_audio(data))

                        # Check if audio data exceeds the silence threshold
                        if rms > self.silence_threshold:
                            silent_frames = 0  # Reset silent frames
                            wf.writeframes(data.tobytes())
                        else:
                            silent_frames += 1
                            if silent_frames > max_silent_frames:
                                #print("INFO: No significant audio detected, stopping recording.")
                                break

                # Ensure the audio buffer is not empty
                audio_buffer.seek(0)
                if audio_buffer.getbuffer().nbytes == 0:
                    print(f"ERROR: Audio buffer is empty. No audio recorded.")
                    return None

            # Send the audio to the server
            #print(f"STAT: Sending audio to server...")
            files = {"audio": ("audio.wav", audio_buffer, "audio/wav")}
            response = requests.post(
                f"{self.config['STT']['external_url']}/save_audio", files=files, timeout=10
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
            print(f"ERROR: Server request failed: {e}")
        return None


#MISC
    def _is_silence_detected(self, data: np.ndarray, detected_speech: bool, silent_frames: int, max_silent_frames: int) -> tuple[bool, bool, int]:
        """
        Determine if silence is detected based on RMS threshold.

        Args:
            data (np.ndarray): Audio data for analysis.
            detected_speech (bool): Whether speech has been detected.
            silent_frames (int): Consecutive frames detected as silent.
            max_silent_frames (int): Maximum allowable silent frames before concluding silence.

        Returns:
            tuple[bool, bool, int]: 
                - `True` if silence exceeds the max allowed silent frames.
                - Updated `detected_speech` state.
                - Updated count of `silent_frames`.
        """
        # Calculate the RMS value of the audio data
        rms = self.prepare_audio_data(data)

        if rms is None:  # Handle invalid RMS calculation
            return False, detected_speech, silent_frames

        # Check if the current frame is silent
        if rms > self.silence_threshold:  # Speech detected
            detected_speech = True
            silent_frames = 0  # Reset silent frame counter
        else:  # Silence detected
            silent_frames += 1
            if silent_frames > max_silent_frames:  # Exceeds max silent frames
                return True, detected_speech, silent_frames

        return False, detected_speech, silent_frames

    def prepare_audio_data(self, data: np.ndarray) -> Optional[float]:
        """
        Prepare and sanitize audio data for further processing.
        - Flattens data.
        - Sanitizes invalid or extreme values.
        - Calculates and returns RMS value.

        Parameters:
        - data (np.ndarray): Raw audio data.

        Returns:
        - Optional[float]: RMS value of the audio data, or None if the data is invalid.
        """
        if data.size == 0:
            print(f"WARNING: Received empty audio data.")
            return None  # Invalid data

        # Flatten and sanitize audio data
        data = data.reshape(-1).astype(np.float64)  # Convert to 1D and float64 for precision
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)  # Replace invalid values
        data = np.clip(data, -32000, 32000)  # Clip extreme values to avoid issues

        # Check for invalid or silent data
        if np.all(data == 0):
            print(f"WARNING: Audio data is all zeros or silent.")
            return None  # Invalid data

        # Calculate RMS (Root Mean Square)
        try:
            rms = np.sqrt(np.mean(np.square(data)))
            return rms
        except Exception as e:
            print(f"ERROR: Failed to calculate RMS: {e}")
            return None  # Error during RMS calculation

    def amplify_audio(self, data: np.ndarray) -> np.ndarray:
        """
        Amplify audio data using the set amplification gain.

        Parameters:
        - data (np.ndarray): Raw audio data.

        Returns:
        - np.ndarray: Amplified audio data.
        """
        return np.clip(data * self.amp_gain, -32768, 32767).astype(np.int16)

    def _measure_background_noise(self):
        """
        Measure the background noise level for 2-3 seconds and set the silence threshold.
        """
        silence_margin = 2.5  # Add a 250% margin to background noise level
        print(f"INFO: Measuring background noise...")

        spinner = ['|', '/', '-', '\\']  # Spinner symbols
        try:
            background_rms_values = []
            total_frames = 20  # 20 frames ~ 2-3 seconds

            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=8000,  # Larger block size
                latency='high',  # High latency to reduce underruns
            ) as stream:
                for i in range(total_frames):
                    data, _ = stream.read(4000)

                    # Prepare and amplify the data stream
                    rms = self.prepare_audio_data(self.amplify_audio(data))
                    background_rms_values.append(rms)

                    # Display spinner animation with clear line
                    spinner_frame = spinner[i % len(spinner)]  # Rotate spinner symbol
                    print(f"\rSTAT: Measuring Noise Level... {spinner_frame}", end="", flush=True)
                    time.sleep(0.1)  # Simulate processing time for smooth animation

                # Clear the spinner and print the final result
                print("\r", end="", flush=True)  # Clear spinner line

            # Calculate the threshold
            if background_rms_values:  # Ensure the list is not empty
                background_noise = np.mean(background_rms_values)
            else:
                background_noise = 0  # Fallback if no valid values are collected
            self.silence_threshold = max(background_noise * silence_margin, 10)  # Avoid setting a very low threshold

            #convert the threshold to dbz for easy of reading
            db = 20 * np.log10(self.silence_threshold)  # Convert RMS to decibels

            # Clear the spinner and print the result
            print(f"\r{' ' * 40}\r", end="", flush=True)  # Clear the line
            print(f"INFO: Silence threshold set to: {db:.2f} dB")

        except Exception as e:
            print(f"ERROR: Failed to measure background noise: {e}")

    def find_default_mic_sample_rate(self):
        """Finds the sample rate (in Hz) of the actual default microphone, rounded to an integer."""
        try:
            # Get the default input device index
            default_device_index = sd.default.device[0]  # Input device index
            if default_device_index is None:
                return "No default microphone detected."

            # Query the device info
            device_info = sd.query_devices(default_device_index, kind='input')
            sample_rate = int(device_info['default_samplerate'])  # Convert to integer

            return sample_rate
        except Exception as e:
            return f"Error: {e}"

    def play_beep(self, frequency, duration, sample_rate, volume):
        """
        Play a beep sound to indicate the system is listening.

        Parameters:
        - frequency (int): Frequency of the beep in Hz (e.g., 1000 for 1kHz).
        - duration (float): Duration of the beep in seconds.
        - sample_rate (int): Sample rate in Hz (default: 44100).
        - volume (float): Volume of the beep (0.0 to 1.0).
        """
        # Generate a sine wave
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = volume * np.sin(2 * np.pi * frequency * t)
        
        # Play the sine wave
        sd.play(wave, samplerate=sample_rate)
        sd.wait()  # Wait until the sound finishes playing

#Callbacks
    def set_wake_word_callback(self, callback: Callable[[str], None]):
        """
        Set the callback function for wake word detection.
        """
        self.wake_word_callback = callback

    def set_utterance_callback(self, callback: Callable[[str], None]):
        """
        Set the callback function for user utterance.
        """
        self.utterance_callback = callback

    def set_post_utterance_callback(self, callback):
        """
        Set a callback to execute after the utterance is handled.
        """
        self.post_utterance_callback = callback