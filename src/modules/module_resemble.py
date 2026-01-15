import io
import re
import asyncio
import os
import hashlib
import json
from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

# Initialize Resemble AI client
try:
    from resemble import Resemble
    Resemble.api_key(CONFIG['TTS']['resemble_api_key'])
except ImportError:
    queue_message("ERROR: Resemble AI package not installed. Please run: pip install resemble")
    Resemble = None

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
    return os.path.join(CACHE_DIR, f"resemble_{text_hash}.mp3")

async def synthesize_resemble_streaming(chunk):
    try:
        if not Resemble:
            queue_message("ERROR: Resemble AI client not initialized")
            return None

        # Use Resemble AI's synchronous clip creation for streaming
        # Since Resemble AI doesn't have built-in streaming like ElevenLabs,
        # we'll create complete clips and yield them as single chunks
        response = Resemble.v2.clips.create_sync(
            project_uuid=CONFIG['TTS']['project_uuid'],
            voice_uuid=CONFIG['TTS']['voice_uuid'],
            body=chunk,
            title=f"TARS_{hash(chunk) % 10000}",
            sample_rate=44100,
            output_format="mp3",
            include_timestamps=False,
            speed=CONFIG['TTS']['resemble_speed'],
            exaggeration=CONFIG['TTS']['resemble_exaggeration'],
            temperature=CONFIG['TTS']['resemble_temperature']
        )

        if 'item' in response and 'audio_src' in response['item']:
            import requests
            audio_url = response['item']['audio_src']

            # Download the audio
            audio_response = requests.get(audio_url)
            if audio_response.status_code == 200:
                audio_bytes = audio_response.content
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                return audio_buffer
            else:
                queue_message(f"ERROR: Failed to download audio from Resemble AI: {audio_response.status_code}")
                return None
        else:
            queue_message(f"ERROR: Invalid response from Resemble AI: {response}")
            return None

    except Exception as e:
        queue_message(f"ERROR: Resemble AI streaming failed: {e}")
        return None

async def synthesize_resemble_complete(text):
    try:
        if not Resemble:
            queue_message("ERROR: Resemble AI client not initialized")
            return None

        response = Resemble.v2.clips.create_sync(
            project_uuid=CONFIG['TTS']['project_uuid'],
            voice_uuid=CONFIG['TTS']['voice_uuid'],
            body=text,
            title=f"TARS_{hash(text) % 10000}",
            sample_rate=44100,
            output_format="mp3",
            include_timestamps=False,
            speed=CONFIG['TTS']['resemble_speed'],
            exaggeration=CONFIG['TTS']['resemble_exaggeration'],
            temperature=CONFIG['TTS']['resemble_temperature']
        )

        if 'item' in response and 'audio_src' in response['item']:
            import requests
            audio_url = response['item']['audio_src']

            # Download the audio
            audio_response = requests.get(audio_url)
            if audio_response.status_code == 200:
                audio_bytes = audio_response.content
                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                return audio_buffer
            else:
                queue_message(f"ERROR: Failed to download audio from Resemble AI: {audio_response.status_code}")
                return None
        else:
            queue_message(f"ERROR: Invalid response from Resemble AI: {response}")
            return None

    except Exception as e:
        queue_message(f"ERROR: Resemble synthesis failed: {e}")
        return None

async def text_to_speech_with_pipelining_resemble(text, is_wakeword):
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
        audio_buffer = await synthesize_resemble_complete(text)
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
        queue_message(f"Processing {len(chunks)} chunks with Resemble AI")

        for i, chunk in enumerate(chunks):
            queue_message(f"Chunk {i+1}/{len(chunks)}: {chunk[:50]}...")
            audio_buffer = await synthesize_resemble_streaming(chunk)
            if audio_buffer:
                yield audio_buffer
            else:
                queue_message(f"WARNING: Chunk {i+1} failed, skipping")