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
import os
import sounddevice as sd
from module_config import load_config
from UI.module_ui_camera import CameraModule
from UI.module_ui_spectrum import SineWaveVisualizer, BarVisualizer
from UI.module_ui_buttons import Button
from UI.module_ui_fake_terminal import ConsoleAnimation
from UI.module_ui_hal import HalAnimation 
from UI.module_ui_brain import BrainVisualization

CONFIG = load_config()

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

BASE_WIDTH = 800
BASE_HEIGHT = 600

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

def get_layout_dimensions(screen_width, screen_height, rotation=0):

    scale = min(screen_width / BASE_WIDTH, screen_height / BASE_HEIGHT)
    original_width, original_height = screen_width, screen_height

    if rotation in (90, 270):
        return get_vertical_layout(screen_height, screen_width, rotation, scale)
    else:
        return get_horizontal_layout(screen_width, screen_height, rotation, scale)

def get_horizontal_layout(screen_width, screen_height, rotation, scale):
    layout = []
    first_box_width = int(screen_width * 0.5)
    layout.append(Box("Box1", 0, 0, first_box_width, screen_height, rotation, first_box_width, screen_height))
    remaining_width = screen_width - first_box_width

    last_row_height = max(int(60 * scale), 1)
    remaining_height = screen_height - last_row_height
    first_row_height = int(remaining_height * 0.5)
    second_row_height = remaining_height - first_row_height
    box_width_3 = int(remaining_width / 3)

    box2_x = first_box_width
    box2_y = 0
    box2_rotation = rotation
    for i in range(3):
        layout.append(Box(
            f"Box{i+2}",
            first_box_width + (i * box_width_3),
            0,
            box_width_3,
            first_row_height,
            rotation,
            box_width_3,
            first_row_height
        ))

    box_width_2 = int(remaining_width / 2)
    for i in range(2):
        layout.append(Box(
            f"Box{i+5}",
            first_box_width + (i * box_width_2),
            first_row_height,
            box_width_2,
            second_row_height,
            rotation,
            box_width_2,
            second_row_height
        ))
    layout.append(Box(
        "Box7",
        first_box_width,
        screen_height - last_row_height,
        remaining_width,
        last_row_height,
        rotation,
        remaining_width,
        last_row_height
    ))
    layout.append(Box(
        "Box8",
        box2_x,
        box2_y,
        remaining_width,
        remaining_height,
        box2_rotation,
        remaining_width,
        remaining_height
    ))

    if rotation == 180:
        layout = [Box(
            box.name,
            screen_width - (box.x + box.width),
            screen_height - (box.y + box.height),
            box.width,
            box.height,
            rotation,
            box.original_width,
            box.original_height
        ) for box in layout]

    return layout

def get_vertical_layout(screen_width, screen_height, rotation, scale):
    row1_height = int(screen_height * 0.5)
    row4_height = max(int(60 * scale), 1)
    remaining_height = screen_height - row1_height - row4_height
    row2_height = int(remaining_height * 0.5)
    row3_height = remaining_height - row2_height
    layout = []
    layout.append(Box("Box1", 0, 0, screen_width, row1_height, rotation, screen_width, row1_height))

    box2_x = 0
    box2_y = row1_height
    box2_rotation = rotation

    box_width_3 = int(screen_width / 3)

    for i in range(3):
        layout.append(Box(
            f"Box{i+2}",
            i * box_width_3,
            row1_height,
            box_width_3,
            row2_height,
            rotation,
            box_width_3,
            row2_height
        ))

    box_width_2 = int(screen_width / 2)

    for i in range(2):
        layout.append(Box(
            f"Box{i+5}",
            i * box_width_2,
            row1_height + row2_height,
            box_width_2,
            row3_height,
            rotation,
            box_width_2,
            row3_height
        ))

    layout.append(Box(
        "Box7",
        0,
        screen_height - row4_height,
        screen_width,
        row4_height,
        rotation,
        screen_width,
        row4_height
    ))

    layout.append(Box(
        "Box8",
        box2_x,
        box2_y,
        screen_width,
        row2_height + row3_height,
        box2_rotation,
        screen_width,
        row2_height + row3_height
    ))

    if rotation == 90:
        layout = [Box(
            box.name,
            box.y,
            screen_width - (box.x + box.width),
            box.height,
            box.width,
            rotation,
            box.original_width,
            box.original_height
        ) for box in layout]
    elif rotation == 270:
        layout = [Box(
            box.name,
            screen_height - (box.y + box.height),
            box.x,
            box.height,
            box.width,
            rotation,
            box.original_width,
            box.original_height
        ) for box in layout]

    return layout

