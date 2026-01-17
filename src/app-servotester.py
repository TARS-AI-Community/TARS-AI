"""
SERVO CONTROLLER GUI - V3
==========================

"""

import pygame
import sys
import time
import board
import busio
from adafruit_pca9685 import PCA9685
import os
import importlib

from modules.module_config import load_config
import modules.module_servoctl as servoctl
from modules.module_servoctl import *

pygame.init()

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 480

REFERENCE_WIDTH = 800
REFERENCE_HEIGHT = 480

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
    try:
        mono_font = pygame.font.SysFont('couriernew', scale_font(20))
        mono_font_small = pygame.font.SysFont('couriernew', scale_font(18))
    except:
        mono_font = pygame.font.Font(None, scale_font(20))
        mono_font_small = pygame.font.Font(None, scale_font(18))

    return {
        'title': pygame.font.Font(None, scale_font(36)),
        'tab': pygame.font.Font(None, scale_font(22)),
        'button': mono_font,
        'label': mono_font_small,
        'small': pygame.font.Font(None, scale_font(14)),
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

    return True

def reload_and_test():
    try:
        global config
        config = load_config()
        importlib.reload(servoctl)

        globals().update({name: getattr(servoctl, name) for name in dir(servoctl) if not name.startswith('_')})

        reset_positions()
        return True
    except Exception as e:
        print(f"⚠ Error during reload/test: {e}")
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

        corner_size = scale_x(12)
        corner_offset = scale_x(5)

        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.left - corner_offset, self.rect.top + corner_size), 
                        (self.rect.left - corner_offset, self.rect.top - corner_offset), 3)
        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.left - corner_offset, self.rect.top - corner_offset), 
                        (self.rect.left + corner_size, self.rect.top - corner_offset), 3)

        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.right + corner_offset, self.rect.top + corner_size), 
                        (self.rect.right + corner_offset, self.rect.top - corner_offset), 3)
        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.right + corner_offset, self.rect.top - corner_offset), 
                        (self.rect.right - corner_size, self.rect.top - corner_offset), 3)

        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.left - corner_offset, self.rect.bottom - corner_size), 
                        (self.rect.left - corner_offset, self.rect.bottom + corner_offset), 3)
        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.left - corner_offset, self.rect.bottom + corner_offset), 
                        (self.rect.left + corner_size, self.rect.bottom + corner_offset), 3)

        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.right + corner_offset, self.rect.bottom - corner_size), 
                        (self.rect.right + corner_offset, self.rect.bottom + corner_offset), 3)
        pygame.draw.line(screen, ACCENT_AMBER, 
                        (self.rect.right + corner_offset, self.rect.bottom + corner_offset), 
                        (self.rect.right - corner_size, self.rect.bottom + corner_offset), 3)

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
            pygame.draw.line(screen, ACCENT_AMBER,
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

class Dropdown:
    def __init__(self, x, y, width, height, options, max_visible=6):
        self.x_ref = x
        self.y_ref = y
        self.width_ref = width
        self.height_ref = height
        self.options = options
        self.selected_index = 0
        self.is_open = False
        self.max_visible = max_visible
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
            'perfectLeftHeightOffset': ('LEFT HEIGHT', 0),
            'perfectRightHeightOffset': ('RIGHT HEIGHT', 1),
            'perfectLeftLegOffset': ('LEFT LEG', 2),
            'perfectRightLegOffset': ('RIGHT LEG', 3)
        }

        self.selected_leg_offset = 'perfectLeftHeightOffset'

        self.leg_offset_custom_input = InputBox(80, 325, 70, 30, "", "0")

        self.leg_offset_rows = {
            'perfectLeftHeightOffset': 90,
            'perfectRightHeightOffset': 140,
            'perfectLeftLegOffset': 190,
            'perfectRightLegOffset': 240
        }

        btn_width = 45
        btn_height = 30

        self.leg_offset_buttons = {}
        for offset_name, y_pos in self.leg_offset_rows.items():
            self.leg_offset_buttons[offset_name] = {
                'minus5': Button(460, y_pos, btn_width, btn_height, "-5", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'minus1': Button(510, y_pos, btn_width, btn_height, "-1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus1': Button(560, y_pos, btn_width, btn_height, "+1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus5': Button(610, y_pos, btn_width, btn_height, "+5", ACCENT_BLUE, ACCENT_BLUE_DARK)
            }

        self.apply_leg_custom_btn = Button(160, 325, 60, 30, "SET", ACCENT_BLUE, ACCENT_BLUE_DARK)
        self.test_leg_offsets_btn = Button(230, 325, 150, 30, "TEST OFFSETS", ACCENT_GREEN, ACCENT_GREEN_DARK)

    def create_tab3_elements(self):
        self.arm_offset_info = {
            'leftMainOffset': ('LEFT MAIN ARM', 4),
            'leftForearmOffset': ('LEFT FOREARM', 5),
            'leftHandOffset': ('LEFT HAND', 6),
            'rightMainOffset': ('RIGHT MAIN ARM', 7),
            'rightForearmOffset': ('RIGHT FOREARM', 8),
            'rightHandOffset': ('RIGHT HAND', 9)
        }

        self.selected_arm_offset = 'leftMainOffset'

        self.arm_offset_custom_input = InputBox(80, 355, 70, 30, "", "0")

        self.arm_offset_rows = {
            'leftMainOffset': 85,
            'leftForearmOffset': 120,
            'leftHandOffset': 155,
            'rightMainOffset': 190,
            'rightForearmOffset': 225,
            'rightHandOffset': 260
        }

        btn_width = 45
        btn_height = 28

        self.arm_offset_buttons = {}
        for offset_name, y_pos in self.arm_offset_rows.items():
            self.arm_offset_buttons[offset_name] = {
                'minus5': Button(460, y_pos, btn_width, btn_height, "-5", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'minus1': Button(510, y_pos, btn_width, btn_height, "-1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus1': Button(560, y_pos, btn_width, btn_height, "+1", ACCENT_BLUE, ACCENT_BLUE_DARK),
                'plus5': Button(610, y_pos, btn_width, btn_height, "+5", ACCENT_BLUE, ACCENT_BLUE_DARK)
            }

        self.apply_arm_custom_btn = Button(160, 355, 60, 30, "SET", ACCENT_BLUE, ACCENT_BLUE_DARK)
        self.test_arm_offsets_btn = Button(230, 355, 150, 30, "TEST OFFSETS", ACCENT_GREEN, ACCENT_GREEN_DARK)
        
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

        self.actions = [
            ("Reset Position", "reset_positions"),
            ("Pose", "pose"),
            ("Laugh", "laugh"),
            ("Bow", "bow"),
            ("Tilt Right", "tilt_right"),
            ("Tilt Left", "tilt_left"),
            ("Side-Side", "side_side"),
            ("Wave Right", "wave_right"),
            ("Wave Left", "wave_left")
        ]

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
        title = self.fonts['tab'].render("LEG SERVO OFFSET CALIBRATION", True, TEXT_PRIMARY)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, scale_y(67)))
        self.screen.blit(title, title_rect)

        for offset_name, y_pos in self.leg_offset_rows.items():
            display_name, channel = self.leg_offset_info[offset_name]
            current_value = offset_values.get(offset_name, 0)

            select_box = pygame.Rect(scale_x(60), scale_y(y_pos + 2), scale_x(20), scale_y(26))
            is_selected = (offset_name == self.selected_leg_offset)

            pygame.draw.rect(self.screen, PANEL_BG, select_box)
            pygame.draw.rect(self.screen, ACCENT_BLUE if is_selected else BORDER_COLOR, select_box, 2)

            if is_selected:

                inner_box = select_box.inflate(-scale_x(8), -scale_y(8))
                pygame.draw.rect(self.screen, ACCENT_BLUE, inner_box)

            label_text = self.fonts['label'].render(f"{display_name} (CH{channel}):", True, TEXT_PRIMARY)
            self.screen.blit(label_text, (scale_x(90), scale_y(y_pos + 5)))

            value_rect = pygame.Rect(scale_x(280), scale_y(y_pos), scale_x(70), scale_y(30))
            pygame.draw.rect(self.screen, PANEL_BG, value_rect)
            pygame.draw.rect(self.screen, ACCENT_BLUE if current_value != 0 else BORDER_COLOR, value_rect, 2)

            value_text = self.fonts['label'].render(f"{current_value:+d}", True, ACCENT_AMBER if current_value != 0 else TEXT_SECONDARY)
            value_text_rect = value_text.get_rect(center=value_rect.center)
            self.screen.blit(value_text, value_text_rect)

            base_pulse = 350 if channel in [0, 1] else 300
            target_pulse = base_pulse + current_value
            target_text = self.fonts['small'].render(f"→ {target_pulse}", True, TEXT_SECONDARY)
            self.screen.blit(target_text, (scale_x(360), scale_y(y_pos + 7)))

            for btn in self.leg_offset_buttons[offset_name].values():
                btn.draw(self.screen, self.fonts)

        pygame.draw.line(self.screen, BORDER_COLOR, 
                        (scale_x(60), scale_y(285)), 
                        (scale_x(740), scale_y(285)), 2)

        custom_label = self.fonts['label'].render("SET CUSTOM VALUE FOR", True, TEXT_SECONDARY)
        self.screen.blit(custom_label, (scale_x(60), scale_y(300)))

        selected_display = self.leg_offset_info[self.selected_leg_offset][0]
        selected_text = self.fonts['label'].render(f"[{selected_display}]:", True, ACCENT_BLUE)
        self.screen.blit(selected_text, (scale_x(300), scale_y(300)))

        self.leg_offset_custom_input.draw(self.screen, self.fonts)
        self.apply_leg_custom_btn.draw(self.screen, self.fonts)
        self.test_leg_offsets_btn.draw(self.screen, self.fonts)

        info_text = self.fonts['small'].render("CHANGES AUTO-SAVE TO CONFIG.INI | USE TEST BUTTON TO VERIFY", True, (0, 200, 255))
        info_rect = info_text.get_rect(center=(WINDOW_WIDTH // 2, scale_y(400)))
        self.screen.blit(info_text, info_rect)

    def draw_tab3(self):
        title = self.fonts['tab'].render("ARM SERVO OFFSET CALIBRATION", True, TEXT_PRIMARY)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, scale_y(67)))
        self.screen.blit(title, title_rect)

        arm_base_values = {
            'leftMainOffset': (int(servo_config.get('leftMainMin', 550)), int(servo_config.get('leftMainMax', 50))),
            'leftForearmOffset': (int(servo_config.get('leftForarmMin', 500)), int(servo_config.get('leftForarmMax', 230))),
            'leftHandOffset': (int(servo_config.get('leftHandMin', 400)), int(servo_config.get('leftHandMax', 300))),
            'rightMainOffset': (int(servo_config.get('rightMainMin', 50)), int(servo_config.get('rightMainMax', 550))),
            'rightForearmOffset': (int(servo_config.get('rightForarmMin', 230)), int(servo_config.get('rightForarmMax', 500))),
            'rightHandOffset': (int(servo_config.get('rightHandMin', 300)), int(servo_config.get('rightHandMax', 400)))
        }

        for offset_name, y_pos in self.arm_offset_rows.items():
            display_name, channel = self.arm_offset_info[offset_name]
            current_value = offset_values.get(offset_name, 0)

            select_box = pygame.Rect(scale_x(60), scale_y(y_pos + 2), scale_x(20), scale_y(24))
            is_selected = (offset_name == self.selected_arm_offset)

            pygame.draw.rect(self.screen, PANEL_BG, select_box)
            pygame.draw.rect(self.screen, ACCENT_BLUE if is_selected else BORDER_COLOR, select_box, 2)

            if is_selected:

                inner_box = select_box.inflate(-scale_x(8), -scale_y(8))
                pygame.draw.rect(self.screen, ACCENT_BLUE, inner_box)

            label_text = self.fonts['label'].render(f"{display_name} (CH{channel}):", True, TEXT_PRIMARY)
            self.screen.blit(label_text, (scale_x(90), scale_y(y_pos + 3)))

            value_rect = pygame.Rect(scale_x(300), scale_y(y_pos), scale_x(70), scale_y(28))
            pygame.draw.rect(self.screen, PANEL_BG, value_rect)
            pygame.draw.rect(self.screen, ACCENT_BLUE if current_value != 0 else BORDER_COLOR, value_rect, 2)

            value_text = self.fonts['label'].render(f"{current_value:+d}", True, ACCENT_AMBER if current_value != 0 else TEXT_SECONDARY)
            value_text_rect = value_text.get_rect(center=value_rect.center)
            self.screen.blit(value_text, value_text_rect)

            base_min, base_max = arm_base_values.get(offset_name, (0, 0))
            target_min = base_min + current_value
            target_max = base_max + current_value
            target_text = self.fonts['small'].render(f"→ {target_min}-{target_max}", True, TEXT_SECONDARY)
            self.screen.blit(target_text, (scale_x(380), scale_y(y_pos + 5)))

            for btn in self.arm_offset_buttons[offset_name].values():
                btn.draw(self.screen, self.fonts)

        pygame.draw.line(self.screen, BORDER_COLOR, 
                        (scale_x(60), scale_y(295)), 
                        (scale_x(740), scale_y(295)), 2)

        custom_label = self.fonts['label'].render("SET CUSTOM VALUE FOR", True, TEXT_SECONDARY)
        self.screen.blit(custom_label, (scale_x(60), scale_y(310)))

        selected_display = self.arm_offset_info[self.selected_arm_offset][0]
        selected_text = self.fonts['label'].render(f"[{selected_display}]:", True, ACCENT_BLUE)
        self.screen.blit(selected_text, (scale_x(300), scale_y(310)))

        self.arm_offset_custom_input.draw(self.screen, self.fonts)
        self.apply_arm_custom_btn.draw(self.screen, self.fonts)
        self.test_arm_offsets_btn.draw(self.screen, self.fonts)

        info_text = self.fonts['small'].render("CHANGES AUTO-SAVE TO CONFIG.INI | USE TEST BUTTON TO VERIFY", True, (0, 200, 255))
        info_rect = info_text.get_rect(center=(WINDOW_WIDTH // 2, scale_y(410)))
        self.screen.blit(info_text, info_rect)

    def draw_tab4(self):
        if self.movement_mode == "slow":
            self.mode_slow_btn.color = ACCENT_BLUE
            self.mode_fast_btn.color = MID_DARK
        else:
            self.mode_slow_btn.color = MID_DARK
            self.mode_fast_btn.color = ACCENT_BLUE

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
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            for offset_name, y_pos in self.leg_offset_rows.items():
                select_box = pygame.Rect(scale_x(60), scale_y(y_pos + 2), scale_x(20), scale_y(26))
                if select_box.collidepoint(mouse_pos):
                    self.selected_leg_offset = offset_name
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
                            self.set_status(f"⚠ Value would exceed safe range (10-600)")
                            return
                    else:  # Leg servos
                        base_forward = int(servo_config.get('forwardLeftLeg' if channel == 2 else 'forwardRightLeg', 300))
                        base_back = int(servo_config.get('backLeftLeg' if channel == 2 else 'backRightLeg', 300))

                        target_forward = base_forward + new_value
                        target_back = base_back + new_value
                        if target_forward < 10 or target_forward > 600 or target_back < 10 or target_back > 600:
                            self.set_status(f"⚠ Value would exceed safe range (10-600)")
                            return

                    offset_values[offset_name] = new_value

                    if save_offset_to_config(offset_name, new_value):
                        display_name = self.leg_offset_info[offset_name][0]
                        self.set_status(f"✓ {display_name}: {new_value:+d} saved")
                    else:
                        self.set_status(f"⚠ Failed to save offset")

                    return

        self.leg_offset_custom_input.handle_event(event)

        if self.apply_leg_custom_btn.handle_event(event):
            try:
                custom_value = int(self.leg_offset_custom_input.text)

                channel = self.leg_offset_info[self.selected_leg_offset][1]
                if channel in [0, 1]:  

                    base_up = int(servo_config.get('leftUpHeight' if channel == 0 else 'rightUpHeight', 350))
                    base_down = int(servo_config.get('leftDownHeight' if channel == 0 else 'rightDownHeight', 350))
                    target_up = base_up + custom_value
                    target_down = base_down + custom_value
                    if target_up < 10 or target_up > 600 or target_down < 10 or target_down > 600:
                        self.set_status(f"⚠ Value would exceed safe range (10-600)")
                        return
                else:  # Leg servos
                    base_forward = int(servo_config.get('forwardLeftLeg' if channel == 2 else 'forwardRightLeg', 300))
                    base_back = int(servo_config.get('backLeftLeg' if channel == 2 else 'backRightLeg', 300))
                    target_forward = base_forward + custom_value
                    target_back = base_back + custom_value
                    if target_forward < 10 or target_forward > 600 or target_back < 10 or target_back > 600:
                        self.set_status(f"⚠ Value would exceed safe range (10-600)")
                        return

                offset_values[self.selected_leg_offset] = custom_value

                if save_offset_to_config(self.selected_leg_offset, custom_value):
                    display_name = self.leg_offset_info[self.selected_leg_offset][0]
                    self.set_status(f"✓ {display_name}: {custom_value:+d} saved")

                    self.leg_offset_custom_input.text = "0"
                else:
                    self.set_status(f"⚠ Failed to save offset")
            except ValueError:
                self.set_status("⚠ Invalid value - enter a number")

        if self.test_leg_offsets_btn.handle_event(event):
            self.set_status("⏳ Testing offsets...")
            if reload_and_test():
                self.set_status("✓ Offsets tested - servos at reset position")
            else:
                self.set_status("⚠ Test failed - check console")

    def handle_tab3_events(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            for offset_name, y_pos in self.arm_offset_rows.items():
                select_box = pygame.Rect(scale_x(60), scale_y(y_pos + 2), scale_x(20), scale_y(24))
                if select_box.collidepoint(mouse_pos):
                    self.selected_arm_offset = offset_name
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
                        self.set_status(f"⚠ Value would exceed safe range (10-600)")
                        return

                    offset_values[offset_name] = new_value

                    if save_offset_to_config(offset_name, new_value):
                        display_name = self.arm_offset_info[offset_name][0]
                        self.set_status(f"✓ {display_name}: {new_value:+d} saved")
                    else:
                        self.set_status(f"⚠ Failed to save offset")

                    return

        self.arm_offset_custom_input.handle_event(event)

        if self.apply_arm_custom_btn.handle_event(event):
            try:
                custom_value = int(self.arm_offset_custom_input.text)

                base_min, base_max = arm_base_values.get(self.selected_arm_offset, (0, 0))
                target_min = base_min + custom_value
                target_max = base_max + custom_value

                if target_min < 10 or target_min > 600 or target_max < 10 or target_max > 600:
                    self.set_status(f"⚠ Value would exceed safe range (10-600)")
                    return

                offset_values[self.selected_arm_offset] = custom_value

                if save_offset_to_config(self.selected_arm_offset, custom_value):
                    display_name = self.arm_offset_info[self.selected_arm_offset][0]
                    self.set_status(f"✓ {display_name}: {custom_value:+d} saved")

                    self.arm_offset_custom_input.text = "0"
                else:
                    self.set_status(f"⚠ Failed to save offset")
            except ValueError:
                self.set_status("⚠ Invalid value - enter a number")

        if self.test_arm_offsets_btn.handle_event(event):
            self.set_status("⏳ Testing offsets...")
            if reload_and_test():
                self.set_status("✓ Offsets tested - servos at reset position")
            else:
                self.set_status("⚠ Test failed - check console")

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

            content_x = scale_x(25)
            content_y = scale_y(53)
            content_w = scale_x(750)
            content_h = scale_y(387)
            content_rect = pygame.Rect(content_x, content_y, content_w, content_h)

            pygame.draw.rect(self.screen, MID_DARK, content_rect)
            pygame.draw.rect(self.screen, BORDER_COLOR, content_rect, 2)

            bracket_size = scale_x(20)
            bracket_thickness = 2

            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x, content_y), (content_x + bracket_size, content_y), bracket_thickness)
            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x, content_y), (content_x, content_y + bracket_size), bracket_thickness)

            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x + content_w, content_y), (content_x + content_w - bracket_size, content_y), bracket_thickness)
            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x + content_w, content_y), (content_x + content_w, content_y + bracket_size), bracket_thickness)

            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x, content_y + content_h), (content_x + bracket_size, content_y + content_h), bracket_thickness)
            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x, content_y + content_h), (content_x, content_y + content_h - bracket_size), bracket_thickness)

            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x + content_w, content_y + content_h), (content_x + content_w - bracket_size, content_y + content_h), bracket_thickness)
            pygame.draw.line(self.screen, (0, 200, 255), 
                           (content_x + content_w, content_y + content_h), (content_x + content_w, content_y + content_h - bracket_size), bracket_thickness)

            grid_spacing = scale_x(50)
            for x in range(content_x, content_x + content_w, grid_spacing):
                pygame.draw.line(self.screen, (30, 32, 35), (x, content_y), (x, content_y + content_h), 1)
            for y in range(content_y, content_y + content_h, grid_spacing):
                pygame.draw.line(self.screen, (30, 32, 35), (content_x, y), (content_x + content_w, y), 1)

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

        disable_all_servos()
        pygame.quit()
        sys.exit()

