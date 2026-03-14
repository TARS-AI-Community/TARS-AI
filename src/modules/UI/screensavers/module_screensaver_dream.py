"""
Module: Dream Screensaver
Visualizes TARS' memories as abstract neural patterns with floating text fragments.
Uses a Compositional Pattern-Producing Network (CPPN) driven by emotional state
to generate organic, flowing visuals that represent TARS "dreaming" about recent
conversations. Text fragments are color-coded by emotion and the background
palette smoothly morphs to match the dominant emotion of visible memories.
"""
import pygame
import numpy as np
import random
import math
import time as time_mod
import hashlib
from UI.screensavers.module_screensaver_overlay import TimeOverlay

# ── Emotion → color palettes (dark, bright) ─────────────────────────────────
_PALETTES = {
    "joy":       ((35, 25, 5),    (255, 195, 55)),
    "anger":     ((40, 5, 5),     (215, 45, 25)),
    "sadness":   ((5, 10, 40),    (55, 95, 215)),
    "fear":      ((20, 5, 30),    (135, 45, 175)),
    "love":      ((30, 5, 20),    (225, 75, 135)),
    "curiosity": ((5, 25, 30),    (45, 215, 205)),
    "surprise":  ((30, 30, 10),   (250, 235, 115)),
    "neutral":   ((8, 12, 22),    (70, 125, 175)),
}

_RADAR_AXES = list(_PALETTES.keys())

# Pre-compute numpy palette arrays for fast lerping
_PAL_DARK  = {k: np.array(v[0], dtype=np.float32) for k, v in _PALETTES.items()}
_PAL_BRIGHT = {k: np.array(v[1], dtype=np.float32) for k, v in _PALETTES.items()}

# Pre-compute emotion text colors (avoid recomputing per frame)
_EMOTION_TEXT_COLORS = {}
for _emo, (_d, _b) in _PALETTES.items():
    _EMOTION_TEXT_COLORS[_emo] = (
        min(255, int(_b[0] * 0.45 + 140)),
        min(255, int(_b[1] * 0.45 + 140)),
        min(255, int(_b[2] * 0.45 + 140)),
    )

# ── Configurable CPPN aesthetic seeds ────────────────────────────────────────
_AESTHETIC_SEEDS = [42, 137, 256, 314, 512, 777, 1024, 1337]

# ── Check surfarray availability ─────────────────────────────────────────────
_HAS_SURFARRAY = False
try:
    import pygame.surfarray
    _HAS_SURFARRAY = True
except ImportError:
    pass


