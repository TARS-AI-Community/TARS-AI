# module_ui_video.py
# ----------------------------------------------
# atomikspace (discord)
# olivierdion1@hotmail.com
# ----------------------------------------------
import pygame
import cv2
import os
import time
import random
from pathlib import Path


class VideoSystem:
    """Video background playback system with auto-cycling"""
    
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
        self.overlay.fill((0, 0, 0, 180))  # 180/255 ≈ 70% opacity
        
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go one level up (from UI/ to modules/) then to video/
        self.video_folder = os.path.join(script_dir, video_folder)
        
        # Video state
        self.current_video = None
        self.video_capture = None
        self.current_frame = None
        self.video_surface = None
        
        # Timing
        self.video_switch_interval = 15.0  # Switch every 15 seconds
        self.last_switch_time = time.time()
        self.fps = 30  # Target FPS for video playback
        self.last_frame_time = time.time()
        
        # Video list
        self.video_files = []
        self.current_video_index = 0
        
        # Load available videos
        self._load_video_list()
        
        # Start first video
        if self.video_files:
            self._load_video(0)
        else:
            print(f"Warning: No video files found in {self.video_folder}/")
            print(f"Please add video files to: {os.path.abspath(self.video_folder)}")
    
    def _load_video_list(self):
        """Load list of video files from video folder"""
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']
        
        if not os.path.exists(self.video_folder):
            print(f"Video folder not found: {self.video_folder}")
            return
        
        # Get all video files
        for file in os.listdir(self.video_folder):
            file_path = os.path.join(self.video_folder, file)
            if os.path.isfile(file_path):
                ext = os.path.splitext(file)[1].lower()
                if ext in video_extensions:
                    self.video_files.append(file_path)
        
        # Shuffle for variety
        random.shuffle(self.video_files)
        for video in self.video_files:
            print(f"  - {os.path.basename(video)}")
    
    def _load_video(self, index):
        """Load a specific video by index"""
        if not self.video_files:
            return
        
        # Clean up previous video
        if self.video_capture:
            self.video_capture.release()
        
        # Load new video
        self.current_video_index = index % len(self.video_files)
        video_path = self.video_files[self.current_video_index]
        
        self.video_capture = cv2.VideoCapture(video_path)
        
        if not self.video_capture.isOpened():
            print(f"Failed to open video: {video_path}")
            return
        
        # Get video properties
        self.video_fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        if self.video_fps == 0:
            self.video_fps = 30
        
        self.frame_delay = 1.0 / self.video_fps
        
        # Reset timing
        self.last_switch_time = time.time()
        self.last_frame_time = time.time()
    
    def _get_next_frame(self):
        """Get the next frame from current video"""
        if not self.video_capture or not self.video_capture.isOpened():
            return None
        
        ret, frame = self.video_capture.read()
        
        if not ret:
            # Video ended, loop it
            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_capture.read()
            
            if not ret:
                return None
        
        # Convert from BGR (OpenCV) to RGB (Pygame)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Rotate frame 90 degrees (since videos might need rotation)
        # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        
        return frame
    
    def _frame_to_surface(self, frame):
        """Convert numpy frame to pygame surface"""
        if frame is None:
            return None
        
        # Resize frame to screen dimensions
        frame_resized = cv2.resize(frame, (self.width, self.height))
        
        # Convert to pygame surface
        frame_surface = pygame.surfarray.make_surface(frame_resized.swapaxes(0, 1))
        
        return frame_surface
    
    def update(self):
        """Update video playback and handle switching"""
        current_time = time.time()
        
        # Check if it's time to switch videos
        if current_time - self.last_switch_time >= self.video_switch_interval:
            if len(self.video_files) > 1:
                next_index = (self.current_video_index + 1) % len(self.video_files)
                self._load_video(next_index)
        
        # Check if it's time for next frame
        if current_time - self.last_frame_time >= self.frame_delay:
            frame = self._get_next_frame()
            if frame is not None:
                self.video_surface = self._frame_to_surface(frame)
            self.last_frame_time = current_time
    
    def draw(self, surface):
        """Draw current video frame"""
        # Fill background
        surface.fill(self.bg_color)
        
        # Draw video frame and dim overlay
        if self.video_surface:
            surface.blit(self.video_surface, (0, 0))
            surface.blit(self.overlay, (0, 0))
    
    # Stub methods for compatibility with other background systems
    def action(self):
        """No action animation for videos"""
        pass
    
    def think(self):
        """No think animation for videos"""
        pass
    
    def add_memory(self):
        """No memory animation for videos"""
        pass
    
    def __del__(self):
        """Cleanup on destruction"""
        if self.video_capture:
            self.video_capture.release()


# Example usage
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
