import os
import random
import math
import pygame
from OpenGL.GL import *
from OpenGL.GLU import *
from UI.screensavers.module_screensaver_overlay import TimeOverlay


class Fish:
    """A single fish swimming in 3D with turning and confinement."""

    # Visible bounds in scene coordinates (tight to camera frustum)
    X_LIMIT = 2.6
    Y_MIN = -3.6
    Y_MAX = 4.5
    Z_MIN = -7.5
    Z_MAX = -3.0
    Z_LAYER_SPLIT = -5.0

    # Scene Y above which the foreground mask is transparent
    # (mask covers bottom ~550px of image, this is the approximate scene Y threshold)
    FG_MASK_TOP_Y = 0.8

    def __init__(self, textures):
        # Position (within visible bounds)
        self.x = random.uniform(-2.3, 2.3)
        self.y = random.uniform(-3.0, 4.0)
        self.z = random.uniform(-7.0, -3.5)

        # Heading (degrees, 0=+X, 90=-Z, 180=-X, 270=+Z)
        self.heading = random.uniform(0, 360)
        self.target_heading = self.heading
        self.pitch = 0.0
        self.target_pitch = 0.0

        # Movement
        self.base_speed = random.uniform(0.3, 0.7)
        self.speed = self.base_speed
        self.turn_speed = random.uniform(20, 40)

        # Direction change timer
        self.change_timer = random.uniform(2.0, 5.0)

        # Idle (stop swimming) behavior
        self.idle = False
        self.idle_timer = random.uniform(6.0, 15.0)
        self.idle_duration = 0.0
        self.target_speed = self.base_speed

        # Layer tracking (back = behind foreground, front = in front)
        self.layer = "back" if self.z < Fish.Z_LAYER_SPLIT else "front"

        # Sprite texture (single sprite dict passed in)
        self.texture_id = textures['id']
        self.aspect_ratio = textures['aspect']
        self.size = random.uniform(0.19, 0.34)

        # Swimming animation (subtle body wobble)
        self.swim_phase = random.uniform(0, math.pi * 2)
        self.swim_speed = random.uniform(4.0, 8.0)

        # Page-turn flip animation
        facing_left = 90 < (self.heading % 360) < 270
        self.face_dir = 1.0 if facing_left else -1.0
        self.prev_face_dir = self.face_dir
        self.flip_progress = 1.0  # 1.0 = flip complete
        self.distance_since_flip = 0.0

    def update(self, dt):
        self.swim_phase += self.swim_speed * dt

        # Idle behavior: gradually slow down, pause, then speed back up
        if self.idle:
            self.idle_duration -= dt
            if self.idle_duration <= 0:
                self.idle = False
                self.target_speed = self.base_speed
                self.idle_timer = random.uniform(6.0, 15.0)
        else:
            self.idle_timer -= dt
            if self.idle_timer <= 0:
                self.idle = True
                self.idle_duration = random.uniform(1.5, 4.0)
                self.target_speed = 0.0

        # Smooth speed transition
        speed_diff = self.target_speed - self.speed
        self.speed += speed_diff * min(1.0, 2.0 * dt)

        # Periodic direction change
        self.change_timer -= dt
        if self.change_timer <= 0:
            self.change_timer = random.uniform(2.0, 5.0)
            self.target_heading += random.uniform(-45, 45)
            self.target_pitch = random.uniform(-10, 10)

        # Page-turn flip: only allow after moving at least ~30px (0.32 scene units)
        self.distance_since_flip += self.speed * dt
        facing_left = 90 < (self.heading % 360) < 270
        target_dir = 1.0 if facing_left else -1.0
        if target_dir != self.face_dir and self.flip_progress >= 1.0 and self.distance_since_flip >= 0.32:
            self.prev_face_dir = self.face_dir
            self.face_dir = target_dir
            self.flip_progress = 0.0
            self.distance_since_flip = 0.0
        if self.flip_progress < 1.0:
            self.flip_progress = min(1.0, self.flip_progress + 2.5 * dt)

        # Steer away from boundaries
        self._steer_from_bounds()

        # Prevent Z layer crossing when below the foreground mask top
        if self.y < Fish.FG_MASK_TOP_Y:
            margin = 0.4
            if self.layer == "back" and self.z > Fish.Z_LAYER_SPLIT - margin:
                self.target_heading = 90 + random.uniform(-20, 20)
            elif self.layer == "front" and self.z < Fish.Z_LAYER_SPLIT + margin:
                self.target_heading = 270 + random.uniform(-20, 20)

        # Smooth heading interpolation
        diff = (self.target_heading - self.heading + 180) % 360 - 180
        max_turn = self.turn_speed * dt
        if abs(diff) <= max_turn:
            self.heading = self.target_heading
        else:
            self.heading += max_turn if diff > 0 else -max_turn
        self.heading %= 360

        # Smooth pitch interpolation
        pdiff = self.target_pitch - self.pitch
        max_pturn = 15.0 * dt
        if abs(pdiff) <= max_pturn:
            self.pitch = self.target_pitch
        else:
            self.pitch += max_pturn if pdiff > 0 else -max_pturn

        # Move forward
        rad = math.radians(self.heading)
        prad = math.radians(self.pitch)
        cos_p = math.cos(prad)
        self.x += math.cos(rad) * cos_p * self.speed * dt
        self.z -= math.sin(rad) * cos_p * self.speed * dt
        self.y += math.sin(prad) * self.speed * dt

        # Hard clamp
        self.x = max(-Fish.X_LIMIT, min(Fish.X_LIMIT, self.x))
        self.y = max(Fish.Y_MIN, min(Fish.Y_MAX, self.y))
        self.z = max(Fish.Z_MIN, min(Fish.Z_MAX, self.z))

        # Update layer only when above the foreground mask
        if self.y >= Fish.FG_MASK_TOP_Y:
            self.layer = "back" if self.z < Fish.Z_LAYER_SPLIT else "front"

    def _steer_from_bounds(self):
        margin = 0.5
        steer_x = False

        if self.x > Fish.X_LIMIT - margin:
            self.target_heading = 180 + random.uniform(-20, 20)
            steer_x = True
        elif self.x < -Fish.X_LIMIT + margin:
            self.target_heading = 0 + random.uniform(-20, 20)
            steer_x = True

        if self.y > Fish.Y_MAX - margin:
            self.target_pitch = random.uniform(-20, -8)
        elif self.y < Fish.Y_MIN + margin:
            self.target_pitch = random.uniform(8, 20)

        if not steer_x:
            if self.z > Fish.Z_MAX - margin:
                self.target_heading = 90 + random.uniform(-20, 20)
            elif self.z < Fish.Z_MIN + margin:
                self.target_heading = 270 + random.uniform(-20, 20)

    def draw(self):
        s = self.size
        half_w = s * self.aspect_ratio * 0.5
        half_h = s * 0.5

        glPushMatrix()
        glTranslatef(self.x, self.y, self.z)

        # Tilt nose up/down based on pitch
        glRotatef(-self.pitch, 0, 0, 1)

        # Draw textured sprite as vertical strips with page-turn flip + tail wiggle
        # Sprite faces left: u=0 is head, u=1 is tail
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.1)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        strips = 12
        tail_amp = s * 0.08
        flipping = self.flip_progress < 1.0

        # Pre-compute per-edge scale so adjacent strips share exact edge positions
        edge_sx = []
        for i in range(strips + 1):
            u = i / strips
            if flipping:
                lt = max(0.0, min(1.0, (self.flip_progress - u * 0.5) / 0.5))
                interp = (1.0 - math.cos(lt * math.pi)) / 2.0
                edge_sx.append(self.prev_face_dir + (self.face_dir - self.prev_face_dir) * interp)
            else:
                edge_sx.append(self.face_dir)

        for i in range(strips):
            u0 = i / strips
            u1 = (i + 1) / strips

            x0 = (-half_w + u0 * 2 * half_w) * edge_sx[i]
            x1 = (-half_w + u1 * 2 * half_w) * edge_sx[i + 1]

            # Tail wiggle displacement (increases head to tail)
            d0 = math.sin(self.swim_phase + u0 * 1.5) * tail_amp * u0 * u0
            d1 = math.sin(self.swim_phase + u1 * 1.5) * tail_amp * u1 * u1

            glBegin(GL_QUADS)
            glTexCoord2f(u0, 0); glVertex3f(x0, -half_h + d0, 0)
            glTexCoord2f(u1, 0); glVertex3f(x1, -half_h + d1, 0)
            glTexCoord2f(u1, 1); glVertex3f(x1, half_h + d1, 0)
            glTexCoord2f(u0, 1); glVertex3f(x0, half_h + d0, 0)
            glEnd()

        glDisable(GL_ALPHA_TEST)
        glDisable(GL_TEXTURE_2D)
        glPopMatrix()


