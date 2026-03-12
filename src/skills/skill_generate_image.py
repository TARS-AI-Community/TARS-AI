"""Skill: generate_image — Generate images via DALL-E, Stable Diffusion, or ComfyUI."""

import threading

SKILL = {
    "name": "generate_image",
    "prompt": """generate_image
    Triggers: Use when the user asks you to CREATE, GENERATE, DRAW, or MAKE an image/picture/photo/artwork.
      * "generate a photo of", "draw me a", "create an image of", "make a picture of"
      * "generate artwork", "paint me", "create a portrait"
    Do NOT use for viewing/seeing (use capture_camera_view instead)
    Parameters: {{"prompt": "detailed description of the image to generate"}}
    Example: {{"function": "generate_image", "parameters": {{"prompt": "a cute puppy playing in a sunny meadow"}}}}""",
    "examples": [
        """Example - Image generation (NOT adjust_persona):
User: "Can you generate a photo of a puppy?"
Response: {{"question": "Can you generate a photo of a puppy?", "reply": "On it \u2014 generating your image now.", "function_calls": [{{"function": "generate_image", "parameters": {{"prompt": "a cute puppy playing in a sunny meadow, photorealistic"}}}}], "new_memories": []}}""",
        """Example - Image generation (NOT adjust_persona, even with "make"):
User: "Make me a picture of a sunset over the ocean"
Response: {{"question": "Make me a picture of a sunset over the ocean", "reply": "On it \u2014 generating your image now.", "function_calls": [{{"function": "generate_image", "parameters": {{"prompt": "a beautiful sunset over the ocean, golden hour, photorealistic"}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Generate an image. Returns reply text."""
    from modules.module_stablediffusion import generate_image
    from modules.module_messageQue import queue_message

    prompt = parameters.get("prompt", "")
    if not prompt:
        return "No image description provided."

    queue_message(f"Generating image: {prompt}")
    source = context.get("source", "voice")

    _callback = None
    if source == "webui":
        def _on_image_ready(image_bytes):
            try:
                queue_message(f"[SD] Image ready ({len(image_bytes)} bytes) — emitting to WebUI")
                import base64 as _b64
                b64 = _b64.b64encode(image_bytes).decode('utf-8')
                img_html = f'<img style="max-width:100%;border-radius:8px;" src="data:image/png;base64,{b64}">'
                from modules.module_chatui import socketio
                socketio.emit('bot_message', {'message': img_html})
                queue_message("[SD] WebUI image emit sent")
            except Exception as _e:
                queue_message(f"[SD] WebUI image emit failed: {_e}")
        _callback = _on_image_ready

    def _generate_bg():
        queue_message("[SD] Background generation thread started")
        try:
            result = generate_image(prompt, on_image_ready=_callback)
            queue_message(f"[SD] Background generation done: {result}")
        except Exception as _e:
            queue_message(f"[SD] Background image generation failed: {_e}")

    if source == "webui":
        try:
            from modules.module_chatui import socketio as _sio
            _sio.start_background_task(_generate_bg)
        except Exception:
            threading.Thread(target=_generate_bg, daemon=True).start()
    else:
        threading.Thread(target=_generate_bg, daemon=True).start()

    queue_message("[SD] Started image generation thread")
    return "On it — generating your image now."
