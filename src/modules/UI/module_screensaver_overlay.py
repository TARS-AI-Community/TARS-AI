"""
Module: Screensaver Overlay (Time Display)
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
import pygame
from datetime import datetime
from OpenGL.GL import *
from modules.module_config import load_config

CONFIG = load_config()


class TimeOverlay:
    
    def __init__(self, width, height, rotation=0):
        self.width = width
        self.height = height
        self.rotation = rotation
        self.is_portrait = height > width  # Detect portrait mode
        self.ampm_format = CONFIG['UI']['ampm_format']
        pygame.font.init()
        self.font = pygame.font.Font("UI/astrolab.ttf", 30)
    
    def render(self, screen):
        current_time = datetime.now()
        if self.ampm_format:
            time_str = current_time.strftime("%I:%M:%S %p")
        else:
            time_str = current_time.strftime("%H:%M:%S")
        
        x_pos = 40
        y_pos = 40
        
        shadow_surface = self.font.render(time_str, True, (0, 0, 0))
        screen.blit(shadow_surface, (x_pos + 3, y_pos + 3))
        screen.blit(shadow_surface, (x_pos + 2, y_pos + 2))
        
        text_surface = self.font.render(time_str, True, (255, 255, 255))
        screen.blit(text_surface, (x_pos, y_pos))
    
    def render_gl(self):
        current_time = datetime.now()
        if self.ampm_format:
            time_str = current_time.strftime("%I:%M:%S %p")
        else:
            time_str = current_time.strftime("%H:%M:%S")
        
        text_surface = self.font.render(time_str, True, (255, 255, 255))
        text_data = pygame.image.tostring(text_surface, "RGBA", True)
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()
        
        shadow_surface = self.font.render(time_str, True, (0, 0, 0))
        shadow_data = pygame.image.tostring(shadow_surface, "RGBA", True)
        shadow_width = shadow_surface.get_width()
        shadow_height = shadow_surface.get_height()
        
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        
        if self.is_portrait:
            # Rotation first in code = applied last (rotates the final 2D output)
            glRotatef(90, 0, 0, 1)
            glOrtho(0, self.height, 0, self.width, -1, 1)
            # Position in logical landscape coordinates
            x = self.height - 80
            y = self.width - 30
        else:
            glOrtho(0, self.width, 0, self.height, -1, 1)
            x = self.width - 80
            y = self.height - 30
        
        text_rotate = -90
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        shadow_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, shadow_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, shadow_width, shadow_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, shadow_data)
        
        glPushMatrix()
        glTranslatef(x + 4, y - 4, 0)
        glRotatef(text_rotate, 0, 0, 1)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(shadow_width, 0)
        glTexCoord2f(1, 1); glVertex2f(shadow_width, shadow_height)
        glTexCoord2f(0, 1); glVertex2f(0, shadow_height)
        glEnd()
        glPopMatrix()
        
        glPushMatrix()
        glTranslatef(x + 3, y - 3, 0)
        glRotatef(text_rotate, 0, 0, 1)
        glColor4f(1.0, 1.0, 1.0, 0.7)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(shadow_width, 0)
        glTexCoord2f(1, 1); glVertex2f(shadow_width, shadow_height)
        glTexCoord2f(0, 1); glVertex2f(0, shadow_height)
        glEnd()
        glPopMatrix()
        
        glBindTexture(GL_TEXTURE_2D, 0)
        glDeleteTextures([shadow_tex])
        
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_width, text_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        
        glPushMatrix()
        glTranslatef(x, y, 0)
        glRotatef(text_rotate, 0, 0, 1)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(text_width, 0)
        glTexCoord2f(1, 1); glVertex2f(text_width, text_height)
        glTexCoord2f(0, 1); glVertex2f(0, text_height)
        glEnd()
        glPopMatrix()
        
        glBindTexture(GL_TEXTURE_2D, 0)
        glDeleteTextures([tex_id])
        
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        
        glPopAttrib()