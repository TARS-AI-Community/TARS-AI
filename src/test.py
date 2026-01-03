import pygame
import random
import math
import sys
import subprocess
import os

# Initialize Pygame
pygame.init()

# Screen settings - create fullscreen display
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
display_width, display_height = screen.get_size()
pygame.display.set_caption("Happy New Year 2026!")
clock = pygame.time.Clock()

# Animation canvas (will be rotated 90 degrees clockwise)
# Swap width/height since we're rotating
WIDTH, HEIGHT = 600, 1024
canvas = pygame.Surface((WIDTH, HEIGHT))

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)

# Firework colors
COLORS = [
    (255, 50, 50),    # Red
    (50, 255, 50),    # Green
    (50, 50, 255),    # Blue
    (255, 255, 50),   # Yellow
    (255, 50, 255),   # Magenta
    (50, 255, 255),   # Cyan
    (255, 150, 50),   # Orange
    (150, 50, 255),   # Purple
    (255, 215, 0),    # Gold
]

class Particle:
    def __init__(self, x, y, color, velocity, gravity=0.15):
        self.x = x
        self.y = y
        self.color = color
        self.vx, self.vy = velocity
        self.gravity = gravity
        self.lifetime = 255
        self.fade_rate = random.uniform(2, 4)
        self.size = random.randint(2, 4)
        
    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= self.fade_rate
        
    def draw(self, surface):
        if self.lifetime > 0:
            alpha = max(0, int(self.lifetime))
            color_with_alpha = tuple(min(255, int(c * alpha / 255)) for c in self.color)
            pygame.draw.circle(surface, color_with_alpha, (int(self.x), int(self.y)), self.size)
            
    def is_alive(self):
        return self.lifetime > 0 and self.y < HEIGHT

class Firework:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.color = random.choice(COLORS)
        self.secondary_color = random.choice(COLORS)
        self.exploded = False
        self.particles = []
        
        # Different firework types and heights
        self.type = random.choice(['burst', 'ring', 'willow', 'sparkler', 'double', 'crackle'])
        
        # Vary the height - some go much higher
        height_category = random.random()
        if height_category < 0.3:  # 30% low
            self.vy = random.uniform(-10, -12)
            self.target_y = random.randint(200, 350)
        elif height_category < 0.6:  # 30% medium
            self.vy = random.uniform(-13, -16)
            self.target_y = random.randint(120, 250)
        else:  # 40% high
            self.vy = random.uniform(-17, -22)
            self.target_y = random.randint(50, 150)
        
    def explode(self):
        if self.type == 'burst':
            # Standard burst
            num_particles = random.randint(60, 120)
            for _ in range(num_particles):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(2, 9)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                self.particles.append(Particle(self.x, self.y, self.color, velocity))
                
        elif self.type == 'ring':
            # Ring explosion
            num_particles = 50
            for i in range(num_particles):
                angle = (i / num_particles) * 2 * math.pi
                speed = random.uniform(5, 7)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                self.particles.append(Particle(self.x, self.y, self.color, velocity, gravity=0.05))
                
        elif self.type == 'willow':
            # Willow effect - particles fall down
            num_particles = random.randint(80, 140)
            for _ in range(num_particles):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(1, 6)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed - 2)
                self.particles.append(Particle(self.x, self.y, self.color, velocity, gravity=0.25))
                
        elif self.type == 'sparkler':
            # Bright, fast sparkles
            num_particles = random.randint(100, 150)
            for _ in range(num_particles):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(3, 12)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                particle = Particle(self.x, self.y, self.color, velocity, gravity=0.1)
                particle.fade_rate = random.uniform(1, 2.5)
                self.particles.append(particle)
                
        elif self.type == 'double':
            # Double color burst
            num_particles = random.randint(50, 80)
            for _ in range(num_particles):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(2, 8)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                color = self.color if random.random() < 0.5 else self.secondary_color
                self.particles.append(Particle(self.x, self.y, color, velocity))
                
        elif self.type == 'crackle':
            # Fast sparkling crackle effect - like strobing sparklers
            num_particles = random.randint(150, 250)
            for _ in range(num_particles):
                angle = random.uniform(0, 2 * math.pi)
                # Very fast initial speed
                speed = random.uniform(4, 15)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                
                particle = Particle(self.x, self.y, self.color, velocity, gravity=0.15)
                # Fast fade for quick sparkle effect
                particle.fade_rate = random.uniform(3, 6)
                # Small bright particles
                particle.size = random.randint(1, 3)
                self.particles.append(particle)
            
            # Add some bright white flashes
            for _ in range(50):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(6, 18)
                velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
                
                particle = Particle(self.x, self.y, WHITE, velocity, gravity=0.2)
                particle.fade_rate = random.uniform(4, 8)
                particle.size = 2
                self.particles.append(particle)
        
        self.exploded = True
        
    def update(self):
        if not self.exploded:
            self.y += self.vy
            self.vy += 0.3
            if self.y <= self.target_y or self.vy > 0:
                self.explode()
        else:
            self.particles = [p for p in self.particles if p.is_alive()]
            for particle in self.particles:
                particle.update()
                
    def draw(self, surface):
        if not self.exploded:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), 3)
            # Trail
            for i in range(5):
                trail_y = self.y + i * 3
                if trail_y < HEIGHT:
                    alpha = 255 - i * 50
                    pygame.draw.circle(surface, self.color, (int(self.x), int(trail_y)), 2)
        else:
            for particle in self.particles:
                particle.draw(surface)
                
    def is_alive(self):
        return not self.exploded or len(self.particles) > 0

