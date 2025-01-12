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
load_dotenv() # Load environment variables from .env file

def load_config():
    """
    Load configuration settings from 'config.ini' and return them as a dictionary.
    This function will print an error and exit if any configuration is invalid or missing.
    
    Returns:
    - CONFIG (dict): Dictionary containing configuration settings.
    """
    # Set the working directory and adjust the system path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    sys.path.append(os.getcwd())

    # Parse the config file
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Ensure required sections and keys exist
    required_sections = [
        'CONTROLS', 'STT', 'CHAR', 'LLM', 'VISION', 'EMOTION', 'TTS', 'DISCORD', 'SERVO', 'STABLE_DIFFUSION'
    ]
    missing_sections = [section for section in required_sections if section not in config]

    if missing_sections:
        print(f"ERROR: Missing sections in config.ini: {', '.join(missing_sections)}")
        sys.exit(1)  # Exit the program if sections are missing

    required_keys = {
        'CONTROLS': ['controller_name'],
        'STT': ['wake_word', 'use_server', 'server_url', 'vosk_model', 'use_indicators'],
        'CHAR': ['character_card_path', 'user_name', 'user_details'],
        'LLM': ['llm_backend', 'base_url', 'openai_model', 'override_encoding_model', 'contextsize', 'max_tokens', 'temperature', 'top_p', 'seed', 'systemprompt', 'instructionprompt'],
        'VISION': ['server_hosted', 'base_url'],
        'EMOTION': ['enabled', 'emotion_model', 'storepath'],
        'TTS': ['ttsoption', 'azure_region', 'ttsurl', 'toggle_charvoice', 'tts_voice', 'voice_only', 'is_talking_override', 'is_talking', 'global_timer_paused'],
        'DISCORD': ['TOKEN', 'channel_id', 'enabled'],
        'SERVO': ['portMain', 'portForarm', 'portHand', 'starMain', 'starForarm', 'starHand', 'upHeight', 'neutralHeight', 'downHeight', 'forwardPort', 'neutralPort', 'backPort', 'perfectportoffset', 'forwardStarboard', 'neutralStarboard', 'backStarboard', 'perfectStaroffset'],
        'STABLE_DIFFUSION': ['enabled', 'url', 'prompt_prefix', 'prompt_postfix', 'seed', 'sampler_name', 'denoising_strength', 'steps', 'cfg_scale', 'width', 'height', 'restore_faces', 'negative_prompt']
    }

    missing_keys = []
    for section, keys in required_keys.items():
        for key in keys:
            if key not in config[section]:
                missing_keys.append(f"{section} -> {key}")

    if missing_keys:
        print(f"ERROR: Missing keys in config.ini: {', '.join(missing_keys)}")
        sys.exit(1)  # Exit the program if keys are missing

    # Extract and return configuration variables with manual type conversion
    return {
        "BASE_DIR": base_dir,
        "CONTROLS": {
            "controller_name": config['CONTROLS']['controller_name'],
        },
        "STT": {
            "wake_word": config['STT']['wake_word'],
            "use_server": config.getboolean('STT', 'use_server'),
            "server_url": config['STT']['server_url'],
            "vosk_model": config['STT']['vosk_model'],
            "use_indicators": config.getboolean('STT', 'use_indicators'),
        },
        "CHAR": {
            "character_card_path": config['CHAR']['character_card_path'],
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
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
            "azure_region": config['TTS']['azure_region'],
            "ttsurl": config['TTS']['ttsurl'],
            "toggle_charvoice": config.getboolean('TTS', 'toggle_charvoice'),
            "tts_voice": config['TTS']['tts_voice'],
            "voice_only": config.getboolean('TTS', 'voice_only'),
            "is_talking_override": config.getboolean('TTS', 'is_talking_override'),
            "is_talking": config.getboolean('TTS', 'is_talking'),
            "global_timer_paused": config.getboolean('TTS', 'global_timer_paused'),
        },
        "DISCORD": {
            "TOKEN": config['DISCORD']['TOKEN'],
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
        "tabby": "TABBY_API_KEY"
    }

    # Check if the backend is supported
    if llm_backend not in backend_to_env_var:
        raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Unsupported LLM backend: {llm_backend}")

    # Fetch the API key from the environment
    api_key = os.getenv(backend_to_env_var[llm_backend])
    if not api_key:
        raise ValueError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: API key not found for LLM backend: {llm_backend}")
    
    return api_key
