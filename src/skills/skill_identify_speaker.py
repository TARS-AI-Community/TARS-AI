"""Skill: identify_speaker_name — Register a speaker's voice profile."""

SKILL = {
    "name": "identify_speaker_name",
    "prompt": """identify_speaker_name
    Triggers: ONLY when someone explicitly tells you their name AND either:
      * The current speaker is UNKNOWN (system prompt says "Current speaker: UNKNOWN")
      * Someone corrects you about their identity (e.g. "I'm not Joe, I'm Sarah")
    This enrolls their voice print so you can recognize them in future conversations.
    IMPORTANT: Do NOT call this if the speaker is already identified by name in the system prompt.
    If the system prompt already says "Current speaker identified as: Joe", do NOT call this function.
    Only call this when the speaker is UNKNOWN or is correcting a wrong identification.
    Parameters: {{"name": "the speaker's actual name as they stated it"}}
    Example: {{"function": "identify_speaker_name", "parameters": {{"name": "Joe"}}}}""",
}


def execute(parameters, context):
    """Register a speaker's name and voice profile. Returns None (no reply modification)."""
    from modules.module_speaker_id import get_speaker_id_manager
    from modules.module_messageQue import queue_message

    name = parameters.get("name", "").strip()

    # Reject invalid names the LLM sometimes hallucinates
    _INVALID_NAMES = {"null", "none", "unknown", "undefined", "n/a", "na", ""}
    if name.lower() in _INVALID_NAMES or name.startswith("Unknown_"):
        queue_message(f"WARNING: identify_speaker_name rejected invalid name '{name}'")
        return None

    if not name:
        queue_message("WARNING: identify_speaker_name called without a name")
        return None

    sid = get_speaker_id_manager()
    if sid is not None:
        result = sid.name_current_speaker(name)
        queue_message(f"INFO: identify_speaker_name('{name}'): {result}")

        # Auto-train face if unknown face is on camera
        try:
            from modules.module_identity import get_identity_manager
            im = get_identity_manager()
            if im is not None:
                im.auto_train_face(name)
        except Exception:
            pass
    else:
        queue_message("WARNING: Speaker ID manager not available")

    return None
