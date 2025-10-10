#!/usr/bin/env python3
"""
Face Animator with Flask Streaming (No Kivy) – Breathing, Blinking, Talking, and Sway Control

This script uses Pillow to simulate face animation with:
  - Blinking at random intervals.
  - Talking mode: when active, the image is chosen to mimic mouth movement.
  - A breathing effect that scales the chest (lower region) of the image.
  - Horizontal sway whose strength is controlled by a variable 'swayamount' (1 = off, 10 = maximum).

The current frame is updated in a background thread and streamed via Flask.
  
Flask endpoints:
  - /stream         → streams the current frame as a multipart HTTP response.
  - /start_talking  → sets talking mode.
  - /stop_talking   → disables talking mode.
  
Requirements:
  - Four image files (placed in the same directory or adjust paths):
       character_nottalking_eyes_open.png  
       character_nottalking_eyes_closed.png  
       character_talking_eyes_open.png  
       character_talking_eyes_closed.png  
  - Pillow and Flask installed in your virtual environment.
"""

import os
import threading, time, math, random, io
from PIL import Image
import logging
import json
import asyncio

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    Response,
)
from flask_cors import CORS
from flask_socketio import SocketIO
import re
import asyncio
import threading
from collections import OrderedDict
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError


# === Custom Modules ===
from modules.module_config import load_config
from modules.module_llm import get_completion
from modules.module_vision import get_image_caption_from_base64
from modules.module_tts import generate_tts_audio
from modules.module_llm import detect_emotion
from modules.module_messageQue import queue_message

# Suppress Flask logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
os.environ['WERKZEUG_RUN_MAIN'] = 'true'

# If using eventlet or gevent with Flask-SocketIO
sio_logger = logging.getLogger('socketio')
sio_logger.setLevel(logging.ERROR)
engineio_logger = logging.getLogger('engineio')
engineio_logger.setLevel(logging.ERROR)

CONFIG = load_config()

if (CONFIG["SERVO"]["MOVEMENT_VERSION"] == "V2"):
    from modules.module_servoctl_v2 import *
else:
    from modules.module_servoctl import *

# Frame dimensions (as requested)
FRAME_WIDTH = 500
FRAME_HEIGHT = 500

# swayamount: 1 means off (no sway), 10 means maximum sway.
swayamount = 1   # You can change this value from 1 to 10.
emotion = 'neutral'

# Get the base directory where the script is running
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
character_path = CONFIG['CHAR']['character_card_path']
character_name = os.path.splitext(os.path.basename(character_path))[0]  # Extract filename without extension
CHARACTER_DIR = os.path.join(BASE_DIR, "character", character_name, "images", emotion)

sprite = character_name

# Load images using the absolute path
img_nottalking_open = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{emotion}_nottalking_eyes_open.png")).convert("RGBA")
img_nottalking_closed = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{emotion}_nottalking_eyes_closed.png")).convert("RGBA")
img_talking_open = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{emotion}_talking_eyes_open.png")).convert("RGBA")
img_talking_closed = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{emotion}_talking_eyes_closed.png")).convert("RGBA")

# Resize images to our frame dimensions.
img_nottalking_open = img_nottalking_open.resize((FRAME_WIDTH, FRAME_HEIGHT))
img_nottalking_closed = img_nottalking_closed.resize((FRAME_WIDTH, FRAME_HEIGHT))
img_talking_open = img_talking_open.resize((FRAME_WIDTH, FRAME_HEIGHT))
img_talking_closed = img_talking_closed.resize((FRAME_WIDTH, FRAME_HEIGHT))

# Global state variables.
is_talking = False
is_blinking = False
next_blink_time = time.time() + random.uniform(3, 4)
blink_end_time = None
latest_text_to_read = ""  # Initialize as an empty string (or a default message)

current_frame = None
frame_lock = threading.Lock()

audio_chunks_dict = OrderedDict()
current_chunk_index = 0  # Keep track of which chunk is currently being served

