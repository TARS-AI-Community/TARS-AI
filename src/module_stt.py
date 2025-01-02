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
from datetime import datetime
from io import BytesIO
import time
import wave
import numpy as np
import json
from typing import Callable, Optional
from vosk import SetLogLevel

# Suppress Vosk logs by setting the log level to 0 (ERROR and above)
SetLogLevel(-1)  # Adjust to 0 for minimal output or -1 to suppress all logs

#needed to supress warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# === Class Definition ===
class STTManager:
    def __init__(self, config, shutdown_event: threading.Event, amp_gain: float = 4.0):
        """
        Initialize the STTManager.

        Parameters:
        - config (dict): Configuration dictionary.
        - shutdown_event (Event): Event to signal stopping the assistant.
        """
        self.config = config
        self.shutdown_event = shutdown_event
        self.SAMPLE_RATE = 16000
        self.running = False
        self.wake_word_callback: Optional[Callable[[str], None]] = None
        self.utterance_callback: Optional[Callable[[str], None]] = None
        self.amp_gain = amp_gain  # Amplification gain factor
        self.post_utterance_callback: Optional[Callable] = None
        self.vosk_model = None
        self.silence_threshold = 10  # Default value; updated dynamically
        self.WAKE_WORD = self.config['STT']['wake_word']
        self.TARS_RESPONSES = [
            "Yes? What do you need?",
            "Ready and listening.",
            "At your service.",
            "Go ahead.",
            "What can I do for you?",
            "Listening. What's up?",
            "Here. What do you require?",
            "Yes? I'm here.",
            "Standing by.",
            "Online and awaiting your command."
        ]
        self._load_vosk_model()
        self._measure_background_noise()

#Main Thread Calls
    def start(self):
        """
        Start the STTManager in a separate thread.
        """
        self.running = True
        self.thread = threading.Thread(
            target=self._stt_processing_loop, name="STTThread", daemon=True
        )
        self.thread.start()

    def stop(self):
        """
        Stop the STTManager.
        """
        self.running = False
        self.shutdown_event.set()
        self.thread.join()

