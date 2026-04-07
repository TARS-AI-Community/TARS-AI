"""
Skill: agent_task — Autonomous agent with optional multi-agent team mode.

Gives TARS the ability to break down complex tasks and solve them
step-by-step using other skills as tools. Can auto-escalate to a
multi-agent team when the goal benefits from parallel specialist work.

Single-agent mode (ReAct loop):
  1. THINK  → reason about what to do next
  2. ACT    → call a tool (web search, code exec, memory, sub-agent, …)
  3. OBSERVE → read the result
  4. repeat until ANSWER or limits reached

Team mode (coordinator orchestration):
  1. Coordinator decomposes goal into tasks with dependencies
  2. Tasks assigned to specialist agents (researcher, analyst, writer, etc.)
  3. Tasks execute in dependency-aware parallel batches
  4. Agents share results via shared memory
  5. Coordinator synthesizes all results into a final answer

Built-in agent tools:
  - think           : internal reasoning step (no external action)
  - web_search_raw  : direct DuckDuckGo search (skips LLM summarisation)
  - recall          : query TARS long-term memory / topic index
  - remember        : save a fact to TARS long-term memory
  - ask_user        : ask the user a clarifying question and wait for response
  - sub_agent       : spawn a child agent for a sub-task (single-agent mode only)

All enabled TARS skills are also available as tools automatically.
"""

import json
import os
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.module_messageQue import queue_message
from modules.module_config import load_config


# ── Skill Definition ─────────────────────────────────────────────────────────

SKILL = {
    "name": "agent_task",
    "required_params": ["goal"],
    "followup": True,
    "description": "Autonomous agent that breaks down complex tasks into steps and solves them",
    "order": 5,

    "config": {
        "max_steps": {
            "type": "number",
            "default": 6,
            "min": 2,
            "max": 15,
            "description": "Maximum reasoning steps before the agent must answer",
        },
        "model_override": {
            "type": "text",
            "default": "",
            "description": "Optional LLM model override for agent reasoning (blank = use main model)",
        },
        "verbose": {
            "type": "bool",
            "default": True,
            "description": "Log each agent step to the message queue",
        },
        "reasoning_style": {
            "type": "select",
            "default": "balanced",
            "options": ["concise", "balanced", "thorough", "creative"],
            "description": "Agent reasoning style: concise (fast), balanced, thorough (deep), creative",
        },
        "overall_timeout": {
            "type": "number",
            "default": 120,
            "min": 30,
            "max": 300,
            "description": "Max seconds for the entire agent run before forced timeout",
        },
        "enable_voice_ask": {
            "type": "bool",
            "default": False,
            "description": "Allow agent to capture voice responses for ask_user (experimental)",
        },
        "sub_agent_max_steps": {
            "type": "number",
            "default": 3,
            "min": 1,
            "max": 6,
            "description": "Maximum steps for sub-agents",
        },
        "team_mode": {
            "type": "select",
            "default": "auto",
            "options": ["auto", "always", "never"],
            "description": "Team mode: auto (LLM decides), always (force team), never (single agent only)",
        },
        "team_concurrency": {
            "type": "number",
            "default": 3,
            "min": 1,
            "max": 6,
            "description": "Max team agents running in parallel",
        },
        "team_task_steps": {
            "type": "number",
            "default": 4,
            "min": 1,
            "max": 10,
            "description": "Maximum reasoning steps per team agent task",
        },
        "team_timeout": {
            "type": "number",
            "default": 180,
            "min": 60,
            "max": 600,
            "description": "Max seconds for team mode (overrides overall_timeout when in team mode)",
        },
    },

    "prompt": """agent_task
   Triggers: Use when the user's request requires MULTIPLE steps to complete, such as:
     * Research tasks: "research X and give me a summary", "find out about X and compare with Y"
     * Multi-step tasks: "look up the weather and then find indoor activities", "search for X, then calculate Y"
     * Planning tasks: "plan a trip to X", "help me figure out how to do X"
     * Analysis tasks: "analyze X and give me recommendations", "compare X vs Y"
     * Multi-domain tasks: "design a marketing strategy with technical feasibility analysis"
     * Complex projects: "create a full business plan for X", "design a system architecture for Y"
   Do NOT use for simple single-step tasks that another skill can handle directly (e.g. a single web search, a single code execution).
   Only use when the task clearly needs chaining multiple actions together.
   CRITICAL: Your "reply" MUST be a short placeholder like "Let me work on that" or "Give me a moment to figure this out." The agent will handle the rest autonomously.
   Parameters: {{"goal": "clear description of what needs to be accomplished"}}
   Example: {{"function": "agent_task", "parameters": {{"goal": "research the latest SpaceX launch and summarize the key details"}}}}""",

    "examples": [
        """Example - Multi-step research:
User: "Find out what movies are coming out this month and pick one for me based on action genres"
Response: {{"reply": "Let me look into that for you.", "function_calls": [{{"function": "agent_task", "parameters": {{"goal": "search for movies releasing this month, filter for action genre, and recommend the best one with reasoning"}}}}], "new_memories": []}}""",
        """Example - Research and calculate:
User: "What's the distance from Earth to Mars right now and how long would it take to drive there?"
Response: {{"reply": "Good question, let me figure that out.", "function_calls": [{{"function": "agent_task", "parameters": {{"goal": "find the current Earth-Mars distance, then calculate travel time at highway speed (100 km/h)"}}}}], "new_memories": []}}""",
        """Example - Complex multi-perspective analysis:
User: "I need a thorough analysis of whether to use React or Vue for our new project"
Response: {{"reply": "Let me dig into that from multiple angles.", "function_calls": [{{"function": "agent_task", "parameters": {{"goal": "Compare React vs Vue: research current ecosystem and community, analyze technical performance and DX, evaluate business factors like hiring and long-term support, and synthesize into a recommendation"}}}}], "new_memories": []}}""",
    ],
}


# ── Constants & Shared State ─────────────────────────────────────────────────

_http_session = requests.Session()

_EXCLUDE_FROM_AGENT = frozenset({"agent_task", "multi_agent", "web_search"})

_MAX_DEPTH = 2  # Sub-agent nesting limit

# Reasoning style presets
_STYLE_CONFIGS = {
    "concise": {
        "max_tokens": 400,
        "temp_mod": -0.1,
        "addon": "Be extremely concise. Minimise steps. Get to the answer fast. "
                 "Prefer fewer, targeted actions.",
    },
    "balanced": {
        "max_tokens": 800,
        "temp_mod": 0.0,
        "addon": "",
    },
    "thorough": {
        "max_tokens": 1200,
        "temp_mod": 0.0,
        "addon": "Be thorough and methodical. Verify information from multiple "
                 "sources when possible. Cross-check facts before answering.",
    },
    "creative": {
        "max_tokens": 1000,
        "temp_mod": 0.15,
        "addon": "Think creatively. Consider unconventional approaches. "
                 "Make unexpected connections. Explore lateral solutions.",
    },
}


# ── ask_user Synchronisation (per-request to avoid race conditions) ──────────

_ask_lock = threading.Lock()
_ask_pending = {}  # request_id -> {"event": Event, "response": str|None}
_ask_counter = 0
_socketio_registered = False


