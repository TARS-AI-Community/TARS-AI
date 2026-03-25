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
import os
import requests
import threading
import json
import re
import time
import random
import asyncio
from modules.module_config import load_config, get_capabilities
from modules.module_prompt import build_prompt
from modules.module_messageQue import queue_message

CONFIG = load_config()
CAPABILITIES = get_capabilities()
character_manager = None
memory_manager = None

# Persistent HTTP session — reuses TCP+TLS connections across LLM requests,
# saving ~100-200ms per call (especially on Pi where TLS handshake is slow).
_http_session = requests.Session()

process_camera_image = None
if CAPABILITIES is None or CAPABILITIES.can_use_vision:
    try:
        from modules.module_vision import process_camera_image as _pci
        process_camera_image = _pci
    except ImportError:
        pass


# Callback invoked with (text_chunk, is_first) as reply text streams from LLM.
# Set by module_main.py before calling process_completion(); cleared afterward.
_reply_chunk_callback = None

# Speaker ID start timestamp — set by module_main.py so the deferred wait
# in build_prompt can block for the remaining budget before resolving the name.
_sid_start_time = None


class _ReplyExtractor:
    """State machine that extracts the 'reply' field value from streaming LLM JSON.

    As tokens arrive one by one, feeds them in and returns the visible reply
    text extracted so far. Handles JSON escape sequences correctly.
    """
    _REPLY_RE = re.compile(r'"reply"\s*:\s*"')

    def __init__(self):
        self._state = 0   # 0=searching for "reply":", 1=inside value, 2=done
        self._buf = ''
        self._escape = False
        self._had_any = False

    def feed(self, token):
        """Return (visible_text, is_first_token) extracted from this token."""
        if self._state == 2:
            return '', False
        self._buf += token
        extracted = ''

        if self._state == 0:
            m = self._REPLY_RE.search(self._buf)
            if m:
                self._state = 1
                self._buf = self._buf[m.end():]

        if self._state == 1:
            new_chars = []
            i = 0
            while i < len(self._buf):
                c = self._buf[i]
                if self._escape:
                    if c == 'n':
                        new_chars.append('\n')
                    elif c == 't':
                        new_chars.append('\t')
                    else:
                        new_chars.append(c)
                    self._escape = False
                elif c == '\\':
                    self._escape = True
                elif c == '"':
                    self._state = 2
                    self._buf = self._buf[i + 1:]
                    break
                else:
                    new_chars.append(c)
                i += 1
            if self._state == 1:
                self._buf = ''
            extracted = ''.join(new_chars)

        if extracted:
            is_first = not self._had_any
            self._had_any = True
            return extracted, is_first
        return '', False


classifier = None
_emotion_method = CONFIG['EMOTION'].get('emotion_method', 'classifier')
if CONFIG['EMOTION']['enabled'] and _emotion_method == 'classifier':
    try:
        _emotion_model = CONFIG['EMOTION'].get('emotion_model', 'SamLowe/roberta-base-go_emotions')
        if _emotion_model.endswith('-onnx'):
            from optimum.onnxruntime import ORTModelForSequenceClassification
            from transformers import pipeline, AutoTokenizer
            _ort_model = ORTModelForSequenceClassification.from_pretrained(_emotion_model)
            _tokenizer = AutoTokenizer.from_pretrained(_emotion_model)
            classifier = pipeline("text-classification", model=_ort_model, tokenizer=_tokenizer, top_k=None)
        else:
            from transformers import pipeline
            classifier = pipeline("text-classification", model=_emotion_model, top_k=None)
    except Exception:
        pass


def _maybe_play_thinking_response():
    """Play a random thinking-response audio clip in a background thread (fire-and-forget)."""
    try:
        enable_thinking = CONFIG["CHAR"].get('enable_thinking_responses', True)
        if isinstance(enable_thinking, str):
            enable_thinking = enable_thinking.lower() in ('true', '1', 'yes')
        if not enable_thinking:
            return

        thinking_responses_raw = CONFIG["CHAR"].get('thinking_responses', '[]')
        try:
            thinking_responses = json.loads(thinking_responses_raw)
        except (json.JSONDecodeError, TypeError):
            thinking_responses = []
        if not isinstance(thinking_responses, list):
            thinking_responses = []

        if not thinking_responses:
            return

        thinking_text = random.choice(thinking_responses)
        if not (thinking_text and isinstance(thinking_text, str) and thinking_text.strip()):
            return

        from modules.module_router import send as router_send
        router_send(thinking_text, thinking=True)
    except Exception:
        pass


