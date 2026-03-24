"""
app.py

Main entry point for the TARS-AI application.

Initializes modules, loads configuration, and manages key threads for functionality such as:
- Speech-to-text (STT)
- Text-to-speech (TTS)
- Bluetooth control
- AI response generation

Includes device profile support based on raspberry_version setting in config.ini.

Run this script directly to start the application.
"""

# === Standard Libraries ===
import os
import sys
import threading
import time
from datetime import datetime
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

# === Set up paths first ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.append(os.getcwd())

# === Core Modules ===
from modules.module_config import load_config, should_use_lite_memory
from modules.module_messageQue import queue_message

# === Load Configuration ===
CONFIG = load_config()
VERSION = "Amelia"

# Get device info
DEVICE_INFO = CONFIG.get("_device", {})
RASPBERRY_VERSION = DEVICE_INFO.get("raspberry_version", "pi5")
USE_LITE_MEMORY = should_use_lite_memory(CONFIG)

queue_message(f"LOAD: TARS-AI starting on {RASPBERRY_VERSION.upper()}")

# === Import Modules ===
from modules.module_character import CharacterManager
from modules.module_tts import update_tts_settings
from modules.module_llm import initialize_manager_llm
from modules.module_skills import initialize_skills
from modules.module_stt import STTManager
from modules.module_state import set_tars_state, on_state_change, TarsState, register_stt_manager
from modules.module_main import (
    initialize_managers,
    wake_word_callback,
    utterance_callback,
    post_utterance_callback,
    start_bt_controller_thread,
    startup_initialization
)
from modules.module_llm import process_completion

# === Conditional Memory Manager Import ===
if USE_LITE_MEMORY:
    from modules.module_memory_lite import MemoryManagerLite as MemoryManager
else:
    from modules.module_memory import MemoryManager

# === Conditional Vision Import ===
VISION_AVAILABLE = False
if CONFIG['VISION']['enabled']:
    caps = DEVICE_INFO.get("capabilities")
    if caps is None or caps.can_use_vision or CONFIG['VISION']['vision_processor'] in ('server_hosted', 'openai', 'llm'):
        try:
            from modules.module_vision import initialize_blip
            VISION_AVAILABLE = True
            queue_message("LOAD: Vision module available")
        except ImportError as e:
            queue_message(f"WARNING: Vision module not available: {e}")

# === Conditional UI Import ===
UI_AVAILABLE = False
_use_lite_ui = False
if CONFIG["UI"]["UI_enabled"]:
    caps = DEVICE_INFO.get("capabilities")
    if caps is None or caps.can_use_ui:
        _use_lite_ui = caps is not None and not caps.can_use_opengl
        try:
            if _use_lite_ui:
                from modules.module_ui_lite import UIManagerLite as UIManager
                queue_message("LOAD: Lite UI module enabled")
            else:
                from modules.module_ui import UIManager
                queue_message("LOAD: Full UI module enabled")
            UI_AVAILABLE = True
        except Exception as e:
            import traceback
            queue_message(f"WARNING: UI module not available: {type(e).__name__}: {e}")
            traceback.print_exc()

# === Conditional ChatUI Import ===
CHATUI_AVAILABLE = False
if CONFIG['ACCESS']['webui_enabled']:
    try:
        import modules.module_chatui
        CHATUI_AVAILABLE = True
    except ImportError as e:
        queue_message(f"WARNING: ChatUI module not available: {e}")

# === Always Load These ===
from modules.module_battery import BatteryModule
from modules.module_cputemp import CPUTempModule
from modules import module_servoctl

# === Conditional Bluetooth Controller ===
BT_AVAILABLE = False
if CONFIG['CONTROLS']['enabled']:
    try:
        from modules.module_btcontroller import start_controls
        BT_AVAILABLE = True
    except ImportError:
        queue_message("WARNING: Bluetooth controller not available")

# === Global Instances ===
ui_manager = None
stt_manager = None


# === UI Stub for devices without UI ===
class UIManagerStub:
    """Lightweight stub when full UI is disabled."""
    
    def __init__(self, *args, **kwargs):
        self.running = False
    
    def start(self):
        self.running = True
    
    def stop(self):
        self.running = False
    
    def pause(self):
        pass
    
    def resume(self):
        pass
    
    def join(self, timeout=None):
        pass

    def update_data(self, source, message, category="INFO"):
        queue_message(f"{category}: {message}")
    
    def update_streaming_data(self, value):
        pass

    def set_tars_status(self, status):
        pass

    def deactivate_screensaver(self):
        pass

    def save_memory(self):
        pass
    
    def think(self):
        pass
    
    def set_tars_status(self, status):
        pass

    def silence(self, frames=0):
        pass

    def show_overlay_image(self, image_path, duration=8):
        pass