def _ensure_socketio_handler():
    """Lazily register the SocketIO handler for ask_user web UI responses."""
    global _socketio_registered
    if _socketio_registered:
        return
    try:
        from modules.module_chatui import socketio

        @socketio.on('agent_user_response')
        def _handle_user_response(data):
            req_id = data.get('request_id')
            text = data.get('text', '')
            with _ask_lock:
                if req_id and req_id in _ask_pending:
                    _ask_pending[req_id]["response"] = text
                    _ask_pending[req_id]["event"].set()
                elif _ask_pending:
                    latest = max(_ask_pending.keys())
                    _ask_pending[latest]["response"] = text
                    _ask_pending[latest]["event"].set()

        _socketio_registered = True
    except Exception:
        pass


# ── Built-in Tool Implementations ───────────────────────────────────────────

def _tool_think(params, context, skill_config):
    """Internal reasoning — no external action taken."""
    return ("(Reasoning step complete. Proceed to your next action "
            "or provide your final answer.)")


def _tool_web_search_raw(params, context, skill_config):
    """Direct DuckDuckGo search — no secondary LLM summarisation."""
    query = params.get("query", "")
    if not query:
        return "Error: No search query provided."
    try:
        from modules.module_websearch import search_google
        result = search_google(query)
        return result if result else "No results found."
    except Exception as e:
        return f"Search error: {e}"


def _tool_recall(params, context, skill_config):
    """Query TARS long-term memory for relevant information."""
    query = params.get("query", "")
    if not query:
        return "Error: No query provided for memory recall."
    try:
        from modules.module_llm import memory_manager
        if not memory_manager:
            return "(Memory system not available)"

        parts = []

        # Semantic memory search
        mem = memory_manager.get_longterm_memory(query)
        if mem and mem.strip():
            parts.append(mem.strip())

        # Topic index (known facts)
        if hasattr(memory_manager, 'get_topic_index_summary'):
            topics = memory_manager.get_topic_index_summary()
            if topics and topics.strip():
                parts.append(topics.strip())

        if parts:
            return "\n\n".join(parts)
        return "(No relevant memories found for this query)"
    except Exception as e:
        return f"Memory recall error: {e}"


def _tool_remember(params, context, skill_config):
    """Save a fact to TARS long-term memory."""
    fact = params.get("fact", "")
    if not fact:
        return "Error: No fact provided to remember."
    try:
        from modules.module_llm import memory_manager
        if not memory_manager:
            return "(Memory system not available)"
        memory_manager.update_topic_index_with_ai_response(json.dumps([fact]))
        return f"Saved to memory: {fact}"
    except Exception as e:
        return f"Memory save error: {e}"


def _tool_ask_user(params, context, skill_config):
    """Ask the user a clarifying question and wait for their response."""
    global _ask_counter
    question = params.get("question", "")
    if not question:
        return "Error: No question provided."

    timeout = min(int(params.get("timeout", 20)), 30)
    source = context.get("source", "voice")

    # Create a per-request event to avoid race conditions in team mode
    with _ask_lock:
        _ask_counter += 1
        req_id = str(_ask_counter)
        event = threading.Event()
        _ask_pending[req_id] = {"event": event, "response": None}

    _ensure_socketio_handler()
    _emit_agent_event("ask_user", {
        "question": question, "timeout": timeout, "request_id": req_id,
    })

    try:
        # Attempt voice capture if enabled
        enable_voice = str(skill_config.get("enable_voice_ask", "false")).lower() \
            in ("true", "1", "yes")
        if source == "voice" and enable_voice:
            voice_result = _capture_voice_response(timeout)
            if voice_result:
                _emit_agent_event("ask_user_response",
                                  {"response": voice_result, "via": "voice"})
                return f"User responded: {voice_result}"

        # Wait for web UI response (fallback)
        if event.wait(timeout=timeout):
            with _ask_lock:
                resp = _ask_pending.get(req_id, {}).get("response", "")
            if resp:
                _emit_agent_event("ask_user_response",
                                  {"response": resp, "via": "webui"})
                return f"User responded: {resp}"
            return "(User sent empty response)"

        return (f"(No response received within {timeout}s. Continue with your "
                f"best judgement based on available information.)")
    finally:
        with _ask_lock:
            _ask_pending.pop(req_id, None)


def _capture_voice_response(timeout=15):
    """Record audio and transcribe via OpenAI Whisper API. Best-effort."""
    try:
        import sounddevice as sd
        import numpy as np
        import wave
        import tempfile

        sample_rate = 16000
        duration = min(timeout, 12)

        # Wait for any ongoing TTS to finish before recording
        try:
            from modules.module_state import get_tars_state, TarsState
            for _ in range(30):  # max 3s
                if get_tars_state() != TarsState.TALKING:
                    break
                time.sleep(0.1)
        except Exception:
            time.sleep(1)

        time.sleep(0.5)  # let echo settle

        queue_message(f"AGENT: Listening for voice response ({duration}s)...")
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                       channels=1, dtype='float32')
        sd.wait()

        # Silence check
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.005:
            queue_message("AGENT: No speech detected (silence)")
            return None

        # Write WAV to temp file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name
        audio_i16 = (audio * 32767).astype(np.int16)
        with wave.open(temp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_i16.tobytes())

        # Transcribe via Whisper
        api_key = os.getenv('OPENAI_API_KEY', '')
        if api_key:
            with open(temp_path, 'rb') as f:
                resp = _http_session.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization': f'Bearer {api_key}'},
                    files={'file': ('response.wav', f, 'audio/wav')},
                    data={'model': 'whisper-1'},
                    timeout=20,
                )
            if resp.ok:
                text = resp.json().get('text', '').strip()
                if text:
                    queue_message(f"AGENT: Voice response: {text}")
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    return text

        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return None

    except ImportError:
        queue_message("AGENT: sounddevice not available for voice capture")
        return None
    except Exception as e:
        queue_message(f"AGENT: Voice capture error: {e}")
        return None


# ── Tool Registry & Discovery ───────────────────────────────────────────────

_BUILTIN_TOOLS = {
    "think": {
        "desc": "Pause to reason, plan, or analyse without taking an external "
                "action. Use to combine information or plan next steps.",
        "params": '{"reasoning": "your detailed reasoning"}',
        "fn": _tool_think,
    },
    "web_search_raw": {
        "desc": "Search the web via DuckDuckGo and get raw results. "
                "More efficient than web_search — use this for research.",
        "params": '{"query": "search terms"}',
        "fn": _tool_web_search_raw,
    },
    "recall": {
        "desc": "Search TARS long-term memory for facts about the user, "
                "past conversations, or previously learned information.",
        "params": '{"query": "what to search for in memory"}',
        "fn": _tool_recall,
    },
    "remember": {
        "desc": "Save an important fact or conclusion to TARS long-term memory "
                "for future reference.",
        "params": '{"fact": "the fact to save"}',
        "fn": _tool_remember,
    },
    "ask_user": {
        "desc": "Ask the user a clarifying question and wait for their response. "
                "Use sparingly — only when you truly need more information.",
        "params": '{"question": "your clarifying question"}',
        "fn": _tool_ask_user,
    },
}

