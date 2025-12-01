import pygame
import math
import numpy as np
from collections import deque
import time
from module_config import load_config

CONFIG = load_config()
target_fps = CONFIG['UI']['target_fps']

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
        self.perspective_shift = perspective_shift  
        self.padding = padding  

    def update(self, spectrum):
        """Update and render the sine wave visualization with FPS control."""
        start_time = time.time()  # Track update start time

        sinewave_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        sinewave_surface.fill((0, 0, 0, 0))

        # Convert to numpy array if needed and check for valid data
        if isinstance(spectrum, list):
            spectrum = np.array(spectrum)
        
        if len(spectrum) > 0 and np.any(spectrum):
            spectrum = np.clip(spectrum, 0, np.max(spectrum))
            spectrum = spectrum / np.max(spectrum)
            sinewave_points = []

            for x in range(self.padding, self.width - self.padding):
                width_adj = max(2, self.width - 2 * self.padding)
                freq_bin = int((x - self.padding) * len(spectrum) / width_adj)
                amplitude = spectrum[freq_bin] * self.max_amplitude
                t = (x - self.padding) / width_adj

                y = amplitude * math.sin(2 * math.pi * t * 3) + (self.height // 2)
                sinewave_points.append((x, int(y)))

            self.wave_history.appendleft(sinewave_points.copy())

        for i, wave in enumerate(reversed(self.wave_history)):
            alpha = int(255 * (1 - self.decay ** i))
            color = (255, 255, 255, alpha)
            x_shift = self.perspective_shift[0] * i 
            y_shift = self.perspective_shift[1] * i
            for j in range(1, len(wave)):
                start_pos = (wave[j - 1][0] + x_shift, wave[j - 1][1] + y_shift)
                end_pos = (wave[j][0] + x_shift, wave[j][1] + y_shift)
                pygame.draw.line(sinewave_surface, color, start_pos, end_pos, 2)

        # ? **Limit FPS to 10**
        elapsed_time = time.time() - start_time
        sleep_time = max(0, (1.0 / target_fps) - elapsed_time)
        time.sleep(sleep_time)

        return sinewave_surface


class BarVisualizer:
    def __init__(self, width, height, num_bars=64, depth=22, bar_width=None, bar_spacing=1, smoothing_factor=0.3):
        self.width = width
        self.height = height
        self.num_bars = num_bars
        self.bar_history = deque(maxlen=depth)
        if bar_width is None:
            total_spacing = (num_bars - 1) * bar_spacing
            self.bar_width = (width - total_spacing) / num_bars
        else:
            self.bar_width = bar_width

        self.bar_spacing = bar_spacing
        self.smoothing_factor = smoothing_factor

        self.previous_values = np.zeros(num_bars)

        self.colors = [
            (255, 0, 0),      
            (255, 165, 0),    
            (255, 255, 0),    
            (0, 255, 0),      
            (0, 255, 255),    
            (0, 0, 255),      
            (128, 0, 128),    
            (255, 0, 255)     
        ]

    def get_color_at_position(self, position):
        """Get color at a specific position in the gradient (0.0 to 1.0)"""
        position = max(0, min(1, position))
        num_colors = len(self.colors)
        scaled_position = position * (num_colors - 1)
        idx1 = int(scaled_position)
        idx2 = min(idx1 + 1, num_colors - 1)
        fraction = scaled_position - idx1

        r = int(self.colors[idx1][0] * (1 - fraction) + self.colors[idx2][0] * fraction)
        g = int(self.colors[idx1][1] * (1 - fraction) + self.colors[idx2][1] * fraction)
        b = int(self.colors[idx1][2] * (1 - fraction) + self.colors[idx2][2] * fraction)

        return (r, g, b)

    def apply_smoothing(self, new_values):
        """Apply temporal smoothing to reduce sudden jumps"""
        smoothed = self.previous_values * (1 - self.smoothing_factor) + new_values * self.smoothing_factor
        self.previous_values = smoothed
        return smoothed

    def apply_neighbor_smoothing(self, values):
        """Apply spatial smoothing between neighboring bars"""
        smoothed = np.copy(values)

        for i in range(1, len(values) - 1):
            smoothed[i] = (values[i-1] + values[i] + values[i+1]) / 3
        return smoothed

    def update(self, spectrum, bar_surface):
        """Update and render the bar visualization with FPS control."""
        start_time = time.time()  # Track update start time

        # Convert to numpy array if needed and check for valid data
        if isinstance(spectrum, list):
            spectrum = np.array(spectrum)
        
        if len(spectrum) > 0 and np.any(spectrum):
            resampled_spectrum = np.zeros(self.num_bars)
            spectrum_bins = len(spectrum)

            for i in range(self.num_bars):
                start_bin = int(i * spectrum_bins / self.num_bars)
                end_bin = int((i + 1) * spectrum_bins / self.num_bars)
                resampled_spectrum[i] = np.mean(spectrum[start_bin:end_bin]) if start_bin != end_bin else spectrum[start_bin]

            if np.max(resampled_spectrum) > 0:
                resampled_spectrum /= np.max(resampled_spectrum)

            smoothed_spectrum = self.apply_smoothing(resampled_spectrum)
            smoothed_spectrum = self.apply_neighbor_smoothing(smoothed_spectrum)

            self.bar_history.appendleft(smoothed_spectrum.copy())

        for i, value in enumerate(self.bar_history[0]):
            bar_height = int(value * self.height * 0.9)
            x = i * (self.bar_width + self.bar_spacing)
            y = self.height - bar_height

            color_position = i / self.num_bars
            color = self.get_color_at_position(color_position)

            rect = pygame.Rect(x, y, self.bar_width, bar_height)
            pygame.draw.rect(bar_surface, (*color, 255), rect)

            reflection_height = bar_height // 2
            reflection_rect = pygame.Rect(x, self.height, self.bar_width, reflection_height)
            pygame.draw.rect(bar_surface, (*color, 85), reflection_rect)

        # ? **Limit FPS to 10**
        elapsed_time = time.time() - start_time
        sleep_time = max(0, (1.0 / target_fps) - elapsed_time)
        time.sleep(sleep_time)

        return bar_surface
