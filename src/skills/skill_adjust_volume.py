"""Skill: adjust_volume — Set or change system audio volume."""

SKILL = {
    "name": "adjust_volume",
    "prompt": """adjust_volume
   Triggers: "raise volume", "lower volume", "set volume to X", "mute"
   Parameters: {{"action": "set|increase|decrease", "value": number}}
   Example: {{"function": "adjust_volume", "parameters": {{"action": "increase", "value": 10}}}}""",
}


def execute(parameters, context):
    """Adjust system volume. Returns reply text."""
    from modules.module_volume import get_volume_control

    vc = get_volume_control()
    action = parameters.get("action", "set")
    value = parameters.get("value", 0)

    if action == "set":
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
