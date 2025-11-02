# module_ui_starfield.py
# ----------------------------------------------
# atomikspace (discord)
# olivierdion1@hotmail.com
# ----------------------------------------------
import pygame
import random
import math
import time


class Star:
    def __init__(self, width: int, height: int):
        self.width = max(2, width)
        self.height = max(2, height)
        self.base_speed = random.uniform(1, 2.5)
        self.speed = self.base_speed
        self.pulse_offset = random.uniform(0, math.pi * 2)
        self.reset()
            
    def reset(self):
        safe_width = max(2, self.width)
        safe_height = max(2, self.height)
        min_x, max_x = sorted([-safe_width, safe_width])
        min_y, max_y = sorted([-safe_height, safe_height])
        self.x = random.randrange(min_x, max_x)
        self.y = random.randrange(min_y, max_y)
        min_z = 1
        max_z = max(2, safe_width)
        self.z = random.randrange(min_z, max_z)
    
    def moveStars(self, speed_multiplier=1.0):
        self.speed = self.base_speed * speed_multiplier
        self.z -= self.speed
        if self.z <= 0:
            self.reset()
    
    def drawStars(self, screen, memory_weight=0, pulse_phase=0):
        factor = 200.0 / max(0.1, self.z)
        x = self.x * factor + self.width // 2
        y = self.y * factor + self.height // 2
        base_size = max(1, min(5, 200.0 / max(0.1, self.z)))
        
        # Color based on depth
        depth_factor = self.z / self.width
        
        # Normal mode: blue/cyan
        normal_r = int(173 * (1 - depth_factor))
        normal_g = int(216 * (1 - depth_factor))
        normal_b = int(230 * (1 - depth_factor))
        
        # Memory mode: light blue/cyan glow with pulsing
        pulse_value = (math.sin(pulse_phase + self.pulse_offset) + 1) / 2
        pulse_brightness = 0.7 + pulse_value * 0.5
        
        memory_r = int(min(255, max(0, 150 * pulse_brightness * (1 - depth_factor * 0.5))))
        memory_g = int(min(255, max(0, 220 * pulse_brightness * (1 - depth_factor * 0.5))))
        memory_b = int(min(255, max(0, 255 * pulse_brightness * (1 - depth_factor * 0.5))))
        
        # Blend colors based on memory_weight
        r = int(normal_r * (1 - memory_weight) + memory_r * memory_weight)
        g = int(normal_g * (1 - memory_weight) + memory_g * memory_weight)
        b = int(normal_b * (1 - memory_weight) + memory_b * memory_weight)
        
        # Flicker effect (only when not in memory mode)
        if memory_weight < 0.5:
            flicker = random.randint(-10, 10)
            r = max(0, min(255, r + flicker))
            g = max(0, min(255, g + flicker))
            b = max(0, min(255, b + flicker))
        
        # Size pulsing and growth for memory mode
        size_multiplier = 1.0
        if memory_weight > 0:
            # Grow stars bigger (up to 2x size) and pulse
            growth = 1.0 + memory_weight * 1.0  # Grows to 2x size at full weight
            pulse_size = 0.85 + pulse_value * 0.3  # Pulse between 0.85 and 1.15
            size_multiplier = growth * pulse_size
        
        size = base_size * size_multiplier
        
        # Draw star if on screen with blur effect
        if 0 <= x < self.width and 0 <= y < self.height:
            # Draw blur layers (outer to inner)
            blur_layers = 3
            for i in range(blur_layers, 0, -1):
                blur_size = int(size * (1 + i * 0.4))
                blur_alpha = int(100 / (i + 1))
                
                # Increase blur intensity during memory mode
                if memory_weight > 0:
                    blur_alpha = int(blur_alpha * (1 + memory_weight * 0.5))
                
                # Create semi-transparent surface for blur layer
                surf_size = max(4, blur_size * 4)
                blur_surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
                
                # Draw circle with alpha on the surface
                center = surf_size // 2
                pygame.draw.circle(
                    blur_surf,
                    (r, g, b, min(255, blur_alpha)),
                    (center, center),
                    blur_size
                )
                
                # Blit the blur layer
                screen.blit(
                    blur_surf,
                    (int(x - surf_size // 2), int(y - surf_size // 2)),
                    special_flags=pygame.BLEND_ALPHA_SDL2
                )
            
            # Draw bright center (no alpha needed)
            pygame.draw.circle(screen, (r, g, b), (int(x), int(y)), max(1, int(size)))


class StarfieldSystem:
    """Manages a warp speed starfield animation"""
    
    def __init__(self, width, height, num_stars=300, bg_color=(0, 0, 0)):
        """
        Initialize starfield system
        
        Args:
            width: Screen width
            height: Screen height
            num_stars: Number of stars to create
            bg_color: Background color tuple (R, G, B) - default black
        """
        self.width = width
        self.height = height
        self.num_stars = num_stars
        self.bg_color = bg_color
        self.stars = []
        
        # Animation weights (0 to 1)
        self.action_weight = 0.0
        self.think_weight = 0.0
        self.memory_weight = 0.0
        
        # Animation timers
        self.action_end_time = None
        self.think_end_time = None
        self.memory_end_time = None
        
        # Pulse phase for memory mode
        self.pulse_phase = 0
        
        # Speed multipliers for different modes
        self.base_speed = 1.0
        self.action_speed = 1.8
        self.think_speed = 3.0
        self.memory_speed = 0.3
        
        for _ in range(num_stars):
            self.stars.append(Star(width, height))

    
    def action(self):
        """Activate action animation mode for 5 seconds"""
        self.action_end_time = time.time() + 5.0
    
    def add_memory(self):
        """Activate memory animation for 4 seconds"""
        self.memory_end_time = time.time() + 4.0
    
    def think(self):
        """Activate thinking animation mode for 5 seconds (WARP SPEED!)"""
        self.think_end_time = time.time() + 5.0
    
    def update(self):
        """Update all stars"""
        current_time = time.time()
        fade_speed = 0.03  # Slower fade for smoother transitions
        
        # Update action weight
        if self.action_end_time and current_time < self.action_end_time:
            self.action_weight = min(1.0, self.action_weight + fade_speed)
        else:
            self.action_weight = max(0.0, self.action_weight - fade_speed)
            if self.action_weight == 0 and self.action_end_time:
                self.action_end_time = None
        
        # Update think weight
        if self.think_end_time and current_time < self.think_end_time:
            self.think_weight = min(1.0, self.think_weight + fade_speed)
        else:
            self.think_weight = max(0.0, self.think_weight - fade_speed)
            if self.think_weight == 0 and self.think_end_time:
                self.think_end_time = None
        
        # Update memory weight
        if self.memory_end_time and current_time < self.memory_end_time:
            self.memory_weight = min(1.0, self.memory_weight + fade_speed)
        else:
            self.memory_weight = max(0.0, self.memory_weight - fade_speed)
            if self.memory_weight == 0 and self.memory_end_time:
                self.memory_end_time = None
        
        # Update pulse phase for memory mode
        if self.memory_weight > 0:
            self.pulse_phase += 0.08  # Slightly slower pulse
        
        # Calculate combined speed multiplier
        speed_mult = self.base_speed
        speed_mult += (self.action_speed - self.base_speed) * self.action_weight
        speed_mult += (self.think_speed - self.base_speed) * self.think_weight
        speed_mult += (self.memory_speed - self.base_speed) * self.memory_weight
        
        # Update all stars
        for star in self.stars:
            star.moveStars(speed_mult)
    
    def draw(self, surface):
        """Draw all stars"""
        # Black background
        surface.fill(self.bg_color)
        
        # Draw stars with memory weight for smooth transitions
        for star in self.stars:
            star.drawStars(surface, self.memory_weight, self.pulse_phase)


# Example usage if run directly
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    
    # Create starfield system
    starfield = StarfieldSystem(800, 600, num_stars=300)
    
    running = True
    
    while running:

        # Update and draw
        starfield.update()
        starfield.draw(screen)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()