# Better descriptions for well-known TARS skills
_KNOWN_SKILL_DESCRIPTIONS = {
    "sandbox_exec": {
        "desc": "Execute Python code in a sandbox (math, data processing, logic). "
                "Use print() for output. Allowed: math, random, json, datetime, "
                "collections, itertools, re, statistics.",
        "params": '{"code": "python code string", "description": "brief description"}',
    },
    "home_assistant": {
        "desc": "Control smart home devices via Home Assistant "
                "(lights, locks, thermostat, garage, etc.).",
        "params": '{"prompt": "natural language command"}',
    },
    "capture_camera_view": {
        "desc": "Take a photo with the camera and get a description of what "
                "is visible.",
        "params": '{"prompt": "what to look for or describe"}',
    },
    "generate_image": {
        "desc": "Generate an image from a text description using "
                "Stable Diffusion.",
        "params": '{"prompt": "image description"}',
    },
    "browser": {
        "desc": "Open a URL in the browser or play a YouTube video on "
                "the display.",
        "params": '{"action": "open_url|play_youtube", "url": "https://...", '
                  '"query": "search terms for youtube"}',
    },
    "discord": {
        "desc": "Send a message to the configured Discord channel.",
        "params": '{"message": "text to send"}',
    },
    "volume": {
        "desc": "Adjust the system audio volume.",
        "params": '{"level": "0-100 or up/down"}',
    },
    "execute_movement": {
        "desc": "Trigger a physical movement (nod, shake head, wave, etc.).",
        "params": '{"movement": "nod|shake|wave|look_left|look_right|..."}',
    },
    "system_control": {
        "desc": "System commands: reboot, shutdown, restart TARS.",
        "params": '{"action": "reboot|shutdown|restart"}',
    },
    "tars_radio": {
        "desc": "Stream internet radio stations.",
        "params": '{"action": "play|stop", "station": "station name or URL"}',
    },
    "reminder": {
        "desc": "Set a timed reminder that TARS will announce later.",
        "params": '{"reminder": "what to remind about", "delay_minutes": 5}',
    },
    "generate_music": {
        "desc": "Generate music from a text description.",
        "params": '{"prompt": "music description / genre / mood"}',
    },
    "network_camera": {
        "desc": "View or snapshot from a network/IP camera.",
        "params": '{"action": "snapshot|stream", "camera": "camera name"}',
    },
    "identify_speaker": {
        "desc": "Register or identify a speaker by their voice.",
        "params": '{"name": "speaker name to register"}',
    },
}


def _extract_params_from_prompt(prompt_text):
    """Extract parameter format from a skill's prompt text."""
    if not prompt_text:
        return '{}'
    for line in prompt_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('Parameters:'):
            params_str = stripped[len('Parameters:'):].strip()
            return params_str.replace('{{', '{').replace('}}', '}')
    return '{}'


def _get_available_tools(depth=0):
    """Build the complete tool list: built-in + sub_agent + TARS skills."""
    tools = {}

    # Built-in tools
    for name, info in _BUILTIN_TOOLS.items():
        tools[name] = {"desc": info["desc"], "params": info["params"]}

    # Sub-agent tool (only if within depth limit)
    if depth < _MAX_DEPTH:
        tools["sub_agent"] = {
            "desc": "Spawn a sub-agent to handle a sub-task independently and "
                    "return its result. Use for complex sub-problems that need "
                    "their own multi-step reasoning.",
            "params": '{"goal": "clear description of the sub-task"}',
        }

    # Auto-discover enabled TARS skills
    try:
        from modules.module_skills import get_skill_manager
        sm = get_skill_manager()
        if sm:
            for name in sm.get_skill_names():
                if name in _EXCLUDE_FROM_AGENT or name in tools:
                    continue
                # Use curated description if available, else auto-generate
                if name in _KNOWN_SKILL_DESCRIPTIONS:
                    tools[name] = _KNOWN_SKILL_DESCRIPTIONS[name]
                else:
                    meta = sm._skill_meta.get(name, {})
                    desc = meta.get("description", f"Skill: {name}")
                    params = _extract_params_from_prompt(meta.get("prompt", ""))
                    tools[name] = {"desc": desc, "params": params}
    except Exception as e:
        queue_message(f"AGENT: Failed to list TARS skills: {e}")

    return tools


# ── Character Info Helper ────────────────────────────────────────────────────

def _get_character_info():
    """Extract character name and personality from the character manager."""
    char_name = "TARS"
    personality = ""
    try:
        from modules.module_llm import character_manager
        if character_manager:
            char_name = getattr(character_manager, 'char_name', 'TARS') or 'TARS'
            persona_text = getattr(character_manager, 'personality', '') or ''
            if not persona_text:
                persona_text = getattr(character_manager, 'description', '') or ''
            if persona_text:
                personality = persona_text[:500]
    except Exception:
        pass
    return char_name, personality


# ── Agent System Prompt ──────────────────────────────────────────────────────

_AGENT_SYSTEM_TEMPLATE = """\
You are {char_name}, an autonomous reasoning agent. You solve tasks \
step-by-step using available tools.
{personality}
## Available tools
{tool_list}

## Response format
You MUST respond with EXACTLY ONE valid JSON object per turn. Choose one:

1. Use a single tool:
{{"thought": "your reasoning", "action": "tool_name", \
"action_input": {{...tool parameters...}}}}

2. Use multiple tools in parallel (when actions are independent):
{{"thought": "your reasoning", "parallel_actions": [\
{{"action": "tool_name", "action_input": {{...}}}}, \
{{"action": "tool_name2", "action_input": {{...}}}}]}}

3. Give the final answer (when you have enough information):
{{"thought": "summarising what I found", \
"answer": "your complete final answer to the user"}}

## Rules
- Think step by step. Each turn you get one action (or multiple parallel actions).
- After each action you will see the result as an OBSERVATION.
- Use observations to inform your next step.
- When you have enough information, provide the final answer immediately.
- If a tool fails, try a different approach or tool.
- You MUST answer within {max_steps} steps.
- Use "think" when you need to reason or plan without calling an external tool.
- Use "recall" to check what you already know before searching the web.
- Use "ask_user" sparingly — only when you truly lack critical information.
- IMPORTANT: Respond with raw JSON only. No markdown, no code fences, no extra text.
{style_addon}
## Context
{context_section}"""


def _build_system_prompt(max_steps, config, context, skill_config, depth=0):
    """Build the agent system prompt with tools, personality, and context."""

    char_name, personality_text = _get_character_info()
    personality = ""
    if personality_text:
        personality = f"\n## Your personality\n{personality_text}\n"

    # ── Tool list ──
    tools = _get_available_tools(depth=depth)
    if tools:
        lines = []
        for name, info in tools.items():
            lines.append(f"- {name}: {info['desc']}\n  Parameters: {info['params']}")
        tool_list = "\n".join(lines)
    else:
        tool_list = "(No tools available — reason from your own knowledge.)"

    # ── Reasoning style ──
    style = skill_config.get("reasoning_style", "balanced")
    style_cfg = _STYLE_CONFIGS.get(style, _STYLE_CONFIGS["balanced"])
    style_addon = ""
    if style_cfg["addon"]:
        style_addon = f"\n## Reasoning style\n{style_cfg['addon']}"

    # ── Conversation history & memory context ──
    context_parts = []
    user_input = context.get("user_input", "")
    if user_input:
        context_parts.append(f'User just said: "{user_input}"')

    try:
        from modules.module_llm import memory_manager
        if memory_manager:
            mem = memory_manager.get_longterm_memory(user_input or "general context")
            if mem and mem.strip():
                context_parts.append(f"Relevant memories:\n{mem[:800]}")
    except Exception:
        pass

    context_section = "\n".join(context_parts) if context_parts \
        else "(No additional context)"

    return _AGENT_SYSTEM_TEMPLATE.format(
        char_name=char_name,
        personality=personality,
        tool_list=tool_list,
        max_steps=max_steps,
        style_addon=style_addon,
        context_section=context_section,
    )


# ── LLM Call ─────────────────────────────────────────────────────────────────

