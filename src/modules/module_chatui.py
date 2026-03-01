#!/usr/bin/env python3
"""
ChatUI — Flask web interface for TARS-AI.

Avatar animation (blinking, talking) is handled entirely client-side in JavaScript.
The server serves sprite image files and pushes talking/emotion state via SocketIO.
"""

import os
import threading
import time
import logging
import json
import asyncio
import re
import base64
from collections import OrderedDict
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    Response,
    session,
    redirect,
    url_for
)
from flask_cors import CORS
from flask_socketio import SocketIO


# === Custom Modules ===
from modules.module_config import load_config
from modules.module_config import CONFIG_METADATA as CONFIG_UI_FIELDS
from modules.module_llm import get_completion
from modules.module_tts import generate_tts_audio
from modules.module_llm import detect_emotion
from modules.module_messageQue import queue_message, get_recent_logs
from modules.module_servoctl import *
from modules.module_movement_registry import get_names, get_names_by_type, LEGS_ONLY, HAS_ARMS, MOVEMENTS

# Vision is optional — only available if enabled and dependencies are installed
try:
    from modules.module_vision import get_image_caption_from_base64
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    get_image_caption_from_base64 = None
    queue_message("ChatUI: Vision module not available — image captioning disabled")

# WiFi manager — lazy-initialised
try:
    from modules.module_wifi import WiFiManager as _WiFiManagerClass
    _wifi_manager = _WiFiManagerClass()
    WIFI_AVAILABLE = True
except Exception as _wifi_err:
    _wifi_manager = None
    WIFI_AVAILABLE = False


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

emotion = 'neutral'

character_path = CONFIG['CHAR']['character_card_path']
character_name = os.path.splitext(os.path.basename(character_path))[0]
sprite = character_name

# Global state variables.
latest_text_to_read = ""
audio_chunks_dict = OrderedDict()
current_chunk_index = 0

def _get_sprite_urls(emo):
    """Return the 4 sprite filenames for a given emotion."""
    return {
        "nottalking_open": f"{sprite}_{emo}_nottalking_eyes_open.png",
        "nottalking_closed": f"{sprite}_{emo}_nottalking_eyes_closed.png",
        "talking_open": f"{sprite}_{emo}_talking_eyes_open.png",
        "talking_closed": f"{sprite}_{emo}_talking_eyes_closed.png",
    }

# ----------------- Flask Setup -----------------

# Get the base directory where the script is running
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Moves up one directory
CHARACTER_DIR = os.path.join(BASE_DIR, "www", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "www", "static")


# Initialize Flask app with absolute paths
flask_app = Flask(__name__, template_folder=CHARACTER_DIR, static_url_path='/static', static_folder=STATIC_DIR)

# Track previous arm positions to determine movement direction
previous_arm_positions = {
    'left_main': 1,
    'left_forearm': 1,
    'left_hand': 1,
    'right_main': 1,
    'right_forearm': 1,
    'right_hand': 1
}

flask_app.secret_key = os.getenv("FLASK_SECRET_KEY", "tars_default_secret_key_8822")

# Authentication requirement check
@flask_app.before_request
def check_auth():
    # Public routes that don't require login
    if request.path.startswith('/static') or request.path.startswith('/socket.io') or request.path == '/login' or not CONFIG['CHATUI'].get('enabled', True):
        return
        
    # Check if user is logged in
    if not session.get('logged_in'):
        return redirect(url_for('login'))

CORS(flask_app)
socketio = SocketIO(flask_app, cors_allowed_origins="*", logger=False, engineio_logger=False)

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    pass

@flask_app.route('/')
def index():
    if WIFI_AVAILABLE and _wifi_manager:
        status = _wifi_manager.get_status()
        ipadd = status.get('ip') or '0.0.0.0'
    else:
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ipadd = s.getsockname()[0]
        except OSError:
            ipadd = '10.42.0.1'
    return render_template('index.html',
                           char_name=character_name,
                           char_greeting='Welcome back',
                           talkinghead_base_url=ipadd,
                           port=CONFIG['CHATUI'].get('port', 5012))

