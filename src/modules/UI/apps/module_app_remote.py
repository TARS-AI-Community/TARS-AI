"""
Remote Access App — full onboarding flow:
  1. Check WiFi → if offline, show network list + on-screen keyboard to connect
  2. Start Cloudflare tunnel
  3. Show QR code to open TARS web UI instantly
"""

import pygame
import threading
import time

# ── App states ────────────────────────────────────────────────────────────────
_S_CHECKING   = "checking"      # Checking WiFi status
_S_WIFI_LIST  = "wifi_list"     # Show available networks
_S_WIFI_PASS  = "wifi_pass"     # Password entry with on-screen keyboard
_S_WIFI_CONN  = "wifi_connecting"  # Connecting to WiFi
_S_TUNNEL_START = "tunnel_start"   # Starting tunnel
_S_HOTSPOT_START = "hotspot_start"  # Starting hotspot
_S_HOTSPOT    = "hotspot"        # Hotspot active — show connect info
_S_ACTIVE     = "active"        # QR code displayed (tunnel)
_S_ERROR      = "error"         # Error with retry
_S_IDLE       = "idle"          # Tunnel stopped


# ── On-screen keyboard layout ────────────────────────────────────────────────
_KB_ROWS_LOWER = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    ["^"] + list("zxcvbnm") + ["<"],
    ["space"],
]
_KB_ROWS_UPPER = [
    list("!@#$%^&*()"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    ["^"] + list("ZXCVBNM") + ["<"],
    ["space"],
]


class RemoteApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        # Colors
        self.bg       = (5, 15, 20)
        self.cyan     = (0, 255, 255)
        self.dim_cyan = (0, 120, 150)
        self.dark_cyan = (0, 60, 80)
        self.white    = (200, 210, 220)
        self.orange   = (255, 160, 0)
        self.red      = (255, 80, 80)
        self.green    = (0, 255, 120)
        self.key_bg   = (20, 40, 50)
        self.key_press = (0, 100, 120)

        # Fonts
        try:
            self.f_title  = pygame.font.Font("UI/mono.ttf", 24)
            self.f_medium = pygame.font.Font("UI/mono.ttf", 16)
            self.f_small  = pygame.font.Font("UI/mono.ttf", 12)
            self.f_key    = pygame.font.Font("UI/mono.ttf", 16)
            self.f_big    = pygame.font.Font("UI/mono.ttf", 18)
        except Exception:
            self.f_title  = pygame.font.SysFont("monospace", 24)
            self.f_medium = pygame.font.SysFont("monospace", 16)
            self.f_small  = pygame.font.SysFont("monospace", 12)
            self.f_key    = pygame.font.SysFont("monospace", 16)
            self.f_big    = pygame.font.SysFont("monospace", 18)

        # State
        self._state = _S_CHECKING
        self._frame = 0
        self._stop_event = threading.Event()

        # WiFi
        self._networks = []       # list of {ssid, signal, security, in_use}
        self._wifi_scroll = 0     # scroll offset for network list
        self._selected_ssid = ""
        self._selected_security = ""
        self._wifi_error = None
        self._wifi_status_msg = ""

        # Password input
        self._password = ""
        self._kb_shift = False
        self._show_password = False
        self._key_rects = []      # [(rect, key_label), ...] rebuilt each frame

        # Tunnel
        self._url = None
        self._error = None
        self._qr_surface = None
        self._stop_btn_rect = None

        # Touch targets (rebuilt each render)
        self._net_rects = []      # [(rect, network_dict), ...]
        self._btn_rects = {}      # name -> rect

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def reset(self):
        self._state = _S_CHECKING
        self._stop_event.clear()
        self._password = ""
        self._kb_shift = False
        self._wifi_scroll = 0
        threading.Thread(target=self._check_wifi, daemon=True).start()

    def cleanup(self):
        self._stop_event.set()

    def update(self):
        self._frame += 1

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return False

        pos = event.pos

        # Generic named buttons
        for name, rect in self._btn_rects.items():
            if rect.collidepoint(pos):
                self._on_button(name)
                return True

        # WiFi network list
        if self._state == _S_WIFI_LIST:
            for rect, net in self._net_rects:
                if rect.collidepoint(pos):
                    self._on_network_select(net)
                    return True

        # On-screen keyboard
        if self._state == _S_WIFI_PASS:
            for rect, key in self._key_rects:
                if rect.collidepoint(pos):
                    self._on_key_press(key)
                    return True

        return False

    def _on_button(self, name):
        if name == "stop_tunnel":
            self._do_stop_tunnel()
        elif name == "retry":
            self.reset()
        elif name == "rescan":
            self._state = _S_CHECKING
            threading.Thread(target=self._scan_wifi, daemon=True).start()
        elif name == "back_to_list":
            self._password = ""
            self._state = _S_WIFI_LIST
        elif name == "connect_wifi":
            self._do_connect_wifi()
        elif name == "toggle_show_pw":
            self._show_password = not self._show_password
        elif name == "scroll_up":
            self._wifi_scroll = max(0, self._wifi_scroll - 1)
        elif name == "scroll_down":
            self._wifi_scroll += 1
        elif name == "start_hotspot":
            self._state = _S_HOTSPOT_START
            threading.Thread(target=self._start_hotspot_bg, daemon=True).start()
        elif name == "stop_hotspot":
            self._do_stop_hotspot()

    def _on_network_select(self, net):
        self._selected_ssid = net["ssid"]
        self._selected_security = net.get("security", "")
        if self._selected_security == "open":
            # Open network — connect immediately
            self._password = ""
            self._do_connect_wifi()
        else:
            self._password = ""
            self._kb_shift = False
            self._state = _S_WIFI_PASS

    def _on_key_press(self, key):
        if key == "<":
            self._password = self._password[:-1]
        elif key == "^":
            self._kb_shift = not self._kb_shift
        elif key == "space":
            self._password += " "
        else:
            self._password += key
            # Auto-lowercase after typing a shifted char
            if self._kb_shift:
                self._kb_shift = False

    # ── Render dispatch ───────────────────────────────────────────────────────

    def render(self):
        self.screen.fill(self.bg)
        self._btn_rects.clear()
        self._net_rects.clear()
        self._key_rects.clear()

        # Title
        title = self.f_title.render("REMOTE ACCESS", True, self.cyan)
        tr = title.get_rect(centerx=self.width // 2, top=8)
        self.screen.blit(title, tr)
        line_y = tr.bottom + 4
        pygame.draw.line(self.screen, self.dark_cyan, (16, line_y), (self.width - 16, line_y), 1)
        content_top = line_y + 4

        if self._state == _S_CHECKING:
            self._render_status("Checking WiFi...", self.orange, content_top)
        elif self._state == _S_WIFI_LIST:
            self._render_wifi_list(content_top)
        elif self._state == _S_WIFI_PASS:
            self._render_password(content_top)
        elif self._state == _S_WIFI_CONN:
            self._render_status("Connecting to WiFi...", self.orange, content_top)
        elif self._state == _S_HOTSPOT_START:
            self._render_status("Starting hotspot...", self.orange, content_top)
        elif self._state == _S_HOTSPOT:
            self._render_hotspot(content_top)
        elif self._state == _S_TUNNEL_START:
            self._render_status("Starting tunnel...", self.orange, content_top)
        elif self._state == _S_ACTIVE:
            self._render_active(content_top)
        elif self._state == _S_ERROR:
            self._render_error(content_top)
        elif self._state == _S_IDLE:
            self._render_idle(content_top)

    # ── Status / spinner ──────────────────────────────────────────────────────

    def _render_status(self, text, color, top_y):
        dots = "." * ((self._frame // 15) % 4)
        surf = self.f_big.render(f"{text}{dots}", True, color)
        self.screen.blit(surf, surf.get_rect(centerx=self.width // 2, centery=self.height // 2))

    # ── WiFi network list ─────────────────────────────────────────────────────

    def _render_wifi_list(self, top_y):
        cx = self.width // 2
        pad = 16
        list_w = min(self.width - pad * 2, 400)  # max width, centered
        list_left = (self.width - list_w) // 2

        # Subtitle
        sub = self.f_medium.render("Select a WiFi network:", True, self.dim_cyan)
        self.screen.blit(sub, sub.get_rect(centerx=cx, top=top_y))

        # Rescan button (top-right)
        rescan_surf = self.f_medium.render("RESCAN", True, self.cyan)
        rr = rescan_surf.get_rect(right=list_left + list_w, top=top_y)
        self.screen.blit(rescan_surf, rr)
        self._btn_rects["rescan"] = rr.inflate(10, 6)

        header_bottom = top_y + sub.get_height() + 6

        # Hotspot button pinned above bottom toolbar
        bottom_margin = int(self.height * 0.06) + 6
        hotspot_h = 44
        hotspot_rect = pygame.Rect(list_left, self.height - hotspot_h - bottom_margin, list_w, hotspot_h)
        pygame.draw.rect(self.screen, self.orange, hotspot_rect, border_radius=6)
        hs_label = self.f_big.render("START HOTSPOT", True, self.bg)
        self.screen.blit(hs_label, hs_label.get_rect(center=hotspot_rect.center))
        self._btn_rects["start_hotspot"] = hotspot_rect

        # "or" hint above hotspot button
        or_surf = self.f_small.render("— or connect directly —", True, self.dark_cyan)
        self.screen.blit(or_surf, or_surf.get_rect(centerx=cx, bottom=hotspot_rect.top - 4))
        bottom_limit = hotspot_rect.top - or_surf.get_height() - 10

        if not self._networks:
            ns = self.f_big.render("No networks found", True, self.dark_cyan)
            self.screen.blit(ns, ns.get_rect(centerx=cx, centery=(header_bottom + bottom_limit) // 2))
            return

        # Calculate row layout
        row_h = 44
        available_h = bottom_limit - header_bottom
        visible_count = max(1, available_h // row_h)

        # Clamp scroll
        max_scroll = max(0, len(self._networks) - visible_count)
        self._wifi_scroll = min(self._wifi_scroll, max_scroll)

        visible = self._networks[self._wifi_scroll:self._wifi_scroll + visible_count]
        actual_count = len(visible)
        total_list_h = actual_count * row_h

        # Center the list block vertically in available space
        list_top = header_bottom + (available_h - total_list_h) // 2
        if list_top < header_bottom:
            list_top = header_bottom

        # Draw network rows
        for i, net in enumerate(visible):
            y = list_top + i * row_h
            row_rect = pygame.Rect(list_left, y, list_w, row_h - 4)

            # Highlight if in use
            bg_col = (0, 40, 50) if net.get("in_use") else (15, 25, 35)
            pygame.draw.rect(self.screen, bg_col, row_rect, border_radius=6)

            # SSID
            ssid_text = net["ssid"]
            if len(ssid_text) > 20:
                ssid_text = ssid_text[:18] + ".."
            ssid_surf = self.f_big.render(ssid_text, True, self.white)
            self.screen.blit(ssid_surf, (row_rect.x + 12, row_rect.centery - ssid_surf.get_height() // 2))

            # Signal bar
            signal = net.get("signal", 0)
            bar_w = 36
            bar_x = row_rect.right - bar_w - 10
            self._draw_signal_bars(bar_x, row_rect.y + 8, bar_w, row_h - 18, signal)

            # Security icon
            sec = net.get("security", "")
            if sec and sec != "open":
                lock = self.f_small.render("*", True, self.dim_cyan)
                self.screen.blit(lock, (bar_x - 16, row_rect.centery - lock.get_height() // 2))

            # In-use indicator
            if net.get("in_use"):
                check = self.f_medium.render(">>", True, self.green)
                self.screen.blit(check, (row_rect.x + 12 + ssid_surf.get_width() + 8, row_rect.centery - check.get_height() // 2))

            self._net_rects.append((row_rect, net))

        # Scroll indicators
        if self._wifi_scroll > 0:
            up_surf = self.f_medium.render("^ more", True, self.dim_cyan)
            ur = up_surf.get_rect(centerx=cx, bottom=list_top - 2)
            self.screen.blit(up_surf, ur)
            self._btn_rects["scroll_up"] = ur.inflate(40, 10)
        if self._wifi_scroll < max_scroll:
            dn_surf = self.f_medium.render("v more", True, self.dim_cyan)
            dr = dn_surf.get_rect(centerx=cx, top=list_top + total_list_h + 2)
            self.screen.blit(dn_surf, dr)
            self._btn_rects["scroll_down"] = dr.inflate(40, 10)

    def _draw_signal_bars(self, x, y, w, h, signal):
        """Draw 4 signal strength bars."""
        bar_count = 4
        bar_w = w // (bar_count * 2)
        gap = bar_w
        for i in range(bar_count):
            bar_h = int(h * (i + 1) / bar_count)
            bx = x + i * (bar_w + gap)
            by = y + h - bar_h
            threshold = (i + 1) * 25
            color = self.cyan if signal >= threshold else self.dark_cyan
            pygame.draw.rect(self.screen, color, (bx, by, bar_w, bar_h))

    # ── Password entry + on-screen keyboard ──────────────────────────────────

    def _render_password(self, top_y):
        cx = self.width // 2
        pad = 10

        # Calculate keyboard height first so we can pin it above the bottom toolbar
        rows = _KB_ROWS_UPPER if self._kb_shift else _KB_ROWS_LOWER
        row_count = len(rows)
        bottom_margin = int(self.height * 0.06) + 4  # clear the bottom toolbar
        key_h = min(40, (self.height * 2 // 5) // row_count - 2)
        kb_total_h = row_count * (key_h + 2)
        kb_top = self.height - kb_total_h - bottom_margin

        # Action buttons row just above keyboard
        btn_h = 36
        btn_gap = 6
        btn_y = kb_top - btn_h - btn_gap
        half_w = (self.width - pad * 3) // 2

        back_rect = pygame.Rect(pad, btn_y, half_w, btn_h)
        pygame.draw.rect(self.screen, self.dark_cyan, back_rect, border_radius=4)
        bs = self.f_big.render("BACK", True, self.white)
        self.screen.blit(bs, bs.get_rect(center=back_rect.center))
        self._btn_rects["back_to_list"] = back_rect

        conn_rect = pygame.Rect(pad * 2 + half_w, btn_y, half_w, btn_h)
        conn_color = self.cyan if self._password else self.dark_cyan
        pygame.draw.rect(self.screen, conn_color, conn_rect, border_radius=4)
        cs = self.f_big.render("CONNECT", True, self.bg)
        self.screen.blit(cs, cs.get_rect(center=conn_rect.center))
        if self._password:
            self._btn_rects["connect_wifi"] = conn_rect

        # Network name + password field centered in remaining upper area
        upper_h = btn_y - btn_gap - top_y
        field_h = 32

        # Network name
        ssid_surf = self.f_big.render(self._selected_ssid, True, self.cyan)
        total_content_h = ssid_surf.get_height() + 8 + field_h
        content_top = top_y + (upper_h - total_content_h) // 2
        if content_top < top_y:
            content_top = top_y

        self.screen.blit(ssid_surf, ssid_surf.get_rect(centerx=cx, top=content_top))

        # Password field
        field_y = content_top + ssid_surf.get_height() + 8
        field_rect = pygame.Rect(pad, field_y, self.width - pad * 2, field_h)
        pygame.draw.rect(self.screen, self.key_bg, field_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.dim_cyan, field_rect, 1, border_radius=4)

        if self._password:
            display = self._password if self._show_password else ("*" * len(self._password))
        else:
            display = "Password"
        pw_color = self.white if self._password else self.dark_cyan
        pw_surf = self.f_big.render(display, True, pw_color)
        # Clip to field width
        clip_w = field_rect.width - 50
        if pw_surf.get_width() > clip_w:
            crop_rect = pygame.Rect(pw_surf.get_width() - clip_w, 0, clip_w, pw_surf.get_height())
            self.screen.blit(pw_surf, (field_rect.x + 8, field_rect.centery - pw_surf.get_height() // 2), crop_rect)
        else:
            self.screen.blit(pw_surf, (field_rect.x + 8, field_rect.centery - pw_surf.get_height() // 2))

        # Cursor blink
        if (self._frame // 20) % 2 == 0:
            cursor_x = field_rect.x + 8 + min(pw_surf.get_width(), clip_w)
            pygame.draw.line(self.screen, self.cyan, (cursor_x, field_rect.y + 6),
                            (cursor_x, field_rect.bottom - 6), 2)

        # Show/hide toggle
        eye_text = "SHOW" if not self._show_password else "HIDE"
        eye_surf = self.f_medium.render(eye_text, True, self.dim_cyan)
        eye_rect = eye_surf.get_rect(right=field_rect.right - 6, centery=field_rect.centery)
        self.screen.blit(eye_surf, eye_rect)
        self._btn_rects["toggle_show_pw"] = eye_rect.inflate(10, 10)

        # On-screen keyboard pinned to bottom
        self._render_keyboard(kb_top)

    def _render_keyboard(self, top_y):
        """Draw the on-screen keyboard and populate _key_rects."""
        rows = _KB_ROWS_UPPER if self._kb_shift else _KB_ROWS_LOWER
        bottom_margin = int(self.height * 0.06) + 4  # clear the bottom toolbar
        available_h = self.height - top_y - bottom_margin
        row_count = len(rows)
        key_h = min(40, available_h // row_count - 2)
        pad = 3

        for ri, row in enumerate(rows):
            y = top_y + ri * (key_h + 2)
            total_keys = len(row)

            # Space bar gets full width
            if row == ["space"]:
                key_rect = pygame.Rect(pad, y, self.width - pad * 2, key_h)
                pygame.draw.rect(self.screen, self.key_bg, key_rect, border_radius=3)
                label = self.f_key.render("SPACE", True, self.dim_cyan)
                self.screen.blit(label, label.get_rect(center=key_rect.center))
                self._key_rects.append((key_rect, " "))
                continue

            key_w = (self.width - pad * 2) // total_keys - 2
            row_width = total_keys * (key_w + 2) - 2
            start_x = (self.width - row_width) // 2

            for ki, key in enumerate(row):
                kx = start_x + ki * (key_w + 2)
                key_rect = pygame.Rect(kx, y, key_w, key_h)

                # Special key colors
                if key == "<":
                    bg = self.red
                    display = "<-"
                    text_col = self.bg
                elif key == "^":
                    bg = self.cyan if self._kb_shift else self.dark_cyan
                    display = "Aa"
                    text_col = self.bg if self._kb_shift else self.white
                else:
                    bg = self.key_bg
                    display = key
                    text_col = self.white

                pygame.draw.rect(self.screen, bg, key_rect, border_radius=3)
                label = self.f_key.render(display, True, text_col)
                self.screen.blit(label, label.get_rect(center=key_rect.center))
                self._key_rects.append((key_rect, key))

    # ── Hotspot active ─────────────────────────────────────────────────────────

    def _render_hotspot(self, top_y):
        """Show hotspot info: SSID, password, QR to local web UI, stop button."""
        cx = self.width // 2

        # Info block — use WiFiManager constants
        from modules.module_wifi import WiFiManager
        info_y = top_y + 8
        ssid_surf = self.f_big.render(f"WiFi: {WiFiManager.HOTSPOT_SSID}", True, self.cyan)
        self.screen.blit(ssid_surf, ssid_surf.get_rect(centerx=cx, top=info_y))

        pw_surf = self.f_big.render(f"Pass: {WiFiManager.HOTSPOT_PASSWORD}", True, self.white)
        self.screen.blit(pw_surf, pw_surf.get_rect(centerx=cx, top=info_y + ssid_surf.get_height() + 4))

        qr_top = info_y + ssid_surf.get_height() + pw_surf.get_height() + 16

        # QR code for local web UI
        btn_h = 40
        btn_gap = 8
        hint_h = 16
        available_h = self.height - qr_top - btn_h - btn_gap - hint_h - 8
        available_w = self.width - 16
        qr_size = min(available_h, available_w)
        if qr_size < 50:
            qr_size = 50

        if self._qr_surface and qr_size > 0:
            scaled = pygame.transform.smoothscale(self._qr_surface, (qr_size, qr_size))
            qr_rect = scaled.get_rect(centerx=cx, top=qr_top)
            self.screen.blit(scaled, qr_rect)
            btn_top = qr_rect.bottom + btn_gap
        else:
            btn_top = qr_top + btn_gap

        # Stop hotspot button
        btn_w = max(self.width // 2, 160)
        btn_rect = pygame.Rect(cx - btn_w // 2, btn_top, btn_w, btn_h)
        pygame.draw.rect(self.screen, self.red, btn_rect, border_radius=6)
        label = self.f_big.render("STOP HOTSPOT", True, self.bg)
        self.screen.blit(label, label.get_rect(center=btn_rect.center))
        self._btn_rects["stop_hotspot"] = btn_rect

        # Hint
        hint = self.f_small.render("Connect phone to WiFi, then scan QR", True, self.dim_cyan)
        self.screen.blit(hint, hint.get_rect(centerx=cx, bottom=self.height - int(self.height * 0.06) - 4))

    # ── Active / QR code ──────────────────────────────────────────────────────

    def _render_active(self, top_y):
        cx = self.width // 2

        btn_h = 44
        btn_gap = 8
        url_h = 16
        url_pad = 4

        available_h = self.height - top_y - btn_h - btn_gap - url_h - url_pad
        available_w = self.width - 16
        qr_size = min(available_h, available_w)
        if qr_size < 50:
            qr_size = 50

        group_h = qr_size + btn_gap + btn_h
        group_top = top_y + (self.height - top_y - url_h - url_pad - group_h) // 2
        if group_top < top_y:
            group_top = top_y

        if self._qr_surface and qr_size > 0:
            scaled = pygame.transform.smoothscale(self._qr_surface, (qr_size, qr_size))
            qr_rect = scaled.get_rect(centerx=cx, top=group_top)
            self.screen.blit(scaled, qr_rect)
            btn_top = qr_rect.bottom + btn_gap
        else:
            btn_top = group_top + btn_gap

        # Stop button
        btn_w = max(self.width // 2, 160)
        btn_rect = pygame.Rect(cx - btn_w // 2, btn_top, btn_w, btn_h)
        self._btn_rects["stop_tunnel"] = btn_rect
        pygame.draw.rect(self.screen, self.red, btn_rect, border_radius=6)
        label = self.f_big.render("STOP TUNNEL", True, self.bg)
        self.screen.blit(label, label.get_rect(center=btn_rect.center))

        # URL
        if self._url:
            display_url = self._url.replace("https://", "")
            url_bottom = self.height - int(self.height * 0.06) - 4
            us = self.f_small.render(display_url, True, self.dim_cyan)
            ur = us.get_rect(centerx=cx, bottom=url_bottom)
            if ur.width > self.width - 16:
                while ur.width > self.width - 24 and len(display_url) > 10:
                    display_url = display_url[:-1]
                us = self.f_small.render(display_url + "..", True, self.dim_cyan)
                ur = us.get_rect(centerx=cx, bottom=url_bottom)
            self.screen.blit(us, ur)

    # ── Error ─────────────────────────────────────────────────────────────────

    def _render_error(self, top_y):
        cx = self.width // 2

        es = self.f_big.render("Error", True, self.red)
        er = es.get_rect(centerx=cx, top=top_y + 20)
        self.screen.blit(es, er)

        if self._error:
            words = str(self._error)[:200].split()
            lines, cur = [], ""
            for w in words:
                test = f"{cur} {w}".strip()
                if self.f_small.size(test)[0] > self.width - 40:
                    lines.append(cur)
                    cur = w
                else:
                    cur = test
            if cur:
                lines.append(cur)
            for i, line in enumerate(lines[:4]):
                ls = self.f_small.render(line, True, self.white)
                self.screen.blit(ls, ls.get_rect(centerx=cx, top=er.bottom + 12 + i * 16))

        # Retry button
        btn_rect = pygame.Rect(cx - 80, self.height - int(self.height * 0.06) - 52, 160, 40)
        pygame.draw.rect(self.screen, self.cyan, btn_rect, border_radius=6)
        rs = self.f_big.render("RETRY", True, self.bg)
        self.screen.blit(rs, rs.get_rect(center=btn_rect.center))
        self._btn_rects["retry"] = btn_rect

    # ── Idle (tunnel stopped) ─────────────────────────────────────────────────

    def _render_idle(self, top_y):
        s = self.f_big.render("Tunnel stopped", True, self.dim_cyan)
        self.screen.blit(s, s.get_rect(centerx=self.width // 2, centery=self.height // 2 - 20))

        btn_rect = pygame.Rect(self.width // 2 - 80, self.height // 2 + 20, 160, 40)
        pygame.draw.rect(self.screen, self.cyan, btn_rect, border_radius=6)
        rs = self.f_big.render("RESTART", True, self.bg)
        self.screen.blit(rs, rs.get_rect(center=btn_rect.center))
        self._btn_rects["retry"] = btn_rect

    # ── Background work ──────────────────────────────────────────────────────

    def _log(self, msg):
        try:
            from modules.module_messageQue import queue_message
            queue_message(f"REMOTE APP: {msg}")
        except Exception:
            print(f"REMOTE APP: {msg}")

    def _get_wifi_manager(self):
        """Get the shared WiFiManager singleton."""
        from modules.module_wifi import _get_manager
        return _get_manager()

    def _get_hotspot_url(self):
        """Build the local web UI URL using WiFiManager constants and config port."""
        from modules.module_wifi import WiFiManager
        port = 80
        try:
            from modules.module_config import load_config
            cfg = load_config()
            port = cfg['ACCESS'].get('webui_port', 80)
        except Exception:
            pass
        ip = WiFiManager.HOTSPOT_IP
        return f"http://{ip}:{port}" if port != 80 else f"http://{ip}"

    def _check_wifi(self):
        """Check if we're online. If yes, go straight to tunnel. If not, scan."""
        try:
            mgr = self._get_wifi_manager()
            status = mgr.get_status()
            self._log(f"WiFi status: {status}")
            if status.get("mode") == "client" and status.get("ip"):
                self._state = _S_TUNNEL_START
                self._start_tunnel_bg()
                return
            elif status.get("mode") == "hotspot":
                local_url = self._get_hotspot_url()
                self._url = local_url
                self._generate_qr(local_url)
                self._state = _S_HOTSPOT
                self._log(f"Already in hotspot mode, web UI at {local_url}")
                return
        except Exception as e:
            self._log(f"WiFi check failed: {e}")

        self._scan_wifi()

    def _scan_wifi(self):
        """Scan for WiFi networks."""
        self._wifi_status_msg = "Scanning..."
        try:
            mgr = self._get_wifi_manager()
            # scan_networks already deduplicates and sorts by signal
            self._networks = mgr.scan_networks(rescan=True)
            self._wifi_scroll = 0
            self._log(f"Found {len(self._networks)} networks")
        except Exception as e:
            self._networks = []
            self._log(f"Scan failed: {e}")

        self._state = _S_WIFI_LIST

    def _do_connect_wifi(self):
        """Connect to selected WiFi network in background."""
        self._state = _S_WIFI_CONN
        threading.Thread(target=self._connect_wifi_bg, daemon=True).start()

    def _connect_wifi_bg(self):
        ssid = self._selected_ssid
        pw = self._password
        self._log(f"Connecting to '{ssid}'...")

        try:
            mgr = self._get_wifi_manager()
            ok = mgr.connect(ssid, pw)
            if ok:
                self._log(f"Connected to '{ssid}'")
                time.sleep(2)
                self._state = _S_TUNNEL_START
                self._start_tunnel_bg()
            else:
                self._error = f"Failed to connect to '{ssid}'. Check password."
                self._state = _S_ERROR
                self._log(self._error)
        except Exception as e:
            self._error = f"WiFi error: {e}"
            self._state = _S_ERROR
            self._log(self._error)

    def _start_tunnel_bg(self):
        """Start the Cloudflare tunnel."""
        try:
            from modules.module_chatui import (
                _get_tunnel_status, _start_tunnel,
                _cloudflared_bin, _install_cloudflared,
            )
        except ImportError as e:
            self._error = f"ChatUI not available: {e}"
            self._state = _S_ERROR
            return

        # Already active?
        status = _get_tunnel_status()
        if status.get("state") == "active" and status.get("url"):
            self._url = status["url"]
            self._log(f"Tunnel already active: {self._url}")
            self._generate_qr(self._url)
            self._state = _S_ACTIVE
            return

        # Install cloudflared if needed
        if not _cloudflared_bin():
            self._log("Installing cloudflared...")
            ok, err = _install_cloudflared()
            if not ok:
                self._error = f"Install failed: {err}"
                self._state = _S_ERROR
                return

        self._log("Starting tunnel...")
        ok, result = _start_tunnel()

        if self._stop_event.is_set():
            return

        if ok:
            self._url = result
            self._log(f"Tunnel active: {self._url}")
            self._generate_qr(self._url)
            self._state = _S_ACTIVE
        else:
            self._error = f"Tunnel failed: {result}"
            self._state = _S_ERROR
            self._log(self._error)

    def _start_hotspot_bg(self):
        """Start WiFi hotspot in background, then show QR to local web UI."""
        self._log("Starting hotspot...")
        try:
            mgr = self._get_wifi_manager()
            ok = mgr.start_hotspot()
            if ok:
                time.sleep(2)  # Wait for AP to be ready
                local_url = self._get_hotspot_url()
                self._url = local_url
                self._generate_qr(local_url)
                self._state = _S_HOTSPOT
                self._log(f"Hotspot active, web UI at {local_url}")
            else:
                self._error = "Failed to start hotspot"
                self._state = _S_ERROR
                self._log(self._error)
        except Exception as e:
            self._error = f"Hotspot error: {e}"
            self._state = _S_ERROR
            self._log(self._error)

    def _do_stop_hotspot(self):
        """Stop the hotspot and go back to WiFi list."""
        try:
            self._get_wifi_manager().stop_hotspot()
        except Exception:
            pass
        self._url = None
        self._qr_surface = None
        self._log("Hotspot stopped by user")
        # Go back to WiFi scan
        self._state = _S_CHECKING
        threading.Thread(target=self._scan_wifi, daemon=True).start()

    def _do_stop_tunnel(self):
        try:
            from modules.module_chatui import _stop_tunnel
            _stop_tunnel()
        except Exception:
            pass
        self._state = _S_IDLE
        self._url = None
        self._qr_surface = None
        self._log("Tunnel stopped by user")

    def _generate_qr(self, url):
        try:
            import qrcode
        except ImportError:
            return
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#00ffff", back_color="#05141a")
        img_rgb = img.convert("RGB")
        self._qr_surface = pygame.image.fromstring(img_rgb.tobytes(), img_rgb.size, "RGB")
