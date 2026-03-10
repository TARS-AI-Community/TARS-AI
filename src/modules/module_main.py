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
from modules.module_tts import play_audio_chunks, SentenceTTSPipeline
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
        import modules.module_llm as llm_mod
        speed.mark_utterance_start()
        speed.start('total')

        # Deactivate screensaver when user speaks
        if ui_manager:
            ui_manager.deactivate_screensaver()

        # Parse the user message
        message_dict = json.loads(message)
        if not message_dict.get('text'):
            return

        user_text = message_dict['text'].strip()

        ui_manager.update_data("USER", user_text, "USER")

        # Push voice-mode user message to web UI
        try:
            from modules.module_chatui import push_user_message
            push_user_message(user_text)
        except Exception:
            pass

        if "shutdown pc" in user_text.lower():
            queue_message(f"SHUTDOWN: Shutting down the PC...")
            os.system('shutdown /s /t 0')
            return

        ui_manager.set_tars_status("THINKING")

        # ── Sentence-pipeline TTS ─────────────────────────────────────────────
        _acc_raw    = ['']   # cumulative raw text from LLM (may include <think>)
        _clean_seen = ['']   # total clean text processed so far (for delta tracking)

        def _apply_sanitize(text):
            text = _sanitize_for_tts(text)
            text = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', text)
            return text.strip()

        def _on_first_play():
            ui_manager.set_tars_status("TALKING")
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text="")

        pipeline = SentenceTTSPipeline(
            CONFIG['TTS']['ttsoption'],
            sanitize=_apply_sanitize,
            on_first_play=_on_first_play,
        )

        # Add placeholder message to OpenGL UI for streaming updates
        character_name = CONFIG['CHAR']['character_name']
        ui_manager.update_data(character_name, "", "TARS")

        def on_reply_chunk(chunk, is_first):
            """Called from LLM streaming thread with each reply text piece."""
            _acc_raw[0] += chunk

            # Remove any completed <think>…</think> blocks from full raw text
            clean_total = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL)

            # If an unclosed <think> tag remains, wait for it to close
            if '<think>' in clean_total:
                return

            # Delta: only the NEW visible text since last call
            new_clean = clean_total[len(_clean_seen[0]):]
            _clean_seen[0] = clean_total

            if not new_clean:
                return

            # Stream to OpenGL UI (update last message in-place)
            ui_manager.update_streaming_data(clean_total)

            # Stream new text to web UI
            try:
                from modules.module_chatui import stream_reply_token
                stream_reply_token(new_clean)
            except Exception:
                pass

            # Feed to sentence-pipeline TTS
            pipeline.feed(new_clean)

        # Check if preemptive LLM already fired during silence detection
        preemptive = message_dict.get("preemptive_llm_result")

        stt_to_llm_dur = 0
        if preemptive is not None:
            # Preemptive result: no streaming possible, fall through to normal TTS
            parsed = preemptive
            llm_total_dur = 0.0
        else:
            # Notify web UI that streaming is starting
            try:
                from modules.module_chatui import begin_bot_stream
                begin_bot_stream()
            except Exception:
                pass

            pipeline.start()
            llm_mod._reply_chunk_callback = on_reply_chunk

            try:
                stt_to_llm_dur = speed.stop('stt_to_llm')
                speed.start('llm_total')
                parsed = process_completion(user_text)
                llm_total_dur = speed.stop('llm_total')
            finally:
                llm_mod._reply_chunk_callback = None
                # Flush remaining — try pipeline remainder, fall back to raw
                remaining = pipeline.remainder.strip()
                if not remaining:
                    full_clean = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL).strip()
                    remaining = full_clean[len(_clean_seen[0]):].strip()
                pipeline.finish(remaining=_apply_sanitize(remaining) if remaining else None)

        # If a movement happened during the LLM call, discard the result
        if stt_manager and stt_manager.is_cancelled():
            queue_message("INFO: LLM response discarded (movement interrupted)")
            if preemptive is None:
                try:
                    from modules.module_chatui import socketio
                    socketio.emit('bot_message', {'message': ''})
                except Exception:
                    pass
            ui_manager.set_tars_status("STANDBY")
            return

        if parsed is None:
            queue_message("DEBUG VOICE: parsed is None — LLM returned no response")
            if preemptive is None:
                try:
                    from modules.module_chatui import socketio
                    socketio.emit('bot_message', {'message': ''})
                except Exception:
                    pass
            ui_manager.set_tars_status("STANDBY")
            return

        # Extract the final reply text for post-processing (emotion, display)
        if isinstance(parsed, str):
            reply = parsed
        else:
            reply = _sanitize_for_tts(parsed.get("reply", ""))

        try:
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        except Exception:
            pass

        if stt_manager and stt_manager.is_cancelled():
            queue_message("INFO: LLM response discarded (movement interrupted)")
            if preemptive is None:
                try:
                    from modules.module_chatui import socketio
                    socketio.emit('bot_message', {'message': ''})
                except Exception:
                    pass
            ui_manager.set_tars_status("STANDBY")
            return

        # Detect emotion (parallel-safe — runs while TTS thread plays sentences)
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

        # Finalize the streaming message with the complete reply
        ui_manager.update_streaming_data(reply)

        # Handle side effects (vision/search/photo run inline, others in background)
        _followup_reply = None
        tools_dur = 0
        if not isinstance(parsed, str):
            func_calls = parsed.get("function_calls", [])
            new_mems = parsed.get("new_memories", [])
            queue_message(f"DEBUG VOICE: parsed type={type(parsed).__name__}, func_calls={func_calls}, new_memories={new_mems}")
            has_blocking_tool = any(
                fc.get("function") in ("capture_camera_view", "web_search", "take_photo")
                for fc in func_calls
            )
            if has_blocking_tool:
                queue_message(f"DEBUG VOICE: Running blocking side effects inline")
                speed.start('tools')
                llm_execute_side_effects(parsed, user_text)
                tools_dur = speed.stop('tools')
                # Check if side effects updated the reply (e.g. vision result, search summary)
                updated_reply = parsed.get("reply", "") or ""
                if updated_reply and updated_reply != reply:
                    _followup_reply = _sanitize_for_tts(updated_reply)
                    queue_message(f"DEBUG VOICE: Follow-up reply detected: {_followup_reply[:80]}...")
                else:
                    queue_message(f"DEBUG VOICE: No reply change after side effects")
            elif func_calls or new_mems:
                queue_message(f"DEBUG VOICE: Running side effects in background thread")
                threading.Thread(
                    target=llm_execute_side_effects,
                    args=(parsed, user_text), daemon=True
                ).start()
            else:
                queue_message(f"DEBUG VOICE: No side effects to run")
        else:
            queue_message(f"DEBUG VOICE: parsed is str (legacy), no side effects")

        # For preemptive results, TTS hasn't started yet — play full reply normally
        if preemptive is not None:
            reply_clean = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', reply)
            ui_manager.set_tars_status("TALKING")
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text=reply_clean)
            speed.start('tts')
            was_interrupted = asyncio.run(play_audio_chunks(reply_clean, CONFIG['TTS']['ttsoption']))
            pipeline._duration = speed.stop('tts')
            if stt_manager:
                stt_manager.stop_bargein_monitor()
        else:
            # Wait for the sentence-pipeline TTS to finish
            pipeline.join(timeout=120)
            if stt_manager:
                stt_manager.stop_bargein_monitor()
            was_interrupted = pipeline.interrupted

        # Speak follow-up if side effects produced new content (vision result, search summary)
        queue_message(f"DEBUG VOICE: followup_reply={'yes' if _followup_reply else 'no'}, was_interrupted={was_interrupted}")
        followup_tts_dur = 0
        if _followup_reply and not was_interrupted:
            followup_clean = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', _followup_reply)
            # Update OpenGL UI with follow-up content
            ui_manager.update_streaming_data(_followup_reply)
            ui_manager.set_tars_status("TALKING")
            if stt_manager:
                stt_manager.start_bargein_monitor(tts_text=followup_clean)
            speed.start('followup_tts')
            was_interrupted = asyncio.run(play_audio_chunks(followup_clean, CONFIG['TTS']['ttsoption']))
            followup_tts_dur = speed.stop('followup_tts')
            if stt_manager:
                stt_manager.stop_bargein_monitor()
            reply = _followup_reply  # Update for web UI display

        if was_interrupted:
            time.sleep(0.3)
            ui_manager.set_tars_status("LISTENING")
        else:
            ui_manager.set_tars_status("STANDBY")

        # Push final reply to web UI (finalizes streaming bubble or creates one for preemptive)
        # Mark audio_streamed=True since audio was played on Pi speakers — prevents
        # browser from also fetching legacy /audio_stream (double-play) and ensures
        # voice mode mic restarts properly via bot_audio_done
        try:
            from modules.module_chatui import socketio
            socketio.emit('bot_message', {'message': reply, 'audio_streamed': True})
            socketio.emit('bot_audio_done', {})
            socketio.emit('talking_state', {'talking': False})
        except Exception:
            pass

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
            if stt_to_llm_dur:
                sp.append(f"stt_to_llm({speed.fmt(stt_to_llm_dur)})")
            llm_timings = parsed.get('_timings', {}) if isinstance(parsed, dict) else {}
            if llm_timings:
                id_t = llm_timings.get('prompt_identity', 0)
                mem_t = llm_timings.get('prompt_memory', 0)
                prompt_t = llm_timings.get('prompt_build', 0)
                prompt_other = prompt_t - id_t - mem_t
                ttft = prompt_t + llm_timings.get('llm_first_byte', 0)
                sp.append(f"ttft({speed.fmt(ttft)})")
                sp.append(f"identity({speed.fmt(id_t)})")
                sp.append(f"memory({speed.fmt(mem_t)})")
                if prompt_other > 0.001:
                    sp.append(f"prompt_other({speed.fmt(prompt_other)})")
                sp.append(f"llm_wait({speed.fmt(llm_timings.get('llm_first_byte', 0))})")
                llm_stream_dur = llm_timings.get('llm_stream', 0)
                token_count = llm_timings.get('token_count', 0)
                if token_count and llm_stream_dur > 0:
                    tps = token_count / llm_stream_dur
                    sp.append(f"llm_stream({speed.fmt(llm_stream_dur)}, {token_count}tok, {tps:.1f} t/s)")
                else:
                    sp.append(f"llm_stream({speed.fmt(llm_stream_dur)})")
                sp.append(f"llm_parse({speed.fmt(llm_timings.get('parse', 0))})")
            else:
                sp.append(f"llm_total({speed.fmt(llm_total_dur)})")
            sp.append(f"emotion({speed.fmt(emo_dur)})")
            sp.append(f"tts({speed.fmt(pipeline.duration)})")
            if tools_dur:
                sp.append(f"tools({speed.fmt(tools_dur)})")
            if followup_tts_dur:
                sp.append(f"followup_tts({speed.fmt(followup_tts_dur)})")
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