"""
LLM CONTROLLER - V3
==========================
# atomikspace (discord)
# olivierdion1@hotmail.com
"""


import requests
import threading
import json
import re
import concurrent.futures
import random
import asyncio
from modules.module_config import load_config
from modules.module_prompt import build_prompt
from modules.module_engine  import execute_movement
from modules.module_vision import describe_camera_view_openai

from modules.module_messageQue import queue_message

CONFIG = load_config()
character_manager = None
memory_manager = None

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

if CONFIG['EMOTION']['enabled']:
    from transformers import pipeline
    classifier = pipeline("text-classification", model="SamLowe/roberta-base-go_emotions", top_k=None)

def get_completion(user_prompt, istext=True):

    if memory_manager is None or character_manager is None:
        raise ValueError("MemoryManager and CharacterManager must be initialized before generating completions.")

    try:
        thinking_responses_raw = CONFIG["CHAR"].get('thinking_responses', '[]')
        try:
            thinking_responses = json.loads(thinking_responses_raw)
        except (json.JSONDecodeError, TypeError):
            thinking_responses = []
        if not isinstance(thinking_responses, list):
            thinking_responses = []

        if thinking_responses and len(thinking_responses) > 0:
            thinking_text = random.choice(thinking_responses)
            if thinking_text and isinstance(thinking_text, str) and thinking_text.strip():
                queue_message(f"{thinking_text}")
                def play_thinking():
                    try:
                        from modules.module_tts import play_audio_chunks
                        asyncio.run(play_audio_chunks(thinking_text, CONFIG['TTS']['ttsoption'], is_wakeword=True))
                    except Exception as e:
                        queue_message(f"ERROR: Failed to play thinking response: {e}")

                thinking_thread = threading.Thread(target=play_thinking, daemon=True)
                thinking_thread.start()
                import time
                time.sleep(0.1)
    except Exception as e:
        pass

    prompt = build_prompt(user_prompt, character_manager, memory_manager, CONFIG, debug=False)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, prompt)

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        bot_reply = _extract_text(response.json(), istext)

        finalReply = llm_process(user_prompt, bot_reply)
        return finalReply

    except requests.RequestException as e:
        queue_message(f"ERROR: LLM request failed: {e}")
        return None