def get_completion(user_prompt, istext=True, image_b64=None, source="voice"):

    if memory_manager is None or character_manager is None:
        raise ValueError("MemoryManager and CharacterManager must be initialized before generating completions.")

    _maybe_play_thinking_response()

    prompt = build_prompt(user_prompt, character_manager, memory_manager, CONFIG, debug=False)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, prompt, image_b64=image_b64)

    try:
        response = _http_session.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()

        # Stream tokens from SSE response
        _content_parts = []
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
                    if token:
                        _content_parts.append(token)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except Exception:
            pass
        full_content = ''.join(_content_parts)

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
        "stream": True
    }

    if llm_backend in ["openai", "grok", "deepinfra"]:
        data["response_format"] = {"type": "json_object"}
    else:
        if CONFIG['LLM'].get('json_mode', True):
            data["response_format"] = {"type": "json_object"}  

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

def process_completion(prompt, image_b64=None):
    """Run LLM completion and return parsed dict with reply + side effects deferred.

    Returns a dict with 'reply', 'function_calls', 'new_memories' fields,
    or a plain string on error.
    """
    def _get_parsed(prompt):
        if memory_manager is None or character_manager is None:
            raise ValueError("Managers must be initialized")

        _maybe_play_thinking_response()

        import modules.module_speed as speed
        _t0 = time.perf_counter()
        built_prompt = build_prompt(prompt, character_manager, memory_manager, CONFIG, debug=False)
        _t_prompt = time.perf_counter()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
        }
        llm_backend = CONFIG['LLM']['llm_backend']
        url, data = _prepare_request_data(llm_backend, built_prompt, image_b64=image_b64)

        response = _http_session.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()
        _t_first_byte = None

        _content_parts = []
        _token_count = 0
        _extractor = _ReplyExtractor()
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
                    if not token:
                        continue
                    if _t_first_byte is None:
                        _t_first_byte = time.perf_counter()
                    _content_parts.append(token)
                    _token_count += 1
                    # Extract visible reply text and invoke callback if set
                    cb = _reply_chunk_callback
                    if cb is not None:
                        visible, is_first = _extractor.feed(token)
                        if visible:
                            if is_first:
                                speed.mark_first_token()
                            try:
                                cb(visible, is_first)
                            except Exception:
                                pass
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except Exception:
            pass
        full_content = ''.join(_content_parts)
        _t_llm_done = time.perf_counter()
        if _t_first_byte is None:
            _t_first_byte = _t_prompt  # no tokens received

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
                'token_count': _token_count,
            }
        return result

    return _get_parsed(prompt)

_emotion_cache = {}
_EMOTION_CACHE_MAX = 128

def detect_emotion(text):
    """Detect emotion and return (top_axis, raw_label, axis_scores_dict).

    Sums all 28 GoEmotions scores into 8 radar axes, then returns
    the dominant axis name, the top raw GoEmotions label, and the
    full {axis: score} dict.
    """
    if classifier is None or not text or not text.strip():
        return None, None, {}
    # Check cache to avoid redundant inference
    cache_key = text.strip().lower()[:200]
    if cache_key in _emotion_cache:
        return _emotion_cache[cache_key]
    try:
        from modules.module_dashboard_data import _EMOTION_TO_AXIS, _RADAR_AXES
        model_outputs = classifier(text)
        if not model_outputs or not model_outputs[0]:
            return None, None, {}
        raw_scores = model_outputs[0]
        # Sum raw scores into grouped radar axes
        axis_scores = {a: 0.0 for a in _RADAR_AXES}
        for s in raw_scores:
            axis = _EMOTION_TO_AXIS.get(s['label'], s['label'])
            if axis in axis_scores:
                axis_scores[axis] += s['score']
        # Pick dominant axis — prefer non-neutral unless nothing else is meaningful
        non_neutral = {k: v for k, v in axis_scores.items() if k != 'neutral'}
        top_axis = max(non_neutral, key=non_neutral.get) if non_neutral else 'neutral'
        if non_neutral.get(top_axis, 0) < 0.05:
            top_axis = 'neutral'
        # Top raw label (excluding neutral unless nothing else scores)
        raw_non_neutral = [s for s in raw_scores if s['label'] != 'neutral']
        if raw_non_neutral and max(raw_non_neutral, key=lambda x: x['score'])['score'] >= 0.05:
            raw_label = max(raw_non_neutral, key=lambda x: x['score'])['label']
        else:
            raw_label = max(raw_scores, key=lambda x: x['score'])['label']
        result = (top_axis, raw_label, axis_scores)
        # Cache result (evict oldest if full)
        if len(_emotion_cache) >= _EMOTION_CACHE_MAX:
            _emotion_cache.pop(next(iter(_emotion_cache)))
        _emotion_cache[cache_key] = result
        return result
    except Exception:
        return None, None, {}


