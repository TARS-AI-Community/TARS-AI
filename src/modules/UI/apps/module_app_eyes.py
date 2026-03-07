"""
Module: Eyes App
Author: Latisha Besariani Hendra
Description: Pygame app that renders RoboEyes.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import time
import random
import asyncio
import threading
import pygame

from modules.module_eyes import RoboEyes, Mood

_mood_request = None

def set_mood_request(mood):
    global _mood_request
    _mood_request = mood

# Voice lines for touch reactions
TOUCH_VOICE_LINES = {
    'poke_left': [
        "Ouch!", "Hey!", "Ow, my eye!", "Watch it!", "That's my eye!",
        "Do you mind?", "Ow!", "Not cool!", "Easy there!",
    ],
    'poke_right': [
        "Ouch!", "Hey!", "Ow, my eye!", "Watch it!", "That's my eye!",
        "Do you mind?", "Ow!", "Not cool!", "Easy there!",
    ],
    'boop_nose': [
        "Boop!", "Hehe, stop it!", "That tickles!", "Boop right back at ya!",
        "My nose!", "Okay that was cute.", "Again? Really?",
    ],
    'forehead_tap': [
        "Hey, I'm thinking up here.", "Quit it.", "Stop poking my head.",
        "Yes, there's a brain in here.", "Knock knock, nobody's home.",
        "Do you mind? I was thinking.",
    ],
    'chin_tap': [
        "Whoa!", "Hey, watch the chin!", "Hmm?", "What's down there?",
        "That startled me!", "Oh!",
    ],
    'poke_face': [
        "Hey!", "Stop that.", "Excuse me.", "Personal space, please.",
        "I felt that.", "Blink.",
    ],
    'dizzy': [
        "Whoa, the room is spinning!", "I'm seeing stars!",
        "Make it stop!", "Everything's going in circles!",
        "I think I need to sit down.", "Too many pokes!",
        "The world won't stay still!",
    ],
}


def _speak_in_background(text):
    """Fire TTS in a background thread without blocking the render loop."""
    def _run():
        try:
            from modules.module_config import load_config
            from modules.module_tts import play_audio_chunks
            config = load_config()
            asyncio.run(play_audio_chunks(text, config['TTS']['ttsoption']))
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


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

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            reaction = self.eyes.handle_touch(x, y)
            if reaction and reaction in TOUCH_VOICE_LINES:
                line = random.choice(TOUCH_VOICE_LINES[reaction])
                _speak_in_background(line)
            return reaction is not None
        return False

    def render(self):
        self.screen.fill((13, 17, 23))
        self.eyes.draw(self.screen)

    def cleanup(self):
        pass
