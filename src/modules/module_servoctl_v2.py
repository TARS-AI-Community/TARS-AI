"""
module_servoctl_v2.py
Atomikspace
"""

from __future__ import division
import time
from threading import Thread, Lock

# Modern CircuitPython imports
import board
import busio
from adafruit_pca9685 import PCA9685

from modules.module_messageQue import queue_message
from module_config import load_config

config = load_config()

# Global speed factor
global_arm_speed = 0.5

i2c_lock = Lock()
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


# Initialize once at module load
if not initialize_pca9685():
    queue_message("WARNING: PCA9685 initialization failed - check hardware")

# Servo Configuration
portMainMin = int(config["SERVO"]["portMainMin"])
portMainMax = int(config["SERVO"]["portMainMax"])
portForarmMin = int(config["SERVO"]["portForarmMin"])
portForarmMax = int(config["SERVO"]["portForarmMax"])
portHandMin = int(config["SERVO"]["portHandMin"])
portHandMax = int(config["SERVO"]["portHandMax"])

starMainMin = int(config["SERVO"]["starMainMin"])
starMainMax = int(config["SERVO"]["starMainMax"])
starForarmMin = int(config["SERVO"]["starForarmMin"])
starForarmMax = int(config["SERVO"]["starForarmMax"])
starHandMin = int(config["SERVO"]["starHandMin"])
starHandMax = int(config["SERVO"]["starHandMax"])

upHeight = int(config["SERVO"]["upHeight"])
neutralHeight = int(config["SERVO"]["neutralHeight"])
downHeight = int(config["SERVO"]["downHeight"])

perfectPortoffset = int(config["SERVO"]["perfectPortoffset"])
forwardPort = int(config["SERVO"]["forwardPort"]) + perfectPortoffset
neutralPort = int(config["SERVO"]["neutralPort"]) + perfectPortoffset
backPort = int(config["SERVO"]["backPort"]) + perfectPortoffset

perfectStaroffset = int(config["SERVO"]["perfectStaroffset"])
forwardStarboard = int(config["SERVO"]["forwardStarboard"]) + perfectStaroffset
neutralStarboard = int(config["SERVO"]["neutralStarboard"]) + perfectStaroffset
backStarboard = int(config["SERVO"]["backStarboard"]) + perfectStaroffset

MOVING = False


def pwm_to_duty_cycle(pwm_value):
    return int((pwm_value / 4095.0) * 65535)


def set_servo_pwm(channel, pwm_value):
    if pca is None:
        return False
    
    duty_cycle = pwm_to_duty_cycle(pwm_value)

    for attempt in range(MAX_RETRIES):
        try:
            with i2c_lock:
                pca.channels[channel].duty_cycle = duty_cycle
            return True
            
        except OSError as e:
            if e.errno == 121:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.05)  # Small delay before retry
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
        with i2c_lock:
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
    
    move_arm(1, 1, 1, 1, 1, 1, 0.4)
    time.sleep(0.2)
    move_legs(50, 50, 50, 0.4)
    
    try:
        with i2c_lock:
            for channel in range(16):
                pca.channels[channel].duty_cycle = 0
    except Exception as e:
        queue_message(f"Error disabling servos: {e}")
    
    time.sleep(0.2)


def reset_positions():  
    move_legs(20, 0, 0, 0.2)  
    move_legs(30, 50, 50, 0.2)
    move_legs(50, 50, 50, 0.2)
    time.sleep(0.5)
    move_arm(1, 1, 1, 1, 1, 1, 0.3)
    time.sleep(0.5)
    disable_all_servos()


def step_forward():
    global MOVING
    if not MOVING:
        MOVING = True
        move_legs(50, 50, 50, 0.4)
        time.sleep(0.2)
        move_legs(22, 50, 50, 0.6)
        time.sleep(0.2)
        move_legs(40, 17, 17, 0.65)
        time.sleep(0.2)
        move_legs(85, 50, 50, 0.8)
        time.sleep(0.2)
        move_legs(50, 50, 50, 1)
        time.sleep(0.5)
        disable_all_servos()
        MOVING = False


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
    move_arm(100, 1, 1, 0, 0, 0, 1)
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
    for _ in range(5):
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
    for _ in range(3):
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
    move_legs(80, 50, 50, 0.8)
    time.sleep(0.2)
    move_legs(80, 50, 70, 0.8)
    time.sleep(0.2)
    move_legs(50, 50, 70, 0.8)
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


def bow():
    move_legs(50, 50, 50, 0.4)
    move_legs(15, 50, 50, 0.7)
    move_legs(15, 70, 70, 0.7)
    move_legs(60, 70, 70, 0.7)
    move_legs(95, 65, 65, 0.7)
    time.sleep(3)
    move_legs(15, 65, 65, 0.7)
    move_legs(50, 50, 50, 0.4)
    disable_all_servos()


def move_servo_gradually_thread(channel, target_value, speed_factor):
    if target_value is None:
        return
    
    with i2c_lock:
        current_value = servo_positions.get(channel, None)
    
    if current_value is None or current_value == target_value:
        if set_servo_pwm(channel, target_value):
            with i2c_lock:
                servo_positions[channel] = target_value
        return
    
    step = 1 if target_value > current_value else -1
    for value in range(current_value, target_value + step, step):
        set_servo_pwm(channel, value)
        time.sleep(0.02 * (1.0 - speed_factor))
    
    with i2c_lock:
        servo_positions[channel] = target_value


def move_legs(height_percent=None, starboard_percent=None, port_percent=None, speed_factor=1.0):
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
        (height_percent, upHeight, downHeight, 0),
        (starboard_percent, forwardStarboard, backStarboard, 1),
        (port_percent, forwardPort, backPort, 2),
    ]

    threads = []
    for percent, min_val, max_val, channel in movements:
        if percent is not None and percent != 0:
            target_value = percentage_to_value(percent, min_val, max_val)
            thread = Thread(target=move_servo_gradually_thread, args=(channel, target_value, speed_factor))
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()


def move_arm(port_main=None, port_forearm=None, port_hand=None,
             star_main=None, star_forearm=None, star_hand=None, speed_factor=1.0):
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
            thread = Thread(target=move_servo_gradually_thread, args=(channel, target_value, speed_factor))
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()


def cleanup():
    """Clean up function"""
    disable_all_servos()


if __name__ == "__main__":
    initialize_servos()