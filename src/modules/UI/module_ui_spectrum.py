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
    
    def __init__(self, width, height, style='wave', bg_alpha=0, sample_rate=44100, chunk_size=1024):
        """
        Initialize spectrum analyzer with audio input
        
        Args:
            width: Screen width
            height: Screen height
            style: 'bars', 'wave', 'circular', or 'spectrogram'
            bg_alpha: Background transparency (0-255)
            sample_rate: Audio sample rate (Hz)
            chunk_size: Audio buffer size
        """
        # Initialize stream early to avoid AttributeError in __del__ if init fails
        self.stream = None
        self.audio_running = False
        
        self.width = width
        self.height = height
        self.style = style
        self.bg_alpha = bg_alpha
        
        # Position - bottom 30% of screen (define early as it's needed by other settings)
        self.spectrum_height = int(height * 0.3)
        self.spectrum_y = height - self.spectrum_height
        
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
        self.wave_history = deque(maxlen=8)  # Reduced from 20 for faster response
        self.wave_decay = 0.85  # Faster decay from 0.9
        self.max_amplitude = 100  # Increased from 80 for more visible changes
        
        # Spectrogram visualizer settings
        self.spectrogram_history = deque(maxlen=100)  # Reduced from 200 for better performance
        self.spectrogram_height = int(self.spectrum_height * 0.9)  # Use 90% of height
        self.spectrogram_freq_resolution = 4  # Only draw every 4th frequency bin for speed
        
        # Pre-fill history with zeros so screen fills immediately
        for _ in range(100):
            self.spectrogram_history.append(np.zeros(64))
        
        # Spectrogram color map (audio fingerprinting style - purple to orange)
        self.spectrogram_colormap = [
            (20, 0, 40),      # Dark purple/black
            (60, 0, 80),      # Purple
            (100, 20, 120),   # Medium purple
            (140, 40, 140),   # Bright purple
            (180, 60, 120),   # Purple-pink
            (220, 80, 80),    # Pink-red
            (255, 120, 40),   # Orange
            (255, 180, 80),   # Light orange
            (255, 220, 150),  # Pale yellow
        ]
        
        # Colors - cyan/blue theme to match UI
        self.primary_color = (0, 255, 255)  # Cyan
        self.secondary_color = (100, 200, 255)  # Light blue
        self.accent_color = (0, 200, 255)  # Bright cyan
        
        # Gradient colors for bars (normal state)
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
        
        # Silence detection progress
        self.silence_progress = 0
        self.silence_max = 20  # Will be updated from UI manager
        self.color_fade = 0.0  # 0.0 = normal colors, 1.0 = silence colors
        self.fade_speed = 0.08
        self.time_at_zero = 0  # Track how long we've been at zero
        self.zero_delay = 0.9  # Wait 0.9 seconds at zero before fading colors back
        self.max_reached = False  # Track if we've reached max value
        self.waiting_for_reset = False  # Track if we're waiting for zero after max
        
        # Silence detection colors - warmer orange/amber theme
        self.silence_gradient_colors = [
            (150, 50, 0),    # Dark orange
            (200, 80, 0),    # Medium orange
            (255, 120, 0),   # Bright orange
            (255, 160, 40),  # Light orange
            (255, 200, 80),  # Amber
        ]
        
        # Surfaces
        # Use HWSURFACE for GPU acceleration and SRCALPHA for transparency
        self.spectrum_surface = pygame.Surface((width, self.spectrum_height), pygame.HWSURFACE | pygame.SRCALPHA)
        self.spectrum_surface = self.spectrum_surface.convert_alpha()  # Pre-convert for faster blitting
        
        # Start audio stream (stream and audio_running already initialized at top of __init__)
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
    
    def silence(self, progress, max_value=20):
        """
        Update silence detection progress
        
        Args:
            progress: Current silence counter (0 to max_value)
            max_value: Maximum silence value (speechdelay)
        """
        self.silence_progress = progress
        self.silence_max = max_value
        
        # Check if we've reached max
        if progress >= max_value and max_value > 0:
            self.max_reached = True
            self.waiting_for_reset = True
        elif progress == 0 and self.waiting_for_reset:
            # We're at zero after reaching max - stay in waiting state
            # Don't clear flags yet
            pass
        elif progress > 0 and self.waiting_for_reset:
            # We've gone from max -> 0 -> positive again, now we can reset
            self.max_reached = False
            self.waiting_for_reset = False
        elif progress > 0:
            # Normal operation - just ensure flags are clear
            self.max_reached = False
            self.waiting_for_reset = False
    
    def get_gradient_color(self, position, use_silence_colors=False):
        """Get color from gradient (0.0 to 1.0)"""
        position = max(0, min(1, position))
        
        # Choose color palette based on state and fade
        if self.color_fade > 0:
            # Blend between normal and silence colors
            normal_color = self._get_color_from_palette(position, self.gradient_colors)
            silence_color = self._get_color_from_palette(position, self.silence_gradient_colors)
            
            r = int(normal_color[0] * (1 - self.color_fade) + silence_color[0] * self.color_fade)
            g = int(normal_color[1] * (1 - self.color_fade) + silence_color[1] * self.color_fade)
            b = int(normal_color[2] * (1 - self.color_fade) + silence_color[2] * self.color_fade)
            
            return (r, g, b)
        else:
            return self._get_color_from_palette(position, self.gradient_colors)
    
    def _get_color_from_palette(self, position, palette):
        """Get interpolated color from a palette"""
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
        """Draw wave-style spectrum - directly responsive to audio"""
        # Generate wave points from spectrum
        wave_points = []
        padding = 20
        center_y = self.spectrum_height // 2
        
        # Map screen width to spectrum bins
        num_points = self.width - 2 * padding
        
        for i in range(num_points):
            x = padding + i
            
            # Map x position to spectrum bin (use full spectrum range)
            bin_idx = int(i * len(self.spectrum) / num_points)
            bin_idx = min(bin_idx, len(self.spectrum) - 1)
            
            # Get amplitude directly from spectrum
            amplitude = self.spectrum[bin_idx] * self.max_amplitude
            
            # Create upper and lower wave points (mirrored)
            y_upper = center_y - amplitude
            y_lower = center_y + amplitude
            
            wave_points.append((x, int(y_upper), int(y_lower)))
        
        # Store in history
        if len(wave_points) > 0:
            self.wave_history.appendleft(wave_points.copy())
        
        # Draw wave history with depth
        for depth_idx, wave in enumerate(self.wave_history):
            alpha = int(255 * (1 - self.wave_decay ** depth_idx) * 0.8)
            
            # Get color with current fade state
            color = self.get_gradient_color(0.5)
            
            # Offset for 3D depth effect
            x_shift = depth_idx * 1
            
            # Draw the wave as filled area
            for j in range(1, len(wave)):
                x1, y1_upper, y1_lower = wave[j - 1]
                x2, y2_upper, y2_lower = wave[j]
                
                # Apply shift
                x1_shifted = x1 + x_shift
                x2_shifted = x2 + x_shift
                
                # Draw upper wave line
                pygame.draw.line(surface, (*color, alpha), 
                               (x1_shifted, y1_upper), 
                               (x2_shifted, y2_upper), 2)
                
                # Draw lower wave line (mirror)
                pygame.draw.line(surface, (*color, alpha), 
                               (x1_shifted, y1_lower), 
                               (x2_shifted, y2_lower), 2)
                
                # Optional: connect them for filled effect on louder sounds
                if depth_idx == 0 and (y1_lower - y1_upper) > 5:
                    # Draw vertical line to create filled effect
                    pygame.draw.line(surface, (*color, int(alpha * 0.3)), 
                                   (x1_shifted, y1_upper), 
                                   (x1_shifted, y1_lower), 1)
    
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
    
    def draw_spectrogram(self, surface):
        """Draw spectrogram-style visualization (audio fingerprinting look) - fades to transparent at top"""
        # Add current spectrum to history
        if len(self.spectrum) > 0:
            self.spectrogram_history.append(self.spectrum.copy())
        
        if len(self.spectrogram_history) == 0:
            return
        
        # Calculate dimensions
        num_time_slices = len(self.spectrogram_history)
        slice_width = max(2, self.width // num_time_slices)  # At least 2px wide
        
        # Number of frequency bins to display (reduced for performance)
        num_freq_bins = len(self.spectrum) // self.spectrogram_freq_resolution
        bin_height = self.spectrogram_height / num_freq_bins
        
        # Create temporary surface to draw on
        temp_surface = pygame.Surface((self.width, self.spectrum_height), pygame.SRCALPHA)
        temp_surface.fill((0, 0, 0, 0))
        
        # Draw spectrogram from left to right (oldest to newest)
        for time_idx, spectrum_slice in enumerate(self.spectrogram_history):
            x = time_idx * slice_width
            
            # Draw each frequency bin as a colored rectangle (skip bins for performance)
            for display_idx in range(num_freq_bins):
                # Get actual frequency bin (skip based on resolution)
                freq_idx = display_idx * self.spectrogram_freq_resolution
                if freq_idx >= len(spectrum_slice):
                    continue
                    
                amplitude = spectrum_slice[freq_idx]
                
                # Y position (inverted - low frequencies at bottom)
                y = self.spectrogram_height - (display_idx + 1) * bin_height
                
                # Map amplitude to color using colormap
                color = self.get_spectrogram_color(amplitude)
                
                # Apply aggressive vertical fade to transparent at top
                # More transparent as we go up (lower y values)
                # Use exponential fade for softer edges
                fade_factor = (self.spectrum_height - y) / self.spectrum_height
                fade_factor = fade_factor ** 2.5  # Exponential fade (more aggressive)
                alpha = int(255 * fade_factor * 0.85)  # Max 85% opacity
                
                # Only draw if amplitude is significant
                if amplitude > 0.05 and alpha > 10:  # Threshold to avoid drawing noise
                    rect = pygame.Rect(x, int(y), slice_width + 1, max(2, int(bin_height) + 1))
                    pygame.draw.rect(temp_surface, (*color, alpha), rect)
        
        # Rotate the entire surface 180 degrees
        rotated_surface = pygame.transform.rotate(temp_surface, 180)
        
        # Blit the rotated surface to the main surface
        surface.blit(rotated_surface, (0, 0))
    
    def get_spectrogram_color(self, amplitude):
        """Get color from spectrogram colormap based on amplitude (0.0 to 1.0)"""
        amplitude = max(0, min(1, amplitude))
        
        # Map to colormap index
        num_colors = len(self.spectrogram_colormap)
        scaled_pos = amplitude * (num_colors - 1)
        idx1 = int(scaled_pos)
        idx2 = min(idx1 + 1, num_colors - 1)
        fraction = scaled_pos - idx1
        
        # Interpolate between colors
        r = int(self.spectrogram_colormap[idx1][0] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][0] * fraction)
        g = int(self.spectrogram_colormap[idx1][1] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][1] * fraction)
        b = int(self.spectrogram_colormap[idx1][2] * (1 - fraction) + 
                self.spectrogram_colormap[idx2][2] * fraction)
        
        return (r, g, b)
    
    def draw_silence_progress(self, surface):
        """Draw silence detection progress bar"""
        # Don't show if max reached (speech triggered) or waiting for reset cycle
        if self.silence_max <= 0:
            return
        
        if self.max_reached or self.waiting_for_reset:
            # Max reached or waiting for full reset - hide bar immediately
            return
        
        if self.silence_progress <= 0 and self.time_at_zero >= self.zero_delay:
            # Been at zero for 0.9+ seconds, don't show
            return
        
        # Calculate progress percentage
        progress_pct = min(1.0, max(0.0, self.silence_progress / self.silence_max))
        
        # Progress bar dimensions - positioned lower by 50px total
        bar_height = 8
        bar_width = self.width - 40
        bar_x = 20
        bar_y = (self.spectrum_height - 20) // 2 + 50  # Lowered by 50px total (was +20, now +50)
        
        # Draw background
        bg_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(surface, (30, 30, 40, 180), bg_rect)
        pygame.draw.rect(surface, (80, 80, 100, 200), bg_rect, 1)
        
        # Draw progress fill
        fill_width = int(bar_width * progress_pct)
        if fill_width > 0:
            fill_rect = pygame.Rect(bar_x, bar_y, fill_width, bar_height)
            
            # Color gradient from orange to red as it approaches max
            if progress_pct < 0.5:
                # Orange to yellow
                r = int(255)
                g = int(140 + (progress_pct * 2) * 80)
                b = 0
            else:
                # Yellow to red
                r = 255
                g = int(220 - ((progress_pct - 0.5) * 2) * 120)
                b = 0
            
            pygame.draw.rect(surface, (r, g, b, 220), fill_rect)
            
            # Add glow effect
            glow_color = (min(255, r + 40), min(255, g + 40), min(255, b + 40))
            pygame.draw.rect(surface, (*glow_color, 150), fill_rect, 1)
    
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
        
        # Update color fade based on silence progress with delay at zero
        if self.max_reached or self.waiting_for_reset:
            # Max reached or waiting for reset - fade back to blue immediately
            if self.color_fade > 0:
                self.color_fade = max(0.0, self.color_fade - self.fade_speed)
            
            # Don't clear max_reached here - let silence() method handle state transitions
                
        elif self.silence_progress > 0:
            # We have silence detected - fade to warmer colors immediately
            self.time_at_zero = 0  # Reset the zero timer
            target_fade = 1.0
            
            if self.color_fade < target_fade:
                self.color_fade = min(1.0, self.color_fade + self.fade_speed)
        else:
            # silence_progress is 0 - track how long we've been at zero
            self.time_at_zero += 1.0 / 60.0  # Assuming 60 FPS, adjust if needed
            
            # Only start fading back to blue after 0.9 seconds at zero
            if self.time_at_zero >= self.zero_delay:
                if self.color_fade > 0:
                    self.color_fade = max(0.0, self.color_fade - self.fade_speed)
        
        # Update animations
        if self.action_flash > 0:
            self.action_flash -= 0.05
            if self.action_flash < 0:
                self.action_flash = 0
    
    def draw(self, surface):
        """Draw spectrum analyzer overlay"""
        # Clear spectrum surface (only the area we need)
        self.spectrum_surface.fill((0, 0, 0, 0))
        
        # Draw selected style
        if self.style == 'bars':
            self.draw_bars(self.spectrum_surface)
        elif self.style == 'wave':
            self.draw_wave(self.spectrum_surface)
        elif self.style == 'circular':
            self.draw_circular(self.spectrum_surface)
        elif self.style == 'spectrogram':
            self.draw_spectrogram(self.spectrum_surface)
        
        # Draw silence progress indicator (on top of spectrum)
        self.draw_silence_progress(self.spectrum_surface)
        
        # Add subtle background
        if self.bg_alpha > 0:
            bg_surface = pygame.Surface((self.width, self.spectrum_height), pygame.SRCALPHA)
            bg_surface.fill((5, 15, 20, self.bg_alpha))
            surface.blit(bg_surface, (0, self.spectrum_y))
        
        # Blit spectrum to main surface at bottom
        surface.blit(self.spectrum_surface, (0, self.spectrum_y))
    
    def __del__(self):
        """Cleanup audio stream on destruction"""
        if hasattr(self, 'stream'):
            self.stop_audio_stream()


# Example usage
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    
    spectrum = SpectrumSystem(800, 600, style='spectrogram')  # Try: 'bars', 'wave', 'circular', 'spectrogram'
    
    running = True
    silence_counter = 0
    print("Spectrum analyzer running - speak into your microphone!")
    print("Press SPACE to simulate silence detection")
    print("Press S to cycle through visualization styles")
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # Simulate silence detection
                    silence_counter = 20
                elif event.key == pygame.K_s:
                    # Cycle through styles
                    styles = ['bars', 'wave', 'circular', 'spectrogram']
                    current_idx = styles.index(spectrum.style)
                    next_idx = (current_idx + 1) % len(styles)
                    spectrum.style = styles[next_idx]
                    print(f"Style: {styles[next_idx]}")
        
        # Update silence counter (simulated)
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