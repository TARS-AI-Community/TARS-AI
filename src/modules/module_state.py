"""
Core application state — thread-safe, importable from any module.

Usage:
    from modules.module_state import set_tars_state, get_tars_state, TarsState

    set_tars_state(TarsState.TALKING)
    if get_tars_state() == TarsState.LISTENING:
        ...
"""

import threading
from enum import Enum
from typing import Callable, List

from modules.module_config import load_config


class TarsState(str, Enum):
    BOOTING = "BOOTING"
    STANDBY = "STANDBY"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    TALKING = "TALKING"


_state: TarsState = TarsState.BOOTING
_lock = threading.Lock()
_listeners: List[Callable[[TarsState, TarsState], None]] = []


def get_tars_state() -> TarsState:
    """Get current TARS state. Thread-safe."""
    with _lock:
        return _state


def set_tars_state(new_state: TarsState) -> None:
    """Set TARS state. Notifies all registered listeners. Thread-safe."""
    global _state
    with _lock:
        old = _state
        if old == new_state:
            return
        _state = new_state
        listeners = _listeners.copy()
    # Log state change in debug mode
    try:
        if load_config().get('STT', {}).get('debug', False):
            from modules.module_messageQue import queue_message
            queue_message(f"DEBUG: State: {old.value} → {new_state.value}")
    except Exception:
        pass

    # Notify outside lock to avoid deadlocks
    for fn in listeners:
        try:
            fn(old, new_state)
        except Exception:
            pass


def on_state_change(callback: Callable[[TarsState, TarsState], None]) -> None:
    """Register a listener called on state changes: callback(old_state, new_state)."""
    with _lock:
        _listeners.append(callback)


def remove_state_change(callback: Callable[[TarsState, TarsState], None]) -> None:
    """Unregister a previously registered state change listener."""
    with _lock:
        try:
            _listeners.remove(callback)
        except ValueError:
            pass


# Reference to STT manager, set by app.py at startup
_stt_manager = None


def register_stt_manager(stt_mgr) -> None:
    """Register the STT manager so force_standby() can cancel it."""
    global _stt_manager
    _stt_manager = stt_mgr


def force_standby() -> None:
    """Kill any active STT session and force TARS into STANDBY. Safe to call from anywhere."""
    if _stt_manager:
        _stt_manager.cancel()
    set_tars_state(TarsState.STANDBY)
