import requests
from modules.module_config import load_config

from modules.module_messageQue import queue_message

config = load_config()

HEADERS = {
    "Authorization": f"Bearer {config['HOME_ASSISTANT']['HA_TOKEN']}",
    "Content-Type": "application/json"
}

def clean_prompt(prompt):
    """
    Cleans and validates the prompt for Home Assistant.

    Parameters:
    - prompt (str): The natural language query.

    Returns:
    - str: Cleaned and formatted prompt.
    """
    # Basic cleanup: strip extra spaces and ensure proper capitalization
    return prompt.strip()

def send_prompt_to_homeassistant(prompt):
    """
    Perform an action in Home Assistant, such as retrieving the state of a device or setting a value, for example turn off the living room lights.

    Parameters:
    - prompt (str): The natural language query describing the desired action or device state.

    Returns:
    - dict: The response from Home Assistant API or an error message.
    """
    queue_message(f"sending prompt {prompt}")

    if config['HOME_ASSISTANT']['enabled'] == "True":
        url = f"{config['HOME_ASSISTANT']['url']}/api/conversation/process"
        cleaned_prompt = clean_prompt(prompt)  # Clean the prompt
        data = {"text": cleaned_prompt}
        queue_message(data)
        response = requests.post(url, json=data, headers=HEADERS)
        if response.ok:
            queue_message(response.json())
            return response.json()
        else:
            raise Exception(f"Failed to send prompt: {response.status_code}, {response.text}")
    else:
        return {"error": "Home Assistant is disabled"}
