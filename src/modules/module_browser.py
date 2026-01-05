"""
Open Browser - V3
==========================
# atomikspace (discord)
# olivierdion1@hotmail.com
"""

import subprocess
import threading
import tempfile
import shutil
import os
import yt_dlp
from modules.module_messageQue import queue_message

class BrowserPlayer:
    def __init__(self):
        self.current_process = None
        self.is_playing = False
        self.on_playback_start = None
        self.on_playback_end = None
        self.temp_profile_dir = None  # Track temporary Chrome profile

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
        try:
            self.stop_video()

            queue_message(f"Opening video in maximized browser: {url}")

            # Add YouTube-specific parameters
            is_youtube = 'youtube.com' in url or 'youtu.be' in url
            if is_youtube:
                if '?' in url:
                    url += '&autoplay=1'
                else:
                    url += '?autoplay=1'

            # Create temporary profile directory for isolated Chrome instance
            self.temp_profile_dir = tempfile.mkdtemp(prefix='tars_browser_')
            queue_message(f"Created temp profile: {self.temp_profile_dir}")

            # Tablet user agent (iPad Pro)
            tablet_ua = 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'

            # Simplified browser commands - fewer flags to avoid issues
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
                        # Command construction - append URL directly
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

                            # Clean up temporary profile directory
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
        
        # Clean up temp profile directory if it exists
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

_browser_player = None

def get_browser_player():
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