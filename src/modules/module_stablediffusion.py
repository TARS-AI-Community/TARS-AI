import requests
import base64
import json
import os
import random
import tempfile
import time
import pygame
import threading

from modules.module_config import load_config
from modules.module_messageQue import queue_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _deliver_image(image_bytes, on_image_ready, label="SD"):
    """Handle image delivery: callback for web UI, or display on screen."""
    if on_image_ready:
        try:
            on_image_ready(image_bytes)
        except Exception as cb_err:
            queue_message(f"[{label}] image callback error: {cb_err}")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        threading.Thread(target=display_image_fullscreen, args=(tmp_path,)).start()


def _get_sd_config(skill_config=None):
    """Resolve image generation config from skill config."""
    if skill_config and skill_config.get("service"):
        return skill_config
    return {}


def generate_image(prompt, skill_config=None, on_image_ready=None):
    """
    Generate an image based on the provided prompt.

    Parameters:
    - prompt (str): A textual description of the image to be generated.
    - skill_config (dict): Config from the skill's config schema (preferred).
    - on_image_ready (callable): Optional callback(image_bytes) called when the image is available.

    Returns:
    - str: The result of the image generation process.
    """
    sd = _get_sd_config(skill_config)

    if not sd:
        return "Image Tool not configured."

    # Legacy config.ini has 'enabled' field; skill config uses the skill enable/disable toggle
    if 'enabled' in sd and not sd['enabled']:
        return "Image Tool not enabled."

    # Apply prompt prefix/postfix
    prefix = str(sd.get('prompt_prefix', '')).strip()
    postfix = str(sd.get('prompt_postfix', '')).strip()
    if prefix:
        prompt = f"{prefix}, {prompt}"
    if postfix:
        prompt = f"{prompt}, {postfix}"

    service = str(sd.get('service', 'automatic1111'))
    if service == "openai":
        return get_image_from_dalle_v3(prompt, on_image_ready=on_image_ready)
    elif service == "external":
        return get_image_from_external(prompt, sd, on_image_ready=on_image_ready)
    elif service == "automatic1111":
        result = get_image_from_automatic1111(prompt, sd, on_image_ready=on_image_ready)
        if result != "The image has been created and displayed on screen.":
            return _try_openai_fallback(prompt, on_image_ready)
        return result
    elif service == "comfyui":
        result = get_image_from_comfyui(prompt, sd, on_image_ready=on_image_ready)
        if result and result != "The image has been created and displayed on screen.":
            return _try_openai_fallback(prompt, on_image_ready)
        return result

    return "Image Tool not enabled."


def _try_openai_fallback(prompt, on_image_ready):
    """Fall back to OpenAI DALL-E if the LLM backend is openai."""
    try:
        config = load_config()
        llm_backend = config['LLM'].get('llm_backend', '').lower()
        if llm_backend == 'openai':
            queue_message("[SD] Primary image service failed, falling back to OpenAI DALL-E...")
            fallback_result = get_image_from_dalle_v3(prompt, on_image_ready=on_image_ready)
            if fallback_result:
                return fallback_result
    except Exception:
        pass
    return "Image generation failed."


def get_image_from_dalle_v3(prompt, on_image_ready=None):
    from openai import OpenAI
    config = load_config()
    client = OpenAI(api_key=config['LLM']['api_key'])

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_bytes = image_response.content

        _deliver_image(image_bytes, on_image_ready, "DALL-E")
        return "The image has been created and displayed on screen."

    except Exception as e:
        queue_message(f"Error: {e}")
        return None


