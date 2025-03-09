import numpy as np
import requests
import asyncio
from fastrtc import Stream, ReplyOnPause, get_stt_model, get_tts_model

# 🔹 Ollama API Configuration (LM Studio Backend)
OLLAMA_URL = "http://192.168.2.58:1234/v1/chat/completions"
OLLAMA_MODEL = "silicon-maid-7b"  # Update if using a different model

# 🔹 Initialize FastRTC STT model (TTS is replaced with Piper)
stt_model = get_stt_model()

# 🔹 Import Piper TTS
import sounddevice as sd
import soundfile as sf
from io import BytesIO
from piper.voice import PiperVoice
import wave
import re
import os
import ctypes

# 🔹 Suppress ALSA sound errors
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
asound = ctypes.cdll.LoadLibrary('libasound.so')

# 🔹 Load Piper TTS Model
script_dir = os.path.dirname(__file__)
model_path = os.path.join(script_dir, '..', f'tts/TARS.onnx')
voice = PiperVoice.load(model_path)

async def synthesize(voice, chunk):
    """
    Synthesize a chunk of text into a BytesIO buffer.
    """
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit samples
        wav_file.setframerate(voice.config.sample_rate)
        try:
            voice.synthesize(chunk, wav_file)
        except TypeError as e:
            pass
    wav_buffer.seek(0)
    return wav_buffer

async def text_to_speech_with_pipelining_piper(text):
    """
    Converts text to speech using the Piper model and streams audio as it's generated.
    """
    chunks = re.split(r'(?<=\.)\s', text)  # Split at sentence boundaries

    for chunk in chunks:
        if chunk.strip():  # Ignore empty chunks
            wav_buffer = await synthesize(voice, chunk.strip())
            yield wav_buffer  # Yield the chunk for external playback

def chat_handler(audio: tuple[int, np.ndarray]):
    """
    Handles transcribed speech, sends cleaned text to LM Studio, and streams TTS response.
    """
    sample_rate, audio_data = audio
    print(f"[chat_handler] Received audio with {len(audio_data)} samples")

    # 🔹 Transcribe Audio
    transcript = stt_model.stt((sample_rate, audio_data)).strip()
    print("[chat_handler] Transcript:", transcript)

    if not transcript:
        print("[chat_handler] No speech detected.")
        return iter([])  # Return an empty generator to avoid FastRTC errors

    # 🔹 Query LM Studio API
    reply_text = raw_complete_llm(transcript)
    
    if not reply_text:
        reply_text = "I couldn't generate a response."

    print("[chat_handler] Bot Reply:", reply_text)

    # 🔹 Convert async generator to synchronous generator
    return sync_tts_generator(reply_text)

import numpy as np
import soundfile as sf

def sync_tts_generator(text):
    """
    Calls the async Piper TTS function synchronously and yields audio as a NumPy array.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async_gen = text_to_speech_with_pipelining_piper(text)  # Get the async generator
    while True:
        try:
            wav_buffer = loop.run_until_complete(async_gen.__anext__())  # Get next chunk synchronously
            
            # ✅ Convert `_io.BytesIO` to raw bytes
            raw_audio = wav_buffer.read()

            # ✅ Convert bytes into a NumPy array
            audio_array, sample_rate = sf.read(BytesIO(raw_audio), dtype='int16')

            yield sample_rate, audio_array  # ✅ FastRTC expects (sample_rate, np.array)

        except StopAsyncIteration:
            break


# 🔹 Function to Query LM Studio API (OpenAI-Compatible Backend)
def raw_complete_llm(user_prompt: str) -> str:
    """
    Sends a user prompt to the LM Studio LLM API and returns the generated response.
    """
    data = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 4096,
        "temperature": 0.8,
        "top_p": 0.9
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(OLLAMA_URL, headers=headers, json=data)
        response.raise_for_status()
        response_json = response.json()

        # ✅ Extract response text properly
        bot_reply = response_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if not bot_reply:
            print("[raw_complete_llm] Empty response from LM Studio.")
            return None

        return bot_reply

    except requests.RequestException as e:
        print(f"[raw_complete_llm] ERROR: LLM request failed: {e}")
        return None

# 🔹 Create and Launch FastRTC Stream
stream = Stream(
    handler=ReplyOnPause(chat_handler),
    modality="audio",
    mode="send-receive"
)

print("🚀 FastRTC Voice Chat is running... Speak naturally or say 'Computer' first if wake word detection is enabled.")
stream.ui.launch()