_LLM_EMOTION_SYNONYMS = {
    "happy": "joy", "excited": "joy", "cheerful": "joy", "pleased": "joy",
    "delighted": "joy", "content": "joy", "glad": "joy",
    "mad": "anger", "furious": "anger", "irritated": "anger", "frustrated": "anger",
    "annoyed": "anger",
    "sad": "sadness", "unhappy": "sadness", "depressed": "sadness", "melancholy": "sadness",
    "scared": "fear", "anxious": "fear", "worried": "fear", "terrified": "fear",
    "nervous": "fear",
    "affection": "love", "caring": "love", "grateful": "love", "thankful": "love",
    "fond": "love",
    "curious": "curiosity", "interested": "curiosity", "intrigued": "curiosity",
    "confused": "curiosity",
    "surprised": "surprise", "shocked": "surprise", "amazed": "surprise",
    "astonished": "surprise",
    "calm": "neutral", "indifferent": "neutral",
}


def detect_emotion_from_llm(emotion_str):
    """Convert an LLM-provided emotion label into (top_axis, raw_label, axis_scores).

    The LLM returns a single emotion word.  Map it to the 8-axis radar and
    generate synthetic axis_scores (dominant axis gets 0.8, rest get 0.0).
    """
    if not emotion_str or not isinstance(emotion_str, str):
        return None, None, {}
    try:
        from modules.module_dashboard_data import _EMOTION_TO_AXIS, _RADAR_AXES
        label = emotion_str.strip().lower()
        # Try GoEmotions mapping first, then axis names, then common synonyms
        axis = _EMOTION_TO_AXIS.get(label, None)
        if axis is None:
            if label in _RADAR_AXES:
                axis = label
            else:
                axis = _LLM_EMOTION_SYNONYMS.get(label, None)
        if axis is None:
            return None, None, {}
        axis_scores = {a: 0.0 for a in _RADAR_AXES}
        axis_scores[axis] = 0.8
        return axis, label, axis_scores
    except Exception:
        return None, None, {}


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
                # Remove stray non-JSON chars between elements (e.g. LLM inserting "." between fields or array items)
                bot_response = re.sub(r'([,\[])\s*[^"\s\[\]{}\d\-tfn]\s*(?=["\[{])', r'\1 ', bot_response)
                # Fix missing opening quote for string values (e.g. "reply":\n text" -> "reply": "text")
                bot_response = re.sub(r':\s*\n\s*([^"\[{\]\}\d\-tfn,\s])', r': "\1', bot_response)
                # Fix missing values after colon (e.g. "function_calls":, or "key": })
                bot_response = re.sub(r':\s*,', ': null,', bot_response)
                bot_response = re.sub(r':\s*}', ': null}', bot_response)
                try:
                    bot_response = json.loads(bot_response)
                    queue_message("WARNING: JSON repair triggered (stray chars / missing values)")
                except json.JSONDecodeError:
                    bot_response = _repair_truncated_json(bot_response)
                    bot_response = json.loads(bot_response)
                    queue_message("WARNING: JSON repair triggered (truncated JSON)")

        except json.JSONDecodeError as e:
            queue_message(f"WARNING: JSON parsing failed, attempting reply extraction: {e}")
            queue_message(f"Raw response: {bot_response}")
            # Last resort: extract the reply field via regex from hopelessly broken JSON
            raw = bot_response if isinstance(bot_response, str) else ''
            reply_match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if not reply_match:
                # Handle missing opening quote: "reply":\n text here",
                reply_match = re.search(r'"reply"\s*:\s*\n?\s*(.*?)",\s*\n', raw, re.DOTALL)
            if reply_match:
                queue_message("WARNING: JSON repair triggered (reply extraction fallback)")
                bot_response = {
                    "reply": reply_match.group(1).replace('\\"', '"').replace('\\n', '\n'),
                    "function_calls": [],
                    "new_memories": []
                }
            else:
                queue_message("ERROR: Could not extract reply from malformed JSON")
                return None

    if not isinstance(bot_response, dict):
        queue_message(f"ERROR: LLM returned non-object JSON: {type(bot_response).__name__}")
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

    bot_response["reply"] = normalize_field(bot_response.get("reply", ""))
    bot_response["function_calls"] = bot_response.get("function_calls") or []
    bot_response["new_memories"] = bot_response.get("new_memories") or []

    # Debug: log parsed structure so we can see what the pipeline produced
    fc = bot_response["function_calls"]
    mem = bot_response["new_memories"]
    queue_message(f"DEBUG: llm_parse_response -> reply={bot_response['reply'][:80]!r}{'...' if len(bot_response['reply'])>80 else ''}, function_calls={fc}, new_memories={mem}")

    return bot_response