def adjust_offsets():
    global offset_values

    while True:
        print("\n" + "="*60)
        print("SERVO OFFSET ADJUSTMENT")
        print("="*60)
        print("\nCurrent Offset Values:")
        print(f"  1. Left Height Offset:    {offset_values['perfectLeftHeightOffset']:+4d}")
        print(f"  2. Right Height Offset:   {offset_values['perfectRightHeightOffset']:+4d}")
        print(f"  3. Left Leg Offset:       {offset_values['perfectLeftLegOffset']:+4d}")
        print(f"  4. Right Leg Offset:      {offset_values['perfectRightLegOffset']:+4d}")
        print(f"  5. Left Main Arm Offset:  {offset_values['leftMainOffset']:+4d}")
        print(f"  6. Left Forearm Offset:   {offset_values['leftForearmOffset']:+4d}")
        print(f"  7. Left Hand Offset:      {offset_values['leftHandOffset']:+4d}")
        print(f"  8. Right Main Arm Offset: {offset_values['rightMainOffset']:+4d}")
        print(f"  9. Right Forearm Offset:  {offset_values['rightForearmOffset']:+4d}")
        print(f" 10. Right Hand Offset:     {offset_values['rightHandOffset']:+4d}")
        print("\n 11. Return to main menu")
        print("="*60)

        choice = input("\nSelect offset to adjust (1-11): ").strip()

        if choice == '11':
            print("\nFinalizing...")
            try:
                global config
                config = load_config()
                importlib.reload(servoctl)
                globals().update({name: getattr(servoctl, name) for name in dir(servoctl) if not name.startswith('_')})
                print("OK Ready")
            except Exception as e:
                print(f"WARNING Reload error: {e}")
            break

        elif choice in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']:
            offset_map = {
                '1': ('perfectLeftHeightOffset', 'Left Height', 0),
                '2': ('perfectRightHeightOffset', 'Right Height', 1),
                '3': ('perfectLeftLegOffset', 'Left Leg', 2),
                '4': ('perfectRightLegOffset', 'Right Leg', 3),
                '5': ('leftMainOffset', 'Left Main Arm', 4),
                '6': ('leftForearmOffset', 'Left Forearm', 5),
                '7': ('leftHandOffset', 'Left Hand', 6),
                '8': ('rightMainOffset', 'Right Main Arm', 7),
                '9': ('rightForearmOffset', 'Right Forearm', 8),
                '10': ('rightHandOffset', 'Right Hand', 9)
            }

            offset_name, servo_name, channel = offset_map[choice]
            current_value = offset_values[offset_name]

            print(f"\n--- Adjusting {servo_name} Offset ---")
            print(f"Current value: {current_value:+d}")

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

