from __future__ import division
import time
import Adafruit_PCA9685

# Initialize the PCA9685 using the default address (0x40).
pwm = Adafruit_PCA9685.PCA9685(busnum=1)

# Set frequency to 60 Hz, good for servos.20
pwm.set_pwm_freq(60)

print("Servo Position Tester")
print("Type a value between 88 and 600 to set the servo position. (256 is center)")
print("The center servo max throw is 88 to 256 (168* of throw max!) or 90* total ")
print("Type 'exit' to quit.")

# Function to set the servo to a specific position
def set_servo_position(channel, position):
    if 0 <= position <= 600:  # Ensure the value is within the valid range
        pwm.set_pwm(channel, 2, position)
        print(f"Set servo on channel {channel} to position {position}")
    else:
        print("Position out of range. Enter a value between 0 and 600.")

# Main loop for input
try:
    while True:
        user_input = input("Enter position for center servo (channel 0): ")
        if user_input.lower() == 'exit':
            print("Exiting...")
            break
        try:
            position = int(user_input)
            set_servo_position(2, position)  # Channel 0 is for the center servo
        except ValueError:
            print("Invalid input. Please enter a number or 'exit'.")
except KeyboardInterrupt:
    print("\nExiting...")
