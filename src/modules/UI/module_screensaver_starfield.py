"""
Module: Starfield Screensaver
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

class StarfieldAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.cx = width // 2
        self.cy = height // 2

        self.stars = []
        self.max_stars = 450
        self.speed = 0.001
        self.curve = 0.0

        for _ in range(self.max_stars):
            self._add_star(random_alpha=True)

    def _add_star(self, random_alpha=False):
        self.stars.append({
            'angle': random.uniform(0, 2 * math.pi),
            'radius': random.uniform(0.15, 1.0),
            'z': random.uniform(0.4, 1.0),
            'alpha': random.randint(0, 160) if random_alpha else 0,
            'color_tint': random.choice(['white', 'blue', 'cyan'])
        })

    def reset(self):
        self.stars.clear()
        self.speed = 0.002
        self.curve = 0.0
        for _ in range(self.max_stars):
            self._add_star(random_alpha=True)

    def update(self):
        self.speed = min(self.speed + 0.00002, 0.008)
        self.curve = min(self.curve + 0.00025, 0.22)

        for star in self.stars[:]:
            star['z'] -= self.speed
            star['angle'] += self.curve * (1 - star['z']) * 0.02
            if star['alpha'] < 255:
                star['alpha'] += 3

            if star['z'] <= 0.05:
                self.stars.remove(star)
                self._add_star()

    def render(self):
        self.screen.fill((0, 0, 0))

        for star in self.stars:
            depth = 1 / star['z']
            r = star['radius'] * depth

            dx = math.cos(star['angle'])
            dy = math.sin(star['angle'])

            x = self.cx + dx * r * self.width * 0.45
            y = self.cy + dy * r * self.height * 0.45

            if x < -50 or x > self.width + 50 or y < -50 or y > self.height + 50:
                continue

            size = max(1, int(depth * 0.55))
            brightness = min(int(140 + depth * 100), 255)
            alpha = max(0, min(255, int(star['alpha'])))

            if star['color_tint'] == 'blue':
                color = (int(brightness * 0.7), int(brightness * 0.85), brightness)
            elif star['color_tint'] == 'cyan':
                color = (int(brightness * 0.8), brightness, brightness)
            else:
                color = (brightness, brightness, brightness)

            if star['z'] < 0.52:
                stretch = (0.52 - star['z']) * 132
                
                segments = 8
                for i in range(segments):
                    fade = 1.0 - (i / segments)
                    seg_alpha = int(alpha * fade)
                    
                    start_x = x - dx * stretch * (i / segments)
                    start_y = y - dy * stretch * (i / segments)
                    end_x = x - dx * stretch * ((i + 1) / segments)
                    end_y = y - dy * stretch * ((i + 1) / segments)
                    
                    if fade > 0.7:
                        seg_color = (brightness, brightness, brightness)
                    elif fade > 0.4:
                        mix = (0.7 - fade) / 0.3
                        r = int(brightness * (1.0 - mix * 0.3))
                        g = int(brightness * (1.0 - mix * 0.15))
                        b = brightness
                        seg_color = (r, g, b)
                    else:
                        darken = (0.4 - fade) / 0.4
                        r = int(brightness * (0.7 - darken * 0.7))
                        g = int(brightness * (0.85 - darken * 0.85))
                        b = int(brightness * (1.0 - darken))
                        seg_color = (r, g, b)
                    
                    seg_len = int(math.hypot(end_x - start_x, end_y - start_y)) + 1
                    if seg_len < 2:
                        continue
                    
                    line_surf = pygame.Surface((seg_len, size + 2), pygame.SRCALPHA)
                    pygame.draw.line(line_surf, seg_color, (0, (size+1)//2), (seg_len, (size+1)//2), size)
                    line_surf.set_alpha(seg_alpha)
                    
                    angle = math.degrees(math.atan2(end_y - start_y, end_x - start_x))
                    line_surf = pygame.transform.rotate(line_surf, -angle)
                    self.screen.blit(line_surf, (start_x - line_surf.get_width()//2, start_y - line_surf.get_height()//2))
                
                dot_surf = pygame.Surface((size*2 + 2, size*2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, color, (size + 1, size + 1), size)
                dot_surf.set_alpha(alpha)
                self.screen.blit(dot_surf, (x - size - 1, y - size - 1))
            else:
                dot_surf = pygame.Surface((size*2 + 2, size*2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(dot_surf, color, (size + 1, size + 1), size)
                dot_surf.set_alpha(alpha)
                self.screen.blit(dot_surf, (x - size - 1, y - size - 1))