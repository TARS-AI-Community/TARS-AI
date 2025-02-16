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

# === Custom Modules ===
from modules.module_config import load_config
from modules.module_llm import get_completion
from modules.module_vision import get_image_caption_from_base64
from modules.module_tts import generate_tts_audio

# Suppress Flask logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
os.environ['WERKZEUG_RUN_MAIN'] = 'true'
os.environ["WAITERSS_LOG_LEVEL"] = "ERROR"

# If using eventlet or gevent with Flask-SocketIO
sio_logger = logging.getLogger('socketio')
sio_logger.setLevel(logging.ERROR)
engineio_logger = logging.getLogger('engineio')
engineio_logger.setLevel(logging.ERROR)

CONFIG = load_config()

# Frame dimensions (as requested)
FRAME_WIDTH = 500
FRAME_HEIGHT = 500

# swayamount: 1 means off (no sway), 10 means maximum sway.
swayamount = 1   # You can change this value from 1 to 10.

# Get the base directory where the script is running
sprite = 'tars'
emotion = 'zero'

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
character_path = CONFIG['CHAR']['character_card_path']
character_name = os.path.splitext(os.path.basename(character_path))[0]  # Extract filename without extension
 
CHARACTER_DIR = os.path.join(BASE_DIR, "character", character_name, "images", emotion)

# Load images using the absolute path
img_nottalking_open = Image.open(os.path.join(CHARACTER_DIR, f"{sprite}_nottalking_eyes_open.png")).convert("RGBA")
img_nottalking_closed = Image.open(os.path.join(CHARACTER_DIR, f"{sprite}_nottalking_eyes_closed.png")).convert("RGBA")
img_talking_open = Image.open(os.path.join(CHARACTER_DIR, f"{sprite}_talking_eyes_open.png")).convert("RGBA")
img_talking_closed = Image.open(os.path.join(CHARACTER_DIR, f"{sprite}_talking_eyes_closed.png")).convert("RGBA")

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

current_frame = None
frame_lock = threading.Lock()

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
    #print('Client connected')
    socketio.start_background_task(send_heartbeat)
    #if IDLE_MSGS_enabled == "True":
        #socketio.start_background_task(idle_msg) 

@socketio.on('heartbeat')
def handle_heartbeat(message):
    #print('Received heartbeat from client')
    pass

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@flask_app.route('/')
def index():
    ipadd = "http://192.168.2.218:5012"
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
    
    print(jsonify({'talkinghead_base_url': f"http://{local_ip}:5012"}))
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
    #print("DEBUG: Talking mode enabled.")
    return Response("started", status=200)

@flask_app.route('/stop_talking')
def stop_talking_endpoint():
    global is_talking
    is_talking = False
    #print("DEBUG: Talking mode disabled.")
    return Response("stopped", status=200)

@flask_app.route('/process_llm', methods=['POST'])
def receive_user_message():
    global latest_text_to_read

    user_message = request.form['message']
    reply = get_completion(user_message)
    latest_text_to_read = reply
    socketio.emit('bot_message', {'message': latest_text_to_read})
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
            print(f"Failed to open the image: {e}")
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
    global is_talking
    is_talking = False

    async def get_audio_chunks():
        """Generate and yield TTS audio chunks asynchronously."""
        if CONFIG['TTS']['voice_only'] == "True":
            extracted_text = re.findall(r'"(.*?)"', latest_text_to_read)
            final_text = ' '.join(extracted_text)
        else:
            final_text = latest_text_to_read

        async for chunk in generate_tts_audio(final_text, CONFIG['TTS']):
            yield chunk.getvalue()  # Convert BytesIO to raw bytes for streaming

    def generate():
        """Sync wrapper to consume the async generator properly."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async_gen = get_audio_chunks()

        try:
            # Iterate over async generator using `asyncio.run()`
            for chunk in loop.run_until_complete(consume_async_gen(async_gen)):
                yield chunk
        finally:
            loop.close()

    async def consume_async_gen(async_gen):
        """Helper function to fully iterate through an async generator."""
        return [chunk async for chunk in async_gen]  # Collect all chunks

    return Response(generate(), mimetype="audio/mpeg")


def start_flask_app():
    import eventlet
    import eventlet.wsgi
    print("INFO: Starting Flask app with Eventlet...")
    eventlet.wsgi.server(eventlet.listen(("0.0.0.0", 5012)), flask_app)