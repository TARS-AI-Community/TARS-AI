"""
Module: Avatar App
Description: Pygame app that renders the character avatar with animated blinking
             and talking-state mouth movement — mirrors the holo.html endpoint
             behavior but runs locally on the OpenGL/Pygame display.
             Follows the TARS-AI app framework (init/reset/update/render/cleanup).
"""

import os
import time
import random
import pygame

# ---------------------------------------------------------------------------
# Module-level state — set by module_chatui to drive the animation
# ---------------------------------------------------------------------------
_talking_state: bool = False
_emotion_request: str | None = None


def set_talking_state(is_talking: bool) -> None:
    """Signal whether TARS is currently speaking (called from module_chatui)."""
    global _talking_state
    _talking_state = is_talking


def set_emotion_request(emotion: str) -> None:
    """Queue an emotion change to be applied on the next update tick."""
    global _emotion_request
    _emotion_request = emotion


# ---------------------------------------------------------------------------
# Sprite key → filename suffix mapping (matches chatui _get_sprite_urls)
# ---------------------------------------------------------------------------
_SPRITE_KEYS = {
    "nottalking_open":   "nottalking_eyes_open",
    "nottalking_closed": "nottalking_eyes_closed",
    "talking_open":      "talking_eyes_open",
    "talking_closed":    "talking_eyes_closed",
}


class AvatarApp:
    """Animated character avatar for the local TARS display."""

    def __init__(self, screen: pygame.Surface, width: int, height: int) -> None:
        self.screen = screen
        self.width = width
        self.height = height

        # Derive src/ base dir: this file lives at src/modules/UI/apps/
        self._base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )

        # Read character name from config
        try:
            from modules.module_config import load_config
            config = load_config()
            char_path = config["CHAR"]["character_card_path"]
            self._char_name = os.path.splitext(os.path.basename(char_path))[0]
        except Exception:
            self._char_name = "TARS"

        # Load initial sprites
        self._emotion = "neutral"
        self._sprites: dict[str, pygame.Surface | None] = {}
        self._load_sprites(self._emotion)

        # Animation state
        self._is_talking = False
        self._is_blinking = False
        self._next_blink = time.time() + 3.0 + random.random() * 2.0
        self._blink_end = 0.0
        self._talk_frame_timer = 0.0
        self._talk_frame_interval = 0.1   # seconds between mouth frames
        self._mouth_open = True

        # Cached scaled frame
        self._current_surf: pygame.Surface | None = None
        self._render_rect: pygame.Rect | None = None
        self._update_frame()

    # ------------------------------------------------------------------
    # Sprite loading
    # ------------------------------------------------------------------

    def _sprite_path(self, emotion: str, key: str) -> str:
        suffix = _SPRITE_KEYS[key]
        filename = f"{self._char_name}_{emotion}_{suffix}.png"
        return os.path.join(
            self._base_dir, "character", self._char_name,
            "images", emotion, "animation", filename
        )

    def _load_sprites(self, emotion: str) -> None:
        """Load all 4 sprite surfaces for *emotion*, falling back to neutral."""
        emo_dir = os.path.join(
            self._base_dir, "character", self._char_name,
            "images", emotion, "animation"
        )
        if not os.path.isdir(emo_dir):
            emotion = "neutral"

        sprites: dict[str, pygame.Surface | None] = {}
        for key in _SPRITE_KEYS:
            path = self._sprite_path(emotion, key)
            if os.path.isfile(path):
                try:
                    sprites[key] = pygame.image.load(path).convert_alpha()
                except Exception:
                    sprites[key] = None
            else:
                sprites[key] = None

        self._sprites = sprites
        self._emotion = emotion

    # ------------------------------------------------------------------
    # Frame selection (same logic as holo.html updateAvatarFrame)
    # ------------------------------------------------------------------

    def _frame_key(self) -> str:
        if self._is_talking:
            if self._is_blinking:
                return "talking_closed"
            return "talking_open" if self._mouth_open else "nottalking_open"
        return "nottalking_closed" if self._is_blinking else "nottalking_open"

    def _update_frame(self) -> None:
        """Resolve the current frame and cache a scaled version."""
        fallback_order = (
            self._frame_key(),
            "nottalking_open",
            "talking_open",
            "nottalking_closed",
            "talking_closed",
        )
        surf = None
        for k in fallback_order:
            surf = self._sprites.get(k)
            if surf is not None:
                break

        if surf is None:
            self._current_surf = None
            self._render_rect = None
            return

        img_w, img_h = surf.get_size()
        scale = min(self.width / img_w, self.height / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        scaled = pygame.transform.smoothscale(surf, (new_w, new_h))
        self._current_surf = scaled
        toolbar_h = int(self.height * 0.06)
        x = (self.width - new_w) // 2
        y = self.height - toolbar_h - new_h
        self._render_rect = scaled.get_rect(topleft=(x, y))

    # ------------------------------------------------------------------
    # App framework interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        global _talking_state
        _talking_state = False
        self._is_talking = False
        self._is_blinking = False
        self._next_blink = time.time() + 3.0 + random.random() * 2.0
        self._blink_end = 0.0
        self._mouth_open = True
        self._update_frame()

    def update(self) -> None:
        global _talking_state, _emotion_request
        now = time.time()

        # Emotion change
        if _emotion_request is not None:
            emo = _emotion_request
            _emotion_request = None
            if emo != self._emotion:
                self._load_sprites(emo)

        # Talking state
        new_talking = _talking_state
        if new_talking != self._is_talking:
            self._is_talking = new_talking
            self._mouth_open = True
            self._talk_frame_timer = now

        # Blink logic
        if not self._is_blinking and now >= self._next_blink:
            self._is_blinking = True
            self._blink_end = now + 0.4
        if self._is_blinking and now >= self._blink_end:
            self._is_blinking = False
            self._next_blink = now + 3.0 + random.random() * 2.0

        # Mouth animation during talking
        if self._is_talking and now - self._talk_frame_timer >= self._talk_frame_interval:
            self._mouth_open = random.random() < 0.7
            self._talk_frame_timer = now

        self._update_frame()

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def render(self) -> None:
        self.screen.fill((0, 0, 0))
        if self._current_surf is not None and self._render_rect is not None:
            self.screen.blit(self._current_surf, self._render_rect)

    def cleanup(self) -> None:
        pass
