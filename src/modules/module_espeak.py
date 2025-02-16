import io
import os
import wave
import subprocess
import re
from pydub import AudioSegment

def apply_tars_effects(audio):
    """
    Apply TARS-like effects: pitch change, speed up, reverb, and echo.
    """
    sample_rate = audio.frame_rate  # Get the actual sample rate
    lower_rate = int(sample_rate * 0.88)
    audio = audio._spawn(audio.raw_data, overrides={"frame_rate": lower_rate})
    audio = audio.set_frame_rate(sample_rate)
    audio = audio.speedup(playback_speed=1.42)
    
    # Apply echo and reverb
    reverb_decay = -2
    delay_ms = 3
    echo1 = audio - reverb_decay
    echo2 = echo1 - 1
    audio = audio.overlay(echo1, position=delay_ms)
    audio = audio.overlay(echo2, position=delay_ms * 2)  # Fixed the delay overlap
    
    return audio

async def text_to_speech_with_pipelining_espeak(text):
    """
    Converts text to speech using `espeak-ng`, applies TARS effects, and streams playback.
    
    Parameters:
    - text (str): The text to convert into speech.

    Yields:
    - BytesIO: Chunks of processed audio as they're generated.
    """
    # Split text into smaller chunks at sentence boundaries
    chunks = re.split(r'(?<=\.)\s', text)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue  # Skip empty chunks

        try:
            # Generate raw WAV data using espeak-ng
            command = [
                "espeak-ng", "-s", "140", "-p", "50", "-v", "en-us+m3", chunk, "--stdout"
            ]
            
            # Run espeak-ng and capture the output
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if process.returncode != 0:
                print(f"ERROR: espeak-ng failed: {process.stderr.decode()}")
                continue

            # Convert espeak output to Pydub AudioSegment
            audio = AudioSegment.from_file(io.BytesIO(process.stdout), format="wav")

            # Apply TARS-like effects
            audio = apply_tars_effects(audio)

            # Convert modified audio to BytesIO buffer
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit samples
                wav_file.setframerate(audio.frame_rate)  # Keep the same sample rate
                wav_file.writeframes(audio.raw_data)

            wav_buffer.seek(0)
            yield wav_buffer  # Yield the processed audio chunk

        except Exception as e:
            print(f"ERROR: Local TTS generation failed: {e}")
            continue