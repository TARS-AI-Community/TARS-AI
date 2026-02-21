"""
App manager
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

import inspect
import pygame

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

from modules.UI.apps.module_app_clock import ClockApp
from UI.screensavers.module_screensaver_dashboard import DashboardAnimation

AVAILABLE_APPS = {
    "clock": {"class": ClockApp, "type": "pygame", "label": "Clock"},
    "dashboard": {"class": DashboardAnimation, "type": "opengl", "label": "Dashboard"},
}


def _class_accepts_param(cls, param_name):
    try:
        sig = inspect.signature(cls.__init__)
        return param_name in sig.parameters
    except (ValueError, TypeError):
        return False


class AppManager:
    def __init__(self, screen, width, height, display_width=None, display_height=None, rotation=0):
        self.screen = screen
        self.width = width
        self.height = height
        self.rotation = rotation

        self.display_width = display_width if display_width else width
        self.display_height = display_height if display_height else height

        self.active = False
        self.current_app = None
        self.current_app_name = None
        self.current_app_type = None
        self.failed_apps = set()

        self.gl_mode_active = False
        try:
            display_flags = pygame.display.get_surface().get_flags()
            if display_flags & pygame.OPENGL:
                self.gl_mode_active = True
        except:
            pass

        self.offscreen_surface = None
        self.gl_texture_id = None

    def get_available_apps(self):
        return [
            {"name": name, "label": info["label"]}
            for name, info in AVAILABLE_APPS.items()
        ]

    def launch(self, app_name):
        if self.current_app and hasattr(self.current_app, 'cleanup'):
            self.current_app.cleanup()
            self.current_app = None
            self.current_app_name = None
            self.current_app_type = None

        if self._try_create_app(app_name):
            self.active = True
            if self.current_app and hasattr(self.current_app, 'reset'):
                self.current_app.reset()
            return True
        return False

    def deactivate(self):
        self.active = False
        if self.current_app:
            if hasattr(self.current_app, 'cleanup'):
                self.current_app.cleanup()
            self.current_app = None
            self.current_app_name = None
            self.current_app_type = None

    def is_active(self):
        return self.active and self.current_app is not None

    def render(self):
        if not self.active or not self.current_app:
            return False

        try:
            self.current_app.update()

            if self.current_app_type == "opengl":
                original_flip = pygame.display.flip
                pygame.display.flip = lambda: None
                try:
                    self.current_app.render()
                finally:
                    pygame.display.flip = original_flip
                return False
            else:
                self.current_app.render()

                if self.gl_mode_active and HAS_OPENGL:
                    self.screen.blit(self.offscreen_surface, (0, 0))
                    return True

                return True
        except Exception as e:
            print(f"[APP] ERROR during render of '{self.current_app_name}': {type(e).__name__}: {e}")
            self.active = False
            return False

    def _try_create_app(self, app_name):
        if app_name not in AVAILABLE_APPS:
            print(f"[APP] Unknown app: '{app_name}'")
            return False

        if app_name in self.failed_apps:
            return False

        try:
            app_info = AVAILABLE_APPS[app_name]
            app_class = app_info["class"]
            app_type = app_info["type"]

            if app_type == "opengl":
                if _class_accepts_param(app_class, 'rotation'):
                    self.current_app = app_class(
                        self.screen,
                        self.display_width,
                        self.display_height,
                        rotation=self.rotation
                    )
                else:
                    self.current_app = app_class(
                        self.screen,
                        self.display_width,
                        self.display_height,
                    )
                self.gl_mode_active = True
            else:
                if self.gl_mode_active and HAS_OPENGL:
                    render_surface = self._ensure_offscreen_surface()
                else:
                    render_surface = self.screen
                self.current_app = app_class(render_surface, self.width, self.height)

            self.current_app_name = app_name
            self.current_app_type = app_type
            return True
        except Exception as e:
            print(f"[APP] ERROR creating '{app_name}': {type(e).__name__}: {e}")
            self.failed_apps.add(app_name)
            self.current_app = None
            self.current_app_name = None
            self.current_app_type = None
            return False

    def _ensure_offscreen_surface(self):
        if self.offscreen_surface is None:
            self.offscreen_surface = pygame.Surface((self.width, self.height))
        return self.offscreen_surface

    def _render_surface_to_gl(self, surface):
        if not HAS_OPENGL:
            return

        is_portrait_output = self.height > self.width
        is_landscape_display = self.display_width > self.display_height
        need_rotation = is_portrait_output and is_landscape_display

        if need_rotation:
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
