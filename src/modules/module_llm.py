"""
Module: LLM
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import requests
import threading
import json
import re
import time
import concurrent.futures
import random
import asyncio
from modules.module_config import load_config, get_capabilities
from modules.module_prompt import build_prompt
from modules.module_engine  import execute_movement

from modules.module_messageQue import queue_message

CONFIG = load_config()
CAPABILITIES = get_capabilities()
character_manager = None
memory_manager = None

process_camera_image = None
try:
    from modules.module_vision import process_camera_image as _pci
    process_camera_image = _pci
except ImportError:
    pass

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

classifier = None
if CONFIG['EMOTION']['enabled']:
    try:
        from transformers import pipeline
        classifier = pipeline("text-classification", model="SamLowe/roberta-base-go_emotions", top_k=None)
    except ImportError:
        pass

def get_completion(user_prompt, istext=True, image_b64=None, source="voice"):

    if memory_manager is None or character_manager is None:
        raise ValueError("MemoryManager and CharacterManager must be initialized before generating completions.")

    try:
        enable_thinking = CONFIG["CHAR"].get('enable_thinking_responses', True)
        if isinstance(enable_thinking, str):
            enable_thinking = enable_thinking.lower() in ('true', '1', 'yes')

        thinking_responses_raw = CONFIG["CHAR"].get('thinking_responses', '[]')
        try:
            thinking_responses = json.loads(thinking_responses_raw)
        except (json.JSONDecodeError, TypeError):
            thinking_responses = []
        if not isinstance(thinking_responses, list):
            thinking_responses = []

        if enable_thinking and thinking_responses and len(thinking_responses) > 0:
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
                time.sleep(0.1)
    except Exception as e:
        pass

    prompt = build_prompt(user_prompt, character_manager, memory_manager, CONFIG, debug=False)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, prompt, image_b64=image_b64)

    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()

        # Stream tokens from SSE response
        full_content = ""
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8')
                if not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    token = chunk['choices'][0]['delta'].get('content', '')
                    full_content += token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except Exception:
            pass

        # Fallback: if streaming yielded nothing, try non-streaming parse
        if not full_content.strip():
            try:
                bot_reply = _extract_text(response.json(), istext)
            except Exception:
                queue_message("ERROR: LLM returned empty response")
                return None
        else:
            bot_reply = full_content.strip()

        finalReply = llm_process(user_prompt, bot_reply, source=source, has_image=image_b64 is not None)
        return finalReply

    except requests.RequestException as e:
        queue_message(f"ERROR: LLM request failed: {e}")
        return None

def _prepare_request_data(llm_backend, prompt, image_b64=None):

    # Build user content — multimodal if image provided, plain text otherwise
    if image_b64:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
    else:
        user_content = prompt

    if llm_backend == "openai":
        url = f"{CONFIG['LLM']['base_url']}/v1/chat/completions"
        model = CONFIG['LLM']['openai_model']
    elif llm_backend == "grok":
        url = f"{CONFIG['LLM']['base_url']}/v1/chat/completions"
        model = CONFIG['LLM']['grok_model']
    elif llm_backend == "deepinfra":
        url = f"{CONFIG['LLM']['base_url']}/v1/openai/chat/completions"
        model = CONFIG['LLM']['openai_model']
    else:
        url = f"{CONFIG['LLM']['base_url']}/v1/chat/completions"
        model = CONFIG['LLM']['other_model']

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": CONFIG['LLM']['systemprompt']},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": CONFIG['LLM']['max_tokens'],
        "temperature": CONFIG['LLM']['temperature'],
        "top_p": CONFIG['LLM']['top_p'],
        "response_format": {"type": "json_object"},
        "stream": True
    }

    return url, data

def _extract_text(response_json, istext):
    try:
        llm_backend = CONFIG['LLM']['llm_backend']
        if 'choices' in response_json:
            return (
                response_json['choices'][0]['message']['content']
                if llm_backend in ["openai", "grok", "deepinfra", "other"]
                else response_json['choices'][0]['text']
            ).strip()
        else:
            raise KeyError("Invalid response format: 'choices' key not found.")
    except (KeyError, IndexError, TypeError) as error:
        return f"Text extraction failed: {str(error)}"

def process_completion(prompt):
    """Run LLM completion and return parsed dict with reply + side effects deferred.

    Returns a dict with 'reply', 'function_calls', 'new_memories' fields,
    or a plain string on error.
    """
    def _get_parsed(prompt):
        # Duplicate the get_completion flow but return parsed dict
        if memory_manager is None or character_manager is None:
            raise ValueError("Managers must be initialized")

        try:
            enable_thinking = CONFIG["CHAR"].get('enable_thinking_responses', True)
            if isinstance(enable_thinking, str):
                enable_thinking = enable_thinking.lower() in ('true', '1', 'yes')

            thinking_responses_raw = CONFIG["CHAR"].get('thinking_responses', '[]')
            try:
                thinking_responses = json.loads(thinking_responses_raw)
            except (json.JSONDecodeError, TypeError):
                thinking_responses = []
            if not isinstance(thinking_responses, list):
                thinking_responses = []

            if enable_thinking and thinking_responses and len(thinking_responses) > 0:
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
                    time.sleep(0.1)
        except Exception:
            pass

        import modules.module_speed as speed
        _t0 = time.perf_counter()
        built_prompt = build_prompt(prompt, character_manager, memory_manager, CONFIG, debug=False)
        _t_prompt = time.perf_counter()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
        }
        llm_backend = CONFIG['LLM']['llm_backend']
        url, data = _prepare_request_data(llm_backend, built_prompt)

        response = requests.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()
        _t_first_byte = time.perf_counter()

        full_content = ""
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8')
                if not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    token = chunk['choices'][0]['delta'].get('content', '')
                    full_content += token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except Exception:
            pass
        _t_llm_done = time.perf_counter()

        if not full_content.strip():
            try:
                bot_reply = _extract_text(response.json(), True)
            except Exception:
                return None
        else:
            bot_reply = full_content.strip()

        result = llm_parse_response(bot_reply)
        _t_parse = time.perf_counter()

        if isinstance(result, dict) and speed.enabled:
            # Pull sub-timings from prompt builder
            try:
                from modules.module_prompt import _last_prompt_timings
                pt = _last_prompt_timings
            except Exception:
                pt = {}
            result['_timings'] = {
                'prompt_build': _t_prompt - _t0,
                'prompt_identity': pt.get('identity', 0),
                'prompt_memory': pt.get('memory', 0),
                'llm_first_byte': _t_first_byte - _t_prompt,
                'llm_stream': _t_llm_done - _t_first_byte,
                'parse': _t_parse - _t_llm_done,
            }
        return result

    future = executor.submit(_get_parsed, prompt)
    return future.result()

def detect_emotion(text):
    if classifier is None:
        return None
    model_outputs = classifier(text)
    emotion_detected = max(model_outputs[0], key=lambda x: x['score'])['label']
    return emotion_detected
    
def _repair_truncated_json(s):
    """Repair truncated JSON by closing unclosed strings, brackets, and braces."""
    in_string = False
    escape_next = False
    stack = []

    for char in s:
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in '{[':
            stack.append('}' if char == '{' else ']')
        elif char in '}]' and stack and stack[-1] == char:
            stack.pop()

    if in_string:
        s += '"'
    while stack:
        s += stack.pop()
    return s

def llm_parse_response(bot_response):
    """Parse raw LLM JSON string into structured dict. No side effects."""
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

            try:
                bot_response = json.loads(bot_response)
            except json.JSONDecodeError:
                bot_response = _repair_truncated_json(bot_response)
                bot_response = json.loads(bot_response)

        except json.JSONDecodeError as e:
            queue_message(f"ERROR: JSON parsing failed: {e}")
            queue_message(f"Raw response: {bot_response}")
            return None

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
    bot_response["new_memories"] = bot_response.get("new_memories", [])

    return bot_response


def llm_execute_side_effects(parsed, user_input, source="voice", has_image=False):
    """Execute function_calls and save memories. Safe to run in a background thread.

    source: 'voice' or 'webui' — controls where generated images are displayed.
    has_image: True when the user already provided an image (skip camera capture).
    """
    global memory_manager
    try:
        if parsed.get("function_calls"):
            for func_call in parsed["function_calls"]:
                execute_function_call(func_call, parsed, user_input, source=source, has_image=has_image)

        if memory_manager:
            threading.Thread(
                target=memory_manager.write_longterm_memory,
                args=(user_input, parsed["reply"])
            ).start()

            new_memories = parsed.get("new_memories", [])
            if isinstance(new_memories, list) and len(new_memories) > 0:
                def save_memories():
                    try:
                        import json
                        memory_manager.update_topic_index_with_ai_response(json.dumps(new_memories))
                    except Exception as e:
                        queue_message(f"MEMORY: Failed to save: {e}")

                threading.Thread(target=save_memories).start()
    except Exception as e:
        queue_message(f"ERROR: Side effects execution failed: {e}")


def llm_process(user_input, bot_response, source="voice", has_image=False):
    """Parse LLM response and execute side effects (legacy wrapper)."""
    parsed = llm_parse_response(bot_response)
    if parsed is None:
        return "[Error: Invalid JSON from LLM. Check logs for details.]"
    llm_execute_side_effects(parsed, user_input, source=source, has_image=has_image)
    return _sanitize_for_tts(parsed["reply"])


def _sanitize_for_tts(text):
    if not isinstance(text, str):
        return text

    text = text.replace(' — ', '... ')
    text = text.replace('— ', '... ')
    text = text.replace(' —', ' ...')
    text = text.replace('—', '... ')

    text = text.replace(' – ', '... ')
    text = text.replace('– ', '... ')
    text = text.replace(' –', ' ...')
    text = text.replace('–', '... ')

    text = re.sub(r'(?<=[a-zA-Z]) - (?=[a-zA-Z])', '... ', text)

    text = text.replace('°C', ' degrees')
    text = text.replace('°F', ' degrees')
    text = text.replace('°', ' degrees')
    text = text.replace('km/h', ' kilometers per hour')
    text = re.sub(r'\bmph\b', 'miles per hour', text)
    text = text.replace(' & ', ' and ')
    text = text.replace('e.g.', 'for example')
    text = text.replace('i.e.', 'that is')
    text = text.replace('etc.', 'and so on')
    text = text.replace('w/', 'with ')
    text = text.replace('b/c', 'because')

    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)

    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()

def _summarize_search_results(search_results, user_question):
    try:
        char_name = character_manager.char_name if character_manager else "TARS"

        summary_prompt = (
            f"You are {char_name}. The user asked: \"{user_question}\"\n\n"
            f"Here are web search results:\n{search_results[:800]}\n\n"
            f"Give a helpful, natural answer based on these results. "
            f"Be concise (2-4 sentences). Just the answer, no JSON, no markdown."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
        }

        llm_backend = CONFIG['LLM']['llm_backend']

        if llm_backend in ["openai", "grok", "deepinfra", "other"]:
            if llm_backend == 'grok':
                model_key = 'grok_model'
            elif llm_backend == 'deepinfra':
                model_key = 'deepinfra'
            elif llm_backend == 'other':
                model_key = 'other_model'
            else:
                model_key = 'openai_model'
            base_url = CONFIG['LLM']['base_url']

            if llm_backend == "deepinfra":
                url = f"{base_url}/v1/openai/chat/completions"
            else:
                url = f"{base_url}/v1/chat/completions"

            data = {
                "model": CONFIG['LLM'][model_key],
                "messages": [
                    {"role": "user", "content": summary_prompt}
                ],
                "max_tokens": 250,
                "temperature": float(CONFIG['LLM'].get('temperature', 0.7))
            }

        else:
            return None

        response = requests.post(url, headers=headers, json=data, timeout=20)
        response.raise_for_status()

        result = response.json()
        if 'choices' in result:
            if llm_backend in ["openai", "grok", "deepinfra"]:
                text = result['choices'][0]['message']['content'].strip()
            else:
                text = result['choices'][0]['text'].strip()

            if text.startswith('{') and text.endswith('}'):
                try:
                    parsed = json.loads(text)
                    text = parsed.get('reply', parsed.get('response', text))
                except json.JSONDecodeError:
                    pass

            if text and len(text) > 10:
                return text

        return None

    except Exception as e:
        queue_message(f"WARN: Search summarization failed: {e}")
        return None


_vision_in_progress = threading.local()

def execute_function_call(func_call, bot_response, user_input, source="voice", has_image=False):
    function_name = func_call.get("function", "")
    parameters = func_call.get("parameters", {})
    import modules.module_speed as speed
    speed.start('tool')

    try:
        if function_name == "execute_movement" and CONFIG["CONTROLS"]["voicemovement"]:
            movements = parameters.get("movements", [])
            if movements:
                execute_movement(movements)

        elif function_name == "capture_camera_view":
            # Skip camera capture when user already provided an image
            if has_image:
                queue_message("INFO: Skipping camera capture — user already provided an image")
            elif getattr(_vision_in_progress, 'active', False):
                queue_message("WARN: Skipping recursive capture_camera_view call")
            elif process_camera_image is None:
                bot_response["reply"] = "Vision is not available on this device."
            else:
                _vision_in_progress.active = True
                try:
                    query = parameters.get("query", bot_response.get("question", ""))
                    vision_processor = CONFIG['VISION'].get('vision_processor', 'blip')

                    # Pull detection context from UI if available
                    detection_context = ""
                    try:
                        from modules.module_main import ui_manager
                        if ui_manager and hasattr(ui_manager, 'detection_manager'):
                            detection_context = ui_manager.detection_manager.get_detection_summary() or ""
                    except Exception:
                        pass

                    # Single-pass for multimodal backends — send image directly to LLM with personality
                    if vision_processor in ("llm", "openai"):
                        from modules.module_vision import capture_camera_base64
                        b64, capture_err = capture_camera_base64()
                        if capture_err:
                            bot_response["reply"] = capture_err
                        else:
                            try:
                                prompt = query or "Describe what you see."
                                if detection_context:
                                    prompt = f"{detection_context}\n\n{prompt}"
                                reply = get_completion(prompt, image_b64=b64)
                                bot_response["reply"] = reply if reply else "I tried to look but couldn't process the image."
                            except Exception as e:
                                queue_message(f"ERROR: Single-pass vision failed: {e}")
                                bot_response["reply"] = "I tried to look but encountered an error."
                    else:
                        # Two-pass for caption-only backends (blip, server_hosted)
                        description = process_camera_image(query, detection_context=detection_context or None)
                        if description and not description.startswith("Error:"):
                            vision_prompt = f"*You looked through your camera and saw: {description}*"
                            if detection_context:
                                vision_prompt += f" {detection_context}"
                            if query:
                                vision_prompt += f" The user asked: {query}"
                            try:
                                reply = get_completion(vision_prompt)
                                bot_response["reply"] = reply if reply else description
                            except Exception as e:
                                queue_message(f"WARN: Vision follow-up LLM call failed: {e}")
                                bot_response["reply"] = description
                        else:
                            bot_response["reply"] = "I tried to look but couldn't process the image."
                finally:
                    _vision_in_progress.active = False

        elif function_name == "web_search":
            from modules.module_websearch import search_google
            query = parameters.get("query", "")
            if query:
                queue_message(f"Web search: {query}")
                search_results = search_google(query)

                is_failure = (
                    not search_results
                    or "No results found" in search_results
                    or "No useful results" in search_results
                    or "Search failed" in search_results
                )

                existing_reply = bot_response.get("reply", "").strip().lower()
                placeholder_phrases = [
                    "let me search", "let me look", "let me check",
                    "searching", "looking that up", "checking",
                    "i'll find", "i'll search", "i'll look",
                    "one moment", "one sec", "hang on",
                ]
                has_real_reply = (
                    existing_reply
                    and len(existing_reply) > 15
                    and not any(p in existing_reply for p in placeholder_phrases)
                )

                if is_failure:
                    if not has_real_reply:
                        bot_response["reply"] = "I searched but couldn't find good results for that. Could you try rephrasing?"
                else:
                    if has_real_reply:
                        summary = _summarize_search_results(search_results, user_input)
                        if summary:
                            bot_response["reply"] = summary
                    else:
                        summary = _summarize_search_results(search_results, user_input)
                        if summary:
                            bot_response["reply"] = summary
                        else:
                            bot_response["reply"] = f"Here's what I found: {search_results[:500]}"

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
                        from modules.module_main import UIManager

                        if ui_manager and not ui_manager.running:
                            queue_message("Reopening UI...")

                            if shutdown_event is None:
                                queue_message("ERROR: Missing shutdown_event - cannot reopen UI")
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
                        from modules.module_main import UIManager

                        if ui_manager and not ui_manager.running:
                            queue_message("Reopening UI...")

                            if shutdown_event is None:
                                queue_message("ERROR: Missing shutdown_event - cannot reopen UI")
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

        elif function_name == "launch_retropie":
            import subprocess
            import os

            retropie_script = os.path.expanduser("~/TARS-AI/launch_retropie.sh")

            if not os.path.isfile(retropie_script) or not os.access(retropie_script, os.X_OK):
                bot_response["reply"] = "RetroPie doesn't seem to be installed. You can install it by running the installer again."
                return

            bot_response["reply"] = "Launching RetroPie. Have fun gaming!"

            def launch_after_tts():
                import time
                time.sleep(5)

                queue_message("Launching RetroPie script...")
                if os.path.isfile("/usr/bin/lxterminal"):
                    os.system(f"setsid lxterminal --title='RetroPie' -e {retropie_script} &")
                elif os.path.isfile("/usr/bin/xfce4-terminal"):
                    os.system(f"setsid xfce4-terminal --title='RetroPie' -e {retropie_script} &")
                else:
                    os.system(f"setsid x-terminal-emulator -e {retropie_script} &")

                try:
                    from modules.module_main import shutdown_event, stop_event
                    if stop_event:
                        stop_event.set()
                    if shutdown_event:
                        queue_message("Setting shutdown event for clean exit...")
                        shutdown_event.set()
                except Exception as e:
                    queue_message(f"Could not set shutdown event: {e}")

            threading.Thread(target=launch_after_tts, daemon=False).start()

        elif function_name == "system_control":
            action = parameters.get("action", "")
            if action == "exit":
                bot_response["reply"] = bot_response.get("reply", "Shutting down the program. See you later!")
                queue_message("[SYSTEM] Exit requested via voice command")

                def exit_after_tts():
                    import time
                    time.sleep(5)
                    try:
                        from modules.module_main import ui_manager
                        if ui_manager and hasattr(ui_manager, 'exit_program'):
                            ui_manager.exit_program()
                        else:
                            from modules.module_main import shutdown_event
                            if shutdown_event:
                                shutdown_event.set()
                            import sys
                            sys.exit(0)
                    except Exception as e:
                        queue_message(f"Exit failed: {e}")
                        import sys
                        sys.exit(0)

                threading.Thread(target=exit_after_tts, daemon=False).start()

            elif action == "shutdown":
                bot_response["reply"] = bot_response.get("reply", "Powering off now. Goodbye!")
                queue_message("[SYSTEM] Shutdown requested via voice command")

                def shutdown_after_tts():
                    import time
                    time.sleep(5)
                    try:
                        from modules.module_main import ui_manager
                        if ui_manager and hasattr(ui_manager, 'initiate_shutdown'):
                            ui_manager.initiate_shutdown()
                        else:
                            import subprocess
                            subprocess.Popen(['sudo', 'shutdown', 'now'])
                            import sys
                            sys.exit(0)
                    except Exception as e:
                        queue_message(f"Shutdown failed: {e}")
                        import subprocess
                        subprocess.Popen(['sudo', 'shutdown', 'now'])
                        import sys
                        sys.exit(0)

                threading.Thread(target=shutdown_after_tts, daemon=False).start()

            else:
                bot_response["reply"] = "I didn't understand that system command."

        elif function_name == "generate_image":
            from modules.module_stablediffusion import generate_image
            prompt = parameters.get("prompt", "")
            if not prompt:
                bot_response["reply"] = "No image description provided."
            else:
                queue_message(f"Generating image: {prompt}")
                # Always override — small LLMs tend to apologize even when calling the function
                bot_response["reply"] = "On it — generating your image now."

                _callback = None
                if source == "webui":
                    def _on_image_ready(image_bytes):
                        try:
                            queue_message(f"[SD] Image ready ({len(image_bytes)} bytes) — emitting to WebUI")
                            import base64 as _b64
                            b64 = _b64.b64encode(image_bytes).decode('utf-8')
                            img_html = f'<img style="max-width:100%;border-radius:8px;" src="data:image/png;base64,{b64}">'
                            from modules.module_chatui import socketio
                            socketio.emit('bot_message', {'message': img_html})
                            queue_message("[SD] WebUI image emit sent")
                        except Exception as _e:
                            queue_message(f"[SD] WebUI image emit failed: {_e}")
                    _callback = _on_image_ready

                def _generate_bg():
                    queue_message("[SD] Background generation thread started")
                    try:
                        result = generate_image(prompt, on_image_ready=_callback)
                        queue_message(f"[SD] Background generation done: {result}")
                    except Exception as _e:
                        queue_message(f"[SD] Background image generation failed: {_e}")

                if source == "webui":
                    # Use socketio background task so emit reaches eventlet-managed clients
                    try:
                        from modules.module_chatui import socketio as _sio
                        _sio.start_background_task(_generate_bg)
                    except Exception:
                        threading.Thread(target=_generate_bg, daemon=True).start()
                else:
                    threading.Thread(target=_generate_bg, daemon=True).start()
                queue_message("[SD] Started image generation thread")

        elif function_name == "home_assistant":
            from modules.module_homeassistant import send_prompt_to_homeassistant
            prompt = parameters.get("prompt", user_input)
            if prompt:
                queue_message(f"Home Assistant: {prompt}")
                ha_response = send_prompt_to_homeassistant(prompt)
                if isinstance(ha_response, dict) and "error" in ha_response:
                    bot_response["reply"] = f"Home Assistant error: {ha_response['error']}"
                elif ha_response:
                    # The response from process conversation usually has a 'response' or similar field
                    # depending on the HA version. We'll try to extract the speech part if possible.
                    speech = ""
                    try:
                        speech = ha_response.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
                    except Exception:
                        pass
                    
                    if speech:
                        if ha_response.get("response", {}).get("response_type") == "error":
                            bot_response["reply"] = f"Home Assistant reported: {speech}"
                        else:
                            bot_response["reply"] = speech
                    else:
                        bot_response["reply"] = "Action completed via Home Assistant."
                else:
                    bot_response["reply"] = "I couldn't get a response from Home Assistant."

        elif function_name == "identify_speaker_name":
            from modules.module_speaker_id import get_speaker_id_manager
            name = parameters.get("name", "").strip()
            if name:
                sid = get_speaker_id_manager()
                if sid is not None:
                    # Rename the enrolled "Unknown" voice profile
                    sid.rename_speaker("Unknown", name)
                    # Also rename any Unknown_<timestamp> session tags in memories
                    with sid._lock:
                        old_session = sid._unknown_session_id
                        sid._unknown_session_id = None
                        sid._pending_name_request = False
                    if old_session:
                        sid._rename_speaker_in_memories(old_session, name)
                    queue_message(f"INFO: Speaker identified as '{name}' via LLM")
                    # Auto-train face if unknown face is on camera
                    try:
                        from modules.module_identity import get_identity_manager
                        im = get_identity_manager()
                        if im is not None:
                            im.auto_train_face(name)
                    except Exception:
                        pass
                else:
                    queue_message("WARNING: Speaker ID manager not available")
            else:
                queue_message("WARNING: identify_speaker_name called without a name")

        else:
            queue_message(f"Unknown function: {function_name}")

    except Exception as e:
        queue_message(f"Function execution failed for {function_name}: {e}")

    speed.log_tool(function_name, speed.stop('tool'))

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