def _prepare_request_data(llm_backend, prompt):

    if llm_backend == "openai":
        url = f"{CONFIG['LLM']['base_url']}/v1/chat/completions"
        data = {
            "model": CONFIG['LLM']['openai_model'],
            "messages": [
                {"role": "system", "content": CONFIG['LLM']['systemprompt']},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p'],
            "response_format": {"type": "json_object"}
        }
    elif llm_backend == "deepinfra":
        url = f"{CONFIG['LLM']['base_url']}/v1/openai/chat/completions"
        data = {
            "model": CONFIG['LLM']['openai_model'],
            "messages": [
                {"role": "system", "content": CONFIG['LLM']['systemprompt']},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p'],
            "response_format": {"type": "json_object"}
        }
    elif llm_backend in ["ooba", "tabby"]:
        url = f"{CONFIG['LLM']['base_url']}/v1/completions"
        data = {
            "prompt": prompt,
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p']
        }
        if llm_backend == "ooba":
            data["seed"] = CONFIG['LLM']['seed']
    else:
        raise ValueError(f"Unsupported LLM backend: {llm_backend}")

    return url, data

def _extract_text(response_json, istext):
    try:
        llm_backend = CONFIG['LLM']['llm_backend']
        if 'choices' in response_json:
            return (
                response_json['choices'][0]['message']['content']
                if llm_backend in ["openai", "deepinfra"]
                else response_json['choices'][0]['text']
            ).strip()
        else:
            raise KeyError("Invalid response format: 'choices' key not found.")
    except (KeyError, IndexError, TypeError) as error:
        return f"Text extraction failed: {str(error)}"

def process_completion(prompt):
    future = executor.submit(get_completion, prompt, istext=True)
    return future.result()

def detect_emotion(text):
    model_outputs = classifier(text)
    emotindetected = max(model_outputs[0], key=lambda x: x['score'])['label']
    requests.post("http://127.0.0.1:5012/emotion", data=emotindetected, timeout=10)
    return

def llm_process(user_input, bot_response):
    global memory_manager
    if isinstance(bot_response, str):
        try:

            bot_response = bot_response.strip()

            bot_response = re.sub(r'^```json\s*', '', bot_response)
            bot_response = re.sub(r'^```\s*', '', bot_response)
            bot_response = re.sub(r'\s*```$', '', bot_response)

            bot_response = re.sub(r'`+$', '', bot_response)
            bot_response = bot_response.strip()

            bot_response = bot_response.replace("True", "true").replace("False", "false")

            json_match = re.search(r'\{.*\}', bot_response, re.DOTALL)
            if json_match:
                bot_response = json_match.group(0)

            while bot_response.endswith('}}') and bot_response.count('{') < bot_response.count('}'):
                bot_response = bot_response[:-1]

            bot_response = json.loads(bot_response)

        except json.JSONDecodeError as e:
            queue_message(f"ERROR: JSON parsing failed: {e}")
            queue_message(f"Raw response: {bot_response}")
            return "[Error: Invalid JSON from LLM. Check logs for details.]"

    if isinstance(bot_response, dict) and len(bot_response.keys()) == 1:
        sole_value = list(bot_response.values())[0]
        if isinstance(sole_value, str) and sole_value.strip().startswith("{"):
            try:
                bot_response = json.loads(sole_value)
            except json.JSONDecodeError:
                pass

    def normalize_field(value):
        if isinstance(value, list) and value:
            return str(value[0])
        elif isinstance(value, str):
            return value
        else:
            return ""

    bot_response["question"] = normalize_field(bot_response.get("question", ""))
    bot_response["reply"] = normalize_field(bot_response.get("reply", ""))
    bot_response["function_calls"] = bot_response.get("function_calls", [])

    print(f"TARS: {bot_response}")

    if bot_response["function_calls"]:
        for func_call in bot_response["function_calls"]:
            execute_function_call(func_call, bot_response, user_input)

    if memory_manager:
        threading.Thread(
            target=memory_manager.write_longterm_memory,
            args=(user_input, bot_response["reply"])
        ).start()

    if CONFIG["EMOTION"]["enabled"]:
        threading.Thread(
            target=detect_emotion,
            args=(bot_response["reply"],)
        ).start()

    return bot_response["reply"]

def execute_function_call(func_call, bot_response, user_input):
    function_name = func_call.get("function", "")
    parameters = func_call.get("parameters", {})

    try:
        if function_name == "execute_movement":
            movements = parameters.get("movements", [])
            if movements:
                execute_movement(movements)

        elif function_name == "capture_camera_view":
            query = parameters.get("query", bot_response.get("question", ""))
            description = describe_camera_view_openai(query)
            if description and not description.startswith("Error:"):
                bot_response["reply"] = description
            else:
                bot_response["reply"] = "I tried to look but couldn't process the image."

        elif function_name == "web_search":
            from modules.module_websearch import search_google
            query = parameters.get("query", "")
            if query:
                queue_message(f"Web search: {query}")
                search_results = search_google(query)
                if search_results:
                    bot_response["reply"] = f"Based on my search: {search_results[:500]}"
                else:
                    bot_response["reply"] = "I couldn't find relevant information for that query."

        elif function_name == "adjust_volume":
            from modules.module_volume import get_volume_control
            vc = get_volume_control()

            action = parameters.get("action", "set")
            value = parameters.get("value", 0)

            current = vc.get_volume()

            if action == "set":
                if vc.set_volume(value):
                    bot_response["reply"] = f"Volume set to {value}%."
                else:
                    bot_response["reply"] = "Failed to set volume."
            elif action == "increase":
                if vc.adjust_volume(value):
                    new_vol = vc.get_volume()
                    bot_response["reply"] = f"Volume increased by {value}%. Now at {new_vol}%."
                else:
                    bot_response["reply"] = "Failed to increase volume."
            elif action == "decrease":
                if vc.adjust_volume(-value):
                    new_vol = vc.get_volume()
                    bot_response["reply"] = f"Volume decreased by {value}%. Now at {new_vol}%."
                else:
                    bot_response["reply"] = "Failed to decrease volume."

        elif function_name == "get_volume":
            from modules.module_volume import get_volume_control
            vc = get_volume_control()
            current = vc.get_volume()
            if current is not None:
                bot_response["reply"] = f"Current volume is {current}%."
            else:
                bot_response["reply"] = "Unable to check volume level."

        elif function_name == "adjust_persona":
            from modules.module_config import update_character_setting
            trait = parameters.get("trait", "")
            value = parameters.get("value", 0)
            if trait and isinstance(value, (int, float)):
                update_character_setting(trait, int(value))
                bot_response["reply"] = f"Updated {trait} setting to {int(value)}%"
                queue_message(f"Persona adjusted: {trait} = {value}")
            else:
                bot_response["reply"] = "Could not parse persona adjustment."

        elif function_name == "open_url":
            url = parameters.get("url", "")
            description = parameters.get("description", "")
            if url:
                from modules.module_browser import get_browser_player

                def close_ui_and_pause_stt():
                    try:
                        from modules.module_stt import get_stt_manager
                        stt = get_stt_manager()
                        if stt:
                            stt.pause()
                            queue_message("STT paused during browser session")
                    except Exception as e:
                        queue_message(f"Could not pause STT: {e}")

                    try:
                        from modules.module_main import ui_manager
                        if ui_manager and ui_manager.running:
                            queue_message("Closing UI for browser...")
                            ui_manager.running = False
                            ui_manager.join(timeout=5)
                            queue_message("UI closed")
                    except Exception as e:
                        queue_message(f"Could not close UI: {e}")

                def reopen_ui_and_resume_stt():
                    try:
                        from modules.module_main import ui_manager, shutdown_event, battery_module, stt_manager
                        import modules.module_main as main_module
                        from modules.module_ui import UIManager

                        if ui_manager and not ui_manager.running:
                            queue_message("Reopening UI...")

                            if shutdown_event is None or battery_module is None:
                                queue_message("ERROR: Missing shutdown_event or battery_module - cannot reopen UI")
                                return

                            new_ui_manager = UIManager(shutdown_event=shutdown_event, battery_module=battery_module)
                            new_ui_manager.start()
                            main_module.ui_manager = new_ui_manager

                            if stt_manager:
                                stt_manager.ui_manager = new_ui_manager

                            from modules.module_main import memory_manager
                            if memory_manager:
                                memory_manager.ui_manager = new_ui_manager

                            queue_message("UI reopened")
                    except Exception as e:
                        queue_message(f"Could not reopen UI: {e}")
                        import traceback
                        traceback.print_exc()

                    try:
                        from modules.module_stt import get_stt_manager
                        stt = get_stt_manager()
                        if stt:
                            stt.resume()
                            queue_message("STT resumed")
                    except Exception as e:
                        queue_message(f"Could not resume STT: {e}")

                player = get_browser_player()
                player.set_callbacks(on_start=close_ui_and_pause_stt, on_end=reopen_ui_and_resume_stt)

                queue_message(f"Opening URL: {url}")
                success = player.play_video(url)  

                if success:
                    bot_response["reply"] = f"Opening {description if description else url}"
                else:
                    bot_response["reply"] = "Failed to open the website"

        elif function_name == "play_youtube":
            from modules.module_browser import search_and_play
            query = parameters.get("query", "")

            if query:

                def close_ui_and_pause_stt():
                    try:

                        from modules.module_stt import get_stt_manager
                        stt = get_stt_manager()
                        if stt:
                            stt.pause()
                            queue_message("STT paused during video playback")
                    except Exception as e:
                        queue_message(f"Could not pause STT: {e}")

                    try:

                        from modules.module_main import ui_manager
                        if ui_manager and ui_manager.running:
                            queue_message("Closing UI for browser playback...")
                            ui_manager.running = False
                            ui_manager.join(timeout=5)  

                            queue_message("UI closed")
                    except Exception as e:
                        queue_message(f"Could not close UI: {e}")

                def reopen_ui_and_resume_stt():
                    try:

                        from modules.module_main import ui_manager, shutdown_event, battery_module, stt_manager
                        import modules.module_main as main_module
                        from modules.module_ui import UIManager

                        if ui_manager and not ui_manager.running:
                            queue_message("Reopening UI...")

                            if shutdown_event is None or battery_module is None:
                                queue_message("ERROR: Missing shutdown_event or battery_module - cannot reopen UI")
                                return

                            new_ui_manager = UIManager(shutdown_event=shutdown_event, battery_module=battery_module)
                            new_ui_manager.start()

                            main_module.ui_manager = new_ui_manager

                            if stt_manager:
                                stt_manager.ui_manager = new_ui_manager

                            from modules.module_main import memory_manager
                            if memory_manager:
                                memory_manager.ui_manager = new_ui_manager

                            queue_message("UI reopened")
                    except Exception as e:
                        queue_message(f"Could not reopen UI: {e}")
                        import traceback
                        traceback.print_exc()

                    try:

                        from modules.module_stt import get_stt_manager
                        stt = get_stt_manager()
                        if stt:
                            stt.resume()
                            queue_message("STT resumed")
                    except Exception as e:
                        queue_message(f"Could not resume STT: {e}")

                result = search_and_play(query, on_start=close_ui_and_pause_stt, on_end=reopen_ui_and_resume_stt)
                if result['success']:
                    video_info = result.get('video', {})
                    bot_response["reply"] = f"{result['message']} by {video_info.get('channel', 'Unknown')}."
                else:
                    bot_response["reply"] = result['message']
            else:
                bot_response["reply"] = "Please specify what video you'd like to watch."

        else:
            queue_message(f"Unknown function: {function_name}")

    except Exception as e:
        queue_message(f"Function execution failed for {function_name}: {e}")

def raw_complete_llm(user_prompt, istext=True):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, user_prompt)

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        bot_reply = _extract_text(response.json(), istext)
        return bot_reply

    except requests.RequestException as e:
        queue_message(f"ERROR: LLM request failed: {e}")
        return None

def initialize_manager_llm(mem_manager, char_manager):
    global memory_manager, character_manager
    memory_manager = mem_manager
    character_manager = char_manager