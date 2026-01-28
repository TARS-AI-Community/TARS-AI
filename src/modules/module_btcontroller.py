"""
Module: BT Controller
Author: Charles-Olivier Dion (Atomikspace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026

This module was originally redesigned by Charles-Olivier Dion (Atomikspace).

Permission is granted to use, copy, modify, and redistribute this module,
in whole or in part, provided that:

- This notice is retained in the source file(s)
- The original author (Charles-Olivier Dion / Atomikspace) is clearly credited
- Any modifications are clearly identified as such

This notice applies only to this module and does not extend to the
entire project or repository in which it may be included.
"""


import evdev
import time
from evdev import InputDevice, list_devices

from modules.module_config import load_config
from modules.module_messageQue import queue_message
from modules.module_movement_registry import MOVEMENTS, get_legs_only, get_has_arms
import modules.module_movements as movements

config = load_config()
controller_name = config["CONTROLS"]["controller_name"]
gamepad_path = None

l2_held = False
r1_held = False
r2_held = False

dpad_state = {"y": 0, "x": 0}
last_dpad_time = 0
DEBOUNCE_TIME = 0.1

controller_search_notified = False

def get_movement(name):
    return getattr(movements, name, None)

def find_controller(controller_name):
    global gamepad_path, controller_search_notified
    devices = [InputDevice(path) for path in list_devices()]
    matching_devices = []
    for device in devices:
        if controller_name.lower() in device.name.lower():
            matching_devices.append(device)
    if matching_devices:
        queue_message(f"LOAD: Found {len(matching_devices)} matching device(s):")
        for device in matching_devices:
            caps = device.capabilities(verbose=True)
            has_buttons = ('EV_KEY', evdev.ecodes.EV_KEY) in caps
            queue_message(f"      - {device.name} at {device.path} (buttons: {has_buttons})")
        excluded_keywords = ["imu", "motion", "sensor"]
        for device in matching_devices:
            if any(keyword in device.name.lower() for keyword in excluded_keywords):
                continue
            caps = device.capabilities(verbose=True)
            if ('EV_KEY', evdev.ecodes.EV_KEY) in caps:
                queue_message(f"LOAD: Using: {device.name} at {device.path}")
                gamepad_path = device.path
                controller_search_notified = False
                return device
        queue_message("LOAD: No suitable controller found (no device with button support)")
        return None
    if not controller_search_notified:
        queue_message(f"LOAD: {controller_name} not found, waiting for connection...")
        controller_search_notified = True
    return None

def execute_movement(name):
    func = get_movement(name)
    if func:
        queue_message(f"CTRL: {MOVEMENTS[name]['name']}")
        func()

def start_controls():
    global gamepad_path, l2_held, r1_held, r2_held, dpad_state, last_dpad_time
    
    DEADZONE = 16000
    
    while gamepad_path is None:
        find_controller(controller_name)
        if gamepad_path is None:
            time.sleep(5)
    
    gamepad = None
    while gamepad is None:
        try:
            gamepad = evdev.InputDevice(gamepad_path)
            queue_message(f"LOAD: {gamepad.name} connected")
        except FileNotFoundError:
            gamepad_path = None
            time.sleep(5)
            return

    queue_message("LOAD: Controls listening...")
    try:
        for event in gamepad.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                if event.value < -DEADZONE or event.value > DEADZONE:
                    pass
                    #queue_message(f"DEBUG ABS: code={event.code} value={event.value}")
            
            if event.type == evdev.ecodes.EV_KEY:
                #queue_message(f"DEBUG KEY: code={event.code} value={event.value}")
                
                if event.code == 312:
                    l2_held = (event.value == 1)
                elif event.code == 311:
                    r1_held = (event.value == 1)
                elif event.code == 313:
                    r2_held = (event.value == 1)
                
                if event.value == 1:
                    if event.code == evdev.ecodes.BTN_SOUTH:
                        if r2_held:
                            execute_movement("right_hi")
                        elif r1_held:
                            execute_movement("wave_right")
                        else:
                            execute_movement("pose")
                    
                    elif event.code == evdev.ecodes.BTN_EAST:
                        if r2_held:
                            execute_movement("side_side")
                        elif r1_held:
                            execute_movement("wave_left")
                        else:
                            execute_movement("bow")
                    
                    elif event.code == evdev.ecodes.BTN_NORTH:
                        if r2_held:
                            execute_movement("monster")
                        elif r1_held:
                            execute_movement("tilt_right")
                        else:
                            execute_movement("laugh")
                    
                    elif event.code == evdev.ecodes.BTN_WEST:
                        if r2_held:
                            execute_movement("pezz_dispenser")
                        elif r1_held:
                            execute_movement("tilt_left")
                        else:
                            execute_movement("excited")

            elif event.type == evdev.ecodes.EV_ABS:
                current_time = time.time()
                
                if event.code in [evdev.ecodes.ABS_HAT0Y, evdev.ecodes.ABS_HAT0X]:
                    new_state = event.value
                else:
                    if event.value < -DEADZONE:
                        new_state = -1
                    elif event.value > DEADZONE:
                        new_state = 1
                    else:
                        new_state = 0
                
                if event.code in [evdev.ecodes.ABS_HAT0Y, evdev.ecodes.ABS_Y]:
                    if new_state != dpad_state["y"]:
                        dpad_state["y"] = new_state
                        last_dpad_time = current_time
                        #queue_message(f"DEBUG: Y state changed to {new_state}")
                        
                        if new_state < 0:
                            if l2_held:
                                execute_movement("step_forward")
                            else:
                                execute_movement("walk_forward")
                        elif new_state > 0:
                            if l2_held:
                                execute_movement("step_backward")
                            else:
                                execute_movement("walk_backward")
                
                elif event.code in [evdev.ecodes.ABS_HAT0X, evdev.ecodes.ABS_X]:
                    if dpad_state["y"] != 0:
                        continue
                    if (current_time - last_dpad_time) < DEBOUNCE_TIME:
                        continue
                    if new_state != dpad_state["x"]:
                        dpad_state["x"] = new_state
                        last_dpad_time = current_time
                        #queue_message(f"DEBUG: X state changed to {new_state}")
                        
                        if new_state < 0:
                            if l2_held:
                                execute_movement("turn_left")
                            else:
                                execute_movement("turn_left_slow")
                        elif new_state > 0:
                            if l2_held:
                                execute_movement("turn_right")
                            else:
                                execute_movement("turn_right_slow")

    except (OSError, IOError) as e:
        queue_message(f"Controller disconnected: {e}")
        gamepad_path = None
    except KeyboardInterrupt:
        pass
    finally:
        gamepad.close()

find_controller(controller_name)

if __name__ == "__main__":
    while True:
        try:
            start_controls()
        except Exception as e:
            queue_message(f"ERROR: {e}")
            time.sleep(1)