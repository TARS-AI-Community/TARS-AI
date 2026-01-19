"""
# atomikspace (discord)
# olivierdion1@hotmail.com

-WIP dont use-

"""

import pygame
import random
import math
import numpy as np
from scipy.ndimage import gaussian_filter

class NebulaAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.stars = []
        
        self.generation_step = 0
        self.max_steps = 120
        self.completed = False
        
        self.color_schemes = [
            [(120, 60, 220), (200, 120, 255), (80, 180, 255)],
            [(255, 80, 120), (255, 150, 180), (120, 200, 255)],
            [(60, 220, 180), (120, 255, 220), (180, 120, 255)],
            [(255, 180, 80), (255, 120, 180), (100, 180, 255)],
        ]
        self.colors = random.choice(self.color_schemes)
        self.seed = random.randint(0, 100000)
        
        self.nebula_surface = pygame.Surface((self.width, self.height))
        self.nebula_surface.fill((5, 5, 15))
        
        self._generate_stars()

    def _generate_stars(self):
        self.stars = []
        num_stars = random.randint(500, 1000)
        for _ in range(num_stars):
            x = random.randint(0, self.width)
            y = random.randint(0, self.height)
            brightness = random.randint(180, 255)
            size = random.choices([1, 2], weights=[90, 10])[0]
            
            self.stars.append({
                'x': x, 
                'y': y, 
                'size': size, 
                'brightness': brightness,
                'twinkle': random.uniform(0, 6.28),
                'speed': random.uniform(0.03, 0.08)
            })

    def _generate_fractal_noise(self, res_w, res_h, num_octaves):
        combined = np.zeros((res_h, res_w))
        
        amplitude = 1.0
        frequency = 1.0
        max_value = 0
        
        for octave in range(num_octaves):
            octave_w = int(res_w * frequency)
            octave_h = int(res_h * frequency)
            
            np.random.seed(self.seed + octave * 1000)
            noise = np.random.rand(octave_h, octave_w)
            
            blur = max(1, int(min(octave_w, octave_h) * 0.15))
            noise = gaussian_filter(noise, sigma=blur)
            
            if octave_w != res_w or octave_h != res_h:
                from scipy.ndimage import zoom
                noise = zoom(noise, (res_h / octave_h, res_w / octave_w), order=1)
            
            combined += noise * amplitude
            max_value += amplitude
            
            amplitude *= 0.5
            frequency *= 2.0
        
        combined /= max_value
        return combined

    def _apply_turbulence(self, data, turbulence_strength):
        res_h, res_w = data.shape
        
        np.random.seed(self.seed + 50000)
        offset_x_noise = np.random.rand(res_h, res_w)
        offset_x_noise = gaussian_filter(offset_x_noise, sigma=max(2, res_w * 0.1))
        
        np.random.seed(self.seed + 60000)
        offset_y_noise = np.random.rand(res_h, res_w)
        offset_y_noise = gaussian_filter(offset_y_noise, sigma=max(2, res_h * 0.1))
        
        y_coords, x_coords = np.mgrid[0:res_h, 0:res_w]
        
        offset_x = ((offset_x_noise - 0.5) * 2 * turbulence_strength).astype(int)
        offset_y = ((offset_y_noise - 0.5) * 2 * turbulence_strength).astype(int)
        
        new_x = np.clip(x_coords + offset_x, 0, res_w - 1)
        new_y = np.clip(y_coords + offset_y, 0, res_h - 1)
        
        return data[new_y, new_x]

    def _generate_nebula(self, res_w, res_h, detail_level):
        base_noise = self._generate_fractal_noise(res_w, res_h, 3 + detail_level)
        
        turbulence = min(res_w, res_h) * 0.15
        warped = self._apply_turbulence(base_noise, turbulence)
        
        threshold = 0.4
        mask = warped > threshold
        warped[mask] = (warped[mask] - threshold) / (1 - threshold)
        warped[~mask] = 0
        warped = warped ** 1.6
        
        if detail_level >= 2:
            np.random.seed(self.seed + 99999)
            dark_noise = np.random.rand(res_h, res_w)
            dark_noise = gaussian_filter(dark_noise, sigma=max(2, min(res_w, res_h) * 0.12))
            
            dark_threshold = 0.7
            darkness = np.zeros((res_h, res_w))
            dark_mask = dark_noise > dark_threshold
            darkness[dark_mask] = ((dark_noise[dark_mask] - dark_threshold) / (1 - dark_threshold)) ** 2.5
            
            warped = np.maximum(0, warped - darkness * 0.4)
        
        return warped

    def _noise_to_image(self, noise_data):
        res_h, res_w = noise_data.shape
        img = np.zeros((res_h, res_w, 3), dtype=np.uint8)
        
        for y in range(res_h):
            for x in range(res_w):
                intensity = noise_data[y, x]
                
                if intensity > 0.05:
                    color_pos = intensity * 2.5
                    
                    if color_pos < 0.8:
                        mix = color_pos / 0.8
                        r = int(self.colors[0][0] * mix * 1.0)
                        g = int(self.colors[0][1] * mix * 1.0)
                        b = int(self.colors[0][2] * mix * 1.0)
                    elif color_pos < 1.6:
                        mix = (color_pos - 0.8) / 0.8
                        r = int(self.colors[0][0] * (1-mix) * 1.1 + self.colors[1][0] * mix * 1.0)
                        g = int(self.colors[0][1] * (1-mix) * 1.1 + self.colors[1][1] * mix * 1.0)
                        b = int(self.colors[0][2] * (1-mix) * 1.1 + self.colors[1][2] * mix * 1.0)
                    else:
                        mix = min(1.0, (color_pos - 1.6) / 0.9)
                        r = int(self.colors[1][0] * (1-mix) * 1.05 + self.colors[2][0] * mix * 1.1)
                        g = int(self.colors[1][1] * (1-mix) * 1.05 + self.colors[2][1] * mix * 1.1)
                        b = int(self.colors[1][2] * (1-mix) * 1.05 + self.colors[2][2] * mix * 1.1)
                    
                    r = min(255, r)
                    g = min(255, g)
                    b = min(255, b)
                    
                    img[y, x] = [r, g, b]
                else:
                    img[y, x] = [5, 5, 15]
        
        return img

    def reset(self):
        self.generation_step = 0
        self.completed = False
        self.colors = random.choice(self.color_schemes)
        self.seed = random.randint(0, 100000)
        self.nebula_surface.fill((5, 5, 15))
        self._generate_stars()

    def update(self):
        for star in self.stars:
            star['twinkle'] += star['speed']
        
        if not self.completed:
            if self.generation_step == 0:
                noise = self._generate_nebula(24, 18, 0)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                self.nebula_surface = pygame.transform.smoothscale(surf, (self.width, self.height))
                
            elif self.generation_step == 20:
                noise = self._generate_nebula(32, 24, 1)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                detail_layer = pygame.transform.smoothscale(surf, (self.width, self.height))
                detail_layer.set_alpha(100)
                self.nebula_surface.blit(detail_layer, (0, 0), special_flags=pygame.BLEND_ADD)
                
            elif self.generation_step == 40:
                noise = self._generate_nebula(48, 36, 2)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                detail_layer = pygame.transform.smoothscale(surf, (self.width, self.height))
                detail_layer.set_alpha(100)
                self.nebula_surface.blit(detail_layer, (0, 0), special_flags=pygame.BLEND_ADD)
                
            elif self.generation_step == 60:
                noise = self._generate_nebula(64, 48, 3)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                detail_layer = pygame.transform.smoothscale(surf, (self.width, self.height))
                detail_layer.set_alpha(100)
                self.nebula_surface.blit(detail_layer, (0, 0), special_flags=pygame.BLEND_ADD)
                
            elif self.generation_step == 80:
                noise = self._generate_nebula(80, 60, 4)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                detail_layer = pygame.transform.smoothscale(surf, (self.width, self.height))
                detail_layer.set_alpha(100)
                self.nebula_surface.blit(detail_layer, (0, 0), special_flags=pygame.BLEND_ADD)
                
            elif self.generation_step == 100:
                noise = self._generate_nebula(96, 72, 5)
                img = self._noise_to_image(noise)
                surf = pygame.surfarray.make_surface(img.swapaxes(0, 1))
                detail_layer = pygame.transform.smoothscale(surf, (self.width, self.height))
                detail_layer.set_alpha(100)
                self.nebula_surface.blit(detail_layer, (0, 0), special_flags=pygame.BLEND_ADD)
            
            self.generation_step += 1
            
            if self.generation_step >= self.max_steps:
                self.completed = True

    def render(self):
        self.screen.blit(self.nebula_surface, (0, 0))
        
        for star in self.stars:
            twinkle = 0.7 + 0.3 * abs(math.sin(star['twinkle']))
            brightness = int(star['brightness'] * twinkle)
            color = (brightness, brightness, brightness)
            
            if star['size'] == 1:
                self.screen.set_at((star['x'], star['y']), color)
            else:
                pygame.draw.circle(self.screen, color, (star['x'], star['y']), 1)
        
        if not self.completed:
            progress = self.generation_step / self.max_steps
            bar_width = int(self.width * 0.3)
            bar_height = 4
            bar_x = (self.width - bar_width) // 2
            bar_y = self.height - 30
            
            pygame.draw.rect(self.screen, (60, 60, 80), (bar_x, bar_y, bar_width, bar_height))
            pygame.draw.rect(self.screen, (120, 180, 255), (bar_x, bar_y, int(bar_width * progress), bar_height))