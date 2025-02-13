"""
module_config.py

Configuration Loading Module for TARS-AI Application.

This module reads configuration details from the `config.ini` file and environment 
variables, providing a structured dictionary for easy access throughout the application. 
"""

# === Standard Libraries ===
import os
import sys
import configparser
from dotenv import load_dotenv
from datetime import datetime

# === Initialization ===
load_dotenv()  # Load environment variables from .env file

def load_config():
    """
    Load configuration settings from 'config.ini' and 'persona.ini' and return them as a dictionary.
    This function will print an error and exit if any configuration is invalid or missing.
    
    Returns:
    - CONFIG (dict): Dictionary containing configuration settings.
    """
    # Set the working directory and adjust the system path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    sys.path.append(os.getcwd())

    # Parse the main config.ini file
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Parse the persona.ini file
    persona_config = configparser.ConfigParser()
    persona_path = os.path.join(base_dir, 'character', 'persona.ini')
    if not os.path.exists(persona_path):
        print(f"ERROR: {persona_path} not found.")
        sys.exit(1)  # Exit if persona.ini is missing

    persona_config.read(persona_path)

    # Ensure required sections and keys exist in config.ini
    required_sections = [
        'CONTROLS', 'STT', 'CHAR', 'LLM', 'VISION', 'EMOTION', 'TTS', 'DISCORD', 'SERVO', 'STABLE_DIFFUSION'
    ]
    missing_sections = [section for section in required_sections if section not in config]

    if missing_sections:
        print(f"ERROR: Missing sections in config.ini: {', '.join(missing_sections)}")
        sys.exit(1)

    # Extract persona traits
    persona_traits = {}
    if 'PERSONA' in persona_config:
        persona_traits = {key: int(value) for key, value in persona_config['PERSONA'].items()}
    else:
        print("ERROR: [PERSONA] section missing in persona.ini.")
        sys.exit(1)

    # Extract and return combined configurations
    return {
        "BASE_DIR": base_dir,
        "CONTROLS": {
            "controller_name": config['CONTROLS']['controller_name'],
        },
        "STT": {
            "wake_word": config['STT']['wake_word'],
            "sensitivity": config['STT']['sensitivity'],
            "stt_processor": config['STT']['stt_processor'],
            "external_url": config['STT']['external_url'],
            "whisper_model": config['STT']['whisper_model'],
            "vosk_model": config['STT']['vosk_model'],
            "use_indicators": config.getboolean('STT', 'use_indicators'),
        },
        "CHAR": {
            "character_card_path": config['CHAR']['character_card_path'],
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
            "traits": persona_traits,  # Include the traits from persona.ini
        },
        "LLM": {
            "llm_backend": config['LLM']['llm_backend'],
            "base_url": config['LLM']['base_url'],
            "api_key": get_api_key(config['LLM']['llm_backend']),
            "openai_model": config['LLM']['openai_model'],
            "override_encoding_model": config['LLM']['override_encoding_model'],
            "contextsize": int(config['LLM']['contextsize']),
            "max_tokens": int(config['LLM']['max_tokens']),
            "temperature": float(config['LLM']['temperature']),
            "top_p": float(config['LLM']['top_p']),
            "seed": int(config['LLM']['seed']),
            "systemprompt": config['LLM']['systemprompt'],
            "instructionprompt": config['LLM']['instructionprompt'],
        },
        "VISION": {
            "server_hosted": config.getboolean('VISION', 'server_hosted'),
            "base_url": config['VISION']['base_url'],
        },
        "EMOTION": {
            "enabled": config.getboolean('EMOTION', 'enabled'),
            "emotion_model": config['EMOTION']['emotion_model'],
            "storepath": os.path.join(os.getcwd(), config['EMOTION']['storepath']),
        },
        "TTS": {
            "ttsoption": config['TTS']['ttsoption'],
            "azure_api_key": os.getenv('AZURE_API_KEY'),
            "elevenlabs_api_key": os.getenv('ELEVENLABS_API_KEY'),
            "azure_region": config['TTS']['azure_region'],
            "ttsurl": config['TTS']['ttsurl'],
            "toggle_charvoice": config.getboolean('TTS', 'toggle_charvoice'),
            "tts_voice": config['TTS']['tts_voice'],
            "voice_id": config['TTS']['voice_id'],
            "model_id": config['TTS']['model_id'],
            "voice_only": config.getboolean('TTS', 'voice_only'),
            "is_talking_override": config.getboolean('TTS', 'is_talking_override'),
            "is_talking": config.getboolean('TTS', 'is_talking'),
            "global_timer_paused": config.getboolean('TTS', 'global_timer_paused'),
        },
        "HOME_ASSISTANT": {
            "enabled": config['HOME_ASSISTANT']['enabled'],
            "url": config['HOME_ASSISTANT']['url'],
            "HA_TOKEN": os.getenv('HA_TOKEN'),
        },
        "DISCORD": {
            "TOKEN": os.getenv('DISCORD_TOKEN'),
            "channel_id": config['DISCORD']['channel_id'],
            "enabled": config['DISCORD']['enabled'],
        },
        "SERVO": {
            "portMain": config['SERVO']['portMain'],
            "portForarm": config['SERVO']['portForarm'],
            "portHand": config['SERVO']['portHand'],
            "starMain": config['SERVO']['starMain'],
            "starForarm": config['SERVO']['starForarm'],
            "starHand": config['SERVO']['starHand'],
            "upHeight": config['SERVO']['upHeight'],
            "neutralHeight": config['SERVO']['neutralHeight'],
            "downHeight": config['SERVO']['downHeight'],
            "forwardPort": config['SERVO']['forwardPort'],
            "neutralPort": config['SERVO']['neutralPort'],
            "backPort": config['SERVO']['backPort'],
            "perfectportoffset": config['SERVO']['perfectportoffset'],
            "forwardStarboard": config['SERVO']['forwardStarboard'],
            "neutralStarboard": config['SERVO']['neutralStarboard'],
            "backStarboard": config['SERVO']['backStarboard'],
            "perfectStaroffset": config['SERVO']['perfectStaroffset'],
        },
        "STABLE_DIFFUSION": {
            "enabled": config['STABLE_DIFFUSION']['enabled'],
            "service": config['STABLE_DIFFUSION']['service'],
            "url": config['STABLE_DIFFUSION']['url'],
            "prompt_prefix": config['STABLE_DIFFUSION']['prompt_prefix'],
            "prompt_postfix": config['STABLE_DIFFUSION']['prompt_postfix'],
            "seed": int(config['STABLE_DIFFUSION']['seed']),
            "sampler_name": config['STABLE_DIFFUSION']['sampler_name'].strip('"'),
            "denoising_strength": float(config['STABLE_DIFFUSION']['denoising_strength']),
            "steps": int(config['STABLE_DIFFUSION']['steps']),
            "cfg_scale": float(config['STABLE_DIFFUSION']['cfg_scale']),
            "width": int(config['STABLE_DIFFUSION']['width']),
            "height": int(config['STABLE_DIFFUSION']['height']),
            "restore_faces": config.getboolean('STABLE_DIFFUSION', 'restore_faces'),
            "negative_prompt": config['STABLE_DIFFUSION']['negative_prompt'],
        },
    }