def _agent_llm_call(messages, config, model_override="", style="balanced",
                    max_tokens_override=None, temp_mod_override=None):
    """Make an LLM chat-completion call. Uses shared HTTP session."""
    llm_backend = config['LLM']['llm_backend']
    base_url = config['LLM']['base_url']
    api_key = config['LLM']['api_key']

    if llm_backend == 'grok':
        model = model_override or config['LLM'].get('grok_model', 'grok-3')
    elif llm_backend == 'deepinfra':
        model = model_override or config['LLM'].get('deepinfra', '')
    elif llm_backend == 'other':
        model = model_override or config['LLM'].get('other_model', '')
    elif llm_backend == 'llamacpp':
        from modules.module_llamacpp import get_server_url
        base_url = get_server_url(config['LLAMACPP'])
        model = "llamacpp"
    else:
        model = model_override or config['LLM'].get('openai_model', 'gpt-4o-mini')

    if llm_backend == "deepinfra":
        url = f"{base_url}/v1/openai/chat/completions"
    else:
        url = f"{base_url}/v1/chat/completions"

    style_cfg = _STYLE_CONFIGS.get(style, _STYLE_CONFIGS["balanced"])
    base_temp = float(config['LLM'].get('temperature', 0.5))
    temp_mod = temp_mod_override if temp_mod_override is not None else style_cfg["temp_mod"]
    temperature = max(0.0, min(1.5, base_temp + temp_mod))
    max_tokens = max_tokens_override or style_cfg["max_tokens"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _http_session.post(url, headers=headers, json=data, timeout=45)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── Tool Dispatch ────────────────────────────────────────────────────────────

def _dispatch_tool(tool_name, tool_input, context, config, skill_config, depth=0):
    """Route a tool call to a built-in handler, sub-agent, or TARS skill."""

    # Normalise string inputs
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, TypeError):
            tool_input = {"query": tool_input}

    # Built-in tools
    if tool_name in _BUILTIN_TOOLS:
        try:
            return _BUILTIN_TOOLS[tool_name]["fn"](
                tool_input, context, skill_config)
        except Exception as e:
            return f"Error in {tool_name}: {e}"

    # Sub-agent
    if tool_name == "sub_agent":
        return _tool_sub_agent(tool_input, context, config, skill_config, depth)

    # TARS skill (with isolated bot_response to prevent mutation leaks)
    try:
        from modules.module_skills import get_skill_manager
        sm = get_skill_manager()
        if not sm or not sm.has_skill(tool_name):
            return (f"Error: Unknown tool '{tool_name}'. "
                    f"Check available tools and try again.")
        if not sm.is_enabled(tool_name):
            return f"Error: Tool '{tool_name}' is disabled."

        sub_context = {
            "bot_response": dict(context.get("bot_response", {})),
            "user_input": context.get("user_input", ""),
            "source": context.get("source", "voice"),
            "has_image": context.get("has_image", False),
            "config": config,
        }
        result = sm.execute(tool_name, tool_input, sub_context)
        if result is None:
            return "(Tool executed successfully but returned no output)"
        return str(result)[:2000]

    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def _tool_sub_agent(params, context, config, skill_config, parent_depth):
    """Spawn a sub-agent for a sub-task."""
    if parent_depth >= _MAX_DEPTH:
        return ("Error: Maximum sub-agent nesting depth reached. "
                "Answer with available information instead.")

    sub_goal = params.get("goal", "")
    if not sub_goal:
        return "Error: No goal provided for sub-agent."

    sub_max_steps = int(skill_config.get("sub_agent_max_steps", 3))
    queue_message(f"AGENT: Spawning sub-agent (depth={parent_depth + 1}): "
                  f"{sub_goal[:100]}")

    result = _run_agent_loop(
        goal=sub_goal,
        max_steps=sub_max_steps,
        config=config,
        skill_config=skill_config,
        context=context,
        depth=parent_depth + 1,
        emit_ui=False,
    )
    return f"Sub-agent result: {result}"


def _execute_parallel(actions, context, config, skill_config, depth=0):
    """Execute multiple tool calls concurrently."""
    max_workers = min(len(actions), 4)
    observations = [None] * len(actions)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for i, act in enumerate(actions):
            name = act.get("action", "")
            inp = act.get("action_input", {})
            f = pool.submit(_dispatch_tool, name, inp, context,
                            config, skill_config, depth)
            futures[f] = (i, name)

        for f in as_completed(futures, timeout=60):
            idx, name = futures[f]
            try:
                result = f.result(timeout=30)
                observations[idx] = f"[{name}]: {result}"
            except Exception as e:
                observations[idx] = f"[{name}]: Error — {e}"

    # Fill any that didn't complete
    for i in range(len(observations)):
        if observations[i] is None:
            name = actions[i].get("action", "unknown")
            observations[i] = f"[{name}]: (timed out)"

    return "\n\n".join(observations)


# ── JSON Parser ──────────────────────────────────────────────────────────────

def _parse_agent_response(text):
    """Parse the agent's JSON response. Returns dict or None."""
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON from surrounding text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ── Status & UI Emission ────────────────────────────────────────────────────

def _emit_agent_event(event_type, data):
    """Emit a detailed agent event to the web UI via SocketIO."""
    try:
        from modules.module_chatui import socketio
        socketio.emit('agent_step', {
            'type': event_type,
            **data,
            'timestamp': time.time(),
        })
    except Exception:
        pass


# ── Core Agent Loop (Single-Agent Mode) ─────────────────────────────────────

