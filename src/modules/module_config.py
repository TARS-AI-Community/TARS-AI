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
from dataclasses import dataclass
from typing import Optional, Dict, List, Set
from enum import Enum

from modules.module_messageQue import queue_message

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_cms import TarsConfigManager

load_dotenv()

character_name = "TARS"

# ── Config cache (avoids re-reading config.ini on every load_config() call) ──
_config_cache = None


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
        allowed_stt={"fastrtc", "silero", "openai", "external", "sherpa-onnx"},
        allowed_tts={"espeak", "piper", "silero", "elevenlabs", "openai", "other", "external"},
        allowed_vad={"silero", "rms", "sherpa-onnx", "smart-turn"},
        allowed_wake={"fastrtc", "atomik", "sherpa-onnx"},
        can_use_embeddings=True,
        can_use_ui=True,
        can_use_vision=True,
        can_use_emotion=True,
        can_use_opengl=True,
        can_use_cv2=True,
        max_context_size=16000,
        fallback_stt="fastrtc",
        fallback_tts="espeak",
        fallback_vad="rms",
        fallback_wake="atomik",
    ),
    DeviceProfile.PI4: DeviceCapabilities(
        profile=DeviceProfile.PI4,
        allowed_stt={"openai", "external", "sherpa-onnx"},
        allowed_tts={"espeak", "piper", "elevenlabs", "openai", "other", "external"},
        allowed_vad={"rms", "sherpa-onnx", "smart-turn"},
        allowed_wake={"atomik", "sherpa-onnx"},
        can_use_embeddings=False,
        can_use_ui=True,
        can_use_vision=False,
        can_use_emotion=False,
        can_use_opengl=True,
        can_use_cv2=False,
        max_context_size=8000,
        fallback_stt="openai",
        fallback_tts="espeak",
        fallback_vad="rms",
        fallback_wake="atomik",
    ),
    DeviceProfile.PI3: DeviceCapabilities(
        profile=DeviceProfile.PI3,
        allowed_stt={"openai", "external"},
        allowed_tts={"espeak", "elevenlabs", "openai", "other", "external"},
        allowed_vad={"rms", "sherpa-onnx"},
        allowed_wake={"atomik", "sherpa-onnx"},
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
        fallback_wake="atomik",
    ),
    DeviceProfile.PIZERO2: DeviceCapabilities(
        profile=DeviceProfile.PIZERO2,
        allowed_stt={"openai"},
        allowed_tts={"elevenlabs", "openai", "other", "external"},
        allowed_vad={"rms"},
        allowed_wake={"atomik"},
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
        fallback_wake="atomik",
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
    is_talking_override: bool = False
    is_talking: bool = False
    global_timer_paused: bool = False
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_model: Optional[str] = None
    ttsurl: Optional[str] = None
    openai_voice: Optional[str] = None
    openai_api_key: Optional[str] = None
    piper_multispeaker: bool = False
    piper_speaker_joy: int = 0
    piper_speaker_neutral: int = 1
    piper_speaker_fear: int = 2
    piper_speaker_curiosity: int = 3
    piper_speaker_love: int = 4
    piper_speaker_sadness: int = 5
    piper_speaker_surprise: int = 6
    piper_speaker_anger: int = 7

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def validate(self) -> bool:
        if self.ttsoption == "elevenlabs":
            if not self.elevenlabs_api_key:
                queue_message("ERROR: ElevenLabs API key is required for ElevenLabs TTS")
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
            elevenlabs_api_key=config_dict.get('elevenlabs_api_key'),
            elevenlabs_voice_id=config_dict.get('elevenlabs_voice_id'),
            elevenlabs_model=config_dict.get('elevenlabs_model'),
            ttsurl=config_dict.get('ttsurl'),
            openai_voice=config_dict.get('openai_voice'),
            openai_api_key=config_dict.get('openai_api_key'),
            piper_multispeaker=config_dict.get('piper_multispeaker', False),
            piper_speaker_joy=config_dict.get('piper_speaker_joy', 0),
            piper_speaker_neutral=config_dict.get('piper_speaker_neutral', 1),
            piper_speaker_fear=config_dict.get('piper_speaker_fear', 2),
            piper_speaker_curiosity=config_dict.get('piper_speaker_curiosity', 3),
            piper_speaker_love=config_dict.get('piper_speaker_love', 4),
            piper_speaker_sadness=config_dict.get('piper_speaker_sadness', 5),
            piper_speaker_surprise=config_dict.get('piper_speaker_surprise', 6),
            piper_speaker_anger=config_dict.get('piper_speaker_anger', 7),
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
    global character_name, _config_cache
    if _config_cache is not None:
        return _config_cache
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
        'CONTROLS', 'STT', 'CHAR', 'LLM', 'VISION', 'EMOTION', 'TTS'
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
            "language": config['STT']['language'],
            "external_url": config['STT']['external_url'],
            "sherpa_onnx_denoise": config.get('STT', 'sherpa_onnx_denoise', fallback='False'),
            "sherpa_onnx_punctuation": config.get('STT', 'sherpa_onnx_punctuation', fallback='False'),
            "wake_word": config['STT']['wake_word'],
            "wake_word_processor": config['STT']['wake_word_processor'],
            "atomik_mode": config.get('STT', 'atomik_mode', fallback='auto'),
            "sensitivity": config['STT']['sensitivity'],
            "vad_transcript_verify": config.get('STT', 'vad_transcript_verify', fallback='False'),
            "vad_presence_gate": config.get('STT', 'vad_presence_gate', fallback='off'),
            "vad_speaker_verify": config.get('STT', 'vad_speaker_verify', fallback='off'),
            "vad_speaker_threshold": config.get('STT', 'vad_speaker_threshold', fallback='0.60'),
            "enable_bargein": config.getboolean('STT', 'enable_bargein', fallback=True),
            "bargein_mode": config.get('STT', 'bargein_mode', fallback='fuzzy'),
            "bargein_sensitivity": config.getint('STT', 'bargein_sensitivity', fallback=5),
            "vad_method": config['STT']['vad_method'],
            "speechdelay": int(config['STT']['speechdelay']),
            "speaker_id_enabled": config.get('STT', 'speaker_id_enabled', fallback='False'),
            "speaker_id_threshold": config.get('STT', 'speaker_id_threshold', fallback='0.75'),
            "mic_amp_gain": config.getfloat('STT', 'mic_amp_gain', fallback=10.0),
            "silence_margin": config.getfloat('STT', 'silence_margin', fallback=3.0),
        },
        "CHAR": {
            "character_name": character_name,
            "character_card_path": config['CHAR']['character_card_path'],
            "location_name": config.get('CHAR', 'location_name', fallback=''),
            "latitude": config.get('CHAR', 'latitude', fallback=''),
            "longitude": config.get('CHAR', 'longitude', fallback=''),
            "user_name": config['CHAR']['user_name'],
            "user_details": config['CHAR']['user_details'],
            "enable_thinking_responses": config.getboolean('CHAR', 'enable_thinking_responses', fallback=True),
            "thinking_responses": config['CHAR']['thinking_responses'],
            "responses": config['CHAR']['responses'],
            "traits": persona_traits,
        },
        "LLM": {
            "llm_backend": config['LLM']['llm_backend'],
            "base_url": config['LLM']['base_url'],
            "openai_model": config['LLM']['openai_model'],
            "other_model": config.get('LLM', 'other_model', fallback=''),
            "grok_model": config['LLM']['grok_model'],
            "systemprompt": config['LLM']['systemprompt'],
            "contextsize": int(config['LLM']['contextsize']),
            "max_tokens": int(config['LLM']['max_tokens']),
            "seed": int(config['LLM']['seed']),
            "temperature": float(config['LLM']['temperature']),
            "top_p": float(config['LLM']['top_p']),
            "json_mode": config.getboolean('LLM', 'json_mode', fallback=True),
            "override_encoding_model": config['LLM']['override_encoding_model'],
            "api_key": get_api_key(config['LLM']['llm_backend']),
        },
        "VISION": {
            "enabled": config.getboolean('VISION', 'enabled'),
            "camera_rotation": config.getint('VISION', 'camera_rotation', fallback=0),
            "vision_processor": config.get('VISION', 'vision_processor', fallback='blip'),
            "use_llm_backend": config.getboolean('VISION', 'use_llm_backend', fallback=True),
            "external": config.get('VISION', 'vision_processor', fallback='blip') == 'external',
            "base_url": config.get('VISION', 'base_url', fallback=''),
            "vision_model": config.get('VISION', 'vision_model', fallback=''),
            "vision_max_tokens": config.getint('VISION', 'vision_max_tokens', fallback=150),
        },
        "EMOTION": {
            "enabled": config.getboolean('EMOTION', 'enabled'),
            "emotion_method": config.get('EMOTION', 'emotion_method', fallback='classifier'),
            "emotion_model": config['EMOTION']['emotion_model'],
        },
        "TTS": TTSConfig.from_config_dict({
            "ttsoption": config['TTS']['ttsoption'],
            "elevenlabs_api_key": os.getenv('ELEVENLABS_API_KEY'),
            "openai_api_key": os.getenv('OPENAI_API_KEY'),
            "ttsurl": config.get('TTS', 'ttsurl', fallback=''),
            "toggle_charvoice": config.getboolean('TTS', 'toggle_charvoice'),
            "tts_voice": config.get('TTS', 'tts_voice', fallback=''),
            "elevenlabs_voice_id": config['TTS']['elevenlabs_voice_id'],
            "elevenlabs_model": config['TTS']['elevenlabs_model'],
            "is_talking_override": False,
            "is_talking": False,
            "global_timer_paused": False,
            "openai_voice" : config['TTS']['openai_voice'],
            "piper_multispeaker": config.getboolean('TTS', 'piper_multispeaker', fallback=False),
            "piper_speaker_joy": config.getint('TTS', 'piper_speaker_joy', fallback=0),
            "piper_speaker_neutral": config.getint('TTS', 'piper_speaker_neutral', fallback=1),
            "piper_speaker_fear": config.getint('TTS', 'piper_speaker_fear', fallback=2),
            "piper_speaker_curiosity": config.getint('TTS', 'piper_speaker_curiosity', fallback=3),
            "piper_speaker_love": config.getint('TTS', 'piper_speaker_love', fallback=4),
            "piper_speaker_sadness": config.getint('TTS', 'piper_speaker_sadness', fallback=5),
            "piper_speaker_surprise": config.getint('TTS', 'piper_speaker_surprise', fallback=6),
            "piper_speaker_anger": config.getint('TTS', 'piper_speaker_anger', fallback=7),
        }),
        "RAG": {
            "enabled": config.getboolean('RAG', 'enabled', fallback=True),
            "strategy": config.get('RAG', 'strategy', fallback='naive'),
            "enable_topic_tracking": config.getboolean('RAG', 'enable_topic_tracking'),
            "context_window": config.getint('RAG', 'context_window', fallback=2),
            "max_memories": config.getint('RAG', 'max_memories', fallback=3),
            "top_k": config.getint('RAG', 'top_k', fallback=5),
            "recency_boost_days": config.getint('RAG', 'recency_boost_days', fallback=7),
            "embedding_source": config.get('RAG', 'embedding_source', fallback='local'),
            "embedding_url": config.get('RAG', 'embedding_url', fallback=''),
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
        "ACCESS": {
            "webui_enabled": config.getboolean('ACCESS', 'webui_enabled', fallback=True),
            "webui_port": config.getint('ACCESS', 'webui_port', fallback=80),
            "webui_password": config.get('ACCESS', 'webui_password', fallback='tarspass1234'),
            "webui_theme": config.get('ACCESS', 'webui_theme', fallback='default'),
            "remote_access_enabled": config.getboolean('ACCESS', 'remote_access_enabled', fallback=False),
        },
        "UI": {
            "UI_enabled": config.getboolean('UI', 'UI_enabled'),
            "use_camera_module": config.getboolean('UI', 'use_camera_module'),
            "show_mouse": config.getboolean('UI', 'show_mouse'),
            "fullscreen": config.getboolean('UI', 'fullscreen'),
            "screen_width": config.getint('UI', 'screen_width', fallback=480),
            "screen_height": config.getint('UI', 'screen_height', fallback=320),
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
        "BATTERY": {
            "battery_enabled": config.getboolean('BATTERY', 'battery_enabled', fallback=False),
            "battery_auto_shutdown": config.getboolean('BATTERY', 'battery_auto_shutdown', fallback=False),
            "battery_capacity_mAh": int(config.get('BATTERY', 'battery_capacity_mAh', fallback='3000')),
            "battery_initial_voltage": float(config.get('BATTERY', 'battery_initial_voltage', fallback='12')),
            "battery_cutoff_voltage": float(config.get('BATTERY', 'battery_cutoff_voltage', fallback='10')),
        }
    }

    config_dict = apply_device_overrides(config_dict, capabilities)
    _config_cache = config_dict
    return config_dict


def get_api_key(llm_backend: str) -> str:
    backend_to_env_var = {
        "openai": "OPENAI_API_KEY",
        "grok": "GROK_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
        "other": "OTHER_API_KEY"
    }
    if llm_backend not in backend_to_env_var:
        print(f"WARNING: Unsupported LLM backend '{llm_backend}', skipping API key lookup.")
        return ""
    api_key = os.getenv(backend_to_env_var[llm_backend])
    if not api_key:
        print(f"WARNING: No API key found for '{llm_backend}' (env var: {backend_to_env_var[llm_backend]}). LLM features will be unavailable.")
        return ""
    return api_key


_persona_cache = None       # cached persona traits dict
_persona_mtime = 0.0        # mtime of persona.ini when last read


def reload_persona_settings():
    global character_name, _persona_cache, _persona_mtime
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        persona_path = os.path.join(base_dir, 'character', character_name, 'persona.ini')
        if not os.path.exists(persona_path):
            queue_message(f"WARNING: persona.ini not found at {persona_path}")
            return None
        # Only re-read if the file has actually changed
        mtime = os.path.getmtime(persona_path)
        if _persona_cache is not None and mtime == _persona_mtime:
            return _persona_cache
        persona_config = configparser.ConfigParser()
        persona_config.read(persona_path)
        if 'PERSONA' in persona_config:
            _persona_cache = {key: int(value) for key, value in persona_config['PERSONA'].items()}
            _persona_mtime = mtime
            return _persona_cache
        return None
    except Exception as e:
        queue_message(f"ERROR: Failed to reload persona settings: {e}")
        return None


def update_character_setting(trait: str, value: int):
    global character_name, _persona_cache, _persona_mtime
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
        # Invalidate persona cache so next reload picks up the change
        _persona_cache = None
        _persona_mtime = 0.0
        queue_message(f"INFO: Updated {trait} to {value}")
        return True
    except Exception as e:
        queue_message(f"ERROR: Failed to update character setting: {e}")
        return False


CONFIG_METADATA = {
    'CHAR': {
        '__description__': 'Set up who TARS is, who you are, and what TARS says when you talk to it',
        'character_card_path': {
            'label': 'Character',
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
        'enable_thinking_responses': {
            'description': 'When ON, TARS will say a random filler phrase (like "Let me think..." or "Processing...") while it waits for the AI to generate a response. When OFF, TARS stays silent while thinking.'
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
            'label': 'AI Backend',
            'options': ['openai', 'grok', 'deepinfra', 'other'],
            'description': 'Choose which AI service TARS uses to generate responses. "openai" uses OpenAI (GPT models) — auto-fills the URL, requires OPENAI_API_KEY in .env. "grok" uses xAI\'s Grok — auto-fills the URL, requires XAI_API_KEY in .env. "deepinfra" uses DeepInfra (cheap hosted models) — auto-fills the URL, requires DEEPINFRA_API_KEY in .env. "other" is for any OpenAI-compatible API — you set the URL yourself and it is preserved when switching backends. Use "other" for Featherless.ai, Ollama (local), LM Studio (local), OpenRouter, or any self-hosted model server. Switching backends auto-updates the URL field except for "other", which always restores your saved URL.'
        },
        'base_url': {
            'label': 'Base URL',
            'depends_on': [{'field': 'llm_backend', 'values': ['other']}],
            'description': 'The API endpoint for your AI service. For the "other" backend, set your server address here (e.g. http://192.168.1.100:11434/v1 for Ollama, or https://api.featherless.ai/v1 for Featherless). For "openai", "grok", and "deepinfra" this is handled automatically.'
        },
        'openai_model': {
            'label': 'model',
            'depends_on': [{'field': 'llm_backend', 'values': ['openai', 'deepinfra']}],
            'description': 'The model identifier sent to the OpenAI or DeepInfra API. For OpenAI: "gpt-4o-mini" is the cheapest capable model (good default), "gpt-4o" is more powerful but costs more per request, "o1-mini" is a reasoning model good for complex questions. For DeepInfra: use the full model path like "meta-llama/Meta-Llama-3.1-70B-Instruct". If you type a model name that does not exist, the API will return an error - check the provider dashboard for a list of available models.'
        },
        'other_model': {
            'label': 'model',
            'depends_on': [{'field': 'llm_backend', 'values': ['other']}],
            'description': 'The model identifier sent to your custom OpenAI-compatible endpoint. The exact format depends on the service you are using. Featherless.ai: use the full HuggingFace path like "meta-llama/Meta-Llama-3.1-8B-Instruct". Ollama: use just the model name you pulled, like "llama3.1:8b" or "qwen2.5:3b". LM Studio: use the model name shown in the app. OpenRouter: use the provider/model format like "mistralai/mistral-7b-instruct". If you get a 404 or "model not found" error, check that the model name exactly matches what your server expects.'
        },
        'json_mode': {
            'label': 'JSON Mode',
            'depends_on': [{'field': 'llm_backend', 'values': ['other']}],
            'description': 'When ON, TARS tells the AI to respond in structured JSON format using the API\'s response_format parameter. Turn OFF if your backend doesn\'t support it (like LM Studio or Ollama) — you\'ll see a 400 Bad Request error if unsupported. TARS will still work without it since the system prompt already asks for JSON, but responses may occasionally need more repair. OpenAI, Grok, and DeepInfra always use JSON mode regardless of this setting.'
        },
        'grok_model': {
            'depends_on': [{'field': 'llm_backend', 'values': ['grok']}],
            'description': 'The Grok model to use when your backend is set to "grok". Current options: "grok-4-1-fast-non-reasoning" is the fastest option and works well for casual conversation. "grok-4-1-fast-reasoning" is a reasoning model that thinks through problems step-by-step (slower but better for complex questions). "grok-3-mini" is a smaller, cheaper model. Check xAI docs for the latest available model names as new ones are added regularly.'
        },
        'systemprompt': {
            'description': 'Hidden instructions that TARS reads before every conversation. This tells the AI HOW to behave in general - like being helpful, conversational, staying in character, etc. This is different from the character card: the character card defines WHO TARS is, while this prompt defines the general RULES for how it should respond. Most people can leave the default as-is.'
        },
        'contextsize': {
            'description': 'How much conversation history TARS remembers in a single chat session. Measured in "tokens" (roughly: 1 token = about 1 word). A higher number means TARS can remember more of what you talked about, but it costs more money per message (if using a paid service) and can be slower. 4000 is a good default for most models. Common model limits: GPT-4o supports up to 128,000 tokens, GPT-4o-mini supports 128,000, Llama 3.1 8B supports 128,000, older models may cap at 4,096 or 8,192. Setting contextsize higher than the model supports will cause errors. If TARS seems to forget what you just said, try increasing this. If responses are slow or expensive, try lowering it to 2000.'
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
            'description': 'Controls how TARS counts tokens (message size) before sending to the AI. DO NOT change this unless you see token-counting errors in the logs. "cl100k_base" is the correct encoding for GPT-4, GPT-3.5-turbo, and most modern models — leave this as-is for 99% of setups. "p50k_base" was used for older InstructGPT/Codex models. "r50k_base" is for legacy GPT-3. "gpt2" is for very old models. If TARS logs say something like "KeyError: encoding not found for model X", try leaving the model name fallback alone first — TARS already falls back to this encoding automatically when the model name is not recognized.'
        },
    },
    'STT': {
        '__description__': 'Configure how TARS listens — wake word, speech recognition, and end-of-speech detection',

        # ── Speech Recognition ────────────────────────────────────────────────
        'stt_processor': {
            'group': 'stt', 'group_label': 'Speech Recognition',
            'label': 'STT Engine',
            'options': ['sherpa-onnx', 'fastrtc', 'openai', 'external', 'silero'],
            'description': 'How TARS converts your speech to text after the wake word triggers. "sherpa-onnx" is fast and offline (Pi5/Pi4, recommended). "fastrtc" is cloud-based, very accurate. "openai" uses OpenAI Whisper (best for non-English, requires API key). "silero" runs on-device (Pi5 only). "external" forwards audio to your own STT server.'
        },
        'language': {
            'group': 'stt',
            'label': 'Spoken Language',
            'options': ['english', 'spanish', 'french', 'german', 'italian', 'portuguese', 'dutch', 'russian', 'chinese', 'japanese', 'korean'],
            'description': 'The language you speak to TARS. For non-English languages, set STT Engine to "openai" — most local on-device models only work well in English.'
        },
        'external_url': {
            'group': 'stt',
            'label': 'External STT Server URL',
            'depends_on': [{'field': 'stt_processor', 'values': ['external']}],
            'description': 'URL of your external speech-to-text server. Format: http://IP-ADDRESS:PORT'
        },
        'sherpa_onnx_denoise': {
            'group': 'stt',
            'label': 'Noise Reduction',
            'options': ['True', 'False'],
            'depends_on': [{'field': 'stt_processor', 'values': ['sherpa-onnx']}],
            'description': 'Clean up audio before transcription to remove background noise (fans, AC, etc). Uses the GTCRN denoiser (~5MB). Leave OFF in quiet environments.'
        },
        'sherpa_onnx_punctuation': {
            'group': 'stt',
            'label': 'Auto Punctuation',
            'options': ['True', 'False'],
            'depends_on': [{'field': 'stt_processor', 'values': ['sherpa-onnx']}],
            'description': 'Add punctuation to transcribed text automatically. Uses the ct-transformer model (~200MB). Leave OFF if the model is not downloaded or you prefer raw transcriptions.'
        },

        # ── Wake Word ─────────────────────────────────────────────────────────
        'wake_word': {
            'group': 'wake_word', 'group_label': 'Wake Word',
            'label': 'Wake Word',
            'description': 'The phrase you say to activate TARS, like "Hey Siri" or "OK Google". Shorter phrases (2–3 syllables) work best — e.g. "hey tars", "ok robot", "computer". Avoid very common words that might trigger accidentally.'
        },
        'wake_word_processor': {
            'group': 'wake_word',
            'label': 'Wake Word Engine',
            'options': ['atomik', 'fastrtc', 'sherpa-onnx'],
            'description': '"atomik" is built into TARS, works offline, and is the recommended choice. "sherpa-onnx" transcribes audio and matches the wake word offline (Pi5/Pi4). "fastrtc" uses an internet-based service for detection.'
        },
        'atomik_mode': {
            'group': 'wake_word',
            'label': 'Atomik Detection Mode',
            'depends_on': [{'field': 'wake_word_processor', 'values': ['atomik']}],
            'options': ['auto', 'model', 'template'],
            'description': '"auto" uses the ONNX model if available, otherwise falls back to template matching. "model" requires a trained ONNX model (created with the wakeword-trainer tool). "template" records your wake word 5 times on-device and matches by cosine similarity — easiest to set up.'
        },
        'sensitivity': {
            'group': 'wake_word',
            'label': 'Wake Word Strictness',
            'depends_on': [{'field': 'wake_word_processor', 'values': ['atomik']}],
            'type': 'slider',
            'min': 1,
            'max': 10,
            'step': 1,
            'description': 'How strictly TARS matches the wake word (atomik only). 1 = very lenient, triggers easily. 10 = very strict, requires a clear and precise match. Start at 5. Raise it if TARS activates randomly; lower it if TARS stops hearing you.'
        },

        # ── Wake Word Gates ───────────────────────────────────────────────────
        'vad_transcript_verify': {
            'group': 'wake_gates', 'group_label': 'Wake Word Gates',
            'label': 'Transcript Verification',
            'options': ['True', 'False'],
            'description': 'After wake word detection, TARS transcribes the audio and confirms the wake word was actually spoken before responding. Nearly eliminates false positives at a small cost (~100–200ms). Only active in atomik template mode; sherpa-onnx and fastrtc already use transcription as their primary detection.'
        },
        'vad_presence_gate': {
            'group': 'wake_gates',
            'label': 'Presence Gate',
            'options': ['off', 'any', 'known'],
            'description': 'Require someone to be visible on camera before TARS responds to the wake word. "off" = disabled. "any" = any face detected (good for keeping TARS quiet in an empty room). "known" = only a recognized enrolled person (prevents TARS responding to strangers or the TV). Background camera detection starts automatically when not "off".'
        },
        'vad_speaker_verify': {
            'group': 'wake_gates',
            'label': 'Speaker Verification',
            'options': ['off', 'any'],
            'description': 'Restrict who can trigger the wake word by voice. "off" = disabled. "any" = any enrolled named speaker. Select a specific name to allow only that person. Requires Speaker ID to be enabled. Skips automatically if no named speakers are enrolled yet.'
        },
        'vad_speaker_threshold': {
            'group': 'wake_gates',
            'label': 'Speaker Match Threshold',
            'depends_on': [{'field': 'vad_speaker_verify', 'not_values': ['off']}],
            'type': 'slider',
            'min': 0.3,
            'max': 0.9,
            'step': 0.05,
            'description': 'How closely the voice must match an enrolled speaker. 0.60 is a good starting point. Raise it if strangers or the TV are triggering TARS; lower it if your own voice is being rejected.'
        },

        # ── Barge-In ──────────────────────────────────────────────────────────
        'enable_bargein': {
            'group': 'bargein', 'group_label': 'Barge-In',
            'label': 'Enable Barge-In',
            'description': 'Allow interrupting TARS while it\'s talking by speaking over it. When OFF, TARS always finishes its full response before listening again.'
        },
        'bargein_mode': {
            'group': 'bargein',
            'label': 'Barge-In Mode',
            'options': ['fuzzy', 'voiceprint'],
            'depends_on': [{'field': 'enable_bargein', 'values': ['True', 'true']}],
            'description': '"fuzzy" transcribes mic audio and checks if the words differ from what TARS is saying — works without any setup. "voiceprint" checks if the interrupting voice matches an enrolled speaker — best in noisy rooms with echo. Requires Speaker ID and at least one enrolled speaker.'
        },
        'bargein_sensitivity': {
            'group': 'bargein',
            'label': 'Barge-In Sensitivity',
            'type': 'slider',
            'min': 1,
            'max': 10,
            'step': 1,
            'depends_on': [{'field': 'enable_bargein', 'values': ['True', 'true']}],
            'description': 'How easy it is to interrupt TARS. 1 = very hard to interrupt. 10 = interrupts at the slightest sound. Start at 5. Lower if TARS gets falsely interrupted by background noise or its own speaker.'
        },

        # ── End-of-Speech Detection ───────────────────────────────────────────
        'use_indicators': {
            'group': 'vad', 'group_label': 'End-of-Speech Detection',
            'label': 'Audio Indicators',
            'description': 'Play a beep when TARS starts and stops recording. The high beep means "I\'m listening", the low beep means "got it, processing". Turn OFF if the beeps are disruptive.'
        },
        'vad_method': {
            'group': 'vad',
            'label': 'Detection Method',
            'options': ['smart-turn', 'sherpa-onnx', 'silero', 'rms'],
            'description': 'How TARS knows you have finished speaking. "smart-turn" uses Pipecat Smart Turn to predict sentence completion from speech patterns — won\'t cut you off mid-pause (Pi5/Pi4). "sherpa-onnx" uses Silero VAD via ONNX (Pi5/Pi4/Pi3, no torch needed). "silero" uses Silero VAD with PyTorch (Pi5). "rms" detects silence by volume — lightweight and works on any Pi.'
        },
        'speechdelay': {
            'group': 'vad',
            'label': 'Silence Before Processing',
            'description': 'How long TARS waits after you stop talking before processing your message. In tenths of a second — 15 = 1.5s, 20 = 2s. Too short and TARS cuts you off mid-thought; too long and there\'s an awkward pause. 15–20 works for most people.'
        },
    },
    'TTS': {
        '__description__': 'Configure how TARS speaks - choose a voice engine and customize how it sounds',
        'toggle_charvoice': {
            'description': 'When this is ON, TARS will use voice settings stored in the character card file instead of the settings on this page. This is useful if you have multiple characters (like TARS, a pirate, a wizard, etc.) and each one should have a different voice. When OFF, the voice settings on this page are always used regardless of which character is loaded.'
        },
        'ttsoption': {
            'label': 'TTS Engine',
            'options': ['espeak', 'piper', 'silero', 'elevenlabs', 'openai', 'other', 'external'],
            'description': 'Choose how TARS speaks out loud. This is the most important voice setting. FREE options that work without internet: "piper" sounds natural and is the best free option (recommended for Pi 5 and Pi 4). "espeak" is a basic robotic-sounding voice but works on any Pi, even very weak ones. "silero" is another good-sounding option but only works on Pi 5. PAID cloud options (need internet + API key in .env file): "elevenlabs" has the most natural, human-like voices. "openai" is good quality and works well in many languages. "other" lets you point to any external TTS server using a custom URL. "external" sends text to a TARS app-server instance for TTS generation.'
        },
        'ttsurl': {
            'label': 'TTS Server URL',
            'depends_on': [{'field': 'ttsoption', 'values': ['other', 'external']}],
            'description': 'The URL of your external TTS server. Used when TTS Engine is set to "other" or "external". Format: http://IP-ADDRESS:PORT. For "external", point to your TARS app-server (e.g. http://192.168.1.100:5678). For "other", compatible servers include Coqui TTS, Piper server mode, AllTalk TTS.'
        },
        'tts_voice': {
            'label': 'TTS Voice',
            'depends_on': [{'field': 'ttsoption', 'values': ['other', 'external']}],
            'description': 'The voice name or ID to request from your external TTS server. Leave blank if your server uses a default voice or does not support voice selection.'
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
        'openai_voice': {
            'depends_on': [{'field': 'ttsoption', 'values': ['openai']}],
            'options': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            'description': 'Only matters if you are using "openai" as your TTS engine. Each voice has a different personality: "alloy" is neutral and balanced. "echo" is warm and conversational. "fable" has a British accent and is expressive. "onyx" is deep and authoritative (the best match for TARS from the movie). "nova" is friendly and upbeat. "shimmer" is clear and gentle. Try a few and see which one you like!'
        },
        'piper_multispeaker': {
            'label': 'Multi-Speaker Mode',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}],
            'description': 'Enable this if your Piper voice model supports multiple speakers (i.e. it was trained with multiple voices, one per emotion). When ON, TARS will automatically select the speaker that matches the detected emotion of its response. Leave OFF for standard single-speaker Piper models.'
        },
        'piper_speaker_joy': {
            'label': 'Speaker ID — Joy',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses joy. Check your model\'s .onnx.json for available speaker IDs.'
        },
        'piper_speaker_neutral': {
            'label': 'Speaker ID — Neutral',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use for neutral responses.'
        },
        'piper_speaker_fear': {
            'label': 'Speaker ID — Fear',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses fear.'
        },
        'piper_speaker_curiosity': {
            'label': 'Speaker ID — Curiosity',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses curiosity.'
        },
        'piper_speaker_love': {
            'label': 'Speaker ID — Love',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses love.'
        },
        'piper_speaker_sadness': {
            'label': 'Speaker ID — Sadness',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses sadness.'
        },
        'piper_speaker_surprise': {
            'label': 'Speaker ID — Surprise',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses surprise.'
        },
        'piper_speaker_anger': {
            'label': 'Speaker ID — Anger',
            'depends_on': [{'field': 'ttsoption', 'values': ['piper']}, {'field': 'piper_multispeaker', 'values': ['true', 'True']}],
            'description': 'Piper speaker ID to use when TARS expresses anger.'
        },
    },
    'EMOTION': {
        '__description__': 'Controls whether TARS shows emotions on its face/display based on what it says',
        'enabled': {
            'description': 'When ON, TARS analyzes its own responses to figure out the emotion behind them (happy, sad, angry, surprised, etc.) and then shows matching facial expressions on its screen. This makes TARS feel more alive and expressive. Turn this OFF if you are not using the TARS display screen, or if you want to save processing power on weaker Pi models.'
        },
        'emotion_method': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['classifier', 'llm'],
            'option_labels': {'classifier': 'Classifier (local model)', 'llm': 'LLM (from response)'},
            'label': 'Detection Method',
            'description': 'How TARS detects emotions. "Classifier" downloads and runs a dedicated AI model locally (~500MB RAM, 28 fine-grained emotions). "LLM" asks your existing LLM to include the emotion in its response — zero extra RAM, but less granular (8 categories). Use LLM on Pi3/PiZero2 to save resources.'
        },
        'emotion_model': {
            'depends_on': [
                {'field': 'enabled', 'values': ['True', 'true']},
                {'field': 'emotion_method', 'values': ['classifier']}
            ],
            'description': 'The name of the AI model used to detect emotions in text. The default model can recognize 28 different emotions like joy, sadness, anger, surprise, fear, and more. It gets downloaded automatically the first time you enable emotion detection (about 500MB download). You should not need to change this unless you want to experiment with a different emotion model from HuggingFace.'
        },
    },
    'VISION': {
        '__description__': 'Let TARS see the world through a camera or process uploaded photos',
        'enabled': {
            'description': 'When ON, TARS can use a camera to see and describe what is in front of it, and can process photos uploaded through the web UI. You can ask "what do you see?" and TARS will take a picture and tell you.'
        },
        'camera_rotation': {
            'label': 'Camera Rotation',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['0', '90', '180', '270'],
            'description': 'Rotate the camera image by this many degrees. Use this if your camera is mounted sideways or upside down. 0 = no rotation, 90 = rotated right, 180 = upside down, 270 = rotated left.'
        },
        'vision_processor': {
            'label': 'Vision Processor',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['blip', 'llm', 'openai', 'external'],
            'description': 'How TARS processes images. "blip" runs a local AI model on your Pi (~1GB RAM) and generates a short caption. "llm" sends the image to your configured LLM backend (must support vision). "openai" sends the image to OpenAI GPT-4o-mini (requires OPENAI_API_KEY). "external" sends the image to an external BLIP server you run on another computer. "external" sends the image to a TARS app-server instance (uses EXTERNAL_API_KEY from .env).'
        },
        'use_llm_backend': {
            'label': 'Use Same as LLM',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'vision_processor', 'values': ['openai', 'llm']}],
            'description': 'When ON, vision uses the same model and API settings as your main LLM backend. Turn OFF to configure a separate model and URL for vision processing.'
        },
        'base_url': {
            'label': 'Vision API URL',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'use_llm_backend', 'values': ['False', 'false']}, {'field': 'vision_processor', 'values': ['external', 'openai', 'llm']}],
            'description': 'The API base URL for vision processing. For server_hosted: the BLIP server (e.g. http://192.168.1.100:5678). For llm/openai: the API endpoint (e.g. https://api.openai.com). Leave blank to use the default for your provider.'
        },
        'vision_model': {
            'label': 'Vision Model',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'use_llm_backend', 'values': ['False', 'false']}, {'field': 'vision_processor', 'values': ['openai', 'llm']}],
            'description': 'The model name for vision. For OpenAI, defaults to gpt-4o-mini if blank.'
        },
        'vision_max_tokens': {
            'label': 'Vision Max Tokens',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'vision_processor', 'values': ['openai', 'llm', 'external']}],
            'description': 'Maximum number of tokens in the vision response. Higher values give more detailed descriptions but cost more.'
        },
    },
    'RAG': {
        '__description__': 'TARS long-term memory - lets TARS remember past conversations and bring up relevant info',
        'enabled': {
            'description': 'Master switch for TARS long-term memory. When ON, TARS saves conversations and recalls relevant past interactions to give more personal, context-aware responses over time. Turn OFF if you want TARS to have no memory of past conversations, or if you are running low on storage/resources.'
        },
        'enable_topic_tracking': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When ON, TARS creates summaries of conversation topics over time. This is like TARS writing notes in a journal about what you have been talking about. These topic summaries help TARS remember broad themes from weeks or months ago, even when the individual conversation details have faded. This gives TARS a much better long-term memory. Recommended to leave ON.'
        },
        'strategy': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['naive', 'hybrid'],
            'description': 'How TARS searches through its memories. "hybrid" (recommended) uses two different search methods together - it looks for memories that are similar in meaning AND memories that contain matching keywords. This gives the best results. "naive" only uses meaning-based search, which is faster but might miss some relevant memories. Unless you are having performance issues, stick with "hybrid".'
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
        'embedding_source': {
            'label': 'Embedding Source',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'options': ['local', 'openai', 'external'],
            'description': 'Where to generate text embeddings for memory search. "local" runs the embedding model on this device (uses ~500MB RAM). "openai" uses the OpenAI Embeddings API (requires OPENAI_API_KEY, uses text-embedding-3-small). "external" sends text to your TARS app-server instance to generate embeddings — much faster and frees up resources on the Pi. WARNING: If you switch between sources (e.g. local to openai), the existing memory database will have vectors of the wrong size (local=384 dimensions, openai=1536) and you will need to rebuild it. Same applies to external — dimensions depend on what model the app-server is running.'
        },
        'embedding_url': {
            'label': 'Embedding Server URL',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}, {'field': 'embedding_source', 'values': ['external']}],
            'description': 'The URL of your TARS app-server for embeddings (e.g. http://192.168.1.100:5678). The server must have the embeddings service enabled.'
        },
    },
    'ACCESS': {
        '__description__': 'Web interface and remote access settings',
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
        'webui_theme': {
            'depends_on': [{'field': 'webui_enabled', 'values': ['True', 'true']}],
            'label': 'Theme',
            'description': 'Color theme for the web interface. Each theme includes unique colors, animations, backgrounds, and effects. Changes take effect immediately without restart. Themes are auto-discovered from CSS files in www/static/css/themes/.'
        },
        'remote_access_enabled': {
            'depends_on': [{'field': 'webui_enabled', 'values': ['True', 'true']}],
            'description': 'Access TARS from anywhere — not just your local network. When enabled, a secure tunnel is automatically created giving you a public URL you can use from any device, anywhere. No accounts or setup needed. A new URL is generated each time TARS starts. The tunnel panel with URL and QR code appears below when enabled.'
        },
    },
    'UI': {
        '__description__': 'Settings for the on-device display',
        'UI_enabled': {
            'label': 'Enabled',
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
        'screen_width': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Width of the TARS on-device display in pixels. Common: 480 for standard 3.5" Pi display, 800 for 5" or 7" displays. Set to 0 for auto-detect.'
        },
        'screen_height': {
            'depends_on': [{'field': 'UI_enabled', 'values': ['True', 'true']}],
            'description': 'Height of the TARS on-device display in pixels. Common: 320 for standard 3.5" Pi display, 480 for 5" displays, 600 for 7" displays. Set to 0 for auto-detect.'
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
            'options': ['terminal', 'dashboard', 'clock', 'eyes', 'avatar'],
            'description': 'What shows on the TARS display when it first starts up. "terminal" shows a scrolling chat-style interface where you can read the conversation in real time. "dashboard" shows a system status overview with battery, CPU, memory, and other stats. "clock" shows a large clean clock display — good if TARS lives on a desk. "eyes" shows an animated eye display that reacts to TARS speaking. "avatar" shows your character\'s animated sprite with blinking and talking animations. You can always switch between modes at runtime.'
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
            'options': ['random', 'blackhole', 'waves', 'matrix', 'starfield', 'hyperspace', 'terminal', 'face', 'fractal', 'pacman', 'nebulas', 'pictures', 'dashboard', 'defrag', 'bounce', 'endurance', 'dream'],
            'description': 'Pick which screensaver animations play on the TARS display when idle. Select "random" to cycle through all of them, or pick specific ones you like. "dream" visualizes recent memories as abstract neural patterns driven by TARS\' emotional state.'
        },
    },
    'CONTROLS': {
        '__description__': 'Connect a Bluetooth or USB game controller to physically steer TARS around',
        'enabled': {
            'description': 'Master switch for game controller support. Turn ON if you have a Bluetooth or USB controller paired to your Pi and want to use it to control TARS movement and actions. Leave OFF if you do not have a controller or do not want to use one.'
        },
        'ventilate': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'When ON, TARS will periodically shift its body into a position that lets more air flow through the case. This helps keep the electronics cool, especially if your TARS is in a sealed or enclosed case where heat can build up. If your Pi is running hot (check with show_cpu_temp in the UI section), try turning this ON.'
        },
        'voicemovement': {
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
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
            'label': 'BT_Controller',
            'depends_on': [{'field': 'enabled', 'values': ['True', 'true']}],
            'description': 'The name of your Bluetooth or USB game controller. TARS looks for this text in the names of all connected controllers. For example, if you have an "8BitDo Pro 2" controller, just putting "8BitDo" here is enough. For Xbox controllers, put "Xbox". For PlayStation, put "PS4" or "DualSense". It just needs to match part of the controller name.'
        },
    },
    'BATTERY': {
        '__description__': 'Monitor battery level and protect against over-discharge (requires INA260 sensor)',
        'battery_enabled': {
            'description': 'Master switch for battery monitoring. Turn ON if your TARS has an INA260 power sensor connected. When enabled, TARS tracks battery voltage and percentage and displays it on the dashboard. Leave OFF if you are running from a wall adapter or do not have the INA260 sensor.'
        },
        'battery_auto_shutdown': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'When ON, TARS will automatically and safely shut down the Raspberry Pi when the battery gets critically low (near 0%). This protects your Pi from sudden power loss (which can corrupt the SD card) and protects your battery from being over-drained. Strongly recommended if running on battery.'
        },
        'battery_capacity_mAh': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'How much charge your battery can hold in milliampere-hours (mAh). This number is printed on your battery. Examples: 3000 for a 3Ah battery, 5600 for a 5.6Ah battery. TARS uses this to calculate the remaining battery percentage.'
        },
        'battery_initial_voltage': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'The voltage of your battery when fully charged. 3S LiPo = 12.6V, 4S LiPo = 16.8V, USB power bank = 5V. TARS uses this as the 100% reference point.'
        },
        'battery_cutoff_voltage': {
            'depends_on': [{'field': 'battery_enabled', 'values': ['True', 'true']}],
            'description': 'The lowest voltage your battery should ever reach. Going below this can permanently damage it. 3S LiPo = 10.5V, 4S LiPo = 14V. TARS uses this as the 0% reference point and will shut down before reaching it if auto_shutdown is ON.'
        },
    },
}


def update_config_from_web_ui(data: dict, create_backup: bool = True) -> dict:
    """
    Update configuration using TARS CMS (Programmatic Access)
    """
    global _config_cache
    try:
        cms = TarsConfigManager()
        success, message, actions_taken = cms.update_config_programmatically(data, create_backup)
        if success:
            _config_cache = None  # Invalidate so next load_config() re-reads disk
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