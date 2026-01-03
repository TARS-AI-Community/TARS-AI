"""
module_volume.py

Simple volume control for TARS-AI.
Designed for use with LLM function calling.
"""

import subprocess
import re
from modules.module_messageQue import queue_message

class VolumeControl:
    def __init__(self, control='Master'):
        self.control = control

    def get_volume(self):
        """Get current volume as percentage (0-100)"""
        try:
            output = subprocess.check_output(
                ['amixer', 'get', self.control],
                stderr=subprocess.STDOUT
            ).decode('utf-8')

            # Find volume percentage
            match = re.search(r'\[(\d+)%\]', output)
            if match:
                return int(match.group(1))
            
            return None
        except Exception as e:
            queue_message(f"ERROR: Failed to get volume: {e}")
            return None

    def set_volume(self, percent):
        """Set volume to exact percentage (0-100)"""
        if not (0 <= percent <= 100):
            queue_message(f"ERROR: Volume must be 0-100, got {percent}")
            return False
        
        try:
            subprocess.check_call(
                ['amixer', 'set', self.control, f'{percent}%'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            queue_message(f"Volume set to {percent}%")
            return True
        except Exception as e:
            queue_message(f"ERROR: Failed to set volume: {e}")
            return False

    def adjust_volume(self, change):
        """Adjust volume by relative amount (-100 to +100)"""
        current = self.get_volume()
        if current is None:
            return False
        
        new_volume = max(0, min(100, current + change))
        return self.set_volume(new_volume)

# Singleton instance
_volume_control = None

def get_volume_control():
    """Get or create volume control instance"""
    global _volume_control
    if _volume_control is None:
        _volume_control = VolumeControl()
    return _volume_control