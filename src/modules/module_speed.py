"""
module_speed.py

Centralized speed profiler for TARS-AI pipeline.
Enable with: python app.py speed=true
All timing instrumentation lives here to keep other modules clean.
"""

import time
from modules.module_messageQue import queue_message

# Global enable flag — set by app.py based on CLI arg
enabled = False

# Timestamps for cross-module measurements
_utterance_start = None
_first_audio_logged = False
_timings = {}


def fmt(seconds):
    """Format seconds as a readable string."""
    if seconds < 0.01:
        return f"{seconds:.4f}s"
    elif seconds < 1:
        return f"{seconds:.2f}s"
    else:
        return f"{seconds:.1f}s"


def start(label):
    """Record start time for a labeled span."""
    if not enabled:
        return
    _timings[label] = time.perf_counter()


def stop(label):
    """Record end time, return duration in seconds (or 0 if not started)."""
    if not enabled:
        return 0
    t_start = _timings.pop(label, None)
    if t_start is None:
        return 0
    return time.perf_counter() - t_start


def mark_utterance_start():
    """Mark the beginning of utterance processing (for time-to-first-audio)."""
    global _utterance_start, _first_audio_logged
    if not enabled:
        return
    _utterance_start = time.perf_counter()
    _first_audio_logged = False


def mark_first_audio():
    """Called when first audio chunk plays. Logs time-to-first-audio once."""
    global _utterance_start, _first_audio_logged
    if not enabled or _utterance_start is None or _first_audio_logged:
        return
    _first_audio_logged = True
    dur = time.perf_counter() - _utterance_start
    queue_message(f"SPEED: time_to_first_audio({fmt(dur)})")


def log(message):
    """Log a SPEED message if profiling is enabled."""
    if not enabled:
        return
    queue_message(f"SPEED: {message}")


def log_tool(name, duration):
    """Log a tool execution time."""
    if not enabled:
        return
    queue_message(f"SPEED: tool:{name}({fmt(duration)})")


def log_pipeline(timings_dict):
    """Log the full pipeline breakdown from a timings dict."""
    if not enabled or not timings_dict:
        return
    parts = []
    for label, dur in timings_dict.items():
        if label.startswith('_'):
            continue
        parts.append(f"{label}({fmt(dur)})")
    if parts:
        queue_message(f"SPEED: {', '.join(parts)}")
