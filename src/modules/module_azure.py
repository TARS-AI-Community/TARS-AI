import io
import re
import asyncio
import azure.cognitiveservices.speech as speechsdk
from modules.module_config import load_config

CONFIG = load_config()

# ✅ Initialize Azure Speech SDK globally
speech_config = speechsdk.SpeechConfig(
    subscription=CONFIG['TTS']['azure_api_key'],
    region=CONFIG['TTS']['azure_region']
)
speech_config.speech_synthesis_voice_name = CONFIG['TTS']['tts_voice']
speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)


async def synthesize_azure(chunk):
    """
    Synthesize a chunk of text into an audio buffer using Azure TTS.

    Parameters:
    - chunk (str): A single sentence or phrase.

    Returns:
    - BytesIO: A buffer containing the generated audio.
    """
    try:
        # ✅ Set up an in-memory audio stream
        stream = speechsdk.audio.PullAudioOutputStream()
        audio_config = speechsdk.audio.AudioOutputConfig(stream=stream)

        # ✅ Create a Speech Synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        # ✅ SSML Configuration (Adjust speed, pitch, and volume)
        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='en-US'>
            <voice name='{CONFIG['TTS']['tts_voice']}'>
                <prosody rate="10%" pitch="5%" volume="default">
                    {chunk}
                </prosody>
            </voice>
        </speak>
        """

        # ✅ Start synthesis asynchronously
        result_future = synthesizer.speak_ssml_async(ssml)
        result = await asyncio.to_thread(result_future.get)

        # ✅ Check if synthesis was successful
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            print(f"ERROR: Azure TTS synthesis failed for chunk: {chunk}")
            return None

        # ✅ Read streamed audio into a buffer
        audio_buffer = io.BytesIO()
        buffer_size = 4096  # Read in small chunks

        while True:
            audio_chunk = stream.read(buffer_size)
            if not audio_chunk:
                break  # Stop reading when no more data is available
            audio_buffer.write(audio_chunk)

        audio_buffer.seek(0)  # Reset buffer position

        return audio_buffer  # ✅ Return processed audio buffer

    except Exception as e:
        print(f"ERROR: Azure TTS synthesis failed: {e}")
        return None


async def text_to_speech_with_pipelining_azure(text):
    """
    Converts text to speech using Azure TTS API and streams audio as it's generated.

    Yields:
    - BytesIO: Processed audio chunks as they're generated.
    """
    if not CONFIG['TTS']['azure_api_key'] or not CONFIG['TTS']['azure_region']:
        raise ValueError("ERROR: Azure API key and region must be provided for ttsoption 'azure'.")

    # ✅ Split text into sentences before sending to Azure
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    # ✅ Process each sentence separately
    for chunk in chunks:
        if chunk.strip():  # ✅ Ignore empty chunks
            wav_buffer = await synthesize_azure(chunk.strip())  # ✅ Generate audio
            if wav_buffer:
                yield wav_buffer  # ✅ Stream audio chunks dynamically
