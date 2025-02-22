import pygame

# Define colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (76, 194, 230)

class Button:
    def __init__(self, real_x, real_y, width, height, rotation, text, font, action=None):
        self.real_x = real_x
        self.real_y = real_y
        self.width = width
        self.height = height
        self.text = text
        self.action = action
        self.font = font
        self.rotation = rotation
    
    def draw_button(self, font):
        button_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(button_surface, BLUE, (0, 0, self.width, self.height))
        text_surface = self.font.render(self.text, True, BLACK)
        text_rect = text_surface.get_rect(center=(self.width / 2, self.height / 2))
        button_surface.blit(text_surface, text_rect)
        return button_surface
    
    def is_clicked(self, pos):
        mouse_x, mouse_y = pos
        if self.rotation == 0 or self.rotation == 180:
            if (self.real_x <= mouse_x <= self.real_x + self.width and 
                self.real_y <= mouse_y <= self.real_y + self.height):
                return self.action
        elif self.rotation == 90 or self.rotation == 270:
            if (self.real_x <= mouse_x <= self.real_x + self.height and 
                self.real_y <= mouse_y <= self.real_y + self.width):
                return self.action