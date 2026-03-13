#!/usr/bin/env python3
"""
ChatUI — Flask web interface for TARS-AI.

Avatar animation (blinking, talking) is handled entirely client-side in JavaScript.
The server serves sprite image files and pushes talking/emotion state via SocketIO.
"""

import os
import sys
import shutil
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

import configparser

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    Response,
    session,
    redirect,
    url_for,
    send_file,
    send_from_directory,
)
from flask_cors import CORS
from flask_socketio import SocketIO


# === Custom Modules ===
from modules.module_config import load_config
from modules.module_config import CONFIG_METADATA as CONFIG_UI_FIELDS
from modules.module_llm import get_completion, process_completion, _sanitize_for_tts
import modules.module_llm as _llm_mod
from modules.module_tts import generate_tts_audio, SentenceTTSPipeline
from modules.module_llm import detect_emotion, detect_emotion_from_llm, classifier as emotion_classifier
from modules.module_messageQue import queue_message, get_recent_logs
from modules.module_servoctl import *
from modules.module_movement_registry import get_names, get_names_by_type, LEGS_ONLY, HAS_ARMS, MOVEMENTS

# Vision is optional — only available if enabled and dependencies are installed
try:
    from modules.module_vision import process_image
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    process_image = None
    queue_message("ChatUI: Vision module not available — image captioning disabled")

# WiFi manager — background-initialised to avoid blocking boot
try:
    from modules.module_wifi import WiFiManager as _WiFiManagerClass
    _wifi_manager = None
    WIFI_AVAILABLE = True

    def _init_wifi_bg():
        global _wifi_manager
        try:
            _wifi_manager = _WiFiManagerClass()
        except Exception:
            pass  # _wifi_manager stays None; routes guard against this

    threading.Thread(target=_init_wifi_bg, daemon=True, name="wifi-init").start()
except ImportError:
    _wifi_manager = None
    WIFI_AVAILABLE = False


# Suppress Flask logs and startup banner
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
import flask.cli
flask.cli.show_server_banner = lambda *_: None

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
_audio_state_lock = threading.Lock()  # Protects audio_chunks_dict + current_chunk_index

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
flask_app.json.sort_keys = False

# Track previous arm positions to determine movement direction
previous_arm_positions = {
    'left_main': 1,
    'left_forearm': 1,
    'left_hand': 1,
    'right_main': 1,
    'right_forearm': 1,
    'right_hand': 1
}

def _get_secret_key():
    """Auto-generate a unique secret key per device, persisted in .env."""
    key = os.getenv("FLASK_SECRET_KEY")
    if key:
        return key
    import secrets
    key = secrets.token_hex(32)
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    try:
        with open(env_path, 'a') as f:
            f.write(f'\n# Auto-generated Flask secret key (unique per device)\nFLASK_SECRET_KEY="{key}"\n')
        os.environ["FLASK_SECRET_KEY"] = key
    except OSError:
        pass
    return key

flask_app.secret_key = _get_secret_key()

# Authentication requirement check
@flask_app.before_request
def check_auth():
    # Public routes that don't require login
    if request.path.startswith('/static') or request.path.startswith('/socket.io') or request.path in ('/login', '/emotion', '/start_talking', '/stop_talking') or not CONFIG['ACCESS'].get('webui_enabled', True):
        return
        
    # Check if user is logged in
    if not session.get('logged_in'):
        return redirect(url_for('login'))

CORS(flask_app)
socketio = SocketIO(flask_app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)


@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    pass

@socketio.on('client_debug')
def handle_client_debug(msg):
    queue_message(f"[BROWSER] {msg}")

@socketio.on('browser_audio')
def handle_browser_audio(data):
    """Receive audio from browser, transcribe with local STT (sherpa-onnx) or OpenAI Whisper."""
    import numpy as np
    try:
        audio_b64 = data.get('audio', '') if isinstance(data, dict) else ''
        if not audio_b64:
            socketio.emit('browser_transcription', {'text': '', 'error': 'No audio data'})
            return

        audio_bytes = base64.b64decode(audio_b64)
        if len(audio_bytes) < 1000:
            socketio.emit('browser_transcription', {'text': ''})
            return

        sample_rate = int(data.get('sample_rate', 16000))

        # Check RMS — reject silence
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        rms = np.sqrt(np.mean(audio_np.astype(np.float64) ** 2))
        if rms < 200:
            socketio.emit('browser_transcription', {'text': ''})
            return

        # Try local STT first (sherpa-onnx via the existing STTManager)
        text = _browser_transcribe_local(audio_np, sample_rate)

        # Fall back to OpenAI Whisper if local STT unavailable
        if text is None:
            text = _browser_transcribe_openai(audio_bytes, sample_rate)

        if text is None:
            socketio.emit('browser_transcription', {'text': '', 'error': 'No STT backend available (no local sherpa-onnx and no OPENAI_API_KEY)'})
            return

        text = text.strip()
        if text:
            queue_message(f"[BROWSER STT] {text}")

            # Submit audio to speaker ID for voice identification (browser voice mode)
            try:
                from modules.module_speaker_id import get_speaker_id_manager
                sid = get_speaker_id_manager()
                if sid and sid.enabled:
                    audio_float32 = audio_np.astype(np.float32) / 32768.0
                    sid.submit_audio(audio_float32, sample_rate)
            except Exception as e:
                queue_message(f"WARNING: Browser speaker ID failed: {e}")

        socketio.emit('browser_transcription', {'text': text})

    except Exception as e:
        queue_message(f"ERROR: browser_audio transcription failed: {e}")
        socketio.emit('browser_transcription', {'text': '', 'error': str(e)})


def _browser_transcribe_local(audio_np, sample_rate):
    """Transcribe using the local STTManager's sherpa-onnx recognizer. Returns text or None."""
    try:
        from modules.module_main import stt_manager
        if not stt_manager or not getattr(stt_manager, 'sherpa_recognizer', None):
            return None
        # _sherpa_transcribe_audio expects a list of int16 chunks
        transcript = stt_manager._sherpa_transcribe_audio([audio_np], sample_rate=sample_rate)
        return transcript if transcript else ''
    except Exception as e:
        queue_message(f"WARNING: Local STT failed for browser audio: {e}")
        return None


def _browser_transcribe_openai(audio_bytes, sample_rate):
    """Transcribe using OpenAI Whisper API. Returns text or None if no API key."""
    import tempfile, wave
    api_key = CONFIG['TTS']['openai_api_key'] if 'TTS' in CONFIG else ''
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)

    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)
    try:
        with open(tmp_path, 'rb') as f:
            response = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json"
            )
    finally:
        os.unlink(tmp_path)

    # Reject high no_speech_prob
    if hasattr(response, 'segments') and response.segments:
        avg_no_speech = sum(
            seg.get('no_speech_prob', 0) if isinstance(seg, dict)
            else getattr(seg, 'no_speech_prob', 0)
            for seg in response.segments
        ) / len(response.segments)
        if avg_no_speech > 0.5:
            return ''

    return response.text.strip() if hasattr(response, 'text') else ''

