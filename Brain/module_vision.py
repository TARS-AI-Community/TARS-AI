import subprocess
import traceback
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from io import BytesIO
import requests
import torch
import configparser

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Vision configuration
server_hosted = config['VISION']['server_hosted']
vision_base_url = config['VISION']['base_url']

# Device configuration
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# BLIP model initialization (only for on-device)
processor = None
model = None


def initialize_blip_model():
    """
    Initialize the BLIP model and processor for on-device vision processing.
    """
    global processor, model
    if processor is None or model is None:
        print("Initializing BLIP model and processor...")
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        model.to(device)
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        print("BLIP model and processor initialized.")


def capture_image() -> BytesIO:
    """
    Capture an image using libcamera-still and return it as a BytesIO object.
    """
    try:
        # Adjust resolution based on whether the server is hosted or on-device
        width = "2592" if server_hosted == 'True' else "320"
        height = "1944" if server_hosted == 'True' else "240"
        
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
        raise RuntimeError(f"Error capturing image: {e}")
    except Exception as e:
        print("Error occurred during image capture:", traceback.format_exc())
        raise e


def send_image_to_server(image_bytes: BytesIO) -> str:
    """
    Send an image to the server for captioning and return the generated caption.
    """
    try:
        files = {'image': ('image.jpg', image_bytes, 'image/jpeg')}
        response = requests.post(f"{vision_base_url}/caption", files=files)

        if response.status_code == 200:
            return response.json().get("caption", "No caption returned")
        else:
            error_message = response.json().get('error', 'Unknown error')
            raise RuntimeError(f"Server error ({response.status_code}): {error_message}")
    except Exception as e:
        print("Error sending image to server:", traceback.format_exc())
        raise e


def describe_camera_view() -> str:
    """
    Capture an image and process it either on-device or by sending it to the server.
    """
    try:
        # Capture the image
        image_bytes = capture_image()

        if server_hosted == 'True':
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
        print("Error during image processing:", traceback.format_exc())
        return f"Error: {e}"
