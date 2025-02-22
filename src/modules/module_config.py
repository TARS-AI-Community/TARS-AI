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
from dataclasses import dataclass
from typing import Optional

from modules.module_messageQue import queue_message

# === Initialization ===
load_dotenv()  # Load environment variables from .env file

@dataclass
class TTSConfig:
    """Configuration class for Text-to-Speech settings"""
    ttsoption: str
    toggle_charvoice: bool
    tts_voice: Optional[str]
    voice_only: bool
    is_talking_override: bool
    is_talking: bool
    global_timer_paused: bool
    
    # Azure specific settings
    azure_api_key: Optional[str] = None
    azure_region: Optional[str] = None
    
    # ElevenLabs specific settings
    elevenlabs_api_key: Optional[str] = None
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    
    # Server specific settings
    ttsurl: Optional[str] = None

    def __getitem__(self, key):
        """Enable dictionary-like access for backward compatibility"""
        return getattr(self, key)

    def validate(self) -> bool:
        """Validate the configuration based on ttsoption"""
        if self.ttsoption == "azure":
            if not (self.azure_api_key and self.azure_region):
                queue_message("ERROR: Azure API key and region are required for Azure TTS")
                return False
        elif self.ttsoption == "elevenlabs":
            if not self.elevenlabs_api_key:
                queue_message("ERROR: ElevenLabs API key is required for ElevenLabs TTS")
                return False
        elif self.ttsoption in ["xttsv2", "alltalk"]:
            if not self.ttsurl:
                queue_message("ERROR: TTS URL is required for server-based TTS")
                return False
        return True

    @classmethod
    def from_config_dict(cls, config_dict: dict) -> 'TTSConfig':
        """Create TTSConfig instance from configuration dictionary"""
        return cls(
            ttsoption=config_dict['ttsoption'],
            toggle_charvoice=config_dict['toggle_charvoice'],
            tts_voice=config_dict['tts_voice'],
            voice_only=config_dict['voice_only'],
            is_talking_override=config_dict['is_talking_override'],
            is_talking=config_dict['is_talking'],
            global_timer_paused=config_dict['global_timer_paused'],
            azure_api_key=config_dict.get('azure_api_key'),
            azure_region=config_dict.get('azure_region'),
            elevenlabs_api_key=config_dict.get('elevenlabs_api_key'),
            voice_id=config_dict.get('voice_id'),
            model_id=config_dict.get('model_id'),
            ttsurl=config_dict.get('ttsurl')
        )

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
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Ensures it resolves to src/
    config = configparser.ConfigParser()
    config_path = os.path.join(base_dir, 'config.ini')  # Ensures it joins "src/config.ini"
    config.read(config_path)  # Should correctly read "src/config.ini"

    # Parse the persona.ini file
    character_path = config.get("CHAR", "character_card_path")  # Get full path
    character_name = os.path.splitext(os.path.basename(character_path))[0]  # Extract filename without extension

    persona_config = configparser.ConfigParser()
    persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')

    if not os.path.exists(persona_path):
        queue_message(f"ERROR: {persona_path} not found.")
        sys.exit(1)  # Exit if persona.ini is missing

    persona_config.read(persona_path)

    # Ensure required sections and keys exist in config.ini
    required_sections = [
        'CONTROLS', 'STT', 'CHAR', 'LLM', 'VISION', 'EMOTION', 'TTS', 'DISCORD', 'SERVO', 'STABLE_DIFFUSION'
    ]
    missing_sections = [section for section in required_sections if section not in config]

    if missing_sections:
        queue_message(f"ERROR: Missing sections in config.ini: {', '.join(missing_sections)}")
        sys.exit(1)

    # Extract persona traits
    persona_traits = {}
    if 'PERSONA' in persona_config:
        persona_traits = {key: int(value) for key, value in persona_config['PERSONA'].items()}
    else:
        queue_message("ERROR: [PERSONA] section missing in persona.ini.")
        sys.exit(1)

    # Extract and return combined configurations
    return {
        "BASE_DIR": base_dir,
        "CONTROLS": {
            "controller_name": config['CONTROLS']['controller_name'],
            "enabled": config['CONTROLS']['enabled'],
            "voicemovement": config['CONTROLS']['voicemovement'],         
        },
        "STT": {
            "wake_word": config['STT']['wake_word'],
            "sensitivity": config['STT']['sensitivity'],
            "stt_processor": config['STT']['stt_processor'],
            "external_url": config['STT']['external_url'],
            "whisper_model": config['STT']['whisper_model'],
            "vosk_model": config['STT']['vosk_model'],
            "use_indicators": config.getboolean('STT', 'use_indicators'),
            "vad_method": config['STT']['vad_method'],
            "speechdelay": int(config['STT']['speechdelay']),
            "picovoice_keyword_path": config['STT']['picovoice_keyword_path'],
            "wake_word_processor": config['STT']['wake_word_processor'],
            "picovoice_api_key": os.getenv('PICOVOICE_API_KEY')
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
        "TTS": TTSConfig.from_config_dict({
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
        }),
        "CHATUI": {
            "enabled": config['CHATUI']['enabled'],
        },
        "RAG": {
            "strategy": config.get('RAG', 'strategy', fallback='naive'),
            "vector_weight": config.getfloat('RAG', 'vector_weight', fallback=0.5),
            "top_k": config.getint('RAG', 'top_k', fallback=5),
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
        "UI": {
            "UI_enabled": config.getboolean('UI', 'UI_enabled'),
            "maximize_console": config.getboolean('UI','maximize_console'),
            "screen_width": int(config['UI']['screen_width']),
            "screen_height": int(config['UI']['screen_height']),
            "rotation": int(config['UI']['rotation']),
            "show_mouse": config.getboolean('UI', 'show_mouse'),
            "use_camera_module": config.getboolean('UI', 'use_camera_module'),
            "background_id": int(config['UI']['background_id']),
        }
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
            queue_message("Error: [PERSONA] section not found in the config file.")
            return False

        # Update the setting
        config['PERSONA'][setting] = str(value)

        # Write the changes back to the file
        with open(config_path, 'w') as config_file:
            config.write(config_file)

        queue_message(f"Updated {setting} to {value} in [PERSONA] section.")
        return True

    except Exception as e:
        queue_message(f"Error updating setting: {e}")
        return False