def apply_breathing(base_img, t):
    """
    Apply a breathing effect by scaling the chest region of the image.
    In this version, we assume the chest occupies the lower 60% of the image.
    (i.e. the cutoff is at 40% of the height.)
    """
    amplitude = 0.005  # 3% expansion
    freq = 0.25       # about one breath every 4 seconds
    breath = 1 + amplitude * math.sin(2 * math.pi * freq * t)
    
    # For chest covering the lower 60%, cutoff is at 40% of the height.
    cutoff = int(FRAME_HEIGHT * 0.4)
    
    # Crop the lower portion.
    lower = base_img.crop((0, cutoff, FRAME_WIDTH, FRAME_HEIGHT))
    orig_lower_height = FRAME_HEIGHT - cutoff
    new_lower_height = int(orig_lower_height * breath)
    
    # Resize the lower portion.
    scaled_lower = lower.resize((FRAME_WIDTH, new_lower_height), resample=Image.BICUBIC)
    
    # Make a copy of the base image.
    new_img = base_img.copy()
    
    # Compute vertical adjustment so the chest remains centered.
    delta = new_lower_height - orig_lower_height
    paste_y = cutoff - (delta // 2)
    
    # Paste the scaled lower portion back into the copy.
    new_img.paste(scaled_lower, (0, paste_y))
    return new_img

def animation_loop():
    global is_talking, is_blinking, next_blink_time, blink_end_time, current_frame
    start_time = time.time()
    while True:
        now = time.time()
        # --- Update blinking state ---
        if not is_blinking and now >= next_blink_time:
            is_blinking = True
            blink_end_time = now + 0.4  # blink lasts 0.4 sec
        if is_blinking and now >= blink_end_time:
            is_blinking = False
            next_blink_time = now + random.uniform(3, 4)
        
        # --- Determine which image to use ---
        if is_talking:
            if is_blinking:
                base_img = img_talking_closed
            else:
                if random.random() < 0.7:
                    base_img = img_talking_open
                else:
                    base_img = img_nottalking_open
        else:
            if is_blinking:
                base_img = img_nottalking_closed
            else:
                base_img = img_nottalking_open
        
        # --- Apply horizontal sway ---
        t = now - start_time
        # The base sway computed (±10 pixels) is scaled by (swayamount - 1), so that when swayamount=1, sway=0.
        sway_base = 10 * math.sin(1.5 * t)
        sway_x = int((swayamount - 1) * sway_base)
        
        # --- Apply breathing effect ---
        t = 0 #no breathing
        base_with_breath = apply_breathing(base_img, t)

        # Create a new frame with a transparent background.
        frame = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
        # Paste the processed image with the horizontal offset.
        frame.paste(base_with_breath, (sway_x, 0))
        
        # --- Update global current_frame ---
        with frame_lock:
            current_frame = frame.copy()
        
        time.sleep(0.1)  # Update at roughly 10 fps
        
                
# Start the animation loop in a daemon thread.
anim_thread = threading.Thread(target=animation_loop, daemon=True)
anim_thread.start()

# ----------------- Flask Setup -----------------

# Get the base directory where the script is running
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Moves up one directory
CHARACTER_DIR = os.path.join(BASE_DIR, "www", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "www", "static")


# Initialize Flask app with absolute paths
flask_app = Flask(__name__, template_folder=CHARACTER_DIR, static_url_path='/static', static_folder=STATIC_DIR)
CORS(flask_app)
socketio = SocketIO(flask_app, cors_allowed_origins="*", logger=False, engineio_logger=False)

def send_heartbeat():
    while True:
        socketio.sleep(10)  # Send heartbeat every 10 seconds
        socketio.emit('heartbeat', {'status': 'alive'})
        
@socketio.on('connect')
def handle_connect():
    #start_idle()
    #queue_message('Client connected')
    socketio.start_background_task(send_heartbeat)
    #if IDLE_MSGS_enabled == "True":
        #socketio.start_background_task(idle_msg) 

@socketio.on('heartbeat')
def handle_heartbeat(message):
    #queue_message('Received heartbeat from client')
    pass

@socketio.on('disconnect')
def handle_disconnect():
    pass
    #queue_message('Client disconnected')

@flask_app.route('/')
def index():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # Connects to an external server but doesn't send data
        local_ip = s.getsockname()[0]
        
    ipadd = local_ip
    return render_template('index.html',
                           char_name=json.dumps(character_name),
                           char_greeting='Welcome back',
                           talkinghead_base_url=json.dumps(ipadd))

@flask_app.route('/holo')
def holo():
    return render_template('holo.html')

@flask_app.route('/get_ip')
def get_config_variable():
    # Assuming the variable is in a section called 'Settings' with key 'my_variable'
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # Connects to an external server but doesn't send data
            local_ip = s.getsockname()[0]
    except Exception as e:
        return f"Error: {e}"
    
    #queue_message(jsonify({'talkinghead_base_url': f"http://{local_ip}:5012"}))
    return jsonify({'talkinghead_base_url': f"http://{local_ip}:5012"})

@flask_app.route('/stream')
def stream():
    def generate_frames():
        while True:
            with frame_lock:
                if current_frame is None:
                    continue
                buffer = io.BytesIO()
                current_frame.save(buffer, format="PNG")
                frame_data = buffer.getvalue()
            yield (b"--frame\r\n"
                   b"Content-Type: image/png\r\n\r\n" + frame_data + b"\r\n")
            socketio.sleep(0.1)
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@flask_app.route('/start_talking')
def start_talking_endpoint():
    global is_talking
    is_talking = True
    #queue_message("DEBUG: Talking mode enabled.")
    return Response("started", status=200)

@flask_app.route('/stop_talking')
def stop_talking_endpoint():
    global is_talking
    is_talking = False
    #queue_message("DEBUG: Talking mode disabled.")
    return Response("stopped", status=200)

@flask_app.route('/emotion', methods=['POST'])
def set_emotion():
    """
    Receives a single-word emotion and updates the stored emotion.
    """
    global CHARACTER_DIR, img_nottalking_open, img_nottalking_closed, img_talking_open, img_talking_closed
    detected_emotion = request.data.decode("utf-8").strip()  # Read raw data as a string

    if detected_emotion:  # Ensure it's not empty
        # Build the new emotion folder path
        new_character_dir = os.path.join(BASE_DIR, "character", character_name, "images", detected_emotion)

        # Check if the folder exists, otherwise, fallback to 'neutral'
        if not os.path.exists(new_character_dir):
            #queue_message(f"Emotion folder '{new_character_dir}' not found. Falling back to 'neutral'.")
            detected_emotion = "neutral"
            new_character_dir = os.path.join(BASE_DIR, "character", character_name, "images", detected_emotion)

        # **Update Global Emotion Directory**
        CHARACTER_DIR = new_character_dir
        #queue_message(f"Updated CHARACTER_DIR: {CHARACTER_DIR}")

        try:
            # **🔄 Reload Character Images for New Emotion**
            img_nottalking_open = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{detected_emotion}_nottalking_eyes_open.png")).convert("RGBA")
            img_nottalking_closed = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{detected_emotion}_nottalking_eyes_closed.png")).convert("RGBA")
            img_talking_open = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{detected_emotion}_talking_eyes_open.png")).convert("RGBA")
            img_talking_closed = Image.open(os.path.join(CHARACTER_DIR, "animation", f"{sprite}_{detected_emotion}_talking_eyes_closed.png")).convert("RGBA")

            # Resize images to match the frame dimensions
            img_nottalking_open = img_nottalking_open.resize((FRAME_WIDTH, FRAME_HEIGHT))
            img_nottalking_closed = img_nottalking_closed.resize((FRAME_WIDTH, FRAME_HEIGHT))
            img_talking_open = img_talking_open.resize((FRAME_WIDTH, FRAME_HEIGHT))
            img_talking_closed = img_talking_closed.resize((FRAME_WIDTH, FRAME_HEIGHT))

            return jsonify({"message": "Emotion updated", "emotion": detected_emotion}), 200

        except FileNotFoundError as e:
            queue_message(f"Error loading images for {detected_emotion}: {e}")
            return jsonify({"error": "Missing image files"}), 500

    return jsonify({"error": "No emotion provided"}), 400  # Ensure a response in all cases

@flask_app.route('/process_llm', methods=['POST'])
def receive_user_message():
    global latest_text_to_read

    user_message = request.form.get('message', '')  
    file = request.files.get('file')  

    if file:
        buffer = BytesIO()
        file.save(buffer)
        buffer.seek(0)

        base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
        img_html = f'<img height="256" src="data:image/png;base64,{base64_image}"></img>'

        try:
            raw_image = Image.open(buffer).convert('RGB')
            caption = get_image_caption_from_base64(base64_image)
        except UnidentifiedImageError as e:
            queue_message(f"Failed to open the image: {e}")
            caption = "Failed to process image"

        cmessage = f"*The Uploaded photo has the following description {caption}* and the user sent the following message with the photo: {user_message}"
        reply = get_completion(cmessage)
    else:
        reply = get_completion(user_message)

    latest_text_to_read = reply
    socketio.emit('bot_message', {'message': latest_text_to_read})

    if CONFIG['EMOTION']['enabled']:
        detect_emotion(reply)
        
    return jsonify({"status": "success"})

@flask_app.route('/upload', methods=['GET', 'POST'])
def upload():
    import base64
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    global start_time, latest_text_to_read
    start_time = time.time() 

    # Assuming 'file' is the key in the FormData object containing the file
    file = request.files['file']
    if file:
        # Convert the image to a BytesIO buffer, then to a base64 string
        buffer = BytesIO()
        file.save(buffer)
        base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')

        img_html = f'<img height="256" src="data:image/png;base64,{base64_image}"></img>'
        socketio.emit('user_message', {'message': img_html})

        # Optionally, for further processing like getting a caption
        try:
            buffer.seek(0)  # Reset buffer position to the beginning
            raw_image = Image.open(buffer).convert('RGB')
            # Proceed with processing the image, like getting a caption
            caption = "Image processed successfully"
        except UnidentifiedImageError as e:
            queue_message(f"Failed to open the image: {e}")
            caption = "Failed to process image"


        caption = get_image_caption_from_base64(base64_image)
        cmessage = f"*Sends {CONFIG['CHAR']['user_name']} a picture of: {caption}*"

        reply = get_completion(cmessage)
        latest_text_to_read = reply

        socketio.emit('bot_message', {'message': latest_text_to_read})

        return 'Upload OK'
    else:
        return 'No file part', 400

@flask_app.route('/audio_stream')
def audio_stream():
    """
    Generate MP3 TTS and serve the first chunk using dictionary-based storage.
    """
    global is_talking, current_chunk_index
    is_talking = True  # Set talking state

    # ✅ Reset chunk tracking for new requests
    audio_chunks_dict.clear()  
    current_chunk_index = 0  

    def get_final_text():
        return latest_text_to_read if 'latest_text_to_read' in globals() else "No response available."

    final_text = get_final_text()
    #queue_message("Audio stream starting with final text:", final_text)

    async def generate_mp3_chunks():
        """
        Generate text-to-speech audio chunks and store them in the dictionary.
        """
        index = 0
        async for chunk in generate_tts_audio(final_text, CONFIG['TTS']['ttsoption']):
            audio_chunks_dict[index] = chunk.getvalue()  # Store chunk with its order
            index += 1

        #queue_message(f"Generated {len(audio_chunks_dict)} chunks.")
        audio_chunks_dict[index] = None  # Mark end of chunks

    # Run the async generator in a background thread
    def run_async_generator():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_mp3_chunks())
        loop.close()

    threading.Thread(target=run_async_generator, daemon=True).start()

    # ✅ Wait for the first chunk to be available
    max_wait_time = 5  # Max time to wait for the first chunk (seconds)
    waited = 0
    while 0 not in audio_chunks_dict:
        if waited >= max_wait_time:
            #queue_message("First chunk did not generate in time.")
            return Response(status=204)
        time.sleep(0.1)
        waited += 0.1

    # ✅ Serve the first MP3 chunk and update index **before returning**
    #queue_message("Serving first chunk.")
    first_chunk = audio_chunks_dict[0]
    current_chunk_index = 1  # ✅ Update chunk index immediately
    return Response(first_chunk, mimetype="audio/mp3", headers={'Content-Type': 'audio/mp3'})

