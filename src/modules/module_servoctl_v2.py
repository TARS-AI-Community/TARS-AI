"""
module_servoctl.py

Servo Control Module for TARS-AI Application.

This module provides a comprehensive set of functions to control servos in TARS, enabling complex movements such as:
- Torso height adjustment.
- Torso rotation to forward/backward positions.
- Controlled arm and hand movements.
- Synchronized servo adjustments for smooth motion transitions.
"""

from __future__ import division
import time
import Adafruit_PCA9685
from threading import Thread
from datetime import datetime

from modules.module_messageQue import queue_message
from module_config import load_config

config = load_config()

# Global speed factor (1.0 = max speed, 0.1 = slowest, must be > 0)
global_arm_speed = 0.5
servo_positions = {}

try:
    # Attempt to initialize the PCA9685 using I2C
    pwm = Adafruit_PCA9685.PCA9685(busnum=1)
    pwm.set_pwm_freq(50)
except FileNotFoundError as e:
    queue_message(f"ERROR: I2C device not found. Ensure that /dev/i2c-1 exists. Details: {e}")
    pwm = None  # Fallback if hardware is unavailable
except Exception as e:
    queue_message(f"ERROR: Unexpected error during PCA9685 initialization: {e}")
    pwm = None  # Fallback if hardware is unavailable

# Servo Configuration Mapping with Integer Casting
portMain = int(config["SERVO"]["portMainMin"])
portMainMin = int(config["SERVO"]["portMainMin"])
portMainMax = int(config["SERVO"]["portMainMax"])

portForarm = int(config["SERVO"]["portForarmMin"])
portForarmMin = int(config["SERVO"]["portForarmMin"])
portForarmMax = int(config["SERVO"]["portForarmMax"])

portHand = int(config["SERVO"]["portHandMin"])
portHandMin = int(config["SERVO"]["portHandMin"])
portHandMax = int(config["SERVO"]["portHandMax"])

starMain = int(config["SERVO"]["starMainMin"])
starMainMin = int(config["SERVO"]["starMainMin"])
starMainMax = int(config["SERVO"]["starMainMax"])

starForarm = int(config["SERVO"]["starForarmMin"])
starForarmMin = int(config["SERVO"]["starForarmMin"])
starForarmMax = int(config["SERVO"]["starForarmMax"])

starHand = int(config["SERVO"]["starHandMin"])
starHandMin = int(config["SERVO"]["starHandMin"])
starHandMax = int(config["SERVO"]["starHandMax"])

# Center Lift Servo (0) Values
upHeight = int(config["SERVO"]["upHeight"])
neutralHeight = int(config["SERVO"]["neutralHeight"])
downHeight = int(config["SERVO"]["downHeight"])

# Port Drive Servo (1) Values
perfectPortoffset = int(config["SERVO"]["perfectPortoffset"])  # Offset for fine-tuning
forwardPort = int(config["SERVO"]["forwardPort"]) + perfectPortoffset
neutralPort = int(config["SERVO"]["neutralPort"]) + perfectPortoffset
backPort = int(config["SERVO"]["backPort"]) + perfectPortoffset

# Starboard Drive Servo (2) Values
perfectStaroffset = int(config["SERVO"]["perfectStaroffset"])  # Offset for fine-tuning
forwardStarboard = int(config["SERVO"]["forwardStarboard"]) + perfectStaroffset
neutralStarboard = int(config["SERVO"]["neutralStarboard"]) + perfectStaroffset
backStarboard = int(config["SERVO"]["backStarboard"]) + perfectStaroffset

def initialize_servos():
    """Ensure all servos start at their minimum positions with speed-controlled movement."""
    global portMain, portForarm, portHand, starMain, starForarm, starHand

    # Disable all servos momentarily
    pwm.set_all_pwm(0, 0)  
    time.sleep(0.1)  # Allow servos to settle
    reset_positions()
    print("All servos initialized to minimum positions")

