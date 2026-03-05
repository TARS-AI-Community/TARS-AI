"""
module_main.py

Core logic module for the TARS-AI application.

"""
# === Standard Libraries ===
import os
import threading
import json
import re
import sys
import time
import asyncio

# === Custom Modules ===
from modules.module_config import load_config, get_capabilities
from modules.module_llm import process_completion, detect_emotion, llm_execute_side_effects, _sanitize_for_tts
from modules.module_tts import play_audio_chunks
from modules.module_messageQue import queue_message
from modules.module_servoctl import initialize_servos

CONFIG = load_config()
CAPABILITIES = get_capabilities()

# Conditional imports based on device capabilities
UIManager = None
if CAPABILITIES is None or CAPABILITIES.can_use_ui:
    _use_lite_ui = CAPABILITIES is not None and not CAPABILITIES.can_use_opengl
    try:
        if _use_lite_ui:
            from modules.module_ui_lite import UIManagerLite as _UIManager
        else:
            from modules.module_ui import UIManager as _UIManager
        UIManager = _UIManager
    except ImportError as e:
        print(f"WARNING: UIManager not available: {e}")

# Discord - lightweight, available on all devices
try:
    from modules.module_discord import *
except ImportError as e:
    print(f"WARNING: Discord module not available: {e}")

# BT Controller
try:
    from modules.module_btcontroller import start_controls
except ImportError:
    start_controls = None

# === Constants and Globals ===
ui_manager = None
character_manager = None
memory_manager = None
stt_manager = None
shutdown_event = None
battery_module = None

# Global Variables (if needed)
stop_event = threading.Event()

# === Threads ===
def start_bt_controller_thread():
    """
    Wrapper to start the BT Controller functionality in a thread.
    """
    config = load_config()
    if not config['CONTROLS'].get('enabled', False):
        return
    if start_controls is None:
        queue_message("WARNING: BT Controller not available")
        return
    try:
        queue_message(f"LOAD: Starting BT Controller thread...")
        while not stop_event.is_set():
            start_controls()
    except Exception as e:
        queue_message(f"ERROR: {e}")

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
        #queue_message(user_message)

        match = re.match(r"<@(\d+)> ?(.*)", user_message)

        if match:
            mentioned_user_id = match.group(1)  # Extracted user ID
            message_content = match.group(2).strip()  # Extracted message content (trim leading/trailing spaces)

        #stream_text_nonblocking(f"{mentioned_user_id}: {message_content}")
        #queue_message(message_content)

        # Process the message using process_completion
        reply = process_completion(message_content)  # Process the message

        #queue_message(f"TARS: {reply}")
        #stream_text_nonblocking(f"TARS: {reply}")
        
    except Exception as e:
        queue_message(f"ERROR: {e}")

    return reply

def wake_word_callback(wake_response):
    """
    Play initial response when wake word is detected.

    Parameters:
    - wake_response (str): The response to the wake word.
    """ 

    # Deactivate screensaver when wake word is detected
    if ui_manager:
        ui_manager.deactivate_screensaver()

    character_name = CONFIG['CHAR']['character_name']
    ui_manager.update_data(character_name, wake_response, character_name)

    ui_manager.set_tars_status("TALKING")
    asyncio.run(play_audio_chunks(wake_response, CONFIG['TTS']['ttsoption'], True))
    ui_manager.set_tars_status("LISTENING")