@flask_app.route('/get_next_audio_chunk')
def get_next_audio_chunk():
    """
    Serve the next MP3 chunk by index from the dictionary.
    """
    global current_chunk_index

    if current_chunk_index in audio_chunks_dict:
        next_chunk = audio_chunks_dict[current_chunk_index]
        
        if next_chunk is None:
            #queue_message(f"End of chunks at index {current_chunk_index}.")
            return Response(status=204)  # No more audio

        #queue_message(f"Serving chunk {current_chunk_index}.")
        response = Response(next_chunk, mimetype="audio/mp3", headers={
            'Content-Type': 'audio/mp3',
            'Content-Length': str(len(next_chunk)),  # Ensure correct content size
        })

        # ✅ Update `current_chunk_index` **AFTER** the chunk is sent
        current_chunk_index += 1
        return response
    else:
        #queue_message(f"Chunk {current_chunk_index} not available yet.")
        return Response(status=204)  # No content available yet

# Add these routes to your Flask application

@flask_app.route('/robot_move', methods=['POST'])
def robot_move():
    """
    Handles robot movement commands.
    Expects JSON with a 'direction' field containing one of: 'forward', 'backward', 'left', 'right'
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    direction = data.get('direction')
    
    if direction not in ['forward', 'backward', 'left', 'right']:
        return jsonify({"error": "Invalid direction. Must be one of: forward, backward, left, right"}), 400
    
    # Execute the robot movement command
    # This is where you would add code to control your actual robot
    # For example, you might send commands to a GPIO interface, a robot API, etc.
    
    try:
        if direction == 'forward':
            step_forward()
        elif direction == 'backward':
            # Code to move robot backward 
            pass 
        elif direction == 'left':
            turn_left()
        elif direction == 'right':
            turn_right()
            
        return jsonify({"success": True, "message": f"Robot moved {direction}"}), 200
        
    except Exception as e:
        queue_message(f"Error moving robot: {e}")
        return jsonify({"error": f"Failed to move robot: {str(e)}"}), 500

@flask_app.route('/execute_action', methods=['POST'])
def execute_action():
    """
    Handles execution of predefined actions selected from dropdown.
    Expects JSON with an 'action' field containing an integer 0-14.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    action = data.get('action')

    try:
        action = int(action)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid action format."}), 400

    try:
        if action == 0:
            reset_positions()
        elif action == 1:
            step_forward()
        elif action == 2:
            step_backward()
        elif action == 3:
            turn_right()
        elif action == 4:
            turn_left()
        elif action == 5:
            right_hi()
        elif action == 6:
            laugh()
        elif action == 7:
            swing_legs()
        elif action == 8:
            pezz_dispenser()
        elif action == 9:
            now()
        elif action == 10:
            balance()
        elif action == 11:
            mic_drop()
        elif action == 12:
            monster()
        elif action == 13:
            pose()
        elif action == 14:
            bow()
        else:
            return jsonify({"error": "Invalid action number."}), 400

        return jsonify({"success": True, "message": f"Action {action} executed successfully."}), 200

    except Exception as e:
        queue_message(f"Error executing action: {e}")
        return jsonify({"error": f"Failed to execute action: {str(e)}"}), 500

