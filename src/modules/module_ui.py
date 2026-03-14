"""
GUI - V3
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
import pygame
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import *
from OpenGL.GLU import *
import threading

from datetime import datetime
import numpy as np
import os
import sounddevice as sd
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter
import socket
import random
import math
import cv2

import time as _time

from module_config import load_config
from UI.module_ui_particles import ParticleSystem
from UI.module_ui_starfield import StarfieldSystem
from UI.module_ui_tesseract import TesseractSystem
from UI.module_ui_terminal import TerminalSystem
from UI.module_ui_spectrum import SpectrumSystem
from UI.module_ui_video import VideoSystem
from UI.module_ui_camera import CameraModule
from UI.module_ui_detections import DetectionManager
from UI.module_ui_screensaver import ScreensaverManager
from UI.module_ui_apps import AppManager

try:
    from module_wifi import get_wifi_status as _get_wifi_status
    _HAS_WIFI = True
except Exception:
    _HAS_WIFI = False

CONFIG = load_config()
screenWidth = CONFIG['UI'].get('screen_width', 0)
screenHeight = CONFIG['UI'].get('screen_height', 0)
rotation = CONFIG['UI'].get('rotation', 0)
show_mouse = CONFIG['UI']['show_mouse']
use_camera_module = CONFIG['UI']['use_camera_module']
fullscreen = CONFIG['UI']['fullscreen']
font_size = CONFIG['UI']['font_size']
target_fps = CONFIG['UI']['target_fps']
screensaver_timer = CONFIG['UI']['screensaver_timer']
show_cpu_temp = CONFIG['UI']['show_cpu_temp']
speechdelay = CONFIG['STT']['speechdelay']

BASE_WIDTH = 800
BASE_HEIGHT = 600

class UIManager(threading.Thread):
    def __init__(self, shutdown_event, battery_module, cpu_temp_module=None, use_camera_module=use_camera_module, show_mouse=show_mouse, 
                 width: int = screenWidth, height: int = screenHeight, rotation_value=rotation, 
                 background_type='particles'):
        super().__init__()
        self.shutdown_event = shutdown_event
        self.battery_module = battery_module
        self.cpu_temp_module = cpu_temp_module
        self.running = False
        self.paused = False  

        self.new_data_added = False
        self.target_fps = target_fps
        self.show_mouse = show_mouse
        self.use_camera_module = use_camera_module
        self.change_camera_resolution = False
        self.width = width
        self.height = height
        self.rotate = rotation_value
        self.effective_rotate = rotation_value
        self.actual_display_width = width
        self.actual_display_height = height
        self.font_size = font_size
        self.silence_progress = 0
        self.speechdelay = speechdelay

        self.background_types = ['particles', 'starfield', 'tesseract', 'video']
        self.background_type = background_type
        self.current_background_index = self.background_types.index(background_type) if background_type in self.background_types else 0
        self.background_change_requested = False
        self.next_background = None

        from pathlib import Path
        self.settings_dir = Path(__file__).resolve().parent.parent / "state"
        self.settings_file = self.settings_dir / "ui_settings.json"
        self.spectrum_style = 'bars'  

        self._load_ui_settings()  

        if self.width > 0 and self.height > 0:
            if self.width > self.height:
                self.logical_width = self.height
                self.logical_height = self.width
            else:
                self.logical_width = self.width
                self.logical_height = self.height
        else:
            self.logical_width = 600
            self.logical_height = 1024

        self.particle_system = None
        self.starfield_system = None
        self.tesseract_system = None
        self.video_system = None 

        self.spectrum_system = None

        self.terminal_system = None

        self.screensaver_manager = None

        self.app_manager = None
        self.show_app = False
        self.app_switch_time = 0

        self.camera_module = None
        self.show_camera = False

        self._wifi_mode = "disconnected"
        self._wifi_signal = 0
        self._wifi_poll_interval = 5.0
        self._wifi_thread_running = False

        # Overlay image for generated images (set from any thread)
        self._overlay_image = None          # pygame.Surface or None
        self._overlay_expire = 0            # time.time() when overlay should disappear
        self._overlay_pending_path = None   # path queued from background thread
        self._overlay_pending_duration = 8
        self._overlay_lock = threading.Lock()

        self.detection_manager = DetectionManager()

        if self.use_camera_module:
            try:
                print("LOAD: Initializing camera module...")
                self.camera_module = CameraModule(
                    self.logical_width,
                    self.logical_height,
                    use_camera_module=True
                )

                if not self.camera_module.running and self.camera_module.picam2 is not None:
                    self.camera_module.start_camera()

                if self.camera_module.running:
                    print("LOAD: Camera module started successfully")
                elif self.camera_module.picam2 is None:
                    print("WARNING: Camera module created but picam2 is None (camera not detected?)")
                else:
                    print("WARNING: Camera module created but not running")

            except Exception as e:
                print(f"ERROR: Camera module initialization failed in UIManager: {e}")
                self.camera_module = None
        else:
            print("LOAD: Camera module disabled in config (use_camera_module=False)")

    def _load_ui_settings(self):
        try:
            import json
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)

                    saved_bg = settings.get('background_type')
                    if saved_bg and saved_bg in self.background_types:
                        self.background_type = saved_bg
                        self.current_background_index = self.background_types.index(saved_bg)

                    self.spectrum_style = settings.get('spectrum_style', 'bars')

        except Exception as e:
            print(f"WARNING: Failed to load UI settings: {e}")

    def _save_ui_settings(self):
        try:
            import json
            self.settings_dir.mkdir(parents=True, exist_ok=True)

            settings = {
                'background_type': self.background_type,
                'spectrum_style': self.spectrum_style
            }

            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)

        except Exception as e:
            print(f"WARNING: Failed to save UI settings: {e}")

    def cycle_background(self):
        self.current_background_index = (self.current_background_index + 1) % len(self.background_types)
        self.next_background = self.background_types[self.current_background_index]
        self.background_change_requested = True
        return self.next_background.upper()

    def toggle_camera(self):
        self.show_camera = not self.show_camera

        if self.screensaver_manager:
            if self.show_camera:
                self.screensaver_manager.deactivate()
            else:
                self.screensaver_manager.reset_timer()

        if self.show_camera:
            if self.terminal_system:
                self.terminal_system.set_camera_active(True)
        else:
            if self.terminal_system:
                self.terminal_system.set_camera_active(False)

    def launch_app(self, app_name):
        if self.show_camera:
            self.toggle_camera()

        if self.screensaver_manager:
            self.screensaver_manager.deactivate()

        if self.app_manager and self.app_manager.launch(app_name):
            self.show_app = True
            self.app_switch_time = pygame.time.get_ticks()
            if self.terminal_system:
                self.terminal_system.set_app_active(True)

    def exit_app(self):
        if self.app_manager:
            self.app_manager.deactivate()
        self.show_app = False
        self.app_switch_time = pygame.time.get_ticks()
        if self.terminal_system:
            self.terminal_system.set_app_active(False)
        if self.screensaver_manager:
            self.screensaver_manager.reset_timer()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def deactivate_screensaver(self):
        """Deactivate the screensaver (called by wake word callback)."""
        if self.screensaver_manager:
            self.screensaver_manager.deactivate()

    def show_overlay_image(self, image_path, duration=8):
        """Queue an image overlay on the UI for *duration* seconds (thread-safe).

        The actual pygame surface creation happens on the main render thread
        to avoid X11 threading errors.
        """
        with self._overlay_lock:
            self._overlay_pending_path = image_path
            self._overlay_pending_duration = duration

    def exit_program(self):
        self.running = False
        self.shutdown_event.set()
        import os
        os._exit(0)  

    def initiate_shutdown(self):
        self.running = False
        self.shutdown_event.set()
        import subprocess
        import os
        try:
            subprocess.Popen(['sudo', 'shutdown', 'now'])  

        except Exception as e:
            print(f"ERROR: Shutdown command failed: {e}")
        os._exit(0)  

    def _start_wifi_polling(self):
        """Start a daemon thread that polls WiFi status without blocking the render loop."""
        if not _HAS_WIFI or self._wifi_thread_running:
            return
        self._wifi_thread_running = True
        t = threading.Thread(target=self._wifi_poll_loop, daemon=True, name="ui-wifi-poll")
        t.start()

    def _wifi_poll_loop(self):
        """Background loop: poll WiFi status and push it to the terminal system."""
        while self._wifi_thread_running and self.running:
            try:
                status = _get_wifi_status()
                self._wifi_mode = status.get("mode", "disconnected")
                self._wifi_signal = status.get("signal", 0)
                if self.terminal_system:
                    self.terminal_system.set_wifi_status(self._wifi_mode, self._wifi_signal)
            except Exception:
                pass
            _time.sleep(self._wifi_poll_interval)

    def silence(self, progress):
        self.silence_progress = progress
        if self.spectrum_system is not None:
            self.spectrum_system.silence(progress, self.speechdelay)
        if self.terminal_system is not None:
            self.terminal_system.set_silence_progress(progress, self.speechdelay)

    def save_memory(self):
        if self.terminal_system is not None:
            self.terminal_system.add_memory()

        if self.spectrum_system is not None:
            self.spectrum_system.add_memory()

        if self.background_type == 'particles' and self.particle_system is not None:
            self.particle_system.add_memory()
        elif self.background_type == 'starfield' and self.starfield_system is not None:
            self.starfield_system.add_memory()
        elif self.background_type == 'tesseract' and self.tesseract_system is not None:
            self.tesseract_system.add_memory()

    def think(self):
        if self.terminal_system is not None:
            self.terminal_system.think()

        if self.spectrum_system is not None:
            self.spectrum_system.think()

        if self.background_type == 'particles' and self.particle_system is not None:
            self.particle_system.think()
        elif self.background_type == 'starfield' and self.starfield_system is not None:
            self.starfield_system.think()
        elif self.background_type == 'tesseract' and self.tesseract_system is not None:
            self.tesseract_system.think()

    def set_tars_status(self, status):
        if self.terminal_system is not None:
            self.terminal_system.set_tars_status(status)

    def update_data(self, key: str, value: str, msg_type: str = 'INFO') -> None:
        self.new_data_added = True
        if self.terminal_system is not None:
            self.terminal_system.add_message(key, value, msg_type)
        if self.spectrum_system is not None:
            self.spectrum_system.action()
        if self.background_type == 'particles' and self.particle_system is not None:
            self.particle_system.action()
        elif self.background_type == 'starfield' and self.starfield_system is not None:
            self.starfield_system.action()
        elif self.background_type == 'tesseract' and self.tesseract_system is not None:
            self.tesseract_system.action()

    def update_streaming_data(self, value: str) -> None:
        """Update the last terminal message in-place (for streaming tokens)."""
        if self.terminal_system is not None:
            self.terminal_system.update_last_message(value)

    def _transform_mouse_pos(self, screen_pos, display_width, display_height):
        x, y = screen_pos

        if self.effective_rotate == 0:
            return (x, y)

        if self.effective_rotate in (90, 270):
            rotated_width = self.logical_height
            rotated_height = self.logical_width
        else:
            rotated_width = self.logical_width
            rotated_height = self.logical_height

        offset_x = (display_width - rotated_width) // 2
        offset_y = (display_height - rotated_height) // 2

        x -= offset_x
        y -= offset_y

        if self.effective_rotate == 90:
            logical_x = self.logical_width - 1 - y
            logical_y = x

        elif self.effective_rotate == 180:
            logical_x = self.logical_width - 1 - x
            logical_y = self.logical_height - 1 - y

        elif self.effective_rotate == 270:
            logical_x = y
            logical_y = self.logical_height - 1 - x
        else:
            logical_x = x
            logical_y = y

        logical_x = max(0, min(logical_x, self.logical_width - 1))
        logical_y = max(0, min(logical_y, self.logical_height - 1))

        return (int(logical_x), int(logical_y))

    def _init_background(self, bg_type):
        new_particle = None
        new_starfield = None
        new_tesseract = None
        new_video = None

        if bg_type == 'particles':
            new_particle = ParticleSystem(
                self.logical_width,
                self.logical_height, 
                num_particles=250,
                bg_color=(0, 0, 0)
            )
        elif bg_type == 'starfield':
            new_starfield = StarfieldSystem(
                self.logical_width,
                self.logical_height,
                num_stars=600,
                bg_color=(0, 0, 0)
            )
        elif bg_type == 'tesseract':
            new_tesseract = TesseractSystem(
                self.logical_width,
                self.logical_height,
                bg_color=(0, 0, 0)
            )
        elif bg_type == 'video':
            new_video = VideoSystem(
                self.logical_width,
                self.logical_height,
                bg_color=(0, 0, 0),
                video_folder="video"
            )

        self.particle_system = new_particle
        self.starfield_system = new_starfield
        self.tesseract_system = new_tesseract
        self.video_system = new_video

    def cycle_spectrum_style(self):
        if self.spectrum_system:
            styles = ['bars', 'wave', 'sinewave', 'circular', 'spectrogram']
            current_idx = styles.index(self.spectrum_system.style)
            next_idx = (current_idx + 1) % len(styles)
            self.spectrum_system.style = styles[next_idx]
            self.spectrum_style = styles[next_idx]

            self._save_ui_settings()
            return styles[next_idx].upper()
        return None

    def _render_surface_to_opengl(self, surface, texture_id):
        """Helper to render a pygame surface as an OpenGL texture"""
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        texture_data = pygame.image.tostring(surface, "RGBA", True)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, surface.get_width(), surface.get_height(), 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
        
        disp_w = self.actual_display_width if hasattr(self, 'actual_display_width') else self.width
        disp_h = self.actual_display_height if hasattr(self, 'actual_display_height') else self.height
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(0, 0)
        glTexCoord2f(1, 1); glVertex2f(disp_w, 0)
        glTexCoord2f(1, 0); glVertex2f(disp_w, disp_h)
        glTexCoord2f(0, 0); glVertex2f(0, disp_h)
        glEnd()

    def _draw_gl_back_button(self):
        btn_surface = pygame.Surface((self.logical_width, self.logical_height), pygame.SRCALPHA)
        btn_surface.fill((0, 0, 0, 0))
        self.terminal_system.draw_back_button(btn_surface)

        if self.effective_rotate != 0:
            btn_surface = pygame.transform.rotate(btn_surface, self.effective_rotate)

        tex_data = pygame.image.tostring(btn_surface, "RGBA", True)
        tex_w, tex_h = btn_surface.get_size()

        if not hasattr(self, '_back_btn_tex_id') or self._back_btn_tex_id is None:
            self._back_btn_tex_id = glGenTextures(1)

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        dw = self.actual_display_width
        dh = self.actual_display_height
        glOrtho(0, dw, 0, dh, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glBindTexture(GL_TEXTURE_2D, self._back_btn_tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tex_w, tex_h, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex_data)

        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(dw, 0)
        glTexCoord2f(1, 1); glVertex2f(dw, dh)
        glTexCoord2f(0, 1); glVertex2f(0, dh)
        glEnd()

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def _draw_camera(self, surface):
        if not self.camera_module:
            return

        frame = self.camera_module.get_frame()
        if frame is None:

            font = pygame.font.Font("UI/mono.ttf", 24)
            text = font.render("Initializing camera...", True, (0, 255, 255))
            text_rect = text.get_rect(center=(self.logical_width // 2, self.logical_height // 2))

            overlay = pygame.Surface((self.logical_width, self.logical_height))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            surface.blit(overlay, (0, 0))

            surface.blit(text, text_rect)
            return

        overlay = pygame.Surface((self.logical_width, self.logical_height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        # Draw light ring first so camera and buttons render on top
        light = self.detection_manager._get_light_ring_detector()
        if light is not None and light.enabled:
            light.draw_light_ring(surface)

        camera_w = int(self.logical_width * 0.8)
        camera_h = int(self.logical_height * 0.8)
        camera_x = (self.logical_width - camera_w) // 2
        camera_y = (self.logical_height - camera_h) // 2

        detected_frame = self.detection_manager.process_frame(frame)

        scaled_frame = pygame.transform.scale(detected_frame, (camera_w, camera_h))

        border_rect = pygame.Rect(camera_x - 2, camera_y - 2, camera_w + 4, camera_h + 4)
        pygame.draw.rect(surface, (0, 255, 255), border_rect, 2)

        surface.blit(scaled_frame, (camera_x, camera_y))

        self.detection_manager.draw_buttons(surface, camera_x, camera_y, camera_w)

    def run(self) -> None:
        try:
            pygame.init()
            pygame.mouse.set_visible(self.show_mouse)
            os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'

            display_flags = pygame.DOUBLEBUF | OPENGL

            if fullscreen:
                display_flags |= pygame.FULLSCREEN

            display_info = pygame.display.Info()
            os_width = display_info.current_w
            os_height = display_info.current_h
            
            if fullscreen:
                screen = pygame.display.set_mode((0, 0), display_flags)
            else:
                win_w = self.width if self.width > 0 else os_width
                win_h = self.height if self.height > 0 else os_height
                screen = pygame.display.set_mode((win_w, win_h), display_flags)
            
            actual_size = screen.get_size()
            display_width = actual_size[0]
            display_height = actual_size[1]
            
            actual_is_portrait = display_height > display_width
            
            if actual_is_portrait:
                self.logical_width = display_width
                self.logical_height = display_height
                self.effective_rotate = 0
            else:
                self.logical_width = display_height
                self.logical_height = display_width
                self.effective_rotate = 270
            
            self.actual_display_width = display_width
            self.actual_display_height = display_height
            
            print(f"[UI] Screen: {display_width}x{display_height}, Logical: {self.logical_width}x{self.logical_height}, Rotate: {self.effective_rotate}")

            pygame.display.set_caption("UI Manager")
            
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluOrtho2D(0, display_width, display_height, 0)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            texture_id = glGenTextures(1)

            original_surface = pygame.Surface((self.logical_width, self.logical_height))

            try:
                self._init_background(self.background_type)

                self.spectrum_system = SpectrumSystem(
                    self.logical_width,
                    self.logical_height,
                    style=self.spectrum_style,  
                    bg_alpha=0  
                )

                self.terminal_system = TerminalSystem(
                    self.logical_width,
                    self.logical_height,
                    bg_alpha=13,
                    battery_module=self.battery_module,
                    cpu_temp_module=self.cpu_temp_module,
                    show_cpu_temp=show_cpu_temp,
                    on_background_change=self.cycle_background,
                    on_shutdown=self.initiate_shutdown,
                    on_spectrum_change=self.cycle_spectrum_style,
                    on_camera_toggle=self.toggle_camera,
                    on_exit=self.exit_program,
                    on_app_select=self.launch_app,
                    on_app_back=self.exit_app
                )

                self.screensaver_manager = ScreensaverManager(
                    original_surface,
                    self.logical_width,
                    self.logical_height,
                    timeout=screensaver_timer,
                    screensaver_list=CONFIG['UI']['screensaver_list'],
                    display_width=display_width,
                    display_height=display_height,
                    rotation=self.effective_rotate
                )

                self.app_manager = AppManager(
                    original_surface,
                    self.logical_width,
                    self.logical_height,
                    display_width=display_width,
                    display_height=display_height,
                    rotation=self.effective_rotate
                )

                if self.terminal_system and self.app_manager:
                    self.terminal_system.set_available_apps(self.app_manager.get_available_apps())

                startup_app = CONFIG['UI'].get('app', 'terminal')
                if startup_app and startup_app.lower() != 'terminal':
                    self.launch_app(startup_app.lower())

            except Exception as e:
                import traceback
                traceback.print_exc()
                return

            clock = pygame.time.Clock()
            font = pygame.font.Font("UI/mono.ttf", self.font_size)
            self.running = True

            # Start background WiFi polling thread (after self.running = True)
            self._start_wifi_polling()

            while self.running and not self.shutdown_event.is_set():

                if self.paused:
                    clock.tick(10)  

                    pygame.event.pump()  

                    continue

                if self.background_change_requested and self.next_background:

                    self._init_background(self.next_background)
                    self.background_type = self.next_background  

                    self._save_ui_settings()

                    self.background_change_requested = False
                    self.next_background = None

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if not self.show_app:
                            if self.screensaver_manager:
                                self.screensaver_manager.reset_timer()

                        # Route key events to detection manager for name input
                        if self.show_camera and self.detection_manager.handle_key_event(event):
                            continue

                        if event.key == pygame.K_ESCAPE:
                            if self.show_app:
                                self.exit_app()
                            else:
                                self.running = False
                        elif not self.show_app:
                            if event.key == pygame.K_s:
                                self.cycle_spectrum_style()
                            elif event.key == pygame.K_c:
                                self.toggle_camera()
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # Dismiss overlay image on touch
                        with self._overlay_lock:
                            if self._overlay_image is not None:
                                self._overlay_image = None
                                continue
                        if self.show_app:
                            logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)
                            # Forward touch to active app
                            if self.app_manager and self.app_manager.is_active():
                                app_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=logical_pos, button=event.button)
                                self.app_manager.handle_event(app_event)
                            if self.terminal_system:
                                self.terminal_system.handle_app_click(logical_pos)
                        else:
                            if self.screensaver_manager:
                                self.screensaver_manager.reset_timer()

                            logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)

                            if self.show_camera and self.detection_manager.handle_click(logical_pos):
                                pass
                            elif self.terminal_system:
                                self.terminal_system.handle_mouse_down(logical_pos)
                                self.terminal_system.handle_click(logical_pos)
                    elif event.type == pygame.MOUSEBUTTONUP:
                        if not self.show_app and self.terminal_system:
                            self.terminal_system.handle_mouse_up()
                    elif event.type == pygame.MOUSEMOTION:
                        if self.show_app:
                            if self.app_manager and self.app_manager.is_active():
                                logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)
                                app_event = pygame.event.Event(pygame.MOUSEMOTION, pos=logical_pos)
                                self.app_manager.handle_event(app_event)
                        else:
                            if self.screensaver_manager:
                                self.screensaver_manager.reset_timer()
                    elif event.type == pygame.MOUSEWHEEL:
                        if not self.show_app and self.terminal_system:
                            self.terminal_system.handle_scroll_wheel(event.y)

                if self.terminal_system and not self.show_app:
                    self.terminal_system.handle_scroll_hold()

                # Check for pending/active overlay image
                _show_overlay = False
                with self._overlay_lock:
                    # Load pending image on main thread (X11 safety)
                    if self._overlay_pending_path is not None:
                        try:
                            img = pygame.image.load(self._overlay_pending_path)
                            iw, ih = img.get_size()
                            scale = min(self.logical_width / iw, self.logical_height / ih)
                            scaled = pygame.transform.smoothscale(img, (int(iw * scale), int(ih * scale)))
                            overlay = pygame.Surface((self.logical_width, self.logical_height))
                            overlay.fill((0, 0, 0))
                            overlay.blit(scaled, ((self.logical_width - scaled.get_width()) // 2,
                                                  (self.logical_height - scaled.get_height()) // 2))
                            self._overlay_image = overlay
                            self._overlay_expire = _time.time() + self._overlay_pending_duration
                        except Exception as e:
                            queue_message(f"[UI] Failed to load overlay image: {e}")
                        self._overlay_pending_path = None

                    # Check if overlay is still active
                    if self._overlay_image is not None:
                        if _time.time() < self._overlay_expire:
                            _show_overlay = True
                            original_surface.blit(self._overlay_image, (0, 0))
                        else:
                            self._overlay_image = None

                if _show_overlay:
                    if self.effective_rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                        self._render_surface_to_opengl(rotated_surface, texture_id)
                    else:
                        self._render_surface_to_opengl(original_surface, texture_id)
                    pygame.display.flip()
                    clock.tick(self.target_fps)
                    continue

                if self.screensaver_manager:
                    if self.show_app or self.show_camera:
                        if self.screensaver_manager.is_active():
                            self.screensaver_manager.deactivate()
                        self.screensaver_manager.reset_timer()
                    elif screensaver_timer > 0:
                        self.screensaver_manager.check_timeout()

                if self.app_manager and self.app_manager.is_active():
                    # Keep terminal data updated (cpu temp, battery, etc.) even during apps
                    if self.terminal_system:
                        self.terminal_system.update()

                    needs_flip = self.app_manager.render()

                    if needs_flip:
                        if self.terminal_system:
                            self.terminal_system.draw_back_button(original_surface)

                        if self.effective_rotate != 0:
                            rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                            self._render_surface_to_opengl(rotated_surface, texture_id)
                        else:
                            self._render_surface_to_opengl(original_surface, texture_id)
                        pygame.display.flip()
                    else:
                        if self.terminal_system:
                            self._draw_gl_back_button()
                        pygame.display.flip()

                    clock.tick(self.target_fps)
                    continue

                if self.screensaver_manager and self.screensaver_manager.is_active():
                    needs_flip = self.screensaver_manager.render()
                    
                    if needs_flip:
                        if self.effective_rotate != 0:
                            rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                            self._render_surface_to_opengl(rotated_surface, texture_id)
                        else:
                            self._render_surface_to_opengl(original_surface, texture_id)
                        pygame.display.flip()
                    
                    clock.tick(self.target_fps)
                    continue
                
                glViewport(0, 0, display_width, display_height)
                
                glMatrixMode(GL_PROJECTION)
                glLoadIdentity()
                gluOrtho2D(0, display_width, display_height, 0)
                
                glMatrixMode(GL_MODELVIEW)
                glLoadIdentity()
                
                glDisable(GL_DEPTH_TEST)
                glEnable(GL_TEXTURE_2D)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                
                glColor4f(1.0, 1.0, 1.0, 1.0)
                
                while glGetError() != GL_NO_ERROR:
                    pass


                if self.background_type == 'particles' and self.particle_system is not None:

                    if not self.show_camera:
                        self.particle_system.update()
                    self.particle_system.draw(original_surface)

                    if self.spectrum_system and not self.show_camera:
                        self.spectrum_system.update()
                        self.spectrum_system.draw(original_surface)

                    if self.show_camera and self.camera_module:
                        self._draw_camera(original_surface)

                    if self.terminal_system:
                        self.terminal_system.update()
                        self.terminal_system.draw(original_surface)

                    if self.effective_rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                        self._render_surface_to_opengl(rotated_surface, texture_id)
                    else:
                        self._render_surface_to_opengl(original_surface, texture_id)

                elif self.background_type == 'starfield' and self.starfield_system is not None:

                    if not self.show_camera:
                        self.starfield_system.update()
                    self.starfield_system.draw(original_surface)

                    if self.spectrum_system and not self.show_camera:
                        self.spectrum_system.update()
                        self.spectrum_system.draw(original_surface)

                    if self.show_camera and self.camera_module:
                        self._draw_camera(original_surface)

                    if self.terminal_system:
                        self.terminal_system.update()
                        self.terminal_system.draw(original_surface)

                    if self.effective_rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                        self._render_surface_to_opengl(rotated_surface, texture_id)
                    else:
                        self._render_surface_to_opengl(original_surface, texture_id)

                elif self.background_type == 'tesseract' and self.tesseract_system is not None:

                    if not self.show_camera:
                        self.tesseract_system.update()
                    self.tesseract_system.draw(original_surface)

                    if self.spectrum_system and not self.show_camera:
                        self.spectrum_system.update()
                        self.spectrum_system.draw(original_surface)

                    if self.show_camera and self.camera_module:
                        self._draw_camera(original_surface)

                    if self.terminal_system:
                        self.terminal_system.update()
                        self.terminal_system.draw(original_surface)

                    if self.effective_rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                        self._render_surface_to_opengl(rotated_surface, texture_id)
                    else:
                        self._render_surface_to_opengl(original_surface, texture_id)

                elif self.background_type == 'video' and self.video_system is not None:

                    if not self.show_camera:
                        self.video_system.update()
                    self.video_system.draw(original_surface)

                    if self.spectrum_system and not self.show_camera:
                        self.spectrum_system.update()
                        self.spectrum_system.draw(original_surface)

                    if self.show_camera and self.camera_module:
                        self._draw_camera(original_surface)

                    if self.terminal_system:
                        self.terminal_system.update()
                        self.terminal_system.draw(original_surface)

                    if self.effective_rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.effective_rotate)
                        self._render_surface_to_opengl(rotated_surface, texture_id)
                    else:
                        self._render_surface_to_opengl(original_surface, texture_id)

                pygame.display.flip()

                clock.tick(self.target_fps)

        except Exception as e:
            print(f"ERROR: UI run loop failed: {e}")
            import traceback
            traceback.print_exc()
            self.running = False

        finally:
            self._wifi_thread_running = False

            if self.app_manager:
                self.app_manager.deactivate()

            if self.spectrum_system:
                self.spectrum_system.stop_audio_stream()

            if self.camera_module:
                self.camera_module.stop()

            pygame.quit()