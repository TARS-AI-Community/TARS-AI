import sys
import time
import board
import busio
from adafruit_pca9685 import PCA9685
import os
import importlib

# === Custom Modules ===
from modules.module_config import load_config
import modules.module_servoctl as servoctl
from modules.module_servoctl import *

# Make config global so it can be reloaded when testing offsets
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

# Load offset values from config
servo_config = config.get('SERVO', {})
offset_values = {
    'perfectLeftHeightOffset': int(servo_config.get('perfectLeftHeightOffset', 0)),
    'perfectRightHeightOffset': int(servo_config.get('perfectRightHeightOffset', 0)),
    'perfectLeftLegOffset': int(servo_config.get('perfectLeftLegOffset', 0)),
    'perfectRightLegOffset': int(servo_config.get('perfectRightLegOffset', 0))
}

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
        # Removed verbose output
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
    
    print("✓ Preset applied - Servo will remain under power until you stop them. (Option 2)")

def save_offset_to_config(offset_name, value):
    """Save the updated offset value to the config.ini file without removing comments"""
    # Try to find config.ini in common locations
    possible_paths = [
        'config.ini',
        '../config.ini',
        os.path.join(os.path.dirname(__file__), 'config.ini'),
        os.path.join(os.path.dirname(__file__), '..', 'config.ini')
    ]
    
    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break
    
    if config_path is None:
        print(f"Error: Config file not found. Searched: {possible_paths}")
        return False
    
    # Read the entire file
    with open(config_path, 'r') as f:
        lines = f.readlines()
    
    # Find and update only the specific offset line
    in_servo_section = False
    updated = False
    
    for i, line in enumerate(lines):
        # Check if we're in the [SERVO] section
        if line.strip().startswith('[SERVO]'):
            in_servo_section = True
            continue
        
        # Check if we've left the [SERVO] section
        if in_servo_section and line.strip().startswith('['):
            in_servo_section = False
        
        # If we're in [SERVO] section and found our offset line
        if in_servo_section and line.strip().startswith(offset_name):
            # Update this line, preserving any inline comment
            if '#' in line:
                # Preserve the comment
                comment_part = '#' + line.split('#', 1)[1]
                lines[i] = f"{offset_name} = {value}  {comment_part}"
            else:
                lines[i] = f"{offset_name} = {value}\n"
            updated = True
            break
    
    # If the offset wasn't found, add it to the [SERVO] section
    if not updated:
        for i, line in enumerate(lines):
            if line.strip().startswith('[SERVO]'):
                # Find the end of the [SERVO] section
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('['):
                    j += 1
                # Insert the new offset before the next section
                lines.insert(j, f"{offset_name} = {value}\n")
                break
    
    # Write back the file
    with open(config_path, 'w') as f:
        f.writelines(lines)
    
    return True

def reload_and_test():
    """Reload servoctl module and test with reset_positions()"""
    try:
        global config
        config = load_config()
        importlib.reload(servoctl)
        # Re-import all functions from the reloaded module
        globals().update({name: getattr(servoctl, name) for name in dir(servoctl) if not name.startswith('_')})
        # Test with reset position
        reset_positions()
    except Exception as e:
        print(f"⚠ Error during reload/test: {e}")