# === Callback Setup ===
def pause_ui_and_stt():
    if ui_manager:
        ui_manager.pause()
    if stt_manager:
        stt_manager.pause()


def resume_ui_and_stt():
    if ui_manager:
        ui_manager.resume()
    if stt_manager:
        stt_manager.resume()


module_servoctl.set_movement_callbacks(
    on_start=pause_ui_and_stt,
    on_end=resume_ui_and_stt
)


# === Core State → UI Bridge ===
def _sync_state_to_ui(old_state, new_state):
    """Update UI whenever core application state changes."""
    if ui_manager:
        ui_manager.set_tars_status(new_state.value)

on_state_change(_sync_state_to_ui)


# === Logging Configuration ===
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger('bm25s').setLevel(logging.WARNING)


# === Command Line Arguments ===
show_ui = True
debug_mode = False
for arg in sys.argv[1:]:
    if "=" in arg:
        key, value = arg.split("=", 1)
        if key == "show_ui":
            show_ui = value.lower() in ["1", "true", "yes", "on"]
        elif key == "speed":
            import modules.module_speed as _speed
            _speed.enabled = value.lower() in ["1", "true", "yes", "on"]
            if _speed.enabled:
                queue_message("LOAD: Speed profiling enabled")
        elif key == "debug":
            if value.lower() in ["1", "true", "yes", "on"]:
                debug_mode = True
                CONFIG['debug_mode'] = True
                logging.basicConfig(level=logging.DEBUG, force=True)
                # Suppress noisy library debug spam
                logging.getLogger('picamera2').setLevel(logging.WARNING)
                logging.getLogger('libcamera').setLevel(logging.WARNING)
                logging.getLogger('piper_phonemize').setLevel(logging.WARNING)
                logging.getLogger('piper').setLevel(logging.INFO)
                logging.getLogger('urllib3').setLevel(logging.WARNING)
                logging.getLogger('huggingface_hub').setLevel(logging.WARNING)
                logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
                logging.getLogger('flashrank').setLevel(logging.WARNING)
                # Suppress web search / HTTP library spam
                logging.getLogger('rustls').setLevel(logging.WARNING)
                logging.getLogger('h2').setLevel(logging.WARNING)
                logging.getLogger('hyper_util').setLevel(logging.WARNING)
                logging.getLogger('reqwest').setLevel(logging.WARNING)
                logging.getLogger('primp').setLevel(logging.WARNING)
                logging.getLogger('cookie_store').setLevel(logging.WARNING)
                logging.getLogger('asyncio').setLevel(logging.WARNING)
                queue_message("LOAD: Debug mode enabled")


# === Helper Functions ===
def init_app():
    """Performs initial setup for the application."""
    queue_message(f"LOAD: Script running from: {BASE_DIR}")
    
    if CONFIG['TTS']['ttsoption'] == 'xttsv2':
        update_tts_settings(CONFIG['TTS']['ttsurl'])





