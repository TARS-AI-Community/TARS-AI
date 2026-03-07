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

    # Don't run barge-in on wake responses — they're too short and the mic
    # picks up TARS's own voice, causing false positives
    asyncio.run(play_audio_chunks(wake_response, CONFIG['TTS']['ttsoption'], True))

    ui_manager.set_tars_status("LISTENING")

def utterance_callback(message):
    """
    Process the recognized message from STTManager and stream audio response to speakers.

    Parameters:
    - message (str): The recognized message from the Speech-to-Text (STT) module.
    """
    try:
        import modules.module_speed as speed
        speed.mark_utterance_start()
        speed.start('total')

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

        ui_manager.update_data("USER", user_text, "USER")

        if "shutdown pc" in user_text.lower():
            queue_message(f"SHUTDOWN: Shutting down the PC...")
            os.system('shutdown /s /t 0')
            return

        ui_manager.set_tars_status("THINKING")

        # Check if preemptive LLM already fired during silence detection
        preemptive = message_dict.get("preemptive_llm_result")
        speed.start('llm_total')
        if preemptive is not None:
            parsed = preemptive
        else:
            parsed = process_completion(user_text)
        llm_total_dur = speed.stop('llm_total')

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
            # Vision calls must run synchronously
            func_calls = parsed.get("function_calls", [])
            has_vision = any(fc.get("function") == "capture_camera_view" for fc in func_calls)
            if has_vision:
                llm_execute_side_effects(parsed, user_text)
                reply = _sanitize_for_tts(parsed.get("reply", ""))
            else:
                reply = _sanitize_for_tts(parsed.get("reply", ""))
                # Run function_calls and memory saves in background — parallel with TTS
                if func_calls or parsed.get("new_memories"):
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

        # Detect emotion
        speed.start('emotion')
        emotion = None
        if CONFIG['EMOTION']['enabled'] and reply:
            emotion = detect_emotion(reply)
            if emotion:
                try:
                    from modules.module_chatui import update_emotion
                    update_emotion(emotion)
                except Exception:
                    pass
        emo_dur = speed.stop('emotion')

        character_name = CONFIG['CHAR']['character_name']
        ui_manager.update_data(character_name, reply, "TARS")

        reply = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', reply)

        ui_manager.set_tars_status("TALKING")

        # Start barge-in monitoring (mic listens for speech during TTS)
        if stt_manager:
            stt_manager.start_bargein_monitor(tts_text=reply)

        speed.start('tts')
        was_interrupted = asyncio.run(play_audio_chunks(reply, CONFIG['TTS']['ttsoption']))
        tts_dur = speed.stop('tts')

        # Stop barge-in monitoring
        if stt_manager:
            stt_manager.stop_bargein_monitor()

        if was_interrupted:
            time.sleep(0.3)
            ui_manager.set_tars_status("LISTENING")
        else:
            ui_manager.set_tars_status("STANDBY")

        # Round summary log
        speaker = '?'
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
            if sid and sid.current_speaker:
                speaker = sid.current_speaker
        except Exception:
            pass
        parts = [
            f"speaker={speaker}",
            f"emotion={emotion or '?'}",
            f"preemptive={'yes' if preemptive is not None else 'no'}",
            f"end={'barge-in' if was_interrupted else 'timeout'}",
        ]
        queue_message(f"ROUND: {' | '.join(parts)}")

        # Speed profiling summary
        total_dur = speed.stop('total')
        if speed.enabled:
            sp = []
            llm_timings = parsed.get('_timings', {}) if isinstance(parsed, dict) else {}
            if llm_timings:
                id_t = llm_timings.get('prompt_identity', 0)
                mem_t = llm_timings.get('prompt_memory', 0)
                prompt_t = llm_timings.get('prompt_build', 0)
                prompt_other = prompt_t - id_t - mem_t
                sp.append(f"identity({speed.fmt(id_t)})")
                sp.append(f"memory({speed.fmt(mem_t)})")
                if prompt_other > 0.001:
                    sp.append(f"prompt_other({speed.fmt(prompt_other)})")
                sp.append(f"llm_wait({speed.fmt(llm_timings.get('llm_first_byte', 0))})")
                sp.append(f"llm_stream({speed.fmt(llm_timings.get('llm_stream', 0))})")
                sp.append(f"llm_parse({speed.fmt(llm_timings.get('parse', 0))})")
            else:
                sp.append(f"llm_total({speed.fmt(llm_total_dur)})")
            sp.append(f"emotion({speed.fmt(emo_dur)})")
            sp.append(f"tts({speed.fmt(tts_dur)})")
            sp.append(f"total({speed.fmt(total_dur)})")
            queue_message(f"SPEED: {', '.join(sp)}")

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