"""
module_main.py

Core logic module for the TARS-AI application.

"""
# === Standard Libraries ===
import os
import threading
import json
import re
import concurrent.futures
import sys
import time
import asyncio
import sounddevice as sd
import soundfile as sf

# === Custom Modules ===
from modules.module_config import load_config
from modules.module_btcontroller import start_controls
from modules.module_discord import *
from modules.module_llm import process_completion
from modules.module_tts import play_audio_chunks

# === Constants and Globals ===
character_manager = None
memory_manager = None
stt_manager = None

CONFIG = load_config()

# Global Variables (if needed)
stop_event = threading.Event()
executor = concurrent.futures.ProcessPoolExecutor(max_workers=4)

# === Threads ===
def start_bt_controller_thread():
    """
    Wrapper to start the BT Controller functionality in a thread.
    """
    try:
        print(f"LOAD: Starting BT Controller thread...")
        while not stop_event.is_set():
            start_controls()
    except Exception as e:
        print(f"ERROR: {e}")

def stream_text_nonblocking(text, delay=0.03):
    """
    Streams text character by character in a non-blocking way.

    Parameters:
    - text (str): The text to stream.
    - delay (float): Delay (in seconds) between each character.
    """
    def stream():
        for char in text:
            sys.stdout.write(char)  # Write one character at a time
            sys.stdout.flush()      # Ensure the text is shown immediately
            time.sleep(delay)
        
        # Explicitly add only one newline
        if not text.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()

    # Run the streaming function in a separate thread
    threading.Thread(target=stream, daemon=True).start()

# === Callback Functions ===
def process_discord_message_callback(user_message):
    """
    Processes the user's message and generates a response.

    Parameters:
    - user_message (str): The message content sent by the user.

    Returns:
    - str: The bot's response.
    """
    try:
        # Parse the user message
        #print(user_message)

        match = re.match(r"<@(\d+)> ?(.*)", user_message)

        if match:
            mentioned_user_id = match.group(1)  # Extracted user ID
            message_content = match.group(2).strip()  # Extracted message content (trim leading/trailing spaces)

        #stream_text_nonblocking(f"{mentioned_user_id}: {message_content}")
        #print(message_content)

        # Process the message using process_completion
        reply = process_completion(message_content)  # Process the message

        #print(f"TARS: {reply}")
        #stream_text_nonblocking(f"TARS: {reply}")
        
    except Exception as e:
        print(f"ERROR: {e}")

    return reply

def wake_word_callback(wake_response):
    """
    Play initial response when wake word is detected.

    Parameters:
    - wake_response (str): The response to the wake word.
    """ 
    asyncio.run(play_audio_chunks(wake_response, CONFIG['TTS']['ttsoption']))

def utterance_callback(message):
    """
    Process the recognized message from STTManager and stream audio response to speakers.

    Parameters:
    - message (str): The recognized message from the Speech-to-Text (STT) module.
    """
    try:
        # Parse the user message
        message_dict = json.loads(message)
        if not message_dict.get('text'):  # Handles cases where text is "" or missing
            #print(f"TARS: Going Idle...")
            return
        
        #Print or stream the response
        #print(f"USER: {message_dict['text']}")
        stream_text_nonblocking(f"USER: {message_dict['text']}")

        # Check for shutdown command
        if "shutdown pc" in message_dict['text'].lower():
            print(f"SHUTDOWN: Shutting down the PC...")
            os.system('shutdown /s /t 0')
            return  # Exit function after issuing shutdown command
        
        # Process the message using process_completion
        reply = process_completion(message_dict['text'])  # Process the message

        # Extract the <think> block if present
        try:
            match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL)
            thoughts = match.group(1).strip() if match else ""
            
            # Remove the <think> block and clean up trailing whitespace/newlines
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        except Exception:
            thoughts = ""

        # Debug output for thoughts
        if thoughts:
            #print(f"DEBUG: Thoughts\n{thoughts}")
            pass

        # Stream the AI's reply
        stream_text_nonblocking(f"TARS: {reply}")

        # Strip special chars so he doesnt say them
        reply = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-]', '', reply)
        
        # Stream TTS audio to speakers
        asyncio.run(play_audio_chunks(reply, CONFIG['TTS']['ttsoption']))

    except json.JSONDecodeError:
        print("ERROR: Invalid JSON format. Could not process user message.")
    except Exception as e:
        print(f"ERROR: {e}")

def post_utterance_callback():
    """
    Restart listening for another utterance after handling the current one.
    """
    global stt_manager
    stt_manager._transcribe_utterance()

# === Initialization ===
def initialize_managers(mem_manager, char_manager, stt_mgr):
    """
    Pass in the shared instances for MemoryManager, CharacterManager, and STTManager.
    
    Parameters:
    - mem_manager: The MemoryManager instance from app.py.
    - char_manager: The CharacterManager instance from app.py.
    - stt_mgr: The STTManager instance from app.py.
    """
    global memory_manager, character_manager, stt_manager
    memory_manager = mem_manager
    character_manager = char_manager
    stt_manager = stt_mgr