# === Main Application Logic ===
if __name__ == "__main__":
    init_app()

    # === Heartbeat (central scheduler for timed tasks) ===
    try:
        import modules.module_heartbeat
        queue_message("LOAD: Heartbeat module ready")
    except Exception as e:
        queue_message(f"WARNING: Heartbeat module not available: {e}")

    # === Skills System (auto-discover tool plugins) ===
    initialize_skills()

    # Shutdown event
    shutdown_event = threading.Event()

    # Battery module (only if enabled in config)
    if CONFIG['BATTERY'].get('battery_enabled', False):
        battery = BatteryModule()
        battery.start()
    else:
        battery = None

    # CPU temperature (lightweight)
    cpu_temp = CPUTempModule()
    temp = cpu_temp.get_temperature()
    queue_message(f"INFO: CPU Temperature: {temp:.1f}°C")

    # === Initialize UI Manager ===
    if UI_AVAILABLE and show_ui and CONFIG["UI"]["UI_enabled"]:
        ui_manager = UIManager(
            shutdown_event=shutdown_event,
            battery_module=battery,
            cpu_temp_module=cpu_temp
        )
        ui_manager.start()
        queue_message(f"LOAD: {'Lite' if _use_lite_ui else 'Full'} UI manager started")
        set_tars_state(TarsState.BOOTING)

    # === ChatUI Thread (starts early so webui is available during model loading) ===
    if CONFIG['ACCESS']['webui_enabled'] and CHATUI_AVAILABLE:
        chatui_port = CONFIG['ACCESS'].get('webui_port', 80)
        queue_message(f"LOAD: ChatUI starting on port {chatui_port}...")
        flask_thread = threading.Thread(
            target=modules.module_chatui.start_flask_app,
            kwargs={'port': chatui_port},
            daemon=True
        )
        flask_thread.start()
    # === Ensure UI Manager is initialized ===
    if ui_manager is None:
        ui_manager = UIManagerStub(
            shutdown_event=shutdown_event,
            battery_module=battery,
            cpu_temp_module=cpu_temp
        )
        if CONFIG["UI"]["UI_enabled"]:
            queue_message("LOAD: UI disabled for this device")
        else:
            queue_message("LOAD: UI disabled in config")

    ui_manager.update_data("System", "Initializing application...", "LOAD")

    # === Character and Memory Managers ===
    char_manager = CharacterManager(config=CONFIG)
    memory_manager = MemoryManager(
        config=CONFIG,
        char_name=char_manager.char_name,
        char_greeting=char_manager.char_greeting,
        ui_manager=ui_manager
    )

    # === STT Manager ===
    stt_manager = STTManager(
        config=CONFIG,
        shutdown_event=shutdown_event,
        ui_manager=ui_manager
    )
    if debug_mode:
        stt_manager.DEBUG = True
    stt_manager.set_wake_word_callback(wake_word_callback)
    stt_manager.set_utterance_callback(utterance_callback)
    stt_manager.set_post_utterance_callback(post_utterance_callback)
    stt_manager.set_preemptive_llm_callback(process_completion)

    # === Speaker ID (optional) ===
    if CONFIG['STT'].get('speaker_id_enabled', 'False').lower() == 'true':
        try:
            from modules.module_speaker_id import SpeakerIDManager
            speaker_id_manager = SpeakerIDManager(config=CONFIG)
            speaker_id_manager.start()
            queue_message("LOAD: Speaker ID module enabled")
        except Exception as e:
            queue_message(f"WARNING: Speaker ID module not available: {e}")

    # === Identity Coordinator (fuses speaker ID + face recognition) ===
    try:
        from modules.module_identity import IdentityManager
        sid = None
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
        except Exception:
            pass
        IdentityManager(speaker_id_manager=sid, ui_manager=ui_manager)
        queue_message("LOAD: Identity coordinator enabled")
    except Exception as e:
        queue_message(f"WARNING: Identity coordinator not available: {e}")

    # === Initialize Managers ===
    initialize_managers(
        memory_manager,
        char_manager,
        stt_manager,
        ui_manager,
        shutdown_event,
        battery
    )
    initialize_manager_llm(memory_manager, char_manager)

    # === Bluetooth Controller Thread ===
    bt_controller_thread = None
    if CONFIG['CONTROLS']['enabled'] and BT_AVAILABLE:
        bt_controller_thread = threading.Thread(
            target=start_bt_controller_thread,
            name="BTControllerThread",
            daemon=True
        )
        bt_controller_thread.start()

    # === Vision Initialization (non-blocking) ===
    if VISION_AVAILABLE and CONFIG['VISION'].get('vision_processor', 'blip') == 'blip':
        threading.Thread(target=initialize_blip, name="BlipInitThread", daemon=True).start()

    # === Servo Initialization ===
    startup_initialization()

    # === Main Loop ===
    try:
        queue_message(f"LOAD: TARS-AI OS: {VERSION} running on {RASPBERRY_VERSION.upper()}")
        ui_manager.update_data("System", f"TARS-AI OS: {VERSION} running", "SYSTEM")

        register_stt_manager(stt_manager)
        stt_manager.start()
        set_tars_state(TarsState.STANDBY)

        while not shutdown_event.is_set():
            time.sleep(0.1)

    except KeyboardInterrupt:
        ui_manager.update_data("System", "Shutting down...", "SYSTEM")
        queue_message("INFO: Stopping all threads...")
        shutdown_event.set()

    finally:
        # Flush all deferred writes to disk before shutdown
        try:
            from modules.module_dashboard_data import flush_log
            flush_log()
        except Exception:
            pass
        try:
            memory_manager.flush()
        except Exception:
            pass
        stt_manager.stop()
        # Stop speaker ID if running
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
            if sid is not None:
                sid.stop()
        except Exception:
            pass
        if battery is not None:
            battery.stop()
        if bt_controller_thread:
            bt_controller_thread.join(timeout=2)
        queue_message("INFO: Shutdown complete.")
        os._exit(0)