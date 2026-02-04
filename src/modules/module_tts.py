"""
module_tts.py

Text-to-Speech (TTS) module for TARS-AI application.

Handles TTS functionality to convert text into audio using:
- Azure Speech SDK
- Local tools (e.g., espeak-ng)
- Server-based TTS systems

"""


import requests
import os 
from datetime import datetime
import numpy as np
import sounddevice as sd
import soundfile as sf
from io import BytesIO
import asyncio

from modules.module_messageQue import queue_message

# Conditional TTS module imports - not all are available on all devices
text_to_speech_with_pipelining_piper = None
text_to_speech_with_pipelining_silero = None
text_to_speech_with_pipelining_espeak = None
text_to_speech_with_pipelining_alltalk = None
text_to_speech_with_pipelining_elevenlabs = None
text_to_speech_with_pipelining_azure = None
text_to_speech_with_pipelining_openai = None
text_to_speech_with_pipelining_minimax = None

try:
    from modules.module_piper import text_to_speech_with_pipelining_piper as _piper
    text_to_speech_with_pipelining_piper = _piper
except ImportError:
    pass

try:
    from modules.module_silero import text_to_speech_with_pipelining_silero as _silero
    text_to_speech_with_pipelining_silero = _silero
except ImportError:
    pass

try:
    from modules.module_espeak import text_to_speech_with_pipelining_espeak as _espeak
    text_to_speech_with_pipelining_espeak = _espeak
except ImportError:
    pass

try:
    from modules.module_alltalk import text_to_speech_with_pipelining_alltalk as _alltalk
    text_to_speech_with_pipelining_alltalk = _alltalk
except ImportError:
    pass

try:
    from modules.module_elevenlabs import text_to_speech_with_pipelining_elevenlabs as _elevenlabs
    text_to_speech_with_pipelining_elevenlabs = _elevenlabs
except ImportError:
    pass

try:
    from modules.module_azure import text_to_speech_with_pipelining_azure as _azure
    text_to_speech_with_pipelining_azure = _azure
except ImportError:
    pass

try:
    from modules.module_openai import text_to_speech_with_pipelining_openai as _openai
    text_to_speech_with_pipelining_openai = _openai
except ImportError:
    pass

try:
    from modules.module_minimax import text_to_speech_with_pipelining_minimax as _minimax
    text_to_speech_with_pipelining_minimax = _minimax
except ImportError:
    pass


def update_tts_settings(ttsurl):
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
            queue_message(f"LOAD: TTS Settings updated successfully.")
        else:
            queue_message(f"ERROR: Failed to update TTS settings. Status code: {response.status_code}")
            queue_message(f"INFO: Response: {response.text}")
    except Exception as e:
        queue_message(f"ERROR: TTS update failed: {e}")

def play_audio_stream(tts_stream, samplerate=22050, channels=1, gain=1.0, normalize=False):
    try:
        with sd.OutputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=4096) as stream:
            for chunk in tts_stream:
                if chunk:
                    audio_data = np.frombuffer(chunk, dtype='int16')
                    
                    if normalize:
                        max_value = np.max(np.abs(audio_data))
                        if max_value > 0:
                            audio_data = audio_data / max_value * 32767
                    
                    audio_data = np.clip(audio_data * gain, -32768, 32767).astype('int16')
                    stream.write(audio_data)
                else:
                    queue_message(f"ERROR: Received empty chunk.")
    except Exception as e:
        queue_message(f"ERROR: Error during audio playback: {e}")


async def generate_tts_audio(text, ttsoption, is_wakeword=False, azure_api_key=None, azure_region=None, ttsurl=None, toggle_charvoice=True, tts_voice=None):
    try:
        if ttsoption == "azure" and text_to_speech_with_pipelining_azure:
           async for chunk in text_to_speech_with_pipelining_azure(text):
                yield chunk

        elif ttsoption == "espeak" and text_to_speech_with_pipelining_espeak:
            async for chunk in text_to_speech_with_pipelining_espeak(text):
                yield chunk

        elif ttsoption == "alltalk" and text_to_speech_with_pipelining_alltalk:
            async for chunk in text_to_speech_with_pipelining_alltalk(text):
                yield chunk
                
        elif ttsoption == "piper" and text_to_speech_with_pipelining_piper:
            async for chunk in text_to_speech_with_pipelining_piper(text):
                yield chunk  

        elif ttsoption == "elevenlabs" and text_to_speech_with_pipelining_elevenlabs:
            async for chunk in text_to_speech_with_pipelining_elevenlabs(text, is_wakeword):
                yield chunk

        elif ttsoption == "minimax" and text_to_speech_with_pipelining_minimax:
            async for chunk in text_to_speech_with_pipelining_minimax(text, is_wakeword):
                yield chunk

        elif ttsoption == "silero" and text_to_speech_with_pipelining_silero:
            async for chunk in text_to_speech_with_pipelining_silero(text):
                yield chunk 

        elif ttsoption == "openai" and text_to_speech_with_pipelining_openai:
            async for chunk in text_to_speech_with_pipelining_openai(text, is_wakeword):
                yield chunk

        else:
            # Try fallback TTS options
            fallback_order = [
                ("openai", text_to_speech_with_pipelining_openai),
                ("elevenlabs", text_to_speech_with_pipelining_elevenlabs),
                ("espeak", text_to_speech_with_pipelining_espeak),
                ("piper", text_to_speech_with_pipelining_piper),
            ]
            
            for name, func in fallback_order:
                if func is not None:
                    queue_message(f"WARNING: TTS '{ttsoption}' not available, falling back to '{name}'")
                    if name in ["openai", "elevenlabs", "minimax"]:
                        async for chunk in func(text, is_wakeword):
                            yield chunk
                    else:
                        async for chunk in func(text):
                            yield chunk
                    return
            
            queue_message(f"ERROR: No TTS backend available for '{ttsoption}'")

    except Exception as e:
        queue_message(f"ERROR: Text-to-speech generation failed: {e}")

async def play_audio_chunks(text, config, is_wakeword=False):
    audio_queue = asyncio.Queue(maxsize=3)
    synthesis_done = asyncio.Event()
    
    async def synthesize_chunks():
        try:
            async for audio_chunk in generate_tts_audio(text, config, is_wakeword):
                await audio_queue.put(audio_chunk)
        except Exception as e:
            queue_message(f"ERROR: Synthesis failed: {e}")
        finally:
            synthesis_done.set()
    
    async def play_chunks():
        try:
            requests.get("http://127.0.0.1:5012/start_talking", timeout=1)
        except:
            pass
        
        while True:
            try:
                try:
                    audio_chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if synthesis_done.is_set() and audio_queue.empty():
                        break
                    continue
                
                data, samplerate = sf.read(audio_chunk, dtype='float32')
                max_val = np.max(np.abs(data))
                if max_val > 0:
                    data = data / max_val
                
                gain = 1.5
                data = np.clip(data * gain, -1.0, 1.0)
                
                sd.play(data, samplerate)
                sd.wait()
                
            except Exception as e:
                queue_message(f"ERROR: Failed to play chunk: {e}")
                if synthesis_done.is_set() and audio_queue.empty():
                    break
        
        try:
            requests.get("http://127.0.0.1:5012/stop_talking", timeout=1)
        except:
            pass
    
    await asyncio.gather(
        synthesize_chunks(),
        play_chunks()
    )