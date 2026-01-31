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
from typing import Optional, Dict, List, Tuple
from enum import Enum

from modules.module_messageQue import queue_message

# === TARS Configuration Management System ===
# Import TARS CMS components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_cms import TarsConfigManager, ConfigAction, ActionType, ConfigSection, ConfigField

# === Initialization ===
load_dotenv()  # Load environment variables from .env file

character_name = "TARS"

@dataclass
class TTSConfig:
    """Configuration class for Text-to-Speech settings"""
    ttsoption: str
    toggle_charvoice: bool
    tts_voice: Optional[str]
    is_talking_override: bool
    is_talking: bool
    global_timer_paused: bool
    
    # Azure specific settings
    azure_api_key: Optional[str] = None
    azure_region: Optional[str] = None
    
    # ElevenLabs specific settings
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_model: Optional[str] = None
    
    # Server specific settings
    ttsurl: Optional[str] = None

    #openai tts
    openai_voice: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    minimax_api_key: Optional[str] = None
    minimax_voice_id: Optional[str] = None
    minimax_model: Optional[str] = None



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
            is_talking_override=config_dict['is_talking_override'],
            is_talking=config_dict['is_talking'],
            global_timer_paused=config_dict['global_timer_paused'],
            azure_api_key=config_dict.get('azure_api_key'),
            azure_region=config_dict.get('azure_region'),
            elevenlabs_api_key=config_dict.get('elevenlabs_api_key'),
            elevenlabs_voice_id=config_dict.get('elevenlabs_voice_id'),
            elevenlabs_model=config_dict.get('elevenlabs_model'),
            ttsurl=config_dict.get('ttsurl'),
            openai_voice=config_dict.get('openai_voice'),
            openai_api_key=config_dict.get('openai_api_key'),
            minimax_api_key=config_dict.get('minimax_api_key'),
            minimax_voice_id=config_dict.get('minimax_voice_id'),
            minimax_model=config_dict.get('minimax_model'),
        )

def _parse_screensaver_list(value: str) -> List[str]:
    """
    Parse the screensaver_list configuration value.
    
    Args:
        value: Configuration string (either "random" or comma-separated list)
        
    Returns:
        List of screensaver names, or ["random"] if random mode is selected
    """
    value = value.strip()
    
    # If "random", return it as a single-item list
    if value.lower() == "random":
        return ["random"]
    
    # Otherwise, parse as comma-separated list
    # Strip whitespace from each item and filter out empty strings
    screensavers = [s.strip() for s in value.split(',') if s.strip()]
    
    # If list is empty after parsing, default to random
    if not screensavers:
        return ["random"]
    
    return screensavers

