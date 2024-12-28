import time
import TARS_Servo_Controller3

def stepForward():
	TARS_Servo_Controller3.height_neutral_to_up()
	TARS_Servo_Controller3.torso_neutral_to_forwards()
	TARS_Servo_Controller3.torso_bump()
	TARS_Servo_Controller3.torso_return()

def turnRight():
	TARS_Servo_Controller3.neutral_to_down()
	TARS_Servo_Controller3.turn_right()
	TARS_Servo_Controller3.down_to_neutral()
	TARS_Servo_Controller3.neutral_from_right()

def turnLeft():
	TARS_Servo_Controller3.neutral_to_down()
	TARS_Servo_Controller3.turn_left()
	TARS_Servo_Controller3.down_to_neutral()
	TARS_Servo_Controller3.neutral_from_left()

def pose():
    TARS_Servo_Controller3.neutral_to_down()
    TARS_Servo_Controller3.torso_neutral_to_backwards()
    TARS_Servo_Controller3.down_to_up()

def unpose():
    TARS_Servo_Controller3.torso_return2()

    