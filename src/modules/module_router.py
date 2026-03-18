"""
Module: Router
Tracks where the user is currently interacting and delivers messages there.

Every time the user sends a message (voice, webui, Discord), the active
route is updated. Any module can call send() / send_image() to deliver
to wherever the user last spoke from.

Voice TTS is queued (not blocking) so reminders and async output don't
conflict with ongoing playback.
"""

import os
import threading
import queue as _queue
from modules.module_messageQue import queue_message

_lock = threading.Lock()
_active_route = {"source": "voice"}  # default to device

# Voice TTS queue — serializes TTS playback so async callers never block
_voice_queue = _queue.Queue()
_voice_worker_started = False


def _start_voice_worker():
    """Start a single background thread that drains the voice TTS queue."""
    global _voice_worker_started
    if _voice_worker_started:
        return
    _voice_worker_started = True

    def _worker():
        while True:
            item = _voice_queue.get()
            if item is None:
                break
            text, image_path = item
            if text:
                try:
                    import asyncio
                    from modules.module_tts import play_audio_chunks
                    from modules.module_config import load_config
                    config = load_config()
                    asyncio.run(play_audio_chunks(text, config['TTS']['ttsoption']))
                except Exception as e:
                    queue_message(f"ROUTER: TTS failed: {e}")
            if image_path:
                try:
                    from modules.module_stablediffusion import display_image_fullscreen
                    display_image_fullscreen(image_path)
                except Exception as e:
                    queue_message(f"ROUTER: Device display failed: {e}")
            _voice_queue.task_done()

    threading.Thread(target=_worker, daemon=True, name="router-voice").start()


# ── Update active route (called at every entry point) ────────────────────────

def set_active_route(source: str, **kwargs):
    """Update where the user is currently talking from.

    Called automatically by voice/webui/discord entry points.
    Args:
        source: "voice", "webui", or "discord"
        **kwargs: source-specific metadata (discord_channel_id, discord_user_id)
    """
    global _active_route
    with _lock:
        prev = _active_route.get("source")
        _active_route = {"source": source}
        _active_route.update(kwargs)
        if prev != source:
            queue_message(f"ROUTER: Switched active route: {prev} -> {source}")


def get_active_route() -> dict:
    """Return the current active route."""
    with _lock:
        return dict(_active_route)


# ── Send to wherever the user is ─────────────────────────────────────────────

def send(text: str):
    """Send a text message to wherever the user currently is."""
    route = get_active_route()
    _deliver(text, route)


def send_image(image, caption: str = ""):
    """Send an image to wherever the user currently is.

    Args:
        image: File path (str) OR raw bytes
        caption: Optional text caption
    """
    route = get_active_route()

    # Convert bytes to temp file if needed
    image_path = None
    if isinstance(image, bytes):
        import tempfile
        _mem_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'memory')
        os.makedirs(_mem_dir, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=_mem_dir)
        tmp.write(image)
        tmp.close()
        image_path = tmp.name
    elif isinstance(image, str):
        image_path = image

    _deliver(caption, route, image_path=image_path)


# ── Internal delivery ────────────────────────────────────────────────────────

def _deliver(text: str, route: dict, image_path: str = None):
    """Deliver text and/or image to wherever the user last interacted."""
    source = route.get("source", "voice")

    try:
        if source == "voice":
            _send_voice(text, image_path)
        elif source == "webui":
            _send_webui(text, image_path)
        elif source == "discord":
            _send_discord(text, route, image_path)
    except Exception as e:
        queue_message(f"ROUTER: Failed to send to {source}: {e}")

    # Clean up temp image file after all targets have consumed it
    if image_path and image_path.endswith('.png'):
        try:
            # Small delay so async targets (Discord) finish reading the file
            def _cleanup():
                import time
                time.sleep(5)
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            threading.Thread(target=_cleanup, daemon=True).start()
        except Exception:
            pass


def _send_voice(text: str, image_path: str = None):
    """Queue TTS and/or image display on the device. Non-blocking."""
    _start_voice_worker()
    _voice_queue.put((text, image_path))


def _send_webui(text: str, image_path: str = None):
    """Send to the web UI via SocketIO."""
    try:
        from modules.module_chatui import socketio
        if text:
            socketio.emit('bot_message', {'message': text})
        if image_path:
            import base64
            with open(image_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            img_html = f'<img style="max-width:100%;border-radius:8px;" src="data:image/png;base64,{img_b64}">'
            socketio.emit('bot_message', {'message': img_html})
        socketio.emit('bot_audio_done', {})
    except Exception as e:
        queue_message(f"ROUTER: WebUI send failed: {e}")


def _send_discord(text: str, route: dict, image_path: str = None):
    """Send to a Discord channel or DM."""
    channel_id = route.get("discord_channel_id")
    user_id = route.get("discord_user_id")
    if not channel_id and not user_id:
        return

    try:
        import asyncio
        from modules.module_discord import bot

        async def _do_send():
            # Try cached channel first, fall back to fetch (needed for DMs)
            channel = bot.get_channel(int(channel_id)) if channel_id else None
            if not channel and user_id:
                try:
                    user = await bot.fetch_user(int(user_id))
                    channel = await user.create_dm()
                except Exception as e:
                    queue_message(f"ROUTER: Could not open DM for user {user_id}: {e}")
                    return
            if not channel:
                queue_message(f"ROUTER: Discord channel {channel_id} not found")
                return

            if image_path:
                import discord as _discord
                msg = text or ""
                await channel.send(msg, file=_discord.File(image_path))
            elif text:
                await channel.send(text)

        if bot.loop and bot.loop.is_running():
            asyncio.run_coroutine_threadsafe(_do_send(), bot.loop)
        else:
            asyncio.run(_do_send())
    except Exception as e:
        queue_message(f"ROUTER: Discord send failed: {e}")
