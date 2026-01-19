"""
# atomikspace (discord)
# olivierdion1@hotmail.com
"""

import pygame
import math
import random

class FaceAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.animation_time = 0
        self.sleep_state = "sleeping"
        self.state_timer = 0
        self.left_eye_open = 0.0
        self.right_eye_open = 0.0
        self.next_event = random.uniform(5, 15)
        self.event_type = "wake"
        self.left_eye_target_scale = 1.0
        self.right_eye_target_scale = 1.0
        self.left_eye_current_scale = 1.0
        self.right_eye_current_scale = 1.0
        self.look_direction = 0
        self.look_phase = 0
        self.eye_offset_x = 0
        self.target_eye_offset_x = 0
        self.head_turn_offset = 0
        self.target_head_turn_offset = 0
        self.mouth_offset_y = 0
        self.target_mouth_offset_y = 0
        self.drool_drops = []
        self.drool_timer = 0
        self._z_surfaces_cache = {}
        self._shadow_cache = {}
        self._drool_cache = {}
        self._max_cache_size = 20

    def reset(self):
        self.animation_time = 0
        self.sleep_state = "sleeping"
        self.left_eye_open = 0.0
        self.right_eye_open = 0.0
        self.state_timer = 0
        self.next_event = random.uniform(5, 15)
        self.drool_drops = []
        self.look_direction = 0
        self.look_phase = 0
        self.left_eye_current_scale = 1.0
        self.right_eye_current_scale = 1.0
        self.left_eye_target_scale = 1.0
        self.right_eye_target_scale = 1.0
        self.eye_offset_x = 0
        self.target_eye_offset_x = 0
        self.mouth_offset_y = 0
        self.target_mouth_offset_y = 0
        self.head_turn_offset = 0
        self.target_head_turn_offset = 0

    def _get_cached_z_surface(self, size, char):
        key = (size, char)
        if key not in self._z_surfaces_cache:
            if len(self._z_surfaces_cache) >= self._max_cache_size:
                self._z_surfaces_cache.clear()
            font = pygame.font.Font(None, size)
            self._z_surfaces_cache[key] = font.render(char, True, (100, 150, 200))
        return self._z_surfaces_cache[key]

    def _get_cached_shadow(self, width, height, border_radius):
        key = (width, height, border_radius)
        if key not in self._shadow_cache:
            if len(self._shadow_cache) >= self._max_cache_size:
                self._shadow_cache.clear()
            shadow_surface = pygame.Surface((width + 10, height + 10), pygame.SRCALPHA)
            shadow_rect = pygame.Rect(5, 5, width, height)
            pygame.draw.rect(shadow_surface, (0, 150, 140, 80), shadow_rect, border_radius=border_radius)
            self._shadow_cache[key] = shadow_surface
        return self._shadow_cache[key]

    def _get_cached_drool_drop(self, size):
        if size not in self._drool_cache:
            if len(self._drool_cache) >= self._max_cache_size:
                self._drool_cache.clear()
            drop_surface = pygame.Surface((size * 2, size * 3), pygame.SRCALPHA)
            pygame.draw.ellipse(drop_surface, (100, 150, 200, 180), (0, 0, size * 2, size * 3))
            self._drool_cache[size] = drop_surface
        return self._drool_cache[size]

    def smooth_transition(self, current, target, speed=0.1):
        diff = target - current
        if abs(diff) < 0.01:
            return target
        return current + diff * speed

    def update(self):
        self.state_timer += 0.016
        self.left_eye_current_scale = self.smooth_transition(self.left_eye_current_scale, self.left_eye_target_scale, 0.15)
        self.right_eye_current_scale = self.smooth_transition(self.right_eye_current_scale, self.right_eye_target_scale, 0.15)
        self.eye_offset_x = self.smooth_transition(self.eye_offset_x, self.target_eye_offset_x, 0.1)
        self.head_turn_offset = self.smooth_transition(self.head_turn_offset, self.target_head_turn_offset, 0.08)
        self.mouth_offset_y = self.smooth_transition(self.mouth_offset_y, self.target_mouth_offset_y, 0.12)
        
        if self.sleep_state == "sleeping":
            if self.left_eye_open > 0:
                self.left_eye_open = max(0, self.left_eye_open - 0.02)
            if self.right_eye_open > 0:
                self.right_eye_open = max(0, self.right_eye_open - 0.02)
            self.left_eye_target_scale = 1.0
            self.right_eye_target_scale = 1.0
            self.target_eye_offset_x = 0
            self.target_mouth_offset_y = 0
            self.target_head_turn_offset = 0
            if self.state_timer >= self.next_event:
                rand = random.random()
                if rand < 0.4:
                    self.event_type = "wake"
                    self.sleep_state = "waking"
                elif rand < 0.7:
                    self.event_type = "one_eye"
                    self.sleep_state = "one_eye_open"
                else:
                    self.event_type = "look_around"
                    self.sleep_state = "looking_around"
                    self.look_phase = 0
                    self.look_direction = 0
                self.state_timer = 0
        elif self.sleep_state == "waking":
            self.left_eye_open = min(0.6, self.left_eye_open + 0.04)
            self.right_eye_open = min(0.6, self.right_eye_open + 0.04)
            self.target_mouth_offset_y = -2
            if self.state_timer >= 1.0:
                self.sleep_state = "back_to_sleep"
                self.state_timer = 0
        elif self.sleep_state == "one_eye_open":
            if self.state_timer < 0.1:
                if random.random() < 0.5:
                    self.left_eye_open = min(0.7, self.left_eye_open + 0.05)
                    self.right_eye_open = max(0, self.right_eye_open - 0.03)
                else:
                    self.right_eye_open = min(0.7, self.right_eye_open + 0.05)
                    self.left_eye_open = max(0, self.left_eye_open - 0.03)
            self.target_mouth_offset_y = -1
            if self.state_timer >= 1.5:
                self.sleep_state = "back_to_sleep"
                self.state_timer = 0
        elif self.sleep_state == "looking_around":
            if self.look_phase == 0:
                self.left_eye_open = min(0.8, self.left_eye_open + 0.05)
                self.right_eye_open = min(0.8, self.right_eye_open + 0.05)
                self.target_mouth_offset_y = -3
                if self.state_timer >= 0.5:
                    self.look_phase = 1
                    self.state_timer = 0
            elif self.look_phase == 1:
                self.look_direction = -1
                self.left_eye_target_scale = 1.3
                self.right_eye_target_scale = 0.8
                self.target_eye_offset_x = -8
                self.target_mouth_offset_y = -2
                self.target_head_turn_offset = -25
                if self.state_timer >= 1.0:
                    self.look_phase = 2
                    self.state_timer = 0
            elif self.look_phase == 2:
                self.look_direction = 0
                self.left_eye_target_scale = 1.0
                self.right_eye_target_scale = 1.0
                self.target_eye_offset_x = 0
                self.target_mouth_offset_y = -3
                self.target_head_turn_offset = 0
                if self.state_timer >= 0.5:
                    self.look_phase = 3
                    self.state_timer = 0
            elif self.look_phase == 3:
                self.look_direction = 1
                self.left_eye_target_scale = 0.8
                self.right_eye_target_scale = 1.3
                self.target_eye_offset_x = 8
                self.target_mouth_offset_y = -2
                self.target_head_turn_offset = 25
                if self.state_timer >= 1.0:
                    self.look_phase = 4
                    self.state_timer = 0
            elif self.look_phase == 4:
                self.look_direction = 0
                self.left_eye_target_scale = 1.0
                self.right_eye_target_scale = 1.0
                self.target_eye_offset_x = 0
                self.target_mouth_offset_y = -3
                self.target_head_turn_offset = 0
                if self.state_timer >= 0.5:
                    self.sleep_state = "back_to_sleep"
                    self.state_timer = 0
        elif self.sleep_state == "back_to_sleep":
            self.left_eye_open = max(0, self.left_eye_open - 0.03)
            self.right_eye_open = max(0, self.right_eye_open - 0.03)
            self.target_mouth_offset_y = 0
            if self.left_eye_open <= 0 and self.right_eye_open <= 0:
                self.sleep_state = "sleeping"
                self.state_timer = 0
                self.next_event = random.uniform(5, 15)
                self.look_direction = 0

        self._update_drool()

    def _update_drool(self):
        self.drool_timer += 0.016
        if self.sleep_state == "sleeping" and random.random() < 0.0006:
            mouth_x = self.width // 2 + 15
            mouth_y = self.height // 2 - 125 + 35 + int(self.mouth_offset_y)
            self.drool_drops.append({
                'x': mouth_x,
                'y': mouth_y,
                'start_y': mouth_y,
                'speed': random.uniform(0.3, 0.6),
                'size': random.randint(2, 4),
                'retracting': False,
                'bobbing': 0
            })
        if self.sleep_state != "sleeping":
            for drop in self.drool_drops:
                drop['retracting'] = True
        for drop in self.drool_drops[:]:
            if drop['retracting']:
                drop['y'] -= drop['speed'] * 1.5
                if drop['y'] <= drop['start_y']:
                    self.drool_drops.remove(drop)
            else:
                drop['bobbing'] += 0.05
                bobbing_offset = math.sin(drop['bobbing']) * 0.5
                drop['y'] += drop['speed'] + bobbing_offset
                if drop['y'] > self.height // 2 - 25:
                    drop['retracting'] = True

    def render(self):
        self.screen.fill((0, 0, 0))
        center_x = self.width // 2
        center_y = self.height // 2 - 125
        head_offset = int(self.head_turn_offset)
        self.animation_time += 0.02
        breathe = 1 + 0.02 * math.sin(self.animation_time)
        eye_y_base = center_y - 10
        eye_spacing = 45
        eye_base_width = 50
        eye_base_height = 60
        eye_color = (0, 255, 220)
        left_eye_height = int(eye_base_height * (0.15 + 0.85 * self.left_eye_open) * self.left_eye_current_scale)
        left_eye_width = int(eye_base_width * breathe * self.left_eye_current_scale)
        right_eye_height = int(eye_base_height * (0.15 + 0.85 * self.right_eye_open) * self.right_eye_current_scale)
        right_eye_width = int(eye_base_width * breathe * self.right_eye_current_scale)
        left_closed_height = int(eye_base_height * 0.15 * self.left_eye_current_scale)
        right_closed_height = int(eye_base_height * 0.15 * self.right_eye_current_scale)
        left_bottom_edge = eye_y_base + left_closed_height // 2
        right_bottom_edge = eye_y_base + right_closed_height // 2
        left_eye_y = left_bottom_edge - left_eye_height // 2
        right_eye_y = right_bottom_edge - right_eye_height // 2
        left_eye_x = center_x - eye_spacing + int(self.eye_offset_x) + head_offset
        self._draw_rounded_rect_eye(left_eye_x, left_eye_y, left_eye_width, left_eye_height, eye_color, self.left_eye_open)
        right_eye_x = center_x + eye_spacing + int(self.eye_offset_x) + head_offset
        self._draw_rounded_rect_eye(right_eye_x, right_eye_y, right_eye_width, right_eye_height, eye_color, self.right_eye_open)
        mouth_y = center_y + 35 + int(self.mouth_offset_y)
        mouth_color = (100, 100, 120)
        pygame.draw.line(self.screen, mouth_color, (center_x - 20 + head_offset, mouth_y), (center_x + 20 + head_offset, mouth_y), 3)
        if self.drool_drops:
            self._draw_drool(center_y, head_offset)
        if self.sleep_state in ["sleeping", "waking", "one_eye_open", "back_to_sleep"]:
            self._draw_sleeping_z(center_x, center_y, head_offset)

    def _draw_rounded_rect_eye(self, center_x, center_y, width, height, color, open_amount):
        x = center_x - width // 2
        y = center_y - height // 2
        border_radius = min(width, height) // 3
        if open_amount > 0.1:
            shadow_offset = 4
            shadow_surface = self._get_cached_shadow(width, height, border_radius)
            self.screen.blit(shadow_surface, (x - 5 + shadow_offset, y - 5 + shadow_offset))
        eye_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, color, eye_rect, border_radius=border_radius)

    def _draw_drool(self, center_y, head_offset):
        for drop in self.drool_drops:
            drop_surface = self._get_cached_drool_drop(drop['size'])
            self.screen.blit(drop_surface, (drop['x'] - drop['size'] + head_offset, drop['y'] - drop['size']))
        if self.drool_drops:
            mouth_x = self.width // 2 + 15 + head_offset
            mouth_y = center_y + 35 + int(self.mouth_offset_y)
            first_drop = self.drool_drops[0]
            distance = abs(first_drop['y'] - mouth_y)
            if distance > 2:
                alpha = min(100, int(100 * (distance / 50)))
                pygame.draw.line(self.screen, (100, 150, 200, alpha), (mouth_x, mouth_y), (int(first_drop['x'] + head_offset), int(first_drop['y'])), 2)

    def _draw_sleeping_z(self, center_x, center_y, head_offset):
        float_offset1 = 15 * math.sin(self.animation_time * 1.5)
        float_offset2 = 15 * math.sin(self.animation_time * 1.5 + 1)
        float_offset3 = 15 * math.sin(self.animation_time * 1.5 + 2)
        z1_x = center_x + 120 + head_offset
        z1_y = center_y - 60 + float_offset1
        z1_surface = self._get_cached_z_surface(48, "Z").copy()
        alpha1 = int(200 * (1 - abs(float_offset1) / 20))
        z1_surface.set_alpha(alpha1)
        self.screen.blit(z1_surface, (z1_x, z1_y))
        z2_x = center_x + 140 + head_offset
        z2_y = center_y - 90 + float_offset2
        z2_surface = self._get_cached_z_surface(36, "Z").copy()
        alpha2 = int(200 * (1 - abs(float_offset2) / 20))
        z2_surface.set_alpha(alpha2)
        self.screen.blit(z2_surface, (z2_x, z2_y))
        z3_x = center_x + 155 + head_offset
        z3_y = center_y - 115 + float_offset3
        z3_surface = self._get_cached_z_surface(28, "z").copy()
        alpha3 = int(200 * (1 - abs(float_offset3) / 20))
        z3_surface.set_alpha(alpha3)
        self.screen.blit(z3_surface, (z3_x, z3_y))