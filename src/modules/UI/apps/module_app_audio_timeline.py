"""
Audio Timeline App — Glass Cockpit real-time audio visualization for TARS.

Self-contained: hooks into the shared mic AudioHub, analyzes audio in-place,
and renders 6 swim-lane timeline + right-side signal diagnostics panel.
"""

import pygame
import time
import math
import threading
import collections
import numpy as np

# ── Colors ────────────────────────────────────────────────────────────────────
BG         = (10, 14, 20)
PANEL      = (14, 18, 30)
BORDER     = (24, 30, 48)
GRID       = (18, 22, 38)
TEXT       = (200, 205, 220)
TEXT_DIM   = (100, 108, 135)
TEXT_VAL   = (220, 235, 255)
DIM        = (45, 50, 70)
ACCENT     = (0, 210, 240)
WHITE_SOFT = (220, 225, 235)

SPEECH      = (30, 210, 50)
SPEECH_HI   = (140, 255, 160)
TTS_COL     = (140, 60, 255)
TTS_HI      = (200, 150, 255)
NOISE_COL   = (220, 155, 20)
NOISE_HI    = (255, 210, 60)
WAKE_COL    = (0, 220, 255)
WAKE_HI     = (120, 245, 255)
BARGEIN_COL = (255, 50, 45)
BARGEIN_HI  = (255, 130, 110)

# STT zone colors
ZONE_SILENCE = (40, 45, 65)      # below noise floor
ZONE_NOISE   = (200, 130, 20)    # noise zone (floor → threshold)
ZONE_SPEECH  = (30, 210, 50)     # above threshold

# SNR meter zone colors
SNR_BAD  = (220, 50, 40)
SNR_WARN = (220, 155, 20)
SNR_GOOD = (30, 210, 50)

STATE_COLOR = {
    'STANDBY':   DIM,
    'LISTENING': SPEECH,
    'THINKING':  NOISE_COL,
    'TALKING':   TTS_COL,
    'BOOTING':   ACCENT,
}

VIEW_SECONDS = 15

_HOP_MS = 50
_RMS_SPEECH_THRESHOLD = 0.015
_RMS_NOISE_FLOOR = 0.005
_SPEECH_HOLD_CHUNKS = 6

# 6 swim lanes — fractions of chart height (top → bottom)
_LANE_FRACS   = [0.12, 0.25, 0.25, 0.12, 0.14, 0.12]
_LANE_BARGEIN = 0
_LANE_TTS     = 1
_LANE_STT     = 2
_LANE_WAKE    = 3
_LANE_NOISE   = 4
_LANE_STATE   = 5

_LANE_META = [
    {'name': 'BARGE-IN', 'color': BARGEIN_COL, 'hi': BARGEIN_HI},
    {'name': 'TTS',      'color': TTS_COL,     'hi': TTS_HI},
    {'name': 'STT',      'color': SPEECH,      'hi': SPEECH_HI},
    {'name': 'WAKE',     'color': WAKE_COL,    'hi': WAKE_HI},
    {'name': 'NOISE',    'color': NOISE_COL,   'hi': NOISE_HI},
    {'name': 'STATE',    'color': ACCENT,      'hi': ACCENT},
]

_GHOST_LAYERS = [
    {'alpha': 0.12, 'smooth': 7},
    {'alpha': 0.22, 'smooth': 5},
    {'alpha': 0.38, 'smooth': 3},
]
_MAIN_SMOOTH = 2
_RMS_MAX     = 0.06
_STATS_W     = 76   # right-side diagnostics panel width
_PEAK_DECAY  = 3.0  # seconds peak hold persists


def _smooth_array(arr, window):
    if window <= 1 or len(arr) < 2:
        return arr[:]
    half, n = window // 2, len(arr)
    return [sum(arr[max(0,i-half):min(n,i+half+1)]) /
            (min(n,i+half+1) - max(0,i-half)) for i in range(n)]


