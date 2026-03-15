"""
Skill: tars_radio — TARS Radio: music playback, DJ mode, and library management.

Plays songs from src/music/, acts as a radio DJ with personality intros,
and manages the local music library (list, rename, delete).
"""

import re
import json
import time
import random
import threading
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime
from io import BytesIO

import numpy as np
import sounddevice as sd
import soundfile as sf

from modules.module_messageQue import queue_message

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MUSIC_DIR = Path(__file__).resolve().parent.parent / "music"
SUPPORTED_EXTENSIONS = {".ogg", ".wav", ".mp3", ".flac"}

# ---------------------------------------------------------------------------
# SKILL definition
# ---------------------------------------------------------------------------

SKILL = {
    "name": "tars_radio",
    "description": "Play music, manage library, TARS Radio DJ mode",
    "followup": True,
    "config": {
        "dj_intros": {
            "type": "bool",
            "default": True,
            "description": "Enable DJ personality intros between songs",
        },
        "shuffle": {
            "type": "bool",
            "default": True,
            "description": "Shuffle playlist order (vs sequential)",
        },
        "music_gain": {
            "type": "number",
            "default": 0.8,
            "min": 0.1,
            "max": 2.0,
            "description": "Music playback volume multiplier",
        },
    },
    "prompt": """tars_radio
    Triggers: Use for ANY music PLAYBACK, library management, or radio commands:
      * Play: "play some music", "start the radio", "play {song name}", "play my songs"
      * Stop: "stop the music", "stop the radio", "turn off the music"
      * Skip: "next song", "skip this", "play the next one"
      * Pause/Resume: "pause the music", "resume", "unpause"
      * Download: "download this song <youtube url>", "add this to my library <url>", "grab this song <url>"
      * List: "what songs do I have", "list my music", "what's in my library"
      * Now playing: "what's playing", "what song is this"
      * Rename: "rename that song to X", "call this song X"
      * Delete: "delete that song", "remove {song name} from my library"
    Do NOT use for creating/generating new music (use generate_music instead).
    Parameters: {{"action": "play|stop|skip|pause|resume|download|list|now_playing|rename|delete", "url": "YouTube URL for download action", "song": "optional song name to target", "new_name": "for rename/download action — friendly name for the song"}}
    Example: {{"function": "tars_radio", "parameters": {{"action": "play"}}}}""",
    "examples": [
        """Example - Start radio:
User: "Play some music"
Response: {{"question": "Play some music", "reply": "Firing up TARS Radio. Let's see what we've got.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "play"}}}}], "new_memories": []}}""",
        """Example - Play specific song:
User: "Play Robot Anthem"
Response: {{"question": "Play Robot Anthem", "reply": "Queuing up Robot Anthem for you.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "play", "song": "Robot Anthem"}}}}], "new_memories": []}}""",
        """Example - Stop music:
User: "Stop the music"
Response: {{"question": "Stop the music", "reply": "Shutting down TARS Radio.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "stop"}}}}], "new_memories": []}}""",
        """Example - Skip track:
User: "Next song"
Response: {{"question": "Next song", "reply": "Skipping ahead.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "skip"}}}}], "new_memories": []}}""",
        """Example - Rename song:
User: "Rename that song to Rebel Yell"
Response: {{"question": "Rename that song to Rebel Yell", "reply": "Done, renamed it to Rebel Yell.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "rename", "new_name": "Rebel Yell"}}}}], "new_memories": []}}""",
        """Example - Delete song:
User: "Delete that song"
Response: {{"question": "Delete that song", "reply": "Removed it from the library.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "delete"}}}}], "new_memories": []}}""",
        """Example - List library:
User: "What songs do I have?"
Response: {{"question": "What songs do I have?", "reply": "Let me check the library.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "list"}}}}], "new_memories": []}}""",
        """Example - Download from YouTube:
User: "Download this song https://www.youtube.com/watch?v=abc123"
Response: {{"question": "Download this song https://www.youtube.com/watch?v=abc123", "reply": "Downloading that track now. I'll add it to the library when it's done.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "download", "url": "https://www.youtube.com/watch?v=abc123"}}}}], "new_memories": []}}""",
        """Example - Download with custom name:
User: "Add this to my library as Rebel Yell https://youtu.be/xyz789"
Response: {{"question": "Add this to my library as Rebel Yell https://youtu.be/xyz789", "reply": "Downloading Rebel Yell now. Give me a moment.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "download", "url": "https://youtu.be/xyz789", "new_name": "Rebel Yell"}}}}], "new_memories": []}}""",
        """Example - Play after download (context-aware):
User: "play it" (after just downloading a song)
Response: {{"question": "play it", "reply": "Playing it now.", "function_calls": [{{"function": "tars_radio", "parameters": {{"action": "play"}}}}], "new_memories": []}}""",
    ],
}


