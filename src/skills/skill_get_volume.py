"""Skill: get_volume — Check the current system volume level."""

SKILL = {
    "name": "get_volume",
    "prompt": """get_volume
   Triggers: "what's the volume", "check volume"
   Parameters: {{}}
   Example: {{"function": "get_volume", "parameters": {{}}}}""",
}


def execute(parameters, context):
    """Get current volume level. Returns reply text."""
    from modules.module_volume import get_volume_control

    vc = get_volume_control()
    current = vc.get_volume()
    if current is not None:
        return f"Current volume is {current}%."
    return "Unable to check volume level."
