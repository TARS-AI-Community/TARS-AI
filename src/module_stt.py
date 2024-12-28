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

# === Class Definition ===
class STTManager:
    def __init__(self, config, shutdown_event: threading.Event):
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

    def _load_vosk_model(self):
        """
        Initialize the Vosk model for local STT transcription.
        """
        if not self.config['STT']['use_server']:
            vosk_model_path = os.path.join(os.getcwd(), "stt", "vosk-model-small-en-us-0.15")
            if not os.path.exists(vosk_model_path):
                raise FileNotFoundError(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Vosk model not found. Download from: https://alphacephei.com/vosk/models"
                )
            self.vosk_model = Model(vosk_model_path)

    def _measure_background_noise(self):
        """
        Measure the background noise level for 2-3 seconds and set the silence threshold.
        """
        silence_margin = 1.2  # Add a 20% margin to background noise level
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Measuring background noise...")

        spinner = ['|', '/', '-', '\\']  # Spinner symbols
        try:
            background_rms_values = []
            total_frames = 20  # 20 frames ~ 2-3 seconds

            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                for i in range(total_frames):
                    data, _ = stream.read(4000)
                    if data.size == 0 or not np.isfinite(data).all():
                        rms = 0  # Assign zero RMS for invalid or empty data
                    else:
                        rms = np.sqrt(np.mean(np.square(data)))
                    background_rms_values.append(rms)

                    # Display spinner animation
                    spinner_frame = spinner[i % len(spinner)]  # Rotate spinner symbol
                    print(f"\rMeasuring... {spinner_frame}", end="", flush=True)
                    time.sleep(0.1)  # Simulate processing time for smooth animation

            # Calculate the threshold
            background_noise = np.mean(background_rms_values)
            self.silence_threshold = max(background_noise * silence_margin, 10)  # Avoid setting a very low threshold

            # Clear the spinner and print the result
            print(f"\r{' ' * 40}\r", end="", flush=True)  # Clear the line
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Silence threshold set to: {self.silence_threshold:.2f}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to measure background noise: {e}")

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

    def _detect_wake_word(self) -> bool:
        """
        Detect the wake word using Pocketsphinx.
        """
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TARS: Idle...")
        try:
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                speech = LiveSpeech(lm=False, keyphrase=self.WAKE_WORD, kws_threshold=1e-20)
                for phrase in speech:
                    if self.WAKE_WORD in phrase.hypothesis().lower():
                        wake_response = random.choice(self.TARS_RESPONSES)
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TARS: {wake_response}")

                        # If a callback is set, send the wake_response
                        if self.wake_word_callback:
                            self.wake_word_callback(wake_response)
                        return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Wake word detection failed: {e}")
        return False
        
        # STUB: Simulate wake word detection
        # wake_response = "Hello. How can I help you?"
        # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TARS: {wake_response}")
        # self.wake_word_callback(wake_response)
        # return True

    def _transcribe_utterance(self):
        """
        Process a user utterance after wake word detection.
        """
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Listening...")
        try:
            if self.config['STT']['use_server']:
                result = self._transcribe_with_server()
            else:
                result = self._transcribe_with_vosk()
            
            # Call post-utterance callback if utterance was detected recently, otherwise return to wake word detection
            if self.post_utterance_callback and result:
                self.post_utterance_callback()

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Utterance transcription failed: {e}")

    def _transcribe_with_vosk(self):
        """
        Transcribe audio using the local Vosk model.
        """
        recognizer = KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16", device=self.mic_index) as stream:
            for _ in range(50):  # Limit duration (~12.5 seconds)
                data, _ = stream.read(4000)
                if recognizer.AcceptWaveform(data.tobytes()):
                    result = recognizer.Result()
                    # print(f"[DEBUG] Recognized: {result}")
                    if self.utterance_callback:
                        self.utterance_callback(result)
                    return result
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: No valid transcription within duration limit.")
        return None
    
        # STUB: Simulate Vosk transcription
        # test_message = {
        #     "text": "How are you doing?",
        #     "result": []
        # }
        
        # # Serialize the dictionary to JSON string
        # message_json = json.dumps(test_message)
        # self.utterance_callback(message_json)
        # return True

    def _transcribe_with_server(self):
        """
        Transcribe audio by sending it to a server for processing.
        """
        try:
            audio_buffer = BytesIO()
            silent_frames = 0
            max_silent_frames = 2  # ~1.25 seconds of silence
            detected_speech = False

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Starting audio recording...")
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16") as stream:
                with wave.open(audio_buffer, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.SAMPLE_RATE)

                    speech_frames = 0  # Track consecutive speech frames
                    max_duration_frames = 50  # Limit maximum recording duration (~12.5 seconds)
                    total_frames = 0

                    while total_frames < max_duration_frames:  # Prevent infinite loops
                        data, _ = stream.read(4000)
                        wf.writeframes(data.tobytes())

                        # Calculate RMS (Root Mean Square) energy of the audio data
                        rms = np.sqrt(np.mean(np.square(data)))

                        if rms > self.silence_threshold:  # Voice detected
                            if not detected_speech:
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Speech detected.")
                            detected_speech = True
                            speech_frames += 1
                            silent_frames = 0  # Reset silent frames
                        elif detected_speech:  # Silence detected after speech
                            silent_frames += 1
                            if silent_frames > max_silent_frames:
                                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Silence detected.")
                                break

                        total_frames += 1

            # Ensure the audio buffer is not empty
            audio_buffer.seek(0)
            buffer_size = audio_buffer.getbuffer().nbytes
            if buffer_size == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Audio buffer is empty. No audio recorded.")
                return None

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Sent {buffer_size} bytes of audio")
            files = {"audio": ("audio.wav", audio_buffer, "audio/wav")}

            response = requests.post(self.config["STT"]["server_url"], files=files, timeout=10)

            # Handle server response
            if response.status_code == 200:
                try:
                    # Parse the JSON response
                    transcription = response.json().get("transcription", [])
                    if isinstance(transcription, list) and transcription:
                        raw_text = transcription[0].get("text", "").strip()

                        # Format as Vosk-style JSON
                        formatted_result = {
                            "text": raw_text,
                            "result": [
                                {
                                    "conf": 1.0,
                                    "end": seg.get("end", 0),
                                    "start": seg.get("start", 0),
                                    "word": seg.get("text", ""),
                                }
                                for seg in transcription
                            ],
                        }

                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] USER: {formatted_result['text']}")

                        # If a callback is set, send the formatted JSON
                        if self.utterance_callback:
                            self.utterance_callback(json.dumps(formatted_result))  # Send as a JSON string

                        return formatted_result
                    else:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Unexpected transcription format or empty transcription.")
                        return None
                except Exception as e:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Exception while processing transcription: {e}")
                    return None

        except requests.exceptions.Timeout:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Server request timed out.")
        except requests.exceptions.RequestException as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Request error during server transcription: {e}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Unexpected error during server transcription: {e}")
        finally:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Exiting _transcribe_with_server.")
