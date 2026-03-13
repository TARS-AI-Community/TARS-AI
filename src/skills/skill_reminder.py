"""Skill: reminder — Set, list, and cancel timed reminders via module_heartbeat."""

SKILL = {
    "name": "reminder",
    "prompt": """reminder
   Triggers: When the user asks you to:
     * Set a reminder, alarm, or timer: "remind me in 5 minutes", "set a timer for 30 seconds", "alarm in 2 hours"
     * List active reminders: "what reminders do I have", "show my timers"
     * Cancel a reminder: "cancel my reminder", "delete the timer", "cancel reminder 3"
   Parameters:
     For setting: {{"action": "set", "seconds": <number>, "message": "what to remind about"}}
     For listing: {{"action": "list"}}
     For canceling: {{"action": "cancel", "id": <number or "all">}}
   CRITICAL: Convert the user's time to seconds. Examples: "5 minutes" = 300, "1 hour" = 3600, "30 seconds" = 30, "2 and a half hours" = 9000.
   CRITICAL: Your "reply" should confirm what you set. Example: "Got it, I'll remind you in 5 minutes about the laundry."
   CRITICAL: The "message" parameter should capture the FULL intent of what the user wants. If they say "tell me a joke in 5 minutes", the message should be "tell me a joke" — not just "joke". When the reminder fires, you will be asked to fulfill this request, so include enough context.
   Example: {{"function": "reminder", "parameters": {{"action": "set", "seconds": 300, "message": "check the laundry"}}}}""",
    "examples": [
        """Example - set a reminder:
User: "Remind me in 10 minutes to take the pizza out"
Response: {{"question": "Remind me in 10 minutes to take the pizza out", "reply": "Timer set! I'll remind you in 10 minutes about the pizza.", "function_calls": [{{"function": "reminder", "parameters": {{"action": "set", "seconds": 600, "message": "take the pizza out"}}}}], "new_memories": []}}""",
        """Example - list reminders:
User: "What reminders do I have?"
Response: {{"question": "What reminders do I have?", "reply": "Let me check your active reminders.", "function_calls": [{{"function": "reminder", "parameters": {{"action": "list"}}}}], "new_memories": []}}""",
        """Example - cancel reminder:
User: "Cancel all my reminders"
Response: {{"question": "Cancel all my reminders", "reply": "All reminders cleared.", "function_calls": [{{"function": "reminder", "parameters": {{"action": "cancel", "id": "all"}}}}], "new_memories": []}}""",
    ],
}

_PREFIX = "reminder_"
_next_id_lock = __import__("threading").Lock()
_next_id = 0


def _get_next_id():
    """Auto-increment reminder ID."""
    global _next_id
    with _next_id_lock:
        from modules.module_heartbeat import list_tasks
        existing = list_tasks(prefix=_PREFIX)
        max_id = 0
        for t in existing:
            try:
                num = int(t["id"].replace(_PREFIX, ""))
                max_id = max(max_id, num)
            except (ValueError, TypeError):
                pass
        _next_id = max(max_id, _next_id) + 1
        return _next_id


def _fire_reminder(task_id, meta):
    """Called by the scheduler when a reminder fires.

    Routes the reminder through the LLM so TARS responds contextually
    (e.g. "tell me a joke" actually tells a joke, not just "Reminder: tell me a joke").
    Falls back to direct TTS if the LLM pipeline isn't available.
    """
    import asyncio
    message = meta.get("message", "Timer expired")

    try:
        from modules.module_messageQue import queue_message
        queue_message(f"REMINDER: #{task_id}: {message}")
    except Exception:
        pass

    # Try to route through LLM for a contextual response
    llm_reply = None
    try:
        from modules.module_llm import process_completion, llm_execute_side_effects
        prompt = f"[SYSTEM: A reminder just fired. The user previously asked you to remind them: \"{message}\". Respond naturally — acknowledge the reminder and fulfill the request if it was an action (e.g. tell a joke, suggest something, etc.). Keep it concise.]"
        parsed = process_completion(prompt)
        if isinstance(parsed, dict):
            llm_reply = parsed.get("reply", "")
            # Run any side effects (function calls, memories) in background
            import threading
            threading.Thread(
                target=llm_execute_side_effects,
                args=(parsed, prompt),
                daemon=True,
            ).start()
        elif isinstance(parsed, str) and parsed.strip():
            llm_reply = parsed.strip()
    except Exception as e:
        try:
            from modules.module_messageQue import queue_message
            queue_message(f"REMINDER: LLM processing failed, falling back to direct TTS: {e}")
        except Exception:
            pass

    # Determine what to speak
    speak_text = llm_reply if llm_reply else f"Reminder: {message}"

    # TTS announcement
    try:
        from modules.module_tts import play_audio_chunks
        from modules.module_config import load_config
        config = load_config()
        asyncio.run(play_audio_chunks(speak_text, config['TTS']['ttsoption']))
    except Exception as e:
        try:
            from modules.module_messageQue import queue_message
            queue_message(f"REMINDER: TTS failed: {e}")
        except Exception:
            pass

    # Push to web UI
    display_text = llm_reply if llm_reply else f"**Reminder:** {message}"
    try:
        from modules.module_chatui import socketio
        socketio.emit('bot_message', {'message': display_text})
        socketio.emit('bot_audio_done', {})
    except Exception:
        pass


