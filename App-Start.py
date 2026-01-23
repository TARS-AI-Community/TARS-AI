import os
os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import subprocess
import time
import pygame
import sys
import configparser
import random

class TerminalScroll:
    def __init__(self, width, height, font, font_bold):
        self.width = width
        self.height = height
        self.font = font
        self.font_bold = font_bold
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
        
        start_y = height - (self.max_lines * self.line_height)
        for i in range(self.max_lines):
            self.lines.append({
                'text': '',
                'full_text': '',
                'completed': True,
                'alpha': 60
            })
    
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
                    if i >= middle_line:
                        self.lines[i]['alpha'] = 200
                    else:
                        distance_from_middle = middle_line - i
                        fade_amount = int(150 * (distance_from_middle / middle_line))
                        self.lines[i]['alpha'] = max(50, 200 - fade_amount)
            
            self.lines[-1] = {
                'text': '',
                'full_text': self.messages[self.current_message_index],
                'completed': False,
                'alpha': 200
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
    
    def draw(self, surface, color):
        blink_state = (self.blink_counter // 20) % 2 == 0
        
        for i, line in enumerate(self.lines):
            y_pos = i * self.line_height + 10
            
            if line['text']:
                text = line['text']
                x_pos = 25
                base_alpha = line['alpha']
                
                keywords = ['def', 'class', 'if', 'for', 'return', 'import', 'while', 'True', 'False']
                numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
                
                j = 0
                while j < len(text):
                    char = text[j]
                    word = ''
                    word_alpha = base_alpha
                    brightness_boost = 0
                    use_bold = False
                    
                    if char == '#':
                        comment_end = text.find('\n', j)
                        if comment_end == -1:
                            comment_end = len(text)
                        word = text[j:comment_end]
                        brightness_boost = 30
                        j = comment_end
                    elif char == '"' or char == "'":
                        quote_char = char
                        quote_end = text.find(quote_char, j + 1)
                        if quote_end == -1:
                            quote_end = len(text)
                        else:
                            quote_end += 1
                        word = text[j:quote_end]
                        brightness_boost = 40
                        j = quote_end
                    elif char.isalnum() or char == '_':
                        word_start = j
                        while j < len(text) and (text[j].isalnum() or text[j] == '_' or text[j] == '.'):
                            j += 1
                        word = text[word_start:j]
                        
                        if word in keywords:
                            brightness_boost = 60
                        elif word in self.blinking_keywords:
                            use_bold = True
                            if blink_state:
                                brightness_boost = 80
                            else:
                                brightness_boost = 20
                        elif any(c in numbers for c in word) and word[0] in numbers:
                            brightness_boost = 50
                    else:
                        word = char
                        j += 1
                    
                    if word:
                        word_alpha = min(255, base_alpha + brightness_boost)
                        
                        blend_factor = brightness_boost / 100.0
                        word_color = (
                            int(color[0] + (255 - color[0]) * blend_factor),
                            int(color[1] + (255 - color[1]) * blend_factor),
                            int(color[2])
                        )
                        
                        chosen_font = self.font_bold if use_bold else self.font
                        word_surface = chosen_font.render(word, True, word_color)
                        word_surface.set_alpha(word_alpha)
                        surface.blit(word_surface, (x_pos, y_pos))
                        x_pos += word_surface.get_width()
                
                if not line['completed'] and i == len(self.lines) - 1:
                    cursor_alpha = 220 if (self.blink_counter // 15) % 2 == 0 else 100
                    cursor_surface = self.font.render('_', True, color)
                    cursor_surface.set_alpha(cursor_alpha)
                    surface.blit(cursor_surface, (x_pos, y_pos))

def check_required_file():
    config = configparser.ConfigParser()
    config_path = os.path.join('src', 'config.ini')
    
    try:
        config.read(config_path)
        if config.has_option('STT', 'wake_word_processor'):
            wake_word_processor = config.get('STT', 'wake_word_processor').strip().lower()
            
            if wake_word_processor == 'atomik':
                file_path = os.path.expanduser("~/.local/share/tars_ai/hey_tars_templates.pkl")
                return os.path.exists(file_path)
            else:
                return True
        else:
            return True
    except Exception as e:
        print(f"[CONFIG] Error reading config file: {e}")
        return True

def load_config():
    config = configparser.ConfigParser()
    config_path = os.path.join('src', 'config.ini')

    rotation = 0
    ui_enabled = False
    font_size = 12
    screen_width = 1024
    screen_height = 600

    try:
        config.read(config_path)
        if config.has_option('UI', 'rotation'):
            rotation = config.getint('UI', 'rotation')
            print(f"[CONFIG] Loaded rotation setting: {rotation}°")

        if config.has_option('UI', 'UI_enabled'):
            ui_enabled = config.getboolean('UI', 'UI_enabled')
            print(f"[CONFIG] UI_enabled: {ui_enabled}")

        if config.has_option('UI', 'font_size'):
            font_size = config.getint('UI', 'font_size')

        if config.has_option('UI', 'screen_width'):
            screen_width = config.getint('UI', 'screen_width')

        if config.has_option('UI', 'screen_height'):
            screen_height = config.getint('UI', 'screen_height')

        print(f"Launching Main App")

    except Exception as e:
        print(f"[CONFIG] Error reading config file: {e}")
        print("[CONFIG] Using default values")

    return rotation, ui_enabled, font_size, screen_width, screen_height

def stop_tars_ai():
    subprocess.Popen("killall xterm", shell=True)
    subprocess.Popen("pkill -f 'python app.py'", shell=True)

def run_tars_ai_fullscreen():
    command = "cd src && source .venv/bin/activate && python app.py show_ui=true"
    subprocess.run(command, shell=True, executable="/bin/bash")

def run_tars_ai_normal():
    command = (
        "cd src && source .venv/bin/activate && python app.py show_ui=false"
    )
    subprocess.run(command, shell=True, executable="/bin/bash")

def draw_corner_brackets(surface, rect, color, size=20, thickness=2):
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

    pygame.draw.line(surface, color, (x, y), (x + size, y), thickness)
    pygame.draw.line(surface, color, (x, y), (x, y + size), thickness)

    pygame.draw.line(surface, color, (x + w, y), (x + w - size, y), thickness)
    pygame.draw.line(surface, color, (x + w, y), (x + w, y + size), thickness)

    pygame.draw.line(surface, color, (x, y + h), (x + size, y + h), thickness)
    pygame.draw.line(surface, color, (x, y + h), (x, y + h - size), thickness)

    pygame.draw.line(surface, color, (x + w, y + h), (x + w - size, y + h), thickness)
    pygame.draw.line(surface, color, (x + w, y + h), (x + w, y + h - size), thickness)

def draw_grid_background(surface, width, height, grid_size=50, color=(20, 20, 20)):
    grid_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    grid_color = (100, 100, 100, 30)
    
    for x in range(0, width, grid_size):
        pygame.draw.line(grid_surface, grid_color, (x, 0), (x, height), 1)
    for y in range(0, height, grid_size):
        pygame.draw.line(grid_surface, grid_color, (0, y), (width, y), 1)
    
    surface.blit(grid_surface, (0, 0))

def draw_technical_frame(surface, rect, color, thickness=2):
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

    pygame.draw.rect(surface, color, rect, thickness)

    corner_size = 15

    pygame.draw.line(surface, color, (x - 5, y + corner_size), (x - 5, y - 5), thickness)
    pygame.draw.line(surface, color, (x - 5, y - 5), (x + corner_size, y - 5), thickness)

    pygame.draw.line(surface, color, (x + w + 5, y + corner_size), (x + w + 5, y - 5), thickness)
    pygame.draw.line(surface, color, (x + w + 5, y - 5), (x + w - corner_size, y - 5), thickness)

    pygame.draw.line(surface, color, (x - 5, y + h - corner_size), (x - 5, y + h + 5), thickness)
    pygame.draw.line(surface, color, (x - 5, y + h + 5), (x + corner_size, y + h + 5), thickness)

    pygame.draw.line(surface, color, (x + w + 5, y + h - corner_size), (x + w + 5, y + h + 5), thickness)
    pygame.draw.line(surface, color, (x + w + 5, y + h + 5), (x + w - corner_size, y + h + 5), thickness)

def create_touch_menu():
    rotation, ui_enabled, font_size, config_width, config_height = load_config()

    pygame.init()

    display_info = pygame.display.Info()
    display_width = display_info.current_w
    display_height = display_info.current_h

    base_width = config_width
    base_height = config_height

    if base_width > display_width * 0.9:
        base_width = int(display_width * 0.9)
        base_height = int(base_width * config_height / config_width)

    if base_height > display_height * 0.9:
        base_height = int(display_height * 0.9)
        base_width = int(base_height * config_width / config_height)

    ui_width = base_width
    ui_height = base_height

    if rotation in [90, 270]:
        draw_surface = pygame.Surface((ui_height, ui_width))
        window_width, window_height = ui_width, ui_height  
    else:
        draw_surface = pygame.Surface((ui_width, ui_height))
        window_width, window_height = ui_width, ui_height

    os.environ['SDL_VIDEO_CENTERED'] = '1'  
    screen = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption("TARS AI INTERFACE")

    surf_width = draw_surface.get_width()
    surf_height = draw_surface.get_height()

    BLACK = (0, 0, 0)
    DARK_GRAY = (15, 15, 15)
    GRAY = (50, 50, 50)
    LIGHT_GRAY = (100, 100, 100)
    WHITE = (255, 255, 255)
    CYAN = (0, 200, 255)
    DARK_CYAN = (0, 100, 150)
    ORANGE = (255, 150, 0)
    RED = (255, 50, 50)

    try:
        title_font = pygame.font.SysFont('dejavusansmono', 80, bold=True)
        section_font = pygame.font.SysFont('dejavusansmono', 24, bold=True)
        button_font = pygame.font.SysFont('dejavusansmono', 32, bold=True)
        small_font = pygame.font.SysFont('dejavusansmono', 18, bold=True)
        tiny_font = pygame.font.SysFont('dejavusansmono', 14, bold=True)
        countdown_font = pygame.font.SysFont('dejavusansmono', 36, bold=True)
        terminal_font = pygame.font.SysFont('dejavusansmono', 9, bold=False)
        terminal_font_bold = pygame.font.SysFont('dejavusansmono', 9, bold=True)
    except:
        try:
            title_font = pygame.font.SysFont('freemono', 80, bold=True)
            section_font = pygame.font.SysFont('freemono', 24, bold=True)
            button_font = pygame.font.SysFont('freemono', 32, bold=True)
            small_font = pygame.font.SysFont('freemono', 18, bold=True)
            tiny_font = pygame.font.SysFont('freemono', 14, bold=True)
            countdown_font = pygame.font.SysFont('freemono', 36, bold=True)
            terminal_font = pygame.font.SysFont('freemono', 9, bold=False)
            terminal_font_bold = pygame.font.SysFont('freemono', 9, bold=True)
        except:
            title_font = pygame.font.Font(None, 80)
            section_font = pygame.font.Font(None, 24)
            button_font = pygame.font.Font(None, 32)
            small_font = pygame.font.Font(None, 18)
            tiny_font = pygame.font.Font(None, 14)
            countdown_font = pygame.font.Font(None, 36)
            terminal_font = pygame.font.Font(None, 9)
            terminal_font_bold = pygame.font.Font(None, 9)

    terminal_scroll = TerminalScroll(surf_width, surf_height, terminal_font, terminal_font_bold)

    button_width = int(surf_width * 0.7)
    button_height = int(surf_height * 0.15)
    button_x = (surf_width - button_width) // 2

    fullscreen_button = pygame.Rect(button_x, int(surf_height * 0.37), button_width, button_height)
    normal_button = pygame.Rect(button_x, int(surf_height * 0.58), button_width, button_height)

    esc_button_width = int(surf_width * 0.12)
    esc_button_height = int(surf_height * 0.06)
    esc_button = pygame.Rect(40, surf_height - esc_button_height - 40, 
                             esc_button_width, esc_button_height)

    countdown_seconds = 30
    start_time = time.time()

    clock = pygame.time.Clock()
    running = True

    button_pressed = None

    while running:
        elapsed_time = time.time() - start_time
        remaining_time = countdown_seconds - elapsed_time

        if remaining_time <= 0:
            pygame.quit()
            stop_tars_ai()
            time.sleep(0.1)
            if ui_enabled:
                print("[AUTO.LAUNCH] UI enabled — starting fullscreen mode.")
                run_tars_ai_fullscreen()
            else:
                print("[AUTO.LAUNCH] UI disabled — starting terminal mode.")
                run_tars_ai_normal()
            return

        mouse_pos = pygame.mouse.get_pos()

        if rotation == 270:
            transformed_mouse = (mouse_pos[1], surf_height - mouse_pos[0])
        elif rotation == 90:
            transformed_mouse = (surf_width - mouse_pos[1], mouse_pos[0])
        elif rotation == 180:
            transformed_mouse = (surf_width - mouse_pos[0], surf_height - mouse_pos[1])
        else:
            transformed_mouse = mouse_pos

        fullscreen_hover = fullscreen_button.collidepoint(transformed_mouse)
        normal_hover = normal_button.collidepoint(transformed_mouse)
        esc_hover = esc_button.collidepoint(transformed_mouse)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    pygame.quit()
                    sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                click_pos = event.pos

                if rotation == 270:
                    transformed_click = (click_pos[1], surf_height - click_pos[0])
                elif rotation == 90:
                    transformed_click = (surf_width - click_pos[1], click_pos[0])
                elif rotation == 180:
                    transformed_click = (surf_width - click_pos[0], surf_height - click_pos[1])
                else:
                    transformed_click = click_pos

                if fullscreen_button.collidepoint(transformed_click):
                    button_pressed = 'fullscreen'
                elif normal_button.collidepoint(transformed_click):
                    button_pressed = 'normal'
                elif esc_button.collidepoint(transformed_click):
                    button_pressed = 'esc'

            if event.type == pygame.MOUSEBUTTONUP:
                click_pos = event.pos

                if rotation == 270:
                    transformed_click = (click_pos[1], surf_height - click_pos[0])
                elif rotation == 90:
                    transformed_click = (surf_width - click_pos[1], click_pos[0])
                elif rotation == 180:
                    transformed_click = (surf_width - click_pos[0], surf_height - click_pos[1])
                else:
                    transformed_click = click_pos

                if button_pressed == 'fullscreen' and fullscreen_button.collidepoint(transformed_click):
                    pygame.quit()
                    stop_tars_ai()
                    time.sleep(0.1)
                    run_tars_ai_fullscreen()
                    return

                elif button_pressed == 'normal' and normal_button.collidepoint(transformed_click):
                    pygame.quit()
                    run_tars_ai_normal()
                    sys.exit()

                elif button_pressed == 'esc' and esc_button.collidepoint(transformed_click):
                    running = False
                    pygame.quit()
                    sys.exit()

                button_pressed = None

        draw_surface.fill(BLACK)

        terminal_scroll.update()
        terminal_scroll.draw(draw_surface, DARK_CYAN)

        draw_grid_background(draw_surface, surf_width, surf_height, 50)

        main_frame = pygame.Rect(20, 20, surf_width - 40, surf_height - 40)
        pygame.draw.rect(draw_surface, CYAN, main_frame, 2)
        draw_corner_brackets(draw_surface, main_frame, CYAN, 30, 3)

        title_text = title_font.render("T.A.R.S", True, CYAN)
        title_rect = title_text.get_rect(center=(surf_width // 2, int(surf_height * 0.12)))
        draw_surface.blit(title_text, title_rect)

        pygame.draw.line(draw_surface, CYAN, (int(surf_width * 0.125), int(surf_height * 0.18)), 
                        (int(surf_width * 0.875), int(surf_height * 0.18)), 2)

        status_y = int(surf_height * 0.22)
        status_texts = [
            "SYS.STATUS: ONLINE",
            "HUMOR.PARAM: 75%",
            "HONEST.PARAM: 90%"
        ]
        for i, text in enumerate(status_texts):
            status_surface = tiny_font.render(text, True, LIGHT_GRAY)
            draw_surface.blit(status_surface, (50, status_y + i * 20))

        mission_text = tiny_font.render(f"MISSION.TIME: {time.strftime('%H:%M:%S')}", True, LIGHT_GRAY)
        draw_surface.blit(mission_text, (int(surf_width * 0.55), status_y))

        esc_color = RED if (esc_hover or button_pressed == 'esc') else DARK_GRAY
        esc_bg_color = WHITE if button_pressed == 'esc' else esc_color
        pygame.draw.rect(draw_surface, esc_bg_color, esc_button)
        pygame.draw.rect(draw_surface, RED if (esc_hover or button_pressed == 'esc') else LIGHT_GRAY, esc_button, 2)
        esc_text = small_font.render("ABORT", True, RED if button_pressed == 'esc' else WHITE)
        esc_text_rect = esc_text.get_rect(center=esc_button.center)
        draw_surface.blit(esc_text, esc_text_rect)

        section_label = section_font.render("LAUNCH MODE SELECTION", True, WHITE)
        section_rect = section_label.get_rect(center=(surf_width // 2, int(surf_height * 0.32)))
        draw_surface.blit(section_label, section_rect)

        fullscreen_color = CYAN if fullscreen_hover else DARK_CYAN
        fullscreen_bg = CYAN if button_pressed == 'fullscreen' else (DARK_GRAY if not fullscreen_hover else (30, 30, 30))
        pygame.draw.rect(draw_surface, fullscreen_bg, fullscreen_button)
        draw_technical_frame(draw_surface, fullscreen_button, fullscreen_color, 2)

        fullscreen_label = tiny_font.render("01", True, LIGHT_GRAY)
        draw_surface.blit(fullscreen_label, (fullscreen_button.x - 30, fullscreen_button.y + 5))

        fullscreen_text = button_font.render("FULLSCREEN.MODE", True, BLACK if button_pressed == 'fullscreen' else (WHITE if fullscreen_hover else CYAN))
        fullscreen_text_rect = fullscreen_text.get_rect(center=fullscreen_button.center)
        draw_surface.blit(fullscreen_text, fullscreen_text_rect)

        normal_color = CYAN if normal_hover else DARK_CYAN
        normal_bg = CYAN if button_pressed == 'normal' else (DARK_GRAY if not normal_hover else (30, 30, 30))
        pygame.draw.rect(draw_surface, normal_bg, normal_button)
        draw_technical_frame(draw_surface, normal_button, normal_color, 2)

        normal_label = tiny_font.render("02", True, LIGHT_GRAY)
        draw_surface.blit(normal_label, (normal_button.x - 30, normal_button.y + 5))

        normal_text = button_font.render("TERMINAL.MODE", True, BLACK if button_pressed == 'normal' else (WHITE if normal_hover else CYAN))
        normal_text_rect = normal_text.get_rect(center=normal_button.center)
        draw_surface.blit(normal_text, normal_text_rect)

        pygame.draw.line(draw_surface, CYAN, (int(surf_width * 0.125), int(surf_height * 0.8)), 
                        (int(surf_width * 0.875), int(surf_height * 0.8)), 2)

        countdown_frame = pygame.Rect(int(surf_width * 0.4), int(surf_height * 0.85), 
                                      int(surf_width * 0.2), int(surf_height * 0.083))
        draw_corner_brackets(draw_surface, countdown_frame, ORANGE if remaining_time <= 3 else CYAN, 15, 2)

        countdown_label = tiny_font.render("AUTO.LAUNCH", True, LIGHT_GRAY)
        countdown_label_rect = countdown_label.get_rect(center=(surf_width // 2, int(surf_height * 0.833)))
        draw_surface.blit(countdown_label, countdown_label_rect)

        countdown_color = ORANGE if remaining_time <= 3 else CYAN
        countdown_text = countdown_font.render(f"{int(remaining_time):02d}s", True, countdown_color)
        countdown_rect = countdown_text.get_rect(center=(surf_width // 2, int(surf_height * 0.892)))
        draw_surface.blit(countdown_text, countdown_rect)

        if remaining_time <= 3:
            warning_text = tiny_font.render(">> INITIATING <<", True, ORANGE)
            warning_rect = warning_text.get_rect(center=(surf_width // 2, int(surf_height * 0.933)))
            draw_surface.blit(warning_text, warning_rect)

        if rotation == 90:
            rotated_surface = pygame.transform.rotate(draw_surface, 90)  
        elif rotation == 180:
            rotated_surface = pygame.transform.rotate(draw_surface, 180)
        elif rotation == 270:
            rotated_surface = pygame.transform.rotate(draw_surface, 270)
        else:
            rotated_surface = draw_surface

        screen.blit(rotated_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    if not check_required_file():
        print("[FILE.CHECK] hey_tars_templates.pkl not found — launching terminal mode.")
        run_tars_ai_normal()
    else:
        create_touch_menu()