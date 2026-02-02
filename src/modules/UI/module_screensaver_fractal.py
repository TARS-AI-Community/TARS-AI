"""
Module: Fractal Screensaver
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import random
import time
import math
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
import pygame
from UI.module_screensaver_overlay import TimeOverlay

class FractalAnimation:
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.is_portrait = height > width  # Detect portrait mode
        self.time = 0.0
        self.initialized = False
        
        # Time overlay
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None

        self.render_width = width
        self.render_height = height
        self.iterations = 128  
        self.zoom = 0.0005  

        self.view_targets = [
            (-0.7463, 0.1102, 0.001),          
            (-0.235125, 0.827215, 0.0002),     
            (-0.7269, 0.1889, 0.0008),         
            (-0.16070135, 1.0375665, 0.0003),  
            (-0.77568377, 0.13646737, 0.0005), 
            (-0.748, 0.11, 0.001),             
            (-0.7453, 0.1127, 0.0004),         
            (-0.1592, 1.0377, 0.0006),         
            (-0.743643887037151, 0.131825904205330, 0.0003), 
            (-0.761574, 0.0847596, 0.0008),    
        ]

        target = random.choice(self.view_targets)
        self.center_x, self.center_y, self.zoom = target

        self.next_center_x = self.center_x
        self.next_center_y = self.center_y
        self.next_zoom = self.zoom

        self.color_schemes = [
            'rainbow', 'fire', 'ocean', 'purple', 'galaxy', 'sunset', 'deep_blue', 'copper'
        ]
        self.current_scheme = random.choice(self.color_schemes)
        self.color_offset = random.uniform(0, 1)  

        self.pan_enabled = False  

        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.pan_speed = 0.00001

        self.texture_current = None
        self.texture_next = None
        self.iteration_data_current = None
        self.iteration_data_next = None
        self.fractal_calculated = False

        self.fade_interval = 10.0  

        self.fade_duration = 2.0  

        self.time_since_switch = 0.0
        self.fade_progress = 0.0  

        self.is_fading = False
        self.next_prepared = False

    def initialize(self):
        if self.initialized:
            return

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glPixelStorei(GL_PACK_ALIGNMENT, 1)

        empty_data = np.zeros((self.render_height, self.render_width, 3), dtype=np.uint8)

        self.texture_current = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.texture_current)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.render_width, self.render_height, 
                     0, GL_RGB, GL_UNSIGNED_BYTE, empty_data)

        self.texture_next = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.texture_next)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, self.render_width, self.render_height, 
                     0, GL_RGB, GL_UNSIGNED_BYTE, empty_data)

        self.initialized = True

    def mandelbrot_vectorized(self, height, width, min_real, max_real, min_imag, max_imag, max_iter):
        real = np.linspace(min_real, max_real, width, dtype=np.float32)
        imag = np.linspace(max_imag, min_imag, height, dtype=np.float32)
        c = real[np.newaxis, :] + 1j * imag[:, np.newaxis]

        z = np.zeros_like(c, dtype=np.complex64)
        iteration_count = np.zeros(c.shape, dtype=np.float32)  

        mask = np.ones(c.shape, dtype=bool)

        for i in range(max_iter):

            z[mask] = z[mask] * z[mask] + c[mask]

            if i % 3 == 0 or i < 10:  

                z_abs = np.abs(z)
                mask_new = z_abs <= 2.0

                newly_escaped = mask & ~mask_new
                if np.any(newly_escaped):

                    z_escaped = z_abs[newly_escaped]
                    smooth_i = i + 1 - np.log2(np.log2(z_escaped))
                    iteration_count[newly_escaped] = smooth_i

                mask = mask_new

                if not mask.any():
                    break

        iteration_count[mask] = max_iter

        return iteration_count

    def get_scheme_colors(self, t, scheme):
        if scheme == 'rainbow':
            r = (127.5 + 127.5 * np.sin(t * 18.85)).astype(np.uint8)
            g = (127.5 + 127.5 * np.sin(t * 18.85 + 2.09)).astype(np.uint8)
            b = (127.5 + 127.5 * np.sin(t * 18.85 + 4.19)).astype(np.uint8)
        elif scheme == 'fire':
            r = np.minimum(255, t * 510).astype(np.uint8)
            g = np.clip((t * 510 - 127.5), 0, 255).astype(np.uint8)
            b = np.clip((t * 510 - 255), 0, 255).astype(np.uint8)
        elif scheme == 'ocean':
            r = (t * 76.5).astype(np.uint8)
            g = (102 + t * 102).astype(np.uint8)
            b = (153 + t * 102).astype(np.uint8)
        elif scheme == 'purple':
            r = (127.5 + 127.5 * np.sin(t * 12.57)).astype(np.uint8)
            g = (t * 76.5).astype(np.uint8)
            b = (178.5 + 76.5 * np.sin(t * 12.57)).astype(np.uint8)
        elif scheme == 'galaxy':
            r = (51 + t * 204).astype(np.uint8)
            g = (25.5 + t * 76.5).astype(np.uint8)
            b = (102 + t * 153).astype(np.uint8)
        elif scheme == 'deep_blue':
            r = (t * 51).astype(np.uint8)
            g = (51 + t * 153).astype(np.uint8)
            b = (102 + t * 153).astype(np.uint8)
        elif scheme == 'copper':
            r = np.minimum(255, t * 382.5).astype(np.uint8)
            g = (t * 191.25).astype(np.uint8)
            b = (t * 127.5).astype(np.uint8)
        else:  # sunset
            r = (204 + 51 * np.sin(t * 9.42)).astype(np.uint8)
            g = (76.5 + t * 102).astype(np.uint8)
            b = (t * 127.5).astype(np.uint8)

        return r, g, b

    def get_color_array(self, iterations, max_iterations, scheme=None, offset=None):
        height, width = iterations.shape
        colors = np.zeros((height, width, 3), dtype=np.uint8)

        if scheme is None:
            scheme = self.current_scheme
        if offset is None:
            offset = self.color_offset

        inside = iterations == max_iterations

        t = ((iterations.astype(np.float32) + offset) / max_iterations) % 1.0

        r, g, b = self.get_scheme_colors(t, scheme)
        colors[:, :, 0] = r
        colors[:, :, 1] = g
        colors[:, :, 2] = b

        colors[inside] = 0

        return colors

    def calculate_fractal(self, use_next_location=False, scheme=None, offset=None):
        aspect = self.width / self.height

        if use_next_location:
            center_x = self.next_center_x + self.pan_offset_x
            center_y = self.next_center_y + self.pan_offset_y
            zoom = self.next_zoom
        else:
            center_x = self.center_x + self.pan_offset_x
            center_y = self.center_y + self.pan_offset_y
            zoom = self.zoom

        view_width = 3.5 * zoom
        view_height = view_width / aspect

        min_real = center_x - view_width / 2
        max_real = center_x + view_width / 2
        min_imag = center_y - view_height / 2
        max_imag = center_y + view_height / 2

        max_iter = self.iterations

        iterations = self.mandelbrot_vectorized(
            self.render_height, self.render_width, 
            min_real, max_real, 
            min_imag, max_imag, 
            max_iter
        )

        fractal_data = self.get_color_array(iterations, max_iter, scheme, offset)

        fractal_data = np.ascontiguousarray(fractal_data, dtype=np.uint8)

        return fractal_data, iterations

    def reset(self):
        target = random.choice(self.view_targets)
        self.center_x, self.center_y, self.zoom = target
        self.next_center_x = self.center_x
        self.next_center_y = self.center_y
        self.next_zoom = self.zoom
        self.current_scheme = random.choice(self.color_schemes)
        self.color_offset = random.uniform(0, 1)
        self.time = 0.0
        self.time_since_switch = 0.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.fractal_calculated = False
        self.is_fading = False
        self.next_prepared = False
        self.fade_progress = 0.0

    def update(self, delta_time=0.016):
        self.time += delta_time
        self.time_since_switch += delta_time

        if self.time_since_switch >= self.fade_interval and not self.is_fading:
            self.is_fading = True
            self.fade_progress = 0.0

            self.next_prepared = False

            target = random.choice(self.view_targets)
            self.next_center_x, self.next_center_y, self.next_zoom = target
            self.next_color_scheme = random.choice(self.color_schemes)
            self.next_color_offset = random.uniform(0, 1)

        if self.is_fading:
            self.fade_progress += delta_time / self.fade_duration
            if self.fade_progress >= 1.0:

                self.fade_progress = 0.0
                self.is_fading = False
                self.time_since_switch = 0.0

                self.texture_current, self.texture_next = self.texture_next, self.texture_current
                self.iteration_data_current = self.iteration_data_next

                self.center_x = self.next_center_x
                self.center_y = self.next_center_y
                self.zoom = self.next_zoom
                self.current_scheme = self.next_color_scheme
                self.color_offset = self.next_color_offset

        if self.pan_enabled:
            self.pan_offset_x += self.pan_speed * math.cos(self.time * 0.1)
            self.pan_offset_y += self.pan_speed * math.sin(self.time * 0.15)

    def render(self):
        if not self.initialized:
            self.initialize()

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glViewport(0, 0, self.width, self.height)

        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        if not self.fractal_calculated:
            fractal_data, self.iteration_data_current = self.calculate_fractal()
            self.fractal_calculated = True

            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glBindTexture(GL_TEXTURE_2D, self.texture_current)
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.render_width, self.render_height,
                            GL_RGB, GL_UNSIGNED_BYTE, fractal_data)

        if self.is_fading and not self.next_prepared:
            fractal_data, self.iteration_data_next = self.calculate_fractal(
                use_next_location=True, 
                scheme=self.next_color_scheme,
                offset=self.next_color_offset
            )
            self.next_prepared = True

            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glBindTexture(GL_TEXTURE_2D, self.texture_next)
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, self.render_width, self.render_height,
                            GL_RGB, GL_UNSIGNED_BYTE, fractal_data)

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)

        if self.is_fading and self.next_prepared:

            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glBindTexture(GL_TEXTURE_2D, self.texture_current)
            glColor4f(1.0, 1.0, 1.0, 1.0 - self.fade_progress)

            glBegin(GL_QUADS)
            glTexCoord2f(0, 0)
            glVertex2f(0, 0)
            glTexCoord2f(1, 0)
            glVertex2f(self.width, 0)
            glTexCoord2f(1, 1)
            glVertex2f(self.width, self.height)
            glTexCoord2f(0, 1)
            glVertex2f(0, self.height)
            glEnd()

            # Use additive blending for next texture
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glBindTexture(GL_TEXTURE_2D, self.texture_next)
            glColor4f(1.0, 1.0, 1.0, self.fade_progress)

            glBegin(GL_QUADS)
            glTexCoord2f(0, 0)
            glVertex2f(0, 0)
            glTexCoord2f(1, 0)
            glVertex2f(self.width, 0)
            glTexCoord2f(1, 1)
            glVertex2f(self.width, self.height)
            glTexCoord2f(0, 1)
            glVertex2f(0, self.height)
            glEnd()
        else:

            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glBindTexture(GL_TEXTURE_2D, self.texture_current)
            glColor4f(1.0, 1.0, 1.0, 1.0)

            glBegin(GL_QUADS)
            glTexCoord2f(0, 0)
            glVertex2f(0, 0)
            glTexCoord2f(1, 0)
            glVertex2f(self.width, 0)
            glTexCoord2f(1, 1)
            glVertex2f(self.width, self.height)
            glTexCoord2f(0, 1)
            glVertex2f(0, self.height)
            glEnd()

        glDisable(GL_TEXTURE_2D)

        # Render time overlay if enabled
        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()

        pygame.display.flip()

    def cleanup(self):
        if self.texture_current:
            glDeleteTextures([self.texture_current])
            self.texture_current = None

        if self.texture_next:
            glDeleteTextures([self.texture_next])
            self.texture_next = None

        self.iteration_data_current = None
        self.iteration_data_next = None
        self.initialized = False

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)