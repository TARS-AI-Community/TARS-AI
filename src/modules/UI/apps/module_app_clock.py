"""
Analog Clock App demo
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

See below on how to use this framework to create more apps
"""

import pygame
import math
from datetime import datetime


class ClockApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        self.bg_color = (5, 15, 20)
        self.primary_color = (0, 255, 255)
        self.secondary_color = (0, 180, 200)
        self.accent_color = (0, 120, 150)
        self.dim_color = (0, 60, 80)
        self.hour_color = (0, 255, 255)
        self.minute_color = (0, 200, 220)
        self.second_color = (255, 100, 0)

        try:
            self.font_large = pygame.font.Font("UI/mono.ttf", 48)
            self.font_medium = pygame.font.Font("UI/mono.ttf", 24)
            self.font_small = pygame.font.Font("UI/mono.ttf", 16)
        except:
            self.font_large = pygame.font.SysFont("monospace", 48)
            self.font_medium = pygame.font.SysFont("monospace", 24)
            self.font_small = pygame.font.SysFont("monospace", 16)

        self.clock_radius = min(width, height) // 4
        self.clock_center_x = width // 2
        self.clock_center_y = height // 2 - 20

    def reset(self):
        pass

    def update(self):
        pass

    def render(self):
        self.screen.fill(self.bg_color)
        now = datetime.now()

        self._draw_analog_clock(now)
        self._draw_digital_time(now)
        self._draw_date(now)

    def _draw_analog_clock(self, now):
        cx = self.clock_center_x
        cy = self.clock_center_y
        r = self.clock_radius

        pygame.draw.circle(self.screen, self.dim_color, (cx, cy), r, 2)
        pygame.draw.circle(self.screen, self.dim_color, (cx, cy), r - 4, 1)

        for i in range(60):
            angle = math.radians(i * 6 - 90)
            if i % 5 == 0:
                inner = r - 18
                outer = r - 6
                color = self.primary_color
                width = 2
            else:
                inner = r - 12
                outer = r - 6
                color = self.dim_color
                width = 1

            x1 = cx + int(inner * math.cos(angle))
            y1 = cy + int(inner * math.sin(angle))
            x2 = cx + int(outer * math.cos(angle))
            y2 = cy + int(outer * math.sin(angle))
            pygame.draw.line(self.screen, color, (x1, y1), (x2, y2), width)

        for i in range(12):
            angle = math.radians(i * 30 - 90)
            num_r = r - 30
            x = cx + int(num_r * math.cos(angle))
            y = cy + int(num_r * math.sin(angle))
            num = str(12 if i == 0 else i)
            num_surf = self.font_small.render(num, True, self.secondary_color)
            num_rect = num_surf.get_rect(center=(x, y))
            self.screen.blit(num_surf, num_rect)

        hour = now.hour % 12
        minute = now.minute
        second = now.second
        microsecond = now.microsecond

        smooth_second = second + microsecond / 1_000_000.0
        smooth_minute = minute + smooth_second / 60.0
        smooth_hour = hour + smooth_minute / 60.0

        hour_angle = math.radians(smooth_hour * 30 - 90)
        hour_len = r * 0.5
        hx = cx + int(hour_len * math.cos(hour_angle))
        hy = cy + int(hour_len * math.sin(hour_angle))
        pygame.draw.line(self.screen, self.hour_color, (cx, cy), (hx, hy), 4)

        min_angle = math.radians(smooth_minute * 6 - 90)
        min_len = r * 0.7
        mx = cx + int(min_len * math.cos(min_angle))
        my = cy + int(min_len * math.sin(min_angle))
        pygame.draw.line(self.screen, self.minute_color, (cx, cy), (mx, my), 3)

        sec_angle = math.radians(smooth_second * 6 - 90)
        sec_len = r * 0.8
        sx = cx + int(sec_len * math.cos(sec_angle))
        sy = cy + int(sec_len * math.sin(sec_angle))
        pygame.draw.line(self.screen, self.second_color, (cx, cy), (sx, sy), 1)

        tail_len = r * 0.15
        tx = cx - int(tail_len * math.cos(sec_angle))
        ty = cy - int(tail_len * math.sin(sec_angle))
        pygame.draw.line(self.screen, self.second_color, (cx, cy), (tx, ty), 1)

        pygame.draw.circle(self.screen, self.primary_color, (cx, cy), 5)
        pygame.draw.circle(self.screen, self.second_color, (cx, cy), 3)

    def _draw_digital_time(self, now):
        time_str = now.strftime("%H:%M:%S")
        time_surf = self.font_large.render(time_str, True, self.primary_color)
        time_rect = time_surf.get_rect(centerx=self.clock_center_x,
                                        top=self.clock_center_y + self.clock_radius + 20)
        self.screen.blit(time_surf, time_rect)

    def _draw_date(self, now):
        date_str = now.strftime("%A, %B %d, %Y")
        date_surf = self.font_medium.render(date_str, True, self.secondary_color)
        date_rect = date_surf.get_rect(centerx=self.clock_center_x,
                                        top=self.clock_center_y + self.clock_radius + 75)
        self.screen.blit(date_surf, date_rect)

    def cleanup(self):
        pass


# =============================================================================
# HOW TO CREATE A NEW TARS APP
# =============================================================================
#
# 1. Create a new file in this folder (src/modules/UI/apps/), e.g.:
#       module_app_weather.py
#
# 2. Write a class with these 5 methods:
#
#       import pygame
#
#       class WeatherApp:
#           def __init__(self, screen, width, height):
#               self.screen = screen       # pygame Surface to draw on
#               self.width = width         # display width in pixels
#               self.height = height       # display height in pixels
#
#           def reset(self):
#               pass  # called when the app is launched/relaunched
#
#           def update(self):
#               pass  # called every frame BEFORE render (update logic here)
#
#           def render(self):
#               self.screen.fill((5, 15, 20))  # clear and draw your UI
#
#           def cleanup(self):
#               pass  # called when the app is closed (free resources)
#
# 3. Register it in module_ui_apps.py:
#
#       from modules.UI.apps.module_app_weather import WeatherApp
#
#       AVAILABLE_APPS = {
#           "clock":   {"class": ClockApp,   "type": "pygame", "label": "Clock"},
#           "weather": {"class": WeatherApp, "type": "pygame", "label": "Weather"},
#       }
#
# NOTES:
#   - "type" should be "pygame" for standard 2D apps, "opengl" only for raw GL
#   - "label" is the display name shown in the app launcher UI
#   - Draw directly to self.screen using pygame (pygame.draw, surface.blit, etc.)
#   - Load fonts with: pygame.font.Font("UI/mono.ttf", 24)
#     Always add a fallback: pygame.font.SysFont("monospace", 24)
#   - The AppManager calls update() then render() every frame automatically
#   - Apps are display-only, they do not receive input events
# =============================================================================
