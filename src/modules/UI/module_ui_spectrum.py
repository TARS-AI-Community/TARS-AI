# module_ui_spectrum.py
# ----------------------------------------------
# atomikspace (discord)
# olivierdion1@hotmail.com
# ----------------------------------------------
import pygame
import math
import numpy as np
from collections import deque
import time
import sounddevice as sd
import threading


class SpectrumSystem:
    """Audio spectrum analyzer overlay system with microphone input"""
    
    def __init__(self, width, height, style='wave', bg_alpha=0, sample_rate=44100, chunk_size=2048):
        """
        Initialize spectrum analyzer with audio input
        
        Args:
            width: Screen width
            height: Screen height
            style: 'bars', 'wave', or 'circular'
            bg_alpha: Background transparency (0-255)
            sample_rate: Audio sample rate (Hz)
            chunk_size: Audio buffer size
        """
        self.width = width
        self.height = height
        self.style = style
        self.bg_alpha = bg_alpha
        
        # Audio settings
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_buffer = np.zeros(chunk_size)
        self.audio_lock = threading.Lock()
        
        # Spectrum data
        self.spectrum = np.zeros(64)
        self.spectrum_smoothed = np.zeros(64)
        self.smoothing_factor = 0.3
        
        # Bar visualizer settings
        self.num_bars = 64
        self.bar_spacing = 2
        self.bar_width = (width - (self.num_bars - 1) * self.bar_spacing) / self.num_bars
        
        # Wave visualizer settings
        self.wave_history = deque(maxlen=20)
        self.wave_decay = 0.9
        self.max_amplitude = 80
        
        # Colors - cyan/blue theme to match UI
        self.primary_color = (0, 255, 255)  # Cyan
        self.secondary_color = (100, 200, 255)  # Light blue
        self.accent_color = (0, 200, 255)  # Bright cyan
        
        # Gradient colors for bars
        self.gradient_colors = [
            (0, 100, 150),   # Dark blue
            (0, 150, 200),   # Medium blue
            (0, 200, 255),   # Bright cyan
            (100, 220, 255), # Light cyan
            (150, 240, 255), # Very light cyan
        ]
        
        # Animation states
        self.thinking = False
        self.action_flash = 0
        
        # Position - bottom 30% of screen
        self.spectrum_height = int(height * 0.3)
        self.spectrum_y = height - self.spectrum_height
        
        # Surfaces
        self.spectrum_surface = pygame.Surface((width, self.spectrum_height), pygame.SRCALPHA)
        
        # Audio stream
        self.stream = None
        self.audio_running = False
        self.start_audio_stream()
    
    def audio_callback(self, indata, frames, time_info, status):
        """Callback for audio input stream"""
        if status:
            print(f"Audio status: {status}")
        
        # Store audio data (mono channel)
        with self.audio_lock:
            self.audio_buffer = indata[:, 0].copy()
    
    def start_audio_stream(self):
        """Start audio input stream"""
        try:
            self.stream = sd.InputStream(
                callback=self.audio_callback,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size
            )
            self.stream.start()
            self.audio_running = True
            print("Audio stream started successfully")
        except Exception as e:
            print(f"Failed to start audio stream: {e}")
            self.audio_running = False
    
    def stop_audio_stream(self):
        """Stop audio input stream"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.audio_running = False
            print("Audio stream stopped")
    
    def process_audio(self):
        """Process audio buffer and extract frequency spectrum"""
        with self.audio_lock:
            audio_data = self.audio_buffer.copy()
        
        # Apply window function to reduce spectral leakage
        window = np.hanning(len(audio_data))
        windowed_data = audio_data * window
        
        # Perform FFT
        fft_data = np.fft.rfft(windowed_data)
        
        # Get magnitude spectrum
        magnitude = np.abs(fft_data)
        
        # Convert to dB scale
        magnitude = np.where(magnitude > 0, magnitude, 1e-10)  # Avoid log(0)
        magnitude_db = 20 * np.log10(magnitude)
        
        # Normalize to 0-1 range
        magnitude_db = np.clip(magnitude_db, -60, 0)  # Clip to reasonable range
        magnitude_normalized = (magnitude_db + 60) / 60
        
        # Take only the first half (useful frequency range)
        useful_bins = len(magnitude_normalized) // 2
        spectrum_data = magnitude_normalized[:useful_bins]
        
        # Apply logarithmic frequency scaling (emphasize lower frequencies)
        # This makes the visualization more musical
        num_output_bins = self.num_bars
        output_spectrum = np.zeros(num_output_bins)
        
        for i in range(num_output_bins):
            # Logarithmic mapping
            start_bin = int((i / num_output_bins) ** 2 * len(spectrum_data))
            end_bin = int(((i + 1) / num_output_bins) ** 2 * len(spectrum_data))
            end_bin = max(start_bin + 1, end_bin)
            
            # Average the bins
            output_spectrum[i] = np.mean(spectrum_data[start_bin:end_bin])
        
        return output_spectrum
    
    def update_spectrum(self, spectrum_data=None):
        """
        Update spectrum with new audio data
        
        Args:
            spectrum_data: numpy array of frequency spectrum values (optional, uses mic if None)
        """
        # If no external data provided, process microphone input
        if spectrum_data is None:
            if self.audio_running:
                spectrum_data = self.process_audio()
            else:
                return
        
        if spectrum_data is None or len(spectrum_data) == 0:
            return
        
        # Resample to num_bars if needed
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
        
        # Normalize
        if np.max(spectrum_data) > 0:
            spectrum_data = spectrum_data / np.max(spectrum_data)
        
        # Apply smoothing
        self.spectrum_smoothed = (self.spectrum_smoothed * (1 - self.smoothing_factor) + 
                                 spectrum_data * self.smoothing_factor)
        
        self.spectrum = self.spectrum_smoothed
    
    def get_gradient_color(self, position):
        """Get color from gradient (0.0 to 1.0)"""
        position = max(0, min(1, position))
        num_colors = len(self.gradient_colors)
        scaled_pos = position * (num_colors - 1)
        idx1 = int(scaled_pos)
        idx2 = min(idx1 + 1, num_colors - 1)
        fraction = scaled_pos - idx1
        
        r = int(self.gradient_colors[idx1][0] * (1 - fraction) + 
                self.gradient_colors[idx2][0] * fraction)
        g = int(self.gradient_colors[idx1][1] * (1 - fraction) + 
                self.gradient_colors[idx2][1] * fraction)
        b = int(self.gradient_colors[idx1][2] * (1 - fraction) + 
                self.gradient_colors[idx2][2] * fraction)
        
        return (r, g, b)
    
    def draw_bars(self, surface):
        """Draw bar-style spectrum"""
        for i, value in enumerate(self.spectrum):
            # Calculate bar dimensions
            bar_height = int(value * self.spectrum_height * 0.85)
            x = i * (self.bar_width + self.bar_spacing)
            y = self.spectrum_height - bar_height
            
            # Get gradient color based on height
            color_pos = value  # Use amplitude for color
            color = self.get_gradient_color(color_pos)
            alpha = int(200 * value)  # More transparent for quiet bars
            
            # Draw main bar
            if bar_height > 2:
                rect = pygame.Rect(x, y, self.bar_width, bar_height)
                pygame.draw.rect(surface, (*color, alpha), rect)
                
                # Draw top glow
                glow_color = (min(255, color[0] + 50), 
                             min(255, color[1] + 50), 
                             min(255, color[2] + 50))
                pygame.draw.line(surface, (*glow_color, alpha), 
                               (x, y), (x + self.bar_width, y), 2)
    
    def draw_wave(self, surface):
        """Draw wave-style spectrum"""
        # Generate wave points from spectrum
        wave_points = []
        padding = 20
        
        for x in range(padding, self.width - padding):
            # Map x position to spectrum bin
            bin_idx = int((x - padding) * len(self.spectrum) / (self.width - 2 * padding))
            bin_idx = min(bin_idx, len(self.spectrum) - 1)
            
            # Get amplitude
            amplitude = self.spectrum[bin_idx] * self.max_amplitude
            
            # Create sine wave modulation
            t = (x - padding) / (self.width - 2 * padding)
            y = amplitude * math.sin(2 * math.pi * t * 3) + (self.spectrum_height // 2)
            
            wave_points.append((x, int(y)))
        
        # Store in history
        if len(wave_points) > 0:
            self.wave_history.appendleft(wave_points.copy())
        
        # Draw wave history with depth
        for depth_idx, wave in enumerate(self.wave_history):
            alpha = int(255 * (1 - self.wave_decay ** depth_idx) * 0.7)
            color = self.secondary_color
            
            # Offset for 3D depth effect
            x_shift = depth_idx * 1
            y_shift = depth_idx * 3
            
            # Draw wave
            for j in range(1, len(wave)):
                start_pos = (wave[j - 1][0] + x_shift, wave[j - 1][1] + y_shift)
                end_pos = (wave[j][0] + x_shift, wave[j][1] + y_shift)
                pygame.draw.line(surface, (*color, alpha), start_pos, end_pos, 2)
    
    def draw_circular(self, surface):
        """Draw circular spectrum analyzer"""
        center_x = self.width // 2
        center_y = self.spectrum_height // 2
        radius_inner = 60
        radius_outer = min(self.width, self.spectrum_height) // 3
        
        num_points = len(self.spectrum)
        angle_step = 2 * math.pi / num_points
        
        for i, value in enumerate(self.spectrum):
            angle = i * angle_step - math.pi / 2  # Start from top
            
            # Calculate inner and outer points
            bar_length = value * (radius_outer - radius_inner)
            x1 = center_x + math.cos(angle) * radius_inner
            y1 = center_y + math.sin(angle) * radius_inner
            x2 = center_x + math.cos(angle) * (radius_inner + bar_length)
            y2 = center_y + math.sin(angle) * (radius_inner + bar_length)
            
            # Color based on position around circle
            color = self.get_gradient_color(i / num_points)
            alpha = int(200 * value)
            
            # Draw line
            if bar_length > 1:
                pygame.draw.line(surface, (*color, alpha), (x1, y1), (x2, y2), 3)
    
    # Animation trigger methods (for compatibility)
    def think(self):
        """Trigger thinking animation"""
        self.thinking = True
    
    def action(self):
        """Trigger action animation"""
        self.action_flash = 1.0
    
    def add_memory(self):
        """Trigger memory animation"""
        pass
    
    def update(self):
        """Update animation states and process audio"""
        # Process microphone input
        self.update_spectrum()
        
        # Update animations
        if self.action_flash > 0:
            self.action_flash -= 0.05
            if self.action_flash < 0:
                self.action_flash = 0
    
    def draw(self, surface):
        """Draw spectrum analyzer overlay"""
        # Clear spectrum surface
        self.spectrum_surface.fill((0, 0, 0, 0))
        
        # Draw selected style
        if self.style == 'bars':
            self.draw_bars(self.spectrum_surface)
        elif self.style == 'wave':
            self.draw_wave(self.spectrum_surface)
        elif self.style == 'circular':
            self.draw_circular(self.spectrum_surface)
        
        # Add subtle background
        if self.bg_alpha > 0:
            bg_surface = pygame.Surface((self.width, self.spectrum_height), pygame.SRCALPHA)
            bg_surface.fill((5, 15, 20, self.bg_alpha))
            surface.blit(bg_surface, (0, self.spectrum_y))
        
        # Blit spectrum to main surface at bottom
        surface.blit(self.spectrum_surface, (0, self.spectrum_y))
    
    def __del__(self):
        """Cleanup audio stream on destruction"""
        self.stop_audio_stream()


# Example usage
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    
    spectrum = SpectrumSystem(800, 600, style='wave')
    
    running = True
    print("Spectrum analyzer running - speak into your microphone!")
    
    while running:
        
        screen.fill((0, 0, 0))
        
        spectrum.update()
        spectrum.draw(screen)
        
        pygame.display.flip()
        clock.tick(60)
    
    spectrum.stop_audio_stream()
    pygame.quit()