def get_image_from_automatic1111(sdpromptllm, sd, on_image_ready=None):
    payload = {
        "prompt": sdpromptllm,
        "negative_prompt": str(sd.get('negative_prompt', '')),
        "seed": int(sd.get('seed', -1)),
        "sampler_name": str(sd.get('sampler_name', 'euler')),
        "denoising_strength": float(sd.get('denoising_strength', 0.5)),
        "steps": int(sd.get('steps', 20)),
        "cfg_scale": float(sd.get('cfg_scale', 7)),
        "width": int(sd.get('width', 480)),
        "height": int(sd.get('height', 320)),
        "restore_faces": bool(sd.get('restore_faces', False)),
        "override_settings_restore_afterwards": True,
    }

    url = f'{sd.get("url", "").rstrip("/")}/sdapi/v1/txt2img'

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()

        image_data_base64 = response.json()['images'][0]
        image_bytes = base64.b64decode(image_data_base64)

        _deliver_image(image_bytes, on_image_ready, "A1111")
        return "The image has been created and displayed on screen."

    except requests.exceptions.HTTPError as err:
        queue_message(f"HTTP error occurred: {err}")
    except requests.exceptions.RequestException as e:
        queue_message(f"Error: {e}")

    return "Image generation failed."


def get_image_from_external(prompt, sd, on_image_ready=None):
    """Generate an image via the TARS app-server's /sdapi/v1/txt2img endpoint."""
    url = sd.get('url', '').rstrip('/')
    if not url:
        queue_message("[SD] ERROR: External image generation URL is not set")
        return "Image generation failed — no server URL configured."

    payload = {
        "prompt": prompt,
        "negative_prompt": str(sd.get('negative_prompt', '')),
        "seed": int(sd.get('seed', -1)),
        "sampler_name": str(sd.get('sampler_name', 'euler')),
        "steps": int(sd.get('steps', 20)),
        "cfg_scale": float(sd.get('cfg_scale', 7)),
        "width": int(sd.get('width', 480)),
        "height": int(sd.get('height', 320)),
    }

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get('EXTERNAL_API_KEY', '')
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        queue_message(f"[SD] Sending to external server: {url}/sdapi/v1/txt2img")
        response = requests.post(f"{url}/sdapi/v1/txt2img", json=payload, headers=headers, timeout=120)
        response.raise_for_status()

        image_data_base64 = response.json()['images'][0]
        image_bytes = base64.b64decode(image_data_base64)

        _deliver_image(image_bytes, on_image_ready, "External")
        return "The image has been created and displayed on screen."

    except requests.exceptions.RequestException as e:
        queue_message(f"[SD] External server error: {e}")
        return "Image generation failed."


