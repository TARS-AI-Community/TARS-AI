import subprocess
import re

class RaspbianVolumeManager:
    def __init__(self, control='Master'):
        self.control = control

    def get_volume(self):
        try:
            output = subprocess.check_output(
                ['amixer', 'get', self.control],
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            match = re.search(r'\[(\d+)%\]', output)
            if match:
                return int(match.group(1))
            raise RuntimeError("Volume percentage not found in amixer output.")
        except subprocess.CalledProcessError as e:
            print(f"Error getting volume: {e}")
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
            print(f"Volume set to {percent}%.")
        except subprocess.CalledProcessError as e:
            print(f"Error setting volume: {e}")

def handle_volume_command(user_input):
    """
    Interprets and handles volume-related commands from the user input.

    Parameters:
        user_input (str): The user's command.

    Returns:
        str: A response describing the result of the volume action.
    """
    volume_manager = RaspbianVolumeManager()  # Create volume manager instance

    # Handle specific volume commands
    if "increase" in user_input.lower() or "raise" in user_input.lower():
        current_volume = volume_manager.get_volume()
        if current_volume is not None:
            increment = 10
            if "by" in user_input.lower():
                match = re.search(r'by (\d+)', user_input.lower())
                if match:
                    increment = int(match.group(1))
            new_volume = min(current_volume + increment, 100)
            volume_manager.set_volume(new_volume)
            return f"Volume increased by {increment}%. Current volume is {new_volume}%."

    elif "decrease" in user_input.lower() or "lower" in user_input.lower():
        current_volume = volume_manager.get_volume()
        if current_volume is not None:
            decrement = 10
            if "by" in user_input.lower():
                match = re.search(r'by (\d+)', user_input.lower())
                if match:
                    decrement = int(match.group(1))
            new_volume = max(current_volume - decrement, 0)
            volume_manager.set_volume(new_volume)
            return f"Volume decreased by {decrement}%. Current volume is {new_volume}%."

    elif "adjust" in user_input.lower():
        current_volume = volume_manager.get_volume()
        if current_volume is not None:
            if "up" in user_input.lower():
                increment = 5
                if "by" in user_input.lower():
                    match = re.search(r'by (\d+)', user_input.lower())
                    if match:
                        increment = int(match.group(1))
                new_volume = min(current_volume + increment, 100)
                volume_manager.set_volume(new_volume)
                return f"Volume adjusted up by {increment}%. Current volume is {new_volume}%."

            elif "down" in user_input.lower():
                decrement = 5
                if "by" in user_input.lower():
                    match = re.search(r'by (\d+)', user_input.lower())
                    if match:
                        decrement = int(match.group(1))
                new_volume = max(current_volume - decrement, 0)
                volume_manager.set_volume(new_volume)
                return f"Volume adjusted down by {decrement}%. Current volume is {new_volume}%."
            else:
                return "Please specify 'up' or 'down' when using 'adjust'."

    elif "set" in user_input.lower():
        match = re.search(r'(\d{1,3})%', user_input)
        if match:
            volume = int(match.group(1))
            if 0 <= volume <= 100:
                volume_manager.set_volume(volume)
                return f"Volume set to {volume}%."
            else:
                return "Please provide a valid volume between 0 and 100."
        else:
            return "Please specify the volume percentage."

    elif "mute" in user_input.lower():
        volume_manager.set_volume(0)
        return "Volume has been muted."

    elif "unmute" in user_input.lower() or "activate sound" in user_input.lower():
        default_volume = 50  # Default volume level when unmuting
        volume_manager.set_volume(default_volume)
        return f"Volume has been unmuted. Current volume is {default_volume}%."

    elif "check volume" in user_input.lower() or "current volume" in user_input.lower():
        current_volume = volume_manager.get_volume()
        if current_volume is not None:
            return f"The current volume is {current_volume}%."
        else:
            return "Unable to retrieve the current volume level."

    return "Volume control command not recognized. Please specify a valid action (e.g., increase, decrease, adjust, mute, unmute, set)."
