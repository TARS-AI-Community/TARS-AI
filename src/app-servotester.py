"""
Module: SERVO CONTROLLER GUI - V3.1
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
import sys
import time
import board
import busio
from adafruit_pca9685 import PCA9685
import os

from modules.module_config import load_config
import modules.module_config as module_config
import modules.module_servoctl as servoctl
from modules.module_servoctl import *
from modules.module_movement_registry import get_names, get_names_by_type, LEGS_ONLY, HAS_ARMS

pygame.init()

display_info = pygame.display.Info()
display_width = display_info.current_w
display_height = display_info.current_h

REFERENCE_WIDTH = 800
REFERENCE_HEIGHT = 480

max_width = int(display_width * 0.9)
max_height = int(display_height * 0.9)

scale = min(max_width / REFERENCE_WIDTH, max_height / REFERENCE_HEIGHT, 1.0)
WINDOW_WIDTH = int(REFERENCE_WIDTH * scale)
WINDOW_HEIGHT = int(REFERENCE_HEIGHT * scale)

print(f"[UI] Screen: {display_width}x{display_height}, Window: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")

BLACK = (0, 0, 0)
DARK_BG = (15, 15, 18)
MID_DARK = (25, 25, 30)
PANEL_BG = (20, 22, 25)
BORDER_COLOR = (60, 65, 70)
WHITE = (240, 245, 250)
GRAY = (100, 105, 110)
LIGHT_GRAY = (140, 145, 150)
ACCENT_BLUE = (0, 150, 200)
ACCENT_BLUE_DARK = (0, 100, 150)
ACCENT_GREEN = (120, 200, 150)
ACCENT_GREEN_DARK = (80, 160, 110)
ACCENT_RED = (220, 90, 80)
ACCENT_RED_DARK = (180, 60, 50)
ACCENT_AMBER = (255, 180, 50)
TEXT_PRIMARY = (230, 235, 240)
TEXT_SECONDARY = (150, 155, 160)

def scale_font(base_size):
    scale_factor = min(WINDOW_WIDTH / REFERENCE_WIDTH, WINDOW_HEIGHT / REFERENCE_HEIGHT)
    return int(base_size * scale_factor)

def get_fonts():
    return {
        'title': pygame.font.Font(None, scale_font(32)),
        'tab': pygame.font.Font(None, scale_font(22)),
        'button': pygame.font.Font(None, scale_font(20)),
        'label': pygame.font.Font(None, scale_font(18)),
        'small': pygame.font.Font(None, scale_font(16)),
        'direction': pygame.font.Font(None, scale_font(48))  
    }

def scale_x(x):
    return int(x * WINDOW_WIDTH / REFERENCE_WIDTH)

def scale_y(y):
    return int(y * WINDOW_HEIGHT / REFERENCE_HEIGHT)

def scale_size(width, height):
    return scale_x(width), scale_y(height)

config = load_config()
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50
servoctl.pca = pca

global_speed = 1.0
MIN_PULSE = 0
MAX_PULSE = 600
servo_positions = {i: (MIN_PULSE + MAX_PULSE) // 2 for i in range(16)}

servo_config = config.get('SERVO', {})
offset_values = {
    'perfectLeftHeightOffset': int(servo_config.get('perfectLeftHeightOffset', 0)),
    'perfectRightHeightOffset': int(servo_config.get('perfectRightHeightOffset', 0)),
    'perfectLeftLegOffset': int(servo_config.get('perfectLeftLegOffset', 0)),
    'perfectRightLegOffset': int(servo_config.get('perfectRightLegOffset', 0)),
    'leftMainOffset': int(servo_config.get('leftMainOffset', 0)),
    'leftForearmOffset': int(servo_config.get('leftForearmOffset', 0)),
    'leftHandOffset': int(servo_config.get('leftHandOffset', 0)),
    'rightMainOffset': int(servo_config.get('rightMainOffset', 0)),
    'rightForearmOffset': int(servo_config.get('rightForearmOffset', 0)),
    'rightHandOffset': int(servo_config.get('rightHandOffset', 0))
}

def pulse_to_duty_cycle(pulse):
    pulse_us = 500 + (pulse / MAX_PULSE) * 2000
    duty_cycle = int((pulse_us / 20000.0) * 65535)
    return duty_cycle

def set_servo_pulse(channel, target_pulse):
    if MIN_PULSE <= target_pulse <= MAX_PULSE:
        current_pulse = servo_positions.get(channel, (MIN_PULSE + MAX_PULSE) // 2)
        step = 1 if target_pulse > current_pulse else -1

        for pulse in range(current_pulse, target_pulse + step, step):
            duty = pulse_to_duty_cycle(pulse)
            pca.channels[channel].duty_cycle = duty
            time.sleep(0.02 * (1.0 - global_speed))

        servo_positions[channel] = target_pulse
    else:
        print(f"Pulse out of range ({MIN_PULSE}-{MAX_PULSE}).")

def set_all_servos_preset():
    set_servo_pulse(0, 350)
    set_servo_pulse(1, 350)
    set_servo_pulse(2, 300)
    set_servo_pulse(3, 300)

    set_servo_pulse(4, 550)  
    set_servo_pulse(5, 500)  
    set_servo_pulse(6, 420)  

    set_servo_pulse(7, 50)   
    set_servo_pulse(8, 230)  
    set_servo_pulse(9, 300)  

    print("OK Preset applied - Servos under power")
    return "OK Preset applied - Servos under power"

def disable_all_servos():
    for ch in range(16):
        pca.channels[ch].duty_cycle = 0
        time.sleep(0.05)
    print("OK Servos disabled")
    return "OK Servos disabled"

def save_offset_to_config(offset_name, value):
    possible_paths = [
        'config.ini',
        '../config.ini',
        os.path.join(os.path.dirname(__file__), 'config.ini'),
        os.path.join(os.path.dirname(__file__), '..', 'config.ini')
    ]

    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break

    if config_path is None:
        print(f"Error: Config file not found. Searched: {possible_paths}")
        return False

    with open(config_path, 'r') as f:
        lines = f.readlines()

    in_servo_section = False
    updated = False

    for i, line in enumerate(lines):

        if line.strip().startswith('[SERVO]'):
            in_servo_section = True
            continue

        if in_servo_section and line.strip().startswith('['):
            in_servo_section = False

        if in_servo_section and line.strip().startswith(offset_name):

            if '#' in line:

                comment_part = '#' + line.split('#', 1)[1]
                lines[i] = f"{offset_name} = {value}  {comment_part}"
            else:
                lines[i] = f"{offset_name} = {value}\n"
            updated = True
            break

    if not updated:
        for i, line in enumerate(lines):
            if line.strip().startswith('[SERVO]'):

                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('['):
                    j += 1

                lines.insert(j, f"{offset_name} = {value}\n")
                break

    with open(config_path, 'w') as f:
        f.writelines(lines)

    module_config._config_cache = None

    return True

def reload_and_test():
    try:
        global config
        config = load_config()
        servoctl.refresh_config()

        globals().update({name: getattr(servoctl, name) for name in dir(servoctl) if not name.startswith('_')})

        reset_positions()
        return True
    except Exception as e:
        print(f"! Error during reload/test: {e}")
        return False

class Button:
    def __init__(self, x, y, width, height, text, color, hover_color, text_color=TEXT_PRIMARY, font_key='button', arrow_dir=None):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.font_key = font_key
        self.arrow_dir = arrow_dir
        self.is_hovered = False
        self.update_rect()

    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        width = scale_x(self.width_ref)
        height = scale_y(self.height_ref)
        self.rect = pygame.Rect(x, y, width, height)

    def draw(self, screen, fonts):
        self.update_rect()
        color = self.hover_color if self.is_hovered else self.color

        pygame.draw.rect(screen, color, self.rect)

        pygame.draw.rect(screen, BORDER_COLOR, self.rect, 2)

        corner_size = scale_x(6)
        corner_color = TEXT_PRIMARY

        pygame.draw.line(screen, corner_color, 
                        (self.rect.left + 2, self.rect.top + 2), 
                        (self.rect.left + 2, self.rect.top + corner_size), 2)
        pygame.draw.line(screen, corner_color, 
                        (self.rect.left + 2, self.rect.top + 2), 
                        (self.rect.left + corner_size, self.rect.top + 2), 2)

        pygame.draw.line(screen, corner_color, 
                        (self.rect.right - 3, self.rect.top + 2), 
                        (self.rect.right - 3, self.rect.top + corner_size), 2)
        pygame.draw.line(screen, corner_color, 
                        (self.rect.right - 3, self.rect.top + 2), 
                        (self.rect.right - corner_size, self.rect.top + 2), 2)

        pygame.draw.line(screen, corner_color, 
                        (self.rect.left + 2, self.rect.bottom - 3), 
                        (self.rect.left + 2, self.rect.bottom - corner_size), 2)
        pygame.draw.line(screen, corner_color, 
                        (self.rect.left + 2, self.rect.bottom - 3), 
                        (self.rect.left + corner_size, self.rect.bottom - 3), 2)

        pygame.draw.line(screen, corner_color, 
                        (self.rect.right - 3, self.rect.bottom - 3), 
                        (self.rect.right - 3, self.rect.bottom - corner_size), 2)
        pygame.draw.line(screen, corner_color, 
                        (self.rect.right - 3, self.rect.bottom - 3), 
                        (self.rect.right - corner_size, self.rect.bottom - 3), 2)

        if self.arrow_dir:
            cx = self.rect.centerx
            cy = self.rect.centery
            size = min(self.rect.width, self.rect.height) // 3

            if self.arrow_dir == 'up':
                points = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
            elif self.arrow_dir == 'down':
                points = [(cx, cy + size), (cx - size, cy - size), (cx + size, cy - size)]
            elif self.arrow_dir == 'left':
                points = [(cx - size, cy), (cx + size, cy - size), (cx + size, cy + size)]
            elif self.arrow_dir == 'right':
                points = [(cx + size, cy), (cx - size, cy - size), (cx - size, cy + size)]

            pygame.draw.polygon(screen, self.text_color, points)
        else:
            font = fonts.get(self.font_key, fonts['button'])
            text_surf = font.render(self.text, True, self.text_color)
            text_rect = text_surf.get_rect(center=self.rect.center)
            screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_hovered:
                return True
        return False

class Tab:
    def __init__(self, x, y, width, height, text):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.text = text
        self.active = False
        self.update_rect()

    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        width = scale_x(self.width_ref)
        height = scale_y(self.height_ref)
        self.rect = pygame.Rect(x, y, width, height)

    def draw(self, screen, fonts):
        self.update_rect()

        color = (0, 150, 200) if self.active else MID_DARK

        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, BORDER_COLOR, self.rect, 2)

        if self.active:
            pygame.draw.line(screen, TEXT_PRIMARY,
                           (self.rect.left, self.rect.bottom - 2),
                           (self.rect.right, self.rect.bottom - 2), 3)

        text_color = TEXT_PRIMARY if self.active else TEXT_SECONDARY
        text_surf = fonts['tab'].render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                return True
        return False

class InputBox:
    def __init__(self, x, y, width, height, label, default_value=""):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.label = label
        self.text = default_value
        self.active = False
        self.update_rect()

    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        width = scale_x(self.width_ref)
        height = scale_y(self.height_ref)
        self.rect = pygame.Rect(x, y, width, height)

    def draw(self, screen, fonts):
        self.update_rect()

        label_surf = fonts['label'].render(self.label, True, TEXT_SECONDARY)
        screen.blit(label_surf, (self.rect.x, self.rect.y - scale_y(25)))

        bg_color = MID_DARK if self.active else PANEL_BG
        border_color = ACCENT_BLUE if self.active else BORDER_COLOR

        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, border_color, self.rect, 2)

        text_surf = fonts['label'].render(self.text, True, TEXT_PRIMARY)
        screen.blit(text_surf, (self.rect.x + scale_x(8), self.rect.y + scale_y(8)))

    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                return self.text
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode.isdigit() or event.unicode == '-':
                self.text += event.unicode
        return None

class Checkbox:
    
    def __init__(self, x, y, size, label, checked=False):
        self.x_ref = x
        self.y_ref = y
        self.size_ref = size
        self.label = label
        self.checked = checked
        self.update_rect()
    
    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        size = scale_x(self.size_ref)
        self.rect = pygame.Rect(x, y, size, size)
    
    def draw(self, screen, fonts):
        self.update_rect()
        
        pygame.draw.rect(screen, PANEL_BG, self.rect)
        pygame.draw.rect(screen, ACCENT_BLUE if self.checked else BORDER_COLOR, self.rect, 2)
        
        if self.checked:
            inner_rect = self.rect.inflate(-scale_x(6), -scale_y(6))
            pygame.draw.rect(screen, ACCENT_GREEN, inner_rect)
        
        label_surf = fonts['small'].render(self.label, True, TEXT_PRIMARY)
        screen.blit(label_surf, (self.rect.right + scale_x(8), self.rect.centery - label_surf.get_height() // 2))
    
    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEBUTTONDOWN:
            label_width = scale_x(200)
            click_area = pygame.Rect(self.rect.x, self.rect.y, self.rect.width + label_width, self.rect.height)
            if click_area.collidepoint(event.pos):
                self.checked = not self.checked
                return True
        return False

class CompactInputBox:
    
    def __init__(self, x, y, width, height, default_value="50"):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.text = default_value
        self.active = False
        self.update_rect()

    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        width = scale_x(self.width_ref)
        height = scale_y(self.height_ref)
        self.rect = pygame.Rect(x, y, width, height)

    def draw(self, screen, fonts):
        self.update_rect()

        bg_color = MID_DARK if self.active else PANEL_BG
        border_color = ACCENT_BLUE if self.active else BORDER_COLOR

        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, border_color, self.rect, 2)

        text_surf = fonts['small'].render(self.text, True, TEXT_PRIMARY)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                self.active = False
                return self.text
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode.isdigit():
                if len(self.text) < 3:
                    self.text += event.unicode
        return None
    
    def get_value(self):
        
        try:
            val = int(self.text) if self.text else 50
            return max(1, min(100, val))
        except ValueError:
            return 50

class Slider:
    def __init__(self, x, y, width, height, min_val=0.65, max_val=1.0, default=0.8):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.min_val = min_val
        self.max_val = max_val
        self.value = default
        self.dragging = False
        self.update_rect()
    
    def update_rect(self):
        self.rect = pygame.Rect(scale_x(self.x_ref), scale_y(self.y_ref), 
                                scale_x(self.width_ref), scale_y(self.height_ref))
    
    def draw(self, screen, fonts):
        self.update_rect()
        
        track_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.height // 2 - 2,
                                  self.rect.width, 4)
        pygame.draw.rect(screen, BORDER_COLOR, track_rect)
        
        fill_width = int((self.value - self.min_val) / (self.max_val - self.min_val) * self.rect.width)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.height // 2 - 2,
                                fill_width, 4)
        pygame.draw.rect(screen, ACCENT_BLUE, fill_rect)
        
        handle_x = self.rect.x + fill_width
        handle_rect = pygame.Rect(handle_x - 6, self.rect.y, 12, self.rect.height)
        pygame.draw.rect(screen, ACCENT_BLUE, handle_rect)
        pygame.draw.rect(screen, TEXT_PRIMARY, handle_rect, 1)
    
    def handle_event(self, event):
        self.update_rect()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self._update_value(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_value(event.pos[0])
    
    def _update_value(self, mouse_x):
        relative_x = mouse_x - self.rect.x
        ratio = max(0, min(1, relative_x / self.rect.width))
        self.value = self.min_val + ratio * (self.max_val - self.min_val)

class Dropdown:
    def __init__(self, x, y, width, height, options, max_visible=6):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.options = options
        self.max_visible = max_visible
        self.selected_index = 0
        self.is_open = False
        self.scroll_offset = 0
        self.update_rect()

    def update_rect(self):
        x = scale_x(self.x_ref)
        y = scale_y(self.y_ref)
        width = scale_x(self.width_ref)
        height = scale_y(self.height_ref)
        self.rect = pygame.Rect(x, y, width, height)

    def draw(self, screen, fonts):
        self.update_rect()

        pygame.draw.rect(screen, MID_DARK, self.rect)
        pygame.draw.rect(screen, ACCENT_BLUE, self.rect, 2)

        if self.options:
            text = self.options[self.selected_index][0]
            text_surf = fonts['label'].render(text, True, TEXT_PRIMARY)
            screen.blit(text_surf, (self.rect.x + scale_x(8), self.rect.y + scale_y(8)))

        arrow_x = self.rect.right - scale_x(20)
        arrow_y = self.rect.centery
        arrow_size = scale_x(6)
        points = [(arrow_x, arrow_y - arrow_size), (arrow_x - arrow_size, arrow_y + arrow_size), (arrow_x + arrow_size, arrow_y + arrow_size)]
        pygame.draw.polygon(screen, TEXT_SECONDARY, points)

        if self.is_open and self.options:
            item_height = scale_y(self.height_ref)
            visible_count = min(len(self.options), self.max_visible)

            scroll_button_height = scale_y(20)

            if len(self.options) > self.max_visible:
                up_rect = pygame.Rect(self.rect.x, self.rect.y + item_height, self.rect.width, scroll_button_height)
                pygame.draw.rect(screen, MID_DARK, up_rect)
                pygame.draw.rect(screen, BORDER_COLOR, up_rect, 1)
                up_arrow_y = up_rect.centery
                up_arrow_x = up_rect.centerx
                up_arrow_size = scale_x(6)
                up_points = [(up_arrow_x, up_arrow_y - up_arrow_size), (up_arrow_x - up_arrow_size, up_arrow_y + up_arrow_size), (up_arrow_x + up_arrow_size, up_arrow_y + up_arrow_size)]
                pygame.draw.polygon(screen, TEXT_SECONDARY, up_points)

                item_start_y = self.rect.y + item_height + scroll_button_height
            else:
                item_start_y = self.rect.y + item_height

            end_index = min(self.scroll_offset + visible_count, len(self.options))
            for i in range(self.scroll_offset, end_index):
                display_index = i - self.scroll_offset
                if len(self.options) > self.max_visible:
                    item_y = item_start_y + display_index * item_height
                else:
                    item_y = self.rect.y + (display_index + 1) * item_height

                item_rect = pygame.Rect(self.rect.x, item_y, self.rect.width, item_height)
                bg_color = ACCENT_BLUE_DARK if i == self.selected_index else PANEL_BG
                pygame.draw.rect(screen, bg_color, item_rect)
                pygame.draw.rect(screen, BORDER_COLOR, item_rect, 1)

                option_text = fonts['label'].render(self.options[i][0], True, TEXT_PRIMARY)
                screen.blit(option_text, (item_rect.x + scale_x(8), item_rect.y + scale_y(8)))

            if len(self.options) > self.max_visible:
                if len(self.options) > self.max_visible:
                    last_item_y = item_start_y + (visible_count - 1) * item_height
                else:
                    last_item_y = self.rect.y + visible_count * item_height

                down_rect = pygame.Rect(self.rect.x, last_item_y + item_height, self.rect.width, scroll_button_height)
                pygame.draw.rect(screen, MID_DARK, down_rect)
                pygame.draw.rect(screen, BORDER_COLOR, down_rect, 1)
                down_arrow_y = down_rect.centery
                down_arrow_x = down_rect.centerx
                down_arrow_size = scale_x(6)
                down_points = [(down_arrow_x, down_arrow_y + down_arrow_size), (down_arrow_x - down_arrow_size, down_arrow_y - down_arrow_size), (down_arrow_x + down_arrow_size, down_arrow_y - down_arrow_size)]
                pygame.draw.polygon(screen, TEXT_SECONDARY, down_points)

    def handle_event(self, event):
        self.update_rect()

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button in [4, 5]:
                return False

            if self.is_open and self.options:
                item_height = scale_y(self.height_ref)
                scroll_button_height = scale_y(20)

                if len(self.options) > self.max_visible:
                    up_rect = pygame.Rect(self.rect.x, self.rect.y + item_height, self.rect.width, scroll_button_height)
                    if up_rect.collidepoint(event.pos):
                        self.scroll_offset = max(0, self.scroll_offset - 1)
                        return False

                    visible_count = min(len(self.options), self.max_visible)
                    item_start_y = self.rect.y + item_height + scroll_button_height
                    last_item_y = item_start_y + (visible_count - 1) * item_height
                    down_rect = pygame.Rect(self.rect.x, last_item_y + item_height, self.rect.width, scroll_button_height)
                    if down_rect.collidepoint(event.pos):
                        max_offset = len(self.options) - self.max_visible
                        self.scroll_offset = min(max_offset, self.scroll_offset + 1)
                        return False

                    end_index = min(self.scroll_offset + visible_count, len(self.options))
                    for i in range(self.scroll_offset, end_index):
                        display_index = i - self.scroll_offset
                        item_y = item_start_y + display_index * item_height
                        item_rect = pygame.Rect(self.rect.x, item_y, self.rect.width, item_height)
                        if item_rect.collidepoint(event.pos):
                            self.selected_index = i
                            self.is_open = False
                            self.scroll_offset = 0
                            return True
                else:
                    for i in range(len(self.options)):
                        item_rect = pygame.Rect(self.rect.x, self.rect.y + (i + 1) * item_height, self.rect.width, item_height)
                        if item_rect.collidepoint(event.pos):
                            self.selected_index = i
                            self.is_open = False
                            return True

            if self.rect.collidepoint(event.pos):
                self.is_open = not self.is_open
                if not self.is_open:
                    self.scroll_offset = 0
                return False
            else:
                self.is_open = False
                self.scroll_offset = 0

        elif event.type == pygame.MOUSEWHEEL and self.is_open:
            mouse_pos = pygame.mouse.get_pos()

            if len(self.options) > self.max_visible:
                item_height = scale_y(self.height_ref)
                scroll_button_height = scale_y(20)
                visible_count = min(len(self.options), self.max_visible)

                dropdown_total_height = item_height + scroll_button_height + (visible_count * item_height) + scroll_button_height
                dropdown_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, dropdown_total_height)

                if dropdown_rect.collidepoint(mouse_pos):
                    if event.y > 0:
                        self.scroll_offset = max(0, self.scroll_offset - 1)
                    else:
                        max_offset = len(self.options) - self.max_visible
                        self.scroll_offset = min(max_offset, self.scroll_offset + 1)
                    return False

        return False

class ServoControllerGUI:
    def __init__(self):
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Servo Controller - V3")
        self.clock = pygame.time.Clock()
        self.running = True
        self.current_tab = 0

        self.fonts = get_fonts()

        self.status_message = "Ready"
        self.status_time = 0

        tab_width = 185
        tab_height = 38
        tab_y = 10
        spacing = 5
        start_x = 20

        self.tabs = [
            Tab(start_x, tab_y, tab_width, tab_height, "Preset Controls"),
            Tab(start_x + tab_width + spacing, tab_y, tab_width, tab_height, "Leg Offsets"),
            Tab(start_x + (tab_width + spacing) * 2, tab_y, tab_width, tab_height, "Arm Offsets"),
            Tab(start_x + (tab_width + spacing) * 3, tab_y, tab_width, tab_height, "Movements")
        ]
        self.tabs[0].active = True

        self.create_tab1_elements()

        self.create_tab2_elements()

        self.create_tab3_elements()

        self.create_tab4_elements()

    def create_tab1_elements(self):
        button_width = 380
        button_height = 50
        start_y = 105
        spacing = 20
        center_x = 400 - button_width // 2  

        self.tab1_buttons = [
            Button(center_x, start_y, button_width, button_height, 
                   "SET ALL SERVOS TO PRESET", ACCENT_BLUE, ACCENT_BLUE_DARK),
            Button(center_x, start_y + (button_height + spacing), button_width, button_height,
                   "DISABLE POWER TO ALL SERVOS", ACCENT_BLUE, ACCENT_BLUE_DARK),
            Button(center_x, start_y + (button_height + spacing) * 2, button_width, button_height,
                   "MANUALLY SET INDIVIDUAL SERVO", ACCENT_BLUE, ACCENT_BLUE_DARK)
        ]

        self.servo_channel_input = InputBox(120, 275, 90, 35, "CHANNEL (0-15):", "0")
        self.servo_pulse_input = InputBox(280, 275, 90, 35, f"PULSE (0-600):", "300")

        self.submit_servo_button = Button(450, 275, 130, 35, "SET SERVO", ACCENT_BLUE, ACCENT_BLUE_DARK)

        self.tab1_mode = "main"  

    def create_tab2_elements(self):
        
        self.leg_offset_info = {
            'perfectLeftHeightOffset': ('LEFT-HEIGHT', 0),
            'perfectRightHeightOffset': ('RIGHT-HEIGHT', 1),
            'perfectLeftLegOffset': ('LEFT-ROTATION', 2),
            'perfectRightLegOffset': ('RIGHT-ROTATION', 3)
        }

        self.selected_leg_offset = 'perfectLeftHeightOffset'

        self.leg_offset_rows = {
            'perfectLeftHeightOffset': 100,
            'perfectRightHeightOffset': 145,
            'perfectLeftLegOffset': 190,
            'perfectRightLegOffset': 235
        }

        btn_width = 38
        btn_height = 32

        self.leg_offset_buttons = {}
        for offset_name, y_pos in self.leg_offset_rows.items():
            self.leg_offset_buttons[offset_name] = {
                'minus5': Button(250, y_pos, btn_width, btn_height, "-5", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'minus1': Button(293, y_pos, btn_width, btn_height, "-1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus1': Button(336, y_pos, btn_width, btn_height, "+1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus5': Button(379, y_pos, btn_width, btn_height, "+5", ACCENT_BLUE, ACCENT_BLUE_DARK)
            }
        
        self.leg_move_inputs = {
            'left_height': CompactInputBox(480, 110, 42, 26, "50"),
            'right_height': CompactInputBox(600, 110, 42, 26, "50"),
            'left_leg': CompactInputBox(480, 155, 42, 26, "50"),
            'right_leg': CompactInputBox(600, 155, 42, 26, "50"),
        }
        
        btn_w = 24
        btn_h = 26
        self.leg_move_adjust_buttons = {
            'left_height': {'minus': Button(446, 110, btn_w, btn_h, "-", ACCENT_BLUE, ACCENT_BLUE_DARK),
                           'plus': Button(534, 110, btn_w, btn_h, "+", ACCENT_BLUE, ACCENT_BLUE_DARK)},
            'right_height': {'minus': Button(566, 110, btn_w, btn_h, "-", ACCENT_BLUE, ACCENT_BLUE_DARK),
                            'plus': Button(654, 110, btn_w, btn_h, "+", ACCENT_BLUE, ACCENT_BLUE_DARK)},
            'left_leg': {'minus': Button(446, 155, btn_w, btn_h, "-", ACCENT_BLUE, ACCENT_BLUE_DARK),
                        'plus': Button(534, 155, btn_w, btn_h, "+", ACCENT_BLUE, ACCENT_BLUE_DARK)},
            'right_leg': {'minus': Button(566, 155, btn_w, btn_h, "-", ACCENT_BLUE, ACCENT_BLUE_DARK),
                         'plus': Button(654, 155, btn_w, btn_h, "+", ACCENT_BLUE, ACCENT_BLUE_DARK)},
        }
        
        self.test_legs_btn = Button(700, 110, 70, 75, "TEST", ACCENT_GREEN, ACCENT_GREEN_DARK)
        
        self.reset_move_btn = Button(700, 110, 60, 28, "RESET", ACCENT_BLUE, ACCENT_BLUE_DARK, TEXT_PRIMARY, 'small')
        
        self.speed_slider = Slider(500, 250, 120, 20, min_val=0.65, max_val=1.0, default=0.8)
        
        self.disable_servos_btn = Button(30, 310, 200, 40, "DISABLE SERVO", ACCENT_RED, ACCENT_RED_DARK, TEXT_PRIMARY, 'small')
        
        self.manual_test_checkbox = Checkbox(30, 365, 16, "MANUAL TEST", checked=False)
        
        self.disable_after_action_checkbox = Checkbox(200, 365, 16, "DISABLE AFTER MOVE", checked=False)

    def create_tab3_elements(self):
        
        self.arm_offset_info = {
            'leftMainOffset': ('LEFT-MAIN', 4),
            'leftForearmOffset': ('LEFT-FOREARM', 5),
            'leftHandOffset': ('LEFT-HAND', 6),
            'rightMainOffset': ('RIGHT-MAIN', 7),
            'rightForearmOffset': ('RIGHT-FOREARM', 8),
            'rightHandOffset': ('RIGHT-HAND', 9)
        }

        self.selected_arm_offset = 'leftMainOffset'

        self.arm_offset_rows = {
            'leftMainOffset': 100,
            'leftForearmOffset': 135,
            'leftHandOffset': 170,
            'rightMainOffset': 205,
            'rightForearmOffset': 240,
            'rightHandOffset': 275
        }

        btn_width = 38
        btn_height = 28

        self.arm_offset_buttons = {}
        for offset_name, y_pos in self.arm_offset_rows.items():
            self.arm_offset_buttons[offset_name] = {
                'minus5': Button(250, y_pos, btn_width, btn_height, "-5", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'minus1': Button(293, y_pos, btn_width, btn_height, "-1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus1': Button(336, y_pos, btn_width, btn_height, "+1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus5': Button(379, y_pos, btn_width, btn_height, "+5", ACCENT_BLUE, ACCENT_BLUE_DARK)
            }
        
        self.arm_move_inputs = {
            'left_main': CompactInputBox(480, 110, 42, 26, "1"),
            'left_forearm': CompactInputBox(480, 140, 42, 26, "1"),
            'left_hand': CompactInputBox(480, 170, 42, 26, "1"),
            'right_main': CompactInputBox(480, 200, 42, 26, "1"),
            'right_forearm': CompactInputBox(480, 230, 42, 26, "1"),
            'right_hand': CompactInputBox(480, 260, 42, 26, "1"),
        }
        
        btn_w = 24
        btn_h = 26
        self.arm_move_adjust_buttons = {}
        for key in self.arm_move_inputs.keys():
            self.arm_move_adjust_buttons[key] = {
                'minus': Button(446, 110, btn_w, btn_h, "-", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus': Button(534, 110, btn_w, btn_h, "+", ACCENT_BLUE, ACCENT_BLUE_DARK)
            }
        
        self.test_arms_btn = Button(700, 110, 70, 75, "TEST", ACCENT_GREEN, ACCENT_GREEN_DARK)
        
        self.reset_arm_move_btn = Button(700, 110, 60, 28, "RESET", ACCENT_BLUE, ACCENT_BLUE_DARK, TEXT_PRIMARY, 'small')
        
        self.arm_speed_slider = Slider(500, 250, 120, 20, min_val=0.65, max_val=1.0, default=0.8)
        
        self.disable_arm_servos_btn = Button(30, 330, 200, 40, "DISABLE SERVO", ACCENT_RED, ACCENT_RED_DARK, TEXT_PRIMARY, 'small')
        
        self.arm_manual_test_checkbox = Checkbox(30, 375, 16, "MANUAL TEST", checked=False)
        
        self.arm_disable_after_action_checkbox = Checkbox(200, 375, 16, "DISABLE AFTER MOVE", checked=False)
        
    def create_tab4_elements(self):
        self.movement_mode = "slow"  

        self.mode_slow_btn = Button(80, 85, 80, 35, "SLOW", ACCENT_BLUE, ACCENT_BLUE_DARK)
        self.mode_fast_btn = Button(180, 85, 80, 35, "FAST", ACCENT_BLUE, ACCENT_BLUE_DARK)

        keypad_center_x = 170
        keypad_center_y = 225
        btn_size = 60
        btn_spacing = 70

        self.move_forward_btn = Button(keypad_center_x - btn_size//2, keypad_center_y - btn_spacing, 
                                        btn_size, btn_size, "", ACCENT_GREEN, ACCENT_GREEN_DARK, TEXT_PRIMARY, 'direction', 'up')
        self.move_backward_btn = Button(keypad_center_x - btn_size//2, keypad_center_y + btn_spacing - btn_size, 
                                         btn_size, btn_size, "", ACCENT_GREEN, ACCENT_GREEN_DARK, TEXT_PRIMARY, 'direction', 'down')
        self.turn_left_btn = Button(keypad_center_x - btn_spacing - btn_size//2, keypad_center_y - btn_size//2, 
                                     btn_size, btn_size, "", ACCENT_GREEN, ACCENT_GREEN_DARK, TEXT_PRIMARY, 'direction', 'left')
        self.turn_right_btn = Button(keypad_center_x + btn_spacing - btn_size//2, keypad_center_y - btn_size//2, 
                                      btn_size, btn_size, "", ACCENT_GREEN, ACCENT_GREEN_DARK, TEXT_PRIMARY, 'direction', 'right')

        self.actions = []
        
        legs_movements = get_names_by_type(LEGS_ONLY)
        for name, func_name in legs_movements:
            self.actions.append((f"{name} [LEGS]", func_name))
        
        arm_movements = get_names_by_type(HAS_ARMS)
        for name, func_name in arm_movements:
            self.actions.append((f"{name} [ARMS]", func_name))

        self.action_dropdown = Dropdown(330, 85, 320, 35, self.actions)
        self.execute_action_btn = Button(660, 85, 105, 35, "EXECUTE", ACCENT_BLUE, ACCENT_BLUE_DARK)

    def set_status(self, message):
        self.status_message = message
        self.status_time = pygame.time.get_ticks()

    def draw_header(self):
        corner_size = scale_x(25)
        thickness = 3

        pygame.draw.line(self.screen, (0, 200, 255), (0, 0), (corner_size, 0), thickness)
        pygame.draw.line(self.screen, (0, 200, 255), (0, 0), (0, corner_size), thickness)

        pygame.draw.line(self.screen, (0, 200, 255), (WINDOW_WIDTH, 0), (WINDOW_WIDTH - corner_size, 0), thickness)
        pygame.draw.line(self.screen, (0, 200, 255), (WINDOW_WIDTH, 0), (WINDOW_WIDTH, corner_size), thickness)

    def draw_status_bar(self):
        status_height = scale_y(40)
        status_rect = pygame.Rect(0, WINDOW_HEIGHT - status_height, WINDOW_WIDTH, status_height)
        pygame.draw.rect(self.screen, PANEL_BG, status_rect)
        pygame.draw.line(self.screen, BORDER_COLOR, (0, WINDOW_HEIGHT - status_height), 
                        (WINDOW_WIDTH, WINDOW_HEIGHT - status_height), 2)

        current_time = pygame.time.get_ticks()
        alpha = max(0, 255 - (current_time - self.status_time) // 10)

        if alpha > 0:
            status_surf = self.fonts['label'].render(self.status_message, True, ACCENT_AMBER)
            status_surf.set_alpha(alpha)
            status_rect_text = status_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT - status_height // 2))
            self.screen.blit(status_surf, status_rect_text)

    def draw_tab1(self):
        if self.tab1_mode == "main":

            for button in self.tab1_buttons:
                button.draw(self.screen, self.fonts)

        elif self.tab1_mode == "manual_servo":

            back_button = Button(40, 65, 90, 32, "BACK", MID_DARK, PANEL_BG, TEXT_PRIMARY, 'label')
            back_button.draw(self.screen, self.fonts)

            title = self.fonts['tab'].render("MANUAL SERVO CONTROL", True, TEXT_PRIMARY)
            title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, scale_y(90)))
            self.screen.blit(title, title_rect)

            info_y = scale_y(120)
            info_lines = [
                "HEIGHT: #0 (LEFT), #1 (RIGHT)  |  LEGS: #2 (LEFT), #3 (RIGHT)",
                "LEFT ARM: #4 (MAIN), #5 (FOREARM), #6 (HAND)",
                "RIGHT ARM: #7 (MAIN), #8 (FOREARM), #9 (HAND)",
                "OTHER: #10-15 (ADDITIONAL SERVOS)"
            ]
            line_spacing = scale_y(20)
            for i, line in enumerate(info_lines):
                text = self.fonts['small'].render(line, True, TEXT_SECONDARY)
                text_rect = text.get_rect(x=scale_x(60), y=info_y + i * line_spacing)
                self.screen.blit(text, text_rect)

            self.servo_channel_input.draw(self.screen, self.fonts)
            self.servo_pulse_input.draw(self.screen, self.fonts)
            self.submit_servo_button.draw(self.screen, self.fonts)

    def draw_tab2(self):
        
        
        panel_left = pygame.Rect(scale_x(20), scale_y(75), scale_x(405), scale_y(210))
        pygame.draw.rect(self.screen, PANEL_BG, panel_left)
        pygame.draw.rect(self.screen, ACCENT_BLUE, panel_left, 2)
        
        header_rect = pygame.Rect(scale_x(20), scale_y(75), scale_x(405), scale_y(22))
        pygame.draw.rect(self.screen, ACCENT_BLUE_DARK, header_rect)
        header_text = self.fonts['small'].render("// OFFSET CALIBRATION //", True, TEXT_PRIMARY)
        header_text_rect = header_text.get_rect(center=header_rect.center)
        self.screen.blit(header_text, header_text_rect)

        for offset_name, y_pos in self.leg_offset_rows.items():
            display_name, channel = self.leg_offset_info[offset_name]
            current_value = offset_values.get(offset_name, 0)

            label_text = self.fonts['small'].render(f"{display_name} [CH{channel}]", True, TEXT_PRIMARY)
            self.screen.blit(label_text, (scale_x(30), scale_y(y_pos + 6)))

            value_rect = pygame.Rect(scale_x(200), scale_y(y_pos), scale_x(40), scale_y(32))
            pygame.draw.rect(self.screen, MID_DARK, value_rect)
            pygame.draw.rect(self.screen, ACCENT_AMBER if current_value != 0 else BORDER_COLOR, value_rect, 2)
            value_text = self.fonts['small'].render(f"{current_value:+d}", True, ACCENT_AMBER if current_value != 0 else TEXT_SECONDARY)
            value_text_rect = value_text.get_rect(center=value_rect.center)
            self.screen.blit(value_text, value_text_rect)

            for btn in self.leg_offset_buttons[offset_name].values():
                btn.draw(self.screen, self.fonts)

        controls_panel = pygame.Rect(scale_x(20), scale_y(295), scale_x(405), scale_y(105))
        pygame.draw.rect(self.screen, PANEL_BG, controls_panel)
        pygame.draw.rect(self.screen, BORDER_COLOR, controls_panel, 2)
        
        ctrl_header = pygame.Rect(scale_x(20), scale_y(295), scale_x(405), scale_y(22))
        pygame.draw.rect(self.screen, MID_DARK, ctrl_header)
        ctrl_text = self.fonts['small'].render("// CONTROLS //", True, TEXT_SECONDARY)
        ctrl_text_rect = ctrl_text.get_rect(center=ctrl_header.center)
        self.screen.blit(ctrl_text, ctrl_text_rect)
        
        self.disable_servos_btn.x_ref = 30
        self.disable_servos_btn.y_ref = 325
        self.disable_servos_btn.width_ref = 180
        self.disable_servos_btn.height_ref = 35
        self.disable_servos_btn.draw(self.screen, self.fonts)
        
        self.manual_test_checkbox.x_ref = 230
        self.manual_test_checkbox.y_ref = 328
        self.manual_test_checkbox.draw(self.screen, self.fonts)
        
        self.disable_after_action_checkbox.x_ref = 230
        self.disable_after_action_checkbox.y_ref = 360
        self.disable_after_action_checkbox.draw(self.screen, self.fonts)

        panel_right = pygame.Rect(scale_x(430), scale_y(75), scale_x(365), scale_y(210))
        pygame.draw.rect(self.screen, PANEL_BG, panel_right)
        pygame.draw.rect(self.screen, ACCENT_GREEN, panel_right, 2)
        
        header_rect2 = pygame.Rect(scale_x(430), scale_y(75), scale_x(365), scale_y(22))
        pygame.draw.rect(self.screen, ACCENT_GREEN_DARK, header_rect2)
        header_text2 = self.fonts['small'].render("// MOVE SERVOS (1-100, 50=NEUTRAL) //", True, TEXT_PRIMARY)
        header_text_rect2 = header_text2.get_rect(center=header_rect2.center)
        self.screen.blit(header_text2, header_text_rect2)
        
        self.reset_move_btn.x_ref = 680
        self.reset_move_btn.y_ref = 100
        self.reset_move_btn.width_ref = 105
        self.reset_move_btn.height_ref = 24
        self.reset_move_btn.text = "RESET"
        self.reset_move_btn.draw(self.screen, self.fonts)
        
        row_y = [100, 130, 160, 190]
        input_x = 555
        minus_x = 600
        plus_x = 626
        
        lh_label = self.fonts['small'].render("LEFT-HEIGHT", True, TEXT_PRIMARY)
        self.screen.blit(lh_label, (scale_x(440), scale_y(row_y[0] + 5)))
        self.leg_move_inputs['left_height'].x_ref = input_x
        self.leg_move_inputs['left_height'].y_ref = row_y[0]
        self.leg_move_inputs['left_height'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['left_height']['minus'].x_ref = minus_x
        self.leg_move_adjust_buttons['left_height']['minus'].y_ref = row_y[0]
        self.leg_move_adjust_buttons['left_height']['plus'].x_ref = plus_x
        self.leg_move_adjust_buttons['left_height']['plus'].y_ref = row_y[0]
        self.leg_move_adjust_buttons['left_height']['minus'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['left_height']['plus'].draw(self.screen, self.fonts)
        
        rh_label = self.fonts['small'].render("RIGHT-HEIGHT", True, TEXT_PRIMARY)
        self.screen.blit(rh_label, (scale_x(440), scale_y(row_y[1] + 5)))
        self.leg_move_inputs['right_height'].x_ref = input_x
        self.leg_move_inputs['right_height'].y_ref = row_y[1]
        self.leg_move_inputs['right_height'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['right_height']['minus'].x_ref = minus_x
        self.leg_move_adjust_buttons['right_height']['minus'].y_ref = row_y[1]
        self.leg_move_adjust_buttons['right_height']['plus'].x_ref = plus_x
        self.leg_move_adjust_buttons['right_height']['plus'].y_ref = row_y[1]
        self.leg_move_adjust_buttons['right_height']['minus'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['right_height']['plus'].draw(self.screen, self.fonts)
        
        ll_label = self.fonts['small'].render("LEFT-ROTATION", True, TEXT_PRIMARY)
        self.screen.blit(ll_label, (scale_x(440), scale_y(row_y[2] + 5)))
        self.leg_move_inputs['left_leg'].x_ref = input_x
        self.leg_move_inputs['left_leg'].y_ref = row_y[2]
        self.leg_move_inputs['left_leg'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['left_leg']['minus'].x_ref = minus_x
        self.leg_move_adjust_buttons['left_leg']['minus'].y_ref = row_y[2]
        self.leg_move_adjust_buttons['left_leg']['plus'].x_ref = plus_x
        self.leg_move_adjust_buttons['left_leg']['plus'].y_ref = row_y[2]
        self.leg_move_adjust_buttons['left_leg']['minus'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['left_leg']['plus'].draw(self.screen, self.fonts)
        
        rl_label = self.fonts['small'].render("RIGHT-ROTATION", True, TEXT_PRIMARY)
        self.screen.blit(rl_label, (scale_x(440), scale_y(row_y[3] + 5)))
        self.leg_move_inputs['right_leg'].x_ref = input_x
        self.leg_move_inputs['right_leg'].y_ref = row_y[3]
        self.leg_move_inputs['right_leg'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['right_leg']['minus'].x_ref = minus_x
        self.leg_move_adjust_buttons['right_leg']['minus'].y_ref = row_y[3]
        self.leg_move_adjust_buttons['right_leg']['plus'].x_ref = plus_x
        self.leg_move_adjust_buttons['right_leg']['plus'].y_ref = row_y[3]
        self.leg_move_adjust_buttons['right_leg']['minus'].draw(self.screen, self.fonts)
        self.leg_move_adjust_buttons['right_leg']['plus'].draw(self.screen, self.fonts)
        
        speed_label = self.fonts['small'].render("SPEED", True, TEXT_PRIMARY)
        self.screen.blit(speed_label, (scale_x(695), scale_y(130)))
        self.speed_slider.x_ref = 665
        self.speed_slider.y_ref = 150
        self.speed_slider.width_ref = 110
        self.speed_slider.height_ref = 20
        self.speed_slider.draw(self.screen, self.fonts)
        
        slow_label = self.fonts['small'].render("SLOW", True, TEXT_SECONDARY)
        self.screen.blit(slow_label, (scale_x(665), scale_y(172)))
        fast_label = self.fonts['small'].render("FAST", True, TEXT_SECONDARY)
        self.screen.blit(fast_label, (scale_x(745), scale_y(172)))
        
        if self.manual_test_checkbox.checked:
            self.test_legs_btn.x_ref = 430
            self.test_legs_btn.y_ref = 295
            self.test_legs_btn.width_ref = 365
            self.test_legs_btn.height_ref = 45
            self.test_legs_btn.draw(self.screen, self.fonts)
        
        info_text = self.fonts['small'].render("[ OFFSET CHANGES AUTO-SAVE TO CONFIG.INI ]", True, ACCENT_BLUE)
        info_rect = info_text.get_rect(center=(WINDOW_WIDTH // 2, scale_y(420)))
        self.screen.blit(info_text, info_rect)

    def draw_tab3(self):
        
        
        panel_left = pygame.Rect(scale_x(20), scale_y(75), scale_x(405), scale_y(235))
        pygame.draw.rect(self.screen, PANEL_BG, panel_left)
        pygame.draw.rect(self.screen, ACCENT_BLUE, panel_left, 2)
        
        header_rect = pygame.Rect(scale_x(20), scale_y(75), scale_x(405), scale_y(22))
        pygame.draw.rect(self.screen, ACCENT_BLUE_DARK, header_rect)
        header_text = self.fonts['small'].render("// ARM OFFSET CALIBRATION //", True, TEXT_PRIMARY)
        header_text_rect = header_text.get_rect(center=header_rect.center)
        self.screen.blit(header_text, header_text_rect)

        for offset_name, y_pos in self.arm_offset_rows.items():
            display_name, channel = self.arm_offset_info[offset_name]
            current_value = offset_values.get(offset_name, 0)

            label_text = self.fonts['small'].render(f"{display_name} [CH{channel}]", True, TEXT_PRIMARY)
            self.screen.blit(label_text, (scale_x(30), scale_y(y_pos + 6)))

            value_rect = pygame.Rect(scale_x(200), scale_y(y_pos), scale_x(40), scale_y(28))
            pygame.draw.rect(self.screen, MID_DARK, value_rect)
            pygame.draw.rect(self.screen, ACCENT_AMBER if current_value != 0 else BORDER_COLOR, value_rect, 2)
            value_text = self.fonts['small'].render(f"{current_value:+d}", True, ACCENT_AMBER if current_value != 0 else TEXT_SECONDARY)
            value_text_rect = value_text.get_rect(center=value_rect.center)
            self.screen.blit(value_text, value_text_rect)

            for btn in self.arm_offset_buttons[offset_name].values():
                btn.draw(self.screen, self.fonts)

        controls_panel = pygame.Rect(scale_x(20), scale_y(320), scale_x(405), scale_y(80))
        pygame.draw.rect(self.screen, PANEL_BG, controls_panel)
        pygame.draw.rect(self.screen, BORDER_COLOR, controls_panel, 2)
        
        ctrl_header = pygame.Rect(scale_x(20), scale_y(320), scale_x(405), scale_y(22))
        pygame.draw.rect(self.screen, MID_DARK, ctrl_header)
        ctrl_text = self.fonts['small'].render("// CONTROLS //", True, TEXT_SECONDARY)
        ctrl_text_rect = ctrl_text.get_rect(center=ctrl_header.center)
        self.screen.blit(ctrl_text, ctrl_text_rect)
        
        self.disable_arm_servos_btn.x_ref = 30
        self.disable_arm_servos_btn.y_ref = 350
        self.disable_arm_servos_btn.width_ref = 180
        self.disable_arm_servos_btn.height_ref = 35
        self.disable_arm_servos_btn.draw(self.screen, self.fonts)
        
        self.arm_manual_test_checkbox.x_ref = 230
        self.arm_manual_test_checkbox.y_ref = 350
        self.arm_manual_test_checkbox.draw(self.screen, self.fonts)
        
        self.arm_disable_after_action_checkbox.x_ref = 230
        self.arm_disable_after_action_checkbox.y_ref = 375
        self.arm_disable_after_action_checkbox.draw(self.screen, self.fonts)

        panel_right = pygame.Rect(scale_x(430), scale_y(75), scale_x(365), scale_y(235))
        pygame.draw.rect(self.screen, PANEL_BG, panel_right)
        pygame.draw.rect(self.screen, ACCENT_GREEN, panel_right, 2)
        
        header_rect2 = pygame.Rect(scale_x(430), scale_y(75), scale_x(365), scale_y(22))
        pygame.draw.rect(self.screen, ACCENT_GREEN_DARK, header_rect2)
        header_text2 = self.fonts['small'].render("// MOVE ARMS (1-100, 1=NEUTRAL) //", True, TEXT_PRIMARY)
        header_text_rect2 = header_text2.get_rect(center=header_rect2.center)
        self.screen.blit(header_text2, header_text_rect2)
        
        self.reset_arm_move_btn.x_ref = 680
        self.reset_arm_move_btn.y_ref = 100
        self.reset_arm_move_btn.width_ref = 105
        self.reset_arm_move_btn.height_ref = 24
        self.reset_arm_move_btn.text = "RESET"
        self.reset_arm_move_btn.draw(self.screen, self.fonts)
        
        row_y = [100, 130, 160, 190, 220, 250]
        input_x = 555
        minus_x = 600
        plus_x = 626
        
        arm_labels = [
            ('left_main', "LEFT-MAIN"),
            ('left_forearm', "LEFT-FOREARM"),
            ('left_hand', "LEFT-HAND"),
            ('right_main', "RIGHT-MAIN"),
            ('right_forearm', "RIGHT-FOREARM"),
            ('right_hand', "RIGHT-HAND"),
        ]
        
        for i, (key, label) in enumerate(arm_labels):
            y = row_y[i]
            lbl = self.fonts['small'].render(label, True, TEXT_PRIMARY)
            self.screen.blit(lbl, (scale_x(440), scale_y(y + 5)))
            self.arm_move_inputs[key].x_ref = input_x
            self.arm_move_inputs[key].y_ref = y
            self.arm_move_inputs[key].draw(self.screen, self.fonts)
            self.arm_move_adjust_buttons[key]['minus'].x_ref = minus_x
            self.arm_move_adjust_buttons[key]['minus'].y_ref = y
            self.arm_move_adjust_buttons[key]['plus'].x_ref = plus_x
            self.arm_move_adjust_buttons[key]['plus'].y_ref = y
            self.arm_move_adjust_buttons[key]['minus'].draw(self.screen, self.fonts)
            self.arm_move_adjust_buttons[key]['plus'].draw(self.screen, self.fonts)
        
        speed_label = self.fonts['small'].render("SPEED", True, TEXT_PRIMARY)
        self.screen.blit(speed_label, (scale_x(695), scale_y(190)))
        self.arm_speed_slider.x_ref = 665
        self.arm_speed_slider.y_ref = 210
        self.arm_speed_slider.width_ref = 110
        self.arm_speed_slider.height_ref = 20
        self.arm_speed_slider.draw(self.screen, self.fonts)
        
        slow_label = self.fonts['small'].render("SLOW", True, TEXT_SECONDARY)
        self.screen.blit(slow_label, (scale_x(665), scale_y(232)))
        fast_label = self.fonts['small'].render("FAST", True, TEXT_SECONDARY)
        self.screen.blit(fast_label, (scale_x(745), scale_y(232)))
        
        if self.arm_manual_test_checkbox.checked:
            self.test_arms_btn.x_ref = 430
            self.test_arms_btn.y_ref = 320
            self.test_arms_btn.width_ref = 365
            self.test_arms_btn.height_ref = 45
            self.test_arms_btn.draw(self.screen, self.fonts)
        
        info_text = self.fonts['small'].render("[ OFFSET CHANGES AUTO-SAVE TO CONFIG.INI ]", True, ACCENT_BLUE)
        info_rect = info_text.get_rect(center=(WINDOW_WIDTH // 2, scale_y(420)))
        self.screen.blit(info_text, info_rect)

    def draw_tab4(self):
        mode_title = self.fonts['label'].render("MODE:", True, TEXT_SECONDARY)
        self.screen.blit(mode_title, (scale_x(20), scale_y(93)))

        self.mode_slow_btn.color = ACCENT_GREEN if self.movement_mode == "slow" else ACCENT_BLUE
        self.mode_fast_btn.color = ACCENT_GREEN if self.movement_mode == "fast" else ACCENT_BLUE
        self.mode_slow_btn.draw(self.screen, self.fonts)
        self.mode_fast_btn.draw(self.screen, self.fonts)

        self.move_forward_btn.draw(self.screen, self.fonts)
        self.move_backward_btn.draw(self.screen, self.fonts)
        self.turn_left_btn.draw(self.screen, self.fonts)
        self.turn_right_btn.draw(self.screen, self.fonts)

        pygame.draw.line(self.screen, BORDER_COLOR, 
                        (scale_x(320), scale_y(60)), 
                        (scale_x(320), scale_y(440)), 2)

        self.action_dropdown.draw(self.screen, self.fonts)
        self.execute_action_btn.draw(self.screen, self.fonts)

    def handle_tab1_events(self, event):
        if self.tab1_mode == "main":
            for i, button in enumerate(self.tab1_buttons):
                if button.handle_event(event):
                    if i == 0:  

                        message = set_all_servos_preset()
                        self.set_status(message)
                    elif i == 1:  

                        message = disable_all_servos()
                        self.set_status(message)
                    elif i == 2:  

                        self.tab1_mode = "manual_servo"

        elif self.tab1_mode == "manual_servo":
            if event.type == pygame.MOUSEBUTTONDOWN:
                back_rect = pygame.Rect(scale_x(40), scale_y(65), scale_x(90), scale_y(32))
                if back_rect.collidepoint(event.pos):
                    self.tab1_mode = "main"
                    return

            self.servo_channel_input.handle_event(event)
            self.servo_pulse_input.handle_event(event)

            if self.submit_servo_button.handle_event(event):
                try:
                    channel = int(self.servo_channel_input.text)
                    pulse = int(self.servo_pulse_input.text)

                    if 0 <= channel <= 15 and MIN_PULSE <= pulse <= MAX_PULSE:
                        set_servo_pulse(channel, pulse)
                        self.set_status(f"OK Servo {channel} set to {pulse}")
                    else:
                        self.set_status("WARNING Invalid channel or pulse value")
                except ValueError:
                    self.set_status("WARNING Please enter valid numbers")

    def handle_tab2_events(self, event):
        
        
        self.disable_after_action_checkbox.handle_event(event)
        self.manual_test_checkbox.handle_event(event)
        
        if self.disable_servos_btn.handle_event(event):
            disable_all_servos()
            self.set_status("OK Servos disabled")
            return

        for offset_name, buttons in self.leg_offset_buttons.items():
            for btn_type, btn in buttons.items():
                if btn.handle_event(event):
                    current_value = offset_values.get(offset_name, 0)

                    if btn_type == 'minus5':
                        new_value = current_value - 5
                    elif btn_type == 'minus1':
                        new_value = current_value - 1
                    elif btn_type == 'plus1':
                        new_value = current_value + 1
                    elif btn_type == 'plus5':
                        new_value = current_value + 5

                    channel = self.leg_offset_info[offset_name][1]
                    if channel in [0, 1]:  
                        base_up = int(servo_config.get('leftUpHeight' if channel == 0 else 'rightUpHeight', 350))
                        base_down = int(servo_config.get('leftDownHeight' if channel == 0 else 'rightDownHeight', 350))
                        target_up = base_up + new_value
                        target_down = base_down + new_value
                        if target_up < 10 or target_up > 600 or target_down < 10 or target_down > 600:
                            self.set_status(f"! Value would exceed safe range (10-600)")
                            return
                    else:
                        base_forward = int(servo_config.get('forwardLeftLeg' if channel == 2 else 'forwardRightLeg', 300))
                        base_back = int(servo_config.get('backLeftLeg' if channel == 2 else 'backRightLeg', 300))
                        target_forward = base_forward + new_value
                        target_back = base_back + new_value
                        if target_forward < 10 or target_forward > 600 or target_back < 10 or target_back > 600:
                            self.set_status(f"! Value would exceed safe range (10-600)")
                            return

                    offset_values[offset_name] = new_value

                    if save_offset_to_config(offset_name, new_value):
                        servoctl.refresh_config()
                        display_name = self.leg_offset_info[offset_name][0]
                        self.set_status(f"OK {display_name}: {new_value:+d}")
                        if not self.manual_test_checkbox.checked:
                            self._do_move()
                    else:
                        self.set_status(f"! Failed to save offset")

                    return

        for input_box in self.leg_move_inputs.values():
            input_box.handle_event(event)
        
        for key, buttons in self.leg_move_adjust_buttons.items():
            input_box = self.leg_move_inputs[key]
            if buttons['minus'].handle_event(event):
                current_val = input_box.get_value()
                new_val = max(1, current_val - 5)
                input_box.text = str(new_val)
                if not self.manual_test_checkbox.checked:
                    self._do_move()
                return
            if buttons['plus'].handle_event(event):
                current_val = input_box.get_value()
                new_val = min(100, current_val + 5)
                input_box.text = str(new_val)
                if not self.manual_test_checkbox.checked:
                    self._do_move()
                return
        
        if self.reset_move_btn.handle_event(event):
            for input_box in self.leg_move_inputs.values():
                input_box.text = "50"
            self.set_status("OK Reset to neutral (50)")
            if not self.manual_test_checkbox.checked:
                self._do_move()
            return
        
        self.speed_slider.handle_event(event)
        
        if self.manual_test_checkbox.checked and self.test_legs_btn.handle_event(event):
            self._do_move()
    
    def _do_move(self):
        
        left_height = self.leg_move_inputs['left_height'].get_value()
        right_height = self.leg_move_inputs['right_height'].get_value()
        left_leg = self.leg_move_inputs['left_leg'].get_value()
        right_leg = self.leg_move_inputs['right_leg'].get_value()
        speed = self.speed_slider.value
        
        print(f"[MOVE] L-Height={left_height}, R-Height={right_height}, L-Rot={left_leg}, R-Rot={right_leg}, Speed={speed:.2f}")
        
        try:
            servoctl.move_legs(left_height, right_height, left_leg, right_leg, speed)
            self.set_status(f"OK Moved (speed={speed:.2f})")

            if self.disable_after_action_checkbox.checked:
                time.sleep(0.3)
                servoctl.disable_all_servos()
                self.set_status("OK Moved - servos disabled")
        except Exception as e:
            print(f"[ERROR] Move failed: {str(e)}")
            self.set_status(f"! Move failed: {str(e)}")

    def handle_tab3_events(self, event):
        
        
        self.arm_disable_after_action_checkbox.handle_event(event)
        self.arm_manual_test_checkbox.handle_event(event)
        
        if self.disable_arm_servos_btn.handle_event(event):
            disable_all_servos()
            self.set_status("OK Servos disabled")
            return

        arm_base_values = {
            'leftMainOffset': (int(servo_config.get('leftMainMin', 550)), int(servo_config.get('leftMainMax', 50))),
            'leftForearmOffset': (int(servo_config.get('leftForarmMin', 500)), int(servo_config.get('leftForarmMax', 230))),
            'leftHandOffset': (int(servo_config.get('leftHandMin', 400)), int(servo_config.get('leftHandMax', 300))),
            'rightMainOffset': (int(servo_config.get('rightMainMin', 50)), int(servo_config.get('rightMainMax', 550))),
            'rightForearmOffset': (int(servo_config.get('rightForarmMin', 230)), int(servo_config.get('rightForarmMax', 500))),
            'rightHandOffset': (int(servo_config.get('rightHandMin', 300)), int(servo_config.get('rightHandMax', 400)))
        }

        for offset_name, buttons in self.arm_offset_buttons.items():
            for btn_type, btn in buttons.items():
                if btn.handle_event(event):
                    current_value = offset_values.get(offset_name, 0)

                    if btn_type == 'minus5':
                        new_value = current_value - 5
                    elif btn_type == 'minus1':
                        new_value = current_value - 1
                    elif btn_type == 'plus1':
                        new_value = current_value + 1
                    elif btn_type == 'plus5':
                        new_value = current_value + 5

                    base_min, base_max = arm_base_values.get(offset_name, (0, 0))
                    target_min = base_min + new_value
                    target_max = base_max + new_value

                    if target_min < 10 or target_min > 600 or target_max < 10 or target_max > 600:
                        self.set_status(f"! Value would exceed safe range (10-600)")
                        return

                    offset_values[offset_name] = new_value

                    if save_offset_to_config(offset_name, new_value):
                        servoctl.refresh_config()
                        display_name = self.arm_offset_info[offset_name][0]
                        self.set_status(f"OK {display_name}: {new_value:+d}")
                        if not self.arm_manual_test_checkbox.checked:
                            self._do_arm_move()
                    else:
                        self.set_status(f"! Failed to save offset")

                    return

        for input_box in self.arm_move_inputs.values():
            input_box.handle_event(event)
        
        for key, buttons in self.arm_move_adjust_buttons.items():
            input_box = self.arm_move_inputs[key]
            if buttons['minus'].handle_event(event):
                current_val = input_box.get_value()
                new_val = max(1, current_val - 5)
                input_box.text = str(new_val)
                if not self.arm_manual_test_checkbox.checked:
                    self._do_arm_move()
                return
            if buttons['plus'].handle_event(event):
                current_val = input_box.get_value()
                new_val = min(100, current_val + 5)
                input_box.text = str(new_val)
                if not self.arm_manual_test_checkbox.checked:
                    self._do_arm_move()
                return
        
        if self.reset_arm_move_btn.handle_event(event):
            for input_box in self.arm_move_inputs.values():
                input_box.text = "1"
            self.set_status("OK Reset to neutral (1)")
            if not self.arm_manual_test_checkbox.checked:
                self._do_arm_move()
            return
        
        self.arm_speed_slider.handle_event(event)
        
        if self.arm_manual_test_checkbox.checked and self.test_arms_btn.handle_event(event):
            self._do_arm_move()
    
    def _do_arm_move(self):
        
        left_main = self.arm_move_inputs['left_main'].get_value()
        left_forearm = self.arm_move_inputs['left_forearm'].get_value()
        left_hand = self.arm_move_inputs['left_hand'].get_value()
        right_main = self.arm_move_inputs['right_main'].get_value()
        right_forearm = self.arm_move_inputs['right_forearm'].get_value()
        right_hand = self.arm_move_inputs['right_hand'].get_value()
        speed = self.arm_speed_slider.value
        
        print(f"[ARM MOVE] L-Main={left_main}, L-Forearm={left_forearm}, L-Hand={left_hand}, R-Main={right_main}, R-Forearm={right_forearm}, R-Hand={right_hand}, Speed={speed:.2f}")
        
        try:
            servoctl.move_arm(left_main, left_forearm, left_hand, right_main, right_forearm, right_hand, speed)
            self.set_status(f"OK Arms moved (speed={speed:.2f})")

            if self.arm_disable_after_action_checkbox.checked:
                time.sleep(0.3)
                servoctl.disable_all_servos()
                self.set_status("OK Arms moved - servos disabled")
        except Exception as e:
            print(f"[ERROR] Arm move failed: {str(e)}")
            self.set_status(f"! Move failed: {str(e)}")

    def handle_tab4_events(self, event):
        if self.mode_slow_btn.handle_event(event):
            self.movement_mode = "slow"
            self.set_status("Mode: SLOW")
            return

        if self.mode_fast_btn.handle_event(event):
            self.movement_mode = "fast"
            self.set_status("Mode: FAST")
            return

        if self.move_forward_btn.handle_event(event):
            if self.movement_mode == "fast":
                self.set_status("LOADING Forward...")
                step_forward()
                self.set_status("OK Forward complete")
            else:
                self.set_status("LOADING Forward (slow)...")
                walk_forward()
                self.set_status("OK Forward complete")
            return

        if self.move_backward_btn.handle_event(event):
            if self.movement_mode == "fast":
                self.set_status("LOADING Backward...")
                step_backward()
                self.set_status("OK Backward complete")
            else:
                self.set_status("LOADING Backward (slow)...")
                walk_backward()
                self.set_status("OK Backward complete")
            return

        if self.turn_left_btn.handle_event(event):
            if self.movement_mode == "fast":
                self.set_status("LOADING Turn left...")
                turn_left()
                self.set_status("OK Turn left complete")
            else:
                self.set_status("LOADING Turn left (slow)...")
                turn_left_slow()
                self.set_status("OK Turn left complete")
            return

        if self.turn_right_btn.handle_event(event):
            if self.movement_mode == "fast":
                self.set_status("LOADING Turn right...")
                turn_right()
                self.set_status("OK Turn right complete")
            else:
                self.set_status("LOADING Turn right (slow)...")
                turn_right_slow()
                self.set_status("OK Turn right complete")
            return

        self.action_dropdown.handle_event(event)

        if self.execute_action_btn.handle_event(event):
            if self.actions:
                selected_action = self.actions[self.action_dropdown.selected_index]
                action_name = selected_action[0]
                function_name = selected_action[1]

                self.set_status(f"LOADING Executing {action_name}...")
                try:
                    func = globals()[function_name]
                    func()
                    self.set_status(f"OK {action_name} complete")
                except Exception as e:
                    self.set_status(f"WARNING Error: {str(e)}")
            return

    def run(self):
        while self.running:

            self.fonts = get_fonts()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                for i, tab in enumerate(self.tabs):
                    if tab.handle_event(event):

                        for t in self.tabs:
                            t.active = False

                        tab.active = True
                        self.current_tab = i

                        if i != 0:
                            self.tab1_mode = "main"

                if self.current_tab == 0:
                    self.handle_tab1_events(event)
                elif self.current_tab == 1:
                    self.handle_tab2_events(event)
                elif self.current_tab == 2:
                    self.handle_tab3_events(event)
                elif self.current_tab == 3:
                    self.handle_tab4_events(event)

            self.screen.fill(DARK_BG)

            self.draw_header()

            for tab in self.tabs:
                tab.draw(self.screen, self.fonts)

            if self.current_tab == 0:
                self.draw_tab1()
            elif self.current_tab == 1:
                self.draw_tab2()
            elif self.current_tab == 2:
                self.draw_tab3()
            elif self.current_tab == 3:
                self.draw_tab4()

            self.draw_status_bar()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

def adjust_offsets():
    offsets = [
        ('perfectLeftHeightOffset', 'Left Height', 0),
        ('perfectRightHeightOffset', 'Right Height', 1),
        ('perfectLeftLegOffset', 'Left Leg', 2),
        ('perfectRightLegOffset', 'Right Leg', 3),
        ('leftMainOffset', 'Left Main Arm', 4),
        ('leftForearmOffset', 'Left Forearm', 5),
        ('leftHandOffset', 'Left Hand', 6),
        ('rightMainOffset', 'Right Main Arm', 7),
        ('rightForearmOffset', 'Right Forearm', 8),
        ('rightHandOffset', 'Right Hand', 9)
    ]

    while True:
        print("\n=== SERVO OFFSET ADJUSTMENT ===")
        for i, (key, name, channel) in enumerate(offsets, 1):
            current_value = offset_values.get(key, 0)
            print(f"{i}. {name:18} (CH{channel}): {current_value:+4d}")
        print("11. Back to main menu")
        print("================================\n")

        choice = input("> ")
        if choice == '11':
            break

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= 10:
                offset_name, servo_name, channel = offsets[choice_num - 1]
                current_value = offset_values.get(offset_name, 0)

                if channel in [0, 1]:
                    base_pulse = 350
                elif channel in [2, 3]:
                    base_pulse = 300
                elif channel == 4:
                    base_pulse = int(servo_config.get('leftMainMin', 550))
                elif channel == 5:
                    base_pulse = int(servo_config.get('leftForarmMin', 500))
                elif channel == 6:
                    base_pulse = int(servo_config.get('leftHandMin', 400))
                elif channel == 7:
                    base_pulse = int(servo_config.get('rightMainMin', 50))
                elif channel == 8:
                    base_pulse = int(servo_config.get('rightForarmMin', 230))
                elif channel == 9:
                    base_pulse = int(servo_config.get('rightHandMin', 300))

                else:
                    base_pulse = 300

                print(f"Base pulse: {base_pulse}, Current target: {base_pulse} {current_value:+d} = {base_pulse + current_value}")

                print("\nCommands:")
                print("  +   = Increase by 5")
                print("  -   = Decrease by 5")
                print("  ++  = Increase by 1")
                print("  --  = Decrease by 1")
                print("  num = Set to value")
                print("  q   = Done")

                while True:
                    target_position = base_pulse + offset_values[offset_name]
                    offset_str = f"{offset_values[offset_name]:+d}"
                    print(f"\n{servo_name} Offset: {offset_values[offset_name]:+4d}  (Target: {base_pulse}{offset_str}={target_position})", end="  ")
                    cmd = input("> ").strip().lower()

                    if cmd == 'q':
                        break
                    elif cmd == '+':
                        offset_values[offset_name] += 5
                        save_offset_to_config(offset_name, offset_values[offset_name])
                        reload_and_test()
                    elif cmd == '-':
                        offset_values[offset_name] -= 5
                        save_offset_to_config(offset_name, offset_values[offset_name])
                        reload_and_test()
                    elif cmd == '++':
                        offset_values[offset_name] += 1
                        save_offset_to_config(offset_name, offset_values[offset_name])
                        reload_and_test()
                    elif cmd == '--':
                        offset_values[offset_name] -= 1
                        save_offset_to_config(offset_name, offset_values[offset_name])
                        reload_and_test()
                    else:
                        try:
                            new_value = int(cmd)
                            offset_values[offset_name] = new_value
                            save_offset_to_config(offset_name, offset_values[offset_name])
                            reload_and_test()
                        except ValueError:
                            print("Invalid command. Use +, -, ++, --, q, or a number.")
            else:
                print("Invalid selection. Please choose 1-11.")
        except ValueError:
            print("Invalid selection. Please choose 1-11.")

def set_single_servo():
    servo_ranges = {
        0: ("Left Height", int(servo_config.get('leftUpHeight', 150)), int(servo_config.get('leftDownHeight', 550))),
        1: ("Right Height", int(servo_config.get('rightUpHeight', 150)), int(servo_config.get('rightDownHeight', 550))),
        2: ("Left Leg", int(servo_config.get('forwardLeftLeg', 100)), int(servo_config.get('backLeftLeg', 500))),
        3: ("Right Leg", int(servo_config.get('forwardRightLeg', 100)), int(servo_config.get('backRightLeg', 500))),
        4: ("Left Main Arm", int(servo_config.get('leftMainMin', 50)), int(servo_config.get('leftMainMax', 550))),
        5: ("Left Forearm", int(servo_config.get('leftForarmMin', 50)), int(servo_config.get('leftForarmMax', 550))),
        6: ("Left Hand", int(servo_config.get('leftHandMin', 50)), int(servo_config.get('leftHandMax', 550))),
        7: ("Right Main Arm", int(servo_config.get('rightMainMin', 50)), int(servo_config.get('rightMainMax', 550))),
        8: ("Right Forearm", int(servo_config.get('rightForarmMin', 50)), int(servo_config.get('rightForarmMax', 550))),
        9: ("Right Hand", int(servo_config.get('rightHandMin', 50)), int(servo_config.get('rightHandMax', 550))),
    }
    
    while True:
        try:
            print("\n=== SERVO PIN LAYOUT ===")
            print("Height Servos:")
            print(f"  #0 - Left Height    [{servo_ranges[0][1]} - {servo_ranges[0][2]}]")
            print(f"  #1 - Right Height   [{servo_ranges[1][1]} - {servo_ranges[1][2]}]")
            print("\nLeg Servos:")
            print(f"  #2 - Left Leg       [{servo_ranges[2][1]} - {servo_ranges[2][2]}]")
            print(f"  #3 - Right Leg      [{servo_ranges[3][1]} - {servo_ranges[3][2]}]")
            print("\nLeft Arm Servos:")
            print(f"  #4 - Left Main Arm  [{servo_ranges[4][1]} - {servo_ranges[4][2]}]")
            print(f"  #5 - Left Forearm   [{servo_ranges[5][1]} - {servo_ranges[5][2]}]")
            print(f"  #6 - Left Hand      [{servo_ranges[6][1]} - {servo_ranges[6][2]}]")
            print("\nRight Arm Servos:")
            print(f"  #7 - Right Main Arm [{servo_ranges[7][1]} - {servo_ranges[7][2]}]")
            print(f"  #8 - Right Forearm  [{servo_ranges[8][1]} - {servo_ranges[8][2]}]")
            print(f"  #9 - Right Hand     [{servo_ranges[9][1]} - {servo_ranges[9][2]}]")
            print("\nOther:")
            print(f"  #10-15 - Additional [{MIN_PULSE} - {MAX_PULSE}]")
            print("========================\n")

            channel = int(input(f"Enter servo number (0-15): "))
            if channel < 0 or channel > 15:
                print("Channel must be between 0 and 15")
                continue

            if channel in servo_ranges:
                name, min_val, max_val = servo_ranges[channel]
                pulse = int(input(f"Enter pulse for {name} [{min_val} - {max_val}]: "))
            else:
                pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break
        except ValueError:
            print("Invalid input. Please try again.")
            break

def control():
    actions = [("Reset Position", "reset_positions")] + get_names()

    try:
        print("\n=== MOVEMENT CONTROLS ===")
        print("--- Legs Only ---")
        for i, (display_name, func_name) in enumerate([("Reset Position", "reset_positions")] + get_names_by_type(LEGS_ONLY)):
            print(f"{i} - {display_name}")
        print("\n--- With Arms ---")
        arms_start = 1 + len(get_names_by_type(LEGS_ONLY))
        for i, (display_name, func_name) in enumerate(get_names_by_type(HAS_ARMS)):
            print(f"{arms_start + i} - {display_name}")
        print("========================\n")

        main_input = input("> ")
        try:
            choice = int(main_input)
            if 0 <= choice < len(actions):
                display_name, function_name = actions[choice]
                print(f"Executing {display_name}...")
                func = globals()[function_name]
                func()
                print(f"OK {display_name} complete")
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

    except ValueError:
        print("Invalid input. Please enter a valid number.")

def terminal_mode():
    print("\n" + "="*50)
    print("V3 Servo Controller - Terminal Mode")
    print("="*50)

    while True:
        print("\n=== MAIN MENU ===")
        print("1. Set all servos to preset position")
        print("2. Disable Power to all servos")
        print("3. Manually set individual servo")
        print("4. Manually set Channel 15 servo")
        print("5. Adjust servo offsets")
        print("6. Movement sequences")
        print("7. Exit")
        print("==================\n")

        choice = input("> ")

        if choice == '1':
            set_all_servos_preset()
        elif choice == '2':
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
                time.sleep(0.05)
            print("OK Servos are not under power anymore.")
        elif choice == '3':
            set_single_servo()
        elif choice == '4':
            pulse = int(input(f"Enter pulse width for servo on channel 15 ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(15, pulse)
        elif choice == '5':
            adjust_offsets()
        elif choice == '6':
            control()
        elif choice == '7':
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
            print("OK Exiting")
            break
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("V3 Servo Controller")
    print("="*50)
    print("\nSelect Mode:")
    print("1. GUI Mode (graphical interface)")
    print("2. Terminal Mode (text-based)")
    print("3. Test Custom Movements (You need to add these in the code yourself.)")
    print("="*50)

    mode_choice = input("\nEnter your choice (1, 2 or 3): ").strip()

    try:
        if mode_choice == '1':
            gui = ServoControllerGUI()
            gui.run()
        elif mode_choice == '2':
            terminal_mode()
        elif mode_choice == '3':
            
            reset_positions()


            move_arm(None, None, None, 40, 50, 100, 0.7)
            time.sleep(1)
            move_arm(None, None, None, 40, 50, 100, 0.7)
            time.sleep(1)
            move_arm(None, None, None, 40, 50, 1, 0.7)
            time.sleep(1)
            move_arm(None, None, None, 1, 1, 1, 0.7)
            
            disable_all_servos()
            pass
            
        else:
            print("Invalid selection. Defaulting to GUI mode...")
            gui = ServoControllerGUI()
            gui.run()
    except KeyboardInterrupt:
        disable_all_servos()
        print("\nOK Servos disabled. Exiting.")