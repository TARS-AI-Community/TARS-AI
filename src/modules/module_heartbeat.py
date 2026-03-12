"""
Module: Heartbeat
Central lightweight scheduler for one-shot and recurring timed tasks.
Any module or skill can register callbacks to fire after a delay or on
a recurring interval.  Uses threading.Timer under the hood — zero
external dependencies, zero polling loops, zero CPU when idle.

Usage:
    from modules.module_heartbeat import schedule_once, schedule_recurring, cancel_task, list_tasks

    # One-shot (fires once after delay):
    schedule_once("reminder_1", 300, my_callback, args=("hello",), persist=True, meta={"message": "hello"})

    # Recurring (fires every interval):
    schedule_recurring("battery_check", 600, check_battery)

    # Cancel:
    cancel_task("reminder_1")

    # List active:
    tasks = list_tasks()

Persistence:
    Tasks with persist=True are saved to disk and restored on startup via
    restore_tasks().  Only one-shot tasks support persistence (recurring
    tasks are expected to be re-registered by their owning module at startup).
"""

import os
import json
import threading
from datetime import datetime, timedelta

_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
_PERSIST_FILE = os.path.join(_MEMORY_DIR, "scheduled_tasks.json")

_lock = threading.Lock()
_tasks = {}  # task_id -> _Task


class _Task:
    """Internal task wrapper."""
    __slots__ = ("task_id", "callback", "args", "kwargs", "fire_at", "interval",
                 "persist", "meta", "timer", "cancelled")

    def __init__(self, task_id, callback, args, kwargs, fire_at, interval, persist, meta):
        self.task_id = task_id
        self.callback = callback
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.fire_at = fire_at        # datetime
        self.interval = interval      # seconds (None = one-shot)
        self.persist = persist
        self.meta = meta or {}        # arbitrary metadata (e.g. reminder message)
        self.timer = None
        self.cancelled = False


# ── Public API ────────────────────────────────────────────────────────────────

def schedule_once(task_id, delay_seconds, callback, args=None, kwargs=None,
                  persist=False, meta=None):
    """Schedule a one-shot task that fires after delay_seconds.

    Args:
        task_id:        Unique string identifier.
        delay_seconds:  Seconds until fire.
        callback:       Callable to invoke when the task fires.
        args/kwargs:    Arguments forwarded to callback.
        persist:        If True, survives app restarts (callback must be
                        re-registered via restore hook).
        meta:           Dict of metadata saved alongside the task (for display/persistence).

    Returns the task_id.
    """
    fire_at = datetime.now() + timedelta(seconds=delay_seconds)

    task = _Task(
        task_id=task_id,
        callback=callback,
        args=args,
        kwargs=kwargs,
        fire_at=fire_at,
        interval=None,
        persist=persist,
        meta=meta,
    )

    with _lock:
        # Cancel existing task with same id
        _cancel_unlocked(task_id)
        _tasks[task_id] = task
        if persist:
            _save_tasks()

    _start_timer(task)
    return task_id


def schedule_recurring(task_id, interval_seconds, callback, args=None, kwargs=None,
                       meta=None):
    """Schedule a recurring task that fires every interval_seconds.

    Recurring tasks are NOT persisted — the owning module should re-register
    them at startup.
    """
    fire_at = datetime.now() + timedelta(seconds=interval_seconds)

    task = _Task(
        task_id=task_id,
        callback=callback,
        args=args,
        kwargs=kwargs,
        fire_at=fire_at,
        interval=interval_seconds,
        persist=False,
        meta=meta,
    )

    with _lock:
        _cancel_unlocked(task_id)
        _tasks[task_id] = task

    _start_timer(task)
    return task_id


def cancel_task(task_id):
    """Cancel a scheduled task by id.  Returns True if found."""
    with _lock:
        found = _cancel_unlocked(task_id)
        if found:
            _save_tasks()
        return found


def cancel_by_prefix(prefix):
    """Cancel all tasks whose id starts with prefix.  Returns count cancelled."""
    with _lock:
        to_cancel = [tid for tid in _tasks if tid.startswith(prefix)]
        for tid in to_cancel:
            _cancel_unlocked(tid)
        if to_cancel:
            _save_tasks()
        return len(to_cancel)