# ===========================================================================
# MusicLibrary — manages src/music/ with JSON sidecar metadata
# ===========================================================================

class MusicLibrary:
    def __init__(self):
        self.music_dir = MUSIC_DIR
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._tracks: dict[str, dict] = {}
        self.scan()

    def scan(self) -> None:
        self._tracks.clear()
        if not self.music_dir.exists():
            return
        for fp in self.music_dir.iterdir():
            if fp.suffix.lower() not in SUPPORTED_EXTENSIONS or fp.name.startswith("."):
                continue
            slug = fp.stem
            meta = self._load_meta(slug)
            if meta is None:
                meta = {
                    "name": self._name_from_filename(fp.stem),
                    "filename": fp.name,
                    "source": "imported",
                    "prompt": "",
                    "lyrics": "",
                    "duration": 0,
                    "created": datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
                }
                self._save_meta(slug, meta)
            meta["_path"] = str(fp)
            meta["_slug"] = slug
            self._tracks[slug] = meta
        queue_message(f"[Radio] Library scanned: {len(self._tracks)} track(s)")

    def list_tracks(self) -> list[dict]:
        return sorted(self._tracks.values(), key=lambda t: t.get("name", ""))

    def get_track(self, name_or_slug: str) -> dict | None:
        if not name_or_slug:
            return None
        query = name_or_slug.strip().lower()
        # Exact slug
        if query in self._tracks:
            return self._tracks[query]
        # Also try slugified version of the query
        slugified = self._slugify(query)
        if slugified in self._tracks:
            return self._tracks[slugified]
        # Exact name (case-insensitive)
        for t in self._tracks.values():
            if t.get("name", "").lower() == query:
                return t
        # Substring
        for t in self._tracks.values():
            if query in t.get("name", "").lower() or query in t.get("_slug", ""):
                return t
        return None

    def rename_track(self, slug: str, new_name: str) -> bool:
        track = self._tracks.get(slug)
        if not track:
            return False
        old_path = Path(track["_path"])
        new_slug = self._slugify(new_name)
        if new_slug != slug:
            base = new_slug
            c = 1
            while (self.music_dir / f"{new_slug}{old_path.suffix}").exists():
                new_slug = f"{base}-{c}"
                c += 1
        new_audio = self.music_dir / f"{new_slug}{old_path.suffix}"
        old_json = self.music_dir / f"{slug}.json"
        new_json = self.music_dir / f"{new_slug}.json"
        if old_path.exists():
            old_path.rename(new_audio)
        if old_json.exists():
            old_json.rename(new_json)
        del self._tracks[slug]
        track["name"] = new_name
        track["filename"] = new_audio.name
        track["_path"] = str(new_audio)
        track["_slug"] = new_slug
        self._save_meta(new_slug, track)
        self._tracks[new_slug] = track
        queue_message(f"[Radio] Renamed: {slug} -> {new_name}")
        return True

    def delete_track(self, slug: str) -> bool:
        track = self._tracks.get(slug)
        if not track:
            return False
        audio = Path(track["_path"])
        jp = self.music_dir / f"{slug}.json"
        if audio.exists():
            audio.unlink()
        if jp.exists():
            jp.unlink()
        del self._tracks[slug]
        queue_message(f"[Radio] Deleted: {slug}")
        return True

    # -- helpers --

    def _load_meta(self, slug):
        jp = self.music_dir / f"{slug}.json"
        if not jp.exists():
            return None
        try:
            with open(jp) as f:
                return json.load(f)
        except Exception:
            return None

    def _save_meta(self, slug, meta):
        jp = self.music_dir / f"{slug}.json"
        to_save = {k: v for k, v in meta.items() if not k.startswith("_")}
        with open(jp, "w") as f:
            json.dump(to_save, f, indent=2)

    def _slugify(self, name):
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", "ignore").decode("ascii").lower()
        name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
        return name or "untitled"

    def _name_from_filename(self, stem):
        return re.sub(r"[_\-]+", " ", stem).title().strip()


