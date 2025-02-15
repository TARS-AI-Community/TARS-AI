"""
module_tts.py

Text-to-Speech (TTS) module for TARS-AI application.

Handles TTS functionality to convert text into audio using:
- Azure Speech SDK
- Local tools (e.g., espeak-ng)
- Server-based TTS systems
"""

# === Standard Libraries ===
import requests
import os 
from datetime import datetime
import azure.cognitiveservices.speech as speechsdk
import numpy as np
import sounddevice as sd
import soundfile as sf
from io import BytesIO
from module_piper import text_to_speech_with_pipelining
from module_silero import text_to_speech_with_pipelining_silero
from elevenlabs.client import ElevenLabs
from elevenlabs import play

elevenlabs_client = None
def init_elevenlabs_client(api_key):
    """
    Initializes the global ElevenLabs client instance with the provided API key.
    
    Parameters:
    - api_key (str): The ElevenLabs API key.
    """
    global elevenlabs_client
    if not api_key:
        raise ValueError("ElevenLabs API key must be provided for initialization.")
    elevenlabs_client = ElevenLabs(api_key=api_key)

def update_tts_settings(ttsurl):
    """
    Updates TTS settings using a POST request to the specified server.

    Parameters:
    - ttsurl: The URL of the TTS server.
    """
    url = f"{ttsurl}/set_tts_settings"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    payload = {
        "stream_chunk_size": 100,
        "temperature": 0.75,
        "speed": 1,
        "length_penalty": 1.0,
        "repetition_penalty": 5,
        "top_p": 0.85,
        "top_k": 50,
        "enable_text_splitting": True
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("LOAD: TTS Settings updated successfully.")
        else:
            print(f"ERROR: Failed to update TTS settings. Status code: {response.status_code}")
            print(f"INFO: Response: {response.text}")
    except Exception as e:
        print(f"ERROR: TTS update failed: {e}")

def play_audio_stream(tts_stream, samplerate=22050, channels=1, gain=5.0, normalize=False):
    """
    Play the audio stream through speakers using SoundDevice with volume/gain adjustment.
    
    Parameters:
    - tts_stream: Stream of audio data in chunks.
    - samplerate: The sample rate of the audio data.
    - channels: The number of audio channels (e.g., 1 for mono, 2 for stereo).
    - gain: A multiplier for adjusting the volume. Default is 1.0 (no change).
    - normalize: Whether to normalize the audio to use the full dynamic range.
    """
    try:
        with sd.OutputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=4096) as stream:
            for chunk in tts_stream:
                if chunk:
                    # Convert bytes to int16 using numpy
                    audio_data = np.frombuffer(chunk, dtype='int16')
                    
                    # Normalize the audio (if enabled)
                    if normalize:
                        max_value = np.max(np.abs(audio_data))
                        if max_value > 0:
                            audio_data = audio_data / max_value * 32767
                    
                    # Apply gain adjustment
                    audio_data = np.clip(audio_data * gain, -32768, 32767).astype('int16')

                    # Write the adjusted audio data to the stream
                    stream.write(audio_data)
                else:
                    print("ERROR: Received empty chunk.")
    except Exception as e:
        print(f"ERROR: Error during audio playback: {e}")

