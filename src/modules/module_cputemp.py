"""
module_cputemp.py
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""

import threading
import time
from modules.module_messageQue import queue_message
from modules.module_config import load_config


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

_cpu_temp_instance = None
_thermal_monitor_thread = None
_stop_thermal_monitor = threading.Event()
_reset_timer = threading.Event()
_ventilate_threshold = 60.0
_check_interval = 30
_is_ventilating = False
_ventilate_callback = None
_last_movement_time = 0
_movement_cooldown = 10

CONFIG = load_config()
_ventilate_enabled = CONFIG['MISC']['ventilate']


def set_cpu_temp_instance(instance):
    global _cpu_temp_instance
    _cpu_temp_instance = instance


def set_ventilate_callback(callback):
    global _ventilate_callback
    _ventilate_callback = callback


def is_ventilating():
    return _is_ventilating


def set_ventilating(state):
    global _is_ventilating
    _is_ventilating = state


def record_movement():
    global _last_movement_time
    _last_movement_time = time.time()
    _reset_timer.set()


def _thermal_monitor_loop():
    while not _stop_thermal_monitor.is_set():
        try:
            time_since_movement = time.time() - _last_movement_time
            if _reset_timer.is_set():
                _reset_timer.clear()
                _stop_thermal_monitor.wait(_check_interval)
                continue
            
            if time_since_movement < _movement_cooldown:
                remaining_cooldown = _movement_cooldown - time_since_movement
                _stop_thermal_monitor.wait(min(remaining_cooldown, _check_interval))
                continue
            
            if _cpu_temp_instance and _cpu_temp_instance.sensor_available:
                temp = _cpu_temp_instance.get_temperature()
                if temp >= _ventilate_threshold and not _is_ventilating and _ventilate_enabled:
                    if _ventilate_callback:
                        try:
                            _ventilate_callback()
                        except Exception as e:
                            pass

                elif temp < (_ventilate_threshold - 5) and _is_ventilating:
                    pass
        
        except Exception as e:
            pass

        _stop_thermal_monitor.wait(_check_interval)


def start_thermal_monitoring():
    global _thermal_monitor_thread
    
    if _thermal_monitor_thread and _thermal_monitor_thread.is_alive():
        return
    
    if not _cpu_temp_instance or not _cpu_temp_instance.sensor_available:
        return
    
    _stop_thermal_monitor.clear()
    _thermal_monitor_thread = threading.Thread(
        target=_thermal_monitor_loop,
        name="ThermalMonitor",
        daemon=True
    )
    _thermal_monitor_thread.start()


def stop_thermal_monitoring():
    global _thermal_monitor_thread
    
    if _thermal_monitor_thread and _thermal_monitor_thread.is_alive():
        _stop_thermal_monitor.set()
        _thermal_monitor_thread.join(timeout=5)
        _thermal_monitor_thread = None


def get_thermal_status():
    return {
        'monitoring_active': _thermal_monitor_thread is not None and _thermal_monitor_thread.is_alive(),
        'is_ventilating': _is_ventilating,
        'threshold': _ventilate_threshold,
        'current_temp': _cpu_temp_instance.temperature if _cpu_temp_instance else None
    }