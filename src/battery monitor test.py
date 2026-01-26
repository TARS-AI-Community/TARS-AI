"""
Quick charging detection diagnostic.
Run this, then plug in your charger and watch what happens.

Since your INA260 only sees load current (charger bypasses it),
we detect charging by:
1. Initial voltage RISE when charger connects
2. Sustained ELEVATED voltage while charging
3. Voltage DROP when charger disconnects
"""

import time
from collections import deque
import board
import adafruit_ina260

print("Charging Detection Diagnostic (Voltage Level Method)")
print("=" * 60)
print("Detects charging via voltage elevation above baseline.")
print("\n1. Let it run for 10 sec to establish baseline")
print("2. Plug in charger - watch voltage rise and state change")
print("3. Leave charger connected - should STAY in CHARGING")
print("4. Unplug charger - should go back to DISCHARGING")
print("\nPress Ctrl+C to stop\n")

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
        
        # Initialize baseline after collecting some data
        if baseline_voltage is None and len(voltage_history) >= 5:
            baseline_voltage = sum(voltage_history) / len(voltage_history)
            print(f">>> Baseline established: {baseline_voltage:.3f}V\n")
        
        # Calculate elevation above baseline
        elevation = (voltage - baseline_voltage) * 1000 if baseline_voltage else 0  # in mV
        
        # Determine state
        if baseline_voltage:
            if trend > 0.002:  # Voltage rising fast
                state = "⚡ CHARGING (voltage rising)"
                # Lower baseline when we detect charging start
                baseline_voltage = min(baseline_voltage, min(list(voltage_history)[-5:]) - 0.02)
            elif last_state.startswith("⚡") and elevation > 10:  # Was charging, still elevated
                state = "⚡ CHARGING (voltage elevated)"
            elif last_state.startswith("⚡") and elevation < 5:  # Was charging, dropped back
                state = "🔋 DISCHARGING (charger removed)"
                baseline_voltage = sum(voltage_history) / len(voltage_history)  # Reset baseline
            elif current > 50:
                state = "🔋 DISCHARGING"
                # Update baseline while discharging
                if trend < 0:
                    baseline_voltage = min(baseline_voltage, voltage)
            else:
                state = "— IDLE"
        else:
            state = "⏳ Establishing baseline..."
        
        last_state = state
        
        # Display
        baseline_str = f"{baseline_voltage:.3f}V" if baseline_voltage else "---"
        print(f"V: {voltage:.3f} (base: {baseline_str}, +{elevation:+.0f}mV)  |  "
              f"I: {current:+.0f}mA  |  {state}")
        
        time.sleep(0.5)
        
except KeyboardInterrupt:
    print("\n\nDone!")