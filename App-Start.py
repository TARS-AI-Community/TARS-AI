import os
os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
# Ensure PipeWire/PulseAudio is reachable (needed when launched from autostart)
os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

import subprocess
import time
import pygame
import sys
import configparser
import random

TEST_UPDATE_MODE = False

def check_for_updates():
    if TEST_UPDATE_MODE:
        fake_commits = [
            "Nothing to see here. Move along",
            "if this code fail, blame atomikspace",
            "this is an update"
        ]
        return len(fake_commits), fake_commits
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        result = subprocess.run(
            ["git", "fetch"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return None, []
        
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"
        
        count_result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/{current_branch}"],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        
        if count_result.returncode != 0:
            return None, []
        
        commit_count = int(count_result.stdout.strip())
        
        if commit_count == 0:
            return 0, []
        
        log_result = subprocess.run(
            ["git", "log", "--oneline", "--no-decorate", f"HEAD..origin/{current_branch}"],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        
        commits = []
        if log_result.returncode == 0:
            commits = [line.strip() for line in log_result.stdout.strip().split('\n') if line.strip()]
        
        return commit_count, commits
        
    except subprocess.TimeoutExpired:
        return None, []
    except Exception as e:
        return None, []


def check_git_clean():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return False
        return len(result.stdout.strip()) == 0
    except:
        return False


def run_install_script():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_script = os.path.join(script_dir, "Install.sh")
        
        if not os.path.exists(install_script):
            return False, "Install.sh not found"
        
        result = subprocess.run(
            ["bash", install_script],
            cwd=script_dir
        )
        
        if result.returncode == 0:
            return True, None
        else:
            return False, "Install script failed"
        
    except Exception as e:
        return False, str(e)


def handle_install_updates():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("\n" + "="*50)
    print("  T.A.R.S UPDATE SYSTEM")
    print("="*50)
    print("\nThis will pull the latest changes and run Install.sh")
    print("Make sure you have no unsaved work.\n")
    
    try:
        response = input("Ready to start update? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nUpdate cancelled.")
        return False
    
    if response not in ['y', 'yes']:
        print("Update cancelled.")
        return False
    
    print("\nChecking for local changes...")
    if not check_git_clean():
        print("ERROR: Local changes detected. Please commit or stash them first.")
        input("\nPress Enter to return to menu...")
        return False
    
    print("Pulling latest changes...")
    pull_result = subprocess.run(
        ["git", "pull"],
        cwd=script_dir
    )
    
    if pull_result.returncode != 0:
        print("ERROR: Git pull failed.")
        input("\nPress Enter to return to menu...")
        return False
    
    print("\nRunning Install.sh...")
    success, error = run_install_script()
    
    if not success:
        print(f"ERROR: {error}")
        input("\nPress Enter to return to menu...")
        return False
    
    print("\nUpdate complete! Restarting...")
    time.sleep(1)
    
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])

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
                base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "tts")
                wake_word = config.get('STT', 'wake_word', fallback='hey tars').strip()
                ww_slug = wake_word.replace(' ', '_')
                onnx_file = os.path.join(base_dir, f"{ww_slug}.onnx")
                templates_file = os.path.join(base_dir, f"{ww_slug}_templates.pkl")

                atomik_mode = config.get('STT', 'atomik_mode', fallback='auto').strip().lower()

                if atomik_mode == 'model':
                    return os.path.exists(onnx_file)
                else:
                    # template and auto both use templates
                    return os.path.exists(templates_file)
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

    ui_enabled = False
    font_size = 12

    try:
        config.read(config_path)

        if config.has_option('UI', 'UI_enabled'):
            ui_enabled = config.getboolean('UI', 'UI_enabled')

        if config.has_option('UI', 'font_size'):
            font_size = config.getint('UI', 'font_size')

        print(f"Launching Main App")

    except Exception as e:
        print(f"[CONFIG] Error reading config file: {e}")
        print("[CONFIG] Using default values")

    return ui_enabled, font_size

def stop_tars_ai():
    subprocess.run(["killall", "xterm"], check=False)
    subprocess.run(["pkill", "-f", "python app.py"], check=False)

def _extra_args():
    """Collect extra key=value CLI args (e.g. speed=true debug=true) to forward to app.py."""
    return " ".join(a for a in sys.argv[1:] if "=" in a)

