import base64
import os
import threading
from io import BytesIO
import requests

from modules.module_config import load_config, get_api_key, get_capabilities
from modules.module_messageQue import queue_message

CONFIG = load_config()
_CAPS_VISION = get_capabilities()

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

# torch / transformers only on devices that support vision (Pi5)
if _CAPS_VISION is None or _CAPS_VISION.can_use_vision:
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

# BLIP model state — guarded by _blip_lock
from pathlib import Path

DEVICE = None
if torch:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

MODEL_NAME = "Salesforce/blip-image-captioning-base"
CACHE_DIR = Path(__file__).resolve().parent.parent / "vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_blip_lock = threading.Lock()
_processor = None
_model = None


def initialize_blip():
    """Initialize BLIP model and processor (thread-safe)."""
    global _processor, _model
    if not CONFIG['VISION']['enabled']:
        return
    if BlipProcessor is None or BlipForConditionalGeneration is None or torch is None:
        queue_message("WARNING: BLIP dependencies not available (transformers, torch)")
        return
    with _blip_lock:
        if _processor is not None and _model is not None:
            return
        queue_message("INFO: Initializing BLIP model...")
        _processor = BlipProcessor.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR), use_fast=False)
        _model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR)).to(DEVICE)
        _model = torch.quantization.quantize_dynamic(_model, {torch.nn.Linear}, dtype=torch.qint8)
        queue_message("INFO: BLIP model initialized.")


def _to_base64(image_data):
    """Accept bytes or base64 string, always return base64 string."""
    if isinstance(image_data, (bytes, bytearray)):
        return base64.b64encode(image_data).decode('utf-8')
    return image_data  # already a base64 string


def _to_bytes(image_data):
    """Accept bytes or base64 string, always return bytes."""
    if isinstance(image_data, (bytes, bytearray)):
        return bytes(image_data)
    return base64.b64decode(image_data)


# --- Backend implementations ---

def _describe_blip(image_data, prompt):
    """Generate caption using local BLIP model."""
    global _processor, _model
    if _processor is None or _model is None:
        initialize_blip()
    if _processor is None or _model is None:
        return "Error: BLIP model not available"

    img_bytes = _to_bytes(image_data)
    debug = CONFIG.get('debug_mode', False)
    raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')

    if debug:
        import numpy as _np
        arr = _np.array(raw_image)
        brightness = arr.mean()
        queue_message(f"DEBUG VISION: Image size={arr.shape}, brightness={brightness:.1f}/255, bytes={len(img_bytes)}")
        if brightness < 10:
            queue_message("DEBUG VISION: WARNING — image is nearly black! Camera may not be ready.")

    inputs = _processor(raw_image, return_tensors="pt").to(DEVICE)
    outputs = _model.generate(**inputs, max_new_tokens=100, num_beams=2)
    caption = _processor.decode(outputs[0], skip_special_tokens=True)
    if debug:
        queue_message(f"DEBUG VISION: BLIP caption: {caption}")
    return caption


def _get_vision_settings():
    """Resolve API key, base URL, and model based on use_llm_backend toggle."""
    use_llm = CONFIG['VISION'].get('use_llm_backend', True)
    llm_backend = CONFIG['LLM']['llm_backend']

    if use_llm:
        # Use main LLM settings
        api_key = CONFIG['LLM']['api_key']
        base_url = CONFIG['LLM']['base_url']
        if llm_backend == "deepinfra":
            model = CONFIG['LLM']['openai_model']
        elif llm_backend == "grok":
            model = CONFIG['LLM']['grok_model']
        elif llm_backend == "openai":
            model = CONFIG['LLM']['openai_model']
        else:
            model = CONFIG['LLM']['other_model']
    else:
        # Use separate vision settings, fall back to LLM settings if blank
        api_key = os.environ.get('VISION_API_KEY', '') or CONFIG['LLM']['api_key']
        base_url = CONFIG['VISION'].get('base_url', '') or CONFIG['LLM']['base_url']
        model = CONFIG['VISION'].get('vision_model', '')
        if not model:
            # Fall back to LLM model
            if llm_backend == "openai":
                model = CONFIG['LLM']['openai_model']
            elif llm_backend == "grok":
                model = CONFIG['LLM']['grok_model']
            elif llm_backend == "deepinfra":
                model = CONFIG['LLM']['openai_model']
            else:
                model = CONFIG['LLM']['other_model']

    return api_key, base_url, model


