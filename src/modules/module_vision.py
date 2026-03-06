import traceback
import base64
import os
from datetime import datetime
from pathlib import Path
from io import BytesIO
import requests

from modules.module_config import load_config, get_api_key
from modules.module_messageQue import queue_message

CONFIG = load_config()

# Conditional imports for heavy dependencies
Image = None
BlipProcessor = None
BlipForConditionalGeneration = None
torch = None
openai = None
CameraModule = None

try:
    from PIL import Image as _Image
    Image = _Image
except ImportError:
    pass

try:
    from transformers import BlipProcessor as _BlipProcessor, BlipForConditionalGeneration as _BlipModel
    BlipProcessor = _BlipProcessor
    BlipForConditionalGeneration = _BlipModel
except ImportError:
    pass

try:
    import torch as _torch
    torch = _torch
except ImportError:
    pass

try:
    import openai as _openai
    openai = _openai
except ImportError:
    pass

try:
    from UI.module_ui_camera import CameraModule as _CameraModule
    CameraModule = _CameraModule
except ImportError:
    pass

# Only set up device/model if torch is available
DEVICE = None
if torch:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

MODEL_NAME = "Salesforce/blip-image-captioning-base"

CACHE_DIR = Path(__file__).resolve().parent.parent / "vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PROCESSOR = None
MODEL = None
CAMERA = None

# Set up OpenAI API key if available
if openai:
    try:
        openai.api_key = CONFIG['TTS']['openai_api_key']
    except (KeyError, TypeError):
        try:
            openai.api_key = CONFIG['VISION']['openai_api_key']
        except (KeyError, TypeError):
            pass

def initialize_camera():
    """Initialize camera once and store the reference globally."""
    if not CONFIG['VISION']['enabled']:
        return
    
    if CameraModule is None:
        queue_message("WARNING: Camera module not available")
        return
        
    global CAMERA
    if CAMERA is None:
        CAMERA = CameraModule(1920, 1080)
        queue_message(f"INFO: Camera initialized.")

def initialize_blip():
    """Initialize BLIP model and processor for detailed captions."""
    if not CONFIG['VISION']['enabled']:
        return
    
    if BlipProcessor is None or BlipForConditionalGeneration is None or torch is None:
        queue_message("WARNING: BLIP dependencies not available (transformers, torch)")
        return
        
    global PROCESSOR, MODEL
    if not PROCESSOR or not MODEL:
        queue_message(f"INFO: Initializing BLIP model...")

        PROCESSOR = BlipProcessor.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR), use_fast=False)
        MODEL = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR)).to(DEVICE)
        MODEL = torch.quantization.quantize_dynamic(MODEL, {torch.nn.Linear}, dtype=torch.qint8)

        queue_message(f"INFO: BLIP model initialized.")

def capture_image() -> str:
    """Capture an image from the camera instance and return the saved image path."""
    if CameraModule is None:
        raise RuntimeError("Camera module not available")
        
    try:
        camera = CameraModule(1920, 1080)
        image_path = camera.capture_single_image()
        print(f"Image saved: {image_path}")
        return image_path

    except Exception as e:
        queue_message(f"ERROR: {e}")
        raise RuntimeError(f"Error capturing image: {e}")

def describe_camera_view() -> str:
    """Capture an image and process it for captioning."""    
    if Image is None:
        return "Error: PIL/Pillow not available"
        
    try:
        image_path = capture_image()
        print(image_path)
        if CONFIG['VISION']['server_hosted']:
            return send_image_to_server(image_path)
        else:
            if PROCESSOR is None or MODEL is None:
                return "Error: BLIP model not initialized"
            image = Image.open(image_path)
            inputs = PROCESSOR(image, return_tensors="pt").to(DEVICE)
            outputs = MODEL.generate(**inputs, max_new_tokens=50, num_beams=2)
            output = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
            print(output)
            return output
        
    except Exception as e:
        character_name = CONFIG['CHAR']['character_name']
        queue_message(f"{character_name} is unable to see right now")
        return f"Error: {e}"
    

def describe_camera_view_openai(user_prompt) -> str:
    """
    Capture an image and generate a description using OpenAI vision model.
    Returns:
        str: Description of what's in the image
    """
    if openai is None:
        return "Error: OpenAI module not available"
        
    try:
        image_path = capture_image()
        if not Path(image_path).exists():
            return "Error: captured image not found."
        
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=150
        )
        description = response.choices[0].message.content
        queue_message(f"Vision: {description}")
        return description

    except Exception as e:
        queue_message(f"ERROR: Vision failed - {e}")
        return f"I tried to look but encountered an error."


def send_image_to_server(image_path: str) -> str:
    """
    Send an image to the server for captioning and return the generated caption.

    Parameters:
    - image_path (str): Path of the saved image.

    Returns:
    - str: Generated caption from the server.
    """
    try:
        with open(image_path, "rb") as img_file:
            files = {'image': ('image.jpg', img_file, 'image/jpeg')}

            response = requests.post(f"{CONFIG['VISION']['base_url']}/caption", files=files)

            if response.status_code == 200:
                return response.json().get("caption", "No caption returned")
            else:
                error_message = response.json().get('error', 'Unknown error')
                raise RuntimeError(f"Server error ({response.status_code}): {error_message}")
    except Exception as e:
        queue_message(f"[{datetime.now()}] ERROR: Failed to send image to server: {e}")
        raise

