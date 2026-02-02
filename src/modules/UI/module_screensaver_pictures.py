"""
Module: Pictures Screensaver
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
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import random
import os
import time
import re
from UI.module_screensaver_overlay import TimeOverlay

class PicturesAnimation:
    def __init__(self, screen, width, height, pictures_folder=None, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.initialized = False
        
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        if pictures_folder is None:
            self.pictures_folder = os.path.join(script_dir, "pictures")
        else:
            self.pictures_folder = pictures_folder
        
        self.backgrounds_folder = script_dir
        self.background_paths = []
        self.background_texture = None
        
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        
        self.glow_size = 15
        self.glow_intensity = 180
        
        self.pan_overflow = 30
        self.pan_start = (0, 0)
        self.pan_end = (0, 0)
        self.next_pan_start = (0, 0)
        self.next_pan_end = (0, 0)
        
        self.transition_type = 'pan'
        self.next_transition_type = 'pan'
        self.perspective_start = 0.0
        self.perspective_end = 0.0
        self.next_perspective_start = 0.0
        self.next_perspective_end = 0.0
        self.perspective_direction = 'horizontal'
        self.next_perspective_direction = 'horizontal'
        self.perspective_intensity = 0.20
        
        self.zoom_start = 1.0
        self.zoom_end = 1.0
        self.next_zoom_start = 1.0
        self.next_zoom_end = 1.0
        self.zoom_min = 1.0
        self.zoom_max = 1.20
        
        self.image_paths = []
        self.shuffled_queue = []
        self.current_index = 0
        
        self.current_texture = None
        self.current_size = (0, 0)
        self.next_texture = None
        self.next_size = (0, 0)
        
        self.display_duration = 10.0
        self.transition_duration = 1.5
        self.last_switch_time = 0
        self.transitioning = False
        self.transition_alpha = 0.0
        
        self.clock = pygame.time.Clock()
        
        self.draw_width = height
        self.draw_height = width
        
        self._load_image_list()
        self._shuffle_queue()
    
    def initialize(self):
        if self.initialized:
            return
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        glViewport(0, 0, self.width, self.height)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -100, 100)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        self._load_background()
        
        self.initialized = True
    
    def _load_image_list(self):
        self.image_paths = []
        
        if not os.path.exists(self.pictures_folder):
            return
        
        for filename in os.listdir(self.pictures_folder):
            if filename.lower().endswith(self.supported_formats):
                full_path = os.path.join(self.pictures_folder, filename)
                if os.path.isfile(full_path):
                    self.image_paths.append(full_path)
    
    def _load_background(self):
        self.background_paths = []
        
        pattern = re.compile(r'^picture_background\d*\.png$', re.IGNORECASE)
        
        if os.path.exists(self.backgrounds_folder):
            for filename in os.listdir(self.backgrounds_folder):
                if pattern.match(filename):
                    full_path = os.path.join(self.backgrounds_folder, filename)
                    if os.path.isfile(full_path):
                        self.background_paths.append(full_path)
        
        if not self.background_paths:
            self.background_texture = None
            return
        
        chosen_background = random.choice(self.background_paths)
        
        try:
            self.background_texture = self._load_texture(chosen_background, scale_to_screen=True)
        except:
            self.background_texture = None
    
    def _load_texture(self, image_path, scale_to_screen=False):
        image = pygame.image.load(image_path).convert_alpha()
        
        if scale_to_screen:
            image = pygame.transform.smoothscale(image, (self.draw_width, self.draw_height))
        
        img_width, img_height = image.get_size()
        image_data = pygame.image.tostring(image, "RGBA", True)
        
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img_width, img_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
        
        return texture_id, img_width, img_height
    
    def _create_glow_surface(self, surface, glow_size, intensity, pan_direction='none'):
        width, height = surface.get_size()
        
        if pan_direction == 'horizontal':
            pad_left, pad_right = 0, 0
            pad_top, pad_bottom = glow_size, glow_size
        elif pan_direction == 'vertical':
            pad_left, pad_right = glow_size, glow_size
            pad_top, pad_bottom = 0, 0
        else:
            pad_left, pad_right = glow_size, glow_size
            pad_top, pad_bottom = glow_size, glow_size
        
        total_width = width + pad_left + pad_right
        total_height = height + pad_top + pad_bottom
        
        glow_surface = pygame.Surface((total_width, total_height), pygame.SRCALPHA)
        
        mask = pygame.mask.from_surface(surface, 50)
        
        for radius in range(glow_size, 0, -3):
            alpha = int(intensity * (radius / glow_size) * 0.5)
            temp_mask = mask.to_surface(setcolor=(0, 0, 0, alpha), unsetcolor=(0, 0, 0, 0))
            
            for dx in range(-radius, radius + 1, 3):
                for dy in range(-radius, radius + 1, 3):
                    if dx * dx + dy * dy <= radius * radius:
                        if pan_direction == 'horizontal' and dx != 0:
                            continue
                        if pan_direction == 'vertical' and dy != 0:
                            continue
                        
                        glow_surface.blit(
                            temp_mask, 
                            (pad_left + dx, pad_top + dy), 
                            special_flags=pygame.BLEND_RGBA_MAX
                        )
        
        glow_surface.blit(surface, (pad_left, pad_top))
        
        return glow_surface
    
    def _shuffle_queue(self):
        self.shuffled_queue = self.image_paths.copy()
        random.shuffle(self.shuffled_queue)
        self.current_index = 0
    
    def _get_next_image_path(self):
        if not self.shuffled_queue:
            return None
        
        if self.current_index >= len(self.shuffled_queue):
            self._shuffle_queue()
        
        path = self.shuffled_queue[self.current_index]
        self.current_index += 1
        return path
    
    def _load_and_scale_image(self, image_path, transition_type='pan'):
        if image_path is None:
            return None, (0, 0), None
        
        try:
            image = pygame.image.load(image_path).convert_alpha()
            img_width, img_height = image.get_size()
            
            if transition_type == 'perspective' or transition_type == 'zoom':
                scale = min(self.draw_width / img_width, self.draw_height / img_height)
                pan_direction = 'none'
            else:
                scale_w = self.draw_width / img_width
                scale_h = self.draw_height / img_height
                
                if scale_w < scale_h:
                    scale = (self.draw_width + self.pan_overflow) / img_width
                    pan_direction = 'horizontal'
                else:
                    scale = (self.draw_height + self.pan_overflow) / img_height
                    pan_direction = 'vertical'
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            scaled_image = pygame.transform.smoothscale(image, (new_width, new_height))
            
            if transition_type == 'perspective' or transition_type == 'zoom':
                glowed_image = self._create_glow_surface(scaled_image, self.glow_size, self.glow_intensity, 'none')
            else:
                glowed_image = self._create_glow_surface(scaled_image, self.glow_size, self.glow_intensity, pan_direction)
            
            final_width, final_height = glowed_image.get_size()
            image_data = pygame.image.tostring(glowed_image, "RGBA", True)
            
            texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, final_width, final_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
            
            return texture_id, (final_width, final_height), pan_direction
        
        except:
            return None, (0, 0), None
    
    def _generate_pan_points(self, size, pan_direction):
        if size[0] == 0 or size[1] == 0:
            return (0, 0), (0, 0)
        
        overflow_x = max(0, size[0] - self.draw_width)
        overflow_y = max(0, size[1] - self.draw_height)
        
        if pan_direction == 'horizontal':
            start_x = 0 if random.random() < 0.5 else overflow_x
            end_x = overflow_x if start_x == 0 else 0
            center_y = overflow_y / 2
            start_y = center_y
            end_y = center_y
        else:
            center_x = overflow_x / 2
            start_x = center_x
            end_x = center_x
            start_y = 0 if random.random() < 0.5 else overflow_y
            end_y = overflow_y if start_y == 0 else 0
        
        return (start_x, start_y), (end_x, end_y)
    
    def _generate_perspective_params(self):
        direction = random.choice(['horizontal', 'vertical'])
        
        if random.random() < 0.5:
            start = -self.perspective_intensity
            end = self.perspective_intensity
        else:
            start = self.perspective_intensity
            end = -self.perspective_intensity
        
        return direction, start, end
    
    def _generate_zoom_params(self):
        if random.random() < 0.5:
            return self.zoom_min, self.zoom_max
        else:
            return self.zoom_max, self.zoom_min
    
    def _load_next_image(self):
        max_attempts = min(10, len(self.image_paths)) if self.image_paths else 0
        
        for _ in range(max_attempts):
            path = self._get_next_image_path()
            if not path:
                break
                
            self.next_transition_type = random.choice(['pan', 'perspective', 'zoom'])
            
            texture, size, pan_direction = self._load_and_scale_image(path, transition_type=self.next_transition_type)
            if texture is not None:
                if self.next_texture is not None:
                    glDeleteTextures([self.next_texture])
                
                self.next_texture = texture
                self.next_size = size
                
                if self.next_transition_type == 'pan':
                    self.next_pan_start, self.next_pan_end = self._generate_pan_points(size, pan_direction)
                elif self.next_transition_type == 'perspective':
                    self.next_perspective_direction, self.next_perspective_start, self.next_perspective_end = self._generate_perspective_params()
                else:
                    self.next_zoom_start, self.next_zoom_end = self._generate_zoom_params()
                return
        
        self.next_texture = None
    
    def reset(self):
        if self.current_texture is not None:
            glDeleteTextures([self.current_texture])
            self.current_texture = None
        if self.next_texture is not None:
            glDeleteTextures([self.next_texture])
            self.next_texture = None
        
        self._load_image_list()
        self._load_background()
        self._shuffle_queue()
        
        self.transitioning = False
        self.transition_alpha = 0.0
        self.last_switch_time = time.time()
        
        if self.image_paths:
            path = self._get_next_image_path()
            
            self.transition_type = random.choice(['pan', 'perspective', 'zoom'])
            
            texture, size, pan_direction = self._load_and_scale_image(path, transition_type=self.transition_type)
            self.current_texture = texture
            self.current_size = size
            
            if self.transition_type == 'pan':
                self.pan_start, self.pan_end = self._generate_pan_points(size, pan_direction)
            elif self.transition_type == 'perspective':
                self.perspective_direction, self.perspective_start, self.perspective_end = self._generate_perspective_params()
            else:
                self.zoom_start, self.zoom_end = self._generate_zoom_params()
            
            self._load_next_image()
    
    def update(self, delta_time=None):
        if not self.image_paths:
            return
        
        current_time = time.time()
        elapsed = current_time - self.last_switch_time
        
        if self.transitioning:
            self.transition_alpha = min(1.0, (elapsed - self.display_duration) / self.transition_duration)
            
            if self.transition_alpha >= 1.0:
                if self.current_texture is not None:
                    glDeleteTextures([self.current_texture])
                
                self.current_texture = self.next_texture
                self.current_size = self.next_size
                self.transition_type = self.next_transition_type
                self.pan_start = self.next_pan_start
                self.pan_end = self.next_pan_end
                self.perspective_direction = self.next_perspective_direction
                self.perspective_start = self.next_perspective_start
                self.perspective_end = self.next_perspective_end
                self.zoom_start = self.next_zoom_start
                self.zoom_end = self.next_zoom_end
                self.next_texture = None
                self.transitioning = False
                self.last_switch_time = current_time - self.transition_duration
                self._load_next_image()
        
        elif elapsed >= self.display_duration:
            if self.next_texture is not None:
                self.transitioning = True
                self.transition_alpha = 0.0
            else:
                self._load_next_image()
                if self.next_texture is not None:
                    self.transitioning = True
                    self.transition_alpha = 0.0
                else:
                    self.last_switch_time = current_time
    
    def _smooth_progress(self, progress):
        progress = max(0.0, min(1.0, progress))
        return progress * progress * (3 - 2 * progress)
    
    def _draw_quad(self, texture, x, y, width, height, alpha=1.0):
        glBindTexture(GL_TEXTURE_2D, texture)
        glColor4f(1.0, 1.0, 1.0, alpha)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + width, y)
        glTexCoord2f(1, 1); glVertex2f(x + width, y + height)
        glTexCoord2f(0, 1); glVertex2f(x, y + height)
        glEnd()
    
    def _draw_panned(self, texture, size, pan_start, pan_end, progress, alpha=1.0):
        smooth = self._smooth_progress(progress)
        
        offset_x = pan_start[0] + (pan_end[0] - pan_start[0]) * smooth
        offset_y = pan_start[1] + (pan_end[1] - pan_start[1]) * smooth
        
        visible_w = min(self.draw_width, size[0])
        visible_h = min(self.draw_height, size[1])
        
        screen_x = (self.draw_width - visible_w) / 2
        screen_y = (self.draw_height - visible_h) / 2
        
        tex_left = offset_x / size[0]
        tex_right = (offset_x + visible_w) / size[0]
        tex_bottom = offset_y / size[1]
        tex_top = (offset_y + visible_h) / size[1]
        
        glBindTexture(GL_TEXTURE_2D, texture)
        glColor4f(1.0, 1.0, 1.0, alpha)
        
        glBegin(GL_QUADS)
        glTexCoord2f(tex_left, tex_bottom); glVertex2f(screen_x, screen_y)
        glTexCoord2f(tex_right, tex_bottom); glVertex2f(screen_x + visible_w, screen_y)
        glTexCoord2f(tex_right, tex_top); glVertex2f(screen_x + visible_w, screen_y + visible_h)
        glTexCoord2f(tex_left, tex_top); glVertex2f(screen_x, screen_y + visible_h)
        glEnd()
    
    def _draw_perspective(self, texture, size, direction, start_tilt, end_tilt, progress, alpha=1.0):
        smooth = self._smooth_progress(progress)
        tilt = start_tilt + (end_tilt - start_tilt) * smooth
        
        cx = self.draw_width / 2
        cy = self.draw_height / 2
        hw = size[0] / 2
        hh = size[1] / 2
        
        
        tilt_abs = abs(tilt)
        
        depth_scale = 1.0 - tilt_abs * 0.05
        
        perspective_amount = 0.25
        near_scale = 1.0 + tilt_abs * perspective_amount * 0.4
        far_scale = 1.0 - tilt_abs * perspective_amount * 0.8
        
        hw *= depth_scale
        hh *= depth_scale
        
        if direction == 'horizontal':
            if tilt > 0:
                left_scale = far_scale
                right_scale = near_scale
                shift_x = tilt_abs * hw * 0.08
            else:
                left_scale = near_scale
                right_scale = far_scale
                shift_x = -tilt_abs * hw * 0.08
            
            left_hh = hh * left_scale
            right_hh = hh * right_scale
            
            x0, y0 = cx - hw + shift_x, cy - left_hh
            x1, y1 = cx + hw + shift_x, cy - right_hh
            x2, y2 = cx + hw + shift_x, cy + right_hh
            x3, y3 = cx - hw + shift_x, cy + left_hh
        else:
            if tilt > 0:
                bottom_scale = far_scale
                top_scale = near_scale
                shift_y = tilt_abs * hh * 0.08
            else:
                bottom_scale = near_scale
                top_scale = far_scale
                shift_y = -tilt_abs * hh * 0.08
            
            top_hw = hw * top_scale
            bottom_hw = hw * bottom_scale
            
            x0, y0 = cx - bottom_hw, cy - hh + shift_y
            x1, y1 = cx + bottom_hw, cy - hh + shift_y
            x2, y2 = cx + top_hw, cy + hh + shift_y
            x3, y3 = cx - top_hw, cy + hh + shift_y
        
        glBindTexture(GL_TEXTURE_2D, texture)
        glColor4f(1.0, 1.0, 1.0, alpha)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x0, y0)
        glTexCoord2f(1, 0); glVertex2f(x1, y1)
        glTexCoord2f(1, 1); glVertex2f(x2, y2)
        glTexCoord2f(0, 1); glVertex2f(x3, y3)
        glEnd()
    
    def _draw_zoomed(self, texture, size, start_zoom, end_zoom, progress, alpha=1.0):
        smooth = self._smooth_progress(progress)
        zoom = start_zoom + (end_zoom - start_zoom) * smooth
        
        w = size[0] * zoom
        h = size[1] * zoom
        x = (self.draw_width - w) / 2
        y = (self.draw_height - h) / 2
        
        self._draw_quad(texture, x, y, w, h, alpha)
    
    def render(self):
        if not self.initialized:
            self.initialize()
        
        glViewport(0, 0, self.width, self.height)
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -100, 100)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        glTranslatef(0, self.height, 0)
        glRotatef(-90, 0, 0, 1)
        
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        if self.background_texture is not None:
            tex_id, bg_w, bg_h = self.background_texture
            self._draw_quad(tex_id, 0, 0, self.draw_width, self.draw_height, 1.0)
        
        if not self.image_paths:
            self.clock.tick(30)
            
            if self.show_time and self.time_overlay:
                self.time_overlay.render_gl()
            
            pygame.display.flip()
            return
        
        if self.current_texture is None:
            self.reset()
            if self.current_texture is None:
                self.clock.tick(30)
                
                if self.show_time and self.time_overlay:
                    self.time_overlay.render_gl()
                
                pygame.display.flip()
                return
        
        current_time = time.time()
        elapsed = current_time - self.last_switch_time
        
        total_duration = self.display_duration + self.transition_duration
        current_progress = min(1.0, elapsed / total_duration)
        
        if self.transitioning and self.next_texture is not None:
            current_alpha = 1.0 - self.transition_alpha
            
            if self.transition_type == 'pan':
                self._draw_panned(self.current_texture, self.current_size, 
                                  self.pan_start, self.pan_end, current_progress, current_alpha)
            elif self.transition_type == 'perspective':
                self._draw_perspective(self.current_texture, self.current_size,
                                       self.perspective_direction, self.perspective_start, 
                                       self.perspective_end, current_progress, current_alpha)
            else:
                self._draw_zoomed(self.current_texture, self.current_size,
                                  self.zoom_start, self.zoom_end, current_progress, current_alpha)
            
            next_progress = (elapsed - self.display_duration) / self.display_duration
            next_progress = max(0.0, next_progress)
            next_alpha = self.transition_alpha
            
            if self.next_transition_type == 'pan':
                self._draw_panned(self.next_texture, self.next_size,
                                  self.next_pan_start, self.next_pan_end, next_progress, next_alpha)
            elif self.next_transition_type == 'perspective':
                self._draw_perspective(self.next_texture, self.next_size,
                                       self.next_perspective_direction, self.next_perspective_start,
                                       self.next_perspective_end, next_progress, next_alpha)
            else:
                self._draw_zoomed(self.next_texture, self.next_size,
                                  self.next_zoom_start, self.next_zoom_end, next_progress, next_alpha)
        else:
            progress = elapsed / self.display_duration
            
            if self.transition_type == 'pan':
                self._draw_panned(self.current_texture, self.current_size,
                                  self.pan_start, self.pan_end, progress, 1.0)
            elif self.transition_type == 'perspective':
                self._draw_perspective(self.current_texture, self.current_size,
                                       self.perspective_direction, self.perspective_start,
                                       self.perspective_end, progress, 1.0)
            else:
                self._draw_zoomed(self.current_texture, self.current_size,
                                  self.zoom_start, self.zoom_end, progress, 1.0)
        
        self.clock.tick(30)
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()
        
        pygame.display.flip()
    
    def cleanup(self):
        if self.current_texture is not None:
            glDeleteTextures([self.current_texture])
            self.current_texture = None
        if self.next_texture is not None:
            glDeleteTextures([self.next_texture])
            self.next_texture = None
        if self.background_texture is not None:
            glDeleteTextures([self.background_texture[0]])
            self.background_texture = None
        
        self.initialized = False
        
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glColor4f(1.0, 1.0, 1.0, 1.0)