def _run_agent_loop(goal, max_steps, config, skill_config, context,
                    depth=0, emit_ui=True, system_prompt=None):
    """Core ReAct loop. Reusable for top-level, sub-agents, and team agents.

    If system_prompt is provided, it's used directly instead of building one.
    This allows team mode to inject specialist agent prompts.
    """
    verbose = str(skill_config.get("verbose", "true")).lower() \
        in ("true", "1", "yes")
    model_override = skill_config.get("model_override", "").strip() or ""
    style = skill_config.get("reasoning_style", "balanced")
    overall_timeout = int(skill_config.get("overall_timeout", 120))

    start_time = time.time()
    prefix = f"AGENT[d{depth}]" if depth > 0 else "AGENT"

    if verbose:
        queue_message(f"{prefix}: Starting — {goal[:200]}")

    if emit_ui:
        _emit_agent_event("start", {
            "goal": goal, "max_steps": max_steps,
            "depth": depth, "style": style,
        })

    # Build system prompt — use override if provided (team mode), else build
    if system_prompt is None:
        system_prompt = _build_system_prompt(
            max_steps, config, context, skill_config, depth)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Goal: {goal}"},
    ]

    for step in range(1, max_steps + 1):

        # ── Timeout check ──
        elapsed = time.time() - start_time
        if elapsed > overall_timeout:
            queue_message(f"{prefix}: Timeout ({overall_timeout}s) at step {step}")
            if emit_ui:
                _emit_agent_event("error", {
                    "step": step, "error": "timeout",
                    "elapsed": round(elapsed, 1),
                })
            break

        # ── Barge-in / abort check ──
        try:
            from modules.module_state import get_tars_state, TarsState
            state = get_tars_state()
            if state == TarsState.LISTENING:
                queue_message(f"{prefix}: Aborting — user barge-in detected")
                if emit_ui:
                    _emit_agent_event("error", {
                        "step": step, "error": "barge-in",
                    })
                return ("(Agent interrupted because you started speaking. "
                        "Ask again if you'd like me to continue.)")
        except Exception:
            pass

        if verbose:
            queue_message(f"{prefix}: Step {step}/{max_steps} "
                          f"({elapsed:.1f}s)")

        # ── LLM reasoning call ──
        try:
            raw = _agent_llm_call(messages, config, model_override, style)
        except Exception as e:
            queue_message(f"{prefix}: LLM call failed at step {step}: {e}")
            if emit_ui:
                _emit_agent_event("error", {
                    "step": step, "error": str(e),
                })
            return f"Agent encountered an error while reasoning: {e}"

        parsed = _parse_agent_response(raw)
        if parsed is None:
            queue_message(f"{prefix}: Unparseable response at step {step}, "
                          "treating as answer")
            if emit_ui:
                _emit_agent_event("complete", {
                    "step": step, "answer": raw[:500],
                })
            return raw[:2000]

        thought = parsed.get("thought", "")
        if verbose and thought:
            queue_message(f"{prefix}: Think -> {thought[:200]}")
        if emit_ui:
            _emit_agent_event("think", {
                "step": step, "thought": thought[:500],
            })

        # ── Final answer ──
        if "answer" in parsed:
            answer = parsed["answer"]
            elapsed = time.time() - start_time
            queue_message(f"{prefix}: Done at step {step} "
                          f"({elapsed:.1f}s) — len={len(answer)}")
            if emit_ui:
                _emit_agent_event("complete", {
                    "step": step, "answer": answer[:500],
                    "elapsed": round(elapsed, 1),
                })
            return answer

        # ── Parallel actions ──
        if "parallel_actions" in parsed:
            actions = parsed["parallel_actions"]
            if isinstance(actions, list) and actions:
                action_names = [a.get("action", "?") for a in actions]
                if verbose:
                    queue_message(f"{prefix}: Parallel -> {action_names}")
                if emit_ui:
                    _emit_agent_event("act", {
                        "step": step, "actions": action_names,
                        "parallel": True,
                    })

                observation = _execute_parallel(
                    actions, context, config, skill_config, depth)

                if verbose:
                    queue_message(f"{prefix}: Observe -> "
                                  f"{observation[:300]}")
                if emit_ui:
                    _emit_agent_event("observe", {
                        "step": step,
                        "observation": observation[:500],
                    })

                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"OBSERVATION:\n{observation}",
                })
                continue

        # ── Single action ──
        action = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        if not action:
            # Malformed — nudge the LLM
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "Please respond with valid JSON containing "
                           "'action', 'parallel_actions', or 'answer'.",
            })
            continue

        if verbose:
            input_preview = json.dumps(action_input, default=str)[:200]
            queue_message(f"{prefix}: Act -> {action}({input_preview})")
        if emit_ui:
            _emit_agent_event("act", {
                "step": step, "action": action,
                "input": json.dumps(action_input, default=str)[:300],
            })

        observation = _dispatch_tool(
            action, action_input, context, config, skill_config, depth)

        if verbose:
            queue_message(f"{prefix}: Observe -> {observation[:300]}")
        if emit_ui:
            _emit_agent_event("observe", {
                "step": step, "observation": observation[:500],
            })

        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"OBSERVATION:\n{observation}",
        })

    # ── Exceeded step or time limit — force final answer ──
    elapsed = time.time() - start_time
    queue_message(f"{prefix}: Forcing final answer "
                  f"(steps={max_steps}, elapsed={elapsed:.1f}s)")
    messages.append({
        "role": "user",
        "content": 'You have reached the limit. You MUST provide your final '
                   'answer NOW using {"thought": "...", "answer": "..."} format. '
                   'Summarise everything you have learned so far.',
    })

    try:
        raw = _agent_llm_call(messages, config, model_override, style)
        parsed = _parse_agent_response(raw)
        if parsed and "answer" in parsed:
            if emit_ui:
                _emit_agent_event("complete", {
                    "step": max_steps,
                    "answer": parsed["answer"][:500],
                    "elapsed": round(time.time() - start_time, 1),
                })
            return parsed["answer"]
        if emit_ui:
            _emit_agent_event("complete", {
                "step": max_steps, "answer": raw[:500],
                "elapsed": round(time.time() - start_time, 1),
            })
        return raw[:2000]
    except Exception as e:
        if emit_ui:
            _emit_agent_event("error", {
                "step": max_steps, "error": str(e),
            })
        return f"Agent could not complete the task: {e}"


# ═════════════════════════════════════════════════════════════════════════════
# TEAM MODE — Multi-agent orchestration
# ═════════════════════════════════════════════════════════════════════════════

# ── Agent Roster ─────────────────────────────────────────────────────────────
# Declarative configs — the coordinator picks from this roster.

_AGENT_ROSTER = {
    "researcher": {
        "name": "researcher",
        "expertise": "web research, fact-finding, data gathering, source verification",
        "system_prompt": (
            "You are a meticulous research specialist. Your job is to find accurate, "
            "up-to-date information from available sources. Always cite where you found "
            "information. Distinguish between facts and speculation. If you cannot find "
            "reliable data, say so clearly rather than guessing."
        ),
    },
    "analyst": {
        "name": "analyst",
        "expertise": "data analysis, comparison, evaluation, critical thinking, pros/cons",
        "system_prompt": (
            "You are an analytical specialist. Your job is to evaluate information, "
            "identify patterns, weigh trade-offs, and draw evidence-based conclusions. "
            "Use structured reasoning. Present findings with clear logic chains. "
            "Quantify when possible. Flag assumptions explicitly."
        ),
    },
    "writer": {
        "name": "writer",
        "expertise": "writing, summarization, synthesis, communication, reports, documentation",
        "system_prompt": (
            "You are a skilled writer and communicator. Your job is to synthesize "
            "information into clear, well-structured prose. Adapt your tone to the "
            "audience. Use headings, bullet points, and logical flow. Be concise "
            "but thorough. Make complex topics accessible."
        ),
    },
    "coder": {
        "name": "coder",
        "expertise": "programming, code, algorithms, technical design, system architecture, debugging",
        "system_prompt": (
            "You are a senior software engineer. Your job is to write code, design "
            "systems, debug problems, and evaluate technical approaches. Write clean, "
            "efficient code. Consider edge cases. Explain trade-offs in technical "
            "decisions."
        ),
    },
    "planner": {
        "name": "planner",
        "expertise": "project planning, strategy, timelines, resource allocation, risk assessment",
        "system_prompt": (
            "You are a strategic planner. Your job is to break down complex initiatives "
            "into actionable plans with timelines, milestones, and risk assessments. "
            "Consider dependencies between tasks. Identify potential blockers early. "
            "Provide realistic estimates and contingency options."
        ),
    },
    "critic": {
        "name": "critic",
        "expertise": "review, quality assurance, devil's advocate, finding flaws, improvement suggestions",
        "system_prompt": (
            "You are a constructive critic and quality reviewer. Your job is to find "
            "weaknesses, gaps, inconsistencies, and areas for improvement. Be specific "
            "and actionable in your feedback. Suggest concrete improvements."
        ),
    },
}


# ── Shared Memory ────────────────────────────────────────────────────────────

