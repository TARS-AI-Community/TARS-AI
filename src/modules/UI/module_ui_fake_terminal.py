import pygame
import random
import string

class ConsoleAnimation:
    def __init__(self, width=300, height=180, font_size=10, code_snippets=None):
        self.width = width
        self.height = height
        if not pygame.font.get_init():
            pygame.font.init()
        self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.bg_color = (0, 0, 0, 80)         # Black background
        self.text_color = (0, 255, 0)     # Green text (typical terminal look)
        self.font = pygame.font.Font("UI/pixelmix.ttf", font_size)
        self.line_height = self.font.get_linesize()
        self.max_lines = (self.height // self.line_height) + 1

        # Use provided code snippets or defaults.
        if code_snippets is None:
            self.code_snippets = [
                "def foo(bar):",
                "    for i in range(10):",
                "if x == y:",
                "    print('Hello, world!')",
                "return x * y",
                "while True:",
                "class MyClass(object):",
                "    pass",
                "try:",
                "except Exception as e:",
                "import sys",
                "print('Debug info')",
                "elif condition:",
                "else:",
                "with open('file.txt') as f:",
                "play_wav('ashley.wave'):"
            ]
        else:
            self.code_snippets = code_snippets

        # Estimate the maximum number of characters that nearly fill the width.
        self.char_width = self.font.size("A")[0]
        self.max_chars_full = (self.width - 10) // self.char_width  # leave some horizontal padding

        # Initialize the lines (each line is a dict holding text and flash info)
        self.lines = [self.make_line("") for _ in range(self.max_lines)]
        self.scroll_offset = 0
        self.scroll_speed = 1
        self.paused = False
        self.pause_end_time = 0
        self.next_clear_time = pygame.time.get_ticks() + random.randint(10000, 60000)

    def make_line(self, text, flash=False, flash_color=None):
        """Helper to create a line data structure."""
        return {"text": text, "flash": flash, "flash_color": flash_color}

    def generate_line(self):
        """
        Generates a code-like line:
          - ~10% chance to be an empty line.
          - ~20% chance to be a long line filling nearly the width.
          - Otherwise, either a typical code snippet or a short random line.
          - ~5% chance for the line to flash (if not empty).
        """
        r = random.random()
        if r < 0.1:
            text = ""
        elif r < 0.3:
            length = random.randint(self.max_chars_full - 5, self.max_chars_full)
            characters = string.ascii_letters + string.digits + " +-*/=<>[](){};:'\""
            text = ''.join(random.choice(characters) for _ in range(length))
        else:
            if random.random() < 0.5:
                text = random.choice(self.code_snippets)
            else:
                length = random.randint(10, 30)
                characters = string.ascii_letters + string.digits + " +-*/=<>[](){};:'\""
                text = ''.join(random.choice(characters) for _ in range(length))
        # ~5% chance to make this line flash (if it's not empty)
        if text and random.random() < 0.05:
            flash_color = random.choice([(0, 0, 255), (255, 255, 255), (255, 0, 0)])
            return self.make_line(text, flash=True, flash_color=flash_color)
        else:
            return self.make_line(text)

    def update(self):
        """
        Update the console animation and return the updated surface.
        Call this in your main loop to get the current state of the animation.
        """
        current_time = pygame.time.get_ticks()

        # Randomly clear the console every 10 to 60 seconds.
        if current_time >= self.next_clear_time:
            self.lines = [self.make_line("") for _ in range(self.max_lines)]
            self.scroll_offset = 0
            self.next_clear_time = current_time + random.randint(10000, 60000)

        # Handle pause (the animation may pause for a random period).
        if self.paused:
            if current_time >= self.pause_end_time:
                self.paused = False
        else:
            self.scroll_offset += self.scroll_speed

        # When a full line has scrolled, update the lines.
        if self.scroll_offset >= self.line_height:
            self.scroll_offset -= self.line_height
            self.lines.pop(0)
            self.lines.append(self.generate_line())

            # Occasionally adjust the scrolling speed.
            if random.random() < 0.5:
                self.scroll_speed = random.randint(1, 5)

            # Occasionally trigger a pause.
            if random.random() < 0.1:
                pause_duration = random.uniform(0.5, 5.0)  # seconds
                self.pause_end_time = current_time + int(pause_duration * 1000)
                self.paused = True

        # Draw the console onto the surface.
        self.surface.fill(self.bg_color)
        for i, line in enumerate(self.lines):
            y = i * self.line_height - self.scroll_offset
            # For flashing lines, alternate drawing based on the current time.
            if line["flash"]:
                if (current_time // 500) % 2 == 0:
                    color = line["flash_color"]
                else:
                    continue  # Skip drawing during off phase.
            else:
                color = self.text_color
            text_surface = self.font.render(line["text"], True, color)
            self.surface.blit(text_surface, (5, y))
        return self.surface
