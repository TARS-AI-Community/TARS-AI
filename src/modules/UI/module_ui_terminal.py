"""
Module: Terminal
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
                 on_exit: Optional[Callable] = None,
                 on_app_select: Optional[Callable] = None,
                 on_app_back: Optional[Callable] = None):
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
        self.on_app_select = on_app_select
        self.on_app_back = on_app_back

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
            self._status_font = pygame.font.Font("UI/pixelmix.ttf", 22)
            self.label_font = pygame.font.Font("UI/mono.ttf", 12)
            self.title_font = pygame.font.Font("UI/mono.ttf", 21)
            self.code_font = pygame.font.Font("UI/mono.ttf", 17)
        except:
            self.font = pygame.font.SysFont("monospace", 20, bold=False)
            self.font_bold = pygame.font.SysFont("monospace", 20, bold=True)
            self.toolbar_font = pygame.font.SysFont("monospace", 14)
            self._status_font = pygame.font.SysFont("monospace", 22)
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

        self.last_click_time = 0
        self.click_cooldown = 400

        self.scroll_up_rect = None
        self.scroll_down_rect = None

        self.log_dir = Path(__file__).resolve().parent.parent.parent / "memory"
        char_name = CONFIG['CHAR']['character_name']
        self.log_file = self.log_dir / f"terminal_log_{char_name}.json"
        self.max_log_messages = 100

        self._ensure_log_dir()
        self._load_messages()

        self.top_buttons = [
            {"label": "PWR-DN", "code": "PWR-DN", "rect": None, "active": False, "color": "warning", "position": "right"},
        ]

        self.bottom_buttons = []

        self.show_main_menu = False
        self.main_menu_buttons = []
        self.main_menu_rect = None
        self.cam_back_rect = None

        self._main_menu_fade = 0.0
        self._app_menu_fade = 0.0
        self._menu_fade_speed = 6.0  # per second

        self._toast_text = None
        self._toast_time = 0
        self._toast_duration = 2.0

        self._silence_progress = 0
        self._silence_max = 0

        self._init_buttons()

        self.thinking = False
        self.thinking_time = 0
        self.action_flash = 0
        self.memory_pulse = 0
        self.scan_line = 0
        self.status_blink = 0

        self.tars_status = "BOOTING"

        self.show_power_menu = False
        self.power_menu_buttons = []

        self.camera_active = False
        self.app_active = False
        self.show_app_menu = False
        self.app_menu_buttons = []
        self.app_list = []
        self.app_menu_rect = None
        self.back_button_rect = None

        self._wifi_mode = "disconnected"
        self._wifi_signal = 0
        self._wifi_initialized = False
        _icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps")
        self._wifi_icon_blue   = self._load_wifi_icon(os.path.join(_icon_dir, "wifi-blue.png"))
        self._wifi_icon_yellow = self._load_wifi_icon(os.path.join(_icon_dir, "wifi-yellow.png"))
        self._wifi_icon_gray   = self._load_wifi_icon(os.path.join(_icon_dir, "wifi-gray.png"))

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
        button_height_top = self.toolbar_height - 4
        button_height_bottom = self.bottom_toolbar_height - 4
        button_spacing = 8
        start_y_top = 2
        start_y_bottom = self.toolbar_height + self.terminal_height + 2

        left_x = 2
        left_index = 0

        for button in self.top_buttons:
            if button.get("position") == "right":
                x = self.width - button_width - 2
            else:
                x = left_x + left_index * (button_width + button_spacing)
                left_index += 1
            button["rect"] = pygame.Rect(x, start_y_top, button_width, button_height_top)

        left_x = 4
        left_index = 0

        for button in self.bottom_buttons:
            if button.get("position") == "right":
                x = self.width - button_width - 2
            else:
                x = left_x + left_index * (button_width + button_spacing)
                left_index += 1

            button["rect"] = pygame.Rect(x, start_y_bottom, button_width, button_height_bottom)

        self._init_scroll_buttons()

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

    def update_last_message(self, value: str):
        """Update the text of the most recent message (for streaming)."""
        if self.messages:
            key, _, msg_type, timestamp = self.messages[-1]
            self.messages[-1] = (key, value, msg_type, timestamp)
            self.cache_dirty = True

    def update_message_speaker(self, old_speaker, text, new_speaker):
        """Update the speaker name of an existing message (for speaker ID resolution).
        Searches backwards for a matching message to avoid adding duplicates."""
        for i in range(len(self.messages) - 1, -1, -1):
            key, msg_text, msg_type, timestamp = self.messages[i]
            if msg_text == text and (key == old_speaker or key == new_speaker):
                self.messages[i] = (new_speaker, msg_text, new_speaker, timestamp)
                self.cache_dirty = True
                return True
        return False

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

    def _init_scroll_buttons(self):
        btn_width = 100
        btn_height = self.toolbar_height - 4
        spacing = 8
        # Place side by side on the left side
        up_x = 2
        down_x = up_x + btn_width + spacing
        y = 2
        self.scroll_up_rect = pygame.Rect(up_x, y, btn_width, btn_height)
        self.scroll_down_rect = pygame.Rect(down_x, y, btn_width, btn_height)
        self.scroll_held = None
        self.scroll_hold_start = 0
        self.scroll_hold_last = 0

    def handle_scroll_hold(self):
        pass

    def handle_mouse_down(self, pos):
        pass

    def handle_mouse_up(self):
        pass

    def _draw_scroll_buttons(self, surface):
        if not self.scroll_up_rect or not self.scroll_down_rect:
            self._init_scroll_buttons()

        for rect, direction in [(self.scroll_up_rect, "up"), (self.scroll_down_rect, "down")]:
            is_held = self.scroll_held == direction
            bg = (*self.accent_color, 200) if is_held else (*self.bg_panel, 180)
            pygame.draw.rect(surface, bg, rect)
            pygame.draw.rect(surface, (*self.border_color, 150), rect, 2)

            cx, cy = rect.centerx, rect.centery
            arrow_size = 8
            if direction == "up":
                points = [(cx, cy - arrow_size), (cx - arrow_size, cy + arrow_size), (cx + arrow_size, cy + arrow_size)]
            else:
                points = [(cx, cy + arrow_size), (cx - arrow_size, cy - arrow_size), (cx + arrow_size, cy - arrow_size)]
            pygame.draw.polygon(surface, self.primary_color, points)

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

    def set_wifi_status(self, mode: str, signal: int):
        """Called by UIManager's background WiFi thread to update display state."""
        self._wifi_mode = mode
        self._wifi_signal = signal
        self._wifi_initialized = True

    def set_app_active(self, active: bool):
        self.app_active = active

    def set_available_apps(self, app_list):
        self.app_list = app_list

    def _init_app_menu(self):
        button_width = 280
        button_height = 84
        button_spacing = 20
        num_apps = len(self.app_list)
        if num_apps == 0:
            return

        total_height = num_apps * button_height + (num_apps - 1) * button_spacing
        modal_width = button_width + 60
        modal_height = total_height + 100
        modal_x = self.width // 2 - modal_width // 2
        modal_y = self.height // 2 - modal_height // 2
        self.app_menu_rect = pygame.Rect(modal_x, modal_y, modal_width, modal_height)

        self.app_menu_buttons = []
        start_y = modal_y + 70
        for i, app_info in enumerate(self.app_list):
            rect = pygame.Rect(
                self.width // 2 - button_width // 2,
                start_y + i * (button_height + button_spacing),
                button_width,
                button_height
            )
            self.app_menu_buttons.append({
                "label": app_info["label"].upper(),
                "name": app_info["name"],
                "rect": rect
            })

    def _draw_app_menu(self, surface):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        if not self.app_menu_rect:
            return

        pygame.draw.rect(surface, (*self.bg_panel, 250), self.app_menu_rect)
        pygame.draw.rect(surface, self.border_color, self.app_menu_rect, 3)

        inner_rect = self.app_menu_rect.inflate(-6, -6)
        pygame.draw.rect(surface, (*self.accent_color, 100), inner_rect, 1)

        title = "SELECT APP"
        title_surface = self.title_font.render(title, True, self.primary_color)
        title_rect = title_surface.get_rect(
            center=(self.app_menu_rect.centerx, self.app_menu_rect.top + 35)
        )
        surface.blit(title_surface, title_rect)

        line_y = self.app_menu_rect.top + 60
        pygame.draw.line(surface, self.border_color,
                        (self.app_menu_rect.left + 20, line_y),
                        (self.app_menu_rect.right - 20, line_y), 2)

        for button in self.app_menu_buttons:
            rect = button["rect"]
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

            text_surface = self.toolbar_font.render(button["label"], True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

    def draw_back_button(self, surface):
        bar_y = self.height - self.bottom_toolbar_height
        button_width = 90
        button_height = self.bottom_toolbar_height - 4
        x = 2
        y = bar_y + 2
        self.back_button_rect = pygame.Rect(x, y, button_width, button_height)

        bottom_bar_bg = pygame.Surface((self.width, self.bottom_toolbar_height), pygame.SRCALPHA)
        bottom_bar_bg.fill((*self.bg_terminal, self.bg_alpha + 20))
        surface.blit(bottom_bar_bg, (0, bar_y))

        pygame.draw.line(surface, (*self.border_color, 200),
                        (0, bar_y), (self.width, bar_y), 2)

        self._draw_tech_button(surface, self.back_button_rect, "<-", "BCK-01", active=True)

        status_colors = {
            "BOOTING": (255, 100, 0),
            "STANDBY": self.dim_text_color,
            "LISTENING": (0, 200, 255),
            "THINKING": (255, 180, 0),
            "TALKING": (0, 255, 100),
        }
        status_color = status_colors.get(self.tars_status, self.dim_text_color)
        status_text = self.tars_status
        status_surface = self._status_font.render(status_text, True, status_color)
        status_x = x + button_width + 8
        pad_x, pad_y = 12, 12
        pill_w = status_surface.get_width() + pad_x * 2
        pill_h = status_surface.get_height() + pad_y * 2
        pill_y = bar_y + (self.bottom_toolbar_height - pill_h) // 2
        pill_rect = pygame.Rect(status_x, pill_y, pill_w, pill_h)
        pill_bg = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pill_bg.fill((0, 0, 0, 220))

        if (self.tars_status == "LISTENING" and self._silence_max > 0
                and self._silence_progress > 0):
            pct = min(1.0, self._silence_progress / self._silence_max)
            fill_w = int((pill_w - 4) * pct)
            if fill_w > 0:
                pygame.draw.rect(pill_bg, (*status_color, 160),
                                 (2, 2, fill_w, pill_h - 4),
                                 border_radius=4)

        pygame.draw.rect(pill_bg, (*status_color, 200), (0, 0, pill_w, pill_h), 2, border_radius=6)
        surface.blit(pill_bg, pill_rect)
        text_rect = status_surface.get_rect(center=pill_rect.center)
        surface.blit(status_surface, text_rect)

        right_x = self.width - 2

        if self.cpu_temp_module and self.show_cpu_temp:
            cpu_width = 80
            cpu_height = button_height
            right_x -= cpu_width
            self._draw_cpu_temp_indicator(surface, right_x, y, cpu_width, cpu_height)
            right_x -= 4

        if self.battery_module:
            battery_width = 60
            battery_height = button_height
            right_x -= battery_width
            self._draw_battery_indicator(surface, right_x, y, battery_width, battery_height)
            right_x -= 4

        if self._wifi_icon_gray is not None:
            wifi_size = button_height
            right_x -= wifi_size
            self._draw_wifi_icon(surface, right_x, y, wifi_size)

    def handle_app_click(self, pos: Tuple[int, int]) -> bool:
        now = pygame.time.get_ticks()
        if now - self.last_click_time < self.click_cooldown:
            return False
        self.last_click_time = now

        if self.back_button_rect and self.back_button_rect.collidepoint(pos):
            if self.on_app_back:
                self.on_app_back()
            return True
        return False

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

    def _init_main_menu(self):
        button_width = 280
        button_height = 84
        button_spacing = 20
        menu_items = [
            {"label": "APP", "code": "APP-01"},
            {"label": "CAM", "code": "CAM-01"},
            {"label": "BG", "code": "BG-SW"},
            {"label": "WAVE", "code": "SPK-CY"},
            {"label": "CLEAR", "code": "CLR-01"},
        ]
        num = len(menu_items)
        total_height = num * button_height + (num - 1) * button_spacing
        modal_width = button_width + 60
        modal_height = total_height + 100
        modal_x = self.width // 2 - modal_width // 2
        modal_y = self.height // 2 - modal_height // 2
        self.main_menu_rect = pygame.Rect(modal_x, modal_y, modal_width, modal_height)

        self.main_menu_buttons = []
        start_y = modal_y + 70
        for i, item in enumerate(menu_items):
            rect = pygame.Rect(
                self.width // 2 - button_width // 2,
                start_y + i * (button_height + button_spacing),
                button_width,
                button_height
            )
            self.main_menu_buttons.append({
                "label": item["label"],
                "code": item["code"],
                "rect": rect
            })

    def _draw_main_menu(self, surface):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        if not self.main_menu_rect:
            return

        pygame.draw.rect(surface, (*self.bg_panel, 250), self.main_menu_rect)
        pygame.draw.rect(surface, self.border_color, self.main_menu_rect, 3)

        inner_rect = self.main_menu_rect.inflate(-6, -6)
        pygame.draw.rect(surface, (*self.accent_color, 100), inner_rect, 1)

        title = "MENU"
        title_surface = self.title_font.render(title, True, self.primary_color)
        title_rect = title_surface.get_rect(
            center=(self.main_menu_rect.centerx, self.main_menu_rect.top + 35)
        )
        surface.blit(title_surface, title_rect)

        line_y = self.main_menu_rect.top + 60
        pygame.draw.line(surface, self.border_color,
                        (self.main_menu_rect.left + 20, line_y),
                        (self.main_menu_rect.right - 20, line_y), 2)

        for button in self.main_menu_buttons:
            rect = button["rect"]
            label = button["label"]

            bg_color = (20, 60, 80, 220)
            border_color = self.primary_color
            text_color = self.primary_color

            pygame.draw.rect(surface, bg_color, rect)
            pygame.draw.rect(surface, border_color, rect, 2)

            inner = rect.inflate(-4, -4)
            pygame.draw.rect(surface, (*self.accent_color, 150), inner, 1)

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

    def handle_click(self, pos: Tuple[int, int]):
        if self.scroll_up_rect and self.scroll_up_rect.collidepoint(pos):
            self.scroll_up(2)
            return
        if self.scroll_down_rect and self.scroll_down_rect.collidepoint(pos):
            self.scroll_down(2)
            return

        now = pygame.time.get_ticks()
        if now - self.last_click_time < self.click_cooldown:
            return
        self.last_click_time = now

        # Handle main menu clicks
        if self.show_main_menu:
            for button in self.main_menu_buttons:
                if button["rect"].collidepoint(pos):
                    label = button["label"]
                    if label == "CLEAR":
                        self.clear_messages()
                    elif label == "BG":
                        if self.on_background_change:
                            result = self.on_background_change()
                            if result:
                                self._toast_text = result
                                self._toast_time = time.time()
                    elif label == "WAVE":
                        if self.on_spectrum_change:
                            result = self.on_spectrum_change()
                            if result:
                                self._toast_text = result
                                self._toast_time = time.time()
                    elif label == "CAM":
                        if self.on_camera_toggle:
                            self.on_camera_toggle()
                    elif label == "APP":
                        if self.app_list:
                            self.show_main_menu = False
                            self.show_app_menu = True
                            self._init_app_menu()
                            return
                    # BG and WAVE stay open to cycle; others close the menu
                    if label not in ("BG", "WAVE"):
                        self.show_main_menu = False
                    return

            if self.main_menu_rect and not self.main_menu_rect.collidepoint(pos):
                self.show_main_menu = False
            return

        if self.show_app_menu:
            for button in self.app_menu_buttons:
                if button["rect"].collidepoint(pos):
                    if self.on_app_select:
                        self.on_app_select(button["name"])
                    self.show_app_menu = False
                    return

            if self.app_menu_rect and not self.app_menu_rect.collidepoint(pos):
                self.show_app_menu = False
            return

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

        # Check PWR-DN button in top toolbar
        for button in self.top_buttons:
            if button["rect"] and button["rect"].collidepoint(pos):
                if button["label"] == "PWR-DN":
                    self.show_power_menu = True
                    self._init_power_menu()
                return

        # Back button exits camera view
        if self.cam_back_rect and self.cam_back_rect.collidepoint(pos):
            if self.on_camera_toggle:
                self.on_camera_toggle()
            return

        # Tap on the terminal area opens the main menu (150px dead zone top and bottom)
        menu_zone_top = self.toolbar_height + 150
        menu_zone_bottom = self.toolbar_height + self.terminal_height - 150
        menu_zone_height = menu_zone_bottom - menu_zone_top
        if menu_zone_height <= 0:
            return
        terminal_rect = pygame.Rect(0, menu_zone_top, self.width, menu_zone_height)
        if not self.camera_active and terminal_rect.collidepoint(pos):
            self.show_main_menu = True
            self._init_main_menu()
            return

    def think(self):
        self.thinking = True
        self.thinking_time = time.time()

    def stop_thinking(self):
        self.thinking = False

    def set_tars_status(self, status):
        self.tars_status = status

    def set_silence_progress(self, progress, max_value):
        self._silence_progress = progress
        self._silence_max = max_value

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

        # Animate menu fades
        fade_step = self._menu_fade_speed / 30.0  # assume ~30fps
        if self.show_main_menu:
            self._main_menu_fade = min(1.0, self._main_menu_fade + fade_step)
        else:
            self._main_menu_fade = max(0.0, self._main_menu_fade - fade_step)
        if self.show_app_menu:
            self._app_menu_fade = min(1.0, self._app_menu_fade + fade_step)
        else:
            self._app_menu_fade = max(0.0, self._app_menu_fade - fade_step)

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

        if label == "<-":
            # Draw a proper back arrow instead of text
            cx, cy = rect.center
            arrow_w = min(rect.width, rect.height) * 0.4
            arrow_h = arrow_w * 0.6
            # Arrow pointing left: tip on the left, shaft on the right
            tip_x = cx - arrow_w * 0.5
            shaft_x = cx + arrow_w * 0.5
            shaft_half = arrow_h * 0.2
            head_half = arrow_h * 0.5
            head_end = cx - arrow_w * 0.05
            points = [
                (tip_x, cy),                    # tip
                (head_end, cy - head_half),     # top of arrowhead
                (head_end, cy - shaft_half),    # top inner notch
                (shaft_x, cy - shaft_half),     # top right of shaft
                (shaft_x, cy + shaft_half),     # bottom right of shaft
                (head_end, cy + shaft_half),    # bottom inner notch
                (head_end, cy + head_half),     # bottom of arrowhead
            ]
            pygame.draw.polygon(surface, text_color, points)
        else:
            text_surface = self.toolbar_font.render(label, True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

    def _load_wifi_icon(self, path: str):
        try:
            img = pygame.image.load(path).convert_alpha()
            return img
        except Exception:
            return None

    def _current_wifi_icon(self):
        if self._wifi_mode == "hotspot":
            return self._wifi_icon_yellow
        if self._wifi_mode == "client":
            return self._wifi_icon_blue
        return self._wifi_icon_gray

    def _draw_wifi_icon(self, surface, x, y, size):
        icon = self._current_wifi_icon()
        if icon is None:
            return
        scaled = pygame.transform.smoothscale(icon, (size, size))
        if not self._wifi_initialized:
            import math
            alpha = int(80 + 175 * (0.5 + 0.5 * math.sin(self.status_blink * 2)))
            scaled = scaled.copy()
            scaled.set_alpha(alpha)
        surface.blit(scaled, (x, y))

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
                
                bolt_h = max(6, (body_height - 4) // 2 - 2)
                bolt_w = max(4, bolt_h * 2 // 3)
                bolt_cx = center_x
                bolt_cy = body_y + body_height - bolt_h + 1
                bolt_points = [
                    (bolt_cx + bolt_w // 4, bolt_cy - bolt_h // 2),
                    (bolt_cx - bolt_w // 2, bolt_cy),
                    (bolt_cx - bolt_w // 8, bolt_cy),
                    (bolt_cx - bolt_w // 4, bolt_cy + bolt_h // 2),
                    (bolt_cx + bolt_w // 2, bolt_cy),
                    (bolt_cx + bolt_w // 8, bolt_cy),
                ]
                for ox in range(-1, 2):
                    for oy in range(-1, 2):
                        if ox != 0 or oy != 0:
                            offset_points = [(px + ox, py + oy) for px, py in bolt_points]
                            pygame.draw.polygon(surface, (255, 255, 255), offset_points)
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

            # Pre-scan visible lines to build message groups for pill backgrounds
            pill_pad_x = 14
            pill_pad_y = 6
            pill_gap = 16
            char_name = CONFIG['CHAR']['character_name']

            # Build groups with gap-aware y positions
            non_sys = set()
            for s in ("SYSTEM", "SYS", "INFO", "WARNING", "ERROR", "DEBUG", "DEBUG VOICE"):
                non_sys.add(s)

            groups = []
            current_group = None
            prev_was_chat = False
            temp_y = y_offset
            line_y_map = []  # maps each visible line index to its actual y position

            for i, (key, value, msg_type, line_text, line_idx) in enumerate(visible_lines):
                if temp_y + self.line_height > self.toolbar_height + self.terminal_height - self.padding:
                    break

                # Add gap between different message groups
                if line_idx == 0 and current_group is not None:
                    temp_y += pill_gap

                if line_idx == 0:
                    if current_group is not None:
                        groups.append(current_group)
                    current_group = {"key": key, "start_y": temp_y, "line_count": 1}
                elif current_group is not None and current_group["key"] == key:
                    current_group["line_count"] += 1
                else:
                    if current_group is not None:
                        groups.append(current_group)
                    current_group = {"key": key, "start_y": temp_y, "line_count": 1}

                line_y_map.append(temp_y)
                temp_y += self.line_height

            if current_group is not None:
                groups.append(current_group)

            # Draw pill backgrounds
            for group in groups:
                gy = group["start_y"] - pill_pad_y
                gh = group["line_count"] * self.line_height + pill_pad_y * 2
                gx = self.padding - pill_pad_x + 13
                gw = self.width - gx - (self.padding - pill_pad_x - 25) - 40

                pill_center_y = group["start_y"] + (group["line_count"] * self.line_height) / 2
                progress = (pill_center_y - start_y) / terminal_draw_height
                progress = max(0.0, min(1.0, progress))
                fade_alpha = 1.0 if progress < 0.5 else max(0.0, 1.0 - ((progress - 0.5) / 0.5))

                gkey = group["key"].upper()
                if group["key"] == char_name:
                    pill_color = (20, 60, 90, int(90 * fade_alpha))
                    outline_color = (60, 130, 180, int(150 * fade_alpha))
                elif gkey in ("SYSTEM", "SYS", "INFO", "WARNING", "ERROR", "DEBUG", "DEBUG VOICE"):
                    pill_color = (70, 70, 80, int(70 * fade_alpha))
                    outline_color = (130, 130, 140, int(120 * fade_alpha))
                else:  # user (any name)
                    pill_color = (60, 45, 75, int(80 * fade_alpha))
                    outline_color = (120, 90, 150, int(150 * fade_alpha))

                pill_surface = pygame.Surface((gw, gh), pygame.SRCALPHA)
                pygame.draw.rect(pill_surface, pill_color, (0, 0, gw, gh), border_radius=8)
                pygame.draw.rect(pill_surface, outline_color, (0, 0, gw, gh), width=2, border_radius=8)
                self.overlay_surface.blit(pill_surface, (gx, gy))

            # Draw text
            line_count = 0
            for i, (key, value, msg_type, line_text, line_idx) in enumerate(visible_lines):
                if i >= len(line_y_map):
                    break
                y_offset = line_y_map[i]

                progress = (y_offset - start_y) / terminal_draw_height
                progress = max(0.0, min(1.0, progress))
                fade_alpha = 1.0 if progress < 0.5 else max(0.0, 1.0 - ((progress - 0.5) / 0.5))

                if line_idx == 0 and ':' in line_text:
                    parts = line_text.split(':', 1)
                    if len(parts) == 2:
                        user_part, msg_part = parts

                        if user_part == char_name:
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
                    if key == char_name:
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

        bottom_toolbar_y = self.toolbar_height + self.terminal_height
        bottom_toolbar_rect = pygame.Rect(0, bottom_toolbar_y, self.width, self.bottom_toolbar_height)
        bottom_toolbar_bg = pygame.Surface((self.width, self.bottom_toolbar_height), pygame.SRCALPHA)
        bottom_toolbar_bg.fill((*self.bg_terminal, self.bg_alpha))
        self.overlay_surface.blit(bottom_toolbar_bg, (0, bottom_toolbar_y))

        pygame.draw.line(self.overlay_surface, (*self.border_color, 200), 
                        (0, bottom_toolbar_y), (self.width, bottom_toolbar_y), 2)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 100), 
                        (0, bottom_toolbar_y + 1), (self.width, bottom_toolbar_y + 1), 1)

        # Draw back button when camera is active
        if self.camera_active:
            back_w = 90
            back_h = self.bottom_toolbar_height - 4
            back_x = 2
            back_y = bottom_toolbar_y + 2
            self.cam_back_rect = pygame.Rect(back_x, back_y, back_w, back_h)
            self._draw_tech_button(self.overlay_surface, self.cam_back_rect, "<-", "BCK-01", active=True)
        else:
            self.cam_back_rect = None

        # Draw status badge (STANDBY/LISTENING/THINKING/TALKING)
        status_colors = {
            "BOOTING": (255, 100, 0),
            "STANDBY": self.dim_text_color,
            "LISTENING": (0, 200, 255),
            "THINKING": (255, 180, 0),
            "TALKING": (0, 255, 100),
        }
        s_color = status_colors.get(self.tars_status, self.dim_text_color)
        s_surface = self._status_font.render(self.tars_status, True, s_color)
        s_x = (self.cam_back_rect.right + 8) if self.cam_back_rect else 2
        s_pad_x, s_pad_y = 12, 12
        s_pill_w = s_surface.get_width() + s_pad_x * 2
        s_pill_h = s_surface.get_height() + s_pad_y * 2
        s_pill_y = bottom_toolbar_y + (self.bottom_toolbar_height - s_pill_h) // 2
        s_pill_rect = pygame.Rect(s_x, s_pill_y, s_pill_w, s_pill_h)
        s_pill_bg = pygame.Surface((s_pill_w, s_pill_h), pygame.SRCALPHA)
        s_pill_bg.fill((0, 0, 0, 220))

        # Draw silence progress fill inside the pill when LISTENING
        if (self.tars_status == "LISTENING" and self._silence_max > 0
                and self._silence_progress > 0):
            pct = min(1.0, self._silence_progress / self._silence_max)
            fill_w = int((s_pill_w - 4) * pct)
            if fill_w > 0:
                fill_color = (*s_color, 160)
                pygame.draw.rect(s_pill_bg, fill_color,
                                 (2, 2, fill_w, s_pill_h - 4),
                                 border_radius=4)

        pygame.draw.rect(s_pill_bg, (*s_color, 200), (0, 0, s_pill_w, s_pill_h), 2, border_radius=6)
        self.overlay_surface.blit(s_pill_bg, s_pill_rect)
        s_text_rect = s_surface.get_rect(center=s_pill_rect.center)
        self.overlay_surface.blit(s_surface, s_text_rect)

        right_x = self.width - 2

        if self.cpu_temp_module and self.show_cpu_temp:
            cpu_width = 80
            cpu_height = self.bottom_toolbar_height - 4
            right_x -= cpu_width
            self._draw_cpu_temp_indicator(self.overlay_surface, right_x, bottom_toolbar_y + 2,
                                          cpu_width, cpu_height)
            right_x -= 4

        if self.battery_module:
            battery_width = 60
            battery_height = self.bottom_toolbar_height - 4
            right_x -= battery_width
            self._draw_battery_indicator(self.overlay_surface, right_x, bottom_toolbar_y + 2,
                                         battery_width, battery_height)
            right_x -= 4

        if self._wifi_icon_gray is not None:
            wifi_size = self.bottom_toolbar_height - 4
            right_x -= wifi_size
            self._draw_wifi_icon(self.overlay_surface, right_x, bottom_toolbar_y + 2, wifi_size)

        if not self.camera_active:
            self._draw_scroll_buttons(self.overlay_surface)

        surface.blit(self.overlay_surface, (0, 0))

        if self.show_power_menu:
            self._draw_power_menu(surface)

        if self.show_main_menu:
            self._draw_main_menu(surface)

        if self._toast_text:
            elapsed = time.time() - self._toast_time
            if elapsed < self._toast_duration:
                if elapsed > self._toast_duration - 0.5:
                    alpha = int(255 * (self._toast_duration - elapsed) / 0.5)
                else:
                    alpha = 255
                toast_surface = self._status_font.render(self._toast_text, True, self.primary_color)
                toast_surface.set_alpha(alpha)
                if self.main_menu_rect:
                    toast_rect = toast_surface.get_rect(centerx=self.main_menu_rect.centerx,
                                                        bottom=self.main_menu_rect.top - 10)
                else:
                    toast_rect = toast_surface.get_rect(centerx=self.width // 2, top=12)
                surface.blit(toast_surface, toast_rect)
            else:
                self._toast_text = None

        if self.show_app_menu:
            self._draw_app_menu(surface)