def load_config():
    global character_name
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
            "swap_turn_directions": config.getboolean('CONTROLS', 'swap_turn_directions', fallback=False),
        },
        "STT": {
            "language" : config['STT']['language'],
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
            "character_name": character_name,
            "character_card_path": config['CHAR']['character_card_path'],
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
            "traits": persona_traits,
            "responses": config['CHAR']['responses'],
            "thinking_responses": config['CHAR']['thinking_responses'],
        },
        "LLM": {
            "llm_backend": config['LLM']['llm_backend'],
            "base_url": config['LLM']['base_url'],
            "api_key": get_api_key(config['LLM']['llm_backend']),
            "openai_model": config['LLM']['openai_model'],
            "grok_model": config['LLM']['grok_model'],
            "override_encoding_model": config['LLM']['override_encoding_model'],
            "contextsize": int(config['LLM']['contextsize']),
            "max_tokens": int(config['LLM']['max_tokens']),
            "temperature": float(config['LLM']['temperature']),
            "top_p": float(config['LLM']['top_p']),
            "seed": int(config['LLM']['seed']),
            "systemprompt": config['LLM']['systemprompt'],
        },
        "VISION": {
            "enabled": config.getboolean('VISION', 'enabled'),
            "server_hosted": config.getboolean('VISION', 'server_hosted'),
            "base_url": config['VISION']['base_url'],
        },
        "EMOTION": {
            "enabled": config.getboolean('EMOTION', 'enabled'),
            "emotion_model": config['EMOTION']['emotion_model'],
        },
        "TTS": TTSConfig.from_config_dict({
            "ttsoption": config['TTS']['ttsoption'],
            "azure_api_key": os.getenv('AZURE_API_KEY'),
            "elevenlabs_api_key": os.getenv('ELEVENLABS_API_KEY'),
            "azure_region": config['TTS']['azure_region'],
            'minimax_api_key': os.getenv('MINIMAX_API_KEY'),
            "openai_api_key": os.getenv('OPENAI_API_KEY'),
            "ttsurl": config['TTS']['ttsurl'],
            "toggle_charvoice": config.getboolean('TTS', 'toggle_charvoice'),
            "tts_voice": config['TTS']['tts_voice'],
            "elevenlabs_voice_id": config['TTS']['elevenlabs_voice_id'],
            "elevenlabs_model": config['TTS']['elevenlabs_model'],
            "minimax_voice_id": config['TTS']['minimax_voice_id'],
            "minimax_model": config['TTS']['minimax_model'],
            "is_talking_override": config.getboolean('TTS', 'is_talking_override'),
            "is_talking": config.getboolean('TTS', 'is_talking'),
            "global_timer_paused": config.getboolean('TTS', 'global_timer_paused'),
            "openai_voice" : config['TTS']['openai_voice'],            
        }),
        "CHATUI": {
            "enabled": config['CHATUI']['enabled'],
        },
        "RAG": {
            "strategy": config.get('RAG', 'strategy', fallback='naive'),
            "vector_weight": config.getfloat('RAG', 'vector_weight', fallback=0.5),
            "top_k": config.getint('RAG', 'top_k', fallback=5),
            "context_window": config.getint('RAG', 'context_window', fallback=2),
            "max_memories": config.getint('RAG', 'max_memories', fallback=3),
            "recency_boost_days": config.getint('RAG', 'recency_boost_days', fallback=7),
            "enable_topic_tracking": config.getboolean('RAG', 'enable_topic_tracking'),
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
            # Arm Servos
            "arms_present": config.getboolean('SERVO', 'arms_present'),
            "leftMainMin": config['SERVO']['leftMainMin'],
            "leftForarmMin": config['SERVO']['leftForarmMin'],
            "leftHandMin": config['SERVO']['leftHandMin'],
            "leftMainMax": config['SERVO']['leftMainMax'],
            "leftForarmMax": config['SERVO']['leftForarmMax'],
            "leftHandMax": config['SERVO']['leftHandMax'],
            "leftMainOffset": config['SERVO']['leftMainOffset'],
            "leftForearmOffset": config['SERVO']['leftForearmOffset'],
            "leftHandOffset": config['SERVO']['leftHandOffset'],
            "rightMainMin": config['SERVO']['rightMainMin'],
            "rightForarmMin": config['SERVO']['rightForarmMin'],
            "rightHandMin": config['SERVO']['rightHandMin'],
            "rightMainMax": config['SERVO']['rightMainMax'],
            "rightForarmMax": config['SERVO']['rightForarmMax'],
            "rightHandMax": config['SERVO']['rightHandMax'],
            "rightMainOffset": config['SERVO']['rightMainOffset'],
            "rightForearmOffset": config['SERVO']['rightForearmOffset'],
            "rightHandOffset": config['SERVO']['rightHandOffset'],
            # Dual Height Servos (Pin 0 = Left, Pin 1 = Right)
            "leftUpHeight": config['SERVO']['leftUpHeight'],
            "leftDownHeight": config['SERVO']['leftDownHeight'],
            "perfectLeftHeightOffset": config['SERVO']['perfectLeftHeightOffset'],
            "rightUpHeight": config['SERVO']['rightUpHeight'],
            "rightDownHeight": config['SERVO']['rightDownHeight'],
            "perfectRightHeightOffset": config['SERVO']['perfectRightHeightOffset'],
            # Left Leg Servo (Pin 2)
            "forwardLeftLeg": config['SERVO']['forwardLeftLeg'],
            "backLeftLeg": config['SERVO']['backLeftLeg'],
            "perfectLeftLegOffset": config['SERVO']['perfectLeftLegOffset'],
            # Right Leg Servo (Pin 3)
            "forwardRightLeg": config['SERVO']['forwardRightLeg'],
            "backRightLeg": config['SERVO']['backRightLeg'],
            "perfectRightLegOffset": config['SERVO']['perfectRightLegOffset'],
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
            "show_mouse": config.getboolean('UI', 'show_mouse'),
            "use_camera_module": config.getboolean('UI', 'use_camera_module'),
            "fullscreen": config.getboolean('UI', 'fullscreen'),
            "font_size": int(config['UI']['font_size']),  
            "target_fps": int(config['UI']['target_fps']),
            "screensaver_timer": config.getint('UI', 'screensaver_timer', fallback=300), 
            "show_cpu_temp": config.getboolean('UI', 'show_cpu_temp', fallback=False),
            "screensaver_list": _parse_screensaver_list(config.get('UI', 'screensaver_list', fallback='random')),
            "show_time": config.getboolean('UI', 'show_time', fallback=True),
            "ampm_format": config.getboolean('UI', 'ampm_format', fallback=True),
            "screensaver_cycle_interval": config.getint('UI', 'screensaver_cycle_interval', fallback=300), 
        },
        "BATTERY": {
            "battery_capacity_mAh":  int(config['BATTERY']['battery_capacity_mAh']),
            "battery_initial_voltage":  float(config['BATTERY']['battery_initial_voltage']),
            "battery_cutoff_voltage":  float(config['BATTERY']['battery_cutoff_voltage']),
            "auto_shutdown": config.getboolean('BATTERY', 'auto_shutdown')     
        },
        "MISC": {
            "ventilate": config.getboolean('MISC', 'ventilate', fallback=False), 
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
        "grok": "GROK_API_KEY",
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


def reload_persona_settings():
    """
    Reload persona settings from persona.ini file.
    This should be called before each LLM response to ensure fresh settings are used.
    
    Returns:
    - dict: Dictionary of persona traits, or None if failed
    """
    global character_name
    
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')
        
        if not os.path.exists(persona_path):
            queue_message(f"WARNING: persona.ini not found at {persona_path}")
            return None
        
        persona_config = configparser.ConfigParser()
        persona_config.read(persona_path, encoding='utf-8')
        
        if 'PERSONA' not in persona_config:
            queue_message("WARNING: [PERSONA] section not found in persona.ini")
            return None
        
        # Convert all values to integers
        persona_traits = {key: int(value) for key, value in persona_config['PERSONA'].items()}
        
        return persona_traits
        
    except Exception as e:
        queue_message(f"ERROR reloading persona settings: {e}")
        return None

def update_character_setting(setting, value):
    global character_name
    """
    Update a specific setting in the [PERSONA] section of persona.ini file.

    Parameters:
    - setting (str): The setting to update (e.g., 'humor', 'honesty', 'sarcasm').
    - value (int): The new value for the setting (0-100).

    Returns:
    - bool: True if the update is successful, False otherwise.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')
        
        if not os.path.exists(config_path):
            queue_message(f"ERROR: persona.ini not found at {config_path}")
            return False
        
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        if 'PERSONA' not in config:
            queue_message("ERROR: [PERSONA] section not found")
            return False

        config['PERSONA'][setting] = str(int(value))

        with open(config_path, 'w', encoding='utf-8') as config_file:
            config.write(config_file)

        queue_message(f"Updated {setting} to {value} in [PERSONA] section.")
        return True

    except Exception as e:
        queue_message(f"ERROR updating {setting}: {e}")
        return False


# === TARS Configuration Management System Integration ===

class ConfigUpdateResult(Enum):
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BACKUP_FAILED = "BACKUP_FAILED"
    WRITE_ERROR = "WRITE_ERROR"
    TEMPLATE_MISMATCH = "TEMPLATE_MISMATCH"

@dataclass
class ConfigUpdateResponse:
    result: ConfigUpdateResult
    message: str
    actions_taken: List[str] = None
    backup_location: str = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.actions_taken is None:
            self.actions_taken = []
        if self.errors is None:
            self.errors = []

class TarsConfigIntegration:
    """
    Integration class that provides web-friendly access to TARS Configuration Management System
    """
    
    def __init__(self):
        self.cms = TarsConfigManager()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    def validate_config_data(self, config_data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate configuration data against the template structure
        
        Args:
            config_data: Dictionary of configuration sections and fields
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Load template structure
            template_sections = self.cms.parse_config_structure(self.cms.template_file)
            
            # Validate each section and field
            for section_name, section_data in config_data.items():
                if section_name not in template_sections:
                    errors.append(f"Unknown section: [{section_name}]")
                    continue
                    
                template_section = template_sections[section_name]
                
                # Validate fields in this section
                for field_name, field_value in section_data.items():
                    if field_name not in template_section.fields:
                        errors.append(f"Unknown field: [{section_name}] {field_name}")
                        continue
                        
                    # Type validation based on template field
                    template_field = template_section.fields[field_name]
                    if not self._validate_field_type(field_name, field_value, template_field.value):
                        errors.append(f"Invalid value for [{section_name}] {field_name}: '{field_value}' (type: {type(field_value).__name__})")
                        
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
            
        return len(errors) == 0, errors
    
    def _validate_field_type(self, field_name: str, value: any, template_value: str) -> bool:
        """
        Validate field value type based on template and field name patterns
        Handles both actual types and string representations from web UI
        """
        try:
            # Convert value to string for consistent checking
            str_value = str(value).lower().strip()
            
            # Boolean fields - accept bool, "true"/"false", "1"/"0"
            if field_name in ['enabled', 'toggle_charvoice', 'is_talking_override', 
                            'is_talking', 'global_timer_paused', 'use_indicators', 'server_hosted',
                            'restore_faces', 'UI_enabled', 'show_mouse', 'use_camera_module',
                            'fullscreen', 'auto_shutdown']:
                return (isinstance(value, bool) or 
                       str_value in ['true', 'false', '1', '0', 'yes', 'no', 'on', 'off'])
            
            # Integer fields - accept int, numeric strings
            elif field_name in ['sensitivity', 'speechdelay', 'contextsize', 'max_tokens',
                              'seed', 'top_k', 'steps', 'width', 'height', 'font_size',
                              'target_fps', 'battery_capacity_mAh']:
                try:
                    int(float(str_value))  # Allow "8.0" -> 8
                    return True
                except (ValueError, TypeError):
                    return False
            
            # Float fields - accept float, numeric strings
            elif field_name in ['temperature', 'top_p', 'vector_weight', 'denoising_strength',
                              'cfg_scale', 'battery_initial_voltage', 'battery_cutoff_voltage']:
                try:
                    float(str_value)
                    return True
                except (ValueError, TypeError):
                    return False
            
            # String fields - accept any value (most fields are strings)
            else:
                return True  # Most fields are strings, so accept anything
                
        except Exception:
            return False
    
    def update_config_from_web(self, config_data: Dict, create_backup: bool = True) -> ConfigUpdateResponse:
        """
        Update configuration from web UI data using TARS CMS
        
        Args:
            config_data: Dictionary of configuration sections and fields
            create_backup: Whether to create a backup before updating
            
        Returns:
            ConfigUpdateResponse with result and details
        """
        actions_taken = []
        
        try:
            # Step 1: Validate the input data
            is_valid, validation_errors = self.validate_config_data(config_data)
            if not is_valid:
                return ConfigUpdateResponse(
                    result=ConfigUpdateResult.VALIDATION_ERROR,
                    message="Configuration validation failed",
                    errors=validation_errors
                )
            
            actions_taken.append("Configuration data validated successfully")
            
            # Step 2: Create backup if requested
            backup_location = None
            if create_backup:
                try:
                    if self.cms.create_backup():
                        backup_location = self.cms.backup_file
                        actions_taken.append(f"Backup created at {backup_location}")
                    else:
                        return ConfigUpdateResponse(
                            result=ConfigUpdateResult.BACKUP_FAILED,
                            message="Failed to create backup",
                            errors=["Backup creation failed"]
                        )
                except Exception as e:
                    return ConfigUpdateResponse(
                        result=ConfigUpdateResult.BACKUP_FAILED,
                        message=f"Backup creation error: {str(e)}",
                        errors=[str(e)]
                    )
            
            # Step 3: Load current and template configurations
            template_sections = self.cms.parse_config_structure(self.cms.template_file)
            existing_sections = self.cms.parse_config_structure(self.cms.config_file)
            
            # Step 4: Create updated configuration structure
            final_sections = {}
            
            for section_name, template_section in template_sections.items():
                # Create final section with template structure
                final_section = ConfigSection(
                    name=section_name,
                    inline_comment=template_section.inline_comment,
                    description_comments=template_section.description_comments.copy() if template_section.description_comments else []
                )
                
                # Process each field in the template section
                for field_name, template_field in template_section.fields.items():
                    # Determine the value to use
                    if section_name in config_data and field_name in config_data[section_name]:
                        # Use value from web input
                        new_value = str(config_data[section_name][field_name])
                        actions_taken.append(f"Updated [{section_name}] {field_name} = {new_value}")
                    elif section_name in existing_sections and field_name in existing_sections[section_name].fields:
                        # Preserve existing value
                        existing_value = existing_sections[section_name].fields[field_name].value
                        new_value = existing_value
                        actions_taken.append(f"Preserved [{section_name}] {field_name} = {existing_value}")
                    else:
                        # Use template default
                        new_value = template_field.value
                        actions_taken.append(f"Used template default [{section_name}] {field_name} = {new_value}")
                    
                    # Create final field with template structure but updated value
                    final_field = ConfigField(
                        name=field_name,
                        value=new_value,
                        inline_comment=template_field.inline_comment,
                        description_comments=template_field.description_comments.copy() if template_field.description_comments else []
                    )
                    
                    final_section.fields[field_name] = final_field
                
                final_sections[section_name] = final_section
            
            # Step 5: Write the updated configuration
            try:
                self.cms.write_config_file(final_sections)
                actions_taken.append("Configuration file written successfully")
                
                return ConfigUpdateResponse(
                    result=ConfigUpdateResult.SUCCESS,
                    message="Configuration updated successfully using TARS CMS",
                    actions_taken=actions_taken,
                    backup_location=backup_location
                )
                
            except Exception as e:
                return ConfigUpdateResponse(
                    result=ConfigUpdateResult.WRITE_ERROR,
                    message=f"Failed to write configuration: {str(e)}",
                    errors=[str(e)],
                    backup_location=backup_location
                )
                
        except Exception as e:
            return ConfigUpdateResponse(
                result=ConfigUpdateResult.WRITE_ERROR,
                message=f"Unexpected error during configuration update: {str(e)}",
                errors=[str(e)],
                backup_location=backup_location
            )
    
    def get_config_analysis(self) -> Dict:
        """
        Get configuration analysis from TARS CMS
        
        Returns:
            Dictionary with analysis results
        """
        try:
            actions = self.cms.analyze_differences()
            
            analysis = {
                "total_actions": len(actions),
                "sections_to_add": len([a for a in actions if a.action == ActionType.ADD_SECTION]),
                "fields_to_add": len([a for a in actions if a.action == ActionType.ADD_FIELD]),
                "comments_to_add": len([a for a in actions if a.action == ActionType.ADD_COMMENT]),
                "sections_to_remove": len([a for a in actions if a.action == ActionType.REMOVE_SECTION]),
                "fields_to_remove": len([a for a in actions if a.action == ActionType.REMOVE_FIELD]),
                "values_to_preserve": len([a for a in actions if a.action == ActionType.PRESERVE_VALUE]),
                "is_synchronized": len(actions) == 0,
                "actions": [
                    {
                        "action": action.action.value,
                        "section": action.section,
                        "field": action.field,
                        "value": action.value,
                        "comment": action.comment
                    } for action in actions
                ]
            }
            
            return analysis
            
        except Exception as e:
            return {
                "error": str(e),
                "is_synchronized": False
            }
    
    def sync_with_template(self, interactive: bool = False) -> ConfigUpdateResponse:
        """
        Synchronize current configuration with template using TARS CMS
        
        Args:
            interactive: Whether to use interactive mode for removals
            
        Returns:
            ConfigUpdateResponse with result and details
        """
        try:
            # Analyze differences
            actions = self.cms.analyze_differences()
            
            if not actions:
                return ConfigUpdateResponse(
                    result=ConfigUpdateResult.SUCCESS,
                    message="Configuration is already synchronized with template",
                    actions_taken=["No changes needed"]
                )
            
            # Handle removals based on interactive setting
            if interactive:
                actions = self.cms.confirm_removals(actions)
            else:
                # Auto-approve removals for programmatic use
                actions = [a for a in actions if a.action not in [ActionType.REMOVE_SECTION, ActionType.REMOVE_FIELD]]
            
            # Apply changes
            self.cms.apply_changes(actions)
            
            return ConfigUpdateResponse(
                result=ConfigUpdateResult.SUCCESS,
                message=f"Synchronized configuration with template ({len(actions)} actions applied)",
                actions_taken=[f"Applied {len(actions)} configuration changes"]
            )
            
        except Exception as e:
            return ConfigUpdateResponse(
                result=ConfigUpdateResult.WRITE_ERROR,
                message=f"Synchronization failed: {str(e)}",
                errors=[str(e)]
            )

# Convenience functions for easy integration
def update_config_from_web_ui(config_data: Dict, create_backup: bool = True) -> Dict:
    """
    Convenience function to update configuration from web UI
    
    Args:
        config_data: Dictionary of configuration sections and fields
        create_backup: Whether to create a backup before updating
        
    Returns:
        Dictionary with result information suitable for JSON response
    """
    integration = TarsConfigIntegration()
    response = integration.update_config_from_web(config_data, create_backup)
    
    return {
        "success": response.result == ConfigUpdateResult.SUCCESS,
        "message": response.message,
        "result": response.result.value,
        "actions_taken": response.actions_taken,
        "backup_location": response.backup_location,
        "errors": response.errors
    }

def get_config_sync_status() -> Dict:
    """
    Get configuration synchronization status
    
    Returns:
        Dictionary with sync status information
    """
    integration = TarsConfigIntegration()
    return integration.get_config_analysis()


CONFIG_UI_FIELDS = {
    'CONTROLS': {
        '__description__': 'Controller settings',
        'controller_name': {
            'description': 'Name of the controller used for interaction'
        },
        'enabled': {
            'description': 'Enable use of controller for interaction'
        },
        'voicemovement': {
            'description': 'Enable or disable movement via voice control'
        },
        'swap_turn_directions': {
            'description': 'Swap left and right turn directions (for mirrored robot orientation)'
        },
    },

    'STT': {
        '__description__': 'Speech-to-Text configuration',
        'language': {
            'description': 'Spoken language (if not english, use stt_processor = openai)'
        },
        'wake_word': {
            'description': 'Wake word for activating the system'
        },
        'wake_word_processor': {
            'options': ['picovoice', 'fastrtc', 'atomik'],
            'description': 'Wake word detection processor'
        },
        'sensitivity': {
            'description': 'Wake word sensitivity (1=lenient, 10=strict)'
        },
        'stt_processor': {
            'options': ['vosk', 'faster-whisper', 'silero', 'fastrtc', 'openai', 'external'],
            'description': 'Speech-to-text processor'
        },
        'use_indicators': {
            'description': 'Use beeps to indicate when listening'
        },
        'external_url': {
            'description': 'URL for external STT server'
        },
        'whisper_model': {
            'options': ['tiny', 'base', 'small', 'medium', 'large'],
            'description': 'Whisper model size for onboard transcription'
        },
        'vosk_model': {
            'description': 'Vosk model name for local STT'
        },
        'vad_method': {
            'options': ['silero', 'rms'],
            'description': 'Voice activity detection method'
        },
        'speechdelay': {
            'description': 'Tenths of seconds to wait before sleeping (20 = 2 seconds)'
        },
        'picovoice_keyword_path': {
            'description': 'Path to Porcupine keyword file'
        },
    },

    'CHAR': {
        '__description__': 'Character-specific details',
        'character_card_path': {
            'description': 'Path to character JSON file'
        },
        'user_name': {
            'description': 'Name of the user'
        },
        'user_details': {
            'description': 'Additional user details for context'
        },
        'responses': {
            'type': 'array',
            'description': 'Wake word responses (what TARS says after hearing wake word)'
        },
        'thinking_responses': {
            'type': 'array',
            'description': 'Thinking responses (what TARS says while processing)'
        },
    },

    'LLM': {
        '__description__': 'Large Language Model configuration',
        'llm_backend': {
            'options': ['openai', 'grok', 'tabby', 'ooba'],
            'description': 'LLM backend service'
        },
        'base_url': {
            'description': 'API URL (OpenAI: https://api.openai.com, Grok: https://api.x.ai)'
        },
        'openai_model': {
            'description': 'OpenAI model (gpt-4o-mini, gpt-4o, etc.)'
        },
        'grok_model': {
            'options': ['grok-4-1-fast-non-reasoning', 'grok-4-1-fast-reasoning', 'grok-3-mini'],
            'description': 'Grok model'
        },
        'override_encoding_model': {
            'options': ['cl100k_base', 'p50k_base', 'r50k_base', 'gpt2'],
            'description': 'Token encoding model override'
        },
        'contextsize': {
            'description': 'Maximum token context size'
        },
        'max_tokens': {
            'description': 'Maximum tokens per response'
        },
        'temperature': {
            'description': 'Randomness (0.0-1.0, higher = more random)'
        },
        'top_p': {
            'description': 'Nucleus sampling threshold'
        },
        'seed': {
            'description': 'Random seed (-1 for random)'
        },
        'systemprompt': {
            'description': 'System prompt defining LLM behavior'
        },
    },

    'VISION': {
        '__description__': 'Vision/image recognition configuration',
        'enabled': {
            'description': 'Enable vision module'
        },
        'server_hosted': {
            'description': 'Vision server is hosted locally'
        },
        'base_url': {
            'description': 'Vision server API URL'
        },
    },

    'EMOTION': {
        '__description__': 'Emotion detection for avatars',
        'enabled': {
            'description': 'Enable emotion detection'
        },
        'emotion_model': {
            'description': 'HuggingFace model for emotion analysis'
        },
    },

    'TTS': {
        '__description__': 'Text-to-Speech configuration',
        'ttsoption': {
            'options': ['espeak', 'piper', 'silero', 'alltalk', 'elevenlabs', 'minimax', 'openai', 'azure'],
            'description': 'TTS engine'
        },
        'ttsurl': {
            'description': 'TTS server URL (for alltalk)'
        },
        'tts_voice': {
            'description': 'Voice name (for azure/alltalk)'
        },
        'azure_region': {
            'options': ['eastus', 'eastus2', 'westus', 'westus2', 'centralus', 'northeurope', 'westeurope'],
            'description': 'Azure region'
        },
        'elevenlabs_voice_id': {
            'description': 'ElevenLabs voice ID'
        },
        'elevenlabs_model': {
            'options': ['eleven_multilingual_v2', 'eleven_monolingual_v1', 'eleven_turbo_v2'],
            'description': 'ElevenLabs model'
        },
        'minimax_voice_id': {
            'description': 'Minimax voice ID'
        },
        'minimax_model': {
            'options': ['speech-2.6-turbo', 'speech-2.8-turbo', 'speech-2.6-hd', 'speech-2.8-hd'],
            'description': 'Minimax model'
        },
        'openai_voice': {
            'options': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            'description': 'OpenAI TTS voice'
        },
        'toggle_charvoice': {
            'description': 'Use character-specific voice settings'
        },
    },

    'STABLE_DIFFUSION': {
        '__description__': 'Image Generation',
        'enabled': {
            'description': 'Enable image generation'
        },
        'service': {
            'options': ['automatic1111', 'openai'],
            'description': 'Image generation service'
        },
        'url': {
            'description': 'Automatic1111 server URL'
        },
        'prompt_prefix': {
            'description': 'Prefix added to image prompts'
        },
        'prompt_postfix': {
            'description': 'Postfix added to image prompts'
        },
        'negative_prompt': {
            'description': 'Negative prompt (things to avoid)'
        },
        'seed': {
            'description': 'Seed (-1 for random)'
        },
        'sampler_name': {
            'options': ['Euler a', 'Euler', 'DPM++ 2M Karras', 'DPM++ SDE Karras', 'DDIM'],
            'description': 'Sampler'
        },
        'steps': {
            'description': 'Generation steps'
        },
        'cfg_scale': {
            'description': 'CFG scale (prompt adherence)'
        },
        'width': {
            'description': 'Image width in pixels'
        },
        'height': {
            'description': 'Image height in pixels'
        },
        'denoising_strength': {
            'description': 'Denoising strength'
        },
        'restore_faces': {
            'description': 'Enable face restoration'
        },
    },

    'CHATUI': {
        '__description__': 'Chat UI settings',
        'enabled': {
            'description': 'Enable Chat UI (required for avatars)'
        },
    },

    'UI': {
        '__description__': 'Graphical interface settings',
        'UI_enabled': {
            'description': 'Enable the visual UI'
        },
        'use_camera_module': {
            'description': 'Enable camera'
        },
        'show_mouse': {
            'description': 'Show software mouse cursor'
        },
        'fullscreen': {
            'description': 'Run in fullscreen mode'
        },
        'font_size': {
            'description': 'Font size (9-20)'
        },
        'screensaver_timer': {
            'description': 'Seconds before screensaver (0 = disabled)'
        },
        'screensaver_cycle_interval': {
            'description': 'Seconds between screensaver changes'
        },
        'screensaver_list': {
            'type': 'array',
            'description': 'Screensavers: random, or specific ones (blackhole, waves, matrix, starfield, hyperspace, terminal, face, fractal, pacman, nebulas, pictures, dashboard, defrag, bounce, endurance)'
        },
        'show_time': {
            'description': 'Show time on screensaver'
        },
        'ampm_format': {
            'description': 'Use AM/PM time format'
        },
        'show_cpu_temp': {
            'description': 'Show CPU temperature'
        },
        'target_fps': {
            'description': 'UI refresh rate (FPS)'
        },
    },

    'RAG': {
        '__description__': 'Retrieval Augmented Generation (Memory)',
        'strategy': {
            'options': ['naive', 'hybrid'],
            'description': 'Retrieval strategy (naive=vector-only, hybrid=vector+BM25)'
        },
        'top_k': {
            'description': 'Number of documents to retrieve'
        },
        'context_window': {
            'description': 'Memories before/after each match'
        },
        'max_memories': {
            'description': 'Max results to expand'
        },
        'recency_boost_days': {
            'description': 'Days to boost recent chats'
        },
        'enable_topic_tracking': {
            'description': 'Enable long-term memory'
        },
    },

    'HOME_ASSISTANT': {
        '__description__': 'Home Assistant integration',
        'enabled': {
            'description': 'Enable Home Assistant'
        },
        'url': {
            'description': 'Home Assistant URL'
        },
    },

    'DISCORD': {
        '__description__': 'Discord bot integration',
        'enabled': {
            'description': 'Enable Discord integration'
        },
        'channel_id': {
            'description': 'Discord channel ID'
        },
    },

    'MISC': {
        '__description__': 'Miscellaneous settings',
        'ventilate': {
            'description': 'Auto-ventilate pose for airflow'
        },
    },
}