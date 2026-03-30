"""
Skill: agent_task — Autonomous multi-step agent (ReAct loop).

Gives TARS the ability to break down complex tasks and solve them
step-by-step using other skills as tools (web search, code execution,
home assistant, vision, etc.).  Inspired by AgentZero / MoltBot.

Flow:
  1. User asks something complex ("research X and summarize", "plan a trip", etc.)
  2. LLM triggers agent_task with the goal.
  3. This skill runs a ReAct loop:
       THINK  → reason about what to do next
       ACT    → call a TARS skill (web_search, sandbox_exec, …)
       OBSERVE → read the result
       repeat until ANSWER or max steps
  4. Returns the final answer to TARS for TTS.
"""

import json
import time
import requests
from modules.module_messageQue import queue_message
from modules.module_config import load_config


# ── Skill definition ─────────────────────────────────────────────────────────

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


# ── Tool registry: maps TARS skill names to agent-friendly descriptions ──────

_TOOL_DESCRIPTIONS = {
    "web_search": {
        "desc": "Search the web for current information.",
        "params": '{"query": "search terms"}',
    },
    "sandbox_exec": {
        "desc": "Execute Python code (math, data processing, logic). Use print() for output.",
        "params": '{"code": "python code", "description": "what it does"}',
    },
    "home_assistant": {
        "desc": "Control smart home devices via Home Assistant.",
        "params": '{"prompt": "natural language command"}',
    },
    "capture_camera_view": {
        "desc": "Take a photo with the camera and describe what is visible.",
        "params": '{"prompt": "what to look for"}',
    },
    "generate_image": {
        "desc": "Generate an image from a text description.",
        "params": '{"prompt": "image description"}',
    },
    "browser": {
        "desc": "Open a URL or play a YouTube video.",
        "params": '{"action": "open_url|play_youtube", "url": "...", "query": "..."}',
    },
}


def _get_available_tools():
    """Build the tool list from currently enabled TARS skills."""
    try:
        from modules.module_skills import get_skill_manager
        sm = get_skill_manager()
        if not sm:
            return {}
        enabled = sm.get_skill_names()
        tools = {}
        for name in enabled:
            if name == "agent_task":
                continue  # don't let the agent call itself
            if name in _TOOL_DESCRIPTIONS:
                tools[name] = _TOOL_DESCRIPTIONS[name]
            else:
                # Auto-generate a basic entry from skill metadata
                meta = sm._skill_meta.get(name, {})
                desc = meta.get("description", f"Skill: {name}")
                tools[name] = {"desc": desc, "params": "{}"}
        return tools
    except Exception as e:
        queue_message(f"AGENT: Failed to list tools: {e}")
        return {}


# ── Agent system prompt ──────────────────────────────────────────────────────

_AGENT_SYSTEM = """You are an autonomous reasoning agent. You solve tasks step-by-step using available tools.

## Available tools
{tool_list}

## Response format
You MUST respond with EXACTLY ONE valid JSON object per turn. Pick one:

1. To use a tool:
{{"thought": "your reasoning about what to do next", "action": "tool_name", "action_input": {{...tool parameters...}}}}

2. To give the final answer (when you have enough information):
{{"thought": "summarizing what I found", "answer": "your complete final answer to the user's goal"}}

## Rules
- Think step by step. Each turn you get ONE action.
- After each action, you will see the result as an OBSERVATION.
- Use observations to inform your next step.
- When you have enough information, provide the final answer.
- Be concise in thoughts. Focus on what matters.
- If a tool fails, try a different approach.
- You MUST answer within {max_steps} steps.
- IMPORTANT: Respond with raw JSON only. No markdown, no code fences, no extra text."""


def _build_system_prompt(max_steps):
    """Build the agent system prompt with available tools."""
    tools = _get_available_tools()
    if not tools:
        tool_list = "(No tools available — reason from your own knowledge.)"
    else:
        lines = []
        for name, info in tools.items():
            lines.append(f"- {name}: {info['desc']}\n  Parameters: {info['params']}")
        tool_list = "\n".join(lines)
    return _AGENT_SYSTEM.format(tool_list=tool_list, max_steps=max_steps)


# ── LLM call (reuses TARS config) ───────────────────────────────────────────

