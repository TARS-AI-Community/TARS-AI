import requests
from module_config import load_config

config = load_config()

HEADERS = {
    "Authorization": f"Bearer {config['HOME_ASSISTANT']['HA_TOKEN']}",
    "Content-Type": "application/json"
}

def send_prompt_to_homeassistant(prompt):
    """
    Perform an action in Home Assistant, such as retrieving the state of a device or setting a value.

    Parameters:
    - query (str): The natural language query describing the desired action or device state.

    Returns:
    - tuple: The result of the action (e.g., device state, confirmation of value change) and any relevant metadata.
    """

    if config['HOME_ASSISTANT']['enabled'] == "True":
        url = f"{config['HOME_ASSISTANT']['url']}/api/conversation/process"
        data = {"text": prompt}

        response = requests.post(url, json=data, headers=HEADERS)
        if response.ok:
            return response.json()
        else:
            raise Exception(f"Failed to send prompt: {response.status_code}, {response.text}")
    else:
        return("Home Assistant is disabled")