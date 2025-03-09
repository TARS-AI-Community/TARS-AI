import cv2  # OpenCV for frame processing
import numpy as np
import pygame
import threading
from datetime import datetime
from pathlib import Path
import time

target_fps=10

class CameraModule:
    _instance = None  # 🔹 Singleton Instance

    def __new__(cls, width, height, use_camera_module=True):
        """Ensure only one instance of CameraModule is created."""
        if cls._instance is None:
            cls._instance = super(CameraModule, cls).__new__(cls)
            cls._instance._initialized = False  # Prevent multiple inits
        return cls._instance

    def __init__(self, width, height, use_camera_module=True):
        if self._initialized:
            return  # ✅ Prevent multiple inits
        self._initialized = True

        self.use_camera_module = use_camera_module
        self.frame = None
        self.running = False  # Camera state flag
        self.save_next_frame = False  # 🔹 Flag to control single capture
        self.lock = threading.Lock()  # 🔹 Lock to prevent race conditions
        self.first_frame_captured = False  # 🔹 Prevent boot-time saving
        self.last_saved_image = None  # 🔹 Store the last saved image path

        if self.use_camera_module:
            from picamera2 import Picamera2

            try:
                self.picam2 = Picamera2()
                self.camera_config = self.picam2.create_preview_configuration(
                    main={"size": (width, height), "format": "RGB888"}
                )
                self.picam2.configure(self.camera_config)

                self.thread = None
                self.start_camera()
                #print("🎥 Camera initialized successfully.")
            except Exception as e:
                #print(f"❌ Camera initialization failed: {e}")
                self.picam2 = None

    def start_camera(self):
        """Starts the camera stream and the capture thread."""
        if not self.use_camera_module or self.running or self.picam2 is None:
            return

        try:
            self.running = True
            self.picam2.start()
            self.thread = threading.Thread(target=self.capture_frames, daemon=True)
            self.thread.start()
            print("🎥 Camera streaming started.")
        except Exception as e:
            print(f"❌ Failed to start camera: {e}")
            self.running = False
            self.picam2 = None  # Reset camera instance


    def restart_camera(self):
        """Restart the camera if it encounters an error."""
        print("🔄 Restarting camera...")
        self.stop()
        time.sleep(2)  # Give time before reinitializing

        try:
            self.__init__(640, 480, self.use_camera_module)  # Reinitialize
            self.start_camera()
        except Exception as e:
            print(f"❌ Camera restart failed: {e}")
            self.running = False

    def update_size(self, width, height):
        """Updates the camera resolution dynamically."""
        self.stop()  # Stop the current camera session

        try:
            self.camera_config = self.picam2.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            self.picam2.configure(self.camera_config)
            self.start_camera()  # Restart camera with new resolution
        except Exception as e:
            pass
            #print(f"❌ Failed to update camera resolution: {e}")

    def capture_frames(self, target_fps=target_fps):
        """Continuously captures frames from the camera, limiting FPS to reduce CPU usage."""
        frame_delay = 1.0 / target_fps  # Calculate time to wait per frame

        while self.running:
            start_time = time.time()  # Track frame start time

            try:
                if self.picam2 is None:
                    raise RuntimeError("Camera not initialized properly.")

                frame = self.picam2.capture_array()

                if frame.shape[-1] == 4:  # If there's an alpha channel (RGBA), remove it
                    frame = frame[:, :, :3]

                frame = np.flip(np.rot90(frame, 3), axis=(0, 1))  # Rotate and flip as needed
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert BGR to RGB

                self.frame = pygame.surfarray.make_surface(frame)

                if not self.first_frame_captured:
                    self.first_frame_captured = True

                with self.lock:
                    if self.save_next_frame:
                        self.last_saved_image = self.save_frame()
                        self.save_next_frame = False  # Reset flag after saving

            except Exception as e:
                self.restart_camera()  # Attempt restart on error

            # ⏳ **Limit FPS**
            elapsed_time = time.time() - start_time  # Calculate time taken for processing
            sleep_time = max(0, frame_delay - elapsed_time)  # Ensure positive sleep time
            time.sleep(sleep_time)


    def capture_single_image(self):
        """Triggers a single image capture and waits for it to be saved."""
        with self.lock:
            if self.first_frame_captured:
                self.save_next_frame = True
                #print("🟢 Next frame will be saved.")

        while True:
            with self.lock:
                if self.last_saved_image:
                    saved_image = self.last_saved_image
                    self.last_saved_image = None  # Reset after retrieval
                    return saved_image
            pygame.time.wait(100)

    def save_frame(self):
        """Saves the current frame as an image."""
        if self.frame is None:
            #print("⚠️ No frame available to save.")
            return None

        frame_array = pygame.surfarray.array3d(self.frame)
        frame_array = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)  # Convert RGB to BGR for OpenCV

        output_dir = Path("../vision")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = output_dir / f"capture_{timestamp}.jpg"

        cv2.imwrite(str(image_path), frame_array)
        #print(f"📸 Image saved to {image_path}")

        return str(image_path)

    def get_frame(self):
        """Returns the most recent frame as a Pygame surface without triggering a save."""
        return self.frame

    def stop(self):
        """Stops the camera and releases resources."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.use_camera_module and self.picam2:
            self.picam2.stop()
        #print("🛑 Camera stopped.")
