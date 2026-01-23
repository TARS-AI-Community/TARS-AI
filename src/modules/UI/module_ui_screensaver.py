"""
Module: Screensaver hub
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

This module was originally created by Charles-Olivier Dion (Atomikspace).

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.
"""


import time
import random
from UI.module_screensaver_face import FaceAnimation
from UI.module_screensaver_terminal import TerminalAnimation
from UI.module_screensaver_matrix import MatrixAnimation
from UI.module_screensaver_hyperspace import HyperspaceAnimation
from UI.module_screensaver_starfield import StarfieldAnimation
from UI.module_screensaver_nebula import NebulaAnimation
from UI.module_screensaver_blackhole import BlackHoleAnimation
from UI.module_screensaver_fractal import FractalAnimation
from UI.module_screensaver_pacman import PacmanAnimation
from UI.module_screensaver_waves import WavesAnimation


AVAILABLE_ANIMATIONS = {
    "face": {"class": FaceAnimation, "type": "pygame"},
    "terminal": {"class": TerminalAnimation, "type": "pygame"},
    "matrix": {"class": MatrixAnimation, "type": "pygame"},
    "hyperspace": {"class": HyperspaceAnimation, "type": "pygame"},
    "starfield": {"class": StarfieldAnimation, "type": "pygame"},
    "pacman": {"class": PacmanAnimation, "type": "pygame"},
    "blackhole": {"class": BlackHoleAnimation, "type": "opengl"},
    "fractal": {"class": FractalAnimation, "type": "opengl"},
    "waves": {"class": WavesAnimation, "type": "opengl"}
}

FALLBACK_ANIMATIONS = ["starfield", "matrix", "hyperspace", "pacman", "terminal", "face"]

class ScreensaverManager:
    def __init__(self, screen, width, height, timeout=5.0, screensaver_list=None, display_width=None, display_height=None):
        self.screen = screen
        self.width = width
        self.height = height
        
        self.display_width = display_width if display_width else width
        self.display_height = display_height if display_height else height
        
        self.active = False
        self.last_activity = time.time()
        self.timeout = float(timeout)
        self.current_animation = None
        self.current_animation_name = None
        self.current_animation_type = None
        self.last_switch_time = None
        self.switch_interval = 300
        self.failed_animations = set()
        
        if screensaver_list is None or not screensaver_list:
            self.screensaver_list = ["random"]
        else:
            self.screensaver_list = screensaver_list
        
        self.is_random_mode = len(self.screensaver_list) == 1 and self.screensaver_list[0].lower() == "random"
        
        if self.is_random_mode:
            self.enabled_animations = list(AVAILABLE_ANIMATIONS.keys())
        else:
            self.enabled_animations = [
                anim for anim in self.screensaver_list 
                if anim in AVAILABLE_ANIMATIONS
            ]
            if not self.enabled_animations:
                self.enabled_animations = list(AVAILABLE_ANIMATIONS.keys())

    def _select_animation(self):
        if self.enabled_animations:
            animation_name = random.choice(self.enabled_animations)
        else:
            animation_name = random.choice(list(AVAILABLE_ANIMATIONS.keys()))

        if animation_name in AVAILABLE_ANIMATIONS:
            if not self._try_create_animation(animation_name):
                fallback_candidates = [fb for fb in FALLBACK_ANIMATIONS if fb in self.enabled_animations]
                if not fallback_candidates:
                    fallback_candidates = FALLBACK_ANIMATIONS
                
                for fallback in fallback_candidates:
                    if fallback not in self.failed_animations and self._try_create_animation(fallback):
                        return
                
                if "face" not in self.failed_animations:
                    self._try_create_animation("face", force=True)
        else:
            self._try_create_animation("face", force=True)

    def _try_create_animation(self, animation_name, force=False):
        if animation_name not in AVAILABLE_ANIMATIONS:
            return False
        
        if not force and animation_name in self.failed_animations:
            return False
        
        try:
            animation_info = AVAILABLE_ANIMATIONS[animation_name]
            animation_class = animation_info["class"]
            animation_type = animation_info["type"]
            
            if animation_type == "opengl":
                self.current_animation = animation_class(self.screen, self.display_width, self.display_height)
            else:
                self.current_animation = animation_class(self.screen, self.width, self.height)
            
            self.current_animation_name = animation_name
            self.current_animation_type = animation_type
            return True
        except Exception as e:
            print(f"[SCREENSAVER] ERROR creating '{animation_name}': {type(e).__name__}: {e}")
            if not force:
                self.failed_animations.add(animation_name)
            
            if force:
                self.current_animation = None
                self.current_animation_name = None
                self.current_animation_type = None
            
            return False

    def _maybe_switch_animation(self):
        if len(self.enabled_animations) <= 1:
            return

        if self.active and self.last_switch_time is not None:
            if (time.time() - self.last_switch_time) >= self.switch_interval:
                old_animation = self.current_animation_name
                self._select_animation()
                
                if self.current_animation and self.current_animation_name != old_animation:
                    self.current_animation.reset()
                    self.last_switch_time = time.time()

    def reset_timer(self):
        self.last_activity = time.time()
        if self.active:
            self.active = False
            if self.current_animation:
                if hasattr(self.current_animation, 'cleanup'):
                    self.current_animation.cleanup()

    def check_timeout(self):
        if self.timeout <= 0:
            return False
        
        time_inactive = time.time() - self.last_activity
        
        if not self.active and time_inactive > self.timeout:
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
            return False
            
        if self.timeout > 0 and (time.time() - self.last_activity) <= self.timeout:
            self.active = False
            return False
            
        self._maybe_switch_animation()
        try:
            self.current_animation.update()
            self.current_animation.render()
            
            return self.current_animation_type == "pygame"
        except Exception as e:
            print(f"[SCREENSAVER] ERROR during render of '{self.current_animation_name}': {type(e).__name__}: {e}")
            self.active = False
            return False