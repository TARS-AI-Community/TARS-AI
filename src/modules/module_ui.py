"""
GUI - V3
==========================
# atomikspace (discord)
# olivierdion1@hotmail.com
"""
import pygame
from pygame.locals import DOUBLEBUF
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

from module_config import load_config
from UI.module_ui_particles import ParticleSystem
from UI.module_ui_starfield import StarfieldSystem
from UI.module_ui_tesseract import TesseractSystem
from UI.module_ui_terminal import TerminalSystem
from UI.module_ui_spectrum import SpectrumSystem
from UI.module_ui_video import VideoSystem
from UI.module_ui_camera import CameraModule  

CONFIG = load_config()
screenWidth = CONFIG['UI']['screen_width']
screenHeight = CONFIG['UI']['screen_height']
rotation = CONFIG['UI']['rotation']
show_mouse = CONFIG['UI']['show_mouse']
use_camera_module = CONFIG['UI']['use_camera_module']
background_id = CONFIG['UI']['background_id']
fullscreen = CONFIG['UI']['fullscreen']
font_size = CONFIG['UI']['font_size']
target_fps = CONFIG['UI']['target_fps']
speechdelay = CONFIG['STT']['speechdelay']

BASE_WIDTH = 800
BASE_HEIGHT = 600

class UIManager(threading.Thread):
    def __init__(self, shutdown_event, battery_module, use_camera_module=use_camera_module, show_mouse=show_mouse, 
                 width: int = screenWidth, height: int = screenHeight, rotation_value=rotation, 
                 background_type='particles'):
        super().__init__()
        self.shutdown_event = shutdown_event
        self.battery_module = battery_module
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
        self.font_size = font_size
        self.silence_progress = 0
        self.speechdelay = speechdelay

        self.background_types = ['particles', 'starfield', 'tesseract', 'video']
        self.background_type = background_type
        self.current_background_index = self.background_types.index(background_type) if background_type in self.background_types else 0
        self.background_change_requested = False
        self.next_background = None

        from pathlib import Path
        self.settings_dir = Path.home() / ".local" / "share" / "tars_ai"
        self.settings_file = self.settings_dir / "ui_settings.json"
        self.spectrum_style = 'bars'  

        self._load_ui_settings()  

        if self.rotate in (0, 180):
            self.logical_width = self.width
            self.logical_height = self.height
        else:
            self.logical_width = self.height
            self.logical_height = self.width

        self.particle_system = None
        self.starfield_system = None
        self.tesseract_system = None
        self.video_system = None 

        self.spectrum_system = None

        self.terminal_system = None

        self.camera_module = None
        self.show_camera = False

        self.face_detector = None
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_detector = cv2.CascadeClassifier(cascade_path)
            if self.face_detector.empty():
                self.face_detector = None
            else:
                print("Face detector loaded")
        except Exception as e:
            print(f"Face detection initialization failed: {e}")
            self.face_detector = None

        if self.use_camera_module:
            try:
                self.camera_module = CameraModule(
                    self.logical_width,
                    self.logical_height,
                    use_camera_module=True
                )

                if not self.camera_module.running and self.camera_module.picam2 is not None:
                    print("Camera was stopped, restarting...")
                    self.camera_module.start_camera()

                print("Camera module initialized")
            except Exception as e:
                print(f"Failed to initialize camera: {e}")
                self.camera_module = None

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

                    print(f"Loaded UI settings: background={self.background_type}, spectrum={self.spectrum_style}")
        except Exception as e:
            print(f"Could not load UI settings: {e}")

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
            print(f"Could not save UI settings: {e}")

    def cycle_background(self):
        self.current_background_index = (self.current_background_index + 1) % len(self.background_types)
        self.next_background = self.background_types[self.current_background_index]
        self.background_change_requested = True

    def toggle_camera(self):
        self.show_camera = not self.show_camera

        if self.show_camera:
            if self.terminal_system:
                self.terminal_system.set_camera_active(True)
        else:
            if self.terminal_system:
                self.terminal_system.set_camera_active(False)

    def pause(self):
        self.paused = True
        print("UIManager paused")

    def resume(self):
        self.paused = False
        print("UIManager resumed")

    def exit_program(self):
        print("Program exit initiated by user")
        self.running = False
        self.shutdown_event.set()
        import os
        os._exit(0)  

    def initiate_shutdown(self):
        print("System shutdown initiated by user")
        self.running = False
        self.shutdown_event.set()
        import subprocess
        import os
        try:
            subprocess.Popen(['sudo', 'shutdown', 'now'])  

        except Exception as e:
            print(f"Failed to shutdown system: {e}")
        os._exit(0)  

    def silence(self, progress):
        self.silence_progress = progress
        if self.spectrum_system is not None:
            self.spectrum_system.silence(progress, self.speechdelay)

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

    def _transform_mouse_pos(self, screen_pos, display_width, display_height):
        x, y = screen_pos

        if self.rotate == 0:
            return (x, y)

        if self.rotate in (90, 270):
            rotated_width = self.logical_height
            rotated_height = self.logical_width
        else:
            rotated_width = self.logical_width
            rotated_height = self.logical_height

        offset_x = (display_width - rotated_width) // 2
        offset_y = (display_height - rotated_height) // 2

        x -= offset_x
        y -= offset_y

        if self.rotate == 90:
            logical_x = self.logical_width - y
            logical_y = x

        elif self.rotate == 180:
            logical_x = self.logical_width - x
            logical_y = self.logical_height - y

        elif self.rotate == 270:
            logical_x = y
            logical_y = self.logical_height - x
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

        camera_w = int(self.logical_width * 0.8)
        camera_h = int(self.logical_height * 0.8)
        camera_x = (self.logical_width - camera_w) // 2
        camera_y = (self.logical_height - camera_h) // 2

        detected_frame = frame
        if self.face_detector is not None:

            frame_array = pygame.surfarray.array3d(frame)
            frame_array = np.transpose(frame_array, (1, 0, 2))
            frame_array = np.ascontiguousarray(frame_array)

            frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)

            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            for (x, y, w_box, h_box) in faces:

                cv2.rectangle(frame_bgr, (x, y), (x+w_box, y+h_box), (0, 255, 255), 2)
                label = "FACE"
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(frame_bgr, (x, y-20), (x+label_size[0]+6, y), (0, 255, 255), -1)
                cv2.putText(frame_bgr, label, (x+3, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            frame_rgb = np.transpose(frame_rgb, (1, 0, 2))
            detected_frame = pygame.surfarray.make_surface(frame_rgb)

        scaled_frame = pygame.transform.scale(detected_frame, (camera_w, camera_h))

        border_rect = pygame.Rect(camera_x - 2, camera_y - 2, camera_w + 4, camera_h + 4)
        pygame.draw.rect(surface, (0, 255, 255), border_rect, 2)

        surface.blit(scaled_frame, (camera_x, camera_y))

    def run(self) -> None:
        try:
            pygame.init()
            pygame.mouse.set_visible(self.show_mouse)
            os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'

            display_flags = pygame.DOUBLEBUF | pygame.HWSURFACE

            if fullscreen:
                display_flags |= pygame.FULLSCREEN

            display_width = self.width
            display_height = self.height

            screen = pygame.display.set_mode((display_width, display_height), display_flags)
            pygame.display.set_caption("UI Manager")

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
                    on_background_change=self.cycle_background,
                    on_shutdown=self.initiate_shutdown,
                    on_spectrum_change=self.cycle_spectrum_style,
                    on_camera_toggle=self.toggle_camera,  
                    on_exit=self.exit_program  

                )

            except Exception as e:
                import traceback
                traceback.print_exc()
                return

            clock = pygame.time.Clock()
            font = pygame.font.Font("UI/mono.ttf", self.font_size)
            self.running = True

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
                        if event.key == pygame.K_ESCAPE:
                            self.running = False
                        elif event.key == pygame.K_s:  # Press 'S' to cycle spectrum styles
                            self.cycle_spectrum_style()
                        elif event.key == pygame.K_c:  # Press 'C' to toggle camera
                            self.toggle_camera()
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if self.terminal_system:
                            logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)
                            self.terminal_system.handle_mouse_down(logical_pos)
                            self.terminal_system.handle_click(logical_pos)
                    elif event.type == pygame.MOUSEBUTTONUP:
                        if self.terminal_system:
                            logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)
                            self.terminal_system.handle_mouse_up(logical_pos)
                    elif event.type == pygame.MOUSEMOTION:
                        if self.terminal_system:
                            logical_pos = self._transform_mouse_pos(event.pos, display_width, display_height)
                            self.terminal_system.handle_mouse_motion(logical_pos)
                    elif event.type == pygame.MOUSEWHEEL:
                        if self.terminal_system:
                            self.terminal_system.handle_scroll_wheel(event.y)

                screen.fill((0, 0, 0))

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

                    if self.rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.rotate)
                        rotated_rect = rotated_surface.get_rect(center=(display_width // 2, display_height // 2))
                        screen.blit(rotated_surface, rotated_rect)
                    else:
                        screen.blit(original_surface, (0, 0))

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

                    if self.rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.rotate)
                        rotated_rect = rotated_surface.get_rect(center=(display_width // 2, display_height // 2))
                        screen.blit(rotated_surface, rotated_rect)
                    else:
                        screen.blit(original_surface, (0, 0))

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

                    if self.rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.rotate)
                        rotated_rect = rotated_surface.get_rect(center=(display_width // 2, display_height // 2))
                        screen.blit(rotated_surface, rotated_rect)
                    else:
                        screen.blit(original_surface, (0, 0))

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

                    if self.rotate != 0:
                        rotated_surface = pygame.transform.rotate(original_surface, self.rotate)
                        rotated_rect = rotated_surface.get_rect(center=(display_width // 2, display_height // 2))
                        screen.blit(rotated_surface, rotated_rect)
                    else:
                        screen.blit(original_surface, (0, 0))

                pygame.display.flip()

                clock.tick(self.target_fps)

        except Exception as e:
            print(f"Fatal UI error: {e}")
            import traceback
            traceback.print_exc()
            self.running = False

        finally:

            if self.spectrum_system:
                self.spectrum_system.stop_audio_stream()

            if self.camera_module:
                self.camera_module.stop()

            pygame.quit()