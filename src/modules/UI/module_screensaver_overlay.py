"""
Module: Screensaver Overlay (Time Display)
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
from datetime import datetime
from OpenGL.GL import *
from modules.module_config import load_config

CONFIG = load_config()


class TimeOverlay:
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
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
        glOrtho(0, self.width, 0, self.height, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        x = self.width - 80
        y = self.height - 30
        
        shadow_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, shadow_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, shadow_width, shadow_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, shadow_data)
        
        glPushMatrix()
        glTranslatef(x + 4, y - 4, 0)
        glRotatef(-90, 0, 0, 1)
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
        glRotatef(-90, 0, 0, 1)
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
        glRotatef(-90, 0, 0, 1)
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