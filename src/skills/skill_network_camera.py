"""
Skill: network_camera — View snapshots or live streams from network cameras.

Supports:
  - RTSP streams (e.g. rtsp://user:pass@192.168.1.100:554/stream1)
  - AgentDVR snapshot API (e.g. http://192.168.1.100:8090)
  - Generic HTTP snapshot URLs (any IP camera /snapshot endpoint)

Cameras are configured as a JSON list in the skill config. Each entry has:
  - name:  friendly name the user can say (e.g. "garage", "front door")
  - url:   full URL to the camera source
  - type:  "rtsp", "agentdvr", or "http"

For AgentDVR, the url should be the base server URL (e.g. http://192.168.1.100:8090)
and the name should match the camera name or ID in AgentDVR. The skill will call
/grab/<name> to fetch a still.
"""

import json
import base64
import time
import threading

SKILL = {
    "name": "network_camera",
    "followup": True,
    "description": "View snapshots or live streams from network cameras (RTSP, AgentDVR, HTTP)",
    "config": {
        "cameras": {
            "type": "text",
            "default": '[{"name": "garage", "url": "rtsp://192.168.1.100:554/stream1", "type": "rtsp"}]',
            "description": 'JSON list of cameras. Each: {"name": "...", "url": "...", "type": "rtsp|agentdvr|http"}',
        },
        "agentdvr_url": {
            "type": "text",
            "default": "http://192.168.1.100:8090",
            "description": "AgentDVR server base URL (used when camera type is agentdvr)",
        },
        "snapshot_width": {
            "type": "number",
            "default": 640,
            "min": 160,
            "max": 1920,
            "description": "Width to resize snapshots to (keeps aspect ratio)",
        },
    },
    "prompt": """network_camera
   Triggers: Use when the user asks to see, view, check, or show a network/security/IP camera feed:
     * "show me the garage camera", "check the front door cam", "pull up the driveway feed"
     * "what's on the security camera", "show me camera X", "view the backyard"
     * "stream the garage", "take a snapshot of the front door camera"
     * "what does my garage camera show", "is anyone at the front door"
   This is for NETWORK cameras (IP cams, RTSP, security cameras), NOT the robot's built-in camera.
   If the user says "what do you see" without mentioning a specific camera name, use capture_camera_view instead.
   Parameters:
     - camera: name of the camera to view (must match a configured camera name)
     - action: "snapshot" (default, captures a still image) or "stream" (starts live MJPEG stream in browser) or "analyze" (captures still and describes what it sees)
   Example: {{"function": "network_camera", "parameters": {{"camera": "garage", "action": "snapshot"}}}}""",
    "examples": [
        """Example - View network camera snapshot:
User: "Show me the garage camera"
Response: {{"question": "Show me the garage camera", "reply": "Pulling up the garage camera now.", "function_calls": [{{"function": "network_camera", "parameters": {{"camera": "garage", "action": "snapshot"}}}}], "new_memories": []}}""",
        """Example - Analyze network camera:
User: "What's happening on the front door camera?"
Response: {{"question": "What's happening on the front door camera?", "reply": "Let me check the front door camera.", "function_calls": [{{"function": "network_camera", "parameters": {{"camera": "front door", "action": "analyze"}}}}], "new_memories": []}}""",
        """Example - Stream network camera:
User: "Stream the driveway camera"
Response: {{"question": "Stream the driveway camera", "reply": "Starting the driveway camera stream.", "function_calls": [{{"function": "network_camera", "parameters": {{"camera": "driveway", "action": "stream"}}}}], "new_memories": []}}""",
    ],
}


# ── Stream registry (module-level, no external dependencies) ─────────────────
_stream_registry = {}  # {camera_key: {cam, skill_config}}
_routes_registered = False


