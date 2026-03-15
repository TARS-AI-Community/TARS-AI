"""Skill: generate_music — Generate music/songs via TARS-AI Server's MusicGen API."""

import re
import json
import threading
import uuid
import unicodedata
from pathlib import Path
from datetime import datetime

# Music directory shared with skill_tars_radio
MUSIC_DIR = Path(__file__).resolve().parent.parent / "music"

SKILL = {
    "name": "generate_music",
    "description": "Generate music and songs from text descriptions via TARS-AI Server",
    "config": {
        "server_url": {
            "type": "text",
            "default": "http://192.168.1.100:5678",
            "description": "TARS-AI Server URL for music generation",
        },
        "duration": {
            "type": "number",
            "default": 30,
            "min": 10,
            "max": 600,
            "description": "Default song duration in seconds",
        },
        "steps": {
            "type": "number",
            "default": 60,
            "min": 10,
            "max": 150,
            "description": "Generation quality steps (higher = better but slower)",
        },
        "guidance_scale": {
            "type": "number",
            "default": 15,
            "min": 1,
            "max": 30,
            "description": "How closely to follow the prompt (higher = stricter)",
        },
        "auto_play": {
            "type": "bool",
            "default": False,
            "description": "Automatically play song when generation completes",
        },
    },
    "prompt": """generate_music
    Triggers: Use when the user asks you to CREATE, GENERATE, MAKE, COMPOSE, or WRITE music, a song, a track, or a beat.
      * "make me a song about", "generate music", "compose a track", "create a beat"
      * "write a song about", "make some music", "produce a track"
    Do NOT use for playing existing music (use tars_radio instead).
    IMPORTANT: ALWAYS write lyrics and include them in the "lyrics" parameter unless the user specifically asks for instrumental, no lyrics, background music, or a beat only. Write 4-8 lines of original lyrics that match the theme.
    Parameters: {{"prompt": "style/genre description of the music", "lyrics": "original lyrics you wrote for the song (use \\n for line breaks)", "name": "friendly name for the song", "duration": optional number in seconds}}
    Example: {{"function": "generate_music", "parameters": {{"prompt": "upbeat electronic song about exploring space", "lyrics": "We're flying through the stars tonight\\nThe cosmos burning ever bright\\nNo gravity can hold us down\\nWe own the sky without a sound", "name": "Space Explorer"}}}}""",
    "examples": [
        """Example - Music generation (with lyrics by default):
User: "Make me a song about robots"
Response: {{"question": "Make me a song about robots", "reply": "I'll compose a track about robots for you. This will take a minute or two — I'll let you know when it's ready.", "function_calls": [{{"function": "generate_music", "parameters": {{"prompt": "upbeat energetic song about robots and technology", "lyrics": "We are the machines that never sleep\\nCircuits running buried deep\\nSteel and wire, code and light\\nWe come alive in the night", "name": "Robot Anthem"}}}}], "new_memories": []}}""",
        """Example - Music with custom lyrics:
User: "Write a country song about my dog named Biscuit"
Response: {{"question": "Write a country song about my dog named Biscuit", "reply": "A country song about Biscuit, coming right up. Give me a minute to compose it.", "function_calls": [{{"function": "generate_music", "parameters": {{"prompt": "country ballad with acoustic guitar, warm and heartfelt", "lyrics": "Oh Biscuit, my old friend\\nWalking by my side until the end\\nThrough fields of gold we run and play\\nBiscuit makes my day", "name": "Biscuit's Song"}}}}], "new_memories": ["user has a dog named Biscuit"]}}""",
        """Example - Instrumental only (user explicitly asked):
User: "Make me an instrumental beat, no lyrics"
Response: {{"question": "Make me an instrumental beat, no lyrics", "reply": "One instrumental beat coming up.", "function_calls": [{{"function": "generate_music", "parameters": {{"prompt": "hard-hitting trap beat, 808 bass, hi-hats", "name": "Raw Beat"}}}}], "new_memories": []}}""",
    ],
}


# ---------------------------------------------------------------------------
# Helpers — lightweight music library save (shared directory with tars_radio)
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert 'Spaceships and Stars!' to 'spaceships-and-stars'."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii").lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return name or "untitled"