def llm_execute_side_effects(parsed, user_input, source="voice", has_image=False):
    """Execute function_calls and save memories. Safe to run in a background thread.

    source: 'voice', 'webui', or 'discord'.
    has_image: True when the user already provided an image (skip camera capture).
    """
    global memory_manager
    try:
        fc = parsed.get("function_calls")
        if fc:
            # Filter out no-op identify_speaker_name calls when the name matches
            # the already-identified speaker. Allow calls with a DIFFERENT name
            # through — those may be legitimate rename corrections.
            # Also allow through when an unknown face is on camera so that
            # auto_train_face can trigger inside the skill.
            try:
                from modules.module_speaker_id import get_speaker_id_manager
                _sid = get_speaker_id_manager()
                if _sid:
                    _cur = _sid.get_current_speaker()
                    if _cur and not _cur.startswith("Unknown"):
                        # Check if an unknown face is visible — if so, let the
                        # call through so auto_train_face can enroll the face.
                        _has_unknown_face = False
                        try:
                            from modules.module_identity import get_identity_manager
                            _im = get_identity_manager()
                            if _im is not None:
                                _face_det = _im._get_face_id_detector()
                                if _face_det and _face_det.enabled and _face_det.has_unknown:
                                    _has_unknown_face = True
                        except Exception:
                            pass
                        if not _has_unknown_face:
                            before = len(fc)
                            fc = [f for f in fc if not (
                                f.get("function") == "identify_speaker_name"
                                and f.get("parameters", {}).get("name", "").strip() == _cur
                            )]
                            if len(fc) < before:
                                queue_message(f"DEBUG: Filtered {before - len(fc)} identify_speaker_name call(s) — name matches current speaker '{_cur}'")
            except Exception:
                pass
            queue_message(f"DEBUG: Executing {len(fc)} function call(s): {fc}")
            for func_call in fc:
                queue_message(f"DEBUG: execute_function_call -> {func_call}")
                execute_function_call(func_call, parsed, user_input, source=source, has_image=has_image)
        else:
            queue_message(f"DEBUG: No function calls to execute (value: {fc!r})")

        if memory_manager:
            # Extract activity BEFORE writing memory so it gets stored on the document
            current_activity = parsed.get("current_activity")
            activity_str = current_activity.strip() if isinstance(current_activity, str) and current_activity else None

            threading.Thread(
                target=memory_manager.write_longterm_memory,
                args=(user_input, parsed["reply"], activity_str)
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

            # Also save to the short-lived activity cache (injected directly into prompt)
            if activity_str:
                threading.Thread(
                    target=memory_manager.save_current_activity,
                    args=(activity_str,)
                ).start()
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


def execute_function_call(func_call, bot_response, user_input, source="voice", has_image=False):
    """Dispatch a function call to the matching skill plugin.

    Skills are auto-discovered from src/skills/skill_*.py at startup.
    Each skill's execute() returns a reply string (or None to keep the existing reply).
    """
    function_name = func_call.get("function", "")
    parameters = func_call.get("parameters", {})
    debug = CONFIG.get('debug_mode', False)
    if debug:
        queue_message(f"DEBUG: {function_name} | params: {parameters}")
    import modules.module_speed as speed
    speed.start('tool')

    try:
        from modules.module_skills import get_skill_manager
        skills = get_skill_manager()

        if skills and skills.has_skill(function_name):
            # Guard against hallucinated calls: skip if params are empty
            # but the skill declares required parameters.
            skill_meta = skills._skill_meta.get(function_name, {})
            req = skill_meta.get("required_params")
            if req and not parameters:
                queue_message(f"DEBUG: Skipping {function_name} — empty params but requires {req}")
                speed.log_tool(function_name, speed.stop('tool'))
                return
            # Build context dict for the skill
            context = {
                "bot_response": bot_response,
                "user_input": user_input,
                "source": source,
                "has_image": has_image,
                "config": CONFIG,
            }
            result = skills.execute(function_name, parameters, context)
            # Track skill usage for the skill engine (context continuity)
            try:
                from modules.module_skill_engine import get_skill_engine
                engine = get_skill_engine()
                if engine:
                    engine.record_skill_use(function_name)
            except Exception:
                pass
            # If skill returns a string, update the reply
            if result is not None:
                if bot_response.get("_skill_replied"):
                    # Multiple skills returning replies — append instead of overwrite
                    bot_response["reply"] = f"{bot_response['reply']} {result}"
                else:
                    bot_response["reply"] = result
                    bot_response["_skill_replied"] = True
        else:
            queue_message(f"Unknown function: {function_name}")

    except Exception as e:
        queue_message(f"Function execution failed for {function_name}: {e}")

    if debug:
        queue_message(f"DEBUG: {function_name} | reply after: {bot_response.get('reply', '')[:300]}")
    speed.log_tool(function_name, speed.stop('tool'))


def raw_complete_llm(user_prompt, istext=True):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, user_prompt)
    data["stream"] = False  # raw_complete_llm reads response as JSON, not SSE
    data.pop("response_format", None)  # plain text response, not JSON mode

    try:
        response = _http_session.post(url, headers=headers, json=data)
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