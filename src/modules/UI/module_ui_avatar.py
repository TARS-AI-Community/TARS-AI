import pygame
import requests
import cv2
import numpy as np
import threading
import time
from io import BytesIO
from PIL import Image

import socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.connect(("8.8.8.8", 80))  # Connects to an external server but doesn't send data
    local_ip = s.getsockname()[0]

class StreamingAvatar:
    def __init__(self, width=800, height=600, base_width=800, base_height=600, stream_url=f"http://{local_ip}:5012/stream"):
        self.width = max(1, width)
        self.height = max(1, height)
        self.scale_factor = min(self.width / base_width, self.height / base_height)
        self.stream_url = stream_url
        self.stream_image = None
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.running = True
        self.last_fetch_time = time.time()
        self.fetch_interval = 0.1  # Fetch every 0.1 seconds for smooth streaming
        self.rotation = 0  # Default rotation, will be updated by UIManager

        # Start the stream fetching thread
        self.stream_thread = threading.Thread(target=self.fetch_stream, daemon=True)
        self.stream_thread.start()

    def fetch_stream(self):
        """Continuously fetch the image stream in a separate thread."""
        while self.running:
            current_time = time.time()
            if current_time - self.last_fetch_time >= self.fetch_interval:
                try:
                    # Fetch the image from the stream (assuming MJPEG or similar format)
                    response = requests.get(self.stream_url, stream=True, timeout=5)
                    if response.status_code == 200:
                        # Read the image data (simplified for MJPEG; adjust for your stream format)
                        image_data = b''
                        for chunk in response.iter_content(chunk_size=1024):
                            if chunk:
                                image_data += chunk
                                # Look for JPEG boundary (simplified; adjust for your stream)
                                if b'\xff\xd8' in image_data and b'\xff\xd9' in image_data:
                                    start = image_data.index(b'\xff\xd8')
                                    end = image_data.index(b'\xff\xd9') + 2
                                    jpeg_data = image_data[start:end]
                                    image_data = image_data[end:]
                                    # Convert JPEG to Pygame surface
                                    image = Image.open(BytesIO(jpeg_data))
                                    image = image.convert('RGB')
                                    image = np.array(image)
                                    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
                                    image = cv2.resize(image, (self.width, self.height))
                                    self.stream_image = pygame.surfarray.make_surface(image.swapaxes(0, 1))
                                    self.last_fetch_time = current_time
                                    break
                    else:
                        print(f"Failed to fetch stream: HTTP {response.status_code}")
                except Exception as e:
                    print(f"Error fetching stream: {e}")
                    time.sleep(1)  # Wait before retrying on error
            time.sleep(0.01)  # Small delay to prevent CPU overload

    def update(self, rotation=0):
        """Update the surface with the latest stream image and apply rotation."""
        self.rotation = rotation
        self.surface.fill((0, 0, 0, 0))  # Clear surface with transparency
        if self.stream_image:
            # Apply rotation if needed
            rotated_image = pygame.transform.rotate(self.stream_image, -self.rotation)
            # Center the rotated image on the surface to handle size changes from rotation
            new_rect = rotated_image.get_rect(center=(self.width // 2, self.height // 2))
            self.surface.blit(rotated_image, new_rect.topleft)
        return self.surface

    def update_size(self, width, height):
        """Update the avatar dimensions dynamically."""
        self.width = max(1, width)
        self.height = max(1, height)
        self.scale_factor = min(self.width / 800, self.height / 600)  # Reset scale factor relative to base
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        # Resize the stream image if available
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