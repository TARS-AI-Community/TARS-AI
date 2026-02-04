"""
module_config.py

Configuration Loading Module for TARS-AI Application.

This module reads configuration details from the `config.ini` file and environment 
variables, providing a structured dictionary for easy access throughout the application. 
"""

import os
import sys
import configparser
from dotenv import load_dotenv
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Set
from enum import Enum

from modules.module_messageQue import queue_message

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_cms import TarsConfigManager, ConfigAction, ActionType, ConfigSection, ConfigField

load_dotenv()

character_name = "TARS"


class DeviceProfile(Enum):
    PI5 = "pi5"
    PI4 = "pi4"
    PI3 = "pi3"
    PIZERO2 = "pizero2"


@dataclass
class DeviceCapabilities:
    profile: DeviceProfile
    allowed_stt: Set[str]
    allowed_tts: Set[str]
    allowed_vad: Set[str]
    allowed_wake: Set[str]
    can_use_embeddings: bool
    can_use_ui: bool
    can_use_vision: bool
    can_use_emotion: bool
    max_context_size: int
    fallback_stt: str
    fallback_tts: str
    fallback_vad: str
    fallback_wake: str


DEVICE_PROFILES: Dict[DeviceProfile, DeviceCapabilities] = {
    DeviceProfile.PI5: DeviceCapabilities(
        profile=DeviceProfile.PI5,
        allowed_stt={"vosk", "faster-whisper", "whisper", "fastrtc", "silero", "openai", "external"},
        allowed_tts={"espeak", "piper", "silero", "alltalk", "elevenlabs", "minimax", "openai", "azure"},
        allowed_vad={"silero", "rms"},
        allowed_wake={"picovoice", "fastrtc", "atomik"},
        can_use_embeddings=True,
        can_use_ui=True,
        can_use_vision=True,
        can_use_emotion=True,
        max_context_size=16000,
        fallback_stt="vosk",
        fallback_tts="espeak",
        fallback_vad="rms",
        fallback_wake="picovoice",
    ),
    DeviceProfile.PI4: DeviceCapabilities(
        profile=DeviceProfile.PI4,
        allowed_stt={"vosk", "openai", "external"},
        allowed_tts={"espeak", "piper", "alltalk", "elevenlabs", "minimax", "openai", "azure"},
        allowed_vad={"silero", "rms"},
        allowed_wake={"picovoice", "atomik"},
        can_use_embeddings=True,
        can_use_ui=True,
        can_use_vision=False,
        can_use_emotion=False,
        max_context_size=8000,
        fallback_stt="vosk",
        fallback_tts="espeak",
        fallback_vad="rms",
        fallback_wake="picovoice",
    ),
    DeviceProfile.PI3: DeviceCapabilities(
        profile=DeviceProfile.PI3,
        allowed_stt={"openai", "external"},
        allowed_tts={"espeak", "elevenlabs", "minimax", "openai", "azure"},
        allowed_vad={"rms"},
        allowed_wake={"picovoice", "atomik"},
        can_use_embeddings=False,
        can_use_ui=False,
        can_use_vision=False,
        can_use_emotion=False,
        max_context_size=4000,
        fallback_stt="openai",
        fallback_tts="openai",
        fallback_vad="rms",
        fallback_wake="picovoice",
    ),
    DeviceProfile.PIZERO2: DeviceCapabilities(
        profile=DeviceProfile.PIZERO2,
        allowed_stt={"openai"},
        allowed_tts={"elevenlabs", "minimax", "openai", "azure"},
        allowed_vad={"rms"},
        allowed_wake={"picovoice", "atomik"},
        can_use_embeddings=False,
        can_use_ui=False,
        can_use_vision=False,
        can_use_emotion=False,
        max_context_size=2000,
        fallback_stt="openai",
        fallback_tts="openai",
        fallback_vad="rms",
        fallback_wake="picovoice",
    ),
}

CAPABILITIES: Optional[DeviceCapabilities] = None
_OVERRIDES_APPLIED = False


def get_device_profile(version_str: str) -> DeviceProfile:
    version_map = {
        "pi5": DeviceProfile.PI5,
        "pi4": DeviceProfile.PI4,
        "pi3": DeviceProfile.PI3,
        "pizero2": DeviceProfile.PIZERO2,
        "pizero": DeviceProfile.PIZERO2,
        "zero2": DeviceProfile.PIZERO2,
        "zero": DeviceProfile.PIZERO2,
    }
    return version_map.get(version_str.lower().strip(), DeviceProfile.PI5)


