"""Skill: home_assistant — Control smart home devices via Home Assistant."""

import requests

SKILL = {
    "name": "home_assistant",
    "prompt": """home_assistant
    Triggers: Use when the user wants to control smart home devices or ask about their status.
      * "open the garage", "turn off the lights", "is the front door locked"
      * "set the thermostat to 72", "is the garage open or closed"
    Parameters: {{"prompt": "natural language command for Home Assistant. Use EXACT entity or area names if the user provides them."}}
    Example: {{"function": "home_assistant", "parameters": {{"prompt": "open the garage door"}}}}""",
    "examples": [
        """Example - Smart home control:
User: "Turn off the living room lights"
Response: {{"question": "Turn off the living room lights", "reply": "On it.", "function_calls": [{{"function": "home_assistant", "parameters": {{"prompt": "turn off the living room lights"}}}}], "new_memories": []}}""",
    ],
}


def _send_prompt_to_homeassistant(prompt, config):
    """Send a natural language command to Home Assistant's conversation API.

    Returns:
        dict: The response from Home Assistant API or an error dict.
    """
    from modules.module_messageQue import queue_message

    if not config.get('HOME_ASSISTANT', {}).get('enabled'):
        return {"error": "Home Assistant is disabled"}

    ha_config = config['HOME_ASSISTANT']
    headers = {
        "Authorization": f"Bearer {ha_config['HA_TOKEN']}",
        "Content-Type": "application/json",
    }
    url = f"{ha_config['url']}/api/conversation/process"
    data = {"text": prompt.strip()}

    queue_message(f"HA Data: {data}")
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.ok:
            queue_message(f"HA Response: {response.json()}")
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
    except requests.RequestException as e:
        return {"error": str(e)}


def execute(parameters, context):
    """Send command to Home Assistant. Returns reply text."""
    from modules.module_messageQue import queue_message

    prompt = parameters.get("prompt", context.get("user_input", ""))
    if not prompt:
        return "No command provided for Home Assistant."

    config = context.get("config", {})
    queue_message(f"Home Assistant: {prompt}")
    ha_response = _send_prompt_to_homeassistant(prompt, config)

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