def azure_tts(text, azure_api_key, azure_region, tts_voice):
    """
    Generate TTS audio using Azure Speech SDK.
    
    Parameters:
    - text (str): The text to convert into speech.
    - azure_api_key (str): Azure API key for authentication.
    - azure_region (str): Azure region for the TTS service.
    - tts_voice (str): Voice configuration for Azure TTS.
    """
    try:
        # Initialize Azure Speech SDK
        speech_config = speechsdk.SpeechConfig(subscription=azure_api_key, region=azure_region)
        audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

        # Create a Speech Synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        # SSML Configuration
        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='en-US'>
            <voice name='{tts_voice}'>
                <prosody rate="10%" pitch="5%" volume="default">
                    {text}
                </prosody>
            </voice>
        </speak>
        """

        # Perform speech synthesis
        result = synthesizer.speak_ssml_async(ssml).get()

        # Check for errors
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            pass
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"ERROR: Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.error_details:
                print(f"ERROR: Error details: {cancellation_details.error_details}")
    except Exception as e:
        print(f"ERROR: Azure TTS generation failed: {e}")

def elevenlabs_tts(text, voice_id="JBFqnCBsd6RMkjVDRZzb", model_id="eleven_multilingual_v2", output_format="mp3_44100_128"):
    """
    Generate TTS audio using ElevenLabs.
    
    Parameters:
    - text (str): The text to convert into speech.
    - voice_id (str): Voice ID for ElevenLabs.
    - model_id (str): Model ID for ElevenLabs.
    - output_format (str): Output format for the audio.
    """
    try:
        audio = elevenlabs_client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
        )
        play(audio)
    except Exception as e:
        print(f"ERROR: ElevenLabs TTS generation failed: {e}")

def alltalk_tts(text, ttsurl, tts_voice):
    try:
        # API endpoint and payload
        url = f"{ttsurl}/api/tts-generate"
        data = {
            "text_input": text,
            "text_filtering": "standard",
            "character_voice_gen": f"{tts_voice}.wav",
            "narrator_enabled": "false",
            "narrator_voice_gen": "default.wav",
            "text_not_inside": "character",
            "language": "en",
            "output_file_name": "test_output",
            "output_file_timestamp": "true",
            "autoplay": "false",
            "autoplay_volume": 0.8,
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        wav_url = response.json().get("output_file_url")
        if not wav_url:
            print("Error: No WAV file URL provided.")
            return
        response = requests.get(wav_url)
        response.raise_for_status()
        wav_data = BytesIO(response.content)
        data, samplerate = sf.read(wav_data, dtype='float32')
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        print(f"An error occurred: {e}")

def local_tts(text):
    """
    Generate TTS audio locally using `espeak-ng` and `sox`.

    Parameters:
    - text (str): The text to convert into speech.
    """
    try:
        command = (
            f'espeak-ng -s 140 -p 50 -v en-us+m3 "{text}" --stdout | '
            f'sox -t wav - -c 1 -t wav - gain 0.0 reverb 30 highpass 500 lowpass 3000 | aplay'
        )
        os.system(command)
    except Exception as e:
        print(f"ERROR: Local TTS generation failed: {e}")

def server_tts(text, ttsurl, tts_voice):
    """
    Generate TTS audio using a server-based TTS system.

    Parameters:
    - text (str): The text to convert into speech.
    - ttsurl (str): The base URL of the TTS server.
    - tts_voice (str): Speaker/voice configuration for the TTS.
    """
    try:
        chunk_size = 1024
        full_url = f"{ttsurl}/tts_stream"
        params = {
            'text': text,
            'speaker_wav': tts_voice,
            'language': "en"
        }
        headers = {'accept': 'audio/x-wav'}
        response = requests.get(full_url, params=params, headers=headers, stream=True)
        response.raise_for_status()
        def tts_stream():
            for chunk in response.iter_content(chunk_size=chunk_size):
                yield chunk
        play_audio_stream(tts_stream())
    except Exception as e:
        print(f"ERROR: Server TTS generation failed: {e}")

def generate_tts_audio(text: str, config):
    """
    Generate TTS audio for the given text using the specified TTS system.
    Handles both dictionary-style config and TTSConfig objects for backward compatibility.
    
    Parameters:
    - text (str): The text to convert into speech
    - config: Either a TTSConfig object or a dictionary with TTS settings
    """
    try:
        if not isinstance(config, dict) and not hasattr(config, '__getitem__'):
            raise ValueError("Config must be either a dictionary or TTSConfig object")
            
        ttsoption = config['ttsoption']
        toggle_charvoice = config['toggle_charvoice']
        
        if ttsoption == "azure":
            azure_tts(text, config['azure_api_key'], config['azure_region'], config['tts_voice'])
            
        elif ttsoption == "elevenlabs":
            if not elevenlabs_client:
                init_elevenlabs_client(config['elevenlabs_api_key'])
            elevenlabs_tts(text, config['voice_id'], config['model_id'])
            
        elif ttsoption == "local" and toggle_charvoice:
            local_tts(text)
            
        elif ttsoption == "alltalk" and toggle_charvoice:
            alltalk_tts(text, config['ttsurl'], config['tts_voice'])
            
        elif ttsoption == "piper" and toggle_charvoice:
            import asyncio
            asyncio.run(text_to_speech_with_pipelining(text))

        elif ttsoption == "silero":
            asyncio.run(text_to_speech_with_pipelining_silero(text))
            
        elif ttsoption == "xttsv2" and toggle_charvoice:
            if not ttsurl:
                raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: TTS URL and play_audio_stream function must be provided for 'xttsv2'.")
            server_tts(text, ttsurl, tts_voice)

        # Local TTS generation using local onboard PIPER TTS
        elif ttsoption == "silero":
            asyncio.run(text_to_speech_with_pipelining_silero(text))

        else:
            raise ValueError(f"Invalid TTS option or character voice flag: {ttsoption}")
            
    except Exception as e:
        print(f"ERROR: Text-to-speech generation failed: {e}")
