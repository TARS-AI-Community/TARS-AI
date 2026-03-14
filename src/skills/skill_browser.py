"""
Skill: browser — Open URLs or play YouTube videos in the browser.

Browser engine originally from module_browser.py:
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""

import subprocess
import threading
import tempfile
import shutil
import os

SKILL = {
    "name": "browser",
    "description": "Open websites and play videos on the display",
    "prompt": """browser
   Triggers: "open [website]", "go to [site]", "visit [url]", "play [video]", "show me [video]", "watch [video]"
   Parameters: {{"action": "open_url|play_youtube", "url": "https://... (for open_url)", "query": "search terms (for play_youtube)", "description": "optional"}}
   Example: {{"function": "browser", "parameters": {{"action": "open_url", "url": "https://google.com", "description": "Google"}}}}
   Example: {{"function": "browser", "parameters": {{"action": "play_youtube", "query": "funny cats"}}}}""",
    "examples": [
        """Example - Play a video:
User: "Play some lofi hip hop"
Response: {{"question": "Play some lofi hip hop", "reply": "Searching for that now.", "function_calls": [{{"function": "browser", "parameters": {{"action": "play_youtube", "query": "lofi hip hop"}}}}], "new_memories": []}}""",
        """Example - Open a website:
User: "Open Reddit"
Response: {{"question": "Open Reddit", "reply": "Opening Reddit for you.", "function_calls": [{{"function": "browser", "parameters": {{"action": "open_url", "url": "https://www.reddit.com", "description": "Reddit"}}}}], "new_memories": []}}""",
    ],
}


# ---------------------------------------------------------------------------
# UI / STT callbacks (pause during browser, resume after)
# ---------------------------------------------------------------------------

def _close_ui_and_pause_stt():
    from modules.module_messageQue import queue_message
    try:
        from modules.module_stt import get_stt_manager
        stt = get_stt_manager()
        if stt:
            stt.pause()
            queue_message("STT paused during browser session")
    except Exception as e:
        queue_message(f"Could not pause STT: {e}")
    try:
        from modules.module_main import ui_manager
        if ui_manager and ui_manager.running:
            queue_message("Closing UI for browser...")
            ui_manager.running = False
            ui_manager.join(timeout=5)
            queue_message("UI closed")
    except Exception as e:
        queue_message(f"Could not close UI: {e}")


def _reopen_ui_and_resume_stt():
    from modules.module_messageQue import queue_message
    try:
        from modules.module_main import ui_manager, shutdown_event, battery_module, stt_manager
        import modules.module_main as main_module
        from modules.module_main import UIManager

        if ui_manager and not ui_manager.running:
            queue_message("Reopening UI...")
            if shutdown_event is None:
                queue_message("ERROR: Missing shutdown_event - cannot reopen UI")
                return
            new_ui_manager = UIManager(shutdown_event=shutdown_event, battery_module=battery_module)
            new_ui_manager.start()
            main_module.ui_manager = new_ui_manager
            if stt_manager:
                stt_manager.ui_manager = new_ui_manager
            from modules.module_main import memory_manager
            if memory_manager:
                memory_manager.ui_manager = new_ui_manager
            queue_message("UI reopened")
    except Exception as e:
        queue_message(f"Could not reopen UI: {e}")
        import traceback
        traceback.print_exc()
    try:
        from modules.module_stt import get_stt_manager
        stt = get_stt_manager()
        if stt:
            stt.resume()
            queue_message("STT resumed")
    except Exception as e:
        queue_message(f"Could not resume STT: {e}")


# ---------------------------------------------------------------------------
# Browser engine (inlined from module_browser.py)
# ---------------------------------------------------------------------------

class _BrowserPlayer:
    def __init__(self):
        self.current_process = None
        self.is_playing = False
        self.on_playback_start = None
        self.on_playback_end = None
        self.temp_profile_dir = None

    def set_callbacks(self, on_start=None, on_end=None):
        self.on_playback_start = on_start
        self.on_playback_end = on_end

    def search_video(self, query, limit=1):
        from modules.module_messageQue import queue_message
        try:
            import yt_dlp
        except ImportError:
            queue_message("ERROR: yt_dlp not installed. Install with: pip install yt-dlp")
            return None
        try:
            queue_message(f"Searching YouTube: {query}")
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch1',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"ytsearch1:{query}", download=False)
                if result and 'entries' in result and len(result['entries']) > 0:
                    video = result['entries'][0]
                    video_info = {
                        'title': video.get('title', 'Unknown'),
                        'url': f"https://www.youtube.com/watch?v={video['id']}",
                        'duration': video.get('duration_string', 'Unknown'),
                        'channel': video.get('uploader', 'Unknown'),
                        'views': video.get('view_count', 'Unknown')
                    }
                    queue_message(f"Found: {video_info['title']}")
                    return video_info
                else:
                    queue_message("No videos found")
                    return None
        except Exception as e:
            queue_message(f"ERROR: YouTube search failed: {e}")
            return None

    def play_video(self, url):
        from modules.module_messageQue import queue_message
        try:
            self.stop_video()
            queue_message(f"Opening video in maximized browser: {url}")

            is_youtube = 'youtube.com' in url or 'youtu.be' in url
            if is_youtube:
                if '?' in url:
                    url += '&autoplay=1'
                else:
                    url += '?autoplay=1'

            self.temp_profile_dir = tempfile.mkdtemp(prefix='tars_browser_')
            queue_message(f"Created temp profile: {self.temp_profile_dir}")

            tablet_ua = 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'

            browsers = [
                ['chromium-browser', '--start-maximized', f'--user-data-dir={self.temp_profile_dir}', f'--user-agent={tablet_ua}', '--disable-pinch'],
                ['chromium', '--start-maximized', f'--user-data-dir={self.temp_profile_dir}', f'--user-agent={tablet_ua}', '--disable-pinch'],
                ['google-chrome', '--start-maximized', f'--user-data-dir={self.temp_profile_dir}', f'--user-agent={tablet_ua}', '--disable-pinch'],
                ['firefox', '--new-window'],
            ]

            browser_found = False
            for browser_cmd in browsers:
                try:
                    check = subprocess.run(['which', browser_cmd[0]], capture_output=True, timeout=1)
                    if check.returncode == 0:
                        cmd = browser_cmd + [url]
                        queue_message(f"Launching: {' '.join(cmd)}")
                        self.current_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.is_playing = True
                        browser_found = True
                        if is_youtube:
                            queue_message(f"Opened maximized with tablet mode in {browser_cmd[0]}")
                        else:
                            queue_message(f"Opened maximized in {browser_cmd[0]}")

                        if self.on_playback_start:
                            try:
                                self.on_playback_start()
                            except Exception as e:
                                queue_message(f"ERROR: Failed to pause UI/STT: {e}")

                        def monitor():
                            self.current_process.wait()
                            self.is_playing = False
                            queue_message("Browser closed")
                            if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
                                try:
                                    shutil.rmtree(self.temp_profile_dir)
                                    queue_message(f"Cleaned up temp profile: {self.temp_profile_dir}")
                                except Exception as e:
                                    queue_message(f"WARNING: Failed to cleanup temp profile: {e}")
                                finally:
                                    self.temp_profile_dir = None
                            if self.on_playback_end:
                                try:
                                    self.on_playback_end()
                                except Exception as e:
                                    queue_message(f"ERROR: Failed to resume UI/STT: {e}")

                        threading.Thread(target=monitor, daemon=True).start()
                        break
                except Exception as e:
                    queue_message(f"ERROR trying {browser_cmd[0]}: {e}")
                    continue

            if not browser_found:
                queue_message("Using default browser (xdg-open)")
                subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True

            return browser_found

        except Exception as e:
            queue_message(f"ERROR: Failed to play video: {e}")
            return False

    def stop_video(self):
        from modules.module_messageQue import queue_message
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
                queue_message("Video stopped")
            except:
                self.current_process.kill()
            finally:
                self.current_process = None
                self.is_playing = False
        if self.temp_profile_dir and os.path.exists(self.temp_profile_dir):
            try:
                shutil.rmtree(self.temp_profile_dir)
                queue_message(f"Cleaned up temp profile: {self.temp_profile_dir}")
            except Exception as e:
                queue_message(f"WARNING: Failed to cleanup temp profile: {e}")
            finally:
                self.temp_profile_dir = None

    def is_playing_video(self):
        return self.is_playing


_player = None


def _get_player():
    global _player
    if _player is None:
        _player = _BrowserPlayer()
    return _player


# ---------------------------------------------------------------------------
# Skill execute
# ---------------------------------------------------------------------------

def execute(parameters, context):
    """Open a URL or play a YouTube video. Returns reply text."""
    from modules.module_messageQue import queue_message

    action = parameters.get("action", "open_url")
    player = _get_player()
    player.set_callbacks(on_start=_close_ui_and_pause_stt, on_end=_reopen_ui_and_resume_stt)

    if action == "play_youtube":
        query = parameters.get("query", "")
        if not query:
            return "Please specify what video you'd like to watch."

        video = player.search_video(query)
        if not video:
            return f"No videos found for '{query}'"

        success = player.play_video(video['url'])
        if success:
            return f"Now playing: {video['title']} by {video.get('channel', 'Unknown')}."
        return "Failed to play video."

    else:  # open_url
        url = parameters.get("url", "")
        description = parameters.get("description", "")
        if not url:
            return "No URL provided."

        queue_message(f"Opening URL: {url}")
        success = player.play_video(url)
        if success:
            return f"Opening {description if description else url}"
        return "Failed to open the website."