def disable_all_servos():
    for ch in range(16):
        time.sleep(0.05)
        pwm.set_pwm(ch, 0, 0)

def reset_positions():    
    move_legs(30, 50, 50, 0.2)
    move_legs(50, 50, 50, 0.2)
    time.sleep(0.5)
    move_arm(1, 1, 1, 1, 1, 1, 0.4)
    time.sleep(0.5)
    disable_all_servos()

def step_forward():
    """ #smooth move
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(30, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(45, 20, 20, 0.6)
    time.sleep(0.2)
    move_legs(52, 60, 60, 0.2)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.8)
    disable_all_servos() """
    #fast move
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(22, 50, 50, 0.6)
    time.sleep(0.2)
    move_legs(40, 15, 15, 0.65)
    time.sleep(0.2)
    move_legs(85, 50, 50, 0.7)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

def step_backward():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(28, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(35, 70, 70, 0.6)
    time.sleep(0.2)
    move_legs(55, 40, 40, 0.2)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.8)
    time.sleep(0.2)
    disable_all_servos()

def turn_right():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(100, 0, 0, 0.8)
    time.sleep(0.3)
    move_legs(0, 70, 30, 0.6)
    time.sleep(0.2)
    move_legs(50, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(0, 50, 50, 0.3)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()


def turn_left():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(100, 0, 0, 0.8)
    time.sleep(0.3)
    move_legs(0, 30, 70, 0.3)
    time.sleep(0.2)
    move_legs(50, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(0, 50, 50, 0.3)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

        
def right_hi():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 70, 0.8)
    time.sleep(0.2)
    move_arm(1, 1, 1, 0, 0, 0, 0.5)
    time.sleep(0.2)
    move_arm(100, 1, 1, 0, 0, 0, 0.8)
    time.sleep(0.2)
    move_arm(100, 100, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 50, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 100, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 50, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 100, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 50, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(100, 1, 1, 0, 0, 0,1)
    time.sleep(0.2)
    move_arm(1, 1, 1, 0, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

def laugh():
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(1, 50, 50, 1)
    time.sleep(0.1)
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(1, 50, 50, 1)
    time.sleep(0.1)
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(1, 50, 50, 1)
    time.sleep(0.1)
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(1, 50, 50, 1)
    time.sleep(0.1)
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(1, 50, 50, 1)
    time.sleep(0.1)
    move_legs(50, 50, 50, 1)
    time.sleep(0.2)
    disable_all_servos()

def swing_legs():
    move_legs(50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(100, 50, 50, 1)
    time.sleep(0.1)
    move_legs(0, 20, 80, 0.6)
    time.sleep(0.1)
    move_legs(0, 80, 20, 0.6)
    time.sleep(0.1)
    move_legs(0, 20, 80, 0.6)
    time.sleep(0.1)
    move_legs(0, 80, 20, 0.6)
    time.sleep(0.1)
    move_legs(0, 20, 80, 0.6)
    time.sleep(0.1)
    move_legs(0, 80, 20, 0.6)
    time.sleep(0.1)
    move_legs(0, 50, 50, 0.6)
    time.sleep(0.1)
    move_legs(50, 50, 50, 0.7)
    time.sleep(0.2)
    disable_all_servos()


def pezz_dispenser():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.6)
    move_arm(1, 1, 1, 1, 1, 1, 0.6)
    time.sleep(0.2)
    move_legs(50, 50, 70, 0.6)
    time.sleep(0.2)
    move_arm(100, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_arm(100, 100, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_arm(100, 100, 100, 1, 1, 1, 0.8)
    time.sleep(10)
    move_arm(100, 100, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_arm(100, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.6)
    time.sleep(0.2)
    move_arm(1, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

def now():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.8)
    time.sleep(0.2)
    move_arm(75, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_legs(50, 50, 65, 0.8)
    time.sleep(0.2)
    move_arm(75, 80, 1, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(60, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(75, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(60, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(75, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(60, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(75, 80, 0, 0, 0, 0, 0.9)
    time.sleep(0.2)
    move_arm(75, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)        
    move_legs(50, 50, 80, 0.8)
    time.sleep(0.2)
    move_arm(1, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

def balance():
    # up
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(30, 50, 50, 0.8)
    # balance
    time.sleep(0.2)
    move_legs(30, 60, 60, 0.5)
    time.sleep(0.2)
    move_legs(30, 40, 40, 0.5)
    time.sleep(0.2)
    move_legs(30, 60, 60, 0.5)
    time.sleep(0.2)
    move_legs(30, 40, 40, 0.5)
    time.sleep(0.2)
    move_legs(30, 60, 60, 0.5)
    time.sleep(0.2)
    move_legs(30, 40, 40, 0.5)
    # down
    time.sleep(0.2)
    move_legs(30, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.8)
    time.sleep(0.5)
    disable_all_servos()


def mic_drop():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 100, 0.8)
    time.sleep(0.2)
    move_arm(1, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(60, 50, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(60, 70, 1, 0, 0, 0, 1)
    time.sleep(1)
    move_arm(60, 70, 100, 0, 0, 0, 1)
    time.sleep(2)
    move_arm(1, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.8)
    time.sleep(0.5)
    disable_all_servos()


def monster():
    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 70, 70, 0.4)

    move_arm(1, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_arm(100, 1, 1, 100, 1, 1, 0.8)

    time.sleep(0.2)
    move_legs(50, 70, 70, 0.4)

    time.sleep(0.2)
    move_arm(100, 100, 1, 100, 100, 1, 1)
    time.sleep(0.2)
    move_arm(100, 100, 100, 100, 100, 100, 1)
    time.sleep(0.2)
    move_arm(100, 50, 100, 100, 100, 100, 1)
    time.sleep(0.2)
    move_arm(100, 100, 50, 100, 50, 50, 1)
    time.sleep(0.2)
    move_arm(100, 50, 100, 100, 100, 100, 1)
    time.sleep(0.2)
    move_arm(100, 100, 50, 100, 50, 50, 1)
    time.sleep(0.2)
    move_arm(100, 100, 100, 100, 100, 100, 1)
    time.sleep(0.2)

    move_arm(100, 100, 1, 100, 100, 1, 1)
    time.sleep(0.2)
    move_arm(100, 100, 100, 100, 100, 100, 1)
    time.sleep(0.2)
    move_arm(100, 100, 1, 100, 100, 1, 1)
    time.sleep(0.2)
    move_arm(100, 100, 100, 100, 100, 100, 1)
    time.sleep(0.2)
    move_arm(100, 100, 1, 100, 100, 1, 1)
    time.sleep(0.2)
    move_arm(100, 100, 100, 100, 100, 100, 1)
    time.sleep(0.2)

    move_arm(100, 100, 1, 100, 100, 1, 1)
    time.sleep(0.2)
    move_arm(100, 1, 1, 100, 1, 1, 1)

    move_legs(50, 70, 70, 0.4)
    time.sleep(0.2)

    time.sleep(0.2)
    move_arm(1, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)

    move_legs(80, 50, 50, 0.4)
    time.sleep(0.2)

    move_legs(50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()

def pose():
    move_legs(50, 50, 50, 0.4)
    move_legs(30, 40, 40, 0.4)
    move_legs(100, 30, 30, 0.4)
    time.sleep(3)
    move_legs(100, 30, 30, 0.4)
    move_legs(30, 30, 30, 0.4)
    move_legs(30, 40, 40, 0.4)
    move_legs(50, 50, 50, 0.4)
    disable_all_servos()

def move_legs(
    height_percent=None,
    starboard_percent=None,
    port_percent=None,
    speed_factor=1.0
):
    """
    Controls 3 leg servos using percentage values.
    
    Parameters:
        height_percent: Percentage for servo 0 (middle servo that raises/lowers the legs).
        starboard_percent: Percentage for servo 1 (starboard leg).
        port_percent: Percentage for servo 2 (port leg).
        speed_factor: Speed factor for smooth movement (0.1 = slow, 1.0 = fast).
    """

    def percentage_to_value(percent, min_val, max_val):
        """Convert percentage (1-100) to a value between min and max."""
        if percent == 0:
            return None
        if percent == 1:
            return min_val
        if percent == 100:
            return max_val
        if max_val > min_val:
            value = min_val + ((max_val - min_val) * (percent - 1) / 99)
        else:
            value = min_val - ((min_val - max_val) * (percent - 1) / 99)
        return int(round(value))

    def move_servo_gradually(channel, target_value, speed_factor):
        """Moves the servo gradually to the target value at the given speed."""
        if target_value is None:
            return
        current_value = servo_positions.get(channel, None)
        if current_value is None or current_value == target_value:
            pwm.set_pwm(channel, 0, target_value)
            servo_positions[channel] = target_value
            return
        step = 1 if target_value > current_value else -1
        for value in range(current_value, target_value + step, step):
            pwm.set_pwm(channel, 0, value)
            time.sleep(0.02 * (1.0 - speed_factor))
        servo_positions[channel] = target_value

    # Define min/max for each servo
    movements = [
        (height_percent, upHeight, downHeight, 0),
        (starboard_percent, forwardStarboard, backStarboard, 1),
        (port_percent, forwardPort, backPort, 2),
    ]

    threads = []
    for percent, min_val, max_val, channel in movements:
        if percent is not None and percent != 0:
            target_value = percentage_to_value(percent, min_val, max_val)
            thread = Thread(target=move_servo_gradually, args=(channel, target_value, speed_factor))
            threads.append(thread)

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

def move_arm(
    port_main=None, port_forearm=None, port_hand=None,
    star_main=None, star_forearm=None, star_hand=None,
    speed_factor=1.0
):
    """
    Moves both port and starboard arm servos using percentage values (1-100).
    
    Parameters:
        port_main, port_forearm, port_hand: Percentages for port arm servos.
        star_main, star_forearm, star_hand: Percentages for starboard arm servos.
        speed_factor: Speed factor for movement (0.1 = slow, 1.0 = fast).
    """

    def percentage_to_value(percent, min_val, max_val):
        """Convert percentage (1-100) to a value within min/max range."""
        if percent == 0:
            return None
        if percent == 1:
            return min_val
        if percent == 100:
            return max_val
        if max_val > min_val:
            value = min_val + ((max_val - min_val) * (percent - 1) / 99)
        else:
            value = min_val - ((min_val - max_val) * (percent - 1) / 99)
        return int(round(value))
    
    def move_servo_gradually(channel, target_value, speed_factor):
        """Moves the servo gradually to the target value at the given speed."""
        if target_value is None:
            return
        current_value = servo_positions.get(channel, None)
        if current_value is None or current_value == target_value:
            pwm.set_pwm(channel, 0, target_value)
            servo_positions[channel] = target_value
            return
        step = 1 if target_value > current_value else -1
        for value in range(current_value, target_value + step, step):
            pwm.set_pwm(channel, 0, value)
            time.sleep(0.02 * (1.0 - speed_factor))
        servo_positions[channel] = target_value

    # Create a list of all desired movements: (percent, min, max, channel)
    movements = [
        (port_main, portMainMin, portMainMax, 3),
        (port_forearm, portForarmMin, portForarmMax, 4),
        (port_hand, portHandMin, portHandMax, 5),
        (star_main, starMainMin, starMainMax, 6),
        (star_forearm, starForarmMin, starForarmMax, 7),
        (star_hand, starHandMin, starHandMax, 8),
    ]

    threads = []
    for percent, min_val, max_val, channel in movements:
        if percent is not None and percent != 0:
            target_value = percentage_to_value(percent, min_val, max_val)
            thread = Thread(target=move_servo_gradually, args=(channel, target_value, speed_factor))
            threads.append(thread)

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

