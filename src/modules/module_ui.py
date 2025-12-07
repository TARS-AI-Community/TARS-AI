# ----------------------------------------------
# atomikspace (discord)
# olivierdion1@hotmail.com
# ----------------------------------------------
import pygame
from pygame.locals import DOUBLEBUF, OPENGL
import OpenGL.GL as GL
import OpenGL.GLU as GLU
import threading
import queue
from typing import Dict, Any, List
import time
from datetime import datetime
import numpy as np
import random
import math
import cv2
import sys
import subprocess
import os
import sounddevice as sd
import json
import requests
from io import BytesIO
from PIL import Image
import socket

from module_config import load_config
from UI.module_ui_camera import CameraModule
from UI.module_ui_spectrum import SineWaveVisualizer, BarVisualizer
from UI.module_ui_buttons import Button
from UI.module_ui_fake_terminal import ConsoleAnimation
from UI.module_ui_hal import HalAnimation 
from UI.module_ui_brain import BrainVisualization

# --- Configuration and Constants ---
CONFIG = load_config()
UI_template = CONFIG['UI']['UI_template']
screenWidth = CONFIG['UI']['screen_width']
screenHeight = CONFIG['UI']['screen_height']
rotation = CONFIG['UI']['rotation']
maximize_console = CONFIG['UI']['maximize_console']
show_mouse = CONFIG['UI']['show_mouse']
use_camera_module = CONFIG['UI']['use_camera_module']
background_id = CONFIG['UI']['background_id']
fullscreen = CONFIG['UI']['fullscreen']
font_size = CONFIG['UI']['font_size']
neural_net = CONFIG['UI']['neural_net']
neural_net_always_visible = CONFIG['UI']['neural_net_always_visible']
target_fps = CONFIG['UI']['target_fps']

BASE_WIDTH = 800
BASE_HEIGHT = 600

# --- Box and Layout Functions ---
class Box:
    def __init__(self, name, x, y, width, height, rotation, original_width, original_height):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rotation = rotation
        self.original_width = original_width
        self.original_height = original_height

    def to_tuple(self):
        return (self.x, self.y, self.width, self.height)

def load_layout_config(config_file):
    config_path = os.path.join("UI", config_file)
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading layout config from {config_path}: {e}")
        return {"landscape": [], "portrait": []}
    
def get_layout_dimensions(layout_config, screen_width, screen_height, rotation):
    """
    Calculate layout dimensions with correct rotation handling.
    
    Parameters:
    - layout_config: Dictionary with layout configurations
    - screen_width: Physical screen width (e.g., 1024)
    - screen_height: Physical screen height (e.g., 600)
    - rotation: Screen rotation in degrees (0, 90, 180, or 270)
    
    Returns:
    - A list of Box objects with correctly calculated positions and dimensions
    """
    # For a 270Â° rotation with 1024x600 screen:
    # - Physical screen is still 1024x600
    # - But the logical screen becomes 600x1024 (portrait orientation)
    
    # Select layout based on orientation
    layout_key = "landscape" if rotation in (0, 180) else "portrait"
    
    # For 270Â° rotation, logical dimensions are swapped
    if rotation in (0, 180):
        logical_width, logical_height = screen_width, screen_height  # 1024x600
    else:  # rotation in (90, 270)
        logical_width, logical_height = screen_height, screen_width  # 600x1024
    
    layout = []
    for box_config in layout_config.get(layout_key, []):
        # Calculate percentage-based dimensions
        logical_x = box_config["x"] * logical_width
        logical_y = box_config["y"] * logical_height
        logical_width_box = box_config["width"] * logical_width
        logical_height_box = box_config["height"] * logical_height
        
        # Apply rotation transformations
        if rotation == 0:
            physical_x = int(logical_x)
            physical_y = int(logical_y)
            physical_width = int(logical_width_box)
            physical_height = int(logical_height_box)
        elif rotation == 180:
            physical_x = int(screen_width - logical_x - logical_width_box)
            physical_y = int(screen_height - logical_y - logical_height_box)
            physical_width = int(logical_width_box)
            physical_height = int(logical_height_box)
        elif rotation == 90:
            # When the screen is rotated 90Â°, Y becomes X and X becomes inverted Y
            physical_x = int(logical_y)  # Y â†’ X
            physical_y = int(logical_width - logical_x - logical_width_box)  # Inverted X â†’ Y
            physical_width = int(logical_height_box)
            physical_height = int(logical_width_box)
        elif rotation == 270:
            # When the screen is rotated 270Â°, Y becomes inverted X and X becomes Y
            physical_x = int(logical_height - logical_y - logical_height_box)  # Inverted Y â†’ X
            physical_y = int(logical_x)  # X â†’ Y
            physical_width = int(logical_height_box)
            physical_height = int(logical_width_box)
        
        layout.append(Box(
            box_config["name"],
            physical_x, 
            physical_y,
            physical_width,
            physical_height,
            rotation,
            int(logical_width_box),
            int(logical_height_box)
        ))
    
    return layout