@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        correct_password = CONFIG['CHATUI'].get('password', 'tars')
        
        if password == correct_password:
            session['logged_in'] = True
            session.permanent = True  # Maintain cookie presence
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid password", char_name=character_name)

    return render_template('login.html', char_name=character_name)

@flask_app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

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
    
    #queue_message(jsonify({'talkinghead_base_url': f"http://{local_ip}:{CONFIG['CHATUI'].get('port', 5012)}"}))
    return jsonify({'talkinghead_base_url': f"http://{local_ip}:{CONFIG['CHATUI'].get('port', 5012)}"})

@flask_app.route('/avatar_sprites')
def avatar_sprites():
    """Return JSON with the 4 sprite URLs for the current emotion."""
    sprites = _get_sprite_urls(emotion)
    base = f"/character_sprite/{emotion}/animation/"
    return jsonify({k: base + v for k, v in sprites.items()})

@flask_app.route('/character_sprite/<emo>/animation/<filename>')
def character_sprite(emo, filename):
    """Serve a character sprite image file."""
    from flask import send_from_directory
    sprite_dir = os.path.join(BASE_DIR, "character", character_name, "images", emo, "animation")
    return send_from_directory(sprite_dir, filename)

@flask_app.route('/start_talking')
def start_talking_endpoint():
    socketio.emit('talking_state', {'talking': True})
    return Response("started", status=200)

@flask_app.route('/stop_talking')
def stop_talking_endpoint():
    socketio.emit('talking_state', {'talking': False})
    return Response("stopped", status=200)

@flask_app.route('/emotion', methods=['POST'])
def set_emotion():
    """
    Receives a single-word emotion and updates the stored emotion.
    Pushes new sprite URLs to connected clients via SocketIO.
    """
    global emotion
    detected_emotion = request.data.decode("utf-8").strip()

    if detected_emotion:
        # Check if the emotion folder exists, otherwise fallback to 'neutral'
        emo_dir = os.path.join(BASE_DIR, "character", character_name, "images", detected_emotion)
        if not os.path.exists(emo_dir):
            detected_emotion = "neutral"

        emotion = detected_emotion

        # Push new sprite URLs to all connected clients
        sprites = _get_sprite_urls(detected_emotion)
        base = f"/character_sprite/{detected_emotion}/animation/"
        socketio.emit('emotion_change', {k: base + v for k, v in sprites.items()})

        return jsonify({"message": "Emotion updated", "emotion": detected_emotion}), 200

    return jsonify({"error": "No emotion provided"}), 400

@flask_app.route('/process_llm', methods=['POST'])
def receive_user_message():
    global latest_text_to_read

    user_message = request.form.get('message', '')
    file = request.files.get('file')

    try:
        if file:
            buffer = BytesIO()
            file.save(buffer)
            buffer.seek(0)

            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            img_html = f'<img height="256" src="data:image/png;base64,{base64_image}"></img>'

            try:
                raw_image = Image.open(buffer).convert('RGB')
                if VISION_AVAILABLE:
                    caption = get_image_caption_from_base64(base64_image)
                else:
                    caption = "Image uploaded (vision module not available)"
            except UnidentifiedImageError as e:
                queue_message(f"Failed to open the image: {e}")
                caption = "Failed to process image"

            cmessage = f"*The Uploaded photo has the following description {caption}* and the user sent the following message with the photo: {user_message}"
            reply = get_completion(cmessage)
        else:
            reply = get_completion(user_message)

        latest_text_to_read = reply
        socketio.emit('bot_message', {'message': latest_text_to_read or ''})

        if CONFIG['EMOTION']['enabled'] and reply:
            detect_emotion(reply)

    except Exception as e:
        queue_message(f"ERROR: process_llm failed: {e}")
        socketio.emit('bot_message', {'message': f'Error processing message: {e}'})

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


        if VISION_AVAILABLE:
            caption = get_image_caption_from_base64(base64_image)
        else:
            caption = "Image uploaded (vision module not available)"
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
    global current_chunk_index
    socketio.emit('talking_state', {'talking': True})

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
    Expects JSON with a 'direction' field containing one of: 
    'forward', 'backward', 'left', 'right' (fast mode)
    'forward_slow', 'backward_slow', 'left_slow', 'right_slow' (slow mode)
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    direction = data.get('direction')
    
    valid_directions = ['forward', 'backward', 'left', 'right', 
                       'forward_slow', 'backward_slow', 'left_slow', 'right_slow']
    
    if direction not in valid_directions:
        return jsonify({"error": f"Invalid direction. Must be one of: {', '.join(valid_directions)}"}), 400
    
    # Execute the robot movement command
    try:
        # Fast movements
        if direction == 'forward':
            step_forward()
        elif direction == 'backward':
            step_backward()
        elif direction == 'left':
            turn_left()
        elif direction == 'right':
            turn_right()
        # Slow movements
        elif direction == 'forward_slow':
            walk_forward()
        elif direction == 'backward_slow':
            walk_backward()
        elif direction == 'left_slow':
            turn_left_slow()
        elif direction == 'right_slow':
            turn_right_slow()
            
        return jsonify({"success": True, "message": f"Robot moved {direction}"}), 200
        
    except Exception as e:
        queue_message(f"Error moving robot: {e}")
        return jsonify({"error": f"Failed to move robot: {str(e)}"}), 500

