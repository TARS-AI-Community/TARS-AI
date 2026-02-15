"""
Module: Flying Toasters Screensaver
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import pygame
import random
import math
import os
from UI.module_screensaver_overlay import TimeOverlay

SPRITE_SHEET_NAME = "flying_toasters_sprites.png"
FRAME_WIDTH = 64
FRAME_HEIGHT = 71
FRAME_COUNT = 5
TARS_ROW_Y = 71
TOAST_Y_OFFSET = 144
FLAP_SEQUENCE = [0, 1, 2, 3, 4, 3, 2, 1]
TARS_CHANCE = 0.5


def _find_sprite_sheet():
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", SPRITE_SHEET_NAME)


def _load_sprites():
    sheet = pygame.image.load(_find_sprite_sheet()).convert()
    sheet.set_colorkey((0, 0, 0))
    sw, sh = sheet.get_size()

    toaster_frames = []
    tars_frames = []
    for i in range(FRAME_COUNT):
        frame = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT))
        frame.fill((0, 0, 0))
        frame.blit(sheet, (0, 0),
                   (i * FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT))
        frame.set_colorkey((0, 0, 0))
        toaster_frames.append(frame)

        frame2 = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT))
        frame2.fill((0, 0, 0))
        frame2.blit(sheet, (0, 0),
                    (i * FRAME_WIDTH, TARS_ROW_Y, FRAME_WIDTH, FRAME_HEIGHT))
        frame2.set_colorkey((0, 0, 0))
        tars_frames.append(frame2)

    toast_h = sh - TOAST_Y_OFFSET
    toast = None
    if toast_h > 0:
        toast = pygame.Surface((FRAME_WIDTH, toast_h))
        toast.fill((0, 0, 0))
        toast.blit(sheet, (0, 0), (0, TOAST_Y_OFFSET, FRAME_WIDTH, toast_h))
        toast.set_colorkey((0, 0, 0))

    return toaster_frames, tars_frames, toast


class FlyingToastersAnimation:
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None

        raw_toaster, raw_tars, raw_toast = _load_sprites()
        self.scale = max(1.0, min(width, height) / 500)

        self.toaster_frames = [
            pygame.transform.scale(
                f, (int(f.get_width() * self.scale), int(f.get_height() * self.scale))
            ) for f in raw_toaster
        ]
        self.tars_frames = [
            pygame.transform.scale(
                f, (int(f.get_width() * self.scale), int(f.get_height() * self.scale))
            ) for f in raw_tars
        ]
        self.toast_surf = None
        if raw_toast:
            self.toast_surf = pygame.transform.scale(
                raw_toast,
                (int(raw_toast.get_width() * self.scale), int(raw_toast.get_height() * self.scale))
            )

        self.sw = self.toaster_frames[0].get_width()
        self.sh = self.toaster_frames[0].get_height()

        # Lane geometry
        self.cell_size = max(self.sw, self.sh) + 6
        self.lane_step = self.cell_size * 0.71

        screen_perp = (self.width + self.height) / 1.414
        self.num_lanes = max(8, int(screen_perp / self.lane_step) + 2)

        self.lane_origin_x = -self.sw
        self.lane_origin_y = -self.sh

        self.objects = []
        area = width * height
        self.max_toasters = max(8, int(area / 35000))
        self.max_toast = max(5, int(area / 50000))

        for _ in range(self.max_toasters):
            self._spawn('toaster', initial=True)
        if self.toast_surf:
            for _ in range(self.max_toast):
                self._spawn('toast', initial=True)

    def _lane_to_screen(self, lane, t):
        lx = lane * self.lane_step * 0.707
        ly = lane * self.lane_step * 0.707
        tx = -t * 0.707
        ty = t * 0.707
        return self.lane_origin_x + lx + tx, self.lane_origin_y + ly + ty

    def _travel_range(self):
        diag = (self.width + self.height) * 0.707
        return -self.cell_size, diag + self.cell_size * 2

    def _rects_overlap(self, x1, y1, x2, y2):
        margin = 2
        w = self.sw - margin
        h = self.sh - margin
        return (x1 < x2 + w and x1 + w > x2 and
                y1 < y2 + h and y1 + h > y2)

    def _any_screen_overlap(self, x, y, exclude=None):
        for obj in self.objects:
            if obj is exclude:
                continue
            if self._rects_overlap(x, y, obj['x'], obj['y']):
                return True
        return False

    def _spawn(self, kind, initial=False):
        t_min, t_max = self._travel_range()

        if kind == 'toaster':
            speed = random.uniform(1.0, 2.5) * self.scale
        else:
            speed = random.uniform(1.2, 3.0) * self.scale

        if initial:
            travel = random.uniform(t_min, t_max)
        else:
            travel = t_min - self.cell_size * 2 - random.uniform(0, self.cell_size * 3)

        lanes = list(range(self.num_lanes))
        random.shuffle(lanes)
        chosen_lane = None
        for lane in lanes:
            x, y = self._lane_to_screen(lane, travel)
            if not self._any_screen_overlap(x, y):
                chosen_lane = lane
                break
        if chosen_lane is None:
            return

        x, y = self._lane_to_screen(chosen_lane, travel)
        obj = {
            'type': kind,
            'lane': chosen_lane,
            'target_lane': float(chosen_lane),
            'visual_lane': float(chosen_lane),
            'travel': travel,
            'speed': speed,
            'x': x, 'y': y,
        }
        if kind == 'toaster':
            obj['base_speed'] = speed
            obj['speed_timer'] = random.uniform(2.0, 6.0)
            obj['frame'] = random.randint(0, len(FLAP_SEQUENCE) - 1)
            obj['frame_timer'] = random.uniform(0, 1.0)
            obj['is_tars'] = random.random() < TARS_CHANCE
        self.objects.append(obj)

    def reset(self):
        self.objects.clear()
        for _ in range(self.max_toasters):
            self._spawn('toaster', initial=True)
        if self.toast_surf:
            for _ in range(self.max_toast):
                self._spawn('toast', initial=True)

    def _resolve_all_overlaps(self):
        """After movement, check every pair. Only toasters ever move.
        Toast never changes lane — toasters always get out of the way."""
        for i, a in enumerate(self.objects):
            for j, b in enumerate(self.objects):
                if j <= i:
                    continue
                ax, ay = self._lane_to_screen(a['lane'], a['travel'])
                bx, by = self._lane_to_screen(b['lane'], b['travel'])
                if not self._rects_overlap(ax, ay, bx, by):
                    continue

                if a['type'] == 'toaster' and b['type'] == 'toaster':
                    mover = a if a['speed'] >= b['speed'] else b
                elif a['type'] == 'toaster':
                    mover = a
                elif b['type'] == 'toaster':
                    mover = b
                else:
                    continue

                old_lane = mover['lane']
                for offset in [1, -1, 2, -2]:
                    new_lane = old_lane + offset
                    if 0 <= new_lane < self.num_lanes:
                        nx, ny = self._lane_to_screen(new_lane, mover['travel'])
                        clear = True
                        for other in self.objects:
                            if other is mover:
                                continue
                            ox, oy = self._lane_to_screen(other['lane'], other['travel'])
                            if self._rects_overlap(nx, ny, ox, oy):
                                clear = False
                                break
                        if clear:
                            mover['lane'] = new_lane
                            mover['target_lane'] = float(new_lane)
                            mover['speed'] = mover['base_speed'] * 1.5
                            break

    def update(self):
        _, t_max = self._travel_range()
        toaster_count = 0
        toast_count = 0

        for obj in self.objects:
            obj['travel'] += obj['speed']

        self._resolve_all_overlaps()

        slide_speed = 0.12
        for obj in self.objects:
            diff = obj['target_lane'] - obj['visual_lane']
            if abs(diff) > 0.02:
                obj['visual_lane'] += diff * slide_speed
            else:
                obj['visual_lane'] = obj['target_lane']
            obj['x'], obj['y'] = self._lane_to_screen(obj['visual_lane'], obj['travel'])

        for obj in self.objects[:]:
            if obj['type'] == 'toaster':
                toaster_count += 1

                obj['speed_timer'] -= 0.016
                if obj['speed_timer'] <= 0:
                    obj['speed_timer'] = random.uniform(2.0, 6.0)
                    if random.random() < 0.25:
                        burst = random.uniform(3.5, 5.0) * self.scale
                        obj['base_speed'] = burst
                        obj['speed'] = burst
                    else:
                        new_speed = random.uniform(1.0, 3.0) * self.scale
                        obj['base_speed'] = new_speed
                        obj['speed'] = new_speed

                flap_speed = 0.06 + (obj['speed'] / self.scale) * 0.07
                obj['frame_timer'] += flap_speed
                if obj['frame_timer'] >= 1.0:
                    obj['frame_timer'] -= 1.0
                    obj['frame'] = (obj['frame'] + 1) % len(FLAP_SEQUENCE)
            else:
                toast_count += 1

            if obj['travel'] > t_max + self.cell_size:
                self.objects.remove(obj)
                if obj['type'] == 'toaster':
                    toaster_count -= 1
                else:
                    toast_count -= 1

        if toaster_count < self.max_toasters:
            self._spawn('toaster')
        if self.toast_surf and toast_count < self.max_toast:
            self._spawn('toast')

    def render(self):
        self.screen.fill((0, 0, 0))

        for obj in self.objects:
            ix = int(obj['x'])
            iy = int(obj['y'])
            if obj['type'] == 'toaster':
                frame_idx = FLAP_SEQUENCE[obj['frame']]
                if obj.get('is_tars', False):
                    self.screen.blit(self.tars_frames[frame_idx], (ix, iy))
                else:
                    self.screen.blit(self.toaster_frames[frame_idx], (ix, iy))
            elif obj['type'] == 'toast' and self.toast_surf:
                self.screen.blit(self.toast_surf, (ix, iy))

        if self.show_time and self.time_overlay:
            self.time_overlay.render(self.screen)