class _SharedMemory:
    """Thread-safe key-value store for inter-agent communication."""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def write(self, agent_name, key, value):
        with self._lock:
            self._store[f"{agent_name}/{key}"] = str(value)

    def get_summary(self, max_chars_per_entry=300, max_total_chars=4000):
        """Build a markdown summary, capped to prevent context blowup."""
        with self._lock:
            if not self._store:
                return ""
            lines = ["## Shared Team Memory"]
            by_agent = {}
            for full_key, value in self._store.items():
                parts = full_key.split("/", 1)
                agent = parts[0] if len(parts) > 1 else "system"
                key = parts[1] if len(parts) > 1 else full_key
                by_agent.setdefault(agent, []).append((key, value))

            total_len = 0
            for agent, entries in by_agent.items():
                lines.append(f"\n### {agent}")
                for key, value in entries:
                    truncated = value[:max_chars_per_entry]
                    if len(value) > max_chars_per_entry:
                        truncated += "..."
                    line = f"- **{key}**: {truncated}"
                    total_len += len(line)
                    if total_len > max_total_chars:
                        lines.append("- *(remaining entries truncated)*")
                        return "\n".join(lines)
                    lines.append(line)
            return "\n".join(lines)

    def clear(self):
        with self._lock:
            self._store.clear()


# ── Task Queue ───────────────────────────────────────────────────────────────

class _TaskQueue:
    """Dependency-aware task queue with status tracking and cascade failure."""

    PENDING = "pending"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def add_task(self, title, description, assignee=None, depends_on=None):
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            self._tasks[task_id] = {
                "id": task_id,
                "title": title,
                "description": description,
                "assignee": assignee,
                "depends_on_titles": depends_on or [],
                "depends_on_ids": [],
                "status": self.PENDING,
                "result": None,
            }
            return task_id

    def resolve_dependencies(self):
        """Convert title-based deps to ID-based. Case-insensitive. Detects cycles."""
        with self._lock:
            title_to_id = {}
            for t in self._tasks.values():
                title_to_id[t["title"].strip().lower()] = t["id"]

            for task in self._tasks.values():
                dep_ids = []
                for dep_title in task["depends_on_titles"]:
                    dep_id = title_to_id.get(dep_title.strip().lower())
                    if dep_id is not None and dep_id != task["id"]:
                        dep_ids.append(dep_id)
                task["depends_on_ids"] = dep_ids
                if dep_ids and task["status"] == self.PENDING:
                    task["status"] = self.BLOCKED

            # Cycle detection via DFS
            WHITE, GREY, BLACK = 0, 1, 2
            colour = {tid: WHITE for tid in self._tasks}
            has_cycle = False

            def dfs(tid):
                nonlocal has_cycle
                colour[tid] = GREY
                for dep_id in self._tasks[tid]["depends_on_ids"]:
                    if dep_id not in colour:
                        continue
                    if colour[dep_id] == GREY:
                        has_cycle = True
                        return
                    if colour[dep_id] == WHITE:
                        dfs(dep_id)
                        if has_cycle:
                            return
                colour[tid] = BLACK

            for tid in self._tasks:
                if colour[tid] == WHITE:
                    dfs(tid)
                    if has_cycle:
                        break

            if has_cycle:
                queue_message("TEAM: WARNING — Circular dependency detected! "
                              "Clearing all deps to avoid deadlock.")
                for task in self._tasks.values():
                    task["depends_on_ids"] = []
                    if task["status"] == self.BLOCKED:
                        task["status"] = self.PENDING

    def get_pending(self):
        with self._lock:
            return [dict(t) for t in self._tasks.values()
                    if t["status"] == self.PENDING]

    def mark_in_progress(self, task_id):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = self.IN_PROGRESS

    def complete(self, task_id, result):
        with self._lock:
            if task_id not in self._tasks:
                return
            self._tasks[task_id]["status"] = self.COMPLETED
            self._tasks[task_id]["result"] = result
            for task in self._tasks.values():
                if task["status"] != self.BLOCKED:
                    continue
                if task_id in task["depends_on_ids"]:
                    all_done = all(
                        self._tasks[did]["status"] == self.COMPLETED
                        for did in task["depends_on_ids"]
                        if did in self._tasks
                    )
                    if all_done:
                        task["status"] = self.PENDING

    def fail(self, task_id, error):
        with self._lock:
            if task_id not in self._tasks:
                return
            self._tasks[task_id]["status"] = self.FAILED
            self._tasks[task_id]["result"] = f"FAILED: {error}"
            self._cascade_fail(task_id)

    def _cascade_fail(self, failed_id):
        for task in self._tasks.values():
            if task["status"] in (self.BLOCKED, self.PENDING):
                if failed_id in task["depends_on_ids"]:
                    task["status"] = self.FAILED
                    task["result"] = (f"FAILED: dependency "
                                      f"'{self._tasks[failed_id]['title']}' failed")
                    self._cascade_fail(task["id"])

    def is_done(self):
        with self._lock:
            return all(t["status"] in (self.COMPLETED, self.FAILED)
                       for t in self._tasks.values())

    def get_all(self):
        with self._lock:
            return [dict(t) for t in self._tasks.values()]

    def get_results_summary(self):
        with self._lock:
            parts = []
            for task in self._tasks.values():
                status = "done" if task["status"] == self.COMPLETED else "FAILED"
                result_text = task["result"] or "(no output)"
                parts.append(
                    f"### Task: {task['title']} [{status}]\n"
                    f"Assigned to: {task['assignee'] or 'unassigned'}\n"
                    f"Result:\n{result_text}\n"
                )
            return "\n---\n".join(parts)


# ── Team Task Assignment ─────────────────────────────────────────────────────

def _score_agent_for_task(agent_config, task_description):
    """Score how well an agent matches a task via keyword overlap."""
    expertise = agent_config["expertise"].lower()
    desc_lower = task_description.lower()
    expertise_words = set(re.findall(r'\w+', expertise))
    desc_words = set(re.findall(r'\w+', desc_lower))
    overlap = expertise_words & desc_words
    substring_hits = sum(1 for w in expertise_words if len(w) > 3 and w in desc_lower)
    return len(overlap) + substring_hits


def _assign_tasks(tasks, agents):
    """Assign unassigned tasks to agents via capability matching."""
    agent_names = list(agents.keys())
    if not agent_names:
        return
    for task in tasks:
        if task.get("assignee") and task["assignee"] in agents:
            continue
        best_agent = None
        best_score = -1
        for name, config in agents.items():
            score = _score_agent_for_task(config, task["description"])
            if score > best_score:
                best_score = score
                best_agent = name
        task["assignee"] = best_agent or agent_names[0]


# ── Coordinator Prompts ──────────────────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
You are a team coordinator. You manage a team of specialist agents:
{roster_desc}

Decompose the following goal into tasks, each assigned to the best agent.
Tasks can depend on other tasks (by title).

Respond with ONLY a JSON array. No other text.
Each task: {{"title": "short name", "description": "detailed instructions", \
"assignee": "agent_name", "depends_on": ["prerequisite title"]}}

Rules:
- Create 2 to {max_tasks} tasks.
- Use depends_on to order tasks that need results from earlier tasks.
- Tasks with no dependencies run in parallel.
- Make descriptions detailed enough for independent work.

Goal: {goal}"""


_SYNTHESIZE_PROMPT = """\
Your specialist agents have completed their tasks.

## Task Results
{results_summary}

## Shared Memory
{memory_summary}

Synthesize ALL results into a comprehensive, well-structured final answer \
that fully addresses the original goal. Integrate insights from all agents. \
Resolve any contradictions. Present the information clearly.

Original goal: {goal}

