import evdev
import time
import TARS_Servo_Abstractor3
import TARS_Servo_Controller3
from evdev import InputDevice, categorize, ecodes
import Adafruit_PCA9685

pwm = Adafruit_PCA9685.PCA9685()

#port
pwm.set_pwm(3, 3, 610)
pwm.set_pwm(4, 4, 570)
pwm.set_pwm(5, 5, 570)
#starboard
pwm.set_pwm(6, 6, 200)
pwm.set_pwm(7, 7, 200)
pwm.set_pwm(8, 8, 240)

# Set frequency to 60hz, good for servos.
pwm.set_pwm_freq(60)

# You may need to edit the below 'event' number depending on your system.
# Suggest you run ls /dev/input before enabling the BlueTooth controller and again after to identify the addition
gamepad = InputDevice('/dev/input/event3')

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

toggle = True
pose = False

print(gamepad)

for event in gamepad.read_loop():
    if event.type == ecodes.EV_KEY:
        if event.value == 1:
            if event.code == lTrg:
                print("Left Trigger")
                if toggle == True:
                    TARS_Servo_Controller3.portMainPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.portMainMinus()
            elif event.code == rTrg:
                print("Right Trigger")
                if toggle == True:
                    TARS_Servo_Controller3.starMainPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.starMainMinus()
            elif event.code == upBtn:
                print("Up - Step Forward")
                TARS_Servo_Abstractor3.stepForward()
            elif event.code == downBtn:
                print("Down")
                if pose == False:
                    TARS_Servo_Abstractor3.pose()
                    pose = True
                elif pose == True:
                    TARS_Servo_Abstractor3.unpose()
                    pose = False
            elif event.code == lBtn:
                print("Left - Turn Left")
                TARS_Servo_Abstractor3.turnLeft()
            elif event.code == rBtn:
                print("Right - Turn Right")
                TARS_Servo_Abstractor3.turnRight()
            elif event.code == xBtn:
                print("X")
                if toggle == True:
                    TARS_Servo_Controller3.starForarmPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.starForarmMinus()
            elif event.code == yBtn:
                print("Y")
                if toggle == True:
                    TARS_Servo_Controller3.portForarmPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.portForarmMinus()
            elif event.code == aBtn:
                print("A")
                if toggle == True:
                    TARS_Servo_Controller3.starHandPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.starHandMinus()
            elif event.code == bBtn:
                print("B")
                if toggle == True:
                    TARS_Servo_Controller3.portHandPlus()
                elif toggle == False:
                    TARS_Servo_Controller3.portHandMinus()
            elif event.code == plusBtn:
                print("+")
                toggle = True
            elif event.code == minusBtn:
                print("-")
                toggle = False
        elif event.value == 0:
            print("Stop")