def adjust_offsets():
    """Interactive menu to adjust servo offset values"""
    global offset_values
    
    while True:
        print("\n" + "="*60)
        print("SERVO OFFSET ADJUSTMENT")
        print("="*60)
        print("\nℹ️  Each adjustment auto-saves & tests with reset position")
        print("\nCurrent Offset Values:")
        print(f"  1. Left Height Offset:  {offset_values['perfectLeftHeightOffset']:+4d}")
        print(f"  2. Right Height Offset: {offset_values['perfectRightHeightOffset']:+4d}")
        print(f"  3. Left Leg Offset:     {offset_values['perfectLeftLegOffset']:+4d}")
        print(f"  4. Right Leg Offset:    {offset_values['perfectRightLegOffset']:+4d}")
        print("\n  5. Return to main menu")
        print("="*60)
        
        choice = input("\nSelect offset to adjust (1-5): ").strip()
        
        if choice == '5':
            # Final reload to ensure everything is up to date
            print("\nFinalizing...")
            try:
                global config
                config = load_config()
                importlib.reload(servoctl)
                globals().update({name: getattr(servoctl, name) for name in dir(servoctl) if not name.startswith('_')})
                print("✓ Ready")
            except Exception as e:
                print(f"⚠ Reload error: {e}")
            break
            
        elif choice in ['1', '2', '3', '4']:
            offset_map = {
                '1': ('perfectLeftHeightOffset', 'Left Height', 0),
                '2': ('perfectRightHeightOffset', 'Right Height', 1),
                '3': ('perfectLeftLegOffset', 'Left Leg', 2),
                '4': ('perfectRightLegOffset', 'Right Leg', 3)
            }
            
            offset_name, servo_name, channel = offset_map[choice]
            current_value = offset_values[offset_name]
            
            print(f"\n--- Adjusting {servo_name} Offset ---")
            print(f"Current value: {current_value:+d}")
            
            # Show what position this offset produces
            if channel in [0, 1]:  # Height servos
                base_pulse = 350
            else:  # Leg servos
                base_pulse = 300
            
            print(f"Base pulse: {base_pulse}, Current target: {base_pulse} {current_value:+d} = {base_pulse + current_value}")
            
            print("\nCommands:")
            print("  +   = Increase by 5")
            print("  -   = Decrease by 5")
            print("  ++  = Increase by 1")
            print("  --  = Decrease by 1")
            print("  num = Set to value")
            print("  q   = Done")
            print("\n(Each change saves & tests with reset position)")
            
            while True:
                # Calculate and display the target position
                target_position = base_pulse + offset_values[offset_name]
                offset_str = f"{offset_values[offset_name]:+d}"  # This includes the sign
                print(f"\n{servo_name} Offset: {offset_values[offset_name]:+4d}  (Target: {base_pulse}{offset_str}={target_position})", end="  ")
                cmd = input("> ").strip().lower()
                
                if cmd == 'q':
                    break
                elif cmd == '+':
                    offset_values[offset_name] += 5
                    save_offset_to_config(offset_name, offset_values[offset_name])
                    reload_and_test()
                elif cmd == '-':
                    offset_values[offset_name] -= 5
                    save_offset_to_config(offset_name, offset_values[offset_name])
                    reload_and_test()
                elif cmd == '++':
                    offset_values[offset_name] += 1
                    save_offset_to_config(offset_name, offset_values[offset_name])
                    reload_and_test()
                elif cmd == '--':
                    offset_values[offset_name] -= 1
                    save_offset_to_config(offset_name, offset_values[offset_name])
                    reload_and_test()
                else:
                    try:
                        new_value = int(cmd)
                        offset_values[offset_name] = new_value
                        save_offset_to_config(offset_name, offset_values[offset_name])
                        reload_and_test()
                    except ValueError:
                        print("Invalid command. Use +, -, ++, --, q, or a number.")
        else:
            print("Invalid selection. Please choose 1-5.")

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
        print("15 - Walk Forward")
        print("16 - Walk Backward")
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
        elif main_input.lower() == "15":
            walk_forward()
        elif main_input.lower() == "16":
            walk_backward()
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
        print("2. Disable Power to all servos")
        print("3. Manually set individual servo")
        print("4. Manually set Channel 15 servo")
        print("5. Adjust servo offsets")
        print("6. Movement sequences")
        print("7. Exit")
        print("==================\n")

        choice = input("> ")

        if choice == '1':
            set_all_servos_preset()
        elif choice == '2':
             # Disable all servos by setting duty cycle to 0
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
                time.sleep(0.05)
            print("✓ Servo are not under power anymore.")
        elif choice == '3':
            set_single_servo()
        elif choice == '4':
            pulse = int(input(f"Enter pulse width for servo on channel 15 ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(15, pulse)
        elif choice == '5':
            adjust_offsets()
        elif choice == '6':
            control()
        elif choice == '7':
            # Disable all servos before exit
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
            print("✓ Exiting")
            break
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    try:
        motion()
       
    except KeyboardInterrupt:
        for ch in range(16):
            pca.channels[ch].duty_cycle = 0
        print("\n✓ Servos disabled. Exiting.")

