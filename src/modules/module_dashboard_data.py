"""
Module: Dashboard Data
Lightweight JSON-based interaction logger for the dashboard.
Records each conversation turn with timestamp, emotion, speaker,
and the full LLM prompt so the dashboard can display mood timelines,
audit logs, prompt debugger, and analytics without modifying any
existing modules.
"""
import os
import json
import math
import threading
from datetime import datetime

_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
_LOG_FILE = os.path.join(_MEMORY_DIR, "interaction_log.json")
_PROMPT_DIR = os.path.join(_MEMORY_DIR, "prompt_history")
_MAX_ENTRIES = 500
_lock = threading.Lock()

# ── Emotional state (derived from recent interactions) ────────────────────────
# Instead of accumulating scores, we compute the radar on the fly from the
# last N log entries weighted by recency.  Recent messages dominate; old ones
# fade with a configurable half-life.
_EMO_WINDOW = 50         # max interactions to consider
_EMO_HALF_LIFE = 1800    # seconds (30 min) — message from 30min ago = half weight

# Map GoEmotions labels → 8 radar axes.  Multiple classifier labels feed
# into the same axis so the radar stays readable.
_RADAR_AXES = ["joy", "anger", "sadness", "fear", "love", "curiosity", "surprise", "neutral"]

_EMOTION_TO_AXIS = {
    # joy
    "joy": "joy", "amusement": "joy", "excitement": "joy", "optimism": "joy",
    "pride": "joy", "relief": "joy",
    # anger
    "anger": "anger", "annoyance": "anger", "disapproval": "anger", "disgust": "anger",
    # sadness
    "sadness": "sadness", "disappointment": "sadness", "grief": "sadness",
    "remorse": "sadness", "embarrassment": "sadness",
    # fear
    "fear": "fear", "nervousness": "fear",
    # love
    "love": "love", "admiration": "love", "caring": "love",
    "desire": "love", "gratitude": "love", "approval": "love",
    # curiosity
    "curiosity": "curiosity", "confusion": "curiosity", "realization": "curiosity",
    # surprise
    "surprise": "surprise",
    # neutral
    "neutral": "neutral",
}

# ── In-memory cache for fast radar lookups ────────────────────────────────────
# Holds the last _EMO_WINDOW entries with axis_scores so get_emotional_state()
# doesn't re-read the log file every call.
_emo_cache = []       # list of (timestamp_float, axis_scores_dict)
_emo_cache_lock = threading.Lock()


def get_emotional_state():
    """Compute the current emotional radar from recent cached interactions.

    Each entry is weighted by recency using exponential decay with _EMO_HALF_LIFE.
    Returns {axis: 0-100} for all 8 radar axes.
    """
    with _emo_cache_lock:
        cache = list(_emo_cache)

    if not cache:
        return {a: 0 for a in _RADAR_AXES}

    now = datetime.now().timestamp()
    decay_rate = math.log(2) / _EMO_HALF_LIFE
    totals = {a: 0.0 for a in _RADAR_AXES}
    weight_sum = 0.0

    for ts, scores in cache:
        age = max(0, now - ts)
        w = math.exp(-decay_rate * age)
        weight_sum += w
        for axis, val in scores.items():
            if axis in totals:
                totals[axis] += val * w

    # Normalize to 0-100: divide by weight_sum to get weighted average,
    # then scale (raw axis scores are 0-1 summed probabilities)
    result = {}
    for axis in _RADAR_AXES:
        if weight_sum > 0:
            avg = totals[axis] / weight_sum    # 0-1 range
            result[axis] = round(min(100, avg * 100))
        else:
            result[axis] = 0
    return result


def _rebuild_emo_cache():
    """Rebuild the in-memory emotion cache from the interaction log.

    Called once at first access.  After that, new entries are appended directly.
    """
    entries = _load_log()
    cache = []
    for e in entries[-_EMO_WINDOW:]:
        scores = e.get("axis_scores")
        ts_str = e.get("ts", "")
        if scores and ts_str:
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                cache.append((ts, scores))
            except ValueError:
                pass
    return cache


