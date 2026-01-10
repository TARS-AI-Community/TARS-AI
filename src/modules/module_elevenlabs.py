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
    try:

        audio_stream = elevenlabs_client.text_to_speech.stream(
            text=chunk,
            voice_id=CONFIG['TTS']['voice_id'],
            model_id=CONFIG['TTS']['model_id'],
            output_format="mp3_44100_128",
            optimize_streaming_latency=3,  

        )

        audio_bytes = b""
        first_byte = True

        for audio_chunk in audio_stream:
            if isinstance(audio_chunk, bytes):
                if first_byte:
                    queue_message(f"First audio bytes received from API")
                    first_byte = False
                audio_bytes += audio_chunk

        if not audio_bytes:
            queue_message(f"ERROR: ElevenLabs returned empty response")
            return None

        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.seek(0)
        return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs streaming failed: {e}")
        return None

async def synthesize_elevenlabs_complete(text):
    try:
        audio_generator = elevenlabs_client.text_to_speech.convert(
            text=text,
            voice_id=CONFIG['TTS']['voice_id'],
            model_id=CONFIG['TTS']['model_id'],
            output_format="mp3_44100_128",
        )

        audio_bytes = b"".join(audio_generator)

        if not audio_bytes:
            queue_message(f"ERROR: ElevenLabs returned empty response")
            return None

        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.seek(0)
        return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs synthesis failed: {e}")
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
        queue_message(f"Streaming {len(chunks)} chunks with optimize_streaming_latency=3")

        for i, chunk in enumerate(chunks):
            queue_message(f"Chunk {i+1}/{len(chunks)}: {chunk[:50]}...")
            audio_buffer = await synthesize_elevenlabs_streaming(chunk)
            if audio_buffer:
                yield audio_buffer
            else:
                queue_message(f"WARNING: Chunk {i+1} failed, skipping")