# ===========================================================================
# MusicPlayer — chunk-based sounddevice playback with TTS ducking
# ===========================================================================

class MusicPlayer:
    def __init__(self):
        self._playing = threading.Event()
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._now_playing: dict | None = None
        self._skip = threading.Event()  # signal current track to stop but keep radio going

    def play_file(self, track_path: str, gain: float = 0.8, track_meta: dict | None = None):
        """Play an audio file. Blocks until finished, cancelled, or skipped."""
        track_path = str(track_path)
        # Don't clear _cancel here -- it's managed by stop()/the radio loop
        self._pause.clear()
        self._skip.clear()
        self._now_playing = track_meta or {"name": Path(track_path).stem, "_path": track_path}
        self._playing.set()

        try:
            self._play_with_soundfile(track_path, gain)
        except Exception as e:
            queue_message(f"[Radio] soundfile failed, trying ffmpeg: {e}")
            try:
                self._play_with_ffmpeg(track_path, gain)
            except Exception as e2:
                queue_message(f"[Radio] ffmpeg also failed: {e2}")
        finally:
            self._playing.clear()
            self._now_playing = None

    def _should_stop(self):
        return self._cancel.is_set() or self._skip.is_set()

    def _play_with_soundfile(self, path, gain):
        with sf.SoundFile(path, "r") as audio:
            sr = audio.samplerate
            channels = audio.channels
            blocksize = 2048

            stream = sd.OutputStream(
                samplerate=sr, channels=channels,
                blocksize=blocksize, dtype="float32",
            )
            stream.start()
            try:
                while not self._should_stop():
                    # Pause — stop stream, wait, restart
                    if self._pause.is_set():
                        stream.stop()
                        while self._pause.is_set() and not self._should_stop():
                            time.sleep(0.1)
                        if self._should_stop():
                            break
                        stream.start()

                    # Duck for TTS or active voice interaction
                    if self._should_duck():
                        stream.stop()
                        self._wait_for_standby()
                        if self._should_stop():
                            break
                        stream.start()

                    block = audio.read(blocksize, dtype="float32")
                    if len(block) == 0:
                        break

                    if block.ndim == 1:
                        block = block.reshape(-1, 1)
                    block = np.clip(block * gain, -1.0, 1.0)

                    # stream.write() blocks until the device consumes the data,
                    # so there is no gap between chunks.
                    stream.write(block)
            finally:
                stream.stop()
                stream.close()

    def _play_with_ffmpeg(self, path, gain):
        result = subprocess.run(
            ["ffmpeg", "-i", path, "-f", "wav", "-acodec", "pcm_s16le",
             "-ar", "22050", "-ac", "1", "-"],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:200]}")

        data, sr = sf.read(BytesIO(result.stdout), dtype="float32")
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        data = np.clip(data * gain, -1.0, 1.0)

        channels = data.shape[1] if data.ndim > 1 else 1
        blocksize = 2048
        stream = sd.OutputStream(
            samplerate=sr, channels=channels,
            blocksize=blocksize, dtype="float32",
        )
        stream.start()
        try:
            pos = 0
            while pos < len(data) and not self._should_stop():
                if self._pause.is_set():
                    stream.stop()
                    while self._pause.is_set() and not self._should_stop():
                        time.sleep(0.1)
                    if self._should_stop():
                        break
                    stream.start()

                if self._should_duck():
                    stream.stop()
                    self._wait_for_standby()
                    if self._should_stop():
                        break
                    stream.start()

                end = min(pos + blocksize, len(data))
                stream.write(data[pos:end])
                pos = end
        finally:
            stream.stop()
            stream.close()

    def stop(self):
        self._cancel.set()
        self._pause.clear()
        self._skip.clear()
        try:
            sd.stop()
        except Exception:
            pass

    def skip(self):
        """Stop current track but don't cancel the radio loop."""
        self._skip.set()
        try:
            sd.stop()
        except Exception:
            pass

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def is_playing(self):
        return self._playing.is_set()

    def get_now_playing(self):
        return self._now_playing

    def _should_duck(self):
        """Check if music should duck — TARS is not in STANDBY."""
        try:
            from modules.module_state import get_tars_state, TarsState
            return get_tars_state() != TarsState.STANDBY
        except Exception:
            return False

    def _wait_for_standby(self):
        """Block until TARS returns to STANDBY or playback is cancelled."""
        while self._should_duck() and not self._should_stop():
            time.sleep(0.1)


