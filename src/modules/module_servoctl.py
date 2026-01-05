"""
module_servoctl.py
Atomikspace
V3
"""

from __future__ import division
import time
import board
import busio
from adafruit_pca9685 import PCA9685

from modules.module_messageQue import queue_message
from modules.module_config import load_config

config = load_config()

# === Hardcoded Neutral Position Constants ===
NEUTRAL_LEFT_HEIGHT = 350
NEUTRAL_RIGHT_HEIGHT = 350
NEUTRAL_LEFT_LEG = 300
NEUTRAL_RIGHT_LEG = 300

global_arm_speed = 0.5
global_easing_strength = 0.6

servo_positions = {}

pca = None
MAX_RETRIES = 3


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

# Apply arm offsets (same pattern as leg servos)
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


def pwm_to_duty_cycle(pwm_value):
    return int((pwm_value / 4095.0) * 65535)


def set_servo_pwm(channel, pwm_value):
    if pca is None:
        return False
    
    duty_cycle = pwm_to_duty_cycle(pwm_value)

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
    move_legs(50, 50, 50, 50, 0.2)
    time.sleep(0.5)
    move_arm(1, 1, 1, 1, 1, 1, 0.3)
    time.sleep(0.5)
    disable_all_servos()


def step_forward():
    global MOVING
    if not MOVING:
        MOVING = True
        move_legs(50, 50, 50, 50, 0.9)
        move_legs(42, 42, 40, 40, 0.9)
        move_legs(70, 70, 23, 23, 0.9)
        move_legs(30, 30, 30, 30, 0.8)
        move_legs(70, 70, 35, 35, 0.9)
        move_legs(60, 60, 50, 50, 0.9)
        move_legs(50, 50, 50, 50, 0.9)
        time.sleep(0.1)
        disable_all_servos()
        MOVING = False

def walk_forward():
    global MOVING
    if not MOVING:
        MOVING = True
        move_legs(50, 50, 50, 50, 0.8)
        sequence = [
            (50, 70, 50, 50),
            (50, 70, 35, 50),
            (70, 50, 50, 50),
            (70, 50, 50, 35),
        ]
        for _ in range(2):
            for a, b, c, d in sequence:
                move_legs(a, b, c, d, 0.5)
        move_legs(70, 70, 50, 50, 0.6)
        move_legs(50, 50, 50, 50, 0.8) 
        time.sleep(0.1)
        disable_all_servos()
        MOVING = False

def step_backward():
    global MOVING
    if not MOVING:
        MOVING = True
        move_legs(50, 50, 50, 50, 0.9)
        move_legs(30, 30, 55, 55, 0.8)
        move_legs(68, 68, 82, 82, 0.8)
        move_legs(30, 30, 70, 70, 0.8)
        move_legs(50, 50, 62, 62, 0.9)
        move_legs(65, 65, 50, 50, 0.9)
        move_legs(50, 50, 50, 50, 0.9)
        time.sleep(0.1)
        disable_all_servos()
        MOVING = False

def walk_backward():
    global MOVING
    if not MOVING:
        MOVING = True
        move_legs(50, 50, 50, 50, 0.8)
        sequence = [
        (50, 65, 50, 50),
        (50, 65, 50, 35),
        (65, 50, 50, 50),
        (65, 50, 35, 50),
        ]
        for _ in range(2):
            for a, b, c, d in sequence:
                move_legs(a, b, c, d, 0.5)
        move_legs(50, 50, 50, 50, 0.6)
        time.sleep(0.1)
        disable_all_servos()
        MOVING = False


def turn_right():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(70, 70, 50, 50, 0.9)
    move_legs(70, 70, 65, 35, 0.9)
    move_legs(45, 45, 65, 35, 0.9)
    move_legs(52, 52, 50, 50, 0.8)
    move_legs(50, 50, 50, 50, 0.8)
    time.sleep(0.1)
    disable_all_servos()

def turn_right_slow():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(70, 40, 50, 50, 0.7)
    move_legs(70, 40, 50, 40, 0.7)
    move_legs(50, 70, 50, 40, 0.7)
    move_legs(50, 70, 50, 50, 0.7)
    move_legs(50, 50, 50, 50, 0.9)
    time.sleep(0.1)
    disable_all_servos()


