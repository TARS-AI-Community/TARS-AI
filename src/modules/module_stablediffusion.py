import requests
import base64
import json
import os
import random
from PIL import Image
import tempfile
import time
import pygame
import threading
from io import BytesIO

from modules.module_config import load_config
from modules.module_messageQue import queue_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load configuration
config = load_config()

def generate_image(prompt, on_image_ready=None):
    """
    Generate an image based on the provided prompt using the configured image generation service.

    Parameters:
    - prompt (str): A textual description of the image to be generated.
    - on_image_ready (callable): Optional callback(image_bytes) called when the image is available.

    Returns:
    - str: The result of the image generation process. If the tool is disabled, returns "Image Tool not enabled."
    """
    result = "Image Tool not enabled"
    if config['STABLE_DIFFUSION']['enabled']:
        if config['STABLE_DIFFUSION']['service'] == "openai":
            result = get_image_from_dalle_v3(prompt)
        if config['STABLE_DIFFUSION']['service'] == "automatic1111":
            result = get_image_from_automatic1111(prompt)
        if config['STABLE_DIFFUSION']['service'] == "comfyui":
            result = get_image_from_comfyui(prompt, on_image_ready=on_image_ready)
    return result

def get_image_from_dalle_v3(prompt):
    # Initialize the OpenAI client
    from openai import OpenAI
    client = OpenAI(api_key=config['LLM']['api_key'])  # Replace with your API key

    try:
        # Generate the image using the updated client method
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,  # Number of images
        )

        # Extract the image URL
        image_url = response.data[0].url

        # Fetch the image data from the URL
        image_response = requests.get(image_url)
        image_response.raise_for_status()

        # Decode the image data into a PIL image
        image = Image.open(BytesIO(image_response.content))

        # Save the image to a temporary file after resizing to 512x512
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_png_file:
            resized_image = image.resize((512, 512))  # Resize the image
            resized_image.save(temp_png_file, format='PNG')  # Save the resized image
            temp_png_file_path = temp_png_file.name

        # Display the image in fullscreen using a thread
        display_thread = threading.Thread(target=display_image_fullscreen, args=(temp_png_file_path,))
        display_thread.start()

        # Return a success message
        return f"Image generated and displayed in fullscreen."

    except Exception as e:
        queue_message(f"Error: {e}")
        return None

def get_image_from_automatic1111(sdpromptllm):
    # Create the payload with the necessary parameters for the API request
    payload = {
        "prompt": sdpromptllm,
        "negative_prompt": config['STABLE_DIFFUSION']['negative_prompt'],
        "seed": int(config['STABLE_DIFFUSION']['seed']),
        "sampler_name": config['STABLE_DIFFUSION']['sampler_name'],
        "denoising_strength": float(config['STABLE_DIFFUSION']['denoising_strength']),
        "steps": int(config['STABLE_DIFFUSION']['steps']),
        "cfg_scale": float(config['STABLE_DIFFUSION']['cfg_scale']),
        "width": int(config['STABLE_DIFFUSION']['width']),
        "height": int(config['STABLE_DIFFUSION']['height']),
        "restore_faces": config.get('STABLE_DIFFUSION', 'restore_faces') == 'True',
        "override_settings_restore_afterwards": True,
    }

    # Correct the URL without the comment
    url = f'{config["STABLE_DIFFUSION"]["url"]}/sdapi/v1/txt2img'

    try:
        # Making a POST request to the API with the payload
        response = requests.post(url, json=payload)
        response.raise_for_status()

        # Assuming the response returns a JSON with an 'images' key containing base64 encoded images
        image_data_base64 = response.json()['images'][0]  # Taking the first image as a Base64 string
        
        # Decode the Base64 data to get the image
        image_data = base64.b64decode(image_data_base64)

        # Save the binary image data to a temporary PNG file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_png_file:
            temp_png_file.write(image_data)
            temp_png_file_path = temp_png_file.name

        # Start a new thread to display the image
        display_thread = threading.Thread(target=display_image_fullscreen, args=(temp_png_file_path,))
        display_thread.start()

        # Continue with the rest of the program (non-blocking)
        return f"The image has been created and displayed on screen."

    except requests.exceptions.HTTPError as err:
        queue_message(f"HTTP error occurred: {err}")
    except requests.exceptions.RequestException as e:
        queue_message(f"Error: {e}")

    return f"Image generated and displayed in fullscreen."

def get_image_from_comfyui(prompt, on_image_ready=None):
    """Generate an image using ComfyUI API with a workflow JSON template."""
    comfy_url = config['STABLE_DIFFUSION']['url'].rstrip('/')
    workflow_path = config['STABLE_DIFFUSION'].get('comfyui_workflow', 'Documentation/Comfy_UI_SD.json')

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
            workflow["11"]["inputs"]["steps"] = int(config['STABLE_DIFFUSION']['steps'])
        if "cfg" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["cfg"] = float(config['STABLE_DIFFUSION']['cfg_scale'])
        if "sampler_name" in workflow["11"]["inputs"]:
            workflow["11"]["inputs"]["sampler_name"] = config['STABLE_DIFFUSION']['sampler_name']

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

                if on_image_ready:
                    # WebUI request — send to browser only
                    try:
                        on_image_ready(image_bytes)
                    except Exception as cb_err:
                        queue_message(f"ComfyUI image callback error: {cb_err}")
                else:
                    # Voice request — display on physical screen
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                        tmp.write(image_bytes)
                        tmp_path = tmp.name
                    display_thread = threading.Thread(target=display_image_fullscreen, args=(tmp_path,))
                    display_thread.start()

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
