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
    can_use_opengl: bool
    can_use_cv2: bool
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
        can_use_opengl=True,
        can_use_cv2=True,
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
        can_use_opengl=True,
        can_use_cv2=False,
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
        can_use_ui=True,
        can_use_vision=False,
        can_use_emotion=False,
        can_use_opengl=False,
        can_use_cv2=False,
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
        can_use_ui=True,
        can_use_vision=False,
        can_use_emotion=False,
        can_use_opengl=False,
        can_use_cv2=False,
        max_context_size=2000,
        fallback_stt="openai",
        fallback_tts="openai",
        fallback_vad="rms",
        fallback_wake="picovoice",
    ),
}

CAPABILITIES: Optional[DeviceCapabilities] = None
_OVERRIDES_APPLIED = False


def detect_raspberry_pi_version() -> str:
    """Auto-detect the Raspberry Pi model from system hardware info."""
    for path in ('/proc/device-tree/model', '/proc/cpuinfo'):
        try:
            with open(path, 'r') as f:
                text = f.read().lower()
            if 'raspberry pi 5' in text:
                return 'pi5'
            if 'raspberry pi 4' in text:
                return 'pi4'
            if 'raspberry pi 3' in text:
                return 'pi3'
            if 'zero 2' in text:
                return 'pizero2'
            if 'zero' in text:
                return 'pizero2'
        except (FileNotFoundError, IOError):
            continue
    return 'pi5'  # safe default for non-Pi dev machines


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
        config_dict["LLM"]["contextsize"] = capabilities.max_context_size
    
    if not capabilities.can_use_ui and config_dict["UI"]["UI_enabled"]:
        if show_warnings:
            queue_message(f"WARNING: UI disabled for {capabilities.profile.value}")
        config_dict["UI"]["UI_enabled"] = False
    
    if not capabilities.can_use_vision and config_dict["VISION"]["enabled"]:
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

    raspberry_version = detect_raspberry_pi_version()

    device_profile = get_device_profile(raspberry_version)
    capabilities = DEVICE_PROFILES[device_profile]

    config_dict = {
        "BASE_DIR": base_dir,
        "CONTROLS": {
            "enabled": config.getboolean('CONTROLS', 'enabled'),
            "ventilate": config.getboolean('CONTROLS', 'ventilate', fallback=False),
            "voicemovement": config.getboolean('CONTROLS', 'voicemovement'),
            "swap_turn_directions": config.getboolean('CONTROLS', 'swap_turn_directions', fallback=False),
            "invert_y": config.getboolean('CONTROLS', 'invert_y', fallback=False),
            "controller_name": config['CONTROLS']['controller_name'],
        },
        "STT": {
            "use_indicators": config.getboolean('STT', 'use_indicators'),
            "stt_processor": config['STT']['stt_processor'],
            "wake_word_processor": config['STT']['wake_word_processor'],
            "wake_word": config['STT']['wake_word'],
            "vad_method": config['STT']['vad_method'],
            "sensitivity": config['STT']['sensitivity'],
            "external_url": config['STT']['external_url'],
            "whisper_model": config['STT']['whisper_model'],
            "vosk_model": config['STT']['vosk_model'],
            "speechdelay": int(config['STT']['speechdelay']),
            "picovoice_keyword_path": config['STT']['picovoice_keyword_path'],
            "language": config['STT']['language'],
            "picovoice_api_key": os.getenv('PICOVOICE_API_KEY')
        },
        "CHAR": {
            "character_name": character_name,
            "character_card_path": config['CHAR']['character_card_path'],
            "location_name": config.get('CHAR', 'location_name', fallback=''),
            "latitude": config.get('CHAR', 'latitude', fallback=''),
            "longitude": config.get('CHAR', 'longitude', fallback=''),
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
            "thinking_responses": config['CHAR']['thinking_responses'],
            "responses": config['CHAR']['responses'],
            "traits": persona_traits,
        },
        "LLM": {
            "llm_backend": config['LLM']['llm_backend'],
            "base_url": config['LLM']['base_url'],
            "openai_model": config['LLM']['openai_model'],
            "grok_model": config['LLM']['grok_model'],
            "systemprompt": config['LLM']['systemprompt'],
            "contextsize": int(config['LLM']['contextsize']),
            "max_tokens": int(config['LLM']['max_tokens']),
            "seed": int(config['LLM']['seed']),
            "temperature": float(config['LLM']['temperature']),
            "top_p": float(config['LLM']['top_p']),
            "override_encoding_model": config['LLM']['override_encoding_model'],
            "api_key": get_api_key(config['LLM']['llm_backend']),
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
        "RAG": {
            "enabled": config.getboolean('RAG', 'enabled', fallback=True),
            "enable_topic_tracking": config.getboolean('RAG', 'enable_topic_tracking'),
            "strategy": config.get('RAG', 'strategy', fallback='naive'),
            "context_window": config.getint('RAG', 'context_window', fallback=2),
            "max_memories": config.getint('RAG', 'max_memories', fallback=3),
            "vector_weight": config.getfloat('RAG', 'vector_weight', fallback=0.5),
            "top_k": config.getint('RAG', 'top_k', fallback=5),
            "recency_boost_days": config.getint('RAG', 'recency_boost_days', fallback=7),
        },
        "HOME_ASSISTANT": {
            "enabled": config.getboolean('HOME_ASSISTANT', 'enabled'),
            "url": config['HOME_ASSISTANT']['url'],
            "HA_TOKEN": os.getenv('HA_TOKEN'),
        },
        "DISCORD": {
            "TOKEN": os.getenv('DISCORD_TOKEN'),
            "channel_id": config['DISCORD']['channel_id'],
            "enabled": config.getboolean('DISCORD', 'enabled'),
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
            "enabled": config.getboolean('STABLE_DIFFUSION', 'enabled'),
            "service": config['STABLE_DIFFUSION']['service'],
            "url": config['STABLE_DIFFUSION']['url'],
            "comfyui_workflow": config.get('STABLE_DIFFUSION', 'comfyui_workflow', fallback='Documentation/Comfy_UI_SD.json'),
            "comfyui_img2img_workflow": config.get('STABLE_DIFFUSION', 'comfyui_img2img_workflow', fallback='Documentation/Comfy_UI_IMG2IMG.json'),
            "seed": int(config['STABLE_DIFFUSION']['seed']),
            "denoising_strength": float(config['STABLE_DIFFUSION']['denoising_strength']),
            "steps": int(config['STABLE_DIFFUSION']['steps']),
            "cfg_scale": float(config['STABLE_DIFFUSION']['cfg_scale']),
            "sampler_name": config['STABLE_DIFFUSION']['sampler_name'].strip('"'),
            "prompt_prefix": config['STABLE_DIFFUSION']['prompt_prefix'],
            "prompt_postfix": config['STABLE_DIFFUSION']['prompt_postfix'],
            "negative_prompt": config['STABLE_DIFFUSION']['negative_prompt'],
            "width": int(config['STABLE_DIFFUSION']['width']),
            "height": int(config['STABLE_DIFFUSION']['height']),
            "restore_faces": config.getboolean('STABLE_DIFFUSION', 'restore_faces'),
        },
        "UI": {
            "webui_enabled": config.getboolean('UI', 'webui_enabled', fallback=True),
            "webui_port": config.getint('UI', 'webui_port', fallback=80),
            "webui_password": config.get('UI', 'webui_password', fallback='tarspass1234'),
            "UI_enabled": config.getboolean('UI', 'UI_enabled'),
            "use_camera_module": config.getboolean('UI', 'use_camera_module'),
            "show_mouse": config.getboolean('UI', 'show_mouse'),
            "fullscreen": config.getboolean('UI', 'fullscreen'),
            "show_time": config.getboolean('UI', 'show_time', fallback=True),
            "show_cpu_temp": config.getboolean('UI', 'show_cpu_temp', fallback=False),
            "ampm_format": config.getboolean('UI', 'ampm_format', fallback=True),
            "app": config.get('UI', 'app', fallback='terminal'),
            "target_fps": int(config['UI']['target_fps']),
            "font_size": int(config['UI']['font_size']),
            "screensaver_timer": config.getint('UI', 'screensaver_timer', fallback=300),
            "screensaver_cycle_interval": config.getint('UI', 'screensaver_cycle_interval', fallback=300),
            "screensaver_list": _parse_screensaver_list(config.get('UI', 'screensaver_list', fallback='random')),
        },
        "MISC": {
            "battery_enabled": config.getboolean('MISC', 'battery_enabled', fallback=False),
            "battery_auto_shutdown": config.getboolean('MISC', 'battery_auto_shutdown', fallback=False),
            "battery_capacity_mAh": int(config.get('MISC', 'battery_capacity_mAh', fallback='3000')),
            "battery_initial_voltage": float(config.get('MISC', 'battery_initial_voltage', fallback='12')),
            "battery_cutoff_voltage": float(config.get('MISC', 'battery_cutoff_voltage', fallback='10')),
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
    'CHAR': {
        '__description__': 'Set up who TARS is, who you are, and what TARS says when you talk to it',
        'character_card_path': {
            'description': 'This points to a file that tells TARS who it is - its name, personality, backstory, and how it should act. Think of it like a character sheet for a role-playing game. The default is the TARS character from the movie Interstellar. If you want to make your own character, create a new folder inside "character/" and put a .json file in it following the same format as the TARS one.'
        },
        'location_name': {
            'description': 'The name of your city/area in plain text. TARS shows this to the AI alongside the coordinates so it has a human-readable name for where you are. Format it like: "City, State/Province, Country". For example: "Los Angeles, California, USA"'
        },
        'latitude': {
            'description': 'Your latitude coordinate (the north/south part of your GPS location). TARS uses this to know where you are in the world so it can answer questions about your local weather, time zone, nearby places, etc. You can find your coordinates by searching "my coordinates" on Google. For example, New York City is about 40.7128. Just put the number here, no letters or symbols.'
        },
        'longitude': {
            'description': 'Your longitude coordinate (the east/west part of your GPS location). This works together with latitude to pinpoint your location. For example, New York City is about -74.0060. West of the Prime Meridian is negative. Search "my coordinates" on Google to find yours.'
        },
        'user_name': {
            'description': 'Type your name here. This is how TARS will call you when it talks to you. For example, if you put "Sarah", TARS might say "Hey Sarah, what do you need?"'
        },
        'user_details': {
            'description': 'Tell TARS a little about yourself so it can personalize its responses. This info gets fed to the AI so it knows who it is talking to. For example: "Species: Human. Gender: Female. Likes: gardening and cooking." You can put whatever you want here, or leave it blank.'
        },
        'thinking_responses': {
            'description': 'After TARS hears your question, it takes a moment to think of an answer (the AI needs time to generate a response). During that pause, TARS will say one of these filler phrases so you know it is working and did not freeze. Things like "Let me think..." or "One moment..." You can customize these the same way as the responses above. Set to [] (empty brackets) if you want silence while it thinks.'
        },
        'responses': {
            'description': 'When you say the wake word (like "Hey TARS"), TARS will immediately say one of these short phrases to let you know it heard you. This happens BEFORE it actually processes what you say next. Think of it like saying "Yeah?" when someone calls your name. You can change these to whatever you want, add new ones, or remove ones you do not like. The format is a list in square brackets with each phrase in quotes separated by commas. Set to [] (empty brackets) if you do not want any response.'
        },
    },
    'LLM': {
        '__description__': 'Configure the AI brain that generates TARS responses',
        'llm_backend': {
            'options': ['openai', 'grok', 'ooba', 'tabby', 'deepinfra', 'other'],
            'description': 'Choose which AI service TARS talks to for generating its responses. "openai" uses OpenAI (ChatGPT) and auto-fills the URL. "grok" uses xAI and auto-fills the URL. "deepinfra" uses DeepInfra and auto-fills the URL. "ooba" and "tabby" are for self-hosted models - set your own URL. "other" is for any OpenAI-compatible API (Featherless, Ollama, LM Studio, etc.) - set your own URL and it will never be overwritten. If you are not sure, start with "openai".'
        },
        'base_url': {
            'depends_on': [{'field': 'llm_backend', 'values': ['ooba', 'tabby', 'other']}],
            'description': 'The API endpoint for your AI service. For "ooba", "tabby", and "other" backends, set your server address here (e.g. http://192.168.1.100:11434/v1 for Ollama, or https://api.featherless.ai/v1 for Featherless). For "openai", "grok", and "deepinfra" this is handled automatically.'
        },
        'openai_model': {
            'label': 'model',
            'depends_on': [{'field': 'llm_backend', 'values': ['openai', 'ooba', 'tabby', 'deepinfra', 'other']}],
            'description': 'The specific AI model to use when your backend is set to "openai". Different models have different capabilities and costs. "gpt-4o-mini" is cheap and fast (good starting point). "gpt-4o" is smarter but costs more per message. If you are using Ollama on your own computer, put the model name you downloaded there, like "llama3.1:8b" or "qwen2.5:3b". This setting is ignored if you picked a different backend above.'
        },
        'grok_model': {
            'depends_on': [{'field': 'llm_backend', 'values': ['grok']}],
            'description': 'The specific Grok model to use when your backend is set to "grok". "grok-4-1-fast-non-reasoning" is fast and good for casual conversation. Only matters if you picked "grok" as your backend above.'
        },
        'systemprompt': {
            'description': 'Hidden instructions that TARS reads before every conversation. This tells the AI HOW to behave in general - like being helpful, conversational, staying in character, etc. This is different from the character card: the character card defines WHO TARS is, while this prompt defines the general RULES for how it should respond. Most people can leave the default as-is.'
        },
        'contextsize': {
            'description': 'How much conversation history TARS remembers in a single chat session. Measured in "tokens" (roughly: 1 token = about 1 word). A higher number means TARS can remember more of what you talked about, but it costs more money per message (if using a paid service) and can be slower. 4000 is a good default. If TARS seems to forget what you just said, try increasing this. If responses are slow or expensive, try lowering it. Most AI models have a maximum they support (check your model\'s docs).'
        },
        'max_tokens': {
            'description': 'The maximum length of TARS responses, measured in tokens (roughly 1 token = 1 word). If set to 200, TARS can say about 200 words max per response. Set this lower (200-300) for quick conversational replies, or higher (500-1000) if you want TARS to give long, detailed explanations. Setting it very high does not mean every response will be long - it just allows longer responses when needed.'
        },
        'seed': {
            'description': 'Leave this at -1 for normal use. If you set it to a specific number (like 42), TARS will try to give the exact same answer every time you ask the same question. This is only useful for testing or debugging. -1 means every response is unique.'
        },
        'temperature': {
            'description': 'Controls how creative vs predictable TARS is. Think of it like a "creativity dial". At 0.1, TARS gives very safe, predictable, repetitive answers (good for factual questions). At 0.7-0.8, TARS is natural and conversational (recommended for most people). At 1.5+, TARS gets very creative and random, which can be fun but also nonsensical. Most people should leave this between 0.5 and 0.9.'
        },
        'top_p': {
            'description': 'Another way to control how creative TARS is (works alongside temperature). At 0.9 (the default), TARS considers many possible words when forming a sentence, giving natural-sounding responses. At 0.5, it only picks from the most obvious words, making responses more focused but potentially robotic. Most people should leave this at 0.9 and just adjust temperature instead.'
        },
        'override_encoding_model': {
            'options': ['cl100k_base', 'p50k_base', 'r50k_base', 'gpt2'],
            'description': 'DO NOT CHANGE THIS unless TARS is crashing with token counting errors. This controls how TARS counts the size of messages before sending them to the AI. "cl100k_base" works for almost all modern AI models. Only change this if you see errors in the logs about token encoding failing.'
        },
    },
    'STT': {
        '__description__': 'Configure how TARS listens to you - wake word, speech recognition, and when to stop listening',
        'use_indicators': {
            'description': 'When this is on, TARS will play a short beep sound when it starts listening to you (after the wake word) and another beep when it stops listening. This is really helpful so you know when to start and stop talking. Turn this off if the beeps annoy you.'
        },
        'stt_processor': {
            'options': ['vosk', 'faster-whisper', 'silero', 'fastrtc', 'openai', 'external'],
            'description': 'After TARS hears the wake word, this is the software that converts your actual speech into text. Think of it as the "ears" of TARS. "fastrtc" sends your audio to the cloud for fast, accurate transcription (recommended if you have internet). "vosk" runs entirely on your Pi with no internet needed, but is less accurate. "faster-whisper" also runs on your Pi and is more accurate than vosk but needs a Pi 5. "openai" uses OpenAI\'s Whisper service (best for non-English languages, needs API key and internet). "external" lets you point to your own speech-to-text server running elsewhere.'
        },
        'wake_word_processor': {
            'options': ['picovoice', 'fastrtc', 'atomik'],
            'description': 'The software that listens for your wake word. "atomik" is built right into TARS, completely free, and works offline - this is the recommended choice for most people. You can adjust how sensitive it is with the "sensitivity" setting below. "fastrtc" uses an internet-based service for detection. "picovoice" is a professional wake word service that is very accurate but requires you to sign up for a free API key at picovoice.ai and put it in your .env file.'
        },
        'wake_word': {
            'description': 'The magic phrase you say to get TARS attention, like saying "Hey Siri" or "OK Google". TARS is always listening in the background for this specific phrase. When it hears it, it "wakes up" and starts recording whatever you say next. You can change this to anything you want, but shorter phrases (2-3 syllables) work best. For example: "hey tars", "ok robot", "computer". Avoid very common words that might trigger accidentally.'
        },
        'vad_method': {
            'options': ['silero', 'rms'],
            'description': 'VAD stands for "Voice Activity Detection" - this is how TARS figures out when you have STOPPED talking so it can process your message. "rms" simply listens for silence (when the volume drops below a threshold). It is lightweight and works on any Pi. "silero" uses a small AI model to detect speech vs silence, which is more accurate (it won\'t be fooled by background noise as easily) but uses more processing power - only recommended for Pi 5.'
        },
        'sensitivity': {
            'depends_on': [{'field': 'wake_word_processor', 'values': ['atomik']}],
            'description': 'How carefully TARS listens for the wake word (only works with the "atomik" wake word processor). Scale of 1 to 10. At 1, TARS triggers very easily - even similar-sounding words might activate it (annoying but you will never miss a command). At 10, you need to say the wake word very clearly and precisely for it to work (fewer accidental activations but you might have to repeat yourself). Start at 5 and adjust from there. If TARS keeps activating randomly, increase this number. If TARS never hears you, decrease it.'
        },
        'external_url': {
            'depends_on': [{'field': 'stt_processor', 'values': ['external']}],
            'description': 'If you set stt_processor to "external", put the web address of your speech-to-text server here. This is for advanced users who run their own Whisper or other STT server on a separate machine. If you are not using "external" mode, this setting is ignored. Format: http://IP-ADDRESS:PORT'
        },
        'whisper_model': {
            'depends_on': [{'field': 'stt_processor', 'values': ['faster-whisper', 'whisper']}],
            'options': ['tiny', 'base', 'small', 'medium', 'large'],
            'description': 'If you are using "faster-whisper" as your stt_processor, this controls the size of the AI model used to understand your speech. Bigger models understand you better but use more of your Pi\'s memory and are slower. "tiny" is the fastest and uses least memory (~1GB) - good enough for clear speech in a quiet room. "base" is a good middle ground. "small" is noticeably more accurate but uses ~2GB of RAM. "medium" and "large" are too heavy for a Raspberry Pi and will likely crash. If you are not using faster-whisper, this setting is ignored.'
        },
        'vosk_model': {
            'depends_on': [{'field': 'stt_processor', 'values': ['vosk']}],
            'description': 'If you are using "vosk" as your stt_processor, this is the name of the language model it uses. The default "vosk-model-small-en-us-0.15" is small and fast. You can download other models from alphacephei.com/vosk/models for different languages or better accuracy. "vosk-model-en-us-0.22" is a larger, more accurate English model. If you are not using vosk, this setting is ignored.'
        },
        'speechdelay': {
            'description': 'After you stop talking, TARS waits this long before it decides you are done and starts processing your message. The number is in tenths of a second, so 20 = 2 seconds. If this is too short (like 5 = half a second), TARS will cut you off mid-sentence every time you pause to think. If it is too long (like 40 = 4 seconds), there will be an awkward silence after every sentence before TARS responds. 15-25 (1.5 to 2.5 seconds) works well for most people.'
        },
        'picovoice_keyword_path': {
            'depends_on': [{'field': 'wake_word_processor', 'values': ['picovoice']}],
            'description': 'Only matters if you are using "picovoice" as your wake_word_processor. This is the path to a special file (.ppn) that Picovoice uses to recognize your wake word. You can create custom wake word files for free at console.picovoice.ai. If you are not using picovoice, ignore this setting.'
        },
        'language': {
            'options': ['english', 'spanish', 'french', 'german', 'italian', 'portuguese', 'dutch', 'russian', 'chinese', 'japanese', 'korean'],
            'description': 'What language are you speaking to TARS? Set this to your spoken language. IMPORTANT: If you pick anything other than English, you should also change the "stt_processor" setting below to "openai", because most of the local (on-device) speech recognition options only work well in English.'
        },
    },
    'TTS': {
        '__description__': 'Configure how TARS speaks - choose a voice engine and customize how it sounds',
        'toggle_charvoice': {
            'description': 'When this is ON, TARS will use voice settings stored in the character card file instead of the settings on this page. This is useful if you have multiple characters (like TARS, a pirate, a wizard, etc.) and each one should have a different voice. When OFF, the voice settings on this page are always used regardless of which character is loaded.'
        },
        'ttsoption': {
            'options': ['espeak', 'piper', 'silero', 'alltalk', 'elevenlabs', 'minimax', 'openai', 'azure'],
            'description': 'Choose how TARS speaks out loud. This is the most important voice setting. FREE options that work without internet: "piper" sounds natural and is the best free option (recommended for Pi 5 and Pi 4). "espeak" is a basic robotic-sounding voice but works on any Pi, even very weak ones. "silero" is another good-sounding option but only works on Pi 5. If you have a separate PC, "alltalk" lets you run a high-quality voice server on it. PAID cloud options (need internet + API key in .env file): "elevenlabs" has the most natural, human-like voices. "openai" is good quality and works well in many languages. "minimax" and "azure" are other cloud options with different voice styles.'
        },
        'ttsurl': {
            'depends_on': [{'field': 'ttsoption', 'values': ['alltalk']}],
            'description': 'If you picked "alltalk" above, put the web address of your AllTalk server here. AllTalk is a voice synthesis program you run on a separate, more powerful computer (like a gaming PC). Format: http://IP-ADDRESS:PORT (for example: http://192.168.1.100:7852). If you are not using alltalk, this setting is ignored.'
        },
        'tts_voice': {
            'depends_on': [{'field': 'ttsoption', 'values': ['alltalk', 'azure']}],
            'description': 'The specific voice to use, but this only applies to "alltalk" or "azure" TTS options. For AllTalk: enter the name of a cloned voice you set up in AllTalk (like "TARS2"). For Azure: enter the full voice ID from Microsoft (like "en-US-Steffan:DragonHDLatestNeural"). If you are using piper, espeak, elevenlabs, or other engines, they have their own voice settings below.'
        },
        'azure_region': {
            'depends_on': [{'field': 'ttsoption', 'values': ['azure']}],
            'options': ['eastus', 'eastus2', 'westus', 'westus2', 'centralus', 'northeurope', 'westeurope'],
            'description': 'Only matters if you are using "azure" as your TTS engine. This must match the region you selected when you created your Azure Speech Services account. If you are in the US, "eastus" is a common choice. Pick the region closest to you for the fastest response. If you are not using Azure, ignore this.'
        },
        'elevenlabs_voice_id': {
            'depends_on': [{'field': 'ttsoption', 'values': ['elevenlabs']}],
            'description': 'Only matters if you are using "elevenlabs" as your TTS engine. This is the unique ID of the voice you want to use. Log in to elevenlabs.io, go to the Voices section, click on a voice, and copy its Voice ID. The default ID is for a voice called "George". You can also clone your own voice on ElevenLabs and use that ID here.'
        },
        'elevenlabs_model': {
            'depends_on': [{'field': 'ttsoption', 'values': ['elevenlabs']}],
            'options': ['eleven_multilingual_v2', 'eleven_monolingual_v1', 'eleven_turbo_v2'],
            'description': 'Only matters if you are using "elevenlabs" as your TTS engine. "eleven_multilingual_v2" can speak in 29 different languages and is the recommended choice. "eleven_monolingual_v1" only speaks English but is slightly faster. "eleven_turbo_v2" is the fastest but sounds slightly lower quality.'
        },
        'minimax_voice_id': {
            'depends_on': [{'field': 'ttsoption', 'values': ['minimax']}],
            'description': 'Only matters if you are using "minimax" as your TTS engine. This is the name of the Minimax voice to use. You can browse available voices on the Minimax website. "English_CaptivatingStoryteller" is a good default for an engaging male voice.'
        },
        'minimax_model': {
            'depends_on': [{'field': 'ttsoption', 'values': ['minimax']}],
            'options': ['speech-2.6-turbo', 'speech-2.8-turbo', 'speech-2.6-hd', 'speech-2.8-hd'],
            'description': 'Only matters if you are using "minimax" as your TTS engine. The "turbo" versions are faster (less delay before TARS speaks). The "hd" versions sound better quality but take slightly longer. Higher numbers (2.8) are newer and generally better than lower numbers (2.6).'
        },
        'openai_voice': {
            'depends_on': [{'field': 'ttsoption', 'values': ['openai']}],
            'options': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            'description': 'Only matters if you are using "openai" as your TTS engine. Each voice has a different personality: "alloy" is neutral and balanced. "echo" is warm and conversational. "fable" has a British accent and is expressive. "onyx" is deep and authoritative (the best match for TARS from the movie). "nova" is friendly and upbeat. "shimmer" is clear and gentle. Try a few and see which one you like!'
        },
    },
    'EMOTION': {
        '__description__': 'Controls whether TARS shows emotions on its face/display based on what it says',
        'enabled': {
            'description': 'When ON, TARS analyzes its own responses to figure out the emotion behind them (happy, sad, angry, surprised, etc.) and then shows matching facial expressions on its screen. This makes TARS feel more alive and expressive. Turn this OFF if you are not using the TARS display screen, or if you want to save processing power on weaker Pi models. The emotion detection runs a small AI model that uses some RAM and CPU.'
        },
        'emotion_model': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'The name of the AI model used to detect emotions in text. The default model can recognize 28 different emotions like joy, sadness, anger, surprise, fear, and more. It gets downloaded automatically the first time you enable emotion detection (about 500MB download). You should not need to change this unless you want to experiment with a different emotion model from HuggingFace.'
        },
    },
    'VISION': {
        '__description__': 'Let TARS see the world through a camera and describe what it sees',
        'enabled': {
            'description': 'When ON, TARS can use a camera to see and describe what is in front of it. You can ask "what do you see?" and TARS will take a picture and tell you. This loads an image recognition AI model into memory which uses about 1GB+ of RAM, so turn this OFF if you do not have a camera connected or if your Pi is running low on memory.'
        },
        'server_hosted': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When OFF (default), the camera image processing happens directly on your Raspberry Pi. When ON, the image is sent to a separate, more powerful computer to be processed. Turn this ON if your Pi is too weak to handle vision (Pi 3 or Pi 4), and then set up the vision server on another computer. If you have a Pi 5, you can leave this OFF to process everything locally.'
        },
        'base_url': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'server_hosted', 'values': ['True', 'true']}],
            'description': 'Only matters if "server_hosted" is ON. Enter the web address of the computer running the vision server. Format: http://IP-ADDRESS:PORT (for example: http://192.168.1.100:5678). The vision server script is included in the TARS project and you run it on a more powerful computer that handles the image processing.'
        },
    },
    'RAG': {
        '__description__': 'TARS long-term memory - lets TARS remember past conversations and bring up relevant info',
        'enabled': {
            'description': 'Master switch for TARS long-term memory. When ON, TARS saves conversations and recalls relevant past interactions to give more personal, context-aware responses over time. Turn OFF if you want TARS to have no memory of past conversations, or if you are running low on storage/resources.'
        },
        'strategy': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['naive', 'hybrid'],
            'description': 'How TARS searches through its memories. "hybrid" (recommended) uses two different search methods together - it looks for memories that are similar in meaning AND memories that contain matching keywords. This gives the best results. "naive" only uses meaning-based search, which is faster but might miss some relevant memories. Unless you are having performance issues, stick with "hybrid".'
        },
        'enable_topic_tracking': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When ON, TARS creates summaries of conversation topics over time. This is like TARS writing notes in a journal about what you have been talking about. These topic summaries help TARS remember broad themes from weeks or months ago, even when the individual conversation details have faded. This gives TARS a much better long-term memory. Recommended to leave ON.'
        },
        'context_window': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When TARS finds a relevant memory, it also grabs nearby memories for additional context. For example, if set to 2, and TARS finds a relevant memory from last Tuesday, it will also grab the 2 conversation entries before AND 2 entries after that memory. This helps TARS understand the full context of past conversations, not just isolated snippets.'
        },
        'max_memories': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'Out of all the memories TARS finds (controlled by top_k above), only this many "best" results get the full context expansion (the context_window setting). So if top_k is 5 and max_memories is 3, TARS finds 5 relevant memories but only the 3 most relevant ones get surrounding context included. This keeps things from getting too large. 2-5 works well.'
        },
        'top_k': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When TARS is looking for relevant memories, this is how many memory chunks it pulls up. Think of it like asking TARS to look through its diary and pull out the 5 most relevant pages. Higher numbers mean more memories are considered (TARS has more context) but it also means longer processing time and more data sent to the AI. 3-7 is the sweet spot for most people.'
        },
        'recency_boost_days': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'Makes TARS prioritize recent conversations in its memory. If set to 7, any conversation from the last 7 days gets a boost in search results, making TARS more likely to reference things you talked about recently. This feels natural because in real life, recent conversations are usually more relevant. Set to 0 if you want all memories treated equally regardless of when they happened.'
        },
    },
    'UI': {
        '__description__': 'Settings for the on-device display and the web browser interface',
        'webui_enabled': {
            'description': 'Master switch for the web-based chat interface. When ON, you can open a web browser on any device connected to the same WiFi/network and go to your Pi\'s IP address to chat with TARS, change settings, and more. This is the page you are probably looking at right now! Turn OFF if you only want to interact with TARS by voice.'
        },
        'webui_port': {
            'depends_on': [{'field': 'webui_enabled', 'values': ['True', 'true']}],
            'description': 'The network port number for the web interface. Port 80 is the standard for websites, which means you can just type your Pi\'s IP address in the browser (like http://192.168.1.50) without adding a port number. If something else on your Pi is already using port 80, change this to something like 8080, and then you would access it at http://192.168.1.50:8080.'
        },
        'webui_password': {
            'depends_on': [{'field': 'webui_enabled', 'values': ['True', 'true']}],
            'description': 'The password needed to log into this web interface. Anyone on your local network could potentially access it, so change this from the default to something only you know. This is NOT stored securely - it is a simple access barrier, not bank-level security.'
        },
        'UI_Port': {
            'description': 'The network port used by the on-device display server. Most people should not change this.'
        },
        'UI_enabled': {
            'description': 'Master switch for the physical screen attached to your TARS robot. Turn this OFF if your TARS does not have a screen, or if you want to save resources by running "headless" (no display). When OFF, TARS still works - you just interact through the web interface or voice only.'
        },
        'use_camera_module': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Turn this ON if you have a Raspberry Pi camera module plugged into the flat ribbon cable connector on your Pi (called the CSI port). This lets the display show camera feeds and enables vision features. Leave OFF if you do not have a camera connected, otherwise TARS might show errors trying to access a camera that is not there.'
        },
        'show_mouse': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Shows a mouse cursor arrow on the TARS display. This is useful when you are setting things up or debugging, because you can see where you are clicking. For normal everyday use, you probably want this OFF for a cleaner look on the display.'
        },
        'fullscreen': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'When ON, the TARS display takes up the entire screen with no window borders or title bar - this is what you want for a finished robot. When OFF, it runs in a regular window that you can move and resize, which is useful during development or if you are also using the Pi desktop for other things.'
        },
        'show_time': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'When ON, shows the current time on top of the screensaver animations. Nice if you want TARS to double as a clock when idle.'
        },
        'show_cpu_temp': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Shows the Raspberry Pi CPU temperature on the display. Useful if your TARS is in an enclosed case and you want to keep an eye on overheating. The Pi can throttle (slow down) if it gets too hot. Normal is around 40-60 C, and above 80 C means you might need better cooling.'
        },
        'ampm_format': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Controls how the clock is displayed. ON = 12-hour format with AM/PM (like 2:30 PM). OFF = 24-hour military time (like 14:30). Pick whichever you are used to reading.'
        },
        'app': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'options': ['terminal', 'dashboard', 'clock'],
            'description': 'What shows on the TARS display when it first starts up. "terminal" shows a chat-style interface where you can see the conversation. "dashboard" shows a system status overview with various stats. "clock" shows a big clock display. You can always switch between these later.'
        },
        'target_fps': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'How many times per second the display updates (frames per second). Higher = smoother animations but uses more CPU power. 30 is a good balance between smooth visuals and low CPU usage. If animations look choppy, try increasing it. If your Pi is running hot or slow, try lowering it to 15-20.'
        },
        'font_size': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'How big the text is on the TARS display. If you have a small screen (like a 3.5 inch screen), use a small number (9-12) so text fits. For a medium screen (5 to 7 inches), try 12-16. For a large screen (10 inches or bigger), use 16-20. If text looks too small or too big, just adjust this number.'
        },
        'screensaver_timer': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'After this many seconds of nobody talking to TARS, a screensaver animation will start playing on the display. Set to 0 to never show a screensaver. 300 = 5 minutes of inactivity before the screensaver kicks in. The screensaver stops automatically when you talk to TARS again.'
        },
        'screensaver_cycle_interval': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'If you have multiple screensavers selected below, this is how many seconds each one plays before switching to the next one. 300 = each screensaver plays for 5 minutes before changing. Only matters if you have more than one screensaver selected.'
        },
        'screensaver_list': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'type': 'screensaver_select',
            'options': ['random', 'blackhole', 'waves', 'matrix', 'starfield', 'hyperspace', 'terminal', 'face', 'fractal', 'pacman', 'nebulas', 'pictures', 'dashboard', 'defrag', 'bounce', 'endurance'],
            'description': 'Pick which screensaver animations play on the TARS display when idle. Select "random" to cycle through all of them, or pick specific ones you like. Each one is a different cool animation - try them out and see which ones you enjoy!'
        },
    },
    'CONTROLS': {
        '__description__': 'Connect a Bluetooth or USB game controller to physically steer TARS around',
        'enabled': {
            'description': 'Master switch for game controller support. Turn ON if you have a Bluetooth or USB controller paired to your Pi and want to use it to control TARS movement and actions. Leave OFF if you do not have a controller or do not want to use one.'
        },
        'ventilate': {
            'description': 'When ON, TARS will periodically shift its body into a position that lets more air flow through the case. This helps keep the electronics cool, especially if your TARS is in a sealed or enclosed case where heat can build up. If your Pi is running hot (check with show_cpu_temp in the UI section), try turning this ON.'
        },
        'voicemovement': {
            'description': 'When ON, you can tell TARS to move by voice, like saying "walk forward", "turn left", or "stop". This works even without a controller connected. When OFF, TARS can only be moved with a physical game controller.'
        },
        'swap_turn_directions': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'If TARS turns left when you press right on the controller (or vice versa), turn this ON to fix it. This can happen depending on how your servos are oriented.'
        },
        'invert_y': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'If pressing up on the controller D-pad makes TARS go backward (or vice versa), turn this ON to fix it. Some controllers report the Y axis in the opposite direction.'
        },
        'controller_name': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'The name of your Bluetooth or USB game controller. TARS looks for this text in the names of all connected controllers. For example, if you have an "8BitDo Pro 2" controller, just putting "8BitDo" here is enough. For Xbox controllers, put "Xbox". For PlayStation, put "PS4" or "DualSense". It just needs to match part of the controller name.'
        },
    },
    'HOME_ASSISTANT': {
        '__description__': 'Let TARS control your smart home lights, switches, and devices through voice',
        'enabled': {
            'description': 'Turn ON to connect TARS to your Home Assistant smart home system. Once connected, you can say things like "turn off the living room lights" or "what temperature is the bedroom?" and TARS will control your smart home devices. You need a Home Assistant server already running on your network, and you need to create a Long-Lived Access Token in Home Assistant (go to your HA profile page > scroll to bottom > create token) and paste it into your .env file as HOME_ASSISTANT_TOKEN.'
        },
        'url': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'The web address of your Home Assistant server. This is usually your HA server\'s IP address followed by port 8123. For example: http://192.168.1.50:8123. You can find this in your Home Assistant settings, or just try typing your HA server\'s IP with :8123 at the end. IMPORTANT: The access token goes in the .env file, NOT here.'
        },
    },
    'DISCORD': {
        '__description__': 'Let TARS chat in a Discord server as a bot',
        'enabled': {
            'description': 'Turn ON to have TARS run as a Discord bot. TARS will join a specific Discord channel and respond to messages there. To set this up: 1) Go to discord.com/developers, create a new Application, go to Bot tab, create a bot, and copy the token. 2) Put that token in your .env file as DISCORD_TOKEN. 3) Invite the bot to your Discord server using the OAuth2 URL generator. 4) Set the channel_id below to the channel you want TARS to chat in.'
        },
        'channel_id': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'The ID number of the Discord channel where TARS should listen and respond. To get this: Open Discord, go to Settings > Advanced > turn on "Developer Mode". Then right-click the channel you want TARS in and click "Copy Channel ID". Paste that number here. It will be a long number like 811470553139249186.'
        },
    },
    'STABLE_DIFFUSION': {
        '__description__': 'Let TARS create images from text descriptions (requires a separate computer running an image generator)',
        'enabled': {
            'description': 'Turn ON to let TARS generate images during conversation. When someone asks TARS to draw or create an image, it will send the request to an image generation server (running on a separate computer - your Pi is not powerful enough for this). You need to have AUTOMATIC1111, ComfyUI, or an OpenAI account set up first. If you do not have any of these, leave this OFF.'
        },
        'service': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['automatic1111', 'comfyui', 'openai'],
            'description': 'Which image generation program you are running on your other computer. "automatic1111" is the most popular free option - it is a web interface for Stable Diffusion. "comfyui" is a more advanced, node-based alternative (harder to set up but more flexible). "openai" uses OpenAI\'s DALL-E to generate images in the cloud (no separate computer needed, but costs money per image and requires an OpenAI API key).'
        },
        'url': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111', 'comfyui']}],
            'description': 'The web address of your image generation server on your network. Format: http://IP-ADDRESS:PORT. For AUTOMATIC1111, the default port is usually 7860 (like http://192.168.1.100:7860). For ComfyUI, the default port is usually 8188. This is ignored if you are using the "openai" service.'
        },
        'comfyui_workflow': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['comfyui']}],
            'description': 'Only used if your service is set to "comfyui". This is the path to a workflow file (a JSON file that tells ComfyUI exactly how to generate an image). The default workflow is included in the Documentation folder. Advanced users can create custom workflows in ComfyUI and point to them here.'
        },
        'comfyui_img2img_workflow': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['comfyui']}],
            'description': 'Same as above but for image-to-image generation (where TARS modifies an existing image instead of creating one from scratch). Only used with ComfyUI.'
        },
        'seed': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'Controls randomness in generated images. Leave at -1 for normal use - each image will be unique and different. If you set this to a specific number (like 12345), the EXACT same image will be generated every time you use the same prompt. This is useful for testing or if you found an image you like and want to reproduce it.'
        },
        'denoising_strength': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111', 'comfyui']}],
            'description': 'A number between 0.0 and 1.0 that controls how much creative freedom the image generator has. At lower values (0.3-0.5), images have more creative variation but may have some imperfections. At higher values (0.5-0.7), images are cleaner but more generic. When using image-to-image mode (modifying an existing image), lower values keep the original image more intact, while higher values change it more dramatically. 0.5 is a good starting point.'
        },
        'steps': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111', 'comfyui']}],
            'description': 'How many passes the AI makes over the image while creating it. More steps = better quality but takes longer to generate. 20 is a good starting point that balances speed and quality. Going above 30-40 usually does not improve the image much but makes it take noticeably longer. Going below 15 can make images look blurry or unfinished.'
        },
        'cfg_scale': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111', 'comfyui']}],
            'description': 'How closely the generated image follows your text description. Think of it as a "creativity vs accuracy" slider. At low values (1-5), the AI takes a lot of creative freedom and the image might not match your description well but could look artistic. At medium values (7-9), there is a good balance (recommended). At high values (10-20), the AI tries very hard to match your exact words, but the image can start looking artificial or over-processed.'
        },
        'sampler_name': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111', 'comfyui']}],
            'description': 'The algorithm used to create the image. Different samplers produce slightly different artistic results. "Euler a" is fast and produces good results (recommended default). You generally do not need to change this unless you are experienced with Stable Diffusion and want to experiment with different visual styles.'
        },
        'width': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111']}],
            'description': 'Width of the generated image in pixels. Bigger images have more detail but take longer to generate. For the standard TARS display, 480 pixels wide works well. For Stable Diffusion 1.5, the native resolution is 512x512. For SDXL, it is 1024x1024. Try to match your model\'s native resolution for best results.'
        },
        'height': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111']}],
            'description': 'Height of the generated image in pixels. Works the same as width. For the TARS display, 320 pixels tall matches the screen well. Together with width, this determines the aspect ratio (shape) of the image - 480x320 gives a wide/landscape image, 320x480 gives a tall/portrait image.'
        },
        'restore_faces': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'service', 'values': ['automatic1111']}],
            'description': 'When ON, the image generator runs an extra step to fix faces in the generated image. AI image generators often struggle with faces - they might look distorted, have extra eyes, or weird features. This post-processing step detects faces and cleans them up. Turn ON if you are generating images of people or characters.'
        },
        'prompt_prefix': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'Text that gets automatically added to the BEGINNING of every image prompt. Use this to set a consistent art style for all generated images. For example, "in the style of midjourney" makes images look polished and artistic. You could also use "photorealistic" or "oil painting style" or "anime style". Leave empty if you do not want a default style.'
        },
        'prompt_postfix': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'Text that gets automatically added to the END of every image prompt. Use this to ensure consistent quality. The default adds terms like "high def" and "highly detailed" which help produce better-looking images. You can customize this to match your preferences.'
        },
        'negative_prompt': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'A list of things you do NOT want in the generated images. The AI will try to avoid these. The default list helps prevent common ugly artifacts like deformed body parts, extra limbs, and bad anatomy. You can add your own terms if you notice recurring problems. For example, add "blurry" if images keep coming out unfocused, or "watermark" to avoid watermark-like artifacts.'
        },
    },
    'MISC': {
        '__description__': 'Other settings that do not fit in the categories above',
        'battery_enabled': {
            'description': 'Master switch for battery monitoring. Turn ON if your TARS has an INA260 power sensor connected. When enabled, TARS tracks battery voltage and percentage, displays it on the dashboard, and can optionally shut down safely when the battery runs low. Leave OFF if you are running from a wall adapter or do not have the INA260 sensor.'
        },
        'battery_auto_shutdown': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'VERY IMPORTANT for battery-powered builds. When ON, TARS will automatically and safely shut down the Raspberry Pi when the battery gets critically low (near 0%). This protects your Pi from suddenly losing power mid-operation (which can corrupt the SD card) and protects your battery from being over-drained (which can permanently kill it). STRONGLY recommended to leave this ON if you are running on battery.'
        },
        'battery_capacity_mAh': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'How much charge your battery can hold, measured in milliampere-hours (mAh). This number is printed on your battery. Common examples: a small battery might be 3000 mAh (3Ah), a medium one 5600 mAh (5.6Ah). TARS uses this to calculate the remaining battery percentage. If the percentage seems wrong, double-check this number against your battery label.'
        },
        'battery_initial_voltage': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'The voltage of your battery when it is fully charged. This depends on your battery type. Most common for TARS builds is a 3S LiPo at 12.6V when full, or 12V for simplicity. If you are using a USB power bank, it would be 5V. Check your battery label or charger to find the full-charge voltage. TARS uses this as the "100%" reference point.'
        },
        'battery_cutoff_voltage': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'The lowest voltage your battery should EVER reach. Draining a battery below this point can permanently damage it or even make it dangerous. For a 3S LiPo battery, this is about 10.5V. For a 4S LiPo, about 14V. TARS uses this as the "0%" reference point. If battery_auto_shutdown is ON, TARS will turn off the Pi before reaching this voltage to protect your battery.'
        },
    }
}


def update_config_from_web_ui(data: dict, create_backup: bool = True) -> dict:
    """
    Update configuration using TARS CMS (Programmatic Access)
    """
    try:
        cms = TarsConfigManager()
        success, message, actions_taken = cms.update_config_programmatically(data, create_backup)
        return {
            "success": success,
            "message": message,
            "actions_taken": actions_taken,
            "backup_location": cms.backup_file if create_backup else None
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "errors": [str(e)]
        }


def get_config_sync_status() -> dict:
    """
    Get TARS CMS sync status programmatically
    """
    try:
        cms = TarsConfigManager()
        return cms.get_config_sync_status()
    except Exception as e:
        return {"error": str(e), "is_synchronized": False}