"""
Module: Blackhole Screensaver
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

import random
import time
import math
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
import pygame
from UI.module_screensaver_overlay import TimeOverlay

class BlackHoleAnimation:
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.time = 0.0
        self.rotation_y = 0
        self.rotation_x = 0
        
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None
        
        self.disk_tilt_x = random.uniform(-25, 25)  
        self.disk_tilt_y = random.uniform(0, 360)   
        self.bh_radius = 3.5  
        self.disk_inner = 4.5  
        self.disk_outer = 10.0  
        self.stars = []
        self.disk_particles = []
        self.initialized = False
        self.stars_display_list = None
        self.blob_texture = None

    def _create_blob_texture(self):
        size = 64
        texture_data = []
        center = size / 2

        for y in range(size):
            for x in range(size):
                dx = x - center
                dy = y - center
                distance = math.sqrt(dx*dx + dy*dy) / center
                if distance <= 1.0:
                    alpha = (1.0 - distance) ** 2  
                else:
                    alpha = 0.0

                texture_data.extend([255, 255, 255, int(alpha * 255)])

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, bytes(texture_data))

        return texture_id

    def initialize(self):
        if self.initialized:
            return

        self.blob_texture = self._create_blob_texture()

        for _ in range(2000):
            x = random.uniform(-30, 30)
            y = random.uniform(-20, 20)
            z = random.uniform(-35, -25)

            rand = random.random()
            if rand < 0.85:  

                brightness = random.uniform(0.15, 0.4)
                size = random.choice([0.8, 1.0, 1.0])
            elif rand < 0.96:  

                brightness = random.uniform(0.4, 0.7)
                size = random.choice([1.0, 1.2, 1.5])
            else:
                brightness = random.uniform(0.7, 1.0)
                size = random.choice([1.5, 2.0, 2.5])

            star_type = random.random()
            if star_type < 0.80:  

                color = (brightness, brightness, brightness)
            elif star_type < 0.92:  

                color = (brightness * 0.75, brightness * 0.9, brightness)
            elif star_type < 0.97:  

                color = (brightness, brightness * 0.85, brightness * 0.5)
            else:
                color = (brightness, brightness * 0.65, brightness * 0.4)

            self.stars.append({
                'pos': (x, y, z),
                'color': color,
                'size': size
            })

        num_nebulas = random.randint(0, 6)  

        nebula_clouds = []

        nebula_colors = [
            (0.4, 0.2, 0.8),   
            (0.2, 0.4, 0.9),   
            (0.6, 0.3, 0.9),   
            (0.3, 0.2, 0.7),   
            (0.5, 0.2, 0.9),   
            (0.2, 0.5, 1.0),   

        ]

        for _ in range(num_nebulas):
            if random.random() < 0.5:
                x = random.uniform(15, 25)
            else:
                x = random.uniform(-25, -15)
            y = random.uniform(-15, 15)  
            z = random.uniform(-35, -28)  
            color = random.choice(nebula_colors)
            nebula_clouds.append((x, y, z, color))

        self.stars_display_list = glGenLists(1)
        glNewList(self.stars_display_list, GL_COMPILE)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glLoadIdentity()
        glTranslatef(0.0, 0.0, -20)
        modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        right = [modelview[0][0], modelview[1][0], modelview[2][0]]
        up = [modelview[0][1], modelview[1][1], modelview[2][1]]

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.blob_texture)

        for cx, cy, cz, base_color in nebula_clouds:
            r, g, b = base_color

            wispy_layers = [
                (0, 0, 18, 0.08),
                (4, 3, 16, 0.06),
                (-3, -4, 17, 0.07),
                (6, -2, 15, 0.05),
                (-5, 3, 14, 0.04),
                (2, 6, 13, 0.03),
                (-6, -3, 16, 0.05),
                (3, -6, 14, 0.04),
            ]

            for ox, oy, size, alpha in wispy_layers:
                px = cx + ox
                py = cy + oy
                pz = cz
                radius = size

                color_var = random.uniform(0.9, 1.1)
                glColor4f(r * color_var, g * color_var, b * color_var, alpha)

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

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_TEXTURE_2D)
        for i in range(60):
            x = random.uniform(-30, 30)
            y = x * 0.3 + random.uniform(-3, 3)
            z = random.uniform(-34, -26)
            glPointSize(random.uniform(10, 25))
            glColor4f(0.1, 0.1, 0.13, random.uniform(0.02, 0.05))
            glBegin(GL_POINTS)
            glVertex3f(x, y, z)
            glEnd()

        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        for star in self.stars:
            glPointSize(star['size'])
            glColor3f(*star['color'])
            glBegin(GL_POINTS)
            glVertex3f(*star['pos'])
            glEnd()
        glDisable(GL_POINT_SMOOTH)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -20)
        modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        right = [modelview[0][0], modelview[1][0], modelview[2][0]]
        up = [modelview[0][1], modelview[1][1], modelview[2][1]]

        bright_stars = [s for s in self.stars if s['size'] >= 2.0][:10]  

        for star in bright_stars:
            px, py, pz = star['pos']
            r, g, b = star['color']
            spike_length = star['size'] * 2.5
            spike_width = 0.12
            glColor4f(r, g, b, 0.4)
            for angle in [0, 90]:  
                rad = math.radians(angle)
                dx = math.cos(rad)
                dy = math.sin(rad)
                glBegin(GL_QUADS)
                glVertex3f(px + right[0]*spike_width*dy + up[0]*spike_width*dy,
                          py + right[1]*spike_width*dy + up[1]*spike_width*dy, pz)
                glVertex3f(px - right[0]*spike_width*dy - up[0]*spike_width*dy,
                          py - right[1]*spike_width*dy - up[1]*spike_width*dy, pz)
                glVertex3f(px + right[0]*dx*spike_length - right[0]*spike_width*dy + up[0]*dx*spike_length - up[0]*spike_width*dy,
                          py + right[1]*dx*spike_length - right[1]*spike_width*dy + up[1]*dx*spike_length - up[1]*spike_width*dy, pz)
                glVertex3f(px + right[0]*dx*spike_length + right[0]*spike_width*dy + up[0]*dx*spike_length + up[0]*spike_width*dy,
                          py + right[1]*dx*spike_length + right[1]*spike_width*dy + up[1]*dx*spike_length + up[1]*spike_width*dy, pz)
                glEnd()

        glDisable(GL_TEXTURE_2D)
        glDisable(GL_POINT_SMOOTH)
        glEnable(GL_DEPTH_TEST)
        glEndList()

        for _ in range(200):  
            angle = random.uniform(0, 2 * math.pi)
            t = random.random() ** 0.8
            radius = self.disk_inner + (self.disk_outer - self.disk_inner) * t
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            lensing_factor = 1.0 - (radius - self.disk_inner) / (self.disk_outer - self.disk_inner)
            y_range = 0.1 + lensing_factor * 1.5  
            y = random.uniform(-y_range, y_range)
            if t < 0.3:
                color = (1.0, 1.0, 0.9, 1.0)  
            elif t < 0.5:
                color = (1.0, 0.8, 0.4, 0.95)  
            elif t < 0.7:
                color = (1.0, 0.5, 0.1, 0.9)  
            else:
                color = (0.9, 0.2, 0.0, 0.85)  
            size = random.uniform(8.0, 16.0)
            radius_ratio = radius / self.disk_inner
            speed = 0.0075 / (radius_ratio ** 2.5)  
            self.disk_particles.append({
                'pos': [x, y, z],
                'angle': angle,
                'radius': radius,
                'base_radius': radius,
                'color': color,
                'size': size,
                'speed': speed,
                't': t,
                'turbulence': random.uniform(0, 2 * math.pi),
                'vertical_phase': random.uniform(0, 2 * math.pi),
                'lensing_height': y_range  

            })
            self.disk_particles.append({
                'pos': [x, y, z],
                'angle': angle,
                'radius': radius,
                'base_radius': radius,
                'color': color,
                'size': size,
                'speed': speed,
                't': t,
                'turbulence': random.uniform(0, 2 * math.pi),
                'vertical_phase': random.uniform(0, 2 * math.pi)
            })

        self.initialized = True

    def reset(self):
        self.time = 0.0
        self.rotation_y = 0
        self.rotation_x = 0
        for particle in self.disk_particles:
            particle['angle'] = random.uniform(0, 2 * math.pi)
            particle['radius'] = particle['base_radius']

    def update(self, delta_time=0.016):
        self.time += delta_time
        for particle in self.disk_particles:

            particle['angle'] += particle['speed']
            if particle['angle'] > 2 * math.pi:
                particle['angle'] -= 2 * math.pi

            particle['turbulence'] += 0.03
            particle['vertical_phase'] += 0.02

            radial_wave = math.sin(particle['turbulence']) * 0.15

            effective_radius = particle['radius'] + radial_wave
            particle['pos'][0] = effective_radius * math.cos(particle['angle'])
            particle['pos'][2] = effective_radius * math.sin(particle['angle'])

            lensing_factor = 1.0 - (particle['radius'] - self.disk_inner) / (self.disk_outer - self.disk_inner)
            base_wave = math.sin(particle['vertical_phase']) * 0.08
            lensing_lift = lensing_factor * 0.8  

            particle['pos'][1] = base_wave + lensing_lift * math.sin(particle['angle'] * 2)

    def draw_event_horizon(self):
        glEnable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)

        modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        right = [modelview[0][0], modelview[1][0], modelview[2][0]]
        up = [modelview[0][1], modelview[1][1], modelview[2][1]]

        px, py, pz = 0, 0, 0
        radius = self.bh_radius

        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.0, 0.0, 0.0, 1.0)

        segments = 32
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(px, py, pz)  

        for i in range(segments + 1):
            angle = (i / segments) * 2 * 3.14159
            x = px + radius * math.cos(angle) * right[0] + radius * math.sin(angle) * up[0]
            y = py + radius * math.cos(angle) * right[1] + radius * math.sin(angle) * up[1]
            z = pz + radius * math.cos(angle) * right[2] + radius * math.sin(angle) * up[2]
            glVertex3f(x, y, z)
        glEnd()

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.blob_texture)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)  

        glDepthMask(GL_FALSE)

        glow_layers = [
            (self.bh_radius * 0.92, 0.6),  
            (self.bh_radius * 1.1, 1.0),   
            (self.bh_radius * 1.5, 0.7),   
            (self.bh_radius * 2.2, 0.4),   

        ]

        for glow_radius, alpha in glow_layers:
            glColor4f(1.0, 1.0, 1.0, alpha)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0)
            glVertex3f(px - right[0] * glow_radius - up[0] * glow_radius,
                       py - right[1] * glow_radius - up[1] * glow_radius,
                       pz - right[2] * glow_radius - up[2] * glow_radius)
            glTexCoord2f(1, 0)
            glVertex3f(px + right[0] * glow_radius - up[0] * glow_radius,
                       py + right[1] * glow_radius - up[1] * glow_radius,
                       pz + right[2] * glow_radius - up[2] * glow_radius)
            glTexCoord2f(1, 1)
            glVertex3f(px + right[0] * glow_radius + up[0] * glow_radius,
                       py + right[1] * glow_radius + up[1] * glow_radius,
                       pz + right[2] * glow_radius + up[2] * glow_radius)
            glTexCoord2f(0, 1)
            glVertex3f(px - right[0] * glow_radius + up[0] * glow_radius,
                       py - right[1] * glow_radius + up[1] * glow_radius,
                       pz + right[2] * glow_radius + up[2] * glow_radius)
            glEnd()

        glDisable(GL_TEXTURE_2D)
        glDepthMask(GL_TRUE)

    def draw_accretion_disk(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)  

        glDisable(GL_COLOR_MATERIAL)
        glEnable(GL_DEPTH_TEST)  

        glDepthMask(GL_FALSE)  

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.blob_texture)

        modelview = glGetFloatv(GL_MODELVIEW_MATRIX)
        right = [modelview[0][0], modelview[1][0], modelview[2][0]]
        up = [modelview[0][1], modelview[1][1], modelview[2][1]]

        bloom_layers = [
            (1.0, 0.7),     
            (2.5, 0.5),     
            (5.0, 0.35),    
            (10.0, 0.15),   

        ]

        for size_mult, alpha_mult in bloom_layers:
            for particle in self.disk_particles:
                px, py, pz = particle['pos']
                radius = particle['size'] * size_mult * 0.015

                r, g, b, a = particle['color']
                glColor4f(r, g, b, a * alpha_mult)

                glBegin(GL_QUADS)

                glTexCoord2f(0, 0)
                glVertex3f(
                    px - right[0] * radius - up[0] * radius,
                    py - right[1] * radius - up[1] * radius,
                    pz - right[2] * radius - up[2] * radius
                )

                glTexCoord2f(1, 0)
                glVertex3f(
                    px + right[0] * radius - up[0] * radius,
                    py + right[1] * radius - up[1] * radius,
                    pz + right[2] * radius - up[2] * radius
                )

                glTexCoord2f(1, 1)
                glVertex3f(
                    px + right[0] * radius + up[0] * radius,
                    py + right[1] * radius + up[1] * radius,
                    pz + right[2] * radius + up[2] * radius
                )

                glTexCoord2f(0, 1)
                glVertex3f(
                    px - right[0] * radius + up[0] * radius,
                    py - right[1] * radius + up[1] * radius,
                    pz - right[2] * radius + up[2] * radius
                )
                glEnd()

        glDisable(GL_TEXTURE_2D)
        glDepthMask(GL_TRUE)  

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def render(self):
        if not self.initialized:
            self.initialize()

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect_ratio = self.width / max(1, self.height)
        gluPerspective(45, aspect_ratio, 0.1, 50.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glViewport(0, 0, self.width, self.height)

        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glDisable(GL_TEXTURE_2D)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glPushMatrix()
        glTranslatef(0.0, 0.0, -20)  

        if self.stars_display_list:
            glCallList(self.stars_display_list)

        glRotatef(90, 0, 0, 1)  
        self.draw_event_horizon()
        glRotatef(self.disk_tilt_y, 0, 1, 0)  
        glRotatef(self.disk_tilt_x, 1, 0, 0)  
        self.draw_accretion_disk()
        glPopMatrix()
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()
        
        pygame.display.flip()

    def cleanup(self):
        self.stars.clear()
        self.disk_particles.clear()
        self.initialized = False

        if self.stars_display_list:
            glDeleteLists(self.stars_display_list, 1)
            self.stars_display_list = None

        if self.blob_texture:
            glDeleteTextures([self.blob_texture])
            self.blob_texture = None

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glColor4f(1.0, 1.0, 1.0, 1.0)