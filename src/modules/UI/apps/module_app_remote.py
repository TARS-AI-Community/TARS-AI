"""
Remote Access App — auto-starts Cloudflare tunnel and shows a QR code on screen.

Scan the QR code with your phone to open the TARS web UI instantly.
No IP addresses to remember, no login required.
"""

import pygame
import threading
import time

# ── State flags (set by tunnel polling thread) ────────────────────────────────
_STATE_IDLE = "idle"
_STATE_STARTING = "starting"
_STATE_ACTIVE = "active"
_STATE_ERROR = "error"


class RemoteApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        # Colors (match TARS UI theme)
        self.bg_color = (5, 15, 20)
        self.cyan = (0, 255, 255)
        self.dim_cyan = (0, 120, 150)
        self.dark_cyan = (0, 60, 80)
        self.white = (200, 210, 220)
        self.orange = (255, 160, 0)
        self.red = (255, 80, 80)
        self.green = (0, 255, 120)

        # Fonts
        try:
            self.font_title = pygame.font.Font("UI/mono.ttf", 28)
            self.font_url = pygame.font.Font("UI/mono.ttf", 14)
            self.font_status = pygame.font.Font("UI/mono.ttf", 18)
            self.font_hint = pygame.font.Font("UI/mono.ttf", 12)
        except Exception:
            self.font_title = pygame.font.SysFont("monospace", 28)
            self.font_url = pygame.font.SysFont("monospace", 14)
            self.font_status = pygame.font.SysFont("monospace", 18)
            self.font_hint = pygame.font.SysFont("monospace", 12)

        # Tunnel state
        self._state = _STATE_IDLE
        self._url = None
        self._error = None
        self._qr_surface = None
        self._poll_thread = None
        self._stop_event = threading.Event()
        self._spinner_frame = 0

    def reset(self):
        """Called on launch — kick off the tunnel."""
        self._state = _STATE_STARTING
        self._url = None
        self._error = None
        self._qr_surface = None
        self._stop_event.clear()

        # Start tunnel via the existing API
        threading.Thread(target=self._start_and_poll, daemon=True).start()

    def update(self):
        self._spinner_frame += 1

    def render(self):
        self.screen.fill(self.bg_color)

        # Title
        title_surf = self.font_title.render("REMOTE ACCESS", True, self.cyan)
        title_rect = title_surf.get_rect(centerx=self.width // 2, top=12)
        self.screen.blit(title_surf, title_rect)

        # Separator line
        line_y = title_rect.bottom + 8
        pygame.draw.line(self.screen, self.dark_cyan, (20, line_y), (self.width - 20, line_y), 1)

        if self._state == _STATE_STARTING:
            self._render_starting(line_y + 20)
        elif self._state == _STATE_ACTIVE:
            self._render_active(line_y + 10)
        elif self._state == _STATE_ERROR:
            self._render_error(line_y + 20)
        else:
            self._render_idle(line_y + 20)

    def _render_starting(self, top_y):
        """Show spinner while tunnel is coming up."""
        dots = "." * ((self._spinner_frame // 15) % 4)
        text = f"Starting tunnel{dots}"
        surf = self.font_status.render(text, True, self.orange)
        rect = surf.get_rect(centerx=self.width // 2, centery=self.height // 2)
        self.screen.blit(surf, rect)

        hint = self.font_hint.render("Installing cloudflared if needed...", True, self.dark_cyan)
        hint_rect = hint.get_rect(centerx=self.width // 2, top=rect.bottom + 16)
        self.screen.blit(hint, hint_rect)

    def _render_active(self, top_y):
        """Show QR code centered and as large as possible, with URL below."""
        cx = self.width // 2

        # Reserve space: URL line (~20px) + hint line (~16px) + padding
        bottom_text_h = 44
        available_h = self.height - top_y - bottom_text_h
        available_w = self.width - 16  # 8px padding each side
        qr_size = min(available_h, available_w)

        if self._qr_surface and qr_size > 0:
            scaled_qr = pygame.transform.smoothscale(self._qr_surface, (qr_size, qr_size))
            # Center vertically in the available space (between top_y and bottom text)
            qr_y = top_y + (available_h - qr_size) // 2
            qr_rect = scaled_qr.get_rect(centerx=cx, top=qr_y)
            self.screen.blit(scaled_qr, qr_rect)

        # URL text at bottom
        if self._url:
            display_url = self._url.replace("https://", "")
            url_surf = self.font_url.render(display_url, True, self.white)
            url_rect = url_surf.get_rect(centerx=cx, bottom=self.height - 20)
            # Truncate if too wide
            if url_rect.width > self.width - 20:
                while url_rect.width > self.width - 30 and len(display_url) > 10:
                    display_url = display_url[:-1]
                url_surf = self.font_url.render(display_url + "...", True, self.white)
                url_rect = url_surf.get_rect(centerx=cx, bottom=self.height - 20)
            self.screen.blit(url_surf, url_rect)

        # Hint at very bottom
        hint = self.font_hint.render("Scan to open TARS", True, self.dim_cyan)
        hint_rect = hint.get_rect(centerx=cx, bottom=self.height - 4)
        self.screen.blit(hint, hint_rect)

    def _render_error(self, top_y):
        """Show error state."""
        err_surf = self.font_status.render("Tunnel Error", True, self.red)
        err_rect = err_surf.get_rect(centerx=self.width // 2, top=top_y)
        self.screen.blit(err_surf, err_rect)

        if self._error:
            # Word-wrap error message
            words = str(self._error)[:200].split()
            lines = []
            current = ""
            for w in words:
                test = f"{current} {w}".strip()
                if self.font_hint.size(test)[0] > self.width - 40:
                    lines.append(current)
                    current = w
                else:
                    current = test
            if current:
                lines.append(current)

            for i, line in enumerate(lines[:4]):
                line_surf = self.font_hint.render(line, True, self.white)
                line_rect = line_surf.get_rect(centerx=self.width // 2, top=err_rect.bottom + 16 + i * 18)
                self.screen.blit(line_surf, line_rect)

    def _render_idle(self, top_y):
        """Show idle state (shouldn't normally be seen)."""
        surf = self.font_status.render("Ready", True, self.dim_cyan)
        rect = surf.get_rect(centerx=self.width // 2, centery=self.height // 2)
        self.screen.blit(surf, rect)

    def _start_and_poll(self):
        """Background thread: start tunnel by calling chatui functions directly.

        We import the tunnel functions from module_chatui instead of going
        through HTTP — avoids lock contention where _start_tunnel holds
        _tunnel_lock for up to 30s and the status poll would block.
        """
        try:
            from modules.module_messageQue import queue_message
        except Exception:
            queue_message = print

        try:
            from modules.module_chatui import (
                _get_tunnel_status, _start_tunnel,
                _cloudflared_bin, _install_cloudflared,
            )
        except ImportError as e:
            self._error = f"ChatUI module not available: {e}"
            self._state = _STATE_ERROR
            queue_message(f"REMOTE APP: {self._error}")
            return

        # Check if tunnel is already active
        status = _get_tunnel_status()
        if status.get('state') == 'active' and status.get('url'):
            self._url = status['url']
            queue_message(f"REMOTE APP: Tunnel already active: {self._url}")
            self._generate_qr(self._url)
            self._state = _STATE_ACTIVE
            return

        # Install cloudflared if needed
        if not _cloudflared_bin():
            queue_message("REMOTE APP: Installing cloudflared...")
            ok, err = _install_cloudflared()
            if not ok:
                self._error = f"Failed to install cloudflared: {err}"
                self._state = _STATE_ERROR
                queue_message(f"REMOTE APP: {self._error}")
                return

        # Start the tunnel (this blocks until URL is found or 30s timeout)
        queue_message("REMOTE APP: Starting tunnel...")
        ok, result = _start_tunnel()

        if self._stop_event.is_set():
            return

        if ok:
            self._url = result
            queue_message(f"REMOTE APP: Tunnel active: {self._url}")
            self._generate_qr(self._url)
            self._state = _STATE_ACTIVE
        else:
            self._error = result
            self._state = _STATE_ERROR
            queue_message(f"REMOTE APP: Tunnel failed: {self._error}")

    def _generate_qr(self, url):
        """Generate a QR code as a pygame surface."""
        try:
            import qrcode
        except ImportError:
            return

        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#00ffff", back_color="#05141a")

        # Convert PIL image to pygame surface
        img_rgb = img.convert("RGB")
        raw = img_rgb.tobytes()
        size = img_rgb.size
        self._qr_surface = pygame.image.fromstring(raw, size, "RGB")

    def cleanup(self):
        """Called when app is closed."""
        self._stop_event.set()
        # Note: we do NOT stop the tunnel here — user may want it to stay up
        # They can stop it from the web UI if needed