def _format_remaining(seconds):
    """Human-readable countdown."""
    if seconds <= 0:
        return "expired"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    return ' '.join(parts)


def execute(parameters, context):
    """Handle reminder actions: set, list, cancel."""
    from modules.module_heartbeat import schedule_once, cancel_task, cancel_by_prefix, list_tasks
    from modules.module_messageQue import queue_message

    action = parameters.get("action", "set")

    if action == "set":
        seconds = parameters.get("seconds", 0)
        message = parameters.get("message", "Timer expired")

        try:
            seconds = int(float(seconds))
        except (ValueError, TypeError):
            return "I couldn't understand the time. Try something like 'remind me in 5 minutes'."

        if seconds <= 0:
            return "The reminder time needs to be in the future."
        if seconds > 86400 * 7:
            return "I can set reminders up to 7 days out. That's a bit too far."

        rid = _get_next_id()
        task_id = f"{_PREFIX}{rid}"

        meta = {"message": message, "rid": rid}
        schedule_once(
            task_id=task_id,
            delay_seconds=seconds,
            callback=_fire_reminder,
            args=(task_id, meta),
            persist=True,
            meta=meta,
        )

        from datetime import datetime, timedelta
        fire_at = (datetime.now() + timedelta(seconds=seconds)).strftime("%H:%M:%S")
        queue_message(f"REMINDER: Set #{rid} — '{message}' in {seconds}s (fires at {fire_at})")
        return None  # LLM already gave a confirmation reply

    elif action == "list":
        tasks = list_tasks(prefix=_PREFIX)

        if not tasks:
            return "You don't have any active reminders."

        lines = []
        for t in tasks:
            meta = t.get("meta", {})
            rid = meta.get("rid", t["id"])
            msg = meta.get("message", "?")
            remaining = _format_remaining(t["remaining_seconds"])
            lines.append(f"#{rid}: {msg} ({remaining} remaining)")
        return "Active reminders:\n" + "\n".join(lines)

    elif action == "cancel":
        cancel_id = parameters.get("id", "all")

        if str(cancel_id).lower() == "all":
            count = cancel_by_prefix(_PREFIX)
            if count > 0:
                return f"Cancelled all {count} reminder{'s' if count != 1 else ''}."
            return "No reminders to cancel."
        else:
            try:
                cancel_id = int(cancel_id)
            except (ValueError, TypeError):
                return "I need a reminder number to cancel, or say 'cancel all'."

            task_id = f"{_PREFIX}{cancel_id}"
            tasks = list_tasks(prefix=_PREFIX)
            msg = ""
            for t in tasks:
                if t["id"] == task_id:
                    msg = t.get("meta", {}).get("message", "")
                    break

            if cancel_task(task_id):
                return f"Cancelled reminder #{cancel_id}: {msg}"
            return f"No reminder #{cancel_id} found."

    return None


# ── Restore persisted reminders on import (runs once at startup) ──────────────
try:
    from modules.module_heartbeat import restore_tasks
    _restored = restore_tasks(fire_callback=_fire_reminder)
    if _restored:
        from modules.module_messageQue import queue_message
        queue_message(f"LOAD: Restored {_restored} reminder(s)")
except Exception:
    pass
