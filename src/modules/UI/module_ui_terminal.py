# module_ui_terminal.py
import pygame
import time
from typing import List, Tuple, Callable, Optional

class TerminalSystem:
    def __init__(self, width: int, height: int, bg_color=(0, 0, 0), bg_alpha=13, 
                 on_background_change: Optional[Callable] = None,
                 on_shutdown: Optional[Callable] = None,
                 on_spectrum_change: Optional[Callable] = None):
        """
        High-tech spacecraft interface terminal UI overlay
        """
        self.width = width
        self.height = height
        self.bg_color = bg_color
        self.bg_alpha = bg_alpha
        
        # Callbacks
        self.on_background_change = on_background_change
        self.on_shutdown = on_shutdown
        self.on_spectrum_change = on_spectrum_change
        
        # Enhanced retro sci-fi color scheme
        self.primary_color = (0, 255, 255)  # Bright cyan
        self.secondary_color = (0, 180, 200)  # Teal
        self.accent_color = (0, 120, 150)  # Dark teal
        self.bg_terminal = (5, 15, 20)  # Very dark blue-teal
        self.bg_panel = (10, 25, 30)  # Panel background
        self.border_color = (0, 200, 220)  # Cyan border
        self.text_color = (0, 240, 200)  # Cyan-green
        self.dim_text_color = (0, 120, 120)  # Dimmed cyan
        self.label_color = (0, 150, 180)  # Label text
        self.warning_color = (255, 100, 0)  # Orange
        self.status_active = (0, 255, 100)  # Green
        self.status_warning = (255, 180, 0)  # Amber
        self.status_error = (255, 50, 50)  # Red
        
        # Layout - Top toolbar (6%), terminal area, bottom toolbar (6%)
        self.toolbar_height = int(height * 0.06)
        self.bottom_toolbar_height = int(height * 0.06)
        self.terminal_height = height - self.toolbar_height - self.bottom_toolbar_height
        
        # Terminal settings
        self.line_spacing = 5
        self.padding = 15
        self.border_thickness = 2
        
        # Font setup - ALL 50% BIGGER
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
        
        # Message storage
        self.messages: List[Tuple[str, str, str, float]] = []
        self.max_messages = 1000
        
        # Scrolling
        self.scroll_offset = 0
        self.auto_scroll = True
        
        # Calculate max visible lines
        self.line_height = self.font.get_linesize() + self.line_spacing
        self.max_visible_lines = (self.terminal_height - 2 * self.padding - 40) // self.line_height
        
        # Cache for wrapped lines
        self.wrapped_cache = []
        self.cache_dirty = True
        
        # Top toolbar buttons
        self.top_buttons = [
            {"label": "CLEAR", "code": "CLR-01", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "BG", "code": "BG-SW", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "WAVE", "code": "SPK-CY", "rect": None, "active": False, "color": None, "position": "left"},
            {"label": "PWR-DN", "code": "PWR-DN", "rect": None, "active": False, "color": "warning", "position": "right"},
        ]
        
        # Bottom toolbar buttons
        self.bottom_buttons = [
            {"label": "CAM", "code": "CAM-01", "rect": None, "active": False, "color": None, "position": "left"},
        ]
        
        self._init_buttons()
        
        # Animation states
        self.thinking = False
        self.thinking_time = 0
        self.action_flash = 0
        self.memory_pulse = 0
        self.scan_line = 0
        self.status_blink = 0
        
        # Shutdown confirmation
        self.shutdown_confirm = False
        self.shutdown_time = 0
        
        # Create surface for overlay
        self.overlay_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        
    def _init_buttons(self):
        """Initialize button positions for top and bottom toolbars"""
        button_width = 90
        button_height_top = self.toolbar_height - 10
        button_height_bottom = self.bottom_toolbar_height - 10
        button_spacing = 8
        start_y_top = 5
        start_y_bottom = self.toolbar_height + self.terminal_height + 5
        
        # Initialize top buttons
        left_x = 10
        left_index = 0
        
        for button in self.top_buttons:
            if button.get("position") == "right":
                x = self.width - button_width - 10
            else:
                x = left_x + left_index * (button_width + button_spacing)
                left_index += 1
            
            button["rect"] = pygame.Rect(x, start_y_top, button_width, button_height_top)
        
        # Initialize bottom buttons
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
        """Update the cache of wrapped messages"""
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
        """Add a new message to the terminal"""
        timestamp = time.time()
        self.messages.append((key, value, msg_type, timestamp))
        self.cache_dirty = True
        
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
            self.cache_dirty = True
        
        if self.auto_scroll:
            self.scroll_offset = 0
    
    def clear_messages(self):
        """Clear all messages"""
        self.messages.clear()
        self.wrapped_cache.clear()
        self.scroll_offset = 0
        self.cache_dirty = True
    
    def scroll_up(self, lines=3):
        """Scroll up by specified lines"""
        self._update_wrapped_cache()
        total_lines = sum(len(wrapped_lines) for _, _, _, wrapped_lines in self.wrapped_cache)
        max_scroll = max(0, total_lines - self.max_visible_lines)
        
        self.scroll_offset = min(self.scroll_offset + lines, max_scroll)
        if self.scroll_offset > 0:
            self.auto_scroll = False
    
    def scroll_down(self, lines=3):
        """Scroll down by specified lines"""
        self.scroll_offset = max(0, self.scroll_offset - lines)
        if self.scroll_offset == 0:
            self.auto_scroll = True
    
    def change_background(self):
        """Trigger background change"""
        if self.on_background_change:
            self.on_background_change()
            self.add_message("SYS", "Background module switched", "INFO")
    
    def change_spectrum(self):
        """Trigger spectrum style change"""
        if self.on_spectrum_change:
            self.on_spectrum_change()
    
    def toggle_camera(self):
        """Toggle camera (placeholder for now)"""
        self.add_message("CAM", "Camera toggle - not yet implemented", "INFO")
    
    def shutdown_system(self):
        """Shutdown the system"""
        if not self.shutdown_confirm:
            self.shutdown_confirm = True
            self.shutdown_time = time.time()
            self.add_message("PWR", "CONFIRM SHUTDOWN - Click again", "WARNING")
        else:
            if time.time() - self.shutdown_time < 5.0:
                self.add_message("PWR", "Initiating system halt sequence...", "WARNING")
                if self.on_shutdown:
                    self.on_shutdown()
                try:
                    import subprocess
                    subprocess.run(["sudo", "halt"], check=False)
                except Exception as e:
                    self.add_message("ERR", f"Shutdown failed: {e}", "ERROR")
            else:
                self.shutdown_confirm = True
                self.shutdown_time = time.time()
                self.add_message("PWR", "CONFIRM SHUTDOWN", "WARNING")
    
    def handle_click(self, pos):
        """Handle mouse clicks on buttons"""
        # Check top buttons
        for button in self.top_buttons:
            if button["rect"] and button["rect"].collidepoint(pos):
                if button["label"] == "CLEAR":
                    self.clear_messages()
                elif button["label"] == "BG":
                    self.change_background()
                elif button["label"] == "WAVE":
                    self.change_spectrum()
                elif button["label"] == "PWR-DN":
                    self.shutdown_system()
                return True
        
        # Check bottom buttons
        for button in self.bottom_buttons:
            if button["rect"] and button["rect"].collidepoint(pos):
                if button["label"] == "CAM":
                    self.toggle_camera()
                return True
        
        return False
    
    def handle_scroll_wheel(self, y):
        """Handle mouse wheel scrolling"""
        if y > 0:
            self.scroll_up(3)
        elif y < 0:
            self.scroll_down(3)
    
    def think(self):
        """Trigger thinking animation"""
        self.thinking = True
        self.thinking_time = time.time()
    
    def action(self):
        """Trigger action animation"""
        self.action_flash = 1.0
    
    def add_memory(self):
        """Trigger memory save animation"""
        self.memory_pulse = 1.0
    
    def update(self):
        """Update animations"""
        current_time = time.time()
        
        if self.thinking and current_time - self.thinking_time > 2.0:
            self.thinking = False
        
        if self.action_flash > 0:
            self.action_flash -= 0.05
            if self.action_flash < 0:
                self.action_flash = 0
        
        if self.memory_pulse > 0:
            self.memory_pulse -= 0.02
            if self.memory_pulse < 0:
                self.memory_pulse = 0
        
        if self.shutdown_confirm and current_time - self.shutdown_time > 5.0:
            self.shutdown_confirm = False
        
        self.scan_line = (self.scan_line + 2) % self.terminal_height
        self.status_blink = (self.status_blink + 0.1) % (3.14159 * 2)
    
    def _wrap_text(self, text: str, max_width: int) -> List[str]:
        """Wrap text to fit within max_width"""
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
    
    def _draw_tech_button(self, surface, rect, label, code, active=False, color_type=None):
        """Draw a technical-style button - SIMPLIFIED (no dots, no code text)"""
        # Main panel with inset effect
        if color_type == "warning":
            if self.shutdown_confirm:
                bg_color = (100, 30, 10, 220)
                border_color = (255, 80, 0, 255)
            else:
                bg_color = (50, 30, 20, 200)
                border_color = (180, 100, 40, 220)
        elif active:
            bg_color = (20, 60, 80, 220)
            border_color = (*self.primary_color, 255)
        else:
            bg_color = (*self.bg_panel, 200)
            border_color = (*self.border_color, 200)
        
        # Draw beveled panel
        pygame.draw.rect(surface, bg_color, rect)
        
        # Outer border
        pygame.draw.rect(surface, border_color, rect, 2)
        
        # Inner detail line
        inner_rect = rect.inflate(-4, -4)
        pygame.draw.rect(surface, (*self.accent_color, 150), inner_rect, 1)
        
        # Corner brackets
        bracket_size = 6
        bracket_color = border_color
        
        # Top-left bracket
        pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left + bracket_size, rect.top), 2)
        pygame.draw.line(surface, bracket_color, rect.topleft, (rect.left, rect.top + bracket_size), 2)
        
        # Top-right bracket
        pygame.draw.line(surface, bracket_color, rect.topright, (rect.right - bracket_size, rect.top), 2)
        pygame.draw.line(surface, bracket_color, (rect.right - 1, rect.top), (rect.right - 1, rect.top + bracket_size), 2)
        
        # Draw main label (centered, no offset)
        text_color = self.primary_color if active or color_type == "warning" else self.text_color
        text_surface = self.toolbar_font.render(label, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        surface.blit(text_surface, text_rect)
    
    def draw(self, surface: pygame.Surface):
        """Draw the high-tech terminal overlay"""
        import math
        
        self._update_wrapped_cache()
        self.overlay_surface.fill((0, 0, 0, 0))
        
        # === TOP TOOLBAR ===
        toolbar_rect = pygame.Rect(0, 0, self.width, self.toolbar_height)
        toolbar_bg = pygame.Surface((self.width, self.toolbar_height), pygame.SRCALPHA)
        toolbar_bg.fill((*self.bg_terminal, self.bg_alpha + 20))
        self.overlay_surface.blit(toolbar_bg, (0, 0))
        
        # Top toolbar border with glow
        pygame.draw.line(self.overlay_surface, (*self.border_color, 200), 
                        (0, self.toolbar_height - 1), (self.width, self.toolbar_height - 1), 2)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 100), 
                        (0, self.toolbar_height - 2), (self.width, self.toolbar_height - 2), 1)
        
        # Draw top buttons
        for button in self.top_buttons:
            if button["rect"]:
                self._draw_tech_button(self.overlay_surface, button["rect"], 
                                       button["label"], button["code"],
                                       button.get("active", False),
                                       button.get("color"))
        
        # === TERMINAL AREA ===
        terminal_rect = pygame.Rect(0, self.toolbar_height, self.width, self.terminal_height)
        terminal_bg = pygame.Surface((self.width, self.terminal_height), pygame.SRCALPHA)
        terminal_bg.fill((*self.bg_terminal, self.bg_alpha))
        self.overlay_surface.blit(terminal_bg, (0, self.toolbar_height))
        
        # Terminal border
        pygame.draw.rect(self.overlay_surface, (*self.border_color, 200), terminal_rect, 2)
        
        # Draw header bar with technical details
        header_y = self.toolbar_height + 8
        
        # Terminal ID
        terminal_id = "TERM-A1"
        id_surface = self.code_font.render(terminal_id, True, self.primary_color)
        self.overlay_surface.blit(id_surface, (25, header_y + 2))
        
        # Status text - MOVED FURTHER RIGHT
        status_text = "[PROCESSING]" if self.thinking else "[ACTIVE]"
        status_surface = self.label_font.render(status_text, True, self.label_color)
        self.overlay_surface.blit(status_surface, (120, header_y + 6))
        
        # System info on right
        msg_count = f"MSG: {len(self.messages):03d}"
        count_surface = self.label_font.render(msg_count, True, self.dim_text_color)
        self.overlay_surface.blit(count_surface, (self.width - 80, header_y + 6))
        
        # Horizontal divider
        line_y = header_y + 22
        pygame.draw.line(self.overlay_surface, (*self.border_color, 180), 
                        (10, line_y), (self.width - 10, line_y), 1)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 80), 
                        (10, line_y + 1), (self.width - 10, line_y + 1), 1)
        
        # === DRAW MESSAGES ===
        y_offset = line_y + 12
        start_y = y_offset
        
        all_lines = []
        reversed_cache = list(reversed(self.wrapped_cache))
        
        for key, value, msg_type, wrapped_lines in reversed_cache:
            for line_idx, line_text in enumerate(wrapped_lines):
                all_lines.append((key, value, msg_type, line_text, line_idx))
        
        total_lines = len(all_lines)
        visible_lines = all_lines[:self.max_visible_lines] if total_lines > self.max_visible_lines else all_lines
        
        # Calculate terminal drawing area for fade effect
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
                    
                    if user_part.upper() == "TARS":
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
                if key.upper() == "TARS":
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
        
        # Scan line effect
        if self.action_flash > 0:
            scan_alpha = int(self.action_flash * 60)
            scan_y = self.toolbar_height + self.scan_line
            pygame.draw.line(self.overlay_surface, (*self.primary_color, scan_alpha),
                           (5, scan_y), (self.width - 5, scan_y), 1)
        
        # === CORNER BRACKETS INSIDE TERMINAL (4 CORNERS) ===
        bracket_size = 12  # SMALLER
        bracket_thickness = 2
        bracket_color = (*self.border_color, 200)
        bracket_offset = 10
        
        term_left = bracket_offset
        term_right = self.width - bracket_offset
        term_top = self.toolbar_height + bracket_offset
        term_bottom = self.toolbar_height + self.terminal_height - bracket_offset
        
        # Top-left corner bracket
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_top), (term_left + bracket_size, term_top), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_top), (term_left, term_top + bracket_size), bracket_thickness)
        
        # Top-right corner bracket
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_top), (term_right - bracket_size, term_top), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_top), (term_right, term_top + bracket_size), bracket_thickness)
        
        # Bottom-left corner bracket
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_bottom), (term_left + bracket_size, term_bottom), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_left, term_bottom), (term_left, term_bottom - bracket_size), bracket_thickness)
        
        # Bottom-right corner bracket
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_bottom), (term_right - bracket_size, term_bottom), bracket_thickness)
        pygame.draw.line(self.overlay_surface, bracket_color,
                        (term_right, term_bottom), (term_right, term_bottom - bracket_size), bracket_thickness)
        
        # Fade gradient at bottom
        gradient_height = 60
        gradient_start_y = self.toolbar_height + self.terminal_height - gradient_height
        
        for i in range(gradient_height):
            alpha = int((i / gradient_height) * 30)
            pygame.draw.line(self.overlay_surface, (0, 0, 0, alpha),
                           (5, gradient_start_y + i), (self.width - 5, gradient_start_y + i), 1)
        
        # === BOTTOM TOOLBAR ===
        bottom_toolbar_y = self.toolbar_height + self.terminal_height
        bottom_toolbar_rect = pygame.Rect(0, bottom_toolbar_y, self.width, self.bottom_toolbar_height)
        bottom_toolbar_bg = pygame.Surface((self.width, self.bottom_toolbar_height), pygame.SRCALPHA)
        bottom_toolbar_bg.fill((*self.bg_terminal, self.bg_alpha + 20))
        self.overlay_surface.blit(bottom_toolbar_bg, (0, bottom_toolbar_y))
        
        # Bottom toolbar border
        pygame.draw.line(self.overlay_surface, (*self.border_color, 200), 
                        (0, bottom_toolbar_y), (self.width, bottom_toolbar_y), 2)
        pygame.draw.line(self.overlay_surface, (*self.accent_color, 100), 
                        (0, bottom_toolbar_y + 1), (self.width, bottom_toolbar_y + 1), 1)
        
        # Draw bottom buttons
        for button in self.bottom_buttons:
            if button["rect"]:
                self._draw_tech_button(self.overlay_surface, button["rect"], 
                                       button["label"], button["code"],
                                       button.get("active", False),
                                       button.get("color"))
        
        # Blit overlay to main surface
        surface.blit(self.overlay_surface, (0, 0))