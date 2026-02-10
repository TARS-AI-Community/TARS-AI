"""
Module: Screensaver hub
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
import inspect
import pygame
from modules.module_config import load_config
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
from UI.module_screensaver_pictures import PicturesAnimation
from UI.module_screensaver_dashboard import DashboardAnimation
from UI.module_screensaver_defrag import DefragAnimation
from UI.module_screensaver_bounce import BounceAnimation
from UI.module_screensaver_endurance import EnduranceAnimation
from UI.module_screensaver_toasters import FlyingToastersAnimation

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

CONFIG = load_config()


AVAILABLE_ANIMATIONS = {
    "face": {"class": FaceAnimation, "type": "pygame"},
    "terminal": {"class": TerminalAnimation, "type": "pygame"},
    "matrix": {"class": MatrixAnimation, "type": "pygame"},
    "hyperspace": {"class": HyperspaceAnimation, "type": "pygame"},
    "starfield": {"class": StarfieldAnimation, "type": "pygame"},
    "pacman": {"class": PacmanAnimation, "type": "pygame"},
    "blackhole": {"class": BlackHoleAnimation, "type": "opengl"},
    "fractal": {"class": FractalAnimation, "type": "opengl"},
    "waves": {"class": WavesAnimation, "type": "opengl"},
    "nebulas": {"class": NebulaAnimation, "type": "opengl"},
    "pictures": {"class": PicturesAnimation, "type": "opengl"},
    "dashboard": {"class": DashboardAnimation, "type": "opengl"},
    "defrag": {"class": DefragAnimation, "type": "pygame"},
    "bounce": {"class": BounceAnimation, "type": "opengl"},
    "endurance": {"class": EnduranceAnimation, "type": "opengl"},
    "toasters": {"class": FlyingToastersAnimation, "type": "pygame"},
}

FALLBACK_ANIMATIONS = ["starfield", "matrix", "hyperspace", "pacman", "terminal", "face", "toasters"]


def _class_accepts_param(cls, param_name):
    """Check if a class's __init__ method accepts a given parameter."""
    try:
        sig = inspect.signature(cls.__init__)
        return param_name in sig.parameters
    except (ValueError, TypeError):
        return False


class ScreensaverManager:
    def __init__(self, screen, width, height, timeout=5.0, screensaver_list=None, 
                 display_width=None, display_height=None, rotation=0):
        self.screen = screen
        self.width = width
        self.height = height
        self.rotation = rotation  # NEW: Store rotation value
        
        self.display_width = display_width if display_width else width
        self.display_height = display_height if display_height else height
        
        self.active = False
        self.last_activity = time.time()
        self.timeout = float(timeout)
        self.current_animation = None
        self.current_animation_name = None
        self.current_animation_type = None
        self.last_switch_time = None
        self.switch_interval = CONFIG['UI']['screensaver_cycle_interval']
        self.failed_animations = set()
        
        self.show_time = CONFIG['UI']['show_time']
        self.gl_mode_active = False
        try:
            display_flags = pygame.display.get_surface().get_flags()
            if display_flags & pygame.OPENGL:
                self.gl_mode_active = True
        except:
            pass

        self.offscreen_surface = None
        self.gl_texture_id = None
        
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

    def _ensure_offscreen_surface(self):
        if self.offscreen_surface is None:
            self.offscreen_surface = pygame.Surface((self.width, self.height))
        return self.offscreen_surface

    def _render_surface_to_gl(self, surface):
        if not HAS_OPENGL:
            return

        # Determine if we need to rotate for portrait output on landscape display
        is_portrait_output = self.height > self.width
        is_landscape_display = self.display_width > self.display_height
        need_rotation = is_portrait_output and is_landscape_display

        if need_rotation:
            # Rotate 270 degrees for landscape display
            surface = pygame.transform.rotate(surface, 270)

        texture_data = pygame.image.tostring(surface, "RGBA", True)
        tex_width, tex_height = surface.get_size()
  
        if self.gl_texture_id is None:
            self.gl_texture_id = glGenTextures(1)

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glDisable(GL_FOG)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.display_width, 0, self.display_height, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glBindTexture(GL_TEXTURE_2D, self.gl_texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tex_width, tex_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
        

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        # Normal texture mapping - pygame rotation already handled orientation
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(self.display_width, 0)
        glTexCoord2f(1, 1); glVertex2f(self.display_width, self.display_height)
        glTexCoord2f(0, 1); glVertex2f(0, self.display_height)
        glEnd()
        
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        
        pygame.display.flip()

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
                # Check if screensaver supports rotation parameter
                if _class_accepts_param(animation_class, 'rotation'):
                    self.current_animation = animation_class(
                        self.screen, 
                        self.display_width, 
                        self.display_height, 
                        show_time=self.show_time,
                        rotation=self.rotation
                    )
                else:
                    self.current_animation = animation_class(
                        self.screen, 
                        self.display_width, 
                        self.display_height, 
                        show_time=self.show_time
                    )
                self.gl_mode_active = True
            else:
                if self.gl_mode_active and HAS_OPENGL:
                    render_surface = self._ensure_offscreen_surface()
                else:
                    render_surface = self.screen
                self.current_animation = animation_class(render_surface, self.width, self.height, show_time=self.show_time)
            
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
                
                if self.current_animation and hasattr(self.current_animation, 'cleanup'):
                    self.current_animation.cleanup()
                
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
            
            if self.current_animation_type == "pygame" and self.gl_mode_active and HAS_OPENGL:
                self._render_surface_to_gl(self.offscreen_surface)
                return False
            
            return self.current_animation_type == "pygame"
        except Exception as e:
            print(f"[SCREENSAVER] ERROR during render of '{self.current_animation_name}': {type(e).__name__}: {e}")
            self.active = False
            return False