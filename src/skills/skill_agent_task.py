"""
Skill: agent_task — Autonomous multi-step agent (ReAct loop).

Gives TARS the ability to break down complex tasks and solve them
step-by-step using other skills as tools.  Inspired by AgentZero / MoltBot.

Flow:
  1. User asks something complex ("research X and summarize", etc.)
  2. LLM triggers agent_task with the goal.
  3. This skill runs a ReAct loop:
       THINK  → reason about what to do next
       ACT    → call a tool (web search, code exec, memory, sub-agent, …)
       OBSERVE → read the result
       repeat until ANSWER or limits reached
  4. Returns the final answer to TARS for TTS.

Built-in agent tools (no TARS skill needed):
  - think           : internal reasoning step (no external action)
  - web_search_raw  : direct DuckDuckGo search (skips LLM summarisation)
  - recall          : query TARS long-term memory / topic index
  - remember        : save a fact to TARS long-term memory
  - ask_user        : ask the user a clarifying question and wait for response
  - sub_agent       : spawn a child agent for a sub-task

All enabled TARS skills are also available as tools automatically.

Features:
  - Barge-in detection (aborts if user starts speaking)
  - Heartbeat watchdog (hard timeout)
  - Parallel tool execution
  - Character personality injection
  - Conversation history / memory context
  - Configurable reasoning style (concise / balanced / thorough / creative)
  - Sub-agent spawning with depth limit
  - Rich SocketIO events for web UI
"""

import json
import time
import os
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.module_messageQue import queue_message
from modules.module_config import load_config


# ── Skill Definition ──────────────────────────────────────────────���──────────

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
    },

    "prompt": """agent_task
   Triggers: Use when the user's request requires MULTIPLE steps to complete, such as:
     * Research tasks: "research X and give me a summary", "find out about X and compare with Y"
     * Multi-step tasks: "look up the weather and then find indoor activities", "search for X, then calculate Y"
     * Planning tasks: "plan a trip to X", "help me figure out how to do X"
     * Analysis tasks: "analyze X and give me recommendations", "compare X vs Y"
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
    ],
}


# ── Constants & Shared State ─────────────────────────────────────────────────

# Reuse TCP+TLS connections across agent LLM requests
_http_session = requests.Session()

# ask_user synchronisation
_ask_event = threading.Event()
_ask_response = None
_socketio_registered = False

# Skills excluded from agent tool list (agent has built-in equivalents)
_EXCLUDE_FROM_AGENT = frozenset({"agent_task", "web_search"})

# Sub-agent nesting limit
_MAX_DEPTH = 2

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


# ── SocketIO Handler Registration (for ask_user) ────────────────────────────

def _ensure_socketio_handler():
    """Lazily register the SocketIO handler for ask_user web UI responses."""
    global _socketio_registered
    if _socketio_registered:
        return
    try:
        from modules.module_chatui import socketio

        @socketio.on('agent_user_response')
        def _handle_user_response(data):
            global _ask_response
            _ask_response = data.get('text', '')
            _ask_event.set()

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
    global _ask_response
    question = params.get("question", "")
    if not question:
        return "Error: No question provided."

    timeout = min(int(params.get("timeout", 20)), 30)
    source = context.get("source", "voice")

    _ask_event.clear()
    _ask_response = None

    # Emit to web UI
    _ensure_socketio_handler()
    _emit_agent_event("ask_user", {"question": question, "timeout": timeout})

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
    if _ask_event.wait(timeout=timeout):
        resp = _ask_response or ""
        if resp:
            _emit_agent_event("ask_user_response",
                              {"response": resp, "via": "webui"})
            return f"User responded: {resp}"
        return "(User sent empty response)"

    return (f"(No response received within {timeout}s. Continue with your "
            f"best judgement based on available information.)")


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

    # ── Character personality ──
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
                personality = f"\n## Your personality\n{persona_text[:500]}\n"
    except Exception:
        pass

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

def _agent_llm_call(messages, config, model_override="", style="balanced"):
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
    else:
        model = model_override or config['LLM'].get('openai_model', 'gpt-4o-mini')

    if llm_backend == "deepinfra":
        url = f"{base_url}/v1/openai/chat/completions"
    else:
        url = f"{base_url}/v1/chat/completions"

    style_cfg = _STYLE_CONFIGS.get(style, _STYLE_CONFIGS["balanced"])
    base_temp = float(config['LLM'].get('temperature', 0.5))
    temperature = max(0.0, min(1.5, base_temp + style_cfg["temp_mod"]))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": style_cfg["max_tokens"],
        "temperature": temperature,
    }

    resp = _http_session.post(url, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── Tool Dispatch ──────────────────────────────────────────────���─────────────

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
    """Emit a detailed agent event to the web UI via SocketIO.

    event_type: 'start', 'think', 'act', 'observe', 'complete',
                'error', 'ask_user', 'ask_user_response'
    """
    try:
        from modules.module_chatui import socketio
        socketio.emit('agent_step', {
            'type': event_type,
            **data,
            'timestamp': time.time(),
        })
    except Exception:
        pass


# ── Core Agent Loop ──────────────────────────────────────────────────────────

def _run_agent_loop(goal, max_steps, config, skill_config, context,
                    depth=0, emit_ui=True):
    """Core ReAct loop. Reusable for top-level execution and sub-agents."""
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

    # Build system prompt with personality, tools, memory context
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
            queue_message(f"{prefix}: Think → {thought[:200]}")
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
                    queue_message(f"{prefix}: Parallel → {action_names}")
                if emit_ui:
                    _emit_agent_event("act", {
                        "step": step, "actions": action_names,
                        "parallel": True,
                    })

                observation = _execute_parallel(
                    actions, context, config, skill_config, depth)

                if verbose:
                    queue_message(f"{prefix}: Observe → "
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
            queue_message(f"{prefix}: Act → {action}({input_preview})")
        if emit_ui:
            _emit_agent_event("act", {
                "step": step, "action": action,
                "input": json.dumps(action_input, default=str)[:300],
            })

        observation = _dispatch_tool(
            action, action_input, context, config, skill_config, depth)

        if verbose:
            queue_message(f"{prefix}: Observe → {observation[:300]}")
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


# ── Main Execute ─────────────────────────────────────────────────────────────

def execute(parameters, context):
    """Entry point — run the autonomous agent loop. Returns final answer."""
    goal = parameters.get("goal", "")
    if not goal:
        return "No goal provided for the agent."

    skill_config = context.get("skill_config", {})
    max_steps = int(skill_config.get("max_steps", 6))
    overall_timeout = int(skill_config.get("overall_timeout", 120))

    # Cache config once — avoids re-reading config.ini on every step
    config = load_config()

    # Heartbeat watchdog — hard timeout safety net
    watchdog_id = f"agent_task_{id(goal)}_{threading.current_thread().ident}"
    try:
        from modules.module_heartbeat import schedule_once
        schedule_once(
            task_id=watchdog_id,
            delay_seconds=overall_timeout + 10,
            callback=lambda: queue_message(
                f"AGENT: WATCHDOG — hard timeout ({overall_timeout}s) exceeded"),
        )
    except Exception:
        pass

    try:
        return _run_agent_loop(
            goal=goal,
            max_steps=max_steps,
            config=config,
            skill_config=skill_config,
            context=context,
            depth=0,
            emit_ui=True,
        )
    finally:
        # Always cancel the watchdog
        try:
            from modules.module_heartbeat import cancel_task
            cancel_task(watchdog_id)
        except Exception:
            pass
