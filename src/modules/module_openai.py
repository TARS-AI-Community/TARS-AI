import io
import re
import os
import hashlib
import openai
from modules.module_messageQue import queue_message
from modules.module_config import load_config

CONFIG = load_config()
openai.api_key = CONFIG["TTS"]["openai_api_key"]
VOICE = CONFIG["TTS"]["openai_voice"]

CACHE_DIR = os.path.expanduser("~/.local/share/tars_ai_replies")
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_filename(text):
    """Generate a cache filename based on text hash"""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"openai_{text_hash}.mp3")

async def text_to_speech_with_pipelining_openai(text, is_wakeword):
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
        
        #queue_message(f"Generating and caching wakeword: {text}")
        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice=VOICE,
                input=text
            )

            audio_bytes = response.read()

            try:
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)
                #queue_message(f"Cached wakeword to: {cache_file}")
            except Exception as e:
                queue_message(f"ERROR: Failed to cache audio: {e}")
            
            audio_buffer = io.BytesIO(audio_bytes)
            audio_buffer.seek(0)
            yield audio_buffer
            
        except Exception as e:
            queue_message(f"ERROR: OpenAI TTS failed: {e}")
            yield None
    else:
        try:
            response = openai.audio.speech.create(
                model="tts-1",
                voice=VOICE,
                input=text
            )

            audio_bytes = response.read()
            audio_buffer = io.BytesIO(audio_bytes)
            audio_buffer.seek(0)

            yield audio_buffer

        except Exception as e:
            queue_message(f"ERROR: OpenAI TTS failed: {e}")
            yield None