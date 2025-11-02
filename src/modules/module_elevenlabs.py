import io
import re
import asyncio
import os
import hashlib
from modules.module_config import load_config
from elevenlabs.client import ElevenLabs

from modules.module_messageQue import queue_message

CONFIG = load_config()

elevenlabs_client = ElevenLabs(api_key=CONFIG['TTS']['elevenlabs_api_key'])

CACHE_DIR = os.path.expanduser("~/.local/share/tars_ai_replies")
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_filename(text):
    """Generate a cache filename based on text hash"""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"elevenlabs_{text_hash}.mp3")

async def synthesize_elevenlabs(chunk):
    try:
        tts_params = {
            "text": chunk,
            "voice_id": CONFIG['TTS']['voice_id'],
            "model_id": CONFIG['TTS']['model_id'],
            "output_format": "mp3_44100_128",
        }

        audio_generator = elevenlabs_client.text_to_speech.convert(**tts_params)

        audio_bytes = b"".join(audio_generator)

        if not audio_bytes:
            queue_message(f"ERROR: ElevenLabs returned an empty response for chunk: {chunk}")
            return None

        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.seek(0)

        return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs TTS synthesis failed: {e}")
        return None

async def text_to_speech_with_pipelining_elevenlabs(text, is_wakeword):
    #print(f"is_wakeword: {is_wakeword}")

    if is_wakeword:
        cache_file = get_cache_filename(text)

        if os.path.exists(cache_file):
            #queue_message(f"Loading wakeword from cache: {cache_file}")
            try:
                with open(cache_file, 'rb') as f:
                    audio_bytes = f.read()
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
                return
            except Exception as e:
                queue_message(f"ERROR: Failed to load cache file: {e}")

        queue_message(f"Generating and caching wakeword: {text}")
        wav_buffer = await synthesize_elevenlabs(text)
        if wav_buffer:

            try:
                audio_bytes = wav_buffer.read()
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)
                #queue_message(f"Cached wakeword to: {cache_file}")

                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
            except Exception as e:
                queue_message(f"ERROR: Failed to cache audio: {e}")

                wav_buffer.seek(0)
                yield wav_buffer
    else:

        wav_buffer = await synthesize_elevenlabs(text)
        if wav_buffer:
            yield wav_buffer