Provide your synthesized answer directly (no JSON, just the final text)."""


# ── Coordinator Functions ────────────────────────────────────────────────────

def _decompose_goal(goal, agents, config, skill_config):
    """Use the coordinator LLM to decompose a goal into tasks."""
    model_override = skill_config.get("model_override", "").strip() or ""

    roster_lines = []
    for name, cfg in agents.items():
        roster_lines.append(f"- {name}: {cfg['expertise']}")
    roster_desc = "\n".join(roster_lines)

    prompt = _DECOMPOSE_PROMPT.format(
        roster_desc=roster_desc,
        max_tasks=len(agents) + 2,
        goal=goal,
    )

    char_name, personality = _get_character_info()
    personality_line = ""
    if personality:
        personality_line = (
            f" You are coordinating on behalf of {char_name}. "
            f"Keep this personality in mind: {personality[:300]}"
        )

    messages = [
        {"role": "system", "content":
            f"You are a task decomposition engine. Output ONLY valid JSON.{personality_line}"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _agent_llm_call(messages, config, model_override,
                              max_tokens_override=1200, temp_mod_override=0.0)
        return _parse_task_specs(raw)
    except Exception as e:
        queue_message(f"TEAM: Coordinator decomposition failed: {e}")
        return None


def _parse_task_specs(raw_text):
    """Extract a JSON array of task specs from coordinator output."""
    raw_text = raw_text.strip()
    raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
    raw_text = re.sub(r'\s*```$', '', raw_text)
    raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "tasks" in result:
            return result["tasks"]
    except json.JSONDecodeError:
        pass

    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start != -1 and end > start:
        try:
            result = json.loads(raw_text[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return None


def _synthesize_results(goal, task_queue, shared_memory, config, skill_config):
    """Coordinator synthesizes all task results into a final answer."""
    model_override = skill_config.get("model_override", "").strip() or ""

    prompt = _SYNTHESIZE_PROMPT.format(
        results_summary=task_queue.get_results_summary(),
        memory_summary=shared_memory.get_summary() or "(empty)",
        goal=goal,
    )

    char_name, personality = _get_character_info()
    personality_line = ""
    if personality:
        personality_line = (
            f" You are synthesizing on behalf of {char_name}. "
            f"Maintain this personality: {personality[:300]}"
        )

    messages = [
        {"role": "system", "content":
            f"You are a synthesis expert. Combine all team results into one "
            f"clear, comprehensive answer.{personality_line}"},
        {"role": "user", "content": prompt},
    ]

    try:
        return _agent_llm_call(messages, config, model_override,
                               max_tokens_override=1500, temp_mod_override=0.0)
    except Exception as e:
        queue_message(f"TEAM: Synthesis failed: {e}")
        return task_queue.get_results_summary()


# ── Team Agent Runner ────────────────────────────────────────────────────────

def _build_team_agent_prompt(agent_config, task, shared_memory, max_steps,
                             skill_config):
    """Build a specialist agent's system prompt for team mode."""
    char_name, personality = _get_character_info()

    # Build tool list (all available tools)
    tools = _get_available_tools(depth=_MAX_DEPTH)  # no sub_agent in team mode
    tool_lines = []
    for name, info in tools.items():
        if name == "sub_agent":
            continue  # team agents don't spawn sub-agents
        tool_lines.append(f"- {name}: {info['desc']}\n  Parameters: {info['params']}")
    tool_list = "\n".join(tool_lines) if tool_lines else "(No tools)"

    # Shared memory context
    mem_summary = shared_memory.get_summary()
    context_block = f"\n{mem_summary}\n" if mem_summary else ""

    # Reasoning style
    style = skill_config.get("reasoning_style", "balanced")
    style_cfg = _STYLE_CONFIGS.get(style, _STYLE_CONFIGS["balanced"])
    style_addon = f"\n## Reasoning style\n{style_cfg['addon']}\n" if style_cfg["addon"] else ""

    personality_block = ""
    if personality:
        personality_block = (
            f"\n## Team personality\n"
            f"You are part of {char_name}'s team. Maintain this personality:\n"
            f"{personality}\n"
        )

    return (
        f"You are {agent_config['name']}, a specialist agent on {char_name}'s team.\n"
        f"Your expertise: {agent_config['expertise']}\n\n"
        f"{agent_config['system_prompt']}\n"
        f"{personality_block}\n"
        f"## Available tools\n{tool_list}\n\n"
        f"## Response format\n"
        f"Respond with EXACTLY ONE JSON object per turn:\n"
        f"1. Use a tool: {{\"thought\": \"...\", \"action\": \"tool_name\", \"action_input\": {{...}}}}\n"
        f"2. Final answer: {{\"thought\": \"...\", \"answer\": \"your complete output for this task\"}}\n\n"
        f"## Rules\n"
        f"- You MUST answer within {max_steps} steps.\n"
        f"- Use observations to build toward your answer.\n"
        f"- Respond with raw JSON only. No markdown fences, no extra text.\n"
        f"- Focus only on YOUR assigned task. Be thorough but efficient.\n"
        f"- Use ask_user sparingly — only when you truly lack critical information.\n"
        f"{style_addon}"
        f"{context_block}"
    )


def _run_team_agent_task(agent_config, task, shared_memory, config, skill_config,
                         context):
    """Run a single specialist agent on a team task using the ReAct loop."""
    max_steps = int(skill_config.get("team_task_steps", 4))
    verbose = str(skill_config.get("verbose", "true")).lower() in ("true", "1", "yes")
    agent_name = agent_config["name"]

    if verbose:
        queue_message(f"TEAM[{agent_name}]: Starting '{task['title']}'")

    # Build specialist prompt and run through the shared ReAct loop
    system_prompt = _build_team_agent_prompt(
        agent_config, task, shared_memory, max_steps, skill_config)

    # Override timeout for team agent tasks
    team_skill_config = dict(skill_config)
    team_skill_config["overall_timeout"] = int(skill_config.get("team_timeout", 180))

    result = _run_agent_loop(
        goal=f"Task: {task['title']}\n\nDetails: {task['description']}",
        max_steps=max_steps,
        config=config,
        skill_config=team_skill_config,
        context=context,
        depth=1,  # team agents are depth 1 (no sub-agents)
        emit_ui=False,
        system_prompt=system_prompt,
    )

    if verbose:
        queue_message(f"TEAM[{agent_name}]: Completed '{task['title']}' "
                      f"({len(result)} chars)")
    return result


# ── Team Orchestration Loop ──────────────────────────────────────────────────

