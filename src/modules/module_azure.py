import io
import re
import asyncio
import azure.cognitiveservices.speech as speechsdk
from modules.module_config import load_config


CONFIG = load_config()

def init_speech_config() -> speechsdk.SpeechConfig:
    """
    Initialize and return Azure speech configuration.
    
    Returns:
        speechsdk.SpeechConfig: Configured speech configuration object
        
    Raises:
        ValueError: If Azure API key or region is missing
    """
    if not CONFIG['TTS']['azure_api_key'] or not CONFIG['TTS']['azure_region']:
        raise ValueError("Azure API key and region must be provided for the 'azure' TTS option.")
    
    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=CONFIG['TTS']['azure_api_key'],
            region=CONFIG['TTS']['azure_region']
        )
        speech_config.speech_synthesis_voice_name = CONFIG['TTS']['tts_voice']
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )
        return speech_config
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Azure speech config: {str(e)}")

async def synthesize_azure(chunk: str) -> io.BytesIO:
    """
    Synthesize a chunk of text into an audio buffer using Azure TTS.
    Extensive debug logging is included.
    """
    try:
        speech_config = init_speech_config()

        # Set audio_config to None to capture the audio data in result.audio_data
        audio_config = None
        # Create the Speech Synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        # Build the SSML string using your original settings
        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
               xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='en-US'>
            <voice name='{CONFIG['TTS']['tts_voice']}'>
                <prosody rate="10%" pitch="5%" volume="default">
                    {chunk}
                </prosody>
            </voice>
        </speak>
        """

        # Run synthesis on a separate thread (since this call is blocking)
        result = await asyncio.to_thread(lambda: synthesizer.speak_ssml_async(ssml).get())
    
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            cancellation_details = getattr(result, "cancellation_details", None)
            return None

        if not result.audio_data:
            return None

        audio_length = len(result.audio_data)

        # Wrap the resulting audio data in a BytesIO buffer
        audio_buffer = io.BytesIO(result.audio_data)
        audio_buffer.seek(0)
        return audio_buffer

    except Exception as e:
        return None

async def text_to_speech_with_pipelining_azure(text: str):
    """
    Converts text to speech by splitting the text into chunks, synthesizing each chunk concurrently,
    and yielding audio buffers as soon as each is ready.
    """
    if not CONFIG['TTS']['azure_api_key'] or not CONFIG['TTS']['azure_region']:
        raise ValueError("Azure API key and region must be provided for the 'azure' TTS option.")

    # Split text into chunks based on sentence endings (adjust regex as needed)
    chunks = re.split(r'(?<=\.)\s', text)

    # Schedule synthesis for all non-empty chunks concurrently.
    tasks = []
    for index, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if chunk:
            tasks.append(asyncio.create_task(synthesize_azure(chunk)))

    # Now await and yield the results in the original order.
    for i, task in enumerate(tasks):
        audio_buffer = await task  # Each task is already running concurrently.
        if audio_buffer:
            yield audio_buffer