@socketio.on('show_qr')
def handle_show_qr(data):
    """Display QR code on the Pi screen overlay."""
    url = data.get('url', '') if isinstance(data, dict) else ''
    if not url:
        return
    try:
        import qrcode, tempfile, os
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#c0c0c0", back_color="#000000")
        tmp = os.path.join(tempfile.gettempdir(), 'tars_qr_overlay.png')
        img.save(tmp)
        # Try the OpenGL UI overlay first
        try:
            from modules.module_main import ui_manager
        except ImportError:
            ui_manager = None
        if ui_manager and hasattr(ui_manager, 'show_overlay_image'):
            ui_manager.show_overlay_image(tmp, duration=8)
        else:
            # Fallback: display on framebuffer/X11 using feh
            import subprocess, shutil
            if shutil.which('feh'):
                proc = subprocess.Popen(
                    ['feh', '--fullscreen', '--auto-zoom', '--hide-pointer', tmp],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                def _kill_feh():
                    import time
                    time.sleep(8)
                    proc.terminate()
                import threading
                threading.Thread(target=_kill_feh, daemon=True).start()
                queue_message("[CHATUI] QR displayed via feh fallback")
            else:
                queue_message("[CHATUI] No UI manager and feh not installed — cannot display QR on screen")
    except Exception as e:
        queue_message(f"[CHATUI] show_qr error: {e}")

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
                           port=CONFIG['ACCESS'].get('webui_port', 80),
                           user_name=CONFIG['CHAR'].get('user_name', 'User'),
                           webui_theme=CONFIG['ACCESS'].get('webui_theme', 'default'))

@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        correct_password = CONFIG['ACCESS'].get('webui_password', 'tarspass1234')
        
        if password == correct_password:
            session['logged_in'] = True
            session.permanent = True  # Maintain cookie presence
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid password", char_name=character_name,
                                       webui_theme=CONFIG['ACCESS'].get('webui_theme', 'default'))

    return render_template('login.html', char_name=character_name,
                           webui_theme=CONFIG['ACCESS'].get('webui_theme', 'default'))

@flask_app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@flask_app.route('/holo')
def holo():
    return render_template('holo.html')

@flask_app.route('/test/voice')
def test_voice():
    return render_template('test_voice.html')

@flask_app.route('/test/voice_pipeline', methods=['GET', 'POST'])
def test_voice_pipeline():
    """Test the server-side audio transcription pipeline without a browser.

    GET:  Generate a synthetic TTS audio clip and transcribe it (round-trip test).
    POST: Accept raw audio (base64 PCM or WAV file) and transcribe it.

    Returns JSON with the transcription result.
    Testable via: curl http://localhost/test/voice_pipeline
    """
    import tempfile, wave, numpy as np

    api_key = CONFIG['TTS']['openai_api_key'] if 'TTS' in CONFIG else ''
    if not api_key:
        api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({"status": "error", "message": "No OpenAI API key configured"}), 500

    from openai import OpenAI as _OAI
    client = _OAI(api_key=api_key)

    if request.method == 'POST':
        # Accept uploaded WAV file or base64 audio
        file = request.files.get('file')
        audio_b64 = request.form.get('audio', '')
        if file:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
                file.save(tmp_path)
        elif audio_b64:
            audio_bytes = base64.b64decode(audio_b64)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
                with wave.open(tmp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_bytes)
        else:
            return jsonify({"status": "error", "message": "No audio provided"}), 400
    else:
        # GET: Generate a test phrase with OpenAI TTS, then transcribe it
        test_phrase = "Hello, this is a voice pipeline test."
        queue_message(f"[TEST] Generating TTS for: {test_phrase}")
        tts_response = client.audio.speech.create(
            model="tts-1", voice="alloy", input=test_phrase,
            response_format="wav"
        )
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(tts_response.content)

    try:
        with open(tmp_path, 'rb') as f:
            response = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json"
            )
        text = response.text.strip() if hasattr(response, 'text') else ''
        queue_message(f"[TEST] Transcription result: {text}")
        result = {"status": "success", "transcription": text}
        if request.method == 'GET':
            result["test_phrase"] = test_phrase
            result["match"] = test_phrase.lower().rstrip('.') in text.lower()
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

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
    
    #queue_message(jsonify({'talkinghead_base_url': f"http://{local_ip}:{CONFIG['ACCESS'].get('webui_port', 80)}"}))
    return jsonify({'talkinghead_base_url': f"http://{local_ip}:{CONFIG['ACCESS'].get('webui_port', 80)}"})

@flask_app.route('/avatar_sprites')
def avatar_sprites():
    """Return JSON with the 4 sprite URLs for the current emotion."""
    sprites = _get_sprite_urls(emotion)
    base = f"/character_sprite/{emotion}/animation/"
    return jsonify({k: base + v for k, v in sprites.items()})

@flask_app.route('/character_sprite/<emo>/animation/<filename>')
def character_sprite(emo, filename):
    """Serve a character sprite image file."""
    sprite_dir = os.path.join(BASE_DIR, "character", character_name, "images", emo, "animation")
    return send_from_directory(sprite_dir, filename)

@flask_app.route('/start_talking')
def start_talking_endpoint():
    socketio.emit('talking_state', {'talking': True})
    _notify_avatar_talking(True)
    return Response("started", status=200)

@flask_app.route('/stop_talking')
def stop_talking_endpoint():
    socketio.emit('talking_state', {'talking': False})
    _notify_avatar_talking(False)
    return Response("stopped", status=200)

_EMOTION_TO_MOOD = {
    # happy / positive
    "happy":      "HAPPY",
    "joy":        "HAPPY",
    "excitement": "EXCITED",
    "excited":    "EXCITED",
    "love":       "LOVE",
    "optimism":   "HAPPY",
    "gratitude":  "HAPPY",
    "pride":      "HAPPY",
    "amusement":  "HAPPY",
    "admiration": "HAPPY",
    "approval":   "HAPPY",
    # sad / negative
    "sad":        "SAD",
    "sadness":    "SAD",
    "grief":      "SAD",
    "remorse":    "SAD",
    "disappointment": "SAD",
    "embarrassment":  "SHY",
    # angry
    "angry":      "ANGRY",
    "anger":      "ANGRY",
    "annoyance":  "ANNOYED",
    "disgust":    "DISGUSTED",
    "disapproval":"DISGUSTED",
    # afraid
    "afraid":     "AFRAID",
    "fear":       "AFRAID",
    "nervousness":"AFRAID",
    # sleepy / bored
    "sleepy":     "SLEEPY",
    "boredom":    "SLEEPY",
    # confused
    "confusion":  "CONFUSED",
    "curiosity":  "CURIOUS",
    "realization":"SURPRISED",
    # surprised
    "surprise":   "SURPRISED",
    # neutral / other
    "neutral":    "NEUTRAL",
    "caring":     "HAPPY",
    "desire":     "LOVE",
    "relief":     "HAPPY",
}

def update_emotion(detected_emotion):
    """Update the stored emotion, push new sprites to clients, and update RoboEyes."""
    global emotion
    if not detected_emotion:
        return

    # Sanitize to prevent path traversal via crafted emotion names
    detected_emotion = re.sub(r'[^a-zA-Z0-9_-]', '', detected_emotion)
    if not detected_emotion:
        return

    # Look up the eye mood from the original emotion BEFORE sprite fallback
    mood_name = _EMOTION_TO_MOOD.get(detected_emotion.lower(), "NEUTRAL")

    emo_dir = os.path.join(BASE_DIR, "character", character_name, "images", detected_emotion)
    if not os.path.exists(emo_dir):
        detected_emotion = "neutral"
    emotion = detected_emotion
    sprites = _get_sprite_urls(detected_emotion)
    base = f"/character_sprite/{detected_emotion}/animation/"
    socketio.emit('emotion_change', {k: base + v for k, v in sprites.items()})

    # Trigger RoboEyes mood to match the detected emotion
    try:
        import modules.UI.apps.module_app_eyes as _eyes_mod
        from modules.module_eyes import Mood
        _eyes_mod.set_mood_request(Mood[mood_name])
    except Exception:
        pass

    # Notify avatar app of emotion change
    try:
        import modules.UI.apps.module_app_avatar as _avatar_mod
        _avatar_mod.set_emotion_request(detected_emotion)
    except Exception:
        pass


