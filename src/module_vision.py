"""
module_vision.py

Vision Processing Module for GPTARS Application.

This module handles image capture and caption generation, supporting both server-hosted 
and on-device processing modes. It utilizes the BLIP model for on-device inference and 
communicates with a server endpoint for remote processing.
"""
# === Standard Libraries ===
import subprocess
import traceback
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from io import BytesIO
import requests
import torch
import base64
from datetime import datetime

# === Custom Modules ===
from module_config import load_config

# === Constants and Globals ===
CONFIG = load_config()

# Device configuration
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# BLIP model initialization (only for on-device)
processor = None
model = None

# === Helper Functions ===

def initialize_blip_model():
    """
    Initialize the BLIP model and processor for on-device vision processing.
    """
    global processor, model
    if processor is None or model is None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Initializing BLIP model and processor...")
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        model.to(device)
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: BLIP model and processor initialized.")


def capture_image() -> BytesIO:
    """
    Capture an image using libcamera-still and return it as a BytesIO object.

    Returns:
    - BytesIO: Captured image in memory.
    """
    try:
        # Adjust resolution based on whether the server is hosted or on-device
        width = "2592" if CONFIG['VISION']['server_hosted'] == 'True' else "320"
        height = "1944" if CONFIG['VISION']['server_hosted'] == 'True' else "240"
        
        # Capture the image directly to stdout
        command = [
            "libcamera-still",
            "--output", "-",  # Output to stdout
            "--timeout", "300",  # 0.3-second timeout for capture
            "--width", width,
            "--height", height
        ]
        process = subprocess.run(command, stdout=subprocess.PIPE, check=True)
        #print(height)
        return BytesIO(process.stdout)  # Return image as BytesIO
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error capturing image: {e}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Image capture failed:", traceback.format_exc())
        raise e

def send_image_to_server(image_bytes: BytesIO) -> str:
    """
    Send an image to the server for captioning and return the generated caption.

    Parameters:
    - image_bytes (BytesIO): The image in memory to be sent.

    Returns:
    - str: Generated caption from the server.
    """
    try:
        files = {'image': ('image.jpg', image_bytes, 'image/jpeg')}
        response = requests.post(f"{CONFIG['VISION']['base_url']}/caption", files=files)

        if response.status_code == 200:
            return response.json().get("caption", "No caption returned")
        else:
            error_message = response.json().get('error', 'Unknown error')
            raise RuntimeError(f"Server error ({response.status_code}): {error_message}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to send image to server:", traceback.format_exc())
        raise e

def get_image_caption_from_base64(base64_str):
    """
    Generate a caption for an image encoded in base64.

    Parameters:
    - base64_str (str): Base64-encoded string of the image.

    Returns:
    - str
    """
    try:
        # Decode the base64 string into image bytes
        img_bytes = base64.b64decode(base64_str)
        raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')

        # Prepare inputs for the BLIP model
        inputs = processor(raw_image, return_tensors="pt")
        outputs = model.generate(**inputs, max_new_tokens=100)

        # Decode and return the generated caption
        caption = processor.decode(outputs[0], skip_special_tokens=True)
        return caption
    except Exception as e:
        raise RuntimeError(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error generating caption from base64: {e}")

# === Main Functions ===
def describe_camera_view() -> str:
    """
    Capture an image and process it either on-device or by sending it to the server.

    Returns:
    - str: Caption describing the captured image.
    """
    try:
        # Capture the image
        image_bytes = capture_image()

        if CONFIG['VISION']['server_hosted'] == 'True':
            # Use server-hosted vision processing
            return send_image_to_server(image_bytes)
        else:
            # Use on-device BLIP model for captioning
            initialize_blip_model()
            image = Image.open(image_bytes)
            inputs = processor(image, return_tensors="pt").to(device)

            outputs = model.generate(**inputs, max_new_tokens=50, num_beams=5)
            caption = processor.decode(outputs[0], skip_special_tokens=True)
            return caption
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error during image processing:", traceback.format_exc())
        return f"Error: {e}"
    


