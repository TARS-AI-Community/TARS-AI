import cv2  # OpenCV to handle frame format conversion
import numpy as np
import pygame
import threading
from picamera2 import Picamera2

class CameraModule:
    def __init__(self, width, height):
        self.picam2 = Picamera2()
        self.camera_config = self.picam2.create_preview_configuration(main={'size': (width, height), 'format': 'RGB888'})
        self.picam2.configure(self.camera_config)
        
        self.frame = None
        self.running = True

        # Start the camera thread
        self.thread = threading.Thread(target=self.capture_frames, daemon=True)
        self.thread.start()
        self.picam2.start()

    def update_size(self, width, height):
        self.stop()  # Stop the current camera
        self.camera_config = self.picam2.create_preview_configuration(main={'size': (width, height), 'format': 'RGB888'})
        self.picam2.configure(self.camera_config)
        self.running = True  # Reset running state
        self.thread = threading.Thread(target=self.capture_frames, daemon=True)  # Recreate thread
        self.thread.start()
        self.picam2.start()

    def capture_frames(self):
        while self.running:
            frame = self.picam2.capture_array()
            if frame.shape[-1] == 4:  # If there's an alpha channel (RGBA), remove it
                frame = frame[:, :, :3]  
                
            frame = np.rot90(frame, 3)  # Rotate if needed (adjust this if flipped)
            frame = np.flip(frame, axis=(0, 1))
            
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert from BGR to RGB
            
            self.frame = pygame.surfarray.make_surface(frame)

    def get_frame(self):
        return self.frame

    def stop(self):
        self.running = False
        self.thread.join()
        self.picam2.stop()