class Star:
    def __init__(self, width: int, height: int):
        self.width = max(2, width)   # Ensure at least 2
        self.height = max(2, height) # Ensure at least 2
        self.reset()
            
    def reset(self):
        # Ensure width and height are always valid
        safe_width = max(2, self.width)   
        safe_height = max(2, self.height)  

        # Debugging print statements
        #print(f"DEBUG: safe_width={safe_width}, safe_height={safe_height}")

        min_x, max_x = sorted([-safe_width, safe_width])
        min_y, max_y = sorted([-safe_height, safe_height])

        #print(f"DEBUG: x range: {min_x} to {max_x}, y range: {min_y} to {max_y}")

        # Ensure that we never provide an invalid range
        if min_x >= max_x or min_y >= max_y:
            #print(f"ERROR: Invalid range for randrange! min_x={min_x}, max_x={max_x}, min_y={min_y}, max_y={max_y}")
            return

        self.x = random.randrange(min_x, max_x)  # Ensures valid range
        self.y = random.randrange(min_y, max_y)

        # Ensure z value does not cause an invalid range
        min_z = 1
        max_z = max(2, safe_width)
        #print(f"DEBUG: z range: {min_z} to {max_z}")

        if min_z >= max_z:
            #print(f"ERROR: Invalid range for randrange! min_z={min_z}, max_z={max_z}")
            return

        self.z = random.randrange(min_z, max_z)  # Ensures at least (1,2)

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

