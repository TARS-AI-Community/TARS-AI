import traceback
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from io import BytesIO
import requests
import torch
import base64
from datetime import datetime
from pathlib import Path

# === Custom Modules ===
from modules.module_config import load_config
from modules.module_messageQue import queue_message
from UI.module_ui_camera import CameraModule  # Import once, no reinitialization in function calls

# === Constants and Globals ===
CONFIG = load_config()

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_NAME = "Salesforce/blip-image-captioning-base"

# Cache directory for model
CACHE_DIR = Path(__file__).resolve().parent.parent / "vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Globals for processor, model, and camera instance
PROCESSOR = None
MODEL = None
CAMERA = None  # Prevents reinitialization

def initialize_camera():
    """Initialize camera once and store the reference globally."""
    if not CONFIG['VISION']['enabled']:
        global CAMERA
        if CAMERA is None:  # Ensure it's only created once
            CAMERA = CameraModule(1920, 1080)
            queue_message(f"INFO: Camera initialized.")

def initialize_blip():
    """Initialize BLIP model and processor for detailed captions."""
    if not CONFIG['VISION']['enabled']:
        global PROCESSOR, MODEL
        if not PROCESSOR or not MODEL:
            queue_message(f"INFO: Initializing BLIP model...")

            PROCESSOR = BlipProcessor.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR))
            MODEL = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR)).to(DEVICE)
            MODEL = torch.quantization.quantize_dynamic(MODEL, {torch.nn.Linear}, dtype=torch.qint8)

            queue_message(f"INFO: BLIP model initialized.")

def capture_image() -> str:
    """Capture an image from the camera instance and return the saved image path."""
    try:
        from UI.module_ui_camera import CameraModule

        camera = CameraModule(1920, 1080)
        image_path = camera.capture_single_image()
        print(f"✅ Image saved: {image_path}")
        #camera.stop()
        return image_path

    except Exception as e:
        queue_message(f"ERROR: {e}")
        raise RuntimeError(f"Error capturing image: {e}")

def describe_camera_view() -> str:
    """Capture an image and process it for captioning."""
    try:
        image_path = capture_image()
        print(image_path)
        if CONFIG['VISION']['server_hosted']:
            return send_image_to_server(image_path)
        else:
            image = Image.open(image_path)
            inputs = PROCESSOR(image, return_tensors="pt").to(DEVICE)
            outputs = MODEL.generate(**inputs, max_new_tokens=50, num_beams=2)
            output = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
            print(output)
            return output
        
    except Exception as e:
        queue_message(f"TARS is unable to see right now")
        return f"Error: {e}"

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
    try:
        img_bytes = base64.b64decode(base64_str)
        raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')

        inputs = PROCESSOR(raw_image, return_tensors="pt").to(DEVICE)
        outputs = MODEL.generate(**inputs, max_new_tokens=100)

        caption = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
        return caption
    except Exception as e:
        raise RuntimeError(f"Error generating caption from base64: {e}")

def save_captured_image(image_path: str) -> str:
    """
    Save the captured image to the 'vision/images' directory.

    Parameters:
    - image_path (str): Path of the image to be saved.

    Returns:
    - str: The new saved image path.
    """
    try:
        output_dir = Path(__file__).resolve().parent.parent / "vision/images"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Define the file name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_path = output_dir / f"captured_image_{timestamp}.jpg"

        # Save the image to the new file path
        img = Image.open(image_path)
        img.save(new_path, format="JPEG", optimize=True, quality=85)

        return str(new_path)
    except Exception as e:
        queue_message(f"Error saving image: {e}")
        return None
