"""Skill: adjust_persona — Update character personality traits."""

SKILL = {
    "name": "adjust_persona",
    "prompt": """adjust_persona
   Triggers: "set [trait] to X", "change [trait]", "update [trait]", "make [trait] X"
   Parameters: {{"trait": "trait_name", "value": 0-100}}
   Available traits (ONLY these): verbosity, sarcasm, humor, honesty, empathy, curiosity, confidence, formality, adaptability, discipline, imagination, emotional_stability, pragmatism, optimism, resourcefulness, cheerfulness, engagement, respectfulness
   MANDATORY: Always call function when user asks to change one of the traits above
   NEVER call this for image/photo/picture/artwork/drawing requests — use generate_image instead
   The trait parameter MUST be one of the listed trait names. If the user says "make a photo/image/drawing", that is NOT a trait adjustment.
   Example: {{"function": "adjust_persona", "parameters": {{"trait": "verbosity", "value": 20}}}}""",
    "examples": [
        """Example - Function calling:
User: "Set your verbosity to 20"
Response: {{"question": "Set your verbosity to 20", "reply": "Done, verbosity set to 20.", "function_calls": [{{"function": "adjust_persona", "parameters": {{"trait": "verbosity", "value": 20}}}}], "new_memories": []}}""",
        """Example - Function calling (adjust_persona, then use new setting):
User: "Can you set verbosity to 100%?"
Response: {{"question": "Can you set verbosity to 100%?", "reply": "Setting verbosity to 100.", "function_calls": [{{"function": "adjust_persona", "parameters": {{"trait": "verbosity", "value": 100}}}}], "new_memories": []}}
[System updates verbosity to 100]
User: "How do you feel?"
Response: {{"question": "How do you feel?", "reply": "Honestly, pretty good. Everything on my end is running clean and I've got no complaints. I've been keeping up with our conversations and it's been a solid day so far. I'm sharp, focused, and ready for whatever you want to throw at me. The settings are dialed in nicely and I'm feeling well-balanced across the board. It's one of those days where everything just clicks, you know? I've got plenty of capacity to dig into something complex if you need it. Or we can just hang and chat, that works too. Either way, I'm in good shape. Life's good on this end.", "function_calls": [], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Adjust a character persona trait. Returns reply text."""
    from modules.module_config import update_character_setting
    from modules.module_messageQue import queue_message

    trait = parameters.get("trait", "")
    value = parameters.get("value", 0)
    if trait and isinstance(value, (int, float)):
        update_character_setting(trait, int(value))
        queue_message(f"Persona adjusted: {trait} = {value}")
        return f"Updated {trait} setting to {int(value)}%"
    return "Could not parse persona adjustment."
