import io
import re
import asyncio
from modules.module_config import load_config
from elevenlabs.client import ElevenLabs

from modules.module_messageQue import queue_message

CONFIG = load_config()

elevenlabs_client = ElevenLabs(api_key=CONFIG['TTS']['elevenlabs_api_key'])

async def synthesize_elevenlabs(chunk):
    try:
        tts_params = {
            "text": chunk,
            "voice_id": CONFIG['TTS']['voice_id'],
            "model_id": CONFIG['TTS']['model_id'],
            "output_format": "mp3_44100_128",
        }
        
        # Let elevenlabs autodetect
        #LANGUAGE_CODE = "en"
        #if LANGUAGE_CODE:
        #    tts_params["language_code"] = LANGUAGE_CODE

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


async def text_to_speech_with_pipelining_elevenlabs(text):
    chunks = re.split(r'(?<=\.)\s', text)

    for chunk in chunks:
        if chunk.strip():
            wav_buffer = await synthesize_elevenlabs(chunk.strip())
            if wav_buffer:
                yield wav_buffer