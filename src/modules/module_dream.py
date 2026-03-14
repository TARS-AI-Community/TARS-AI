"""
Module: Dream Consolidation
Nightly memory consolidation — summarizes recent interactions, extracts themes
and emotional arcs, and stores compressed "dream memories" in HyperDB.
Runs at most once per day, triggered when the screensaver activates.
"""
import os
import json
import time
import threading
import requests
from datetime import datetime, timedelta

from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
_STATE_FILE = os.path.join(_MEMORY_DIR, "dream_state.json")

_lock = threading.Lock()
_running = False

# ── State persistence ────────────────────────────────────────────────────────

def _load_state():
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_dream": None, "dream_count": 0}


def _save_state(state):
    try:
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        with open(_STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        queue_message(f"DREAM: Failed to save state: {e}")


def _already_dreamed_today():
    state = _load_state()
    last = state.get("last_dream")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return last_dt.date() == datetime.now().date()
    except Exception:
        return False


# ── Consolidation prompt ─────────────────────────────────────────────────────

_CONSOLIDATION_PROMPT = """You are analyzing a day's worth of conversations for memory consolidation.

Below are recent interactions (user messages and bot responses) with timestamps and emotions.

Summarize them into a compact dream memory with these sections:
1. **Themes**: 2-4 key topics or themes discussed (brief phrases)
2. **Emotional Arc**: How the emotional tone shifted through the day (1-2 sentences)
3. **Key Memories**: 2-3 specific moments worth remembering long-term (brief descriptions)
4. **People**: Names of anyone who interacted (if identifiable)

Be concise. Total output should be under 200 words. Output as JSON:
{
  "themes": ["theme1", "theme2"],
  "emotional_arc": "Started curious, shifted to joyful after discussing...",
  "key_memories": ["memory1", "memory2"],
  "people": ["name1"]
}

Here are the interactions:
"""


def _build_interaction_summary():
    """Pull last 24h of interactions from the dashboard log."""
    try:
        from modules.module_dashboard_data import get_interactions
        entries = get_interactions(limit=100)
    except Exception:
        return None

    cutoff = datetime.now() - timedelta(hours=24)
    recent = []
    for e in entries:
        ts_str = e.get("ts", "")
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if ts < cutoff:
                continue
        except ValueError:
            continue

        user = e.get("user", "")
        bot = e.get("bot", "")
        emotion = e.get("emotion", "")
        speaker = e.get("speaker", "")
        if not user and not bot:
            continue
        line = f"[{ts_str}]"
        if emotion:
            line += f" ({emotion})"
        if speaker:
            line += f" {speaker}: {user}"
        else:
            line += f" User: {user}"
        line += f"\n  Bot: {bot}"
        recent.append(line)

    if not recent:
        return None

    return "\n\n".join(recent[-40:])  # cap at 40 most recent


def _call_llm(prompt_text):
    """Make a lightweight LLM API call for dream consolidation."""
    llm_backend = CONFIG['LLM']['llm_backend']

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

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a memory consolidation assistant. Output valid JSON only."},
            {"role": "user", "content": prompt_text}
        ],
        "max_tokens": 500,
        "temperature": 0.7,
    }

    if llm_backend in ["openai", "grok", "deepinfra"]:
        data["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        queue_message(f"DREAM: LLM call failed: {e}")
        return None


# ── Public API ───────────────────────────────────────────────────────────────

def try_dream_consolidation():
    """Attempt nightly memory consolidation. Safe to call multiple times —
    will only run once per day, in a background thread.
    """
    global _running
    if _already_dreamed_today():
        return
    with _lock:
        if _running:
            return
        _running = True

    thread = threading.Thread(target=_run_consolidation, daemon=True)
    thread.start()


def _run_consolidation():
    """Background thread: summarize the day and store dream memory."""
    global _running
    try:
        queue_message("DREAM: Starting dream consolidation...")

        summary = _build_interaction_summary()
        if not summary:
            queue_message("DREAM: No recent interactions to consolidate.")
            return

        prompt = _CONSOLIDATION_PROMPT + summary
        result = _call_llm(prompt)
        if not result:
            return

        # Parse the LLM response
        try:
            dream = json.loads(result)
        except json.JSONDecodeError:
            queue_message(f"DREAM: Failed to parse LLM response as JSON")
            return

        # Store the dream memory in HyperDB
        _store_dream(dream)

        # Update state
        state = _load_state()
        state["last_dream"] = datetime.now().isoformat()
        state["dream_count"] = state.get("dream_count", 0) + 1
        _save_state(state)

        themes = dream.get("themes", [])
        queue_message(f"DREAM: Consolidation complete — themes: {', '.join(themes)}")

    except Exception as e:
        queue_message(f"DREAM: Consolidation error: {e}")
    finally:
        with _lock:
            _running = False


def _store_dream(dream):
    """Write the dream summary into long-term memory (HyperDB)."""
    try:
        from modules.module_llm import memory_manager
        if memory_manager is None:
            queue_message("DREAM: Memory manager not available, skipping storage.")
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        themes = dream.get("themes", [])
        arc = dream.get("emotional_arc", "")
        memories = dream.get("key_memories", [])
        people = dream.get("people", [])

        # Build a compact dream document
        dream_text = f"[Dream Consolidation] Themes: {', '.join(themes)}. "
        dream_text += f"Emotional arc: {arc} "
        if memories:
            dream_text += f"Key memories: {'; '.join(memories)}. "
        if people:
            dream_text += f"People: {', '.join(people)}."

        document = {
            "timestamp": now,
            "bot_response": dream_text,
            "type": "dream",
        }

        memory_manager.hyper_db.add_document(document)
        memory_manager._mark_dirty()

        # Also update topic index with dream themes
        if themes:
            topic_json = json.dumps({"new_topics": themes})
            memory_manager.update_topic_index_with_ai_response(topic_json)

    except Exception as e:
        queue_message(f"DREAM: Failed to store dream memory: {e}")


def get_last_dream():
    """Return info about the most recent dream consolidation."""
    state = _load_state()
    return state
