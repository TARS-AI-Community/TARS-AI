"""
app-server.py

Flask Server for GPTARS Application.

This script provides a Flask-based API server to handle image captioning 
and audio transcription tasks using pre-trained machine learning models.
"""

from flask import Flask, request, jsonify
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import torch
import traceback
from faster_whisper import WhisperModel
from flask_cors import CORS
from io import BytesIO
from datetime import datetime

# Initialize Flask app and enable CORS
app = Flask(__name__)
CORS(app)

# Set up device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Initialize BLIP model for image captioning
def initialize_blip_model():
    """Load BLIP model and processor for image captioning."""
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    model.to(device)
    return processor, model

blip_processor, blip_model = initialize_blip_model()

# Initialize Whisper model for audio transcription
"""
# Whisper Model Options
# OpenAI Whisper provides a range of models with varying size, speed, and accuracy:

1. Tiny
   - Size: ~39 MB
   - Use Case: Basic transcription tasks prioritizing speed over accuracy.

2. Base
   - Size: ~74 MB
   - Use Case: Quick transcription in moderately constrained environments.

3. Small
   - Size: ~244 MB
   - Use Case: Real-time transcription where quality matters more.

4. Medium
   - Size: ~769 MB
   - Use Case: Transcription tasks with high accuracy requirements.

5. Large
   - Size: ~1.55 GB
   - Use Case: Critical transcription tasks where accuracy is paramount.
"""

def initialize_whisper_model(
    model_size="large-v3", 
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu"),
    compute_type="int8_float8"  # Use "float16" or "int8" for optimization
):
    """Load Whisper model for audio transcription using faster-whisper."""
    try:
        return WhisperModel(
            model_size,
            device=device,  # Correctly pass device as "cpu" or "cuda"
            compute_type=compute_type
        )
    except Exception as e:
        print("Error initializing Whisper model:", traceback.format_exc())
        raise e

whisper_model = initialize_whisper_model(
    model_size="tiny", 
    device="cuda" if torch.cuda.is_available() else "cpu", 
    compute_type="int8_float16" if torch.cuda.is_available() else "int8"
)

# Routes
@app.route('/caption', methods=['POST'])
def caption_image():
    """
    Endpoint to generate a caption for an uploaded image.
    """
    try:
        # Validate the request
        if 'image' not in request.files:
            return jsonify({"error": "No image file provided"}), 400
        
        # Read the uploaded image into a BytesIO object
        image_file = request.files['image']
        image_bytes = BytesIO(image_file.read())
        image = Image.open(image_bytes)
        
        # Generate caption
        inputs = blip_processor(image, return_tensors="pt").to(device)
        outputs = blip_model.generate(**inputs, max_new_tokens=100, num_beams=3)
        caption = blip_processor.decode(outputs[0], skip_special_tokens=True)
        
        return jsonify({"caption": caption})
    except Exception as e:
        print("Error occurred during caption generation:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500



@app.route('/save_audio', methods=['POST'])
def save_audio():
    """
    Endpoint to transcribe uploaded audio using Whisper.
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]  Accessed")
    try:
        # Validate the request
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400

        # Read the uploaded audio into a BytesIO object
        audio_blob = request.files['audio']
        audio_bytes = BytesIO(audio_blob.read())

        # Transcribe the audio
        segments, _ = whisper_model.transcribe(audio_bytes, beam_size=5)

        # Extract and format transcription
        transcription = [
            {"text": segment.text, "start": segment.start, "end": segment.end}
            for segment in segments
        ]

        return jsonify({"transcription": transcription})

    except Exception as e:
        print("Error occurred during audio transcription:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# Main entry point
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5678)
