""" Created by mskull """

import subprocess
import re

from modules.module_messageQue import queue_message

class RaspbianVolumeManager:
    def __init__(self, control='Master'):
        self.control = control

    def get_volume(self):
        try:
            # Executes the amixer command to get volume information
            output = subprocess.check_output(
                ['amixer', 'get', self.control],
                stderr=subprocess.STDOUT
            ).decode('utf-8')

            # Search for volume percentages in the output for both channels
            left_match = re.search(r'Front Left: Playback \d+ \[(\d+)%\]', output)
            right_match = re.search(r'Front Right: Playback \d+ \[(\d+)%\]', output)

            if left_match and right_match:
                # Calculate the average volume of both channels
                left_volume = int(left_match.group(1))
                right_volume = int(right_match.group(1))
                return (left_volume + right_volume) // 2

            elif left_match:  # If only the left channel is present
                return int(left_match.group(1))

            elif right_match:  # If only the right channel is present
                return int(right_match.group(1))

            raise RuntimeError("Volume percentage not found in amixer output.")
        except subprocess.CalledProcessError as e:
            queue_message(f"Error getting volume: {e}")
            return None

    def set_volume(self, percent):
        if not (0 <= percent <= 100):
            raise ValueError("Volume percentage must be between 0 and 100.")
        try:
            subprocess.check_call(
                ['amixer', 'set', self.control, f'{percent}%'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            # Verify the current volume after setting it
            current_volume = self.get_volume()
            queue_message(f"Volume set to {percent}%. Current volume is {current_volume}%.")
        except subprocess.CalledProcessError as e:
            queue_message(f"Error setting volume: {e}")


def correct_transcription(transcribed_text):
    """
    Corrects common misinterpretations of volume commands by the STT module.
    Parameters:
        transcribed_text (str): The transcribed user input.
    Returns:
        str: The corrected user input.
    """
    corrections = {
        "the grease volume": "decrease volume",
        "degrees volume": "decrease volume",
        "the greek volume": "decrease volume",
        "the great volume": "decrease volume",
        "the greece volume": "decrease volume",
        "the brief volume": "decrease volume",
        "the grief volume": "decrease volume",
        "increase volume": "increase volume",
        "reduce volume": "decrease volume",
    }
    for wrong, correct in corrections.items():
        if wrong in transcribed_text.lower():
            suggestion = "increase" if "increase" in correct else "decrease"
            queue_message(f"I think I heard {suggestion}. Proceeding as '{correct}'.")
            return transcribed_text.lower().replace(wrong, correct)
    return transcribed_text


def handle_volume_command(user_input):
    """
    Interprets and handles volume-related commands from the user input.
    Parameters:
        user_input (str): The user's command.
    Returns:
        str: A response describing the result of the volume action.
    """
    # Correct the input text based on common misinterpretations
    user_input = correct_transcription(user_input)

    volume_manager = RaspbianVolumeManager()  # Create volume manager instance

    current_volume = volume_manager.get_volume()

    if current_volume is None:
        return "Unable to retrieve the current volume level. Please try again."

    #queue_message(f"TOOL: Current Volume {current_volume / 100:.2f}")  # Report the correct volume value

    # Handle specific volume commands
    if "increase" in user_input.lower() or "raise" in user_input.lower():
        increment = 10
        if "by" in user_input.lower():
            match = re.search(r'by (\d+)', user_input.lower())
            if match:
                increment = int(match.group(1))
        new_volume = min(current_volume + increment, 100)
        volume_manager.set_volume(new_volume)
        current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
        return f"Volume increased by {increment}%. Current volume is {current_volume}%."

    elif "decrease" in user_input.lower() or "lower" in user_input.lower():
        decrement = 10
        if "by" in user_input.lower():
            match = re.search(r'by (\d+)', user_input.lower())
            if match:
                decrement = int(match.group(1))
        new_volume = max(current_volume - decrement, 0)
        volume_manager.set_volume(new_volume)
        current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
        return f"Volume decreased by {decrement}%. Current volume is {current_volume}%."

    elif "adjust" in user_input.lower():
        if "up" in user_input.lower():
            increment = 5
            if "by" in user_input.lower():
                match = re.search(r'by (\d+)', user_input.lower())
                if match:
                    increment = int(match.group(1))
            new_volume = min(current_volume + increment, 100)
            volume_manager.set_volume(new_volume)
            current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
            return f"Volume adjusted up by {increment}%. Current volume is {current_volume}%."

        elif "down" in user_input.lower():
            decrement = 5
            if "by" in user_input.lower():
                match = re.search(r'by (\d+)', user_input.lower())
                if match:
                    decrement = int(match.group(1))
            new_volume = max(current_volume - decrement, 0)
            volume_manager.set_volume(new_volume)
            current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
            return f"Volume adjusted down by {decrement}%. Current volume is {current_volume}%."
        else:
            return "Please specify 'up' or 'down' when using 'adjust'."

    elif "set" in user_input.lower():
        match = re.search(r'(\d{1,3})%', user_input)
        if match:
            volume = int(match.group(1))
            if 0 <= volume <= 100:
                volume_manager.set_volume(volume)
                current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
                return f"Volume set to {volume}%. Current volume is {current_volume}%."
            else:
                return "Please provide a valid volume between 0 and 100."
        else:
            return "Please specify the volume percentage."

    elif "mute" in user_input.lower():
        volume_manager.set_volume(0)
        current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
        return "Volume has been muted. Current volume is 0%."

    elif "unmute" in user_input.lower() or "activate sound" in user_input.lower():
        default_volume = 50  # Default volume level when unmuting
        volume_manager.set_volume(default_volume)
        current_volume = volume_manager.get_volume()  # Ensure updated value is fetched
        return f"Volume has been unmuted. Current volume is {current_volume}%."

    elif "check volume" in user_input.lower() or "current volume" in user_input.lower():
        return f"The current volume is {current_volume}%."

    return "Volume control command not recognized. Please specify a valid action (e.g., increase, decrease, adjust, mute, unmute, set)."