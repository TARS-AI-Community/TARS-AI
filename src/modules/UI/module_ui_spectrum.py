import pygame
import math
import numpy as np
from collections import deque

class SineWaveVisualizer:
    def __init__(self, width, height, rotation, depth=22, decay=0.9, perspective_shift=(-2, 5), padding=-35):
        if rotation in (90, 270):
            self.width, self.height = height, width
        else:
            self.width = width
            self.height = height
        self.max_amplitude = 70
        self.wave_history = deque(maxlen=depth)
        self.decay = decay
        self.perspective_shift = perspective_shift  # (x_shift, y_shift) per depth level
        self.padding = padding  # Minimum padding from boundaries

    def update(self, spectrum):
        sinewave_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        sinewave_surface.fill((0, 0, 0, 0))

        if spectrum.any():
            spectrum = np.clip(spectrum, 0, np.max(spectrum))
            spectrum = spectrum / np.max(spectrum)
            sinewave_points = []
            
            # Map x coordinates to the center, and apply padding
            for x in range(self.padding, self.width - self.padding):
                # Adjust the frequency bin to account for padding on both sides
                freq_bin = int((x - self.padding) * len(spectrum) / (self.width - 2 * self.padding))
                amplitude = spectrum[freq_bin] * self.max_amplitude
                t = (x - self.padding) / (self.width - 2 * self.padding)
                # Centering the wave around the middle of the screen
                y = amplitude * math.sin(2 * math.pi * t * 3) + (self.height // 2)
                sinewave_points.append((x, int(y)))

            self.wave_history.appendleft(sinewave_points.copy())

        for i, wave in enumerate(reversed(self.wave_history)):
            # Start with 0 alpha, and gradually increase to 255
            alpha = int(255 * (1 - self.decay ** i))
            color = (255, 255, 255, alpha)  # White in front, fading from transparent to full white
            x_shift = self.perspective_shift[0] * i 
            y_shift = self.perspective_shift[1] * i
            for j in range(1, len(wave)):
                start_pos = (wave[j - 1][0] + x_shift, wave[j - 1][1] + y_shift)
                end_pos = (wave[j][0] + x_shift, wave[j][1] + y_shift)
                pygame.draw.line(sinewave_surface, color, start_pos, end_pos, 2)

        return sinewave_surface
