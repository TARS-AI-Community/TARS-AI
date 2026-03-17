"""Skill: home_assistant — Control smart home devices via Home Assistant."""

import os
import requests

SKILL = {
    "name": "home_assistant",
    "required_params": ["prompt"],
    "description": "Control smart home devices via Home Assistant",
    "config": {
        "url": {
            "type": "text",
            "default": "http://192.168.1.1:8123",
            "description": "Home Assistant server URL (e.g. http://192.168.1.50:8123)",
        },
    },
    "prompt": """home_assistant
    Triggers: Use when the user wants to control smart home devices or ask about their status.
      * "open the garage", "turn off the lights", "is the front door locked"
      * "set the thermostat to 72", "is the garage open or closed"
    Parameters: {{"prompt": "natural language command for Home Assistant. Use EXACT entity or area names if the user provides them."}}
    Example: {{"function": "home_assistant", "parameters": {{"prompt": "open the garage door"}}}}""",
    "examples": [
        """Example - Smart home control:
User: "Turn off the living room lights"
Response: {{"reply": "On it.", "function_calls": [{{"function": "home_assistant", "parameters": {{"prompt": "turn off the living room lights"}}}}], "new_memories": []}}""",
    ],
}


def _send_prompt_to_homeassistant(prompt, skill_config):
    """Send a natural language command to Home Assistant's conversation API."""
    from modules.module_messageQue import queue_message

    url = skill_config.get("url", "").rstrip("/")
    token = os.getenv("HA_TOKEN", "")

    if not url:
        return {"error": "Home Assistant URL not configured"}
    if not token:
        return {"error": "Home Assistant token not configured (set HA_TOKEN in .env)"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    api_url = f"{url}/api/conversation/process"
    data = {"text": prompt.strip()}

    queue_message(f"HA Data: {data}")
    try:
        response = requests.post(api_url, json=data, headers=headers, timeout=15)
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

    skill_config = context.get("skill_config", {})
    queue_message(f"Home Assistant: {prompt}")
    ha_response = _send_prompt_to_homeassistant(prompt, skill_config)

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
