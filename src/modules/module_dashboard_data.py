"""
Module: Dashboard Data
Lightweight interaction logger for the dashboard.
Records each conversation turn with timestamp, emotion, speaker,
and (for recent entries) the LLM prompt.

The log is kept in-memory and flushed to disk periodically via the
heartbeat module — no per-interaction file I/O.  Prompts are stored
inline (no separate prompt_history/ directory).
"""
import os
import json
import math
import threading
from datetime import datetime

_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
_LOG_FILE = os.path.join(_MEMORY_DIR, "interaction_log.json")
_MAX_ENTRIES = 500
_MAX_PROMPT_ENTRIES = 50   # only keep prompt text for the N most recent entries
_USER_TEXT_MAX = 150       # truncate user text in log
_BOT_TEXT_MAX = 300        # truncate bot text in log
_FLUSH_INTERVAL = 60      # seconds between periodic disk flushes
_lock = threading.Lock()

# ── In-memory log (loaded from disk once at startup) ──────────────────────────
_log_entries = None        # list of dicts — lazily initialized
_log_dirty = False         # True when in-memory log has unflushed changes

# ── Emotional state (derived from recent interactions) ────────────────────────
_EMO_WINDOW = 50
_EMO_HALF_LIFE = 1800     # seconds (30 min)

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

_emo_cache = []       # list of (timestamp_float, axis_scores_dict)
_emo_cache_lock = threading.Lock()


# ── In-memory log management ─────────────────────────────────────────────────

def _ensure_log():
    """Lazily load the log from disk into memory on first access."""
    global _log_entries
    if _log_entries is None:
        _log_entries = _load_log_from_disk()


def _load_log_from_disk():
    """Read the interaction log from disk."""
    if os.path.exists(_LOG_FILE):
        try:
            with open(_LOG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def flush_log():
    """Write the in-memory log to disk.  Called periodically by the heartbeat
    and on shutdown.  No-op if nothing changed since last flush.
    """
    global _log_dirty
    with _lock:
        if not _log_dirty or _log_entries is None:
            return
        _write_log_to_disk(_log_entries)
        _log_dirty = False


def _write_log_to_disk(entries):
    """Persist entries to disk (trimmed, prompts stripped from old entries)."""
    trimmed = entries[-_MAX_ENTRIES:]

    # Only keep prompt/llm_raw text for the most recent N entries
    cutoff = len(trimmed) - _MAX_PROMPT_ENTRIES
    for i, e in enumerate(trimmed):
        if i < cutoff:
            if "prompt" in e:
                del e["prompt"]
                e["has_prompt"] = False
            if "llm_raw" in e:
                del e["llm_raw"]

    try:
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        with open(_LOG_FILE, 'w') as f:
            json.dump(trimmed, f, indent=None, separators=(',', ':'))
    except IOError:
        pass


def _start_periodic_flush():
    """Register a recurring heartbeat task to flush the log every _FLUSH_INTERVAL seconds."""
    try:
        from modules.module_heartbeat import schedule_recurring
        schedule_recurring("dashboard_log_flush", _FLUSH_INTERVAL, lambda: flush_log())
    except Exception:
        pass  # heartbeat not available — log will flush on shutdown only


# ── Emotional state ───────────────────────────────────────────────────────────

def get_emotional_state():
    """Compute the current emotional radar from recent cached interactions.

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

    result = {}
    for axis in _RADAR_AXES:
        if weight_sum > 0:
            avg = totals[axis] / weight_sum
            result[axis] = round(min(100, avg * 100))
        else:
            result[axis] = 0
    return result


def _rebuild_emo_cache():
    """Rebuild the in-memory emotion cache from the log."""
    _ensure_log()
    cache = []
    for e in _log_entries[-_EMO_WINDOW:]:
        scores = e.get("axis_scores")
        ts_str = e.get("ts", "")
        if scores and ts_str:
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                cache.append((ts, scores))
            except ValueError:
                pass
    return cache


# ── Public API ────────────────────────────────────────────────────────────────

def _get_last_prompt():
    """Get the most recently built prompt from module_prompt (in-memory)."""
    try:
        from modules.module_prompt import get_last_prompt
        return get_last_prompt() or ''
    except Exception:
        return ''


def log_interaction(user_input, bot_response, emotion=None, emotion_raw=None, axis_scores=None, speaker=None, llm_response=None):
    """Record a single conversation turn (in-memory, flushed periodically)."""
    global _log_dirty
    _ensure_log()

    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "id": entry_id,
        "ts": now_str,
        "user": (user_input or "")[:_USER_TEXT_MAX],
        "bot": (bot_response or "")[:_BOT_TEXT_MAX],
    }
    if emotion:
        entry["emotion"] = emotion
    if emotion_raw:
        entry["emotion_raw"] = emotion_raw
    if axis_scores:
        entry["axis_scores"] = axis_scores
    if speaker:
        entry["speaker"] = speaker

    # Capture the prompt inline
    prompt_text = _get_last_prompt()
    if prompt_text:
        entry["has_prompt"] = True
        entry["prompt"] = prompt_text

    # Capture the raw LLM response (dict or string)
    if llm_response is not None:
        try:
            if isinstance(llm_response, dict):
                # Store without internal keys like _timings
                clean = {k: v for k, v in llm_response.items() if not k.startswith('_')}
                entry["llm_raw"] = json.dumps(clean, indent=2, ensure_ascii=False)
            else:
                entry["llm_raw"] = str(llm_response)
        except Exception:
            pass

    with _lock:
        _log_entries.append(entry)
        # Trim in-memory to cap
        if len(_log_entries) > _MAX_ENTRIES:
            del _log_entries[:len(_log_entries) - _MAX_ENTRIES]
        _log_dirty = True

    # Update in-memory emotion cache
    if axis_scores:
        ts_float = datetime.now().timestamp()
        with _emo_cache_lock:
            _emo_cache.append((ts_float, axis_scores))
            if len(_emo_cache) > _EMO_WINDOW:
                _emo_cache[:] = _emo_cache[-_EMO_WINDOW:]


def get_interactions(limit=100):
    """Return the most recent interactions (without prompt text)."""
    _ensure_log()
    with _lock:
        entries = _log_entries[-limit:]
    return [{k: v for k, v in e.items() if k not in ("prompt", "llm_raw")} for e in entries]


def get_prompt_for_interaction(entry_id):
    """Load the full prompt and LLM response for a specific interaction."""
    _ensure_log()
    with _lock:
        for e in _log_entries:
            if e.get("id") == entry_id:
                return e.get("prompt"), e.get("llm_raw")
    return None, None


def get_mood_analytics():
    """Compute mood counts, timeline, activity heatmap, and hourly totals."""
    _ensure_log()
    with _lock:
        entries = list(_log_entries)

    mood_counts = {}
    timeline = []
    activity_by_hour = {}
    activity_heatmap = {}

    for e in entries:
        mood = e.get("emotion")
        mood_raw = e.get("emotion_raw", mood)
        ts = e.get("ts", "")

        if mood:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
            timeline.append({"timestamp": ts, "mood": mood_raw or mood, "axis": mood})

        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            hour = str(dt.hour)
            activity_by_hour[hour] = activity_by_hour.get(hour, 0) + 1
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


# ── Initialization ────────────────────────────────────────────────────────────

def _init():
    """Bootstrap: load log, rebuild emotion cache, start periodic flush."""
    global _emo_cache
    _ensure_log()
    with _emo_cache_lock:
        if not _emo_cache:
            _emo_cache = _rebuild_emo_cache()
    _start_periodic_flush()

_init()
