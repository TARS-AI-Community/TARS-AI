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
        self.zero_percent_start_time = None
        self.shutdown_delay_seconds = 60
        
        self.voltage_history = deque(maxlen=15)
        self.baseline_voltage = None
        self.charging_state = "DISCHARGING"
        self.last_printed_state = None
        
        self.last_servo_activity_time = 0
        self.servo_cooldown_seconds = 10
        self.verbose = False

        try:
            self.i2c = board.I2C()
            self.ina260 = adafruit_ina260.INA260(self.i2c, address=0x41)
            self.sensor_initialized = True
            print("INA260 sensor detected")
        except Exception as e:
            print(f"INA260 sensor not detected: {e}")
            self.sensor_initialized = False

    def signal_servo_activity(self):
        self.last_servo_activity_time = time.time()
        self.voltage_history.clear()

    def set_verbose(self, enabled):
        self.verbose = enabled

    def _is_servo_cooldown_active(self):
        return (time.time() - self.last_servo_activity_time) < self.servo_cooldown_seconds

    def calculate_battery_percentage(self, current_voltage):
        if current_voltage > self.battery_initial_voltage:
            current_voltage = self.battery_initial_voltage  
        elif current_voltage < self.battery_cutoff_voltage:
            current_voltage = self.battery_cutoff_voltage  
        percentage = ((current_voltage - self.battery_cutoff_voltage) / 
                (self.battery_initial_voltage - self.battery_cutoff_voltage)) * 100
        return round(percentage, 1)

    def normalize_percentage(self, percentage):
        self.percentage_history.append(percentage)
        if len(self.percentage_history) > 0:
            normalized = sum(self.percentage_history) / len(self.percentage_history)
            return int(normalized)  
        return int(percentage)

    def _get_voltage_trend(self):
        if len(self.voltage_history) < 3:
            return 0.0
        voltages = list(self.voltage_history)
        total_change = sum(voltages[i] - voltages[i-1] for i in range(1, len(voltages)))
        return total_change / (len(voltages) - 1)

    def _update_charging_state(self):
        if self._is_servo_cooldown_active():
            return
        
        self.voltage_history.append(self.voltage)
        trend = self._get_voltage_trend()
        
        if self.baseline_voltage is None and len(self.voltage_history) >= 5:
            self.baseline_voltage = sum(self.voltage_history) / len(self.voltage_history)
        
        if self.baseline_voltage is None:
            return
        
        elevation = (self.voltage - self.baseline_voltage) * 1000
        was_charging = self.charging_state == "CHARGING"
        
        if trend > 0.002:
            self.charging_state = "CHARGING"
            self.baseline_voltage = min(self.baseline_voltage, min(list(self.voltage_history)[-5:]) - 0.02)
        elif was_charging and elevation >= 5:
            self.charging_state = "CHARGING"
        elif was_charging and elevation < 5 and trend < -0.002:
            self.charging_state = "DISCHARGING"
            self.baseline_voltage = sum(self.voltage_history) / len(self.voltage_history)
        elif was_charging:
            self.charging_state = "CHARGING"
        elif self.current > 50:
            self.charging_state = "DISCHARGING"
            if trend < 0:
                self.baseline_voltage = min(self.baseline_voltage, self.voltage)
        else:
            self.charging_state = "IDLE"
        
        if self.last_printed_state != self.charging_state:
            if self.charging_state == "CHARGING":
                #print("Battery is charging")
                pass
            elif self.charging_state == "DISCHARGING":
                #print("Battery is discharging")
                pass
            self.last_printed_state = self.charging_state

    def _monitoring_loop(self):
        print("Battery monitoring started")
        while self.is_running and self.sensor_initialized:
            try:
                self.current = self.ina260.current  
                self.voltage = self.ina260.voltage  
                self.power = self.ina260.power  
                self.battery_percentage = self.calculate_battery_percentage(self.voltage)
                self.normalized_percentage = self.normalize_percentage(self.battery_percentage)
                
                self._update_charging_state()
                
                if self.verbose:
                    self.print_debug()

                if self.auto_shutdown and self.sensor_initialized:
                    if self.normalized_percentage <= 0:
                        if self.zero_percent_start_time is None:
                            self.zero_percent_start_time = time.time()
                        else:
                            elapsed = time.time() - self.zero_percent_start_time
                            if elapsed >= self.shutdown_delay_seconds:
                                self._initiate_shutdown()
                                break  
                    else:
                        if self.zero_percent_start_time is not None:
                            self.zero_percent_start_time = None

                time.sleep(0.5)

            except Exception as e:
                print(f"Battery monitoring error: {e}")
                time.sleep(5)

    def _initiate_shutdown(self):
        import subprocess
        import os
        try:
            subprocess.Popen(['sudo', 'shutdown', 'now'])
        except Exception as e:
            print(f"Failed to shutdown system: {e}")
        time.sleep(2)
        os._exit(0)

    def start(self):
        if not self.sensor_initialized:
            print("Cannot start battery monitoring: sensor not initialized")
            return False
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()
            return True
        return False

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self.thread:
                self.thread.join(timeout=2.0)
            return True
        return False

    def is_charging(self):
        return self.charging_state == "CHARGING"

    def get_battery_status(self):
        return {
            'current': self.current,  
            'voltage': self.voltage,  
            'power': self.power,  
            'percentage': self.battery_percentage,  
            'normalized_percentage': self.normalized_percentage,  
            'capacity': self.battery_capacity_mAh,  
            'is_charging': self.is_charging(),
            'charging_state': self.charging_state,
            'sensor_initialized': self.sensor_initialized  
        }

    def get_battery_percentage(self):
        return self.battery_percentage

    def get_normalized_percentage(self):
        return self.normalized_percentage

    def print_debug(self):
        trend = self._get_voltage_trend()
        baseline_str = f"{self.baseline_voltage:.3f}V" if self.baseline_voltage else "---"
        elevation = (self.voltage - self.baseline_voltage) * 1000 if self.baseline_voltage else 0
        cooldown = "COOLDOWN" if self._is_servo_cooldown_active() else ""
        print(f"V: {self.voltage:.3f} (base: {baseline_str}, {elevation:+.0f}mV)  |  "
              f"I: {self.current:+.0f}mA  |  {self.charging_state} {cooldown}")