def run_tars_ai_fullscreen():
    extra = _extra_args()
    command = f"cd src && source .venv/bin/activate && python app.py show_ui=true {extra}"
    subprocess.run(command, shell=True, executable="/bin/bash")

def run_tars_ai_normal():
    extra = _extra_args()
    command = f"cd src && source .venv/bin/activate && python app.py show_ui=false {extra}"
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
    ui_enabled, font_size = load_config()
    
    update_count, update_commits = check_for_updates()
    if update_count is None:
        update_count = 0
        update_commits = []

    pygame.init()

    display_info = pygame.display.Info()
    display_width = display_info.current_w
    display_height = display_info.current_h

    if display_height > display_width:
        logical_width = display_width
        logical_height = display_height
        effective_rotate = 0
    else:
        logical_width = display_height
        logical_height = display_width
        effective_rotate = 270

    max_width = int(display_width * 0.9)
    max_height = int(display_height * 0.9)
    
    if effective_rotate in [90, 270]:
        window_width = logical_height
        window_height = logical_width
    else:
        window_width = logical_width
        window_height = logical_height
    
    scale = min(max_width / window_width, max_height / window_height, 1.0)
    window_width = int(window_width * scale)
    window_height = int(window_height * scale)
    logical_width = int(logical_width * scale)
    logical_height = int(logical_height * scale)

    print(f"[UI] Screen: {display_width}x{display_height}, Logical: {logical_width}x{logical_height}, Rotate: {effective_rotate}")

    draw_surface = pygame.Surface((logical_width, logical_height))

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
    GREEN = (0, 200, 100)

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

    esc_button_width = int(surf_width * 0.15)
    esc_button_height = int(surf_height * 0.06)
    esc_button = pygame.Rect(40, surf_height - esc_button_height - 40, 
                             esc_button_width, esc_button_height)

    updates_button_width = int(surf_width * 0.25)
    updates_button_height = int(surf_height * 0.06)
    updates_button = pygame.Rect(surf_width - updates_button_width - 40, 
                                  surf_height - updates_button_height - 40,
                                  updates_button_width, updates_button_height)

    show_popup = False
    popup_scroll_offset = 0
    popup_max_visible = 8
    popup_button_pressed = None
    popup_open_time = 0
    paused_time = 0
    elapsed_time = 0

    countdown_seconds = 30
    start_time = time.time()

    clock = pygame.time.Clock()
    running = True

    button_pressed = None

    while running:
        current_time = time.time()
        
        if not show_popup:
            elapsed_time = current_time - start_time - paused_time
        remaining_time = countdown_seconds - elapsed_time

        if remaining_time <= 0 and not show_popup:
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

        if effective_rotate == 270:
            transformed_mouse = (mouse_pos[1], surf_height - mouse_pos[0])
        elif effective_rotate == 90:
            transformed_mouse = (surf_width - mouse_pos[1], mouse_pos[0])
        elif effective_rotate == 180:
            transformed_mouse = (surf_width - mouse_pos[0], surf_height - mouse_pos[1])
        else:
            transformed_mouse = mouse_pos

        fullscreen_hover = fullscreen_button.collidepoint(transformed_mouse)
        normal_hover = normal_button.collidepoint(transformed_mouse)
        esc_hover = esc_button.collidepoint(transformed_mouse)
        updates_hover = updates_button.collidepoint(transformed_mouse) if update_count > 0 else False

        popup_width = int(surf_width * 0.85)
        popup_height = int(surf_height * 0.7)
        popup_x = (surf_width - popup_width) // 2
        popup_y = (surf_height - popup_height) // 2
        popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)
        
        popup_btn_width = int(popup_width * 0.28)
        popup_btn_height = int(popup_height * 0.09)
        popup_btn_y = popup_y + popup_height - popup_btn_height - 25
        popup_install_btn = pygame.Rect(popup_x + 20, popup_btn_y, popup_btn_width, popup_btn_height)
        popup_skip_btn = pygame.Rect(popup_x + popup_width - popup_btn_width - 20, popup_btn_y, popup_btn_width, popup_btn_height)
        
        popup_install_hover = popup_install_btn.collidepoint(transformed_mouse) if show_popup else False
        popup_skip_hover = popup_skip_btn.collidepoint(transformed_mouse) if show_popup else False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if show_popup:
                    if event.key == pygame.K_ESCAPE:
                        show_popup = False
                        paused_time += time.time() - popup_open_time
                    elif event.key == pygame.K_RETURN:
                        pygame.quit()
                        handle_install_updates()
                        create_touch_menu()
                        return
                    elif event.key == pygame.K_UP:
                        popup_scroll_offset = max(0, popup_scroll_offset - 1)
                    elif event.key == pygame.K_DOWN:
                        popup_scroll_offset = min(max(0, len(update_commits) - popup_max_visible), popup_scroll_offset + 1)
                else:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        pygame.quit()
                        sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                click_pos = event.pos

                if effective_rotate == 270:
                    transformed_click = (click_pos[1], surf_height - click_pos[0])
                elif effective_rotate == 90:
                    transformed_click = (surf_width - click_pos[1], click_pos[0])
                elif effective_rotate == 180:
                    transformed_click = (surf_width - click_pos[0], surf_height - click_pos[1])
                else:
                    transformed_click = click_pos

                if show_popup:
                    if event.button == 4:
                        popup_scroll_offset = max(0, popup_scroll_offset - 1)
                    elif event.button == 5:
                        popup_scroll_offset = min(max(0, len(update_commits) - popup_max_visible), popup_scroll_offset + 1)
                    elif event.button == 1:
                        if popup_install_btn.collidepoint(transformed_click):
                            popup_button_pressed = 'install'
                        elif popup_skip_btn.collidepoint(transformed_click):
                            popup_button_pressed = 'skip'
                else:
                    if fullscreen_button.collidepoint(transformed_click):
                        button_pressed = 'fullscreen'
                    elif normal_button.collidepoint(transformed_click):
                        button_pressed = 'normal'
                    elif esc_button.collidepoint(transformed_click):
                        button_pressed = 'esc'
                    elif update_count > 0 and updates_button.collidepoint(transformed_click):
                        button_pressed = 'updates'

            if event.type == pygame.MOUSEBUTTONUP:
                click_pos = event.pos

                if effective_rotate == 270:
                    transformed_click = (click_pos[1], surf_height - click_pos[0])
                elif effective_rotate == 90:
                    transformed_click = (surf_width - click_pos[1], click_pos[0])
                elif effective_rotate == 180:
                    transformed_click = (surf_width - click_pos[0], surf_height - click_pos[1])
                else:
                    transformed_click = click_pos

                if show_popup:
                    if popup_button_pressed == 'install' and popup_install_btn.collidepoint(transformed_click):
                        pygame.quit()
                        handle_install_updates()
                        create_touch_menu()
                        return
                    elif popup_button_pressed == 'skip' and popup_skip_btn.collidepoint(transformed_click):
                        show_popup = False
                        paused_time += time.time() - popup_open_time
                    popup_button_pressed = None
                else:
                    if button_pressed == 'fullscreen' and fullscreen_button.collidepoint(transformed_click):
                        pygame.quit()
                        stop_tars_ai()
                        time.sleep(0.1)
                        run_tars_ai_fullscreen()
                        return

                    elif button_pressed == 'normal' and normal_button.collidepoint(transformed_click):
                        pygame.quit()
                        stop_tars_ai()
                        time.sleep(0.1)
                        run_tars_ai_normal()
                        sys.exit()

                    elif button_pressed == 'esc' and esc_button.collidepoint(transformed_click):
                        running = False
                        pygame.quit()
                        sys.exit()

                    elif button_pressed == 'updates' and update_count > 0 and updates_button.collidepoint(transformed_click):
                        show_popup = True
                        popup_open_time = time.time()
                        popup_scroll_offset = 0

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

        if update_count > 0:
            updates_color = GREEN if (updates_hover or button_pressed == 'updates') else DARK_GRAY
            updates_bg_color = WHITE if button_pressed == 'updates' else updates_color
            pygame.draw.rect(draw_surface, updates_bg_color, updates_button)
            pygame.draw.rect(draw_surface, GREEN if (updates_hover or button_pressed == 'updates') else LIGHT_GRAY, updates_button, 2)
            updates_text = small_font.render(f"UPDATES ({update_count})", True, GREEN if button_pressed == 'updates' else WHITE)
            updates_text_rect = updates_text.get_rect(center=updates_button.center)
            draw_surface.blit(updates_text, updates_text_rect)

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
        
        if show_popup:
            frame_color = LIGHT_GRAY
            countdown_color = LIGHT_GRAY
        elif remaining_time <= 3:
            frame_color = ORANGE
            countdown_color = ORANGE
        else:
            frame_color = CYAN
            countdown_color = CYAN
            
        draw_corner_brackets(draw_surface, countdown_frame, frame_color, 15, 2)

        countdown_label = tiny_font.render("AUTO.LAUNCH", True, LIGHT_GRAY)
        countdown_label_rect = countdown_label.get_rect(center=(surf_width // 2, int(surf_height * 0.833)))
        draw_surface.blit(countdown_label, countdown_label_rect)

        if show_popup:
            countdown_text = section_font.render("PAUSED", True, countdown_color)
        else:
            countdown_text = countdown_font.render(f"{int(remaining_time):02d}s", True, countdown_color)
        countdown_rect = countdown_text.get_rect(center=(surf_width // 2, int(surf_height * 0.892)))
        draw_surface.blit(countdown_text, countdown_rect)

        if remaining_time <= 3 and not show_popup:
            warning_text = tiny_font.render(">> INITIATING <<", True, ORANGE)
            warning_rect = warning_text.get_rect(center=(surf_width // 2, int(surf_height * 0.933)))
            draw_surface.blit(warning_text, warning_rect)

        if show_popup:
            overlay = pygame.Surface((surf_width, surf_height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            draw_surface.blit(overlay, (0, 0))
            
            pygame.draw.rect(draw_surface, BLACK, popup_rect)
            pygame.draw.rect(draw_surface, CYAN, popup_rect, 2)
            draw_corner_brackets(draw_surface, popup_rect, CYAN, 20, 2)
            
            popup_title = section_font.render("UPDATES AVAILABLE", True, CYAN)
            popup_title_rect = popup_title.get_rect(center=(surf_width // 2, popup_y + 30))
            draw_surface.blit(popup_title, popup_title_rect)
            
            count_text = tiny_font.render(f"{update_count} new commit(s) from remote:", True, WHITE)
            draw_surface.blit(count_text, (popup_x + 20, popup_y + 55))
            
            list_margin = 20
            list_top = popup_y + 80
            list_height = popup_height - 170
            list_rect_inner = pygame.Rect(popup_x + list_margin, list_top, popup_width - list_margin * 2, list_height)
            pygame.draw.rect(draw_surface, (15, 15, 15), list_rect_inner)
            pygame.draw.rect(draw_surface, DARK_CYAN, list_rect_inner, 1)
            
            commit_line_height = 24
            visible_commits = update_commits[popup_scroll_offset:popup_scroll_offset + popup_max_visible]
            for i, commit in enumerate(visible_commits):
                max_chars = 45
                display_text = commit[:max_chars] + "..." if len(commit) > max_chars else commit
                color = CYAN if i % 2 == 0 else WHITE
                commit_surface = tiny_font.render(f"• {display_text}", True, color)
                draw_surface.blit(commit_surface, (popup_x + list_margin + 10, list_top + 8 + i * commit_line_height))
            
            if len(update_commits) > popup_max_visible:
                scroll_text = tiny_font.render(
                    f"[{popup_scroll_offset + 1}-{min(popup_scroll_offset + popup_max_visible, len(update_commits))}/{len(update_commits)}]", 
                    True, LIGHT_GRAY
                )
                scroll_rect = scroll_text.get_rect(center=(surf_width // 2, list_top + list_height + 12))
                draw_surface.blit(scroll_text, scroll_rect)
            
            install_color = GREEN if popup_install_hover else DARK_CYAN
            install_bg = GREEN if popup_button_pressed == 'install' else (DARK_GRAY if not popup_install_hover else (30, 50, 30))
            pygame.draw.rect(draw_surface, install_bg, popup_install_btn)
            pygame.draw.rect(draw_surface, GREEN, popup_install_btn, 2)
            install_text = small_font.render("INSTALL", True, BLACK if popup_button_pressed == 'install' else (WHITE if popup_install_hover else GREEN))
            install_text_rect = install_text.get_rect(center=popup_install_btn.center)
            draw_surface.blit(install_text, install_text_rect)
            
            skip_bg = WHITE if popup_button_pressed == 'skip' else (DARK_GRAY if not popup_skip_hover else (40, 40, 40))
            pygame.draw.rect(draw_surface, skip_bg, popup_skip_btn)
            pygame.draw.rect(draw_surface, WHITE if popup_skip_hover else LIGHT_GRAY, popup_skip_btn, 2)
            skip_text = small_font.render("SKIP", True, BLACK if popup_button_pressed == 'skip' else WHITE)
            skip_text_rect = skip_text.get_rect(center=popup_skip_btn.center)
            draw_surface.blit(skip_text, skip_text_rect)
            
            hint_text = tiny_font.render("ENTER to install | ESC to close", True, LIGHT_GRAY)
            hint_rect = hint_text.get_rect(center=(surf_width // 2, popup_y + popup_height - 8))
            draw_surface.blit(hint_text, hint_rect)

        if effective_rotate == 90:
            rotated_surface = pygame.transform.rotate(draw_surface, 90)  
        elif effective_rotate == 180:
            rotated_surface = pygame.transform.rotate(draw_surface, 180)
        elif effective_rotate == 270:
            rotated_surface = pygame.transform.rotate(draw_surface, 270)
        else:
            rotated_surface = draw_surface

        screen.blit(rotated_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)

def check_aec_setup():
    """Run AEC auto-setup on first boot if not already configured.

    Flags:
        aec=tune          — force a full AEC re-tune
        aec=skip          — skip AEC entirely (run app without echo cancellation)
        aec=remove        — remove AEC config and restore backup
        aec=<config-name> — apply a specific config by name (e.g. aec=raw-max-all)
    """
    # Extract the aec= value from argv
    aec_val = None
    for a in sys.argv[1:]:
        if a.lower().startswith("aec="):
            aec_val = a.split("=", 1)[1].strip()
            break
    if aec_val is None:
        aec_val = ""

    force = aec_val.lower() == "tune"
    remove = aec_val.lower() == "remove"
    skip = aec_val.lower() == "skip"
    # Any other non-empty value is treated as a config name
    config_name = aec_val if aec_val and not force and not remove and not skip else None

    if skip:
        print("[AEC] aec=skip — skipping AEC setup")
        return

    try:
        from aec import (is_aec_tuned, is_aec_configured, is_aec_disabled,
                         aec_module_installed, setup_aec, remove_aec, apply_named_config)
        if remove:
            print("[AEC] aec=remove — removing AEC configuration...")
            remove_aec()
            return
        if config_name:
            print(f"[AEC] aec={config_name} — applying config directly...")
            apply_named_config(config_name)
            return
        if force:
            print("[AEC] aec=tune — forcing AEC re-tune...")
            setup_aec(force=True)
            return
        if is_aec_configured():
            return  # Already configured (tuned or default) — nothing to do
        if is_aec_disabled():
            return  # User explicitly removed AEC — don't re-install
        # AEC not configured and not disabled — first boot, install default
        if not aec_module_installed():
            print("[AEC] AEC module not available — skipping")
            return
        print("[AEC] First boot — installing default AEC config (raw-max-all)...")
        print("[AEC]   Run with aec=tune to auto-tune for your specific hardware.")
        apply_named_config("raw-max-all")
    except ImportError:
        print("[AEC] aec.py not found — skipping")
    except Exception as e:
        print(f"[AEC] Auto-setup failed (non-fatal): {e}")

if __name__ == "__main__":
    check_aec_setup()
    if not check_required_file():
        # Read atomik_mode to give a specific message
        try:
            _cfg = configparser.ConfigParser()
            _cfg.read(os.path.join('src', 'config.ini'))
            _amode = _cfg.get('STT', 'atomik_mode', fallback='auto').strip().lower()
        except Exception:
            _amode = 'auto'

        if _amode == 'template':
            print("[FILE.CHECK] Wake word templates not found — launching terminal mode for recording.")
        elif _amode == 'model':
            print("[FILE.CHECK] Wake word model (ONNX/CNN) not found — launching terminal mode for training.")
            print("[FILE.CHECK] For ONNX: use tools/wakeword-trainer on a PC, then copy hey_tars.onnx to src/tts/")
        else:
            print("[FILE.CHECK] Wake word model not found — launching terminal mode for training.")
        run_tars_ai_normal()
    else:
        create_touch_menu()