def _run_team(goal, config, skill_config, context):
    """Main team orchestration: decompose -> execute -> synthesize."""
    verbose = str(skill_config.get("verbose", "true")).lower() in ("true", "1", "yes")
    concurrency = int(skill_config.get("team_concurrency", 3))
    team_timeout = int(skill_config.get("team_timeout", 180))
    start_time = time.time()

    agents = dict(_AGENT_ROSTER)
    shared_memory = _SharedMemory()
    task_queue = _TaskQueue()

    # ── Phase 1: Decompose ──
    if verbose:
        queue_message("TEAM: Coordinator decomposing goal into tasks...")
    _emit_agent_event("team_start", {"goal": goal})

    task_specs = _decompose_goal(goal, agents, config, skill_config)

    if not task_specs:
        queue_message("TEAM: Decomposition failed, using fallback tasks")
        task_specs = [
            {"title": "Research", "description": goal,
             "assignee": "researcher", "depends_on": []},
            {"title": "Analysis", "description": f"Analyze findings about: {goal}",
             "assignee": "analyst", "depends_on": ["Research"]},
            {"title": "Report", "description": f"Write a report about: {goal}",
             "assignee": "writer", "depends_on": ["Analysis"]},
        ]

    for spec in task_specs:
        task_queue.add_task(
            title=spec.get("title", "Untitled"),
            description=spec.get("description", goal),
            assignee=spec.get("assignee"),
            depends_on=spec.get("depends_on") or spec.get("dependsOn") or [],
        )
    task_queue.resolve_dependencies()

    # Assign unassigned tasks directly on originals
    with task_queue._lock:
        _assign_tasks(list(task_queue._tasks.values()), agents)

    if verbose:
        for t in task_queue.get_all():
            deps = t["depends_on_titles"]
            dep_str = f" (after: {', '.join(deps)})" if deps else ""
            queue_message(f"TEAM: Task '{t['title']}' -> {t['assignee']}{dep_str}")

    _emit_agent_event("team_decomposed", {
        "tasks": [{"title": t["title"], "assignee": t["assignee"],
                    "status": t["status"]} for t in task_queue.get_all()],
    })

    # ── Phase 2: Execute in dependency-aware batches ──
    batch_num = 0
    empty_polls = 0
    max_empty_polls = 20

    while not task_queue.is_done():
        elapsed = time.time() - start_time
        if elapsed > team_timeout:
            queue_message(f"TEAM: Timeout ({team_timeout}s) exceeded")
            break

        # Barge-in detection
        try:
            from modules.module_state import get_tars_state, TarsState
            if get_tars_state() == TarsState.LISTENING:
                queue_message("TEAM: Aborting — user barge-in detected")
                return ("(Team interrupted because you started speaking. "
                        "Ask again if you'd like me to continue.)")
        except Exception:
            pass

        pending = task_queue.get_pending()
        if not pending:
            remaining = [t for t in task_queue.get_all()
                         if t["status"] in (_TaskQueue.BLOCKED, _TaskQueue.IN_PROGRESS)]
            if not remaining:
                break
            empty_polls += 1
            if empty_polls >= max_empty_polls:
                queue_message("TEAM: WARNING — Tasks stuck. Aborting wait.")
                break
            time.sleep(0.5)
            continue
        empty_polls = 0

        batch_num += 1
        if verbose:
            queue_message(f"TEAM: Batch {batch_num} — {[t['title'] for t in pending]}")

        for task in pending:
            task_queue.mark_in_progress(task["id"])

        with ThreadPoolExecutor(max_workers=min(len(pending), concurrency)) as pool:
            futures = {}
            for task in pending:
                assignee = task["assignee"] or "researcher"
                agent_config = agents.get(assignee)
                if agent_config is None:
                    queue_message(f"TEAM: WARNING — Unknown agent '{assignee}', "
                                  f"using researcher")
                    agent_config = agents["researcher"]
                f = pool.submit(
                    _run_team_agent_task,
                    agent_config, task, shared_memory, config, skill_config,
                    context,
                )
                futures[f] = task

            remaining_timeout = team_timeout - (time.time() - start_time)
            try:
                for f in as_completed(futures, timeout=max(remaining_timeout, 10)):
                    task = futures[f]
                    try:
                        result = f.result(timeout=30)
                        # Truncate very long results
                        if len(result) > 3000:
                            result = result[:3000] + "\n\n[... truncated ...]"
                        shared_memory.write(
                            task["assignee"] or "unknown",
                            f"task:{task['title']}",
                            result,
                        )
                        task_queue.complete(task["id"], result)
                        if verbose:
                            queue_message(f"TEAM: '{task['title']}' done "
                                          f"({len(result)} chars)")
                        _emit_agent_event("team_task_complete", {
                            "task": task["title"],
                            "agent": task["assignee"],
                        })
                    except Exception as e:
                        task_queue.fail(task["id"], str(e))
                        queue_message(f"TEAM: '{task['title']}' FAILED: {e}")
            except TimeoutError:
                for f, task in futures.items():
                    if not f.done():
                        task_queue.fail(task["id"], "timed out")
                        queue_message(f"TEAM: '{task['title']}' timed out")

    # ── Phase 3: Synthesize ──
    elapsed = time.time() - start_time
    completed = sum(1 for t in task_queue.get_all()
                    if t["status"] == _TaskQueue.COMPLETED)
    total = len(task_queue.get_all())
    if verbose:
        queue_message(f"TEAM: {completed}/{total} tasks done in {elapsed:.1f}s. "
                      "Synthesizing...")

    final_answer = _synthesize_results(goal, task_queue, shared_memory,
                                       config, skill_config)

    if verbose:
        queue_message(f"TEAM: Complete in {time.time() - start_time:.1f}s")

    _emit_agent_event("team_complete", {
        "elapsed": round(time.time() - start_time, 1),
    })

    shared_memory.clear()
    return final_answer


# ── Team Mode Routing ────────────────────────────────────────────────────────

def _should_use_team(goal, config, skill_config):
    """Quick LLM check: does this goal benefit from parallel specialists?"""
    model_override = skill_config.get("model_override", "").strip() or ""

    messages = [
        {"role": "system", "content": (
            "You are a routing classifier. Respond with ONLY the word "
            "SINGLE or TEAM. Nothing else.\n\n"
            "SINGLE: The goal can be solved by one agent working step-by-step "
            "(sequential research, simple lookups, calculations, single-domain tasks).\n\n"
            "TEAM: The goal genuinely benefits from multiple specialists working "
            "in parallel (multi-domain analysis, compare from different perspectives, "
            "tasks requiring both research AND coding AND writing, complex projects)."
        )},
        {"role": "user", "content": f"Goal: {goal}"},
    ]

    try:
        raw = _agent_llm_call(messages, config, model_override,
                              max_tokens_override=10, temp_mod_override=0.0)
        decision = raw.strip().upper()
        use_team = "TEAM" in decision
        queue_message(f"AGENT: Route -> {'TEAM' if use_team else 'SINGLE'}")
        return use_team
    except Exception as e:
        queue_message(f"AGENT: Routing failed ({e}), defaulting to single")
        return False


# ── Main Execute ─────────────────────────────────────────────────────────────

def execute(parameters, context):
    """Entry point — route to single-agent or team mode."""
    goal = parameters.get("goal", "")
    if not goal:
        return "No goal provided for the agent."

    skill_config = context.get("skill_config", {})
    config = load_config()

    team_mode = skill_config.get("team_mode", "auto")

    # Decide: single agent or team
    use_team = False
    if team_mode == "always":
        use_team = True
    elif team_mode == "auto":
        use_team = _should_use_team(goal, config, skill_config)
    # team_mode == "never" → use_team stays False

    if use_team:
        overall_timeout = int(skill_config.get("team_timeout", 180))
    else:
        overall_timeout = int(skill_config.get("overall_timeout", 120))

    # Heartbeat watchdog
    watchdog_id = f"agent_task_{id(goal)}_{threading.current_thread().ident}"
    try:
        from modules.module_heartbeat import schedule_once
        schedule_once(
            task_id=watchdog_id,
            delay_seconds=overall_timeout + 15,
            callback=lambda: queue_message(
                f"AGENT: WATCHDOG — hard timeout ({overall_timeout}s) exceeded"),
        )
    except Exception:
        pass

    try:
        if use_team:
            return _run_team(
                goal=goal, config=config,
                skill_config=skill_config, context=context)
        else:
            max_steps = int(skill_config.get("max_steps", 6))
            return _run_agent_loop(
                goal=goal, max_steps=max_steps,
                config=config, skill_config=skill_config,
                context=context, depth=0, emit_ui=True)
    finally:
        try:
            from modules.module_heartbeat import cancel_task
            cancel_task(watchdog_id)
        except Exception:
            pass
