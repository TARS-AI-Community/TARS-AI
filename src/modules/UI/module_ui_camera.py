import cv2
import numpy as np
import pygame
import threading
from datetime import datetime
from pathlib import Path
import time
from module_config import load_config

CONFIG = load_config()
target_fps = CONFIG['UI']['target_fps']

class CameraModule:
    _instance = None  

    def __new__(cls, width, height, use_camera_module=True, apply_corrections=False):
        if cls._instance is None:
            cls._instance = super(CameraModule, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, width, height, use_camera_module=True):
        apply_corrections = True

        if self._initialized:
            return
        self._initialized = True

        self.rotation = 270
        self.use_camera_module = use_camera_module
        self.apply_corrections = apply_corrections
        self.frame = None
        self.running = False
        self.save_next_frame = False
        self.lock = threading.Lock()
        self.first_frame_captured = False
        self.last_saved_image = None

        if self.use_camera_module:
            from picamera2 import Picamera2

            try:
                self.picam2 = Picamera2()
                # Detect camera sensor
                sensor_name = self.picam2.camera_controls.get("SensorName", "")
                if "ov5647" in sensor_name.lower():
                    self.apply_corrections = True
                else:
                    self.apply_corrections = False

                self.camera_config = self.picam2.create_preview_configuration(
                    main={"size": (width, height), "format": "RGB888"}
                )
                self.picam2.configure(self.camera_config)

                self.thread = None
                self.start_camera()
            except Exception as e:
                self.picam2 = None

    def apply_color_corrections(self, frame):
        """Apply gray-world AWB + optional brightness/contrast/gamma."""

        if frame.shape[-1] == 4:
            frame = frame[:, :, :3]
        frame = frame.astype(np.float32)

        meanR, meanG, meanB = np.mean(frame[:,:,2]), np.mean(frame[:,:,1]), np.mean(frame[:,:,0])
        meanGray = (meanR + meanG + meanB) / 3.0
        frame[:,:,2] *= meanGray / meanR
        frame[:,:,1] *= meanGray / meanG
        frame[:,:,0] *= meanGray / meanB

        in_min, in_max = np.min(frame), np.max(frame)
        frame = (frame - in_min) * (255 / (in_max - in_min + 1e-6))

        gamma = 1.1
        invGamma = 1.0 / gamma
        table = np.array([((i/255.0)**invGamma)*255 for i in np.arange(256)]).astype(np.uint8)
        frame = cv2.LUT(frame.astype(np.uint8), table)

        return frame

    def start_camera(self):
        if not self.use_camera_module or self.running or self.picam2 is None:
            return
        try:
            self.running = True
            self.picam2.start()
            self.thread = threading.Thread(target=self.capture_frames, daemon=True)
            self.thread.start()
        except Exception as e:
            print(f"Failed to start camera: {e}")
            self.running = False
            self.picam2 = None

    def restart_camera(self):
        print("🔄 Restarting camera...")
        self.stop()
        time.sleep(2)
        try:
            self.__init__(640, 480, self.use_camera_module, self.apply_corrections)
            self.start_camera()
        except Exception as e:
            print(f"Camera restart failed: {e}")
            self.running = False

    def update_size(self, width, height):
        self.stop()
        try:
            self.camera_config = self.picam2.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            self.picam2.configure(self.camera_config)
            self.start_camera()
        except Exception as e:
            pass

    def capture_frames(self, target_fps=target_fps):
        frame_delay = 1.0 / target_fps
        while self.running:
            start_time = time.time()
            try:
                if self.picam2 is None:
                    raise RuntimeError("Camera not initialized properly.")
                frame = self.picam2.capture_array()
                if self.apply_corrections:
                    frame = self.apply_color_corrections(frame)

                if self.rotation == 90:
                    frame = np.rot90(frame, k=1)
                elif self.rotation == 180:
                    frame = np.rot90(frame, k=2)
                elif self.rotation == 270:
                    frame = np.rot90(frame, k=3)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.frame = pygame.surfarray.make_surface(frame)

                if not self.first_frame_captured:
                    self.first_frame_captured = True

                with self.lock:
                    if self.save_next_frame:
                        self.last_saved_image = self.save_frame()
                        self.save_next_frame = False

            except Exception as e:
                self.restart_camera()

            elapsed_time = time.time() - start_time
            sleep_time = max(0, frame_delay - elapsed_time)
            time.sleep(sleep_time)

    def capture_single_image(self):
        with self.lock:
            if self.first_frame_captured:
                self.save_next_frame = True
        while True:
            with self.lock:
                if self.last_saved_image:
                    saved_image = self.last_saved_image
                    self.last_saved_image = None
                    return saved_image
            pygame.time.wait(100)

    def save_frame(self):
        if self.frame is None:
            return None
        frame_array = pygame.surfarray.array3d(self.frame)
        frame_array = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
        output_dir = Path("../vision")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = output_dir / f"capture_{timestamp}.jpg"
        cv2.imwrite(str(image_path), frame_array)
        return str(image_path)

    def get_frame(self):
        return self.frame

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.use_camera_module and self.picam2:
            self.picam2.stop()