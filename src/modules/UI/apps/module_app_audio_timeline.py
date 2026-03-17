"""
Audio Timeline App — Real-time audio visualization for TARS display.

Self-contained: hooks directly into the shared mic AudioHub, analyzes
audio in-place (RMS, labeling), and renders the timeline.
"""

import pygame
import time
import threading
import collections
import numpy as np

# ── Colors ────────────────────────────────────────────────────────────────────
BG         = (4, 6, 12)
PANEL      = (10, 12, 20)
BORDER     = (22, 28, 48)
GRID       = (16, 20, 35)
TEXT       = (190, 195, 210)
DIM        = (55, 60, 80)
ACCENT     = (0, 200, 230)

SILENCE    = (16, 18, 32)
SPEECH     = (40, 210, 60)
SPEECH_HI  = (80, 255, 100)
TTS        = (110, 65, 250)
TTS_HI     = (150, 110, 255)
NOISE      = (240, 160, 25)
NOISE_HI   = (255, 200, 60)
WAKE       = (0, 230, 255)
BARGEIN    = (255, 55, 45)

LABEL_COLOR = {
    'silence': SILENCE, 'speech': SPEECH, 'tts_playing': TTS,
    'noise': NOISE, 'wake': WAKE,
}
LABEL_COLOR_HI = {
    'speech': SPEECH_HI, 'tts_playing': TTS_HI, 'noise': NOISE_HI,
}
STATE_COLOR = {
    'STANDBY': DIM, 'LISTENING': SPEECH, 'THINKING': NOISE,
    'TALKING': TTS, 'BOOTING': ACCENT,
}

VIEW_SECONDS = 15

# Audio analysis
_HOP_MS = 50
_RMS_SPEECH_THRESHOLD = 0.015
_RMS_NOISE_FLOOR = 0.005
_SPEECH_HOLD_CHUNKS = 6


class AudioTimelineApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        try:
            self.font = pygame.font.Font("UI/mono.ttf", 12)
            self.font_sm = pygame.font.Font("UI/mono.ttf", 10)
            self.font_lg = pygame.font.Font("UI/mono.ttf", 15)
            self.font_xl = pygame.font.Font("UI/mono.ttf", 20)
        except Exception:
            self.font = pygame.font.SysFont("monospace", 12)
            self.font_sm = pygame.font.SysFont("monospace", 10)
            self.font_lg = pygame.font.SysFont("monospace", 15)
            self.font_xl = pygame.font.SysFont("monospace", 20)

        # Data
        self._segments = []
        self._wake_times = []
        self._bargein_times = []
        self._lock = threading.Lock()
        self._max = 2000

        # Stats
        self._speech_n = 0
        self._tts_n = 0
        self._wake_n = 0
        self._bargein_n = 0
        self._last_label = 'silence'
        self._prev_state = 'STANDBY'
        self._cur_state = 'STANDBY'
        self._cur_rms = 0.0
        self._t0 = time.time()

        # Audio analysis state
        self._mic_rid = None
        self._running = False
        self._speech_hold = 0
        self._noise_floor = _RMS_NOISE_FLOOR
        self._noise_samples = collections.deque(maxlen=200)
        self._start_time = 0.0
        self._accum = []
        self._accum_frames = 0
        self._hop_frames = 0

        # Layout
        pad = 6
        toolbar = int(height * 0.06) + 4
        x = pad
        w = width - pad * 2
        info_h = 22 + 6 + 18
        self._chart_rect = (x, pad, w, height - toolbar - info_h - pad * 2 - 4)
        legend_y = pad + self._chart_rect[3] + 8
        self._legend_y = legend_y
        self._counter_y = legend_y + 24
        self._x = x
        self._w = w
        self._legend_items = [
            ("You", SPEECH), ("TARS", TTS), ("Noise", NOISE),
            ("Wake", WAKE), ("Barge-in", BARGEIN),
        ]

        # Pre-render bar gradient textures (column strips, stretched per bar)
        self._bar_gradients = {}
        for label, base in LABEL_COLOR.items():
            hi = LABEL_COLOR_HI.get(label, base)
            if base == SILENCE:
                continue
            grad = pygame.Surface((1, 64), pygame.SRCALPHA)
            for gy in range(64):
                frac = gy / 63.0  # 0=top(bright), 1=bottom(dark)
                r = int(hi[0] + (base[0] - hi[0]) * frac)
                g = int(hi[1] + (base[1] - hi[1]) * frac)
                b = int(hi[2] + (base[2] - hi[2]) * frac)
                grad.set_at((0, gy), (r, g, b, 255))
            self._bar_gradients[label] = grad

        # Pre-render glow strips
        self._glow_cache = {}
        for label, base in LABEL_COLOR.items():
            if base == SILENCE:
                continue
            glow = pygame.Surface((1, 32), pygame.SRCALPHA)
            for gy in range(32):
                a = int(40 * (1.0 - gy / 31.0))
                glow.set_at((0, gy), (*base, a))
            self._glow_cache[label] = glow

        # Baseline glow surface (horizontal, cached)
        self._baseline_glow = pygame.Surface((w, 8), pygame.SRCALPHA)
        for gy in range(8):
            a = int(30 * (1.0 - gy / 7.0))
            pygame.draw.line(self._baseline_glow, (0, 200, 230, a), (0, gy), (w, gy))

    def reset(self):
        self._start_audio()

    def cleanup(self):
        self._stop_audio()

    def update(self):
        pass

    # ── Audio hookup ──────────────────────────────────────────────────────

    def _start_audio(self):
        if self._running:
            return
        try:
            from modules.module_mic import _hub, get_native_rate
            rate = get_native_rate()
            self._hop_frames = int(rate * _HOP_MS / 1000)
            self._start_time = time.monotonic()
            self._running = True
            self._mic_rid = _hub.register_callback(self._on_audio)
        except Exception as e:
            print(f"[AudioTimeline] Mic hookup failed: {e}")

    def _stop_audio(self):
        self._running = False
        if self._mic_rid is not None:
            try:
                from modules.module_mic import _hub
                _hub.unregister_callback(self._mic_rid)
            except Exception:
                pass
            self._mic_rid = None

    def _on_audio(self, indata, frames, time_info, status):
        if not self._running:
            return
        chunk = indata[:, 0] if indata.ndim > 1 else indata.ravel()
        self._accum.append(chunk)
        self._accum_frames += len(chunk)
        while self._accum_frames >= self._hop_frames:
            all_audio = np.concatenate(self._accum)
            hop = all_audio[:self._hop_frames]
            remaining = all_audio[self._hop_frames:]
            self._accum = [remaining] if len(remaining) > 0 else []
            self._accum_frames = len(remaining) if len(remaining) > 0 else 0
            self._analyze(hop)

    def _analyze(self, audio):
        now = time.monotonic() - self._start_time
        rms = float(np.sqrt(np.mean(audio ** 2)))

        self._noise_samples.append(rms)
        if len(self._noise_samples) >= 50:
            s = sorted(self._noise_samples)
            self._noise_floor = max(_RMS_NOISE_FLOOR, s[len(s) // 5])

        tars_state = "unknown"
        try:
            from modules.module_state import get_tars_state
            tars_state = get_tars_state().value
        except Exception:
            pass

        tts_active = False
        try:
            from modules.module_tts import is_tts_playing
            tts_active = is_tts_playing()
        except Exception:
            pass

        speech_threshold = max(_RMS_SPEECH_THRESHOLD, self._noise_floor * 3.0)
        if tts_active:
            label = 'tts_playing'
            self._speech_hold = 0
        elif rms > speech_threshold:
            label = 'speech'
            self._speech_hold = _SPEECH_HOLD_CHUNKS
        elif self._speech_hold > 0:
            self._speech_hold -= 1
            label = 'speech'
        elif rms > self._noise_floor * 1.5:
            label = 'noise'
        else:
            label = 'silence'

        seg = {
            't': round(now, 3), 'dur': _HOP_MS, 'label': label,
            'rms': round(rms, 4), 'state': tars_state,
            'thr': round(speech_threshold, 5), 'nf': round(self._noise_floor, 5),
        }

        with self._lock:
            if label == 'speech' and self._last_label != 'speech':
                self._speech_n += 1
            if label == 'tts_playing' and self._last_label != 'tts_playing':
                self._tts_n += 1
            self._last_label = label

            if tars_state != self._prev_state:
                if self._prev_state == 'STANDBY' and tars_state == 'LISTENING':
                    self._wake_times.append(seg['t'])
                    self._wake_n += 1
                    if len(self._wake_times) > 200:
                        self._wake_times = self._wake_times[-100:]
                if self._prev_state == 'TALKING' and tars_state == 'LISTENING':
                    self._bargein_times.append(seg['t'])
                    self._bargein_n += 1
                    if len(self._bargein_times) > 200:
                        self._bargein_times = self._bargein_times[-100:]
                self._prev_state = tars_state

            self._cur_state = tars_state
            self._cur_rms = rms
            self._segments.append(seg)
            if len(self._segments) > self._max:
                self._segments = self._segments[-1500:]

    # ── Rendering ─────────────────────────────────────────────────────────

    def render(self):
        self.screen.fill(BG)

        with self._lock:
            segs = list(self._segments)
            wakes = list(self._wake_times)
            bargeins = list(self._bargein_times)

        if not segs:
            msg = self.font_lg.render("Waiting for audio...", True, DIM)
            self.screen.blit(msg, (self.width // 2 - msg.get_width() // 2,
                                    self.height // 2 - msg.get_height() // 2))
            return

        latest = segs[-1]['t']
        ws = latest - VIEW_SECONDS
        vis = [s for s in segs if s['t'] >= ws]
        if not vis:
            return

        self._draw_chart(vis, ws, wakes, bargeins)
        self._draw_legend()
        self._draw_counters()

    # ── Chart ─────────────────────────────────────────────────────────────

    _RMS_MAX = 0.06

    def _rms_to_px(self, rms, max_bar):
        return max(0, int(min(1.0, rms / self._RMS_MAX) * max_bar))

    def _draw_chart(self, vis, ws, wakes, bargeins):
        cx, cy, cw, ch = self._chart_rect
        time_margin = 14
        label_margin = 38
        baseline = cy + ch - time_margin
        max_bar = ch - time_margin - 6
        cl = cx + label_margin  # chart left edge
        cwr = cw - label_margin  # chart draw width

        # ── Background panel ──────────────────────────────────────────
        pygame.draw.rect(self.screen, PANEL, (cx, cy, cw, ch), border_radius=6)

        # ── RMS scale (Y axis) ────────────────────────────────────────
        for rms_val in [0.005, 0.01, 0.02, 0.03, 0.05]:
            py = self._rms_to_px(rms_val, max_bar)
            if py < 4 or py > max_bar - 4:
                continue
            ly = baseline - py
            # Subtle dotted line
            for dx in range(0, cwr, 6):
                if dx + 2 < cwr:
                    pygame.draw.line(self.screen, GRID, (cl + dx, ly), (cl + dx + 2, ly), 1)
            # Label
            lbl = self.font_sm.render(f".{int(rms_val*1000):03d}", True, DIM)
            self.screen.blit(lbl, (cx + 3, ly - lbl.get_height() // 2))

        # ── Time grid (X axis) ────────────────────────────────────────
        gs = max(1, VIEW_SECONDS // 5)
        for t in range(int(ws) + gs, int(ws + VIEW_SECONDS) + 1, gs):
            gx = cl + int(((t - ws) / VIEW_SECONDS) * cwr)
            if cl < gx < cx + cw - 5:
                # Subtle vertical dots
                for dy in range(cy + 4, baseline, 6):
                    self.screen.set_at((gx, dy), GRID)
                lbl = self.font_sm.render(f"{t:.0f}s", True, DIM)
                self.screen.blit(lbl, (gx - lbl.get_width() // 2, baseline + 2))

        # ── Baseline glow ─────────────────────────────────────────────
        self.screen.blit(self._baseline_glow, (cx, baseline))

        # ── Bars (gradient + glow) ────────────────────────────────────
        for seg in vis:
            sx = cl + int(((seg['t'] - ws) / VIEW_SECONDS) * cwr)
            bh = self._rms_to_px(seg['rms'], max_bar)
            bw = max(1, int((seg.get('dur', 50) / 1000 / VIEW_SECONDS) * cwr))
            label = seg['label']

            if bh < 1 or label == 'silence':
                continue

            bar_top = baseline - bh

            # Glow underneath bar
            glow_src = self._glow_cache.get(label)
            if glow_src and bh > 3:
                glow_scaled = pygame.transform.scale(glow_src, (bw + 4, min(bh, 24)))
                self.screen.blit(glow_scaled, (sx - 2, bar_top - 2))

            # Gradient bar
            grad_src = self._bar_gradients.get(label)
            if grad_src:
                bar_surf = pygame.transform.scale(grad_src, (bw, bh))
                self.screen.blit(bar_surf, (sx, bar_top))
            else:
                color = LABEL_COLOR.get(label, SILENCE)
                pygame.draw.rect(self.screen, color, (sx, bar_top, bw, bh))

            # Bright cap at top of bar (1px highlight)
            hi = LABEL_COLOR_HI.get(label)
            if hi and bh > 2:
                pygame.draw.line(self.screen, hi, (sx, bar_top), (sx + bw - 1, bar_top), 1)

        # ── Threshold line ────────────────────────────────────────────
        last = vis[-1]
        thr = last.get('thr')
        nf = last.get('nf')

        if thr and thr > 0:
            thr_px = self._rms_to_px(thr, max_bar)
            if 4 < thr_px < max_bar - 4:
                thr_y = baseline - thr_px
                self._draw_labeled_line(cl, thr_y, cwr, SPEECH,
                                        f"speech .{int(thr*1000):03d}", above=True)

        if nf and nf > 0:
            nf_px = self._rms_to_px(nf, max_bar)
            if 4 < nf_px < max_bar - 4:
                nf_y = baseline - nf_px
                self._draw_labeled_line(cl, nf_y, cwr, NOISE,
                                        f"floor .{int(nf*1000):03d}", above=False)

        # ── RMS readout ───────────────────────────────────────────────
        rms_val = f"{self._cur_rms:.4f}"
        rms_lbl = self.font_sm.render("RMS", True, DIM)
        rms_num = self.font_lg.render(rms_val, True, ACCENT)
        self.screen.blit(rms_lbl, (cl + 6, cy + 5))
        self.screen.blit(rms_num, (cl + 6 + rms_lbl.get_width() + 4,
                                    cy + 4 + (rms_lbl.get_height() - rms_num.get_height()) // 2))

        # ── Wake markers ──────────────────────────────────────────────
        for t in wakes:
            mx = cl + int(((t - ws) / VIEW_SECONDS) * cwr)
            if cl <= mx <= cx + cw:
                self._draw_marker(mx, cy, baseline, WAKE, "WAKE")

        # ── Barge-in markers ──────────────────────────────────────────
        for t in bargeins:
            mx = cl + int(((t - ws) / VIEW_SECONDS) * cwr)
            if cl <= mx <= cx + cw:
                self._draw_marker(mx, cy, baseline, BARGEIN, "BARGE-IN")

        # ── State badge ───────────────────────────────────────────────
        sc = STATE_COLOR.get(self._cur_state, DIM)
        state_txt = self.font.render(self._cur_state, True, sc)
        pw = state_txt.get_width() + 14
        ph = state_txt.get_height() + 8
        sx = cx + cw - pw - 6
        sy = cy + 4
        pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pill.fill((4, 6, 12, 200))
        pygame.draw.rect(pill, (*sc, 120), (0, 0, pw, ph), 2, border_radius=5)
        # Subtle fill
        inner = pygame.Surface((pw - 4, ph - 4), pygame.SRCALPHA)
        inner.fill((*sc, 15))
        pill.blit(inner, (2, 2))
        self.screen.blit(pill, (sx, sy))
        self.screen.blit(state_txt, (sx + 7, sy + 4))

        # ── Border ────────────────────────────────────────────────────
        pygame.draw.rect(self.screen, BORDER, (cx, cy, cw, ch), 1, border_radius=6)

    def _draw_labeled_line(self, x, y, w, color, text, above=True):
        """Draw a dashed horizontal line with a label pill."""
        # Dashed line
        cx = x
        end = x + w
        while cx < end:
            dx = min(8, end - cx)
            pygame.draw.line(self.screen, (*color[:3], 140) if len(color) > 3 else color,
                             (cx, y), (cx + dx, y), 1)
            cx += 12

        # Label pill
        lbl = self.font_sm.render(text, True, color)
        pw = lbl.get_width() + 8
        ph = lbl.get_height() + 4
        px = x + w - pw - 2
        py = y - ph - 1 if above else y + 2
        pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pill.fill((4, 6, 12, 210))
        pygame.draw.rect(pill, (*color, 80), (0, 0, pw, ph), 1, border_radius=3)
        self.screen.blit(pill, (px, py))
        self.screen.blit(lbl, (px + 4, py + 2))

    def _draw_marker(self, mx, top, bottom, color, text):
        """Draw a vertical event marker with glow and label."""
        # Glow line (wider, transparent)
        glow_surf = pygame.Surface((6, bottom - top), pygame.SRCALPHA)
        glow_surf.fill((*color, 30))
        self.screen.blit(glow_surf, (mx - 3, top + 2))

        # Main line
        pygame.draw.line(self.screen, color, (mx, top + 2), (mx, bottom), 2)

        # Diamond at top
        d = 5
        pygame.draw.polygon(self.screen, color,
                            [(mx, top + 4), (mx + d, top + 4 + d),
                             (mx, top + 4 + d * 2), (mx - d, top + 4 + d)])

        # Label pill
        tag = self.font_sm.render(text, True, color)
        pw = tag.get_width() + 8
        ph = tag.get_height() + 4
        pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
        pill.fill((4, 6, 12, 220))
        pygame.draw.rect(pill, (*color, 100), (0, 0, pw, ph), 1, border_radius=3)
        self.screen.blit(pill, (mx + 5, top + 18))
        self.screen.blit(tag, (mx + 9, top + 20))

    # ── Legend ────────────────────────────────────────────────────────────
    def _draw_legend(self):
        ix = self._x
        for label, color in self._legend_items:
            # Rounded color pill
            pygame.draw.rect(self.screen, color,
                             (ix, self._legend_y + 5, 14, 10), border_radius=3)
            # Highlight on top half
            hi_surf = pygame.Surface((14, 5), pygame.SRCALPHA)
            hi_surf.fill((255, 255, 255, 30))
            self.screen.blit(hi_surf, (ix, self._legend_y + 5))
            ix += 18
            surf = self.font_sm.render(label, True, TEXT)
            self.screen.blit(surf, (ix, self._legend_y + 5))
            ix += surf.get_width() + 12

    # ── Counters ──────────────────────────────────────────────────────────
    def _draw_counters(self):
        elapsed = int(time.time() - self._t0)
        mins, secs = divmod(elapsed, 60)
        parts = [
            (f"Speech:{self._speech_n}", SPEECH),
            (f"TTS:{self._tts_n}", TTS),
            (f"Wake:{self._wake_n}", WAKE),
            (f"BI:{self._bargein_n}", BARGEIN),
            (f"{mins}:{secs:02d}", DIM),
        ]
        ix = self._x
        for text, color in parts:
            surf = self.font_sm.render(text, True, color)
            self.screen.blit(surf, (ix, self._counter_y))
            ix += surf.get_width() + 12

    # ── Helpers ───────────────────────────────────────────────────────────
    def _dashed_h(self, x, y, length, color, dash=5, gap=3):
        cx = x
        end = x + length
        while cx < end:
            dx = min(dash, end - cx)
            pygame.draw.line(self.screen, color, (cx, y), (cx + dx, y), 1)
            cx += dash + gap
