"""
Module: Eyes - Expressive animated robot eyes
Author: Latisha Besariani Hendra
Description: Expressive animated robot eyes for TARS-AI.
             9 moods, blinking, and random idle movement.
"""
import math
import random
import pygame
from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple, Optional


class Mood(Enum):
    """Emotional states for the eyes"""
    NEUTRAL = auto()
    HAPPY = auto()
    SAD = auto()
    ANGRY = auto()
    EXCITED = auto()
    AFRAID = auto()
    SIDEEYE_LEFT = auto()
    SIDEEYE_RIGHT = auto()
    SLEEPY = auto()
    CONFUSED = auto()
    SURPRISED = auto()
    DISGUSTED = auto()
    LOVE = auto()
    SHY = auto()
    ANNOYED = auto()
    CURIOUS = auto()


# Emotion transition speeds (higher = faster)
EMOTION_TRANSITION_SPEEDS = {
    Mood.EXCITED: 8.0,
    Mood.ANGRY: 6.0,
    Mood.HAPPY: 5.0,
    Mood.NEUTRAL: 4.0,
    Mood.SAD: 2.0,
    Mood.SLEEPY: 1.5,
    Mood.AFRAID: 7.0,
    Mood.SIDEEYE_LEFT: 4.0,
    Mood.SIDEEYE_RIGHT: 4.0,
    Mood.CONFUSED: 3.0,
    Mood.SURPRISED: 8.0,
    Mood.DISGUSTED: 4.0,
    Mood.LOVE: 3.0,
    Mood.SHY: 2.5,
    Mood.ANNOYED: 4.0,
    Mood.CURIOUS: 3.5,
}

# Blink intervals per mood (min, max in seconds)
BLINK_INTERVALS = {
    Mood.NEUTRAL: (3.0, 5.0),
    Mood.EXCITED: (1.5, 3.0),
    Mood.HAPPY: (2.5, 4.5),
    Mood.SAD: (4.0, 7.0),
    Mood.SLEEPY: (5.0, 10.0),
    Mood.ANGRY: (2.0, 4.0),
    Mood.AFRAID: (2.0, 3.5),
    Mood.SIDEEYE_LEFT: (3.0, 5.0),
    Mood.SIDEEYE_RIGHT: (3.0, 5.0),
    Mood.CONFUSED: (2.5, 4.5),
    Mood.SURPRISED: (3.0, 6.0),
    Mood.DISGUSTED: (3.0, 5.0),
    Mood.LOVE: (3.5, 6.0),
    Mood.SHY: (2.0, 3.5),
    Mood.ANNOYED: (2.5, 4.0),
    Mood.CURIOUS: (2.0, 4.0),
}

# Mood-specific eye colors
MOOD_COLORS = {
    Mood.NEUTRAL:       (0, 206, 209),
    Mood.HAPPY:         (0, 206, 209),
    Mood.SAD:           (70, 130, 200),
    Mood.ANGRY:         (220, 40, 40),
    Mood.EXCITED:       (255, 220, 50),
    Mood.AFRAID:        (180, 120, 255),
    Mood.SIDEEYE_LEFT:  (0, 206, 209),
    Mood.SIDEEYE_RIGHT: (0, 206, 209),
    Mood.SLEEPY:        (0, 100, 110),
    Mood.CONFUSED:      (255, 200, 50),
    Mood.SURPRISED:     (255, 255, 180),
    Mood.DISGUSTED:     (80, 180, 80),
    Mood.LOVE:          (255, 80, 140),
    Mood.SHY:           (255, 150, 170),
    Mood.ANNOYED:       (255, 130, 40),
    Mood.CURIOUS:       (80, 200, 255),
}


@dataclass
class EyeConfig:
    """Eye visual configuration"""
    width: int = 120
    height: int = 160
    border_radius: int = 30
    space_between: int = 80
    bg_color: Tuple[int, int, int] = (13, 17, 23)
    eye_color: Tuple[int, int, int] = (0, 206, 209)


def smooth_lerp(current: float, target: float, speed: float, dt: float) -> float:
    """Frame-rate independent exponential smoothing"""
    return current + (target - current) * (1.0 - math.exp(-speed * dt))


