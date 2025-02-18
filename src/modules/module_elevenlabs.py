import io
import re
import asyncio
import wave
from modules.module_config import load_config
from elevenlabs.client import ElevenLabs

from modules.module_messageQue import queue_message

CONFIG = load_config()

# ✅ Initialize ElevenLabs client globally
elevenlabs_client = ElevenLabs(api_key=CONFIG['TTS']['elevenlabs_api_key'])


async def synthesize_elevenlabs(chunk):
    """
    Synthesize a chunk of text into an AudioSegment using ElevenLabs API.

    Parameters:
    - chunk (str): A single sentence or phrase.
    - voice_id (str): ElevenLabs voice ID.
    - model_id (str): ElevenLabs model ID.
    - output_format (str): The desired output format.

    Returns:
    - BytesIO: A buffer containing the generated audio.
    """
    try:
        # ✅ Generate audio using ElevenLabs API
        audio_generator = elevenlabs_client.text_to_speech.convert(
            text=chunk,
            voice_id=CONFIG['TTS']['voice_id'],
            model_id=CONFIG['TTS']['model_id'],
            output_format="mp3_44100_128",
        )

        # ✅ Join the generator output into a single byte object
        audio_bytes = b"".join(audio_generator)

        if not audio_bytes:  # ✅ Ensure the API response is valid
            queue_message(f"ERROR: ElevenLabs returned an empty response for chunk: {chunk}")
            return None

        # Convert raw audio bytes to BytesIO buffer
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.seek(0)  # Reset buffer position

        return audio_buffer  # ✅ Return the processed audio buffer

    except Exception as e:
        queue_message(f"ERROR: ElevenLabs TTS synthesis failed: {e}")
        return None


async def text_to_speech_with_pipelining_elevenlabs(text):
    """
    Converts text to speech using the ElevenLabs API and streams audio as it's generated.

    Yields:
    - BytesIO: Processed audio chunks as they're generated.
    """
    # ✅ Split text into sentences before sending to ElevenLabs
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # ✅ Process each sentence separately
    for chunk in chunks:
        if chunk.strip():  # ✅ Ignore empty chunks
            wav_buffer = await synthesize_elevenlabs(chunk.strip())  # ✅ Generate audio
            if wav_buffer:
                yield wav_buffer  # ✅ Stream audio chunks dynamically
