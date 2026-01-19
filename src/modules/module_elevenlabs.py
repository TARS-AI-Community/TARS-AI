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

def split_into_sentences(text, max_length=80):
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_chunk and len(current_chunk + " " + sentence) > max_length:
            chunks.append(current_chunk)
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text]

def get_cache_filename(text):
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"elevenlabs_{text_hash}.mp3")

async def synthesize_elevenlabs_streaming(chunk):
    """
    Synthesize using direct REST API to ensure SSML tags are processed.
    The Python SDK sometimes doesn't handle SSML properly, so we use direct HTTP.
    """
    try:
        import aiohttp
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{CONFIG['TTS']['voice_id']}/stream"
        headers = {
            "xi-api-key": CONFIG['TTS']['elevenlabs_api_key'],
            "Content-Type": "application/json"
        }
        
        # Check if model supports SSML
        model_id = CONFIG['TTS']['model_id']
        is_eleven_v3 = 'v3' in model_id.lower()
        
        if is_eleven_v3 and '<break' in chunk:
            # Eleven V3 doesn't support SSML, log warning
            queue_message(f"WARNING: Model {model_id} doesn't support SSML tags. Use [pause], [short pause], [long pause] instead.")
        
        payload = {
            "text": chunk,
            "model_id": model_id,
            "output_format": "mp3_44100_128",
            "optimize_streaming_latency": 3,
            "enable_ssml": True  # CRITICAL: Enable SSML parsing
        }
        
        # Log the actual text being sent (for debugging)
        if '<break' in chunk:
            queue_message(f"DEBUG: Sending text with SSML: {chunk[:100]}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    queue_message(f"ERROR: ElevenLabs API returned {response.status}: {error_text}")
                    return None
                
                audio_bytes = await response.read()
                
                if not audio_bytes:
                    queue_message(f"ERROR: ElevenLabs returned empty response")
                    return None
                
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def synthesize_elevenlabs_complete(text):
    """
    Synthesize complete speech using direct REST API.
    """
    try:
        import aiohttp
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{CONFIG['TTS']['voice_id']}"
        headers = {
            "xi-api-key": CONFIG['TTS']['elevenlabs_api_key'],
            "Content-Type": "application/json"
        }
        
        # Check if model supports SSML
        model_id = CONFIG['TTS']['model_id']
        is_eleven_v3 = 'v3' in model_id.lower()
        
        if is_eleven_v3 and '<break' in text:
            queue_message(f"WARNING: Model {model_id} doesn't support SSML tags. Use [pause], [short pause], [long pause] instead.")
        
        payload = {
            "text": text,
            "model_id": model_id,
            "output_format": "mp3_44100_128",
            "enable_ssml": True  # CRITICAL: Enable SSML parsing
        }
        
        # Log if SSML is present
        if '<break' in text:
            queue_message(f"DEBUG: Sending wakeword with SSML: {text}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    queue_message(f"ERROR: ElevenLabs API returned {response.status}: {error_text}")
                    return None
                
                audio_bytes = await response.read()
                
                if not audio_bytes:
                    queue_message(f"ERROR: ElevenLabs returned empty response")
                    return None
                
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def text_to_speech_with_pipelining_elevenlabs(text, is_wakeword):    

    if is_wakeword:
        cache_file = get_cache_filename(text)

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    audio_bytes = f.read()
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
                return
            except Exception as e:
                queue_message(f"ERROR: Failed to load cache: {e}")

        queue_message(f"Caching wakeword: {text}")
        audio_buffer = await synthesize_elevenlabs_complete(text)
        if audio_buffer:
            try:
                audio_bytes = audio_buffer.read()
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)

                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
            except Exception as e:
                queue_message(f"ERROR: Failed to cache: {e}")
                audio_buffer.seek(0)
                yield audio_buffer

    else:

        chunks = split_into_sentences(text, max_length=80)
        for i, chunk in enumerate(chunks):
            audio_buffer = await synthesize_elevenlabs_streaming(chunk)
            if audio_buffer:
                yield audio_buffer
            else:
                queue_message(f"WARNING: Chunk {i+1} failed, skipping")