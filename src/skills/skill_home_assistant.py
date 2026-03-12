"""Skill: home_assistant — Control smart home devices via Home Assistant."""

SKILL = {
    "name": "home_assistant",
    "prompt": """home_assistant
    Triggers: Use when the user wants to control smart home devices or ask about their status.
      * "open the garage", "turn off the lights", "is the front door locked"
      * "set the thermostat to 72", "is the garage open or closed"
    Parameters: {{"prompt": "natural language command for Home Assistant. Use EXACT entity or area names if the user provides them."}}
    Example: {{"function": "home_assistant", "parameters": {{"prompt": "open the garage door"}}}}""",
}


def execute(parameters, context):
    """Send command to Home Assistant. Returns reply text."""
    from modules.module_homeassistant import send_prompt_to_homeassistant
    from modules.module_messageQue import queue_message

    prompt = parameters.get("prompt", context.get("user_input", ""))
    if not prompt:
        return "No command provided for Home Assistant."

    queue_message(f"Home Assistant: {prompt}")
    ha_response = send_prompt_to_homeassistant(prompt)

    if isinstance(ha_response, dict) and "error" in ha_response:
        return f"Home Assistant error: {ha_response['error']}"

    if ha_response:
        speech = ""
        try:
            speech = ha_response.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
        except Exception:
            pass

        if speech:
            if ha_response.get("response", {}).get("response_type") == "error":
                return f"Home Assistant reported: {speech}"
            return speech
        return "Action completed via Home Assistant."

    return "I couldn't get a response from Home Assistant."