def get_image_from_comfyui(prompt, sd, on_image_ready=None):
    """Generate an image using ComfyUI API with a workflow JSON template."""
    comfy_url = sd.get('url', '').rstrip('/')
    workflow_path = sd.get('comfyui_workflow', 'Documentation/Comfy_UI_SD.json')

    # Resolve relative paths against project root
    if not os.path.isabs(workflow_path):
        workflow_path = os.path.join(BASE_DIR, workflow_path)

    if not os.path.exists(workflow_path):
        queue_message(f"ComfyUI workflow not found: {workflow_path}")
        return "ComfyUI workflow template not found."

    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        queue_message(f"Failed to load ComfyUI workflow: {e}")
        return "Failed to load ComfyUI workflow template."

    # Inject prompt into positive prompt node (node 3)
    if "3" in workflow and "inputs" in workflow["3"]:
        workflow["3"]["inputs"]["text"] = prompt

    # Randomize seed in sampler node (node 11)
    if "11" in workflow and "inputs" in workflow["11"]:
        if "noise_seed" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["noise_seed"] = random.randint(1, 999999999999999)
        elif "seed" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["seed"] = random.randint(1, 999999999999999)
        if "steps" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["steps"] = int(sd.get('steps', 20))
        if "cfg" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["cfg"] = float(sd.get('cfg_scale', 7))
        if "sampler_name" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["sampler_name"] = str(sd.get('sampler_name', 'euler'))

    # Inject width/height into Empty Latent Image node (scan all nodes)
    img_w = int(sd.get('width', 480))
    img_h = int(sd.get('height', 320))
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage":
            if "inputs" in node:
                node["inputs"]["width"] = img_w
                node["inputs"]["height"] = img_h
            break

    try:
        # Queue the prompt
        resp = requests.post(f"{comfy_url}/prompt", json={"prompt": workflow}, timeout=10)
        if resp.status_code != 200:
            queue_message(f"ComfyUI queue error: {resp.text}")
            return f"ComfyUI error: {resp.text}"

        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            queue_message("ComfyUI returned no prompt_id")
            return "ComfyUI error: no prompt_id returned."

        # Poll for completion
        for _ in range(60):
            time.sleep(1)
            hist_resp = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=10)
            if hist_resp.status_code != 200 or not hist_resp.json():
                continue

            history = hist_resp.json().get(prompt_id)
            if not history:
                continue

            outputs = history.get("outputs", {})
            for node_id, node_output in outputs.items():
                if "images" not in node_output:
                    continue

                img_info = node_output["images"][0]
                fname = img_info.get("filename")
                subfolder = img_info.get("subfolder", "")
                img_type = img_info.get("type", "output")

                img_resp = requests.get(
                    f"{comfy_url}/view",
                    params={"filename": fname, "subfolder": subfolder, "type": img_type},
                    timeout=30
                )
                if img_resp.status_code != 200:
                    queue_message(f"ComfyUI failed to fetch image: {img_resp.status_code}")
                    return "ComfyUI error fetching generated image."

                image_bytes = img_resp.content

                _deliver_image(image_bytes, on_image_ready, "ComfyUI")
                return "The image has been created and displayed on screen."

        queue_message("ComfyUI image generation timed out.")
        return "Image generation timed out."

    except requests.exceptions.RequestException as e:
        queue_message(f"ComfyUI request error: {e}")
        return f"ComfyUI error: {e}"

def display_image_fullscreen(image_path):
    """Display an image for 8 seconds — uses the existing UI overlay if running, otherwise opens a standalone pygame window."""
    try:
        # Try the existing UI manager first (avoids X11 display conflict)
        import sys
        app_module = sys.modules.get('app') or sys.modules.get('__main__')
        ui_mgr = getattr(app_module, 'ui_manager', None) if app_module else None
        if ui_mgr and hasattr(ui_mgr, 'show_overlay_image') and getattr(ui_mgr, 'running', False):
            ui_mgr.show_overlay_image(image_path, duration=8)
            queue_message("[SD] Image displayed via UI overlay")
            return
        else:
            queue_message(f"[SD] UI overlay not available (ui_mgr={ui_mgr}, running={getattr(ui_mgr, 'running', None)})")
    except Exception as e:
        queue_message(f"[SD] UI overlay lookup failed: {e}")

    # Fallback: standalone pygame window (only if no existing display)
    if not pygame.display.get_init() or pygame.display.get_surface() is None:
        try:
            _display_image_fullscreen_inner(image_path)
        except Exception as e:
            queue_message(f"Display error (non-fatal): {e}")
    else:
        queue_message("[SD] Cannot display image: pygame display already active but UI overlay unavailable")


def _display_image_fullscreen_inner(image_path):
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    time.sleep(0.1)

    screen_width, screen_height = screen.get_size()
    pygame_img = pygame.image.load(image_path)
    img_width, img_height = pygame_img.get_width(), pygame_img.get_height()
    scale_factor = min(screen_width / img_width, screen_height / img_height)
    new_width = int(img_width * scale_factor)
    new_height = int(img_height * scale_factor)
    scaled_img = pygame.transform.smoothscale(pygame_img, (new_width, new_height))
    x_pos = (screen_width - new_width) // 2
    y_pos = (screen_height - new_height) // 2

    screen.fill((0, 0, 0))
    screen.blit(scaled_img, (x_pos, y_pos))
    pygame.display.update()

    start_ticks = pygame.time.get_ticks()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        if pygame.time.get_ticks() - start_ticks > 8000:
            running = False
        pygame.display.update()

    pygame.quit()