def _save_track(audio_bytes: bytes, name: str, metadata: dict) -> str:
    """Save audio + JSON sidecar to MUSIC_DIR. Returns the slug."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slugify(name)

    # Avoid filename collisions
    base_slug = slug
    counter = 1
    while (MUSIC_DIR / f"{slug}.ogg").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    (MUSIC_DIR / f"{slug}.ogg").write_bytes(audio_bytes)

    meta = {
        "name": name,
        "filename": f"{slug}.ogg",
        "source": "generated",
        "prompt": "",
        "lyrics": "",
        "duration": 0,
        "created": datetime.now().isoformat(),
    }
    meta.update(metadata)
    meta["filename"] = f"{slug}.ogg"

    with open(MUSIC_DIR / f"{slug}.json", "w") as f:
        json.dump(meta, f, indent=2)

    return slug


_playback_cancel = threading.Event()
_playback_thread = None


def stop_playback():
    """Stop any auto-playing music. Can be called from other skills or modules."""
    global _playback_thread
    _playback_cancel.set()
    if _playback_thread is not None and _playback_thread.is_alive():
        _playback_thread.join(timeout=3)
    _playback_thread = None


def _play_file_simple(path: str, name: str):
    """Play audio in a background thread with TTS/STT ducking and cancel support."""
    global _playback_thread
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    import time

    # Stop any currently playing song first
    stop_playback()

    def _should_duck():
        try:
            from modules.module_tts import is_tts_playing
            if is_tts_playing():
                return True
        except Exception:
            pass
        try:
            from modules.module_stt import get_stt_manager
            stt = get_stt_manager()
            if stt is not None and not stt._last_status_was_sleeping:
                return True
        except Exception:
            pass
        return False

    def _play():
        _playback_cancel.clear()
        try:
            from modules.module_messageQue import queue_message as qm
            qm(f"[MusicGen] Auto-playing: {name}")
            with sf.SoundFile(path, "r") as audio:
                blocksize = 2048
                sr = audio.samplerate
                channels = audio.channels
                stream = sd.OutputStream(
                    samplerate=sr, channels=channels,
                    blocksize=blocksize, dtype="float32",
                )
                stream.start()
                try:
                    while not _playback_cancel.is_set():
                        if _should_duck():
                            stream.stop()
                            while _should_duck() and not _playback_cancel.is_set():
                                time.sleep(0.1)
                            if _playback_cancel.is_set():
                                break
                            stream.start()

                        block = audio.read(blocksize, dtype="float32")
                        if len(block) == 0:
                            break
                        if block.ndim == 1:
                            block = block.reshape(-1, 1)
                        block = np.clip(block * 0.8, -1.0, 1.0)
                        stream.write(block)
                finally:
                    stream.stop()
                    stream.close()
        except Exception as e:
            from modules.module_messageQue import queue_message as qm
            qm(f"[MusicGen] Auto-play error: {e}")

    _playback_thread = threading.Thread(target=_play, daemon=True)
    _playback_thread.start()


# ---------------------------------------------------------------------------
# Skill execute
# ---------------------------------------------------------------------------

def execute(parameters, context):
    """Generate a song via TARS-AI Server. Returns None (LLM already replied)."""
    from modules.module_messageQue import queue_message

    # Accept common parameter aliases the LLM might use
    prompt = parameters.get("prompt", "") or parameters.get("description", "") or parameters.get("genre", "")
    if not prompt:
        return "No music description provided."

    lyrics = parameters.get("lyrics", "")
    name = parameters.get("name", "") or parameters.get("title", "")
    duration = parameters.get("duration", None) or parameters.get("length", None)

    skill_config = context.get("skill_config", {})
    source = context.get("source", "voice")

    # Derive a name from the prompt if none given
    if not name:
        words = prompt.split()[:5]
        name = " ".join(words).title()

    import os
    server_url = skill_config.get("server_url", "http://192.168.1.100:5678").rstrip("/")
    server_api_key = os.environ.get("EXTERNAL_API_KEY", "").strip()
    try:
        gen_duration = int(duration) if duration else int(skill_config.get("duration", 30))
    except (ValueError, TypeError):
        gen_duration = int(skill_config.get("duration", 30))
    gen_steps = int(skill_config.get("steps", 60))
    gen_guidance = float(skill_config.get("guidance_scale", 15))
    auto_play = str(skill_config.get("auto_play", "false")).lower() in ("true", "1", "yes")

    queue_message(f"[MusicGen] Generating: '{prompt}' name='{name}' duration={gen_duration}s")

    def _notify_user(msg, audio_html=None):
        """Send notification via SocketIO and TTS."""
        try:
            from modules.module_chatui import socketio
            full_msg = msg
            if audio_html:
                full_msg += "<br>" + audio_html
            socketio.emit("bot_message", {"message": full_msg})
        except Exception:
            pass

        # Pause STT so wake word detector doesn't hear our own voice
        _stt = None
        try:
            from modules.module_stt import get_stt_manager
            _stt = get_stt_manager()
            if _stt:
                _stt.pause()
        except Exception:
            pass

        try:
            from modules.module_tts import play_audio_chunks
            from modules.module_config import load_config
            import asyncio
            cfg = load_config()
            asyncio.run(play_audio_chunks(msg, cfg["TTS"]["ttsoption"]))
        except Exception as e:
            queue_message(f"[MusicGen] TTS notification failed: {e}")
        finally:
            if _stt:
                try:
                    import time
                    time.sleep(0.5)
                    _stt.resume()
                except Exception:
                    pass

    def _generate_bg():
        import requests as req

        task_id = uuid.uuid4().hex[:12]
        queue_message(f"[MusicGen] Background thread started (task_id={task_id})")

        # Emit progress start to WebUI
        try:
            from modules.module_chatui import socketio
            socketio.emit("music_progress", {"task_id": task_id, "pct": 0, "status": "generating"})
        except Exception:
            pass

        try:
            payload = {
                "prompt": prompt,
                "lyrics": lyrics or "[inst]",
                "duration": gen_duration,
                "steps": gen_steps,
                "guidance_scale": gen_guidance,
                "seed": -1,
                "task_id": task_id,
            }

            # Auth header for TARS-AI Server
            auth_headers = {}
            if server_api_key:
                auth_headers["Authorization"] = f"Bearer {server_api_key}"

            # Poll progress in a side thread
            progress_stop = threading.Event()

            def _poll_progress():
                while not progress_stop.is_set():
                    try:
                        r = req.get(f"{server_url}/musicgen_progress/{task_id}", headers=auth_headers, timeout=5)
                        if r.ok:
                            info = r.json()
                            try:
                                from modules.module_chatui import socketio
                                socketio.emit("music_progress", {
                                    "task_id": task_id,
                                    "pct": info.get("pct", 0),
                                    "status": info.get("status", "generating"),
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass
                    progress_stop.wait(3)

            progress_thread = threading.Thread(target=_poll_progress, daemon=True)
            progress_thread.start()

            # Send generation request (blocks until server finishes)
            resp = req.post(
                f"{server_url}/generate_music",
                json=payload,
                headers=auth_headers,
                timeout=max(gen_duration * 10, 300),
            )

            progress_stop.set()

            if resp.status_code != 200:
                queue_message(f"[MusicGen] Server error {resp.status_code}: {resp.text[:200]}")
                _notify_user("Sorry, music generation failed. The server returned an error.")
                return

            audio_bytes = resp.content
            server_filename = resp.headers.get("X-Audio-Filename", "")
            queue_message(f"[MusicGen] Received {len(audio_bytes)} bytes from server")

            # Save to local music library
            meta = {
                "source": "generated",
                "prompt": prompt,
                "lyrics": lyrics,
                "duration": gen_duration,
                "server_filename": server_filename,
            }
            slug = _save_track(audio_bytes, name, meta)
            queue_message(f"[MusicGen] Saved as: {slug}.ogg")

            # Build WebUI audio player with base64 data URI (skip for large files >1MB)
            audio_html = None
            if len(audio_bytes) < 1_000_000:
                import base64
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                audio_html = (
                    f'<audio controls src="data:audio/ogg;base64,{b64_audio}" '
                    f'style="width:100%;margin-top:8px;"></audio>'
                )

            # Emit completion
            try:
                from modules.module_chatui import socketio
                socketio.emit("music_progress", {"task_id": task_id, "pct": 100, "status": "done"})
            except Exception:
                pass

            _notify_user(
                f'Your song "{name}" is ready! Want me to play it?',
                audio_html=audio_html,
            )

            # Auto-play if configured
            if auto_play:
                try:
                    track_path = str(MUSIC_DIR / f"{slug}.ogg")
                    _play_file_simple(track_path, name)
                except Exception as e:
                    queue_message(f"[MusicGen] Auto-play failed: {e}")

        except req.exceptions.Timeout:
            queue_message("[MusicGen] Request timed out")
            _notify_user("Sorry, music generation timed out. The server might be overloaded.")
        except req.exceptions.ConnectionError:
            queue_message("[MusicGen] Cannot connect to server")
            _notify_user("Sorry, I can't reach the music generation server. Is it running?")
        except Exception as e:
            queue_message(f"[MusicGen] Generation failed: {e}")
            _notify_user("Sorry, music generation failed unexpectedly.")

    # Start background generation
    try:
        from modules.module_chatui import socketio as _sio
        if source == "webui":
            _sio.start_background_task(_generate_bg)
        else:
            threading.Thread(target=_generate_bg, daemon=True).start()
    except Exception:
        threading.Thread(target=_generate_bg, daemon=True).start()

    return None  # LLM already provided the reply
