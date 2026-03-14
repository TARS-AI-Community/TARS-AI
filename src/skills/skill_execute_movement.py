"""Skill: execute_movement — Send movement commands to servo motors."""

import threading

SKILL = {
    "name": "execute_movement",
    "description": "Perform physical movements and gestures",
    "prompt": """execute_movement
   Triggers: Use ONLY when user explicitly commands movement
     * "walk forward", "turn left", "step back", "move backward"
     * "go forward", "turn right"
   Valid movements:
     * "forward" - walk forward
     * "backward" - walk backward
     * "left" - turn left slowly
     * "right" - turn right slowly
   Do NOT infer or guess movement from suggestions or questions
   Parameters: {{"movements": ["forward", "backward", "left", "right"]}}
   Example: {{"function": "execute_movement", "parameters": {{"movements": ["forward", "forward", "left"]}}}}""",
    "examples": [
        """Example - Movement command:
User: "Walk forward and then turn left"
Response: {{"question": "Walk forward and then turn left", "reply": "Moving now.", "function_calls": [{{"function": "execute_movement", "parameters": {{"movements": ["forward", "left"]}}}}], "new_memories": []}}""",
    ],
}


def _execute_movement(movements):
    """Execute a sequence of movements in a separate thread."""
    from modules.module_messageQue import queue_message

    # Lazy import servo functions
    try:
        from modules.module_servoctl import step_forward, walk_backward, turn_right_slow, turn_left_slow
    except ImportError:
        queue_message("[ERROR] Servo control module not available.")
        return

    action_map = {
        "forward": step_forward,
        "backward": walk_backward,
        "left": turn_left_slow,
        "right": turn_right_slow,
    }

    def movement_task():
        try:
            for i, move in enumerate(movements, start=1):
                action_function = action_map.get(move)
                if callable(action_function):
                    queue_message(f"[INFO] Executing movement {i}/{len(movements)}: {move}")
                    action_function()
                else:
                    queue_message(f"[ERROR] Movement '{move}' not found in action_map.")
        except Exception as e:
            queue_message(f"[ERROR] Unexpected error while executing movements: {e}")
        finally:
            queue_message(f"[DEBUG] Thread completed for movements: {movements}")

    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return thread


def execute(parameters, context):
    """Execute servo movement commands. Returns None (no reply modification)."""
    config = context.get("config", {})
    if not config.get("CONTROLS", {}).get("voicemovement"):
        return None

    movements = parameters.get("movements", [])
    if movements:
        _execute_movement(movements)
    return None