def _load_log():
    """Load the interaction log from disk."""
    if os.path.exists(_LOG_FILE):
        try:
            with open(_LOG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_log(entries):
    """Save the interaction log to disk (trimmed to MAX_ENTRIES)."""
    trimmed = entries[-_MAX_ENTRIES:]
    try:
        with open(_LOG_FILE, 'w') as f:
            json.dump(trimmed, f, indent=None, separators=(',', ':'))
    except IOError:
        pass


def _read_last_prompt():
    """Read the most recently built prompt from the dump file."""
    try:
        dump_path = os.path.join(_MEMORY_DIR, "last_prompt.txt")
        if os.path.exists(dump_path):
            with open(dump_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception:
        pass
    return ''


def _save_prompt(entry_id, prompt_text):
    """Save a prompt to the prompt history directory."""
    try:
        os.makedirs(_PROMPT_DIR, exist_ok=True)
        path = os.path.join(_PROMPT_DIR, f"{entry_id}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(prompt_text)
    except Exception:
        pass


def _cleanup_old_prompts(keep_ids):
    """Remove prompt files not in the keep set."""
    try:
        if not os.path.isdir(_PROMPT_DIR):
            return
        for fname in os.listdir(_PROMPT_DIR):
            if fname.endswith('.txt'):
                fid = fname[:-4]
                if fid not in keep_ids:
                    os.remove(os.path.join(_PROMPT_DIR, fname))
    except Exception:
        pass


def log_interaction(user_input, bot_response, emotion=None, emotion_raw=None, axis_scores=None, speaker=None):
    """Record a single conversation turn with its full prompt."""
    global _emo_cache
    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "id": entry_id,
        "ts": now_str,
        "user": user_input,
        "bot": bot_response,
    }
    if emotion:
        entry["emotion"] = emotion
    if emotion_raw:
        entry["emotion_raw"] = emotion_raw
    if axis_scores:
        entry["axis_scores"] = axis_scores
    if speaker:
        entry["speaker"] = speaker

    # Capture the prompt that was just built
    prompt_text = _read_last_prompt()
    if prompt_text:
        entry["has_prompt"] = True
        _save_prompt(entry_id, prompt_text)

    with _lock:
        entries = _load_log()
        entries.append(entry)
        _save_log(entries)
        # Clean up prompt files for entries that were trimmed
        keep = {e.get("id", "") for e in entries[-_MAX_ENTRIES:]}
        _cleanup_old_prompts(keep)

    # Update in-memory emotion cache
    if axis_scores:
        ts_float = datetime.now().timestamp()
        with _emo_cache_lock:
            _emo_cache.append((ts_float, axis_scores))
            # Trim to window size
            if len(_emo_cache) > _EMO_WINDOW:
                _emo_cache = _emo_cache[-_EMO_WINDOW:]


def get_interactions(limit=100):
    """Return the most recent interactions."""
    with _lock:
        entries = _load_log()
    return entries[-limit:]


def get_prompt_for_interaction(entry_id):
    """Load the full prompt for a specific interaction."""
    try:
        path = os.path.join(_PROMPT_DIR, f"{entry_id}.txt")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception:
        pass
    return None


def get_mood_analytics():
    """Compute mood counts, timeline, activity heatmap, and hourly totals."""
    entries = _load_log()

    mood_counts = {}
    timeline = []
    activity_by_hour = {}
    activity_heatmap = {}  # "day_hour" → count (e.g. "Mon_14": 3)

    for e in entries:
        mood = e.get("emotion")
        mood_raw = e.get("emotion_raw", mood)
        ts = e.get("ts", "")

        if mood:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
            timeline.append({"timestamp": ts, "mood": mood_raw or mood, "axis": mood})

        # Parse day+hour for heatmap and hour for legacy chart
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            hour = str(dt.hour)
            activity_by_hour[hour] = activity_by_hour.get(hour, 0) + 1
            # Heatmap key: "day_hour" (day 0=Mon, 6=Sun)
            hkey = f"{dt.weekday()}_{dt.hour}"
            activity_heatmap[hkey] = activity_heatmap.get(hkey, 0) + 1
        except (ValueError, IndexError):
            pass

    return {
        "mood_counts": mood_counts,
        "timeline": timeline[-50:],
        "activity_by_hour": activity_by_hour,
        "activity_heatmap": activity_heatmap,
    }


# ── Lazy-init: rebuild cache from log on first access ─────────────────────────
def _ensure_cache():
    global _emo_cache
    with _emo_cache_lock:
        if not _emo_cache:
            _emo_cache = _rebuild_emo_cache()

_ensure_cache()