class AudioTimelineApp:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width  = width
        self.height = height

        try:
            self.font       = pygame.font.Font("UI/mono.ttf", 13)
            self.font_sm    = pygame.font.Font("UI/mono.ttf", 11)
            self.font_lg    = pygame.font.Font("UI/mono.ttf", 15)
            self.font_label = pygame.font.Font("UI/mono.ttf", 11)
            self.font_val   = pygame.font.Font("UI/mono.ttf", 12)
            self.font_state = pygame.font.Font("UI/mono.ttf", 9)
            self.font_xs    = pygame.font.Font("UI/mono.ttf", 9)
        except Exception:
            self.font       = pygame.font.SysFont("monospace", 13)
            self.font_sm    = pygame.font.SysFont("monospace", 11)
            self.font_lg    = pygame.font.SysFont("monospace", 15)
            self.font_label = pygame.font.SysFont("monospace", 11)
            self.font_val   = pygame.font.SysFont("monospace", 12)
            self.font_state = pygame.font.SysFont("monospace", 9)
            self.font_xs    = pygame.font.SysFont("monospace", 9)

        # Timeline data
        self._segments    = []
        self._wake_times  = []
        self._bargein_times = []
        self._lock = threading.Lock()
        self._max  = 2000

        # Event counters / state tracking
        self._speech_n  = 0
        self._tts_n     = 0
        self._wake_n    = 0
        self._bargein_n = 0
        self._last_label = 'silence'
        self._prev_state = 'STANDBY'
        self._wake_ack_pending    = False
        self._response_pending    = False
        self._speech_during_talking = False
        self._cur_state = 'STANDBY'
        self._cur_rms   = 0.0
        self._t0 = time.time()

        # Peak hold
        self._peak_rms  = 0.0
        self._peak_time = 0.0

        # Audio analysis
        self._mic_rid    = None
        self._running    = False
        self._speech_hold = 0
        self._noise_floor = _RMS_NOISE_FLOOR
        self._noise_samples = collections.deque(maxlen=200)
        self._start_time = 0.0
        self._accum      = []
        self._accum_frames = 0
        self._hop_frames = 0

        # Cached STT-module values (refreshed lazily each render)
        self._stt_silence_thr  = None   # stt_manager.silence_threshold
        self._stt_amp_gain     = None   # stt_manager.amp_gain
        self._stt_margin       = None   # stt_manager.silence_margin
        self._stt_cache_time   = 0.0

        # Layout
        self._pad          = 8
        self._legend_h     = 26
        self._toolbar_h    = int(height * 0.06) + 4
        self._footer_row_h = 18
        self._time_axis_h  = 12
        self._bottom_margin = self._footer_row_h + 8 + self._toolbar_h

        chart_top = self._pad + self._legend_h + 4
        chart_bot = height - self._bottom_margin - self._pad - self._time_axis_h
        self._chart_rect = (self._pad, chart_top,
                            width - self._pad * 2, chart_bot - chart_top)
        self._time_axis_y = chart_bot

        # Full chart draw width for all swim lanes
        self._cwr = self._chart_rect[2]

        # Swim lane pixel regions
        ch = chart_bot - chart_top
        self._lanes = []
        y = chart_top
        for frac in _LANE_FRACS:
            lh = int(ch * frac)
            self._lanes.append({'top': y, 'h': lh,
                                'center': y + lh // 2, 'bot': y + lh})
            y += lh

        # Stats panel anchored beside STATE lane (may extend below into time axis gap)
        self._lower_cwr = self._cwr - _STATS_W - 4
        self._sp_x = self._pad + self._lower_cwr + 4
        self._sp_y = self._lanes[_LANE_STATE]['top']
        self._sp_w = _STATS_W - 2
        self._sp_h = max(self._lanes[_LANE_STATE]['h'], 100)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def reset(self):   self._start_audio()
    def cleanup(self): self._stop_audio()
    def update(self):  pass

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
            self._accum = [remaining] if len(remaining) else []
            self._accum_frames = len(remaining)
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

            # Peak hold
            if rms > self._peak_rms:
                self._peak_rms  = rms
                self._peak_time = now
            elif now - self._peak_time > _PEAK_DECAY:
                self._peak_rms = rms

            if tars_state == 'TALKING' and label == 'speech':
                self._speech_during_talking = True

            if tars_state != self._prev_state:
                if self._prev_state == 'STANDBY' and tars_state in ('LISTENING', 'TALKING'):
                    self._wake_times.append(seg['t'])
                    self._wake_n += 1
                    self._wake_ack_pending  = True
                    self._response_pending  = False
                    if len(self._wake_times) > 200:
                        self._wake_times = self._wake_times[-100:]

                elif self._prev_state == 'THINKING' and tars_state == 'TALKING':
                    self._response_pending      = True
                    self._speech_during_talking = False

                elif self._prev_state == 'TALKING' and tars_state == 'LISTENING':
                    if self._wake_ack_pending:
                        self._wake_ack_pending = False
                    elif self._response_pending:
                        if self._speech_during_talking:
                            self._bargein_times.append(seg['t'])
                            self._bargein_n += 1
                            if len(self._bargein_times) > 200:
                                self._bargein_times = self._bargein_times[-100:]
                        self._response_pending      = False
                        self._speech_during_talking = False

                elif tars_state == 'STANDBY':
                    self._wake_ack_pending      = False
                    self._response_pending      = False
                    self._speech_during_talking = False

                self._prev_state = tars_state

            self._cur_state = tars_state
            self._cur_rms   = rms
            self._segments.append(seg)
            if len(self._segments) > self._max:
                self._segments = self._segments[-1500:]

    # ── STT module value cache ────────────────────────────────────────────

    def _refresh_stt_cache(self):
        """Read STT manager values at most once per second."""
        if time.time() - self._stt_cache_time < 1.0:
            return
        try:
            from modules.module_stt import get_stt_manager
            mgr = get_stt_manager()
            if mgr:
                self._stt_silence_thr = getattr(mgr, 'silence_threshold', None)
                self._stt_amp_gain    = getattr(mgr, 'amp_gain', None)
                self._stt_margin      = getattr(mgr, 'silence_margin', None)
        except Exception:
            pass
        self._stt_cache_time = time.time()

    # ── Top-level render ──────────────────────────────────────────────────

    def render(self):
        self.screen.fill(BG)
        self._refresh_stt_cache()

        with self._lock:
            segs    = list(self._segments)
            wakes   = list(self._wake_times)
            bargeins = list(self._bargein_times)
            peak_rms  = self._peak_rms
            peak_time = self._peak_time
            cur_rms   = self._cur_rms
            noise_floor = self._noise_floor

        self._draw_legend()

        if not segs:
            self._draw_waiting()
            self._draw_footer()
            return

        latest = segs[-1]['t']
        ws  = latest - VIEW_SECONDS
        vis = [s for s in segs if s['t'] >= ws]
        if not vis:
            return

        last = vis[-1]
        thr = last.get('thr', 0)

        self._draw_chart(vis, ws, wakes, bargeins, thr, noise_floor)
        self._draw_time_axis(ws, latest)
        self._draw_stats_panel(cur_rms, peak_rms, peak_time, noise_floor,
                               thr, latest)
        self._draw_footer()

    # ── Waiting ───────────────────────────────────────────────────────────

    def _draw_waiting(self):
        pulse = 0.5 + 0.5 * math.sin(time.time() * 2.0)
        msg = self.font_lg.render("Waiting for audio...", True, ACCENT)
        msg.set_alpha(int(80 + 120 * pulse))
        self.screen.blit(msg, (self.width // 2 - msg.get_width() // 2,
                                self.height // 2 - msg.get_height() // 2))

    # ── Legend ────────────────────────────────────────────────────────────

    def _draw_legend(self):
        y = self._pad + 2
        rendered, total_w = [], 0
        for meta in _LANE_META:
            surf = self.font_label.render(meta['name'], True, TEXT_DIM)
            rendered.append((surf, meta['color']))
            total_w += 8 + 6 + surf.get_width() + 16
        total_w -= 8

        ix = (self.width - total_w) // 2
        for surf, color in rendered:
            pill_h, py = 8, y + (self._legend_h - 8) // 2 - 2
            glow = pygame.Surface((14, 14), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, 35), (0, 0, 14, 14), border_radius=5)
            self.screen.blit(glow, (ix - 3, py - 3))
            pygame.draw.rect(self.screen, color, (ix, py, 8, pill_h), border_radius=3)
            self.screen.blit(surf, (ix + 14, y + (self._legend_h - surf.get_height()) // 2 - 2))
            ix += 14 + surf.get_width() + 16

        lx = self._pad + 4
        lw = self.width - self._pad * 2 - 8
        sep = pygame.Surface((lw, 1), pygame.SRCALPHA)
        for sx in range(lw):
            frac = 1.0 - abs(sx - lw / 2) / (lw / 2)
            sep.set_at((sx, 0), (*BORDER, int(45 * frac)))
        self.screen.blit(sep, (lx, y + self._legend_h - 3))

    # ── Chart ─────────────────────────────────────────────────────────────

    def _rms_to_half_px(self, rms, half_h):
        return max(0, int(min(1.0, rms / _RMS_MAX) * half_h))

    def _draw_chart(self, vis, ws, wakes, bargeins, thr, nf):
        cx, cy, cw, ch = self._chart_rect
        cl  = cx
        cwr = self._cwr
        lcwr = self._lower_cwr  # reduced width for NOISE/STATE (stats panel on right)

        # Lane chrome
        for i, lane in enumerate(self._lanes):
            meta, color, cy_ = _LANE_META[i], _LANE_META[i]['color'], lane['center']
            lane_w = lcwr if i == _LANE_STATE else cwr

            if i != _LANE_STATE:
                cline = pygame.Surface((lane_w, 1), pygame.SRCALPHA)
                for dx in range(0, lane_w, 8):
                    for ddx in range(min(4, lane_w - dx)):
                        cline.set_at((dx + ddx, 0), (*color, 22))
                self.screen.blit(cline, (cl, cy_))

            if i < len(self._lanes) - 1:
                div = pygame.Surface((lane_w, 1), pygame.SRCALPHA)
                for dx in range(lane_w):
                    frac = 1.0 - abs(dx - lane_w / 2) / (lane_w / 2)
                    div.set_at((dx, 0), (*BORDER, int(35 * frac)))
                self.screen.blit(div, (cl, lane['bot']))

            lbl = self.font_sm.render(meta['name'], True, color)
            lbl.set_alpha(130)
            self.screen.blit(lbl, (cl + 3, cy_ - lbl.get_height() // 2))

        # ── Continuous waveforms ──────────────────────────────────────
        for lane_idx, label_key in [(_LANE_NOISE, 'noise'),
                                     (_LANE_TTS,   'tts_playing')]:
            lane   = self._lanes[lane_idx]
            meta   = _LANE_META[lane_idx]
            half_h = lane['h'] // 2 - 2
            cy_    = lane['center']
            color, hi = meta['color'], meta['hi']
            raw_h, raw_xs = [], []
            for seg in vis:
                sx = cl + int(((seg['t'] - ws) / VIEW_SECONDS) * cwr)
                raw_xs.append(sx)
                raw_h.append(self._rms_to_half_px(seg['rms'], half_h)
                             if seg['label'] == label_key else 0)

            if not any(h > 0 for h in raw_h):
                continue
            for ghost in _GHOST_LAYERS:
                self._draw_centered_wave(raw_xs, _smooth_array(raw_h, ghost['smooth']),
                                          cy_, half_h, color, ghost['alpha'], 2)
            sh = _smooth_array(raw_h, _MAIN_SMOOTH)
            self._draw_centered_wave(raw_xs, sh, cy_, half_h, color, 0.50, 0)
            self._draw_centered_edge(raw_xs, sh, cy_, hi, color)
            self._draw_centered_blooms(raw_xs, sh, cy_, half_h, hi)

        # ── STT lane with zone coloring ───────────────────────────────
        self._draw_stt_lane(vis, ws, cl, cwr, thr, nf)

        # ── Threshold lines on STT lane ───────────────────────────────
        stt_lane = self._lanes[_LANE_STT]
        half_h   = stt_lane['h'] // 2 - 2
        cy_      = stt_lane['center']

        if thr > 0:
            thr_px = self._rms_to_half_px(thr, half_h)
            if 2 < thr_px < half_h - 2:
                self._draw_threshold_line(cl, cy_ - thr_px, cwr, SPEECH,    0.45, "THR")
                self._draw_threshold_line(cl, cy_ + thr_px, cwr, SPEECH,    0.45, None)

        if nf > 0:
            nf_px = self._rms_to_half_px(nf, half_h)
            if 2 < nf_px < half_h - 2:
                self._draw_threshold_line(cl, cy_ - nf_px,  cwr, NOISE_COL, 0.35, "NF")
                self._draw_threshold_line(cl, cy_ + nf_px,  cwr, NOISE_COL, 0.35, None)

        # STT module threshold (from actual stt_manager — may differ from ours)
        if self._stt_silence_thr and self._stt_silence_thr > 0:
            stt_px = self._rms_to_half_px(
                min(self._stt_silence_thr / max(self._stt_amp_gain or 1, 1) / 32768.0,
                    _RMS_MAX), half_h)
            if 2 < stt_px < half_h - 2:
                self._draw_threshold_line(cl, cy_ - stt_px, cwr, ACCENT, 0.30, "STT")
                self._draw_threshold_line(cl, cy_ + stt_px, cwr, ACCENT, 0.30, None)

        # Noise floor on noise lane
        noise_lane = self._lanes[_LANE_NOISE]
        nh = noise_lane['h'] // 2 - 2
        ncy = noise_lane['center']
        if nf > 0:
            nf_px2 = self._rms_to_half_px(nf, nh)
            if 2 < nf_px2 < nh - 2:
                self._draw_threshold_line(cl, ncy - nf_px2, cwr, NOISE_COL, 0.25, None)
                self._draw_threshold_line(cl, ncy + nf_px2, cwr, NOISE_COL, 0.25, None)

        # ── Event markers ─────────────────────────────────────────────
        self._draw_event_markers(_LANE_WAKE,    wakes,    ws, cl, cwr)
        self._draw_event_markers(_LANE_BARGEIN, bargeins, ws, cl, cwr)

        # ── State lane ────────────────────────────────────────────────
        self._draw_state_lane(vis, ws, cl, lcwr, wakes, bargeins)

    # ── STT lane — zone-colored waveform ──────────────────────────────────

    def _draw_stt_lane(self, vis, ws, cl, cwr, thr, nf):
        """Draw the STT waveform color-coded by RMS zone."""
        lane   = self._lanes[_LANE_STT]
        half_h = lane['h'] // 2 - 2
        cy_    = lane['center']

        # Build per-sample (x, height, zone_color) only for speech segments
        data = []
        for seg in vis:
            sx = cl + int(((seg['t'] - ws) / VIEW_SECONDS) * cwr)
            if seg['label'] != 'speech':
                data.append((sx, 0, ZONE_SILENCE))
                continue
            h = self._rms_to_half_px(seg['rms'], half_h)
            rms = seg['rms']
            if rms >= thr:
                zone = ZONE_SPEECH
            elif rms >= nf * 1.5:
                zone = ZONE_NOISE
            else:
                zone = ZONE_SILENCE
            data.append((sx, h, zone))

        if not any(d[1] > 0 for d in data):
            return

        # Ghost layers (single color — use speech color for ghosts)
        raw_h  = [d[1] for d in data]
        raw_xs = [d[0] for d in data]
        for ghost in _GHOST_LAYERS:
            self._draw_centered_wave(raw_xs, _smooth_array(raw_h, ghost['smooth']),
                                      cy_, half_h, SPEECH, ghost['alpha'] * 0.7, 2)

        # Main layer — draw per-zone colored segments
        smooth_h = _smooth_array(raw_h, _MAIN_SMOOTH)

        # Group into runs by zone color
        runs = []
        cur_run_xs, cur_run_hs, cur_color = [], [], None
        for i, (sx, h, zone) in enumerate(data):
            sh = smooth_h[i]
            if sh <= 0:
                if cur_run_xs:
                    runs.append((cur_run_xs[:], cur_run_hs[:], cur_color))
                    cur_run_xs, cur_run_hs = [], []
                    cur_color = None
                continue
            if zone != cur_color:
                if cur_run_xs:
                    runs.append((cur_run_xs[:], cur_run_hs[:], cur_color))
                cur_run_xs, cur_run_hs, cur_color = [sx], [sh], zone
            else:
                cur_run_xs.append(sx)
                cur_run_hs.append(sh)
        if cur_run_xs:
            runs.append((cur_run_xs, cur_run_hs, cur_color))

        for rxs, rhs, color in runs:
            if not rxs:
                continue
            hi = SPEECH_HI if color == ZONE_SPEECH else (
                 NOISE_HI  if color == ZONE_NOISE  else DIM)
            self._draw_centered_wave(rxs, rhs, cy_, half_h, color, 0.55, 0)
            self._draw_centered_edge(rxs, rhs, cy_, hi, color)

        self._draw_centered_blooms(raw_xs, smooth_h, cy_, half_h, SPEECH_HI)

    # ── Centered waveform ─────────────────────────────────────────────────

    def _draw_centered_wave(self, xs, heights, cy_, half_h,
                             color, alpha_frac, expand):
        regions, cur = [], []
        for i, h in enumerate(heights):
            if h > 0:
                cur.append((xs[i], h))
            elif cur:
                regions.append(cur); cur = []
        if cur:
            regions.append(cur)

        base_a = int(255 * alpha_frac)
        for region in regions:
            if len(region) < 2:
                x, h = region[0]
                bw = max(2, 3 + expand)
                bar = pygame.Surface((bw, int(h) * 2), pygame.SRCALPHA)
                bar.fill((*color, base_a))
                self.screen.blit(bar, (x - expand, cy_ - int(h)))
                continue

            for sign in (1, -1):  # bottom then top (or vice versa)
                poly = [(x, cy_ - sign * int(h)) for x, h in region]
                poly += [(region[-1][0], cy_), (region[0][0], cy_)]
                if len(poly) < 3:
                    continue
                min_x = min(p[0] for p in poly)
                max_x = max(p[0] for p in poly)
                min_y = min(p[1] for p in poly)
                max_y = max(p[1] for p in poly)
                sw = max(1, max_x - min_x + 1 + expand * 2)
                sh = max(1, max_y - min_y + 1 + expand)
                surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
                local = [(p[0] - min_x + expand, p[1] - min_y) for p in poly]
                if len(local) >= 3:
                    pygame.draw.polygon(surf, (*color, base_a), local)
                    for yi in range(sh):
                        dist = abs(min_y + yi - cy_) / max(half_h, 1)
                        if dist > 0.4:
                            boost = int(base_a * 0.25 * (dist - 0.4) / 0.6)
                            pygame.draw.line(surf, (*color, min(255, boost)),
                                             (0, yi), (sw, yi))
                self.screen.blit(surf, (min_x - expand, min_y))

    def _draw_centered_edge(self, xs, heights, cy_, hi_color, fill_color):
        top_e, bot_e = [], []
        for i, h in enumerate(heights):
            if h > 0:
                top_e.append((xs[i], cy_ - int(h)))
                bot_e.append((xs[i], cy_ + int(h)))
            elif top_e:
                if len(top_e) >= 2:
                    self._draw_edge_line(top_e, hi_color, fill_color)
                    self._draw_edge_line(bot_e, hi_color, fill_color)
                top_e, bot_e = [], []
        if len(top_e) >= 2:
            self._draw_edge_line(top_e, hi_color, fill_color)
            self._draw_edge_line(bot_e, hi_color, fill_color)

    def _draw_edge_line(self, edge, hi_color, fill_color):
        for i in range(len(edge) - 1):
            pygame.draw.line(self.screen, (*fill_color, 35), edge[i], edge[i+1], 5)
        for i in range(len(edge) - 1):
            pygame.draw.line(self.screen, (*fill_color, 70), edge[i], edge[i+1], 3)
        for i in range(len(edge) - 1):
            pygame.draw.line(self.screen, hi_color, edge[i], edge[i+1], 2)

    def _draw_centered_blooms(self, xs, heights, cy_, half_h, hi_color):
        bloom_thr = half_h * 0.50
        for i, h in enumerate(heights):
            if h < bloom_thr:
                continue
            ph = heights[i-1] if i > 0 else 0
            nh = heights[i+1] if i < len(heights)-1 else 0
            if h < ph or h < nh:
                continue
            intensity = min(1.0, (h - bloom_thr) / (half_h * 0.4))
            br = int(10 + 14 * intensity)
            bloom = pygame.Surface((br*2, br*2), pygame.SRCALPHA)
            for ring in range(br, 0, -1):
                a = int(50 * intensity * (1.0 - (ring/br)**2))
                if a > 0:
                    pygame.draw.circle(bloom, (*hi_color, a), (br, br), ring)
            self.screen.blit(bloom, (xs[i]-br, cy_ - int(h) - br))
            self.screen.blit(bloom, (xs[i]-br, cy_ + int(h) - br))

    # ── Threshold line ────────────────────────────────────────────────────

    def _draw_threshold_line(self, x, y, w, color, opacity, label=None):
        alpha = int(255 * opacity)
        line  = pygame.Surface((w, 1), pygame.SRCALPHA)
        for dx in range(0, w, 10):
            for ddx in range(min(5, w - dx)):
                line.set_at((dx + ddx, 0), (*color, alpha))
        self.screen.blit(line, (x, y))
        if label:
            lbl = self.font_xs.render(label, True, color)
            lbl.set_alpha(alpha)
            # Draw label inset from right edge of the threshold line
            self.screen.blit(lbl, (x + w - lbl.get_width() - 4,
                                   y - lbl.get_height() // 2))

    # ── Event markers ─────────────────────────────────────────────────────

    def _draw_event_markers(self, lane_idx, event_times, ws, cl, cwr):
        lane   = self._lanes[lane_idx]
        meta   = _LANE_META[lane_idx]
        color, hi = meta['color'], meta['hi']
        top, bot  = lane['top'] + 2, lane['bot'] - 2
        h, cy_    = bot - top, lane['center']

        for evt_t in event_times:
            mx = cl + int(((evt_t - ws) / VIEW_SECONDS) * cwr)
            if mx < cl or mx > cl + cwr:
                continue

            gw = 16
            glow = pygame.Surface((gw, h), pygame.SRCALPHA)
            for gx in range(gw):
                dist = abs(gx - gw//2) / (gw/2)
                a = int(30 * (1.0 - dist*dist))
                pygame.draw.line(glow, (*color, a), (gx, 0), (gx, h))
            self.screen.blit(glow, (mx - gw//2, top))
            pygame.draw.line(self.screen, color, (mx, top), (mx, bot), 2)

            d = 4
            pts = [(mx, cy_-d), (mx+d, cy_), (mx, cy_+d), (mx-d, cy_)]
            pygame.draw.polygon(self.screen, hi, pts)
            pygame.draw.polygon(self.screen, color, pts, 1)

            tag = self.font_state.render(meta['name'], True, WHITE_SOFT)
            pw, ph = tag.get_width() + 6, tag.get_height() + 2
            pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
            pill.fill((color[0]//6, color[1]//6, color[2]//6, 200))
            pygame.draw.rect(pill, (*color, 120), (0, 0, pw, ph), 1, border_radius=3)
            if mx + 10 + pw < cl + cwr:
                self.screen.blit(pill, (mx+6, top+2))
                self.screen.blit(tag,  (mx+9, top+3))
            else:
                self.screen.blit(pill, (mx-6-pw, top+2))
                self.screen.blit(tag,  (mx-3-pw, top+3))

    # ── State lane ────────────────────────────────────────────────────────

    def _draw_state_lane(self, vis, ws, cl, cwr, wakes, bargeins):
        lane   = self._lanes[_LANE_STATE]
        top, h = lane['top'] + 1, lane['h'] - 2
        cy_, pad = lane['center'], 1

        # State blocks
        runs, cur_state, cur_start = [], vis[0]['state'], vis[0]['t']
        for seg in vis[1:]:
            if seg['state'] != cur_state:
                runs.append((cur_state, cur_start, seg['t']))
                cur_state, cur_start = seg['state'], seg['t']
        runs.append((cur_state, cur_start, vis[-1]['t'] + _HOP_MS/1000))

        for state, t0, t1 in runs:
            x1 = max(cl, cl + int(((t0 - ws) / VIEW_SECONDS) * cwr))
            x2 = min(cl + cwr, cl + int(((t1 - ws) / VIEW_SECONDS) * cwr))
            bw = x2 - x1
            if bw < 1:
                continue
            sc = STATE_COLOR.get(state, DIM)
            block = pygame.Surface((bw, h), pygame.SRCALPHA)
            block.fill((*sc, 30))
            if h > 4:
                pygame.draw.line(block, (*sc, 70), (0, pad), (bw, pad))
                pygame.draw.line(block, (*sc, 70), (0, h-pad-1), (bw, h-pad-1))
            self.screen.blit(block, (x1, top))
            pygame.draw.rect(self.screen, (*sc, 50),
                             (x1, top+pad, bw, h-pad*2), 1, border_radius=2)
            lbl = self.font_state.render(state, True, sc)
            if bw > lbl.get_width() + 6:
                self.screen.blit(lbl, (x1 + (bw - lbl.get_width()) // 2,
                                       top + (h - lbl.get_height()) // 2))

        # Wake / barge-in ticks
        for evt_t in wakes:
            mx = cl + int(((evt_t - ws) / VIEW_SECONDS) * cwr)
            if cl <= mx <= cl + cwr:
                pygame.draw.line(self.screen, WAKE_COL,  (mx, top), (mx, top+h), 2)
                pygame.draw.line(self.screen, WAKE_HI,   (mx-3, top+2), (mx+3, top+2), 1)
        for evt_t in bargeins:
            mx = cl + int(((evt_t - ws) / VIEW_SECONDS) * cwr)
            if cl <= mx <= cl + cwr:
                pygame.draw.line(self.screen, BARGEIN_COL, (mx, top), (mx, top+h), 2)
                pygame.draw.line(self.screen, BARGEIN_HI,  (mx-3, top+2), (mx+3, top+2), 1)

    # ── X-axis time labels ────────────────────────────────────────────────

    def _draw_time_axis(self, ws, latest):
        cl  = self._pad
        cwr = self._cwr
        y   = self._time_axis_y + 2

        for offset in range(0, VIEW_SECONDS + 1, 5):
            t = ws + offset
            x = cl + int((offset / VIEW_SECONDS) * cwr)
            age = latest - t
            label = f"-{int(age)}s" if age > 0.5 else "now"
            lbl = self.font_xs.render(label, True, TEXT_DIM)
            # Tick mark
            pygame.draw.line(self.screen, DIM, (x, y), (x, y + 3), 1)
            self.screen.blit(lbl, (x - lbl.get_width() // 2, y + 4))

    # ── Stats panel ───────────────────────────────────────────────────────

    def _draw_stats_panel(self, cur_rms, peak_rms, peak_time, nf, thr, now):
        px = self._sp_x
        py = self._sp_y
        pw = self._sp_w
        ph = self._sp_h

        # Panel background
        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((*PANEL, 200))
        pygame.draw.rect(bg, (*BORDER, 100), (0, 0, pw, ph), 1, border_radius=3)
        self.screen.blit(bg, (px, py))

        snr = cur_rms / max(nf, 1e-6)
        snr_color = SNR_GOOD if snr >= 3.0 else (SNR_WARN if snr >= 1.5 else SNR_BAD)
        rms_color = (SPEECH_HI if cur_rms >= thr else
                     NOISE_HI  if cur_rms >= nf * 1.5 else TEXT_DIM)
        peak_age   = now - peak_time
        peak_alpha = max(0, int(255 * (1.0 - peak_age / _PEAK_DECAY)))

        bar_w = pw - 6
        ry = py + 3
        row_gap = 12   # px between text rows

        # ── Row 1: RMS live bar ───────────────────────────────────────
        bar_h = 7
        rms_frac  = min(1.0, cur_rms / _RMS_MAX)
        peak_frac = min(1.0, peak_rms / _RMS_MAX)
        pygame.draw.rect(self.screen, (*DIM, 50),
                         (px + 3, ry, bar_w, bar_h), border_radius=2)
        if rms_frac > 0:
            pygame.draw.rect(self.screen, rms_color,
                             (px + 3, ry, max(2, int(bar_w * rms_frac)), bar_h),
                             border_radius=2)
        if peak_alpha > 20:
            pk_x = px + 3 + int(bar_w * peak_frac)
            pk_surf = pygame.Surface((2, bar_h), pygame.SRCALPHA)
            pk_surf.fill((*SPEECH_HI, peak_alpha))
            self.screen.blit(pk_surf, (min(pk_x, px + 3 + bar_w - 2), ry))
        if thr > 0:
            tx = px + 3 + int(bar_w * min(1.0, thr / _RMS_MAX))
            pygame.draw.line(self.screen, (*SPEECH, 160),
                             (tx, ry - 1), (tx, ry + bar_h + 1), 1)
        ry += bar_h + 4

        # ── Row 2: RMS value ──────────────────────────────────────────
        r_lbl = self.font_xs.render("RMS", True, TEXT_DIM)
        r_val = self.font_xs.render(f"{cur_rms:.4f}", True, rms_color)
        self.screen.blit(r_lbl, (px + 2, ry))
        self.screen.blit(r_val, (px + pw - r_val.get_width() - 2, ry))
        ry += row_gap

        # ── Row 3: NF value ───────────────────────────────────────────
        nf_lbl = self.font_xs.render("NF", True, TEXT_DIM)
        nf_val = self.font_xs.render(f"{nf:.4f}", True, NOISE_COL)
        self.screen.blit(nf_lbl, (px + 2, ry))
        self.screen.blit(nf_val, (px + pw - nf_val.get_width() - 2, ry))
        ry += row_gap

        # ── Row 4: THR value ──────────────────────────────────────────
        thr_lbl = self.font_xs.render("THR", True, TEXT_DIM)
        thr_val = self.font_xs.render(f"{thr:.4f}", True, SPEECH)
        self.screen.blit(thr_lbl, (px + 2, ry))
        self.screen.blit(thr_val, (px + pw - thr_val.get_width() - 2, ry))
        ry += row_gap

        # ── Row 5: SNR bar ────────────────────────────────────────────
        snr_bar_h = 6
        pygame.draw.rect(self.screen, (*DIM, 50),
                         (px + 3, ry, bar_w, snr_bar_h), border_radius=2)
        fill_frac = min(1.0, snr / 6.0)
        fill_w = max(2, int(bar_w * fill_frac))
        bad_w  = min(fill_w, int(bar_w * (1.5 / 6.0)))
        warn_w = max(0, min(fill_w, int(bar_w * (3.0 / 6.0))) - bad_w)
        good_w = max(0, fill_w - bad_w - warn_w)
        bx = px + 3
        if bad_w > 0:
            pygame.draw.rect(self.screen, SNR_BAD,  (bx, ry, bad_w,  snr_bar_h), border_radius=2)
            bx += bad_w
        if warn_w > 0:
            pygame.draw.rect(self.screen, SNR_WARN, (bx, ry, warn_w, snr_bar_h))
            bx += warn_w
        if good_w > 0:
            pygame.draw.rect(self.screen, SNR_GOOD, (bx, ry, good_w, snr_bar_h))
        pygame.draw.rect(self.screen, (*BORDER, 120),
                         (px + 3, ry, bar_w, snr_bar_h), 1, border_radius=2)
        for threshold_snr in (1.5, 3.0):
            mx = px + 3 + int(bar_w * threshold_snr / 6.0)
            pygame.draw.line(self.screen, (*BORDER, 200), (mx, ry), (mx, ry + snr_bar_h), 1)
        ry += snr_bar_h + 4

        # ── Row 6: SNR value ──────────────────────────────────────────
        snr_lbl = self.font_xs.render("SNR", True, TEXT_DIM)
        snr_val = self.font_xs.render(f"{snr:.1f}x", True, snr_color)
        self.screen.blit(snr_lbl, (px + 2, ry))
        self.screen.blit(snr_val, (px + pw - snr_val.get_width() - 2, ry))
        ry += row_gap

        # ── Row 7: AMP + margin config ────────────────────────────────
        if self._stt_amp_gain is not None:
            amp_lbl = self.font_xs.render("AMP", True, TEXT_DIM)
            amp_val = self.font_xs.render(f"{self._stt_amp_gain:.0f}x", True, TEXT_VAL)
            self.screen.blit(amp_lbl, (px + 2, ry))
            self.screen.blit(amp_val, (px + pw - amp_val.get_width() - 2, ry))
            ry += row_gap
        if self._stt_margin is not None:
            mar_lbl = self.font_xs.render("MAR", True, TEXT_DIM)
            mar_val = self.font_xs.render(f"{self._stt_margin:.1f}x", True, TEXT_VAL)
            self.screen.blit(mar_lbl, (px + 2, ry))
            self.screen.blit(mar_val, (px + pw - mar_val.get_width() - 2, ry))

    # ── Footer ────────────────────────────────────────────────────────────

    def _draw_footer(self):
        pad = self._pad
        y   = self.height - self._toolbar_h - self._footer_row_h - 4
        w   = self.width - pad * 2

        sep = pygame.Surface((w - 4, 1), pygame.SRCALPHA)
        for sx in range(w - 4):
            frac = 1.0 - abs(sx - (w-4)/2) / ((w-4)/2)
            sep.set_at((sx, 0), (*BORDER, int(40 * frac)))
        self.screen.blit(sep, (pad + 2, y - 3))

        elapsed = int(time.time() - self._t0)
        mins, secs = divmod(elapsed, 60)
        counters = [
            ("SPK", str(self._speech_n),  SPEECH),
            ("TTS", str(self._tts_n),     TTS_COL),
            ("WK",  str(self._wake_n),    WAKE_COL),
            ("BI",  str(self._bargein_n), BARGEIN_COL),
        ]

        ix = pad + 4
        for label, val, color in counters:
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*color, 50), (4, 4), 4)
            pygame.draw.circle(dot, color, (4, 4), 3)
            self.screen.blit(dot, (ix, y + 4))
            ix += 12
            lbl = self.font_sm.render(label, True, TEXT_DIM)
            self.screen.blit(lbl, (ix, y + 2))
            ix += lbl.get_width() + 1
            vsf = self.font_val.render(val, True, TEXT_VAL)
            self.screen.blit(vsf, (ix, y + 1))
            ix += vsf.get_width() + 10

        time_surf = self.font_sm.render(f"{mins}:{secs:02d}", True, DIM)
        self.screen.blit(time_surf, (ix + 4, y + 2))

        sc  = STATE_COLOR.get(self._cur_state, DIM)
        stxt = self.font_sm.render(self._cur_state, True, sc)
        bw   = stxt.get_width() + 16
        bh   = self._footer_row_h
        bx   = pad + w - bw - 2

        badge = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(badge, (*sc, 12), (0, 0, bw, bh), border_radius=4)
        pygame.draw.rect(badge, (*sc, 60), (0, 0, bw, bh), 1, border_radius=4)
        self.screen.blit(badge, (bx, y))

        if self._cur_state in ('LISTENING', 'THINKING', 'TALKING'):
            pulse = 0.5 + 0.5 * math.sin(time.time() * 3.5)
            pdot = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(pdot, (*sc, int(130 + 125 * pulse)), (3, 3), 3)
            self.screen.blit(pdot, (bx + 4, y + bh // 2 - 3))

        self.screen.blit(stxt, (bx + (bw - stxt.get_width()) // 2,
                                 y + (bh - stxt.get_height()) // 2))
