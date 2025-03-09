import pygame
import requests
import cv2
import numpy as np
import threading
import time
from io import BytesIO
from PIL import Image
import socket

target_fps=10

# Get local IP address
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
        self.raw_image = None      # Will hold the resized numpy array (RGB)
        self.stream_image = None   # Cached pygame Surface (from raw_image)
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.running = True
        self.rotation = 0  # Default rotation

        # Create a lock to protect raw_image
        self.image_lock = threading.Lock()

        #print("Starting stream fetch thread...")
        self.stream_thread = threading.Thread(target=self.fetch_stream, daemon=True)
        self.stream_thread.start()

    def fetch_stream(self):
        """
        Continuously fetch the PNG image stream while limiting FPS.
        """
        boundary = b"--frame\r\n"
        buffer = b""
        frame_delay = 1.0 / target_fps  # Calculate delay per frame

        while self.running:
            start_time = time.time()  # Track frame start time

            try:
                response = requests.get(self.stream_url, stream=True, timeout=5)
                if response.status_code == 200:
                    for chunk in response.iter_content(chunk_size=1024):
                        if not self.running:
                            break
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
                                        #resized_image = cv2.resize(np_image, (self.width, self.height))
                                        resized_image = cv2.resize(np_image, (self.width, self.height), interpolation=cv2.INTER_AREA)

                                        with self.image_lock:
                                            self.raw_image = resized_image
                                    except Exception as img_err:
                                        print("Error processing PNG image:", img_err)

            except Exception as e:
                time.sleep(1)

            # ⏳ **Limit FPS to 10**
            elapsed_time = time.time() - start_time
            sleep_time = max(0, frame_delay - elapsed_time)
            time.sleep(sleep_time)


    def update(self, rotation=0):
        """
        Update the surface with the latest stream image, ensuring transparency.
        """
        start_time = time.time()  # Track update start time

        self.rotation = rotation
        self.surface.fill((0, 0, 0, 0))  # Ensure full transparency

        with self.image_lock:
            if self.raw_image is not None:
                # self.raw_image is already (height, width, 4) from fetch_stream
                # Create surface directly from RGBA data
                self.stream_image = pygame.image.frombuffer(self.raw_image.tobytes(), (self.width, self.height), "RGBA")

                if self.stream_image:
                    rotated_image = pygame.transform.rotate(self.stream_image, -rotation)
                    new_rect = rotated_image.get_rect(center=(self.width // 2, self.height // 2))
                    self.surface.blit(rotated_image, new_rect.topleft)
            
        # Limit FPS
        elapsed_time = time.time() - start_time
        sleep_time = max(0, (1.0 / target_fps) - elapsed_time)
        time.sleep(sleep_time)

        return self.surface



    def update_size(self, width, height):
        """Update the avatar dimensions and re-create the surface."""
        self.width = max(1, width)
        self.height = max(1, height)
        self.scale_factor = min(self.width / self.base_width, self.height / self.base_height)
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        with self.image_lock:
            if self.raw_image is not None:
                self.raw_image = cv2.resize(self.raw_image, (self.width, self.height))
        if self.stream_image:
            self.stream_image = pygame.transform.scale(self.stream_image, (self.width, self.height))

    def stop_streaming(self):
        """Stop the streaming thread."""
        self.running = False
        if self.stream_thread:
            self.stream_thread.join()

    def get_surface(self):
        """Return the current surface for external use."""
        return self.surface