class DreamAnimation:
    """TARS dream-state screensaver — CPPN neural patterns + floating memories."""

    _PALETTE_LERP_SPEED = 0.4

    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None

        # ── Fonts ────────────────────────────────────────────────────────
        try:
            self.font_frag = pygame.font.Font("UI/pixelmix.ttf", 20)
            self.font_label = pygame.font.Font("UI/pixelmix.ttf", 12)
        except Exception:
            self.font_frag = pygame.font.SysFont("monospace", 20)
            self.font_label = pygame.font.SysFont("monospace", 12)

        # ── CPPN grid (low-res, upscaled for dreamy pixelated look) ─────
        self.scale = 12
        self.gw = max(10, width // self.scale)
        self.gh = max(10, height // self.scale)
        self.n = self.gw * self.gh

        x = np.linspace(-1.5, 1.5, self.gw, dtype=np.float32)
        y = np.linspace(-1.5, 1.5, self.gh, dtype=np.float32)
        X, Y = np.meshgrid(x, y)
        self.cx = X.flatten()
        self.cy = Y.flatten()
        self.cr = np.sqrt(self.cx ** 2 + self.cy ** 2)

        # Pre-allocate CPPN input array
        self._inp = np.empty((self.n, 6), dtype=np.float32)
        self._inp[:, 0] = self.cx
        self._inp[:, 1] = self.cy
        self._inp[:, 2] = self.cr

        # Pre-compute radial mask
        self._radial = np.clip(1.0 - self.cr / 2.2, 0.15, 1.0)

        self.cppn_surf = pygame.Surface((self.gw, self.gh))

        # Weights (set in _init_cppn)
        self.W1 = self.b1 = self.W2 = self.b2 = self.W3 = self.b3 = None

        # ── Animation state ──────────────────────────────────────────────
        self.t = 0.0
        self.t_speed = 0.008
        self._last = time_mod.time()

        # ── CPPN frame caching ───────────────────────────────────────────
        self._cppn_interval = 10
        self._cppn_counter = 0
        self._cached_bg = None

        # ── Emotion / palette ────────────────────────────────────────────
        self.emo = {a: 0 for a in _RADAR_AXES}
        self.base_emotion = "neutral"
        self.current_emotion = "neutral"

        self.dark   = np.array(_PALETTES["neutral"][0], dtype=np.float32)
        self.bright = np.array(_PALETTES["neutral"][1], dtype=np.float32)

        self._target_dark   = self.dark.copy()
        self._target_bright = self.bright.copy()

        self._color_range = self.bright - self.dark

        # ── Palette check throttle ───────────────────────────────────────
        self._palette_check_counter = 0
        self._palette_check_interval = 15  # only re-evaluate every 15 frames

        # ── Text fragments ───────────────────────────────────────────────
        self.mem_pool = []
        self.frags = []
        self.next_frag = 0.0
        self._text_cache = {}

        # ── Particles ────────────────────────────────────────────────────
        self.particles = []
        self.max_particles = 8

        # ── Pre-allocated glow surfaces ──────────────────────────────────
        self._glow_cache = {}

        # ── Pulse effect ─────────────────────────────────────────────────
        self.pulse_active = False
        self.pulse_pos = 0.0
        self.pulse_timer = 0.0

        # ── Label animation ──────────────────────────────────────────────
        self.label_alpha = 0.0
        self.label_dir = 1

        # ── Breathing ────────────────────────────────────────────────────
        self.breathe = 1.0

        # ── surfarray flag ───────────────────────────────────────────────
        self._use_surfarray = _HAS_SURFARRAY

    # ═════════════════════════════════════════════════════════════════════════
    #  DATA LOADING
    # ═════════════════════════════════════════════════════════════════════════

    def _load_data(self):
        """Pull recent interactions + emotional state from dashboard data."""
        self.mem_pool = []
        self.emo = {a: 0 for a in _RADAR_AXES}

        try:
            from modules.module_dashboard_data import get_interactions, get_emotional_state
            self.emo = get_emotional_state()
            for entry in get_interactions(limit=30):
                emotion = entry.get("emotion", "neutral") or "neutral"
                if emotion not in _PALETTES:
                    emotion = "neutral"
                for key in ("user", "bot"):
                    txt = entry.get(key, "")
                    if txt and len(txt) > 5:
                        snippet = txt[:55] + ("..." if len(txt) > 55 else "")
                        self.mem_pool.append({"text": snippet, "emotion": emotion})
        except Exception:
            pass

        if not self.mem_pool:
            self.mem_pool = [
                {"text": "Processing neural pathways...", "emotion": "curiosity"},
                {"text": "Memory consolidation active...", "emotion": "neutral"},
                {"text": "Analyzing interaction patterns...", "emotion": "curiosity"},
                {"text": "Dream cycle initiated...", "emotion": "neutral"},
                {"text": "Recalling recent events...", "emotion": "neutral"},
            ]

        scored = sorted(_RADAR_AXES, key=lambda a: self.emo.get(a, 0), reverse=True)
        self.base_emotion = scored[0] if self.emo.get(scored[0], 0) > 0 else "neutral"
        self.current_emotion = self.base_emotion

        self._set_palette_target(self.base_emotion)
        self.dark[:] = self._target_dark
        self.bright[:] = self._target_bright
        self._color_range = self.bright - self.dark

    def _set_palette_target(self, emotion):
        """Set the target palette to lerp toward."""
        self._target_dark[:] = _PAL_DARK[emotion]
        self._target_bright[:] = _PAL_BRIGHT[emotion]

    # ═════════════════════════════════════════════════════════════════════════
    #  PALETTE LERP (smooth background transitions)
    # ═════════════════════════════════════════════════════════════════════════

    def _update_palette(self, dt):
        """Determine dominant emotion from visible fragments and lerp palette."""
        # Throttle: only re-evaluate dominant emotion every N frames
        self._palette_check_counter += 1
        do_check = self._palette_check_counter >= self._palette_check_interval
        if do_check:
            self._palette_check_counter = 0

        if do_check and self.frags:
            # Simple tally — no Counter, just a dict
            counts = {}
            for f in self.frags:
                r = f["age"] / f["life"]
                if 0.12 < r < 0.75:
                    e = f["emotion"]
                    counts[e] = counts.get(e, 0) + 1

            if counts:
                dominant = max(counts, key=counts.get)
            else:
                dominant = self.base_emotion

            if dominant != self.current_emotion:
                self.current_emotion = dominant
                self._set_palette_target(dominant)
                self._text_cache.clear()
        elif do_check and not self.frags:
            if self.current_emotion != self.base_emotion:
                self.current_emotion = self.base_emotion
                self._set_palette_target(self.base_emotion)
                self._text_cache.clear()

        # Lerp current palette toward target
        t = min(1.0, self._PALETTE_LERP_SPEED * dt)
        self.dark   += (self._target_dark   - self.dark)   * t
        self.bright += (self._target_bright - self.bright) * t
        self._color_range = self.bright - self.dark

    # ═════════════════════════════════════════════════════════════════════════
    #  CPPN ENGINE
    # ═════════════════════════════════════════════════════════════════════════

    def _init_cppn(self):
        """Create CPPN weights — single pass, 10 hidden units."""
        seed_str = "_".join(f"{k}{self.emo.get(k, 0)}" for k in _RADAR_AXES)
        seed_val = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        base_seed = _AESTHETIC_SEEDS[seed_val % len(_AESTHETIC_SEEDS)]
        rng = np.random.RandomState(base_seed + seed_val % 1000)

        H = 10
        I = 6

        self.W1 = (rng.randn(I, H) * 0.9).astype(np.float32)
        self.b1 = (rng.randn(H) * 0.3).astype(np.float32)
        self.W2 = (rng.randn(H, H) * 0.7).astype(np.float32)
        self.b2 = (rng.randn(H) * 0.2).astype(np.float32)
        self.W3 = (rng.randn(H, 1) * 0.5).astype(np.float32)
        self.b3 = (rng.randn(1) * 0.1).astype(np.float32)

    def _cppn_frame(self):
        """Compute CPPN intensity map (H x W) for current time step."""
        t = self.t

        self._inp[:, 3] = math.sin(t * 0.7)
        self._inp[:, 4] = math.cos(t * 0.5)
        self._inp[:, 5] = self.breathe

        h = np.sin(self._inp @ self.W1 + self.b1)
        h = np.sin(h @ self.W2 + self.b2)
        # Fast sigmoid: x/(1+|x|)*0.5+0.5 — no np.exp
        raw = (h @ self.W3 + self.b3).flatten()
        out = raw / (1.0 + np.abs(raw)) * 0.5 + 0.5

        out *= self._radial

        if self.pulse_active:
            # Cheaper gaussian approximation: 1 - clamp(|x|/w)
            dist = np.abs(self.cr - self.pulse_pos)
            ring = np.clip(1.0 - dist * 6.0, 0, 1)
            out = np.clip(out + ring * 0.45, 0, 1)

        return out.reshape(self.gh, self.gw)

    def _to_surface(self, intensity):
        """Map (H,W) intensities to colored pygame surface, upscale to screen."""
        i = intensity[:, :, np.newaxis]
        colors = self.dark + i * self._color_range
        colors = np.clip(colors, 0, 255).astype(np.uint8)

        if self._use_surfarray:
            try:
                pygame.surfarray.blit_array(self.cppn_surf, colors.transpose(1, 0, 2))
            except Exception:
                self._use_surfarray = False
                self._blit_manual(colors)
        else:
            self._blit_manual(colors)

        return pygame.transform.scale(self.cppn_surf, (self.width, self.height))

    def _blit_manual(self, colors):
        """Fallback: write pixels one by one."""
        for y in range(self.gh):
            for x in range(self.gw):
                c = colors[y, x]
                self.cppn_surf.set_at((x, y), (int(c[0]), int(c[1]), int(c[2])))

    # ═════════════════════════════════════════════════════════════════════════
    #  TEXT FRAGMENTS
    # ═════════════════════════════════════════════════════════════════════════

    def _spawn_frag(self):
        if not self.mem_pool:
            return

        entry = random.choice(self.mem_pool)
        x = random.uniform(20, self.width - 120)
        y = random.uniform(20, self.height - 30)
        vx = random.uniform(-0.15, 0.15)
        vy = random.uniform(-0.15, 0.15)

        self.frags.append({
            "text": entry["text"],
            "emotion": entry["emotion"],
            "x": x, "y": y,
            "vx": vx, "vy": vy,
            "age": 0.0, "life": random.uniform(10.0, 16.0),
        })

    def _update_frags(self, dt):
        alive = []
        for f in self.frags:
            f["age"] += dt
            if f["age"] < f["life"]:
                f["x"] += f["vx"]
                f["y"] += f["vy"]
                f["vx"] *= 0.998
                f["vy"] *= 0.998
                alive.append(f)
        self.frags = alive

    def _get_text_surfaces(self, text, color):
        """Return cached (text_surface, shadow_surface) for the given text+color."""
        key = (text, color)
        if key not in self._text_cache:
            ts = self.font_frag.render(text, True, color)
            sh = self.font_frag.render(text, True, (0, 0, 0))
            self._text_cache[key] = (ts, sh)
        return self._text_cache[key]

    def _draw_frags(self):
        for f in self.frags:
            r = f["age"] / f["life"]
            if r < 0.12:
                a = r / 0.12
            elif r > 0.75:
                a = (1.0 - r) / 0.25
            else:
                a = 1.0
            alpha = max(0, min(255, int(a * 240)))
            if alpha == 0:
                continue

            text_color = _EMOTION_TEXT_COLORS.get(f["emotion"], _EMOTION_TEXT_COLORS["neutral"])
            ts, sh = self._get_text_surfaces(f["text"], text_color)
            ix, iy = int(f["x"]), int(f["y"])

            sh.set_alpha(alpha)
            self.screen.blit(sh, (ix + 1, iy + 1))

            ts.set_alpha(alpha)
            self.screen.blit(ts, (ix, iy))

    # ═════════════════════════════════════════════════════════════════════════
    #  PARTICLES
    # ═════════════════════════════════════════════════════════════════════════

    def _get_glow_surface(self, radius):
        """Return a cached glow surface for the given radius."""
        if radius not in self._glow_cache:
            size = radius * 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 255, 255, 50), (radius, radius), radius)
            self._glow_cache[radius] = surf
        return self._glow_cache[radius]

    def _spawn_particle(self):
        if len(self.particles) >= self.max_particles:
            return
        self.particles.append({
            "x": random.uniform(0, self.width),
            "y": random.uniform(self.height * 0.3, self.height),
            "vx": random.uniform(-0.25, 0.25),
            "vy": random.uniform(-0.7, -0.15),
            "sz": random.randint(2, 3),
            "age": 0.0, "life": random.uniform(5.0, 12.0),
            "bri": random.uniform(0.6, 1.0),
        })

    def _update_particles(self, dt):
        alive = []
        for p in self.particles:
            p["age"] += dt
            if p["age"] < p["life"]:
                p["x"] += p["vx"] + math.sin(p["age"] * 1.8) * 0.15
                p["y"] += p["vy"]
                alive.append(p)
        self.particles = alive
        if random.random() < 0.12:
            self._spawn_particle()

    def _draw_particles(self):
        b = self.bright
        for p in self.particles:
            r = p["age"] / p["life"]
            a = (1.0 - r) * p["bri"] if r > 0.1 else (r / 0.1) * p["bri"]
            if a <= 0.02:
                continue
            color = (
                min(255, int(b[0] * a + 70 * a)),
                min(255, int(b[1] * a + 70 * a)),
                min(255, int(b[2] * a + 70 * a)),
            )
            ix, iy = int(p["x"]), int(p["y"])

            # Core dot only — skip glow blit for performance
            pygame.draw.circle(self.screen, color, (ix, iy), p["sz"])

    # ═════════════════════════════════════════════════════════════════════════
    #  LABEL
    # ═════════════════════════════════════════════════════════════════════════

    def _draw_label(self):
        self.label_alpha += self.label_dir * 0.006
        if self.label_alpha >= 1.0:
            self.label_alpha = 1.0
            self.label_dir = -1
        elif self.label_alpha <= 0.15:
            self.label_alpha = 0.15
            self.label_dir = 1

        dots = int(time_mod.time() * 0.7) % 4
        text = "DREAM CYCLE" + "." * dots
        ts = self.font_label.render(text, True, (190, 190, 190))
        ts.set_alpha(int(self.label_alpha * 180))
        self.screen.blit(ts, (self.width - ts.get_width() - 12, self.height - 22))

    # ═════════════════════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═════════════════════════════════════════════════════════════════════════

    def reset(self):
        self.t = random.uniform(0, 100)
        self.frags = []
        self.particles = []
        self._glow_cache = {}
        self._text_cache = {}
        self._cached_bg = None
        self._cppn_counter = 0
        self._palette_check_counter = 0
        self.pulse_active = False
        self.pulse_pos = 0.0
        self.pulse_timer = 0.0
        self.label_alpha = 0.0
        self.label_dir = 1
        self._last = time_mod.time()
        self.next_frag = self._last + 1.5

        self._load_data()
        self._init_cppn()

        # Trigger nightly memory consolidation (runs once per day, background thread)
        try:
            from modules.module_dream import try_dream_consolidation
            try_dream_consolidation()
        except Exception:
            pass

        for _ in range(5):
            self._spawn_particle()

    def update(self):
        now = time_mod.time()
        dt = min(now - self._last, 0.1)
        self._last = now

        self.t += self.t_speed
        self.breathe = math.sin(self.t * 0.15) * 0.5 + 0.5

        # Pulse management
        self.pulse_timer += dt
        if not self.pulse_active and self.pulse_timer > random.uniform(18, 30):
            self.pulse_active = True
            self.pulse_pos = 0.0
            self.pulse_timer = 0.0
        if self.pulse_active:
            self.pulse_pos += dt * 0.6
            if self.pulse_pos > 2.0:
                self.pulse_active = False

        self._update_frags(dt)
        if now >= self.next_frag:
            self._spawn_frag()
            self.next_frag = now + random.uniform(4.5, 7.5)

        self._update_particles(dt)
        self._update_palette(dt)

    def render(self):
        self.screen.fill((0, 0, 0))

        try:
            # 1 — CPPN background (recompute only every N frames)
            self._cppn_counter += 1
            if self._cached_bg is None or self._cppn_counter >= self._cppn_interval:
                self._cppn_counter = 0
                intensity = self._cppn_frame()
                self._cached_bg = self._to_surface(intensity)

            breathe_alpha = int(210 + 45 * math.sin(self.t * 0.3))
            self._cached_bg.set_alpha(breathe_alpha)
            self.screen.blit(self._cached_bg, (0, 0))
        except Exception:
            pass

        # 2 — Particles (dots only, no glow blits)
        self._draw_particles()

        # 3 — Text fragments (emotion-colored)
        self._draw_frags()

        # 4 — Dream label
        self._draw_label()

        # 5 — Time overlay
        if self.show_time and self.time_overlay:
            self.time_overlay.render(self.screen)
