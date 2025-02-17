import io
import re
import asyncio
import azure.cognitiveservices.speech as speechsdk
from modules.module_config import load_config

# Simple debug logger function
def debug_log(message: str):
    print(f"[DEBUG] {message}")

CONFIG = load_config()

# Debug: Log configuration details (avoid printing sensitive info in production)
debug_log("Initializing Azure Speech SDK with configuration:")
debug_log(f"  API Key: {CONFIG['TTS']['azure_api_key']}")
debug_log(f"  Region: {CONFIG['TTS']['azure_region']}")
debug_log(f"  Voice: {CONFIG['TTS']['tts_voice']}")

# Initialize global speech configuration
speech_config = speechsdk.SpeechConfig(
    subscription=CONFIG['TTS']['azure_api_key'],
    region=CONFIG['TTS']['azure_region']
)
speech_config.speech_synthesis_voice_name = CONFIG['TTS']['tts_voice']
speech_config.set_speech_synthesis_output_format(
    speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
)
debug_log("Global speech config initialized and output format set.")

async def synthesize_azure(chunk: str) -> io.BytesIO:
    """
    Synthesize a chunk of text into an audio buffer using Azure TTS.
    Extensive debug logging is included.
    """
    try:
        debug_log(f"Starting synthesis for chunk: '{chunk}'")
        
        # Set audio_config to None to capture the audio data in result.audio_data
        audio_config = None
        debug_log("AudioOutputConfig set to None to capture audio data.")

        # Create the Speech Synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        debug_log("SpeechSynthesizer created.")

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
        debug_log(f"SSML built: {ssml.strip()}")

        # Run synthesis on a separate thread (since this call is blocking)
        debug_log("Calling speak_ssml_async...")
        result = await asyncio.to_thread(lambda: synthesizer.speak_ssml_async(ssml).get())
        debug_log("speak_ssml_async completed.")

        debug_log(f"Synthesis result reason: {result.reason}")
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            cancellation_details = getattr(result, "cancellation_details", None)
            debug_log(f"Synthesis failed for chunk: '{chunk}'. Cancellation details: {cancellation_details}")
            return None

        if not result.audio_data:
            debug_log("No audio data was returned from synthesis!")
            return None

        audio_length = len(result.audio_data)
        debug_log(f"Synthesized audio data length: {audio_length} bytes.")

        # Wrap the resulting audio data in a BytesIO buffer
        audio_buffer = io.BytesIO(result.audio_data)
        audio_buffer.seek(0)
        debug_log("Audio buffer is ready for this chunk.")
        return audio_buffer

    except Exception as e:
        debug_log(f"Exception during synthesis for chunk '{chunk}': {e}")
        return None

async def text_to_speech_with_pipelining_azure(text: str):
    """
    Converts text to speech by splitting the text into chunks, synthesizing each chunk concurrently,
    and yielding audio buffers as soon as each is ready.
    """
    debug_log("Starting text-to-speech pipelining.")
    if not CONFIG['TTS']['azure_api_key'] or not CONFIG['TTS']['azure_region']:
        raise ValueError("Azure API key and region must be provided for the 'azure' TTS option.")

    debug_log(f"Input text: {text}")

    # Split text into chunks based on sentence endings (adjust regex as needed)
    chunks = re.split(r'(?<=\.)\s', text)
    debug_log(f"Text split into {len(chunks)} chunks: {chunks}")

    # Schedule synthesis for all non-empty chunks concurrently.
    tasks = []
    for index, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if chunk:
            debug_log(f"Scheduling synthesis for chunk {index + 1}: '{chunk}'")
            tasks.append(asyncio.create_task(synthesize_azure(chunk)))
        else:
            debug_log(f"Skipping empty chunk at index {index}.")

    # Now await and yield the results in the original order.
    for i, task in enumerate(tasks):
        audio_buffer = await task  # Each task is already running concurrently.
        if audio_buffer:
            debug_log(f"Yielding synthesized chunk {i+1} audio buffer.")
            yield audio_buffer
        else:
            debug_log(f"Failed to synthesize chunk {i+1}.")
    debug_log("Completed text-to-speech pipelining.")
