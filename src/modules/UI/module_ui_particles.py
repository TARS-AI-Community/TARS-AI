"""
Module: Particles
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

This module was originally created by Charles-Olivier Dion (Atomikspace).

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.
"""


import pygame
import random
import math
import time
from PIL import Image, ImageDraw, ImageFilter

class Particle:
    def __init__(self, width, height):
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)

        self.vx = random.uniform(-0.4, 0.4)
        self.vy = random.uniform(-0.4, 0.4)

        self.original_vx = self.vx
        self.original_vy = self.vy

        self.energy_boost = random.uniform(2.0, 3.5)  
        self.pulse_offset = random.uniform(0, math.pi * 2)  

        size_type = random.choices(
            ['tiny', 'small', 'medium', 'large', 'xlarge'],
            weights=[0.4, 0.3, 0.2, 0.08, 0.02]
        )[0]

        if size_type == 'tiny':
            self.radius = random.uniform(1, 2)
            self.alpha = random.randint(180, 255)
            self.blur_amount = random.uniform(1, 2)
        elif size_type == 'small':
            self.radius = random.uniform(2, 4)
            self.alpha = random.randint(120, 180)
            self.blur_amount = random.uniform(2, 4)
        elif size_type == 'medium':
            self.radius = random.uniform(4, 8)
            self.alpha = random.randint(80, 140)
            self.blur_amount = random.uniform(4, 8)
        elif size_type == 'large':
            self.radius = random.uniform(8, 15)
            self.alpha = random.randint(50, 100)
            self.blur_amount = random.uniform(8, 15)
        else:  
            self.radius = random.uniform(15, 30)
            self.alpha = random.randint(30, 70)
            self.blur_amount = random.uniform(15, 25)

        self.brightness = random.uniform(0.8, 1.0)
        self.base_alpha = self.alpha  
        self.current_scale = 1.0  

        self.width = width
        self.height = height

        self.base_surface = self.create_blurred_particle(mode='normal')
        self.bright_surface = self.create_blurred_particle(mode='bright')

        self.surface = self.base_surface

    def create_blurred_particle(self, mode='normal'):
        size = int((self.radius + self.blur_amount) * 4)

        pil_image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(pil_image)

        if mode == 'bright':

            color = (
                int(120 * self.brightness),
                int(200 * self.brightness),
                int(255 * self.brightness),
                self.alpha
            )
        else:

            color = (
                int(60 * self.brightness),
                int(140 * self.brightness),
                int(255 * self.brightness),
                self.alpha
            )

        center = size // 2
        draw.ellipse(
            [center - self.radius, center - self.radius, 
             center + self.radius, center + self.radius],
            fill=color
        )

        blur_iterations = max(1, int(self.blur_amount / 3))
        for _ in range(blur_iterations):
            pil_image = pil_image.filter(ImageFilter.GaussianBlur(radius=self.blur_amount))

        mode = pil_image.mode
        size = pil_image.size
        data = pil_image.tobytes()

        py_image = pygame.image.fromstring(data, size, mode)

        return py_image

    def update(self, action_weight=0, think_weight=0, memory_weight=0, pulse_phase=0):
        target_vx = self.original_vx
        target_vy = self.original_vy
        target_brightness = 0.9
        target_scale = 1.0

        if action_weight > 0:
            speed_mult = self.energy_boost
            random_jitter = random.uniform(-0.2, 0.2)
            action_vx = self.original_vx * speed_mult + random_jitter
            action_vy = self.original_vy * speed_mult + random_jitter

            target_vx += (action_vx - self.original_vx) * action_weight
            target_vy += (action_vy - self.original_vy) * action_weight

            pulse_value = (math.sin(pulse_phase + self.pulse_offset) + 1) / 2
            action_brightness = 0.6 + pulse_value * 0.6
            target_brightness += (action_brightness - 0.9) * action_weight

        if think_weight > 0:
            speed_mult = self.energy_boost * 1.2
            random_jitter = random.uniform(-0.3, 0.3)
            think_vx = self.original_vx * speed_mult + random_jitter
            think_vy = self.original_vy * speed_mult + random_jitter

            target_vx += (think_vx - self.original_vx) * think_weight
            target_vy += (think_vy - self.original_vy) * think_weight

            pulse_value = (math.sin(pulse_phase * 1.5 + self.pulse_offset) + 1) / 2
            think_brightness = 1.0 + pulse_value * 0.8
            target_brightness += (think_brightness - 0.9) * think_weight

            think_scale = 1.0 + pulse_value * 0.4  
            target_scale += (think_scale - 1.0) * think_weight

        if memory_weight > 0:
            memory_vx = self.original_vx * 0.5
            memory_vy = self.original_vy * 0.5

            target_vx += (memory_vx - self.original_vx) * memory_weight
            target_vy += (memory_vy - self.original_vy) * memory_weight

            pulse_value = (math.sin(pulse_phase * 2 + self.pulse_offset) + 1) / 2
            memory_brightness = 0.7 + pulse_value * 0.5
            target_brightness += (memory_brightness - 0.9) * memory_weight

        self.vx = self.vx * 0.9 + target_vx * 0.1
        self.vy = self.vy * 0.9 + target_vy * 0.1
        self.brightness = self.brightness * 0.9 + target_brightness * 0.1
        self.current_scale = self.current_scale * 0.9 + target_scale * 0.1

        self.x += self.vx
        self.y += self.vy

        if self.x > self.width:
            self.x = 0
        elif self.x < 0:
            self.x = self.width

        if self.y > self.height:
            self.y = 0
        elif self.y < 0:
            self.y = self.height

        if think_weight > 0.1:
            self.surface = self.bright_surface
        else:
            self.surface = self.base_surface

    def draw(self, surface):
        if self.brightness != 1.0:

            adjusted_surface = self.surface.copy()
            adjusted_surface.set_alpha(int(255 * min(self.brightness, 1.0)))
            surf_to_draw = adjusted_surface
        else:
            surf_to_draw = self.surface

        if abs(self.current_scale - 1.0) > 0.01:
            original_size = surf_to_draw.get_size()
            new_size = (int(original_size[0] * self.current_scale), 
                       int(original_size[1] * self.current_scale))
            surf_to_draw = pygame.transform.smoothscale(surf_to_draw, new_size)

        pos = (int(self.x - surf_to_draw.get_width() // 2), 
               int(self.y - surf_to_draw.get_height() // 2))
        surface.blit(surf_to_draw, pos, special_flags=pygame.BLEND_ALPHA_SDL2)

class ParticleSystem:
    def __init__(self, width, height, num_particles=250, bg_color=(0, 0, 0)):
        self.width = width
        self.height = height
        self.num_particles = num_particles
        self.bg_color = bg_color
        self.particles = []

        self.action_weight = 0.0
        self.think_weight = 0.0
        self.memory_weight = 0.0

        self.action_end_time = None
        self.think_end_time = None
        self.memory_end_time = None

        self.center_x = width / 2
        self.center_y = height / 2

        self.pulse_phase = 0
        for i in range(num_particles):
            self.particles.append(Particle(width, height))

    def action(self):
        self.action_end_time = time.time() + 5.0

    def add_memory(self):
        self.memory_end_time = time.time() + 2.0

    def think(self):
        self.think_end_time = time.time() + 5.0

    def update(self):
        current_time = time.time()
        fade_speed = 0.05  

        if self.action_end_time and current_time < self.action_end_time:
            self.action_weight = min(1.0, self.action_weight + fade_speed)
        else:
            self.action_weight = max(0.0, self.action_weight - fade_speed)
            if self.action_weight == 0 and self.action_end_time:
                self.action_end_time = None

        if self.think_end_time and current_time < self.think_end_time:
            self.think_weight = min(1.0, self.think_weight + fade_speed)
        else:
            self.think_weight = max(0.0, self.think_weight - fade_speed)
            if self.think_weight == 0 and self.think_end_time:
                self.think_end_time = None

        if self.memory_end_time and current_time < self.memory_end_time:
            self.memory_weight = min(1.0, self.memory_weight + fade_speed)
        else:
            self.memory_weight = max(0.0, self.memory_weight - fade_speed)
            if self.memory_weight == 0 and self.memory_end_time:
                self.memory_end_time = None

        if self.action_weight > 0 or self.think_weight > 0 or self.memory_weight > 0:
            self.pulse_phase += 0.1

        for particle in self.particles:
            particle.update(self.action_weight, self.think_weight, self.memory_weight, self.pulse_phase)

    def draw(self, surface):

        surface.fill(self.bg_color)

        for particle in self.particles:
            particle.draw(surface)

        if self.memory_weight > 0.1:
            self.draw_memory_connections(surface)

    def draw_memory_connections(self, surface):
        short_distance = 120
        long_distance = 300  

        pulse_intensity = (math.sin(self.pulse_phase * 3) + 1) / 2
        base_alpha = int(80 * pulse_intensity * self.memory_weight)  

        connections_drawn = 0
        max_connections = 150  

        for i, p1 in enumerate(self.particles):
            if connections_drawn >= max_connections:
                break

            for p2 in self.particles[i+1:]:
                if connections_drawn >= max_connections:
                    break

                dx = p2.x - p1.x
                dy = p2.y - p1.y
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < long_distance:

                    distance_factor = 1 - (dist / long_distance)
                    alpha = int(base_alpha * distance_factor)

                    if alpha > 10:

                        color = (80, 160, 255, alpha)

                        line_surface = pygame.Surface((int(abs(dx)) + 10, int(abs(dy)) + 10), pygame.SRCALPHA)
                        start_pos = (5, 5) if dx >= 0 else (int(abs(dx)) + 5, 5)
                        end_pos = (int(abs(dx)) + 5, int(abs(dy)) + 5) if dx >= 0 else (5, int(abs(dy)) + 5)

                        if dy < 0:
                            start_pos = (start_pos[0], int(abs(dy)) + 5)
                            end_pos = (end_pos[0], 5)

                        pygame.draw.line(line_surface, color, start_pos, end_pos, 2)

                        blit_x = min(p1.x, p2.x) - 5
                        blit_y = min(p1.y, p2.y) - 5
                        surface.blit(line_surface, (blit_x, blit_y), special_flags=pygame.BLEND_ALPHA_SDL2)

                        connections_drawn += 1

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    particle_system = ParticleSystem(800, 600, num_particles=200)

    running = True

    while running:

        particle_system.update()
        particle_system.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()