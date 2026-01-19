"""
module_cuptemp.py
Atomikspace
V3
"""

class CPUTempModule:
    def __init__(self):
        self.temperature = 0.0
        try:
            self._read_temp()
            self.sensor_available = True
        except Exception as e:
            print(f"CPU temperature sensor error: {e}")
            self.sensor_available = False
    
    def _read_temp(self):
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = float(f.read()) / 1000.0
        return temp
    
    def get_temperature(self):
        if self.sensor_available:
            try:
                self.temperature = self._read_temp()
            except Exception as e:
                print(f"Error reading temperature: {e}")
        return self.temperature
    
    def get_status(self):
        return {
            'temperature': self.temperature,
            'sensor_available': self.sensor_available
        }
