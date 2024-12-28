"""
module_config.py

Configuration Loading Module for GPTARS Application.

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

    # Extract and return configuration variables
    return {
        "BASE_DIR": base_dir,
        "CONTROLS": {
            "controller_name": config['CONTROLS']['controller_name'],
        },
        "STT": {
            "wake_word": config['STT']['wake_word'],
            "use_server": config.getboolean('STT', 'use_server'),
            "server_url": config['STT']['server_url'],
        },
        "CHAR": {
            "character_card_path": config['CHAR']['character_card_path'],
            "char_name": config['CHAR']['char_name'],
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
        },
        "LLM": {
            "llm_backend": config['LLM']['llm_backend'],
            "base_url": config['LLM']['base_url'],
            "api_key": get_api_key(config['LLM']['llm_backend']),
            "openai_model": config['LLM']['openai_model'],
            "contextsize": config.getint('LLM', 'contextsize'),
            "max_tokens": config.getint('LLM', 'max_tokens'),
            "temperature": config.getfloat('LLM', 'temperature'),
            "top_p": config.getfloat('LLM', 'top_p'),
            "seed": config.getint('LLM', 'seed'),
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

