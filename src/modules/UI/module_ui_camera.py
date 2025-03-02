import cv2  # OpenCV for frame processing
import numpy as np
import pygame
import threading


class CameraModule:
    def __init__(self, width, height, use_camera_module=True):
        self.use_camera_module = use_camera_module
        self.frame = None
        self.running = False  # Camera state flag

        if self.use_camera_module:
            from picamera2 import Picamera2

            self.picam2 = Picamera2()
            self.camera_config = self.picam2.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            self.picam2.configure(self.camera_config)

            self.thread = None
            self.start_camera()

    def start_camera(self):
        """Starts the camera stream and the capture thread."""
        if not self.use_camera_module or self.running:
            return

        self.running = True
        self.picam2.start()
        self.thread = threading.Thread(target=self.capture_frames, daemon=True)
        self.thread.start()

    def update_size(self, width, height):
        """Updates the camera resolution dynamically."""
        self.stop()  # Stop the current camera session

        self.camera_config = self.picam2.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self.picam2.configure(self.camera_config)

        self.start_camera()  # Restart camera with new resolution

    def capture_frames(self):
        """Continuously captures frames from the camera."""
        while self.running:
            frame = self.picam2.capture_array()

            # Ensure the frame format is correct
            if frame.shape[-1] == 4:  # If there's an alpha channel (RGBA), remove it
                frame = frame[:, :, :3]

            frame = np.flip(np.rot90(frame, 3), axis=(0, 1))  # Rotate and flip as needed
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert BGR to RGB

            self.frame = pygame.surfarray.make_surface(frame)

    def get_frame(self):
        """Returns the most recent frame as a Pygame surface."""
        return self.frame

    def stop(self):
        """Stops the camera and releases resources."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.use_camera_module:
            self.picam2.stop()