"""Skill: execute_movement — Send movement commands to servo motors."""

SKILL = {
    "name": "execute_movement",
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
}


def execute(parameters, context):
    """Execute servo movement commands. Returns None (no reply modification)."""
    from modules.module_config import load_config

    config = load_config()
    if not config["CONTROLS"]["voicemovement"]:
        return None

    movements = parameters.get("movements", [])
    if movements:
        from modules.module_engine import execute_movement
        execute_movement(movements)
    return None
