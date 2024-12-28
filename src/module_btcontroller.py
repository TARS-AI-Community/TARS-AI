"""
module_btcontroller.py

Provides functionality for managing and interpreting Bluetooth gamepad input 
to control servos and execute specific actions in the GPTARS system.

This module listens to gamepad events such as button presses, joystick movements, 
and D-pad directions, mapping these events to corresponding robotic movements or 
in-app commands. 
"""

import evdev
import time
from datetime import datetime
from module_servoctl import *
from evdev import InputDevice, categorize, ecodes, list_devices
import Adafruit_PCA9685

global posevar

try:
    pwm = Adafruit_PCA9685.PCA9685(busnum=1)  # Specify I2C bus 1
    pwm.set_pwm_freq(60)  # Set frequency to 60 Hz
except FileNotFoundError as e:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: I2C device not found. Ensure that /dev/i2c-1 exists. Details: {e}")
    pwm = None  # Fallback if hardware is unavailable
except Exception as e:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Unexpected error during PCA9685 initialization: {e}")
    pwm = None  # Fallback if hardware is unavailable



# Set initial servo positions
if pwm:
    try:
        # Port
        pwm.set_pwm(3, 3, 610)
        pwm.set_pwm(4, 4, 570)
        pwm.set_pwm(5, 5, 570)
        # Starboard
        pwm.set_pwm(6, 6, 200)
        pwm.set_pwm(7, 7, 200)
        pwm.set_pwm(8, 8, 240)
    except Exception as e:
        print(f"Error setting initial servo positions: {e}")

lTrg = 37
rTrg = 50
upBtn = 46
downBtn = 32
lBtn = 18
rBtn = 33
xBtn = 23
yBtn = 35
aBtn = 36
bBtn = 34
minusBtn = 49
plusBtn = 24

global gamepad_path
toggle = True
posevar = False

SECRET_CODE = [
    "up", "up", "down", "down", "left", "right", "left", "right", "B", "A Button", "Start Button"
]

# Track user input
input_sequence = []

def find_controller(controller_name):
    global gamepad_path
    """
    Search for a controller by its name.
    """
    devices = [InputDevice(path) for path in list_devices()]
    for device in devices:
        if controller_name.lower() in device.name.lower():
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Controller found: {device.name} at {device.path}")
            gamepad_path = device.path
            return device
    print(f"No controller found with name: {controller_name}")
    return None

def check_secret_code(button_name):
    global input_sequence
    input_sequence.append(button_name)

    # Check if the current sequence matches the start of the secret code
    if input_sequence == SECRET_CODE[:len(input_sequence)]:
        # If the sequence matches the full secret code
        if len(input_sequence) == len(SECRET_CODE):
            from module_secrets import play_video_fullscreen
            play_video_fullscreen("secrets/secret.mp4", rotation_angle=90)
            input_sequence = []  # Reset the sequence after the code is entered
    else:
        # If the sequence doesn't match, reset it
        #print(f"Invalid sequence detected: {input_sequence}. Resetting...")
        input_sequence = []

#functions to move
def stepForward():
	module_servoctl.height_neutral_to_up()
	module_servoctl.torso_neutral_to_forwards()
	module_servoctl.torso_bump()
	module_servoctl.torso_return()

def turnRight():
	module_servoctl.neutral_to_down()
	module_servoctl.turn_right()
	module_servoctl.down_to_neutral()
	module_servoctl.neutral_from_right()

def turnLeft():
	module_servoctl.neutral_to_down()
	module_servoctl.turn_left()
	module_servoctl.down_to_neutral()
	module_servoctl.neutral_from_left()

def poseaction():
    module_servoctl.neutral_to_down()
    module_servoctl.torso_neutral_to_backwards()
    module_servoctl.down_to_up()

def unposeaction():
    module_servoctl.torso_return2()  
        
        
# D-Pad Actions (pressed and released)
def action_dpad_up_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Up pressed! Let's move up!")
    stepForward()

def action_dpad_down_pressed():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Down pressed! Let's move down!")
    global posevar
    
    if posevar == False:
        poseaction()
        posevar = True
    elif posevar == True:
        unposeaction()
        posevar = False

def action_dpad_left_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Left pressed! Moving left!")
    turnLeft()

def action_dpad_right_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Right pressed! Moving right!")
    turnRight()

def action_dpad_up_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Up released! Stopping move up.")
    pass

def action_dpad_down_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Down released! Stopping move down.")
    pass

def action_dpad_left_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Left released! Stopping move left.")
    pass