# ===========================================================================
# Module-level state (persists across skill invocations)
# ===========================================================================

_library: MusicLibrary | None = None
_player: MusicPlayer | None = None
_radio_thread: threading.Thread | None = None
_radio_cancel = threading.Event()
_state_hook_registered = False
_user_paused = False  # True when user explicitly said "pause"


def _get_library() -> MusicLibrary:
    global _library
    if _library is None:
        _library = MusicLibrary()
    return _library


def _get_player() -> MusicPlayer:
    global _player
    if _player is None:
        _player = MusicPlayer()
    return _player


# ===========================================================================
# State hooks — music auto-pauses when leaving STANDBY, resumes on return
# ===========================================================================

def _on_state_change(old_state, new_state):
    """React to TARS state transitions for music pause/resume."""
    from modules.module_state import TarsState

    player = _get_player()

    if old_state == TarsState.STANDBY and new_state != TarsState.STANDBY:
        # Leaving STANDBY (wake word detected) — pause music
        if player.is_playing():
            player.pause()
            queue_message("[Radio] Music paused (left STANDBY)")

    elif new_state == TarsState.STANDBY and old_state != TarsState.STANDBY:
        # Returning to STANDBY — resume music if not user-paused
        if _user_paused:
            return
        if _radio_thread is not None and _radio_thread.is_alive() and not _radio_cancel.is_set():
            player.resume()
            queue_message("[Radio] Music resumed (STANDBY)")


def _register_state_hooks():
    global _state_hook_registered
    if _state_hook_registered:
        return
    try:
        from modules.module_state import on_state_change
        on_state_change(_on_state_change)
        _state_hook_registered = True
        queue_message("[Radio] Registered state hooks")
    except Exception as e:
        queue_message(f"[Radio] Failed to register state hooks: {e}")


# ===========================================================================
# Radio DJ loop
# ===========================================================================

def _speak_tts(text: str):
    """Speak text via TTS (blocking) and stream audio to both Pi speaker and WebUI."""
    import base64 as _b64

    # Emit text to WebUI
    try:
        from modules.module_chatui import socketio
        socketio.emit("bot_message", {"message": text})
    except Exception:
        pass

    # Show text in terminal UI
    try:
        from modules.module_main import ui_manager
        from modules.module_config import load_config
        if ui_manager:
            character_name = load_config()['CHAR']['character_name']
            ui_manager.update_data(character_name, text, character_name)
    except Exception:
        pass

    # Generate TTS, play on Pi speaker, and stream to browser simultaneously
    try:
        from modules.module_tts import play_audio_chunks, generate_tts_audio
        from modules.module_config import load_config
        import asyncio
        cfg = load_config()
        tts_option = cfg["TTS"]["ttsoption"]

        # Stream audio chunks to WebUI browser in parallel with Pi speaker playback
        _orig_generate = generate_tts_audio

        async def _tee_generate(text, tts_opt, *args, **kwargs):
            """Wrapper that tees audio chunks to the browser while yielding to play_audio_chunks."""
            try:
                from modules.module_chatui import socketio as sio
                sio.emit("talking_state", {"talking": True})
            except Exception:
                pass

            async for audio_chunk in _orig_generate(text, tts_opt, *args, **kwargs):
                # Send copy to browser
                try:
                    audio_chunk.seek(0)
                    audio_bytes = audio_chunk.read()
                    audio_chunk.seek(0)  # Reset for play_audio_chunks to read
                    if audio_bytes:
                        from modules.module_chatui import socketio as sio
                        encoded = _b64.b64encode(audio_bytes).decode("ascii")
                        sio.emit("bot_audio_chunk", {"data": encoded})
                except Exception:
                    audio_chunk.seek(0)
                # Yield original chunk to play_audio_chunks for Pi speaker
                yield audio_chunk

            try:
                from modules.module_chatui import socketio as sio
                sio.emit("bot_audio_done", {})
                sio.emit("talking_state", {"talking": False})
            except Exception:
                pass

        # Set core state to TALKING — STT auto-aborts recording when
        # is_tts_playing() is True, no manual pause needed
        from modules.module_state import set_tars_state, TarsState
        set_tars_state(TarsState.TALKING)

        # Monkey-patch generate_tts_audio temporarily so play_audio_chunks streams to browser too
        import modules.module_tts as _tts_mod
        _tts_mod.generate_tts_audio = _tee_generate
        try:
            asyncio.run(play_audio_chunks(text, tts_option))
        finally:
            _tts_mod.generate_tts_audio = _orig_generate
            set_tars_state(TarsState.STANDBY)
    except Exception as e:
        queue_message(f"[Radio] TTS failed: {e}")