def utterance_callback(message):
    """
    Process the recognized message from STTManager and stream audio response to speakers.

    Parameters:
    - message (str): The recognized message from the Speech-to-Text (STT) module.
    """
    try:
        # Deactivate screensaver when user speaks
        if ui_manager:
            ui_manager.deactivate_screensaver()
        
        # Parse the user message
        message_dict = json.loads(message)
        if not message_dict.get('text'):  # Handles cases where text is "" or missing
            #queue_message(f"TARS: Going Idle...")
            return
        
        # Strip any special characters/control characters from user text
        user_text = message_dict['text'].strip()
        
        #Print or stream the response
        #queue_message(f"USER: {user_text}")
        ui_manager.update_data("USER", user_text, "USER")
        queue_message(f"USER: {user_text}", stream=False)

        if "shutdown pc" in user_text.lower():
            queue_message(f"SHUTDOWN: Shutting down the PC...")
            os.system('shutdown /s /t 0')
            return

        ui_manager.set_tars_status("THINKING")

        # Check if preemptive LLM already fired during silence detection
        preemptive = message_dict.get("preemptive_llm_result")
        if preemptive is not None:
            queue_message("INFO: Using preemptive LLM result (saved ~1-3s)")
            parsed = preemptive
        else:
            parsed = process_completion(user_text)

        # If a movement happened during the LLM call, discard the result
        if stt_manager and stt_manager.is_cancelled():
            queue_message("INFO: LLM response discarded (movement interrupted)")
            ui_manager.set_tars_status("STANDBY")
            return

        # Handle both old string returns and new parsed dict returns
        if parsed is None:
            queue_message("ERROR: LLM returned no response")
            ui_manager.set_tars_status("STANDBY")
            return
        if isinstance(parsed, str):
            # Legacy path or error string
            reply = parsed
        else:
            reply = _sanitize_for_tts(parsed.get("reply", ""))

            # Run function_calls and memory saves in background — parallel with TTS
            if parsed.get("function_calls") or parsed.get("new_memories"):
                threading.Thread(
                    target=llm_execute_side_effects,
                    args=(parsed, user_text), daemon=True
                ).start()

        try:
            match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL)
            thoughts = match.group(1).strip() if match else ""

            # Remove the <think> block and clean up trailing whitespace/newlines
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        except Exception:
            thoughts = ""

        # Check again before TTS — movement could have started during post-processing
        if stt_manager and stt_manager.is_cancelled():
            queue_message("INFO: LLM response discarded (movement interrupted)")
            ui_manager.set_tars_status("STANDBY")
            return

        if CONFIG['EMOTION']['enabled'] and reply:
            detected = detect_emotion(reply)
            if detected:
                try:
                    from modules.module_chatui import update_emotion
                    update_emotion(detected)
                except Exception:
                    pass

        character_name = CONFIG['CHAR']['character_name']
        ui_manager.update_data(character_name, reply, "TARS")
        queue_message(f"{character_name}: {reply}", stream=False)

        reply = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', reply)

        ui_manager.set_tars_status("TALKING")
        asyncio.run(play_audio_chunks(reply, CONFIG['TTS']['ttsoption']))
        ui_manager.set_tars_status("STANDBY")

    except json.JSONDecodeError:
        queue_message("ERROR: Invalid JSON format. Could not process user message.")
    except Exception as e:
        ui_manager.set_tars_status("STANDBY")
        queue_message(f"ERROR: {e}")

def post_utterance_callback():
    """
    Restart listening for another utterance after handling the current one.
    """
    global stt_manager
    stt_manager._transcribe_utterance()

# === Initialization ===
def initialize_managers(mem_manager, char_manager, stt_mgr, ui_mgr, shutdown_evt=None, battery_mod=None):
    """
    Pass in the shared instances for MemoryManager, CharacterManager, STTManager, and other components.
    
    Parameters:
    - mem_manager: The MemoryManager instance from app.py.
    - char_manager: The CharacterManager instance from app.py.
    - stt_mgr: The STTManager instance from app.py.
    - ui_mgr: The UIManager instance from app.py.
    - shutdown_evt: The shutdown event from app.py.
    - battery_mod: The BatteryModule instance from app.py.
    """
    global memory_manager, character_manager, stt_manager, ui_manager, shutdown_event, battery_module
    memory_manager = mem_manager
    character_manager = char_manager
    stt_manager = stt_mgr
    ui_manager = ui_mgr
    shutdown_event = shutdown_evt
    battery_module = battery_mod

def startup_initialization():
    try:
        queue_message("SYSTEM: Starting servo initialization...")
        initialize_servos()
        queue_message("SYSTEM: Servo initialization complete")
        try:
            from modules.module_cputemp import (
                CPUTempModule,
                set_cpu_temp_instance, 
                set_ventilate_callback, 
                start_thermal_monitoring
            )
            from modules.module_servoctl import ventilate_on
            cpu_temp_module = CPUTempModule()
            set_cpu_temp_instance(cpu_temp_module)
            set_ventilate_callback(ventilate_on)
            start_thermal_monitoring()
        except Exception as e:
            print(f"WARNING: Thermal monitoring not available: {e}")
    except Exception as e:
        queue_message(f"ERROR: Servo initialization failed - {e}")