def action_dpad_right_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: D-Pad Right released! Stopping move right.")
    pass

# Joystick Actions (show values when moved)
def action_left_stick_move(x_value, y_value):
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Left Stick moved to X: {x_value}, Y: {y_value}")
    pass

def action_right_stick_move(x_value, y_value):
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Right Stick moved to X: {x_value}, Y: {y_value}")
    pass

# Define custom actions for specific buttons (pressed)
def action_a_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: A Button? Are you trying to jump?")
    global toggle
    if toggle == True:
        module_servoctl.starHandPlus()
    elif toggle == False:
        module_servoctl.starHandMinus()

def action_b_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Oh no, the B! Self-destruct initiated... just kidding!")
    global toggle
    if toggle == True:
        module_servoctl.portHandPlus()
    elif toggle == False:
        module_servoctl.portHandMinus()

def action_x_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Hey, stop pushing my X Button!")
    global toggle
    if toggle == True:
        module_servoctl.starForarmPlus()
    elif toggle == False:
        module_servoctl.starForarmMinus()

def action_y_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Y Button? I hope you know what youre doing!")
    global toggle
    if toggle == True:
        module_servoctl.portForarmPlus()
    elif toggle == False:
        module_servoctl.portForarmMinus()

def action_r1_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: R1 Button pressed! Thats the turbo button!")
    global toggle
    if toggle == True:
        module_servoctl.starMainPlus()
    elif toggle == False:
        module_servoctl.starMainMinus()

def action_l1_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: L1 Button activated! Shields up!")
    global toggle
    if toggle == True:
        module_servoctl.portMainPlus()
    elif toggle == False:
        module_servoctl.portMainMinus()

def action_r2_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: R2 Button? Are we accelerating now?")
    pass

def action_l2_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: L2 Button pressed! Steady... dont crash!")
    pass

def action_bottom_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Bottom Button? What kind of mischief is this?")
    pass

def action_select_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Select Button pressed. Are you opening a menu?")
    pass

def action_start_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Start Button pressed. Game on!")
    pass

def LJoyStick_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: L JoyStick Pressed. HAHAHAHAHA")
    pass

def RJoyStick_button_pressed():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: R JoyStick Pressed. Be Careful!")
    pass

# Define custom actions for specific buttons (released)
def action_a_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Okay, you stopped jumping. Good!")
    pass

def action_b_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: B released. Crisis averted!")
    pass

def action_x_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Thats better. Leave my X Button alone!")
    pass

def action_y_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Y Button released. Thank you for being cautious!")
    pass

def action_r1_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Turbo disengaged. R1 Button safe!")
    pass

def action_l1_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Shields down. L1 Button released!")
    pass

def action_r2_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: R2 Button released. No more speeding!")
    global toggle
    print("+")
    toggle = True

def action_l2_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: L2 Button released. Smooth landing!")
    global toggle
    print("-")
    toggle = False

def action_bottom_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Bottom Button released. Mischief managed!")
    pass

def action_select_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Select Button released. Menu closed!")
    pass

def action_start_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: Start Button released. Lets pause for a moment.")
    pass

def LJoyStick_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: L JoyStick released. That tickled.")
    pass

def RJoyStick_button_released():
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CTRL: R JoyStick released. Whew!.")
    pass

