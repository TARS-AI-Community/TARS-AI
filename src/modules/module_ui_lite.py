"""
GUI Lite - PiZero2
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
import threading
import os

try:
    import pygame.sysfont
    pygame.sysfont.Sysfonts = {"_": ""}
    pygame.sysfont.Sysalias = {}
except (ImportError, AttributeError):
    pass

from module_config import load_config

try:
    from UI.module_ui_screensaver_lite import ScreensaverManagerLite
except Exception:
    ScreensaverManagerLite = None

CONFIG = load_config()

screenWidth = CONFIG['UI'].get('screen_width', 0)
screenHeight = CONFIG['UI'].get('screen_height', 0)
show_mouse = CONFIG['UI']['show_mouse']
fullscreen = CONFIG['UI']['fullscreen']
screensaver_timer = CONFIG['UI']['screensaver_timer']
screensaver_list = CONFIG['UI']['screensaver_list']
_char_name = CONFIG['CHAR'].get('character_name', 'TARS')

MSG_COLORS = {
    "USER": (255, 200, 0),
    _char_name: (0, 200, 255),
    "SYSTEM": (0, 200, 100),
    "DEBUG": (80, 80, 80),
    "INFO": (255, 255, 255),
    "WARNING": (255, 80, 80),
}
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
CYAN = (0, 200, 255)
YELLOW = (255, 200, 0)


class UIManagerLite(threading.Thread):
    def __init__(self, shutdown_event, battery_module, cpu_temp_module=None, **kwargs):
        super().__init__(daemon=True)
        self.shutdown_event = shutdown_event
        self.battery_module = battery_module
        self.cpu_temp_module = cpu_temp_module
        self.running = False
        self.paused = False

        self._lock = threading.Lock()
        self._pending = []
        self._dirty = threading.Event()

        self._state = ""
        self._screensaver_mgr = None
        self._activity = threading.Event()


    def update_data(self, source, message, category="INFO"):
        with self._lock:
            self._pending.append((source, str(message), category))
        if source == _char_name:
            self._state = ""
        self._activity.set()
        self._dirty.set()

    def deactivate_screensaver(self):
        if self._screensaver_mgr:
            self._screensaver_mgr.deactivate()
            self._dirty.set()

    def save_memory(self):
        pass

    def set_tars_status(self, status):
        pass

    def think(self):
        if self._state != "THINKING":
            self._state = "THINKING"
            self._activity.set()
            self._dirty.set()

    def silence(self, progress=0):
        new = "LISTENING" if progress > 0 else ""
        if self._state != new:
            self._state = new
            if new:
                self._activity.set()
            self._dirty.set()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.running = False
        self._dirty.set()

    def exit_program(self):
        self.running = False
        self.shutdown_event.set()
        os._exit(0)

    def initiate_shutdown(self):
        self.running = False
        self.shutdown_event.set()
        import subprocess
        try:
            subprocess.Popen(['sudo', 'shutdown', 'now'])
        except Exception:
            pass
        os._exit(0)


    def run(self):
        try:
            try:
                os.nice(19)
            except OSError:
                pass

            pygame.display.init()
            pygame.font.init()
            pygame.mouse.set_visible(show_mouse)

            flags = pygame.HWSURFACE
            if fullscreen:
                flags |= pygame.FULLSCREEN

            if fullscreen:
                screen = pygame.display.set_mode((0, 0), flags, 16)
            else:
                w = screenWidth if screenWidth > 0 else pygame.display.Info().current_w
                h = screenHeight if screenHeight > 0 else pygame.display.Info().current_h
                screen = pygame.display.set_mode((w, h), flags, 16)

            display_width, display_height = screen.get_size()

            if display_height > display_width:
                logical_width = display_width
                logical_height = display_height
                effective_rotate = 0
            else:
                logical_width = display_height
                logical_height = display_width
                effective_rotate = 270

            print(f"[UI-LITE] Screen: {display_width}x{display_height}, Logical: {logical_width}x{logical_height}, Rotate: {effective_rotate}", flush=True)

            font_path = os.path.join(os.path.dirname(__file__), "UI", "mono.ttf")
            if not os.path.exists(font_path):
                font_path = None
            font = pygame.font.Font(font_path, 20)
            line_h = font.get_linesize() + 5
            bar_h = line_h + 8
            padding = 15
            max_text_width = logical_width - 2 * padding
            max_lines = (logical_height - bar_h) // line_h

            msg_surface = pygame.Surface((logical_width, logical_height - bar_h))
            msg_surface.fill(BLACK)

            label_listening = font.render("LISTENING...", True, CYAN)
            label_thinking = font.render("THINKING...", True, YELLOW)

            composed = pygame.Surface((logical_width, logical_height))
            composed.fill(BLACK)

            if effective_rotate != 0:
                screen_cache = pygame.transform.rotate(composed, effective_rotate)
            else:
                screen_cache = composed.copy()

            ss_mgr = None
            if screensaver_timer > 0 and ScreensaverManagerLite is not None:
                try:
                    ss_mgr = ScreensaverManagerLite(
                        composed, logical_width, logical_height,
                        timeout=screensaver_timer,
                        screensaver_list=screensaver_list,
                    )
                    self._screensaver_mgr = ss_mgr
                except Exception as e:
                    print(f"[UI-LITE] Screensaver init failed: {e}", flush=True)

            self.running = True
            screen.blit(screen_cache, (0, 0))
            pygame.display.flip()

            rendered_lines = []
            prev_state = ""
            msgs_dirty = False
            was_screensaver = False

            while self.running and not self.shutdown_event.is_set():
                if ss_mgr:
                    if ss_mgr.is_active():
                        self._dirty.wait(timeout=1.0 / 15)
                    else:
                        self._dirty.wait(timeout=1.0)
                else:
                    self._dirty.wait()
                self._dirty.clear()

                if not self.running:
                    break
                if self.paused:
                    continue

                for evt in pygame.event.get():
                    if evt.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION):
                        if ss_mgr:
                            ss_mgr.reset_timer()

                if ss_mgr and self._activity.is_set():
                    self._activity.clear()
                    ss_mgr.reset_timer()

                if ss_mgr:
                    ss_mgr.check_timeout()

                with self._lock:
                    new = self._pending[:]
                    self._pending.clear()

                if new:
                    msgs_dirty = True
                    for source, text, category in new:
                        color = MSG_COLORS.get(category, WHITE)
                        full_text = f"[{source}] {text}"
                        words = full_text.split(' ')
                        lines = []
                        current = []
                        for word in words:
                            test = ' '.join(current + [word])
                            if font.size(test)[0] <= max_text_width:
                                current.append(word)
                            else:
                                if current:
                                    lines.append(' '.join(current))
                                current = [word]
                        if current:
                            lines.append(' '.join(current))
                        if not lines:
                            lines = ['']
                        for line in lines:
                            rendered_lines.append(font.render(line, True, color))
                    if len(rendered_lines) > max_lines:
                        rendered_lines = rendered_lines[-max_lines:]

                state = self._state

                if ss_mgr and ss_mgr.is_active():
                    try:
                        ss_mgr.render()
                    except Exception as e:
                        print(f"[UI-LITE] Screensaver render error: {e}", flush=True)
                        ss_mgr.deactivate()
                        ss_mgr = None
                        self._screensaver_mgr = None
                    was_screensaver = True
                else:
                    if was_screensaver:
                        msgs_dirty = True
                        was_screensaver = False

                    if not msgs_dirty and state == prev_state:
                        continue

                    if msgs_dirty:
                        msg_surface.fill(BLACK)
                        y = 0
                        for surf in rendered_lines:
                            msg_surface.blit(surf, (padding, y))
                            y += line_h
                        msgs_dirty = False

                    composed.blit(msg_surface, (0, 0))

                    bar_y = logical_height - bar_h
                    pygame.draw.rect(composed, BLACK, (0, bar_y, logical_width, bar_h))

                    if state:
                        label = label_thinking if state == "THINKING" else label_listening
                        lx = (logical_width - label.get_width()) // 2
                        ly = bar_y + (bar_h - label.get_height()) // 2
                        composed.blit(label, (lx, ly))

                    prev_state = state

                if effective_rotate != 0:
                    screen_cache = pygame.transform.rotate(composed, effective_rotate)
                else:
                    screen_cache = composed
                screen.blit(screen_cache, (0, 0))
                pygame.display.flip()

        except Exception as e:
            print(f"[UI-LITE] ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            pygame.quit()