def apply_device_overrides(config_dict: dict, capabilities: DeviceCapabilities) -> dict:
    global CAPABILITIES, _OVERRIDES_APPLIED
    CAPABILITIES = capabilities
    
    show_warnings = not _OVERRIDES_APPLIED
    _OVERRIDES_APPLIED = True
    
    stt_processor = config_dict["STT"]["stt_processor"]
    if stt_processor not in capabilities.allowed_stt:
        if show_warnings:
            queue_message(f"WARNING: STT '{stt_processor}' not supported on {capabilities.profile.value}, using '{capabilities.fallback_stt}'")
        config_dict["STT"]["stt_processor"] = capabilities.fallback_stt
    
    tts_option = config_dict["TTS"].ttsoption if hasattr(config_dict["TTS"], 'ttsoption') else config_dict["TTS"]["ttsoption"]
    if tts_option not in capabilities.allowed_tts:
        if show_warnings:
            queue_message(f"WARNING: TTS '{tts_option}' not supported on {capabilities.profile.value}, using '{capabilities.fallback_tts}'")
        if hasattr(config_dict["TTS"], 'ttsoption'):
            config_dict["TTS"].ttsoption = capabilities.fallback_tts
        else:
            config_dict["TTS"]["ttsoption"] = capabilities.fallback_tts
    
    vad_method = config_dict["STT"]["vad_method"]
    if vad_method not in capabilities.allowed_vad:
        if show_warnings:
            queue_message(f"WARNING: VAD '{vad_method}' not supported on {capabilities.profile.value}, using '{capabilities.fallback_vad}'")
        config_dict["STT"]["vad_method"] = capabilities.fallback_vad
    
    wake_processor = config_dict["STT"]["wake_word_processor"]
    if wake_processor not in capabilities.allowed_wake:
        if show_warnings:
            queue_message(f"WARNING: Wake word '{wake_processor}' not supported on {capabilities.profile.value}, using '{capabilities.fallback_wake}'")
        config_dict["STT"]["wake_word_processor"] = capabilities.fallback_wake
    
    if config_dict["LLM"]["contextsize"] > capabilities.max_context_size:
        if show_warnings:
            queue_message(f"WARNING: Context size {config_dict['LLM']['contextsize']} exceeds max {capabilities.max_context_size} for {capabilities.profile.value}")
        config_dict["LLM"]["contextsize"] = capabilities.max_context_size
    
    if not capabilities.can_use_ui and config_dict["UI"]["UI_enabled"]:
        if show_warnings:
            queue_message(f"WARNING: UI disabled for {capabilities.profile.value}")
        config_dict["UI"]["UI_enabled"] = False
    
    if not capabilities.can_use_vision and config_dict["VISION"]["enabled"]:
        if show_warnings:
            queue_message(f"WARNING: Vision disabled for {capabilities.profile.value}")
        config_dict["VISION"]["enabled"] = False
    
    if not capabilities.can_use_emotion and config_dict["EMOTION"]["enabled"]:
        if show_warnings:
            queue_message(f"WARNING: Emotion disabled for {capabilities.profile.value}")
        config_dict["EMOTION"]["enabled"] = False
    
    config_dict["_device"] = {
        "raspberry_version": capabilities.profile.value,
        "capabilities": capabilities,
    }
    
    return config_dict


def should_use_lite_memory(config: dict) -> bool:
    device_info = config.get("_device", {})
    caps = device_info.get("capabilities")
    if caps is not None:
        return not caps.can_use_embeddings
    return False


def get_capabilities() -> Optional[DeviceCapabilities]:
    return CAPABILITIES


@dataclass
class TTSConfig:
    ttsoption: str
    toggle_charvoice: bool
    tts_voice: Optional[str]
    is_talking_override: bool
    is_talking: bool
    global_timer_paused: bool
    azure_api_key: Optional[str] = None
    azure_region: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_model: Optional[str] = None
    ttsurl: Optional[str] = None
    openai_voice: Optional[str] = None
    openai_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None
    minimax_voice_id: Optional[str] = None
    minimax_model: Optional[str] = None

    def __getitem__(self, key):
        return getattr(self, key)

    def validate(self) -> bool:
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
    value = value.strip()
    if value.lower() == "random":
        return ["random"]
    screensavers = [s.strip() for s in value.split(',') if s.strip()]
    if not screensavers:
        return ["random"]
    return screensavers