def _notify_avatar_talking(is_talking: bool) -> None:
    """Notify the avatar app of a talking state change (best-effort)."""
    try:
        import modules.UI.apps.module_app_avatar as _avatar_mod
        _avatar_mod.set_talking_state(is_talking)
    except Exception:
        pass


def begin_bot_stream():
    """Signal web UI that a bot response is starting to stream (voice mode)."""
    try:
        socketio.emit('bot_stream_start', {})
    except Exception:
        pass


def stream_reply_token(text):
    """Push a streaming text chunk of the bot reply to the web UI."""
    try:
        socketio.emit('bot_token', {'text': text})
    except Exception:
        pass


def push_user_message(text, speaker_name=None):
    """Push a voice-mode user message to the web UI chat, including speaker name."""
    if not speaker_name:
        speaker_name = CONFIG['CHAR'].get('user_name', 'User')
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
            if sid and sid.enabled:
                name = sid.get_current_speaker()
                if name and not name.startswith("Unknown"):
                    speaker_name = name
        except Exception:
            pass
    try:
        socketio.emit('user_message', {'message': text, 'speaker': speaker_name})
    except Exception:
        pass


@flask_app.route('/emotion', methods=['POST'])
def set_emotion():
    """
    Receives a single-word emotion and updates the stored emotion.
    Pushes new sprite URLs to connected clients via SocketIO.
    """
    detected_emotion = request.data.decode("utf-8").strip()

    if detected_emotion:
        update_emotion(detected_emotion)
        return jsonify({"message": "Emotion updated", "emotion": detected_emotion}), 200

    return jsonify({"error": "No emotion provided"}), 400

def _process_chat_message(msg, img_b64):
    """Shared pipeline for WebUI text chat and voice mode — sends to LLM and emits response."""
    global latest_text_to_read
    try:
        # Resolve speaker for this WebUI message.
        # If speaker ID was just set by browser voice (handle_browser_audio),
        # use that result. Otherwise default to configured user for typed messages.
        try:
            from modules.module_speaker_id import get_speaker_id_manager
            sid = get_speaker_id_manager()
            if sid and sid.enabled:
                import time as _time
                # Wait for any in-progress speaker ID (e.g. from browser voice)
                identified = sid.wait_for_identification(timeout=1.5)
                if not identified:
                    queue_message("DEBUG: Browser speaker ID timed out (1.5s)")
                current = sid.get_current_speaker()
                # If no recent voice ID (typed message), set to config user
                age = _time.time() - (sid.last_identified_time or 0)
                if not current or current.startswith("Unknown") or age > 10:
                    with sid._lock:
                        sid.current_speaker = CONFIG['CHAR']['user_name']
                        sid.current_confidence = 1.0
                        sid.last_identified_time = _time.time()
        except Exception:
            pass
        _audio_streamed = False
        _reply_changed = False
        _followup_reply = None
        if img_b64:
            vision_mode = CONFIG['VISION'].get('vision_processor', 'blip')

            if vision_mode in ('llm', 'openai'):
                if CONFIG.get('debug_mode', False):
                    queue_message("DEBUG: Single-pass upload (image sent directly to LLM with prompt)")
                _llm_prompt = msg or "The user sent you a photo. Describe what you see and respond in character."
                _llm_image = img_b64
            else:
                if VISION_AVAILABLE:
                    try:
                        caption = process_image(img_b64, msg or "Describe this image in detail.")
                    except Exception as e:
                        queue_message(f"ERROR: Vision processing failed: {e}")
                        caption = "Image uploaded but vision processing failed"
                else:
                    caption = "Image uploaded (vision module not available)"

                if CONFIG.get('debug_mode', False):
                    queue_message(f"DEBUG: Two-pass upload (caption via {vision_mode}, then LLM)")
                if msg:
                    _llm_prompt = f"*The uploaded photo has the following description: {caption}* The user also said: {msg}"
                else:
                    _llm_prompt = f"*The user uploaded a photo. Description: {caption}*"
                _llm_image = img_b64
            # Fall through to streaming path below with _llm_prompt and _llm_image set
            msg = _llm_prompt

        # Stream tokens to web UI + TTS sentence-by-sentence to browser
        # (works for both text and image uploads — image is passed to process_completion)
        import modules.module_speed as speed
        speed.mark_utterance_start()

        begin_bot_stream()

        # Think-block stripping + delta tracking (same pattern as voice mode)
        _acc_raw = ['']
        _clean_seen = ['']

        def _sanitize_tts(text):
            text = _sanitize_for_tts(text)
            text = re.sub(r'[^a-zA-Z0-9\s.,?!;:"\'-<>]', '', text)
            return text.strip()

        async def _browser_tts_play(sentence, tts_option):
            """Generate TTS for a sentence and emit audio bytes to browser via SocketIO."""
            try:
                async for audio_chunk in generate_tts_audio(sentence, tts_option):
                    audio_chunk.seek(0)
                    audio_bytes = audio_chunk.read()
                    if audio_bytes:
                        encoded = base64.b64encode(audio_bytes).decode('ascii')
                        socketio.emit('bot_audio_chunk', {'data': encoded})
            except Exception as e:
                queue_message(f"ERROR: Browser TTS failed: {e}")
            return False  # No barge-in in browser

        def _on_first_browser_play():
            socketio.emit('talking_state', {'talking': True})
            _notify_avatar_talking(True)

        pipeline = SentenceTTSPipeline(
            CONFIG['TTS']['ttsoption'],
            sanitize=_sanitize_tts,
            on_first_play=_on_first_browser_play,
            play_func=_browser_tts_play,
        )
        pipeline.start()

        def _on_chunk(chunk, is_first):
            _acc_raw[0] += chunk
            # Strip completed <think> blocks
            clean_total = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL)
            if '<think>' in clean_total:
                return  # Unclosed think block, wait
            new_clean = clean_total[len(_clean_seen[0]):]
            _clean_seen[0] = clean_total
            if not new_clean:
                return
            stream_reply_token(new_clean)
            pipeline.feed(new_clean)
            if is_first:
                speed.mark_first_token()

        _llm_mod._reply_chunk_callback = _on_chunk
        try:
            parsed = process_completion(msg, image_b64=img_b64)
        finally:
            _llm_mod._reply_chunk_callback = None
            # Flush remaining text to pipeline
            remaining = pipeline.remainder.strip()
            if not remaining:
                full_clean = re.sub(r'<think>.*?</think>', '', _acc_raw[0], flags=re.DOTALL).strip()
                remaining = full_clean[len(_clean_seen[0]):].strip()
            pipeline.finish(remaining=remaining if remaining else None)

        if isinstance(parsed, dict):
            reply = parsed.get("reply", "") or ""
            if speed.enabled:
                timings = parsed.get('_timings', {})
                if timings:
                    ttft = timings.get('prompt_build', 0) + timings.get('llm_first_byte', 0)
                    speed.log(f"webui: ttft({speed.fmt(ttft)}), llm_stream({speed.fmt(timings.get('llm_stream', 0))}), parse({speed.fmt(timings.get('parse', 0))})")
            # Run side effects — may update parsed["reply"] (e.g. web search)
            from modules.module_llm import llm_execute_side_effects
            llm_execute_side_effects(parsed, msg, source="webui", has_image=img_b64 is not None)
            updated_reply = parsed.get("reply", "") or ""
            _reply_changed = (updated_reply != reply)
            if _reply_changed:
                _followup_reply = updated_reply
        else:
            reply = parsed or ""

        # Always mark as streamed so browser never falls back to legacy audio path
        # (which doesn't properly restart voice mode mic)
        _audio_streamed = bool(_acc_raw[0])

        # Send the streamed reply (what the user already saw) — keeps original bubble
        latest_text_to_read = reply
        socketio.emit('bot_message', {'message': reply or '', 'audio_streamed': True})

        detected = None
        detected_raw = None
        axis_scores = {}
        if CONFIG['EMOTION']['enabled'] and msg:
            _emo_method = CONFIG['EMOTION'].get('emotion_method', 'classifier')
            if _emo_method == 'llm':
                if isinstance(parsed, dict):
                    detected, detected_raw, axis_scores = detect_emotion_from_llm(parsed.get('emotion'))
                # else: LLM response wasn't valid JSON — skip emotion silently
            else:
                detected, detected_raw, axis_scores = detect_emotion(msg)
            if detected:
                update_emotion(detected)

        # Log interaction for dashboard analytics
        try:
            from modules.module_dashboard_data import log_interaction
            log_interaction(msg, reply, emotion=detected, emotion_raw=detected_raw, axis_scores=axis_scores, llm_response=parsed)
        except Exception:
            pass

        # Wait for streamed TTS to finish
        if _audio_streamed:
            pipeline.join()

        # If side effects produced new content (e.g. search results), show + speak as follow-up
        if _reply_changed and _followup_reply:
            followup = SentenceTTSPipeline(
                CONFIG['TTS']['ttsoption'],
                sanitize=_sanitize_tts,
                play_func=_browser_tts_play,
            )
            followup.start()
            followup.feed(_followup_reply)
            followup.finish()
            socketio.emit('bot_message', {'message': _followup_reply, 'audio_streamed': True})
            followup.join()

        # Always emit bot_audio_done so voice mode mic can restart
        socketio.emit('bot_audio_done', {})
        socketio.emit('talking_state', {'talking': False})
        _notify_avatar_talking(False)

    except Exception as e:
        queue_message(f"ERROR: process_llm failed: {e}")
        socketio.emit('bot_message', {'message': f'Error processing message: {e}', 'audio_streamed': True})
        socketio.emit('bot_audio_done', {})
        socketio.emit('talking_state', {'talking': False})
        _notify_avatar_talking(False)