def _describe_llm(image_data, prompt):
    """Send image to the configured LLM backend for vision."""
    api_key, base_url, model = _get_vision_settings()
    if not api_key:
        return "Error: No API key configured for vision"
    if not base_url:
        return "Error: No base_url configured for vision"
    max_tokens = int(CONFIG['VISION'].get('vision_max_tokens', 150))
    llm_backend = CONFIG['LLM']['llm_backend']

    if llm_backend == "deepinfra":
        url = f"{base_url}/v1/openai/chat/completions"
    else:
        url = f"{base_url}/v1/chat/completions"

    b64 = _to_base64(image_data)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "max_tokens": max_tokens
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    description = response.json()['choices'][0]['message']['content']
    queue_message(f"Vision: {description}")
    return description


def _describe_openai(image_data, prompt):
    """Send image to OpenAI vision API."""
    use_llm = CONFIG['VISION'].get('use_llm_backend', True)

    if use_llm:
        api_key = os.getenv('OPENAI_API_KEY') or CONFIG['LLM']['api_key']
        api_url = "https://api.openai.com/v1/chat/completions"
        model = 'gpt-4o-mini'
    else:
        api_key = os.environ.get('VISION_API_KEY', '') or os.getenv('OPENAI_API_KEY') or CONFIG['LLM']['api_key']
        vision_base = CONFIG['VISION'].get('base_url', '')
        api_url = f"{vision_base}/v1/chat/completions" if vision_base else "https://api.openai.com/v1/chat/completions"
        model = CONFIG['VISION'].get('vision_model', '') or 'gpt-4o-mini'

    if not api_key:
        return "Error: No API key available for OpenAI vision"

    max_tokens = int(CONFIG['VISION'].get('vision_max_tokens', 150))
    b64 = _to_base64(image_data)

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "max_tokens": max_tokens
    }
    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    description = response.json()['choices'][0]['message']['content']
    queue_message(f"Vision: {description}")
    return description


def _describe_server(image_data, prompt):
    """Send image to external vision server for captioning."""
    base_url = CONFIG['VISION'].get('base_url', '')
    if not base_url:
        return "Error: No base_url configured for server_hosted vision"
    img_bytes = _to_bytes(image_data)
    files = {'image': ('image.jpg', BytesIO(img_bytes), 'image/jpeg')}
    headers = {}
    api_key = os.environ.get('EXTERNAL_API_KEY', '')
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(f"{base_url}/caption", files=files, headers=headers, timeout=15)
    if response.status_code == 200:
        return response.json().get("caption", "No caption returned")
    return f"Error: Server returned {response.status_code}"


# Backend dispatch table
_BACKENDS = {
    "blip": _describe_blip,
    "llm": _describe_llm,
    "openai": _describe_openai,
    "external": _describe_server,
}


def process_image(image_data, prompt="Describe this image in detail.", detection_context=None):
    """Unified vision dispatcher. Accepts bytes or base64 string."""
    processor = CONFIG['VISION'].get('vision_processor', 'blip')
    backend = _BACKENDS.get(processor)
    if backend is None:
        queue_message(f"ERROR: Unknown vision_processor '{processor}'")
        return f"Error: Unknown vision_processor '{processor}'"

    if detection_context:
        prompt = f"{detection_context}\n\n{prompt}"

    try:
        return backend(image_data, prompt)
    except Exception as e:
        queue_message(f"ERROR: Vision ({processor}) failed - {e}")
        return f"Error: {e}"


def capture_camera_base64():
    """Capture from camera and return base64 string. Returns (b64, None) or (None, error)."""
    if not CONFIG['VISION'].get('enabled', False):
        return None, "Error: Vision is not enabled"
    if CameraModule is None:
        return None, "Error: Camera module not available"
    try:
        import time as _time
        camera = CameraModule.get_instance()
        if camera is None:
            return None, "Error: Camera not initialized"
        # Discard first capture and wait briefly for a fresh frame from the sensor
        camera.capture_bytes()
        _time.sleep(0.3)
        image_bytes = camera.capture_bytes()
        return _to_base64(image_bytes), None
    except Exception as e:
        queue_message(f"ERROR: Camera capture failed - {e}")
        return None, "I tried to look but encountered an error."


def process_camera_image(user_prompt="Describe what you see.", detection_context=None):
    """Capture from camera and process with configured vision backend."""
    b64, error = capture_camera_base64()
    if error:
        return error
    try:
        return process_image(b64, user_prompt, detection_context=detection_context)
    except Exception as e:
        queue_message(f"ERROR: Camera vision failed - {e}")
        return "I tried to look but encountered an error."
