"""
Module: Servo Controller V3.1
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

from __future__ import division
import time
import os
import board
import busio
from adafruit_pca9685 import PCA9685

from modules.module_messageQue import queue_message
from modules.module_config import load_config

config = load_config()

NEUTRAL_LEFT_HEIGHT = 350
NEUTRAL_RIGHT_HEIGHT = 350
NEUTRAL_LEFT_LEG = 300
NEUTRAL_RIGHT_LEG = 300

global_arm_speed = 0.5
global_easing_strength = 0.6

SERVO_POSITIONS_FILE = os.path.expanduser("~/.servo_positions.json")

def _load_servo_positions():
    
    import json
    try:
        with open(SERVO_POSITIONS_FILE, 'r') as f:
            positions = json.load(f)
            return {int(k): v for k, v in positions.items()}
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"[SERVO] No saved positions found, starting fresh")
        return {}

def _save_servo_positions():
    
    import json
    try:
        with open(SERVO_POSITIONS_FILE, 'w') as f:
            json.dump(servo_positions, f)
    except Exception as e:
        print(f"[SERVO] Warning: Could not save positions: {e}")

servo_positions = _load_servo_positions()

_channels_initialized = set(servo_positions.keys())

pca = None
MAX_RETRIES = 3

battery_module = None

def set_battery_module(battery_mod):
    global battery_module
    battery_module = battery_mod

def signal_servo_activity():
    if battery_module is not None:
        battery_module.signal_servo_activity()

def initialize_pca9685():
    
    global pca
    
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=0x40)
        pca.frequency = 50
        queue_message("LOAD: PCA9685 initialized successfully")
        return True
        
    except OSError as e:
        if e.errno == 121:
            queue_message(f"ERROR: I2C Remote I/O error - Check connections and power!")
        else:
            queue_message(f"ERROR: I2C error {e.errno}: {e}")
        return False
        
    except Exception as e:
        queue_message(f"ERROR: Failed to initialize PCA9685: {e}")
        return False

if not initialize_pca9685():
    queue_message("WARNING: PCA9685 initialization failed - check hardware")

leftMainMin = int(config["SERVO"]["leftMainMin"])
leftMainMax = int(config["SERVO"]["leftMainMax"])
leftForarmMin = int(config["SERVO"]["leftForarmMin"])
leftForarmMax = int(config["SERVO"]["leftForarmMax"])
leftHandMin = int(config["SERVO"]["leftHandMin"])
leftHandMax = int(config["SERVO"]["leftHandMax"])

rightMainMin = int(config["SERVO"]["rightMainMin"])
rightMainMax = int(config["SERVO"]["rightMainMax"])
rightForarmMin = int(config["SERVO"]["rightForarmMin"])
rightForarmMax = int(config["SERVO"]["rightForarmMax"])
rightHandMin = int(config["SERVO"]["rightHandMin"])
rightHandMax = int(config["SERVO"]["rightHandMax"])

leftMainOffset = int(config["SERVO"]["leftMainOffset"])
leftMainMin = leftMainMin + leftMainOffset
leftMainMax = leftMainMax + leftMainOffset

leftForearmOffset = int(config["SERVO"]["leftForearmOffset"])
leftForarmMin = leftForarmMin + leftForearmOffset
leftForarmMax = leftForarmMax + leftForearmOffset

leftHandOffset = int(config["SERVO"]["leftHandOffset"])
leftHandMin = leftHandMin + leftHandOffset
leftHandMax = leftHandMax + leftHandOffset

rightMainOffset = int(config["SERVO"]["rightMainOffset"])
rightMainMin = rightMainMin + rightMainOffset
rightMainMax = rightMainMax + rightMainOffset

rightForearmOffset = int(config["SERVO"]["rightForearmOffset"])
rightForarmMin = rightForarmMin + rightForearmOffset
rightForarmMax = rightForarmMax + rightForearmOffset

rightHandOffset = int(config["SERVO"]["rightHandOffset"])
rightHandMin = rightHandMin + rightHandOffset
rightHandMax = rightHandMax + rightHandOffset

perfectLeftHeightOffset = int(config["SERVO"]["perfectLeftHeightOffset"])
leftUpHeight = int(config["SERVO"]["leftUpHeight"]) + perfectLeftHeightOffset
leftNeutralHeight = NEUTRAL_LEFT_HEIGHT + perfectLeftHeightOffset
leftDownHeight = int(config["SERVO"]["leftDownHeight"]) + perfectLeftHeightOffset

perfectRightHeightOffset = int(config["SERVO"]["perfectRightHeightOffset"])
rightUpHeight = int(config["SERVO"]["rightUpHeight"]) - perfectRightHeightOffset
rightNeutralHeight = NEUTRAL_RIGHT_HEIGHT - perfectRightHeightOffset
rightDownHeight = int(config["SERVO"]["rightDownHeight"]) - perfectRightHeightOffset

perfectLeftLegOffset = int(config["SERVO"]["perfectLeftLegOffset"])
forwardLeftLeg = int(config["SERVO"]["forwardLeftLeg"]) + perfectLeftLegOffset
neutralLeftLeg = NEUTRAL_LEFT_LEG + perfectLeftLegOffset
backLeftLeg = int(config["SERVO"]["backLeftLeg"]) + perfectLeftLegOffset

perfectRightLegOffset = int(config["SERVO"]["perfectRightLegOffset"])
forwardRightLeg = int(config["SERVO"]["forwardRightLeg"]) + perfectRightLegOffset
neutralRightLeg = NEUTRAL_RIGHT_LEG + perfectRightLegOffset
backRightLeg = int(config["SERVO"]["backRightLeg"]) + perfectRightLegOffset

MOVING = False
HOLD = -1
ARMS_PRESENT = config["SERVO"]["arms_present"]

if not servo_positions:
    print("[SERVO] No saved positions - initializing to neutral estimates")
    servo_positions[0] = leftNeutralHeight
    servo_positions[1] = rightNeutralHeight
    servo_positions[2] = neutralLeftLeg
    servo_positions[3] = neutralRightLeg
    servo_positions[4] = leftMainMin
    servo_positions[5] = leftForarmMin
    servo_positions[6] = leftHandMin
    servo_positions[7] = rightMainMin
    servo_positions[8] = rightForarmMin
    servo_positions[9] = rightHandMin
else:
    print(f"[SERVO] Loaded saved positions")

_on_movement_start = None
_on_movement_end = None
_is_ventilate_operation = False

def set_movement_callbacks(on_start=None, on_end=None):
    
    global _on_movement_start, _on_movement_end
    _on_movement_start = on_start
    _on_movement_end = on_end

def _notify_movement_start():
    global _is_ventilate_operation
    
    signal_servo_activity()
    
    if not _is_ventilate_operation:
        try:
            from modules.module_cputemp import is_ventilating
            if is_ventilating():
                from modules.module_movements import ventilate_off
                ventilate_off()
        except Exception as e:
            pass
    
    if _on_movement_start:
        try:
            _on_movement_start()
        except Exception as e:
            queue_message(f"ERROR: Failed to pause UI/STT: {e}")

def _notify_movement_end():
    
    signal_servo_activity()
    
    if _on_movement_end:
        try:
            _on_movement_end()
        except Exception as e:
            queue_message(f"ERROR: Failed to resume UI/STT: {e}")

def pulse_to_duty_cycle(pulse_value):
    
    MAX_PULSE = 600
    pulse_us = 500 + (pulse_value / MAX_PULSE) * 2000
    duty_cycle = int((pulse_us / 20000.0) * 65535)
    return duty_cycle

def set_servo_pwm(channel, pwm_value):
    if pca is None:
        return False
    
    duty_cycle = pulse_to_duty_cycle(pwm_value)

    for attempt in range(MAX_RETRIES):
        try:
            pca.channels[channel].duty_cycle = duty_cycle
            return True
            
        except OSError as e:
            if e.errno == 121:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.05)
                    continue
                else:
                    queue_message(f"I2C error on channel {channel} after {MAX_RETRIES} attempts")
            return False
            
        except Exception as e:
            queue_message(f"Error setting PWM on channel {channel}: {e}")
            return False
    
    return False

def initialize_servos():
    if pca is None:
        queue_message("WARNING: Cannot initialize servos - PCA9685 not available")
        return
    
    try:
        for channel in range(16):
            pca.channels[channel].duty_cycle = 0
    except Exception as e:
        queue_message(f"Error initializing servos: {e}")
    
    time.sleep(0.1)
    reset_positions()
    print("All servos initialized")

def disable_all_servos():
    if pca is None:
        return
    
    try:
        for channel in range(16):
            pca.channels[channel].duty_cycle = 0
    except Exception as e:
        queue_message(f"Error disabling servos: {e}")
    
    time.sleep(0.05)

def reset_positions():
    global servo_positions
    
    servo_positions[0] = leftNeutralHeight
    servo_positions[1] = rightNeutralHeight
    servo_positions[2] = neutralLeftLeg
    servo_positions[3] = neutralRightLeg
    servo_positions[4] = leftMainMin
    servo_positions[5] = leftForarmMin
    servo_positions[6] = leftHandMin
    servo_positions[7] = rightMainMin
    servo_positions[8] = rightForarmMin
    servo_positions[9] = rightHandMin
    
    disable_all_servos()
    
    move_legs(30, 30, 50, 50, 0.5)
    time.sleep(0.2)
    move_legs(50, 50, 50, 50, 0.5)
    time.sleep(0.3)
    
    move_arm(1, 1, 1, 1, 1, 1, 0.3)
    time.sleep(0.5)
    
    disable_all_servos()

def move_servos_synchronized(movements, speed_factor, easing_strength=None):
    """
    Move multiple servos simultaneously.
    
    Parameters:
    - movements: List of (channel, target_value) tuples
    - speed_factor: Speed multiplier (0.0-1.0, higher is faster)
    - easing_strength: Easing amount (None uses global default, 0 = linear, higher = more ease in/out)
    """
    global _channels_initialized
    
    effective_easing = easing_strength if easing_strength is not None else global_easing_strength
    
    signal_servo_activity()
    
    servo_data = []
    hold_channels = []
    has_uninitialized_channel = False
    
    for channel, target_value in movements:
        if target_value is None:
            continue
        
        if channel not in _channels_initialized:
            has_uninitialized_channel = True
            _channels_initialized.add(channel)
            
        current_value = servo_positions.get(channel, None)
        
        if current_value is None:
            neutral_positions = {
                0: leftNeutralHeight,
                1: rightNeutralHeight,
                2: neutralLeftLeg,
                3: neutralRightLeg,
                4: leftMainMin,
                5: leftForarmMin,
                6: leftHandMin,
                7: rightMainMin,
                8: rightForarmMin,
                9: rightHandMin,
            }
            current_value = neutral_positions.get(channel, 300)
            servo_positions[channel] = current_value
        
        if target_value == -1:
            hold_channels.append((channel, current_value))
            continue
        
        if current_value == target_value:
            continue
        
        distance = abs(target_value - current_value)
        step = 1 if target_value > current_value else -1
        
        servo_data.append({
            'channel': channel,
            'current': current_value,
            'target': target_value,
            'step': step,
            'distance': distance,
            'steps_taken': 0
        })
    
    for channel, value in hold_channels:
        set_servo_pwm(channel, value)
    
    if not servo_data:
        return
    
    try:
        from modules.module_cputemp import record_movement
        record_movement()
    except Exception:
        pass
    
    max_distance = max(s['distance'] for s in servo_data)
    
    if has_uninitialized_channel:
        effective_speed = min(speed_factor, 0.3)
    else:
        effective_speed = speed_factor
    
    base_delay = 0.02 * (1.0 - effective_speed)
    
    while any(s['current'] != s['target'] for s in servo_data):
        for servo in servo_data:
            if servo['current'] != servo['target']:
                servo['current'] += servo['step']
                set_servo_pwm(servo['channel'], servo['current'])
                servo['steps_taken'] += 1
        
        if max_distance > 0:
            progress = min(s['steps_taken'] for s in servo_data if s['current'] != s['target'] or s['steps_taken'] > 0) / max_distance
        else:
            progress = 1.0
        
        if effective_easing > 0:
            if progress < 0.5:
                eased = 2 * progress * progress
            else:
                eased = 1 - 2 * (1 - progress) * (1 - progress)
            delay_multiplier = 1.0 + effective_easing * (1.0 - 4 * (eased - 0.5) ** 2)
        else:
            delay_multiplier = 1.0
        
        time.sleep(base_delay * delay_multiplier)
    
    for servo in servo_data:
        servo_positions[servo['channel']] = servo['target']
    
    _save_servo_positions()
    
    signal_servo_activity()
    
    time.sleep(0.05)

def move_legs(left_height_percent=None, right_height_percent=None, left_leg_percent=None, right_leg_percent=None, speed_factor=1.0):
    """
    Move leg servos to specified positions.
    
    Parameters:
    - left_height_percent: Left leg height (1-100, None to skip)
    - right_height_percent: Right leg height (1-100, None to skip)
    - left_leg_percent: Left leg forward/back (1-100, None to skip)
    - right_leg_percent: Right leg forward/back (1-100, None to skip)
    - speed_factor: Speed multiplier (0.0-1.0, higher is faster)
    """
    
    def percentage_to_value(percent, min_val, max_val):
        if percent == 0:
            return None
        normalized = (percent - 1) / 99.0
        value = min_val + (max_val - min_val) * normalized
        return int(round(value))

    movements = []
    
    if left_height_percent is not None and left_height_percent != 0:
        target_value = percentage_to_value(left_height_percent, leftUpHeight, leftDownHeight)
        movements.append((0, target_value))
    
    if right_height_percent is not None and right_height_percent != 0:
        target_value = percentage_to_value(right_height_percent, rightUpHeight, rightDownHeight)
        movements.append((1, target_value))
    
    if left_leg_percent is not None and left_leg_percent != 0:
        target_value = percentage_to_value(left_leg_percent, forwardLeftLeg, backLeftLeg)
        movements.append((2, target_value))
    
    if right_leg_percent is not None and right_leg_percent != 0:
        target_value = percentage_to_value(right_leg_percent, forwardRightLeg, backRightLeg)
        movements.append((3, target_value))

    move_servos_synchronized(movements, speed_factor)

def move_arm(left_main=None, left_forearm=None, left_hand=None,
             right_main=None, right_forearm=None, right_hand=None, speed_factor=1.0):
    """
    Move arm servos to specified positions.
    
    Parameters:
    - left_main: Left main arm position (1-100, None to skip, -1 to hold)
    - left_forearm: Left forearm position (1-100, None to skip, -1 to hold)
    - left_hand: Left hand position (1-100, None to skip, -1 to hold)
    - right_main: Right main arm position (1-100, None to skip, -1 to hold)
    - right_forearm: Right forearm position (1-100, None to skip, -1 to hold)
    - right_hand: Right hand position (1-100, None to skip, -1 to hold)
    - speed_factor: Speed multiplier (0.0-1.0, higher is faster)
    """
    
    arm_speed_curve = 0.2
    adjusted_speed = speed_factor ** arm_speed_curve
    arm_easing_strength = 0.85
    
    def percentage_to_value(percent, min_val, max_val):
        if percent == 0:
            return None
        if percent == -1:
            return -1
        if percent == 1:
            return min_val
        if percent == 100:
            return max_val
        if max_val > min_val:
            value = min_val + ((max_val - min_val) * (percent - 1) / 99)
        else:
            value = min_val - ((min_val - max_val) * (percent - 1) / 99)
        return int(round(value))

    def get_value(val, min_val, max_val):
        if val is None or val == 0:
            return None
        if val == -1:
            return -1
        return percentage_to_value(val, min_val, max_val)

    movements = [
        (4, get_value(left_main, leftMainMin, leftMainMax)),
        (5, get_value(left_forearm, leftForarmMin, leftForarmMax)),
        (6, get_value(left_hand, leftHandMin, leftHandMax)),
        (7, get_value(right_main, rightMainMin, rightMainMax)),
        (8, get_value(right_forearm, rightForarmMin, rightForarmMax)),
        (9, get_value(right_hand, rightHandMin, rightHandMax)),
    ]

    move_servos_synchronized(movements, adjusted_speed, easing_strength=arm_easing_strength)

def cleanup():
    
    disable_all_servos()

from modules.module_movements import (
    step_forward,
    walk_forward,
    step_backward,
    walk_backward,
    turn_right,
    turn_right_slow,
    turn_left,
    turn_left_slow,
    right_hi,
    left_hi,
    laugh,
    excited,
    swing_legs,
    left_pezz_dispenser,
    right_pezz_dispenser,
    monster,
    pose,
    bow,
    tilt_right,
    tilt_left,
    side_side,
    wave_right,
    wave_left,
    neutral_legs,
    ventilate_on,
    ventilate_off,
    set_swap_turn_directions,
    left_point,
    right_point,
    left_poke,
    right_poke,
    left_wave_open,
    right_wave_open,
    left_shy_wave,
    right_shy_wave,
    happy_dance
)

set_swap_turn_directions(config["CONTROLS"]["swap_turn_directions"])

from modules.module_movement_registry import (
    MOVEMENTS,
    LEGS_ONLY,
    HAS_ARMS,
    get_all,
    get_by_type,
    get_legs_only,
    get_has_arms,
    get_names,
    get_names_by_type
)

if __name__ == "__main__":
    initialize_servos()