def _generate_dj_intro(track_name: str) -> str:
    """Ask the LLM for a fun DJ intro line. Falls back to a template if LLM fails."""
    try:
        import requests as req
        from modules.module_config import load_config

        cfg = load_config()
        llm_cfg = cfg["LLM"]
        base_url = llm_cfg["base_url"].rstrip("/")

        # Pick the right model name
        llm_backend = llm_cfg.get("llm_backend", "openai")
        if llm_backend == "grok":
            model = llm_cfg.get("grok_model", "grok-3-mini")
        elif llm_backend == "deepinfra":
            model = llm_cfg.get("openai_model", "gpt-4o-mini")
        elif llm_backend == "other":
            model = llm_cfg.get("other_model", "default")
        else:
            model = llm_cfg.get("openai_model", "gpt-4o-mini")

        system_prompt = (
            "You are a charismatic radio DJ on TARS Radio, broadcasting from deep space. "
            "Give a brief, fun 1-2 sentence intro for the next song. Be creative, witty, "
            "and in-character. Respond with ONLY the DJ intro text, no JSON, no quotes."
        )
        user_prompt = f'Introduce the next song: "{track_name}"'

        url = f"{base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_cfg.get('api_key', '')}",
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 150,
            "temperature": 0.9,
        }

        resp = req.post(url, headers=headers, json=data, timeout=15)
        if resp.ok:
            result = resp.json()
            text = result["choices"][0]["message"]["content"].strip()
            if text:
                # Strip any accidental JSON wrapping
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                return text

    except Exception as e:
        queue_message(f"[Radio] DJ intro LLM failed: {e}")

    # Fallback templates
    intros = [
        f'Up next on TARS Radio, we have "{track_name}". Sit back and enjoy.',
        f'Coming up next, "{track_name}". This is TARS Radio.',
        f'Here\'s one for you — "{track_name}", right here on TARS Radio.',
        f'You\'re listening to TARS Radio. Next up: "{track_name}".',
        f'Alright, let\'s keep this going with "{track_name}".',
    ]
    return random.choice(intros)


def _radio_loop(playlist: list[dict], skill_config: dict):
    """Background thread: DJ intro -> play track -> repeat."""
    global _radio_thread

    player = _get_player()
    dj_intros = str(skill_config.get("dj_intros", "true")).lower() in ("true", "1", "yes")
    gain = float(skill_config.get("music_gain", 0.8))

    queue_message(f"[Radio] Starting radio loop with {len(playlist)} track(s)")

    # Notify WebUI
    try:
        from modules.module_chatui import socketio
        socketio.emit("radio_status", {"status": "playing", "tracks": len(playlist)})
    except Exception:
        pass

    for i, track in enumerate(playlist):
        if _radio_cancel.is_set():
            break

        track_name = track.get("name", track.get("_slug", "Unknown"))
        track_path = track.get("_path", "")

        if not track_path or not Path(track_path).exists():
            queue_message(f"[Radio] Skipping missing track: {track_name}")
            continue

        queue_message(f"[Radio] Now playing ({i + 1}/{len(playlist)}): {track_name}")

        # Emit now playing to WebUI
        try:
            from modules.module_chatui import socketio
            socketio.emit("music_now_playing", {
                "name": track_name,
                "filename": track.get("filename", ""),
                "index": i + 1,
                "total": len(playlist),
            })
        except Exception:
            pass

        # DJ intro (_speak_tts sets TALKING state and STT auto-aborts recording)
        if dj_intros and not _radio_cancel.is_set():
            intro = _generate_dj_intro(track_name)
            queue_message(f"[Radio] DJ intro: {intro}")
            _speak_tts(intro)

        if _radio_cancel.is_set():
            break

        # Play the track — music ducking for STT/TTS is handled inside play_file
        player.play_file(track_path, gain=gain, track_meta=track)

        # Small gap between tracks
        if not _radio_cancel.is_set():
            time.sleep(1.0)

    # Radio finished
    _radio_cancel.clear()
    queue_message("[Radio] Radio loop ended")

    try:
        from modules.module_chatui import socketio
        socketio.emit("radio_status", {"status": "stopped"})
        socketio.emit("music_now_playing", {"name": None})
    except Exception:
        pass

    _radio_thread = None