#Vosk INIT
    def _download_vosk_model(self, url, dest_folder):
        """Download the Vosk model from the specified URL with basic progress display."""
        file_name = url.split("/")[-1]
        dest_path = os.path.join(dest_folder, file_name)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Downloading Vosk model from {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0

        with open(dest_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
                downloaded_size += len(chunk)
                progress = (downloaded_size / total_size) * 100 if total_size else 0
                print(f"\r[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Download progress: {progress:.2f}%", end="")
                
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Download complete. Extracting...")
        if file_name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(dest_path, 'r') as zip_ref:
                zip_ref.extractall(dest_folder)
            os.remove(dest_path)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Zip file deleted.")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Extraction complete.")

    def _load_vosk_model(self):
        """
        Initialize the Vosk model for local STT transcription.
        """
        if not self.config['STT']['use_server']:
            vosk_model_path = os.path.join(os.getcwd(), "stt", self.config['STT']['vosk_model'])
            if not os.path.exists(vosk_model_path):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Vosk model not found. Downloading...")
                download_url = f"https://alphacephei.com/vosk/models/{self.config['STT']['vosk_model']}.zip"  # Example URL
                self._download_vosk_model(download_url, os.path.join(os.getcwd(), "stt"))
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Restarting model loading...")
                self._load_vosk_model()
                return

            self.vosk_model = Model(vosk_model_path)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Vosk model loaded successfully.")

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
                    # If wake word detected, transcribe the user utterance
                    self._transcribe_utterance()
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error in STT processing loop: {e}")
        finally:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: STT Manager stopped.")

#Detect Wake
    def _detect_wake_word(self) -> bool:
        """
        Detect the wake word using Pocketsphinx with enhanced false-positive filtering.
        """
        
        # Listening State
        if self.config['STT']['use_indicators']:
            self.play_beep(400, 0.1, 44100, 0.6) #sleeping tone
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TARS: Sleeping...")
        try:
            kws_threshold = 1e-5  # Stricter keyword threshold

            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                speech = LiveSpeech(lm=False, keyphrase=self.WAKE_WORD, kws_threshold=kws_threshold)

                for phrase in speech:
                    # Convert raw audio to RMS
                    data, _ = stream.read(4000)
                    rms = self.prepare_audio_data(self.amplify_audio(data))

                    # Process wake word
                    if self.WAKE_WORD in phrase.hypothesis().lower():
                        if self.config['STT']['use_indicators']:
                            self.play_beep(1200, 0.1, 44100, 0.8) #wake tone
                        wake_response = random.choice(self.TARS_RESPONSES)
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TARS: {wake_response}")

                        # If a callback is set, send the wake_response
                        if self.wake_word_callback:
                            self.wake_word_callback(wake_response)
                        return True

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Wake word detection failed: {e}")
        return False

#Transcripe functions
    def _transcribe_utterance(self):
        """
        Process a user utterance after wake word detection.
        """
        #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Listening...")
        try:
            if self.config['STT']['use_server']:
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Utterance transcription failed: {e}")

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

        #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: No transcription within duration limit.")
        return None

    def _transcribe_with_server(self):
        """
        Transcribe audio by sending it to a server for processing.
        """
        try:
            audio_buffer = BytesIO()
            detected_speech = False
            silent_frames = 0
            max_silent_frames = 3  # ~1.25 seconds of silence

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Starting audio recording...")
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                with wave.open(audio_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.SAMPLE_RATE)

                    for _ in range(50):  # Limit maximum recording duration (~12.5 seconds)
                        data, _ = stream.read(4000)
                        data = self.amplify_audio(data)  # Apply amplification
                        wf.writeframes(data.tobytes())

                        is_silence, detected_speech, silent_frames = self._is_silence_detected(
                            data, detected_speech, silent_frames, max_silent_frames
                        )
                        if is_silence:
                            break

            # Ensure the audio buffer is not empty
            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Audio buffer is empty. No audio recorded.")
                return None

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Sending audio to server...")
            files = {"audio": ("audio.wav", audio_buffer, "audio/wav")}
            response = requests.post(f"{self.config['STT']['server_url']}/save_audio", files=files, timeout=10)

            if response.status_code == 200:
                transcription = response.json().get("transcription", [])
                if transcription:
                    raw_text = transcription[0].get("text", "").strip()
                    formatted_result = {
                        "text": raw_text,
                        "result": [
                            {"conf": 1.0, "start": seg.get("start", 0), "end": seg.get("end", 0), "word": seg.get("text", "")}
                            for seg in transcription
                        ],
                    }
                    if self.utterance_callback:
                        self.utterance_callback(json.dumps(formatted_result))
                    return formatted_result

        except requests.RequestException as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Server request failed: {e}")
        return None

#MISC
    def _is_silence_detected(self, data, detected_speech, silent_frames, max_silent_frames):
        """
        Check if silence has been detected in the audio data.
        """
        rms = self.prepare_audio_data(data)

        # Silence detection logic
        #if rms < self.silence_threshold:
            #print(f"Silence {rms} rms | {self.silence_threshold} threshold")  # Voice detected
        #else:
            #print(f"SOUND__ {rms} rms | {self.silence_threshold} threshold")


        if rms > self.silence_threshold:  # Voice detected
            #if not detected_speech:
                #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Speech detected.")
            detected_speech = True
            silent_frames = 0  # Reset silent frames
        else:  # Silence detected
            silent_frames += 1
            if silent_frames > max_silent_frames:
                #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Silence detected.")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Received empty audio data.")
            return None  # Invalid data

        # Flatten and sanitize audio data
        data = data.reshape(-1).astype(np.float64)  # Convert to 1D and float64 for precision
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)  # Replace invalid values
        data = np.clip(data, -32000, 32000)  # Clip extreme values to avoid issues

        # Check for invalid or silent data
        if np.all(data == 0):
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Audio data is all zeros or silent.")
            return None  # Invalid data

        # Calculate RMS (Root Mean Square)
        try:
            rms = np.sqrt(np.mean(np.square(data)))
            return rms
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to calculate RMS: {e}")
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
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Measuring background noise...")

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

                    #prepare and amp the data stream
                    rms = self.prepare_audio_data(self.amplify_audio(data))
                    background_rms_values.append(rms)

                    # Display spinner animation
                    spinner_frame = spinner[i % len(spinner)]  # Rotate spinner symbol
                    print(f"\r[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Measuring Noise Level... {spinner_frame}", end="", flush=True)
                    time.sleep(0.1)  # Simulate processing time for smooth animation

            # Calculate the threshold
            if background_rms_values:  # Ensure the list is not empty
                background_noise = np.mean(background_rms_values)
            else:
                background_noise = 0  # Fallback if no valid values are collected
            self.silence_threshold = max(background_noise * silence_margin, 10)  # Avoid setting a very low threshold

            # Clear the spinner and print the result
            print(f"\r{' ' * 40}\r", end="", flush=True)  # Clear the line
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Silence threshold set to: {self.silence_threshold:.2f}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to measure background noise: {e}")

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