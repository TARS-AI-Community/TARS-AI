"""
Module: Endurance Screensaver
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
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import os
from collections import defaultdict
from PIL import Image

try:
    from UI.module_screensaver_overlay import TimeOverlay
except ImportError:
    TimeOverlay = None


class Material:
    def __init__(self, name):
        self.name = name
        self.diffuse = [0.8, 0.8, 0.8]
        self.ambient = [1.0, 1.0, 1.0]
        self.specular = [0.5, 0.5, 0.5]
        self.shininess = 50.0
        self.texture_path = None
        self.texture_id = None


class OBJLoader:
    def __init__(self):
        self.vertices = []
        self.tex_coords = []
        self.normals = []
        self.faces = {}
        self.materials = {}
        self.center = [0, 0, 0]
        self.scale = 1.0
        self.smooth_normals = {}
    
    def load_mtl(self, filepath, model_dir):
        if not os.path.exists(filepath):
            return
        current_mat = None
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == 'newmtl':
                    name = parts[1] if len(parts) > 1 else 'default'
                    current_mat = Material(name)
                    self.materials[name] = current_mat
                elif current_mat:
                    if parts[0] == 'Kd':
                        current_mat.diffuse = [float(x) for x in parts[1:4]]
                    elif parts[0] == 'Ka':
                        current_mat.ambient = [float(x) for x in parts[1:4]]
                    elif parts[0] == 'Ks':
                        current_mat.specular = [float(x) for x in parts[1:4]]
                    elif parts[0] == 'Ns':
                        current_mat.shininess = min(float(parts[1]), 128.0)
                    elif parts[0] == 'map_Kd':
                        current_mat.texture_path = os.path.join(model_dir, parts[1])
    
    def load(self, filepath):
        self.vertices = []
        self.tex_coords = []
        self.normals = []
        self.faces = {}
        model_dir = os.path.dirname(filepath)
        current_material = 'default'
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == 'mtllib':
                    mtl_path = os.path.join(model_dir, parts[1])
                    self.load_mtl(mtl_path, model_dir)
                elif parts[0] == 'usemtl':
                    current_material = parts[1] if len(parts) > 1 else 'default'
                    if current_material not in self.faces:
                        self.faces[current_material] = []
                elif parts[0] == 'v':
                    self.vertices.append([float(x) for x in parts[1:4]])
                elif parts[0] == 'vt':
                    self.tex_coords.append([float(x) for x in parts[1:3]])
                elif parts[0] == 'vn':
                    self.normals.append([float(x) for x in parts[1:4]])
                elif parts[0] == 'f':
                    face = []
                    for vertex in parts[1:]:
                        indices = vertex.split('/')
                        v_idx = int(indices[0]) - 1
                        t_idx = int(indices[1]) - 1 if len(indices) > 1 and indices[1] else -1
                        n_idx = int(indices[2]) - 1 if len(indices) > 2 and indices[2] else -1
                        face.append((v_idx, t_idx, n_idx))
                    if current_material not in self.faces:
                        self.faces[current_material] = []
                    self.faces[current_material].append(face)
        
        self._calculate_bounds()
        return self
    
    def _calculate_bounds(self):
        if not self.vertices:
            return
        min_v = [float('inf')] * 3
        max_v = [float('-inf')] * 3
        for v in self.vertices:
            for i in range(3):
                min_v[i] = min(min_v[i], v[i])
                max_v[i] = max(max_v[i], v[i])
        self.center = [(min_v[i] + max_v[i]) / 2 for i in range(3)]
        size = max(max_v[i] - min_v[i] for i in range(3))
        self.scale = 2.0 / size if size > 0 else 1.0
    
    def _compute_face_normal(self, face):
        if len(face) < 3:
            return [0, 1, 0]
        v0 = self.vertices[face[0][0]]
        v1 = self.vertices[face[1][0]]
        v2 = self.vertices[face[2][0]]
        u = [v1[i] - v0[i] for i in range(3)]
        v = [v2[i] - v0[i] for i in range(3)]
        normal = [u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0]]
        length = math.sqrt(sum(n*n for n in normal))
        if length > 0:
            normal = [n/length for n in normal]
        return normal
    
    def _get_vertex(self, v_idx):
        v = self.vertices[v_idx]
        return [(v[i] - self.center[i]) * self.scale for i in range(3)]
    
    def compute_smooth_normals(self):
        vertex_normals = defaultdict(lambda: [0.0, 0.0, 0.0])
        for mat_name, faces in self.faces.items():
            for face in faces:
                face_normal = self._compute_face_normal(face)
                for v_idx, t_idx, n_idx in face:
                    for i in range(3):
                        vertex_normals[v_idx][i] += face_normal[i]
        self.smooth_normals = {}
        for v_idx, normal in vertex_normals.items():
            length = math.sqrt(sum(n*n for n in normal))
            if length > 0:
                self.smooth_normals[v_idx] = [n/length for n in normal]
            else:
                self.smooth_normals[v_idx] = [0, 1, 0]
    
    def load_textures(self):
        for mat in self.materials.values():
            if mat.texture_path and os.path.exists(mat.texture_path):
                mat.texture_id = self._load_texture(mat.texture_path)
    
    def _load_texture(self, filepath):
        img = Image.open(filepath).transpose(Image.FLIP_TOP_BOTTOM)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width, img.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img.tobytes())
        glGenerateMipmap(GL_TEXTURE_2D)
        return texture_id
    
    def build_display_lists(self):
        display_lists = {}
        has_texcoords = len(self.tex_coords) > 0
        use_smooth = self.smooth_normals
        
        for mat_name, faces in self.faces.items():
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            for face in faces:
                if len(face) == 3:
                    glBegin(GL_TRIANGLES)
                elif len(face) == 4:
                    glBegin(GL_QUADS)
                else:
                    glBegin(GL_POLYGON)
                for v_idx, t_idx, n_idx in face:
                    if use_smooth and v_idx in self.smooth_normals:
                        glNormal3fv(self.smooth_normals[v_idx])
                    elif len(self.normals) > 0 and 0 <= n_idx < len(self.normals):
                        glNormal3fv(self.normals[n_idx])
                    if has_texcoords and 0 <= t_idx < len(self.tex_coords):
                        glTexCoord2fv(self.tex_coords[t_idx])
                    glVertex3fv(self._get_vertex(v_idx))
                glEnd()
            glEndList()
            display_lists[mat_name] = dl
        return display_lists


def create_sky_sphere(radius=50, segments=32):
    dl = glGenLists(1)
    glNewList(dl, GL_COMPILE)
    for i in range(segments):
        lat0 = math.pi * (-0.5 + float(i) / segments)
        lat1 = math.pi * (-0.5 + float(i + 1) / segments)
        glBegin(GL_QUAD_STRIP)
        for j in range(segments + 1):
            lng = 2 * math.pi * float(j) / segments
            x0 = math.cos(lat0) * math.cos(lng)
            y0 = math.sin(lat0)
            z0 = math.cos(lat0) * math.sin(lng)
            x1 = math.cos(lat1) * math.cos(lng)
            y1 = math.sin(lat1)
            z1 = math.cos(lat1) * math.sin(lng)
            glNormal3f(-x0, -y0, -z0)
            glTexCoord2f(float(j) / segments, float(i) / segments)
            glVertex3f(x0 * radius, y0 * radius, z0 * radius)
            glNormal3f(-x1, -y1, -z1)
            glTexCoord2f(float(j) / segments, float(i + 1) / segments)
            glVertex3f(x1 * radius, y1 * radius, z1 * radius)
        glEnd()
    glEndList()
    return dl


class EnduranceAnimation:
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
        self.time_overlay = None
        if show_time and TimeOverlay:
            self.time_overlay = TimeOverlay(width, height, rotation)
        
        self.loader = None
        self.display_lists = {}
        self.sky_sphere = None
        self.sky_texture = None
        
        self.model_spin_speed = 8.0
        self.camera_orbit_speed = 3.0
        self.model_rotation = 0.0
        self.camera_angle = 0.0
        self.camera_height_phase = 0.0
        
        self.zoom_base = 2.0
        self.zoom_phase = 0.0
        self.zoom_speed = 0.15
        self.zoom_amplitude = 0.4
        self.zoom_offset = 0.0
        
        self.load_stage = 0
    
    def initialize(self):
        if self.initialized:
            return
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_NORMALIZE)
        glShadeModel(GL_SMOOTH)
        
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if self.is_portrait:
            glRotatef(90, 0, 0, 1)
            gluPerspective(45, self.height / self.width, 0.1, 100.0)
        else:
            gluPerspective(45, self.width / self.height, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT0, GL_POSITION, [5.0, 4.0, 5.0, 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.25, 0.25, 0.28, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.9, 0.88, 0.85, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.6, 0.6, 0.6, 1.0])
        glLightfv(GL_LIGHT1, GL_POSITION, [-4.0, -2.0, 3.0, 0.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT, [0.1, 0.1, 0.12, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.4, 0.42, 0.5, 1.0])
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        self.initialized = True
        self.load_stage = 0
    
    def _load_stars(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        starfield_path = os.path.join(script_dir, "models", "starfield.png")
        
        if os.path.exists(starfield_path):
            img = Image.open(starfield_path).transpose(Image.FLIP_TOP_BOTTOM).convert('RGBA')
            self.sky_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.sky_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width, img.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img.tobytes())
        
        self.sky_sphere = create_sky_sphere(radius=40, segments=32)
    
    def _load_model(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, "models", "endurance.obj")
        
        if os.path.exists(model_path):
            self.loader = OBJLoader()
            self.loader.load(model_path)
            self.loader.compute_smooth_normals()
            self.loader.load_textures()
            self.display_lists = self.loader.build_display_lists()
    
    def update(self, delta_time=None):
        if delta_time is None:
            try:
                delta_time = self.clock.get_time() / 1000.0
            except:
                delta_time = 0.033
        
        if self.load_stage == 3:
            self.time += delta_time
            self.model_rotation += self.model_spin_speed * delta_time
            self.camera_angle += self.camera_orbit_speed * delta_time
            self.camera_height_phase += delta_time * 0.2
            self.zoom_phase += delta_time * self.zoom_speed
            
            if self.zoom_phase > math.pi * 2:
                self.zoom_phase -= math.pi * 2
                self.zoom_offset = (hash(int(self.time * 1000)) % 100) / 250.0 - 0.2
    
    def render(self):
        if not self.initialized:
            self.initialize()
        
        if self.load_stage == 0:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            pygame.display.flip()
            self._load_stars()
            self.load_stage = 1
            return
        
        if self.load_stage == 1:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
            gluLookAt(2, 0.3, 2, 0, 0, 0, 0, 1, 0)
            
            if self.sky_sphere and self.sky_texture:
                glDisable(GL_LIGHTING)
                glDepthMask(GL_FALSE)
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, self.sky_texture)
                glColor3f(1.0, 1.0, 1.0)
                glCallList(self.sky_sphere)
                glDepthMask(GL_TRUE)
            
            pygame.display.flip()
            self._load_model()
            self.load_stage = 3
            return
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        cam_dist = self.zoom_base + math.sin(self.zoom_phase) * self.zoom_amplitude + self.zoom_offset
        cam_height = 0.3 + math.sin(self.camera_height_phase) * 0.2
        cam_x = math.cos(math.radians(self.camera_angle)) * cam_dist
        cam_z = math.sin(math.radians(self.camera_angle)) * cam_dist
        
        gluLookAt(cam_x, cam_height, cam_z, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        
        if self.sky_sphere and self.sky_texture:
            glDisable(GL_LIGHTING)
            glDepthMask(GL_FALSE)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.sky_texture)
            glColor3f(1.0, 1.0, 1.0)
            glCallList(self.sky_sphere)
            glDepthMask(GL_TRUE)
        
        glEnable(GL_LIGHTING)
        if self.display_lists and self.loader:
            glPushMatrix()
            glRotatef(self.model_rotation, 0, 1, 0)
            
            for mat_name, dl in self.display_lists.items():
                mat = self.loader.materials.get(mat_name)
                if mat:
                    if mat.texture_id:
                        glEnable(GL_TEXTURE_2D)
                        glBindTexture(GL_TEXTURE_2D, mat.texture_id)
                        glColor3f(1.0, 1.0, 1.0)
                    else:
                        glDisable(GL_TEXTURE_2D)
                        glColor3fv(mat.diffuse)
                    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, mat.specular + [1.0])
                    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, mat.shininess)
                else:
                    glDisable(GL_TEXTURE_2D)
                    glColor3f(0.8, 0.8, 0.8)
                glCallList(dl)
            
            glPopMatrix()
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render_gl()
        
        pygame.display.flip()
        
        try:
            self.clock.tick(30)
        except:
            pass
    
    def reset(self):
        self.time = 0.0
        self.model_rotation = 0.0
        self.camera_angle = 0.0
        self.camera_height_phase = 0.0
        self.zoom_phase = 0.0
        self.zoom_offset = 0.0
        self.load_stage = 0
    
    def cleanup(self):
        self.initialized = False
        self.load_stage = 0
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 1.0)