def get_image_caption_from_base64(base64_str):
    """
    Generate a caption for an image encoded in base64.

    Parameters:
    - base64_str (str): Base64-encoded string of the image.

    Returns:
    - str: Generated caption.
    """
    if Image is None or PROCESSOR is None or MODEL is None:
        raise RuntimeError("Vision dependencies not available")
        
    try:
        img_bytes = base64.b64decode(base64_str)
        raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')

        inputs = PROCESSOR(raw_image, return_tensors="pt").to(DEVICE)
        outputs = MODEL.generate(**inputs, max_new_tokens=100)

        caption = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
        return caption
    except Exception as e:
        raise RuntimeError(f"Error generating caption from base64: {e}")


def describe_image_openai(base64_image, prompt="Describe this image in detail."):
    """Send a base64 image to OpenAI GPT-4o-mini vision API."""
    if openai is None:
        return "Error: OpenAI module not available"

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return "Error: OPENAI_API_KEY not set"

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 150
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        description = response.json()['choices'][0]['message']['content']
        queue_message(f"Vision: {description}")
        return description
    except Exception as e:
        queue_message(f"ERROR: OpenAI vision failed - {e}")
        return f"Error: {e}"


def describe_image_llm(base64_image, prompt="Describe this image in detail."):
    """Send a base64 image to the configured LLM backend for vision."""
    llm_backend = CONFIG['LLM']['llm_backend']
    api_key = CONFIG['LLM']['api_key']
    base_url = CONFIG['LLM']['base_url']

    if llm_backend == "deepinfra":
        url = f"{base_url}/v1/openai/chat/completions"
        model = CONFIG['LLM']['openai_model']
    elif llm_backend == "grok":
        url = f"{base_url}/v1/chat/completions"
        model = CONFIG['LLM']['grok_model']
    elif llm_backend == "openai":
        url = f"{base_url}/v1/chat/completions"
        model = CONFIG['LLM']['openai_model']
    else:
        url = f"{base_url}/v1/chat/completions"
        model = CONFIG['LLM']['other_model']

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 150
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        description = response.json()['choices'][0]['message']['content']
        queue_message(f"Vision: {description}")
        return description
    except Exception as e:
        queue_message(f"ERROR: LLM vision failed - {e}")
        return f"Error: {e}"


def describe_image_server(base64_image):
    """Send a base64 image to the external vision server for captioning."""
    try:
        img_bytes = base64.b64decode(base64_image)
        files = {'image': ('image.jpg', BytesIO(img_bytes), 'image/jpeg')}
        response = requests.post(f"{CONFIG['VISION']['base_url']}/caption", files=files)
        if response.status_code == 200:
            return response.json().get("caption", "No caption returned")
        else:
            return f"Error: Server returned {response.status_code}"
    except Exception as e:
        queue_message(f"ERROR: Vision server failed - {e}")
        return f"Error: {e}"


def process_image(base64_image, prompt="Describe this image in detail."):
    """Unified vision dispatcher — routes to the configured vision_processor."""
    processor = CONFIG['VISION'].get('vision_processor', 'blip')

    if processor == "blip":
        if PROCESSOR is None or MODEL is None:
            initialize_blip()
        if PROCESSOR is None or MODEL is None:
            return "Error: BLIP model not available"
        return get_image_caption_from_base64(base64_image)

    elif processor == "llm":
        return describe_image_llm(base64_image, prompt)

    elif processor == "openai":
        return describe_image_openai(base64_image, prompt)

    elif processor == "server_hosted":
        return describe_image_server(base64_image)

    else:
        queue_message(f"ERROR: Unknown vision_processor '{processor}'")
        return f"Error: Unknown vision_processor '{processor}'"


def process_camera_image(user_prompt="Describe what you see."):
    """Capture from camera and process with configured vision_processor."""
    try:
        image_path = capture_image()
        if not Path(image_path).exists():
            return "Error: captured image not found."

        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')

        return process_image(base64_image, user_prompt)
    except Exception as e:
        queue_message(f"ERROR: Camera vision failed - {e}")
        return f"I tried to look but encountered an error."


def save_captured_image(image_path: str) -> str:
    """
    Save the captured image to the 'vision/images' directory.

    Parameters:
    - image_path (str): Path of the image to be saved.

    Returns:
    - str: The new saved image path.
    """
    if Image is None:
        queue_message("Error: PIL/Pillow not available")
        return None
        
    try:
        output_dir = Path(__file__).resolve().parent.parent / "vision/images"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_path = output_dir / f"captured_image_{timestamp}.jpg"

        img = Image.open(image_path)
        img.save(new_path, format="JPEG", optimize=True, quality=85)

        return str(new_path)
    except Exception as e:
        queue_message(f"Error saving image: {e}")
        return None