class RoboEyes:
    """Expressive animated robot eyes for TARS-AI"""

    def __init__(self, screen_width: int = 480, screen_height: int = 800):
        self.screen_width = screen_width
        self.screen_height = screen_height

        scale = min(screen_width, screen_height) / 480
        self.config = EyeConfig(
            width=int(100 * scale),
            height=int(140 * scale),
            border_radius=int(25 * scale),
            space_between=int(150 * scale),
        )

        # Mood
        self._mood = Mood.NEUTRAL
        self._mood_intensity = 1.0
        self._prev_mood = Mood.NEUTRAL
        self._mood_transition_progress = 1.0

        # Look direction
        self._look_x = 0.0
        self._look_y = 0.0
        self._target_look_x = 0.0
        self._target_look_y = 0.0

        # Eyelid positions
        self._lid_top_left = 0.0
        self._lid_top_right = 0.0
        self._lid_bottom_left = 0.0
        self._lid_bottom_right = 0.0
        self._lid_angle_left = 0.0
        self._lid_angle_right = 0.0

        # Curved eyelid state (happy)
        self._curved_bottom_left = False
        self._curved_bottom_right = False
        self._curved_amount_left = 0.0
        self._curved_amount_right = 0.0

        # Eye openness
        self._left_open = 1.0
        self._right_open = 1.0
        self._left_open_target = 1.0
        self._right_open_target = 1.0

        # Pupil / squint
        self._pupil_scale = 1.0
        self._pupil_scale_target = 1.0
        self._squint_intensity = 0.0
        self._squint_target = 0.0
        self._eye_offset_y_left = 0.0
        self._eye_offset_y_right = 0.0

        # Blinking
        self._auto_blink = True
        self._is_blinking = False
        self._blink_phase = 0.0
        self._blink_timer = 0.0
        self._next_blink = self._random_blink_time()
        self._blink_left = True
        self._blink_right = True

        # Idle glances
        self._idle_timer = 0.0
        self._next_idle = self._random_idle_time()

        # Micro-saccades
        self._saccade_timer = 0.0
        self._next_saccade = random.uniform(0.5, 2.0)

        self._anim_offset_x = 0.0
        self._anim_offset_y = 0.0

        # Mood color (smooth transition)
        default_color = MOOD_COLORS[Mood.NEUTRAL]
        self._current_color = [float(default_color[0]), float(default_color[1]), float(default_color[2])]

        # Heart particles for LOVE mood
        self._heart_particles = []  # list of [x, y, size, life, drift_x]
        self._heart_spawn_timer = 0.0

        # Touch reaction system
        self._touch_reaction = None
        self._touch_timer = 0.0
        self._touch_duration = 0.0
        self._touch_phase = 0
        self._pre_touch_mood = None
        self._rapid_tap_count = 0
        self._rapid_tap_timer = 0.0
        self._star_particles = []  # list of [x, y, size, life, angle, speed]

    # ── Blink System ─────────────────────────────────────────────────────────

    def _random_blink_time(self) -> float:
        interval = BLINK_INTERVALS.get(self._mood, (3.0, 5.0))
        return random.uniform(interval[0], interval[1])

    def _random_idle_time(self) -> float:
        return random.uniform(2.0, 5.0)

    def blink(self, both: bool = True, left: bool = True, right: bool = True):
        if both:
            self._blink_left = True
            self._blink_right = True
        else:
            self._blink_left = left
            self._blink_right = right
        self._is_blinking = True
        self._blink_phase = 0.0

    # ── Mood Control ──────────────────────────────────────────────────────────

    def set_mood(self, mood: Mood, intensity: float = 1.0):
        if self._mood != mood:
            self._prev_mood = self._mood
            self._mood_transition_progress = 0.0
            if self._mood in (Mood.SIDEEYE_LEFT, Mood.SIDEEYE_RIGHT):
                self._target_look_x = 0.0
                self._target_look_y = 0.0
                self._left_open_target = 1.0
                self._right_open_target = 1.0
        self._mood = mood
        self._mood_intensity = max(0.0, min(1.0, intensity))
        self._next_blink = self._random_blink_time()

    def set_look(self, x: float, y: float):
        self._target_look_x = max(-1.0, min(1.0, x))
        self._target_look_y = max(-1.0, min(1.0, y))

    def set_pupil_scale(self, scale: float):
        self._pupil_scale_target = max(0.5, min(1.5, scale))

    def set_squint(self, intensity: float):
        self._squint_target = max(0.0, min(1.0, intensity))

    def get_current_mood(self) -> Tuple[Mood, float]:
        return (self._mood, self._mood_intensity)

    # ── Touch Reactions ──────────────────────────────────────────────────────

    def get_eye_rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        """Return approximate bounding rects for left and right eyes."""
        center_y = self.screen_height // 2
        left_x = (self.screen_width - self.config.space_between) // 2 - self.config.width // 2
        right_x = (self.screen_width + self.config.space_between) // 2 - self.config.width // 2
        h = self.config.height
        pad = int(self.config.width * 0.3)
        left_rect = pygame.Rect(left_x - pad, center_y - h // 2 - pad, self.config.width + pad * 2, h + pad * 2)
        right_rect = pygame.Rect(right_x - pad, center_y - h // 2 - pad, self.config.width + pad * 2, h + pad * 2)
        return left_rect, right_rect

    def handle_touch(self, x: int, y: int) -> Optional[str]:
        """Handle a touch/click at screen position. Returns reaction name or None."""
        if self._touch_reaction is not None:
            return None

        # Track rapid tapping
        self._rapid_tap_count += 1
        self._rapid_tap_timer = 0.0

        if self._rapid_tap_count >= 5:
            self._rapid_tap_count = 0
            self._start_touch_reaction('dizzy')
            return 'dizzy'

        left_rect, right_rect = self.get_eye_rects()
        center_y = self.screen_height // 2
        between_x_min = left_rect.right
        between_x_max = right_rect.left

        if left_rect.collidepoint(x, y):
            self._start_touch_reaction('poke_left')
            return 'poke_left'
        elif right_rect.collidepoint(x, y):
            self._start_touch_reaction('poke_right')
            return 'poke_right'
        elif between_x_min <= x <= between_x_max and abs(y - center_y) < self.config.height:
            self._start_touch_reaction('boop_nose')
            return 'boop_nose'
        elif y < center_y - self.config.height:
            self._start_touch_reaction('forehead_tap')
            return 'forehead_tap'
        elif y > center_y + self.config.height:
            self._start_touch_reaction('chin_tap')
            return 'chin_tap'
        else:
            self._start_touch_reaction('poke_face')
            return 'poke_face'

    def _start_touch_reaction(self, reaction: str):
        """Begin a touch reaction animation."""
        self._pre_touch_mood = self._mood
        self._touch_reaction = reaction
        self._touch_timer = 0.0
        self._touch_phase = 0

        if reaction == 'poke_left':
            self._touch_duration = 1.2
        elif reaction == 'poke_right':
            self._touch_duration = 1.2
        elif reaction == 'boop_nose':
            self._touch_duration = 1.5
        elif reaction == 'forehead_tap':
            self._touch_duration = 1.0
        elif reaction == 'chin_tap':
            self._touch_duration = 1.0
        elif reaction == 'poke_face':
            self._touch_duration = 0.8
            self._touch_phase = random.choice([-1, 1])  # flinch direction
        elif reaction == 'dizzy':
            self._touch_duration = 3.0
            # Spawn star particles around the eyes
            cx, cy = self.screen_width // 2, self.screen_height // 2
            for _ in range(8):
                angle = random.uniform(0, math.pi * 2)
                self._star_particles.append([
                    cx + math.cos(angle) * 60,
                    cy + math.sin(angle) * 40,
                    random.uniform(8, 14),
                    0.0,
                    angle,
                    random.uniform(20, 50),
                ])

    def _update_touch_reaction(self, dt: float):
        """Update the active touch reaction animation."""
        if self._touch_reaction is None:
            # Decay rapid tap counter
            self._rapid_tap_timer += dt
            if self._rapid_tap_timer > 1.0:
                self._rapid_tap_count = max(0, self._rapid_tap_count - 1)
                self._rapid_tap_timer = 0.0
            return

        self._touch_timer += dt
        progress = min(1.0, self._touch_timer / self._touch_duration)
        reaction = self._touch_reaction

        if reaction == 'poke_left':
            # Left eye closes, flinch away, shake
            if progress < 0.15:
                self._left_open_target = 0.0
                self._anim_offset_x = 8
            elif progress < 0.5:
                self._left_open_target = 0.0
                self._right_open_target = 1.3
                self._target_look_x = 0.8
                self._anim_offset_x = math.sin(self._touch_timer * 40) * 5
            elif progress < 0.8:
                self._left_open_target = 0.4
                self._right_open_target = 1.0
                self._anim_offset_x = math.sin(self._touch_timer * 20) * 2
                self._target_look_x = 0.3
            else:
                self._left_open_target = 1.0
                self._right_open_target = 1.0
                self._target_look_x = 0.0
                self._anim_offset_x *= 0.8

        elif reaction == 'poke_right':
            if progress < 0.15:
                self._right_open_target = 0.0
                self._anim_offset_x = -8
            elif progress < 0.5:
                self._right_open_target = 0.0
                self._left_open_target = 1.3
                self._target_look_x = -0.8
                self._anim_offset_x = math.sin(self._touch_timer * 40) * 5
            elif progress < 0.8:
                self._right_open_target = 0.4
                self._left_open_target = 1.0
                self._anim_offset_x = math.sin(self._touch_timer * 20) * 2
                self._target_look_x = -0.3
            else:
                self._right_open_target = 1.0
                self._left_open_target = 1.0
                self._target_look_x = 0.0
                self._anim_offset_x *= 0.8

        elif reaction == 'boop_nose':
            # Cross-eyed, then surprised, then giggle shake
            if progress < 0.3:
                self._target_look_x = 0.0
                self._target_look_y = 0.5
                self._left_open_target = 1.2
                self._right_open_target = 1.2
                self._pupil_scale_target = 0.7
            elif progress < 0.6:
                self._target_look_x = 0.0
                self._target_look_y = 0.0
                self._left_open_target = 1.4
                self._right_open_target = 1.4
                self._pupil_scale_target = 0.6
                self._anim_offset_y = math.sin(self._touch_timer * 30) * 4
            else:
                self._left_open_target = 0.85
                self._right_open_target = 0.85
                self._pupil_scale_target = 1.0
                self._anim_offset_y = math.sin(self._touch_timer * 25) * 3 * (1.0 - progress)

        elif reaction == 'forehead_tap':
            # Annoyed look - eyelids droop, eyes look up at the finger
            if progress < 0.2:
                self._target_look_y = -0.9
                self._left_open_target = 0.7
                self._right_open_target = 0.7
            elif progress < 0.7:
                self._target_look_y = -0.9
                self._squint_target = 0.4
                self._left_open_target = 0.6
                self._right_open_target = 0.6
            else:
                self._target_look_y = 0.0
                self._squint_target = 0.0
                self._left_open_target = 1.0
                self._right_open_target = 1.0

        elif reaction == 'chin_tap':
            # Surprised look up, then curious
            if progress < 0.3:
                self._target_look_y = 0.8
                self._left_open_target = 1.4
                self._right_open_target = 1.4
                self._anim_offset_y = -6
            elif progress < 0.7:
                self._target_look_y = 0.5
                self._left_open_target = 1.2
                self._right_open_target = 0.9
                self._anim_offset_y = -3
            else:
                self._target_look_y = 0.0
                self._left_open_target = 1.0
                self._right_open_target = 1.0
                self._anim_offset_y *= 0.8

        elif reaction == 'poke_face':
            # Quick flinch and blink
            if progress < 0.3:
                self._left_open_target = 0.2
                self._right_open_target = 0.2
                self._anim_offset_x = self._touch_phase * 5
            elif progress < 0.6:
                self._left_open_target = 1.0
                self._right_open_target = 1.0
                self._anim_offset_x *= 0.7
            else:
                self._anim_offset_x *= 0.8

        elif reaction == 'dizzy':
            # Spinning eyes, wobbly, stars
            spin_speed = 4.0 if progress < 0.7 else 2.0
            angle = self._touch_timer * spin_speed
            self._target_look_x = math.sin(angle) * 0.7
            self._target_look_y = math.cos(angle) * 0.5
            wobble = math.sin(self._touch_timer * 6) * 8 * (1.0 - progress)
            self._anim_offset_x = wobble
            self._anim_offset_y = math.sin(self._touch_timer * 4) * 5 * (1.0 - progress)
            # Asymmetric eye sizes for dazed look
            self._left_open_target = 0.7 + math.sin(self._touch_timer * 3) * 0.3
            self._right_open_target = 0.7 + math.cos(self._touch_timer * 3) * 0.3

            # Update star particles
            for s in self._star_particles:
                s[3] += dt
                s[4] += 1.5 * dt  # orbit
                radius = 70 + s[5] * s[3] * 0.3
                cx, cy = self.screen_width // 2, self.screen_height // 2
                s[0] = cx + math.cos(s[4]) * radius
                s[1] = cy + math.sin(s[4]) * radius * 0.6
                s[2] *= 0.997
            self._star_particles = [s for s in self._star_particles if s[3] < self._touch_duration]

        # End reaction
        if progress >= 1.0:
            self._touch_reaction = None
            self._touch_timer = 0.0
            self._touch_phase = 0
            self._anim_offset_x = 0.0
            self._anim_offset_y = 0.0
            self._squint_target = 0.0
            self._pupil_scale_target = 1.0
            self._target_look_x = 0.0
            self._target_look_y = 0.0
            self._left_open_target = 1.0
            self._right_open_target = 1.0
            self._eye_offset_y_left = 0.0
            self._eye_offset_y_right = 0.0
            self._star_particles.clear()
            if self._pre_touch_mood is not None:
                self.set_mood(self._pre_touch_mood)
                self._pre_touch_mood = None

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        # Touch reactions (override normal behavior while active)
        self._update_touch_reaction(dt)

        # Auto-blink
        if self._auto_blink and self._touch_reaction is None:
            self._blink_timer += dt
            if self._blink_timer >= self._next_blink:
                self.blink()
                self._blink_timer = 0
                self._next_blink = self._random_blink_time()

        # Blink animation
        if self._is_blinking:
            self._blink_phase += dt * 12
            if self._blink_phase < 0.5:
                if self._blink_left:
                    self._left_open_target = 0.0
                if self._blink_right:
                    self._right_open_target = 0.0
            else:
                if self._blink_left:
                    self._left_open_target = 1.0
                if self._blink_right:
                    self._right_open_target = 1.0
            if self._blink_phase >= 1.0:
                self._is_blinking = False
                self._blink_left = True
                self._blink_right = True

        # Idle glances (skip during touch reactions)
        if self._touch_reaction is None:
            self._idle_timer += dt
            if self._idle_timer >= self._next_idle:
                self._target_look_x = random.uniform(-0.5, 0.5)
                self._target_look_y = random.uniform(-0.3, 0.2)
                self._idle_timer = 0
                self._next_idle = self._random_idle_time()

        # Micro-saccades (skip during touch reactions)
        if self._touch_reaction is None:
            self._saccade_timer += dt
            if self._saccade_timer >= self._next_saccade:
                offset = random.uniform(-0.05, 0.05)
                self._target_look_x = max(-1.0, min(1.0, self._target_look_x + offset))
                self._saccade_timer = 0
                self._next_saccade = random.uniform(0.5, 2.0)

        if self._touch_reaction is None:
            self._update_mood(dt)

        speed = EMOTION_TRANSITION_SPEEDS.get(self._mood, 6.0)

        if self._mood_transition_progress < 1.0:
            self._mood_transition_progress = min(1.0, self._mood_transition_progress + dt * 2.0)

        self._look_x = smooth_lerp(self._look_x, self._target_look_x, 8.0, dt)
        self._look_y = smooth_lerp(self._look_y, self._target_look_y, 8.0, dt)
        self._left_open = smooth_lerp(self._left_open, self._left_open_target, speed, dt)
        self._right_open = smooth_lerp(self._right_open, self._right_open_target, speed, dt)
        self._pupil_scale = smooth_lerp(self._pupil_scale, self._pupil_scale_target, 10.0, dt)
        self._squint_intensity = smooth_lerp(self._squint_intensity, self._squint_target, 6.0, dt)

        # Smooth mood color transition
        target_color = MOOD_COLORS.get(self._mood, MOOD_COLORS[Mood.NEUTRAL])
        for i in range(3):
            self._current_color[i] = smooth_lerp(self._current_color[i], float(target_color[i]), 4.0, dt)

        # Heart particles (LOVE mood)
        if self._mood == Mood.LOVE:
            self._heart_spawn_timer += dt
            if self._heart_spawn_timer >= 0.8 and len(self._heart_particles) < 6:
                cx = self.screen_width // 2
                cy = self.screen_height // 2
                self._heart_particles.append([
                    cx + random.uniform(-60, 60),   # x
                    cy + random.uniform(-20, 20),    # y
                    random.uniform(10, 18),           # size
                    0.0,                              # life
                    random.uniform(-15, 15),          # drift_x
                ])
                self._heart_spawn_timer = 0.0
        else:
            self._heart_spawn_timer = 0.0

        # Update heart particles
        for h in self._heart_particles:
            h[3] += dt           # life
            h[1] -= 50 * dt     # float upward
            h[0] += h[4] * dt   # horizontal drift
            h[2] *= 0.995       # shrink slowly
        self._heart_particles = [h for h in self._heart_particles if h[3] < 2.5]

    def _update_mood(self, dt: float):
        target_top_l = 0.0
        target_top_r = 0.0
        target_bot_l = 0.0
        target_bot_r = 0.0
        target_angle_l = 0.0
        target_angle_r = 0.0
        target_curve_l = 0.0
        target_curve_r = 0.0
        use_curved_bottom = False

        h = self.config.height * 0.5
        intensity = self._mood_intensity

        if self._mood == Mood.HAPPY:
            use_curved_bottom = True
            target_curve_l = 0.48
            target_curve_r = 0.48
            self._left_open_target = 0.85
            self._right_open_target = 0.85

        elif self._mood == Mood.EXCITED:
            use_curved_bottom = True
            target_curve_l = 0.48
            target_curve_r = 0.48
            self._left_open_target = 1.0
            self._right_open_target = 1.0
            shake = math.sin(pygame.time.get_ticks() * 0.02) * 8
            self._anim_offset_y = shake

        elif self._mood == Mood.SAD:
            target_top_l = h * 0.5 * intensity
            target_top_r = h * 0.5 * intensity
            target_angle_l = 15 * intensity
            target_angle_r = -15 * intensity
            self._left_open_target = 0.8
            self._right_open_target = 0.8
            self._anim_offset_y = math.sin(pygame.time.get_ticks() * 0.002) * 3

        elif self._mood == Mood.AFRAID:
            target_top_l = h * 0.5 * intensity
            target_top_r = h * 0.5 * intensity
            target_angle_l = 15 * intensity
            target_angle_r = -15 * intensity
            self._left_open_target = 0.8
            self._right_open_target = 0.8
            shake = math.sin(pygame.time.get_ticks() * 0.03) * 6
            self._anim_offset_x = shake

        elif self._mood == Mood.SIDEEYE_LEFT:
            self._left_open_target = 1.3
            self._right_open_target = 0.8
            self._target_look_x = -0.9

        elif self._mood == Mood.SIDEEYE_RIGHT:
            self._left_open_target = 0.8
            self._right_open_target = 1.3
            self._target_look_x = 0.9

        elif self._mood == Mood.ANGRY:
            target_top_l = h * 0.5 * intensity
            target_top_r = h * 0.5 * intensity
            target_angle_l = -30 * intensity
            target_angle_r = 30 * intensity
            self._left_open_target = 1.0
            self._right_open_target = 1.0
            # Red pulsing glow
            pulse = math.sin(pygame.time.get_ticks() * 0.005) * 0.15
            base = MOOD_COLORS[Mood.ANGRY]
            self._current_color = [min(255, base[0] + pulse * 60), base[1], base[2]]

        elif self._mood == Mood.SLEEPY:
            self._left_open_target = 0.1
            self._right_open_target = 0.1

        elif self._mood == Mood.CONFUSED:
            # Asymmetric eyes — one raised eyebrow, slight tilt
            target_top_l = h * 0.35 * intensity
            target_angle_l = 20 * intensity
            target_angle_r = -10 * intensity
            self._left_open_target = 0.7
            self._right_open_target = 1.1
            self._eye_offset_y_left = -5 * intensity
            self._eye_offset_y_right = 5 * intensity
            self._anim_offset_x = math.sin(pygame.time.get_ticks() * 0.004) * 4

        elif self._mood == Mood.SURPRISED:
            # Wide open eyes, raised
            self._left_open_target = 1.4
            self._right_open_target = 1.4
            self._pupil_scale_target = 0.75
            self._eye_offset_y_left = -8 * intensity
            self._eye_offset_y_right = -8 * intensity

        elif self._mood == Mood.DISGUSTED:
            # Squinted eyes, slight look away, bottom lids raised
            target_bot_l = h * 0.25 * intensity
            target_bot_r = h * 0.25 * intensity
            target_angle_l = -10 * intensity
            target_angle_r = 10 * intensity
            self._left_open_target = 0.6
            self._right_open_target = 0.6
            self._squint_target = 0.4 * intensity
            self._target_look_x = -0.3

        elif self._mood == Mood.LOVE:
            # Dreamy half-lidded eyes, soft upward gaze, curved bottom lids
            target_bot_l = h * 0.15 * intensity
            target_bot_r = h * 0.15 * intensity
            target_curve_l = 1.0 * intensity
            target_curve_r = 1.0 * intensity
            use_curved_bottom = True
            self._left_open_target = 0.75
            self._right_open_target = 0.75
            self._pupil_scale_target = 1.3
            self._eye_offset_y_left = -4 * intensity
            self._eye_offset_y_right = -4 * intensity

        elif self._mood == Mood.SHY:
            # Eyes looking down, partially closed, slight asymmetry
            target_top_l = h * 0.2 * intensity
            target_top_r = h * 0.15 * intensity
            self._left_open_target = 0.5
            self._right_open_target = 0.55
            self._eye_offset_y_left = 10 * intensity
            self._eye_offset_y_right = 10 * intensity
            self._target_look_x = -0.2
            self._pupil_scale_target = 0.85

        elif self._mood == Mood.ANNOYED:
            # Mild squint, one eyebrow lower, less intense than ANGRY
            target_top_l = h * 0.3 * intensity
            target_top_r = h * 0.15 * intensity
            target_angle_l = -15 * intensity
            target_angle_r = 8 * intensity
            self._left_open_target = 0.8
            self._right_open_target = 0.9
            self._squint_target = 0.2 * intensity
            self._target_look_x = 0.15

        elif self._mood == Mood.CURIOUS:
            # One eye wider, slight head tilt, looking to the side
            target_angle_l = 10 * intensity
            target_angle_r = -5 * intensity
            self._left_open_target = 1.3
            self._right_open_target = 0.9
            self._pupil_scale_target = 1.15
            self._target_look_x = 0.4
            self._eye_offset_y_left = -6 * intensity
            self._eye_offset_y_right = 2 * intensity

        self._curved_bottom_left = use_curved_bottom
        self._curved_bottom_right = use_curved_bottom

        speed = EMOTION_TRANSITION_SPEEDS.get(self._mood, 4.0)
        self._lid_top_left = smooth_lerp(self._lid_top_left, target_top_l, speed, dt)
        self._lid_top_right = smooth_lerp(self._lid_top_right, target_top_r, speed, dt)
        self._lid_bottom_left = smooth_lerp(self._lid_bottom_left, target_bot_l, speed, dt)
        self._lid_bottom_right = smooth_lerp(self._lid_bottom_right, target_bot_r, speed, dt)
        self._lid_angle_left = smooth_lerp(self._lid_angle_left, target_angle_l, speed, dt)
        self._lid_angle_right = smooth_lerp(self._lid_angle_right, target_angle_r, speed, dt)
        self._curved_amount_left = smooth_lerp(self._curved_amount_left, target_curve_l, speed, dt)
        self._curved_amount_right = smooth_lerp(self._curved_amount_right, target_curve_r, speed, dt)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface):
        center_y = self.screen_height // 2
        left_x = (self.screen_width - self.config.space_between) // 2 - self.config.width // 2
        right_x = (self.screen_width + self.config.space_between) // 2 - self.config.width // 2

        self._draw_eye(surface, left_x, center_y, True,
                       curved_bottom=self._curved_bottom_left,
                       curve_amount=self._curved_amount_left)
        self._draw_eye(surface, right_x, center_y, False,
                       curved_bottom=self._curved_bottom_right,
                       curve_amount=self._curved_amount_right)

        self._draw_effects(surface)

    def _draw_curved_bottom_lid(self, surface: pygame.Surface, x: int, y: int, w: int, h: int, curve_amount: float):
        if curve_amount < 0.01:
            return
        cfg = self.config
        points = []
        num_points = 20
        curve_height = h * 0.5 * curve_amount
        for i in range(num_points + 1):
            t = i / num_points
            px = x + t * w
            curve = math.sin(t * math.pi)
            py = y + h * 0.75 - (curve * curve_height)
            points.append((px, py))
        points.append((x + w + 5, y + h + 20))
        points.append((x - 5, y + h + 20))
        pygame.draw.polygon(surface, cfg.bg_color, points)

    def _draw_eye(self, surface: pygame.Surface, x: int, y: int, is_left: bool,
                  curved_bottom: bool = False, curve_amount: float = 0.0):
        look_offset_x = int(self._look_x * self.config.width * 0.3)
        look_offset_y = int(self._look_y * self.config.height * 0.3)
        anim_x = int(self._anim_offset_x)
        anim_y = int(self._anim_offset_y)
        offset_y = int(self._eye_offset_y_left if is_left else self._eye_offset_y_right)

        total_x = x + look_offset_x + anim_x
        total_y = y + look_offset_y + anim_y + offset_y

        openness = self._left_open if is_left else self._right_open

        eye_height = int(self.config.height * openness)
        eye_rect = pygame.Rect(
            total_x,
            total_y - eye_height // 2,
            self.config.width,
            eye_height,
        )
        border_radius = min(self.config.border_radius, self.config.width // 2, max(1, eye_height // 2))
        eye_color = (int(self._current_color[0]), int(self._current_color[1]), int(self._current_color[2]))
        pygame.draw.rect(surface, eye_color, eye_rect, border_radius=border_radius)

        lid_color = self.config.bg_color

        # Top lid
        lid_top = self._lid_top_left if is_left else self._lid_top_right
        lid_angle = self._lid_angle_left if is_left else self._lid_angle_right
        if lid_top > 1:
            top_y = total_y - eye_height // 2
            if abs(lid_angle) > 1:
                if is_left:
                    if lid_angle < 0:
                        points = [
                            (total_x, top_y - 1),
                            (total_x + self.config.width, top_y - 1),
                            (total_x + self.config.width, top_y + int(lid_top)),
                        ]
                    else:
                        points = [
                            (total_x, top_y - 1),
                            (total_x + self.config.width, top_y - 1),
                            (total_x, top_y + int(lid_top)),
                        ]
                else:
                    if lid_angle > 0:
                        points = [
                            (total_x, top_y - 1),
                            (total_x + self.config.width, top_y - 1),
                            (total_x, top_y + int(lid_top)),
                        ]
                    else:
                        points = [
                            (total_x, top_y - 1),
                            (total_x + self.config.width, top_y - 1),
                            (total_x + self.config.width, top_y + int(lid_top)),
                        ]
                pygame.draw.polygon(surface, lid_color, points)
            else:
                pygame.draw.rect(surface, lid_color,
                                 (total_x - 2, top_y - 2, self.config.width + 4, int(lid_top) + 2))

        # Bottom lid
        lid_bottom = self._lid_bottom_left if is_left else self._lid_bottom_right
        if curved_bottom and curve_amount > 0.01:
            self._draw_curved_bottom_lid(surface, total_x, total_y - eye_height // 2,
                                         self.config.width, eye_height, curve_amount)
        elif lid_bottom > 1:
            lid_h = int(lid_bottom)
            lid_rect = pygame.Rect(total_x - 2, total_y + eye_height - int(lid_bottom),
                                   self.config.width + 4, lid_h + 10)
            pygame.draw.rect(surface, lid_color, lid_rect)

    @staticmethod
    def _draw_heart(surface: pygame.Surface, cx: int, cy: int, size: int, color):
        """Draw a heart shape at (cx, cy) with given size."""
        r = max(1, size // 3)
        # Two circles for the top bumps
        pygame.draw.circle(surface, color, (cx - r, cy - r // 2), r)
        pygame.draw.circle(surface, color, (cx + r, cy - r // 2), r)
        # Triangle for the bottom point
        points = [
            (cx - size // 2 - 1, cy),
            (cx + size // 2 + 1, cy),
            (cx, cy + int(size * 0.7)),
        ]
        pygame.draw.polygon(surface, color, points)

    @staticmethod
    def _draw_star(surface: pygame.Surface, cx: int, cy: int, size: int, color):
        """Draw a 4-pointed star at (cx, cy)."""
        points = []
        for i in range(8):
            angle = i * math.pi / 4 - math.pi / 2
            r = size if i % 2 == 0 else size * 0.4
            points.append((cx + int(math.cos(angle) * r), cy + int(math.sin(angle) * r)))
        if len(points) >= 3:
            pygame.draw.polygon(surface, color, points)

    def _draw_effects(self, surface: pygame.Surface):
        """Draw mood overlay effects (hearts, etc.)."""
        for h in self._heart_particles:
            x, y, size, life = int(h[0]), int(h[1]), int(h[2]), h[3]
            if size < 2:
                continue
            # Fade: full pink at birth, dimmer as life increases
            fade = max(0.0, 1.0 - life / 2.5)
            r = int(255 * fade)
            g = int(80 * fade)
            b = int(140 * fade)
            self._draw_heart(surface, x, y, size, (r, g, b))

        # Star particles (dizzy touch reaction)
        for s in self._star_particles:
            sx, sy, size, life = int(s[0]), int(s[1]), int(s[2]), s[3]
            if size < 2:
                continue
            fade = max(0.0, 1.0 - life / 3.0)
            color = (int(255 * fade), int(255 * fade), int(50 * fade))
            self._draw_star(surface, sx, sy, size, color)
