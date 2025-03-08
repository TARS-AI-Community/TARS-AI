import pygame
import requests
import cv2
import numpy as np
import threading
import time
from io import BytesIO
from PIL import Image
import socket

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
        Continuously fetch the PNG image stream.
        Our server sends data with boundary '--frame\r\n' followed by headers and PNG data.
        """
        boundary = b"--frame\r\n"  # Must match your server exactly.
        buffer = b""
        while self.running:
            try:
                #print(f"Connecting to stream at {self.stream_url}")
                response = requests.get(self.stream_url, stream=True, timeout=5)
                if response.status_code == 200:
                    #print("Connected. Reading stream data...")
                    for chunk in response.iter_content(chunk_size=1024):
                        if not self.running:
                            break
                        # Print first 50 bytes for debugging
                        #print(f"Received chunk of size {len(chunk)}: {chunk[:50]}")
                        buffer += chunk
                        # Process complete frames from the buffer
                        while boundary in buffer:
                            parts = buffer.split(boundary, 1)
                            frame_chunk = parts[0]
                            buffer = parts[1]
                            # Find header end: look for \r\n\r\n
                            header_end = frame_chunk.find(b"\r\n\r\n")
                            if header_end != -1:
                                png_data = frame_chunk[header_end+4:].strip()
                                if png_data:
                                    try:
                                        pil_image = Image.open(BytesIO(png_data))
                                        pil_image = pil_image.convert("RGB")
                                        np_image = np.array(pil_image)
                                        # Resize image to current desired dimensions
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
        Update the surface with the latest stream image.
        This method re-scales the raw image to the current width/height.
        """
        self.rotation = rotation
        self.surface.fill((0, 0, 0, 0))
        with self.image_lock:
            if self.raw_image is not None:
                # Re-scale the raw image to current dimensions if needed.
                if (self.raw_image.shape[1], self.raw_image.shape[0]) != (self.width, self.height):
                    # raw_image shape: (height, width, channels)
                    resized = cv2.resize(self.raw_image, (self.width, self.height))
                else:
                    resized = self.raw_image
                self.stream_image = pygame.surfarray.make_surface(resized.swapaxes(0, 1))
        if self.stream_image:
            rotated_image = pygame.transform.rotate(self.stream_image, -self.rotation)
            new_rect = rotated_image.get_rect(center=(self.width // 2, self.height // 2))
            self.surface.blit(rotated_image, new_rect.topleft)
        else:
            # Fallback color so we know update() is being called.
            self.surface.fill((255, 0, 0))
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
