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

        # Animation system
        self._current_animation = None
        self._anim_timer = 0.0
        self._anim_duration = 0.0
        self._anim_phase = 0.0

        # Legacy animations
        self._anim_laugh = False
        self._anim_laugh_timer = 0.0
        self._anim_confused = False
        self._anim_confused_timer = 0.0
        self._anim_offset_x = 0.0
        self._anim_offset_y = 0.0

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

    # ── Animation Sequences ───────────────────────────────────────────────────

    def is_animating(self) -> bool:
        return self._current_animation is not None

    def anim_wink(self, eye: str = 'right'):
        self._current_animation = 'wink'
        self._anim_timer = 0.0
        self._anim_duration = 0.3
        self._blink_left = (eye == 'left')
        self._blink_right = (eye == 'right')

    def anim_double_take(self):
        self._current_animation = 'double_take'
        self._anim_timer = 0.0
        self._anim_duration = 1.5
        self._anim_phase = 0

    def anim_eye_roll(self):
        self._current_animation = 'eye_roll'
        self._anim_timer = 0.0
        self._anim_duration = 2.0

    def anim_excited(self):
        self._current_animation = 'excited'
        self._anim_timer = 0.0
        self._anim_duration = 0.8

    def anim_sleepy(self):
        self._current_animation = 'sleepy'
        self._anim_timer = 0.0
        self._anim_duration = 2.0

    def anim_thinking(self):
        self._current_animation = 'thinking'
        self._anim_timer = 0.0
        self._anim_duration = 2.5
        self._anim_phase = 0

    def anim_blink_fast(self):
        self._current_animation = 'blink_fast'
        self._anim_timer = 0.0
        self._anim_duration = 0.4
        self._anim_phase = 0

    def anim_squint_suspicious(self):
        self._current_animation = 'squint_suspicious'
        self._anim_timer = 0.0
        self._anim_duration = 1.5

    def anim_laugh(self):
        self._anim_laugh = True
        self._anim_laugh_timer = 0.5

    def anim_confused(self):
        self._anim_confused = True
        self._anim_confused_timer = 0.5

    def get_current_mood(self) -> Tuple[Mood, float]:
        return (self._mood, self._mood_intensity)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        # Auto-blink
        if self._auto_blink:
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

        # Idle glances
        self._idle_timer += dt
        if self._idle_timer >= self._next_idle:
            self._target_look_x = random.uniform(-0.5, 0.5)
            self._target_look_y = random.uniform(-0.3, 0.2)
            self._idle_timer = 0
            self._next_idle = self._random_idle_time()

        # Micro-saccades
        self._saccade_timer += dt
        if self._saccade_timer >= self._next_saccade:
            offset = random.uniform(-0.05, 0.05)
            self._target_look_x = max(-1.0, min(1.0, self._target_look_x + offset))
            self._saccade_timer = 0
            self._next_saccade = random.uniform(0.5, 2.0)

        self._update_animations(dt)
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

    def _update_animations(self, dt: float):
        if self._current_animation is None:
            if self._anim_laugh:
                self._anim_laugh_timer -= dt
                self._anim_offset_y = math.sin(self._anim_laugh_timer * 50) * 5
                if self._anim_laugh_timer <= 0:
                    self._anim_laugh = False
                    self._anim_offset_y = 0
            if self._anim_confused:
                self._anim_confused_timer -= dt
                self._anim_offset_x = math.sin(self._anim_confused_timer * 50) * 5
                if self._anim_confused_timer <= 0:
                    self._anim_confused = False
                    self._anim_offset_x = 0
            return

        self._anim_timer += dt
        progress = min(1.0, self._anim_timer / self._anim_duration)

        if self._current_animation == 'wink':
            if progress < 0.5:
                self._is_blinking = True
                self._blink_phase = progress * 2
            else:
                self._is_blinking = False

        elif self._current_animation == 'double_take':
            if progress < 0.3:
                self._target_look_x = 0.8
            elif progress < 0.35:
                self._target_look_x = 0.0
            elif progress < 0.6:
                self._left_open_target = 1.3
                self._right_open_target = 1.3
            else:
                self._left_open_target = 1.0
                self._right_open_target = 1.0

        elif self._current_animation == 'eye_roll':
            angle = progress * 3.14159 * 2
            self._target_look_x = math.sin(angle) * 0.6
            self._target_look_y = -math.cos(angle) * 0.6 - 0.3

        elif self._current_animation == 'excited':
            bounce = math.sin(progress * 3.14159 * 4) * 0.3
            self._anim_offset_y = -abs(bounce) * 10
            self._left_open_target = 1.3
            self._right_open_target = 1.3

        elif self._current_animation == 'sleepy':
            if progress < 0.7:
                self._left_open_target = 1.0 - progress / 0.7
                self._right_open_target = 1.0 - progress / 0.7
            else:
                self._left_open_target = 1.0
                self._right_open_target = 1.0

        elif self._current_animation == 'thinking':
            cycle = int(progress * 3)
            if cycle == 0:
                self._target_look_x = -0.4
                self._target_look_y = -0.6
            elif cycle == 1:
                self._target_look_x = 0.4
                self._target_look_y = -0.6
            else:
                self._target_look_x = 0.0
                self._target_look_y = 0.0
            self._squint_target = 0.2

        elif self._current_animation == 'blink_fast':
            blink_cycle = int(progress * 4) % 2
            if blink_cycle == 0:
                self._left_open_target = 0.0
                self._right_open_target = 0.0
            else:
                self._left_open_target = 1.0
                self._right_open_target = 1.0

        elif self._current_animation == 'squint_suspicious':
            self._squint_target = progress * 0.7
            self._target_look_x = math.sin(progress * 3.14159) * 0.3

        if progress >= 1.0:
            self._current_animation = None
            self._anim_timer = 0.0
            self._anim_offset_x = 0.0
            self._anim_offset_y = 0.0
            self._squint_target = 0.0

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

        elif self._mood == Mood.SLEEPY:
            self._left_open_target = 0.1
            self._right_open_target = 0.1

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
        pygame.draw.rect(surface, self.config.eye_color, eye_rect, border_radius=border_radius)

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