class UIManager(threading.Thread):
    def __init__(self, shutdown_event, use_camera_module=use_camera_module, show_mouse=show_mouse, 
                 width: int = screenWidth, height: int = screenHeight, rotation_value=rotation):
        super().__init__()        
        self.show_mouse = show_mouse
        self.use_camera_module = use_camera_module
        self.width = width
        self.height = height
        self.rotate = rotation_value  

        self.background_image = pygame.image.load("UI/background.png")
        self.background_image = pygame.transform.scale(self.background_image, (self.width , self.height))

        self.scale = min(width / BASE_WIDTH, height / BASE_HEIGHT)
        self.layouts = get_layout_dimensions(width, height, self.rotate)        
        self.console_box = self.layouts[0]
        self.hal_box = self.layouts[1]
        self.hal_anim = HalAnimation(self.hal_box.original_width, self.hal_box.original_height)
        self.fake_terminal_box = self.layouts[2]
        self.terminal_anim = ConsoleAnimation(self.fake_terminal_box.original_width, self.fake_terminal_box.original_height)

        self.img_box = self.layouts[3]
        self.img_folder = "UI/img"
        self.current_image = None
        self.next_image = None
        self.last_switch_time = 0
        self.last_image_filename = None
        self.crossfade_duration = 1000  
        self.display_time = 15000  
        self.alpha = 255

        self.camera_box = self.layouts[5]
        if use_camera_module:
            self.camera_module = CameraModule(self.camera_box.original_width, self.camera_box.original_height, self.use_camera_module)
        else:
            self.camera_module = None
        self.change_camera_resolution = False

        self.spectrum_box = self.layouts[4] 
        self.spectrum = []
        self.sineWaveVisualizer = SineWaveVisualizer(
            self.spectrum_box.width, self.spectrum_box.height, self.spectrum_box.rotation
        )        

        self.system_box = self.layouts[6]
        self.buttons = []

        self.brain_box = self.layouts[7]
        self.brain = BrainVisualization(self.width, self.height)
        self.barVisualizer = BarVisualizer(
            self.brain_box.original_width, self.brain_box.original_height, int(self.brain_box.original_width / 3)
        )         
        self.brain_visible = False
        self.neural_net_always_visible = neural_net_always_visible
        if self.neural_net_always_visible:
            self.brain_visible = True
        self.neural_net = neural_net
        self.brain_x = self.brain_box.x
        self.brain_y = self.brain_box.y
        self.brain_width = self.brain_box.width
        self.brain_height = self.brain_box.height
        if self.rotate in (90, 270):
            self.brain_x = self.brain_box.y
            self.brain_y = self.brain_box.x
            self.brain_width = self.brain_box.height
            self.brain_height = self.brain_box.width

        self.running = True
        self.data_queue = queue.Queue()
        self.data_store: Dict[str, Any] = {}
        self.shutdown_event = shutdown_event
        self.silence_progress = 0
        self.expanded_box = ""
        self.background_id = background_id
        self.maximize_console = maximize_console
        if maximize_console:
            self.expanded_box = "Box1"

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
        self.spectrum = fft_data[:len(fft_data) // 2]

    def silence(self, progress):
        self.silence_progress = progress
        if progress != 0:
            self.start_time = time.time()

    def draw_starfield(self, surface):
        for star in self.stars:
            star.moveStars()
            star.drawStars(surface)

    def update_data(self, key: str, value: Any, msg_type: str = 'INFO') -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.data_queue.put((timestamp, key, value, msg_type))
        self.data_store[f"{timestamp}_{key}"] = (value, msg_type)
        self.new_data_added = True

    def draw_console(self, surface, font):
        if self.expanded_box not in ["", "Box1"]:
            return

        x = self.console_box.x
        y = self.console_box.y
        width = self.console_box.original_width
        height = self.console_box.original_height

        if self.expanded_box == "Box1":
            if self.rotate in [90, 270]:
                width = self.height
                height = self.width
                x = y = 0
            else:
                width = self.width
                height = self.height
                x = y = 0

        console_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        console_background = (0, 0, 0, 160)
        pygame.draw.rect(console_surface, console_background, (0, 0, width, height))
        pygame.draw.rect(console_surface, (76, 194, 230, 255), (0, 0, width, height), int(2 * self.scale))

        title = font.render("System Console", True, (150, 150, 150))
        console_surface.blit(title, (10, 5))

        if self.expanded_box == "Box1":
            max_frames = 20
            padding = int(25 * self.scale)        
            progress_bar_height = int(10 * self.scale)
            available_width = width - (padding * 2) - (int(220 * self.scale))
            progress_bar_x = int(220 * self.scale)
            progress_bar_y = int(10 * self.scale)

            if self.silence_progress > 0:
                progress_fraction = self.silence_progress / max_frames
                fill_width = int(available_width * progress_fraction)
                progress_color = (76, 194, 230)
                pygame.draw.rect(console_surface, progress_color,
                                (progress_bar_x, progress_bar_y, fill_width, progress_bar_height))

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

        if getattr(self, 'new_data_added', False):
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
        rotated_surface = pygame.transform.rotate(console_surface, self.console_box.rotation)
        surface.blit(rotated_surface, (x, y))

    def draw_camera(self, surface, font):        
        if self.expanded_box == "" or self.expanded_box == "Box6":            
            if self.expanded_box == "Box6":
                if self.rotate in [90, 270]:
                    width = self.height
                    height = self.width
                    x = 0
                    y = 0
                else:
                    width = self.width
                    height = self.height
                    x = 0
                    y = 0
            else:
                width = self.camera_box.original_width
                height = self.camera_box.original_height
                x = self.camera_box.x
                y = self.camera_box.y

            if self.change_camera_resolution and use_camera_module:
                self.camera_module.update_size(width, height)
                self.change_camera_resolution = False

            box_surface = pygame.Surface((width, height), pygame.SRCALPHA)
            if self.use_camera_module and self.camera_module:
                camera_frame = self.camera_module.get_frame()
                if camera_frame:
                    scaled_frame = pygame.transform.scale(camera_frame, (width, height))
                    box_surface.blit(scaled_frame, (0, 0))
            border_color = (76, 194, 230, 255)
            pygame.draw.rect(box_surface, border_color, (0, 0, width, height), int(2 * self.scale))
            rotated_surface = pygame.transform.rotate(box_surface, self.camera_box.rotation)
            surface.blit(rotated_surface, (x, y))

    def draw_fake_terminal(self, surface, font):
        if self.expanded_box == "":
            box_surface = pygame.Surface(
                (self.fake_terminal_box.original_width, self.fake_terminal_box.original_height), pygame.SRCALPHA
            )
            box_surface.fill((0, 0, 0, 128))  
            border_color = (76, 194, 230, 255)
            anim_surface = self.terminal_anim.update()
            box_surface.blit(anim_surface, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
            pygame.draw.rect(
                box_surface, border_color,
                (0, 0, self.fake_terminal_box.original_width, self.fake_terminal_box.original_height),
                int(2 * self.scale)
            )
            rotated_surface = pygame.transform.rotate(box_surface, self.fake_terminal_box.rotation)
            surface.blit(rotated_surface, (self.fake_terminal_box.x, self.fake_terminal_box.y))

    def draw_hal(self, surface, font):
        if self.expanded_box == "":
            box_surface = pygame.Surface(
                (self.hal_box.original_width, self.hal_box.original_height), pygame.SRCALPHA
            )
            border_color = (76, 194, 230, 255)
            self.hal_anim.update()
            box_surface = self.hal_anim.get_surface()
            pygame.draw.rect(
                box_surface, border_color,
                (0, 0, self.hal_box.original_width, self.hal_box.original_height),
                int(2 * self.scale)
            )
            rotated_surface = pygame.transform.rotate(box_surface, self.hal_box.rotation)
            surface.blit(rotated_surface, (self.hal_box.x, self.hal_box.y))

    def draw_spectrum(self, surface, font):
        if self.expanded_box == "":
            box_surface = self.sineWaveVisualizer.update(self.spectrum)

            if not neural_net:
                max_frames = 20
                padding = int(15 * self.scale)
                progress_bar_height = int(25 * self.scale)
                available_width = self.spectrum_box.original_width - (padding * 2)
                progress_bar_x = padding
                progress_bar_y = padding

                if self.silence_progress > 0:
                    progress_fraction = self.silence_progress / max_frames
                    fill_width = int(available_width * progress_fraction)
                    progress_color = (76, 194, 230)
                    pygame.draw.rect(box_surface, progress_color,
                                    (progress_bar_x, progress_bar_y, fill_width, progress_bar_height))

            border_color = (76, 194, 230, 255)
            pygame.draw.rect(box_surface, border_color,
                             (0, 0, self.spectrum_box.original_width, self.spectrum_box.original_height),
                             int(2 * self.scale))
            rotated_surface = pygame.transform.rotate(box_surface, self.spectrum_box.rotation)
            surface.blit(rotated_surface, (self.spectrum_box.x, self.spectrum_box.y))

    def draw_brain(self, surface, font):
        if self.expanded_box == "":
            box_surface = pygame.Surface(
                (self.brain_box.original_width, self.brain_box.original_height), pygame.SRCALPHA
            )
            box_surface.fill((0, 0, 0, 200))                          
            box_surface = self.barVisualizer.update(self.spectrum, box_surface)
            border_color = (76, 194, 230, 255)
            pygame.draw.rect(
                box_surface, border_color,
                (0, 0, self.brain_box.original_width, self.brain_box.original_height),
                int(2 * self.scale)
            )

            max_frames = 20
            padding = int(15 * self.scale)
            progress_bar_height = int(10 * self.scale)
            available_width = self.brain_box.original_width - (padding * 2)
            progress_bar_x = padding
            progress_bar_y = padding                    
            if self.silence_progress > 0:
                progress_fraction = self.silence_progress / max_frames
                fill_width = int(available_width * progress_fraction)
                progress_color = (76, 194, 230)
                pygame.draw.rect(box_surface, progress_color,
                                (progress_bar_x, progress_bar_y, fill_width, progress_bar_height))
            pygame.draw.rect(box_surface, (100, 100, 100), (progress_bar_x, progress_bar_y, available_width, progress_bar_height), 1)
            rotated_surface = pygame.transform.rotate(box_surface, self.brain_box.rotation)
            surface.blit(rotated_surface, (self.brain_box.x, self.brain_box.y))

    def load_random_image(self, img_folder, size, last_filename=None):
        img_files = [f for f in os.listdir(img_folder) if f.endswith(('png', 'jpg', 'jpeg'))]
        if not img_files:
            raise FileNotFoundError("No images found in the img folder.")
        if last_filename and last_filename in img_files and len(img_files) > 1:
            img_files.remove(last_filename)
        img_path = os.path.join(img_folder, random.choice(img_files))
        img = pygame.image.load(img_path).convert_alpha()
        self.last_image_filename = os.path.basename(img_path)
        return pygame.transform.scale(img, size)

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
        if self.expanded_box == "":
            box_surface = pygame.Surface(
                (self.img_box.original_width, self.img_box.original_height), pygame.SRCALPHA
            )
            if self.current_image is None:
                self.current_image = self.load_random_image(
                    self.img_folder, (self.img_box.original_width, self.img_box.original_height)
                )
            box_surface.blit(self.current_image, (0, 0))
            if self.next_image:
                fade_surface = pygame.Surface(
                    (self.img_box.original_width, self.img_box.original_height), pygame.SRCALPHA
                )
                fade_surface.blit(self.next_image, (0, 0))
                fade_surface.set_alpha(255 - self.alpha)
                box_surface.blit(fade_surface, (0, 0))
            border_color = (76, 194, 230, 255)
            pygame.draw.rect(
                box_surface, border_color,
                (0, 0, self.img_box.original_width, self.img_box.original_height),
                int(2 * self.scale)
            )
            rotated_surface = pygame.transform.rotate(box_surface, self.img_box.rotation)
            surface.blit(rotated_surface, (self.img_box.x, self.img_box.y))
            self.update_images()

    def draw_system(self, surface, font):
        if self.expanded_box == "":
            box_surface = pygame.Surface(
                (self.system_box.original_width, self.system_box.original_height), pygame.SRCALPHA
            )
            border_color = (76, 194, 230, 255)
            pygame.draw.rect(
                box_surface, border_color,
                (0, 0, self.system_box.original_width, self.system_box.original_height),
                int(2 * self.scale)
            )
            rotated_temp = pygame.transform.rotate(box_surface, self.system_box.rotation)
            offset_x = (rotated_temp.get_width() - box_surface.get_width()) // 2
            offset_y = (rotated_temp.get_height() - box_surface.get_height()) // 2
            self.buttons = []
            spacing = int(140 * self.scale)
            for i, label in enumerate(["SHUTDOWN", "BG"]):
                relative_x = int(10 * self.scale) + (i * spacing)
                relative_y = int(10 * self.scale)
                button_width = int(130 * self.scale)
                button_height = self.system_box.original_height - int(20 * self.scale)

                if self.system_box.rotation == 0:
                    real_x = self.system_box.x + relative_x
                    real_y = self.system_box.y + relative_y
                elif self.system_box.rotation == 90:
                    real_x = self.system_box.x + offset_x + relative_y
                    real_y = self.system_box.y + offset_y + (box_surface.get_width() - relative_x - button_width)
                elif self.system_box.rotation == 180:
                    real_x = self.system_box.x + offset_x + (box_surface.get_width() - relative_x - button_width)
                    real_y = self.system_box.y + offset_y + (box_surface.get_height() - relative_y - button_height)
                elif self.system_box.rotation == 270:
                    real_x = self.system_box.x + (self.system_box.original_height - relative_y - button_height)
                    real_y = self.system_box.y + relative_x

                button = Button(real_x, real_y, button_width, button_height,
                                self.system_box.rotation, label, font, action=label.lower())
                self.buttons.append(button)
                button_surface = button.draw_button(font)
                box_surface.blit(button_surface, (relative_x, relative_y))

            rotated_surface = pygame.transform.rotate(box_surface, self.system_box.rotation)
            surface.blit(rotated_surface, (self.system_box.x, self.system_box.y))

    def on_click(self, action):
        if isinstance(action, str) and hasattr(self, action):
            method = getattr(self, action)
            if callable(method):
                method()

    def shutdown(self):
        self.running = False
        if self.video_enabled:
            self.cap.release()
        if self.camera_module:
            self.camera_module.stop()
        self.shutdown_event.set()

    def bg(self):
        self.background_id = self.background_id + 1
        if self.background_id > 4:
            self.background_id = 0

    def wake(self):
        if self.neural_net:
            self.start_time = time.time()
            self.brain.add_ripple_effect(
                origin=(0, 0, 0),
                speed=5.5,
                duration=3.0,
                amplitude=0.6,
                color=(82, 255, 139),
                thickness=1)
            self.brain_visible = True

    def think(self):
        if self.neural_net:
            self.start_time = time.time()
            self.brain.add_band_effect(
                        origin=(0, -5, 0),
                        direction=(0, 1, 0),
                        speed=4.0,
                        color=(50, 200, 255),
                        band_width=0.2)

    def save_memory(self):
        if self.neural_net:
            self.start_time = time.time()
            self.brain.add_matrix_data_insertion(
                    color=(0, 255, 0),
                    duration=4.0,
                    speed=1.0,
                    density=2.8)

    def expand_panel(self, pos):
        mouse_x, mouse_y = pos
        for layout in self.layouts:
            x = layout.x
            y = layout.y
            x2 = layout.x + layout.width
            y2 = layout.y + layout.height
            if (mouse_x >= x and mouse_y >= y and mouse_x <= x2 and mouse_y <= y2):
                return layout.name

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
                                for button in self.buttons:
                                    action = button.is_clicked(event.pos)
                                    self.on_click(action)
                                if self.expanded_box == "":
                                    box = self.expand_panel(event.pos)
                                    if box in ["Box1", "Box6"]:
                                        if box == "Box6":
                                            self.change_camera_resolution = True
                                        self.expanded_box = box
                                elif self.expanded_box != "":
                                    self.expanded_box = ""
                                    self.change_camera_resolution = True
                        elif event.type == pygame.MOUSEWHEEL:
                            if hasattr(self, 'total_display_lines') and hasattr(self, 'visible_line_count'):
                                self.scroll_offset = max(
                                    0, min(self.total_display_lines - self.visible_line_count,
                                        self.scroll_offset - event.y)
                                )

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
                        original_surface.blit(self.background_image, (0, 0))
                    elif self.background_id in [3, 4, 5]:
                        video_paths = {
                            2: "UI/video/bg1.mp4",
                            3: "UI/video/bg2.mp4",
                            4: "UI/video/bg3.mp4"
                        }
                        new_video_path = video_paths[self.background_id]
                        if not hasattr(self, "current_video") or self.current_video != new_video_path:
                            self.load_video(new_video_path)
                            self.current_video = new_video_path
                        self.draw_video(original_surface)

                    GL.glDisable(GL.GL_DEPTH_TEST)
                    GL.glEnable(GL.GL_BLEND)
                    GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
                    brain_surface = pygame.Surface((self.brain_box.width, self.brain_box.width), pygame.SRCALPHA)
                    brain_surface.fill((0, 0, 0, 0))


                    self.draw_console(original_surface, font)
                    self.draw_system(original_surface, font)
                    if not self.brain_visible:                        
                        self.draw_spectrum(original_surface, font)
                        self.draw_camera(original_surface, font)
                        self.draw_hal(original_surface, font)
                        self.draw_img(original_surface, font)
                        self.draw_fake_terminal(original_surface, font)
                    else:
                        self.draw_brain(original_surface, font)

                    pygame.draw.rect(original_surface, (255, 255, 255, 255), (0, 0, self.width, self.width), 1) # DO NOT REMOVE THIS LINE

                    #texture_data = pygame.image.tostring(original_surface, "BGRA", True) # BREAKS MY INSTALL FIX BELOW
                    texture_data = pygame.image.tostring(original_surface, "RGBA", True) #fix

                    GL.glBindTexture(GL.GL_TEXTURE_2D, texture_id)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)

                    #GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.width, self.height, 0, GL.GL_BGRA, GL.GL_UNSIGNED_BYTE, texture_data) #breaks color
                    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.width, self.height, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, texture_data) #fix color for applied fix above

                    GL.glBegin(GL.GL_QUADS)
                    GL.glTexCoord2f(0, 1); GL.glVertex2f(0, 0)
                    GL.glTexCoord2f(1, 1); GL.glVertex2f(self.width, 0)
                    GL.glTexCoord2f(1, 0); GL.glVertex2f(self.width, self.height)
                    GL.glTexCoord2f(0, 0); GL.glVertex2f(0, self.height)
                    GL.glEnd()

                    if self.expanded_box == "" and self.brain_visible and neural_net:
                        previous_viewport = GL.glGetIntegerv(GL.GL_VIEWPORT)
                        GL.glViewport(self.brain_x, self.brain_y, self.brain_width, self.brain_height)  
                        self.brain.render()
                        GL.glViewport(*previous_viewport)
                        GL.glMatrixMode(GL.GL_PROJECTION)
                        GL.glLoadIdentity()
                        GLU.gluOrtho2D(0, self.width, self.height, 0)
                        GL.glMatrixMode(GL.GL_MODELVIEW)
                        GL.glLoadIdentity()                    



                    pygame.display.flip()

                    if not self.neural_net_always_visible:
                        if time.time() - self.start_time >= 15 and self.brain_visible:
                            self.brain_visible = False

                    clock.tick(60)

                except Exception as e:
                    print(f"Error in main UI loop: {e}")
                    self.running = False
                    if self.video_enabled:
                        self.cap.release()
                    if self.camera_module:
                        self.camera_module.stop()

        except Exception as e:
            print(f"Fatal UI error: {e}")
            self.running = False
            if self.video_enabled:
                self.cap.release()
            if self.camera_module:
                self.camera_module.stop()

        finally:
            pygame.quit()
            if self.video_enabled:
                self.cap.release()
            if self.camera_module:
                self.camera_module.stop()

    def stop(self) -> None:
        self.running = False
        if self.video_enabled:
            self.cap.release()
        if self.camera_module:
            self.camera_module.stop()