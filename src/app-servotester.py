from __future__ import division
import time
import Adafruit_PCA9685

try:
    pwm = Adafruit_PCA9685.PCA9685(busnum=1)
except Exception as e:
    print(f"Error initializing PCA9685: {e}")
    exit()

pwm.set_pwm_freq(60)

MIN_PULSE = 150  # Calibrate these values
MAX_PULSE = 600  # Calibrate these values

def set_servo_pulse(channel, pulse):
    if MIN_PULSE <= pulse <= MAX_PULSE:
        pwm.set_pwm(channel, 0, pulse)
        print(f"Set servo on channel {channel} to pulse {pulse}")
    else:
        print(f"Pulse out of range ({MIN_PULSE}-{MAX_PULSE}).")

def set_all_servos_preset():
    set_servo_pulse(0, 250)  # Example preset pulse for servo 0
    set_servo_pulse(1, 400)  # Example preset pulse for servo 1
    set_servo_pulse(2, 400)  # Example preset pulse for servo 2
    print("All servos set to preset pulse widths.")

def set_single_servo(channel):
    while True:
        try:
            pulse = int(input(f"Enter pulse width for servo {channel} ({MIN_PULSE}-{MAX_PULSE}): "))
            set_servo_pulse(channel, pulse)
            break  # Exit the loop after a valid pulse is entered
        except ValueError:
            print("Invalid input. Please enter a number.")

print("Servo Control Menu (Pulse Width)")

while True:
    print("\nSelect an option:")
    print("1. Set all servos to preset pulse widths")
    print("2. Manually set servo 0 pulse width")
    print("3. Manually set servo 1 pulse width")
    print("4. Manually set servo 2 pulse width")
    print("5. Exit")

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
        print("Exiting...")
        break
    else:
        print("Invalid choice. Please try again.")