def list_tasks(prefix=None):
    """Return list of active task dicts (optionally filtered by id prefix).

    Each dict: {id, fire_at, remaining_seconds, interval, meta}
    """
    now = datetime.now()
    result = []
    with _lock:
        for tid, task in _tasks.items():
            if task.cancelled:
                continue
            if prefix and not tid.startswith(prefix):
                continue
            remaining = max(0, (task.fire_at - now).total_seconds())
            result.append({
                "id": tid,
                "fire_at": task.fire_at.strftime("%Y-%m-%d %H:%M:%S"),
                "remaining_seconds": round(remaining),
                "interval": task.interval,
                "meta": task.meta,
            })
    return result


def get_task(task_id):
    """Get a single task dict by id, or None."""
    tasks = list_tasks()
    for t in tasks:
        if t["id"] == task_id:
            return t
    return None


# ── Persistence ───────────────────────────────────────────────────────────────

def restore_tasks(fire_callback):
    """Restore persisted one-shot tasks from disk.

    Args:
        fire_callback: callable(task_id, meta) — called when a restored task
                       fires (or fires immediately if already expired).

    This is the startup entry point.  The caller provides the callback since
    the original callback reference can't be pickled.
    """
    data = _load_persisted()
    if not data:
        return 0

    restored = 0
    now = datetime.now()

    for entry in data:
        task_id = entry.get("id", "")
        fire_at_str = entry.get("fire_at", "")
        meta = entry.get("meta", {})

        try:
            fire_at = datetime.strptime(fire_at_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        delay = (fire_at - now).total_seconds()

        task = _Task(
            task_id=task_id,
            callback=fire_callback,
            args=(task_id, meta),
            kwargs={},
            fire_at=fire_at,
            interval=None,
            persist=True,
            meta=meta,
        )

        with _lock:
            _tasks[task_id] = task

        if delay <= 0:
            # Already expired — fire immediately in a thread
            threading.Thread(target=_fire_task, args=(task,), daemon=True).start()
        else:
            _start_timer(task)

        restored += 1

    return restored


# ── Internal ──────────────────────────────────────────────────────────────────

def _start_timer(task):
    """Start the threading.Timer for a task."""
    delay = max(0, (task.fire_at - datetime.now()).total_seconds())

    if delay <= 0 and task.interval is None:
        # Fire immediately for expired one-shots
        threading.Thread(target=_fire_task, args=(task,), daemon=True).start()
        return

    timer = threading.Timer(delay, _fire_task, args=(task,))
    timer.daemon = True
    timer.start()
    task.timer = timer


def _fire_task(task):
    """Called when a timer expires."""
    if task.cancelled:
        return

    # Execute callback
    try:
        task.callback(*task.args, **task.kwargs)
    except Exception as e:
        try:
            from modules.module_messageQue import queue_message
            queue_message(f"WARNING: Scheduled task '{task.task_id}' failed: {e}")
        except Exception:
            pass

    if task.interval and not task.cancelled:
        # Recurring — reschedule
        task.fire_at = datetime.now() + timedelta(seconds=task.interval)
        _start_timer(task)
    else:
        # One-shot — remove
        with _lock:
            _tasks.pop(task.task_id, None)
            if task.persist:
                _save_tasks()


def _cancel_unlocked(task_id):
    """Cancel a task (must hold _lock).  Returns True if found."""
    task = _tasks.pop(task_id, None)
    if task:
        task.cancelled = True
        if task.timer:
            task.timer.cancel()
        return True
    return False


def _save_tasks():
    """Persist only one-shot persistent tasks to disk."""
    to_save = []
    for tid, task in _tasks.items():
        if task.persist and not task.cancelled and task.interval is None:
            to_save.append({
                "id": tid,
                "fire_at": task.fire_at.strftime("%Y-%m-%d %H:%M:%S"),
                "meta": task.meta,
            })
    try:
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        with open(_PERSIST_FILE, 'w') as f:
            json.dump(to_save, f, indent=None, separators=(',', ':'))
    except IOError:
        pass


def _load_persisted():
    """Load persisted tasks from disk."""
    if os.path.exists(_PERSIST_FILE):
        try:
            with open(_PERSIST_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []
