import pygame
import cv2
import os
import time
import random
from pathlib import Path

class VideoSystem:
    def __init__(self, width, height, bg_color=(0, 0, 0), video_folder="video"):
        """
        Initialize video background system

        Args:
            width: Screen width
            height: Screen height
            bg_color: Background color
            video_folder: Folder containing video files (relative to UI folder parent)
        """
        self.width = width
        self.height = height
        self.bg_color = bg_color

        self.overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, 180))  

        script_dir = os.path.dirname(os.path.abspath(__file__))

        self.video_folder = os.path.join(script_dir, video_folder)

        self.current_video = None
        self.video_capture = None
        self.current_frame = None
        self.video_surface = None

        self.video_switch_interval = 15.0  

        self.last_switch_time = time.time()
        self.fps = 30  

        self.last_frame_time = time.time()

        self.video_files = []
        self.current_video_index = 0

        self._load_video_list()

        if self.video_files:
            self._load_video(0)
        else:
            print(f"Warning: No video files found in {self.video_folder}/")
            print(f"Please add video files to: {os.path.abspath(self.video_folder)}")

    def _load_video_list(self):
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']

        if not os.path.exists(self.video_folder):
            print(f"Video folder not found: {self.video_folder}")
            return

        for file in os.listdir(self.video_folder):
            file_path = os.path.join(self.video_folder, file)
            if os.path.isfile(file_path):
                ext = os.path.splitext(file)[1].lower()
                if ext in video_extensions:
                    self.video_files.append(file_path)

        random.shuffle(self.video_files)
        for video in self.video_files:
            print(f"  - {os.path.basename(video)}")

    def _load_video(self, index):
        if not self.video_files:
            return

        if self.video_capture:
            self.video_capture.release()

        self.current_video_index = index % len(self.video_files)
        video_path = self.video_files[self.current_video_index]

        self.video_capture = cv2.VideoCapture(video_path)

        if not self.video_capture.isOpened():
            print(f"Failed to open video: {video_path}")
            return

        self.video_fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        if self.video_fps == 0:
            self.video_fps = 30

        self.frame_delay = 1.0 / self.video_fps

        self.last_switch_time = time.time()
        self.last_frame_time = time.time()

    def _get_next_frame(self):
        if not self.video_capture or not self.video_capture.isOpened():
            return None

        ret, frame = self.video_capture.read()

        if not ret:

            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_capture.read()

            if not ret:
                return None

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        return frame

    def _frame_to_surface(self, frame):
        if frame is None:
            return None

        frame_resized = cv2.resize(frame, (self.width, self.height))

        frame_surface = pygame.surfarray.make_surface(frame_resized.swapaxes(0, 1))

        return frame_surface

    def update(self):
        current_time = time.time()

        if current_time - self.last_switch_time >= self.video_switch_interval:
            if len(self.video_files) > 1:
                next_index = (self.current_video_index + 1) % len(self.video_files)
                self._load_video(next_index)

        if current_time - self.last_frame_time >= self.frame_delay:
            frame = self._get_next_frame()
            if frame is not None:
                self.video_surface = self._frame_to_surface(frame)
            self.last_frame_time = current_time

    def draw(self, surface):
        surface.fill(self.bg_color)

        if self.video_surface:
            surface.blit(self.video_surface, (0, 0))
            surface.blit(self.overlay, (0, 0))

    def action(self):
        pass

    def think(self):
        pass

    def add_memory(self):
        pass

    def __del__(self):
        if self.video_capture:
            self.video_capture.release()

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    video_system = VideoSystem(800, 600, video_folder="video")

    running = True
    while running:

        video_system.update()
        video_system.draw(screen)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