# --- Star Class for Background Effects ---
class Star:
    def __init__(self, width: int, height: int):
        self.width = max(2, width)
        self.height = max(2, height)
        self.reset()
            
    def reset(self):
        safe_width = max(2, self.width)
        safe_height = max(2, self.height)
        min_x, max_x = sorted([-safe_width, safe_width])
        min_y, max_y = sorted([-safe_height, safe_height])
        self.x = random.randrange(min_x, max_x)
        self.y = random.randrange(min_y, max_y)
        min_z = 1
        max_z = max(2, safe_width)
        self.z = random.randrange(min_z, max_z)
        self.speed = random.uniform(2, 5)
    
    def moveStars(self):
        self.z -= self.speed
        if self.z <= 0:
            self.reset()
    
    def drawStars(self, screen):
        factor = 200.0 / self.z
        x = self.x * factor + self.width // 2
        y = self.y * factor + self.height // 2
        size = max(1, min(5, 200.0 / self.z))
        depth_factor = self.z / self.width
        r = int(173 * (1 - depth_factor))
        g = int(216 * (1 - depth_factor))
        b = int(230 * (1 - depth_factor))
        flicker = random.randint(-10, 10)
        r, g, b = (max(0, min(255, c + flicker)) for c in (r, g, b))
        if 0 <= x < self.width and 0 <= y < self.height:
            pygame.draw.circle(screen, (r, g, b), (int(x), int(y)), int(size))

# --- StreamingAvatar Class ---
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]

class StreamingAvatar:
    def __init__(self, width=800, height=600, base_width=800, base_height=600,
                 stream_url=f"http://{local_ip}:5012/stream"):
        self.width = max(1, width)
        self.height = max(1, height)
        self.base_width = base_width
        self.base_height = base_height
        self.scale_factor = min(self.width / base_width, self.height / base_height)
        self.stream_url = stream_url
        self.raw_image = None      # Resized numpy array (RGB)
        self.stream_image = None   # Cached pygame Surface (from raw_image)
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.running = True
        self.rotation = 0

        self.image_lock = threading.Lock()

        #print("Starting StreamingAvatar fetch thread...")
        self.stream_thread = threading.Thread(target=self.fetch_stream, daemon=True)
        self.stream_thread.start()

    def fetch_stream(self):
        boundary = b"--frame\r\n"  # Must match server's boundary
        buffer = b""
        while self.running:
            try:
                #print(f"Connecting to stream at {self.stream_url}")
                response = requests.get(self.stream_url, stream=True, timeout=5)
                if response.status_code == 200:
                    #print("Connected to stream. Reading data...")
                    for chunk in response.iter_content(chunk_size=1024):
                        if not self.running:
                            break
                        #print(f"Received chunk of size {len(chunk)}: {chunk[:50]}")
                        buffer += chunk
                        while boundary in buffer:
                            parts = buffer.split(boundary, 1)
                            frame_chunk = parts[0]
                            buffer = parts[1]
                            header_end = frame_chunk.find(b"\r\n\r\n")
                            if header_end != -1:
                                png_data = frame_chunk[header_end+4:].strip()
                                if png_data:
                                    try:
                                        pil_image = Image.open(BytesIO(png_data))
                                        pil_image = pil_image.convert("RGBA")
                                        np_image = np.array(pil_image)
                                        resized_image = cv2.resize(np_image, (self.width, self.height))
                                        with self.image_lock:
                                            self.raw_image = resized_image
                                        #print("Fetched and processed one PNG frame; new image shape:", resized_image.shape)
                                    except Exception as img_err:
                                        print("Error processing PNG image:", img_err)
                else:
                    #print(f"Failed to fetch stream: HTTP {response.status_code}")
                    time.sleep(1)
            except Exception as e:
                #print("Error fetching stream:", e)
                time.sleep(1)
            time.sleep(0.01)

    def update(self, rotation=0):
        """
        Update the surface with the latest stream image, ensuring transparency.
        """
        self.surface.fill((0, 0, 0, 0))  # Clear with transparency
        with self.image_lock:
            if self.raw_image is not None:
                # Create surface from RGBA data, no rotation needed here
                self.stream_image = pygame.image.frombuffer(self.raw_image.tobytes(), (self.width, self.height), "RGBA")
                if self.stream_image:
                    # Blit the image directly at the top-left (no rotation)
                    self.surface.blit(self.stream_image, (0, 0))
        return self.surface

    def stop_streaming(self):
        self.running = False
        if self.stream_thread:
            self.stream_thread.join()

    def get_surface(self):
        return self.surface

