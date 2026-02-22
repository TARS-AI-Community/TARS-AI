"""
Module: Eyes App
Author: Latisha Besariani Hendra
Description: Pygame app that renders RoboEyes with a WiFi signal HUD overlay.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import os
import time
import pygame

from modules.module_eyes import RoboEyes, Mood

# WiFi status helper
try:
    from modules.module_wifi import get_wifi_status
    HAS_WIFI = True
except Exception:
    HAS_WIFI = False
    def get_wifi_status():
        return {"mode": "disconnected", "ssid": None, "ip": None, "signal": 0}

_ASSET_DIR = os.path.dirname(os.path.abspath(__file__))

_mood_request = None

def set_mood_request(mood):
    global _mood_request
    _mood_request = mood


def _load_icon(name: str, size: int = 32) -> pygame.Surface | None:
    path = os.path.join(_ASSET_DIR, name)
    try:
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (size, size))
    except Exception:
        return None


class EyesApp:
    POLL_INTERVAL = 5.0

    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        self.eyes = RoboEyes(width, height)
        self.eyes.set_mood(Mood.NEUTRAL)

        self._last_poll = 0.0
        self._wifi_signal = 0
        self._wifi_mode = "disconnected"

        self._icon_blue   = _load_icon("wifi-blue.png")
        self._icon_yellow = _load_icon("wifi-yellow.png")
        self._icon_gray   = _load_icon("wifi-gray.png")

        self._prev_time = time.time()
        self._poll_status()

    def reset(self):
        self.eyes.set_mood(Mood.NEUTRAL)
        self._prev_time = time.time()
        self._poll_status()

    def _poll_status(self):
        self._last_poll = time.time()
        if HAS_WIFI:
            status = get_wifi_status()
            self._wifi_signal = status.get("signal", 0)
            self._wifi_mode   = status.get("mode", "disconnected")

    def update(self):
        now = time.time()
        dt = now - self._prev_time
        self._prev_time = now

        if now - self._last_poll >= self.POLL_INTERVAL:
            self._poll_status()

        global _mood_request
        if _mood_request is not None:
            self.eyes.set_mood(_mood_request)
            _mood_request = None
        self.eyes.update(dt)

    def render(self):
        self.screen.fill((13, 17, 23))
        self.eyes.draw(self.screen)
        self._draw_hud(self.screen)

    def _wifi_icon(self):
        if self._wifi_mode == "hotspot":
            return self._icon_yellow
        if self._wifi_mode == "client":
            return self._icon_blue
        return self._icon_gray

    def _draw_hud(self, surface):
        icon = self._wifi_icon()
        if icon:
            surface.blit(icon, (10, 10))

    def cleanup(self):
        pass
