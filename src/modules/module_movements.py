"""
module_movements.py
Atomikspace
V3
"""

import time
import modules.module_servoctl as servoctl

move_legs = servoctl.move_legs
move_arm = servoctl.move_arm
disable_all_servos = servoctl.disable_all_servos
HOLD = servoctl.HOLD

_swap_directions = False

def set_swap_turn_directions(swap: bool):
    """Set whether to swap left/right turn directions"""
    global _swap_directions
    _swap_directions = swap

def get_swap_turn_directions() -> bool:
    """Get current direction swap setting"""
    return _swap_directions


def step_forward():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:

            if not servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.9)
                move_legs(42, 42, 40, 40, 0.9)
                move_legs(70, 70, 23, 23, 0.9)
                move_legs(30, 30, 30, 30, 0.8)
                move_legs(70, 70, 35, 35, 0.9)
                move_legs(60, 60, 50, 50, 0.9)
                move_legs(50, 50, 50, 50, 0.9)
            

            if servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.9)
                move_legs(32, 32, 25, 25, 0.9)
                move_legs(88, 88, 8, 8, 1)
                move_legs(15, 15, 17, 17, 0.9)
                move_legs(75, 75, 24, 24, 0.9)
                move_legs(70, 70, 50, 50, 0.9)
                move_legs(50, 50, 50, 50, 0.9)

            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def walk_forward():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:

            if not servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.8)
                sequence = [
                    (40, 70, 50, 50),
                    (40, 70, 35, 50),
                    (70, 40, 50, 50),
                    (70, 40, 50, 35),
                ]
                for _ in range(2):
                    for a, b, c, d in sequence:
                        move_legs(a, b, c, d, 0.5)
                move_legs(70, 70, 50, 50, 0.6)
                move_legs(50, 50, 50, 50, 0.8) 

            if servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.8)
                sequence = [
                    (50, 95, 50, 50),
                    (40, 95, 25, 50),
                    (95, 50, 50, 50),
                    (95, 40, 50, 25),
                ]
                for _ in range(2):
                    for a, b, c, d in sequence:
                        move_legs(a, b, c, d, 0.9)
                move_legs(95, 95, 50, 50, 0.8)
                move_legs(50, 50, 50, 50, 0.8) 


            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def step_backward():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:

            if not servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.9)
                move_legs(30, 30, 55, 55, 0.8)
                move_legs(68, 68, 82, 82, 0.8)
                move_legs(30, 30, 70, 70, 0.8)
                move_legs(50, 50, 62, 62, 0.9)
                move_legs(65, 65, 50, 50, 0.9)
                move_legs(50, 50, 50, 50, 0.9)

            
            if servoctl.ARMS_PRESENT:
                move_legs(50, 50, 50, 50, 0.9)
                move_legs(22, 22, 50, 50, 0.9)
                move_legs(22, 22, 80, 80, 0.9)
                move_legs(68, 68, 92, 92, 0.9)
                move_legs(15, 15, 83, 83, 0.9)
                move_legs(75, 75, 76, 76, 0.9)
                move_legs(70, 70, 50, 50, 0.9)
                move_legs(50, 50, 50, 50, 0.9)
            
            
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def walk_backward():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:

            if not servoctl.ARMS_PRESENT:
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
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_right_impl():
    """Internal implementation of turn right"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 70, 50, 50, 0.9)
            move_legs(70, 70, 65, 35, 0.9)
            move_legs(45, 45, 65, 35, 0.9)
            move_legs(52, 52, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_right_slow_impl():
    """Internal implementation of turn right slow"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(40, 70, 50, 50, 0.7)
            move_legs(40, 70, 40, 50, 0.7)
            move_legs(70, 50, 40, 50, 0.7)
            move_legs(70, 50, 50, 50, 0.7)
            move_legs(50, 50, 50, 50, 0.9)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_left_impl():
    """Internal implementation of turn left"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 70, 50, 50, 0.9)
            move_legs(70, 70, 35, 65, 0.9)
            move_legs(45, 45, 35, 65, 0.9)
            move_legs(52, 52, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def _turn_left_slow_impl():
    """Internal implementation of turn left slow"""
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(70, 40, 50, 50, 0.7)
            move_legs(70, 40, 50, 40, 0.7)
            move_legs(50, 70, 50, 40, 0.7)
            move_legs(50, 70, 50, 50, 0.7)
            move_legs(50, 50, 50, 50, 0.9)
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def turn_right():
    """Turn right (or left if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_left_impl()
    else:
        _turn_right_impl()


def turn_right_slow():
    """Turn right slowly (or left if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_left_slow_impl()
    else:
        _turn_right_slow_impl()


def turn_left():
    """Turn left (or right if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_right_impl()
    else:
        _turn_left_impl()


def turn_left_slow():
    """Turn left slowly (or right if swap_turn_directions is enabled)"""
    if _swap_directions:
        _turn_right_slow_impl()
    else:
        _turn_left_slow_impl()


def right_hi():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(None, 50, None, 50, 0.8)
            move_legs(None, 80, None, 50, 0.8)
            move_legs(None, 80, None, 80, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 50, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.8)
            move_legs(None, 50, None, 50, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_hi():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, None, 50, None, 0.8)
            move_legs(80, None, 50, None, 0.8)
            move_legs(80, None, 80, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 50, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.8)
            move_legs(50, None, 50, None, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def laugh():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            for _ in range(5):
                move_legs(50, 50, 50, 50, 1)
                time.sleep(0.1)
                move_legs(1, 1, 50, 50, 1)
                time.sleep(0.1)
            move_legs(50, 50, 50, 50, 1)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()

def excited():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            for _ in range(4):
                move_legs(40, 60, 45, 50, 0.95) 
                move_legs(60, 40, 50, 45, 0.95)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def swing_legs():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
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
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def pezz_dispenser():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)            
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(98, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.9)
            time.sleep(2)
            move_arm(100, 100, 1, None, None, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.8)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)            
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.9)
            time.sleep(2)
            move_arm(None, None, None, 100, 100, 1, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def monster():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)
            move_legs(80, 80, 50, 50, 0.5)
            move_legs(80, 80, 65, 65, 0.5)
            time.sleep(0.2)
            move_arm(1, 1, 1, 1, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(100, 1, 1, 100, 1, 1, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, HOLD, 100, 1, 1)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 100, 1)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 50, 50, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 50, 50, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 50, 50, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 50, 50, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 100, 100, HOLD, 100, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 100, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 1, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 100, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 1, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, HOLD, HOLD, 100, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, HOLD, HOLD, 1, 0.8)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, HOLD, 1, HOLD, 0.8)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, 1, HOLD, HOLD, 0.8)
            time.sleep(0.2)
            move_legs(80, 80, 50, 50, 0.5)
            move_legs(50, 50, 50, 50, 0.4)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def pose():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)
            move_legs(30, 30, 40, 40, 0.4)
            move_legs(100, 100, 30, 30, 0.4)
            time.sleep(3)
            move_legs(100, 100, 30, 30, 0.4)
            move_legs(30, 30, 30, 30, 0.4)
            move_legs(30, 30, 40, 40, 0.4)
            move_legs(50, 50, 50, 50, 0.4)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def bow():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.4)
            move_legs(15, 15, 50, 50, 0.7)
            move_legs(15, 15, 70, 70, 0.7)
            move_legs(60, 60, 70, 70, 0.7)
            move_legs(95, 95, 65, 65, 0.7)
            time.sleep(3)
            move_legs(15, 15, 65, 65, 0.7)
            move_legs(50, 50, 50, 50, 0.4)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def tilt_right():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(20, 80, 50, 50, 0.9)
            time.sleep(3)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def tilt_left():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.9)
            move_legs(80, 20, 50, 50, 0.9)
            time.sleep(3)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def side_side():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(10, 90, 50, 50, 0.9)
            move_legs(90, 10, 50, 50, 0.9)
            move_legs(50, 50, 50, 50, 0.9)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def wave_right():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
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
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def wave_left():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
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
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def neutral_legs():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(90, 90, None, None, 0.8)
            move_legs(90, 90, 50, 50, 0.8)
            move_legs(50, 50, 50, 50, 0.8)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_point():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(100, 100, 1, None, None, None, 0.7)
            time.sleep(0.5)
            move_arm(100, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_point():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 1, 0.7)
            time.sleep(0.5)
            move_arm(None, None, None, 100, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_poke():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.15)
            move_arm(HOLD, 70, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 100, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 70, 1, None, None, None, 0.6)
            time.sleep(0.15)
            move_arm(HOLD, 100, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_poke():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 70, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 100, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 70, 1, 0.6)
            time.sleep(0.15)
            move_arm(None, None, None, HOLD, 100, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_wave_open():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 70, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 100, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 70, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, 100, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_wave_open():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 100, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 70, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 70, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def left_shy_wave():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(80, None, 50, None, 0.9)
            move_legs(80, None, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(1, 1, 1, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(100, 1, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 100, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 100, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(90, 70, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(90, 70, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(92, 50, 40, None, None, None, 0.6)
            move_legs(70, 90, 80, None, 0.9)
            time.sleep(0.2)
            move_arm(100, 100, 100, None, None, None, 0.6)
            move_legs(80, 50, 80, 50, 0.9)
            time.sleep(0.2)
            move_arm(HOLD, HOLD, 1, None, None, None, 0.7)
            time.sleep(0.2)
            move_arm(HOLD, 1, HOLD, None, None, None, 0.6)
            time.sleep(0.2)
            move_arm(1, HOLD, HOLD, None, None, None, 0.5)
            time.sleep(0.2)
            move_legs(80, None, 50, None, 0.9)
            move_legs(50, None, 50, None, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def right_shy_wave():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 1, 1, 1, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 1, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 100, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 100, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(70, 90, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(70, 90, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 92, 50, 40, 0.6)
            move_legs(90, 70, None, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, 100, 100, 100, 0.6)
            move_legs(50, 80, 50, 80, 0.9)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, HOLD, 1, 0.7)
            time.sleep(0.2)
            move_arm(None, None, None, HOLD, 1, HOLD, 0.6)
            time.sleep(0.2)
            move_arm(None, None, None, 1, HOLD, HOLD, 0.5)
            time.sleep(0.2)
            move_legs(None, 80, None, 50, 0.9)
            move_legs(None, 50, None, 50, 0.9)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def happy_dance():
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._notify_movement_start()
        try:
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(None, None, 45, 55, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 55, 45, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 45, 55, 0.9)
            time.sleep(0.1)
            move_legs(None, None, 50, 50, 0.9)
            move_legs(20, 80, None, None, 0.9)
            time.sleep(0.1)
            move_legs(80, 20, None, None, 0.9)
            time.sleep(0.1)
            move_legs(20, 80, None, None, 0.9)
            time.sleep(0.1)
            move_legs(50, 50, None, None, 0.9)
            move_legs(None, 80, None, 80, 0.9)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.8)
            time.sleep(0.2)
            move_legs(40, 70, None, None, 0.95)
            time.sleep(0.1)
            move_legs(60, 80, None, None, 0.95)
            time.sleep(0.1)
            move_legs(40, 70, None, None, 0.95)
            time.sleep(0.1)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.8)
            move_legs(80, None, 80, None, 0.9)
            move_arm(85, HOLD, None, None, HOLD, None, 0.8)
            time.sleep(0.15)
            move_legs(80, 80, 70, 70, 0.9)
            move_arm(85, HOLD, None, 85, HOLD, None, 0.7)
            time.sleep(0.25)
            move_legs(20, 90, None, None, 0.9)
            time.sleep(0.12)
            move_legs(90, 20, None, None, 0.9)
            time.sleep(0.12)
            move_legs(20, 90, None, None, 0.9)
            time.sleep(0.12)
            move_legs(80, 80, None, None, 0.9)
            move_arm(1, HOLD, None, 1, HOLD, None, 0.7)
            move_legs(None, None, 50, 50, 0.9)
            time.sleep(0.1)
            move_legs(50, 50, None, None, 0.8)
            time.sleep(0.1)
            move_legs(30, 30, None, None, 0.95)
            time.sleep(0.08)
            move_legs(65, 65, None, None, 0.95)
            time.sleep(0.08)
            move_legs(30, 30, None, None, 0.95)
            time.sleep(0.08)
            move_legs(50, 50, None, None, 0.9)
            time.sleep(0.1)
            move_legs(None, 80, None, 80, 0.95)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.9)
            time.sleep(0.1)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.9)
            move_legs(80, None, 80, None, 0.95)
            move_arm(85, HOLD, None, None, HOLD, None, 0.9)
            time.sleep(0.1)
            move_arm(1, HOLD, None, None, HOLD, None, 0.9)
            move_legs(None, 80, None, 80, 0.95)
            move_arm(None, HOLD, None, 85, HOLD, None, 0.9)
            time.sleep(0.1)
            time.sleep(0.3)
            move_arm(None, HOLD, None, 1, HOLD, None, 0.7)
            move_legs(None, None, 50, 50, 0.9)
            move_legs(50, 50, None, None, 0.8)
            time.sleep(0.2)
            disable_all_servos()
        finally:
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def ventilate_on():
    """
    Position tars for better airflow
    """
    if not servoctl.MOVING:
        servoctl.MOVING = True
        servoctl._is_ventilate_operation = True
        
        servoctl._notify_movement_start()
        try:
            from modules.module_cputemp import set_ventilating
            
            move_legs(50, 50, 50, 50, 0.8)
            move_legs(25, 25, 50, 50, 0.75)
            move_legs(25, 25, 42, 42, 0.75)
            move_legs(55, 55, 30, 30, 0.75)

            set_ventilating(True)
            
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl._is_ventilate_operation = False
            servoctl.MOVING = False
            servoctl._notify_movement_end()


def ventilate_off():
    from modules.module_cputemp import is_ventilating, set_ventilating
    
    if is_ventilating():
        was_moving = servoctl.MOVING

        servoctl.MOVING = True
        servoctl._is_ventilate_operation = True
        
        if not was_moving:
            servoctl._notify_movement_start()
        
        try:
            move_legs(55, 55, 30, 30, 0.75)
            move_legs(25, 25, 30, 30, 0.75)
            move_legs(25, 25, 50, 50, 0.75)
            move_legs(50, 50, 50, 50, 0.75)
            
            set_ventilating(False)
            
            time.sleep(0.1)
            disable_all_servos()
        finally:
            servoctl._is_ventilate_operation = False
            servoctl.MOVING = was_moving
            if not was_moving:
                servoctl._notify_movement_end()