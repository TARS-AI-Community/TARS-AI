import math
import random
import time
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np

class BrainVisualization:
    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height
        self.BACKGROUND = (0, 0, 0, 150)  
        self.NODE_COLOR = (220, 240, 255, 200)
        self.EDGE_COLOR = (100, 170, 255, 180)
        self.SPHERE_COLOR = (0, 215, 90, 120)
        self.num_nodes = 300
        self.brain_width = 6
        self.brain_height = 6
        self.brain_depth = 6
        self.connections_per_node = 4
        self.rotation_y = 0
        self.rotation_x = 0
        self.sphere_rotation_angle = 0.0
        self.sphere_rotation_speed = 0.05  
        self.sphere_rotation_axis = (1, 1, 0)  
        self.nodes = []
        self.edges = []
        self.initialized = False
        self.wave_active = False
        self.wave_origin = (0, 0, 0)
        self.wave_direction = (1, 0, 0)
        self.wave_start_time = 0.0
        self.wave_duration = 3.0
        self.wave_speed = 1.0
        self.wave_amplitude = 1.5
        self.wave_progress = 0.0
        self.wave_color = (255, 100, 50)
        self.particles = []
        self.max_particles = 800
        self.node_effects = []  

    def initialize(self):
        if self.initialized:
            return
        self.generate_brain()
        self.node_effects = [(0.0, 0.0) for _ in range(len(self.nodes))]  
        self.initialized = True

    def generate_brain(self):
        self.nodes = []
        for _ in range(self.num_nodes):
            theta = random.uniform(0, 2 * math.pi)
            phi = random.uniform(0, math.pi)
            radius = random.uniform(0.8, 1.0)
            x = self.brain_width * radius * math.sin(phi) * math.cos(theta)
            y = self.brain_height * radius * math.sin(phi) * math.sin(theta)
            z = self.brain_depth * radius * math.cos(phi)
            x += random.uniform(-0.5, 0.5)
            y += random.uniform(-0.5, 0.5)
            z += random.uniform(-0.5, 0.5)
            if x > 0:
                x += 0.5
            else:
                x -= 0.5
            self.nodes.append((x, y, z))
        self.edges = []
        for i in range(len(self.nodes)):
            distances = [(j, np.sqrt((self.nodes[i][0] - self.nodes[j][0])**2 + 
                                (self.nodes[i][1] - self.nodes[j][1])**2 + 
                                (self.nodes[i][2] - self.nodes[j][2])**2))
                     for j in range(len(self.nodes)) if i != j]
            distances.sort(key=lambda x: x[1])
            for j in range(min(self.connections_per_node, len(distances))):
                if j < 3 or random.random() < 0.3:
                    self.edges.append((i, distances[j][0]))
            if random.random() < 0.1:
                far_idx = random.randint(len(distances) // 2, len(distances) - 1)
                self.edges.append((i, distances[far_idx][0]))

    def draw_sphere(self):

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        r, g, b, a = self.SPHERE_COLOR

        glColor4f(r / 255.0, g / 255.0, b / 255.0, a / 255.0)  
        quadric = gluNewQuadric()
        gluQuadricDrawStyle(quadric, GLU_LINE)
        gluSphere(quadric, 2.5, 16, 16)
        gluDeleteQuadric(quadric)

        num_layers = 3
        blur_amount = 0.1

        for i in range(num_layers):
            alpha = (a / 255.0) * (1 - i / num_layers) * 0.5
            glColor4f(r / 255.0, g / 255.0, b / 255.0, alpha)

            glPushMatrix()
            glScalef(1 + i * blur_amount, 1 + i * blur_amount, 1 + i * blur_amount)
            quadric = gluNewQuadric()
            gluQuadricDrawStyle(quadric, GLU_FILL)
            gluSphere(quadric, 2.5, 16, 16)
            gluDeleteQuadric(quadric)
            glPopMatrix()

        glDisable(GL_BLEND)

    def draw_nodes(self):

        has_wave_effects = hasattr(self, 'node_effects') and len(self.node_effects) == len(self.nodes)

        r, g, b, a = self.NODE_COLOR
        glDisable(GL_COLOR_MATERIAL)

        for i, node in enumerate(self.nodes):

            wave_value, _ = self.node_effects[i] if has_wave_effects else (0.0, 0.0)

            if wave_value > 0.01:

                glPointSize(5.0 + wave_value * 3.0)

                wave_r, wave_g, wave_b = self.wave_color
                blend_factor = min(1.0, wave_value)

                node_r = r * (1 - blend_factor) + wave_r * blend_factor
                node_g = g * (1 - blend_factor) + wave_g * blend_factor
                node_b = b * (1 - blend_factor) + wave_b * blend_factor
                node_a = min(255, a + wave_value * 100)

                glColor4f(node_r/255.0, node_g/255.0, node_b/255.0, node_a/255.0)

                glBegin(GL_POINTS)
                glVertex3f(node[0], node[1], node[2])
                glEnd()

                if wave_value > 0.5:
                    glPointSize(9.0 + wave_value * 5.0)
                    glow_alpha = 0.3 * wave_value
                    glColor4f(node_r/255.0, node_g/255.0, node_b/255.0, glow_alpha)
                    glBegin(GL_POINTS)
                    glVertex3f(node[0], node[1], node[2])
                    glEnd()
            else:

                glPointSize(5.0)
                glColor4f(r/255.0, g/255.0, b/255.0, a/255.0)
                glBegin(GL_POINTS)
                glVertex3f(node[0], node[1], node[2])
                glEnd()

    def draw_edges(self):

        has_wave_effects = hasattr(self, 'node_effects') and len(self.node_effects) == len(self.nodes)

        r, g, b, a = self.EDGE_COLOR
        glDisable(GL_COLOR_MATERIAL)

        for edge in self.edges:
            n1_idx, n2_idx = edge
            n1 = self.nodes[n1_idx]
            n2 = self.nodes[n2_idx]
            wave_value1, _ = self.node_effects[n1_idx] if has_wave_effects else (0.0, 0.0)
            wave_value2, _ = self.node_effects[n2_idx] if has_wave_effects else (0.0, 0.0)
            wave_value = max(wave_value1, wave_value2)

            if wave_value > 0.01:

                wave_r, wave_g, wave_b = self.wave_color
                blend_factor = min(1.0, wave_value)

                edge_r = r * (1 - blend_factor) + wave_r * blend_factor
                edge_g = g * (1 - blend_factor) + wave_g * blend_factor
                edge_b = b * (1 - blend_factor) + wave_b * blend_factor
                edge_a = min(255, a + wave_value * 100)

                glColor4f(edge_r/255.0, edge_g/255.0, edge_b/255.0, edge_a/255.0)
                glLineWidth(1.0 + wave_value * 2.0)
            else:

                glColor4f(r/255.0, g/255.0, b/255.0, a/255.0)
                glLineWidth(1.0)

            glBegin(GL_LINES)
            glVertex3f(n1[0], n1[1], n1[2])
            glVertex3f(n2[0], n2[1], n2[2])
            glEnd()

    def draw_particles(self):
        if not hasattr(self, 'particles'):
            return

        glDisable(GL_COLOR_MATERIAL)

        for particle in self.particles:
            glPointSize(particle['size'])
            glColor4f(*particle['color'])

            glBegin(GL_POINTS)
            glVertex3f(*particle['position'])
            glEnd()

    def add_wave_effect(self, origin=(0, 0, 0), direction=(1, 0, 0), 
                      speed=1.0, duration=3.0, amplitude=1.5, color=(255, 100, 50)):

        self.wave_active = True
        self.wave_origin = origin
        self.wave_start_time = 0.0
        self.wave_duration = duration
        self.wave_speed = speed
        self.wave_amplitude = amplitude
        self.wave_progress = 0.0

        dir_norm = np.array(direction, dtype=float)
        self.wave_direction = dir_norm / np.linalg.norm(dir_norm) if np.linalg.norm(dir_norm) > 0 else np.array([1, 0, 0])

        self.wave_color = color
        self.particles = []

        self.node_effects = [(0.0, 0.0) for _ in range(len(self.nodes))]  

    def _update_wave(self, delta_time=0.033):
        if not self.wave_active:
            return

        self.wave_start_time += delta_time
        self.wave_progress = self.wave_start_time * self.wave_speed

        if self.wave_start_time >= self.wave_duration:
            self.wave_active = False
            return

        wave_front = self.wave_progress
        wave_tail = max(0, wave_front - 3.0)

        for i, node in enumerate(self.nodes):

            node_pos = np.array(node)
            origin_pos = np.array(self.wave_origin)

            direction_distance = np.dot(node_pos - origin_pos, self.wave_direction)

            perpendicular_vector = node_pos - origin_pos - direction_distance * self.wave_direction
            perpendicular_distance = np.linalg.norm(perpendicular_vector)

            wave_influence = 0.0
            decay_time = 0.0

            perpendicular_factor = max(0, 1.0 - perpendicular_distance * 0.4)
            if wave_tail <= direction_distance <= wave_front and perpendicular_factor > 0.1:

                relative_pos = (direction_distance - wave_tail) / (wave_front - wave_tail) if wave_front > wave_tail else 0

                wave_shape = np.sin(relative_pos * np.pi) 
                wave_influence = wave_shape * self.wave_amplitude * perpendicular_factor
                decay_time = self.wave_start_time + random.uniform(0.3, 0.8)  

                if wave_influence > 0.5 and random.random() < 0.3 and len(self.particles) < self.max_particles:

                    self.particles.append({
                        'position': list(node),
                        'velocity': [
                            random.uniform(-0.05, 0.05) + self.wave_direction[0] * 0.1,
                            random.uniform(-0.05, 0.05) + self.wave_direction[1] * 0.1,
                            random.uniform(-0.05, 0.05) + self.wave_direction[2] * 0.1
                        ],
                        'life': random.uniform(0.5, 1.5),
                        'size': random.uniform(1.5, 3.0),
                        'color': (
                            self.wave_color[0] / 255.0,
                            self.wave_color[1] / 255.0,
                            self.wave_color[2] / 255.0,
                            random.uniform(0.6, 0.9)
                        )
                    })

            current_effect, current_decay = self.node_effects[i]
            if wave_influence > current_effect:
                self.node_effects[i] = (wave_influence, decay_time)
            elif self.wave_start_time > current_decay:

                self.node_effects[i] = (current_effect * 0.95, current_decay)

        updated_particles = []
        for particle in self.particles:

            particle['position'][0] += particle['velocity'][0]
            particle['position'][1] += particle['velocity'][1]
            particle['position'][2] += particle['velocity'][2]

            particle['life'] -= delta_time
            particle['velocity'][1] -= 0.01  
            particle['color'] = (
                particle['color'][0],
                particle['color'][1],
                particle['color'][2],
                particle['color'][3] * 0.95  
            )

            if particle['life'] > 0:
                updated_particles.append(particle)

        self.particles = updated_particles

    def add_ripple_effect(self, origin=(0, 0, 0), speed=1.0, duration=3.0, 
                        amplitude=1.5, color=(255, 100, 50), thickness=1.0):

        self.wave_active = True
        self.wave_origin = origin
        self.wave_start_time = 0.0
        self.wave_duration = duration
        self.wave_speed = speed
        self.wave_amplitude = amplitude
        self.wave_progress = 0.0
        self.wave_thickness = thickness

        self.is_ripple = True

        self.wave_color = color
        self.particles = []

        self.node_effects = [(0.0, 0.0) for _ in range(len(self.nodes))]  

    def _update_ripple(self, delta_time=0.033):
        if not self.wave_active:
            return

        self.wave_start_time += delta_time
        self.wave_progress = self.wave_start_time * self.wave_speed

        if self.wave_start_time >= self.wave_duration:
            self.wave_active = False
            return

        max_radius = 15.0  
        ripple_radius = self.wave_progress * 2.0  
        ripple_radius = min(ripple_radius, max_radius)  

        thickness = self.wave_thickness
        inner_radius = max(0, ripple_radius - thickness)

        for i, node in enumerate(self.nodes):

            node_pos = np.array(node)
            origin_pos = np.array(self.wave_origin)
            distance = np.linalg.norm(node_pos - origin_pos)

            wave_influence = 0.0
            decay_time = 0.0

            if inner_radius <= distance <= ripple_radius:

                relative_pos = (distance - inner_radius) / thickness if thickness > 0 else 0

                ripple_shape = np.sin(relative_pos * np.pi)
                wave_influence = ripple_shape * self.wave_amplitude
                decay_time = self.wave_start_time + random.uniform(0.3, 0.8)

                if wave_influence > 0.5 and random.random() < 0.3 and len(self.particles) < self.max_particles:

                    direction = node_pos - origin_pos
                    if np.linalg.norm(direction) > 0:
                        direction = direction / np.linalg.norm(direction)
                    else:
                        direction = np.array([0, 1, 0])  

                    self.particles.append({
                        'position': list(node),
                        'velocity': [
                            direction[0] * random.uniform(0.05, 0.15),
                            direction[1] * random.uniform(0.05, 0.15),
                            direction[2] * random.uniform(0.05, 0.15)
                        ],
                        'life': random.uniform(0.5, 1.5),
                        'size': random.uniform(1.5, 3.0),
                        'color': (
                            self.wave_color[0] / 255.0,
                            self.wave_color[1] / 255.0,
                            self.wave_color[2] / 255.0,
                            random.uniform(0.6, 0.9)
                        )
                    })

            current_effect, current_decay = self.node_effects[i]
            if wave_influence > current_effect:
                self.node_effects[i] = (wave_influence, decay_time)
            elif self.wave_start_time > current_decay:

                self.node_effects[i] = (current_effect * 0.95, current_decay)

        updated_particles = []
        for particle in self.particles:

            particle['position'][0] += particle['velocity'][0]
            particle['position'][1] += particle['velocity'][1]
            particle['position'][2] += particle['velocity'][2]

            particle['life'] -= delta_time
            particle['velocity'][1] -= 0.01  
            particle['color'] = (
                particle['color'][0],
                particle['color'][1],
                particle['color'][2],
                particle['color'][3] * 0.95  
            )

            if particle['life'] > 0:
                updated_particles.append(particle)

        self.particles = updated_particles

    def add_band_effect(self, origin=(0, 0, 0), direction=(1, 0, 0), speed=0.8, duration=5.0, 
                    amplitude=2.0, color=(255, 100, 50), band_width=1.5):

        self.wave_active = True
        self.wave_origin = origin
        self.wave_start_time = 0.0
        self.wave_duration = duration
        self.wave_speed = speed
        self.wave_amplitude = amplitude
        self.wave_progress = 0.0
        self.band_width = band_width

        self.is_band = True
        self.is_ripple = False

        adjusted_origin = np.array(origin) - np.array(direction, dtype=float) * 10.0
        self.wave_origin = tuple(adjusted_origin)

        dir_norm = np.array(direction, dtype=float)
        self.wave_direction = dir_norm / np.linalg.norm(dir_norm) if np.linalg.norm(dir_norm) > 0 else np.array([1, 0, 0])

        self.wave_color = color
        self.particles = []

        self.node_effects = [(0.0, 0.0) for _ in range(len(self.nodes))]  

    def _update_band(self, delta_time=0.033):
        if not self.wave_active:
            return

        self.wave_start_time += delta_time
        self.wave_progress = self.wave_start_time * self.wave_speed

        if self.wave_start_time >= self.wave_duration:
            self.wave_active = False
            return

        max_travel_distance = 20.0  
        band_center_distance = (self.wave_progress / self.wave_duration) * max_travel_distance
        band_center = np.array(self.wave_origin) + self.wave_direction * band_center_distance

        half_width = self.band_width * 3.0  

        for i, node in enumerate(self.nodes):
            node_pos = np.array(node)
            node_to_origin = node_pos - np.array(self.wave_origin)
            projected_distance = np.dot(node_to_origin, self.wave_direction)
            distance_to_band_center = abs(projected_distance - band_center_distance)
            band_center_to_node = node_pos - (np.array(self.wave_origin) + self.wave_direction * band_center_distance)
            distance_to_plane = abs(np.dot(band_center_to_node, self.wave_direction))
            wave_influence = 0.0
            decay_time = 0.0
            if distance_to_plane <= half_width:
                relative_pos = distance_to_plane / half_width if half_width > 0 else 0

                band_shape = (1.0 - relative_pos) ** 2  
                wave_influence = band_shape * self.wave_amplitude
                decay_time = self.wave_start_time + 0.3  

                if wave_influence > 0.5 and random.random() < 0.3 and len(self.particles) < self.max_particles:

                    self.particles.append({
                        'position': list(node),
                        'velocity': [
                            self.wave_direction[0] * random.uniform(0.1, 0.2) + random.uniform(-0.05, 0.05),
                            self.wave_direction[1] * random.uniform(0.1, 0.2) + random.uniform(-0.05, 0.05),
                            self.wave_direction[2] * random.uniform(0.1, 0.2) + random.uniform(-0.05, 0.05)
                        ],
                        'life': random.uniform(0.4, 1.0),  
                        'size': random.uniform(2.0, 5.0),  
                        'color': (
                            self.wave_color[0] / 255.0,
                            self.wave_color[1] / 255.0,
                            self.wave_color[2] / 255.0,
                            random.uniform(0.7, 1.0)  
                        )
                    })

            current_effect, current_decay = self.node_effects[i]
            if wave_influence > current_effect:
                self.node_effects[i] = (wave_influence, decay_time)
            elif self.wave_start_time > current_decay:

                self.node_effects[i] = (current_effect * 0.9, current_decay)

        updated_particles = []
        for particle in self.particles:

            particle['position'][0] += particle['velocity'][0]
            particle['position'][1] += particle['velocity'][1]
            particle['position'][2] += particle['velocity'][2]

            particle['life'] -= delta_time
            particle['color'] = (
                particle['color'][0],
                particle['color'][1],
                particle['color'][2],
                particle['color'][3] * 0.95  
            )

            if particle['life'] > 0:
                updated_particles.append(particle)

        self.particles = updated_particles


    def add_matrix_data_insertion(self, target_nodes=None, duration=4.0, color=(0, 255, 0), 
                                speed=1.0, density=0.8, entry_point=None):

        self._cleanup_matrix_effects()

        self.matrix_active = True
        self.matrix_start_time = 0.0
        self.matrix_duration = duration
        self.matrix_speed = speed
        self.matrix_color = color
        self.matrix_progress = 0.0
        self.matrix_density = min(1.0, max(0.1, density))

        max_targets = min(20, int(len(self.nodes) * 0.1))  
        num_targets = min(max(3, max_targets), len(self.nodes))  # Ensure num_targets is valid

        if target_nodes is None:
            if num_targets > 0:
                self.matrix_targets = random.sample(range(len(self.nodes)), num_targets)
            else:
                self.matrix_targets = []
        else:
            self.matrix_targets = target_nodes[:max_targets] if len(target_nodes) > max_targets else target_nodes

        if entry_point is None:
            self.matrix_entry = (0, self.brain_height * 1.5, 0)
        else:
            self.matrix_entry = entry_point

        self.binary_streams = []
        self.node_matrix_effects = {}
        max_streams_per_target = 2  

        for target_idx in self.matrix_targets:
            target_pos = self.nodes[target_idx]
            streams_per_target = min(max_streams_per_target, 
                                    max(1, int(max_streams_per_target * self.matrix_density)))

            for _ in range(streams_per_target):


                start_pos = (
                    self.matrix_entry[0] + random.uniform(-1.0, 1.0),
                    self.matrix_entry[1] + random.uniform(-0.5, 0.5),
                    self.matrix_entry[2] + random.uniform(-1.0, 1.0)
                )

                stream_length = min(20, random.randint(10, 20))
                binary_chars = []
                for _ in range(stream_length):
                    if random.random() < 0.8:  
                        binary_chars.append(random.choice(['0', '1']))
                    else:  
                        binary_chars.append(random.choice(['0', '1', '丂', '乃']))

                self.binary_streams.append({
                    'start_pos': start_pos,
                    'target_pos': target_pos,
                    'target_idx': target_idx,
                    'binary': binary_chars,
                    'progress': 0.0,
                    'delay': random.uniform(0, 1.0),
                    'speed_factor': random.uniform(0.8, 1.2),
                    'lifetime': random.uniform(1.0, 2.0),  
                    'chars_active': [],
                    'char_positions': [],
                    'active': True
                })

    def _cleanup_matrix_effects(self):
        if hasattr(self, 'binary_streams'):
            self.binary_streams.clear()

        if hasattr(self, 'node_matrix_effects'):
            if isinstance(self.node_matrix_effects, dict):
                self.node_matrix_effects.clear()
            else:
                self.node_matrix_effects = {}

        if hasattr(self, 'particles'):

            max_particles = self.max_particles if hasattr(self, 'max_particles') else 200
            if len(self.particles) > max_particles:
                self.particles = self.particles[-max_particles:]

    def _update_matrix_effect(self, delta_time=0.033):
        if not hasattr(self, 'matrix_active') or not self.matrix_active:
            return

        self.matrix_start_time += delta_time
        self.matrix_progress = self.matrix_start_time / self.matrix_duration

        if self.matrix_start_time >= self.matrix_duration:
            self.matrix_active = False
            self._cleanup_matrix_effects()
            return

        active_streams = [s for s in self.binary_streams if s['active']]
        streams_to_process = active_streams

        for stream in streams_to_process:

            if stream['delay'] > 0:
                stream['delay'] -= delta_time
                continue

            stream['progress'] += delta_time * self.matrix_speed * stream['speed_factor']

            t = min(1.0, stream['progress'])

            if t <= 0.0 or t >= 1.0:
                if t >= 1.0 and stream['active']:

                    target_idx = stream['target_idx']
                    self.node_matrix_effects[target_idx] = (
                        1.0,  
                        self.matrix_start_time + stream['lifetime'],  
                        random.choice(stream['binary'])  
                    )

                    if hasattr(self, 'particles'):
                        num_particles = min(8, random.randint(3, 8))
                        for _ in range(num_particles):
                            self.particles.append({
                                'position': list(stream['target_pos']),
                                'velocity': [
                                    random.uniform(-0.1, 0.1),
                                    random.uniform(-0.1, 0.1),
                                    random.uniform(-0.1, 0.1)
                                ],
                                'life': random.uniform(0.3, 0.6),
                                'size': random.uniform(1.0, 2.0),
                                'color': (
                                    self.matrix_color[0] / 255.0,
                                    self.matrix_color[1] / 255.0,
                                    self.matrix_color[2] / 255.0,
                                    random.uniform(0.7, 0.9)
                                )
                            })

                    stream['active'] = False
                continue

            start_pos = stream['start_pos']
            target_pos = stream['target_pos']
            current_pos = (
                start_pos[0] + (target_pos[0] - start_pos[0]) * t,
                start_pos[1] + (target_pos[1] - start_pos[1]) * t,
                start_pos[2] + (target_pos[2] - start_pos[2]) * t
            )

            stream['chars_active'] = []
            stream['char_positions'] = []

            num_chars = len(stream['binary'])
            path_length = np.linalg.norm(np.array(target_pos) - np.array(start_pos))
            char_spacing = path_length / (num_chars + 1)

            visible_char_count = min(10, num_chars)  
            for i in range(visible_char_count):

                char_t = t - (i * char_spacing / path_length)

                if 0.0 <= char_t <= 1.0:
                    char_pos = (
                        start_pos[0] + (target_pos[0] - start_pos[0]) * char_t,
                        start_pos[1] + (target_pos[1] - start_pos[1]) * char_t,
                        start_pos[2] + (target_pos[2] - start_pos[2]) * char_t
                    )

                    stream['chars_active'].append(stream['binary'][i])
                    stream['char_positions'].append(char_pos)

                    if random.random() < 0.03:  
                        if random.random() < 0.8:
                            stream['binary'][i] = random.choice(['0', '1'])
                        else:
                            stream['binary'][i] = random.choice(['0', '1', '丂', '乃'])

        if random.random() < 0.5:  

            keys_to_remove = []
            for node_idx, (effect, decay_time, char) in self.node_matrix_effects.items():
                if effect > 0.01:
                    if self.matrix_start_time > decay_time:

                        new_effect = effect * 0.9
                        if new_effect > 0.05:  
                            self.node_matrix_effects[node_idx] = (new_effect, decay_time, char)
                        else:
                            keys_to_remove.append(node_idx)

            for key in keys_to_remove:
                del self.node_matrix_effects[key]

    def _draw_matrix_streams(self):
        if not hasattr(self, 'binary_streams') or not self.matrix_active:
            return

        glDisable(GL_COLOR_MATERIAL)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        r, g, b = self.matrix_color

        all_points = []
        all_colors = []

        for stream in self.binary_streams:
            if not stream['active'] or stream['delay'] > 0:
                continue

            for i, (char, pos) in enumerate(zip(stream['chars_active'], stream['char_positions'])):

                alpha = 0.9 - (i / max(1, len(stream['chars_active']))) * 0.5
                all_points.append(pos)
                all_colors.append((r/255.0, g/255.0, b/255.0, alpha))

        if all_points:

            glPointSize(4.0)  
            glBegin(GL_POINTS)
            for point, color in zip(all_points, all_colors):
                glColor4f(*color)
                glVertex3f(*point)
            glEnd()

        if len(self.node_matrix_effects) > 0:

            glPointSize(8.0)  
            glBegin(GL_POINTS)
            for node_idx, (effect, decay_time, char) in self.node_matrix_effects.items():
                if effect > 0.01:
                    node = self.nodes[node_idx]
                    pulse = 1.0 + 0.5 * ((self.matrix_start_time * 8) % 1.0)  
                    glColor4f(r/255.0, g/255.0, b/255.0, effect * 0.9)  
                    glVertex3f(node[0], node[1], node[2])
            glEnd()

            has_strong_effects = any(effect > 0.3 for effect, _, _ in self.node_matrix_effects.values())
            if has_strong_effects:

                glPointSize(14.0)  
                glBegin(GL_POINTS)
                for node_idx, (effect, decay_time, char) in self.node_matrix_effects.items():
                    if effect > 0.3:  
                        node = self.nodes[node_idx]
                        glColor4f(r/255.0, g/255.0, b/255.0, effect * 0.4)
                        glVertex3f(node[0], node[1], node[2])
                glEnd()

                glPointSize(20.0)  
                glBegin(GL_POINTS)
                for node_idx, (effect, decay_time, char) in self.node_matrix_effects.items():
                    if effect > 0.7:  
                        node = self.nodes[node_idx]
                        glColor4f(r/255.0, g/255.0, b/255.0, effect * 0.2)
                        glVertex3f(node[0], node[1], node[2])
                glEnd()

    def render2(self):
        if not self.initialized:
            self.initialize()

        glPushAttrib(GL_ALL_ATTRIB_BITS)

        glDisable(GL_LIGHTING)
        glDisable(GL_COLOR_MATERIAL)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluPerspective(45, (self.width / self.height), 0.1, 50.0)

        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        self.rotation_y += 0.08
        self.rotation_x += 0.12
        self.sphere_rotation_angle += self.sphere_rotation_speed

        glPushMatrix()
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -15)

        glRotatef(self.rotation_y, 0, 1, 0)
        glRotatef(self.rotation_x, 1, 0, 0)

        self.draw_edges()
        self.draw_nodes()

        if hasattr(self, 'matrix_active') and self.matrix_active:
            self._draw_matrix_streams()

        glPopMatrix()

        glPushMatrix()
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -15)

        glRotatef(self.sphere_rotation_angle, 
                self.sphere_rotation_axis[0], 
                self.sphere_rotation_axis[1], 
                self.sphere_rotation_axis[2])

        self.draw_sphere()
        glPopMatrix()

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()

        current_time = time.time() if hasattr(time, 'time') else 0
        if not hasattr(self, 'last_frame_time'):
            self.last_frame_time = current_time

        delta_time = min(0.1, current_time - self.last_frame_time)  
        self.last_frame_time = current_time

        if hasattr(self, 'wave_active') and self.wave_active:
            if hasattr(self, 'is_band') and self.is_band:
                self._update_band(delta_time)
            elif hasattr(self, 'is_ripple') and self.is_ripple:
                self._update_ripple(delta_time)
            else:
                self._update_wave(delta_time)

        if hasattr(self, 'matrix_active') and self.matrix_active:
            self._update_matrix_effect(delta_time)

        if hasattr(self, 'particles') and self.particles:
            glPushAttrib(GL_ALL_ATTRIB_BITS)

            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            gluPerspective(45, (self.width / self.height), 0.1, 50.0)

            glMatrixMode(GL_MODELVIEW)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)

            glPushMatrix()
            glLoadIdentity()
            glTranslatef(0.0, 0.0, -15)
            glRotatef(self.rotation_y, 0, 1, 0)
            glRotatef(self.rotation_x, 1, 0, 0)

            if self.particles:
                size_groups = {}
                for particle in self.particles:
                    size = particle['size']
                    if size not in size_groups:
                        size_groups[size] = []
                    size_groups[size].append(particle)

                for size, particles in size_groups.items():
                    glPointSize(size)
                    glBegin(GL_POINTS)
                    for particle in particles:
                        glColor4f(*particle['color'])
                        glVertex3f(*particle['position'])
                    glEnd()

            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glPopAttrib()
            glMatrixMode(GL_MODELVIEW)

        if hasattr(self, 'particles') and self.particles:
            max_particles = self.max_particles if hasattr(self, 'max_particles') else 200
            if len(self.particles) > max_particles:
                self.particles = self.particles[-max_particles:]

        glPopAttrib()
        glMatrixMode(GL_MODELVIEW)

    def render(self, brain_box, screen_height):
        """
        Renders the Brain Visualization inside the specified Pygame brain_box.

        :param brain_box: Object containing x, y, width, and height (Pygame surface area)
        :param screen_height: Total screen height to adjust OpenGL y-coordinates
        """
        if not self.initialized:
            self.initialize()

        glPushAttrib(GL_ALL_ATTRIB_BITS)  # Save OpenGL state

        try:
            # ✅ Fix OpenGL viewport (Pygame y-coordinates start from top, OpenGL from bottom)
            adjusted_y = screen_height - (brain_box.y + brain_box.height)  # Flip y-axis for OpenGL
            glViewport(brain_box.x, adjusted_y, brain_box.width, brain_box.height)

            # ✅ Projection matrix setup
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()

            aspect_ratio = brain_box.width / max(1, brain_box.height)  # Prevent division by zero
            gluPerspective(45, aspect_ratio, 0.1, 50.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            # ✅ Enable depth testing and transparency blending
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            # ✅ Apply transformations
            self.rotation_y += 0.08
            self.rotation_x += 0.12
            self.sphere_rotation_angle += self.sphere_rotation_speed

            glPushMatrix()
            glTranslatef(0.0, 0.0, -15)  # Keep the brain inside view
            glRotatef(self.rotation_y, 0, 1, 0)
            glRotatef(self.rotation_x, 1, 0, 0)

            self.draw_edges()
            self.draw_nodes()

            if hasattr(self, 'matrix_active') and self.matrix_active:
                self._draw_matrix_streams()

            glPopMatrix()

            # ✅ Render the rotating sphere
            glPushMatrix()
            glTranslatef(0.0, 0.0, -15)
            glRotatef(self.sphere_rotation_angle, *self.sphere_rotation_axis)
            self.draw_sphere()
            glPopMatrix()

            # ✅ Restore projection and attributes
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)

            # ✅ Time-based updates
            current_time = time.time() if hasattr(time, 'time') else 0
            if not hasattr(self, 'last_frame_time'):
                self.last_frame_time = current_time

            delta_time = min(0.1, current_time - self.last_frame_time)  
            self.last_frame_time = current_time

            # ✅ Handle animation updates
            if hasattr(self, 'wave_active') and self.wave_active:
                if hasattr(self, 'is_band') and self.is_band:
                    self._update_band(delta_time)
                elif hasattr(self, 'is_ripple') and self.is_ripple:
                    self._update_ripple(delta_time)
                else:
                    self._update_wave(delta_time)

            if hasattr(self, 'matrix_active') and self.matrix_active:
                self._update_matrix_effect(delta_time)

            # ✅ Render particles
            if hasattr(self, 'particles') and self.particles:
                glPushAttrib(GL_ALL_ATTRIB_BITS)

                glMatrixMode(GL_PROJECTION)
                glPushMatrix()
                glLoadIdentity()
                gluPerspective(45, aspect_ratio, 0.1, 50.0)

                glMatrixMode(GL_MODELVIEW)
                glEnable(GL_DEPTH_TEST)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE)

                glPushMatrix()
                glLoadIdentity()
                glTranslatef(0.0, 0.0, -15)
                glRotatef(self.rotation_y, 0, 1, 0)
                glRotatef(self.rotation_x, 1, 0, 0)

                if self.particles:
                    size_groups = {}
                    for particle in self.particles:
                        size = particle['size']
                        if size not in size_groups:
                            size_groups[size] = []
                        size_groups[size].append(particle)

                    for size, particles in size_groups.items():
                        glPointSize(size)
                        glBegin(GL_POINTS)
                        for particle in particles:
                            glColor4f(*particle['color'])
                            glVertex3f(*particle['position'])
                        glEnd()

                glPopMatrix()
                glMatrixMode(GL_PROJECTION)
                glPopMatrix()
                glPopAttrib()
                glMatrixMode(GL_MODELVIEW)

            # ✅ Limit particle count
            if hasattr(self, 'particles') and self.particles:
                max_particles = self.max_particles if hasattr(self, 'max_particles') else 200
                if len(self.particles) > max_particles:
                    self.particles = self.particles[-max_particles:]

        finally:
            glPopAttrib()  # Restore OpenGL state



    def set_sphere_rotation(self, speed=None, axis=None):
        if speed is not None:
            self.sphere_rotation_speed = speed
        if axis is not None:
            self.sphere_rotation_axis = axis