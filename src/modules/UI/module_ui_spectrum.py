"""
SPECTRUM V3
==========================
# atomikspace (discord)
# olivierdion1@hotmail.com
"""
import pygame
import math
import numpy as np
from collections import deque
import time
import sounddevice as sd
import threading

class SpectrumSystem:
    def __init__(self, width, height, style='wave', bg_alpha=0, sample_rate=44100, chunk_size=1024):
        self.stream = None
        self.audio_running = False

        self.width = width
        self.height = height
        self.style = style
        self.bg_alpha = bg_alpha

        self.spectrum_height = int(height * 0.3)
        self.spectrum_y = height - self.spectrum_height

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_buffer = np.zeros(chunk_size)
        self.audio_lock = threading.Lock()

        self.spectrum = np.zeros(64)
        self.spectrum_smoothed = np.zeros(64)
        self.smoothing_factor = 0.3

        self.num_bars = 64
        self.bar_spacing = 2
        self.bar_width = (width - (self.num_bars - 1) * self.bar_spacing) / self.num_bars

        self.wave_history = deque(maxlen=8)  
        self.wave_decay = 0.85  
        self.max_amplitude = 100  

        self.sinewave_history = deque(maxlen=8)  

        self.spectrogram_history = deque(maxlen=100)  
        self.spectrogram_height = int(self.spectrum_height * 0.9)  
        self.spectrogram_freq_resolution = 4  

        for _ in range(100):
            self.spectrogram_history.append(np.zeros(64))

        self.spectrogram_colormap = [
            (20, 0, 40),      
            (60, 0, 80),      
            (100, 20, 120),   
            (140, 40, 140),   
            (180, 60, 120),   
            (220, 80, 80),    
            (255, 120, 40),   
            (255, 180, 80),   
            (255, 220, 150),  
        ]

        self.primary_color = (0, 255, 255)  
        self.secondary_color = (100, 200, 255)  
        self.accent_color = (0, 200, 255)  

        self.gradient_colors = [
            (0, 100, 150),   
            (0, 150, 200),   
            (0, 200, 255),   
            (100, 220, 255), 
            (150, 240, 255), 
        ]

        self.thinking = False
        self.action_flash = 0

        self.silence_progress = 0
        self.silence_max = 20  
        self.color_fade = 0.0  
        self.fade_speed = 0.08
        self.time_at_zero = 0  
        self.zero_delay = 0.9  
        self.max_reached = False  
        self.waiting_for_reset = False  

        self.silence_gradient_colors = [
            (150, 50, 0),    
            (200, 80, 0),    
            (255, 120, 0),   
            (255, 160, 40),  
            (255, 200, 80),  
        ]

        self.spectrum_surface = pygame.Surface((width, self.spectrum_height), pygame.HWSURFACE | pygame.SRCALPHA)
        self.spectrum_surface = self.spectrum_surface.convert_alpha()  

        self.start_audio_stream()

    def audio_callback(self, indata, frames, time_info, status):
        with self.audio_lock:
            self.audio_buffer = indata[:, 0].copy()

    def start_audio_stream(self):
        try:
            self.stream = sd.InputStream(
                callback=self.audio_callback,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size
            )
            self.stream.start()
            self.audio_running = True
        except Exception as e:
            print(f"Failed to start audio stream: {e}")
            self.audio_running = False

    def stop_audio_stream(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.audio_running = False

    def process_audio(self):
        with self.audio_lock:
            audio_data = self.audio_buffer.copy()

        window = np.hanning(len(audio_data))
        windowed_data = audio_data * window

        fft_data = np.fft.rfft(windowed_data)

        magnitude = np.abs(fft_data)

        magnitude = np.where(magnitude > 0, magnitude, 1e-10)  
        magnitude_db = 20 * np.log10(magnitude)

        magnitude_db = np.clip(magnitude_db, -60, 0)  
        magnitude_normalized = (magnitude_db + 60) / 60

        useful_bins = len(magnitude_normalized) // 2
        spectrum_data = magnitude_normalized[:useful_bins]

        num_output_bins = self.num_bars
        output_spectrum = np.zeros(num_output_bins)

        for i in range(num_output_bins):

            start_bin = int((i / num_output_bins) ** 2 * len(spectrum_data))
            end_bin = int(((i + 1) / num_output_bins) ** 2 * len(spectrum_data))
            end_bin = max(start_bin + 1, end_bin)

            output_spectrum[i] = np.mean(spectrum_data[start_bin:end_bin])

        return output_spectrum

    def update_spectrum(self, spectrum_data=None):
        if spectrum_data is None:
            if self.audio_running:
                spectrum_data = self.process_audio()
            else:
                return

        if spectrum_data is None or len(spectrum_data) == 0:
            return

        if len(spectrum_data) != self.num_bars:
            resampled = np.zeros(self.num_bars)
            spectrum_bins = len(spectrum_data)

            for i in range(self.num_bars):
                start_bin = int(i * spectrum_bins / self.num_bars)
                end_bin = int((i + 1) * spectrum_bins / self.num_bars)
                if start_bin != end_bin:
                    resampled[i] = np.mean(spectrum_data[start_bin:end_bin])
                else:
                    resampled[i] = spectrum_data[start_bin]

            spectrum_data = resampled

        if np.max(spectrum_data) > 0:
            spectrum_data = spectrum_data / np.max(spectrum_data)

        self.spectrum_smoothed = (self.spectrum_smoothed * (1 - self.smoothing_factor) + 
                                 spectrum_data * self.smoothing_factor)

        self.spectrum = self.spectrum_smoothed

    def silence(self, progress, max_value=20):
        self.silence_progress = progress
        self.silence_max = max_value

        if progress >= max_value and max_value > 0:
            self.max_reached = True
            self.waiting_for_reset = True
        elif progress == 0 and self.waiting_for_reset:

            pass
        elif progress > 0 and self.waiting_for_reset:

            self.max_reached = False
            self.waiting_for_reset = False
        elif progress > 0:

            self.max_reached = False
            self.waiting_for_reset = False

    def get_gradient_color(self, position, use_silence_colors=False):
        position = max(0, min(1, position))

        if self.color_fade > 0:

            normal_color = self._get_color_from_palette(position, self.gradient_colors)
            silence_color = self._get_color_from_palette(position, self.silence_gradient_colors)

            r = int(normal_color[0] * (1 - self.color_fade) + silence_color[0] * self.color_fade)
            g = int(normal_color[1] * (1 - self.color_fade) + silence_color[1] * self.color_fade)
            b = int(normal_color[2] * (1 - self.color_fade) + silence_color[2] * self.color_fade)

            return (r, g, b)
        else:
            return self._get_color_from_palette(position, self.gradient_colors)

    def _get_color_from_palette(self, position, palette):
        position = max(0, min(1, position))
        num_colors = len(palette)
        scaled_pos = position * (num_colors - 1)
        idx1 = int(scaled_pos)
        idx2 = min(idx1 + 1, num_colors - 1)
        fraction = scaled_pos - idx1

        r = int(palette[idx1][0] * (1 - fraction) + palette[idx2][0] * fraction)
        g = int(palette[idx1][1] * (1 - fraction) + palette[idx2][1] * fraction)
        b = int(palette[idx1][2] * (1 - fraction) + palette[idx2][2] * fraction)

        return (r, g, b)

    def draw_bars(self, surface):
        for i, value in enumerate(self.spectrum):

            bar_height = int(value * self.spectrum_height * 0.85)
            x = i * (self.bar_width + self.bar_spacing)
            y = self.spectrum_height - bar_height

            color_pos = value  
            color = self.get_gradient_color(color_pos)
            alpha = int(200 * value)  

            if bar_height > 2:
                rect = pygame.Rect(x, y, self.bar_width, bar_height)
                pygame.draw.rect(surface, (*color, alpha), rect)

                glow_color = (min(255, color[0] + 50), 
                             min(255, color[1] + 50), 
                             min(255, color[2] + 50))
                pygame.draw.line(surface, (*glow_color, alpha), 
                               (x, y), (x + self.bar_width, y), 2)

    def draw_wave(self, surface):
        wave_points = []
        padding = 20
        center_y = self.spectrum_height // 2

        num_points = self.width - 2 * padding

        for i in range(num_points):
            x = padding + i

            bin_idx = int(i * len(self.spectrum) / num_points)
            bin_idx = min(bin_idx, len(self.spectrum) - 1)

            amplitude = self.spectrum[bin_idx] * self.max_amplitude

            y_upper = center_y - amplitude
            y_lower = center_y + amplitude

            wave_points.append((x, int(y_upper), int(y_lower)))

        if len(wave_points) > 0:
            self.wave_history.appendleft(wave_points.copy())

        for depth_idx, wave in enumerate(self.wave_history):
            alpha = int(255 * (1 - self.wave_decay ** depth_idx) * 0.8)

            color = self.get_gradient_color(0.5)

            x_shift = depth_idx * 1

            for j in range(1, len(wave)):
                x1, y1_upper, y1_lower = wave[j - 1]
                x2, y2_upper, y2_lower = wave[j]

                x1_shifted = x1 + x_shift
                x2_shifted = x2 + x_shift

                pygame.draw.line(surface, (*color, alpha), 
                               (x1_shifted, y1_upper), 
                               (x2_shifted, y2_upper), 2)

                pygame.draw.line(surface, (*color, alpha), 
                               (x1_shifted, y1_lower), 
                               (x2_shifted, y2_lower), 2)

                if depth_idx == 0 and (y1_lower - y1_upper) > 5:

                    pygame.draw.line(surface, (*color, int(alpha * 0.3)), 
                                   (x1_shifted, y1_upper), 
                                   (x1_shifted, y1_lower), 1)

    def draw_sinewave(self, surface):
        """Draw oscilloscope-style waveform with grid and phosphor glow"""
        padding = 40

        osc_height = int(self.spectrum_height * 0.6)  

        osc_top = (self.spectrum_height - osc_height) // 2  

        center_y = osc_top + osc_height // 2

        grid_base_color = (30, 80, 80)

        num_h_divisions = 8
        for i in range(num_h_divisions + 1):
            y = osc_top + int(i * osc_height / num_h_divisions)

            distance_from_center = abs(i - num_h_divisions / 2) / (num_h_divisions / 2)

            alpha = int(60 * (1 - distance_from_center ** 2))

            if alpha > 5:
                pygame.draw.line(surface, (*grid_base_color, alpha), 
                               (padding, y), (self.width - padding, y), 1)

        num_v_divisions = 20
        grid_spacing = (self.width - 2 * padding) // num_v_divisions
        for i in range(num_v_divisions + 1):
            x = padding + i * grid_spacing

            num_segments = 20
            for seg in range(num_segments):
                y1 = osc_top + int(seg * osc_height / num_segments)
                y2 = osc_top + int((seg + 1) * osc_height / num_segments)

                seg_center = (y1 + y2) / 2
                distance_from_center = abs(seg_center - center_y) / (osc_height / 2)

                alpha = int(60 * (1 - distance_from_center ** 2))

                if alpha > 5:
                    pygame.draw.line(surface, (*grid_base_color, alpha), 
                                   (x, y1), (x, y2), 1)

        with self.audio_lock:
            audio_data = self.audio_buffer.copy()

        num_points = self.width - 2 * padding
        step = max(1, len(audio_data) // num_points)

        wave_points = []
        for i in range(num_points):
            x = padding + i

            sample_idx = min(i * step, len(audio_data) - 1)
            amplitude = audio_data[sample_idx]

            y = center_y + int(amplitude * osc_height * 0.45)

            y = max(osc_top, min(osc_top + osc_height, y))

            wave_points.append((x, y))

        if len(wave_points) > 1:
            self.sinewave_history.appendleft(wave_points.copy())

        oscilloscope_color = (0, 255, 200)

        for depth_idx, old_wave in enumerate(self.sinewave_history):

            alpha = int(255 * (1 - depth_idx / len(self.sinewave_history)) * 0.4)

            if len(old_wave) > 1 and alpha > 10:
                pygame.draw.lines(surface, (*oscilloscope_color, alpha), False, old_wave, 1)

        if len(wave_points) > 1:

            pygame.draw.lines(surface, (*oscilloscope_color, 60), False, wave_points, 3)

            pygame.draw.lines(surface, (*oscilloscope_color, 150), False, wave_points, 2)

            pygame.draw.lines(surface, oscilloscope_color, False, wave_points, 1)

        pygame.draw.line(surface, (*oscilloscope_color, 50), 
                        (padding, center_y), 
                        (self.width - padding, center_y), 1)

    def draw_circular(self, surface):
        center_x = self.width // 2
        center_y = self.spectrum_height // 2
        radius_inner = 60
        radius_outer = min(self.width, self.spectrum_height) // 3

        num_points = len(self.spectrum)
        angle_step = 2 * math.pi / num_points

        for i, value in enumerate(self.spectrum):
            angle = i * angle_step - math.pi / 2  

            bar_length = value * (radius_outer - radius_inner)
            x1 = center_x + math.cos(angle) * radius_inner
            y1 = center_y + math.sin(angle) * radius_inner
            x2 = center_x + math.cos(angle) * (radius_inner + bar_length)
            y2 = center_y + math.sin(angle) * (radius_inner + bar_length)

            color = self.get_gradient_color(i / num_points)
            alpha = int(200 * value)

            if bar_length > 1:
                pygame.draw.line(surface, (*color, alpha), (x1, y1), (x2, y2), 3)

    def draw_spectrogram(self, surface):
        if len(self.spectrum) > 0:
            self.spectrogram_history.append(self.spectrum.copy())

        if len(self.spectrogram_history) == 0:
            return

        num_time_slices = len(self.spectrogram_history)
        slice_width = max(2, self.width // num_time_slices)  

        num_freq_bins = len(self.spectrum) // self.spectrogram_freq_resolution
        bin_height = self.spectrogram_height / num_freq_bins

        temp_surface = pygame.Surface((self.width, self.spectrum_height), pygame.SRCALPHA)
        temp_surface.fill((0, 0, 0, 0))

        for time_idx, spectrum_slice in enumerate(self.spectrogram_history):
            x = time_idx * slice_width

            for display_idx in range(num_freq_bins):

                freq_idx = display_idx * self.spectrogram_freq_resolution
                if freq_idx >= len(spectrum_slice):
                    continue

                amplitude = spectrum_slice[freq_idx]

                y = self.spectrogram_height - (display_idx + 1) * bin_height

                color = self.get_spectrogram_color(amplitude)

                fade_factor = (self.spectrum_height - y) / self.spectrum_height
                fade_factor = fade_factor ** 2.5  
                alpha = int(255 * fade_factor * 0.85)  

                if amplitude > 0.05 and alpha > 10:  
                    rect = pygame.Rect(x, int(y), slice_width + 1, max(2, int(bin_height) + 1))
                    pygame.draw.rect(temp_surface, (*color, alpha), rect)

        rotated_surface = pygame.transform.rotate(temp_surface, 180)

        surface.blit(rotated_surface, (0, 0))

    def get_spectrogram_color(self, amplitude):
        amplitude = max(0, min(1, amplitude))

        num_colors = len(self.spectrogram_colormap)
        scaled_pos = amplitude * (num_colors - 1)
        idx1 = int(scaled_pos)
        idx2 = min(idx1 + 1, num_colors - 1)
        fraction = scaled_pos - idx1

        r = int(self.spectrogram_colormap[idx1][0] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][0] * fraction)
        g = int(self.spectrogram_colormap[idx1][1] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][1] * fraction)
        b = int(self.spectrogram_colormap[idx1][2] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][2] * fraction)

        return (r, g, b)

    def draw_silence_progress(self, surface):
        if self.silence_max <= 0:
            return

        if self.max_reached or self.waiting_for_reset:

            return

        if self.silence_progress <= 0 and self.time_at_zero >= self.zero_delay:

            return

        progress_pct = min(1.0, max(0.0, self.silence_progress / self.silence_max))

        bar_height = 8
        bar_width = self.width - 40
        bar_x = 20
        bar_y = (self.spectrum_height - 20) // 2 + 50  

        bg_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(surface, (30, 30, 40, 180), bg_rect)
        pygame.draw.rect(surface, (80, 80, 100, 200), bg_rect, 1)

        fill_width = int(bar_width * progress_pct)
        if fill_width > 0:
            fill_rect = pygame.Rect(bar_x, bar_y, fill_width, bar_height)

            if progress_pct < 0.5:

                r = int(255)
                g = int(140 + (progress_pct * 2) * 80)
                b = 0
            else:

                r = 255
                g = int(220 - ((progress_pct - 0.5) * 2) * 120)
                b = 0

            pygame.draw.rect(surface, (r, g, b, 220), fill_rect)

            glow_color = (min(255, r + 40), min(255, g + 40), min(255, b + 40))
            pygame.draw.rect(surface, (*glow_color, 150), fill_rect, 1)

    def think(self):
        self.thinking = True

    def action(self):
        self.action_flash = 1.0

    def add_memory(self):
        pass

    def update(self):
        self.update_spectrum()

        if self.max_reached or self.waiting_for_reset:

            if self.color_fade > 0:
                self.color_fade = max(0.0, self.color_fade - self.fade_speed)

        elif self.silence_progress > 0:

            self.time_at_zero = 0  
            target_fade = 1.0

            if self.color_fade < target_fade:
                self.color_fade = min(1.0, self.color_fade + self.fade_speed)
        else:

            self.time_at_zero += 1.0 / 60.0  

            if self.time_at_zero >= self.zero_delay:
                if self.color_fade > 0:
                    self.color_fade = max(0.0, self.color_fade - self.fade_speed)

        if self.action_flash > 0:
            self.action_flash -= 0.05
            if self.action_flash < 0:
                self.action_flash = 0

    def draw(self, surface):
        self.spectrum_surface.fill((0, 0, 0, 0))

        if self.style == 'bars':
            self.draw_bars(self.spectrum_surface)
        elif self.style == 'wave':
            self.draw_wave(self.spectrum_surface)
        elif self.style == 'sinewave':
            self.draw_sinewave(self.spectrum_surface)
        elif self.style == 'circular':
            self.draw_circular(self.spectrum_surface)
        elif self.style == 'spectrogram':
            self.draw_spectrogram(self.spectrum_surface)

        self.draw_silence_progress(self.spectrum_surface)

        if self.bg_alpha > 0:
            bg_surface = pygame.Surface((self.width, self.spectrum_height), pygame.SRCALPHA)
            bg_surface.fill((5, 15, 20, self.bg_alpha))
            surface.blit(bg_surface, (0, self.spectrum_y))

        surface.blit(self.spectrum_surface, (0, self.spectrum_y))

    def __del__(self):
        if hasattr(self, 'stream'):
            self.stop_audio_stream()

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    spectrum = SpectrumSystem(800, 600, style='spectrogram')  

    running = True
    silence_counter = 0
    while running:
        if silence_counter > 0:
            spectrum.silence(silence_counter, 20)
            silence_counter -= 0.3
        else:
            spectrum.silence(0, 20)

        screen.fill((0, 0, 0))

        spectrum.update()
        spectrum.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    spectrum.stop_audio_stream()
    pygame.quit()