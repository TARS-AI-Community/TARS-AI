import sounddevice as sd
import soundfile as sf
from io import BytesIO
from piper.voice import PiperVoice
import asyncio
import wave
import re

model_path = "/home/pyrater/TARS-AI/src/tts/TARS.onnx"  # Update with the actual path to your model

#compile onnxruntime-gpu for speed
async def synthesize(voice, chunk):
    """
    Synthesize a chunk of text into a BytesIO buffer.
    """
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit samples
        wav_file.setframerate(voice.config.sample_rate)
        voice.synthesize(chunk, wav_file)
    wav_buffer.seek(0)
    return wav_buffer

async def play_audio(wav_buffer):
    """
    Play audio from a BytesIO buffer.
    """
    data, samplerate = sf.read(wav_buffer, dtype='float32')
    sd.play(data, samplerate)
    await asyncio.sleep(len(data) / samplerate)  # Wait until playback finishes

async def text_to_speech_with_pipelining(text):
    """
    Converts text to speech using the specified Piper model and streams audio playback with pipelining.
    """
    # Load the Piper model
    voice = PiperVoice.load(model_path)

    # Split text into smaller chunks
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # Process and play chunks sequentially
    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize(voice, chunk.strip())
            await play_audio(wav_buffer)


#testtext = "The vast expanse of the cosmos is a reminder of humanity's enduring curiosity. Each star in the night sky is a beacon of possibilities. As technology evolves, so too does our capacity to gaze further into the depths of space. In the heart of a bustling city, life unfolds at a pace that reflects modern existence. Moments of tranquility remind us to appreciate the beauty amidst the chaos."
#asyncio.run(text_to_speech_with_pipelining(testtext))