def start_controls():
    """
    Listen to gamepad events and execute actions based on button presses/releases and analog movements.
    """
    # Retry loop for detecting the gamepad
    gamepad = None
    while gamepad is None:
        try:
            # Try to connect to the gamepad
            gamepad = evdev.InputDevice(gamepad_path)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: {gamepad.name} connected.")
        except FileNotFoundError:
            time.sleep(5)  # Wait before retrying

    # Define mappings for button events with actions
    button_map = {
        evdev.ecodes.BTN_SOUTH: ("A Button", action_a_button_pressed, action_a_button_released),
        evdev.ecodes.BTN_EAST: ("B", action_b_button_pressed, action_b_button_released),
        evdev.ecodes.BTN_NORTH: ("X Button", action_x_button_pressed, action_x_button_released),
        evdev.ecodes.BTN_WEST: ("Y Button", action_y_button_pressed, action_y_button_released),
        311: ("R1 Button", action_r1_button_pressed, action_r1_button_released),
        310: ("L1 Button", action_l1_button_pressed, action_l1_button_released),
        313: ("R2 Button", action_r2_button_pressed, action_r2_button_released),
        312: ("L2 Button", action_l2_button_pressed, action_l2_button_released),
        306: ("Bottom Button", action_bottom_button_pressed, action_bottom_button_released),
        314: ("Select Button", action_select_button_pressed, action_select_button_released),
        315: ("Start Button", action_start_button_pressed, action_start_button_released),
        317: ("L JoyStick", LJoyStick_button_pressed, LJoyStick_button_released),
        318: ("R JoyStick", RJoyStick_button_pressed, RJoyStick_button_released),
    }

    # Define mappings for analog events
    analog_map = {
        evdev.ecodes.ABS_HAT0Y: {"up": action_dpad_up_pressed, "down": action_dpad_down_pressed},
        evdev.ecodes.ABS_HAT0X: {"left": action_dpad_left_pressed, "right": action_dpad_right_pressed},
        evdev.ecodes.ABS_X: "Left Stick X",
        evdev.ecodes.ABS_Y: "Left Stick Y",
        evdev.ecodes.ABS_Z: "Right Stick X",
        evdev.ecodes.ABS_RZ: "Right Stick Y",
        9: "Trigger Axis",  # Example label for Unknown Axis 9
    }

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Controls Listening...")
    try:
        dpad_state = {"up": False, "down": False, "left": False, "right": False}
        
        for event in gamepad.read_loop():
            if event.type == evdev.ecodes.EV_KEY:  # Button press/release
                button_info = button_map.get(event.code)
                if button_info:
                    button_name, button_action_pressed, button_action_released = button_info
                    if event.value == 1:  # Button pressed
                        button_action_pressed()  # Call the associated pressed action
                        check_secret_code(button_name)
                    elif event.value == 0:  # Button released
                        button_action_released()  # Call the associated released action
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] MOVE: Unknown Button {event.code}")
            elif event.type == evdev.ecodes.EV_ABS:  # Analog stick or D-pad movement
                #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] MOVE: Event Code: {event.code}, Event Value: {event.value}")

                if event.code == evdev.ecodes.ABS_HAT0Y:
                    if event.value < 0 and not dpad_state["up"]:  # Up pressed
                        action_dpad_up_pressed()
                        check_secret_code("up")
                        dpad_state["up"] = True
                        dpad_state["down"] = False
                    elif event.value > 0 and not dpad_state["down"]:  # Down pressed
                        action_dpad_down_pressed()
                        check_secret_code("down")
                        dpad_state["down"] = True
                        dpad_state["up"] = False
                    elif event.value == 0:  # Released
                        if dpad_state["up"]:
                            action_dpad_up_released()
                        if dpad_state["down"]:
                            action_dpad_down_released()
                        dpad_state["up"] = False
                        dpad_state["down"] = False


                # Handle Left and Right (ABS_HAT0X)
                elif event.code == evdev.ecodes.ABS_HAT0X:
                    if event.value < 0 and not dpad_state["left"]:  # Left pressed
                        action_dpad_left_pressed()
                        check_secret_code("left")
                        dpad_state["left"] = True
                        dpad_state["right"] = False
                    elif event.value > 0 and not dpad_state["right"]:  # Right pressed
                        action_dpad_right_pressed()
                        check_secret_code("right")
                        dpad_state["right"] = True
                        dpad_state["left"] = False
                    elif event.value == 0:  # Released
                        if dpad_state["left"]:
                            action_dpad_left_released()
                        if dpad_state["right"]:
                            action_dpad_right_released()
                        dpad_state["left"] = False
                        dpad_state["right"] = False



                elif event.code == evdev.ecodes.ABS_X:  # Left Stick X Axis
                    action_left_stick_move(event.value, 0)  # Y value isn't used here
                elif event.code == evdev.ecodes.ABS_Y:  # Left Stick Y Axis
                    action_left_stick_move(0, event.value)  # X value isn't used here
                elif event.code == evdev.ecodes.ABS_Z:  # Right Stick X Axis
                    action_right_stick_move(event.value, 0)  # Y value isn't used here
                elif event.code == evdev.ecodes.ABS_RZ:  # Right Stick Y Axis
                    action_right_stick_move(0, event.value)  # X value isn't used here

    except KeyboardInterrupt:
        print("\nExiting...")

    # Clean up
    gamepad.close()

    # Clean up
    gamepad.close()

controller_name = "8BitDo"  # Replace with part of your controller's name
device = find_controller(controller_name)

#Delete this is for testing
if __name__ == "__main__":
    while True:
        try:
            start_controls()
        except Exception as e:
            print(f"An error occurred: {e}")
            # Optionally add a small delay to prevent tight infinite loops in case of failure
            import time
            time.sleep(1)