def parse_config_with_comments(file_path):
    """Parse config file and extract comments for each field"""
    comments = {}
    
    if not os.path.exists(file_path):
        return comments
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    current_section = None
    pending_comment = []
    
    for line in lines:
        stripped = line.strip()
        
        # Track section
        if stripped.startswith('[') and ']' in stripped:
            current_section = stripped[1:stripped.index(']')]
            # Extract inline comment for section
            if '#' in stripped:
                section_comment = stripped.split('#', 1)[1].strip()
                comments[f"{current_section}.__section__"] = section_comment
            pending_comment = []
        # Collect comment lines
        elif stripped.startswith('#'):
            pending_comment.append(stripped[1:].strip())
        # Parse field with value
        elif '=' in stripped and current_section:
            field_name = stripped.split('=')[0].strip()
            
            # Get inline comment if exists
            inline_comment = ""
            if '#' in stripped.split('=', 1)[1]:
                inline_comment = stripped.split('#', 1)[1].strip()
            
            # Combine pending comments and inline comment
            full_comment = ' '.join(pending_comment)
            if inline_comment:
                full_comment = inline_comment if not full_comment else f"{full_comment} {inline_comment}"
            
            if full_comment:
                comments[f"{current_section}.{field_name}"] = full_comment
            
            pending_comment = []
        elif stripped == "":
            pending_comment = []
    
    return comments