# --- UIManager Class ---
class UIManager(threading.Thread):
    def __init__(self, shutdown_event, battery_module, use_camera_module=use_camera_module, show_mouse=show_mouse, 
                 width: int = screenWidth, height: int = screenHeight, rotation_value=rotation):
        super().__init__()
        self.target_fps = target_fps
        self.show_mouse = show_mouse
        self.use_camera_module = use_camera_module
        self.neural_net_always_visible = neural_net_always_visible 
        self.neural_net = neural_net   
        self.change_camera_resolution = False

        self.width = width
        self.height = height
        self.rotate = rotation_value

        # Compute logical dimensions
        if self.rotate in (0, 180):
            self.logical_width = self.width
            self.logical_height = self.height
        else:
            self.logical_width = self.height
            self.logical_height = self.width

        # Load layout from JSON.
        self.layout_config = load_layout_config(UI_template)
        self.layouts = get_layout_dimensions(self.layout_config, width, height, self.rotate)
        self.box_map = {box.name: box for box in self.layouts}

        # Get panel references.
        self.console_box = self.box_map.get("console")
        self.hal_box = self.box_map.get("hal")
        self.fake_terminal_box = self.box_map.get("fake_terminal")
        self.img_box = self.box_map.get("img")
        self.camera_box = self.box_map.get("camera")
        self.spectrum_box = self.box_map.get("spectrum")
        self.system_box = self.box_map.get("buttons")
        self.brain_box = self.box_map.get("brain")
        self.avatar_box = self.box_map.get("avatar")

        # Initialize components if their boxes exist.
        self.hal_anim = HalAnimation(self.hal_box.original_width, self.hal_box.original_height) if self.hal_box else None
        self.terminal_anim = ConsoleAnimation(self.fake_terminal_box.original_width, self.fake_terminal_box.original_height) if self.fake_terminal_box else None

        self.shutdown_confirmation = False
        self.confirmation_buttons = []

        if self.img_box:
            self.img_folder = "UI/img"
            self.current_image = None
            self.next_image = None
            self.last_switch_time = 0
            self.last_image_filename = None
            self.crossfade_duration = 1000
            self.display_time = 15000
            self.alpha = 255
        else:
            self.img_folder = None

        self.camera_module = (CameraModule(self.camera_box.original_width, self.camera_box.original_height, use_camera_module)
                              if (self.camera_box and use_camera_module) else None)

        self.sineWaveVisualizer = (SineWaveVisualizer(self.spectrum_box.width, self.spectrum_box.height, self.spectrum_box.rotation)
                                   if self.spectrum_box else None)

        if self.brain_box:
            self.brain = BrainVisualization(self.width, self.height)
            self.barVisualizer = BarVisualizer(self.brain_box.original_width, self.brain_box.original_height,
                                                int(self.brain_box.original_width / 3))
        else:
            self.brain = None
            self.barVisualizer = None

        # Initialize StreamingAvatar if "avatar" panel is defined.
        if self.avatar_box:
            self.avatar_anim = StreamingAvatar(width=self.avatar_box.original_width, height=self.avatar_box.original_height)
        else:
            self.avatar_anim = None

        self.background_image = pygame.image.load("UI/background.png")
        #self.background_image = pygame.transform.scale(self.background_image, (self.logical_width, self.logical_height))
        self.stars: List[Star] = [Star(self.logical_width, self.logical_height) for _ in range(1800)]
        
        self.scale = min(width / BASE_WIDTH, height / BASE_HEIGHT)

        self.spectrum = []
        self.buttons = []
        self.running = True
        self.data_queue = queue.Queue()
        self.data_store: Dict[str, Any] = {}
        self.shutdown_event = shutdown_event
        self.silence_progress = 0
        self.new_data_added = False
        self.brain_visible = False
        self.expanded_box = ""
        self.background_id = background_id
        self.maximize_console = maximize_console
        if maximize_console and self.console_box:
            self.expanded_box = "console"
        self.video_path = "UI/video/bg1.mp4"
        self.cap = None
        self.video_enabled = False

        self.scroll_offset = 10
        self.max_lines = 15
        self.font_size = font_size
        self.line_height = self.font_size + int(7 * self.scale)
        self.stars: List[Star] = [Star(width, height) for _ in range(1800)]
        self.colors = {
            'TARS': (76, 194, 230),
            '*': (0, 215, 90),
            'USER': (255, 255, 255),
            'INFO': (200, 200, 200),
            'DEBUG': (100, 200, 100),
            'ERROR': (255, 100, 100),
            'SYSTEM': (100, 100, 255),
            'default': (200, 200, 200)
        }
        self.audio_thread = threading.Thread(target=self.audio_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()

        self.battery = battery_module
        self.battery_percent = 100
        status = self.battery.get_battery_status()
        self.battery_percent = status['normalized_percentage']

    def silence(self, progress):
        self.silence_progress = progress
        if progress != 0:
            self.start_time = time.time()

    def draw_starfield(self, surface):
            logical_background = pygame.Surface((self.logical_width, self.logical_height), pygame.SRCALPHA)
            for star in self.stars:
                star.moveStars()
                star.drawStars(logical_background)
            rotated_background = pygame.transform.rotate(logical_background, -self.rotate)
            surface.blit(rotated_background, (0, 0))

    def update_data(self, key: str, value: Any, msg_type: str = 'INFO') -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.data_queue.put((timestamp, key, value, msg_type))
        self.data_store[f"{timestamp}_{key}"] = (value, msg_type)
        self.new_data_added = True
        
    # --- Drawing Methods ---
    def draw_avatar(self, surface, font):
        if not self.avatar_box or self.expanded_box not in ["", "avatar"]:
            return
        box = self.avatar_box
        if self.expanded_box == "avatar":
            x = y = 0
            width = self.width if self.rotate not in [90, 270] else self.height
            height = self.height if self.rotate not in [90, 270] else self.width
            if self.avatar_anim:
                self.avatar_anim.update_size(width, height)
        else:
            x, y = box.x, box.y
            width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        if self.avatar_anim:
            avatar_surface = self.avatar_anim.update(box.rotation)
            scaled_avatar = pygame.transform.scale(avatar_surface, (width, height))
            box_surface.blit(scaled_avatar, (0, 0))
        else:
            box_surface.fill((50, 50, 50))
        border_color = (76, 194, 230, 255)
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_console(self, surface, font):
        if not self.console_box or self.expanded_box not in ["", "console"]:
            return
        box = self.console_box
        x, y = box.x, box.y
        width, height = box.original_width, box.original_height
        if self.expanded_box == "console":
            x, y = 0, 0
            width, height = self.width, self.height
            if box.rotation in (90, 270):
                width, height = self.height, self.width

        console_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        console_background = (0, 0, 0, 160)
        pygame.draw.rect(console_surface, console_background, (0, 0, width, height))
        pygame.draw.rect(console_surface, (76, 194, 230, 255), (0, 0, width, height), int(2 * self.scale))
        title = font.render("(" + str(self.battery_percent) + "%) System Console", True, (150, 150, 150))
        console_surface.blit(title, (10, 5))
        


        display_lines = []
        for key, (value, msg_type) in self.data_store.items():
            actual_key = '_'.join(key.split('_')[1:])
            text = f"{actual_key}: {str(value)}"
            words = text.split()
            line = ''
            for word in words:
                test_line = line + word + ' '
                if font.size(test_line)[0] < (width - 40):
                    line = test_line
                else:
                    if line:
                        display_lines.append((line.strip(), msg_type))
                        line = word + ' '
                    else:
                        display_lines.append((word + ' ', msg_type))
                        line = ''
            if line:
                display_lines.append((line.strip(), msg_type))
        self.total_display_lines = len(display_lines)
        visible_line_count = (height - 40) // self.line_height
        self.visible_line_count = visible_line_count
        if self.new_data_added:
            self.scroll_offset = max(0, self.total_display_lines - visible_line_count)
            self.new_data_added = False
        y_pos = 40
        visible_lines = display_lines[self.scroll_offset:self.scroll_offset + visible_line_count]
        for line, msg_type in visible_lines:
            color = self.colors.get(msg_type, self.colors['default'])
            text_surface = font.render(line, True, color)
            console_surface.blit(text_surface, (10, y_pos))
            y_pos += self.line_height
        if self.total_display_lines > visible_line_count:
            scroll_pct = self.scroll_offset / (self.total_display_lines - visible_line_count)
            indicator_height = (height * visible_line_count) / self.total_display_lines
            indicator_pos = scroll_pct * (height - indicator_height)
            pygame.draw.rect(console_surface, (100, 100, 100, 255),
                             (width - int(15 * self.scale), indicator_pos, int(5 * self.scale), indicator_height))
        self.max_scroll = max(0, self.total_display_lines - visible_line_count)
        self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
        rotated_surface = pygame.transform.rotate(console_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_camera(self, surface, font):
        if not self.camera_box or self.expanded_box not in ["", "camera"]:
            return
        box = self.camera_box
        if self.expanded_box == "camera":
            x = y = 0
            width = self.width if self.rotate not in [90, 270] else self.height
            height = self.height if self.rotate not in [90, 270] else self.width
            if self.change_camera_resolution and self.camera_module:
                self.camera_module.update_size(width, height)
                self.change_camera_resolution = False
        else:
            x, y = box.x, box.y
            width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        if self.use_camera_module and self.camera_module:
            camera_frame = self.camera_module.get_frame()
            if camera_frame:
                scaled_frame = pygame.transform.scale(camera_frame, (width, height))
                box_surface.blit(scaled_frame, (0, 0))
        border_color = (76, 194, 230, 255)
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_fake_terminal(self, surface, font):
        if not self.fake_terminal_box or self.expanded_box not in ["", "fake_terminal"]:
            return
        box = self.fake_terminal_box
        if self.expanded_box == "fake_terminal":
            x = y = 0
            width, height = self.width, self.height
        else:
            x, y = box.x, box.y
            width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        box_surface.fill((0, 0, 0, 128))
        border_color = (76, 194, 230, 255)
        if self.terminal_anim:
            anim_surface = self.terminal_anim.update()
            box_surface.blit(anim_surface, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_hal(self, surface, font):
        if not self.hal_box or self.expanded_box not in ["", "hal"]:
            return
        box = self.hal_box
        x, y = box.x, box.y
        width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        border_color = (76, 194, 230, 255)
        if self.hal_anim:
            self.hal_anim.update()
            box_surface = self.hal_anim.get_surface()
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_spectrum(self, surface, font):
        if not self.spectrum_box or self.expanded_box not in ["", "spectrum"]:
            return

        box = self.spectrum_box

        # choose a surface to draw (your visualizer or a fallback)
        if self.sineWaveVisualizer:
            box_surface = self.sineWaveVisualizer.update(self.spectrum)
        else:
            box_surface = pygame.Surface((box.original_width, box.original_height), pygame.SRCALPHA)
            box_surface.fill((0, 0, 0, 128))

        border_color = (76, 194, 230, 255)

        # --- Progress bar for listening ---
        # Use the spectrum box dimensions, not brain_box (which may be None)
        width, height = box.original_width, box.original_height
        padding = int(15 * self.scale)
        progress_bar_height = int(10 * self.scale)
        available_width = width - (padding * 2)          # <- changed
        progress_bar_x = padding
        progress_bar_y = padding
        max_frames = 20

        if self.silence_progress > 0:
            pygame.draw.rect(box_surface, (100, 100, 100),
                            (progress_bar_x, progress_bar_y, available_width, progress_bar_height), 1)
            progress_fraction = self.silence_progress / max_frames
            fill_width = int(available_width * progress_fraction)
            pygame.draw.rect(box_surface, (76, 194, 230),
                            (progress_bar_x, progress_bar_y, fill_width, progress_bar_height))

        # border & blit
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (box.x, box.y))

    def draw_brain(self, surface, font):
        if not self.brain or not self.brain_box or self.expanded_box not in ["", "brain"]:
            return
        box = self.brain_box
        x, y = box.x, box.y
        width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        box_surface.fill((0, 0, 0, 0))

        #if self.barVisualizer:
            #box_surface = self.barVisualizer.update(self.spectrum, box_surface)
            
        border_color = (76, 194, 230, 255)
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))

    def load_random_image(self, img_folder, size, last_filename=None):
        img_files = [f for f in os.listdir(img_folder) if f.endswith(('png', 'jpg', 'jpeg'))]
        if not img_files:
            raise FileNotFoundError("No images found in the img folder.")
        if last_filename and last_filename in img_files and len(img_files) > 1:
            img_files.remove(last_filename)
        img_path = os.path.join(img_folder, random.choice(img_files))
        self.last_image_filename = os.path.basename(img_path)
        return pygame.transform.scale(pygame.image.load(img_path).convert_alpha(), size)

    def update_images(self):
        now = pygame.time.get_ticks()
        elapsed = now - self.last_switch_time
        if elapsed >= self.display_time + self.crossfade_duration:
            self.current_image = self.next_image
            self.next_image = None
            self.last_switch_time = now
            self.alpha = 255
        elif elapsed >= self.display_time:
            if self.next_image is None:
                self.next_image = self.load_random_image(
                    self.img_folder,
                    (self.img_box.original_width, self.img_box.original_height),
                    self.last_image_filename
                )
            self.alpha = max(0, 255 - int((elapsed - self.display_time) / self.crossfade_duration * 255))

    def draw_img(self, surface, font):
        if not self.img_box or self.expanded_box not in ["", "img"]:
            return
        box = self.img_box
        x, y = box.x, box.y
        width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        if self.current_image is None:
            self.current_image = self.load_random_image(self.img_folder, (width, height))
        box_surface.blit(self.current_image, (0, 0))
        if self.next_image:
            fade_surface = pygame.Surface((width, height), pygame.SRCALPHA)
            fade_surface.blit(self.next_image, (0, 0))
            fade_surface.set_alpha(255 - self.alpha)
            box_surface.blit(fade_surface, (0, 0))
        border_color = (76, 194, 230, 255)
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (x, y))
        self.update_images()

    def draw_system(self, surface, font):
        if not self.system_box or self.expanded_box not in ["", "buttons"]:
            return
        box = self.system_box
        x, y = box.x, box.y
        width, height = box.original_width, box.original_height
        box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        border_color = (76, 194, 230, 255)
        pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
        rotated_temp = pygame.transform.rotate(box_surface, box.rotation)
        offset_x = (rotated_temp.get_width() - box_surface.get_width()) // 2
        offset_y = (rotated_temp.get_height() - box_surface.get_height()) // 2
        self.buttons = []
        spacing = int(140 * self.scale)
        for i, label in enumerate(["SHUTDOWN", "BG"]):
            relative_x = int(10 * self.scale) + (i * spacing)
            relative_y = int(10 * self.scale)
            button_width = int(130 * self.scale)
            button_height = box.original_height - int(20 * self.scale)
            if box.rotation == 0:
                real_x = box.x + relative_x
                real_y = box.y + relative_y
            elif box.rotation == 90:
                real_x = box.x + offset_x + relative_y
                real_y = box.y + offset_y + (box_surface.get_width() - relative_x - button_width)
            elif box.rotation == 180:
                real_x = box.x + offset_x + (box_surface.get_width() - relative_x - button_width)
                real_y = box.y + offset_y + (box_surface.get_height() - relative_y - button_height)
            elif box.rotation == 270:
                real_x = box.x + (box.original_height - relative_y - button_height)
                real_y = box.y + relative_x
            button = Button(real_x, real_y, button_width, button_height, box.rotation, label, font, action=label.lower())
            self.buttons.append(button)
            button_surface = button.draw_button(font)
            box_surface.blit(button_surface, (relative_x, relative_y))
        rotated_surface = pygame.transform.rotate(box_surface, box.rotation)
        surface.blit(rotated_surface, (box.x, box.y))

    def on_click(self, action):
        if isinstance(action, str) and hasattr(self, action):
            method = getattr(self, action)
            if callable(method):
                method()

    def expand_panel(self, pos):
        mouse_x, mouse_y = pos
        for box in self.layouts:
            x, y = box.x, box.y
            x2 = box.x + box.width
            y2 = box.y + box.height
            if mouse_x >= x and mouse_y >= y and mouse_x <= x2 and mouse_y <= y2:
                return box.name
        return None

    def bg(self):
        self.background_id = (self.background_id + 1) % 6
        print("Background ID is now", self.background_id)

    def wake(self):
        if self.neural_net and self.brain:
            self.start_time = time.time()
            self.brain.add_ripple_effect(
                origin=(0, 0, 0),
                speed=5.5,
                duration=3.0,
                amplitude=0.6,
                color=(82, 255, 139),
                thickness=1
            )
            self.brain_visible = True

    def think(self):
        if self.neural_net and self.brain:
            self.start_time = time.time()
            self.brain.add_band_effect(
                origin=(0, -5, 0),
                direction=(0, 1, 0),
                speed=4.0,
                color=(50, 200, 255),
                band_width=0.2
            )

    def save_memory(self):
        if self.neural_net and self.brain:
            self.start_time = time.time()
            self.brain.add_matrix_data_insertion(
                color=(0, 255, 0),
                duration=4.0,
                speed=1.0,
                density=2.8
            )

    def audio_loop(self):
        SAMPLE_RATE = 22500
        CHUNK_SIZE = 1024
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while self.running:
                data, _ = stream.read(CHUNK_SIZE)
                self.process_audio(data)

    def process_audio(self, data, flatten_factor=0.2):
        if data.shape[1] == 2:
            left_channel = data[:, 0]
            right_channel = data[:, 1]
            data = (left_channel + right_channel) * flatten_factor
        else:
            data = data.flatten()
        fft_data = np.abs(np.fft.fft(data))
        self.spectrum = fft_data[:len(fft_data)//2]

    def load_video(self, video_path):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            print(f"Error: Could not open video file {video_path}")
            self.video_enabled = False
        else:
            self.video_enabled = True
            self.video_path = video_path

    def draw_video(self, surface):
        if not self.video_enabled:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_surface = pygame.surfarray.make_surface(np.flipud(frame))
        frame_surface = pygame.transform.scale(frame_surface, (self.width, self.height))
        surface.blit(frame_surface, (0, 0))

    def draw_starfield(self, surface):
        for star in self.stars:
            star.moveStars()
            star.drawStars(surface)
    
    def draw_shutdown_confirmation(self, surface, font):
        if not self.shutdown_confirmation:
            return
        dialog_width = int(600 * self.scale)
        dialog_height = int(400 * self.scale)
        dialog_surface = pygame.Surface((dialog_width, dialog_height), pygame.SRCALPHA)
        dialog_surface.fill((20, 20, 20, 250))
        pygame.draw.rect(dialog_surface, (76, 194, 230, 255), (0, 0, dialog_width, dialog_height), int(3 * self.scale))
        title_font = pygame.font.Font("UI/mono.ttf", int(self.font_size * 1.5))
        title = title_font.render("SHUTDOWN CONFIRMATION", True, (76, 194, 230))
        title_rect = title.get_rect(center=(dialog_width // 2, int(40 * self.scale)))
        dialog_surface.blit(title, title_rect)
        message = font.render("What would you like to do?", True, (200, 200, 200))
        message_rect = message.get_rect(center=(dialog_width // 2, int(100 * self.scale)))
        dialog_surface.blit(message, message_rect)
        button_width = int(500 * self.scale)
        button_height = int(60 * self.scale)
        button_spacing = int(20 * self.scale)
        start_y = int(150 * self.scale)
        
        button_configs = [
            ("SHUTDOWN APP ONLY", "shutdown_app_only"),
            ("SHUTDOWN RASPBERRY PI", "shutdown_pi"),
            ("CANCEL", "cancel_shutdown")
        ]
        for i, (label, action) in enumerate(button_configs):
            button_x_relative = (dialog_width - button_width) // 2
            button_y_relative = start_y + (i * (button_height + button_spacing))
            temp_button = Button(
                0, 0, button_width, button_height, 0, label, font, action=action
            )
            button_surface = temp_button.draw_button(font)
            dialog_surface.blit(button_surface, (button_x_relative, button_y_relative))
        
        rotated_dialog = pygame.transform.rotate(dialog_surface, self.rotate)
        center_x = self.width // 2
        center_y = self.height // 2
        rotated_width = rotated_dialog.get_width()
        rotated_height = rotated_dialog.get_height()
        dialog_x = center_x - rotated_width // 2
        dialog_y = center_y - rotated_height // 2
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        surface.blit(rotated_dialog, (dialog_x, dialog_y))
        self.confirmation_buttons = []
        
        for i, (label, action) in enumerate(button_configs):
            relative_x = (dialog_width - button_width) // 2
            relative_y = start_y + (i * (button_height + button_spacing))
            
            if self.rotate == 0:
                real_x = dialog_x + relative_x
                real_y = dialog_y + relative_y
                final_width = button_width
                final_height = button_height
            elif self.rotate == 90:
                real_x = dialog_x + relative_y
                real_y = dialog_y + (dialog_width - relative_x - button_width)
                final_width = button_height
                final_height = button_width
            elif self.rotate == 180:
                real_x = dialog_x + (dialog_width - relative_x - button_width)
                real_y = dialog_y + (dialog_height - relative_y - button_height)
                final_width = button_width
                final_height = button_height
            elif self.rotate == 270:
                real_x = dialog_x + (dialog_height - relative_y - button_height)
                real_y = dialog_y + relative_x
                final_width = button_height
                final_height = button_width
            
            button = Button(
                real_x, 
                real_y, 
                final_width, 
                final_height, 
                0,
                label, 
                font, 
                action=action
            )
            self.confirmation_buttons.append(button)

    def shutdown(self):
        self.shutdown_confirmation = True
    
    def shutdown_app_only(self):
        self.running = False
        self.shutdown_event.set()
        pygame.quit()
        sys.exit(0)

    def shutdown_pi(self):
        self.running = False
        self.shutdown_event.set()
        time.sleep(0.5)
        try:
            subprocess.call(['sudo', 'shutdown', '-h', 'now'])
        except Exception as e:
            print(f"Error initiating shutdown: {e}")

    def cancel_shutdown(self):
        self.shutdown_confirmation = False
        self.confirmation_buttons = []

    def run(self) -> None:
        try:
            pygame.init()
            pygame.mouse.set_visible(self.show_mouse)
            os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
            if fullscreen:
                screen = pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL | pygame.FULLSCREEN)
            else:
                screen = pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL)
            pygame.display.set_caption("TARS-AI Monitor")
            GL.glMatrixMode(GL.GL_PROJECTION)
            GL.glLoadIdentity()
            GLU.gluOrtho2D(0, self.width, self.height, 0)
            GL.glMatrixMode(GL.GL_MODELVIEW)
            GL.glLoadIdentity()
            GL.glEnable(GL.GL_TEXTURE_2D)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            texture_id = GL.glGenTextures(1)

            clock = pygame.time.Clock()
            font = pygame.font.Font("UI/mono.ttf", self.font_size)
            original_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

            self.start_time = time.time()
            self.battery_checked = time.time()

            while self.running:
                try:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self.running = False
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_v:
                                self.bg()
                        elif event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                # Check confirmation buttons first if dialog is open
                                if self.shutdown_confirmation:
                                    for button in self.confirmation_buttons:
                                        action = button.is_clicked(event.pos)
                                        if action:
                                            self.on_click(action)
                                            break  # Stop checking after first button click
                                else:
                                    # Regular button handling
                                    for button in self.buttons:
                                        action = button.is_clicked(event.pos)
                                        if action:
                                            self.on_click(action)
                                            break  # Stop checking after first button click
                                    
                                    # Panel expansion only if no button was clicked
                                    if not any(button.is_clicked(event.pos) for button in self.buttons):
                                        if self.expanded_box == "":
                                            panel = self.expand_panel(event.pos)
                                            if panel in ["console", "camera"]:
                                                self.expanded_box = panel
                                        else:
                                            self.expanded_box = ""
                        elif event.type == pygame.MOUSEWHEEL:
                            if hasattr(self, 'total_display_lines') and hasattr(self, 'visible_line_count'):
                                self.scroll_offset = max(0, min(self.total_display_lines - self.visible_line_count,
                                                                self.scroll_offset - event.y))

                    while not self.data_queue.empty():
                        try:
                            timestamp, key, value, msg_type = self.data_queue.get_nowait()
                            self.data_store[f"{timestamp}_{key}"] = (value, msg_type)
                            self.scroll_offset = max(0, len(self.data_store) - self.max_lines)
                        except queue.Empty:
                            break

                    GL.glClearColor(0.0, 0.0, 0.0, 0.0)
                    GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)


                    original_surface.fill((0, 0, 0, 0))
                    if self.background_id == 1:
                        self.draw_starfield(original_surface)
                    elif self.background_id == 2:
                        # Rotate the native-sized image
                        rotated_background = pygame.transform.rotate(self.background_image, -self.rotate + 180)
                        # Get dimensions of the rotated image
                        rot_width, rot_height = rotated_background.get_width(), rotated_background.get_height()
                        # Calculate centering offsets
                        offset_x = (self.width - rot_width) // 2
                        offset_y = (self.height - rot_height) // 2
                        # Blit centered
                        original_surface.blit(rotated_background, (offset_x, offset_y))
                    elif self.background_id in [3, 4, 5]:
                        video_paths = {3: "UI/video/bg1.mp4", 4: "UI/video/bg2.mp4", 5: "UI/video/bg3.mp4"}
                        new_video_path = video_paths[self.background_id]
                        if not hasattr(self, "current_video") or self.current_video != new_video_path:
                            self.load_video(new_video_path)
                            self.current_video = new_video_path
                        self.draw_video(original_surface)

                    # Draw all other UI elements onto original_surface
                    if self.console_box:
                        self.draw_console(original_surface, font)
                    if self.system_box:
                        self.draw_system(original_surface, font)
                    if self.spectrum_box:
                        self.draw_spectrum(original_surface, font)
                    if self.camera_box:
                        self.draw_camera(original_surface, font)
                    if self.hal_box:
                        self.draw_hal(original_surface, font)
                    if self.img_box:
                        self.draw_img(original_surface, font)
                    if self.fake_terminal_box:
                        self.draw_fake_terminal(original_surface, font)
                    if self.avatar_box:
                        self.draw_avatar(original_surface, font)

                    # Draw shutdown confirmation on top of everything (BEFORE OpenGL texture rendering)
                    if self.shutdown_confirmation:
                        self.draw_shutdown_confirmation(original_surface, font)

                    # Render original_surface to OpenGL texture
                    texture_data = pygame.image.tostring(original_surface, "RGBA", True)

                    # Render original_surface to OpenGL texture
                    texture_data = pygame.image.tostring(original_surface, "RGBA", True)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.width, self.height, 0,
                                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, texture_data)
                    GL.glBegin(GL.GL_QUADS)
                    GL.glTexCoord2f(0, 1); GL.glVertex2f(0, 0)
                    GL.glTexCoord2f(1, 1); GL.glVertex2f(self.width, 0)
                    GL.glTexCoord2f(1, 0); GL.glVertex2f(self.width, self.height)
                    GL.glTexCoord2f(0, 0); GL.glVertex2f(0, self.height)
                    GL.glEnd()

                    # Render BrainVisualization last to ensure itâ€™s on top
                    if self.brain_box and self.brain_visible:
                        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)  # Clear depth to render on top
                        screen_height = pygame.display.get_surface().get_height()
                        previous_viewport = GL.glGetIntegerv(GL.GL_VIEWPORT)
                        self.brain.render(self.brain_box, screen_height)
                        GL.glViewport(*previous_viewport)  # Restore viewport

                    pygame.display.flip()
                    clock.tick(self.target_fps)

                    if not self.neural_net_always_visible and self.brain_visible:
                        if time.time() - self.start_time >= 15:
                            self.brain_visible = False

                    current_time = time.time()
                    if current_time - self.battery_checked >= 60 and self.battery.is_running:                    
                        status = self.battery.get_battery_status()
                        self.battery_percent = status['normalized_percentage']
                        self.battery_checked = current_time


                except Exception as e:
                    print(f"Error in main UI loop: {e}")
                    self.running = False
                    if self.video_enabled and self.cap:
                        self.cap.release()
                    if self.camera_module:
                        self.camera_module.stop()

        except Exception as e:
            print(f"Fatal UI error: {e}")
            self.running = False
            if self.video_enabled and self.cap:
                self.cap.release()
            if self.camera_module:
                self.camera_module.stop()

        finally:
            pygame.quit()
            if self.video_enabled and self.cap:
                self.cap.release()
            if self.camera_module:
                self.camera_module.stop()

    def stop(self) -> None:
        self.running = False
        if self.video_enabled and self.cap:
            self.cap.release()
        if self.camera_module:
            self.camera_module.stop()
