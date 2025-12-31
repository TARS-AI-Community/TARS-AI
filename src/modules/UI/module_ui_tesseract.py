# module_ui_tesseract.py
# ----------------------------------------------
# atomikspace (discord)
# olivierdion1@hotmail.com
# ----------------------------------------------
import pygame
import math
import time
import random


class TesseractSystem:
    """Manages a 3D tesseract/hypercube grid animation using pure pygame"""

    def __init__(self, width, height, bg_color=(0, 0, 0)):
        self.width = width
        self.height = height
        self.bg_color = bg_color

        # Animation weights (0..1)
        self.action_weight = 0.0
        self.think_weight = 0.0
        self.memory_weight = 0.0

        # Animation timers
        self.action_end_time = None
        self.think_end_time = None
        self.memory_end_time = None

        # Rotation angles (radians)
        self.rot_x = 0.0
        self.rot_y = 0.0
        self.rot_z = 0.0

        # Grid params - REDUCED for performance
        self.grid_size = 3  # 3x3x3 = 27 cubes for better performance
        self.cube_spacing = 3.5

        # Pulse & color phases
        self.pulse_phase = 0.0
        self.color_phase = 0.0

        # Colors
        self.current_color = [0.3, 0.6, 1.0]
        self.target_color = [0.3, 0.6, 1.0]

        # Camera/projection settings
        self.camera_distance = 18.0
        self.fov = 60.0
        
        # Calculate focal length for perspective projection
        self.focal_length = (min(width, height) / 2) / math.tan(math.radians(self.fov / 2))
        
        # Pre-create reusable surfaces for performance
        self.cube_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.line_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

    # Animation control methods
    def action(self):
        self.action_end_time = time.time() + 5.0

    def add_memory(self):
        self.memory_end_time = time.time() + 4.0

    def think(self):
        self.think_end_time = time.time() + 5.0

    def update(self):
        """Update animation state and rotations"""
        now = time.time()
        fade_speed = 0.03

        # action weight
        if self.action_end_time and now < self.action_end_time:
            self.action_weight = min(1.0, self.action_weight + fade_speed)
        else:
            self.action_weight = max(0.0, self.action_weight - fade_speed)
            if self.action_weight == 0 and self.action_end_time:
                self.action_end_time = None

        # think weight
        if self.think_end_time and now < self.think_end_time:
            self.think_weight = min(1.0, self.think_weight + fade_speed)
        else:
            self.think_weight = max(0.0, self.think_weight - fade_speed)
            if self.think_weight == 0 and self.think_end_time:
                self.think_end_time = None

        # memory weight
        if self.memory_end_time and now < self.memory_end_time:
            self.memory_weight = min(1.0, self.memory_weight + fade_speed)
        else:
            self.memory_weight = max(0.0, self.memory_weight - fade_speed)
            if self.memory_weight == 0 and self.memory_end_time:
                self.memory_end_time = None

        # phases
        if self.memory_weight > 0:
            self.pulse_phase += 0.05
        if self.think_weight > 0.1:
            self.color_phase += 0.01

        # target color
        if self.think_weight > 0.1:
            self.target_color = [
                0.5 + 0.5 * math.sin(self.color_phase),
                0.7 + 0.3 * math.sin(self.color_phase + 2.0),
                1.0
            ]
        elif self.memory_weight > 0.1:
            pulse = (math.sin(self.pulse_phase) + 1.0) / 2.0
            self.target_color = [
                0.4 + pulse * 0.2,
                0.7 + pulse * 0.2,
                1.0
            ]
        else:
            self.target_color = [0.3, 0.6, 1.0]

        # lerp current color to target
        blend_speed = 0.02
        for i in range(3):
            self.current_color[i] += (self.target_color[i] - self.current_color[i]) * blend_speed

        # rotation speeds blended by weights
        base_speed = 0.003
        action_speed = 0.008
        think_speed = 0.015
        memory_speed = 0.001

        rot_speed = base_speed
        rot_speed += (action_speed - base_speed) * self.action_weight
        rot_speed += (think_speed - base_speed) * self.think_weight
        rot_speed += (memory_speed - base_speed) * self.memory_weight

        self.rot_x += rot_speed * 0.5
        self.rot_y += rot_speed * 0.7
        self.rot_z += rot_speed * 0.3

    def rotate_point_3d(self, x, y, z):
        """Apply 3D rotation transformations"""
        # Rotate around X axis
        cos_x = math.cos(self.rot_x)
        sin_x = math.sin(self.rot_x)
        y1 = y * cos_x - z * sin_x
        z1 = y * sin_x + z * cos_x
        x1 = x
        
        # Rotate around Y axis
        cos_y = math.cos(self.rot_y)
        sin_y = math.sin(self.rot_y)
        x2 = x1 * cos_y + z1 * sin_y
        z2 = -x1 * sin_y + z1 * cos_y
        y2 = y1
        
        # Rotate around Z axis
        cos_z = math.cos(self.rot_z)
        sin_z = math.sin(self.rot_z)
        x3 = x2 * cos_z - y2 * sin_z
        y3 = x2 * sin_z + y2 * cos_z
        z3 = z2
        
        return (x3, y3, z3)

    def project_3d_to_2d(self, x, y, z):
        """Project 3D point to 2D screen coordinates with proper perspective"""
        # Move point relative to camera
        z_cam = z + self.camera_distance
        
        # Don't project points behind or too close to camera
        if z_cam < 0.5:
            return None
        
        # Perspective projection
        scale = self.focal_length / z_cam
        x_2d = x * scale + self.width / 2
        y_2d = -y * scale + self.height / 2
        
        return (x_2d, y_2d, z_cam)

    def compute_alpha_by_distance(self, x, y, z):
        """Compute alpha based on distance from camera"""
        x_rot, y_rot, z_rot = self.rotate_point_3d(x, y, z)
        
        # Distance from camera
        dist = math.sqrt(x_rot**2 + y_rot**2 + (z_rot + self.camera_distance)**2)
        
        # Fade based on distance
        fade_start = 8.0
        fade_end = 25.0
        alpha = 1.0 - (dist - fade_start) / (fade_end - fade_start)
        alpha = max(0.1, min(1.0, alpha))
        
        return alpha

    def draw_cube_wireframe(self, temp_surface, cx, cy, cz, size, color, alpha):
        """Draw a cube wireframe - much faster than filled polygons"""
        s = size / 2.0
        
        # Define 8 vertices of the cube
        vertices_3d = [
            (cx - s, cy - s, cz - s),  # 0
            (cx + s, cy - s, cz - s),  # 1
            (cx + s, cy + s, cz - s),  # 2
            (cx - s, cy + s, cz - s),  # 3
            (cx - s, cy - s, cz + s),  # 4
            (cx + s, cy - s, cz + s),  # 5
            (cx + s, cy + s, cz + s),  # 6
            (cx - s, cy + s, cz + s),  # 7
        ]
        
        # Rotate and project vertices
        vertices_2d = []
        for v in vertices_3d:
            rotated = self.rotate_point_3d(*v)
            projected = self.project_3d_to_2d(*rotated)
            if projected is None:
                return
            vertices_2d.append((int(projected[0]), int(projected[1])))
        
        # Convert color - INCREASED VISIBILITY BY 30%
        r = int(color[0] * 255)
        g = int(color[1] * 255)
        b = int(color[2] * 255)
        a = int(alpha * 255)
        line_color = (r, g, b, a)
        
        # Draw edges (12 edges total)
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # Back face
            (4, 5), (5, 6), (6, 7), (7, 4),  # Front face
            (0, 4), (1, 5), (2, 6), (3, 7),  # Connecting edges
        ]
        
        for start, end in edges:
            try:
                pygame.draw.line(temp_surface, line_color, vertices_2d[start], vertices_2d[end], 2)
            except:
                pass

    def draw(self, surface):
        """Main draw method - OPTIMIZED for smooth 60fps"""
        # Fill background
        surface.fill(self.bg_color)
        
        base_color = tuple(self.current_color)
        center = (self.grid_size - 1) * self.cube_spacing / 2.0
        cube_size = 1.8
        max_dist = center * math.sqrt(3) if center > 0 else 1.0

        # Clear reusable surfaces
        self.cube_surface.fill((0, 0, 0, 0))
        
        # Collect all cubes with their depths for z-sorting
        cubes_to_draw = []
        
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                for k in range(self.grid_size):
                    x = i * self.cube_spacing - center
                    y = j * self.cube_spacing - center
                    z = k * self.cube_spacing - center

                    # Calculate rotated position for depth sorting
                    x_rot, y_rot, z_rot = self.rotate_point_3d(x, y, z)
                    
                    # distance-based fade
                    dist = math.sqrt(x*x + y*y + z*z)
                    center_fade = 1.0 - (dist / max_dist) * 0.3
                    base_fade = center_fade

                    if self.memory_weight > 0.1:
                        pulse = (math.sin(self.pulse_phase + dist * 0.3) + 1.0) / 2.0
                        memory_fade = 0.7 + pulse * 0.3
                        total_fade = base_fade * (1.0 - self.memory_weight) + (base_fade * memory_fade) * self.memory_weight
                    else:
                        total_fade = base_fade

                    # INCREASED VISIBILITY: 0.21 * 1.3 = 0.273, and adjusted min/max bounds
                    face_alpha = total_fade * self.compute_alpha_by_distance(x, y, z) * 0.29
                    face_alpha = max(0.05, min(0.49, face_alpha))

                    cubes_to_draw.append((z_rot, x, y, z, cube_size, base_color, face_alpha))
        
        # Sort cubes by depth (draw far cubes first)
        cubes_to_draw.sort(key=lambda c: c[0], reverse=True)
        
        # Draw all cubes to ONE surface
        for z_rot, x, y, z, size, color, alpha in cubes_to_draw:
            self.draw_cube_wireframe(self.cube_surface, x, y, z, size, color, alpha)
        
        # Blit all cubes at once
        surface.blit(self.cube_surface, (0, 0))

        # Draw memory mode connecting lines
        if self.memory_weight > 0.2:
            # Clear and reuse line surface
            self.line_surface.fill((0, 0, 0, 0))
            
            # Pre-calculate weight fade once
            weight_fade = (self.memory_weight - 0.2) / 0.8
            weight_fade = max(0.0, min(1.0, weight_fade))
            
            # Convert color once
            r = int(base_color[0] * 255)
            g = int(base_color[1] * 255)
            b = int(base_color[2] * 255)
            
            for i in range(self.grid_size):
                for j in range(self.grid_size):
                    for k in range(self.grid_size):
                        x = i * self.cube_spacing - center
                        y = j * self.cube_spacing - center
                        z = k * self.cube_spacing - center

                        dist = math.sqrt(x*x + y*y + z*z)
                        pulse = (math.sin(self.pulse_phase + dist * 0.3) + 1.0) / 2.0
                        alpha = weight_fade * (0.5 + pulse * 0.3) * 0.3
                        
                        a = int(alpha * 255)
                        line_color = (r, g, b, a)

                        # Draw connections
                        if i < self.grid_size - 1:
                            nx = (i+1) * self.cube_spacing - center
                            self.draw_connection_line_fast(self.line_surface, (x, y, z), (nx, y, z), line_color)
                        if j < self.grid_size - 1:
                            ny = (j+1) * self.cube_spacing - center
                            self.draw_connection_line_fast(self.line_surface, (x, y, z), (x, ny, z), line_color)
                        if k < self.grid_size - 1:
                            nz = (k+1) * self.cube_spacing - center
                            self.draw_connection_line_fast(self.line_surface, (x, y, z), (x, y, nz), line_color)
            
            # Blit all lines at once
            surface.blit(self.line_surface, (0, 0))
    
    def draw_connection_line_fast(self, temp_surface, p1, p2, line_color):
        """Optimized line drawing - color pre-calculated"""
        rot1 = self.rotate_point_3d(*p1)
        rot2 = self.rotate_point_3d(*p2)
        
        proj1 = self.project_3d_to_2d(*rot1)
        proj2 = self.project_3d_to_2d(*rot2)
        
        if proj1 and proj2:
            try:
                pygame.draw.line(temp_surface, line_color, 
                               (int(proj1[0]), int(proj1[1])), 
                               (int(proj2[0]), int(proj2[1])), 2)
            except:
                pass


# Example usage if run directly
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    tesseract = TesseractSystem(800, 600, bg_color=(0, 0, 0))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_a:
                    tesseract.action()
                elif event.key == pygame.K_t:
                    tesseract.think()
                elif event.key == pygame.K_m:
                    tesseract.add_memory()

        tesseract.update()
        tesseract.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()