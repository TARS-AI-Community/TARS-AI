import pygame
import random
import math
import pygame
import math
import random
import numpy as np
from typing import List, Tuple


# Constants
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (76, 194, 230)

def get_random_semi_transparent_color():
    r = random.randint(0, 255) * 0.5
    g = random.randint(0, 255) * 0.5
    b = random.randint(0, 255) * 0.5
    if r > g and r > b:
        g = 0
        b = 0
    elif g > r and g > b:
        r = 0
        b = 0
    else:
        r = 0
        g = 0
    return (int(r), int(g), int(b), 128)

BACKGROUND = get_random_semi_transparent_color()

class HalAnimation:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        if not pygame.font.get_init():
            pygame.font.init()
        self.font = pygame.font.Font("UI/pixelmix.ttf", 12)
        self.big_font = pygame.font.Font("UI/mono.ttf", 30)
        self.big_font = pygame.font.Font(None, 50)
        self.animations = [
            FrequencyBars3DAnimation(width, height),
            OrbitalAnimation(width, height, self.font),
            NeuralNetAnimation(width, height),
            CircuitAnimation(width, height),
            HALInterfaceAnimation(width, height, self.font),
            HealthMonitorAnimation(width, height),
            WormholeAnimation(width, height),
        ]
        self.current_animation = 0
        self.text_animation = None
    
    def update(self):
        if self.animations[self.current_animation].should_switch():
            global BACKGROUND
            BACKGROUND = get_random_semi_transparent_color()
            
            self.current_animation = random.randint(0, len(self.animations) - 1)
            self.animations[self.current_animation].reset()
            if random.random() < 0.33:
                self.text_animation = TextAnimation(self.width, self.height, self.big_font, 50)
            else:
                self.text_animation = None
            
            if self.text_animation:
                self.text_animation.reset()
        
        self.animations[self.current_animation].update()
        if self.text_animation:
            self.text_animation.update()
    
    def get_surface(self):
        self.surface.fill(BACKGROUND)
        self.animations[self.current_animation].draw(self.surface)
        if self.text_animation:
            self.text_animation.draw(self.surface)
        return self.surface
    


class TextAnimation:
    def __init__(self, width, height, font, font_size):
        self.width = width
        self.height = height
        self.font_size = font_size
        self.font = font
        self.reset()

    def generate_text(self):
        num_chars = random.choice([2, 5])
        return ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=num_chars))

    def random_position(self):
        margin = 20
        corner = random.choice(['top-left', 'top-right', 'bottom-left', 'bottom-right'])

        if corner == 'top-left':
            return margin, margin
        elif corner == 'top-right':
            return self.width - self.font_size * len(self.text) - margin, margin
        elif corner == 'bottom-left':
            return margin, self.height - self.font_size - margin
        elif corner == 'bottom-right':
            return self.width - self.font_size * len(self.text) - margin, self.height - self.font_size - margin

    def reset(self):
        self.text = self.generate_text()
        self.position = self.random_position()
        self.alpha = 255
        self.fade_duration = 60
        self.current_frame = 0
        self.fade_out_occurred = False
        self.text_changed = False
        self.should_fade = random.choice([True, False, False])
        self.fading_in = self.should_fade

    def update(self):
        if self.text_changed:
            self.alpha = 255
            self.text_changed = False
        elif self.should_fade:
            if self.fading_in:
                self.alpha = min(255, self.alpha + 40)
                if self.alpha == 255:
                    self.fading_in = False
            else:
                self.alpha = max(0, self.alpha - 40)
                if self.alpha == 0:
                    if self.fade_out_occurred and random.choice([True, False]):
                        self.text = self.generate_text()
                        self.text_changed = True
                        self.fade_out_occurred = True
                    else:
                        self.fade_out_occurred = False
                    self.fading_in = True
                    self.current_frame = 0
        self.current_frame += 1
        if self.current_frame >= self.fade_duration * 2:
            self.current_frame = 0

    def draw(self, surface):
        x, y = self.position
        text_surface = self.font.render(self.text, True, WHITE)
        text_outline = self.font.render(self.text, True, BLACK)
        text_surface.set_alpha(self.alpha)
        text_outline.set_alpha(self.alpha)
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            surface.blit(text_outline, (x + dx, y + dy))
        surface.blit(text_surface, (x, y))

    def should_switch(self):
        return False

