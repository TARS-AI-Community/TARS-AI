# modules/module_openai-tts.py

import io
import re
import asyncio
import openai
from modules.module_messageQue import queue_message
from modules.module_config import load_config

CONFIG = load_config()
openai.api_key = CONFIG["TTS"]["openai_api_key"]
VOICE = CONFIG["TTS"]["openai_voice"]

async def text_to_speech_with_pipelining_openai(text):
    """
    Converts text to speech using OpenAI's TTS and streams audio chunks.
    """
    chunks = re.split(r'(?<=\.)\s+', text)

    for chunk in chunks:
        try:
            if not chunk.strip():
                continue

            response = openai.audio.speech.create(
                model="tts-1",  # or "tts-1-hd" if desired
                voice=VOICE,
                input=chunk.strip()
            )

            audio_bytes = response.read()
            audio_buffer = io.BytesIO(audio_bytes)
            audio_buffer.seek(0)

            yield audio_buffer

        except Exception as e:
            queue_message(f"ERROR: OpenAI TTS failed: {e}")
            yield None
