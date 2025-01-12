from __future__ import division
import time
import Adafruit_PCA9685

try:
    pwm = Adafruit_PCA9685.PCA9685(busnum=1)
except Exception as e:
    print(f"Error initializing PCA9685: {e}")
    exit()

pwm.set_pwm_freq(60)

print("Auto calibrate is in internal testing DO NOT USE / risk it unless you know what your doing!!!!")

MIN_PULSE = 0  # Calibrate these values
MAX_PULSE = 600  # Calibrate these values

def set_servo_pulse(channel, pulse):
    if MIN_PULSE <= pulse <= MAX_PULSE:
        pwm.set_pwm(channel, 0, pulse)
        print(f"Set servo on channel {channel} to pulse {pulse}")
    else:
        print(f"Pulse out of range ({MIN_PULSE}-{MAX_PULSE}).")

def set_all_servos_preset():
    set_servo_pulse(0, 128)  # Example preset pulse for servo 0
    set_servo_pulse(1, 350)  # Example preset pulse for servo 1
    set_servo_pulse(2, 350)  # Example preset pulse for servo 2
    print("All servos set to preset pulse widths.")

def set_single_servo(channel):
    while True:
        try:
            pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break  # Exit the loop after a valid pulse is entered
        except ValueError:
            print("Invalid input. Please enter a number.")

def auto_calibrate_servo(channel, is_center_servo=False):
    """
    Automatically calibrates a servo to find min, max, and neutral PWM values.
    For a center servo, it calculates additional height values.
    """
    print(f"Starting auto-calibration for servo on channel {channel}...")

    # Find minimum PWM value using a curved approach
    print("Finding minimum PWM value...")
    step = 50  # Initial large step
    pwm_value = MAX_PULSE  # Start at the high end
    min_pulse = None
    while step >= 1:
        print(f"Testing PWM: {pwm_value}")
        set_servo_pulse(channel, pwm_value)
        time.sleep(0.5)
        user_input = input("Did the servo start moving? (y/n): ").strip().lower()
        if user_input == "y":
            min_pulse = pwm_value
            pwm_value -= step
        else:
            pwm_value -= step
        step //= 2

    if min_pulse is None:
        print("Failed to find minimum PWM value.")
        return
    print(f"Servo starts moving at PWM: {min_pulse}")

    # Find maximum PWM value
    print("Finding maximum PWM value...")
    step = 50
    pwm_value = min_pulse  # Start from the found minimum value
    max_pulse = None
    while step >= 1:
        print(f"Testing PWM: {pwm_value}")
        set_servo_pulse(channel, pwm_value)
        time.sleep(0.5)
        user_input = input("Did the servo stop moving? (y/n): ").strip().lower()
        if user_input == "n":
            max_pulse = pwm_value
            pwm_value += step
        else:
            max_pulse = pwm_value - step
            pwm_value -= step
        step //= 2

    if max_pulse is None:
        print("Failed to find maximum PWM value.")
        return
    print(f"Servo stops moving at PWM: {max_pulse}")

    # Calculate neutral position
    neutral_pulse = (min_pulse + max_pulse) // 2
    print(f"Setting servo to neutral position: {neutral_pulse}")
    set_servo_pulse(channel, neutral_pulse)

    # Output port/starboard values if not a center servo
    if not is_center_servo:
        neutral_port = neutral_pulse
        neutral_starboard = neutral_pulse
        forward_port = int(neutral_pulse + 0.1 * (max_pulse - neutral_pulse))
        back_starboard = int(neutral_pulse + 0.1 * (neutral_pulse - min_pulse))
        forward_starboard = int(neutral_pulse - 0.1 * (neutral_pulse - min_pulse))
        back_port = int(neutral_pulse - 0.1 * (max_pulse - neutral_pulse))

        print(f"Calibration complete for servo {channel}:")
        print(f"  Back Port: {back_port}")
        print(f"  Neutral Port: {neutral_port}")
        print(f"  Forward Port: {forward_port}")
        print(f"  Back Starboard: {back_starboard}")
        print(f"  Neutral Starboard: {neutral_starboard}")
        print(f"  Forward Starboard: {forward_starboard}")

    else:  # Additional calculations for center servo
        down_height = abs((min_pulse - max_pulse) // 2)
        up_height = min_pulse
        neutral_height = (down_height + up_height) // 2

        print(f"Calibration complete for center servo {channel}:")
        print(f"  Up Height: {up_height}")
        print(f"  Neutral Height: {neutral_height}")
        print(f"  Down Height: {down_height}")

print("Servo Control Menu (Pulse Width)")

while True:
    print("\nSelect an option:")
    print("1. Set all servos to preset pulse widths")
    print("2. Manually set servo 0 pulse width")
    print("3. Manually set servo 1 pulse width")
    print("4. Manually set servo 2 pulse width")
    print("5. Auto-calibrate servo")
    print("6. Exit")

    choice = input("> ")

    if choice == '1':
        set_all_servos_preset()
    elif choice == '2':
        set_single_servo(0)
    elif choice == '3':
        set_single_servo(1)
    elif choice == '4':
        set_single_servo(2)
    elif choice == '5':
        try:
            print("WARNING: This auto-calibration will only work on channel 12 for safety reasons.")
            print("Before continuing, ensure you have a servo connected to channel 12 that is NOT attached or installed to anything!")
            confirmation = input("Type 'confirm' to proceed: ").strip().lower()
            if confirmation == "confirm":
                channel = 12
                print(f"Proceeding with auto-calibration for channel {channel}...")
                auto_calibrate_servo(channel)
            else:
                print("Calibration aborted. Please ensure all safety measures are in place before retrying.")
        except ValueError:
            print("Exiting...")
    elif choice == '6':
        print("Exiting...")
        break
    else:
        print("Invalid choice. Please try again.")
