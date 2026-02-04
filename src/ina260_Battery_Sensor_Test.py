"""
Module: INA260 Sensor Test
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import time
from collections import deque
import board
import adafruit_ina260

print("Charging Detection Diagnostic (Voltage Level Method)")
print("* Make sure the right settings are set for your battery in the config.ini file. *")
print("=" * 60)
print("Detects charging via voltage elevation above baseline.")
print("\n1. Let it run for 10 sec to establish baseline")
print("2. Plug in charger - watch voltage rise and state change")
print("3. Leave charger connected - should STAY in CHARGING")
print("4. Unplug charger - should go back to DISCHARGING")


i2c = board.I2C()
ina = adafruit_ina260.INA260(i2c, address=0x41)

voltage_history = deque(maxlen=15)
baseline_voltage = None
last_state = "DISCHARGING"

def get_voltage_trend():
    if len(voltage_history) < 3:
        return 0.0
    voltages = list(voltage_history)
    total_change = sum(voltages[i] - voltages[i-1] for i in range(1, len(voltages)))
    return total_change / (len(voltages) - 1)

try:
    while True:
        current = ina.current
        voltage = ina.voltage
        
        voltage_history.append(voltage)
        trend = get_voltage_trend()
        
        if baseline_voltage is None and len(voltage_history) >= 5:
            baseline_voltage = sum(voltage_history) / len(voltage_history)
            print(f">>> Baseline established: {baseline_voltage:.3f}V\n")
        
        elevation = (voltage - baseline_voltage) * 1000 if baseline_voltage else 0
        
        if baseline_voltage:
            if trend > 0.002:
                state = "CHARGING (voltage rising)"
                baseline_voltage = min(baseline_voltage, min(list(voltage_history)[-5:]) - 0.02)
            elif last_state.startswith("CHARGING") and elevation > 10:
                state = "CHARGING (voltage elevated)"
            elif last_state.startswith("CHARGING") and elevation < 5:
                state = "DISCHARGING (charger removed)"
                baseline_voltage = sum(voltage_history) / len(voltage_history)
            elif current > 50:
                state = "DISCHARGING"
                if trend < 0:
                    baseline_voltage = min(baseline_voltage, voltage)
            else:
                state = "IDLE"
        else:
            state = "Establishing baseline..."
        
        last_state = state
        
        baseline_str = f"{baseline_voltage:.3f}V" if baseline_voltage else "---"
        print(f"V: {voltage:.3f} (base: {baseline_str}, +{elevation:+.0f}mV)  |  "
              f"I: {current:+.0f}mA  |  {state}")
        
        time.sleep(0.5)
        
except KeyboardInterrupt:
    print("\n\nDone!")