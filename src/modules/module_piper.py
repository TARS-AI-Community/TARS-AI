import sounddevice as sd
import soundfile as sf
from io import BytesIO
from piper.voice import PiperVoice
import wave
import re
import os
import ctypes
from urllib.request import urlretrieve

# === Custom Modules ===
from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

character_path = CONFIG['CHAR']['character_card_path']
character_name = os.path.splitext(os.path.basename(character_path))[0]  # Extract filename without extension

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
model_path = os.path.join(script_dir, '..', f'character/{character_name}/voice/{character_name}.onnx')

HF_BASE_URL = "https://huggingface.co/olivierdion007/TARS-AI/resolve/main"

def _download_voice_model(character, dest_path):
    """Download Piper voice model (.onnx and .onnx.json) from Hugging Face."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    for ext in [".onnx", ".onnx.json"]:
        url = f"{HF_BASE_URL}/{character}{ext}"
        local = dest_path if ext == ".onnx" else dest_path + ".json"
        if os.path.isfile(local):
            continue
        queue_message(f"[Piper] Downloading {character}{ext} from Hugging Face...")
        try:
            urlretrieve(url, local)
            size_mb = os.path.getsize(local) / (1024 * 1024)
            queue_message(f"[Piper] Downloaded {character}{ext} ({size_mb:.1f} MB)")
        except Exception as e:
            queue_message(f"[Piper] Failed to download {character}{ext}: {e}")
            if os.path.exists(local):
                os.remove(local)
            return False
    return True

voice = None
if CONFIG['TTS']['ttsoption'] == 'piper':
    if not os.path.isfile(model_path):
        queue_message("[Piper] Voice model not found, downloading from Hugging Face...")
        _download_voice_model(character_name, model_path)

    if os.path.isfile(model_path):
        try:
            voice = PiperVoice.load(model_path)
        except Exception as e:
            queue_message(f"[Piper] Failed to load voice model: {e}")
            voice = None

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
            # need both methods for compatibility
            if hasattr(voice, "synthesize_wav"):
                voice.synthesize_wav(chunk, wav_file)
            elif hasattr(voice, "synthesize"):
                voice.synthesize(chunk, wav_file)
            else:
                raise AttributeError("Neither synthesize_wav nor synthesize found in voice object")

        except Exception as e:
            queue_message(f"ERROR during synthesis: {e}")
    wav_buffer.seek(0)
    return wav_buffer

async def text_to_speech_with_pipelining_piper(text):
    """
    Converts text to speech using the Piper model and streams audio as it's generated.
    """
    if voice is None:
        queue_message("[Piper] Cannot synthesize - voice model not loaded.")
        return

    # Split text into smaller chunks
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # Yield each audio chunk as soon as it's ready
    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize(voice, chunk.strip())
            yield wav_buffer  # Return the chunk for external playback