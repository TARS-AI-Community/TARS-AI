import os
import subprocess
import time
import pygame
import sys
import configparser

def load_config():
    """Load configuration from config.ini"""
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
    """Run TARS AI in fullscreen mode or fallback to terminal mode."""
    command = "cd src && source .venv/bin/activate && python app.py show_ui=true"


    subprocess.run(command, shell=True, executable="/bin/bash")

def run_tars_ai_normal():
    command = (
        "cd src && source .venv/bin/activate && python app.py show_ui=false"
    )

    subprocess.run(command, shell=True, executable="/bin/bash")

def draw_corner_brackets(surface, rect, color, size=20, thickness=2):
    """Draw corner brackets like in Interstellar UI"""
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
    """Draw a subtle grid background"""
    for x in range(0, width, grid_size):
        pygame.draw.line(surface, color, (x, 0), (x, height), 1)
    for y in range(0, height, grid_size):
        pygame.draw.line(surface, color, (0, y), (width, y), 1)

def draw_technical_frame(surface, rect, color, thickness=2):
    """Draw technical-looking frame elements"""
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
    except:
        try:
            title_font = pygame.font.SysFont('freemono', 80, bold=True)
            section_font = pygame.font.SysFont('freemono', 24, bold=True)
            button_font = pygame.font.SysFont('freemono', 32, bold=True)
            small_font = pygame.font.SysFont('freemono', 18, bold=True)
            tiny_font = pygame.font.SysFont('freemono', 14, bold=True)
            countdown_font = pygame.font.SysFont('freemono', 36, bold=True)
        except:
            title_font = pygame.font.Font(None, 80)
            section_font = pygame.font.Font(None, 24)
            button_font = pygame.font.Font(None, 32)
            small_font = pygame.font.Font(None, 18)
            tiny_font = pygame.font.Font(None, 14)
            countdown_font = pygame.font.Font(None, 36)

    button_width = int(surf_width * 0.7)
    button_height = int(surf_height * 0.15)
    button_x = (surf_width - button_width) // 2

    fullscreen_button = pygame.Rect(button_x, int(surf_height * 0.37), button_width, button_height)
    normal_button = pygame.Rect(button_x, int(surf_height * 0.58), button_width, button_height)

    esc_button_width = int(surf_width * 0.12)
    esc_button_height = int(surf_height * 0.06)
    esc_button = pygame.Rect(40, surf_height - esc_button_height - 40, 
                             esc_button_width, esc_button_height)

    countdown_seconds = 10
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

        draw_grid_background(draw_surface, surf_width, surf_height, 50, DARK_GRAY)

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
    os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    create_touch_menu()