@flask_app.route('/get_movements', methods=['GET'])
def get_movements():
    """
    Returns available movements from the registry, organized by type.
    """
    try:
        # Build the movements list with reset_positions first
        movements = [{"id": "reset_positions", "name": "Reset Position", "type": "system"}]
        
        # Add legs-only movements
        for func_name, info in MOVEMENTS.items():
            movements.append({
                "id": func_name,
                "name": info["name"],
                "type": info["type"]
            })
        
        return jsonify({
            "success": True,
            "movements": movements,
            "legs_only": [{"id": k, "name": v["name"]} for k, v in MOVEMENTS.items() if v["type"] == LEGS_ONLY],
            "has_arms": [{"id": k, "name": v["name"]} for k, v in MOVEMENTS.items() if v["type"] == HAS_ARMS]
        }), 200
        
    except Exception as e:
        queue_message(f"Error getting movements: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route('/execute_action', methods=['POST'])
def execute_action():
    """
    Handles execution of predefined actions selected from dropdown.
    Expects JSON with an 'action' field containing a movement function name.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    action = data.get('action')

    if not action:
        return jsonify({"error": "No action specified."}), 400

    try:
        # Handle reset_positions specially
        if action == "reset_positions":
            reset_positions()
            return jsonify({"success": True, "message": "Reset positions executed successfully."}), 200
        
        # Check if action exists in the movement registry
        if action in MOVEMENTS:
            # Get the function from globals (imported from module_servoctl)
            if action in globals():
                func = globals()[action]
                func()
                return jsonify({"success": True, "message": f"{MOVEMENTS[action]['name']} executed successfully."}), 200
            else:
                return jsonify({"error": f"Movement function '{action}' not found."}), 400
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400

    except Exception as e:
        queue_message(f"Error executing action: {e}")
        return jsonify({"error": f"Failed to execute action: {str(e)}"}), 500

@flask_app.route('/move_legs', methods=['POST'])
def move_legs_endpoint():
    """
    Handles direct leg servo control.
    Expects JSON with fields: left_height, right_height, left_leg, right_leg, speed
    Each value should be between 1-100, with 50 being neutral.
    Speed should be between 0.5 and 1.
    """
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    
    try:
        left_height = int(data.get('left_height', 50))
        right_height = int(data.get('right_height', 50))
        left_leg = int(data.get('left_leg', 50))
        right_leg = int(data.get('right_leg', 50))
        speed = float(data.get('speed', 0.5))
        
        # Validate values are within range
        for value, name in [(left_height, 'left_height'), (right_height, 'right_height'), 
                            (left_leg, 'left_leg'), (right_leg, 'right_leg')]:
            if not (5 <= value <= 100):
                return jsonify({"error": f"{name} must be between 5 and 100"}), 400
        
        # Validate speed range
        if not (0.65 <= speed <= 1.0):
            return jsonify({"error": "speed must be between 0.65 and 1"}), 400
        
        # Call the move_legs function from module_servoctl
        move_legs(left_height, right_height, left_leg, right_leg, speed)
        
        return jsonify({
            "success": True, 
            "message": "Leg positions updated",
            "values": {
                "left_height": left_height,
                "right_height": right_height,
                "left_leg": left_leg,
                "right_leg": right_leg,
                "speed": speed
            }
        }), 200
        
    except Exception as e:
        queue_message(f"Error moving legs: {e}")
        return jsonify({"error": f"Failed to move legs: {str(e)}"}), 500

@flask_app.route('/disable_servos', methods=['POST'])
def disable_servos_endpoint():
    """
    Disables all servos
    """
    try:
        disable_all_servos()
        return jsonify({
            "success": True, 
            "message": "All servos disabled"
        }), 200
        
    except Exception as e:
        queue_message(f"Error disabling servos: {e}")
        return jsonify({"error": f"Failed to disable servos: {str(e)}"}), 500

@flask_app.route('/reset_positions', methods=['POST'])
def reset_positions_endpoint():
    """
    Calls reset_positions from module_servoctl
    """
    try:
        reset_positions()
        return jsonify({
            "success": True, 
            "message": "Positions reset"
        }), 200
        
    except Exception as e:
        queue_message(f"Error resetting positions: {e}")
        return jsonify({"error": f"Failed to reset positions: {str(e)}"}), 500

@flask_app.route('/neutral_legs', methods=['POST'])
def neutral_legs_endpoint():
    """
    Calls neutral_legs from module_servoctl
    """
    try:
        neutral_legs()
        return jsonify({
            "success": True, 
            "message": "Legs neutralized"
        }), 200
        
    except Exception as e:
        queue_message(f"Error neutralizing legs: {e}")
        return jsonify({"error": f"Failed to neutralize legs: {str(e)}"}), 500



@flask_app.route('/move_arms', methods=['POST'])
def move_arms_endpoint():
    """
    Handles direct arm servo control with leg sequence and sequential movement.
    Opens legs before moving arms, moves servos in sequence to avoid mechanical conflicts.
    - Increasing values: Main → Forearm → Hand
    - Decreasing values: Hand → Forearm → Main
    """
    global previous_arm_positions
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    
    try:
        left_main = int(data.get('left_main', 1))
        left_forearm = int(data.get('left_forearm', 1))
        left_hand = int(data.get('left_hand', 1))
        right_main = int(data.get('right_main', 1))
        right_forearm = int(data.get('right_forearm', 1))
        right_hand = int(data.get('right_hand', 1))
        speed = float(data.get('speed', 0.85))
        
        # Validate values are within range
        for value, name in [(left_main, 'left_main'), (left_forearm, 'left_forearm'), 
                            (left_hand, 'left_hand'), (right_main, 'right_main'),
                            (right_forearm, 'right_forearm'), (right_hand, 'right_hand')]:
            if not (1 <= value <= 100):
                return jsonify({"error": f"{name} must be between 1 and 100"}), 400
        
        # Validate speed range
        if not (0.65 <= speed <= 1.0):
            return jsonify({"error": "speed must be between 0.65 and 1"}), 400
        
        # Get previous positions
        prev_left_main = previous_arm_positions['left_main']
        prev_left_forearm = previous_arm_positions['left_forearm']
        prev_left_hand = previous_arm_positions['left_hand']
        prev_right_main = previous_arm_positions['right_main']
        prev_right_forearm = previous_arm_positions['right_forearm']
        prev_right_hand = previous_arm_positions['right_hand']
        
        # Check if arms need to move
        left_arm_moving = (left_main != 1 or left_forearm != 1 or left_hand != 1)
        right_arm_moving = (right_main != 1 or right_forearm != 1 or right_hand != 1)
        
        # Open left leg if left arm needs to move
        if left_arm_moving:
            move_legs(80, None, None, None, 0.9)  # Raise left height
            move_legs(80, None, 65, None, 0.9)    # Open left leg
        
        # Open right leg if right arm needs to move
        if right_arm_moving:
            move_legs(None, 80, None, None, 0.9)  # Raise right height
            move_legs(None, 80, None, 65, 0.9)    # Open right leg
        
        # Determine movement direction for left arm
        left_increasing = (left_main + left_forearm + left_hand) > (prev_left_main + prev_left_forearm + prev_left_hand)
        
        # Determine movement direction for right arm
        right_increasing = (right_main + right_forearm + right_hand) > (prev_right_main + prev_right_forearm + prev_right_hand)
        
        # Move left arm in sequence
        if left_increasing:
            # Increasing: Main → Forearm → Hand
            if left_main != prev_left_main:
                move_arm(left_main, None, None, None, None, None, speed)
            if left_forearm != prev_left_forearm:
                move_arm(None, left_forearm, None, None, None, None, speed)
            if left_hand != prev_left_hand:
                move_arm(None, None, left_hand, None, None, None, speed)
        else:
            # Decreasing: Hand → Forearm → Main
            if left_hand != prev_left_hand:
                move_arm(None, None, left_hand, None, None, None, speed)
            if left_forearm != prev_left_forearm:
                move_arm(None, left_forearm, None, None, None, None, speed)
            if left_main != prev_left_main:
                move_arm(left_main, None, None, None, None, None, speed)
        
        # Move right arm in sequence
        if right_increasing:
            # Increasing: Main → Forearm → Hand
            if right_main != prev_right_main:
                move_arm(None, None, None, right_main, None, None, speed)
            if right_forearm != prev_right_forearm:
                move_arm(None, None, None, None, right_forearm, None, speed)
            if right_hand != prev_right_hand:
                move_arm(None, None, None, None, None, right_hand, speed)
        else:
            # Decreasing: Hand → Forearm → Main
            if right_hand != prev_right_hand:
                move_arm(None, None, None, None, None, right_hand, speed)
            if right_forearm != prev_right_forearm:
                move_arm(None, None, None, None, right_forearm, None, speed)
            if right_main != prev_right_main:
                move_arm(None, None, None, right_main, None, None, speed)
        
        # Update previous positions
        previous_arm_positions['left_main'] = left_main
        previous_arm_positions['left_forearm'] = left_forearm
        previous_arm_positions['left_hand'] = left_hand
        previous_arm_positions['right_main'] = right_main
        previous_arm_positions['right_forearm'] = right_forearm
        previous_arm_positions['right_hand'] = right_hand
        
        # Check if arms are back at neutral
        left_arm_neutral = (left_main == 1 and left_forearm == 1 and left_hand == 1)
        right_arm_neutral = (right_main == 1 and right_forearm == 1 and right_hand == 1)
        
        # Close left leg if left arm is at neutral (all values = 1)
        if left_arm_neutral:
            move_legs(80, None, 50, None, 0.9)    # Close left leg
            move_legs(50, None, None, None, 0.9)  # Lower left height
        
        # Close right leg if right arm is at neutral (all values = 1)
        if right_arm_neutral:
            move_legs(None, 80, None, 50, 0.9)    # Close right leg
            move_legs(None, 50, None, None, 0.9)  # Lower right height
        
        return jsonify({
            "success": True, 
            "message": "Arm positions updated with sequential movement",
            "values": {
                "left_main": left_main,
                "left_forearm": left_forearm,
                "left_hand": left_hand,
                "right_main": right_main,
                "right_forearm": right_forearm,
                "right_hand": right_hand,
                "speed": speed
            }
        }), 200
        
    except Exception as e:
        queue_message(f"Error moving arms: {e}")
        return jsonify({"error": f"Failed to move arms: {str(e)}"}), 500



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
    import configparser
    
    try:
        config_file = os.path.join(BASE_DIR, 'config.ini')
        template_file = os.path.join(BASE_DIR, 'config.ini.template')
        
        file_to_read = config_file if os.path.exists(config_file) else template_file
        
        if not os.path.exists(file_to_read):
            return jsonify({"error": "No configuration file found"}), 404
        
        config = configparser.RawConfigParser()
        config.optionxform = str
        config.read(file_to_read)
        
        filtered_config = {}
        field_options = {}
        
        for section_name, section_def in CONFIG_UI_FIELDS.items():
            if section_name not in config.sections():
                continue
            
            if '__description__' in section_def:
                field_options[f"{section_name}.__section__"] = {
                    'description': section_def['__description__']
                }
            
            filtered_config[section_name] = {}
            
            for field_name, field_def in section_def.items():
                if field_name.startswith('__'):
                    continue
                
                if field_name in config[section_name]:
                    filtered_config[section_name][field_name] = config[section_name][field_name]
                    
                    field_key = f"{section_name}.{field_name}"
                    field_options[field_key] = {}
                    
                    if 'options' in field_def:
                        field_options[field_key]['options'] = field_def['options']
                    if 'description' in field_def:
                        field_options[field_key]['description'] = field_def['description']
                    if 'type' in field_def:
                        field_options[field_key]['type'] = field_def['type']
        
        return jsonify({
            "config": filtered_config,
            "field_options": field_options
        })
    except Exception as e:
        queue_message(f"Error reading config: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route('/save_config', methods=['POST'])
def save_config():
    """
    Saves the configuration to config.ini using TARS Configuration Management System
    """
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        
        data = request.get_json()
        
        # Import the TARS CMS integration from module_config
        from modules.module_config import update_config_from_web_ui
        
        # Use TARS CMS to save configuration
        result = update_config_from_web_ui(data, create_backup=True)
        
        if result["success"]:
            queue_message(f"INFO: Configuration saved successfully using TARS CMS - {result['message']}")
            if result.get("backup_location"):
                queue_message(f"INFO: Backup created at {result['backup_location']}")
            
            return jsonify({
                "success": True, 
                "message": result["message"],
                "actions_taken": result.get("actions_taken", []),
                "backup_location": result.get("backup_location"),
                "tars_cms_enabled": True
            })
        else:
            queue_message(f"ERROR: Configuration save failed - {result['message']}")
            return jsonify({
                "success": False, 
                "error": result["message"],
                "errors": result.get("errors", []),
                "tars_cms_enabled": True
            }), 500
    
    except Exception as e:
        queue_message(f"ERROR: Configuration save error - {str(e)}")
        return jsonify({
            "success": False, 
            "error": str(e),
            "tars_cms_enabled": False
        }), 500


@flask_app.route('/config_sync_status', methods=['GET'])
def config_sync_status():
    """
    Get configuration synchronization status using TARS CMS
    """
    try:
        from modules.module_config import get_config_sync_status
        
        status = get_config_sync_status()
        
        return jsonify({
            "success": True,
            "sync_status": status,
            "tars_cms_enabled": True
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "tars_cms_enabled": False
        }), 500



@flask_app.route('/api/wifi/status', methods=['GET'])
def wifi_status():
    if not WIFI_AVAILABLE:
        return jsonify({"mode": "disconnected", "ssid": None, "ip": None, "signal": 0})
    try:
        return jsonify(_wifi_manager.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/wifi/networks', methods=['GET'])
def wifi_networks():
    if not WIFI_AVAILABLE:
        return jsonify({"networks": []})
    try:
        networks = _wifi_manager.scan_networks()
        return jsonify({"networks": networks})
    except Exception as e:
        return jsonify({"error": str(e), "networks": []}), 500


@flask_app.route('/api/wifi/connect', methods=['POST'])
def wifi_connect():
    if not WIFI_AVAILABLE:
        return jsonify({"success": False, "error": "WiFi module unavailable"}), 503
    data = request.get_json(silent=True) or {}
    ssid     = data.get('ssid', '').strip()
    password = data.get('password', '')
    username = data.get('username', '').strip()
    if not ssid:
        return jsonify({"success": False, "error": "ssid required"}), 400
    try:
        if username:
            ok = _wifi_manager.connect_enterprise(ssid, username, password)
        else:
            ok = _wifi_manager.connect(ssid, password)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@flask_app.route('/api/wifi/hotspot', methods=['PUT'])
def wifi_hotspot():
    if not WIFI_AVAILABLE:
        return jsonify({"success": False, "error": "WiFi module unavailable"}), 503
    try:
        status = _wifi_manager.get_status()
        if status.get('mode') == 'hotspot':
            ok = _wifi_manager.stop_hotspot()
            action = 'stopped'
        else:
            ok = _wifi_manager.start_hotspot()
            action = 'started'
        return jsonify({"success": ok, "action": action})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@flask_app.route('/api/eyes/mood', methods=['POST'])
def eyes_set_mood():
    import modules.UI.apps.module_app_eyes as _eyes_mod
    data = request.get_json(silent=True) or {}
    mood_name = data.get('mood', '').upper()
    try:
        from modules.module_eyes import Mood
        mood = Mood[mood_name]
        _eyes_mod.set_mood_request(mood)
        return jsonify({'success': True, 'mood': mood_name})
    except KeyError:
        return jsonify({'success': False, 'error': f'Unknown mood: {mood_name}'}), 400


# ── NEXUS DASHBOARD ENDPOINTS ──────────────────────────────────────────────

@flask_app.route('/api/system/metrics', methods=['GET'])
def system_metrics():
    """System metrics for the NEXUS dashboard tab."""
    metrics = {}

    # CPU load (1-min average as percentage of cores)
    try:
        load_avg = os.getloadavg()
        cpu_count = os.cpu_count() or 4
        metrics['cpu_load'] = round((load_avg[0] / cpu_count) * 100, 1)
    except Exception:
        metrics['cpu_load'] = 0

    # RAM usage
    try:
        with open('/proc/meminfo') as f:
            lines = f.readlines()
        mem_total = int(lines[0].split()[1])
        mem_available = int(lines[2].split()[1])
        metrics['ram_usage'] = round((1 - mem_available / mem_total) * 100, 1)
        metrics['ram_total_mb'] = round(mem_total / 1024)
    except Exception:
        metrics['ram_usage'] = 0
        metrics['ram_total_mb'] = 0

    # CPU temperature
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            metrics['cpu_temp'] = round(int(f.read().strip()) / 1000, 1)
    except Exception:
        metrics['cpu_temp'] = 0

    # Uptime
    try:
        with open('/proc/uptime') as f:
            metrics['uptime_secs'] = round(float(f.read().split()[0]))
    except Exception:
        metrics['uptime_secs'] = 0

    # Current emotion state
    metrics['emotion'] = emotion or 'neutral'

    # Battery (optional — may not be available on all hardware)
    try:
        from modules.module_battery import get_battery_status
        batt = get_battery_status()
        metrics['battery'] = {
            'percentage': batt.get('normalized_percentage', batt.get('percentage', 0)),
            'voltage': batt.get('voltage', 0),
            'charging': batt.get('is_charging', False),
            'state': batt.get('charging_state', 'UNKNOWN'),
        }
    except Exception:
        metrics['battery'] = None

    # Character info
    metrics['character'] = character_name

    return jsonify(metrics)


@flask_app.route('/api/memory/stats', methods=['GET'])
def memory_stats():
    """Memory/knowledge graph statistics for the NEXUS dashboard."""
    stats = {'topics': 0, 'memories': 0, 'topic_list': []}

    # Try to load topic index
    try:
        topic_path = os.path.join(BASE_DIR, '..', 'memory', f'{character_name}_topics.json')
        if os.path.exists(topic_path):
            with open(topic_path, 'r') as f:
                topics = json.load(f)
            stats['topics'] = len(topics)
            stats['topic_list'] = topics[:20]  # last 20 topics
    except Exception:
        pass

    # Try to get memory count
    try:
        memory_dir = os.path.join(BASE_DIR, '..', 'memory')
        lite_path = os.path.join(memory_dir, f'{character_name}_lite.json')
        if os.path.exists(lite_path):
            with open(lite_path, 'r') as f:
                memories = json.load(f)
            stats['memories'] = len(memories)
    except Exception:
        pass

    return jsonify(stats)


@flask_app.route('/api/console/logs', methods=['GET'])
def console_logs():
    """Stream terminal output to the WebUI nexus console."""
    since = request.args.get('since', 0, type=int)
    lines, head = get_recent_logs(since)
    return jsonify({'lines': lines, 'head': head})


def start_flask_app(port=None):
    if port is None:
        port = CONFIG['CHATUI'].get('port', 5012)
    import eventlet
    import eventlet.wsgi
    queue_message(f"INFO: Starting Flask app on port {port} with Eventlet...")
    eventlet.wsgi.server(
        eventlet.listen(("0.0.0.0", port)),
        flask_app,
        log_output=False  # Disable request logging.
    )