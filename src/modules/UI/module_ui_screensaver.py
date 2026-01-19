import time
import random
from UI.module_screensaver_face import FaceAnimation
from UI.module_screensaver_terminal import TerminalAnimation
from UI.module_screensaver_matrix import MatrixAnimation
from UI.module_screensaver_hyperspace import HyperspaceAnimation
from UI.module_screensaver_starfield import StarfieldAnimation
from UI.module_screensaver_nebula import NebulaAnimation

SELECTED_ANIMATION = "starfield"

AVAILABLE_ANIMATIONS = {
    "face": FaceAnimation,
    "terminal": TerminalAnimation,
    "matrix": MatrixAnimation,
    "hyperspace": HyperspaceAnimation,
    "starfield": StarfieldAnimation,
    #"nebula": NebulaAnimation #wip
}

class ScreensaverManager:
    def __init__(self, screen, width, height, timeout=5.0):
        self.screen = screen
        self.width = width
        self.height = height
        self.active = False
        self.last_activity = time.time()
        self.timeout = float(timeout)
        self.current_animation = None
        self.current_animation_name = None
        self.last_switch_time = None
        self.switch_interval = 300

    def _select_animation(self):
        if SELECTED_ANIMATION == "random":
            animation_name = random.choice(list(AVAILABLE_ANIMATIONS.keys()))
        else:
            animation_name = SELECTED_ANIMATION

        if animation_name in AVAILABLE_ANIMATIONS:
            animation_class = AVAILABLE_ANIMATIONS[animation_name]
            self.current_animation = animation_class(self.screen, self.width, self.height)
            self.current_animation_name = animation_name
        else:
            animation_class = AVAILABLE_ANIMATIONS["face"]
            self.current_animation = animation_class(self.screen, self.width, self.height)
            self.current_animation_name = "face"

    def _maybe_switch_animation(self):
        if SELECTED_ANIMATION != "random":
            return

        if self.active and self.last_switch_time is not None:
            if (time.time() - self.last_switch_time) >= self.switch_interval:
                self._select_animation()
                if self.current_animation:
                    self.current_animation.reset()
                self.last_switch_time = time.time()

    def reset_timer(self):
        self.last_activity = time.time()
        if self.active:
            self.active = False

    def check_timeout(self):
        if self.timeout <= 0:
            return False

        if not self.active and (time.time() - self.last_activity) > self.timeout:
            self.active = True
            self._select_animation()
            if self.current_animation:
                self.current_animation.reset()
            self.last_switch_time = time.time()
            return True
        return False

    def is_active(self):
        return self.active

    def deactivate(self):
        self.active = False
        self.reset_timer()

    def render(self):
        if self.active and self.current_animation:
            self._maybe_switch_animation()
            self.current_animation.update()
            self.current_animation.render()
            return True
        return False
