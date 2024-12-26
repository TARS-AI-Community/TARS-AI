import os
import random
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from pocketsphinx import LiveSpeech
from threading import Event
import requests
from datetime import datetime
from io import BytesIO
import wave
import configparser
import sys
import numpy as np
import json


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Set the working directory to the base directory
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.append(os.getcwd())

config = configparser.ConfigParser()
config.read('config.ini')

use_server_stt = config.getboolean("STT", "use_server")
server_url = config["STT"]["server_url"]

vosk_model = None
if not use_server_stt:
    VOSK_MODEL_PATH = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")
    if not os.path.exists(VOSK_MODEL_PATH):
        raise FileNotFoundError("Vosk model not found. Download from: https://alphacephei.com/vosk/models")
    vosk_model = Model(VOSK_MODEL_PATH)

# List of TARS-style responses
tars_responses = [
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

# Constants
WAKE_PHRASE = "hey tar"
SAMPLE_RATE = 16000


# Global running flag and callback
running = False
message_callback = None
wakeword_callback = None

def set_wakewordtts_callback(callback_function):
    """
    Set the callback function to handle wake word TTS responses.
    """
    global wakeword_callback
    wakeword_callback = callback_function

def detect_wake_word():
    """
    Continuously listens for the wake word using Pocketsphinx.
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] TARS: Idle...")

    speech = LiveSpeech(lm=False, keyphrase=WAKE_PHRASE, kws_threshold=1e-20)
    for phrase in speech:
        #print(f"Detected phrase: {phrase.hypothesis()}")
        if WAKE_PHRASE in phrase.hypothesis().lower():
            response = random.choice(tars_responses)
            print(f"[{current_time}] TARS: {response}")
            if wakeword_callback:
                wakeword_callback(response)
            return True

def transcribe_command():
    """
    Transcribes a command using either the local Vosk model or the server.
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Listening...")
    try:
        if use_server_stt:
            return transcribe_with_server()
        else:
            return transcribe_with_vosk()
    except Exception as e:
        print(f"[ERROR] Transcription failed: {e}")


def transcribe_with_vosk():
    """
    Transcribes audio locally using Vosk.
    """
    recognizer = None
    try:
        recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE)
        #print("KaldiRecognizer initialized successfully.")

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            max_duration_frames = 50  # Limit maximum recording duration (~12.5 seconds)
            total_frames = 0

            while total_frames < max_duration_frames:  # Prevent infinite loops
                data, _ = stream.read(4000)
                if recognizer.AcceptWaveform(data.tobytes()):
                    result = recognizer.Result()
                    #print(f"[DEBUG] Recognized: {result}")
                    if message_callback:
                        message_callback(result)
                    return result
                total_frames += 1
            print("[ERROR] No valid transcription within duration limit.")
            return None

    except Exception as e:
        print(f"[ERROR] Error during local transcription: {e}")
    finally:
        if recognizer:
            del recognizer


def measure_background_noise():
    """
    Measure the background noise level for 2-3 seconds and set the silence threshold.
    """
    global silence_threshold
    silence_margin = 1.2  # 20% margin above background noise

   
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Measuring background noise...")
    
    background_rms_values = []

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(20):  # Collect ~2 seconds of audio (20 frames * 4000 samples)
            data, _ = stream.read(4000)
            if data.size == 0 or not np.isfinite(data).all():
                rms = 0  # Assign zero RMS for invalid or empty data
            else:
                rms = np.sqrt(np.mean(np.square(data)))
            background_rms_values.append(rms)

    background_noise = np.mean(background_rms_values)
    silence_threshold = background_noise * silence_margin  # Add margin to background noise
    if silence_threshold < 10:
        silence_threshold = 10
    else:
        pass
    #print(f"LOAD: Measured background noise: {background_noise:.2f}")
    #print(f"LOAD: Silence threshold set to: {silence_threshold:.2f}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Silence threshold set to: {silence_threshold:.2f}")

def transcribe_with_server():
    """
    Transcribes audio by sending it to a server for processing.
    """
    try:
        audio_buffer = BytesIO()
        silent_frames = 0
        max_silent_frames = 2  # ~1.25 seconds of silence
        detected_speech = False
        noise_threshold = silence_threshold  # Minimum RMS to ignore random noise
        min_speech_duration = 4  # Require at least 4 consecutive frames of speech

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Starting audio recording...")
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            with wave.open(audio_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)

                speech_frames = 0  # Track consecutive speech frames
                max_duration_frames = 50  # Limit maximum recording duration (~12.5 seconds)
                total_frames = 0

                while total_frames < max_duration_frames:  # Prevent infinite loops
                    data, _ = stream.read(4000)
                    wf.writeframes(data.tobytes())

                    # Calculate RMS (Root Mean Square) energy of the audio data
                    rms = np.sqrt(np.mean(np.square(data)))

                    if rms > silence_threshold:  # Voice detected
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
            print("[ERROR] Audio buffer is empty. No audio recorded.")
            return None

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STAT: Sent {buffer_size} bytes of audio")
        files = {"audio": ("audio.wav", audio_buffer, "audio/wav")}

        response = requests.post(server_url, files=files, timeout=10)

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
                    if message_callback:
                        message_callback(json.dumps(formatted_result))  # Send as a JSON string

                    return formatted_result
                else:
                    print("[ERROR] Unexpected transcription format or empty transcription.")
                    return None
            except Exception as e:
                print(f"[ERROR] Exception while processing transcription: {e}")
                return None

    except requests.exceptions.Timeout:
        print("[ERROR] Server request timed out.")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request error during server transcription: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error during server transcription: {e}")
    finally:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Exiting transcribe_with_server.")




def start_stt(stop_event: Event = None):
    """
    Start the voice assistant. Listens for wake word and transcribes commands.
    """
    global running
    running = True

    try:
        while running:
            if stop_event and stop_event.is_set():
                print("Stopping STT...")
                break

            if detect_wake_word():
                transcribe_command()
    except KeyboardInterrupt:
        print("\nSTT interrupted by user.")
    except Exception as e:
        print(f"Error in STT: {e}")
    finally:
        print("STT stopped.")


def stop_stt():
    """
    Stop the voice assistant.
    """
    global running
    running = False
    print("Voice assistant stopped.")


def set_message_callback(callback):
    """
    Set the callback function to handle recognized messages.
    """
    global message_callback
    message_callback = callback