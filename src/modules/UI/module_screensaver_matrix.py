"""
# atomikspace (discord)
# olivierdion1@hotmail.com
"""

import pygame
import random

class MatrixAnimation:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height
        self.font = pygame.font.Font("UI/pixelmix.ttf", 16)
        self.char_width = 10
        self.char_height = 16
        self.columns = width // self.char_width
        self.rows = height // self.char_height
        
        self.chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789(){}[]<>=+-*/%:;.,_#@!&|"
        
        self.code_words = [
            "def", "class", "if", "for", "while", "return", "import", "from",
            "try", "except", "lambda", "yield", "async", "await", "self",
            "True", "False", "None", "print", "range", "len", "str", "int",
            "list", "dict", "set", "open", "read", "write", "data", "func",
            "var", "val", "temp", "count", "index", "result", "status",
            "x", "y", "z", "i", "j", "k", "n", "a", "b", "c"
        ]
        
        self.streams = []
        for col in range(self.columns):
            chars = []
            i = 0
            while i < self.rows + 10:
                if random.random() < 0.3:
                    word = random.choice(self.code_words)
                    for char in word:
                        chars.append(char)
                        i += 1
                    if i < self.rows + 10 and random.random() < 0.5:
                        chars.append(random.choice("(){}[]<>=+-*:;.,"))
                        i += 1
                else:
                    chars.append(random.choice(self.chars))
                    i += 1
            
            self.streams.append({
                'x': col * self.char_width,
                'y': random.randint(-self.height, 0),
                'speed': random.uniform(0.5, 2.5),
                'length': random.randint(10, 30),
                'chars': chars,
                'char_change_counter': 0
            })

    def reset(self):
        self.streams = []
        for col in range(self.columns):
            chars = []
            i = 0
            while i < self.rows + 10:
                if random.random() < 0.3:
                    word = random.choice(self.code_words)
                    for char in word:
                        chars.append(char)
                        i += 1
                    if i < self.rows + 10 and random.random() < 0.5:
                        chars.append(random.choice("(){}[]<>=+-*:;.,"))
                        i += 1
                else:
                    chars.append(random.choice(self.chars))
                    i += 1
            
            self.streams.append({
                'x': col * self.char_width,
                'y': random.randint(-self.height, 0),
                'speed': random.uniform(0.5, 2.5),
                'length': random.randint(10, 30),
                'chars': chars,
                'char_change_counter': 0
            })

    def update(self):
        for stream in self.streams:
            stream['y'] += stream['speed']
            
            if stream['y'] > self.height + (stream['length'] * self.char_height):
                stream['y'] = random.randint(-self.height // 2, -self.char_height)
                stream['speed'] = random.uniform(0.5, 2.5)
                stream['length'] = random.randint(10, 30)
            
            stream['char_change_counter'] += 1
            if stream['char_change_counter'] >= 5:
                stream['char_change_counter'] = 0
                for i in range(len(stream['chars'])):
                    if random.random() < 0.02:
                        if random.random() < 0.3:
                            word = random.choice(self.code_words)
                            if i + len(word) < len(stream['chars']):
                                for j, char in enumerate(word):
                                    stream['chars'][i + j] = char
                        else:
                            stream['chars'][i] = random.choice(self.chars)

    def render(self):
        self.screen.fill((0, 0, 0))
        
        for stream in self.streams:
            head_y = int(stream['y'])
            
            for i in range(stream['length']):
                char_y = head_y - (i * self.char_height)
                
                if char_y < -self.char_height or char_y > self.height:
                    continue
                
                char_index = i % len(stream['chars'])
                char = stream['chars'][char_index]
                
                if i == 0:
                    color = (180, 220, 255)
                    brightness = 1.0
                elif i < 3:
                    brightness = 0.9 - (i * 0.1)
                    color = (int(140 * brightness), int(200 * brightness), int(255 * brightness))
                else:
                    fade_factor = 1.0 - (i / stream['length'])
                    fade_factor = max(0.1, fade_factor)
                    color = (int(60 * fade_factor), int(120 * fade_factor), int(180 * fade_factor))
                
                text_surface = self.font.render(char, True, color)
                self.screen.blit(text_surface, (stream['x'], char_y))