def _agent_llm_call(messages, model_override=""):
    """Make an LLM chat completion call for the agent loop."""
    config = load_config()
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

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": 800,
        "temperature": float(config['LLM'].get('temperature', 0.5)),
    }

    resp = requests.post(url, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"].strip()


# ── Tool execution (delegates to TARS SkillManager) ─────────────────────────

def _execute_tool(tool_name, tool_input, context):
    """Execute a TARS skill and return the observation string."""
    try:
        from modules.module_skills import get_skill_manager
        sm = get_skill_manager()
        if not sm or not sm.has_skill(tool_name):
            return f"Error: Unknown tool '{tool_name}'"

        if not sm.is_enabled(tool_name):
            return f"Error: Tool '{tool_name}' is disabled"

        # Build a minimal context for the sub-skill
        sub_context = {
            "bot_response": context.get("bot_response", {}),
            "user_input": context.get("user_input", ""),
            "source": context.get("source", "voice"),
            "has_image": context.get("has_image", False),
            "config": context.get("config", {}),
        }

        result = sm.execute(tool_name, tool_input, sub_context)
        if result is None:
            return "(Tool returned no output)"
        return str(result)[:2000]  # cap observation length

    except Exception as e:
        return f"Error executing {tool_name}: {e}"


# ── Parse agent JSON response ───────────────────────────────────────────────

def _parse_agent_response(text):
    """Parse the agent's JSON response. Returns dict or None."""
    text = text.strip()
    # Strip markdown code fences if the LLM wraps them
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from surrounding text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ── Status emission ──────────────────────────────────────────────────────────

def _emit_status(status, step=0, max_steps=0, thought="", action=""):
    """Emit agent status to web UI via SocketIO."""
    try:
        from modules.module_chatui import socketio
        socketio.emit('skill_status', {
            'skill': 'agent_task',
            'status': status,
            'description': f"Step {step}/{max_steps}: {action}" if step else status,
            'output': thought[:300] if thought else "",
        })
    except Exception:
        pass


# ── Main execute ─────────────────────────────────────────────────────────────

def execute(parameters, context):
    """Run the autonomous agent loop. Returns the final answer string."""
    goal = parameters.get("goal", "")
    if not goal:
        return "No goal provided for the agent."

    skill_config = context.get("skill_config", {})
    max_steps = int(skill_config.get("max_steps", 6))
    model_override = skill_config.get("model_override", "").strip() or ""
    verbose = str(skill_config.get("verbose", "true")).lower() in ("true", "1", "yes")

    queue_message(f"AGENT: Starting — goal: {goal}")
    queue_message(f"AGENT: Max steps: {max_steps}, model override: {model_override or '(default)'}")
    _emit_status("running", thought=f"Goal: {goal}")

    system_prompt = _build_system_prompt(max_steps)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Goal: {goal}"},
    ]

    for step in range(1, max_steps + 1):
        if verbose:
            queue_message(f"AGENT: Step {step}/{max_steps}")

        # Ask the LLM for next action
        try:
            raw = _agent_llm_call(messages, model_override)
        except Exception as e:
            queue_message(f"AGENT: LLM call failed at step {step}: {e}")
            _emit_status("failed", step, max_steps, thought=str(e))
            return f"Agent encountered an error while reasoning: {e}"

        parsed = _parse_agent_response(raw)
        if parsed is None:
            # LLM returned unparseable text — treat as final answer
            queue_message(f"AGENT: Unparseable response at step {step}, treating as answer")
            _emit_status("completed", step, max_steps)
            return raw[:2000]

        thought = parsed.get("thought", "")
        if verbose and thought:
            queue_message(f"AGENT: Think → {thought[:200]}")

        # ── Final answer ──
        if "answer" in parsed:
            answer = parsed["answer"]
            queue_message(f"AGENT: Finished at step {step} — answer length: {len(answer)}")
            _emit_status("completed", step, max_steps, thought=thought)
            return answer

        # ── Tool action ──
        action = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        if not action:
            # No action and no answer — malformed, ask to continue
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Please respond with valid JSON containing either an 'action' or 'answer' field."})
            continue

        if verbose:
            queue_message(f"AGENT: Act → {action}({json.dumps(action_input)[:200]})")
        _emit_status("running", step, max_steps, thought=thought, action=action)

        # Execute the tool
        if isinstance(action_input, str):
            try:
                action_input = json.loads(action_input)
            except (json.JSONDecodeError, TypeError):
                action_input = {"query": action_input}

        observation = _execute_tool(action, action_input, context)
        if verbose:
            queue_message(f"AGENT: Observe → {observation[:300]}")

        # Append to conversation
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"OBSERVATION:\n{observation}"})

    # ── Hit max steps — force a final answer ──
    queue_message(f"AGENT: Hit max steps ({max_steps}), forcing final answer")
    messages.append({
        "role": "user",
        "content": "You have reached the maximum number of steps. You MUST provide your final answer NOW using the {\"thought\": \"...\", \"answer\": \"...\"} format. Summarize everything you've learned so far.",
    })

    try:
        raw = _agent_llm_call(messages, model_override)
        parsed = _parse_agent_response(raw)
        if parsed and "answer" in parsed:
            _emit_status("completed", max_steps, max_steps)
            return parsed["answer"]
        _emit_status("completed", max_steps, max_steps)
        return raw[:2000]
    except Exception as e:
        _emit_status("failed", max_steps, max_steps, thought=str(e))
        return f"Agent could not complete the task: {e}"
