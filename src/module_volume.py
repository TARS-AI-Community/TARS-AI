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
