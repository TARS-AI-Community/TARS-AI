import sounddevice as sd
import soundfile as sf
from io import BytesIO
from piper.voice import PiperVoice
import wave
import re
import os
import ctypes

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

def _is_lfs_pointer(filepath):
    """Check if a file is a Git LFS pointer instead of actual content."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(20)
            return header.startswith(b'version https://git-lfs')
    except Exception:
        return False

voice = None
if CONFIG['TTS']['ttsoption'] == 'piper':
    if not os.path.isfile(model_path):
        queue_message(f"[Piper] Voice model not found: {model_path}")
        queue_message("[Piper] Please place a valid .onnx voice model in the character voice folder.")
    elif _is_lfs_pointer(model_path):
        queue_message(f"[Piper] Voice model is a Git LFS pointer, not the actual file: {model_path}")
        queue_message("[Piper] Run 'git lfs install && git lfs pull' to download the real model file.")
    else:
        try:
            voice = PiperVoice.load(model_path)
            # Warmup: run a dummy synthesis to trigger ONNX runtime JIT
            # so the first real call doesn't pay the compilation cost.
            _warmup_buf = BytesIO()
            with wave.open(_warmup_buf, 'wb') as _wf:
                _wf.setnchannels(1)
                _wf.setsampwidth(2)
                _wf.setframerate(voice.config.sample_rate)
                if hasattr(voice, "synthesize_wav"):
                    voice.synthesize_wav("warm", _wf)
                elif hasattr(voice, "synthesize"):
                    voice.synthesize("warm", _wf)
            del _warmup_buf
        except Exception as e:
            queue_message(f"[Piper] Failed to load voice model: {e}")
            queue_message(f"[Piper] The file may be corrupt: {model_path}")
            queue_message("[Piper] Try re-downloading the .onnx voice model.")
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
        queue_message("[Piper] Cannot synthesize - voice model not loaded. Check logs for details.")
        return
    # Split text into smaller chunks
    # Split at sentence boundaries and commas for faster first-chunk playback
    chunks = re.split(r'(?<=[.!?;])\s+|,\s+', text)

    #chunks = [c.strip() for c in chunks if len(c.strip()) >= 3]
    #fix for missing "hi" or "hey"
    chunks = [c.strip() for c in chunks if c.strip()]
    # If splitting produced nothing (e.g. short text like "Hi"), use original text
    if not chunks and text.strip():
        chunks = [text.strip()]

    # Yield each audio chunk as soon as it's ready
    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize(voice, chunk.strip())
            yield wav_buffer  # Return the chunk for external playback