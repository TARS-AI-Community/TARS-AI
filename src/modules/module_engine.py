"""
module_engine.py

Core module for TARS-AI responsible for:
- Executing tool-specific functions like web searches, vision analysis, and volume control.
"""

import threading

from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

search_google = None
search_google_news = None
try:
    from modules.module_websearch import search_google, search_google_news
except ImportError:
    pass

describe_camera_view = None
try:
    from modules.module_vision import describe_camera_view
except ImportError:
    pass

generate_image = None
try:
    from modules.module_stablediffusion import generate_image
except ImportError:
    pass

send_prompt_to_homeassistant = None
try:
    from modules.module_homeassistant import send_prompt_to_homeassistant
except ImportError:
    pass

generate_tts_audio = None
try:
    from modules.module_tts import generate_tts_audio
except ImportError:
    pass

walk_forward = None
walk_backward = None
turn_right_slow = None
turn_left_slow = None
try:
    from modules.module_servoctl import walk_forward, walk_backward, turn_right_slow, turn_left_slow, step_forward
except ImportError:
    pass

def execute_movement(movements):
    """
    Executes a sequence of movements in a separate thread.
    'movements' should be a list like ["forward", "backward", "left", "right"].
    
    Movement mapping:
    - "forward" -> walk_forward()
    - "backward" -> walk_backward()
    - "left" -> turn_left_slow()
    - "right" -> turn_right_slow()
    """
    def movement_task():
            
        action_map = {
            "forward": step_forward,
            "backward": walk_backward,
            "left": turn_left_slow,
            "right": turn_right_slow
        }

        try:
            for i, move in enumerate(movements, start=1):
                action_function = action_map.get(move)
                if callable(action_function):
                    queue_message(f"[INFO] Executing movement {i}/{len(movements)}: {move}")
                    action_function()
                else:
                    queue_message(f"[ERROR] Movement '{move}' not found in action_map.")
        except Exception as e:
            queue_message(f"[ERROR] Unexpected error while executing movements: {e}")
        finally:
            queue_message(f"[DEBUG] Thread completed for movements: {movements}")

    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return thread


def call_function(module_name, *args, **kwargs):
    """
    Legacy function caller for FUNCTION_REGISTRY.
    May be used by other parts of the application.
    """
    if module_name not in FUNCTION_REGISTRY:
        return "Not a Function"
    func = FUNCTION_REGISTRY[module_name]
    if func is None:
        return f"{module_name} is not available on this device."
    try:
        if func.__code__.co_argcount == 0:
            return func()
        else:
            return func(*args, **kwargs)
    except Exception as e:
        queue_message(f"[DEBUG] Error while executing {module_name}: {e}")

 
def launch_retropie():
    """Launch RetroPie/EmulationStation."""
    import subprocess
    import os
    script = os.path.expanduser("~/TARS-AI/launch_retropie.sh")
    es_bin = "/opt/retropie/supplementary/emulationstation/emulationstation"
    if os.path.isfile(script) and os.access(script, os.X_OK):
        subprocess.Popen([script])
        return "RetroPie launched."
    elif os.path.isfile(es_bin):
        subprocess.Popen([es_bin])
        return "EmulationStation launched."
    else:
        return "RetroPie is not installed."


FUNCTION_REGISTRY = {
    "Weather": search_google,
    "News": search_google_news,
    "Vision": describe_camera_view,
    "Search": search_google,
    "SDmodule-Generate": generate_image,
    "Home_Assistant": send_prompt_to_homeassistant,
    "RetroPie": launch_retropie
}