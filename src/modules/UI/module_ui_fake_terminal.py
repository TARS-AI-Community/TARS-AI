import pygame
import random
import string

class ConsoleAnimation:
    def __init__(self, width=800, height=600, base_width=800, base_height=600, font_size=8, code_snippets=None):
        self.width = max(1, width)
        self.height = max(1, height)
        self.scale_factor = min(self.width / base_width, self.height / base_height)

        adjusted_font_size = max(8, int(font_size * self.scale_factor))

        if not pygame.font.get_init():
            pygame.font.init()
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        self.bg_color = (0, 0, 0, 80)
        self.text_color = (0, 255, 0)
        self.font = pygame.font.Font("UI/pixelmix.ttf", adjusted_font_size)

        self.line_height = max(10, self.font.get_linesize())
        self.max_lines = (self.height // self.line_height) + 1

        if code_snippets is None:
            self.code_snippets = [
                "def foo(bar):", "if x == y:", "print('Hello, world!')", "return x * y",
                "while True:", "class MyClass(object):", "try:", "except Exception as e:",
                "import sys", "print('Debug info')", "elif condition:", "else:", "with open('file.txt') as f:",
                "play_wav('ashley.wave'):"
            ]
        else:
            self.code_snippets = code_snippets

        self.char_width = self.font.size("A")[0]
        self.max_chars_full = max(5, (self.width - 10) // self.char_width)

        self.lines = [self.make_line("") for _ in range(self.max_lines)]
        self.scroll_offset = 0
        self.scroll_speed = 1
        self.paused = False
        self.pause_end_time = 0
        self.next_clear_time = pygame.time.get_ticks() + random.randint(10000, 60000)

    def make_line(self, text, flash=False, flash_color=None):
        return {"text": text, "flash": flash, "flash_color": flash_color}

    def generate_line(self):
        r = random.random()
        if r < 0.1:
            text = ""
        elif r < 0.3:
            length = random.randint(max(1, min(self.max_chars_full, self.max_chars_full - 5)), self.max_chars_full)
            characters = string.ascii_letters + string.digits + " +-*/=<>[](){};:'\""
            text = ''.join(random.choice(characters) for _ in range(length))
        else:
            if random.random() < 0.5:
                text = random.choice(self.code_snippets)
            else:
                length = random.randint(10, 30)
                characters = string.ascii_letters + string.digits + " +-*/=<>[](){};:'\""
                text = ''.join(random.choice(characters) for _ in range(length))

        if text and random.random() < 0.05:
            flash_color = random.choice([(0, 0, 255), (255, 255, 255), (255, 0, 0)])
            return self.make_line(text, flash=True, flash_color=flash_color)
        else:
            return self.make_line(text)

    def update(self):
        current_time = pygame.time.get_ticks()

        if current_time >= self.next_clear_time:
            self.lines = [self.make_line("") for _ in range(self.max_lines)]
            self.scroll_offset = 0
            self.next_clear_time = current_time + random.randint(10000, 60000)

        if self.paused:
            if current_time >= self.pause_end_time:
                self.paused = False
        else:
            self.scroll_offset += self.scroll_speed

        if self.scroll_offset >= self.line_height:
            self.scroll_offset -= self.line_height
            self.lines.pop(0)
            self.lines.append(self.generate_line())

            if random.random() < 0.5:
                self.scroll_speed = random.randint(1, 5)
            self.scroll_speed = max(1, self.scroll_speed)

            if random.random() < 0.1:
                pause_duration = max(0.5, random.uniform(0.5, 5.0))
                self.pause_end_time = current_time + int(pause_duration * 1000)
                self.paused = True

        self.surface.fill(self.bg_color)
        for i, line in enumerate(self.lines):
            y = i * self.line_height - self.scroll_offset
            if line["flash"]:
                if (current_time // 500) % 2 == 0:
                    color = line["flash_color"]
                else:
                    continue
            else:
                color = self.text_color
            text_surface = self.font.render(line["text"], True, color)
            self.surface.blit(text_surface, (5, y))
        return self.surface
