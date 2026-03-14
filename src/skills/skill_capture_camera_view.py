"""Skill: capture_camera_view — Analyze what the camera sees."""

import threading

SKILL = {
    "name": "capture_camera_view",
    "followup": True,
    "description": "Capture and analyze what the camera sees",
    "prompt": """capture_camera_view
   Triggers: MUST USE when user asks ANY question about vision/seeing:
     * "what do you see", "look at", "what's visible", "describe surroundings"
     * "what's in front", "what's around", "look around", "check visually"
     * "what's that", "can you see", "describe view"
     * ANY question asking about current visual state
   You HAVE a camera and CAN see - always use this function for vision queries
   CRITICAL: When you use capture_camera_view, your "reply" MUST be a short placeholder like "Let me take a look" or "Checking now." Do NOT describe or guess what you see — you haven't looked yet. The camera result will be delivered separately.
   Parameters: {{"query": "string describing what to analyze in the image"}}
   Example: {{"function": "capture_camera_view", "parameters": {{"query": "describe what you see"}}}}""",
    "examples": [
        """Example - Camera function:
User: "What do you see?"
Response: {{"question": "What do you see?", "reply": "Let me take a look.", "function_calls": [{{"function": "capture_camera_view", "parameters": {{"query": "describe what you see"}}}}], "new_memories": []}}""",
        """Example - Camera function (implicit):
User: "What's in front of you?"
Response: {{"question": "What's in front of you?", "reply": "Checking now.", "function_calls": [{{"function": "capture_camera_view", "parameters": {{"query": "describe what is in front"}}}}], "new_memories": []}}""",
        """Example - capture_camera_view vs take_photo (KNOW THE DIFFERENCE):
User: "Take a picture" -> take_photo (saves a file)
User: "What do you see?" -> capture_camera_view (analyzes the view)
User: "Snap a photo of this" -> take_photo
User: "Look at this" -> capture_camera_view""",
    ],
}

_vision_in_progress = threading.local()


def execute(parameters, context):
    """Capture and analyze camera view. Returns reply text."""
    from modules.module_messageQue import queue_message
    from modules.module_config import load_config

    # Skip if user already provided an image
    if context.get("has_image"):
        queue_message("INFO: Skipping camera capture — user already provided an image")
        return None

    if getattr(_vision_in_progress, 'active', False):
        queue_message("WARN: Skipping recursive capture_camera_view call")
        return None

    try:
        from modules.module_vision import process_camera_image
    except ImportError:
        return "Vision is not available on this device."

    config = load_config()
    debug = config.get('debug_mode', False)
    query = parameters.get("query", context.get("user_input", ""))
    vision_processor = config.get('VISION', {}).get('vision_processor', 'blip')

    # Pull detection context from UI if available
    detection_context = ""
    try:
        from modules.module_main import ui_manager
        if ui_manager and hasattr(ui_manager, 'detection_manager'):
            detection_context = ui_manager.detection_manager.get_detection_summary() or ""
    except Exception:
        pass

    _vision_in_progress.active = True
    try:
        # Single-pass for multimodal backends
        if vision_processor in ("llm", "openai"):
            if debug:
                queue_message("DEBUG VISION: Single-pass (camera image sent directly to LLM)")
            from modules.module_vision import capture_camera_base64
            from modules.module_llm import get_completion
            b64, capture_err = capture_camera_base64()
            if capture_err:
                return capture_err
            try:
                prompt = query or "Describe what you see."
                if detection_context:
                    prompt = f"{detection_context}\n\n{prompt}"
                reply = get_completion(prompt, image_b64=b64)
                return reply if reply else "I tried to look but couldn't process the image."
            except Exception as e:
                queue_message(f"ERROR: Single-pass vision failed: {e}")
                return "I tried to look but encountered an error."
        else:
            # Two-pass for caption-only backends (blip, server_hosted)
            if debug:
                queue_message(f"DEBUG VISION: Two-pass (caption via {vision_processor}, then LLM)")
            description = process_camera_image(query, detection_context=detection_context or None)
            if description and not description.startswith("Error:"):
                vision_prompt = f"*You looked through your camera and saw: {description}*"
                if detection_context:
                    vision_prompt += f" {detection_context}"
                if query:
                    vision_prompt += f" The user asked: {query}"
                try:
                    from modules.module_llm import get_completion
                    reply = get_completion(vision_prompt)
                    return reply if reply else description
                except Exception as e:
                    queue_message(f"WARN: Vision follow-up LLM call failed: {e}")
                    return description
            return "I tried to look but couldn't process the image."
    finally:
        _vision_in_progress.active = False