@flask_app.route('/process_llm', methods=['POST'])
def receive_user_message():
    user_message = request.form.get('message', '')
    file = request.files.get('file')

    # Read file data now (before request context ends)
    base64_image = None
    if file:
        buffer = BytesIO()
        file.save(buffer)
        file_bytes = buffer.getvalue()
        if not file_bytes:
            queue_message(f"ERROR: Empty image upload: {file.filename}")
            socketio.emit('bot_message', {'message': 'Sorry, the uploaded file was empty.'})
            return jsonify({"status": "error", "message": "Empty file"})
        # Validate with PIL but don't block — LLM vision APIs handle many formats natively
        try:
            buffer.seek(0)
            Image.open(buffer).convert('RGB')
        except Exception as e:
            queue_message(f"WARNING: PIL could not validate image ({file.filename}, {len(file_bytes)} bytes): {e}")
        base64_image = base64.b64encode(file_bytes).decode('utf-8')

    socketio.start_background_task(_process_chat_message, user_message, base64_image)
    return jsonify({"status": "success"})

@flask_app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Legacy upload endpoint — redirects to the unified /process_llm pipeline."""
    file = request.files.get('file')
    if not file:
        return 'No file part', 400
    return receive_user_message()

@flask_app.route('/camera_feed')
def camera_feed():
    """MJPEG stream from the camera for the web UI."""
    try:
        from UI.module_ui_camera import CameraModule
    except ImportError:
        from flask import abort
        abort(503, "Camera module not available")

    import cv2 as _cv2
    import numpy as _np

    camera = CameraModule(1920, 1080)

    def generate():
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            try:
                import pygame as _pg
                frame_array = _pg.surfarray.array3d(frame)
                frame_array = _np.transpose(frame_array, (1, 0, 2))
                frame_bgr = _cv2.cvtColor(frame_array, _cv2.COLOR_RGB2BGR)
                ok, buf = _cv2.imencode('.jpg', frame_bgr, [_cv2.IMWRITE_JPEG_QUALITY, 60])
                if ok:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
            except Exception:
                pass
            time.sleep(0.066)  # ~15 fps

    from flask import Response
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@flask_app.route('/audio_stream')
def audio_stream():
    """
    Generate MP3 TTS and serve the first chunk using dictionary-based storage.
    """
    global current_chunk_index
    socketio.emit('talking_state', {'talking': True})
    _notify_avatar_talking(True)

    with _audio_state_lock:
        audio_chunks_dict.clear()
        current_chunk_index = 0

    final_text = latest_text_to_read or "No response available."

    async def generate_mp3_chunks():
        index = 0
        async for chunk in generate_tts_audio(final_text, CONFIG['TTS']['ttsoption']):
            audio_chunks_dict[index] = chunk.getvalue()
            index += 1
        audio_chunks_dict[index] = None  # Sentinel: end of chunks

    def run_async_generator():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_mp3_chunks())
        loop.close()

    threading.Thread(target=run_async_generator, daemon=True).start()

    # Wait for the first chunk (max 5 s)
    max_wait_time = 5
    waited = 0
    while 0 not in audio_chunks_dict:
        if waited >= max_wait_time:
            return Response(status=204)
        time.sleep(0.1)
        waited += 0.1

    with _audio_state_lock:
        first_chunk = audio_chunks_dict[0]
        current_chunk_index = 1
    return Response(first_chunk, mimetype="audio/mp3", headers={'Content-Type': 'audio/mp3'})

@flask_app.route('/get_next_audio_chunk')
def get_next_audio_chunk():
    """Serve the next MP3 chunk by index from the dictionary."""
    global current_chunk_index

    with _audio_state_lock:
        idx = current_chunk_index
        if idx not in audio_chunks_dict:
            return Response(status=204)  # Not ready yet

        next_chunk = audio_chunks_dict[idx]
        if next_chunk is None:
            return Response(status=204)  # End of stream

        current_chunk_index += 1

    return Response(next_chunk, mimetype="audio/mp3", headers={
        'Content-Type': 'audio/mp3',
        'Content-Length': str(len(next_chunk)),
    })

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
                    if 'depends_on' in field_def:
                        field_options[field_key]['depends_on'] = field_def['depends_on']
                    if 'label' in field_def:
                        field_options[field_key]['label'] = field_def['label']
                    for k in ('min', 'max', 'step'):
                        if k in field_def:
                            field_options[field_key][k] = field_def[k]
        
        # Populate character_card_path options from character directory
        char_key = 'CHAR.character_card_path'
        if char_key in field_options:
            char_dir = os.path.join(BASE_DIR, 'character')
            char_options = []
            if os.path.isdir(char_dir):
                for entry in sorted(os.listdir(char_dir)):
                    json_path = os.path.join(char_dir, entry, f'{entry}.json')
                    if os.path.isfile(json_path):
                        char_options.append(f'character/{entry}/{entry}.json')
            if char_options:
                field_options[char_key]['options'] = char_options
                field_options[char_key]['option_labels'] = {
                    p: p.split('/')[1] for p in char_options
                }

        # Populate webui_theme options from CSS files in themes directory
        theme_key = 'ACCESS.webui_theme'
        if theme_key in field_options:
            themes_dir = os.path.join(BASE_DIR, 'www', 'static', 'css', 'themes')
            if os.path.isdir(themes_dir):
                theme_files = sorted([
                    f[:-4] for f in os.listdir(themes_dir)
                    if f.endswith('.css') and not f.startswith('.')
                ])
                if theme_files:
                    # Put default first, then alphabetical
                    if 'default' in theme_files:
                        theme_files.remove('default')
                        theme_files.insert(0, 'default')
                    field_options[theme_key]['options'] = theme_files
                    # Build labels: capitalize, keep known labels, title-case the rest
                    known_labels = field_options[theme_key].get('option_labels', {})
                    labels = {}
                    for t in theme_files:
                        if t in known_labels:
                            labels[t] = known_labels[t]
                        else:
                            labels[t] = t.replace('_', ' ').replace('-', ' ').title()
                    field_options[theme_key]['option_labels'] = labels

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


@flask_app.route('/reboot_program', methods=['POST'])
def reboot_program():
    """
    Restarts the TARS-AI program to reload configuration.
    Re-executes the current Python process with the same arguments.
    """
    try:
        queue_message("INFO: Reboot requested from web UI - restarting program...")

        def do_restart():
            import time as _time
            _time.sleep(1)  # Give response time to send
            app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
            args = [sys.executable, app_path] + sys.argv[1:]
            os.execv(sys.executable, args)

        import threading
        threading.Thread(target=do_restart, daemon=True).start()

        return jsonify({"success": True, "message": "Rebooting..."})
    except Exception as e:
        queue_message(f"ERROR: Reboot failed - {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


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
    if not WIFI_AVAILABLE or not _wifi_manager:
        return jsonify({"mode": "disconnected", "ssid": None, "ip": None, "signal": 0})
    try:
        return jsonify(_wifi_manager.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/wifi/networks', methods=['GET'])
def wifi_networks():
    if not WIFI_AVAILABLE or not _wifi_manager:
        return jsonify({"networks": []})
    try:
        networks = _wifi_manager.scan_networks()
        return jsonify({"networks": networks})
    except Exception as e:
        return jsonify({"error": str(e), "networks": []}), 500


@flask_app.route('/api/wifi/connect', methods=['POST'])
def wifi_connect():
    if not WIFI_AVAILABLE or not _wifi_manager:
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
    if not WIFI_AVAILABLE or not _wifi_manager:
        return jsonify({"success": False, "error": "WiFi initialising, try again shortly"}), 503
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


# ── CLOUDFLARE QUICK TUNNEL (REMOTE ACCESS) ──────────────────────────────

import subprocess as _sp

_tunnel_process = None
_tunnel_url = None
_tunnel_lock = threading.Lock()

def _cloudflared_bin():
    """Return path to cloudflared binary, or None if not installed."""
    return shutil.which('cloudflared')


def _install_cloudflared():
    """Install cloudflared via apt or direct download. Returns (success, error)."""
    # Try apt first (works on Debian/Ubuntu/Raspbian)
    try:
        r = _sp.run(['bash', '-c',
            'curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && '
            'echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list && '
            'sudo apt-get update -qq && sudo apt-get install -y -qq cloudflared'
        ], capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and _cloudflared_bin():
            return True, ''
    except Exception:
        pass
    # Fallback: direct binary download for ARM64
    try:
        import platform
        arch = platform.machine()
        if arch in ('aarch64', 'arm64'):
            deb_url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb'
        elif arch in ('armv7l', 'armhf'):
            deb_url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm.deb'
        else:
            deb_url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb'
        r = _sp.run(['bash', '-c', f'curl -fsSL -o /tmp/cloudflared.deb {deb_url} && sudo dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb'],
                     capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and _cloudflared_bin():
            return True, ''
        return False, r.stderr.strip() or 'Download failed'
    except _sp.TimeoutExpired:
        return False, 'Download timed out'
    except Exception as e:
        return False, str(e)


def _start_tunnel():
    """Start cloudflared quick tunnel in background. Returns (success, url_or_error)."""
    global _tunnel_process, _tunnel_url
    with _tunnel_lock:
        # Already running?
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return True, _tunnel_url

        # Kill any stale process
        _stop_tunnel_internal()

        bin_path = _cloudflared_bin()
        if not bin_path:
            return False, 'cloudflared not installed'

        port = CONFIG['ACCESS'].get('webui_port', 80)
        try:
            proc = _sp.Popen(
                [bin_path, 'tunnel', '--url', f'http://localhost:{port}'],
                stdout=_sp.PIPE, stderr=_sp.PIPE, text=True
            )
        except Exception as e:
            return False, str(e)

        # Read stderr lines until we find the URL (cloudflared prints it there)
        url = None
        url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            match = url_pattern.search(line)
            if match:
                url = match.group(0)
                break

        if not url:
            proc.kill()
            return False, 'Could not get tunnel URL (cloudflared may have failed to start)'

        _tunnel_process = proc
        _tunnel_url = url

        # Background thread to drain stderr so the process doesn't block
        def _drain():
            try:
                for _ in proc.stderr:
                    pass
            except Exception:
                pass
        threading.Thread(target=_drain, daemon=True).start()

        queue_message(f"SYSTEM: Remote access tunnel active: {url}")
        return True, url


def _stop_tunnel_internal():
    """Stop tunnel process (must hold _tunnel_lock)."""
    global _tunnel_process, _tunnel_url
    if _tunnel_process:
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=5)
        except Exception:
            try:
                _tunnel_process.kill()
            except Exception:
                pass
        _tunnel_process = None
    _tunnel_url = None


def _stop_tunnel():
    """Stop tunnel process (thread-safe)."""
    with _tunnel_lock:
        _stop_tunnel_internal()


def _get_tunnel_status():
    """Get current tunnel status."""
    global _tunnel_process
    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return {'state': 'active', 'url': _tunnel_url}
        # Clean up if process died
        if _tunnel_process:
            _tunnel_process = None
        return {'state': 'inactive'}


@flask_app.route('/api/tunnel/status', methods=['GET'])
def tunnel_status():
    """Get remote access tunnel status."""
    info = _get_tunnel_status()
    info['installed'] = _cloudflared_bin() is not None
    if info['state'] == 'inactive' and _tunnel_error:
        info['state'] = 'error'
        info['error'] = _tunnel_error
    return jsonify(info)


_tunnel_error = None

@flask_app.route('/api/tunnel/start', methods=['POST'])
def tunnel_start():
    """Kick off tunnel in background, return immediately."""
    global _tunnel_error
    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None and _tunnel_url:
            return jsonify({'state': 'active', 'url': _tunnel_url})
    _tunnel_error = None

    def _bg_start():
        global _tunnel_error
        if not _cloudflared_bin():
            ok, err = _install_cloudflared()
            if not ok:
                _tunnel_error = err
                return
        ok, result = _start_tunnel()
        if not ok:
            _tunnel_error = result

    threading.Thread(target=_bg_start, daemon=True).start()
    return jsonify({'state': 'starting'})


@flask_app.route('/api/tunnel/stop', methods=['POST'])
def tunnel_stop():
    """Stop the remote access tunnel."""
    _stop_tunnel()
    return jsonify({'state': 'inactive'})


@flask_app.route('/api/tunnel/qr', methods=['GET'])
def tunnel_qr():
    """Generate QR code PNG for a given URL."""
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL'}), 400
    try:
        import qrcode, io
    except ImportError:
        return jsonify({'error': 'qrcode package not installed'}), 500
    buf = io.BytesIO()
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#c0c0c0", back_color="#1a1a2e")
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')



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

    try:
        import modules.module_llm as _llm
        mm = _llm.memory_manager
        if mm and hasattr(mm, 'topic_index'):
            topics = mm.topic_index.get('topics', [])
            stats['topics'] = len(topics)
            stats['topic_list'] = [
                t.get('topic', str(t)) if isinstance(t, dict) else str(t)
                for t in topics[:20]
            ]
        if mm:
            if hasattr(mm, 'hyper_db'):
                stats['memories'] = len(mm.hyper_db.documents)
            elif hasattr(mm, 'documents'):
                stats['memories'] = len(mm.documents)
    except Exception:
        pass

    return jsonify(stats)


@flask_app.route('/api/console/logs', methods=['GET'])
def console_logs():
    """Stream terminal output to the WebUI nexus console."""
    since = request.args.get('since', 0, type=int)
    lines, head = get_recent_logs(since)
    return jsonify({'lines': lines, 'head': head})


@flask_app.route('/api/characters', methods=['GET'])
def list_characters():
    """Return a list of available character names."""
    char_dir = os.path.join(BASE_DIR, 'character')
    names = []
    if os.path.isdir(char_dir):
        for entry in sorted(os.listdir(char_dir)):
            if os.path.isfile(os.path.join(char_dir, entry, f'{entry}.json')):
                names.append(entry)
    return jsonify({'characters': names})


@flask_app.route('/api/character/<name>', methods=['GET'])
def get_character(name):
    """Return character JSON data and persona traits."""
    import configparser
    char_dir = os.path.join(BASE_DIR, 'character', name)
    json_path = os.path.join(char_dir, f'{name}.json')
    persona_path = os.path.join(char_dir, 'persona.ini')

    if not os.path.isfile(json_path):
        return jsonify({'error': 'Character not found'}), 404

    with open(json_path, 'r', encoding='utf-8') as f:
        char_data = json.load(f)

    traits = {}
    if os.path.isfile(persona_path):
        p = configparser.ConfigParser()
        p.read(persona_path)
        if 'PERSONA' in p:
            traits = {k: int(v) for k, v in p['PERSONA'].items() if v.strip().isdigit()}

    return jsonify({'character': char_data, 'traits': traits})


@flask_app.route('/api/character/<name>/save', methods=['POST'])
def save_character(name):
    """Save character JSON and persona traits to disk."""
    import configparser
    import time as _time

    data = request.get_json(force=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    char_dir = os.path.join(BASE_DIR, 'character', name)
    json_path = os.path.join(char_dir, f'{name}.json')
    persona_path = os.path.join(char_dir, 'persona.ini')

    if not os.path.isdir(char_dir):
        return jsonify({'error': 'Character directory not found'}), 404

    char_data = data.get('character', {})
    traits = data.get('traits', {})

    # Update modified timestamp
    if 'metadata' not in char_data:
        char_data['metadata'] = {}
    char_data['metadata']['modified'] = int(_time.time() * 1000)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(char_data, f, indent=4, ensure_ascii=False)

    if traits:
        p = configparser.ConfigParser()
        p['PERSONA'] = {k: str(int(v)) for k, v in traits.items()}
        with open(persona_path, 'w', encoding='utf-8') as f:
            p.write(f)

    return jsonify({'success': True})


# ── Dashboard API endpoints ──────────────────────────────────────────────────

@flask_app.route('/api/dashboard/memory/delete', methods=['POST'])
def dashboard_memory_delete():
    """Delete a memory document by its index (supports both full and lite memory)."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if not mm:
        return jsonify({"error": "Memory manager not available"}), 500

    is_full = hasattr(mm, 'hyper_db')
    is_lite = hasattr(mm, 'documents') and not is_full
    if not is_full and not is_lite:
        return jsonify({"error": "Memory manager not available"}), 500

    data = request.get_json(silent=True) or {}
    index = data.get('index')
    if index is None:
        return jsonify({"error": "Missing 'index' parameter"}), 400

    try:
        index = int(index)
        docs = mm.hyper_db.documents if is_full else mm.documents
        doc_count = len(docs)
        if index < 0 or index >= doc_count:
            return jsonify({"error": f"Index {index} out of range (0-{doc_count-1})"}), 400

        # Get the document before deleting for confirmation
        doc = docs[index]
        preview = ''
        if isinstance(doc, dict):
            preview = doc.get('user_input', doc.get('bot_response', ''))[:80]

        if is_full:
            mm.hyper_db.remove_document(index)
            mm._mark_dirty()
            mm.flush()
            remaining = len(mm.hyper_db.documents)
        else:
            docs.pop(index)
            mm._mark_dirty()
            mm.flush()
            remaining = len(docs)

        queue_message(f"DASHBOARD: Deleted memory #{index}: {preview}")
        return jsonify({"success": True, "deleted_index": index, "remaining": remaining})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/dashboard/memory/edit', methods=['POST'])
