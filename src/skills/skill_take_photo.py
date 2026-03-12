"""Skill: take_photo — Take and save a photo from the camera."""

import os
import threading

SKILL = {
    "name": "take_photo",
    "prompt": """take_photo
   Triggers: Use when the user wants to take/snap a photo or picture (to KEEP, not to analyze)
     * "take a photo", "snap a picture", "take my picture", "photo of me"
     * "take a pic", "photograph this", "capture a photo"
   This is DIFFERENT from capture_camera_view: take_photo SAVES a photo file, capture_camera_view ANALYZES what the camera sees.
   If the user says "take a photo" → use take_photo. If the user says "what do you see" → use capture_camera_view.
   Reply with something fun like "Say cheese! 3, 2, 1!" and call take_photo immediately.
   Parameters: {{}} (no parameters needed)
   Example: {{"function": "take_photo", "parameters": {{}}}}""",
    "examples": [
        """Example - Take photo (single turn - call function immediately):
User: "Take a photo of me"
Response: {{"question": "Take a photo of me", "reply": "Say cheese! 3, 2, 1!", "function_calls": [{{"function": "take_photo", "parameters": {{}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Capture camera image and save to file. Returns reply text."""
    import base64 as _b64
    from datetime import datetime
    from modules.module_vision import capture_camera_base64
    from modules.module_messageQue import queue_message

    b64, capture_err = capture_camera_base64()
    if capture_err:
        return "I tried to take a photo but the camera isn't working."

    photos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vision", "photos")
    os.makedirs(photos_dir, exist_ok=True)
    filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    filepath = os.path.join(photos_dir, filename)
    with open(filepath, "wb") as f:
        f.write(_b64.b64decode(b64))
    queue_message(f"Photo saved: {filepath}")

    # Display on RPi screen
    try:
        from modules.module_stablediffusion import display_image_fullscreen
        threading.Thread(target=display_image_fullscreen, args=(filepath,)).start()
    except Exception as e:
        queue_message(f"WARN: Could not display photo: {e}")

    return f"Photo saved! Got it as {filename}."
