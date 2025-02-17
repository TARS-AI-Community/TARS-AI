import requests
import io
import re
import asyncio
import wave
from modules.module_config import load_config

CONFIG = load_config()

async def generate_chunks(text):
    """
    Splits text into sentence chunks for TTS processing.

    Parameters:
    - text (str): The full text input.

    Yields:
    - str: Sentence chunks for processing.
    """
    # Split text at sentence boundaries (handles period + space)
    chunks = re.split(r'(?<=\.)\s', text)
    
    for chunk in chunks:
        chunk = chunk.strip()
        if chunk:
            yield chunk  # ✅ Now an async generator


async def synthesize_alltalk(chunk):
    """
    Sends a text chunk to the AllTalk API and returns a BytesIO buffer with the audio.

    Parameters:
    - chunk (str): A sentence chunk from `generate_chunks()`.

    Returns:
    - BytesIO: A buffer containing the generated WAV audio.
    """
    try:
        # API endpoint and payload
        url = f"{CONFIG['TTS']['ttsurl']}/api/tts-generate"
        data = {
            "text_input": chunk,  # Send only one chunk at a time
            "text_filtering": "standard",
            "character_voice_gen": f"{CONFIG['TTS']['tts_voice']}.wav",
            "narrator_enabled": "false",
            "narrator_voice_gen": "default.wav",
            "text_not_inside": "character",
            "language": "en",
            "output_file_name": "test_output",
            "output_file_timestamp": "true",
            "autoplay": "false",
            "autoplay_volume": 0.8,
        }

        # Send request to generate TTS
        response = requests.post(url, data=data)
        response.raise_for_status()

        wav_url = response.json().get("output_file_url")
        if not wav_url:
            print(f"ERROR: No WAV file URL for chunk: {chunk}")
            return None

        # Download the WAV file into memory
        response = requests.get(wav_url)
        response.raise_for_status()

        # Convert WAV response to BytesIO buffer
        wav_data = io.BytesIO(response.content)
        wav_data.seek(0)  # Reset buffer position

        return wav_data  # Return the processed audio buffer

    except Exception as e:
        print(f"ERROR: AllTalk TTS synthesis failed: {e}")
        return None


async def text_to_speech_with_pipelining_alltalk(text):
    """
    Converts text to speech using the AllTalk API and streams audio as it's generated.

    Yields:
    - BytesIO: Processed audio chunks as they're generated.
    """
    async for chunk in generate_chunks(text):  # ✅ Now works with async generator
        wav_buffer = await synthesize_alltalk(chunk)  # Send to API
        if wav_buffer:
            yield wav_buffer  # Yield processed audio chunk
