import sys
import time
import board
import busio
from adafruit_pca9685 import PCA9685

# === Custom Modules ===
from modules.module_config import load_config

config = load_config()

if (config["SERVO"]["MOVEMENT_VERSION"] == "V2"):
    # Import other necessary functions from the V2 module if needed
    # but we'll handle PWM setup here
    try:
        from modules.module_btcontroller_v2 import *
    except ImportError:
        # If the module doesn't have the PWM setup anymore, we can skip it
        pass
else:
    print("\nThis tool can only be used if you are using the V2 MOVEMENT Configurations.")
    print("\n")
    sys.exit()

# Initialize I2C and PCA9685
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50  # Standard servo frequency (50Hz)

global_speed = 1.0  # Adjust this to change movement speed
MIN_PULSE = 0  # Calibrate these values
MAX_PULSE = 600  # Calibrate these values

# Store last known positions of servos
servo_positions = {i: (MIN_PULSE + MAX_PULSE) // 2 for i in range(16)}

def pulse_to_duty_cycle(pulse):
    """
    Convert pulse width value to 16-bit duty cycle.
    Assumes pulse values are mapped to microseconds range.
    For typical servos: 500-2500 microseconds
    """
    # Map your pulse range (0-600) to typical servo range (500-2500 microseconds)
    pulse_us = 500 + (pulse / MAX_PULSE) * 2000
    # Convert microseconds to duty cycle (16-bit value for 50Hz)
    # At 50Hz, period is 20000 microseconds
    duty_cycle = int((pulse_us / 20000.0) * 65535)
    return duty_cycle

def set_servo_pulse(channel, target_pulse):
    """
    Moves the servo gradually to the target pulse width at the global speed rate.
    """
    if MIN_PULSE <= target_pulse <= MAX_PULSE:
        current_pulse = servo_positions.get(channel, (MIN_PULSE + MAX_PULSE) // 2)
        step = 1 if target_pulse > current_pulse else -1

        for pulse in range(current_pulse, target_pulse + step, step):
            duty = pulse_to_duty_cycle(pulse)
            pca.channels[channel].duty_cycle = duty
            time.sleep(0.02 * (1.0 - global_speed))  # Slows down movement when global_speed < 1

        servo_positions[channel] = target_pulse  # Save the new position
        print(f"Set servo on channel {channel} to pulse {target_pulse}")
    else:
        print(f"Pulse out of range ({MIN_PULSE}-{MAX_PULSE}).")

def set_all_servos_preset():
    set_servo_pulse(0, 300)  
    set_servo_pulse(1, 300)  
    set_servo_pulse(2, 300)
    
    set_servo_pulse(3, 135)  # was 200 to 500
    set_servo_pulse(4, 200)  
    set_servo_pulse(5, 200)
    
    set_servo_pulse(6, 440)  
    set_servo_pulse(7, 380)  
    set_servo_pulse(8, 380)
    
    print("All servos set to preset pulse widths.")

def set_single_servo():
    while True:
        try:
            print("#0 -Main Legs - Raise legs up and down")
            print("#1 -Left Leg Rotation")
            print("#2 -Right Leg Rotation")
            print("#3 -Right Leg Main Arm")
            print("#4 -Right Leg Forearm")
            print("#5 -Right Leg Hand")
            print("#6 -Left Leg Main Arm")
            print("#7 -Left Leg Forearm")
            print("#8 -Left Leg Hand")
            channel = int(input(f"Enter servo number: "))
            pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break
        except ValueError:
            break

def control():
    try:
        print("0 - Reset Position.")
        print("1 - Move Forward.")
        print("2 - Move Backward.")
        print("3 - Turn Right.")
        print("4 - Turn Left.")
        print("5 - Greet")
        print("6 - Simulate Laughter")
        print("7 - Dynamic Motion")
        print("8 - PEZZ dispenser")
        print("9 - Now!")
        print("10 - Balance")
        print("11 - Mic Drop")
        print("12 - Defensive Posture")
        print("13 - Pose")
        print("14 - bow")

        main_input = input("> ")
        if main_input.lower() == "0":
            reset_positions()
        if main_input.lower() == "1":
            step_forward()
        if main_input.lower() == "2":
            step_backward()
        if main_input.lower() == "3":
            turn_right()
        if main_input.lower() == "4":
            turn_left()                
        if main_input.lower() == "5":
            right_hi()
        if main_input.lower() == "6":
            laugh()    
        if main_input.lower() == "7":
            swing_legs()         
        if main_input.lower() == "8":
            pezz_dispenser()
        if main_input.lower() == "9":
            now()         
        if main_input.lower() == "10":
            balance()         
        if main_input.lower() == "11":
            mic_drop()                                        
        if main_input.lower() == "12":
            monster()          
        if main_input.lower() == "13":
            pose()
        if main_input.lower() == "14":
            bow()                                   
                
    except ValueError:
        print("Invalid input. Please enter a valid number.")

def motion():
    print("V2 Servo Controller")
    while True:
        print("\nSelect an option:")
        print("1. Set all servos to preset position")
        print("2. Manually set servo and position")
        print("3. Manually set Channel 15 Servo position")
        print("4. Disable all servos")
        print("5. Movements")

        choice = input("> ")

        if choice == '1':
            set_all_servos_preset()
        elif choice == '2':
            set_single_servo()
        elif choice == '3':
            pulse = int(input(f"Enter pulse width for servo on channel 15 ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(15, pulse)
        elif choice == '4':
            # Disable all servos by setting duty cycle to 0
            for ch in range(16):
                time.sleep(0.1)
                pca.channels[ch].duty_cycle = 0
        elif choice == '5':
            control()

if __name__ == "__main__":
    motion()