class FrequencyBars3DAnimation:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.num_bars = random.randint(15, 35)
        self.bars = [random.randint(50, height) for _ in range(self.num_bars)]
        self.bar_speeds = [random.uniform(0.05, 0.2) for _ in range(self.num_bars)]
        self.bar_directions = [random.choice([-1, 1]) for _ in range(self.num_bars)]
        self.moving_indices = random.sample(range(len(self.bars)), max(2, min(10, len(self.bars))))
        self.time = 0
        self.delay_frames = 30

    def update(self):
        self.time += 0.1
        for i in self.moving_indices:
            if random.random() < self.bar_speeds[i]:
                self.bars[i] += self.bar_directions[i]
                if self.bars[i] <= 50 or self.bars[i] >= self.height:
                    self.bar_directions[i] *= -1

    def draw(self, surface):
        num_bars = len(self.bars)
        bar_width = self.width / num_bars
        for i, height in enumerate(self.bars):
            color = (255, 255, 255) if i in self.moving_indices else (200, 200, 200)
            x_pos = int(i * bar_width)
            next_x_pos = int((i + 1) * bar_width)
            pygame.draw.rect(surface, color, (x_pos, self.height - height, next_x_pos - x_pos - 1, height))

    def should_switch(self):
        return self.time >= self.delay_frames

    def reset(self):
        self.num_bars = random.randint(15, 35)
        self.bars = [random.randint(50, self.height) for _ in range(self.num_bars)]
        self.bar_speeds = [random.uniform(0.05, 0.2) for _ in range(self.num_bars)]
        self.bar_directions = [random.choice([-1, 1]) for _ in range(self.num_bars)]
        self.moving_indices = random.sample(range(len(self.bars)), max(2, min(10, len(self.bars))))
        self.time = 0

