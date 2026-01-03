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

def split_into_sentences(text, max_length=150):
    """
    Split text into sentences for streaming TTS.
    Keeps sentences under max_length for faster processing.
    """
    # Split on sentence boundaries only (not commas)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence exceeds max_length, yield current chunk
        if current_chunk and len(current_chunk + " " + sentence) > max_length:
            chunks.append(current_chunk)
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text]

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

        # convert() already returns a streaming generator
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
    
    # Wakewords are short - don't split them
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
                queue_message(f"ERROR: Failed to load cache file: {e}")

        queue_message(f"Generating and caching wakeword: {text}")
        wav_buffer = await synthesize_elevenlabs(text)
        if wav_buffer:
            try:
                audio_bytes = wav_buffer.read()
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)

                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
            except Exception as e:
                queue_message(f"ERROR: Failed to cache audio: {e}")
                wav_buffer.seek(0)
                yield wav_buffer
    else:
        # Split into 150-char chunks - balances speed vs sentence integrity
        chunks = split_into_sentences(text, max_length=150)
        queue_message(f"Split text into {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            wav_buffer = await synthesize_elevenlabs(chunk)
            if wav_buffer:
                yield wav_buffer