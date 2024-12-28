"""
module_secrets.py

Secrets Module for GPTARS Application.

This module provides functionality for handling secret or special content.
"""

# === Standard Libraries ===
from pathlib import Path
from moviepy.video.io.VideoFileClip import VideoFileClip

def play_video_fullscreen(video_path, rotation_angle=0):
    """
    Plays a video in fullscreen mode using MoviePy while maintaining aspect ratio.

    Parameters:
    - video_path (str): Path to the video file to play.
    - rotation_angle (int): Angle to rotate the video (default is 0).
    """
    # Resolve the base directory of the current file
    BASE_DIR = Path(__file__).resolve().parent

    # Construct the absolute path to the video file
    clip_path = BASE_DIR / video_path

    # Ensure the video file exists
    if not clip_path.exists():
        raise FileNotFoundError(f"[ERROR] Video file not found: {clip_path}")

    try:
        # Load the video file
        clip = VideoFileClip(str(clip_path))

        # Apply rotation if specified
        if rotation_angle != 0:
            clip = clip.rotate(rotation_angle)

        # Play the video in fullscreen mode
        clip.preview()

    finally:
        # Close the video clip to release resources
        clip.close()
