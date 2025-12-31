import sys
import time
import board
import busio
from adafruit_pca9685 import PCA9685
from modules.module_btcontroller import *

# === Custom Modules ===
from modules.module_config import load_config

config = load_config()

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
    """Set all servos to their neutral/preset positions"""
    # Height servos (Pins 0-1)
    set_servo_pulse(0, 350)  # Left height servo
    set_servo_pulse(1, 350)  # Right height servo
    
    # Leg servos (Pins 2-3)
    set_servo_pulse(2, 300)  # Left leg
    set_servo_pulse(3, 300)  # Right leg
    
    # Left arm servos (Pins 4-6)
    set_servo_pulse(4, 80)   # Left main arm
    set_servo_pulse(5, 200)  # Left forearm
    set_servo_pulse(6, 200)  # Left hand
    
    # Right arm servos (Pins 7-9)
    set_servo_pulse(7, 580)  # Right main arm
    set_servo_pulse(8, 380)  # Right forearm
    set_servo_pulse(9, 380)  # Right hand
    
    print("All servos set to preset pulse widths.")

def set_single_servo():
    while True:
        try:
            print("\n=== SERVO PIN LAYOUT ===")
            print("Height Servos:")
            print("  #0 - Left Height Servo (raises/lowers left side)")
            print("  #1 - Right Height Servo (raises/lowers right side)")
            print("\nLeg Servos:")
            print("  #2 - Left Leg (forward/back rotation)")
            print("  #3 - Right Leg (forward/back rotation)")
            print("\nLeft Arm Servos:")
            print("  #4 - Left Main Arm")
            print("  #5 - Left Forearm")
            print("  #6 - Left Hand")
            print("\nRight Arm Servos:")
            print("  #7 - Right Main Arm")
            print("  #8 - Right Forearm")
            print("  #9 - Right Hand")
            print("\nOther:")
            print("  #10-15 - Additional servos (if connected)")
            print("========================\n")
            
            channel = int(input(f"Enter servo number (0-15): "))
            if channel < 0 or channel > 15:
                print("Channel must be between 0 and 15")
                continue
                
            pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break
        except ValueError:
            print("Invalid input. Please try again.")
            break

def control():
    try:
        print("\n=== MOVEMENT CONTROLS ===")
        print("0 - Reset Position")
        print("1 - Move Forward")
        print("2 - Move Backward")
        print("3 - Turn Right")
        print("4 - Turn Left")
        print("5 - Greet (Arms)")
        print("6 - Simulate Laughter")
        print("7 - Dynamic Motion")
        print("8 - PEZZ Dispenser (Arms)")
        print("9 - Now! (Arms)")
        print("10 - Balance")
        print("11 - Mic Drop (Arms)")
        print("12 - Defensive Posture (Arms)")
        print("13 - Pose")
        print("14 - Bow")
        print("========================\n")

        main_input = input("> ")
        if main_input.lower() == "0":
            reset_positions()
        elif main_input.lower() == "1":
            step_forward()
        elif main_input.lower() == "2":
            step_backward()
        elif main_input.lower() == "3":
            turn_right()
        elif main_input.lower() == "4":
            turn_left()                
        elif main_input.lower() == "5":
            right_hi()
        elif main_input.lower() == "6":
            laugh()    
        elif main_input.lower() == "7":
            swing_legs()         
        elif main_input.lower() == "8":
            pezz_dispenser()
        elif main_input.lower() == "9":
            now()         
        elif main_input.lower() == "10":
            balance()         
        elif main_input.lower() == "11":
            mic_drop()                                        
        elif main_input.lower() == "12":
            monster()          
        elif main_input.lower() == "13":
            pose()
        elif main_input.lower() == "14":
            bow()
        else:
            print("Invalid selection")
                
    except ValueError:
        print("Invalid input. Please enter a valid number.")

def motion():
    print("\n" + "="*50)
    print("V3 Servo Controller - Dual Height + Left/Right Naming")
    print("="*50)
    
    while True:
        print("\n=== MAIN MENU ===")
        print("1. Set all servos to preset position")
        print("2. Manually set individual servo")
        print("3. Manually set Channel 15 servo")
        print("4. Disable all servos")
        print("5. Movement sequences")
        print("6. Exit")
        print("==================\n")

        choice = input("> ")

        if choice == '1':
            set_all_servos_preset()
        elif choice == '2':
            set_single_servo()
        elif choice == '3':
            pulse = int(input(f"Enter pulse width for servo on channel 15 ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(15, pulse)
        elif choice == '4':
            print("Disabling all servos...")
            # Disable all servos by setting duty cycle to 0
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
                time.sleep(0.05)
            print("All servos disabled.")
        elif choice == '5':
            control()
        elif choice == '6':
            print("Exiting...")
            # Disable all servos before exit
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
            break
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    try:
        motion()
       
    except KeyboardInterrupt:
        print("\nInterrupted by user. Disabling servos...")
        for ch in range(16):
            pca.channels[ch].duty_cycle = 0
        print("Servos disabled. Exiting.")

    



