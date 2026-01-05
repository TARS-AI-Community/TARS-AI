"""
BATTERY MONITOR - V2
==========================

"""

import time
import threading
import board
import adafruit_ina260
from collections import deque
from modules.module_config import load_config

CONFIG = load_config()

class BatteryModule:
    def __init__(self, 
                 battery_capacity_mAh=CONFIG['BATTERY']['battery_capacity_mAh'], 

                 battery_initial_voltage=CONFIG['BATTERY']['battery_initial_voltage'], 

                 battery_cutoff_voltage=CONFIG['BATTERY']['battery_cutoff_voltage'], 

                 auto_shutdown=CONFIG['BATTERY']['auto_shutdown'],
                 smoothing_window=10):
        """Initialize the Battery Module with battery parameters."""
        self.battery_capacity_mAh = battery_capacity_mAh
        self.battery_initial_voltage = battery_initial_voltage
        self.battery_cutoff_voltage = battery_cutoff_voltage
        self.auto_shutdown = auto_shutdown
        self.smoothing_window = smoothing_window
        self.current = 0.0  
        self.voltage = 0.0  
        self.power = 0.0  
        self.battery_percentage = 0.0
        self.normalized_percentage = 0  
        self.percentage_history = deque(maxlen=smoothing_window)
        self.is_running = False
        self.thread = None
        self.last_printed_percentage = None

        self.zero_percent_start_time = None
        self.shutdown_delay_seconds = 60  

        try:
            self.i2c = board.I2C()
            self.ina260 = adafruit_ina260.INA260(self.i2c, address=0x41)
            self.sensor_initialized = True
        except Exception as e:
            print(f"Battery sensor initialization error: {e}")
            self.sensor_initialized = False

    def calculate_battery_percentage(self, current_voltage):

        if current_voltage > self.battery_initial_voltage:
            current_voltage = self.battery_initial_voltage  

        elif current_voltage < self.battery_cutoff_voltage:
            current_voltage = self.battery_cutoff_voltage  

        percentage = ((current_voltage - self.battery_cutoff_voltage) / 
                (self.battery_initial_voltage - self.battery_cutoff_voltage)) * 100
        return round(percentage, 1)

    def normalize_percentage(self, percentage):
        """Normalize the percentage using a moving average to stabilize readings."""
        self.percentage_history.append(percentage)
        if len(self.percentage_history) > 0:
            normalized = sum(self.percentage_history) / len(self.percentage_history)
            return int(normalized)  

        return int(percentage)  

    def _monitoring_loop(self):
        """Internal method that runs in a thread to continuously monitor battery status."""
        while self.is_running and self.sensor_initialized:
            try:
                self.current = self.ina260.current  

                self.voltage = self.ina260.voltage  

                self.power = self.ina260.power  

                self.battery_percentage = self.calculate_battery_percentage(self.voltage)
                self.normalized_percentage = self.normalize_percentage(self.battery_percentage)

                if self.last_printed_percentage is None or self.battery_percentage <= self.last_printed_percentage - 20:
                    print(f"Battery percentage: {self.battery_percentage}%")
                    self.last_printed_percentage = self.battery_percentage

                if self.auto_shutdown and self.sensor_initialized:
                    if self.normalized_percentage <= 0:

                        if self.zero_percent_start_time is None:

                            self.zero_percent_start_time = time.time()
                            print("WARNING: Battery at 0%. System will shutdown in 60 seconds if battery remains critical.")
                        else:

                            elapsed = time.time() - self.zero_percent_start_time
                            if elapsed >= self.shutdown_delay_seconds:
                                print("CRITICAL: Battery at 0% for 60 seconds. Initiating system shutdown...")
                                self._initiate_shutdown()
                                break  

                    else:

                        if self.zero_percent_start_time is not None:
                            print(f"Battery recovered to {self.normalized_percentage}%. Shutdown cancelled.")
                            self.zero_percent_start_time = None

                time.sleep(3)

            except Exception as e:
                print(f"Battery monitoring error: {e}")
                time.sleep(5)

    def _initiate_shutdown(self):
        """Initiate system shutdown."""
        import subprocess
        import os
        try:
            print("Executing: sudo shutdown now")
            subprocess.Popen(['sudo', 'shutdown', 'now'])
        except Exception as e:
            print(f"Failed to shutdown system: {e}")

        time.sleep(2)
        os._exit(0)

    def start(self):
        """Start the battery monitoring thread."""
        if not self.sensor_initialized:
            print("Cannot start battery monitoring: sensor not initialized")
            return False

        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()
            print("Battery monitoring started")
            return True
        return False

    def stop(self):
        """Stop the battery monitoring thread."""
        if self.is_running:
            self.is_running = False
            if self.thread:
                self.thread.join(timeout=2.0)
            print("Battery monitoring stopped")
            return True
        return False

    def is_charging(self):

        current_threshold = 50  

        voltage_rise_threshold = 0.005  

        if hasattr(self, 'current') and self.current > current_threshold:
            return True

        if not hasattr(self, 'voltage_history'):
            self.voltage_history = deque(maxlen=6)

        self.voltage_history.append(self.voltage)

        if len(self.voltage_history) < 5:
            return False

        trend = [self.voltage_history[i+1] - self.voltage_history[i] for i in range(len(self.voltage_history) - 1)]

        if all(x > voltage_rise_threshold for x in trend):
            return True

        return False

    def get_battery_status(self):
        """Return current battery status as a dictionary."""
        return {
            'current': self.current,  
            'voltage': self.voltage,  
            'power': self.power,  
            'percentage': self.battery_percentage,  
            'normalized_percentage': self.normalized_percentage,  
            'capacity': self.battery_capacity_mAh,  
            'is_charging': self.is_charging(),  
            'sensor_initialized': self.sensor_initialized  
        }

    def get_battery_percentage(self):
        """Return just the battery percentage."""
        return self.battery_percentage

    def get_normalized_percentage(self):
        """Return the normalized (smoothed) battery percentage."""
        return self.normalized_percentage