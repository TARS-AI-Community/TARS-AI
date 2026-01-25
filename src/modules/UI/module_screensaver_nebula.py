"""
Module: Nebula Screensaver
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

This module was originally created by Charles-Olivier Dion (Atomikspace).
Modified to create nebula visualization.

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.
"""

import random
import time
import math
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
import pygame
from UI.module_screensaver_overlay import TimeOverlay


class NebulaAnimation:
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.time = 0.0
        self.initialized = False
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None
        self.blob_texture = None
        self.wisp_texture = None
        self.star_texture = None
        self.filament_texture = None
        self.noise_texture = None
        self.background_display_list = None
        
        self.stars = []
        self.nebula_clouds = []
        self.dust_particles = []
        self.bright_stars = []
        
        self.nebula_offset = (0, 0)
        self.nebula_scale = 1.0
        
        self.nebula_name = self._generate_nebula_name()
        self.name_font = None
        self.name_surface = None
        
        self.transition_duration = 2.0
        self.display_duration = 20.0
        self.time_since_last_transition = 0.0
        self.transitioning = False
        self.transition_progress = 0.0

        self.current_texture = None
        self.next_texture = None
        self.current_name = None
        self.next_name = None
        
        self.nebula_cache = []
        self.cache_size = 3
        self.cache_index = 0

        self.nebula_palettes = [
            {
                'primary': (1.0, 0.4, 0.1),      
                'secondary': (0.9, 0.2, 0.1),    
                'tertiary': (1.0, 0.7, 0.2),     
                'accent': (1.0, 0.5, 0.3),       
            },
            {
                'primary': (0.2, 0.4, 0.9),      
                'secondary': (0.4, 0.3, 0.8),    
                'tertiary': (0.3, 0.6, 1.0),     
                'accent': (0.5, 0.4, 0.9),       
            },
            {
                'primary': (0.9, 0.3, 0.2),      
                'secondary': (0.3, 0.5, 0.9),    
                'tertiary': (0.8, 0.5, 0.2),     
                'accent': (0.4, 0.3, 0.7),       
            },
            {
                'primary': (0.9, 0.3, 0.5),      
                'secondary': (0.7, 0.2, 0.6),    
                'tertiary': (1.0, 0.5, 0.6),     
                'accent': (0.5, 0.2, 0.4),       
            },
            {
                'primary': (0.1, 0.7, 0.7),      
                'secondary': (0.2, 0.5, 0.6),    
                'tertiary': (0.3, 0.9, 0.9),     
                'accent': (0.1, 0.4, 0.5),       
            },
            {
                'primary': (1.0, 0.2, 0.5),      
                'secondary': (0.3, 0.3, 0.8),    
                'tertiary': (1.0, 0.4, 0.7),     
                'accent': (0.5, 0.2, 0.7),       
            },
            {
                'primary': (0.4, 0.6, 1.0),      
                'secondary': (0.6, 0.3, 0.8),    
                'tertiary': (0.3, 0.8, 1.0),     
                'accent': (0.7, 0.4, 0.9),       
            },
            {
                'primary': (1.0, 0.3, 0.4),      
                'secondary': (0.2, 0.3, 0.7),    
                'tertiary': (1.0, 0.6, 0.5),     
                'accent': (0.4, 0.4, 0.9),       
            },
        ]

    def _generate_nebula_name(self):
        catalogs = ['NGC', 'IC', 'M', 'Sh2-', 'LBN', 'RCW', 'Gum', 'LDN', 'B', 'vdB']
        type_names = [
            'Nebula', 'Cloud', 'Complex', 'Region', 'Cluster'
        ]
        descriptive = [
            'Eagle', 'Crab', 'Orion', 'Swan', 'Lagoon', 'Trifid', 'Rosette', 'Helix',
            'Ring', 'Owl', 'Horsehead', 'Flame', 'Cone', 'Pelican', 'Veil', 'Carina',
            'Tarantula', 'Butterfly', 'Cat\'s Eye', 'Bubble', 'Elephant Trunk',
            'Witch Head', 'Wizard', 'Heart', 'Soul', 'Jellyfish', 'Medusa',
            'Ghost', 'Skull', 'Spider', 'Ant', 'Stingray', 'Boomerang',
            'Red Spider', 'Blue Snowball', 'Little Ghost', 'Crescent',
            'Flaming Star', 'Running Chicken', 'Prawn', 'Gabriela Mistral',
            'Thor\'s Helmet', 'Seagull', 'Pacman', 'Christmas Tree',
            'Cocoon', 'Cave', 'Iris', 'Tulip', 'Sunflower', 'Pinwheel'
        ]
        greek = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta',
                 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Omicron', 'Pi', 'Rho',
                 'Sigma', 'Tau', 'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega']
        constellations = [
            'Orionis', 'Cygni', 'Sagittarii', 'Scorpii', 'Carinae', 'Centauri',
            'Monocerotis', 'Serpentis', 'Ophiuchi', 'Aquilae', 'Lyrae', 'Cassiopeiae',
            'Persei', 'Aurigae', 'Cephei', 'Draconis', 'Ursae', 'Velorum'
        ]
        style = random.choice(['catalog', 'catalog', 'descriptive', 'descriptive', 'greek', 'messier'])
        if style == 'catalog':
            catalog = random.choice(catalogs)
            if catalog in ['M']:
                number = random.randint(1, 110)
            elif catalog in ['NGC']:
                number = random.randint(100, 7840)
            elif catalog in ['IC']:
                number = random.randint(1, 5386)
            elif catalog in ['Sh2-']:
                number = random.randint(1, 313)
            else:
                number = random.randint(1, 999)
            return f"{catalog}{number}"
        elif style == 'descriptive':
            name = random.choice(descriptive)
            nebula_type = random.choice(type_names)
            return f"{name} {nebula_type}"
        elif style == 'greek':
            letter = random.choice(greek)
            const = random.choice(constellations)
            nebula_type = random.choice(type_names)
            return f"{letter} {const} {nebula_type}"

        else:
            return f"M{random.randint(1, 110)}"

    def _create_blob_texture(self):
        size = 128
        texture_data = []
        center = size / 2

        for y in range(size):
            for x in range(size):
                dx = x - center
                dy = y - center
                distance = math.sqrt(dx * dx + dy * dy) / center

                if distance <= 1.0:
                    alpha = (1.0 - distance) ** 1.5
                    noise = random.uniform(0.95, 1.05)
                    alpha = alpha * noise
                else:
                    alpha = 0.0

                alpha = max(0.0, min(1.0, alpha))
                texture_data.extend([255, 255, 255, int(alpha * 255)])

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))

        return texture_id

    def _create_wisp_texture(self):
        width = 256
        height = 64
        texture_data = []

        for y in range(height):
            for x in range(width):
                norm_x = x / width
                norm_y = (y - height / 2) / (height / 2)
                wave = math.sin(norm_x * math.pi * 4) * 0.3
                edge_dist = abs(norm_y) - wave
                if edge_dist < 0.7:
                    alpha = (0.7 - edge_dist) / 0.7

                    end_fade = math.sin(norm_x * math.pi) ** 0.5
                    alpha *= end_fade
                    alpha = alpha ** 1.2
                else:
                    alpha = 0.0

                alpha = max(0.0, min(1.0, alpha))
                texture_data.extend([255, 255, 255, int(alpha * 255)])

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))

        return texture_id

    def _create_filament_texture(self):
        width = 128
        height = 32
        texture_data = []
        
        for y in range(height):
            for x in range(width):
                norm_x = x / width
                norm_y = (y - height / 2) / (height / 2)
                dist = abs(norm_y)
                core = max(0, 1.0 - dist * 4) ** 1.5
                glow = max(0, 1.0 - dist * 1.5) ** 2
                haze = max(0, 1.0 - dist) ** 3
                alpha = core * 0.8 + glow * 0.5 + haze * 0.2
                end_fade = math.sin(norm_x * math.pi) ** 0.3
                alpha *= end_fade
                variation = 0.8 + 0.2 * math.sin(norm_x * math.pi * 8)
                alpha *= variation
                
                alpha = max(0.0, min(1.0, alpha))
                texture_data.extend([255, 255, 255, int(alpha * 255)])
        
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))
        
        return texture_id

    def _create_detail_noise_texture(self):
        size = 256
        texture_data = []

        for y in range(size):
            for x in range(size):
                value = 0
                amplitude = 1.0
                frequency = 1.0
                
                for octave in range(5):
                    nx = x * frequency / size
                    ny = y * frequency / size
                    noise = math.sin(nx * 12.9898 + ny * 78.233) * 43758.5453
                    noise = noise - math.floor(noise)
                    value += noise * amplitude
                    amplitude *= 0.5
                    frequency *= 2.0
                
                value = value / 2.0
                value = max(0.0, min(1.0, value))
                
                texture_data.extend([255, 255, 255, int(value * 255)])
        
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))
        
        return texture_id

    def _create_star_texture(self):
        size = 64
        texture_data = []
        center = size / 2
        
        for y in range(size):
            for x in range(size):
                dx = x - center
                dy = y - center
                distance = math.sqrt(dx * dx + dy * dy) / center
                if distance <= 1.0:
                    core = max(0, 1.0 - distance * 3) ** 2
                    glow = (1.0 - distance) ** 3
                    alpha = core + glow * 0.5
                else:
                    alpha = 0.0

                alpha = max(0.0, min(1.0, alpha))
                texture_data.extend([255, 255, 255, int(alpha * 255)])
        
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))
        
        return texture_id

    def _generate_stars(self):
        self.stars = []
        self.bright_stars = []
        
        for _ in range(3000):
            x = random.uniform(-40, 40)
            y = random.uniform(-30, 30)
            z = random.uniform(-50, -30)
            
            rand = random.random()
            if rand < 0.75:
                brightness = random.uniform(0.1, 0.3)
                size = random.uniform(0.5, 1.0)
            elif rand < 0.92:
                brightness = random.uniform(0.3, 0.6)
                size = random.uniform(1.0, 1.5)
            else:
                brightness = random.uniform(0.6, 1.0)
                size = random.uniform(1.5, 2.5)
            
            star_type = random.random()
            if star_type < 0.70:
                # White stars
                color = (brightness, brightness, brightness)
            elif star_type < 0.82:
                # Blue-white stars
                color = (brightness * 0.8, brightness * 0.9, brightness)
            elif star_type < 0.90:
                # Yellow stars
                color = (brightness, brightness * 0.95, brightness * 0.7)
            elif star_type < 0.96:
                # Orange stars
                color = (brightness, brightness * 0.7, brightness * 0.4)
            else:
                # Red stars
                color = (brightness, brightness * 0.5, brightness * 0.4)
            star = {
                'pos': [x, y, z],
                'color': color,
                'size': size,
                'brightness': brightness,
                'twinkle_phase': random.uniform(0, 2 * math.pi),
                'twinkle_speed': random.uniform(0.5, 2.0),
            }
            
            self.stars.append(star)
            
            if brightness > 0.6 and size > 1.5 and len(self.bright_stars) < 25:
                self.bright_stars.append(star)

        for _ in range(random.randint(8, 15)):
            x = random.uniform(-35, 35)
            y = random.uniform(-25, 25)
            z = random.uniform(-45, -32)
            
            brightness = random.uniform(0.85, 1.0)
            size = random.uniform(2.5, 4.0)

            if random.random() < 0.7:
                color = (brightness, brightness, brightness)
            else:
                color = (brightness * 0.85, brightness * 0.92, brightness)
            
            star = {
                'pos': [x, y, z],
                'color': color,
                'size': size,
                'brightness': brightness,
                'twinkle_phase': random.uniform(0, 2 * math.pi),
                'twinkle_speed': random.uniform(0.3, 1.0),
                'spike_length': random.uniform(3.0, 6.0),
            }
            
            self.stars.append(star)
            self.bright_stars.append(star)

    def _generate_nebula_structure(self):
        self.nebula_clouds = []

        num_palettes = random.randint(1, 2)
        chosen_palettes = random.sample(self.nebula_palettes, num_palettes)

        position_type = random.choice([
            'center', 'center', 
            'top_left', 'top_right', 'bottom_left', 'bottom_right',
            'left', 'right', 'top', 'bottom',
            'upper_half', 'lower_half', 'left_half', 'right_half',
            'diagonal_tl_br', 'diagonal_bl_tr',
            'scattered_wide', 'corner_cluster'
        ])
        
        scale_type = random.choice([
            'full', 'full',
            'large', 'large', 
            'medium', 'medium', 'medium',
            'small', 'compact'
        ])
        
        self.nebula_offset, self.nebula_scale = self._get_position_params(position_type, scale_type)
        layout = random.choice(['centered', 'diagonal', 'dual_lobe', 'scattered', 'spiral', 'filamentary'])
        
        if layout == 'centered':
            self._generate_centered_nebula(chosen_palettes)
        elif layout == 'diagonal':
            self._generate_diagonal_nebula(chosen_palettes)
        elif layout == 'dual_lobe':
            self._generate_dual_lobe_nebula(chosen_palettes)
        elif layout == 'spiral':
            self._generate_spiral_nebula(chosen_palettes)
        elif layout == 'filamentary':
            self._generate_filamentary_nebula(chosen_palettes)
        else:
            self._generate_scattered_nebula(chosen_palettes)
        
        self._generate_filaments(chosen_palettes)
        self._generate_dark_foreground_clouds(chosen_palettes)
        self._generate_fine_details(chosen_palettes)
        self._generate_dust_lanes()
    
    def _get_position_params(self, position_type, scale_type):
        scale_factors = {
            'full': 1.8,
            'large': 1.5,
            'medium': 1.2,
            'small': 0.9,
            'compact': 0.7
        }
        scale = scale_factors.get(scale_type, 1.2)

        position_offsets = {
            'center': (0, 0),
            'top_left': (-6, 4),
            'top_right': (6, 4),
            'bottom_left': (-6, -4),
            'bottom_right': (6, -4),
            'left': (-7, random.uniform(-2, 2)),
            'right': (7, random.uniform(-2, 2)),
            'top': (random.uniform(-3, 3), 5),
            'bottom': (random.uniform(-3, 3), -5),
            'upper_half': (random.uniform(-4, 4), 3),
            'lower_half': (random.uniform(-4, 4), -3),
            'left_half': (-4, random.uniform(-2, 2)),
            'right_half': (4, random.uniform(-2, 2)),
            'diagonal_tl_br': (random.uniform(-3, 3), random.uniform(-2, 2)),
            'diagonal_bl_tr': (random.uniform(-3, 3), random.uniform(-2, 2)),
            'scattered_wide': (random.uniform(-5, 5), random.uniform(-3, 3)),
            'corner_cluster': random.choice([(-7, 4), (7, 4), (-7, -4), (7, -4)]),
        }
        
        offset = position_offsets.get(position_type, (0, 0))
        offset = (offset[0] + random.uniform(-1, 1), offset[1] + random.uniform(-0.5, 0.5))
        
        return offset, scale

    def _generate_centered_nebula(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale
        
        center_x = ox + random.uniform(-3, 3) * scale
        center_y = oy + random.uniform(-2, 2) * scale
        center_z = -38
        
        for i in range(random.randint(20, 35)):
            offset_x = random.gauss(0, 12 * scale)
            offset_y = random.gauss(0, 9 * scale)
            
            color_choice = random.choice(['primary', 'secondary', 'tertiary', 'accent'])
            base_color = palette[color_choice]
            
            self._add_cloud(
                center_x + offset_x,
                center_y + offset_y,
                center_z + random.uniform(-3, 3),
                base_color,
                size=random.uniform(12, 28) * scale,
                alpha=random.uniform(0.02, 0.06)
            )
        
        for i in range(random.randint(25, 45)):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(10, 28) * scale
            
            x = center_x + math.cos(angle) * distance
            y = center_y + math.sin(angle) * distance * 0.7
            
            color_choice = random.choice(['primary', 'secondary', 'tertiary'])
            base_color = palette[color_choice]
            
            self._add_cloud(
                x, y, center_z + random.uniform(-2, 2),
                base_color,
                size=random.uniform(8, 18) * scale,
                alpha=random.uniform(0.015, 0.04) 
            )

    def _generate_diagonal_nebula(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale
        
        diagonal_type = random.choice(['tl_br', 'bl_tr', 'l_r', 't_b'])
        
        if diagonal_type == 'tl_br':
            start_x, start_y = ox - 25 * scale, oy + 14 * scale
            end_x, end_y = ox + 25 * scale, oy - 14 * scale
        elif diagonal_type == 'bl_tr':
            start_x, start_y = ox - 25 * scale, oy - 14 * scale
            end_x, end_y = ox + 25 * scale, oy + 14 * scale
        elif diagonal_type == 'l_r':
            start_x, start_y = ox - 28 * scale, oy + random.uniform(-4, 4)
            end_x, end_y = ox + 28 * scale, oy + random.uniform(-4, 4)
        else:
            start_x, start_y = ox + random.uniform(-4, 4), oy + 16 * scale
            end_x, end_y = ox + random.uniform(-4, 4), oy - 16 * scale
        
        steps = random.randint(35, 55)
        for i in range(steps):
            t = i / steps
            x = start_x + (end_x - start_x) * t + random.gauss(0, 5 * scale)
            y = start_y + (end_y - start_y) * t + random.gauss(0, 4 * scale)
            z = -38 + random.uniform(-2, 2)
            if t < 0.5:
                color = palette['primary']
            else:
                color = palette['secondary']
            
            self._add_cloud(x, y, z, color,
                          size=random.uniform(10, 22) * scale,
                          alpha=random.uniform(0.02, 0.055)) 
        
        if len(palettes) > 1:
            palette2 = palettes[1]
            for i in range(random.randint(15, 28)):
                x = ox + random.uniform(-20, 20) * scale
                y = oy + random.uniform(-14, 14) * scale
                z = -40 + random.uniform(-2, 2)
                
                color = random.choice([palette2['primary'], palette2['tertiary']])
                self._add_cloud(x, y, z, color,
                              size=random.uniform(12, 22) * scale,
                              alpha=random.uniform(0.015, 0.04))

    def _generate_dual_lobe_nebula(self, palettes):
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        if len(palettes) > 1:
            left_palette = palettes[0]
            right_palette = palettes[1]
        else:
            left_palette = palettes[0]
            right_palette = palettes[0]
        
        separation = random.uniform(12, 20) * scale
        
        left_center = (ox - separation, oy + random.uniform(-4, 4) * scale, -38)
        for i in range(random.randint(25, 38)):
            x = left_center[0] + random.gauss(0, 9 * scale)
            y = left_center[1] + random.gauss(0, 7 * scale)
            z = left_center[2] + random.uniform(-2, 2)
            
            color = random.choice([left_palette['primary'], left_palette['secondary'], left_palette['tertiary']])
            self._add_cloud(x, y, z, color,
                          size=random.uniform(10, 22) * scale,
                          alpha=random.uniform(0.02, 0.06))

        right_center = (ox + separation, oy + random.uniform(-4, 4) * scale, -38)
        for i in range(random.randint(25, 38)):
            x = right_center[0] + random.gauss(0, 9 * scale)
            y = right_center[1] + random.gauss(0, 7 * scale)
            z = right_center[2] + random.uniform(-2, 2)
            
            color = random.choice([right_palette['primary'], right_palette['secondary'], right_palette['tertiary']])
            self._add_cloud(x, y, z, color,
                          size=random.uniform(10, 22) * scale,
                          alpha=random.uniform(0.02, 0.06))
        
        for i in range(random.randint(12, 22)):
            t = random.uniform(0.2, 0.8)
            x = left_center[0] + (right_center[0] - left_center[0]) * t
            y = (left_center[1] + right_center[1]) / 2 + random.gauss(0, 3 * scale)
            z = -38 + random.uniform(-1, 1)

            if t < 0.5:
                color = left_palette['accent']
            else:
                color = right_palette['accent']
            
            self._add_cloud(x, y, z, color,
                          size=random.uniform(8, 16) * scale,
                          alpha=random.uniform(0.015, 0.04)) 

    def _generate_scattered_nebula(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale
        
        num_patches = random.randint(5, 10)
        for _ in range(num_patches):
            patch_x = ox + random.uniform(-25, 25) * scale
            patch_y = oy + random.uniform(-18, 18) * scale
            patch_z = -38 + random.uniform(-3, 3)
            
            color = random.choice([palette['primary'], palette['secondary'], palette['tertiary']])
            
            for _ in range(random.randint(8, 18)):
                x = patch_x + random.gauss(0, 6 * scale)
                y = patch_y + random.gauss(0, 5 * scale)
                z = patch_z + random.uniform(-1, 1)
                
                self._add_cloud(x, y, z, color,
                              size=random.uniform(8, 20) * scale,
                              alpha=random.uniform(0.02, 0.05))
    def _generate_spiral_nebula(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        num_arms = random.randint(2, 4)
        arm_offset = 2 * math.pi / num_arms

        for arm in range(num_arms):
            base_angle = arm * arm_offset + random.uniform(0, 0.5)

            for i in range(random.randint(20, 35)):
                t = i / 25.0
                angle = base_angle + t * math.pi * 1.5  

                distance = (3 + t * 24) * scale

                x = ox + math.cos(angle) * distance + random.gauss(0, 3 * scale)
                y = oy + math.sin(angle) * distance * 0.6 + random.gauss(0, 2 * scale)
                z = -38 + random.uniform(-2, 2)

                color_choices = ['primary', 'secondary', 'tertiary']
                color = palette[random.choice(color_choices)]

                self._add_cloud(x, y, z, color,
                              size=random.uniform(8, 18) * scale,
                              alpha=random.uniform(0.02, 0.055))  

        for _ in range(random.randint(12, 22)):
            x = ox + random.gauss(0, 6 * scale)
            y = oy + random.gauss(0, 5 * scale)
            z = -38 + random.uniform(-1, 1)

            self._add_cloud(x, y, z, palette['accent'],
                          size=random.uniform(10, 22) * scale,
                          alpha=random.uniform(0.025, 0.06))  

    def _generate_filamentary_nebula(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        main_angle = random.uniform(0, math.pi)

        num_filaments = random.randint(6, 12)
        for f in range(num_filaments):

            perp_offset = (f - num_filaments / 2) * 4 * scale
            perp_x = math.cos(main_angle + math.pi/2) * perp_offset
            perp_y = math.sin(main_angle + math.pi/2) * perp_offset

            length = random.uniform(30, 50) * scale

            steps = random.randint(18, 30)
            for i in range(steps):
                t = (i / steps) - 0.5  

                x = ox + perp_x + math.cos(main_angle) * length * t + random.gauss(0, 2 * scale)
                y = oy + perp_y + math.sin(main_angle) * length * t * 0.6 + random.gauss(0, 1.5 * scale)
                z = -38 + random.uniform(-2, 2)

                color = random.choice([palette['primary'], palette['secondary']])

                self._add_cloud(x, y, z, color,
                              size=random.uniform(7, 16) * scale,
                              alpha=random.uniform(0.02, 0.05))  

        for _ in range(random.randint(10, 20)):
            x = ox + random.uniform(-18, 18) * scale
            y = oy + random.uniform(-12, 12) * scale
            z = -38 + random.uniform(-1, 1)

            self._add_cloud(x, y, z, palette['accent'],
                          size=random.uniform(10, 18) * scale,
                          alpha=random.uniform(0.025, 0.055))  

    def _generate_dark_foreground_clouds(self, palettes):
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        if random.random() < 0.25:
            return  

        num_blobs = random.randint(8, 20)
        for _ in range(num_blobs):
            x = ox + random.gauss(0, 20) * scale
            y = oy + random.gauss(0, 15) * scale
            z = -32 + random.uniform(-2, 2)

            size = random.uniform(4, 14) * scale

            darkness = random.choice(['dark', 'medium', 'light', 'medium'])
            if darkness == 'dark':
                alpha = random.uniform(0.5, 0.8)
            elif darkness == 'medium':
                alpha = random.uniform(0.25, 0.45)
            else:
                alpha = random.uniform(0.1, 0.25)

            self.nebula_clouds.append({
                'type': 'dark_cloud',
                'pos': [x, y, z],
                'size': size,
                'alpha': alpha,
            })

            num_edges = random.randint(3, 8)
            for _ in range(num_edges):
                edge_angle = random.uniform(0, 2 * math.pi)
                edge_dist = size * random.uniform(0.3, 1.0)
                edge_x = x + math.cos(edge_angle) * edge_dist
                edge_y = y + math.sin(edge_angle) * edge_dist * 0.7
                edge_size = size * random.uniform(0.2, 0.5)

                edge_alpha = alpha * random.uniform(0.3, 0.8)

                self.nebula_clouds.append({
                    'type': 'dark_cloud',
                    'pos': [edge_x, edge_y, z + random.uniform(-0.3, 0.3)],
                    'size': edge_size,
                    'alpha': edge_alpha,
                })

        if random.random() < 0.7:  

            num_dark_filaments = random.randint(2, 5)
            for _ in range(num_dark_filaments):
                self._create_dark_filament(ox, oy, scale)

        num_wisps = random.randint(10, 25)
        for _ in range(num_wisps):
            x = ox + random.gauss(0, 22) * scale
            y = oy + random.gauss(0, 16) * scale
            z = -31 + random.uniform(-1, 1)

            self.nebula_clouds.append({
                'type': 'dark_cloud',
                'pos': [x, y, z],
                'size': random.uniform(2, 8) * scale,
                'alpha': random.uniform(0.08, 0.22),  

            })

    def _create_dark_filament(self, ox, oy, scale):
        start_x = ox + random.gauss(0, 18) * scale
        start_y = oy + random.gauss(0, 14) * scale
        start_z = -32 + random.uniform(-1, 1)

        length = random.uniform(15, 35) * scale
        base_width = random.uniform(3, 8) * scale
        num_points = random.randint(12, 25)

        base_alpha = random.uniform(0.25, 0.6)

        main_angle = random.uniform(0, 2 * math.pi)
        curve_amount = random.uniform(-0.8, 0.8)

        x, y, z = start_x, start_y, start_z

        for i in range(num_points):
            t = i / (num_points - 1) if num_points > 1 else 0

            current_angle = main_angle + curve_amount * math.sin(t * math.pi)

            width_mult = 0.5 + 0.5 * math.sin(t * math.pi)
            width = base_width * width_mult * random.uniform(0.8, 1.2)

            opacity_variation = 0.5 + 0.5 * math.sin(t * math.pi * random.uniform(1.5, 3))
            alpha = base_alpha * opacity_variation * random.uniform(0.6, 1.2)
            alpha = min(0.75, max(0.1, alpha))  

            self.nebula_clouds.append({
                'type': 'dark_cloud',
                'pos': [x, y, z],
                'size': width,
                'alpha': alpha,
            })

            if random.random() < 0.5:
                perp_angle = current_angle + math.pi / 2
                side = random.choice([-1, 1])
                side_dist = width * random.uniform(0.4, 0.9)
                side_x = x + math.cos(perp_angle) * side_dist * side
                side_y = y + math.sin(perp_angle) * side_dist * side

                self.nebula_clouds.append({
                    'type': 'dark_cloud',
                    'pos': [side_x, side_y, z],
                    'size': width * random.uniform(0.3, 0.6),
                    'alpha': alpha * random.uniform(0.3, 0.6),  

                })

            step = length / num_points
            x += math.cos(current_angle) * step
            y += math.sin(current_angle) * step * 0.7
            z += random.uniform(-0.1, 0.1)

    def _generate_filaments(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        filament_intensity = random.random()

        if filament_intensity < 0.5:

            num_major_filaments = 0
            num_minor_filaments = 0
            num_hair_wisps = random.randint(0, 5)
        elif filament_intensity < 0.8:

            num_major_filaments = random.randint(1, 3)
            num_minor_filaments = random.randint(1, 4)
            num_hair_wisps = random.randint(3, 10)
        else:

            num_major_filaments = random.randint(2, 5)
            num_minor_filaments = random.randint(3, 8)
            num_hair_wisps = random.randint(8, 18)

        for _ in range(num_major_filaments):
            self._create_organic_filament(palette, ox, oy, scale, is_major=True)

        for _ in range(num_minor_filaments):
            self._create_organic_filament(palette, ox, oy, scale, is_major=False)

        for _ in range(num_hair_wisps):
            self._create_hair_wisp(palette, ox, oy, scale)

    def _create_organic_filament(self, palette, ox, oy, scale, is_major=True):

        start_x = ox + random.gauss(0, 14) * scale
        start_y = oy + random.gauss(0, 10) * scale
        start_z = -38 + random.uniform(-3, 3)

        if is_major:
            length = random.uniform(18, 40) * scale
            base_width = random.uniform(2.5, 5.5) * scale  
            num_points = random.randint(45, 75)  
            alpha = random.uniform(0.06, 0.14)  

        else:
            length = random.uniform(8, 22) * scale
            base_width = random.uniform(1.5, 3.5) * scale  
            num_points = random.randint(30, 50)  
            alpha = random.uniform(0.04, 0.1)  

        main_angle = random.uniform(0, 2 * math.pi)
        raw_points = []
        widths = []
        turbulence_scale = random.uniform(0.25, 0.6)  
        turbulence_freq = random.uniform(1.0, 2.5)  
        drift_amount = random.uniform(0.15, 0.35)  
        x, y, z = start_x, start_y, start_z
        angle = main_angle


        for i in range(num_points):
            t = i / (num_points - 1) if num_points > 1 else 0

            angle_wobble = math.sin(t * turbulence_freq * math.pi) * turbulence_scale
            angle_wobble += math.sin(t * turbulence_freq * 2.3 * math.pi) * turbulence_scale * 0.3
            current_angle = angle + angle_wobble

            step = length / num_points
            x += math.cos(current_angle) * step
            y += math.sin(current_angle) * step * 0.7  

            z += random.uniform(-0.05, 0.05)  

            perp_angle = current_angle + math.pi / 2
            perp_displacement = math.sin(t * turbulence_freq * 1.7 * math.pi) * scale * 0.5

            px = x + math.cos(perp_angle) * perp_displacement
            py = y + math.sin(perp_angle) * perp_displacement

            raw_points.append((px, py, z))

            width_variation = math.sin(t * math.pi) ** 0.4 if t > 0 else 0.3

            bulge = 1.0 + 0.25 * math.sin(t * random.uniform(2, 5) * math.pi)
            widths.append(base_width * max(0.35, width_variation) * bulge)

        points = self._smooth_points(raw_points, 5)

        if random.random() < 0.3:
            core_color = (1.0, 0.95, 1.0)  

        else:
            core_color = palette['tertiary']
        glow_color = random.choice([palette['primary'], palette['secondary']])

        self.nebula_clouds.append({
            'type': 'organic_filament',
            'points': points,
            'widths': widths,
            'core_color': core_color,
            'glow_color': glow_color,
            'alpha': alpha,
            'is_major': is_major
        })

    def _smooth_points(self, points, iterations=2):
        if len(points) < 3:
            return points

        smoothed = list(points)

        for _ in range(iterations):
            new_smoothed = [smoothed[0]]  

            for i in range(1, len(smoothed) - 1):

                px = (smoothed[i-1][0] + smoothed[i][0] * 2 + smoothed[i+1][0]) / 4
                py = (smoothed[i-1][1] + smoothed[i][1] * 2 + smoothed[i+1][1]) / 4
                pz = (smoothed[i-1][2] + smoothed[i][2] * 2 + smoothed[i+1][2]) / 4
                new_smoothed.append((px, py, pz))

            new_smoothed.append(smoothed[-1])  

            smoothed = new_smoothed

        return smoothed

    def _create_hair_wisp(self, palette, ox, oy, scale):
        x = ox + random.gauss(0, 20) * scale
        y = oy + random.gauss(0, 14) * scale
        z = -37 + random.uniform(-4, 4)

        length = random.uniform(3, 10) * scale
        num_points = random.randint(15, 25)  

        angle = random.uniform(0, 2 * math.pi)

        raw_points = []
        curve = random.uniform(-0.8, 0.8)

        for i in range(num_points):
            t = i / (num_points - 1) if num_points > 1 else 0

            current_angle = angle + curve * math.sin(t * math.pi)

            px = x + math.cos(current_angle) * length * t
            py = y + math.sin(current_angle) * length * t * 0.7
            pz = z + random.uniform(-0.02, 0.02)  

            raw_points.append((px, py, pz))

        points = self._smooth_points(raw_points, 2)

        color = random.choice([palette['primary'], palette['secondary'], palette['accent']])

        self.nebula_clouds.append({
            'type': 'hair_wisp',
            'points': points,
            'color': color,
            'width': random.uniform(0.4, 1.0) * scale,  

            'alpha': random.uniform(0.02, 0.07),  

        })

    def _generate_fine_details(self, palettes):
        palette = palettes[0]
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        detail_intensity = random.random()

        if detail_intensity < 0.3:

            num_fine_wisps = random.randint(3, 10)
            num_knots = random.randint(10, 25)
        elif detail_intensity < 0.6:

            num_fine_wisps = random.randint(8, 20)
            num_knots = random.randint(20, 40)
        else:

            num_fine_wisps = random.randint(15, 35)
            num_knots = random.randint(35, 60)

        for _ in range(num_fine_wisps):

            x = ox + random.gauss(0, 24) * scale
            y = oy + random.gauss(0, 16) * scale
            z = -37 + random.uniform(-4, 4)

            angle = random.uniform(0, 2 * math.pi)
            length = random.uniform(2, 8) * scale

            num_points = random.randint(10, 18)
            raw_points = []

            curve_amount = random.uniform(-0.6, 0.6)

            for i in range(num_points):
                t = i / (num_points - 1) if num_points > 1 else 0

                curve = math.sin(t * math.pi) * curve_amount * length
                perp_angle = angle + math.pi / 2

                px = x + math.cos(angle) * length * t + math.cos(perp_angle) * curve
                py = y + math.sin(angle) * length * t * 0.7 + math.sin(perp_angle) * curve
                pz = z + random.uniform(-0.05, 0.05)  

                raw_points.append((px, py, pz))

            points = self._smooth_points(raw_points, 2)

            if random.random() < 0.7:
                color = random.choice([palette['primary'], palette['secondary'], palette['tertiary']])
            else:

                color = (0.9, 0.8, 0.9)

            self.nebula_clouds.append({
                'type': 'fine_wisp',
                'points': points,
                'color': color,
                'width': random.uniform(0.4, 1.0) * scale,  

                'alpha': random.uniform(0.02, 0.08),  

            })

        for _ in range(num_knots):
            x = ox + random.gauss(0, 22) * scale
            y = oy + random.gauss(0, 16) * scale
            z = -37 + random.uniform(-2, 2)

            rand = random.random()
            if rand < 0.15:
                color = (1.0, 0.95, 0.98)  

            elif rand < 0.4:
                color = palette['tertiary']
            else:
                color = random.choice([palette['primary'], palette['secondary']])

            self.nebula_clouds.append({
                'type': 'knot',
                'pos': [x, y, z],
                'color': color,
                'size': random.uniform(1.0, 4.0) * scale,  

                'alpha': random.uniform(0.03, 0.1),
            })

    def _generate_dust_lanes(self):
        ox, oy = self.nebula_offset
        scale = self.nebula_scale

        num_lanes = random.randint(6, 14)

        for _ in range(num_lanes):
            x = ox + random.gauss(0, 18) * scale
            y = oy + random.gauss(0, 14) * scale
            z = -36 + random.uniform(-2, 2)

            self.nebula_clouds.append({
                'type': 'dust',
                'pos': [x, y, z],
                'size': random.uniform(10, 25) * scale,
                'alpha': random.uniform(0.02, 0.06),
                'color': (0.02, 0.02, 0.03),
            })

        num_patches = random.randint(15, 35)
        for _ in range(num_patches):
            x = ox + random.gauss(0, 22) * scale
            y = oy + random.gauss(0, 16) * scale
            z = -35 + random.uniform(-1, 1)
            
            self.nebula_clouds.append({
                'type': 'dust',
                'pos': [x, y, z],
                'size': random.uniform(3, 10) * scale,
                'alpha': random.uniform(0.015, 0.04),
                'color': (0.01, 0.01, 0.02),
            })

    def _add_cloud(self, x, y, z, color, size, alpha):
        self.nebula_clouds.append({
            'type': 'cloud',
            'pos': [x, y, z],
            'color': color,
            'size': size,
            'alpha': alpha,
            'phase': random.uniform(0, 2 * math.pi),
            'pulse_speed': random.uniform(0.1, 0.3),
        })

    def _generate_dust_particles(self):
        self.dust_particles = []

        for _ in range(150):
            self.dust_particles.append({
                'pos': [
                    random.uniform(-40, 40),
                    random.uniform(-30, 30),
                    random.uniform(-48, -28)
                ],
                'size': random.uniform(0.3, 1.0),
                'alpha': random.uniform(0.05, 0.15),
                'drift_x': random.uniform(-0.003, 0.003),
                'drift_y': random.uniform(-0.002, 0.002),
            })

    def initialize(self):
        if self.initialized:
            return
        
        self.blob_texture = self._create_blob_texture()
        self.wisp_texture = self._create_wisp_texture()
        self.star_texture = self._create_star_texture()
        self.filament_texture = self._create_filament_texture()
        self.noise_texture = self._create_detail_noise_texture()
        
        self._generate_stars()
        self._generate_nebula_structure()
        self._generate_dust_particles()
        self._compile_background_list()
        
        self.current_name = self.nebula_name
        self.current_texture = self._render_to_texture()
        
        for _ in range(self.cache_size - 1):
            self._generate_and_cache_nebula()
        
        self.initialized = True
    
    def _create_render_texture(self):
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.width, self.height, 0,
                     GL_RGB, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return texture
    
    def _render_to_texture(self):
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect_ratio = self.width / max(1, self.height)
        gluPerspective(45, aspect_ratio, 0.1, 100.0)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        glClearColor(0.005, 0.005, 0.015, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        if self.background_display_list:
            glCallList(self.background_display_list)
        
        texture = self._create_render_texture()
        glBindTexture(GL_TEXTURE_2D, texture)
        glCopyTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, 0, 0, self.width, self.height, 0)
        
        return texture
    
    def _generate_and_cache_nebula(self):
        self.stars = []
        self.bright_stars = []
        self.nebula_clouds = []
        self.dust_particles = []
        
        new_name = self._generate_nebula_name()
        self.nebula_name = new_name
        
        self._generate_stars()
        self._generate_nebula_structure()
        self._generate_dust_particles()
        
        if self.background_display_list:
            glDeleteLists(self.background_display_list, 1)
        self._compile_background_list()
        
        texture = self._render_to_texture()
        
        self.nebula_cache.append((texture, new_name))
    
    def _get_next_cached_nebula(self):
        if not self.nebula_cache:
            self._generate_and_cache_nebula()
        
        texture, name = self.nebula_cache.pop(0)

        self._generate_and_cache_nebula()
        
        return texture, name

    def _compile_background_list(self):
        self.background_display_list = glGenLists(1)
        glNewList(self.background_display_list, GL_COMPILE)
        
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -20)
        
        modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        right = [modelview[0][0], modelview[1][0], modelview[2][0]]
        up = [modelview[0][1], modelview[1][1], modelview[2][1]]
        
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.blob_texture)
        
        for cloud in self.nebula_clouds:
            if cloud['type'] == 'dust':
                px, py, pz = cloud['pos']
                radius = cloud['size']
                r, g, b = cloud['color']
                alpha = cloud['alpha']
                
                glColor4f(r, g, b, alpha)
                self._draw_billboard_quad(px, py, pz, radius, right, up)
        
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        
        sorted_clouds = sorted(
            [c for c in self.nebula_clouds if c['type'] == 'cloud'],
            key=lambda c: c['pos'][2]
        )
        
        for cloud in sorted_clouds:
            px, py, pz = cloud['pos']
            radius = cloud['size']
            r, g, b = cloud['color']
            alpha = cloud['alpha']

            for layer_mult, layer_alpha in [(1.0, 0.7), (1.5, 0.35), (2.0, 0.15)]:
                glColor4f(r, g, b, alpha * layer_alpha)
                self._draw_billboard_quad(px, py, pz, radius * layer_mult, right, up)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glBindTexture(GL_TEXTURE_2D, self.wisp_texture)
        for cloud in self.nebula_clouds:
            if cloud['type'] == 'filament':
                self._draw_filament(cloud, right, up)

        self._draw_detailed_filaments(right, up)

        self._draw_fine_wisps(right, up)

        glBindTexture(GL_TEXTURE_2D, self.blob_texture)
        for cloud in self.nebula_clouds:
            if cloud['type'] == 'knot':
                px, py, pz = cloud['pos']
                r, g, b = cloud['color']
                alpha = cloud['alpha']
                size = cloud['size']

                for mult, a in [(3.0, 0.15), (2.0, 0.25), (1.0, 0.5)]:
                    glColor4f(r, g, b, alpha * a)
                    self._draw_billboard_quad(px, py, pz, size * mult, right, up)

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)

        for star in self.stars:
            if star.get('spike_length') is None:  # Regular stars only
                glPointSize(star['size'])
                glColor3f(*star['color'])
                glBegin(GL_POINTS)
                glVertex3f(*star['pos'])
                glEnd()

        glDisable(GL_POINT_SMOOTH)

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.star_texture)

        for star in self.bright_stars:
            px, py, pz = star['pos']
            r, g, b = star['color']

            for size_mult, alpha in [(1.5, 0.8), (3.0, 0.4), (5.0, 0.15)]:
                radius = star['size'] * size_mult * 0.1
                glColor4f(r, g, b, alpha)
                self._draw_billboard_quad(px, py, pz, radius, right, up)

        glDisable(GL_TEXTURE_2D)

        for star in self.bright_stars:
            if star.get('spike_length'):
                self._draw_static_diffraction_spikes(star)

        glEnable(GL_POINT_SMOOTH)
        glPointSize(0.7)
        glColor4f(0.8, 0.8, 0.9, 0.1)
        glBegin(GL_POINTS)
        for particle in self.dust_particles:
            glVertex3f(*particle['pos'])
        glEnd()
        glDisable(GL_POINT_SMOOTH)

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.blob_texture)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        sorted_dark = sorted(
            [c for c in self.nebula_clouds if c['type'] == 'dark_cloud'],
            key=lambda c: c['pos'][2],
            reverse=True  

        )

        for cloud in sorted_dark:
            px, py, pz = cloud['pos']
            size = cloud['size']
            alpha = cloud['alpha']

            glColor4f(0.0, 0.0, 0.0, alpha * 0.9)
            self._draw_billboard_quad(px, py, pz, size * 0.6, right, up)

            glColor4f(0.01, 0.01, 0.02, alpha * 0.7)
            self._draw_billboard_quad(px, py, pz, size * 0.85, right, up)

            glColor4f(0.02, 0.02, 0.03, alpha * 0.35)
            self._draw_billboard_quad(px, py, pz, size * 1.2, right, up)

        glDisable(GL_TEXTURE_2D)
        glEndList()

    def _draw_static_diffraction_spikes(self, star):
        px, py, pz = star['pos']
        r, g, b = star['color']
        spike_length = star.get('spike_length', 3.0)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        spike_width = 0.08

        glBegin(GL_TRIANGLES)

        for angle_offset in [0, 90, 180, 270]:
            angle = math.radians(angle_offset)

            tip_x = px + math.cos(angle) * spike_length
            tip_y = py + math.sin(angle) * spike_length

            perp_angle = angle + math.pi / 2
            base1_x = px + math.cos(perp_angle) * spike_width
            base1_y = py + math.sin(perp_angle) * spike_width
            base2_x = px - math.cos(perp_angle) * spike_width
            base2_y = py - math.sin(perp_angle) * spike_width

            glColor4f(r, g, b, 0.6)
            glVertex3f(px, py, pz)
            glColor4f(r, g, b, 0.0)
            glVertex3f(tip_x, tip_y, pz)
            glColor4f(r, g, b, 0.3)
            glVertex3f(base1_x, base1_y, pz)

            glColor4f(r, g, b, 0.6)
            glVertex3f(px, py, pz)
            glColor4f(r, g, b, 0.3)
            glVertex3f(base2_x, base2_y, pz)
            glColor4f(r, g, b, 0.0)
            glVertex3f(tip_x, tip_y, pz)

        glEnd()

    def _draw_fine_wisps(self, right, up):
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.filament_texture)

        for cloud in self.nebula_clouds:
            if cloud['type'] == 'fine_wisp':
                points = cloud['points']
                color = cloud['color']
                width = cloud['width']
                alpha = cloud['alpha']

                if len(points) < 2:
                    continue

                r, g, b = color

                glColor4f(r, g, b, alpha * 0.35)
                self._draw_filament_strip(points, width * 1.8)

                glColor4f(min(1.0, r * 1.1), min(1.0, g * 1.1), min(1.0, b * 1.1), alpha * 0.7)
                self._draw_filament_strip(points, width)

        for cloud in self.nebula_clouds:
            if cloud['type'] == 'hair_wisp':
                points = cloud['points']
                color = cloud['color']
                width = cloud['width']
                alpha = cloud['alpha']

                if len(points) < 2:
                    continue

                r, g, b = color

                glColor4f(r, g, b, alpha * 0.3)
                self._draw_filament_strip(points, width * 1.4)

                glColor4f(r, g, b, alpha * 0.7)
                self._draw_filament_strip(points, width)

    def _draw_detailed_filaments(self, right, up):
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.filament_texture)

        for cloud in self.nebula_clouds:
            if cloud['type'] == 'organic_filament':
                points = cloud['points']
                widths = cloud['widths']
                core_color = cloud['core_color']
                glow_color = cloud['glow_color']
                alpha = cloud['alpha']

                if len(points) < 2:
                    continue

                for glow_mult, glow_alpha in [(5.0, 0.06), (3.5, 0.1), (2.0, 0.16)]:
                    r, g, b = glow_color
                    glColor4f(r, g, b, alpha * glow_alpha)
                    self._draw_filament_strip_variable(points, widths, glow_mult)

                r, g, b = glow_color
                glColor4f(r, g, b, alpha * 0.35)
                self._draw_filament_strip_variable(points, widths, 1.2)

                r, g, b = core_color
                glColor4f(r, g, b, alpha * 0.5)
                self._draw_filament_strip_variable(points, widths, 0.6)

                glColor4f(1.0, 1.0, 1.0, alpha * 0.25)
                self._draw_filament_strip_variable(points, widths, 0.2)

    def _draw_filament_strip_variable(self, points, widths, width_mult):
        if len(points) < 2:
            return

        perpendiculars = []
        for i in range(len(points)):
            dx, dy = 0, 0
            count = 0

            for j in range(max(0, i-2), i):
                dx += points[i][0] - points[j][0]
                dy += points[i][1] - points[j][1]
                count += 1

            for j in range(i+1, min(len(points), i+3)):
                dx += points[j][0] - points[i][0]
                dy += points[j][1] - points[i][1]
                count += 1

            if count > 0:
                dx /= count
                dy /= count

            length = math.sqrt(dx*dx + dy*dy)
            if length > 0.001:
                perpendiculars.append((-dy / length, dx / length))
            else:
                perpendiculars.append((1, 0))

        smoothed_perps = []
        for i in range(len(perpendiculars)):
            px, py = 0, 0
            total_weight = 0
            for j in range(max(0, i-3), min(len(perpendiculars), i+4)):
                weight = 1.0 / (1 + abs(j - i))
                px += perpendiculars[j][0] * weight
                py += perpendiculars[j][1] * weight
                total_weight += weight
            px /= total_weight
            py /= total_weight
            length = math.sqrt(px*px + py*py)
            if length > 0.001:
                smoothed_perps.append((px / length, py / length))
            else:
                smoothed_perps.append(perpendiculars[i])

        smoothed_widths = []
        for i in range(len(widths)):
            total = 0
            count = 0
            for j in range(max(0, i-2), min(len(widths), i+3)):
                total += widths[j]
                count += 1
            smoothed_widths.append(total / count)

        glBegin(GL_QUAD_STRIP)

        for i, (x, y, z) in enumerate(points):
            w = smoothed_widths[i] if i < len(smoothed_widths) else smoothed_widths[-1]
            w *= width_mult

            perp_x, perp_y = smoothed_perps[i]
            tex_t = i / max(1, len(points) - 1)

            glTexCoord2f(tex_t, 0)
            glVertex3f(x - perp_x * w, y - perp_y * w, z)
            glTexCoord2f(tex_t, 1)
            glVertex3f(x + perp_x * w, y + perp_y * w, z)

        glEnd()

    def _draw_filament_strip(self, points, width):
        if len(points) < 2:
            return


        perpendiculars = []
        for i in range(len(points)):
            dx, dy = 0, 0
            count = 0

            for j in range(max(0, i-2), i):
                dx += points[i][0] - points[j][0]
                dy += points[i][1] - points[j][1]
                count += 1

            for j in range(i+1, min(len(points), i+3)):
                dx += points[j][0] - points[i][0]
                dy += points[j][1] - points[i][1]
                count += 1
            
            if count > 0:
                dx /= count
                dy /= count

            length = math.sqrt(dx*dx + dy*dy)
            if length > 0.001:
                perpendiculars.append((-dy / length, dx / length))
            else:
                perpendiculars.append((1, 0))
        
        smoothed_perps = []
        for i in range(len(perpendiculars)):
            px, py = 0, 0
            total_weight = 0
            for j in range(max(0, i-3), min(len(perpendiculars), i+4)):
                weight = 1.0 / (1 + abs(j - i))
                px += perpendiculars[j][0] * weight
                py += perpendiculars[j][1] * weight
                total_weight += weight
            px /= total_weight
            py /= total_weight
            length = math.sqrt(px*px + py*py)
            if length > 0.001:
                smoothed_perps.append((px / length, py / length))
            else:
                smoothed_perps.append(perpendiculars[i])
        
        glBegin(GL_QUAD_STRIP)
        
        for i, (x, y, z) in enumerate(points):
            perp_x, perp_y = smoothed_perps[i]
            t = i / max(1, len(points) - 1)
            width_mult = math.sin(t * math.pi) * 0.5 + 0.5
            w = width * width_mult
            
            glTexCoord2f(t, 0)
            glVertex3f(x - perp_x * w, y - perp_y * w, z)
            glTexCoord2f(t, 1)
            glVertex3f(x + perp_x * w, y + perp_y * w, z)
        
        glEnd()


    def _draw_billboard_quad(self, px, py, pz, radius, right, up):
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex3f(px - right[0]*radius - up[0]*radius,
                   py - right[1]*radius - up[1]*radius,
                   pz - right[2]*radius - up[2]*radius)
        glTexCoord2f(1, 0)
        glVertex3f(px + right[0]*radius - up[0]*radius,
                   py + right[1]*radius - up[1]*radius,
                   pz + right[2]*radius - up[2]*radius)
        glTexCoord2f(1, 1)
        glVertex3f(px + right[0]*radius + up[0]*radius,
                   py + right[1]*radius + up[1]*radius,
                   pz + right[2]*radius + up[2]*radius)
        glTexCoord2f(0, 1)
        glVertex3f(px - right[0]*radius + up[0]*radius,
                   py - right[1]*radius + up[1]*radius,
                   pz + right[2]*radius + up[2]*radius)
        glEnd()

    def _draw_filament(self, filament, right, up):
        px, py, pz = filament['pos']
        angle = filament['angle']
        length = filament['length']
        width = filament['width']
        r, g, b = filament['color']
        alpha = filament['alpha']
        dx = math.cos(angle) * length
        dy = math.sin(angle) * length
        glColor4f(r, g, b, alpha)
        perp_x = -math.sin(angle) * width
        perp_y = math.cos(angle) * width
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex3f(px - perp_x, py - perp_y, pz)
        glTexCoord2f(1, 0)
        glVertex3f(px + dx - perp_x, py + dy - perp_y, pz)
        glTexCoord2f(1, 1)
        glVertex3f(px + dx + perp_x, py + dy + perp_y, pz)
        glTexCoord2f(0, 1)
        glVertex3f(px + perp_x, py + perp_y, pz)
        glEnd()

    def reset(self):
        if self.initialized and not self.transitioning:
            self.time_since_last_transition = self.display_duration
            self._start_transition()

    def update(self, delta_time=0.016):
        self.time += delta_time
        self.time_since_last_transition += delta_time
        
        if not self.transitioning and self.time_since_last_transition >= self.display_duration:
            self._start_transition()
        
        if self.transitioning:
            self.transition_progress += delta_time / self.transition_duration
            if self.transition_progress >= 1.0:
                self._finish_transition()
    
    def _start_transition(self):
        self.next_texture, self.next_name = self._get_next_cached_nebula()
        self.transitioning = True
        self.transition_progress = 0.0
    
    def _finish_transition(self):
        if self.current_texture:
            glDeleteTextures([self.current_texture])
        
        self.current_texture = self.next_texture
        self.current_name = self.next_name
        self.next_texture = None
        self.next_name = None
        
        self.transitioning = False
        self.transition_progress = 0.0
        self.time_since_last_transition = 0.0

    def render(self):
        import pygame
        
        if not self.initialized:
            self.initialize()
        
        glViewport(0, 0, self.width, self.height)
        
        glClearColor(0.005, 0.005, 0.015, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        if self.current_texture:
            if self.transitioning:
                alpha = 1.0 - self.transition_progress
            else:
                alpha = 1.0
            
            self._draw_fullscreen_texture(self.current_texture, alpha)
        
        if self.transitioning and self.next_texture:
            alpha = self.transition_progress
            self._draw_fullscreen_texture(self.next_texture, alpha)
        
        self._draw_nebula_label()
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()
        
        pygame.display.flip()
        
    
    def _draw_fullscreen_texture(self, texture, alpha):
        glBindTexture(GL_TEXTURE_2D, texture)
        glColor4f(1.0, 1.0, 1.0, alpha)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(self.width, 0)
        glTexCoord2f(1, 1); glVertex2f(self.width, self.height)
        glTexCoord2f(0, 1); glVertex2f(0, self.height)
        glEnd()
    
    def _draw_nebula_label(self):
        import pygame
        
        if self.name_font is None:
            pygame.font.init()
            try:
                self.name_font = pygame.font.SysFont('arial', 24)
            except:
                self.name_font = pygame.font.Font(None, 28)
        
        display_name = self.current_name if self.current_name else self.nebula_name
        
        if display_name:
            if self.transitioning:
                alpha = 0.85 * (1.0 - self.transition_progress)
            else:
                alpha = 0.85
            self._draw_text_label(display_name, alpha)
        
        if self.transitioning and self.next_name:
            alpha = 0.85 * self.transition_progress
            self._draw_text_label(self.next_name, alpha)
    
    def _draw_text_label(self, text, alpha):
        import pygame
        
        if alpha <= 0:
            return
        
        text_color = (200, 200, 220)
        text_surface = self.name_font.render(text, True, text_color)
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()
        
        text_data = pygame.image.tostring(text_surface, 'RGBA', True)
        
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        
        text_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, text_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_width, text_height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        
        x = (self.width - text_width) // 2
        y = 30 
        
        glColor4f(1.0, 1.0, 1.0, alpha)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + text_width, y)
        glTexCoord2f(1, 1); glVertex2f(x + text_width, y + text_height)
        glTexCoord2f(0, 1); glVertex2f(x, y + text_height)
        glEnd()
        
        glDeleteTextures([text_texture])

    def cleanup(self):
        self.stars.clear()
        self.bright_stars.clear()
        self.nebula_clouds.clear()
        self.dust_particles.clear()
        self.initialized = False
        
        if self.background_display_list:
            glDeleteLists(self.background_display_list, 1)
            self.background_display_list = None
        
        if self.current_texture:
            glDeleteTextures([self.current_texture])
            self.current_texture = None
        
        if self.next_texture:
            glDeleteTextures([self.next_texture])
            self.next_texture = None
        
        for texture, _ in self.nebula_cache:
            glDeleteTextures([texture])
        self.nebula_cache.clear()
        
        if self.blob_texture:
            glDeleteTextures([self.blob_texture])
            self.blob_texture = None
        
        if self.wisp_texture:
            glDeleteTextures([self.wisp_texture])
            self.wisp_texture = None
        
        if self.star_texture:
            glDeleteTextures([self.star_texture])
            self.star_texture = None
        
        if self.filament_texture:
            glDeleteTextures([self.filament_texture])
            self.filament_texture = None
        
        if self.noise_texture:
            glDeleteTextures([self.noise_texture])
            self.noise_texture = None
        
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)