def dashboard_memory_edit():
    """Edit a memory document's fields by index (supports both full and lite memory)."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if not mm:
        return jsonify({"error": "Memory manager not available"}), 500

    # Determine storage backend
    is_full = hasattr(mm, 'hyper_db')
    is_lite = hasattr(mm, 'documents') and not is_full
    if not is_full and not is_lite:
        return jsonify({"error": "Memory manager not available"}), 500

    data = request.get_json(silent=True) or {}
    index = data.get('index')
    fields = data.get('fields')  # dict of field_name -> new_value

    if index is None:
        return jsonify({"error": "Missing 'index' parameter"}), 400
    if not fields or not isinstance(fields, dict):
        return jsonify({"error": "Missing or invalid 'fields' parameter"}), 400

    try:
        index = int(index)
        docs = mm.hyper_db.documents if is_full else mm.documents
        doc_count = len(docs)
        if index < 0 or index >= doc_count:
            return jsonify({"error": f"Index {index} out of range (0-{doc_count-1})"}), 400

        doc = docs[index]
        if not isinstance(doc, dict):
            return jsonify({"error": "Document is not editable"}), 400

        # Build an updated copy — never mutate the live doc in-place before
        # update_document(), which saves old_doc for rollback from docs[index].
        new_doc = dict(doc)
        allowed = {'user_input', 'bot_response', 'speaker', 'timestamp'}
        updated = []
        for key, value in fields.items():
            if key in allowed:
                new_doc[key] = str(value)
                updated.append(key)

        if not updated:
            return jsonify({"error": "No valid fields to update"}), 400

        if is_full:
            # Re-embed the document with updated content; update_document handles
            # the rollback using the original doc still in documents[index].
            mm.hyper_db.update_document(index, new_doc)
            mm._mark_dirty()
            mm.flush()
        else:
            # Lite mode: update keywords and flush
            if hasattr(mm, '_extract_keywords'):
                new_doc['keywords'] = list(mm._extract_keywords(
                    (new_doc.get('user_input', '') + ' ' + new_doc.get('bot_response', ''))
                ))
            docs[index] = new_doc
            mm._mark_dirty()
            mm.flush()

        queue_message(f"DASHBOARD: Edited memory #{index}: {', '.join(updated)}")
        return jsonify({"success": True, "updated_fields": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/dashboard/topic/edit', methods=['POST'])
def dashboard_topic_edit():
    """Edit a topic's fields by its index in the topic list."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if not mm or not hasattr(mm, 'topic_index'):
        return jsonify({"error": "Memory manager not available"}), 500

    data = request.get_json(silent=True) or {}
    index = data.get('index')
    fields = data.get('fields')

    if index is None:
        return jsonify({"error": "Missing 'index' parameter"}), 400
    if not fields or not isinstance(fields, dict):
        return jsonify({"error": "Missing or invalid 'fields' parameter"}), 400

    try:
        index = int(index)
        topics = mm.topic_index.get('topics', [])
        if index < 0 or index >= len(topics):
            return jsonify({"error": f"Topic index {index} out of range"}), 400

        topic = topics[index]
        if not isinstance(topic, dict):
            return jsonify({"error": "Topic is not editable"}), 400

        updated = []
        if 'topic' in fields:
            topic['topic'] = str(fields['topic'])
            updated.append('topic')
        if 'mention_count' in fields:
            try:
                topic['mention_count'] = max(1, int(fields['mention_count']))
                updated.append('mention_count')
            except (ValueError, TypeError):
                pass

        if not updated:
            return jsonify({"error": "No valid fields to update"}), 400

        mm.save_topic_index()
        mm.flush()
        queue_message(f"DASHBOARD: Edited topic #{index}: {', '.join(updated)}")
        return jsonify({"success": True, "updated_fields": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/dashboard/topic/delete', methods=['POST'])
def dashboard_topic_delete():
    """Delete a topic by its index."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if not mm or not hasattr(mm, 'topic_index'):
        return jsonify({"error": "Memory manager not available"}), 500

    data = request.get_json(silent=True) or {}
    index = data.get('index')
    if index is None:
        return jsonify({"error": "Missing 'index' parameter"}), 400

    try:
        index = int(index)
        topics = mm.topic_index.get('topics', [])
        if index < 0 or index >= len(topics):
            return jsonify({"error": f"Topic index {index} out of range"}), 400

        removed = topics.pop(index)
        name = removed.get('topic', '') if isinstance(removed, dict) else str(removed)
        mm.save_topic_index()
        mm.flush()
        queue_message(f"DASHBOARD: Deleted topic #{index}: {name}")
        return jsonify({"success": True, "deleted_topic": name, "remaining": len(topics)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@flask_app.route('/api/dashboard/graph')
def dashboard_graph():
    """Return nodes+links for a brain-like D3 knowledge graph."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    nodes = []
    links = []
    node_ids = set()

    def add_node(n):
        if n["id"] not in node_ids:
            nodes.append(n)
            node_ids.add(n["id"])

    # ── Central brain node ──
    add_node({"id": "BRAIN", "name": character_name.upper(), "color": "#b44dff", "size": 32, "group": "core"})

    # ── IDENTITY HUB: Voice speakers + Face IDs ──
    voice_mem_path = os.path.join(BASE_DIR, 'memory', 'voice_memory.json')
    voice_speakers = []
    if os.path.exists(voice_mem_path):
        try:
            with open(voice_mem_path, 'r') as f:
                vm = json.load(f)
            voice_speakers = vm.get('speakers', [])
        except Exception:
            pass

    face_names = []
    try:
        import numpy as np
        face_db = os.path.join(BASE_DIR, 'vision', 'faces', 'known_faces.npz')
        if os.path.exists(face_db):
            data = np.load(face_db, allow_pickle=True)
            face_names = data['names'].tolist()
    except Exception:
        pass

    # Merge voice + face into known people
    all_people = {}
    for s in voice_speakers:
        name = s.get('name', 'Unknown')
        all_people[name] = {
            "voice": True,
            "voice_role": s.get('role', ''),
            "voice_embeddings": len(s.get('embeddings', [])),
            "face": name in face_names,
        }
    for fn in face_names:
        if fn not in all_people:
            all_people[fn] = {"voice": False, "face": True}
        else:
            all_people[fn]["face"] = True

    if all_people:
        add_node({"id": "hub_people", "name": "PEOPLE", "color": "#ff2d8a", "size": 22, "group": "hub"})
        links.append({"source": "BRAIN", "target": "hub_people"})

        for name, info in all_people.items():
            pid = f"person_{name}"
            modalities = []
            if info.get("voice"): modalities.append("voice")
            if info.get("face"): modalities.append("face")
            add_node({
                "id": pid, "name": name, "color": "#ec407a", "size": 14, "group": "person",
                "details": {
                    "role": info.get("voice_role", ""),
                    "voice_enrolled": info.get("voice", False),
                    "voice_samples": info.get("voice_embeddings", 0),
                    "face_enrolled": info.get("face", False),
                    "modalities": ", ".join(modalities),
                }
            })
            links.append({"source": "hub_people", "target": pid})

    # ── MEMORIES: grouped by speaker / source ──
    _has_full = mm and hasattr(mm, 'hyper_db') and mm.hyper_db.documents
    _has_lite = mm and hasattr(mm, 'documents') and mm.documents and not _has_full
    if _has_full or _has_lite:
        add_node({"id": "hub_memory", "name": "MEMORIES", "color": "#ffca28", "size": 22, "group": "hub"})
        links.append({"source": "BRAIN", "target": "hub_memory"})

        docs = mm.hyper_db.documents if _has_full else mm.documents
        # Classify memories into buckets
        speaker_groups = {}  # speaker name -> list of (i, doc)
        ingested = []        # memories with no user_input (bulk loaded)
        conversations = []   # memories with user_input but no/unknown speaker

        for i, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            user_in = doc.get('user_input', '').strip()
            bot_resp = doc.get('bot_response', '').strip()
            speaker = doc.get('speaker', '').strip()

            # Detect ingested/seeded data: no user_input, or user_input looks like a fact statement
            if not user_in and bot_resp:
                ingested.append((i, doc))
            elif speaker and speaker != 'Unknown' and not speaker.startswith('Unknown'):
                speaker_groups.setdefault(speaker, []).append((i, doc))
            else:
                conversations.append((i, doc))

        # Helper to add memory leaf nodes (capped to prevent visual overload)
        MAX_LEAVES = 25  # max visible memories per cluster

        def add_memory_leaves(parent_nid, mem_list, color):
            shown = mem_list[-MAX_LEAVES:]  # show most recent
            hidden = len(mem_list) - len(shown)
            for i, doc in shown:
                user_in = doc.get('user_input', '')
                bot_resp = doc.get('bot_response', '')
                label = user_in[:50] if user_in else bot_resp[:50] if bot_resp else f"mem_{i}"
                nid = f"mem_{i}"
                add_node({
                    "id": nid, "name": label, "color": color, "size": 5, "group": "memory",
                    "details": {
                        "timestamp": doc.get('timestamp', ''),
                        "speaker": doc.get('speaker', ''),
                        "user_input": user_in[:300],
                        "bot_response": bot_resp[:300],
                    }
                })
                links.append({"source": parent_nid, "target": nid})
            return hidden

        # Ingested knowledge cluster
        if ingested:
            add_node({
                "id": "cluster_ingested", "name": f"INGESTED ({len(ingested)})",
                "color": "#ffa726", "size": 12 + min(len(ingested), 12), "group": "cluster",
                "details": {"count": len(ingested), "description": "Bulk-loaded knowledge and seed data"}
            })
            links.append({"source": "hub_memory", "target": "cluster_ingested"})
            overflow = add_memory_leaves("cluster_ingested", ingested, "#ffcc80")
            if overflow > 0:
                add_node({"id": "more_ingested", "name": f"+{overflow} more", "color": "#ffa726", "size": 4, "group": "overflow"})
                links.append({"source": "cluster_ingested", "target": "more_ingested"})

        # Per-speaker memory clusters
        for spk_name, mem_list in speaker_groups.items():
            cluster_nid = f"cluster_spk_{spk_name}"
            add_node({
                "id": cluster_nid, "name": f"{spk_name} ({len(mem_list)})",
                "color": "#42a5f5", "size": 10 + min(len(mem_list) * 2, 12), "group": "cluster",
                "details": {"count": len(mem_list), "speaker": spk_name}
            })
            links.append({"source": "hub_memory", "target": cluster_nid})
            overflow = add_memory_leaves(cluster_nid, mem_list, "#64b5f6")
            if overflow > 0:
                add_node({"id": f"more_spk_{spk_name}", "name": f"+{overflow} more", "color": "#42a5f5", "size": 4, "group": "overflow"})
                links.append({"source": cluster_nid, "target": f"more_spk_{spk_name}"})

        # Knowledge / unattributed conversations cluster
        if conversations:
            add_node({
                "id": "cluster_convos", "name": f"KNOWLEDGE ({len(conversations)})",
                "color": "#29b6f6", "size": 12 + min(len(conversations), 12), "group": "cluster",
                "details": {"count": len(conversations), "description": "Ingested knowledge and conversations"}
            })
            links.append({"source": "hub_memory", "target": "cluster_convos"})
            overflow = add_memory_leaves("cluster_convos", conversations, "#81d4fa")
            if overflow > 0:
                add_node({"id": "more_convos", "name": f"+{overflow} more", "color": "#29b6f6", "size": 4, "group": "overflow"})
                links.append({"source": "cluster_convos", "target": "more_convos"})

    # ── KNOWLEDGE (TOPICS): categorized ──
    if mm and hasattr(mm, 'topic_index') and mm.topic_index.get('topics'):
        add_node({"id": "hub_knowledge", "name": "KNOWLEDGE", "color": "#39ff14", "size": 22, "group": "hub"})
        links.append({"source": "BRAIN", "target": "hub_knowledge"})

        categories = {
            "Personal Facts": {"color": "#26c6da", "keywords": [
                "has ", "is ", "lives", "owns", "favorite", "name", "born",
                "age", "family", "wife", "husband", "dog", "cat", "pet",
                "garage", "el paso", "blue", "likes", "dislikes", "works",
            ]},
            "Emotional": {"color": "#ab47bc", "keywords": [
                "frustrat", "happy", "humor", "angry", "sad", "excit",
                "nervou", "grateful", "love", "fear", "curious", "surprise",
                "disappoint", "emotion", "mood", "feel", "gratitude", "sarcasm",
            ]},
            "Tools & Tech": {"color": "#00e5ff", "keywords": [
                "tool", "search", "vision", "camera", "photo", "home assistant",
                "discord", "voice", "servo", "movement", "volume", "program",
                "code", "debug", "test", "api",
            ]},
        }

        categorized = {cat: [] for cat in categories}
        categorized["General"] = []

        for j, t in enumerate(mm.topic_index['topics']):
            topic_name = t.get('topic', str(t)) if isinstance(t, dict) else str(t)
            mentions = t.get('mention_count', 1) if isinstance(t, dict) else 1
            nl = topic_name.lower()
            placed = False
            for cat, info in categories.items():
                if any(kw in nl for kw in info["keywords"]):
                    categorized[cat].append((j, t, topic_name, mentions))
                    placed = True
                    break
            if not placed:
                categorized["General"].append((j, t, topic_name, mentions))

        cat_colors = {
            "Personal Facts": "#26c6da", "Emotional": "#ab47bc",
            "Tools & Tech": "#00e5ff", "General": "#66bb6a",
        }

        for cat, items in categorized.items():
            if not items:
                continue
            cat_nid = f"cat_{cat.lower().replace(' ', '_').replace('&', '')}"
            add_node({
                "id": cat_nid, "name": f"{cat.upper()} ({len(items)})",
                "color": cat_colors.get(cat, "#66bb6a"),
                "size": 12 + min(len(items), 10), "group": "category",
                "details": {"count": len(items)}
            })
            links.append({"source": "hub_knowledge", "target": cat_nid})

            for j, t, topic_name, mentions in items:
                nid = f"topic_{j}"
                add_node({
                    "id": nid, "name": topic_name,
                    "color": cat_colors.get(cat, "#66bb6a"),
                    "size": 5 + min(mentions * 2, 10), "group": "topic",
                    "details": {
                        "topic": topic_name,
                        "category": cat, "mention_count": mentions,
                        "first_mentioned": t.get('first_mentioned', '')[:16] if isinstance(t, dict) else '',
                        "last_mentioned": t.get('last_mentioned', '')[:16] if isinstance(t, dict) else '',
                    }
                })
                links.append({"source": cat_nid, "target": nid})


    return jsonify({"nodes": nodes, "links": links})


@flask_app.route('/api/dashboard/mood')
def dashboard_mood():
    """Return mood analytics for the dashboard."""
    from modules.module_dashboard_data import get_mood_analytics, get_emotional_state
    data = get_mood_analytics()
    data['emotional_state'] = get_emotional_state()
    return jsonify(data)


@flask_app.route('/api/dashboard/interactions')
def dashboard_interactions():
    """Return recent interactions for the audit log."""
    from modules.module_dashboard_data import get_interactions
    limit = request.args.get('limit', 100, type=int)
    return jsonify(get_interactions(limit))


@flask_app.route('/api/dashboard/topics')
def dashboard_topics():
    """Return the topic index for the facts/topic view."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if mm and hasattr(mm, 'topic_index'):
        return jsonify(mm.topic_index)
    return jsonify({"topics": []})


@flask_app.route('/api/dashboard/stats')
def dashboard_stats():
    """Return summary stats for the dashboard header."""
    import modules.module_llm as _llm
    mm = _llm.memory_manager
    if mm and hasattr(mm, 'hyper_db') and mm.hyper_db.documents:
        mem_count = len(mm.hyper_db.documents)
    elif mm and hasattr(mm, 'documents') and mm.documents:
        mem_count = len(mm.documents)
    else:
        mem_count = 0
    topic_count = len(mm.topic_index.get('topics', [])) if mm and hasattr(mm, 'topic_index') else 0
    from modules.module_dashboard_data import get_interactions, get_emotional_state
    interaction_count = len(get_interactions(500))
    # Derive dominant mood from the time-weighted emotional state
    # Prefer non-neutral unless nothing else has a meaningful score
    emo_state = get_emotional_state()
    non_neutral = {k: v for k, v in emo_state.items() if k != 'neutral' and v > 0}
    if non_neutral:
        dominant = max(non_neutral, key=non_neutral.get)
    elif emo_state.get('neutral', 0) > 0:
        dominant = 'neutral'
    else:
        dominant = 'neutral'
    return jsonify({
        "memories": mem_count,
        "topics": topic_count,
        "interactions": interaction_count,
        "current_emotion": dominant,
        "emotion_enabled": bool(CONFIG['EMOTION']['enabled']),
    })


@flask_app.route('/api/dashboard/prompt')
def dashboard_prompt():
    """Return prompt history list, or a specific prompt if ?id= is given."""
    from modules.module_dashboard_data import get_interactions, get_prompt_for_interaction

    entry_id = request.args.get('id', '')
    if entry_id:
        # Return the full prompt and LLM response for a specific interaction
        prompt, llm_raw = get_prompt_for_interaction(entry_id)
        return jsonify({
            "prompt": prompt or '(prompt not stored for this interaction)',
            "llm_raw": llm_raw or '',
        })

    # Return the interaction list with metadata for the dropdown
    interactions = get_interactions(200)
    items = []
    for e in reversed(interactions):  # newest first
        items.append({
            "id": e.get("id", ""),
            "ts": e.get("ts", ""),
            "user": (e.get("user", "") or "")[:60],
            "bot": (e.get("bot", "") or "")[:60],
            "emotion": e.get("emotion", ""),
            "speaker": e.get("speaker", ""),
            "has_prompt": e.get("has_prompt", False),
        })
    return jsonify({"interactions": items
    })


def start_flask_app(port=None):
    if port is None:
        port = CONFIG['ACCESS'].get('webui_port', 80)
    queue_message(f"INFO: Starting Flask app on port {port}...")
    socketio.run(flask_app, host="0.0.0.0", port=port, log_output=False, allow_unsafe_werkzeug=True)