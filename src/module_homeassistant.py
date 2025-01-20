import requests
from module_config import load_config

config = load_config()

HEADERS = {
    "Authorization": f"Bearer {config['HOME_ASSISTANT']['HA_TOKEN']}",
    "Content-Type": "application/json"
}

def send_prompt_to_homeassistant(prompt):
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