"""
Module: Terminal
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
import time
import os
import json
from pathlib import Path
from typing import List, Tuple, Callable, Optional

from modules.module_config import load_config

CONFIG = load_config()

class TerminalSystem:
    def __init__(self, width: int, height: int, bg_color=(0, 0, 0), bg_alpha=13, 
                 battery_module=None,
                 cpu_temp_module=None,
                 show_cpu_temp=False,
                 on_background_change: Optional[Callable] = None,
                 on_shutdown: Optional[Callable] = None,
                 on_spectrum_change: Optional[Callable] = None,
                 on_camera_toggle: Optional[Callable] = None,
                 on_exit: Optional[Callable] = None):
        self.width = width
        self.height = height
        self.bg_color = bg_color
        self.bg_alpha = bg_alpha

        self.battery_module = battery_module
        self.cpu_temp_module = cpu_temp_module
        self.show_cpu_temp = show_cpu_temp

        self.last_cpu_update_time = 0
        self.cpu_update_interval = 30
        self.current_cpu_temp = 0.0
        self.cpu_temp_history = []
        self.max_temp_history = 20
        self.on_background_change = on_background_change
        self.on_shutdown = on_shutdown
        self.on_spectrum_change = on_spectrum_change
        self.on_camera_toggle = on_camera_toggle
        self.on_exit = on_exit

        self.primary_color = (0, 255, 255)  
        self.secondary_color = (0, 180, 200)  
        self.accent_color = (0, 120, 150)  
        self.bg_terminal = (5, 15, 20)  
        self.bg_panel = (10, 25, 30)  
        self.border_color = (0, 200, 220)  
        self.text_color = (0, 240, 200)  
        self.dim_text_color = (0, 120, 120)  
        self.label_color = (0, 150, 180)  
        self.warning_color = (255, 100, 0)  
        self.status_active = (0, 255, 100)  
        self.status_warning = (255, 180, 0)  
        self.status_error = (255, 50, 50)

        self.toolbar_height = int(height * 0.06)
        self.bottom_toolbar_height = int(height * 0.06)
        self.terminal_height = height - self.toolbar_height - self.bottom_toolbar_height

        self.line_spacing = 5
        self.padding = 15
        self.border_thickness = 2

        try:
            self.font = pygame.font.Font("UI/mono.ttf", 20)
            self.font_bold = pygame.font.Font("UI/mono.ttf", 20)
            self.toolbar_font = pygame.font.Font("UI/pixelmix.ttf", 14)
            self.label_font = pygame.font.Font("UI/mono.ttf", 12)
            self.title_font = pygame.font.Font("UI/mono.ttf", 21)
            self.code_font = pygame.font.Font("UI/mono.ttf", 17)
        except:
            self.font = pygame.font.SysFont("monospace", 20, bold=False)
            self.font_bold = pygame.font.SysFont("monospace", 20, bold=True)
            self.toolbar_font = pygame.font.SysFont("monospace", 14)
            self.label_font = pygame.font.SysFont("monospace", 12)
            self.title_font = pygame.font.SysFont("monospace", 21)
            self.code_font = pygame.font.SysFont("monospace", 17)

        self.messages: List[Tuple[str, str, str, float]] = []
        self.max_messages = 1000

        self.scroll_offset = 0
        self.auto_scroll = True

        self.line_height = self.font.get_linesize() + self.line_spacing
        self.max_visible_lines = (self.terminal_height - 2 * self.padding - 40) // self.line_height

        self.wrapped_cache = []
        self.cache_dirty = True

        self.dragging = False

        self.last_drag_y = 0
        self.drag_positions = []
        self.max_drag_buffer = 3
        self.accumulated_scroll = 0.0  

        self.log_dir = Path.home() / ".local" / "share" / "tars_ai"
        self.log_file = self.log_dir / "terminal_log.json"
        self.max_log_messages = 100

        self._ensure_log_dir()
        self._load_messages()

        self.top_buttons = [
            {"label": "CLEAR", "code": "CLR-01", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "BG", "code": "BG-SW", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "WAVE", "code": "SPK-CY", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "PWR-DN", "code": "PWR-DN", "rect": None, "active": False, "color": "warning", "position": "right"},
        ]

        self.bottom_buttons = [
            {"label": "CAM", "code": "CAM-01", "rect": None, "active": False, "color": None, "position": "left"},
        ]

        self._init_buttons()

        self.thinking = False
        self.thinking_time = 0
        self.action_flash = 0
        self.memory_pulse = 0
        self.scan_line = 0
        self.status_blink = 0

        self.show_power_menu = False
        self.power_menu_buttons = []

        self.camera_active = False

        self.overlay_surface = pygame.Surface((width, height), pygame.SRCALPHA)

    def _ensure_log_dir(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _load_messages(self):
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    for msg in data:
                        self.messages.append((msg['key'], msg['value'], msg['type'], msg['timestamp']))
                    self.cache_dirty = True
            except Exception as e:
                print(f"Failed to load messages: {e}")

    def _save_messages(self):
        try:
            messages_to_save = [
                (key, value, msg_type, timestamp)
                for key, value, msg_type, timestamp in self.messages[-self.max_log_messages:]
                if key.upper() not in ["SYSTEM", "SYS"]
            ]
            data = [
                {
                    'key': key,
                    'value': value,
                    'type': msg_type,
                    'timestamp': timestamp
                }
                for key, value, msg_type, timestamp in messages_to_save
            ]
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save messages: {e}")

    def _init_buttons(self):
        button_width = 90
        button_height_top = self.toolbar_height - 10
        button_height_bottom = self.bottom_toolbar_height - 10
        button_spacing = 8
        start_y_top = 5
        start_y_bottom = self.toolbar_height + self.terminal_height + 5

        left_x = 10
        left_index = 0

        for button in self.top_buttons:
            if button.get("position") == "right":
                x = self.width - button_width - 10
            else:
                x = left_x + left_index * (button_width + button_spacing)
                left_index += 1

            button["rect"] = pygame.Rect(x, start_y_top, button_width, button_height_top)

        left_x = 10
        left_index = 0

        for button in self.bottom_buttons:
            if button.get("position") == "right":
                x = self.width - button_width - 10
            else:
                x = left_x + left_index * (button_width + button_spacing)
                left_index += 1

            button["rect"] = pygame.Rect(x, start_y_bottom, button_width, button_height_bottom)

    def _update_wrapped_cache(self):
        if not self.cache_dirty:
            return

        self.wrapped_cache = []
        max_text_width = self.width - 2 * self.padding - 60

        for key, value, msg_type, timestamp in self.messages:
            full_text = f"{key}: {value}"
            wrapped_lines = self._wrap_text(full_text, max_text_width)
            self.wrapped_cache.append((key, value, msg_type, wrapped_lines))

        self.cache_dirty = False

    def add_message(self, key: str, value: str, msg_type: str = "INFO"):
        timestamp = time.time()
        self.messages.append((key, value, msg_type, timestamp))
        self.cache_dirty = True

        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
            self.cache_dirty = True

        self.scroll_offset = 0
        self.auto_scroll = True

        self._save_messages()

    def clear_messages(self):
        self.messages.clear()
        self.wrapped_cache.clear()
        self.scroll_offset = 0
        self.cache_dirty = True
        self._save_messages()  

    def scroll_up(self, lines=3):
        self._update_wrapped_cache()
        total_lines = sum(len(wrapped_lines) for _, _, _, wrapped_lines in self.wrapped_cache)
        scroll_padding = int(self.max_visible_lines * 0.75)
        max_scroll = max(0, total_lines - self.max_visible_lines) + scroll_padding

        self.scroll_offset = min(self.scroll_offset + lines, max_scroll)
        if self.scroll_offset > 0:
            self.auto_scroll = False

    def scroll_down(self, lines=3):
        scroll_padding = int(self.max_visible_lines * 0.75)
        self.scroll_offset = max(-scroll_padding, self.scroll_offset - lines)
        if self.scroll_offset == 0:
            self.auto_scroll = True

    def handle_scroll_wheel(self, wheel_y: int):
        if wheel_y > 0:
            self.scroll_down(3)
        elif wheel_y < 0:
            self.scroll_up(3)

    def handle_mouse_down(self, pos: Tuple[int, int]):
        terminal_y_start = self.toolbar_height
        terminal_y_end = self.toolbar_height + self.terminal_height

        if terminal_y_start <= pos[1] <= terminal_y_end:
            self.dragging = True
            self.last_drag_y = pos[1]
            self.drag_positions = [pos[1]]
            self.accumulated_scroll = 0.0  

    def handle_mouse_up(self, pos: Tuple[int, int]):
        self.dragging = False
        self.drag_positions = []
        self.accumulated_scroll = 0.0  

    def handle_mouse_motion(self, pos: Tuple[int, int]):
        if self.dragging:
            current_y = pos[1]

            self.drag_positions.append(current_y)
            if len(self.drag_positions) > self.max_drag_buffer:
                self.drag_positions.pop(0)

            smoothed_y = sum(self.drag_positions) / len(self.drag_positions)

            pixel_delta = self.last_drag_y - smoothed_y

            self.last_drag_y = smoothed_y

            self.accumulated_scroll += pixel_delta / self.line_height

            lines_to_scroll = int(self.accumulated_scroll)

            if lines_to_scroll != 0:

                self.scroll_offset += lines_to_scroll

                self.accumulated_scroll -= lines_to_scroll

                self._update_wrapped_cache()
                total_lines = sum(len(wrapped_lines) for _, _, _, wrapped_lines in self.wrapped_cache)
                scroll_padding = int(self.max_visible_lines * 0.75)
                max_scroll = max(0, total_lines - self.max_visible_lines) + scroll_padding

                self.scroll_offset = max(-scroll_padding, min(self.scroll_offset, max_scroll))

                if self.scroll_offset > 0:
                    self.auto_scroll = False
                elif self.scroll_offset == 0:
                    self.auto_scroll = True

    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if self.font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else ['']

    def set_camera_active(self, active: bool):
        self.camera_active = active

    def _init_power_menu(self):
        modal_center_x = self.width // 2
        modal_center_y = self.height // 2
        button_width = 160
        button_height = 50
        button_spacing = 20

        self.power_menu_buttons = [
            {
                "label": "EXIT PROGRAM",
                "action": "exit",
                "rect": pygame.Rect(
                    modal_center_x - button_width - button_spacing // 2,
                    modal_center_y + 20,
                    button_width,
                    button_height
                )
            },
            {
                "label": "SHUTDOWN",
                "action": "shutdown",
                "rect": pygame.Rect(
                    modal_center_x + button_spacing // 2,
                    modal_center_y + 20,
                    button_width,
                    button_height
                )
            }
        ]

    def handle_click(self, pos: Tuple[int, int]):

        if self.show_power_menu:
            for button in self.power_menu_buttons:
                if button["rect"].collidepoint(pos):
                    if button["action"] == "exit":
                        if self.on_exit:
                            self.on_exit()
                    elif button["action"] == "shutdown":
                        if self.on_shutdown:
                            self.on_shutdown()
                    self.show_power_menu = False
                    return

            modal_rect = pygame.Rect(self.width // 2 - 200, self.height // 2 - 100, 400, 200)
            if not modal_rect.collidepoint(pos):
                self.show_power_menu = False
            return

        for button in self.top_buttons:
            if button["rect"] and button["rect"].collidepoint(pos):
                if button["label"] == "CLEAR":
                    self.clear_messages()
                elif button["label"] == "BG":
                    if self.on_background_change:
                        self.on_background_change()
                elif button["label"] == "WAVE":
                    if self.on_spectrum_change:
                        self.on_spectrum_change()
                elif button["label"] == "PWR-DN":
                    self.show_power_menu = True
                    self._init_power_menu()

        for button in self.bottom_buttons:
            if button["rect"] and button["rect"].collidepoint(pos):
                if button["label"] == "CAM":
                    if self.on_camera_toggle:
                        self.on_camera_toggle()

    def think(self):
        self.thinking = True
        self.thinking_time = time.time()

    def stop_thinking(self):
        self.thinking = False

    def add_memory(self):
        self.memory_pulse = 1.0
        self.action_flash = 1.0

    def update(self):
        current_time = time.time()

        if self.thinking:
            elapsed = current_time - self.thinking_time
            if elapsed > 5.0:
                self.thinking = False

        if self.memory_pulse > 0:
            self.memory_pulse -= 0.02
            if self.memory_pulse < 0:
                self.memory_pulse = 0

        if self.action_flash > 0:
            self.action_flash -= 0.05
            if self.action_flash < 0:
                self.action_flash = 0
            self.scan_line = (self.scan_line + 4) % self.terminal_height

        self.status_blink = (self.status_blink + 0.1) % (2 * 3.14159)

        if self.cpu_temp_module:
            if current_time - self.last_cpu_update_time >= self.cpu_update_interval:
                self.current_cpu_temp = self.cpu_temp_module.get_temperature()
                self.cpu_temp_history.append(self.current_cpu_temp)
                if len(self.cpu_temp_history) > self.max_temp_history:
                    self.cpu_temp_history.pop(0)
                self.last_cpu_update_time = current_time

    def _draw_tech_button(self, surface, rect, label, code, active=False, color_type=None, disabled=False):
        if disabled:

            bg_color = (20, 20, 20, 150)
            border_color = (60, 60, 60, 180)
        elif color_type == "warning":
            bg_color = (50, 30, 20, 200)
            border_color = (180, 100, 40, 220)
        elif active:
            bg_color = (20, 60, 80, 220)
            border_color = (*self.primary_color, 255)
        else:
            bg_color = (*self.bg_panel, 200)
            border_color = (*self.border_color, 200)

        pygame.draw.rect(surface, bg_color, rect)

        pygame.draw.rect(surface, border_color, rect, 2)

        inner_rect = rect.inflate(-4, -4)
        pygame.draw.rect(surface, (*self.accent_color, 150), inner_rect, 1)

        bracket_size = 6
        bracket_color = border_color

        pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left + bracket_size, rect.top), 2)
        pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left, rect.top + bracket_size), 2)

        pygame.draw.line(surface, bracket_color, rect.topright, (rect.right - bracket_size, rect.top), 2)
        pygame.draw.line(surface, bracket_color, (rect.right - 1, rect.top), (rect.right - 1, rect.top + bracket_size), 2)

        if disabled:
            text_color = (80, 80, 80)
        else:
            text_color = self.primary_color if active or color_type == "warning" else self.text_color
        text_surface = self.toolbar_font.render(label, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        surface.blit(text_surface, text_rect)

    def _draw_battery_indicator(self, surface, x, y, width, height):
        if not self.battery_module:
            return

        try:
            battery_status = self.battery_module.get_battery_status()

            if not battery_status.get('sensor_initialized', False):
                return

            percentage = battery_status['normalized_percentage']
            is_charging = battery_status['is_charging']

            if percentage > 60:
                fill_color = (0, 200, 80)  

            elif percentage > 20:
                fill_color = (255, 160, 0)  

            else:
                fill_color = (255, 40, 40)  

            bg_fill_color = (10, 20, 35)

            body_width = width - 8
            body_height = height - 8
            body_x = x + 4
            body_y = y + 4

            pygame.draw.rect(surface, self.border_color, 
                           (body_x, body_y, body_width, body_height), 2)

            tip_width = 4
            tip_height = int(body_height * 0.5)
            tip_x = body_x + body_width
            tip_y = body_y + (body_height - tip_height) // 2
            pygame.draw.rect(surface, self.border_color, 
                           (tip_x, tip_y, tip_width, tip_height))

            pygame.draw.rect(surface, bg_fill_color,
                           (body_x + 2, body_y + 2, body_width - 4, body_height - 4))

            fill_width = int((body_width - 4) * (percentage / 100))
            if fill_width > 0:
                pygame.draw.rect(surface, fill_color,
                               (body_x + 2, body_y + 2, fill_width, body_height - 4))

            try:
                battery_font = pygame.font.SysFont("arial", 16, bold=True)
            except:
                battery_font = self.font_bold

            text = f"{percentage}"
            text_surface = battery_font.render(text, True, (0, 255, 255))
            
            if is_charging:
                center_x = body_x + body_width // 2
                center_y = body_y + body_height // 2
                
                text_y = center_y - 10
                for ox in [-1, 0, 1]:
                    for oy in [-1, 0, 1]:
                        if ox != 0 or oy != 0:
                            outline = battery_font.render(text, True, (0, 0, 0))
                            outline_rect = outline.get_rect(center=(center_x + ox, text_y + oy))
                            surface.blit(outline, outline_rect)
                text_rect = text_surface.get_rect(center=(center_x, text_y))
                surface.blit(text_surface, text_rect)
                
                bolt_y = center_y + 6
                bolt_points = [
                    (center_x + 4, bolt_y - 10),
                    (center_x - 4, bolt_y - 1),
                    (center_x, bolt_y - 1),
                    (center_x - 4, bolt_y + 10),
                    (center_x + 4, bolt_y + 1),
                    (center_x, bolt_y + 1),
                ]
                pygame.draw.polygon(surface, (0, 0, 0), bolt_points)
            else:
                for offset_x in [-1, 0, 1]:
                    for offset_y in [-1, 0, 1]:
                        if offset_x != 0 or offset_y != 0:
                            outline_surface = battery_font.render(text, True, (0, 0, 0))
                            outline_rect = outline_surface.get_rect(center=(body_x + body_width // 2 + offset_x, body_y + body_height // 2 + offset_y))
                            surface.blit(outline_surface, outline_rect)

                text_rect = text_surface.get_rect(center=(body_x + body_width // 2, body_y + body_height // 2))
                surface.blit(text_surface, text_rect)

        except Exception as e:
            pass  

    def _draw_cpu_temp_indicator(self, surface, x, y, width, height):
        if not self.cpu_temp_module:
            return
        
        try:
            temp = self.current_cpu_temp
            text_color = self.text_color
            border_color = (*self.border_color, 200)
            rect = pygame.Rect(x, y, width, height)
            bg_color = (*self.bg_panel, 200)
            pygame.draw.rect(surface, bg_color, rect)
            pygame.draw.rect(surface, border_color, rect, 2)
            inner_rect = rect.inflate(-4, -4)
            pygame.draw.rect(surface, (*self.accent_color, 150), inner_rect, 1)
            bracket_size = 6
            bracket_color = border_color
            pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left + bracket_size, rect.top), 2)
            pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left, rect.top + bracket_size), 2)
            pygame.draw.line(surface, bracket_color, rect.topright, (rect.right - bracket_size, rect.top), 2)
            pygame.draw.line(surface, bracket_color, (rect.right - 1, rect.top), (rect.right - 1, rect.top + bracket_size), 2)
            text = f"{int(temp)}°C"
            text_surface = self.toolbar_font.render(text, True, text_color)
            text_rect = text_surface.get_rect(center=(rect.centerx, rect.centery - 5))
            surface.blit(text_surface, text_rect)
            graph_area_y = text_rect.bottom + 4
            graph_area_height = rect.bottom - graph_area_y - 6
            graph_area_left = rect.left + 8
            graph_area_right = rect.right - 8
            graph_area_width = graph_area_right - graph_area_left
            
            if self.cpu_temp_history and len(self.cpu_temp_history) > 1 and graph_area_height > 0:
                min_temp = 30
                max_temp = 85
                temp_range = max_temp - min_temp

                num_points = len(self.cpu_temp_history)
                point_spacing = graph_area_width / max(num_points - 1, 1)
                
                if temp < 70:
                    graph_color = (0, 200, 80)
                elif temp < 75:
                    graph_color = (255, 160, 0)
                else:
                    graph_color = (255, 40, 40)
                
                points = []
                for i, temp_val in enumerate(self.cpu_temp_history):
                    x_pos = graph_area_left + (i * point_spacing)
                    temp_normalized = (temp_val - min_temp) / temp_range
                    temp_normalized = max(0, min(1, temp_normalized))
                    y_pos = graph_area_y + graph_area_height - (temp_normalized * graph_area_height)
                    
                    points.append((int(x_pos), int(y_pos)))
                
                if len(points) > 1:
                    pygame.draw.lines(surface, graph_color, False, points, 2)
                    for point in points:
                        pygame.draw.circle(surface, graph_color, point, 2)
            
        except Exception as e:
            pass


    def _draw_power_menu(self, surface):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        modal_width = 400
        modal_height = 200
        modal_x = self.width // 2 - modal_width // 2
        modal_y = self.height // 2 - modal_height // 2
        modal_rect = pygame.Rect(modal_x, modal_y, modal_width, modal_height)

        pygame.draw.rect(surface, (*self.bg_panel, 250), modal_rect)
        pygame.draw.rect(surface, self.border_color, modal_rect, 3)

        inner_rect = modal_rect.inflate(-6, -6)
        pygame.draw.rect(surface, (*self.accent_color, 100), inner_rect, 1)

        title = "POWER OPTIONS"
        title_surface = self.title_font.render(title, True, self.primary_color)
        title_rect = title_surface.get_rect(center=(modal_x + modal_width // 2, modal_y + 35))
        surface.blit(title_surface, title_rect)

        line_y = modal_y + 60
        pygame.draw.line(surface, self.border_color, 
                        (modal_x + 20, line_y), (modal_x + modal_width - 20, line_y), 2)

        for button in self.power_menu_buttons:
            rect = button["rect"]
            label = button["label"]
            action = button["action"]

            if action == "shutdown":
                bg_color = (80, 20, 20, 220)
                border_color = (255, 80, 80, 255)
                text_color = (255, 120, 120)
            else:
                bg_color = (20, 60, 80, 220)
                border_color = self.primary_color
                text_color = self.primary_color

            pygame.draw.rect(surface, bg_color, rect)
            pygame.draw.rect(surface, border_color, rect, 2)

            corner_size = 8
            pygame.draw.line(surface, border_color, rect.topleft, 
                           (rect.left + corner_size, rect.top), 3)
            pygame.draw.line(surface, border_color, rect.topleft, 
                           (rect.left, rect.top + corner_size), 3)
            pygame.draw.line(surface, border_color, 
                           (rect.right - 1, rect.top), (rect.right - corner_size - 1, rect.top), 3)
            pygame.draw.line(surface, border_color, 
                           (rect.right - 1, rect.top), (rect.right - 1, rect.top + corner_size), 3)

            text_surface = self.toolbar_font.render(label, True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

    def draw(self, surface):
        self._update_wrapped_cache()

        self.overlay_surface.fill((0, 0, 0, 0))

        toolbar_rect = pygame.Rect(0, 0, self.width, self.toolbar_height)
        toolbar_bg = pygame.Surface((self.width, self.toolbar_height), pygame.SRCALPHA)
        toolbar_bg.fill((*self.bg_terminal, self.bg_alpha + 20))
        self.overlay_surface.blit(toolbar_bg, (0, 0))

        pygame.draw.line(self.overlay_surface, (*self.border_color, 200), 
                        (0, self.toolbar_height - 2), (self.width, self.toolbar_height - 2), 2)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 100), 
                        (0, self.toolbar_height - 1), (self.width, self.toolbar_height - 1), 1)

        for button in self.top_buttons:
            if button["rect"]:
                is_active = button["label"] == "PWR-DN" and self.show_power_menu
                self._draw_tech_button(self.overlay_surface, button["rect"], 
                                       button["label"], button["code"],
                                       is_active,
                                       button.get("color"))

        if self.battery_module:
            battery_width = 60
            battery_height = self.toolbar_height - 10
            battery_x = self.width - battery_width - 120
            battery_y = 5
            self._draw_battery_indicator(self.overlay_surface, battery_x, battery_y, 
                                        battery_width, battery_height)


        terminal_rect = pygame.Rect(0, self.toolbar_height, self.width, self.terminal_height)
        terminal_bg = pygame.Surface((self.width, self.terminal_height), pygame.SRCALPHA)
        terminal_bg.fill((*self.bg_terminal, self.bg_alpha))
        self.overlay_surface.blit(terminal_bg, (0, self.toolbar_height))

        pygame.draw.rect(self.overlay_surface, (*self.border_color, 200), terminal_rect, 2)

        header_y = self.toolbar_height + 8

        terminal_id = "TERM-A1"
        id_surface = self.code_font.render(terminal_id, True, self.primary_color)
        self.overlay_surface.blit(id_surface, (25, header_y + 2))

        status_text = "[PROCESSING]" if self.thinking else "[ACTIVE]"
        status_surface = self.label_font.render(status_text, True, self.label_color)
        self.overlay_surface.blit(status_surface, (120, header_y + 6))

        msg_count = f"MSG: {len(self.messages):03d}"
        count_surface = self.label_font.render(msg_count, True, self.dim_text_color)
        self.overlay_surface.blit(count_surface, (self.width - 80, header_y + 6))

        line_y = header_y + 22
        pygame.draw.line(self.overlay_surface, (*self.border_color, 180), 
                        (10, line_y), (self.width - 10, line_y), 1)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 80), 
                        (10, line_y + 1), (self.width - 10, line_y + 1), 1)

        if not self.camera_active:
            y_offset = line_y + 12
            start_y = y_offset

            all_lines = []
            reversed_cache = list(reversed(self.wrapped_cache))

            for key, value, msg_type, wrapped_lines in reversed_cache:
                for line_idx, line_text in enumerate(wrapped_lines):
                    all_lines.append((key, value, msg_type, line_text, line_idx))

            total_lines = len(all_lines)

            if self.scroll_offset < 0:

                y_offset += abs(self.scroll_offset) * self.line_height
                start_index = 0
                end_index = min(self.max_visible_lines, total_lines)
            else:
                start_index = self.scroll_offset
                end_index = min(start_index + self.max_visible_lines, total_lines)

            visible_lines = all_lines[start_index:end_index]

            terminal_draw_height = self.toolbar_height + self.terminal_height - start_y - self.padding

            line_count = 0
            for key, value, msg_type, line_text, line_idx in visible_lines:
                if y_offset + self.line_height > self.toolbar_height + self.terminal_height - self.padding:
                    break

                progress = (y_offset - start_y) / terminal_draw_height
                progress = max(0.0, min(1.0, progress))
                fade_alpha = 1.0 - (progress * 0.9)

                if line_idx == 0 and ':' in line_text:
                    parts = line_text.split(':', 1)
                    if len(parts) == 2:
                        user_part, msg_part = parts

                        if user_part == CONFIG['CHAR']['character_name']:
                            msg_color = (100, 200, 255)
                            code_color_base = (100, 200, 255)
                        elif user_part.upper() == "USER":
                            msg_color = (255, 255, 255)
                            code_color_base = (255, 255, 255)
                        else:
                            msg_color = (150, 150, 150)
                            code_color_base = (150, 150, 150)

                        code_text = f"[{user_part}]"
                        temp_surface = pygame.Surface((self.width, self.line_height), pygame.SRCALPHA)
                        code_surface = self.font_bold.render(code_text, True, code_color_base)
                        code_surface.set_alpha(int(255 * fade_alpha))

                        x_pos = self.padding + 5
                        temp_surface.blit(code_surface, (0, 0))
                        self.overlay_surface.blit(temp_surface, (x_pos, y_offset))

                        msg_surface = self.font.render(msg_part, True, msg_color)
                        msg_surface.set_alpha(int(255 * fade_alpha))

                        temp_surface2 = pygame.Surface((self.width, self.line_height), pygame.SRCALPHA)
                        temp_surface2.blit(msg_surface, (0, 0))
                        self.overlay_surface.blit(temp_surface2, (x_pos + code_surface.get_width() + 5, y_offset))
                else:
                    if key == CONFIG['CHAR']['character_name']:
                        cont_color = (100, 200, 255)
                    elif key.upper() == "USER":
                        cont_color = (255, 255, 255)
                    else:
                        cont_color = (150, 150, 150)

                    text_surface = self.font.render(line_text, True, cont_color)
                    text_surface.set_alpha(int(255 * fade_alpha))

                    temp_surface = pygame.Surface((self.width, self.line_height), pygame.SRCALPHA)
                    temp_surface.blit(text_surface, (0, 0))
                    self.overlay_surface.blit(temp_surface, (self.padding + 25, y_offset))

                y_offset += self.line_height
                line_count += 1

        if self.action_flash > 0:
            scan_alpha = int(self.action_flash * 60)
            scan_y = self.toolbar_height + self.scan_line
            pygame.draw.line(self.overlay_surface, (*self.primary_color, scan_alpha),
                           (5, scan_y), (self.width - 5, scan_y), 1)

        bracket_size = 12  
        bracket_thickness = 2
        bracket_color = (*self.border_color, 200)
        bracket_offset = 10

        term_left = bracket_offset
        term_right = self.width - bracket_offset
        term_top = self.toolbar_height + bracket_offset
        term_bottom = self.toolbar_height + self.terminal_height - bracket_offset

        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_top), (term_left + bracket_size, term_top), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_top), (term_left, term_top + bracket_size), bracket_thickness)

        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_top), (term_right - bracket_size, term_top), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_top), (term_right, term_top + bracket_size), bracket_thickness)

        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_bottom), (term_left + bracket_size, term_bottom), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_bottom), (term_left, term_bottom - bracket_size), bracket_thickness)

        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_bottom), (term_right - bracket_size, term_bottom), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_bottom), (term_right, term_bottom - bracket_size), bracket_thickness)

        gradient_height = 60
        gradient_start_y = self.toolbar_height + self.terminal_height - gradient_height

        for i in range(gradient_height):
            alpha = int((i / gradient_height) * 30)
            pygame.draw.line(self.overlay_surface, (0, 0, 0, alpha),
                           (5, gradient_start_y + i), (self.width - 5, gradient_start_y + i), 1)

        bottom_toolbar_y = self.toolbar_height + self.terminal_height
        bottom_toolbar_rect = pygame.Rect(0, bottom_toolbar_y, self.width, self.bottom_toolbar_height)
        bottom_toolbar_bg = pygame.Surface((self.width, self.bottom_toolbar_height), pygame.SRCALPHA)
        bottom_toolbar_bg.fill((*self.bg_terminal, self.bg_alpha + 20))
        self.overlay_surface.blit(bottom_toolbar_bg, (0, bottom_toolbar_y))

        pygame.draw.line(self.overlay_surface, (*self.border_color, 200), 
                        (0, bottom_toolbar_y), (self.width, bottom_toolbar_y), 2)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 100), 
                        (0, bottom_toolbar_y + 1), (self.width, bottom_toolbar_y + 1), 1)

        for button in self.bottom_buttons:
            if button["rect"]:
                is_active = button["label"] == "CAM" and self.camera_active
                self._draw_tech_button(self.overlay_surface, button["rect"], 
                                       button["label"], button["code"],
                                       is_active,
                                       button.get("color"))

        if self.cpu_temp_module and self.show_cpu_temp:
            cpu_width = 80
            cpu_height = self.bottom_toolbar_height - 10
            cpu_x = self.width - cpu_width - 10 
            cpu_y = bottom_toolbar_y + 5
            self._draw_cpu_temp_indicator(self.overlay_surface, cpu_x, cpu_y,
                                          cpu_width, cpu_height)

        surface.blit(self.overlay_surface, (0, 0))

        if self.show_power_menu:
            self._draw_power_menu(surface)