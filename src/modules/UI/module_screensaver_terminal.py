"""
Module: Terminal Screensaver
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
import random
from UI.module_screensaver_overlay import TimeOverlay

class TerminalAnimation:
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None
        
        self.font = pygame.font.Font(None, 16)
        self.font_bold = pygame.font.Font(None, 16)
        self.font_bold.set_bold(True)
        self.lines = []
        self.line_height = 13
        self.max_lines = (height // self.line_height) - 2
        
        self.messages = [
            "def calculate_trajectory():",
            "    wormhole_coords = [x:48.2, y:23.7, z:91.4]",
            "    if time_dilation > 1.0:",
            "        adjust_for_relativity()",
            "    return optimal_path",
            "",
            "class EnduranceSystem:",
            "    def __init__(self, fuel_capacity=1000, crew_count=4):",
            "        self.fuel = 87.3",
            "        self.oxygen = 94.1",
            "        self.status = 'NOMINAL'",
            "        self.gravitational_stress_level = calculate_stress(self.position)",
            "",
            "# GARGANTUA PROXIMITY WARNING - CRITICAL SYSTEM ALERT",
            "singularity_distance = 4127.8  # km",
            "event_horizon_threshold = 4000.0",
            "gravitational_pull_force = calculate_schwarzschild_radius(black_hole_mass)",
            "",
            "if singularity_distance < event_horizon_threshold:",
            "    print('CRITICAL: TOO CLOSE')",
            "    engage_emergency_thrust()",
            "    transmit_distress_signal(frequency=121.5, power='MAX')",
            "",
            "# Time dilation calculation - Einstein field equations",
            "years_per_hour = 7.0",
            "elapsed_time = calculate_elapsed()",
            "relativistic_factor = sqrt(1 - (velocity_squared / speed_of_light_squared))",
            "",
            "# Cooper Station alignment",
            "alignment_percent = 97.4",
            "docking_rotation = 68  # RPM",
            "centrifugal_force = mass * angular_velocity_squared * radius",
            "",
            "quantum_data = receive_transmission()",
            "if quantum_data.valid:",
            "    decode_message(quantum_data)",
            "    verify_morse_sequence(data_stream, pattern='S.T.A.Y')",
            "",
            "# TARS parameters",
            "humor_setting = 0.75",
            "honesty_param = 0.90",
            "discretion_mode = True",
            "adaptive_learning_rate = 0.001",
            "",
            "def analyze_gravity_anomaly():",
            "    data = collect_sensor_data()",
            "    pattern = find_pattern(data)",
            "    if pattern == 'MORSE':",
            "        message = decode_morse(pattern)",
            "        return message",
            "    else:",
            "        log_anomaly(timestamp=current_time(), severity='WARNING')",
            "",
            "# Miller's planet approach - WARNING: massive tidal forces detected",
            "tidal_wave_height = 1200  # meters",
            "surface_time_loss = 23  # years",
            "atmospheric_pressure = 1.3  # atm",
            "water_coverage_percent = 100",
            "",
            "for module in habitat_systems:",
            "    module.status_check()",
            "    if not module.is_operational():",
            "        initiate_repair_sequence()",
            "        log_maintenance(module.id, timestamp=now(), priority='HIGH')",
            "",
            "def dock_with_endurance(rotation_speed, alignment_tolerance=0.5):",
            "    while abs(rotation_speed - target_rotation) > alignment_tolerance:",
            "        adjust_thrust_vectors()",
            "        recalculate_approach_angle()",
            "    return docking_status",
            "",
            "# Tesseract dimension analysis",
            "spacetime_coordinates = [t, x, y, z, w]",
            "if dimensions > 3:",
            "    enable_quantum_visualization()",
            "",
            "ranger_fuel_remaining = 12.7  # percent",
            "life_support_duration = 847  # hours",
            "communication_delay = 91  # minutes",
            "",
            "# Plan A: Solve gravity equation",
            "# Plan B: Population bomb with frozen embryos",
            "if plan_a_viable == False:",
            "    activate_plan_b(embryo_count=5000, destination='edmunds_planet')",
        ]
        
        self.current_message_index = 0
        self.current_char_index = 0
        self.typing_speed = 0
        self.char_counter = 0
        self.pause_counter = 0
        self.pause_duration = 0
        self.blink_counter = 0
        self.blinking_keywords = ['CRITICAL', 'WARNING', 'event_horizon', 'singularity_distance', 'plan_a_viable', 'ALERT']
        
        random.shuffle(self.messages)
        
        for i in range(self.max_lines):
            self.lines.append({
                'text': '',
                'full_text': '',
                'completed': True,
                'alpha': 60
            })

    def reset(self):
        random.shuffle(self.messages)
        self.current_message_index = 0
        self.current_char_index = 0
        self.char_counter = 0
        self.pause_counter = 0
        self.blink_counter = 0
        for line in self.lines:
            line['text'] = ''
            line['full_text'] = ''
            line['completed'] = True
            line['alpha'] = 60

    def update(self):
        if self.pause_counter > 0:
            self.pause_counter -= 1
            return
        
        self.char_counter += 1
        if self.char_counter < self.typing_speed:
            return
        
        self.char_counter = 0
        self.blink_counter += 1
        
        if self.current_char_index == 0:
            middle_line = len(self.lines) // 2
            
            for i in range(len(self.lines) - 1):
                self.lines[i] = self.lines[i + 1].copy()
                if self.lines[i]['completed']:
                    if i >= middle_line - 5 and i <= middle_line + 5:
                        self.lines[i]['alpha'] = 200
                    elif i < middle_line - 5:
                        distance_from_middle = middle_line - i
                        fade_amount = int(150 * (distance_from_middle / middle_line))
                        self.lines[i]['alpha'] = max(50, 200 - fade_amount)
                    else:
                        distance_from_middle = i - middle_line
                        fade_amount = int(150 * (distance_from_middle / middle_line))
                        self.lines[i]['alpha'] = max(50, 200 - fade_amount)
            
            last_line_index = len(self.lines) - 1
            if last_line_index >= middle_line - 5 and last_line_index <= middle_line + 5:
                alpha = 200
            elif last_line_index < middle_line - 5:
                distance_from_middle = middle_line - last_line_index
                fade_amount = int(150 * (distance_from_middle / middle_line))
                alpha = max(50, 200 - fade_amount)
            else:
                distance_from_middle = last_line_index - middle_line
                fade_amount = int(150 * (distance_from_middle / middle_line))
                alpha = max(50, 200 - fade_amount)
            
            self.lines[-1] = {
                'text': '',
                'full_text': self.messages[self.current_message_index],
                'completed': False,
                'alpha': alpha
            }
        
        current_line = self.lines[-1]
        if not current_line['completed']:
            chars_to_type = min(3, len(current_line['full_text']) - self.current_char_index)
            for _ in range(chars_to_type):
                if self.current_char_index < len(current_line['full_text']):
                    current_line['text'] += current_line['full_text'][self.current_char_index]
                    self.current_char_index += 1
            
            if self.current_char_index >= len(current_line['full_text']):
                current_line['completed'] = True
                self.current_char_index = 0
                self.current_message_index = (self.current_message_index + 1) % len(self.messages)
                
                if random.random() < 0.15:
                    self.pause_duration = random.randint(10, 25)
                else:
                    self.pause_duration = random.randint(0, 1)
                self.pause_counter = self.pause_duration

    def _parse_syntax(self, text, base_alpha):
        keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 'return', 'import', 'from', 'True', 'False', 'None', 'in', 'not', 'and', 'or']
        segments = []
        i = 0
        
        while i < len(text):
            if text[i] == '#':
                color = (100, 150, 100)
                segments.append((text[i:], color, base_alpha, False))
                break
            elif text[i] in ('"', "'"):
                quote = text[i]
                end = text.find(quote, i + 1)
                if end == -1:
                    end = len(text)
                else:
                    end += 1
                color = (255, 100, 100)
                segments.append((text[i:end], color, base_alpha, False))
                i = end
            elif text[i].isdigit() or (text[i] == '.' and i + 1 < len(text) and text[i + 1].isdigit()):
                end = i
                while end < len(text) and (text[end].isdigit() or text[end] == '.'):
                    end += 1
                color = (150, 200, 150)
                segments.append((text[i:end], color, base_alpha, False))
                i = end
            elif text[i].isalpha() or text[i] == '_':
                end = i
                while end < len(text) and (text[end].isalnum() or text[end] == '_'):
                    end += 1
                word = text[i:end]
                if word in keywords:
                    color = (100, 150, 255)
                    bold = True
                else:
                    color = (0, 200, 200)
                    bold = False
                segments.append((word, color, base_alpha, bold))
                i = end
            else:
                color = (0, 200, 200)
                segments.append((text[i], color, base_alpha, False))
                i += 1
        
        return segments

    def render(self):
        self.screen.fill((0, 0, 0))
        
        start_y = self.height - (self.max_lines * self.line_height)
        
        for i, line in enumerate(self.lines):
            y = start_y + (i * self.line_height)
            text = line['text']
            alpha = line['alpha']
            
            if not text:
                continue
            
            should_blink = False
            for keyword in self.blinking_keywords:
                if keyword in text:
                    should_blink = True
                    break
            
            if should_blink and (self.blink_counter // 10) % 2 == 0:
                alpha = min(255, alpha + 55)
            
            segments = self._parse_syntax(text, alpha)
            x_offset = 20
            
            for segment_text, color, seg_alpha, use_bold in segments:
                text_color = (
                    int(color[0] * (seg_alpha / 255)),
                    int(color[1] * (seg_alpha / 255)),
                    int(color[2] * (seg_alpha / 255))
                )
                
                font_to_use = self.font_bold if use_bold else self.font
                text_surface = font_to_use.render(segment_text, True, text_color)
                self.screen.blit(text_surface, (x_offset, y))
                x_offset += text_surface.get_width()
            
            if i == len(self.lines) - 1 and not line['completed']:
                cursor_x = x_offset + 2
                if (self.blink_counter // 15) % 2 == 0:
                    cursor_color = (0, 255, 255)
                    pygame.draw.rect(self.screen, cursor_color, (cursor_x, y, 8, self.line_height - 2))
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render(self.screen)