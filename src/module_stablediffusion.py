import requests
import base64
from PIL import Image
import tempfile
import time
import pygame
import threading
from module_config import load_config

# Load configuration
config = load_config()

def display_image_fullscreen(image_path):
    """Function to display image in fullscreen for 8 seconds."""
    # Initialize Pygame
    pygame.init()

    # Set the Pygame window to fullscreen
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    # Allow time for the Pygame window to be fully initialized
    time.sleep(0.1)  # Give a slight delay to ensure it's on top

    # Load the image using Pygame
    pygame_img = pygame.image.load(image_path)

    # Display the image on the screen
    screen.blit(pygame_img, (0, 0))
    pygame.display.update()

    # Start a timer for 8 seconds but keep the event loop running
    start_ticks = pygame.time.get_ticks()  # Get the current time (milliseconds)
    running = True

    # Event loop to keep the window open and allow other events to be handled
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:  # If the window is closed, exit
                running = False
        
        # Check if 8 seconds have passed
        if pygame.time.get_ticks() - start_ticks > 8000:
            running = False

        pygame.display.update()

    # Close Pygame and exit
    pygame.quit()

def get_base64_encoded_image_generate(sdpromptllm):
    # Create the payload with the necessary parameters for the API request
    payload = {
        "prompt": sdpromptllm,
        "negative_prompt": config['STABLE_DIFFUSION']['negative_prompt'],
        "seed": int(config['STABLE_DIFFUSION']['seed']),
        "sampler_name": config['STABLE_DIFFUSION']['sampler_name'],
        "denoising_strength": float(config['STABLE_DIFFUSION']['denoising_strength']),
        "steps": int(config['STABLE_DIFFUSION']['steps']),
        "cfg_scale": float(config['STABLE_DIFFUSION']['cfg_scale']),
        "width": int(config['STABLE_DIFFUSION']['width']),
        "height": int(config['STABLE_DIFFUSION']['height']),
        "restore_faces": config.get('STABLE_DIFFUSION', 'restore_faces') == 'True',
        "override_settings_restore_afterwards": True,
    }

    # Correct the URL without the comment
    url = f'{config["STABLE_DIFFUSION"]["url"]}/sdapi/v1/txt2img'

    try:
        # Making a POST request to the API with the payload
        response = requests.post(url, json=payload)
        response.raise_for_status()

        # Assuming the response returns a JSON with an 'images' key containing base64 encoded images
        image_data_base64 = response.json()['images'][0]  # Taking the first image as a Base64 string
        
        # Decode the Base64 data to get the image
        image_data = base64.b64decode(image_data_base64)

        # Save the binary image data to a temporary PNG file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_png_file:
            temp_png_file.write(image_data)
            temp_png_file_path = temp_png_file.name

        # Start a new thread to display the image
        display_thread = threading.Thread(target=display_image_fullscreen, args=(temp_png_file_path,))
        display_thread.start()

        # Continue with the rest of the program (non-blocking)
        return f"Picture is displayed in fullscreen for 8 seconds. The program continues."

    except requests.exceptions.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

    return None
