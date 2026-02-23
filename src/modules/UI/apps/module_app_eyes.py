"""
Module: Eyes App
Author: Latisha Besariani Hendra
Description: Pygame app that renders RoboEyes.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import time
import pygame

from modules.module_eyes import RoboEyes, Mood

_mood_request = None

def set_mood_request(mood):
    global _mood_request
    _mood_request = mood


class EyesApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        self.eyes = RoboEyes(width, height)
        self.eyes.set_mood(Mood.NEUTRAL)

        self._prev_time = time.time()

    def reset(self):
        self.eyes.set_mood(Mood.NEUTRAL)
        self._prev_time = time.time()

    def update(self):
        now = time.time()
        dt = now - self._prev_time
        self._prev_time = now

        global _mood_request
        if _mood_request is not None:
            self.eyes.set_mood(_mood_request)
            _mood_request = None
        self.eyes.update(dt)

    def render(self):
        self.screen.fill((13, 17, 23))
        self.eyes.draw(self.screen)

    def cleanup(self):
        pass
