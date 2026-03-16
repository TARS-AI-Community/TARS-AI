"""Skill: volume — Get or change system audio volume."""

import subprocess
import re

SKILL = {
    "name": "volume",
    "required_params": ["action"],
    "description": "Adjust speaker volume",
    "prompt": """volume
   Triggers: "raise volume", "lower volume", "set volume to X", "mute", "what's the volume", "check volume"
   Parameters: {{"action": "get|set|increase|decrease", "value": number (optional, not needed for get)}}
   Example: {{"function": "volume", "parameters": {{"action": "increase", "value": 10}}}}
   Example: {{"function": "volume", "parameters": {{"action": "get"}}}}""",
    "examples": [
        """Example - Volume control:
User: "Turn the volume up"
Response: {{"reply": "Raising the volume.", "function_calls": [{{"function": "volume", "parameters": {{"action": "increase", "value": 10}}}}], "new_memories": []}}""",
        """Example - Check volume:
User: "What's the volume at?"
Response: {{"reply": "Let me check.", "function_calls": [{{"function": "volume", "parameters": {{"action": "get"}}}}], "new_memories": []}}""",
    ],
}


class _VolumeControl:
    """Simple amixer-based volume control."""

    def __init__(self, control='Master'):
        self.control = control

    def get_volume(self):
        """Get current volume as percentage (0-100)."""
        try:
            output = subprocess.check_output(
                ['amixer', 'get', self.control],
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            match = re.search(r'\[(\d+)%\]', output)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            from modules.module_messageQue import queue_message
            queue_message(f"ERROR: Failed to get volume: {e}")
            return None

    def set_volume(self, percent):
        """Set volume to exact percentage (0-100)."""
        if not (0 <= percent <= 100):
            from modules.module_messageQue import queue_message
            queue_message(f"ERROR: Volume must be 0-100, got {percent}")
            return False
        try:
            subprocess.check_call(
                ['amixer', 'set', self.control, f'{percent}%'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            from modules.module_messageQue import queue_message
            queue_message(f"Volume set to {percent}%")
            return True
        except Exception as e:
            from modules.module_messageQue import queue_message
            queue_message(f"ERROR: Failed to set volume: {e}")
            return False

    def adjust_volume(self, change):
        """Adjust volume by relative amount (-100 to +100)."""
        current = self.get_volume()
        if current is None:
            return False
        new_volume = max(0, min(100, current + change))
        return self.set_volume(new_volume)


_vc = None


def _get_vc():
    global _vc
    if _vc is None:
        _vc = _VolumeControl()
    return _vc


def execute(parameters, context):
    """Get or adjust system volume. Returns reply text."""
    vc = _get_vc()
    action = parameters.get("action", "set")
    value = parameters.get("value", 0)

    if action == "get":
        current = vc.get_volume()
        if current is not None:
            return f"Current volume is {current}%."
        return "Unable to check volume level."
    elif action == "set":
        if vc.set_volume(value):
            return f"Volume set to {value}%."
        return "Failed to set volume."
    elif action == "increase":
        if vc.adjust_volume(value):
            new_vol = vc.get_volume()
            return f"Volume increased by {value}%. Now at {new_vol}%."
        return "Failed to increase volume."
    elif action == "decrease":
        if vc.adjust_volume(-value):
            new_vol = vc.get_volume()
            return f"Volume decreased by {value}%. Now at {new_vol}%."
        return "Failed to decrease volume."
    return "Unknown volume action."