@flask_app.route('/get_config', methods=['GET'])
def get_config():
    """
    Returns the current configuration with field options for dropdowns
    """
    import configparser
    
    # Define field options for dropdowns and hardcoded hints
    field_options = {
        # CONTROLS Section
        'CONTROLS.__section__': {'description': 'Controller settings'},
        'CONTROLS.controller_name': {'description': 'Name of the controller used for interaction'},
        'CONTROLS.enabled': {'description': 'Enable use of controller used for interaction'},
        'CONTROLS.voicemovement': {'description': 'Enable or disable movement via voice control'},
        
        # STT Section
        'STT.__section__': {'description': 'Speech-to-Text configuration'},
        'STT.wake_word': {'description': 'Wake word for activating the system'},
        'STT.sensitivity': {'description': 'Lower threshold (e.g., 1) is lenient; higher (e.g., 10) is strict for wake word detection'},
        'STT.stt_processor': {
            'options': ['vosk', 'faster-whisper', 'silero', 'fastrtc', 'external'],
            'description': 'vosk, faster-whisper, silero, fastrtc, or external'
        },
        'STT.external_url': {'description': 'URL for the STT server (if enabled)'},
        'STT.whisper_model': {
            'options': ['tiny', 'base', 'small', 'medium', 'large'],
            'description': 'Whisper model size'
        },
        'STT.vad_method': {
            'options': ['silero', 'rms'],
            'description': 'Voice activity detection method'
        },
        'STT.wake_word_processor': {
            'options': ['picovoice', 'pocketsphinx', 'fastrtc'],
            'description': 'Wake word detection processor'
        },
        'LLM.llm_backend': {
            'options': ['openai', 'tabby', 'ooba', 'deepinfra'],
            'description': 'LLM backend service'
        },
        'LLM.openai_model': {
            'description': 'OpenAI model to use for LLM if backend = openai (e.g., gpt-4o-mini, gpt-4o, gpt-3.5-turbo, gpt-4)'
        },
        'LLM.override_encoding_model': {
            'options': ['cl100k_base', 'p50k_base', 'r50k_base', 'gpt2'],
            'description': 'Token encoding model'
        },
        'LLM.functioncalling': {
            'options': ['llm', 'nb'],
            'description': 'Function calling method'
        },
        'TTS.ttsoption': {
            'options': ['espeak', 'piper', 'silero', 'alltalk', 'azure', 'elevenlabs', 'openai'],
            'description': 'Text-to-speech service'
        },
        'TTS.azure_region': {
            'options': ['eastus', 'westus', 'westus2', 'eastus2', 'centralus'],
            'description': 'Azure region for TTS'
        },
        'TTS.openai_voice': {
            'options': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            'description': 'OpenAI TTS voice'
        },
        'TTS.model_id': {
            'options': ['eleven_multilingual_v2', 'eleven_monolingual_v1', 'eleven_turbo_v2'],
            'description': 'ElevenLabs model ID'
        },
        'STABLE_DIFFUSION.service': {
            'options': ['automatic1111', 'openai'],
            'description': 'Image generation service'
        },
        'STABLE_DIFFUSION.sampler_name': {
            'options': ['Euler a', 'Euler', 'DPM++ 2M Karras', 'DPM++ SDE Karras', 'DDIM'],
            'description': 'Stable Diffusion sampler'
        },
        'UI.background_id': {
            'options': ['0', '1', '2', '3', '4', '5'],
            'description': 'Background animation (0=none, 1=image, 2=stars, 3-5=video)'
        },
        'UI.rotation': {
            'options': ['0', '90', '180', '270'],
            'description': 'Screen rotation in degrees'
        },
        'RAG.strategy': {
            'options': ['naive', 'hybrid'],
            'description': 'RAG retrieval strategy'
        },
        'SERVO.MOVEMENT_VERSION': {
            'options': ['V1', 'V2'],
            'description': 'Servo movement version'
        }
    }
    
    try:
        config_file = os.path.join(BASE_DIR, 'config.ini')
        template_file = os.path.join(BASE_DIR, 'config.ini.template')
        
        # Use template if config.ini doesn't exist
        file_to_read = config_file if os.path.exists(config_file) else template_file
        
        if not os.path.exists(file_to_read):
            return jsonify({"error": "No configuration file found"}), 404
        
        config = configparser.RawConfigParser()
        config.optionxform = str  # Preserve case
        config.read(file_to_read)
        
        # Convert to dictionary
        config_dict = {}
        for section in config.sections():
            config_dict[section] = dict(config[section])
        
        # Parse comments from template
        template_comments = parse_config_with_comments(template_file)
        
        # Merge comments with field_options
        for key, comment in template_comments.items():
            if key in field_options:
                # Keep existing dropdown options, just update description if not set
                if 'description' not in field_options[key] or not field_options[key]['description']:
                    field_options[key]['description'] = comment
            else:
                # Add new field option with just description
                field_options[key] = {'description': comment}
        
        return jsonify({
            "config": config_dict,
            "field_options": field_options
        })
    except Exception as e:
        queue_message(f"Error reading config: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route('/save_config', methods=['POST'])
def save_config():
    """
    Saves the configuration to config.ini
    """
    import configparser
    
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        
        data = request.get_json()
        config_file = os.path.join(BASE_DIR, 'config.ini')
        template_file = os.path.join(BASE_DIR, 'config.ini.template')
        
        # Read the template to get comments and structure
        template_config = configparser.RawConfigParser()
        template_config.optionxform = str  # Preserve case
        if os.path.exists(template_file):
            template_config.read(template_file)
        
        # Create new config
        new_config = configparser.RawConfigParser()
        new_config.optionxform = str  # Preserve case
        
        # If config.ini exists, read it first to preserve any custom sections
        if os.path.exists(config_file):
            new_config.read(config_file)
        
        # Update with new values from the request
        for section, fields in data.items():
            if not new_config.has_section(section):
                new_config.add_section(section)
            
            for key, value in fields.items():
                # Convert boolean to string
                if isinstance(value, bool):
                    value = str(value)
                new_config.set(section, key, str(value))
        
        # Write to file
        with open(config_file, 'w') as f:
            new_config.write(f)
        
        queue_message("INFO: Configuration saved successfully")
        return jsonify({"success": True, "message": "Configuration saved successfully"})
    
    except Exception as e:
        queue_message(f"Error saving config: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def start_flask_app():
    import eventlet
    import eventlet.wsgi
    queue_message("INFO: Starting Flask app with Eventlet...")
    eventlet.wsgi.server(
        eventlet.listen(("0.0.0.0", 5012)),
        flask_app,
        log_output=False  # Disable request logging.
    )