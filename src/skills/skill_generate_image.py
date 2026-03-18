"""Skill: generate_image — Generate images via DALL-E, Stable Diffusion, or ComfyUI."""

import threading

SKILL = {
    "name": "generate_image",
    "description": "Generate images from text descriptions",
    "config": {
        "service": {
            "type": "select",
            "default": "automatic1111",
            "options": ["automatic1111", "comfyui", "openai", "external"],
            "description": "Image generation backend to use",
        },
        "url": {
            "type": "text",
            "default": "http://192.168.1.100:7860",
            "description": "Image generation server URL (A1111 :7860, ComfyUI :8188)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "prompt_prefix": {
            "type": "text",
            "default": "in the style of midjourney",
            "description": "Text added before every image prompt (sets style)",
        },
        "prompt_postfix": {
            "type": "text",
            "default": "clearly defined,high def,(detailed scene and background),key visual,vibrant,highly detailed",
            "description": "Text added after every image prompt (quality terms)",
        },
        "negative_prompt": {
            "type": "text",
            "default": "deformed,black and white,disfigured,low contrast,extra limbs,bad anatomy,bad hands",
            "description": "Terms to avoid in generated images",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "seed": {
            "type": "number",
            "default": -1,
            "description": "Random seed (-1 = random, fixed = reproducible)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "steps": {
            "type": "number",
            "default": 20,
            "min": 1,
            "max": 100,
            "description": "Diffusion steps (20-30 = good balance)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "cfg_scale": {
            "type": "number",
            "default": 7,
            "min": 1,
            "max": 30,
            "description": "Prompt adherence (1-5 loose, 7-9 balanced, 10+ strict)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "sampler_name": {
            "type": "text",
            "default": "euler",
            "description": "Sampler algorithm (euler_ancestral, dpmpp_2m, etc.)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "denoising_strength": {
            "type": "number",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "description": "Noise reduction strength (img2img: how much image changes)",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui"]},
        },
        "width": {
            "type": "number",
            "default": 480,
            "min": 64,
            "max": 2048,
            "description": "Output image width in pixels",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "height": {
            "type": "number",
            "default": 320,
            "min": 64,
            "max": 2048,
            "description": "Output image height in pixels",
            "depends_on": {"field": "service", "values": ["automatic1111", "comfyui", "external"]},
        },
        "restore_faces": {
            "type": "bool",
            "default": False,
            "description": "Enable face restoration post-processing",
            "depends_on": {"field": "service", "values": ["automatic1111"]},
        },
        "comfyui_workflow": {
            "type": "text",
            "default": "Documentation/Comfy_UI_SD.json",
            "description": "ComfyUI text-to-image workflow JSON path",
            "depends_on": {"field": "service", "values": ["comfyui"]},
        },
        "comfyui_img2img_workflow": {
            "type": "text",
            "default": "Documentation/Comfy_UI_IMG2IMG.json",
            "description": "ComfyUI image-to-image workflow JSON path",
            "depends_on": {"field": "service", "values": ["comfyui"]},
        },
    },
    "required_params": ["prompt"],
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
Response: {{"reply": "On it \u2014 generating your image now.", "function_calls": [{{"function": "generate_image", "parameters": {{"prompt": "a cute puppy playing in a sunny meadow, photorealistic"}}}}], "new_memories": []}}""",
        """Example - Image generation (NOT adjust_persona, even with "make"):
User: "Make me a picture of a sunset over the ocean"
Response: {{"reply": "On it \u2014 generating your image now.", "function_calls": [{{"function": "generate_image", "parameters": {{"prompt": "a beautiful sunset over the ocean, golden hour, photorealistic"}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Generate an image. Returns reply text."""
    from modules.module_stablediffusion import generate_image
    from modules.module_messageQue import queue_message

    prompt = parameters.get("prompt", "")
    if not prompt:
        return "No image description provided."

    skill_config = context.get("skill_config", {})
    queue_message(f"Generating image: {prompt}")
    source = context.get("source", "voice")

    def _on_image_ready(image_bytes):
        try:
            queue_message(f"[SD] Image ready ({len(image_bytes)} bytes) — routing to active device")
            from modules.module_router import send_image as _send, get_active_route
            queue_message(f"[SD] Active route: {get_active_route()}")
            _send(image_bytes, "Here's your generated image!")
            queue_message(f"[SD] Image routed successfully")
        except Exception as _e:
            import traceback
            queue_message(f"[SD] Image delivery failed: {_e}")
            traceback.print_exc()

    def _generate_bg():
        queue_message("[SD] Background generation thread started")
        try:
            result = generate_image(prompt, skill_config=skill_config, on_image_ready=_on_image_ready)
            queue_message(f"[SD] Background generation done: {result}")
            if result and "failed" in result.lower():
                from modules.module_router import send as _send
                _send("Sorry, image generation failed.")
        except Exception as _e:
            queue_message(f"[SD] Background image generation failed: {_e}")
            from modules.module_router import send as _send
            _send("Sorry, image generation failed.")

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
