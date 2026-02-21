"""
Module: Screensaver hub (Lite) - Pi Zero 2 / Pi3
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
import time
import random
import pygame
from module_config import load_config

CONFIG = load_config()

AVAILABLE_ANIMATIONS = {}

def _try_load(name, module_path, class_name):
    try:
        mod = __import__(module_path, fromlist=[class_name])
        AVAILABLE_ANIMATIONS[name] = getattr(mod, class_name)
    except Exception as e:
        print(f"[SCREENSAVER-LITE] Skipping '{name}': {e}", flush=True)

_try_load("face", "UI.screensavers.module_screensaver_face", "FaceAnimation")
_try_load("terminal", "UI.screensavers.module_screensaver_terminal", "TerminalAnimation")
_try_load("matrix", "UI.screensavers.module_screensaver_matrix", "MatrixAnimation")
_try_load("hyperspace", "UI.screensavers.module_screensaver_hyperspace", "HyperspaceAnimation")
_try_load("starfield", "UI.screensavers.module_screensaver_starfield", "StarfieldAnimation")
_try_load("pacman", "UI.screensavers.module_screensaver_pacman", "PacmanAnimation")
_try_load("toasters", "UI.screensavers.module_screensaver_toasters", "FlyingToastersAnimation")

FALLBACK_ORDER = ["starfield", "matrix", "hyperspace", "face", "toasters"]


class ScreensaverManagerLite:
    def __init__(self, screen, width, height, timeout=5.0, screensaver_list=None):
        self.screen = screen
        self.width = width
        self.height = height

        self.active = False
        self.last_activity = time.time()
        self.timeout = float(timeout)
        self.current_animation = None
        self.current_animation_name = None
        self.last_switch_time = None
        self.switch_interval = CONFIG['UI']['screensaver_cycle_interval']
        self.failed_animations = set()
        self.show_time = CONFIG['UI']['show_time']

        if screensaver_list is None or not screensaver_list:
            screensaver_list = ["random"]

        is_random = len(screensaver_list) == 1 and screensaver_list[0].lower() == "random"

        if is_random:
            self.enabled_animations = list(AVAILABLE_ANIMATIONS.keys())
        else:
            self.enabled_animations = [
                a for a in screensaver_list if a in AVAILABLE_ANIMATIONS
            ]
            if not self.enabled_animations:
                self.enabled_animations = list(AVAILABLE_ANIMATIONS.keys())

    def _select_animation(self):
        if self.enabled_animations:
            name = random.choice(self.enabled_animations)
        else:
            name = random.choice(list(AVAILABLE_ANIMATIONS.keys()))

        if not self._try_create(name):
            for fb in FALLBACK_ORDER:
                if fb not in self.failed_animations and self._try_create(fb):
                    return
            self._try_create("face", force=True)

    def _try_create(self, name, force=False):
        if name not in AVAILABLE_ANIMATIONS:
            return False
        if not force and name in self.failed_animations:
            return False
        try:
            cls = AVAILABLE_ANIMATIONS[name]
            self.current_animation = cls(self.screen, self.width, self.height, show_time=self.show_time)
            self.current_animation_name = name
            return True
        except Exception as e:
            print(f"[SCREENSAVER-LITE] ERROR creating '{name}': {e}", flush=True)
            if not force:
                self.failed_animations.add(name)
            if force:
                self.current_animation = None
                self.current_animation_name = None
            return False

    def _maybe_switch(self):
        if len(self.enabled_animations) <= 1:
            return
        if self.active and self.last_switch_time is not None:
            if (time.time() - self.last_switch_time) >= self.switch_interval:
                if self.current_animation and hasattr(self.current_animation, 'cleanup'):
                    self.current_animation.cleanup()
                old = self.current_animation_name
                self._select_animation()
                if self.current_animation and self.current_animation_name != old:
                    self.current_animation.reset()
                    self.last_switch_time = time.time()

    def reset_timer(self):
        self.last_activity = time.time()
        if self.active:
            self.active = False
            if self.current_animation and hasattr(self.current_animation, 'cleanup'):
                self.current_animation.cleanup()

    def check_timeout(self):
        if self.timeout <= 0:
            return False
        if not self.active and (time.time() - self.last_activity) > self.timeout:
            self.active = True
            self._select_animation()
            if self.current_animation:
                self.current_animation.reset()
                self.last_switch_time = time.time()
                return True
            else:
                self.active = False
                return False
        return False

    def is_active(self):
        return self.active and self.current_animation is not None

    def deactivate(self):
        self.active = False
        self.reset_timer()

    def render(self):
        if not self.active or not self.current_animation:
            return
        if self.timeout > 0 and (time.time() - self.last_activity) <= self.timeout:
            self.active = False
            return
        self._maybe_switch()
        try:
            self.current_animation.update()
            self.current_animation.render()
        except Exception as e:
            print(f"[SCREENSAVER-LITE] ERROR rendering '{self.current_animation_name}': {e}", flush=True)
            self.active = False
