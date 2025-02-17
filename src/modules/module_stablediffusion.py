import requests
import base64
from PIL import Image
import tempfile
import time
import pygame
import threading
from io import BytesIO

from modules.module_config import load_config
from modules.module_messageQue import queue_message

# Load configuration
config = load_config()

def generate_image(prompt):
    """
    Generate an image based on the provided prompt using the configured image generation service.

    Parameters:
    - prompt (str): A textual description of the image to be generated.

    Returns:
    - str: The result of the image generation process. If the tool is disabled, returns "Image Tool not enabled."
    """
    result = "Image Tool not enabled"
    if config['STABLE_DIFFUSION']['enabled'] == "True":
        if config['STABLE_DIFFUSION']['service'] == "openai":
            result = get_image_from_dalle_v3(prompt)
        if config['STABLE_DIFFUSION']['service'] == "automatic1111":
            result = get_image_from_automatic1111(prompt)
    return result 

def get_image_from_dalle_v3(prompt):
    # Initialize the OpenAI client
    from openai import OpenAI
    client = OpenAI(api_key=config['LLM']['api_key'])  # Replace with your API key

    try:
        # Generate the image using the updated client method
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,  # Number of images
        )

        # Extract the image URL
        image_url = response.data[0].url

        # Fetch the image data from the URL
        image_response = requests.get(image_url)
        image_response.raise_for_status()

        # Decode the image data into a PIL image
        image = Image.open(BytesIO(image_response.content))

        # Save the image to a temporary file after resizing to 512x512
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_png_file:
            resized_image = image.resize((512, 512))  # Resize the image
            resized_image.save(temp_png_file, format='PNG')  # Save the resized image
            temp_png_file_path = temp_png_file.name

        # Display the image in fullscreen using a thread
        display_thread = threading.Thread(target=display_image_fullscreen, args=(temp_png_file_path,))
        display_thread.start()

        # Return a success message
        return f"Image generated and displayed in fullscreen."

    except Exception as e:
        queue_message(f"Error: {e}")
        return None

def get_image_from_automatic1111(sdpromptllm):
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
        return f"The image has been created and displayed on screen."

    except requests.exceptions.HTTPError as err:
        queue_message(f"HTTP error occurred: {err}")
    except requests.exceptions.RequestException as e:
        queue_message(f"Error: {e}")

    return f"Image generated and displayed in fullscreen."
  
def display_image_fullscreen(image_path):
    """Function to display an image in fullscreen, scaled to fit the screen, for 8 seconds."""
    # Initialize Pygame
    pygame.init()

    # Set the Pygame window to fullscreen
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    # Allow time for the Pygame window to be fully initialized
    time.sleep(0.1)  # Give a slight delay to ensure it's on top

    # Get the screen dimensions
    screen_width, screen_height = screen.get_size()

    # Load the image using Pygame
    pygame_img = pygame.image.load(image_path)

    # Get the original image dimensions
    img_width, img_height = pygame_img.get_width(), pygame_img.get_height()

    # Calculate the scaling factor to maintain aspect ratio
    scale_factor = min(screen_width / img_width, screen_height / img_height)

    # Compute the new dimensions
    new_width = int(img_width * scale_factor)
    new_height = int(img_height * scale_factor)

    # Scale the image
    scaled_img = pygame.transform.smoothscale(pygame_img, (new_width, new_height))

    # Calculate position to center the image on the screen
    x_pos = (screen_width - new_width) // 2
    y_pos = (screen_height - new_height) // 2

    # Display the image on the screen
    screen.fill((0, 0, 0))  # Fill the screen with black
    screen.blit(scaled_img, (x_pos, y_pos))
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
