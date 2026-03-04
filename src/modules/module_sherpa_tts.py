"""
module_sherpa_tts.py

Sherpa-ONNX TTS module for TARS-AI application.

Provides offline text-to-speech using sherpa-onnx with Kokoro or VITS models.
Follows the same async generator pattern as module_piper.py.
"""

import os
import re
import wave
from io import BytesIO

from modules.module_config import load_config
from modules.module_messageQue import queue_message

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

CONFIG = load_config()

# Load TTS model at module init (only if sherpa-onnx is selected)
tts = None
tts_sample_rate = 22050

if CONFIG['TTS']['ttsoption'] == 'sherpa-onnx' and sherpa_onnx is not None:
    try:
        # Look for model files in tts/ directory
        tts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tts')

        # Auto-detect model type by scanning for known file patterns
        kokoro_model = None
        kokoro_voices = None
        kokoro_tokens = None
        kokoro_data_dir = None
        kokoro_dict_dir = None
        vits_model = None
        vits_tokens = None
        vits_data_dir = None
        vits_dict_dir = None

        # Search tts/ subdirectories for model files
        if os.path.isdir(tts_dir):
            for entry in os.listdir(tts_dir):
                subdir = os.path.join(tts_dir, entry)
                if not os.path.isdir(subdir):
                    continue

                # Check for Kokoro model
                for f in os.listdir(subdir):
                    if f.startswith('model') and f.endswith('.onnx') and 'kokoro' in entry.lower():
                        kokoro_model = os.path.join(subdir, f)
                        kokoro_tokens = os.path.join(subdir, 'tokens.txt')
                        kokoro_voices = os.path.join(subdir, 'voices.bin') if os.path.exists(os.path.join(subdir, 'voices.bin')) else None
                        kokoro_data_dir = os.path.join(subdir, 'espeak-ng-data') if os.path.isdir(os.path.join(subdir, 'espeak-ng-data')) else None
                        kokoro_dict_dir = subdir
                        break
                    elif f.startswith('model') and f.endswith('.onnx') and 'vits' in entry.lower():
                        vits_model = os.path.join(subdir, f)
                        vits_tokens = os.path.join(subdir, 'tokens.txt')
                        vits_data_dir = os.path.join(subdir, 'espeak-ng-data') if os.path.isdir(os.path.join(subdir, 'espeak-ng-data')) else None
                        vits_dict_dir = subdir
                        break

        if kokoro_model and os.path.exists(kokoro_model):
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                        model=kokoro_model,
                        voices=kokoro_voices or "",
                        tokens=kokoro_tokens or "",
                        data_dir=kokoro_data_dir or "",
                        dict_dir=kokoro_dict_dir or "",
                    ),
                    num_threads=2,
                    debug=False,
                ),
            )
            tts = sherpa_onnx.OfflineTts(tts_config)
            tts_sample_rate = tts.sample_rate
            queue_message(f"LOAD: sherpa-onnx Kokoro TTS loaded ({tts_sample_rate}Hz)")
        elif vits_model and os.path.exists(vits_model):
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=vits_model,
                        tokens=vits_tokens or "",
                        data_dir=vits_data_dir or "",
                        dict_dir=vits_dict_dir or "",
                    ),
                    num_threads=2,
                    debug=False,
                ),
            )
            tts = sherpa_onnx.OfflineTts(tts_config)
            tts_sample_rate = tts.sample_rate
            queue_message(f"LOAD: sherpa-onnx VITS TTS loaded ({tts_sample_rate}Hz)")
        else:
            queue_message("ERROR: No sherpa-onnx TTS model found in tts/ directory")
            queue_message("INFO: Place a Kokoro or VITS model directory in src/tts/")

    except Exception as e:
        queue_message(f"ERROR: Failed to load sherpa-onnx TTS: {e}")


async def synthesize_chunk(text, speaker_id=0, speed=1.0):
    """Synthesize a text chunk into a WAV BytesIO buffer."""
    if tts is None:
        return None

    try:
        audio = tts.generate(text, sid=speaker_id, speed=speed)
        if audio.samples is None or len(audio.samples) == 0:
            return None

        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(audio.sample_rate)
            # Convert float32 samples to int16
            import numpy as np
            samples_int16 = np.clip(
                np.array(audio.samples) * 32767, -32768, 32767
            ).astype(np.int16)
            wf.writeframes(samples_int16.tobytes())

        wav_buffer.seek(0)
        return wav_buffer
    except Exception as e:
        queue_message(f"ERROR: sherpa-onnx TTS synthesis failed: {e}")
        return None


async def text_to_speech_with_pipelining_sherpa_tts(text):
    """
    Convert text to speech using sherpa-onnx TTS, yielding WAV chunks per sentence.
    Follows the same pattern as module_piper.py.
    """
    speaker_id = int(CONFIG['TTS'].get('sherpa_onnx_tts_speaker', 0))
    speed = float(CONFIG['TTS'].get('sherpa_onnx_tts_speed', 1.0))

    # Split text into sentences
    chunks = re.split(r'(?<=[.!?])\s+', text)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        wav_buffer = await synthesize_chunk(chunk, speaker_id, speed)
        if wav_buffer is not None:
            yield wav_buffer
