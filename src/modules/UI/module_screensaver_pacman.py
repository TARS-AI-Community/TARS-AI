"""
Module: Pacman Screensaver / game
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.
"""

import pygame
import random
import math

STOP, UP, DOWN, LEFT, RIGHT = 0, 1, -1, 2, -2
SCATTER, CHASE, FREIGHT = 0, 1, 2

class PacmanAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        self.maze_template = [
            "XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
            "X............XX............X",
            "X.XXXX.XXXXX.XX.XXXXX.XXXX.X",
            "XoXXXX.XXXXX.XX.XXXXX.XXXXoX",
            "X.XXXX.XXXXX.XX.XXXXX.XXXX.X",
            "X..........................X",
            "X.XXXX.XX.XXXXXXXX.XX.XXXX.X",
            "X.XXXX.XX.XXXXXXXX.XX.XXXX.X",
            "X......XX....XX....XX......X",
            "XXXXXX.XXXXX XX XXXXX.XXXXXX",
            "XXXXXX.XXXXX XX XXXXX.XXXXXX",
            "XXXXXX.XX          XX.XXXXXX",
            "XXXXXX.XX XXXDDXXX XX.XXXXXX",
            "XXXXXX.XX XGGGGGGX XX.XXXXXX",
            "      .   XGGGGGGX   .      ",
            "XXXXXX.XX XGGGGGGX XX.XXXXXX",
            "XXXXXX.XX XXXXXXXX XX.XXXXXX",
            "XXXXXX.XX          XX.XXXXXX",
            "XXXXXX.XX XXXXXXXX XX.XXXXXX",
            "XXXXXX.XX XXXXXXXX XX.XXXXXX",
            "X............XX............X",
            "X.XXXX.XXXXX.XX.XXXXX.XXXX.X",
            "X.XXXX.XXXXX.XX.XXXXX.XXXX.X",
            "Xo..XX.......  .......XX..oX",
            "XXX.XX.XX.XXXXXXXX.XX.XX.XXX",
            "XXX.XX.XX.XXXXXXXX.XX.XX.XXX",
            "X......XX....XX....XX......X",
            "X.XXXXXXXXXX.XX.XXXXXXXXXX.X",
            "X.XXXXXXXXXX.XX.XXXXXXXXXX.X",
            "X..........................X",
            "XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        ]

        self.maze_rows = len(self.maze_template)
        self.maze_cols = len(self.maze_template[0])

        hud_rows = 4
        tile_w = width // self.maze_cols
        tile_h = height // (self.maze_rows + hud_rows)
        self.tile_size = min(tile_w, tile_h)

        self.offset_x = (width - self.maze_cols * self.tile_size) // 2
        self.offset_y = self.tile_size * 2 + (height - (self.maze_rows + hud_rows) * self.tile_size) // 2

        self.maze = []
        self.pellets = []
        self.pacman = None
        self.ghosts = []
        self.score = 0
        self.high_score = 0
        self.lives = 3
        self.collected_fruits = []
        self.power_timer = 0

        self.maze_surface = None
        self.pacman_sprites = {}
        self.ghost_sprites = {}
        self.pellet_sprites = {}
        self.score_font = None
        self.lives_sprite = None

        self.reset_game()

    def reset_game(self):
        self.score = 0
        self.lives = 3
        self.level = 1
        self.collected_fruits = []
        self.reset()

    def reset(self):
        self.maze = [list(row) for row in self.maze_template]
        self.pellets = []

        for row in range(self.maze_rows):
            for col in range(self.maze_cols):
                cell = self.maze[row][col]
                if cell == '.':
                    self.pellets.append({'x': col, 'y': row, 'power': False})
                elif cell == 'o':
                    self.pellets.append({'x': col, 'y': row, 'power': True})

        self.power_timer = 0
        self._build_caches()
        self.reset_positions()

    def _build_caches(self):
        self._build_maze_cache()
        self._build_pacman_cache()
        self._build_ghost_cache()
        self._build_fruit_cache()
        self._build_pellet_cache()
        self._build_font_cache()

    def _build_maze_cache(self):
        ts = self.tile_size
        wall_color = (33, 33, 255)
        thick = max(3, ts // 8)
        inset = ts * 0.42

        self.maze_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        for row in range(self.maze_rows):
            for col in range(self.maze_cols):
                cell = self.maze[row][col]
                sx = self.offset_x + col * ts
                sy = self.offset_y + row * ts

                if cell == 'X':
                    top_open = row == 0 or self.maze[row-1][col] != 'X'
                    bottom_open = row == self.maze_rows-1 or self.maze[row+1][col] != 'X'
                    left_open = col == 0 or self.maze[row][col-1] != 'X'
                    right_open = col == self.maze_cols-1 or self.maze[row][col+1] != 'X'

                    left_x = sx + inset if left_open else sx - inset
                    right_x = sx + ts - inset if right_open else sx + ts + inset
                    top_y = sy + inset if top_open else sy - inset
                    bottom_y = sy + ts - inset if bottom_open else sy + ts + inset

                    if top_open:
                        pygame.draw.line(self.maze_surface, wall_color,
                                        (left_x, sy + inset + thick//2), (right_x, sy + inset + thick//2), thick)
                    if bottom_open:
                        pygame.draw.line(self.maze_surface, wall_color,
                                        (left_x, sy + ts - inset - thick//2), (right_x, sy + ts - inset - thick//2), thick)
                    if left_open:
                        pygame.draw.line(self.maze_surface, wall_color,
                                        (sx + inset + thick//2, top_y), (sx + inset + thick//2, bottom_y), thick)
                    if right_open:
                        pygame.draw.line(self.maze_surface, wall_color,
                                        (sx + ts - inset - thick//2, top_y), (sx + ts - inset - thick//2, bottom_y), thick)

                    if top_open and left_open:
                        pygame.draw.circle(self.maze_surface, wall_color,
                                          (int(sx + inset + thick//2), int(sy + inset + thick//2)), thick//2 + 1)
                    if top_open and right_open:
                        pygame.draw.circle(self.maze_surface, wall_color,
                                          (int(sx + ts - inset - thick//2), int(sy + inset + thick//2)), thick//2 + 1)
                    if bottom_open and left_open:
                        pygame.draw.circle(self.maze_surface, wall_color,
                                          (int(sx + inset + thick//2), int(sy + ts - inset - thick//2)), thick//2 + 1)
                    if bottom_open and right_open:
                        pygame.draw.circle(self.maze_surface, wall_color,
                                          (int(sx + ts - inset - thick//2), int(sy + ts - inset - thick//2)), thick//2 + 1)

                    if not top_open and not left_open:
                        if row > 0 and col > 0 and self.maze[row-1][col-1] != 'X':
                            pygame.draw.arc(self.maze_surface, wall_color,
                                           (sx - thick + inset, sy - thick + inset, thick*2, thick*2),
                                           -math.pi/2, 0, thick)
                    if not top_open and not right_open:
                        if row > 0 and col < self.maze_cols-1 and self.maze[row-1][col+1] != 'X':
                            pygame.draw.arc(self.maze_surface, wall_color,
                                           (sx + ts - thick - inset, sy - thick + inset, thick*2, thick*2),
                                           math.pi, math.pi*1.5, thick)
                    if not bottom_open and not left_open:
                        if row < self.maze_rows-1 and col > 0 and self.maze[row+1][col-1] != 'X':
                            pygame.draw.arc(self.maze_surface, wall_color,
                                           (sx - thick + inset, sy + ts - thick - inset, thick*2, thick*2),
                                           0, math.pi/2, thick)
                    if not bottom_open and not right_open:
                        if row < self.maze_rows-1 and col < self.maze_cols-1 and self.maze[row+1][col+1] != 'X':
                            pygame.draw.arc(self.maze_surface, wall_color,
                                           (sx + ts - thick - inset, sy + ts - thick - inset, thick*2, thick*2),
                                           math.pi/2, math.pi, thick)

                elif cell == 'D':
                    pygame.draw.rect(self.maze_surface, (255, 184, 174),
                                    (sx + 2, sy + ts//2 - thick//2, ts - 4, thick))

    def _build_pacman_cache(self):
        ts = self.tile_size

        sprite_pixel_size = 13
        pixel_scale = max(2, int(ts * 0.85) // sprite_pixel_size)

        pacman_open = [
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,0,0,0,0,0],
            [1,1,1,1,1,1,1,0,0,0,0,0,0],
            [1,1,1,1,1,1,0,0,0,0,0,0,0],
            [1,1,1,1,1,0,0,0,0,0,0,0,0],
            [1,1,1,1,1,1,0,0,0,0,0,0,0],
            [1,1,1,1,1,1,1,0,0,0,0,0,0],
            [1,1,1,1,1,1,1,1,0,0,0,0,0],
            [0,1,1,1,1,1,1,1,1,0,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
        ]

        pacman_mid = [
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,0,0],
            [1,1,1,1,1,1,1,1,1,1,0,0,0],
            [1,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,0,0,0,0,0],
            [1,1,1,1,1,1,1,0,0,0,0,0,0],
            [1,1,1,1,1,1,1,1,0,0,0,0,0],
            [1,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,1,1,0,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
        ]

        pacman_small = [
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1,1,1,1,0,0],
            [1,1,1,1,1,1,1,1,1,1,0,0,0],
            [1,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,1,0,0,0,0],
            [1,1,1,1,1,1,1,1,1,1,0,0,0],
            [1,1,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
        ]

        pacman_closed = [
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1],
            [0,1,1,1,1,1,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,0,1,1,1,1,1,0,0,0,0],
        ]

        self.pacman_sprites = {}
        yellow = (255, 255, 0)

        def rotate_sprite(sprite, times):
            result = [row[:] for row in sprite]
            for _ in range(times % 4):
                result = [list(row) for row in zip(*result[::-1])]
            return result

        def create_surface_from_pixels(pixels, scale):
            h, w = len(pixels), len(pixels[0])
            surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
            for y, row in enumerate(pixels):
                for x, pixel in enumerate(row):
                    if pixel == 1:
                        pygame.draw.rect(surf, yellow,
                                        (x * scale, y * scale, scale, scale))
            return surf

        direction_rotations = {RIGHT: 0, DOWN: 1, LEFT: 2, UP: 3}

        frame_map = {
            0: pacman_closed,
            5: pacman_closed,
            10: pacman_small,
            15: pacman_small,
            20: pacman_mid,
            25: pacman_mid,
            30: pacman_mid,
            35: pacman_open,
            40: pacman_open,
            45: pacman_open,
        }

        for direction, rot in direction_rotations.items():
            for deg, frame in frame_map.items():
                rotated = rotate_sprite(frame, rot)
                self.pacman_sprites[(direction, deg)] = create_surface_from_pixels(rotated, pixel_scale)

        self.pacman_sprite_size = sprite_pixel_size * pixel_scale
        self.pacman_sprite_offset = self.pacman_sprite_size // 2

    def _build_ghost_cache(self):
        ts = self.tile_size

        sprite_pixel_size = 14
        pixel_scale = max(2, int(ts * 0.85) // sprite_pixel_size)

        ghost_body = [
            [0,0,0,0,0,1,1,1,1,0,0,0,0,0],
            [0,0,0,1,1,1,1,1,1,1,1,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,1,0],
            [0,1,1,2,2,1,1,1,1,2,2,1,1,0],
            [0,1,2,2,2,2,1,1,2,2,2,2,1,0],
            [1,1,2,2,3,3,1,1,2,2,3,3,1,1],
            [1,1,2,2,3,3,1,1,2,2,3,3,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,0,0,1,1,1,1,0,0,1,1,1],
            [1,1,0,0,0,0,1,1,0,0,0,0,1,1],
        ]

        frightened_ghost = [
            [0,0,0,0,0,1,1,1,1,0,0,0,0,0],
            [0,0,0,1,1,1,1,1,1,1,1,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,1,0],
            [0,1,1,1,1,1,1,1,1,1,1,1,1,0],
            [0,1,1,2,2,1,1,1,1,2,2,1,1,0],
            [1,1,1,2,2,1,1,1,1,2,2,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,2,1,1,2,2,2,2,1,1,2,1,1],
            [1,2,1,2,2,1,1,1,1,2,2,1,2,1],
            [1,1,1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,0,0,1,1,1,1,0,0,1,1,1],
            [1,1,0,0,0,0,1,1,0,0,0,0,1,1],
        ]

        eyes_only = [
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,2,2,2,0,0,0,0,2,2,2,0,0],
            [0,2,2,2,2,2,0,0,2,2,2,2,2,0],
            [0,2,2,3,3,2,0,0,2,2,3,3,2,0],
            [0,2,2,3,3,2,0,0,2,2,3,3,2,0],
            [0,0,2,2,2,0,0,0,0,2,2,2,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        ]

        def create_ghost_surface(pixels, body_color, scale):
            h, w = len(pixels), len(pixels[0])
            surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
            for y, row in enumerate(pixels):
                for x, pixel in enumerate(row):
                    color = None
                    if pixel == 1:
                        color = body_color
                    elif pixel == 2:
                        color = (255, 255, 255)
                    elif pixel == 3:
                        color = (33, 33, 255)
                    if color:
                        pygame.draw.rect(surf, color,
                                        (x * scale, y * scale, scale, scale))
            return surf

        def create_frightened_surface(pixels, body_color, scale):
            h, w = len(pixels), len(pixels[0])
            surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
            for y, row in enumerate(pixels):
                for x, pixel in enumerate(row):
                    color = None
                    if pixel == 1:
                        color = body_color
                    elif pixel == 2:
                        color = (255, 184, 174)
                    if color:
                        pygame.draw.rect(surf, color,
                                        (x * scale, y * scale, scale, scale))
            return surf

        self.ghost_sprites = {}

        ghost_colors = {
            (255, 0, 0): 'blinky',
            (255, 184, 255): 'pinky',
            (0, 255, 255): 'inky',
            (255, 184, 82): 'clyde',
        }

        for color in ghost_colors.keys():
            self.ghost_sprites[color] = create_ghost_surface(ghost_body, color, pixel_scale)

        self.ghost_sprites[(33, 33, 255)] = create_frightened_surface(
            frightened_ghost, (33, 33, 255), pixel_scale)

        self.ghost_sprites[(255, 255, 255)] = create_frightened_surface(
            frightened_ghost, (255, 255, 255), pixel_scale)

        self.ghost_sprites['eaten'] = create_ghost_surface(eyes_only, (0, 0, 0), pixel_scale)

        self.ghost_sprite_size = sprite_pixel_size * pixel_scale
        self.ghost_sprite_offset = self.ghost_sprite_size // 2

    def _build_fruit_cache(self):
        ts = self.tile_size

        sprite_pixel_size = 12
        pixel_scale = max(2, int(ts * 0.70) // sprite_pixel_size)

        self.fruit_sprites = {}

        cherry = [
            [0,0,0,0,0,0,0,3,3,0,0,0],
            [0,0,0,0,0,0,3,3,0,0,0,0],
            [0,0,0,0,0,3,3,0,0,0,0,0],
            [0,0,0,0,3,3,3,3,0,0,0,0],
            [0,0,0,3,3,0,0,3,3,0,0,0],
            [0,0,1,1,1,0,0,0,1,1,1,0],
            [0,1,1,1,1,1,0,1,1,1,1,1],
            [1,1,2,1,1,1,0,1,1,2,1,1],
            [1,1,1,1,1,1,0,1,1,1,1,1],
            [1,1,1,1,1,1,0,1,1,1,1,1],
            [0,1,1,1,1,0,0,0,1,1,1,0],
            [0,0,1,1,0,0,0,0,0,1,1,0],
        ]
        cherry_colors = {1: (255, 0, 0), 2: (255, 184, 174), 3: (0, 150, 0)}

        strawberry = [
            [0,0,0,0,0,3,3,0,0,0,0,0],
            [0,0,0,0,3,3,3,3,0,0,0,0],
            [0,0,0,3,3,3,3,3,3,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,2,1,1,2,1,1,1,0],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [1,1,1,2,1,1,1,1,2,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,2,2,1,1,1,1,1],
            [0,1,1,2,1,1,1,1,2,1,1,0],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [0,0,1,1,1,2,2,1,1,1,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
            [0,0,0,0,0,1,1,0,0,0,0,0],
        ]
        strawberry_colors = {1: (255, 0, 0), 2: (255, 255, 255), 3: (0, 200, 0)}

        orange = [
            [0,0,0,0,0,3,3,0,0,0,0,0],
            [0,0,0,0,0,3,0,0,0,0,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,2,1,1,1,1,1,1,0],
            [0,1,1,2,2,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
        ]
        orange_colors = {1: (255, 184, 82), 2: (255, 255, 184), 3: (0, 150, 0)}

        apple = [
            [0,0,0,0,0,3,3,0,0,0,0,0],
            [0,0,0,0,0,3,0,0,0,0,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,1,1,1,2,1,1,1,1,1,1,0],
            [0,1,1,2,2,1,1,1,1,1,1,0],
            [1,1,1,1,1,1,1,1,1,1,1,1],
            [1,1,1,1,1,1,1,1,1,1,1,1],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [0,1,1,1,1,1,1,1,1,1,1,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
        ]
        apple_colors = {1: (255, 0, 0), 2: (255, 255, 255), 3: (0, 150, 0)}

        melon = [
            [0,0,0,0,1,1,1,1,0,0,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
            [0,0,1,1,2,1,2,1,1,1,0,0],
            [0,1,1,2,1,2,1,2,1,1,1,0],
            [0,1,1,1,2,1,2,1,2,1,1,0],
            [1,1,1,2,1,2,1,2,1,1,1,1],
            [1,1,1,1,2,1,2,1,2,1,1,1],
            [1,1,1,2,1,2,1,2,1,1,1,1],
            [0,1,1,1,2,1,2,1,2,1,1,0],
            [0,1,1,2,1,2,1,2,1,1,1,0],
            [0,0,1,1,1,1,1,1,1,1,0,0],
            [0,0,0,1,1,1,1,1,1,0,0,0],
        ]
        melon_colors = {1: (0, 200, 0), 2: (144, 238, 144)}

        def create_fruit_surface(pixels, color_map, scale):
            h, w = len(pixels), len(pixels[0])
            surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
            for y, row in enumerate(pixels):
                for x, pixel in enumerate(row):
                    if pixel in color_map:
                        pygame.draw.rect(surf, color_map[pixel],
                                        (x * scale, y * scale, scale, scale))
            return surf

        self.fruit_sprites['cherry'] = create_fruit_surface(cherry, cherry_colors, pixel_scale)
        self.fruit_sprites['strawberry'] = create_fruit_surface(strawberry, strawberry_colors, pixel_scale)
        self.fruit_sprites['orange'] = create_fruit_surface(orange, orange_colors, pixel_scale)
        self.fruit_sprites['apple'] = create_fruit_surface(apple, apple_colors, pixel_scale)
        self.fruit_sprites['melon'] = create_fruit_surface(melon, melon_colors, pixel_scale)

        self.fruit_order = ['cherry', 'strawberry', 'orange', 'apple', 'melon']
        self.fruit_points = {'cherry': 100, 'strawberry': 300, 'orange': 500, 'apple': 700, 'melon': 1000}

        self.fruit_sprite_offset = (sprite_pixel_size * pixel_scale) // 2

    def _build_font_cache(self):
        ts = self.tile_size

        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(script_dir, 'vga.ttf')

        try:
            if os.path.exists(font_path):
                self.score_font = pygame.font.Font(font_path, max(16, ts))
                self.small_font = pygame.font.Font(font_path, max(12, ts * 3 // 4))
            else:
                self.score_font = pygame.font.Font(None, max(24, ts * 2))
                self.small_font = pygame.font.Font(None, max(18, ts))
        except:
            self.score_font = pygame.font.Font(None, max(24, ts * 2))
            self.small_font = pygame.font.Font(None, max(18, ts))

        self.lives_sprite = self.pacman_sprites.get((LEFT, 30))

    def _build_pellet_cache(self):
        ts = self.tile_size
        pellet_color = (255, 184, 174)

        r_normal = max(2, ts // 10)
        size_normal = r_normal * 2 + 2
        surf_normal = pygame.Surface((size_normal, size_normal), pygame.SRCALPHA)
        pygame.draw.circle(surf_normal, pellet_color, (size_normal // 2, size_normal // 2), r_normal)
        self.pellet_sprites['normal'] = surf_normal
        self.pellet_normal_offset = size_normal // 2

        r_power = max(3, ts // 4)
        size_power = r_power * 2 + 2
        surf_power = pygame.Surface((size_power, size_power), pygame.SRCALPHA)
        pygame.draw.circle(surf_power, pellet_color, (size_power // 2, size_power // 2), r_power)
        self.pellet_sprites['power'] = surf_power
        self.pellet_power_offset = size_power // 2

    def reset_positions(self):
        self.pacman = {
            'x': 14.0, 'y': 23.0,
            'dir': LEFT, 'next_dir': LEFT,
            'speed': 0.2,
            'mouth': 0, 'mouth_open': True
        }

        self.ghosts = [
            {
                'name': 'Blinky', 'x': 14.0, 'y': 11.0, 'dir': LEFT, 'speed': 0.2,
                'color': (255, 0, 0), 'mode': SCATTER,
                'scatter_target': (25, -3),
                'in_house': False,
                'dot_limit': 0,
                'frightened': False,
                'eaten': False,
                'respawn_timer': 0,
            },
            {
                'name': 'Pinky', 'x': 14.0, 'y': 14.0, 'dir': DOWN, 'speed': 0.2,
                'color': (255, 184, 255), 'mode': SCATTER,
                'scatter_target': (2, -3),
                'in_house': True,
                'dot_limit': 0,
                'frightened': False,
                'eaten': False,
                'respawn_timer': 0,
            },
            {
                'name': 'Inky', 'x': 12.0, 'y': 14.0, 'dir': UP, 'speed': 0.2,
                'color': (0, 255, 255), 'mode': SCATTER,
                'scatter_target': (27, 32),
                'in_house': True,
                'dot_limit': 10,
                'frightened': False,
                'eaten': False,
                'respawn_timer': 0,
            },
            {
                'name': 'Clyde', 'x': 16.0, 'y': 14.0, 'dir': UP, 'speed': 0.2,
                'color': (255, 184, 82), 'mode': SCATTER,
                'scatter_target': (0, 32),
                'in_house': True,
                'dot_limit': 20,
                'frightened': False,
                'eaten': False,
                'respawn_timer': 0,
            },
        ]

        self.global_dot_counter = 0
        self.house_timer = 0

        self.mode_switch_timer = 420
        self.scatter_chase_index = 0
        self.mode_timings = [
            (1200, CHASE),
            (420, SCATTER),
            (1200, CHASE),
            (300, SCATTER),
            (1200, CHASE),
            (300, SCATTER),
            (999999, CHASE),
        ]

        self.power_timer = 0
        self.blink_timer = 0

        self.ghost_eat_pause = 0
        self.ghost_eat_points = 0
        self.ghost_eat_pos = (0, 0)
        self.ghost_eat_combo = 0
        self.eaten_ghost_index = -1

        self.current_fruit = None
        self.fruit_timer = 0
        self.fruit_spawn_dots = [70, 170]
        self.fruits_spawned = 0

    def is_wall(self, col, row):
        row = int(round(row))
        col = int(round(col))

        if col < 0 or col >= self.maze_cols:
            return False
        if row < 0 or row >= self.maze_rows:
            return True

        cell = self.maze[row][col]
        return cell == 'X'

    def is_valid_position(self, col, row):
        r = int(round(row))
        c = int(round(col))

        if c < 0 or c >= self.maze_cols:
            return True
        if r < 0 or r >= self.maze_rows:
            return False

        cell = self.maze[r][c]

        if cell == 'X':
            return False

        if cell == 'G':
            return False

        if cell == 'D':
            return False

        return True

    def can_move(self, x, y, direction, allow_house=False):
        col, row = int(round(x)), int(round(y))

        tx, ty = col, row
        if direction == UP:
            ty = row - 1
        elif direction == DOWN:
            ty = row + 1
        elif direction == LEFT:
            tx = col - 1
        elif direction == RIGHT:
            tx = col + 1
        else:
            return False

        if allow_house:
            if 0 <= tx < self.maze_cols and 0 <= ty < self.maze_rows:
                return self.maze[ty][tx] != 'X'
            return False
        else:
            return self.is_valid_position(tx, ty)

    def get_valid_directions(self, x, y, current_dir):
        dirs = []
        for d in [UP, DOWN, LEFT, RIGHT]:
            if self.can_move(x, y, d):
                dirs.append(d)

        if current_dir and len(dirs) > 1:
            reverse = -current_dir
            if reverse in dirs:
                dirs.remove(reverse)

        return dirs

    def move_entity(self, entity):
        x, y = entity['x'], entity['y']
        speed = entity['speed']
        direction = entity['dir']

        col, row = int(round(x)), int(round(y))

        can_enter_house = False
        if 'in_house' in entity:
            can_enter_house = entity['in_house'] or entity.get('eaten', False)

        dx = x - col
        dy = y - row
        at_center = abs(dx) < 0.01 and abs(dy) < 0.01

        if at_center:
            entity['x'] = float(col)
            entity['y'] = float(row)
            x, y = float(col), float(row)

            if 'next_dir' in entity and entity['next_dir'] != direction:
                if self.can_move(col, row, entity['next_dir'], can_enter_house):
                    entity['dir'] = entity['next_dir']
                    direction = entity['dir']

            if direction == STOP or not self.can_move(col, row, direction, can_enter_house):
                for d in [UP, DOWN, LEFT, RIGHT]:
                    if self.can_move(col, row, d, can_enter_house):
                        entity['dir'] = d
                        direction = d
                        break
                else:
                    return

        if direction == STOP:
            return

        nx, ny = x, y
        if direction == UP:
            ny -= speed
        elif direction == DOWN:
            ny += speed
        elif direction == LEFT:
            nx -= speed
        elif direction == RIGHT:
            nx += speed

        if direction in [UP, DOWN]:
            nx = float(col)
        else:
            ny = float(row)

        new_col, new_row = int(round(nx)), int(round(ny))

        if nx < -0.5:
            entity['x'] = float(self.maze_cols) - 0.5
            entity['y'] = float(row)
            return
        elif nx >= self.maze_cols - 0.5:
            entity['x'] = -0.5
            entity['y'] = float(row)
            return

        entering_new_tile = (new_col != col or new_row != row)

        if entering_new_tile:
            new_valid = False
            if can_enter_house:
                if 0 <= new_col < self.maze_cols and 0 <= new_row < self.maze_rows:
                    new_valid = self.maze[new_row][new_col] != 'X'
            else:
                new_valid = self.is_valid_position(new_col, new_row)

            if new_valid:
                entity['x'] = nx
                entity['y'] = ny
            else:
                entity['x'] = float(col)
                entity['y'] = float(row)
        else:
            entity['x'] = nx
            entity['y'] = ny

    def ai_pacman(self):
        col = int(round(self.pacman['x']))
        row = int(round(self.pacman['y']))
        px, py = float(col), float(row)

        valid = self.get_valid_directions(col, row, self.pacman['dir'])
        if not valid:
            return

        closest_ghost_dist = 999
        closest_ghost = None
        for ghost in self.ghosts:
            if not ghost['frightened'] and not ghost['eaten'] and not ghost['in_house']:
                gx, gy = ghost['x'], ghost['y']
                dist = math.sqrt((px - gx)**2 + (py - gy)**2)
                if dist < closest_ghost_dist:
                    closest_ghost_dist = dist
                    closest_ghost = ghost

        scores = {}
        for d in valid:
            scores[d] = random.uniform(0, 5)

            tx, ty = col, row
            if d == UP: ty -= 1
            elif d == DOWN: ty += 1
            elif d == LEFT: tx -= 1
            elif d == RIGHT: tx += 1

            for ghost in self.ghosts:
                if not ghost['frightened'] and not ghost['eaten'] and not ghost['in_house']:
                    gx, gy = ghost['x'], ghost['y']
                    current_dist = math.sqrt((px - gx)**2 + (py - gy)**2)
                    new_dist = math.sqrt((tx - gx)**2 + (ty - gy)**2)

                    if current_dist < 3:
                        if new_dist > current_dist:
                            scores[d] += 200
                        else:
                            scores[d] -= 300
                    elif current_dist < 5:
                        if new_dist > current_dist:
                            scores[d] += 50
                        else:
                            scores[d] -= 100
                    elif current_dist < 8:
                        if new_dist < current_dist:
                            scores[d] -= 30

            if self.pellets and closest_ghost_dist > 3:
                sample_pellets = random.sample(self.pellets, min(10, len(self.pellets)))
                nearest_pellet = min(sample_pellets,
                    key=lambda p: abs(px - p['x']) + abs(py - p['y']))

                old_dist = abs(px - nearest_pellet['x']) + abs(py - nearest_pellet['y'])
                new_dist = abs(tx - nearest_pellet['x']) + abs(ty - nearest_pellet['y'])

                if new_dist < old_dist:
                    scores[d] += 30
                    if nearest_pellet['power'] and closest_ghost_dist < 10:
                        scores[d] += 100

            if closest_ghost_dist < 4:
                for p in self.pellets:
                    if p['power']:
                        power_dist = abs(tx - p['x']) + abs(ty - p['y'])
                        old_power_dist = abs(px - p['x']) + abs(py - p['y'])
                        if power_dist < closest_ghost_dist * 1.5 and power_dist < old_power_dist:
                            scores[d] += 150

            for ghost in self.ghosts:
                if ghost['frightened'] and not ghost['eaten']:
                    gx, gy = ghost['x'], ghost['y']
                    old_dist = abs(px - gx) + abs(py - gy)
                    new_dist = abs(tx - gx) + abs(ty - gy)
                    if new_dist < old_dist:
                        scores[d] += 80

        best = max(valid, key=lambda d: scores[d])
        self.pacman['next_dir'] = best

    def ai_ghost(self, ghost, idx):
        col = int(round(ghost['x']))
        row = int(round(ghost['y']))

        at_center = abs(ghost['x'] - col) < 0.1 and abs(ghost['y'] - row) < 0.1

        if not at_center and not ghost['eaten']:
            return

        if ghost['eaten']:
            target = (14, 14)

            ghost_col = int(round(ghost['x']))
            ghost_row = int(round(ghost['y']))
            cell_type = ''
            if 0 <= ghost_row < self.maze_rows and 0 <= ghost_col < self.maze_cols:
                cell_type = self.maze[ghost_row][ghost_col]
            in_ghost_house = cell_type in ('G', 'D')
            near_center = abs(ghost['x'] - 14) < 1.0 and abs(ghost['y'] - 14) < 1.0

            if in_ghost_house or near_center:
                ghost['eaten'] = False
                ghost['in_house'] = True
                ghost['x'], ghost['y'] = 14.0, 14.0
                ghost['respawn_timer'] = 120
                ghost['speed'] = 0.2
                ghost['frightened'] = False
                ghost['eaten_timer'] = 0
                return

            if not at_center:
                return

            all_valid = []
            for d in [UP, DOWN, LEFT, RIGHT]:
                tx, ty = col, row
                if d == UP: ty -= 1
                elif d == DOWN: ty += 1
                elif d == LEFT: tx -= 1
                elif d == RIGHT: tx += 1
                if 0 <= tx < self.maze_cols and 0 <= ty < self.maze_rows:
                    if self.maze[ty][tx] != 'X':
                        all_valid.append(d)

            if all_valid:
                if ghost['dir'] != STOP and ghost['dir'] != 0:
                    reverse = -ghost['dir']
                    if reverse in all_valid and len(all_valid) > 1:
                        all_valid.remove(reverse)

                best = all_valid[0]
                best_dist = 9999
                for d in all_valid:
                    tx, ty = col, row
                    if d == UP: ty -= 1
                    elif d == DOWN: ty += 1
                    elif d == LEFT: tx -= 1
                    elif d == RIGHT: tx += 1
                    dist = (tx - target[0])**2 + (ty - target[1])**2
                    if dist < best_dist:
                        best_dist = dist
                        best = d
                ghost['dir'] = best
            return

        if ghost['in_house']:
            ready_to_exit = False
            if ghost['respawn_timer'] > 0:
                ready_to_exit = False
            else:
                ready_to_exit = (self.global_dot_counter >= ghost['dot_limit'] or self.house_timer >= 240)

            if ready_to_exit:
                door_y = 12
                door_x = 14
                exit_y = 11

                all_valid = []
                for d in [UP, DOWN, LEFT, RIGHT]:
                    tx, ty = col, row
                    if d == UP: ty -= 1
                    elif d == DOWN: ty += 1
                    elif d == LEFT: tx -= 1
                    elif d == RIGHT: tx += 1
                    if 0 <= tx < self.maze_cols and 0 <= ty < self.maze_rows:
                        if self.maze[ty][tx] in ['G', 'D', ' ', '.']:
                            all_valid.append(d)

                if all_valid:
                    if row == exit_y and col == door_x:
                        ghost['x'] = float(door_x)
                        ghost['y'] = float(exit_y)
                        ghost['in_house'] = False
                        if ghost['name'] == 'Inky':
                            ghost['dir'] = LEFT
                        elif ghost['name'] == 'Clyde':
                            ghost['dir'] = RIGHT
                        else:
                            ghost['dir'] = LEFT
                        for other_g in self.ghosts:
                            if not other_g['in_house'] and not other_g['eaten'] and not other_g['frightened']:
                                ghost['mode'] = other_g['mode']
                                break
                        return
                    else:
                        if col != door_x:
                            if col < door_x and RIGHT in all_valid:
                                ghost['dir'] = RIGHT
                            elif col > door_x and LEFT in all_valid:
                                ghost['dir'] = LEFT
                            elif UP in all_valid:
                                ghost['dir'] = UP
                        elif row > exit_y and UP in all_valid:
                            ghost['dir'] = UP
                        elif all_valid:
                            ghost['dir'] = all_valid[0]
            else:
                all_valid = []
                for d in [UP, DOWN]:
                    tx, ty = col, row
                    if d == UP: ty -= 1
                    elif d == DOWN: ty += 1
                    if 0 <= tx < self.maze_cols and 0 <= ty < self.maze_rows:
                        if self.maze[ty][tx] == 'G':
                            all_valid.append(d)

                if all_valid:
                    if random.random() < 0.05:
                        ghost['dir'] = random.choice(all_valid)
                    elif ghost['dir'] not in all_valid:
                        ghost['dir'] = all_valid[0]
            return

        all_valid = [d for d in [UP, DOWN, LEFT, RIGHT] if self.can_move(col, row, d)]

        if not all_valid:
            return

        valid = all_valid.copy()
        if ghost['dir'] != STOP and ghost['dir'] != 0:
            reverse = -ghost['dir']
            if reverse in valid and len(valid) > 1:
                valid.remove(reverse)

        if not valid:
            valid = all_valid

        px, py = int(self.pacman['x']), int(self.pacman['y'])
        target = None

        if ghost['frightened']:
            if ghost['dir'] not in valid:
                ghost['dir'] = random.choice(valid)
            elif len(valid) > 2:
                if random.random() < 0.2:
                    ghost['dir'] = random.choice(valid)
            return

        if ghost['mode'] == SCATTER:
            target = ghost['scatter_target']

        elif ghost['mode'] == CHASE:
            if ghost['name'] == 'Blinky':
                target = (px, py)

            elif ghost['name'] == 'Pinky':
                if self.pacman['dir'] == UP:
                    target = (px - 4, py - 4)
                elif self.pacman['dir'] == DOWN:
                    target = (px, py + 4)
                elif self.pacman['dir'] == LEFT:
                    target = (px - 4, py)
                elif self.pacman['dir'] == RIGHT:
                    target = (px + 4, py)
                else:
                    target = (px, py)

            elif ghost['name'] == 'Inky':
                blinky = self.ghosts[0]

                if self.pacman['dir'] == UP:
                    pivot_x, pivot_y = px - 2, py - 2
                elif self.pacman['dir'] == DOWN:
                    pivot_x, pivot_y = px, py + 2
                elif self.pacman['dir'] == LEFT:
                    pivot_x, pivot_y = px - 2, py
                elif self.pacman['dir'] == RIGHT:
                    pivot_x, pivot_y = px + 2, py
                else:
                    pivot_x, pivot_y = px, py

                vec_x = pivot_x - int(blinky['x'])
                vec_y = pivot_y - int(blinky['y'])
                target = (int(blinky['x']) + vec_x * 2, int(blinky['y']) + vec_y * 2)

            elif ghost['name'] == 'Clyde':
                dist = math.sqrt((col - px)**2 + (row - py)**2)
                if dist > 8:
                    target = (px, py)
                else:
                    target = ghost['scatter_target']

        if target:
            direction_distances = []
            for d in valid:
                tx, ty = col, row
                if d == UP: ty -= 1
                elif d == DOWN: ty += 1
                elif d == LEFT: tx -= 1
                elif d == RIGHT: tx += 1
                dist = (tx - target[0])**2 + (ty - target[1])**2
                direction_distances.append((d, dist))

            direction_distances.sort(key=lambda x: x[1])

            best = direction_distances[0][0]
            best_dist = direction_distances[0][1]

            if ghost['dir'] in valid:
                current_dist = next((dist for d, dist in direction_distances if d == ghost['dir']), 9999)
                if current_dist <= best_dist * 1.05:
                    best = ghost['dir']
            else:
                priority = {UP: 0, LEFT: 1, DOWN: 2, RIGHT: 3}
                best_priority = priority.get(best, 999)

                for d, dist in direction_distances:
                    if abs(dist - best_dist) < 0.01:
                        if priority.get(d, 999) < best_priority:
                            best = d
                            best_priority = priority[d]

            ghost['dir'] = best

    def update(self):
        if self.ghost_eat_pause > 0:
            self.ghost_eat_pause -= 1
            if self.ghost_eat_pause == 0:
                self.eaten_ghost_index = -1
            return

        if self.pacman['mouth_open']:
            self.pacman['mouth'] += 15
            if self.pacman['mouth'] >= 45:
                self.pacman['mouth_open'] = False
        else:
            self.pacman['mouth'] -= 15
            if self.pacman['mouth'] <= 0:
                self.pacman['mouth_open'] = True

        self.blink_timer += 1
        if self.blink_timer >= 60:
            self.blink_timer = 0

        self.house_timer += 1

        if self.power_timer == 0:
            self.mode_switch_timer -= 1
            if self.mode_switch_timer <= 0:
                if self.scatter_chase_index < len(self.mode_timings):
                    duration, new_mode = self.mode_timings[self.scatter_chase_index]
                    self.mode_switch_timer = duration
                    self.scatter_chase_index += 1

                    for g in self.ghosts:
                        if not g['in_house'] and not g['eaten']:
                            g['mode'] = new_mode

        self.ai_pacman()
        for i, g in enumerate(self.ghosts):
            if not g['in_house'] and not g['eaten']:
                col, row = int(round(g['x'])), int(round(g['y']))
                if not self.is_valid_position(col, row):
                    for r in range(1, 10):
                        found = False
                        for dc in range(-r, r+1):
                            for dr in range(-r, r+1):
                                if self.is_valid_position(col+dc, row+dr):
                                    g['x'] = float(col + dc)
                                    g['y'] = float(row + dr)
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break

            self.ai_ghost(g, i)

        self.move_entity(self.pacman)
        for g in self.ghosts:
            self.move_entity(g)

        px, py = int(round(self.pacman['x'])), int(round(self.pacman['y']))
        for p in self.pellets[:]:
            if p['x'] == px and p['y'] == py:
                self.pellets.remove(p)
                self.score += 50 if p['power'] else 10
                self.maze[p['y']][p['x']] = ' '

                self.global_dot_counter += 1

                if p['power']:
                    self.power_timer = 420
                    self.ghost_eat_combo = 0
                    for g in self.ghosts:
                        if not g['in_house'] and not g['eaten']:
                            g['frightened'] = True
                            g['speed'] = 0.15

        if self.score > self.high_score:
            self.high_score = self.score

        if self.power_timer > 0:
            self.power_timer -= 1
            if self.power_timer == 0:
                for g in self.ghosts:
                    g['frightened'] = False
                    if not g['eaten']:
                        g['speed'] = 0.2

        for g in self.ghosts:
            if g['respawn_timer'] > 0:
                g['respawn_timer'] -= 1

            if g['eaten']:
                g['eaten_timer'] = g.get('eaten_timer', 0) + 1
                if g['eaten_timer'] > 600:
                    g['eaten'] = False
                    g['in_house'] = True
                    g['x'], g['y'] = 14.0, 14.0
                    g['respawn_timer'] = 60
                    g['speed'] = 0.2
                    g['frightened'] = False
                    g['eaten_timer'] = 0
            else:
                g['eaten_timer'] = 0

        for i, g in enumerate(self.ghosts):
            if g['eaten'] or g['in_house']:
                continue

            dist = math.sqrt((self.pacman['x'] - g['x'])**2 +
                            (self.pacman['y'] - g['y'])**2)
            if dist < 1.0:
                if g['frightened'] and not g['eaten']:
                    self.ghost_eat_combo += 1
                    points = 100 * self.ghost_eat_combo
                    self.score += points

                    self.ghost_eat_pause = 60
                    self.ghost_eat_points = points
                    self.ghost_eat_pos = (g['x'], g['y'])
                    self.eaten_ghost_index = i

                    g['eaten'] = True
                    g['frightened'] = False
                    g['speed'] = 0.4
                    return
                elif not g['eaten']:
                    self.lives -= 1
                    if self.lives <= 0:
                        self.reset_game()
                    else:
                        self.reset_positions()
                    return

        if not self.pellets:
            self.level += 1
            self.reset()

        total_pellets = 244
        eaten_pellets = total_pellets - len(self.pellets)

        if self.fruits_spawned < len(self.fruit_spawn_dots):
            if eaten_pellets >= self.fruit_spawn_dots[self.fruits_spawned]:
                fruit_index = min((self.level - 1) % len(self.fruit_order), len(self.fruit_order) - 1)
                self.current_fruit = {
                    'type': self.fruit_order[fruit_index],
                    'x': 14,
                    'y': 17,
                }
                self.fruit_timer = 600
                self.fruits_spawned += 1

        if self.current_fruit:
            self.fruit_timer -= 1
            if self.fruit_timer <= 0:
                self.current_fruit = None
            else:
                if (int(round(self.pacman['x'])) == self.current_fruit['x'] and
                    int(round(self.pacman['y'])) == self.current_fruit['y']):
                    self.score += self.fruit_points[self.current_fruit['type']]
                    self.collected_fruits.append(self.current_fruit['type'])
                    self.current_fruit = None

    def render(self):
        self.screen.fill((0, 0, 0))
        ts = self.tile_size

        self.screen.blit(self.maze_surface, (0, 0))

        for p in self.pellets:
            px = self.offset_x + int(p['x'] * ts + ts // 2)
            py = self.offset_y + int(p['y'] * ts + ts // 2)

            if p['power']:
                if self.blink_timer % 20 < 10:
                    self.screen.blit(self.pellet_sprites['power'],
                                    (px - self.pellet_power_offset, py - self.pellet_power_offset))
            else:
                self.screen.blit(self.pellet_sprites['normal'],
                                (px - self.pellet_normal_offset, py - self.pellet_normal_offset))

        if self.ghost_eat_pause == 0:
            px = self.offset_x + int(self.pacman['x'] * ts + ts // 2)
            py = self.offset_y + int(self.pacman['y'] * ts + ts // 2)

            direction = self.pacman['dir'] if self.pacman['dir'] != STOP else RIGHT
            mouth_deg = int(self.pacman['mouth'] / 5) * 5
            mouth_deg = max(0, min(45, mouth_deg))

            sprite_key = (direction, mouth_deg)
            if sprite_key in self.pacman_sprites:
                sprite = self.pacman_sprites[sprite_key]
                self.screen.blit(sprite, (px - self.pacman_sprite_offset, py - self.pacman_sprite_offset))

        for i, g in enumerate(self.ghosts):
            if self.ghost_eat_pause > 0 and i == self.eaten_ghost_index:
                continue

            gx = self.offset_x + int(g['x'] * ts + ts // 2)
            gy = self.offset_y + int(g['y'] * ts + ts // 2)

            if g['eaten']:
                sprite = self.ghost_sprites['eaten']
            elif g['frightened']:
                if self.power_timer > 0 and self.power_timer <= 120:
                    if (self.power_timer // 5) % 2 == 0:
                        sprite = self.ghost_sprites[(255, 255, 255)]
                    else:
                        sprite = self.ghost_sprites[(33, 33, 255)]
                else:
                    sprite = self.ghost_sprites[(33, 33, 255)]
            else:
                sprite = self.ghost_sprites[g['color']]

            self.screen.blit(sprite, (gx - self.ghost_sprite_offset, gy - self.ghost_sprite_offset))

        if self.ghost_eat_pause > 0 and self.score_font:
            eat_x = self.offset_x + int(self.ghost_eat_pos[0] * ts + ts // 2)
            eat_y = self.offset_y + int(self.ghost_eat_pos[1] * ts + ts // 2)
            points_text = self.score_font.render(str(self.ghost_eat_points), True, (0, 255, 255))
            self.screen.blit(points_text, (eat_x - points_text.get_width() // 2,
                                          eat_y - points_text.get_height() // 2))

        if self.current_fruit and self.current_fruit['type'] in self.fruit_sprites:
            fx = self.offset_x + int(self.current_fruit['x'] * ts + ts // 2)
            fy = self.offset_y + int(self.current_fruit['y'] * ts + ts // 2)
            fruit_sprite = self.fruit_sprites[self.current_fruit['type']]
            self.screen.blit(fruit_sprite, (fx - self.fruit_sprite_offset, fy - self.fruit_sprite_offset))

        if self.score_font:
            score_y = max(5, self.offset_y - ts * 2)

            oneup_text = self.score_font.render("1UP", True, (255, 255, 255))
            oneup_x = self.offset_x + ts * 3
            self.screen.blit(oneup_text, (oneup_x, score_y))

            score_text = self.score_font.render(f"{self.score:>6}", True, (255, 255, 255))
            self.screen.blit(score_text, (oneup_x - ts, score_y + ts))

            high_label = self.score_font.render("HIGH SCORE", True, (255, 255, 255))
            high_x = self.offset_x + (self.maze_cols * ts) // 2 - high_label.get_width() // 2
            self.screen.blit(high_label, (high_x, score_y))

            high_text = self.score_font.render(f"{self.high_score:>6}", True, (255, 255, 255))
            self.screen.blit(high_text, (high_x + high_label.get_width() // 2 - high_text.get_width() // 2, score_y + ts))

        lives_y = self.offset_y + self.maze_rows * ts + ts // 2
        if self.lives_sprite:
            for i in range(self.lives - 1):
                lives_x = self.offset_x + ts + i * (self.pacman_sprite_size + 4)
                self.screen.blit(self.lives_sprite, (lives_x, lives_y))

        if self.collected_fruits:
            fruit_y = lives_y
            fruits_to_show = self.collected_fruits[-7:]
            for i, fruit_type in enumerate(reversed(fruits_to_show)):
                if fruit_type in self.fruit_sprites:
                    fruit_x = self.offset_x + self.maze_cols * ts - ts - i * (self.fruit_sprite_offset * 2 + 4)
                    self.screen.blit(self.fruit_sprites[fruit_type],
                                    (fruit_x - self.fruit_sprite_offset, fruit_y))