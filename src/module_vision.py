"""
module_vision.py

Vision Processing Module for TARS-AI Application.

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
from pathlib import Path

# === Custom Modules ===
from module_config import load_config

# === Constants and Globals ===
CONFIG = load_config()

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_NAME = "Salesforce/blip-image-captioning-base"

# Cache directory for model
CACHE_DIR = Path("./vision")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Globals for processor and model
PROCESSOR = None
MODEL = None

# === Helper Functions ===

def initialize_blip():
    """
    Initialize BLIP model and processor for detailed captions.
    Ensures the model is loaded from the cache directory.
    """
    global PROCESSOR, MODEL
    if not PROCESSOR or not MODEL:
        print(f"INFO: Initializing BLIP model...")
        PROCESSOR = BlipProcessor.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR))
        MODEL = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR)).to(DEVICE)
        MODEL = torch.quantization.quantize_dynamic(
            MODEL, {torch.nn.Linear}, dtype=torch.qint8
        )
        print(f"INFO: BLIP model initialized.")


def capture_image() -> BytesIO:
    """
    Capture an image using libcamera-still and return it as a BytesIO object.

    Returns:
    - BytesIO: Captured image in memory.
    """
    try:
        # Determine resolution from CONFIG
        if CONFIG['VISION']['server_hosted']:
            width, height = "2592", "1944"  # High resolution for server processing
        else:
            width, height = "1920", "1080"   # Low resolution for on-device processing

        print(f"INFO: Capturing image at resolution {width}x{height}.")

        # Capture the image using libcamera-still
        command = [
            "libcamera-still",
            "--output", "-",  # Output to stdout
            "--timeout", "50",  # Short timeout
            "--width", width,
            "--height", height,
        ]
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,  # Capture standard output (image data)
            stderr=subprocess.DEVNULL,  # Suppress standard error (libcamera logs)
            check=True
        )
        return BytesIO(process.stdout)  # Return the captured image as BytesIO
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error capturing image: {e}")


def send_image_to_server(image_bytes: BytesIO) -> str:
    """
    Send an image to the server for captioning and return the generated caption.

    Parameters:
    - image_bytes (BytesIO): The image in memory to be sent.

    Returns:
    - str: Generated caption from the server.
    """
    # Ensure the BytesIO object is rewound before sending
    image_bytes.seek(0)

    try:
        # Properly send the image as a file
        files = {'image': ('image.jpg', image_bytes.getvalue(), 'image/jpeg')}
        #print(f"DEBUG: Sending image to {CONFIG['VISION']['base_url']}/caption")

        response = requests.post(f"{CONFIG['VISION']['base_url']}/caption", files=files)

        if response.status_code == 200:
            return response.json().get("caption", "No caption returned")
        else:
            error_message = response.json().get('error', 'Unknown error')
            raise RuntimeError(f"Server error ({response.status_code}): {error_message}")
    except Exception as e:
        print(f"[{datetime.now()}] ERROR: Failed to send image to server:", traceback.format_exc())
        raise


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
        inputs = PROCESSOR(raw_image, return_tensors="pt")
        outputs = MODEL.generate(**inputs, max_new_tokens=100)

        # Decode and return the generated caption
        caption = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
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
        # Capture the image once
        image_bytes = capture_image()

        # Save the image before processing
        save_captured_image(image_bytes)  # Pass image_bytes as an argument

        if CONFIG['VISION']['server_hosted']:
            # Use server-hosted vision processing
            return send_image_to_server(image_bytes)
        else:
            # Use on-device BLIP model for captioning
            image = Image.open(image_bytes)
            inputs = PROCESSOR(image, return_tensors="pt").to(DEVICE)

            outputs = MODEL.generate(**inputs, max_new_tokens=50, num_beams=2)
            caption = PROCESSOR.decode(outputs[0], skip_special_tokens=True)
            return caption
    except Exception as e:
        print(f"TARS is unable to see right now")
        return f"Error: {e}"

def save_captured_image(image_bytes: BytesIO):
    """
    Save the captured image to the 'vision/images' directory.

    Parameters:
    - image_bytes (BytesIO): The image to save.
    """
    try:
        # Create the output directory if it doesn't exist
        output_dir = Path("vision/images")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Define the file name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = output_dir / f"captured_image_{timestamp}.jpg"

        # Save the image to the file path
        with Image.open(image_bytes) as img:
            img.save(file_path, format="JPEG", optimize=True, quality=85)

        #print(f"Image saved to {file_path}")
        return file_path
    except Exception as e:
        print(f"Error saving image: {e}")
        return None