class Star:
    def __init__(self):
        self.x = random.randint(0, WIDTH)
        self.y = random.randint(0, HEIGHT)
        self.brightness = random.randint(100, 255)
        self.twinkle_speed = random.uniform(0.02, 0.05)
        self.phase = random.uniform(0, 2 * math.pi)
        
    def update(self):
        self.phase += self.twinkle_speed
        
    def draw(self, surface):
        brightness = int(self.brightness * (0.5 + 0.5 * math.sin(self.phase)))
        color = (brightness, brightness, brightness)
        pygame.draw.circle(surface, color, (self.x, self.y), 1)

# Create stars
stars = [Star() for _ in range(100)]

# Fireworks list
fireworks = []
firework_timer = 0

# Text setup - digital display style
# Try to use a digital-looking font, fallback to courier/monospace
try:
    font_large = pygame.font.SysFont('couriernew', 110, bold=True)
    font_medium = pygame.font.SysFont('couriernew', 48, bold=True)
except:
    font_large = pygame.font.SysFont('courier', 110, bold=True)
    font_medium = pygame.font.SysFont('courier', 48, bold=True)

def draw_digital_text(surface, text, x, y, color, size=80, outline_color=None):
    """Draw text in a digital/pixelated style"""
    char_width = size // 2
    char_height = size
    spacing = size // 8
    
    current_x = x - (len(text) * (char_width + spacing)) // 2
    
    for char in text.upper():
        rects = []
        
        # Define segments for each character (7-segment style + extras)
        if char == '2':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height//2),  # right top
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
                pygame.Rect(current_x, y + char_height//2, size//10, char_height//2),  # left bottom
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == '0':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == '6':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
                pygame.Rect(current_x + char_width - size//10, y + char_height//2, size//10, char_height//2),  # right bottom
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == 'T':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x + char_width//2 - size//20, y, size//10, char_height),  # middle vertical
            ]
        elif char == 'A':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
            ]
        elif char == 'R':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height//2),  # right top
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
                pygame.Rect(current_x + char_width//2, y + char_height//2, size//10, char_height//2),  # diagonal
            ]
        elif char == 'S':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height//2),  # left top
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
                pygame.Rect(current_x + char_width - size//10, y + char_height//2, size//10, char_height//2),  # right bottom
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == 'W':
            rects = [
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width//3, y + char_height//2, size//10, char_height//2),  # middle left
                pygame.Rect(current_x + 2*char_width//3, y + char_height//2, size//10, char_height//2),  # middle right
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
            ]
        elif char == 'I':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x + char_width//2 - size//20, y, size//10, char_height),  # middle
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == 'H':
            rects = [
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
            ]
        elif char == 'E':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == 'Y':
            rects = [
                pygame.Rect(current_x, y, size//10, char_height//2),  # left top
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height//2),  # right top
                pygame.Rect(current_x + char_width//2 - size//20, y + char_height//2, size//10, char_height//2),  # middle bottom
            ]
        elif char == 'U':
            rects = [
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
                pygame.Rect(current_x, y + char_height - size//10, char_width, size//10),  # bottom
            ]
        elif char == 'P':
            rects = [
                pygame.Rect(current_x, y, char_width, size//10),  # top
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height//2),  # right top
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle
            ]
        elif char == 'N':
            rects = [
                pygame.Rect(current_x, y, size//10, char_height),  # left
                pygame.Rect(current_x + char_width - size//10, y, size//10, char_height),  # right
                pygame.Rect(current_x, y, char_width, size//10),  # diagonal (simplified)
            ]
        elif char == '-':
            rects = [
                pygame.Rect(current_x, y + char_height//2 - size//20, char_width, size//10),  # middle horizontal
            ]
        elif char == ' ':
            current_x += char_width + spacing
            continue
        
        # Draw outline if specified
        if outline_color and rects:
            for rect in rects:
                outline_rect = rect.inflate(size//15, size//15)
                pygame.draw.rect(surface, outline_color, outline_rect)
        
        # Draw main character
        for rect in rects:
            pygame.draw.rect(surface, color, rect)
        
        current_x += char_width + spacing

def draw_text_with_glow(surface, text, font, x, y, color, glow_color):
    # Draw glow
    for offset in range(3, 0, -1):
        glow_alpha = 100 - offset * 20
        glow_surf = font.render(text, True, glow_color)
        glow_surf.set_alpha(glow_alpha)
        rect = glow_surf.get_rect(center=(x, y))
        for dx in [-offset, 0, offset]:
            for dy in [-offset, 0, offset]:
                surface.blit(glow_surf, (rect.x + dx, rect.y + dy))
    
    # Draw main text
    text_surf = font.render(text, True, color)
    rect = text_surf.get_rect(center=(x, y))
    surface.blit(text_surf, rect)

# Animation time
start_time = pygame.time.get_ticks()
app_launched = False  # Track if we've launched the servo tester app

# Main loop
running = True
while running:
    dt = clock.tick(60) / 1000.0
    current_time = (pygame.time.get_ticks() - start_time) / 1000.0
    
    # Launch app-servotester.py after 5 seconds
    if not app_launched and current_time >= 5.0:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        servo_app_path = os.path.join(script_dir, "app-servotester.py")
        if os.path.exists(servo_app_path):
            subprocess.Popen([sys.executable, servo_app_path])
            app_launched = True
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
    
    # Clear canvas
    canvas.fill(BLACK)
    
    # Draw and update stars
    for star in stars:
        star.update()
        star.draw(canvas)
    
    # Spawn fireworks
    firework_timer += dt
    if firework_timer > random.uniform(0.3, 0.8):
        x = random.randint(100, WIDTH - 100)
        fireworks.append(Firework(x, HEIGHT))
        firework_timer = 0
    
    # Update and draw fireworks
    fireworks = [fw for fw in fireworks if fw.is_alive()]
    for firework in fireworks:
        firework.update()
        firework.draw(canvas)
    
    # Draw "2026" text with digital display style
    pulse = 1 + 0.1 * math.sin(current_time * 2)
    gold_brightness = int(255 * (0.8 + 0.2 * math.sin(current_time * 3)))
    gold_color = (gold_brightness, int(gold_brightness * 0.84), 0)
    
    # Draw postcard-style message with digital font and outline
    text_color = (100, 200, 255)  # Light blue/cyan
    outline_color = (20, 40, 80)  # Dark blue outline
    
    draw_digital_text(canvas, "HAPPY NEW YEAR", WIDTH // 2, HEIGHT // 2 - 60, 
                     text_color, size=55, outline_color=outline_color)
    draw_digital_text(canvas, "2026", WIDTH // 2, HEIGHT // 2 + 10, 
                     gold_color, size=90)
    draw_digital_text(canvas, "- TARS", WIDTH // 2, HEIGHT // 2 + 130, 
                     text_color, size=40, outline_color=outline_color)
    
    # Rotate canvas 90 degrees clockwise and scale to fit screen
    rotated_canvas = pygame.transform.rotate(canvas, -90)
    
    # Scale to fit screen while maintaining aspect ratio
    rotated_rect = rotated_canvas.get_rect()
    scale_factor = min(display_width / rotated_rect.width, display_height / rotated_rect.height)
    new_size = (int(rotated_rect.width * scale_factor), int(rotated_rect.height * scale_factor))
    scaled_canvas = pygame.transform.scale(rotated_canvas, new_size)
    
    # Center on screen
    screen.fill(BLACK)
    scaled_rect = scaled_canvas.get_rect(center=(display_width // 2, display_height // 2))
    screen.blit(scaled_canvas, scaled_rect)
    
    # Update display
    pygame.display.flip()

pygame.quit()
sys.exit()




    """  step_forward()

    move_legs(50, 50, 50, 50, 0.8)
    sequence = [
        (50, 70, 50, 50),
        (50, 70, 30, 50),
        (70, 50, 50, 50),
        (70, 50, 50, 30),
    ]
    for _ in range(2):
        for a, b, c, d in sequence:
            move_legs(a, b, c, d, 0.7)
    move_legs(70, 70, 50, 50, 0.8)
    move_legs(50, 50, 50, 50, 0.8) 

    sequence = [
        (50, 60, 50, 50),
        (50, 60, 50, 30),
        (60, 50, 50, 50),
        (60, 50, 30, 50),
    ]
    for _ in range(2):
        for a, b, c, d in sequence:
            move_legs(a, b, c, d, 0.7)
    move_legs(50, 50, 50, 50, 0.7)

    time.sleep(1)
    move_legs(50, 50, 50, 50, 0.8)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(50, 50, 50, 50, 0.9)


    move_legs(50, 50, 50, 50, 0.8)
    move_legs(90, 50, 50, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 50, 100, 50, 0.9)
    move_legs(90, 50, 70, 50, 0.9)
    move_legs(90, 50, 100, 50, 0.9)
    move_legs(90, 50, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(50, 50, 50, 50, 0.8)

    step_backward()




 """