class OrbitalAnimation:
    def __init__(self, width, height, font):
        self.width = width
        self.height = height
        self.num_orbits = random.randint(3, 6)
        self.orbit_radii = [random.randint(50, min(width, height) // 2) for _ in range(self.num_orbits)]
        self.orbit_speeds = [random.uniform(0.01, 0.05) for _ in range(self.num_orbits)]
        self.time = 0
        self.delay_frames = 30
        self.orbit_inclinations = [random.uniform(0, math.pi/3) for _ in range(self.num_orbits)]
        self.orbit_rotations = [random.uniform(0, 2*math.pi) for _ in range(self.num_orbits)]
        self.reset_view_angles()
        self.name_patterns = [
            "Kep-", "HD-", "Prox-", "Tau-", "Sig-", "Omi-", "Psi-", "Xi-", "Nyx-", "Vex-"
        ]
        self.generate_planet_names()
        self.font = font

    def generate_planet_names(self):
        self.planet_names = []
        for _ in range(self.num_orbits):
            prefix = random.choice(self.name_patterns)
            suffix = str(random.randint(1, 999))
            name = prefix + suffix
            self.planet_names.append(name)

    def reset_view_angles(self):
        self.azimuth = random.uniform(0, 2*math.pi)
        self.elevation = random.uniform(-math.pi/4, math.pi/4)

    def project_3d_to_2d(self, x, y, z):
        x_rot = x * math.cos(self.elevation) + z * math.sin(self.elevation)
        y_rot = y
        z_rot = -x * math.sin(self.elevation) + z * math.cos(self.elevation)
        x_final = x_rot * math.cos(self.azimuth) - y_rot * math.sin(self.azimuth)
        y_final = x_rot * math.sin(self.azimuth) + y_rot * math.cos(self.azimuth)
        # I hate maths
        scale = 1000 / (1000 + z_rot)
        x_screen = self.width//2 + x_final * scale
        y_screen = self.height//2 + y_final * scale
        
        return int(x_screen), int(y_screen), z_rot

    
    def update(self):
        self.time += 0.1

    def draw(self, surface):
        orbit_depths = []
        for i in range(self.num_orbits):
            z = math.cos(self.orbit_inclinations[i])
            orbit_depths.append((i, z))
        orbit_depths.sort(key=lambda x: x[1], reverse=True)

        for depth_index, (i, _) in enumerate(orbit_depths):
            radius = self.orbit_radii[i]
            speed = self.orbit_speeds[i]
            inclination = self.orbit_inclinations[i]
            rotation = self.orbit_rotations[i]
            points = []
            for angle in range(0, 360, 5):
                theta = math.radians(angle)
                x = radius * math.cos(theta)
                y = radius * math.sin(theta)
                z = 0
                x_rot = x * math.cos(rotation) - y * math.sin(rotation)
                y_rot = x * math.sin(rotation) + y * math.cos(rotation)
                z_rot = z
                y_final = y_rot * math.cos(inclination) - z_rot * math.sin(inclination)
                z_final = y_rot * math.sin(inclination) + z_rot * math.cos(inclination)
                screen_x, screen_y, depth = self.project_3d_to_2d(x_rot, y_final, z_final)
                points.append((screen_x, screen_y))
            alpha = max(50, min(255, int(255 * (depth_index + 1) / self.num_orbits)))
            orbit_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            if len(points) > 2:
                pygame.draw.lines(orbit_surface, (200, 200, 200, alpha), True, points, 2)
            surface.blit(orbit_surface, (0, 0))
            angle = self.time * speed
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            z = 0
            x_rot = x * math.cos(rotation) - y * math.sin(rotation)
            y_rot = x * math.sin(rotation) + y * math.cos(rotation)
            z_rot = z
            y_final = y_rot * math.cos(inclination) - z_rot * math.sin(inclination)
            z_final = y_rot * math.sin(inclination) + z_rot * math.cos(inclination)
            planet_x, planet_y, depth = self.project_3d_to_2d(x_rot, y_final, z_final)
            pygame.draw.circle(surface, (255, 255, 255), (planet_x, planet_y), 4)
            label = self.font.render(self.planet_names[i], True, (255, 255, 255))
            label_pos = (planet_x + 10, planet_y - 10)
            surface.blit(label, label_pos)

    def should_switch(self):
        return self.time >= self.delay_frames

    def reset(self):
        self.num_orbits = random.randint(3, 6)
        self.orbit_radii = [random.randint(50, min(self.width, self.height) // 2) for _ in range(self.num_orbits)]
        self.orbit_speeds = [random.uniform(0.01, 0.05) for _ in range(self.num_orbits)]
        self.orbit_inclinations = [random.uniform(0, math.pi/3) for _ in range(self.num_orbits)]
        self.orbit_rotations = [random.uniform(0, 2*math.pi) for _ in range(self.num_orbits)]
        self.generate_planet_names()
        self.reset_view_angles()
        self.time = 0 


class HALInterfaceAnimation:
    def __init__(self, width, height, font):
        self.width = width
        self.height = height
        self.time = 0
        self.delay_frames = 60
        self.grid_size = 20
        self.grid_opacity = 40
        self.num_trajectories = 14
        self.trajectories = self._init_trajectories()
        self.numbers = self._generate_numbers()
        self.font_size = 14
        self.font = font
        
    def _init_trajectories(self) -> List[dict]:
        trajectories = []
        for _ in range(self.num_trajectories):
            start_y = random.randint(self.height//4, 3*self.height//4)
            
            trajectories.append({
                'start': (-50, start_y),
                'control1': (self.width//3, start_y + random.randint(-100, 100)),
                'control2': (2*self.width//3, start_y + random.randint(-100, 100)),
                'end': (self.width + 50, start_y + random.randint(-200, 200)),
                'progress': 0.0,
                'speed': random.uniform(0.001, 0.01),
                'active': True,
                'opacity': 255
            })
        return trajectories
    
    def _generate_numbers(self) -> List[dict]:
        numbers = []
        for i in range(3):
            numbers.append({
                'value': f"POS: {random.randint(100,999)}",
                'pos': (50, 40 + i * 30),
                'opacity': 255
            })
        return numbers
    
    def update(self):
        self.time += 0.1
        for traj in self.trajectories:
            if traj['active']:
                traj['progress'] += traj['speed']
                if traj['progress'] >= 1.0:
                    traj['active'] = False
                    traj['opacity'] = 0
        if self.time % 60 == 0:
            for i, traj in enumerate(self.trajectories):
                if not traj['active']:
                    self.trajectories[i] = {
                        'start': (-50, random.randint(self.height//4, 3*self.height//4)),
                        'control1': (self.width//3, random.randint(self.height//4, 3*self.height//4)),
                        'control2': (2*self.width//3, random.randint(self.height//4, 3*self.height//4)),
                        'end': (self.width + 50, random.randint(self.height//4, 3*self.height//4)),
                        'progress': 0.0,
                        'speed': random.uniform(0.001, 0.003),
                        'active': True,
                        'opacity': 255
                    }
        if self.time % 30 == 0:
            self.numbers = self._generate_numbers()
    

    def draw(self, surface: pygame.Surface):
        for x in range(0, self.width, self.grid_size):
            pygame.draw.line(surface, (self.grid_opacity, self.grid_opacity, self.grid_opacity),
                           (x, 0), (x, self.height))
        for y in range(0, self.height, self.grid_size):
            pygame.draw.line(surface, (self.grid_opacity, self.grid_opacity, self.grid_opacity),
                           (0, y), (self.width, y))
        for traj in self.trajectories:
            if traj['active']:
                points = []
                steps = 50
                for i in range(steps + 1):
                    t = (i / steps) * traj['progress']
                    if t > 1.0:
                        break
                    x = (1-t)**3 * traj['start'][0] + \
                        3*t*(1-t)**2 * traj['control1'][0] + \
                        3*t**2*(1-t) * traj['control2'][0] + \
                        t**3 * traj['end'][0]
                    y = (1-t)**3 * traj['start'][1] + \
                        3*t*(1-t)**2 * traj['control1'][1] + \
                        3*t**2*(1-t) * traj['control2'][1] + \
                        t**3 * traj['end'][1]
                    points.append((int(x), int(y)))
                if len(points) > 1:
                    pygame.draw.lines(surface, (traj['opacity'], traj['opacity'], traj['opacity']), 
                                   False, points, 2)
        for num in self.numbers:
            text = self.font.render(num['value'], True, 
                             (num['opacity'], num['opacity'], num['opacity']))
            surface.blit(text, num['pos'])
    
    def should_switch(self) -> bool:
        return self.time >= self.delay_frames
    
    def reset(self):
        self.__init__(self.width, self.height, self.font)




class CircuitAnimation:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.time = 0
        self.font = pygame.font.Font(None, 20)
        self.big_font = pygame.font.Font(None, 30)
        self.delay_frames = 30
        self.is_finished = False
        self.nodes = []
        self.paths = []
        self.components = []
        self.scroll_x = 0
        self.scroll_y = 0
        self.scroll_angle = random.uniform(0, 2 * math.pi)
        self.scroll_speed = 1.0
        self.direction_change_timer = 0
        self.direction_change_interval = 180
        self.zoom_level = 0.8
        self.zoom_target = random.uniform(0.8, 1.4)
        self.zoom_speed = 0.0005
        self.highlight = None
        self.highlight_timer = 0
        self.highlight_duration = 120
        self.overlay_text = []
        self.circuit_width = width * 2
        self.circuit_height = height * 2
        self._generate_circuit()
    
    def should_switch(self) -> bool:
        return self.time >= self.delay_frames
    
    def reset(self):
        self.__init__(self.width, self.height)

    def _update_scroll_direction(self):
        self.direction_change_timer += 1
        if self.direction_change_timer >= self.direction_change_interval:
            target_angle = random.uniform(0, 2 * math.pi)
            angle_diff = target_angle - self.scroll_angle
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            elif angle_diff < -math.pi:
                angle_diff += 2 * math.pi
            self.scroll_angle += angle_diff * 0.1
            self.direction_change_timer = 0


    def _generate_circuit(self):
        num_nodes = 8
        padding = 40
        min_x = padding
        max_x = self.circuit_width - padding
        min_y = padding
        max_y = self.circuit_height - padding
        if min_x >= max_x or min_y >= max_y:
            min_x, max_x = 0, self.circuit_width
            min_y, max_y = 0, self.circuit_height
            
        for _ in range(num_nodes):
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            self.nodes.append({
                'pos': (x, y),
                'connections': []
            })
        for i, node in enumerate(self.nodes):
            num_connections = random.randint(1, 3)
            possible_connections = self.nodes[i+1:]
            if possible_connections:
                for _ in range(num_connections):
                    if possible_connections:
                        target = random.choice(possible_connections)
                        path = self._generate_path(node['pos'], target['pos'])
                        self.paths.append({
                            'points': path,
                            'highlighted': False,
                            'color': (120,120,120)
                        })
                        node['connections'].append(len(self.paths) - 1)
                        possible_connections.remove(target)
        num_components = 10
        for _ in range(num_components):
            node = random.choice(self.nodes)
            self.components.append({
                'pos': node['pos'],
                'type': random.choice(['R', 'C', 'L', 'IC']),
                'id': f"RD-{random.randint(10,99)}",
                'highlighted': False
            })

    def _generate_path(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        points = [start]
        current = start
        target = end
        
        while current != target:
            if random.random() < 0.5:
                new_x = current[0] + (10 if target[0] > current[0] else -10)
                new_y = current[1]
            else:
                new_x = current[0]
                new_y = current[1] + (10 if target[1] > current[1] else -10)
            
            current = (new_x, new_y)
            points.append(current)
            if abs(current[0] - target[0]) < 10 and abs(current[1] - target[1]) > 10:
                current = (current[0], target[1])
                points.append(current)
            elif abs(current[1] - target[1]) < 10 and abs(current[0] - target[0]) > 10:
                current = (target[0], current[1])
                points.append(current)
            if current == target:
                break
            if len(points) > 1000:
                points.append(target)
                break
        
        return points
    
    def update(self):
        self.time += 0.1
        
        if self.should_switch():
            self.is_finished = True
            return
        self._update_scroll_direction()
        dx = math.cos(self.scroll_angle) * self.scroll_speed
        dy = math.sin(self.scroll_angle) * self.scroll_speed
        new_scroll_x = self.scroll_x + dx
        new_scroll_y = self.scroll_y + dy
        max_scroll_x = self.circuit_width - self.width
        max_scroll_y = self.circuit_height - self.height
        
        if 0 <= new_scroll_x <= max_scroll_x:
            self.scroll_x = new_scroll_x
        else:
            self.scroll_angle = math.pi - self.scroll_angle
            
        if 0 <= new_scroll_y <= max_scroll_y:
            self.scroll_y = new_scroll_y
        else:
            self.scroll_angle = -self.scroll_angle
        if self.zoom_level < self.zoom_target:
            self.zoom_level += self.zoom_speed
        
        # Update highlighting
        if self.highlight_timer > 0:
            self.highlight_timer -= 1
        elif random.random() < 0.01:
            if self.components:
                self.highlight = random.choice(self.components)
                self.highlight['highlighted'] = True
                self.highlight_timer = self.highlight_duration
                self.overlay_text = [
                    f"I/N/P: C{random.randint(10,99)}C{random.randint(10,99)}",
                    f"DR(+HD{random.randint(1,9)})",
                    f"{random.randint(100,999)}.{random.randint(100,999)}"
                ]
        elif self.highlight:
            self.highlight['highlighted'] = False
            self.highlight = None
            self.overlay_text = []
    
    def draw(self, surface: pygame.Surface):
        def transform_point(point):
            x = (point[0] - self.scroll_x) * self.zoom_level
            y = (point[1] - self.scroll_y) * self.zoom_level
            return (int(x), int(y))
        for path in self.paths:
            points = [transform_point(p) for p in path['points']]
            visible_points = [p for p in points if 0 <= p[0] <= self.width and 0 <= p[1] <= self.height]
            if len(visible_points) > 1:
                color = (255, 255, 255) if path.get('highlighted', False) else path['color']
                pygame.draw.lines(surface, color, False, points, max(1, int(self.zoom_level)))
        for comp in self.components:
            pos = transform_point(comp['pos'])
            if 0 <= pos[0] <= self.width and 0 <= pos[1] <= self.height:
                color = (255, 255, 255) if comp.get('highlighted', False) else (120,120,120)
                pygame.draw.circle(surface, color, pos, int(5 * self.zoom_level))
                text = self.font.render(comp['id'], True, color)
                surface.blit(text, (pos[0] + 10, pos[1] - 10))
        if self.highlight and self.overlay_text:            
            y_offset = 50
            for text in self.overlay_text:
                text_surface = self.big_font.render(text, True, (255, 255, 255))
                surface.blit(text_surface, (50, y_offset))
                y_offset += 30



class NeuralNetAnimation:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.num_nodes = random.randint(15, 35)
        self.nodes = [(random.randint(10, width - 10), random.randint(10, height - 10)) for _ in range(self.num_nodes)]
        self.node_speeds = [(random.uniform(-0.3, 0.8), random.uniform(-0.3, 0.8)) for _ in range(self.num_nodes)]
        self.connections = self.generate_connections()
        self.time = 0
        self.delay_frames = 30
        self.flashing_connections = {}

    def update(self):
        self.time += 0.1
        if self.time % self.delay_frames == 0:
            self.remove_flashing_connections()

        for i in range(self.num_nodes):
            dx, dy = self.node_speeds[i]
            new_x = self.nodes[i][0] + dx
            new_y = self.nodes[i][1] + dy
            if new_x < 50 or new_x > self.width - 50:
                dx *= -1
            if new_y < 50 or new_y > self.height - 50:
                dy *= -1

            self.node_speeds[i] = (dx, dy)
            self.nodes[i] = (new_x, new_y)

        self.update_flashing_connections()

    def draw(self, surface):
        for i, j in self.connections:
            if (i, j) not in self.flashing_connections or self.flashing_connections[(i, j)] % 10 < 5:
                pygame.draw.line(surface, (160, 160, 160), self.nodes[i], self.nodes[j], 2)

        for node in self.nodes:
            pygame.draw.circle(surface, (255, 255, 255), (int(node[0]), int(node[1])), 3)

    def generate_connections(self):
        connections = []
        for i in range(self.num_nodes):
            num_connections = random.randint(1, 3)
            possible_targets = [j for j in range(self.num_nodes) if j != i]
            random.shuffle(possible_targets)
            for target_index in possible_targets[:num_connections]:
                connections.append((i, target_index))
        return connections

    def update_flashing_connections(self):
        if random.random() < 0.04 and self.connections:
            connection = random.choice(self.connections)
            self.flashing_connections[connection] = random.randint(10, 30)

        to_remove = []
        for connection in self.flashing_connections:
            self.flashing_connections[connection] -= 1
            if self.flashing_connections[connection] <= 0:
                to_remove.append(connection)
        
        for connection in to_remove:
            self.connections.remove(connection)
            del self.flashing_connections[connection]

    def remove_flashing_connections(self):
        self.connections = [conn for conn in self.connections if conn not in self.flashing_connections]
        self.flashing_connections.clear()

    def reset(self):
        self.__init__(self.width, self.height)

    def should_switch(self) -> bool:
        return self.time >= self.delay_frames


class HealthMonitorAnimation:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.time = 0
        self.delay_frames = 30
        self.systems = [
            {'color': (200, 200, 200), 'bg_color': (50, 50, 50), 'pattern': 'cardiac'},
            {'color': (180, 180, 180), 'bg_color': (40, 40, 40), 'pattern': 'metabolic'},
            {'color': (160, 160, 160), 'bg_color': (30, 30, 30), 'pattern': 'nervous'},
            {'color': (140, 140, 140), 'bg_color': (20, 20, 20), 'pattern': 'pulmonary'},
            {'color': (120, 120, 120), 'bg_color': (10, 10, 10), 'pattern': 'integration'},
            {'color': (100, 100, 100), 'bg_color': (0, 0, 0), 'pattern': 'locomotor'}
        ]
        self.wave_data = {system['pattern']: [0] * 200 for system in self.systems}

    def generate_point(self, pattern, time):
        if pattern == 'cardiac':
            base = math.sin(time * 0.1) * 20
            if int(time * 10) % 20 == 0:
                base = 40
            return base
        elif pattern == 'metabolic':
            return math.sin(time * 0.05) * 15 + random.randint(-5, 5)
        elif pattern == 'nervous':
            return 20 if int(time * 10) % 10 == 0 else -5
        elif pattern == 'pulmonary':
            return math.sin(time * 0.3) * 10 + random.randint(-8, 8)
        elif pattern == 'integration':
            return 20 if int(time * 10) % 30 == 0 else 0
        elif pattern == 'locomotor':
            return random.randint(-20, 20)

    def update(self):
        self.time += 0.05
        for system in self.systems:
            self.wave_data[system['pattern']].pop(0)
            self.wave_data[system['pattern']].append(self.generate_point(system['pattern'], self.time))

    def draw(self, surface):
        for x in range(0, self.width, 20):
            pygame.draw.line(surface, (30, 30, 30), (x, 0), (x, self.height))
        for y in range(0, self.height, 20):
            pygame.draw.line(surface, (30, 30, 30), (0, y), (self.width, y))
        system_height = self.height // len(self.systems)
        for i, system in enumerate(self.systems):
            center_y = i * system_height + system_height // 2
            points = []
            
            for x, y in enumerate(self.wave_data[system['pattern']]):
                point_x = x * (self.width / 200)
                points.append((point_x, center_y + y))
            
            if len(points) >= 2:
                pygame.draw.lines(surface, system['color'], False, points, 2)

    def should_switch(self):
        return self.time >= self.delay_frames

    def reset(self):
        self.time = 0
        for system in self.systems:
            self.wave_data[system['pattern']] = [0] * 200




class WormholeAnimation:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.time = 0
        self.delay_frames = 5
        self.num_rings = 60
        self.radial_lines = 40
        self.radius = 150
        self.tunnel_length = 3000
        self.target_x = 0
        self.target_y = 0
        self.next_target_x = 0
        self.next_target_y = 0
        self.target_change_timer = 0
        
    def update(self):
        self.time += 0.02
        self.target_change_timer += 0.01
        if self.target_change_timer >= 1.0:
            self.next_target_x = random.uniform(-150, 150)
            self.next_target_y = random.uniform(-150, 150)
            self.target_change_timer = 0
        t = math.sin(self.target_change_timer * math.pi * 0.5)
        self.target_x += (self.next_target_x - self.target_x) * t * 0.02
        self.target_y += (self.next_target_y - self.target_y) * t * 0.02
    
    def draw(self, surface):
        z_offset = (self.time * 100) % 50
        visible_rings_step = 2
        
        all_rings = []
        for depth in range(self.num_rings):
            points, colors = self.get_ring_points(depth, z_offset)
            all_rings.append((depth, points, colors))
        
        for index, (depth, points, colors) in enumerate(all_rings):
            if index % visible_rings_step != 0:
                continue
            
            for i in range(len(points)):
                next_i = (i + 1) % len(points)
                color_val = colors[i]
                pygame.draw.line(surface, (color_val, color_val, color_val), points[i], points[next_i], 1)
            
            if depth < self.num_rings - 1:
                next_points, next_colors = self.get_ring_points(depth + 1, z_offset)
                for i in range(0, len(points), 2):
                    color_val = (colors[i] + next_colors[i]) // 2
                    pygame.draw.line(surface, (color_val, color_val, color_val), points[i], next_points[i], 1)

    def get_ring_points(self, depth, z_offset):
        points = []
        colors = []
        
        z = depth * 50 - z_offset
        scale = z / self.tunnel_length

        influence = scale ** 2
        target_x_effect = self.target_x * influence
        target_y_effect = self.target_y * influence
        
        for i in range(self.radial_lines):
            angle = (i / self.radial_lines) * 2 * math.pi
            
            ring_radius = self.radius * (1 - scale * 0.6)
            base_x = math.cos(angle) * ring_radius
            base_y = math.sin(angle) * ring_radius
            
            x = base_x + target_x_effect
            y = base_y + target_y_effect
            
            depth_factor = 2500 / (z + 2500)
            screen_x = x * depth_factor + self.width / 2
            screen_y = y * depth_factor + self.height / 2
            
            intensity = max(0, min(255, (1 - scale) * 255))
            if z > self.tunnel_length * 0.8:
                intensity *= (1 - (z - self.tunnel_length * 0.8) / (self.tunnel_length * 0.2))
            
            points.append((int(screen_x), int(screen_y)))
            colors.append(int(intensity))
            
        return points, colors

        
    def should_switch(self):
        return self.time >= self.delay_frames
    
    def reset(self):
        self.time = 0
        self.target_x = 0
        self.target_y = 0
        self.next_target_x = 0
        self.next_target_y = 0
        self.target_change_timer = 0