def turn_left():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(70, 70, 50, 50, 0.9)
    move_legs(70, 70, 35, 65, 0.9)
    move_legs(45, 45, 35, 65, 0.9)
    move_legs(52, 52, 50, 50, 0.8)
    move_legs(50, 50, 50, 50, 0.8)
    time.sleep(0.1)
    disable_all_servos()

def turn_left_slow():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(40, 70, 50, 50, 0.7)
    move_legs(40, 70, 40, 50, 0.7)
    move_legs(70, 50, 40, 50, 0.7)
    move_legs(70, 50, 50, 50, 0.7)
    move_legs(50, 50, 50, 50, 0.9)
    time.sleep(0.1)
    disable_all_servos()

def right_hi():
    move_legs(50, 50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 70, 0.8)
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
    move_arm(100, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_arm(1, 1, 1, 0, 0, 0, 0.6)
    time.sleep(0.2)
    move_legs(80, 80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()


def laugh():
    for _ in range(5):
        move_legs(50, 50, 50, 50, 1)
        time.sleep(0.1)
        move_legs(1, 1, 50, 50, 1)
        time.sleep(0.1)
    move_legs(50, 50, 50, 50, 1)
    time.sleep(0.2)
    disable_all_servos()


def swing_legs():
    move_legs(50, 50, 50, 50, 1)
    time.sleep(0.1)
    move_legs(100, 100, 50, 50, 1)
    time.sleep(0.1)
    for _ in range(3):
        move_legs(0, 0, 20, 80, 0.6)
        time.sleep(0.1)
        move_legs(0, 0, 80, 20, 0.6)
        time.sleep(0.1)
    move_legs(0, 0, 50, 50, 0.6)
    time.sleep(0.1)
    move_legs(50, 50, 50, 50, 0.7)
    time.sleep(0.2)
    disable_all_servos()


def pezz_dispenser():
    move_legs(50, 50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 70, 0.8)
    time.sleep(0.2)
    move_arm(1, 1, 1, 1, 1, 1, 0.5)
    time.sleep(0.2)
    move_arm(40, 1, 1, 40, 1, 1, 0.6)
    time.sleep(0.2)
    move_arm(60, 70, 100, 40, 1, 1, 1)
    time.sleep(1)
    move_arm(60, 70, 100, 60, 70, 100, 1)
    time.sleep(1)
    move_arm(60, 70, 100, 0, 0, 0, 1)
    time.sleep(2)
    move_arm(1, 1, 1, 0, 0, 0, 1)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 50, 50, 0.8)
    time.sleep(0.5)
    disable_all_servos()


def monster():
    move_legs(50, 50, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(80, 80, 70, 70, 0.4)
    move_arm(1, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_arm(100, 1, 1, 100, 1, 1, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 70, 70, 0.4)
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
    move_legs(50, 50, 70, 70, 0.4)
    time.sleep(0.2)
    time.sleep(0.2)
    move_arm(1, 1, 1, 1, 1, 1, 0.8)
    time.sleep(0.2)
    move_legs(80, 80, 50, 50, 0.4)
    time.sleep(0.2)
    move_legs(50, 50, 50, 50, 0.4)
    time.sleep(0.2)
    disable_all_servos()


def pose():
    move_legs(50, 50, 50, 50, 0.4)
    move_legs(30, 30, 40, 40, 0.4)
    move_legs(100, 100, 30, 30, 0.4)
    time.sleep(3)
    move_legs(100, 100, 30, 30, 0.4)
    move_legs(30, 30, 30, 30, 0.4)
    move_legs(30, 30, 40, 40, 0.4)
    move_legs(50, 50, 50, 50, 0.4)
    disable_all_servos()


def bow():
    move_legs(50, 50, 50, 50, 0.4)
    move_legs(15, 15, 50, 50, 0.7)
    move_legs(15, 15, 70, 70, 0.7)
    move_legs(60, 60, 70, 70, 0.7)
    move_legs(95, 95, 65, 65, 0.7)
    time.sleep(3)
    move_legs(15, 15, 65, 65, 0.7)
    move_legs(50, 50, 50, 50, 0.4)
    disable_all_servos()

def tilt_right():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(20, 80, 50, 50, 0.9)
    time.sleep(3)
    move_legs(50, 50, 50, 50, 0.9)
    disable_all_servos()


def tilt_left():
    move_legs(50, 50, 50, 50, 0.9)
    move_legs(80, 20, 50, 50, 0.9)
    time.sleep(3)
    move_legs(50, 50, 50, 50, 0.9)
    disable_all_servos()

def side_side():
    move_legs(50, 50, 50, 50, 0.8)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(10, 90, 50, 50, 0.9)
    move_legs(90, 10, 50, 50, 0.9)
    move_legs(50, 50, 50, 50, 0.9)
    disable_all_servos()

def wave_right():
    move_legs(50, 50, 50, 50, 0.8)
    move_legs(50, 90, 50, 50, 0.9)
    move_legs(20, 90, 50, 100, 0.9)
    move_legs(20, 90, 50, 70, 0.9)
    move_legs(20, 90, 50, 100, 0.9)
    move_legs(20, 90, 50, 70, 0.9)
    move_legs(50, 90, 50, 100, 0.9)
    move_legs(50, 90, 50, 70, 0.9)
    move_legs(50, 90, 50, 100, 0.9)
    move_legs(50, 90, 50, 70, 0.9)
    move_legs(20, 90, 50, 100, 0.9)
    move_legs(20, 90, 50, 70, 0.9)
    move_legs(20, 90, 50, 100, 0.9)
    move_legs(20, 90, 50, 70, 0.9)
    move_legs(50, 50, 50, 50, 0.8)
    disable_all_servos()

def wave_left():
    move_legs(50, 50, 50, 50, 0.8)
    move_legs(90, 50, 50, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 50, 100, 50, 0.9)
    move_legs(90, 50, 70, 50, 0.9)
    move_legs(90, 50, 100, 50, 0.9)
    move_legs(90, 50, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(90, 20, 100, 50, 0.9)
    move_legs(90, 20, 70, 50, 0.9)
    move_legs(50, 50, 50, 50, 0.8)
    disable_all_servos()


def move_servos_synchronized(movements, speed_factor):
    servo_data = []
    
    for channel, target_value in movements:
        if target_value is None:
            continue
            
        current_value = servo_positions.get(channel, None)
        
        if current_value is None:
            set_servo_pwm(channel, target_value)
            servo_positions[channel] = target_value
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
    
    if not servo_data:
        return
    
    max_distance = max(s['distance'] for s in servo_data)
    base_delay = 0.02 * (1.0 - speed_factor)
    
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
        
        if global_easing_strength > 0:
            if progress < 0.5:
                eased = 2 * progress * progress
            else:
                eased = 1 - 2 * (1 - progress) * (1 - progress)
            delay_multiplier = 1.0 + global_easing_strength * (1.0 - 4 * (eased - 0.5) ** 2)
        else:
            delay_multiplier = 1.0
        
        time.sleep(base_delay * delay_multiplier)
    
    for servo in servo_data:
        servo_positions[servo['channel']] = servo['target']
    
    time.sleep(0.05)


def move_legs(left_height_percent=None, right_height_percent=None, left_leg_percent=None, right_leg_percent=None, speed_factor=1.0):
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
    def percentage_to_value(percent, min_val, max_val):
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

    movements = [
        (4, percentage_to_value(left_main, leftMainMin, leftMainMax) if left_main is not None and left_main != 0 else None),
        (5, percentage_to_value(left_forearm, leftForarmMin, leftForarmMax) if left_forearm is not None and left_forearm != 0 else None),
        (6, percentage_to_value(left_hand, leftHandMin, leftHandMax) if left_hand is not None and left_hand != 0 else None),
        (7, percentage_to_value(right_main, rightMainMin, rightMainMax) if right_main is not None and right_main != 0 else None),
        (8, percentage_to_value(right_forearm, rightForarmMin, rightForarmMax) if right_forearm is not None and right_forearm != 0 else None),
        (9, percentage_to_value(right_hand, rightHandMin, rightHandMax) if right_hand is not None and right_hand != 0 else None),
    ]

    move_servos_synchronized(movements, speed_factor)


def cleanup():
    disable_all_servos()


if __name__ == "__main__":
    initialize_servos()