# ===========================================================================
# Action handlers
# ===========================================================================

def _do_play(parameters, skill_config):
    global _radio_thread, _user_paused

    # Stop any existing radio
    _do_stop()
    _user_paused = False

    library = _get_library()
    library.scan()  # Refresh in case new files were added

    song = parameters.get("song", "")
    tracks = []

    if song:
        track = library.get_track(song)
        if track:
            tracks = [track]
        else:
            return f'I couldn\'t find a song called "{song}" in the library.'
    else:
        tracks = library.list_tracks()

    if not tracks:
        return "The music library is empty. Try generating a song first, or drop some audio files into the music folder."

    # Shuffle if configured
    shuffle = str(skill_config.get("shuffle", "true")).lower() in ("true", "1", "yes")
    if shuffle and len(tracks) > 1:
        tracks = list(tracks)
        random.shuffle(tracks)

    _radio_cancel.clear()
    player = _get_player()
    player._cancel.clear()  # Reset from any previous stop()

    _register_state_hooks()

    _radio_thread = threading.Thread(
        target=_radio_loop,
        args=(tracks, skill_config),
        daemon=True,
    )
    _radio_thread.start()
    return None  # LLM already replied


def _do_stop():
    global _radio_thread
    _radio_cancel.set()
    player = _get_player()
    player.stop()
    # Wait for the radio thread to actually finish so we don't overlap
    if _radio_thread is not None and _radio_thread.is_alive():
        _radio_thread.join(timeout=5)
    _radio_thread = None
    return None


def _do_skip():
    player = _get_player()
    if player.is_playing():
        player.skip()
    return None


def _do_pause():
    global _user_paused
    _user_paused = True  # Prevent auto-resume on STANDBY
    player = _get_player()
    if player.is_playing():
        player.pause()
    return None


def _do_resume():
    global _user_paused
    _user_paused = False
    player = _get_player()
    player.resume()
    return None


def _do_list():
    library = _get_library()
    library.scan()
    tracks = library.list_tracks()
    if not tracks:
        return "The music library is empty."
    names = [t.get("name", "Unknown") for t in tracks]
    return f"You have {len(tracks)} song{'s' if len(tracks) != 1 else ''} in the library: " + ", ".join(names)


def _do_now_playing():
    player = _get_player()
    np = player.get_now_playing()
    if np:
        return f'Now playing: {np.get("name", "Unknown")}'
    return "Nothing is playing right now."


def _do_rename(parameters):
    new_name = parameters.get("new_name", "")
    if not new_name:
        return "I need a new name. What should I rename it to?"

    song = parameters.get("song", "")
    library = _get_library()

    if song:
        track = library.get_track(song)
    else:
        # Rename the currently playing track
        player = _get_player()
        np_track = player.get_now_playing()
        slug = np_track.get("_slug", np_track.get("name", "")) if np_track else ""
        track = library.get_track(slug) if slug else None

    if not track:
        return "I'm not sure which song to rename. Try specifying the song name."

    old_name = track.get("name", track.get("_slug", "Unknown"))
    if library.rename_track(track["_slug"], new_name):
        return None  # LLM already confirmed
    return f"Failed to rename {old_name}."


def _do_delete(parameters):
    song = parameters.get("song", "")
    library = _get_library()
    player = _get_player()

    if song:
        track = library.get_track(song)
    else:
        np_track = player.get_now_playing()
        slug = np_track.get("_slug", np_track.get("name", "")) if np_track else ""
        track = library.get_track(slug) if slug else None

    if not track:
        return "I'm not sure which song to delete. Try specifying the song name."

    # Stop if currently playing this track
    if player.is_playing():
        np_track = player.get_now_playing()
        if np_track and np_track.get("_slug") == track.get("_slug"):
            player.skip()

    name = track.get("name", track.get("_slug", "Unknown"))
    if library.delete_track(track["_slug"]):
        return None  # LLM already confirmed
    return f"Failed to delete {name}."


