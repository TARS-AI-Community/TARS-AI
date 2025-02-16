import sounddevice as sd
import soundfile as sf
from io import BytesIO
from piper.voice import PiperVoice
import asyncio
import wave
import re
import os
import ctypes

# === Custom Modules ===
from modules.module_config import load_config
CONFIG = load_config()

# Define the error handler function type
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
)

# Define the custom error handler function
def py_error_handler(filename, line, function, err, fmt):
    pass  # Suppress the error message

# Create a C-compatible function pointer
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

# Load the ALSA library
asound = ctypes.cdll.LoadLibrary('libasound.so')

# Load the Piper model globally
script_dir = os.path.dirname(__file__)
model_path = os.path.join(script_dir, '..', 'tts/TARS.onnx')

if CONFIG['TTS']['ttsoption'] == 'piper':
    voice = PiperVoice.load(model_path)

async def synthesize(voice, chunk):
    """
    Synthesize a chunk of text into a BytesIO buffer.
    """
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit samples
        wav_file.setframerate(voice.config.sample_rate)
        try:
            voice.synthesize(chunk, wav_file)
        except TypeError as e:
            print(f"ERROR: {e}")
    wav_buffer.seek(0)
    return wav_buffer

async def play_audio(wav_buffer):
    """
    Play audio from a BytesIO buffer.
    """
    data, samplerate = sf.read(wav_buffer, dtype='float32')
    # Set the custom error handler
    asound.snd_lib_error_set_handler(c_error_handler)
    sd.play(data, samplerate)
    await asyncio.sleep(len(data) / samplerate)  # Wait until playback finishes
    # Reset to the default error handler
    asound.snd_lib_error_set_handler(None)

async def text_to_speech_with_pipelining(text):
    """
    Converts text to speech using the specified Piper model and streams audio playback with pipelining.
    """
    # Split text into smaller chunks
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # Process and play chunks sequentially
    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize(voice, chunk.strip())
            await play_audio(wav_buffer)