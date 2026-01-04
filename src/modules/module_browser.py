"""
module_browser.py

Web video search and playback for TARS-AI.
Uses yt-dlp for search and browser for playback.
Closes UI and pauses STT during playback.
"""

import subprocess
import threading
import yt_dlp
from modules.module_messageQue import queue_message

class BrowserPlayer:
    def __init__(self):
        self.current_process = None
        self.is_playing = False
        self.on_playback_start = None
        self.on_playback_end = None

    def set_callbacks(self, on_start=None, on_end=None):
        self.on_playback_start = on_start
        self.on_playback_end = on_end

    def search_video(self, query, limit=1):
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
        """
        Play YouTube video in maximized browser window.

        Parameters:
        - url (str): YouTube video URL

        Returns:
        - bool: Success status
        """
        try:

            self.stop_video()

            queue_message(f"Opening video in maximized browser: {url}")

            if 'youtube.com' in url or 'youtu.be' in url:
                if '?' in url:
                    url += '&autoplay=1'
                else:
                    url += '?autoplay=1'

            browsers = [
                ['chromium-browser', '--start-maximized', '--new-window'],
                ['chromium', '--start-maximized', '--new-window'],
                ['google-chrome', '--start-maximized', '--new-window'],
                ['firefox', '--new-window'],
            ]

            browser_found = False
            for browser_cmd in browsers:
                try:

                    check = subprocess.run(['which', browser_cmd[0]], capture_output=True, timeout=1)
                    if check.returncode == 0:

                        cmd = browser_cmd + [url]
                        self.current_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.is_playing = True
                        browser_found = True
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

                            if self.on_playback_end:
                                try:
                                    self.on_playback_end()
                                except Exception as e:
                                    queue_message(f"ERROR: Failed to resume UI/STT: {e}")

                        threading.Thread(target=monitor, daemon=True).start()
                        break
                except:
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
        """Stop currently playing video"""
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

    def is_playing_video(self):
        """Check if a video is currently playing"""
        return self.is_playing

_browser_player = None

def get_browser_player():
    """Get or create browser player instance"""
    global _browser_player
    if _browser_player is None:
        _browser_player = BrowserPlayer()
    return _browser_player

def search_and_play(query, on_start=None, on_end=None):
    player = get_browser_player()

    if on_start or on_end:
        player.set_callbacks(on_start, on_end)

    video = player.search_video(query)

    if not video:
        return {
            'success': False,
            'message': f"No videos found for '{query}'"
        }

    success = player.play_video(video['url'])

    if success:
        return {
            'success': True,
            'message': f"Now playing: {video['title']}",
            'video': video
        }
    else:
        return {
            'success': False,
            'message': "Failed to play video"
        }