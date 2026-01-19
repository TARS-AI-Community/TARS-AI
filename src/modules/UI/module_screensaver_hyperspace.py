"""
# atomikspace (discord)
# olivierdion1@hotmail.com
"""

import pygame
import random
import math

class HyperspaceAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.cx = width // 2
        self.cy = height * 0.65  

        self.lanes = self._create_lanes()
        self.trails = []
        self.max_trails = 200  

        self.colors = [
            (255, 0, 255),      
            (0, 255, 255),      
            (255, 0, 127),      
            (0, 255, 0),        
            (255, 255, 0),      
            (255, 64, 255),     
            (0, 191, 255),      
            (255, 20, 147),     

        ]

        for _ in range(self.max_trails):
            self._add_trail()

    def _create_lanes(self):
        lanes = []
        num_lanes = 80  

        for i in range(num_lanes):
            bottom_x = self.cx + (i - num_lanes / 2) * (self.width / num_lanes) * 3.0  
            top_x = self.cx + (i - num_lanes / 2) * 2.5  
            lanes.append({
                'bottom_x': bottom_x,
                'top_x': top_x
            })

        return lanes

    def _add_trail(self):
        lane = random.choice(self.lanes)
        color = random.choice(self.colors)
        speed = random.uniform(0.75, 2)  

        self.trails.append({
            'lane': lane,
            'y': self.height + random.randint(0, 50),  
            'color': color,
            'speed': speed,
            'history': [],
            'max_history': random.randint(5, 12),  

        })

    def reset(self):
        self.trails = []
        for _ in range(self.max_trails):
            self._add_trail()

    def update(self):
        for trail in self.trails[:]:

            distance_to_vanish = abs(trail['y'] - self.cy)
            max_distance = self.height

            if trail['y'] > self.cy:
                progress = 1.0 - (distance_to_vanish / max_distance)
                speed_mult = 0.3 + (progress ** 2) * 7.7
            else:
                speed_mult = 8.0  

            trail['y'] -= trail['speed'] * speed_mult
            lane = trail['lane']
            curve_zone_height = self.height * 0.6  
            curve_start_y = self.height  
            curve_end_y = self.cy  

            if trail['y'] > curve_start_y:
                current_x = lane['bottom_x']

            elif trail['y'] > curve_end_y:
                distance_from_bottom = curve_start_y - trail['y']
                curve_progress = distance_from_bottom / (curve_start_y - curve_end_y)
                curve_progress = max(0, min(1, curve_progress))
                smooth = curve_progress * curve_progress * (3 - 2 * curve_progress)
                current_x = lane['bottom_x'] + (lane['top_x'] - lane['bottom_x']) * smooth

            else:
                current_x = lane['top_x']

            trail['history'].append((current_x, trail['y']))

            if len(trail['history']) > trail['max_history']:
                trail['history'].pop(0)

            if trail['y'] < -50:
                self.trails.remove(trail)
                self._add_trail()

    def render(self):
        self.screen.fill((0, 0, 0))  

        for trail in self.trails:
            if len(trail['history']) < 2:
                continue

            color = trail['color']

            for i in range(len(trail['history']) - 1):
                start_pos = trail['history'][i]
                end_pos = trail['history'][i + 1]
                if (start_pos[0] < -50 and end_pos[0] < -50) or \
                   (start_pos[0] > self.width + 50 and end_pos[0] > self.width + 50):
                    continue

                fade = i / len(trail['history'])
                faded_color = (
                    int(color[0] * fade),
                    int(color[1] * fade),
                    int(color[2] * fade)
                )

                line_width = int(8 * fade) + 3
                for thickness in range(line_width, 0, -1):
                    glow_intensity = (thickness / line_width) ** 0.5  

                    glow_color = (
                        int(faded_color[0] * 0.6 * glow_intensity),
                        int(faded_color[1] * 0.6 * glow_intensity),
                        int(faded_color[2] * 0.6 * glow_intensity)
                    )
                    if glow_color[0] > 0 or glow_color[1] > 0 or glow_color[2] > 0:
                        pygame.draw.line(self.screen, glow_color,
                                       (int(start_pos[0]), int(start_pos[1])),
                                       (int(end_pos[0]), int(end_pos[1])), thickness)

                pygame.draw.line(self.screen, faded_color,
                               (int(start_pos[0]), int(start_pos[1])),
                               (int(end_pos[0]), int(end_pos[1])), 3)

                white_fade = int(255 * fade * 0.8)
                pygame.draw.line(self.screen, (white_fade, white_fade, white_fade),
                               (int(start_pos[0]), int(start_pos[1])),
                               (int(end_pos[0]), int(end_pos[1])), 1)

            if trail['history']:
                head_pos = trail['history'][-1]
                if -10 < head_pos[0] < self.width + 10 and -10 < head_pos[1] < self.height + 10:
                    pygame.draw.circle(self.screen, color, (int(head_pos[0]), int(head_pos[1])), 3)
                    pygame.draw.circle(self.screen, (255, 255, 255), (int(head_pos[0]), int(head_pos[1])), 1)