def get_api_key(llm_backend: str) -> str:
    """
    Retrieves the API key for the specified LLM backend.
    
    Parameters:
    - llm_backend (str): The LLM backend to retrieve the API key for.

    Returns:
    - api_key (str): The API key for the specified LLM backend.
    """
    # Map the backend to the corresponding environment variable
    backend_to_env_var = {
        "openai": "OPENAI_API_KEY",
        "ooba": "OOBA_API_KEY",
        "tabby": "TABBY_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY"
    }

    # Check if the backend is supported
    if llm_backend not in backend_to_env_var:
        raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Unsupported LLM backend: {llm_backend}")

    # Fetch the API key from the environment
    api_key = os.getenv(backend_to_env_var[llm_backend])
    if not api_key:
        raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: API key not found for LLM backend: {llm_backend}")
    
    return api_key


def update_character_setting(setting, value):
    """
    Update a specific setting in the [CHAR] section of the config.ini file.

    Parameters:
    - setting (str): The setting to update (e.g., 'humor', 'honesty').
    - value (int): The new value for the setting.

    Returns:
    - bool: True if the update is successful, False otherwise.
    """
    # Determine the path to config.ini in the same folder as this script
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'character', 'persona.ini')
    config = configparser.ConfigParser()

    try:
        # Read the config file
        config.read(config_path)

        # Check if [CHAR] section exists
        if 'PERSONA' not in config:
            print("Error: [PERSONA] section not found in the config file.")
            return False

        # Update the setting
        config['PERSONA'][setting] = str(value)

        # Write the changes back to the file
        with open(config_path, 'w') as config_file:
            config.write(config_file)

        print(f"Updated {setting} to {value} in [PERSONA] section.")
        return True

    except Exception as e:
        print(f"Error updating setting: {e}")
        return False