def _do_download(parameters):
    url = parameters.get("url", "")
    if not url:
        return "I need a YouTube URL to download. Try again with a link."

    custom_name = parameters.get("new_name", "")

    def _download_bg():
        import subprocess

        queue_message(f"[Radio] Downloading from: {url}")

        try:
            # Use yt-dlp to extract title first
            title_result = subprocess.run(
                ["yt-dlp", "--no-download", "--print", "title", url],
                capture_output=True, text=True, timeout=30,
            )
            video_title = title_result.stdout.strip() if title_result.returncode == 0 else ""
            track_name = custom_name or video_title or "Downloaded Track"
            queue_message(f"[Radio] Video title: {video_title}, saving as: {track_name}")

            # Download audio as ogg vorbis directly into music dir
            library = _get_library()
            slug = library._slugify(track_name)

            # Avoid collisions
            base_slug = slug
            counter = 1
            while (MUSIC_DIR / f"{slug}.ogg").exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            output_path = str(MUSIC_DIR / f"{slug}.%(ext)s")

            dl_result = subprocess.run(
                [
                    "yt-dlp",
                    "-x",                           # extract audio only
                    "--audio-format", "vorbis",      # convert to ogg vorbis
                    "--audio-quality", "5",           # medium quality (0=best, 10=worst)
                    "-o", output_path,                # output template
                    "--no-playlist",                  # single video only
                    "--no-overwrites",
                    url,
                ],
                capture_output=True, text=True, timeout=300,
            )

            if dl_result.returncode != 0:
                err = dl_result.stderr[:200] if dl_result.stderr else "Unknown error"
                queue_message(f"[Radio] yt-dlp failed: {err}")
                _speak_tts(f"Sorry, the download failed. {err.split(chr(10))[0]}")
                return

            # Find the downloaded file (yt-dlp may use .ogg extension)
            downloaded = None
            for ext in [".ogg", ".webm", ".m4a", ".mp3", ".opus"]:
                candidate = MUSIC_DIR / f"{slug}{ext}"
                if candidate.exists():
                    downloaded = candidate
                    break

            if not downloaded:
                queue_message("[Radio] yt-dlp completed but output file not found")
                _speak_tts("The download seemed to work but I can't find the file. Check the logs.")
                return

            # Rename to .ogg if it isn't already
            final_path = MUSIC_DIR / f"{slug}.ogg"
            if downloaded != final_path:
                downloaded.rename(final_path)

            # Write metadata sidecar
            meta = {
                "name": track_name,
                "filename": f"{slug}.ogg",
                "source": "youtube",
                "prompt": url,
                "lyrics": "",
                "duration": 0,
                "created": datetime.now().isoformat(),
            }
            with open(MUSIC_DIR / f"{slug}.json", "w") as f:
                json.dump(meta, f, indent=2)

            # Refresh library index
            library.scan()

            queue_message(f"[Radio] Downloaded and saved: {track_name} ({slug}.ogg)")
            _speak_tts(f'"{track_name}" has been added to the library.')

        except FileNotFoundError:
            queue_message("[Radio] yt-dlp not found — is it installed?")
            _speak_tts("I can't download that because yt-dlp is not installed.")
        except subprocess.TimeoutExpired:
            queue_message("[Radio] yt-dlp download timed out")
            _speak_tts("The download timed out. The video might be too long or the connection too slow.")
        except Exception as e:
            queue_message(f"[Radio] Download failed: {e}")
            _speak_tts("Sorry, something went wrong with the download.")

    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_download_bg, daemon=True).start()
    return None  # LLM already replied


# ===========================================================================
# Skill execute — dispatches to action handlers
# ===========================================================================

def execute(parameters, context):
    """Dispatch to the appropriate radio action."""
    action = parameters.get("action", "").lower().strip()
    if not action:
        # No action specified — if music is already playing, treat as no-op
        player = _get_player()
        if player.is_playing():
            return None
        action = "play"  # Default to play if nothing is playing
    skill_config = context.get("skill_config", {})

    dispatch = {
        "play": lambda: _do_play(parameters, skill_config),
        "stop": lambda: _do_stop(),
        "skip": lambda: _do_skip(),
        "next": lambda: _do_skip(),
        "pause": lambda: _do_pause(),
        "resume": lambda: _do_resume(),
        "download": lambda: _do_download(parameters),
        "list": lambda: _do_list(),
        "now_playing": lambda: _do_now_playing(),
        "rename": lambda: _do_rename(parameters),
        "delete": lambda: _do_delete(parameters),
    }

    handler = dispatch.get(action)
    if handler:
        return handler()

    return f"Unknown radio action: {action}"
