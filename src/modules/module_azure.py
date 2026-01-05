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
    try:
        speech_config = init_speech_config()
        audio_config = None
        
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
               xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='en-US'>
            <voice name='{CONFIG['TTS']['tts_voice']}'>
                <prosody rate="+18%" pitch="-55%" volume="+30%" range="-20%" contour="(0%,+20Hz) (10%,-2st) (40%,+10Hz)">
                    <mstts:express-as style="depressed" styledegree="6">
                        <p>{chunk}</p>
                    </mstts:express-as>
                </prosody>
            </voice>
        </speak>
        """
        """ 
        style="advertisement_upbeat"	Expresses an excited and high-energy tone for promoting a product or service.
        style="affectionate"	Expresses a warm and affectionate tone, with higher pitch and vocal energy. The speaker is in a state of attracting the attention of the listener. The personality of the speaker is often endearing in nature.
        style="angry"	Expresses an angry and annoyed tone.
        style="assistant"	Expresses a warm and relaxed tone for digital assistants.
        style="calm"	Expresses a cool, collected, and composed attitude when speaking. Tone, pitch, and prosody are more uniform compared to other types of speech.
        style="chat"	Expresses a casual and relaxed tone.
        style="cheerful"	Expresses a positive and happy tone.
        style="customerservice"	Expresses a friendly and helpful tone for customer support.
        style="depressed"	Expresses a melancholic and despondent tone with lower pitch and energy.
        style="disgruntled"	Expresses a disdainful and complaining tone. Speech of this emotion displays displeasure and contempt.
        style="documentary-narration"	Narrates documentaries in a relaxed, interested, and informative style suitable for documentaries, expert commentary, and similar content.
        style="embarrassed"	Expresses an uncertain and hesitant tone when the speaker is feeling uncomfortable.
        style="empathetic"	Expresses a sense of caring and understanding.
        style="envious"	Expresses a tone of admiration when you desire something that someone else has.
        style="excited"	Expresses an upbeat and hopeful tone. It sounds like something great is happening and the speaker is happy about it.
        style="fearful"	Expresses a scared and nervous tone, with higher pitch, higher vocal energy, and faster rate. The speaker is in a state of tension and unease.
        style="friendly"	Expresses a pleasant, inviting, and warm tone. It sounds sincere and caring.
        style="gentle"	Expresses a mild, polite, and pleasant tone, with lower pitch and vocal energy.
        style="hopeful"	Expresses a warm and yearning tone. It sounds like something good will happen to the speaker.
        style="lyrical"	Expresses emotions in a melodic and sentimental way.
        style="narration-professional"	Expresses a professional, objective tone for content reading.
        style="narration-relaxed"	Expresses a soothing and melodious tone for content reading.
        style="newscast"	Expresses a formal and professional tone for narrating news.
        style="newscast-casual"	Expresses a versatile and casual tone for general news delivery.
        style="newscast-formal"	Expresses a formal, confident, and authoritative tone for news delivery.
        style="poetry-reading"	Expresses an emotional and rhythmic tone while reading a poem.
        style="sad"	Expresses a sorrowful tone.
        style="serious"	Expresses a strict and commanding tone. Speaker often sounds stiffer and much less relaxed with firm cadence.
        style="shouting"	Expresses a tone that sounds as if the voice is distant or in another location and making an effort to be clearly heard.
        style="sports_commentary"	Expresses a relaxed and interested tone for broadcasting a sports event.
        style="sports_commentary_excited"	Expresses an intensive and energetic tone for broadcasting exciting moments in a sports event.
        style="whispering"	Expresses a soft tone that's trying to make a quiet and gentle sound.
        style="terrified"	Expresses a scared tone, with a faster pace and a shakier voice. It sounds like the speaker is in an unsteady and frantic status.
        style="unfriendly"	Expresses a cold and indifferent tone. """


        result = await asyncio.to_thread(lambda: synthesizer.speak_ssml_async(ssml).get())
    
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            cancellation_details = getattr(result, "cancellation_details", None)
            return None

        if not result.audio_data:
            return None

        audio_buffer = io.BytesIO(result.audio_data)
        audio_buffer.seek(0)
        
        return audio_buffer

    except Exception as e:
        return None

async def apply_tars_effects(audio_buffer):
    try:
        from pydub import AudioSegment
        from pydub.effects import compress_dynamic_range, normalize
        audio_buffer.seek(0)
        sound = AudioSegment.from_file(audio_buffer, format="wav")
        sound = compress_dynamic_range(sound, ratio=3.0, threshold=-15.0)
        sound = sound.low_shelf_filter(frequency=300, gain_db=4.0)
        sound = sound.high_shelf_filter(frequency=5000, gain_db=2.0)
        robot_effect = sound + 2
        robot_effect = normalize(robot_effect, headroom=1.0)
        high_freq = sound.high_pass_filter(3000) - 12
        robot_effect = robot_effect.overlay(high_freq, gain_during_overlay=-8)
        chunk_length = 500
        final_sound = AudioSegment.empty()
        
        for i in range(0, len(robot_effect), chunk_length):
            chunk = robot_effect[i:i+chunk_length]
            if i % 3 == 0:
                pitch_change = -0.1
                chunk = chunk._spawn(chunk.raw_data, overrides={
                    "frame_rate": int(chunk.frame_rate * (1 + pitch_change/100))
                })
            final_sound += chunk
        output_buffer = io.BytesIO()
        final_sound.export(output_buffer, format="wav")
        output_buffer.seek(0)
        return output_buffer
        
    except ImportError:
        audio_buffer.seek(0)
        return audio_buffer

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