class AquariumAnimation:
    def __init__(self, screen, width, height, show_time=False, rotation=0):
        self.screen = screen
        self.width = width
        self.height = height
        self.rotation = rotation
        self.is_portrait = height > width
        self.time = 0.0
        self.initialized = False
        self.clock = pygame.time.Clock()

        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height, rotation) if show_time else None

        # Scene bounds
        self.scene_x = 12.0
        self.scene_y = 6.0
        self.scene_z = 10.0

        # Entities
        self.fish = []
        self.bubbles = []

        # Light rays
        self.light_rays = []

        # Bubble spawn
        # With -90° rotation: scene X+ = physical down, scene Y+ = physical right
        self.bubble_timer = 0
        self.bubble_source_z = -3.0

        # GL resources
        self.bg_texture = None
        self.fg_texture = None
        self.fish_textures = []

    def _load_texture(self, filename):
        """Load an image from UI/assets/ as an OpenGL texture."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ui_dir = os.path.dirname(script_dir)
        img_path = os.path.join(ui_dir, "assets", filename)

        try:
            surface = pygame.image.load(img_path)
            surface = surface.convert_alpha()
        except Exception as e:
            print(f"[AQUARIUM] Could not load image '{filename}': {e}")
            return None

        tex_data = pygame.image.tostring(surface, "RGBA", True)
        tex_w, tex_h = surface.get_size()

        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tex_w, tex_h, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex_data)
        return texture_id

    def _load_fish_sprites(self):
        """Load fish.png sprite sheet and extract individual fish textures."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ui_dir = os.path.dirname(script_dir)
        img_path = os.path.join(ui_dir, "assets", "fish.png")

        try:
            sheet = pygame.image.load(img_path).convert_alpha()
        except Exception as e:
            print(f"[AQUARIUM] Could not load fish.png: {e}")
            return []

        w, h = sheet.get_size()
        raw = pygame.image.tostring(sheet, "RGBA", False)

        # Scan columns to find fish regions (separated by transparent gaps)
        def col_has_content(x):
            for y in range(h):
                if raw[(y * w + x) * 4 + 3] > 10:
                    return True
            return False

        regions = []
        in_region = False
        start_x = 0
        for x in range(w):
            has = col_has_content(x)
            if has and not in_region:
                start_x = x
                in_region = True
            elif not has and in_region:
                regions.append((start_x, x))
                in_region = False
        if in_region:
            regions.append((start_x, w))

        # Extract each fish sprite and create an OpenGL texture
        textures = []
        for (x1, x2) in regions:
            # Find vertical bounds (trim transparent rows)
            top_y = h
            bot_y = 0
            for x in range(x1, x2):
                for y in range(h):
                    if raw[(y * w + x) * 4 + 3] > 10:
                        top_y = min(top_y, y)
                        bot_y = max(bot_y, y + 1)

            if top_y >= bot_y:
                continue

            region_w = x2 - x1
            region_h = bot_y - top_y
            sub = sheet.subsurface((x1, top_y, region_w, region_h))

            tex_data = pygame.image.tostring(sub, "RGBA", True)
            texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, region_w, region_h, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex_data)

            textures.append({
                'id': texture_id,
                'aspect': region_w / max(1, region_h),
            })
        return textures

    def initialize(self):
        if self.initialized:
            return

        self.bg_texture = self._load_texture("aquarium_bg.jpg")
        self.fg_texture = self._load_texture("aquarium_1_bg.png")
        self.fish_textures = self._load_fish_sprites()

        # Create fish (fixed count, evenly distributed sprite types)
        if self.fish_textures:
            num_fish = 15
            sprites = self.fish_textures
            # Cycle through types so each appears roughly equally
            assigned = (sprites * ((num_fish // len(sprites)) + 1))[:num_fish]
            random.shuffle(assigned)
            for sprite in assigned:
                self.fish.append(Fish(sprite))

        # Create light ray positions
        for _ in range(random.randint(4, 7)):
            self.light_rays.append({
                'x': random.uniform(-self.scene_x * 0.7, self.scene_x * 0.7),
                'z': random.uniform(-self.scene_z, -self.scene_z * 0.3),
                'width': random.uniform(0.5, 1.5),
                'phase': random.uniform(0, math.pi * 2),
                'sway_speed': random.uniform(0.2, 0.5),
                'alpha': random.uniform(0.03, 0.08),
            })

        self.initialized = True

    def update(self, delta_time=None):
        if delta_time is None:
            try:
                delta_time = self.clock.get_time() / 1000.0
            except Exception:
                delta_time = 0.033

        self.time += delta_time

        # Update fish
        for f in self.fish:
            f.update(delta_time)

        # Update bubbles - rise in scene Y+ (toward water surface)
        for b in self.bubbles:
            b['y'] += b['speed'] * delta_time
            b['phase'] += 4.0 * delta_time
            b['x'] = b['base_x'] + math.sin(b['phase']) * b['wobble']
        self.bubbles = [b for b in self.bubbles if b['y'] < self.scene_y * 0.9]

        # Spawn many tiny bubbles (source shifted left)
        self.bubble_timer += delta_time
        if self.bubble_timer > 0.012:
            self.bubble_timer = 0
            for _ in range(random.randint(2, 5)):
                bx = -1.0 + random.uniform(-0.8, 0.8)
                self.bubbles.append({
                    'x': bx,
                    'base_x': bx,
                    'y': -self.scene_y * 0.6 + random.uniform(-0.3, 0.3),
                    'z': self.bubble_source_z + random.uniform(-0.5, 0.5),
                    'radius': random.uniform(0.01, 0.035),
                    'speed': random.uniform(0.8, 2.2),
                    'phase': random.uniform(0, math.pi * 2),
                    'wobble': random.uniform(0.08, 0.25),
                    'alpha': random.uniform(0.15, 0.45),
                })

        # Update light rays
        for ray in self.light_rays:
            ray['phase'] += ray['sway_speed'] * delta_time

    def _draw_background(self):
        """Draw background image with slow water distortion at the top."""
        if self.bg_texture is None:
            return

        glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        if not self.is_portrait:
            glRotatef(-90, 0, 0, 1)
        glOrtho(-1, 1, -1, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.bg_texture)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        # Draw as a grid of quads with wavy vertex distortion toward the top
        # Overscale slightly so distortion at the top edge stays off-screen
        margin = 0.06
        rows = 32
        cols = 32
        t = self.time
        for j in range(rows):
            glBegin(GL_QUAD_STRIP)
            for i in range(cols + 1):
                fx = i / cols              # 0 to 1 across
                x = -(1.0 + margin) + fx * 2.0 * (1.0 + margin)

                for k in [0, 1]:
                    fy = (j + k) / rows    # 0 (bottom) to 1 (top)
                    y = -(1.0 + margin) + fy * 2.0 * (1.0 + margin)

                    # Distortion strength: none at bottom, strongest at top
                    strength = max(0.0, (fy - 0.4) / 0.6) ** 2

                    # Wavy vertex displacement in both X and Y
                    dx = strength * 0.018 * math.sin(t * 0.7 + fy * 8.0 + fx * 3.0)
                    dx += strength * 0.010 * math.sin(t * 0.4 + fy * 5.0 - fx * 2.5 + 2.0)
                    dy = strength * 0.012 * math.sin(t * 0.6 + fx * 7.0 + fy * 2.0 + 1.0)
                    dy += strength * 0.007 * math.sin(t * 0.9 + fx * 4.0 - fy * 3.0 + 3.5)

                    glTexCoord2f(fx, fy)
                    glVertex3f(x + dx, y + dy, 0)
            glEnd()

        glDisable(GL_TEXTURE_2D)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)

    def _draw_foreground(self):
        """Draw foreground image overlay for depth effect."""
        if self.fg_texture is None:
            return

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_FOG)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        if not self.is_portrait:
            glRotatef(-90, 0, 0, 1)
        glOrtho(-1, 1, -1, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.fg_texture)
        glColor4f(1.0, 1.0, 1.0, 1.0)

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex3f(-1, -1, 0)
        glTexCoord2f(1, 0); glVertex3f(1, -1, 0)
        glTexCoord2f(1, 1); glVertex3f(1, 1, 0)
        glTexCoord2f(0, 1); glVertex3f(-1, 1, 0)
        glEnd()

        glDisable(GL_TEXTURE_2D)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)

    def _draw_light_rays(self):
        """Draw volumetric light rays from the surface."""
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)

        top_y = self.scene_y * 0.9
        bottom_y = -self.scene_y * 0.7

        for ray in self.light_rays:
            sway = math.sin(ray['phase']) * 0.8
            x = ray['x'] + sway
            w = ray['width']
            z = ray['z']
            alpha = ray['alpha'] * (0.7 + 0.3 * math.sin(self.time * 0.5 + ray['phase']))

            # Ray widens as it goes down
            top_w = w * 0.3
            bot_w = w * 1.5

            glBegin(GL_QUADS)
            glColor4f(0.4, 0.6, 0.8, alpha)
            glVertex3f(x - top_w, top_y, z)
            glVertex3f(x + top_w, top_y, z)
            glColor4f(0.2, 0.4, 0.6, alpha * 0.2)
            glVertex3f(x + bot_w, bottom_y, z)
            glVertex3f(x - bot_w, bottom_y, z)
            glEnd()

        glEnable(GL_DEPTH_TEST)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_surface_ripples(self):
        """Draw subtle ripple effect at the water surface."""
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)

        top_y = self.scene_y * 0.85
        z_back = -self.scene_z
        z_front = -self.scene_z * 0.2

        glBegin(GL_QUADS)
        alpha = 0.06 + math.sin(self.time * 0.7) * 0.02
        glColor4f(0.4, 0.6, 0.9, alpha)
        glVertex3f(-self.scene_x, top_y, z_back)
        glVertex3f(self.scene_x, top_y, z_back)
        glColor4f(0.5, 0.7, 1.0, alpha * 1.5)
        glVertex3f(self.scene_x, top_y + 0.15, z_front)
        glVertex3f(-self.scene_x, top_y + 0.15, z_front)
        glEnd()

        # Ripple lines
        for i in range(5):
            rx = math.sin(self.time * 0.4 + i * 1.3) * self.scene_x * 0.5
            rz = -self.scene_z * 0.5 + i * 0.5
            wave_y = top_y + math.sin(self.time * 1.2 + i * 0.8) * 0.05
            glColor4f(0.6, 0.8, 1.0, 0.04)
            glBegin(GL_LINES)
            glVertex3f(rx - 2.0, wave_y, rz)
            glVertex3f(rx + 2.0, wave_y, rz)
            glEnd()

        glEnable(GL_DEPTH_TEST)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_particles(self):
        """Draw tiny floating particles in the water."""
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_POINT_SMOOTH)
        glPointSize(2.0)

        glBegin(GL_POINTS)
        for i in range(40):
            px = math.sin(self.time * 0.1 + i * 2.3) * self.scene_x * 0.8
            py = math.sin(self.time * 0.15 + i * 1.7) * self.scene_y * 0.5
            pz = -self.scene_z * 0.3 + math.cos(self.time * 0.08 + i * 3.1) * self.scene_z * 0.4
            glColor4f(0.6, 0.7, 0.8, 0.2 + math.sin(self.time + i) * 0.1)
            glVertex3f(px, py, pz)
        glEnd()

        glDisable(GL_POINT_SMOOTH)

    def _draw_bubbles(self):
        """Draw small air bubbles rising on the right side."""
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_POINT_SMOOTH)
        glDepthMask(GL_FALSE)

        for b in self.bubbles:
            # Bubble circle
            r = b['radius']
            segments = 10
            glColor4f(0.7, 0.85, 1.0, b['alpha'])
            glBegin(GL_TRIANGLE_FAN)
            glVertex3f(b['x'], b['y'], b['z'])
            for i in range(segments + 1):
                angle = (i / segments) * math.pi * 2
                glVertex3f(
                    b['x'] + math.cos(angle) * r,
                    b['y'] + math.sin(angle) * r,
                    b['z']
                )
            glEnd()

            # Small highlight dot
            glColor4f(1.0, 1.0, 1.0, b['alpha'] * 0.8)
            glPointSize(max(1.0, r * 15))
            glBegin(GL_POINTS)
            glVertex3f(b['x'] + r * 0.3, b['y'] + r * 0.3, b['z'] + 0.01)
            glEnd()

        glDepthMask(GL_TRUE)
        glDisable(GL_POINT_SMOOTH)

    def render(self):
        if not self.initialized:
            self.initialize()

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if not self.is_portrait:
            # Display is landscape in software but screen is physically portrait
            glRotatef(-90, 0, 0, 1)
            gluPerspective(50, self.height / max(1, self.width), 0.1, 100.0)
        else:
            gluPerspective(50, self.width / max(1, self.height), 0.1, 100.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glViewport(0, 0, self.width, self.height)

        glClearColor(0.01, 0.05, 0.15, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Static background image
        self._draw_background()

        # Set up camera
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Gentle camera sway
        cam_x = math.sin(self.time * 0.12) * 0.3
        cam_y = math.sin(self.time * 0.08) * 0.3
        gluLookAt(
            cam_x, cam_y, 4.0,        # eye
            cam_x * 0.3, 0.0, -6.0,   # center
            0, 1, 0                    # up
        )

        # Enable fog for depth
        glEnable(GL_FOG)
        glFogi(GL_FOG_MODE, GL_EXP2)
        glFogfv(GL_FOG_COLOR, [0.02, 0.06, 0.18, 1.0])
        glFogf(GL_FOG_DENSITY, 0.06)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)

        # Draw bubbles (behind foreground image)
        self._draw_bubbles()

        # Draw back-layer fish (between back bg and foreground)
        for f in self.fish:
            if f.layer == "back":
                f.draw()

        # Draw floating particles
        self._draw_particles()

        # Surface ripples
        self._draw_surface_ripples()

        # Disable fog before foreground overlay
        glDisable(GL_FOG)

        # Foreground image layer (in front of bubbles for depth effect)
        self._draw_foreground()

        # Draw front-layer fish (in front of foreground)
        glEnable(GL_FOG)
        for f in self.fish:
            if f.layer == "front":
                f.draw()
        glDisable(GL_FOG)

        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()

        pygame.display.flip()

        try:
            self.clock.tick(30)
        except Exception:
            pass

    def reset(self):
        self.time = 0.0
        self.bubble_timer = 0
        self.bubbles.clear()
        for f in self.fish:
            f.x = random.uniform(-2.3, 2.3)
            f.y = random.uniform(-3.5, 4.0)
            f.z = random.uniform(-7.0, -3.5)
            f.heading = random.uniform(0, 360)
            f.target_heading = f.heading

    def cleanup(self):
        self.fish.clear()
        self.bubbles.clear()
        self.light_rays.clear()
        self.initialized = False

        if self.bg_texture:
            glDeleteTextures([self.bg_texture])
            self.bg_texture = None
        if self.fg_texture:
            glDeleteTextures([self.fg_texture])
            self.fg_texture = None
        for sprite in self.fish_textures:
            glDeleteTextures([sprite['id']])
        self.fish_textures = []

        glDisable(GL_FOG)
        glDisable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)
