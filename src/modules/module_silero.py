"""
Enhanced Silero TTS with TARS Effects, Audio Normalization, and Better Playback
"""

import io
import torch
import re
import os
import wave
from pydub import AudioSegment
import numpy as np

from modules.module_messageQue import queue_message

# Set relative path for model storage
model_dir = os.path.join(os.path.dirname(__file__), "..", "stt")  # Relative to script location
torch.hub.set_dir(model_dir)  # Set PyTorch hub directory

# === Custom Modules ===
from module_config import load_config
CONFIG = load_config()

# Load Silero model globally
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if CONFIG['TTS']['ttsoption'] == 'silero':
    model, example_texts = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language="en",
        speaker="v3_en"  # Model version, not speaker ID
    )
    model.to(device)
    sample_rate = 24000  # Set to Silero's recommended sample rate
    speaker = "en_2"  # Use a valid speaker ID

def apply_tars_effects(audio):
    """
    Apply TARS-like effects: pitch change, speed up, reverb, and echo.
    """
    lower_rate = int(sample_rate * 0.88)
    audio = audio._spawn(audio.raw_data, overrides={"frame_rate": lower_rate})
    audio = audio.set_frame_rate(sample_rate)
    audio = audio.speedup(playback_speed=1.42)
    # Apply echo and reverb
    reverb_decay = -2
    delay_ms = 3
    echo1 = audio - reverb_decay
    echo2 = echo1 - 1
    audio = audio.overlay(echo1, position=delay_ms)
    audio = audio.overlay(echo2, position=delay_ms * 2)  # Fixed the delay overlap
    return audio

async def synthesize_silero(text):
    """
    Synthesize a chunk of text into a BytesIO buffer using Silero TTS with TARS effects.
    """
    with torch.no_grad():
        audio_tensor = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)

    # Convert tensor to NumPy
    audio_np = audio_tensor.numpy()  # Convert tensor to numpy
    audio_int16 = (audio_np * 32767).astype("int16")  # Convert to 16-bit PCM

    # Convert NumPy audio to Pydub AudioSegment
    audio = AudioSegment(
        audio_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,  # 16-bit PCM = 2 bytes per sample
        channels=1  # Mono
    )

    # Apply TARS-like effects
    audio = apply_tars_effects(audio)

    # Convert Pydub AudioSegment back to BytesIO WAV buffer
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit samples
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.raw_data)

    wav_buffer.seek(0)
    return wav_buffer  # Return the BytesIO object

async def text_to_speech_with_pipelining_silero(text):
    """
    Converts text to speech using Silero TTS, applies TARS effects, and streams audio as it's generated.
    """
    # Split text into smaller chunks
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # Yield each audio chunk as soon as it's ready
    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize_silero(chunk.strip())
            yield wav_buffer  # Return the chunk for external playback