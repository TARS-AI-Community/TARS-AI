import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import random
from datetime import datetime

class WavesAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.time = 0.0
        self.initialized = False
        self.clock = pygame.time.Clock()
        self.wireframe = True
        
        self.wireframe_r = random.uniform(0.05, 0.15)
        self.wireframe_g = random.uniform(0.1, 0.3)
        self.wireframe_b = random.uniform(0.2, 0.5)
        
        pygame.font.init()
        self.font = pygame.font.Font(None, 60)
        
        self.waves = []
        for _ in range(8):
            self.waves.append({
                'freq': random.uniform(0.5, 1.2),
                'amp': random.uniform(0.15, 0.3),
                'speed': random.uniform(0.6, 1.2),
                'dir_x': random.uniform(-1, 1),
                'dir_z': random.uniform(-1, 1)
            })
    
    def initialize(self):
        if self.initialized:
            return
        
        bg_r = self.wireframe_r * 0.5
        bg_g = self.wireframe_g * 0.5
        bg_b = self.wireframe_b * 0.5
        
        glClearColor(bg_r, bg_g, bg_b, 1.0)
        
        glDisable(GL_LIGHTING)
        glDisable(GL_LIGHT0)
        glDisable(GL_COLOR_MATERIAL)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        
        glEnable(GL_DEPTH_TEST)
        glShadeModel(GL_SMOOTH)
        
        glEnable(GL_FOG)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glFogfv(GL_FOG_COLOR, [bg_r, bg_g, bg_b, 1.0])
        glFogf(GL_FOG_START, 20.0)
        glFogf(GL_FOG_END, 60.0)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(50, self.width / self.height, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        
        self.initialized = True
    
    def update(self, delta_time=None):
        if delta_time is None:
            try:
                delta_time = self.clock.get_time() / 1000.0
            except:
                delta_time = 0.033
        self.time += delta_time
    
    def wave_height(self, x, z):
        h = 0.0
        for wave in self.waves:
            dist = x * wave['dir_x'] + z * wave['dir_z']
            h += wave['amp'] * math.sin(wave['freq'] * dist + self.time * wave['speed'])
        return h
    
    def render(self):
        if not self.initialized:
            self.initialize()
        
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        if self.wireframe:
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        else:
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        gluLookAt(11, 0, 6, 0, 0, -6, 0, 1, 0)
        
        glRotatef(90, 0, 0, 1)
        
        grid_size_x = 50
        grid_size_z = 100
        spacing = 0.8
        half_x = grid_size_x // 2
        half_z = grid_size_z // 2
        
        for i in range(grid_size_x - 1):
            glBegin(GL_TRIANGLE_STRIP)
            for j in range(grid_size_z):
                for k in [0, 1]:
                    x = (i + k - half_x) * spacing
                    z = (j - half_z) * spacing
                    y = self.wave_height(x, z)
                    
                    wave_factor = (y + 0.3)
                    
                    if self.wireframe:
                        r = self.wireframe_r
                        g = self.wireframe_g
                        b = self.wireframe_b
                    else:
                        r = 0.05 + wave_factor * 0.15
                        g = 0.25 + wave_factor * 0.2
                        b = 0.45 + wave_factor * 0.15
                    
                    glColor3f(r, g, b)
                    glVertex3f(x, y, z)
            glEnd()
        
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        
        current_time = datetime.now()
        time_str = current_time.strftime("%I:%M:%S %p")
        text_surface = self.font.render(time_str, True, (255, 255, 255))
        text_data = pygame.image.tostring(text_surface, "RGBA", False)
        
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()
        
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, text_width, text_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        
        x_pos = self.width - 80
        y_pos = self.height - 30
        
        glTranslatef(x_pos, y_pos, 0)
        glRotatef(-90, 0, 0, 1)
        
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1)
        glVertex2f(0, 0)
        glTexCoord2f(1, 1)
        glVertex2f(text_width, 0)
        glTexCoord2f(1, 0)
        glVertex2f(text_width, text_height)
        glTexCoord2f(0, 0)
        glVertex2f(0, text_height)
        glEnd()
        
        glDeleteTextures([tex_id])
        
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        
        try:
            self.clock.tick(30)
        except:
            pass
        pygame.display.flip()
    
    def reset(self):
        self.time = 0.0
    
    def cleanup(self):
        self.initialized = False
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glDisable(GL_FOG)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)