def _ensure_stream_route():
    """Lazily register the /network_camera_feed/<key> Flask route once."""
    global _routes_registered
    if _routes_registered:
        return
    _routes_registered = True

    try:
        from modules.module_chatui import flask_app
    except ImportError:
        return  # No web UI available

    from flask import Response, abort

    def _network_camera_feed(camera_key):
        info = _stream_registry.get(camera_key)
        if not info:
            abort(404, f"Camera '{camera_key}' not registered for streaming")

        cam = info["cam"]
        cam_type = cam.get("type", "rtsp").lower()
        url = cam.get("url", "")

        if cam_type == "rtsp":
            def generate_rtsp():
                import cv2
                cap = cv2.VideoCapture(url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                try:
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            time.sleep(0.5)
                            cap.release()
                            cap = cv2.VideoCapture(url)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            continue
                        h, w = frame.shape[:2]
                        if w > 800:
                            scale = 800 / w
                            frame = cv2.resize(frame, (800, int(h * scale)))
                        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                        if ok:
                            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
                        time.sleep(0.066)
                finally:
                    cap.release()
            return Response(generate_rtsp(), mimetype='multipart/x-mixed-replace; boundary=frame')

        elif cam_type in ("http", "agentdvr"):
            def generate_http():
                import requests as _req
                skill_cfg = info["skill_config"]
                while True:
                    try:
                        if cam_type == "agentdvr":
                            agentdvr_url = skill_cfg.get("agentdvr_url", "").strip() or url
                            snap_url = f"{agentdvr_url.rstrip('/')}/grab/{_req.utils.quote(cam.get('name', ''))}"
                        else:
                            snap_url = url
                        resp = _req.get(snap_url, timeout=5)
                        if resp.status_code == 200:
                            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + resp.content + b'\r\n')
                    except Exception:
                        pass
                    time.sleep(0.5)
            return Response(generate_http(), mimetype='multipart/x-mixed-replace; boundary=frame')

        abort(400, f"Unsupported camera type: {cam_type}")

    flask_app.add_url_rule(
        '/network_camera_feed/<camera_key>',
        endpoint='network_camera_feed',
        view_func=_network_camera_feed,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_cameras(skill_config):
    """Parse the cameras JSON config into a list of dicts."""
    raw = skill_config.get("cameras", "[]")
    try:
        cameras = json.loads(raw)
        if isinstance(cameras, list):
            return cameras
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _find_camera(cameras, name):
    """Find a camera by name (case-insensitive, partial match)."""
    name_lower = name.lower().strip()
    for cam in cameras:
        if cam.get("name", "").lower().strip() == name_lower:
            return cam
    for cam in cameras:
        cam_name = cam.get("name", "").lower().strip()
        if name_lower in cam_name or cam_name in name_lower:
            return cam
    return None


def _capture_rtsp(url, width=640):
    """Capture a single frame from an RTSP stream using OpenCV."""
    import cv2
    cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(3):
            ret, frame = cap.read()
        if not ret or frame is None:
            return None, "Could not capture frame from RTSP stream."
        h, w = frame.shape[:2]
        if w > width:
            scale = width / w
            frame = cv2.resize(frame, (width, int(h * scale)))
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes(), None
    finally:
        cap.release()


def _capture_agentdvr(base_url, camera_name):
    """Capture a snapshot from AgentDVR's API."""
    import requests
    urls_to_try = [
        f"{base_url.rstrip('/')}/grab/{requests.utils.quote(camera_name)}",
        f"{base_url.rstrip('/')}/api/camera/{requests.utils.quote(camera_name)}/snapshot",
        f"{base_url.rstrip('/')}/snapshot/{requests.utils.quote(camera_name)}",
    ]
    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('image'):
                return resp.content, None
        except requests.RequestException:
            continue
    return None, f"Could not fetch snapshot from AgentDVR for camera '{camera_name}'. Tried: {', '.join(urls_to_try)}"


def _capture_http(url):
    """Capture a snapshot from a direct HTTP URL."""
    import requests
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.content, None
        return None, f"HTTP camera returned status {resp.status_code}."
    except requests.RequestException as e:
        return None, f"Could not fetch snapshot from HTTP camera: {e}"


def _capture_snapshot(cam, skill_config):
    """Capture a snapshot from any camera type. Returns (jpeg_bytes, error_str)."""
    cam_type = cam.get("type", "rtsp").lower()
    url = cam.get("url", "")
    width = int(skill_config.get("snapshot_width", 640))

    if cam_type == "rtsp":
        return _capture_rtsp(url, width=width)
    elif cam_type == "agentdvr":
        agentdvr_url = skill_config.get("agentdvr_url", "").strip() or url
        return _capture_agentdvr(agentdvr_url, cam.get("name", ""))
    elif cam_type == "http":
        return _capture_http(url)
    else:
        return None, f"Unknown camera type: {cam_type}"


# ── Main execute ─────────────────────────────────────────────────────────────

def execute(parameters, context):
    """View or analyze a network camera. Returns reply text."""
    from modules.module_messageQue import queue_message

    skill_config = context.get("skill_config", {})
    cameras = _parse_cameras(skill_config)

    if not cameras:
        return "No network cameras are configured. Add cameras in the Network Camera skill settings."

    camera_name = parameters.get("camera", "").strip()
    action = parameters.get("action", "snapshot").lower().strip()

    if not camera_name:
        names = [c.get("name", "unnamed") for c in cameras]
        return f"Which camera? Available cameras: {', '.join(names)}"

    cam = _find_camera(cameras, camera_name)
    if not cam:
        names = [c.get("name", "unnamed") for c in cameras]
        return f"Camera '{camera_name}' not found. Available cameras: {', '.join(names)}"

    cam_display_name = cam.get("name", camera_name)
    queue_message(f"[NetworkCam] {action} requested for camera: {cam_display_name}")

    if action == "stream":
        return _handle_stream(cam, cam_display_name, context, skill_config)
    elif action == "analyze":
        return _handle_analyze(cam, cam_display_name, context, skill_config)
    else:
        return _handle_snapshot(cam, cam_display_name, context, skill_config)


def _handle_snapshot(cam, cam_name, context, skill_config):
    """Capture and display a snapshot."""
    from modules.module_messageQue import queue_message

    jpeg_bytes, err = _capture_snapshot(cam, skill_config)
    if err:
        queue_message(f"[NetworkCam] Snapshot error: {err}")
        return f"Couldn't get a snapshot from the {cam_name} camera. {err}"

    b64 = base64.b64encode(jpeg_bytes).decode('utf-8')

    # Send image to web UI
    source = context.get("source", "voice")
    if source == "webui":
        try:
            from modules.module_chatui import socketio
            img_html = (
                f'<div style="margin:4px 0">'
                f'<div style="font-size:0.85em;opacity:0.7;margin-bottom:4px">{cam_name} camera</div>'
                f'<img style="max-width:100%;border-radius:8px;" src="data:image/jpeg;base64,{b64}">'
                f'</div>'
            )
            socketio.emit('bot_message', {'message': img_html})
            queue_message(f"[NetworkCam] Snapshot sent to WebUI ({len(jpeg_bytes)} bytes)")
        except Exception as e:
            queue_message(f"[NetworkCam] WebUI emit failed: {e}")

    # Display on RPi screen if available
    try:
        import os
        from datetime import datetime
        snap_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vision", "cameras")
        os.makedirs(snap_dir, exist_ok=True)
        filename = f"{cam_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(snap_dir, filename)
        with open(filepath, "wb") as f:
            f.write(jpeg_bytes)
        try:
            from modules.module_stablediffusion import display_image_fullscreen
            threading.Thread(target=display_image_fullscreen, args=(filepath,), daemon=True).start()
        except Exception:
            pass
    except Exception as e:
        queue_message(f"[NetworkCam] Save/display error: {e}")

    return f"Here's the snapshot from the {cam_name} camera."


def _handle_stream(cam, cam_name, context, skill_config):
    """Start a live MJPEG stream in the web UI."""
    from modules.module_messageQue import queue_message

    # Register the Flask route (once) and add this camera to the registry
    _ensure_stream_route()
    cam_key = cam.get("name", "camera").lower().replace(" ", "_")
    _stream_registry[cam_key] = {"cam": cam, "skill_config": skill_config}
    stream_path = f"/network_camera_feed/{cam_key}"
    queue_message(f"[NetworkCam] Stream registered at {stream_path}")

    source = context.get("source", "voice")
    if source == "webui":
        try:
            from modules.module_chatui import socketio
            socketio.emit('bot_media', {
                'type': 'stream',
                'url': stream_path,
                'label': f'{cam_name} — live',
            })
            queue_message(f"[NetworkCam] Stream event sent to WebUI")
        except Exception as e:
            queue_message(f"[NetworkCam] WebUI stream emit failed: {e}")

    return f"Starting live stream from the {cam_name} camera."


def _handle_analyze(cam, cam_name, context, skill_config):
    """Capture a snapshot and analyze it with the vision pipeline."""
    from modules.module_messageQue import queue_message

    jpeg_bytes, err = _capture_snapshot(cam, skill_config)
    if err:
        queue_message(f"[NetworkCam] Capture error for analysis: {err}")
        return f"Couldn't capture the {cam_name} camera for analysis. {err}"

    b64 = base64.b64encode(jpeg_bytes).decode('utf-8')

    # Also show the snapshot in the web UI
    source = context.get("source", "voice")
    if source == "webui":
        try:
            from modules.module_chatui import socketio
            img_html = (
                f'<div style="margin:4px 0">'
                f'<div style="font-size:0.85em;opacity:0.7;margin-bottom:4px">{cam_name} camera</div>'
                f'<img style="max-width:100%;border-radius:8px;" src="data:image/jpeg;base64,{b64}">'
                f'</div>'
            )
            socketio.emit('bot_message', {'message': img_html})
        except Exception as e:
            queue_message(f"[NetworkCam] WebUI image emit failed: {e}")

    # Run through vision pipeline
    try:
        from modules.module_vision import process_image
        from modules.module_config import load_config

        config = load_config()
        vision_processor = config.get('VISION', {}).get('vision_processor', 'openai')
        user_input = context.get("user_input", "")
        query = f"This is a frame from the '{cam_name}' security camera. {user_input}" if user_input else \
                f"Describe what you see in this security camera frame from the '{cam_name}' camera."

        queue_message(f"[NetworkCam] Calling process_image with processor={vision_processor}, query={query[:80]}")
        description = process_image(b64, query)
        queue_message(f"[NetworkCam] process_image returned: {str(description)[:200] if description else '(empty/None)'}")

        if description and not str(description).startswith("Error"):
            if vision_processor in ("blip", "server_hosted"):
                try:
                    from modules.module_llm import get_completion
                    vision_prompt = (
                        f"*You checked the {cam_name} security camera and saw: {description}*"
                        f" The user asked: {user_input}" if user_input else
                        f"*You checked the {cam_name} security camera and saw: {description}*"
                    )
                    reply = get_completion(vision_prompt)
                    return reply if reply else description
                except Exception as e:
                    queue_message(f"[NetworkCam] LLM follow-up failed: {e}")
                    return description
            return description
        return f"I checked the {cam_name} camera but couldn't process the image."
    except ImportError:
        queue_message("[NetworkCam] Vision module not available, returning snapshot only")
        return f"Here's the {cam_name} camera. Vision analysis isn't available on this device."
    except Exception as e:
        queue_message(f"[NetworkCam] Vision analysis failed: {e}")
        return f"I got the {cam_name} camera snapshot but couldn't analyze it: {e}"