def set_single_servo():
    while True:
        try:
            print("\n=== SERVO PIN LAYOUT ===")
            print("Height Servos:")
            print("  #0 - Left Height Servo")
            print("  #1 - Right Height Servo")
            print("\nLeg Servos:")
            print("  #2 - Left Leg")
            print("  #3 - Right Leg")
            print("\nLeft Arm Servos:")
            print("  #4 - Left Main Arm")
            print("  #5 - Left Forearm")
            print("  #6 - Left Hand")
            print("\nRight Arm Servos:")
            print("  #7 - Right Main Arm")
            print("  #8 - Right Forearm")
            print("  #9 - Right Hand")
            print("\nOther:")
            print("  #10-15 - Additional servos")
            print("========================\n")

            channel = int(input(f"Enter servo number (0-15): "))
            if channel < 0 or channel > 15:
                print("Channel must be between 0 and 15")
                continue

            pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break
        except ValueError:
            print("Invalid input. Please try again.")
            break

def control():
    actions = [
        ("Reset Position", "reset_positions"),
        ("Pose", "pose"),
        ("Laugh", "laugh"),
        ("Bow", "bow"),
        ("Tilt Right", "tilt_right"),
        ("Tilt Left", "tilt_left"),
        ("Side-Side", "side_side"),
        ("Wave Right", "wave_right"),
        ("Wave Left", "wave_left"),
        ("Move Forward", "step_forward"),
        ("Move Backward", "step_backward"),
        ("Turn Right", "turn_right"),
        ("Turn Left", "turn_left"),
        ("Walk Forward", "walk_forward"),
        ("Walk Backward", "walk_backward"),
        ("Turn Left Slow", "turn_left_slow"),
        ("Turn Right Slow", "turn_right_slow")
    ]

    try:
        print("\n=== MOVEMENT CONTROLS ===")
        for i, (name, _) in enumerate(actions):
            print(f"{i} - {name}")
        print("========================\n")

        main_input = input("> ")
        try:
            choice = int(main_input)
            if 0 <= choice < len(actions):
                action_name, function_name = actions[choice]
                print(f"Executing {action_name}...")
                func = globals()[function_name]
                func()
                print(f"OK {action_name} complete")
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
            """Custom Movements keep code enclosed"""
            reset_positions()
            """-----------------------------------"""


            move_legs(100, 50, 60, 50, 0.8)
            move_arm(98, None, None, None, None, None, 0.92)
            move_arm(None, 100, None, None, None, None,  1)
            move_arm(None, 50, 90, None, None, None,  0.92)
            move_arm(None, 100, 20, None, None, None,  0.92)
            move_arm(None, 50, 90, None, None, None,  0.92)
            move_arm(None, 100, 20, None, None, None,  0.92)
            move_arm(None, 50, 90, None, None, None,  0.92)
            move_arm(None, 100, 20, None, None, None,  0.92)
            move_arm(98, 80, 1, None, None, None,  0.92)
            move_arm(98, 1, 1, None, None, None,  0.92)
            move_arm(1, 1, 1, 1, None, None,  0.92)
            move_legs(50, 50, 50, 50, 0.8)

            step_forward()

            move_legs(50, 100, 50, 60, 0.8)
            move_arm(None, None, None, 98, None, None, 0.92)
            move_arm(None, None, None, None, 100, None, 1)
            move_arm(None, None, None, None, 50, 90, 0.92)
            move_arm(None, None, None, None, 100, 20, 0.92)
            move_arm(None, None, None, None, 50, 90, 0.92)
            move_arm(None, None, None, None, 100, 20, 0.92)
            move_arm(None, None, None, None, 50, 90, 0.92)
            move_arm(None, None, None, None, 100, 20, 0.92)
            move_arm(None, None, None, 98, 80, 1, 0.92)
            move_arm(None, None, None, 98, 1, 1, 0.92)
            move_arm(1, None, None, 1, 1, 1, 0.92)
            move_legs(50, 50, 50, 50, 0.8)

            walk_backward()

            """keep code enclosed"""
            disable_all_servos()
            pass
            """------------------"""
        else:
            print("Invalid selection. Defaulting to GUI mode...")
            gui = ServoControllerGUI()
            gui.run()
    except KeyboardInterrupt:
        disable_all_servos()
        print("\nOK Servos disabled. Exiting.")