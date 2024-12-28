"""
module_tts.py

Text-to-Speech (TTS) module for GPTARS application.

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
        "temperature": 0.7,
        "speed": 1.1,
        "length_penalty": 1.0,
        "repetition_penalty": 1.2,
        "top_p": 0.9,
        "top_k": 40,
        "enable_text_splitting": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: TTS Settings updated successfully.")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to update TTS settings. Status code: {response.status_code}")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Response: {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: TTS update failed: {e}")

def play_audio_stream(tts_stream, samplerate=22050, channels=1, gain=1.0, normalize=False):
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
        with sd.OutputStream(samplerate=samplerate, channels=channels, dtype='int16') as stream:
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
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Received empty chunk.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error during audio playback: {e}")

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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.error_details:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error details: {cancellation_details.error_details}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Azure TTS generation failed: {e}")
    
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
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Local TTS generation failed: {e}")

def server_tts(text, ttsurl, tts_voice):
    """
    Generate TTS audio using a server-based TTS system.

    Parameters:
    - text (str): The text to convert into speech.
    - ttsurl (str): The base URL of the TTS server.
    - tts_voice (str): Speaker/voice configuration for the TTS.
    - play_audio_stream (Callable): Function to play the audio stream.
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

        # Pass the response content to play_audio_stream
        def tts_stream():
            for chunk in response.iter_content(chunk_size=chunk_size):
                yield chunk

        play_audio_stream(tts_stream())
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Server TTS generation failed: {e}")


def generate_tts_audio(text, ttsoption, azure_api_key=None, azure_region=None, ttsurl=None, toggle_charvoice=True, tts_voice=None):
    """
    Generate TTS audio for the given text using the specified TTS system.

    Parameters:
    - text (str): The text to convert into speech.
    - ttsoption (str): The TTS system to use (Azure, server-based, or local).
    - ttsurl (str): The base URL of the TTS server (for server-based TTS).
    - toggle_charvoice (bool): Flag indicating whether to use character voice for TTS.
    - tts_voice (str): The TTS speaker/voice configuration.
    """
    try:
        # Azure TTS generation
        if ttsoption == "azure":
            if not azure_api_key or not azure_region:
                raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Azure API key and region must be provided for ttsoption 'azure'.")
            azure_tts(text, azure_api_key, azure_region, tts_voice)

        # Local TTS generation using `espeak-ng`
        elif ttsoption == "local" and toggle_charvoice:
            local_tts(text)

        # Server-based TTS generation using `xttsv2`
        elif ttsoption == "xttsv2" and toggle_charvoice:
            if not ttsurl:
                raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: TTS URL and play_audio_stream function must be provided for 'xttsv2'.")
            server_tts(text, ttsurl, tts_voice)

        else:
            raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Invalid TTS option or character voice flag.")

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Text-to-speech generation failed: {e}")

