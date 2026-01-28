"""
Module: TARS Bounce Screensaver (OpenGL)
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
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import random
import math


class BounceAnimation:
    COLORS = [
        (1.0, 0.33, 0.33),
        (0.33, 1.0, 0.33),
        (0.33, 0.33, 1.0),
        (1.0, 1.0, 0.33),
        (1.0, 0.33, 1.0),
        (0.33, 1.0, 1.0),
        (1.0, 0.65, 0.0),
        (0.58, 0.0, 0.83),
    ]
    
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.initialized = False
        self.clock = pygame.time.Clock()
        
        self.logo_width = 160
        self.logo_height = 100
        
        self.bounds_w = height
        self.bounds_h = width
        
        self.color_index = 0
        self.current_color = self.COLORS[self.color_index]
        self.corner_hits = 0
        
        self.distortion_time = 0
        self.jitter_x = 0
        self.jitter_y = 0
        
        self.glitch_active = False
        self.glitch_timer = 0
        self.glitch_duration = 0
        self.glitch_wave_speed = 0
        self.glitch_wave_amp = 0
        self.glitch_color_intensity = 0
        
        self.texture_id = None
        self.scanline_texture_id = None
        self._create_logo_texture()
        
        max_x = max(10, self.bounds_w - self.logo_width - 10)
        max_y = max(10, self.bounds_h - self.logo_height - 10)
        self.x = float(random.randint(10, max_x))
        self.y = float(random.randint(10, max_y))
        self.vx = random.choice([-1.5, -1.0, 1.0, 1.5])
        self.vy = random.choice([-1.5, -1.0, 1.0, 1.5])
    
    def _create_logo_texture(self):
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        brandy_path = os.path.join(script_dir, 'brandy.ttf')
        
        pygame.font.init()
        
        try:
            if os.path.exists(brandy_path):
                font_logo = pygame.font.Font(brandy_path, 80)
            else:
                font_logo = pygame.font.SysFont('Arial', 80, bold=True)
            font_system = pygame.font.SysFont('Arial', 19, bold=True)
        except:
            font_logo = pygame.font.Font(None, 80)
            font_system = pygame.font.Font(None, 21)
        
        text = font_logo.render("TARS", True, (255, 255, 255))
        text_w = text.get_width()
        text_h = text.get_height()
        
        oval_width = int(text_w * 1.1)
        oval_height = 44
        
        w = oval_width + 10
        h = text_h + oval_height - 10
        
        self.logo_width = w
        self.logo_height = h
        
        surface = pygame.Surface((w, h), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        
        text_x = (w - text_w) // 2
        surface.blit(text, (text_x, 0))
        
        oval_x = (w - oval_width) // 2
        oval_y = text_h - 14
        oval_rect = pygame.Rect(oval_x, oval_y, oval_width, oval_height)
        pygame.draw.ellipse(surface, (255, 255, 255), oval_rect)
        
        system_text = font_system.render("S Y S T E M", True, (0, 0, 0))
        system_x = (w - system_text.get_width()) // 2
        system_y = oval_y + (oval_height - system_text.get_height()) // 2
        surface.blit(system_text, (system_x, system_y))
        
        blurred = self._apply_blur(surface, 2)
        
        self.logo_surface = blurred
    
    def _apply_blur(self, surface, radius):
        w, h = surface.get_size()
        
        result = pygame.Surface((w, h), pygame.SRCALPHA)
        result.fill((0, 0, 0, 0))
        
        offsets = [
            (-radius, 0), (radius, 0), (0, -radius), (0, radius),
            (-radius, -radius), (radius, -radius), (-radius, radius), (radius, radius),
        ]
        
        faded = surface.copy()
        faded.set_alpha(30)
        for ox, oy in offsets:
            result.blit(faded, (ox, oy))
        
        result.blit(surface, (0, 0))
        
        return result
    
    def _create_scanline_texture(self):
        w = self.bounds_w
        h = self.bounds_h
        
        surface = pygame.Surface((w, h), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        
        for y in range(0, h, 2):
            pygame.draw.line(surface, (0, 0, 0, 255), (0, y), (w, y), 1)
        
        texture_data = pygame.image.tostring(surface, "RGBA", True)
        
        self.scanline_texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.scanline_texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
    
    def _upload_texture(self):
        if self.texture_id is not None:
            glDeleteTextures([self.texture_id])
        
        texture_data = pygame.image.tostring(self.logo_surface, "RGBA", True)
        w, h = self.logo_surface.get_size()
        
        self.texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
    
    def initialize(self):
        if self.initialized:
            return
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glDisable(GL_FOG)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        self._upload_texture()
        self._create_scanline_texture()
        
        self.initialized = True
    
    def _change_color(self):
        self.color_index = (self.color_index + 1) % len(self.COLORS)
        self.current_color = self.COLORS[self.color_index]
    
    def reset(self):
        max_x = max(10, self.bounds_w - self.logo_width - 10)
        max_y = max(10, self.bounds_h - self.logo_height - 10)
        self.x = float(random.randint(10, max_x))
        self.y = float(random.randint(10, max_y))
        self.vx = random.choice([-1.5, -1.0, 1.0, 1.5])
        self.vy = random.choice([-1.5, -1.0, 1.0, 1.5])
        self.color_index = random.randint(0, len(self.COLORS) - 1)
        self.current_color = self.COLORS[self.color_index]
        self.distortion_time = 0
        self.jitter_x = 0
        self.jitter_y = 0
        self.glitch_active = False
        self.glitch_timer = 0
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        
        bounced_x = False
        bounced_y = False
        
        if self.x <= 0:
            self.x = 0
            self.vx = abs(self.vx)
            bounced_x = True
        elif self.x >= self.bounds_w - self.logo_width:
            self.x = self.bounds_w - self.logo_width
            self.vx = -abs(self.vx)
            bounced_x = True
        
        if self.y <= 0:
            self.y = 0
            self.vy = abs(self.vy)
            bounced_y = True
        elif self.y >= self.bounds_h - self.logo_height:
            self.y = self.bounds_h - self.logo_height
            self.vy = -abs(self.vy)
            bounced_y = True
        
        if bounced_x or bounced_y:
            self._change_color()
        
        if bounced_x and bounced_y:
            self.corner_hits += 1
        
        self.distortion_time += 1
        
        if random.random() < 0.02:
            self.jitter_x = random.uniform(-3, 3)
        else:
            self.jitter_x *= 0.8
        
        self.jitter_y = math.sin(self.distortion_time * 0.05) * 0.5
        
        if self.glitch_active:
            self.glitch_timer += 1
            if self.glitch_timer >= self.glitch_duration:
                self.glitch_active = False
        else:
            if random.random() < 0.002:
                self._trigger_glitch()
    
    def _trigger_glitch(self):
        self.glitch_active = True
        self.glitch_timer = 0
        self.glitch_duration = random.randint(6, 15)
        self.glitch_wave_speed = random.uniform(0.3, 0.6)
        self.glitch_wave_amp = random.uniform(8, 20)
        self.glitch_color_intensity = random.uniform(0.15, 0.3)
    
    def render(self):
        if not self.initialized:
            self.initialize()
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        glTranslatef(0, self.height, 0)
        glRotatef(-90, 0, 0, 1)
        
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        r, g, b = self.current_color
        
        x1 = self.x + self.jitter_x
        y1 = self.y + self.jitter_y
        
        chroma_offset = 1.5
        
        if self.glitch_active:
            num_slices = 12
            slice_h = self.logo_height / num_slices
            
            for i in range(num_slices):
                sy = y1 + i * slice_h
                wave_phase = self.glitch_timer * self.glitch_wave_speed + i * 0.5
                offset = math.sin(wave_phase) * self.glitch_wave_amp
                
                color_shift = math.sin(wave_phase * 1.3) * self.glitch_color_intensity
                
                tex_y1 = i / num_slices
                tex_y2 = (i + 1) / num_slices
                
                sr = max(0, min(1, r + color_shift))
                sg = max(0, min(1, g))
                sb = max(0, min(1, b - color_shift))
                
                sx1 = x1 + offset
                sx2 = sx1 + self.logo_width
                sy2 = sy + slice_h
                
                glColor4f(sr * 0.4, 0, 0, 1.0)
                glBegin(GL_QUADS)
                glTexCoord2f(0, tex_y1); glVertex2f(sx1 - chroma_offset - abs(offset) * 0.2, sy)
                glTexCoord2f(1, tex_y1); glVertex2f(sx2 - chroma_offset - abs(offset) * 0.2, sy)
                glTexCoord2f(1, tex_y2); glVertex2f(sx2 - chroma_offset - abs(offset) * 0.2, sy2)
                glTexCoord2f(0, tex_y2); glVertex2f(sx1 - chroma_offset - abs(offset) * 0.2, sy2)
                glEnd()
                
                glColor4f(0, sg * 0.5, 0, 1.0)
                glBegin(GL_QUADS)
                glTexCoord2f(0, tex_y1); glVertex2f(sx1, sy)
                glTexCoord2f(1, tex_y1); glVertex2f(sx2, sy)
                glTexCoord2f(1, tex_y2); glVertex2f(sx2, sy2)
                glTexCoord2f(0, tex_y2); glVertex2f(sx1, sy2)
                glEnd()
                
                glColor4f(0, 0, sb * 0.4, 1.0)
                glBegin(GL_QUADS)
                glTexCoord2f(0, tex_y1); glVertex2f(sx1 + chroma_offset + abs(offset) * 0.2, sy)
                glTexCoord2f(1, tex_y1); glVertex2f(sx2 + chroma_offset + abs(offset) * 0.2, sy)
                glTexCoord2f(1, tex_y2); glVertex2f(sx2 + chroma_offset + abs(offset) * 0.2, sy2)
                glTexCoord2f(0, tex_y2); glVertex2f(sx1 + chroma_offset + abs(offset) * 0.2, sy2)
                glEnd()
        else:
            x2 = x1 + self.logo_width
            y2 = y1 + self.logo_height
            
            glColor4f(r * 0.4, 0, 0, 1.0)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x1 - chroma_offset, y1)
            glTexCoord2f(1, 0); glVertex2f(x2 - chroma_offset, y1)
            glTexCoord2f(1, 1); glVertex2f(x2 - chroma_offset, y2)
            glTexCoord2f(0, 1); glVertex2f(x1 - chroma_offset, y2)
            glEnd()
            
            glColor4f(0, g * 0.5, 0, 1.0)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x1, y1)
            glTexCoord2f(1, 0); glVertex2f(x2, y1)
            glTexCoord2f(1, 1); glVertex2f(x2, y2)
            glTexCoord2f(0, 1); glVertex2f(x1, y2)
            glEnd()
            
            glColor4f(0, 0, b * 0.4, 1.0)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x1 + chroma_offset, y1)
            glTexCoord2f(1, 0); glVertex2f(x2 + chroma_offset, y1)
            glTexCoord2f(1, 1); glVertex2f(x2 + chroma_offset, y2)
            glTexCoord2f(0, 1); glVertex2f(x1 + chroma_offset, y2)
            glEnd()
        
        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glBegin(GL_POINTS)
        for _ in range(50):
            sx = random.uniform(0, self.bounds_w)
            sy = random.uniform(0, self.bounds_h)
            glColor4f(1.0, 1.0, 1.0, random.uniform(0.02, 0.08))
            glVertex2f(sx, sy)
        glEnd()
        glEnable(GL_TEXTURE_2D)
        
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glBindTexture(GL_TEXTURE_2D, self.scanline_texture_id)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(self.bounds_w, 0)
        glTexCoord2f(1, 1); glVertex2f(self.bounds_w, self.bounds_h)
        glTexCoord2f(0, 1); glVertex2f(0, self.bounds_h)
        glEnd()
        
        pygame.display.flip()
        self.clock.tick(60)
    
    def cleanup(self):
        if self.texture_id is not None:
            try:
                glDeleteTextures([self.texture_id])
            except:
                pass
            self.texture_id = None
        if self.scanline_texture_id is not None:
            try:
                glDeleteTextures([self.scanline_texture_id])
            except:
                pass
            self.scanline_texture_id = None
        self.initialized = False