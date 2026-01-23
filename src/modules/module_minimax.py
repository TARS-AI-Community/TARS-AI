"""
MINIMAX TTS - V3
==========================
# atomikspace (discord)
# olivierdion1@hotmail.com
"""
import io
import re
import asyncio
import os
import hashlib
import json
import aiohttp
from io import BytesIO
from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

MINIMAX_API_URL = "https://api.minimax.io/v1/t2a_v2"

MODEL_ID = CONFIG['TTS']['minimax_model']
VOICE_ID = CONFIG['TTS']['minimax_voice_id']
SAMPLE_RATE = 32000
BITRATE = 128000
AUDIO_FORMAT = "mp3"
CHANNEL = 1

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
    return os.path.join(CACHE_DIR, f"minimax_{text_hash}.mp3")

async def synthesize_minimax_non_streaming(text, speed=1.0, volume=1.0, pitch=0):
    """
    Synthesize speech using non-streaming API (faster for short texts).
    
    Parameters:
    - text (str): The text to convert to speech
    - speed (float): Speech speed (0.5 to 2.0)
    - volume (float): Volume level (0.0 to 2.0)
    - pitch (int): Pitch adjustment (-12 to 12)
    
    Returns:
    - BytesIO: Complete audio buffer or None on failure
    """
    try:
        api_key = CONFIG['TTS']['minimax_api_key']
        if not api_key:
            queue_message("ERROR: Minimax API key not found in env file")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": MODEL_ID,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": VOICE_ID,
                "speed": speed,
                "vol": volume,
                "pitch": pitch
            },
            "audio_setting": {
                "sample_rate": SAMPLE_RATE,
                "bitrate": BITRATE,
                "format": AUDIO_FORMAT,
                "channel": CHANNEL
            },
            "output_format": "hex"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(MINIMAX_API_URL, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    queue_message(f"ERROR: Minimax API returned {response.status}: {error_text}")
                    return None

                response_data = await response.json()
                
                if 'data' in response_data and 'audio' in response_data['data']:
                    hex_audio = response_data['data']['audio']
                    if hex_audio:
                        binary_audio = bytes.fromhex(hex_audio)
                        audio_buffer = BytesIO(binary_audio)
                        audio_buffer.seek(0)
                        return audio_buffer
                
                queue_message("ERROR: No audio data in Minimax response")
                return None

    except Exception as e:
        queue_message(f"ERROR: Minimax non-streaming synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def synthesize_minimax_streaming(text, speed=1.0, volume=1.0, pitch=0):
    try:
        api_key = CONFIG['TTS']['minimax_api_key']
        if not api_key:
            queue_message("ERROR: Minimax API key not found in env file")
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": MODEL_ID,
            "text": text,
            "stream": True,
            "voice_setting": {
                "voice_id": VOICE_ID,
                "speed": speed,
                "vol": volume,
                "pitch": pitch
            },
            "audio_setting": {
                "sample_rate": SAMPLE_RATE,
                "bitrate": BITRATE,
                "format": AUDIO_FORMAT,
                "channel": CHANNEL
            },
            "output_format": "hex"  

        }

        async with aiohttp.ClientSession() as session:
            async with session.post(MINIMAX_API_URL, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    queue_message(f"ERROR: Minimax API returned {response.status}: {error_text}")
                    return
                audio_data = bytearray()
                buffer = ""
                async for chunk in response.content.iter_any():
                    if chunk:
                        buffer += chunk.decode('utf-8', errors='ignore')
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            if line.startswith('data: '):
                                json_str = line[6:]
                                try:
                                    data = json.loads(json_str)

                                    if 'data' in data and 'audio' in data['data'] and data['data'].get('status') == 1:
                                        hex_audio = data['data']['audio']
                                        if hex_audio:
                                            binary_audio = bytes.fromhex(hex_audio)
                                            audio_data.extend(binary_audio)
                                            if len(audio_data) >= 262144:
                                                audio_buffer = BytesIO(bytes(audio_data))
                                                audio_buffer.seek(0)
                                                yield audio_buffer
                                                audio_data.clear()
                                except json.JSONDecodeError:
                                    pass
                if audio_data:
                    audio_buffer = BytesIO(bytes(audio_data))
                    audio_buffer.seek(0)
                    yield audio_buffer

    except Exception as e:
        queue_message(f"ERROR: Minimax streaming synthesis failed: {e}")
        import traceback
        traceback.print_exc()

async def synthesize_minimax_complete(text, speed=1.0, volume=1.0, pitch=0):
    try:
        audio_data = bytearray()

        async for audio_chunk in synthesize_minimax_streaming(text, speed, volume, pitch):
            chunk_bytes = audio_chunk.read()
            audio_data.extend(chunk_bytes)

        if not audio_data:
            queue_message(f"ERROR: No audio data received from Minimax")
            return None

        audio_buffer = BytesIO(bytes(audio_data))
        audio_buffer.seek(0)
        return audio_buffer

    except Exception as e:
        queue_message(f"ERROR: Minimax complete synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def text_to_speech_with_pipelining_minimax(text, is_wakeword):
    speed = 1
    volume = 1.0
    pitch = 0

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
                queue_message(f"ERROR: Failed to load Minimax cache: {e}")

        queue_message(f"Minimax: Caching wakeword using non-streaming")
        audio_buffer = await synthesize_minimax_non_streaming(text, speed, volume, pitch)
        if audio_buffer:
            try:
                audio_bytes = audio_buffer.read()
                with open(cache_file, 'wb') as f:
                    f.write(audio_bytes)

                audio_buffer = io.BytesIO(audio_bytes)
                audio_buffer.seek(0)
                yield audio_buffer
            except Exception as e:
                queue_message(f"ERROR: Failed to cache Minimax audio: {e}")
                audio_buffer.seek(0)
                yield audio_buffer
    else:
        # Use non-streaming for short texts (< 300 chars)
        if len(text) < 100:
            queue_message(f"Minimax: Using non-streaming (text length: {len(text)} chars)")
            audio_buffer = await synthesize_minimax_non_streaming(text, speed, volume, pitch)
            if audio_buffer:
                yield audio_buffer
            else:
                queue_message(f"WARNING: Minimax non-streaming synthesis failed")
        else:
            # Use streaming for longer texts
            queue_message(f"Minimax: Using streaming (text length: {len(text)} chars)")
            chunks = split_into_sentences(text, max_length=80)
            for i, chunk in enumerate(chunks):
                async for audio_buffer in synthesize_minimax_streaming(chunk, speed, volume, pitch):
                    if audio_buffer:
                        yield audio_buffer
                    else:
                        queue_message(f"WARNING: Minimax chunk {i+1} failed, skipping")