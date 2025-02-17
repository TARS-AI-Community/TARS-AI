#!/usr/bin/env python3
"""
This script listens for the keyword "hey mori" using one of three VAD methods.
Set VAD_METHOD to "vosk", "webrtc", or "silero" to choose your VAD engine.
"""

import time
import numpy as np
import sounddevice as sd
import torch
import librosa

# For pocketsphinx keyword spotting
from pocketsphinx import LiveSpeech

# Global option: choose one of "vosk", "webrtc", or "silero"
VAD_METHOD = "silero"  # Change to "vosk" or "webrtc" as desired

# For RMS-based (vosk-like) detection, set a threshold (adjust as needed)
RMS_THRESHOLD = 500

# --- VAD Engine Setup ---
if VAD_METHOD == "webrtc":
    try:
        import webrtcvad
        vad = webrtcvad.Vad(3)  # mode 3: most aggressive
    except ImportError:
        print("py-webrtcvad is not installed. Please install it or change VAD_METHOD.")
        exit(1)
elif VAD_METHOD == "silero":
    try:
        # Load Silero VAD from torch.hub.
        # The repository now returns a tuple with (model, ...) – we take the first element.
        silero_vad_tuple = torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)
        if isinstance(silero_vad_tuple, (tuple, list)):
            silero_vad = silero_vad_tuple[0]
        else:
            silero_vad = silero_vad_tuple
    except Exception as e:
        print("Failed to load Silero VAD:", e)
        exit(1)

# --- VAD Detection Functions ---
def compute_rms(data: np.ndarray) -> float:
    """Compute the RMS value of the audio data."""
    return np.sqrt(np.mean(np.square(data.astype(np.float64))))

def detect_speech_vosk(data: np.ndarray) -> bool:
    """Simple RMS threshold detection."""
    return compute_rms(data) > RMS_THRESHOLD

def detect_speech_webrtc(data: np.ndarray, sample_rate: int) -> bool:
    """
    Use py-webrtcvad.
    Split the data into 30ms frames and check each frame.
    """
    frame_duration_ms = 30
    frame_length = int(sample_rate * frame_duration_ms / 1000)
    num_frames = len(data) // frame_length
    for i in range(num_frames):
        frame = data[i * frame_length:(i + 1) * frame_length]
        # Convert the frame to bytes (16-bit PCM, little-endian)
        if vad.is_speech(frame.tobytes(), sample_rate):
            return True
    return False

def detect_speech_silero(data: np.ndarray, sample_rate: int) -> bool:
    """
    Use Silero VAD.
    The Silero VAD model (for 16kHz) expects a window of exactly 512 samples.
    This function segments the input audio into non-overlapping windows of 512 samples,
    applies the model, and if any window’s output exceeds 0.5, returns True.
    """
    # Determine the expected window size (512 for 16kHz)
    window_size = 512  # (for 16kHz)
    # Split data into non-overlapping windows; pad last window if necessary
    if len(data) < window_size:
        data = np.pad(data, (0, window_size - len(data)), mode='constant')
    num_windows = int(np.ceil(len(data) / window_size))
    speech_found = False
    for i in range(num_windows):
        start = i * window_size
        end = start + window_size
        window = data[start:end]
        if len(window) < window_size:
            window = np.pad(window, (0, window_size - len(window)), mode='constant')
        # Convert window to tensor, normalize to [-1, 1], and add batch dimension.
        win_tensor = torch.tensor(window.astype(np.float32)) / 32768.0
        win_tensor = win_tensor.unsqueeze(0)  # shape (1, 512)
        # Call the Silero VAD model.
        # The forward expects two arguments: x (tensor) and sr (int).
        output = silero_vad(win_tensor, sample_rate)
        # output is a tensor; check if the maximum value exceeds a threshold.
        if output.max().item() > 0.5:
            speech_found = True
            break
    return speech_found

# --- Keyword Detection ---
def keyword_listener():
    """
    Use pocketsphinx LiveSpeech for keyword spotting.
    It is configured to listen for "hey mori" with a very low threshold.
    """
    speech = LiveSpeech(lm=False, keyphrase="hey mori", kws_threshold=1e-20)
    for phrase in speech:
        text = phrase.hypothesis().lower()
        if "hey mori" in text:
            print("Keyword 'hey mori' detected!")
            return

# --- Main Loop ---
def main():
    sample_rate = 16000  # Hz
    duration = 1         # seconds per recording chunk

    print(f"Using VAD method: {VAD_METHOD}")
    print("Listening for speech...")

    while True:
        # Record a chunk of audio (1 second)
        audio = sd.rec(int(sample_rate * duration), samplerate=sample_rate, channels=1, dtype="int16")
        sd.wait()
        audio = audio.flatten()

        if VAD_METHOD == "vosk":
            speech_present = detect_speech_vosk(audio)
        elif VAD_METHOD == "webrtc":
            speech_present = detect_speech_webrtc(audio, sample_rate)
        elif VAD_METHOD == "silero":
            speech_present = detect_speech_silero(audio, sample_rate)
        else:
            speech_present = False

        if speech_present:
            print("Speech detected. Now listening for keyword 'hey mori'...")
            keyword_listener()
        else:
            print("No speech detected.")

        time.sleep(0.1)

if __name__ == "__main__":
    main()
