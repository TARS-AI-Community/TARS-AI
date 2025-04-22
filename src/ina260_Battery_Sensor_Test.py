import time
from modules.module_battery import BatteryModule

battery = BatteryModule()
battery.start()

while True:
    print(battery.get_battery_status())
    time.sleep(1)
    