def _format_screensaver_list(value) -> str:
    if isinstance(value, list):
        if len(value) == 0:
            return "random"
        elif len(value) == 1 and value[0].lower() == "random":
            return "random"
        else:
            return ",".join(str(item).strip() for item in value if str(item).strip())
    str_value = str(value).strip()
    if str_value.startswith('[') and str_value.endswith(']'):
        try:
            import json
            parsed = json.loads(str_value)
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    return "random"
                elif len(parsed) == 1 and str(parsed[0]).lower() == "random":
                    return "random"
                else:
                    return ",".join(str(item).strip() for item in parsed if str(item).strip())
        except (json.JSONDecodeError, ValueError):
            pass
    return str_value


def load_config():
    global character_name
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    sys.path.append(os.getcwd())

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = configparser.ConfigParser()
    config_path = os.path.join(base_dir, 'config.ini')
    config.read(config_path)

    character_path = config.get("CHAR", "character_card_path")
    character_name = os.path.splitext(os.path.basename(character_path))[0]

    persona_config = configparser.ConfigParser()
    persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')

    if not os.path.exists(persona_path):
        queue_message(f"ERROR: {persona_path} not found.")
        sys.exit(1)

    persona_config.read(persona_path)

    required_sections = [
        'CONTROLS', 'STT', 'CHAR', 'LLM', 'VISION', 'EMOTION', 'TTS', 'DISCORD', 'SERVO', 'STABLE_DIFFUSION'
    ]
    missing_sections = [section for section in required_sections if section not in config]

    if missing_sections:
        queue_message(f"ERROR: Missing sections in config.ini: {', '.join(missing_sections)}")
        sys.exit(1)

    persona_traits = {}
    if 'PERSONA' in persona_config:
        persona_traits = {key: int(value) for key, value in persona_config['PERSONA'].items()}
    else:
        queue_message("ERROR: [PERSONA] section missing in persona.ini.")
        sys.exit(1)

    raspberry_version = "pi5"
    if config.has_section('DEVICE') and config.has_option('DEVICE', 'raspberry_version'):
        raspberry_version = config.get('DEVICE', 'raspberry_version')
    
    device_profile = get_device_profile(raspberry_version)
    capabilities = DEVICE_PROFILES[device_profile]

    config_dict = {
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
            "latitude": config.get('CHAR', 'latitude', fallback=''),
            "longitude": config.get('CHAR', 'longitude', fallback=''),
            "location_name": config.get('CHAR', 'location_name', fallback=''),
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
            "leftUpHeight": config['SERVO']['leftUpHeight'],
            "leftDownHeight": config['SERVO']['leftDownHeight'],
            "perfectLeftHeightOffset": config['SERVO']['perfectLeftHeightOffset'],
            "rightUpHeight": config['SERVO']['rightUpHeight'],
            "rightDownHeight": config['SERVO']['rightDownHeight'],
            "perfectRightHeightOffset": config['SERVO']['perfectRightHeightOffset'],
            "forwardLeftLeg": config['SERVO']['forwardLeftLeg'],
            "backLeftLeg": config['SERVO']['backLeftLeg'],
            "perfectLeftLegOffset": config['SERVO']['perfectLeftLegOffset'],
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

    config_dict = apply_device_overrides(config_dict, capabilities)
    
    return config_dict


def get_api_key(llm_backend: str) -> str:
    backend_to_env_var = {
        "openai": "OPENAI_API_KEY",
        "grok": "GROK_API_KEY",
        "ooba": "OOBA_API_KEY",
        "tabby": "TABBY_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY"
    }
    if llm_backend not in backend_to_env_var:
        print(f"WARNING: Unsupported LLM backend '{llm_backend}', skipping API key lookup.")
        return ""
    api_key = os.getenv(backend_to_env_var[llm_backend])
    if not api_key:
        print(f"WARNING: No API key found for '{llm_backend}' (env var: {backend_to_env_var[llm_backend]}). LLM features will be unavailable.")
        return ""
    return api_key


def reload_persona_settings():
    global character_name
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')
        if not os.path.exists(persona_path):
            queue_message(f"WARNING: persona.ini not found at {persona_path}")
            return None
        persona_config = configparser.ConfigParser()
        persona_config.read(persona_path)
        if 'PERSONA' in persona_config:
            return {key: int(value) for key, value in persona_config['PERSONA'].items()}
        return None
    except Exception as e:
        queue_message(f"ERROR: Failed to reload persona settings: {e}")
        return None


def update_character_setting(trait: str, value: int):
    global character_name
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')
        if not os.path.exists(persona_path):
            queue_message(f"WARNING: persona.ini not found at {persona_path}")
            return False
        persona_config = configparser.ConfigParser()
        persona_config.read(persona_path)
        if 'PERSONA' not in persona_config:
            persona_config['PERSONA'] = {}
        persona_config['PERSONA'][trait] = str(value)
        with open(persona_path, 'w') as f:
            persona_config.write(f)
        queue_message(f"INFO: Updated {trait} to {value}")
        return True
    except Exception as e:
        queue_message(f"ERROR: Failed to update character setting: {e}")
        return False


CONFIG_METADATA = {
    'DEVICE': {
        '__description__': 'Device profile configuration',
        'raspberry_version': {
            'options': ['pi5', 'pi4', 'pi3', 'pizero2'],
            'description': 'Raspberry Pi model for capability detection'
        },
    },
    'CHAR': {
        '__description__': 'Character and user settings',
        'character_card_path': {
            'description': 'Path to character card file'
        },
        'user_name': {
            'description': 'Your name (how TARS addresses you)'
        },
        'user_details': {
            'description': 'Details about you for context'
        },
        'responses': {
            'description': 'Random idle responses (JSON array)'
        },
        'thinking_responses': {
            'description': 'Thinking filler responses (JSON array)'
        },
        'latitude': {
            'description': 'TARS latitude (e.g. 45.5017)'
        },
        'longitude': {
            'description': 'TARS longitude (e.g. -73.5673)'
        },
        'location_name': {
            'description': 'TARS location name (e.g. Montreal, Quebec, Canada)'
        },
    },
    'CONTROLS': {
        '__description__': 'Controller settings for physical input devices',
        'controller_name': {
            'description': 'Name of the connected controller'
        },
        'enabled': {
            'description': 'Enable controller input'
        },
        'voicemovement': {
            'description': 'Enable voice-controlled movement'
        },
        'swap_turn_directions': {
            'description': 'Swap left/right turn directions'
        },
    },
    'STT': {
        '__description__': 'Speech-to-Text configuration',
        'language': {
            'options': ['english', 'spanish', 'french', 'german', 'italian', 'portuguese', 'dutch', 'russian', 'chinese', 'japanese', 'korean'],
            'description': 'Speech recognition language'
        },
        'wake_word': {
            'description': 'Phrase to activate listening'
        },
        'wake_word_processor': {
            'options': ['picovoice', 'fastrtc', 'atomik'],
            'description': 'Wake word detection engine'
        },
        'sensitivity': {
            'description': 'Wake word sensitivity (1-10)'
        },
        'stt_processor': {
            'options': ['vosk', 'faster-whisper', 'silero', 'fastrtc', 'openai', 'external'],
            'description': 'Speech-to-text engine'
        },
        'external_url': {
            'description': 'URL for external STT server'
        },
        'whisper_model': {
            'options': ['tiny', 'base', 'small', 'medium', 'large'],
            'description': 'Whisper model size'
        },
        'vosk_model': {
            'description': 'Vosk model name'
        },
        'use_indicators': {
            'description': 'Play audio indicators for listening state'
        },
        'vad_method': {
            'options': ['silero', 'rms'],
            'description': 'Voice Activity Detection method'
        },
        'speechdelay': {
            'description': 'Silence duration before processing (tenths of seconds)'
        },
    },
    'LLM': {
        '__description__': 'Large Language Model configuration',
        'llm_backend': {
            'options': ['openai', 'grok', 'ooba', 'tabby', 'deepinfra'],
            'description': 'LLM backend service'
        },
        'base_url': {
            'description': 'API base URL'
        },
        'openai_model': {
            'description': 'OpenAI model name'
        },
        'grok_model': {
            'description': 'Grok model name'
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
            'type': 'screensaver_select',
            'options': ['random', 'blackhole', 'waves', 'matrix', 'starfield', 'hyperspace', 'terminal', 'face', 'fractal', 'pacman', 'nebulas', 'pictures', 'dashboard', 'defrag', 'bounce', 'endurance'],
            'description': 'Select "random" for all, or pick specific screensavers'
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
}