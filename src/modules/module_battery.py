"""
BATTERY MONITOR - V3
==========================
Enhanced battery monitoring module for INA260-based systems.

Key improvements over V2:
- Fixed charging detection with configurable current direction
- Added thread safety for shared variables
- Added hysteresis to prevent state flickering
- Improved battery percentage calculation with optional voltage curve support
- Better error handling and logging
- Added discharge rate estimation
"""

import time
import threading
import logging
from collections import deque
from typing import Optional, Dict, Any
from enum import Enum

import board
import adafruit_ina260

from modules.module_config import load_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONFIG = load_config()


class ChargingState(Enum):
    """Enum for battery charging states."""
    UNKNOWN = "unknown"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    FULL = "full"
    IDLE = "idle"  # Neither charging nor significant discharge


class BatteryModule:
    """
    Battery monitoring module using INA260 current/voltage/power sensor.
    
    Provides real-time battery status monitoring including:
    - Voltage, current, and power readings
    - Battery percentage with smoothing
    - Charging state detection
    - Auto-shutdown on critical battery level
    - Discharge rate estimation
    """
    
    # Default Li-ion voltage curve (voltage -> percentage)
    # These are typical values for a 1S Li-ion cell (3.0V - 4.2V)
    # Adjust these values based on your specific battery chemistry
    DEFAULT_VOLTAGE_CURVE = {
        4.20: 100,
        4.15: 95,
        4.10: 90,
        4.05: 85,
        4.00: 80,
        3.95: 75,
        3.90: 70,
        3.85: 65,
        3.80: 60,
        3.75: 55,
        3.70: 50,
        3.65: 45,
        3.60: 40,
        3.55: 35,
        3.50: 30,
        3.45: 25,
        3.40: 20,
        3.35: 15,
        3.30: 10,
        3.20: 5,
        3.00: 0,
    }

    def __init__(
        self,
        battery_capacity_mAh: float = CONFIG['BATTERY']['battery_capacity_mAh'],
        battery_initial_voltage: float = CONFIG['BATTERY']['battery_initial_voltage'],
        battery_cutoff_voltage: float = CONFIG['BATTERY']['battery_cutoff_voltage'],
        auto_shutdown: bool = CONFIG['BATTERY']['auto_shutdown'],
        smoothing_window: int = 5,
        i2c_address: int = 0x41,
        # Charging detection parameters
        charging_current_threshold_mA: float = 50.0,
        charging_current_negative: bool = True,  # Set based on your wiring
        use_voltage_curve: bool = False,  # Use non-linear voltage curve
        voltage_curve: Optional[Dict[float, float]] = None,
        # Hysteresis settings
        charging_hysteresis_mA: float = 20.0,
        shutdown_delay_seconds: int = 60,
    ):
        """
        Initialize the Battery Module with battery parameters.
        
        Args:
            battery_capacity_mAh: Total battery capacity in mAh
            battery_initial_voltage: Voltage when battery is fully charged
            battery_cutoff_voltage: Voltage at which battery is considered empty
            auto_shutdown: Whether to auto-shutdown on critical battery
            smoothing_window: Number of readings to average for smoothing
            i2c_address: I2C address of the INA260 sensor
            charging_current_threshold_mA: Minimum current to consider as charging
            charging_current_negative: If True, negative current = charging
                                       If False, positive current = charging
                                       (depends on your INA260 wiring)
            use_voltage_curve: Use non-linear voltage-to-percentage curve
            voltage_curve: Custom voltage curve dict (voltage -> percentage)
            charging_hysteresis_mA: Hysteresis band to prevent state flickering
            shutdown_delay_seconds: Seconds at 0% before initiating shutdown
        """
        # Battery parameters
        self.battery_capacity_mAh = battery_capacity_mAh
        self.battery_initial_voltage = battery_initial_voltage
        self.battery_cutoff_voltage = battery_cutoff_voltage
        self.auto_shutdown = auto_shutdown
        self.shutdown_delay_seconds = shutdown_delay_seconds
        
        # Smoothing parameters
        self.smoothing_window = smoothing_window
        self.percentage_history: deque = deque(maxlen=smoothing_window)
        self.voltage_history: deque = deque(maxlen=smoothing_window)
        self.current_history: deque = deque(maxlen=smoothing_window)
        # Longer window for discharge rate to stabilize time remaining estimate
        self.discharge_rate_history: deque = deque(maxlen=30)
        
        # Charging detection parameters
        self.charging_current_threshold_mA = charging_current_threshold_mA
        self.charging_current_negative = charging_current_negative
        self.charging_hysteresis_mA = charging_hysteresis_mA
        
        # Voltage curve for non-linear percentage calculation
        self.use_voltage_curve = use_voltage_curve
        self.voltage_curve = voltage_curve or self.DEFAULT_VOLTAGE_CURVE
        
        # Thread safety lock
        self._lock = threading.Lock()
        
        # Current readings (protected by lock)
        self._current: float = 0.0  # mA
        self._voltage: float = 0.0  # V
        self._power: float = 0.0    # mW
        self._battery_percentage: float = 0.0
        self._normalized_percentage: int = 0
        self._charging_state: ChargingState = ChargingState.UNKNOWN
        self._last_charging_state: ChargingState = ChargingState.UNKNOWN
        
        # Monitoring state
        self.is_running: bool = False
        self.thread: Optional[threading.Thread] = None
        self._last_printed_percentage: Optional[float] = None
        self._zero_percent_start_time: Optional[float] = None
        self._last_reading_time: Optional[float] = None
        
        # Discharge rate tracking
        self._discharge_rate_mA: float = 0.0
        self._estimated_time_remaining_min: Optional[float] = None
        
        # Initialize sensor
        self.sensor_initialized: bool = False
        self._init_sensor(i2c_address)

    def _init_sensor(self, i2c_address: int) -> None:
        """Initialize the INA260 sensor."""
        try:
            self.i2c = board.I2C()
            self.ina260 = adafruit_ina260.INA260(self.i2c, address=i2c_address)
            
            # Configure averaging for more stable readings
            # Lower = faster response, Higher = more stable
            # Options: COUNT_1, COUNT_4, COUNT_16, COUNT_64, COUNT_128, COUNT_256, COUNT_512, COUNT_1024
            self.ina260.averaging_count = adafruit_ina260.AveragingCount.COUNT_4
            
            self.sensor_initialized = True
            logger.info(f"INA260 sensor initialized at address 0x{i2c_address:02X}")
            
        except Exception as e:
            logger.error(f"Battery sensor initialization error: {e}")
            self.sensor_initialized = False

    # Thread-safe property accessors
    @property
    def current(self) -> float:
        """Current in mA (thread-safe)."""
        with self._lock:
            return self._current

    @property
    def voltage(self) -> float:
        """Voltage in V (thread-safe)."""
        with self._lock:
            return self._voltage

    @property
    def power(self) -> float:
        """Power in mW (thread-safe)."""
        with self._lock:
            return self._power

    @property
    def battery_percentage(self) -> float:
        """Raw battery percentage (thread-safe)."""
        with self._lock:
            return self._battery_percentage

    @property
    def normalized_percentage(self) -> int:
        """Smoothed battery percentage (thread-safe)."""
        with self._lock:
            return self._normalized_percentage

    @property
    def charging_state(self) -> ChargingState:
        """Current charging state (thread-safe)."""
        with self._lock:
            return self._charging_state

    def calculate_battery_percentage(self, current_voltage: float) -> float:
        """
        Calculate battery percentage from voltage.
        
        Uses either linear interpolation or voltage curve lookup depending
        on the use_voltage_curve setting.
        
        Args:
            current_voltage: Current battery voltage
            
        Returns:
            Battery percentage (0-100)
        """
        # Clamp voltage to valid range
        current_voltage = max(
            self.battery_cutoff_voltage,
            min(self.battery_initial_voltage, current_voltage)
        )
        
        if self.use_voltage_curve:
            return self._calculate_percentage_from_curve(current_voltage)
        else:
            return self._calculate_percentage_linear(current_voltage)

    def _calculate_percentage_linear(self, voltage: float) -> float:
        """Linear voltage to percentage calculation."""
        voltage_range = self.battery_initial_voltage - self.battery_cutoff_voltage
        if voltage_range <= 0:
            return 0.0
            
        percentage = ((voltage - self.battery_cutoff_voltage) / voltage_range) * 100
        return round(percentage, 1)

    def _calculate_percentage_from_curve(self, voltage: float) -> float:
        """
        Calculate percentage using voltage curve interpolation.
        
        This provides more accurate readings for Li-ion batteries which have
        a non-linear discharge curve.
        """
        sorted_voltages = sorted(self.voltage_curve.keys(), reverse=True)
        
        # Handle edge cases
        if voltage >= sorted_voltages[0]:
            return self.voltage_curve[sorted_voltages[0]]
        if voltage <= sorted_voltages[-1]:
            return self.voltage_curve[sorted_voltages[-1]]
        
        # Find the two voltage points to interpolate between
        for i in range(len(sorted_voltages) - 1):
            v_high = sorted_voltages[i]
            v_low = sorted_voltages[i + 1]
            
            if v_low <= voltage <= v_high:
                # Linear interpolation between the two points
                pct_high = self.voltage_curve[v_high]
                pct_low = self.voltage_curve[v_low]
                
                ratio = (voltage - v_low) / (v_high - v_low)
                percentage = pct_low + (pct_high - pct_low) * ratio
                return round(percentage, 1)
        
        return 0.0

    def normalize_percentage(self, percentage: float) -> int:
        """
        Normalize the percentage using a moving average to stabilize readings.
        
        Args:
            percentage: Raw battery percentage
            
        Returns:
            Smoothed percentage as integer
        """
        self.percentage_history.append(percentage)
        
        if len(self.percentage_history) > 0:
            normalized = sum(self.percentage_history) / len(self.percentage_history)
            return int(round(normalized))
        
        return int(round(percentage))

    def _determine_charging_state(self, current_mA: float) -> ChargingState:
        """
        Determine the charging state based on current flow with hysteresis.
        
        The INA260 measures current direction:
        - The sign of current depends on how IN+ and IN- are wired
        - charging_current_negative=True means negative current = charging
        - charging_current_negative=False means positive current = charging
        
        Args:
            current_mA: Current reading in mA
            
        Returns:
            ChargingState enum value
        """
        # Get the "charging direction" current
        # If charging_current_negative is True, we flip the sign so that
        # positive values indicate charging
        directed_current = -current_mA if self.charging_current_negative else current_mA
        
        # Get thresholds with hysteresis
        # Use different thresholds based on previous state to prevent flickering
        if self._last_charging_state == ChargingState.CHARGING:
            # Currently charging - need to drop below threshold minus hysteresis to switch
            charge_threshold = self.charging_current_threshold_mA - self.charging_hysteresis_mA
            discharge_threshold = -(self.charging_current_threshold_mA - self.charging_hysteresis_mA)
        else:
            # Not charging - need to exceed threshold plus hysteresis to switch
            charge_threshold = self.charging_current_threshold_mA + self.charging_hysteresis_mA
            discharge_threshold = -(self.charging_current_threshold_mA + self.charging_hysteresis_mA)
        
        # Check if battery is full (charging but voltage at max and low current)
        if (self._voltage >= self.battery_initial_voltage - 0.05 and 
            abs(current_mA) < self.charging_current_threshold_mA and
            self._last_charging_state == ChargingState.CHARGING):
            return ChargingState.FULL
        
        # Determine state based on current direction and magnitude
        if directed_current > charge_threshold:
            return ChargingState.CHARGING
        elif directed_current < discharge_threshold:
            return ChargingState.DISCHARGING
        else:
            # Current is within the "idle" band
            return ChargingState.IDLE

    def _update_discharge_rate(self, current_mA: float) -> None:
        """
        Update the discharge rate estimation.
        
        Uses a longer averaging window for stable time remaining estimates.
        
        Args:
            current_mA: Current reading in mA
        """
        self.current_history.append(current_mA)
        
        # Only calculate if discharging
        if self._charging_state == ChargingState.DISCHARGING:
            # Add current to discharge rate history (longer window)
            self.discharge_rate_history.append(abs(current_mA))
            
            if len(self.discharge_rate_history) >= 2:
                # Use the longer history for stable average
                avg_discharge = sum(self.discharge_rate_history) / len(self.discharge_rate_history)
                self._discharge_rate_mA = avg_discharge
                
                # Estimate time remaining
                if avg_discharge > 0:
                    remaining_capacity = (self._normalized_percentage / 100.0) * self.battery_capacity_mAh
                    self._estimated_time_remaining_min = (remaining_capacity / avg_discharge) * 60
                else:
                    self._estimated_time_remaining_min = None
        else:
            # Clear discharge history when not discharging
            self.discharge_rate_history.clear()
            self._discharge_rate_mA = 0.0
            self._estimated_time_remaining_min = None

    def _read_sensor(self) -> bool:
        """
        Read current values from the INA260 sensor.
        
        Returns:
            True if reading was successful, False otherwise
        """
        if not self.sensor_initialized:
            return False
            
        try:
            current = self.ina260.current    # mA
            voltage = self.ina260.voltage    # V
            power = self.ina260.power        # mW
            
            # Update values with thread safety
            with self._lock:
                self._current = current
                self._voltage = voltage
                self._power = power
                self._battery_percentage = self.calculate_battery_percentage(voltage)
                self._normalized_percentage = self.normalize_percentage(self._battery_percentage)
                
                # Update charging state
                new_state = self._determine_charging_state(current)
                if new_state != self._charging_state:
                    logger.info(f"Charging state changed: {self._charging_state.value} -> {new_state.value}")
                self._last_charging_state = self._charging_state
                self._charging_state = new_state
                
                # Update voltage history for trend analysis
                self.voltage_history.append(voltage)
            
            # Update discharge rate (outside lock to avoid holding it too long)
            self._update_discharge_rate(current)
            
            self._last_reading_time = time.time()
            return True
            
        except OSError as e:
            logger.error(f"I2C communication error: {e}")
            return False
        except Exception as e:
            logger.error(f"Sensor read error: {e}")
            return False

    def _check_critical_battery(self) -> None:
        """Check for critical battery level and handle auto-shutdown."""
        if not self.auto_shutdown:
            return
            
        if self._normalized_percentage <= 0:
            if self._zero_percent_start_time is None:
                # Start the countdown
                self._zero_percent_start_time = time.time()
                logger.warning(
                    f"Battery at 0%. System will shutdown in "
                    f"{self.shutdown_delay_seconds} seconds if battery remains critical."
                )
            else:
                # Check if we've been at 0% long enough
                elapsed = time.time() - self._zero_percent_start_time
                remaining = self.shutdown_delay_seconds - elapsed
                
                if remaining <= 10 and remaining > 0:
                    logger.warning(f"Critical battery shutdown in {int(remaining)} seconds...")
                    
                if elapsed >= self.shutdown_delay_seconds:
                    logger.critical("Battery at 0% for too long. Initiating system shutdown...")
                    self._initiate_shutdown()
        else:
            # Battery recovered
            if self._zero_percent_start_time is not None:
                logger.info(f"Battery recovered to {self._normalized_percentage}%. Shutdown cancelled.")
                self._zero_percent_start_time = None

    def _monitoring_loop(self) -> None:
        """Internal method that runs in a thread to continuously monitor battery status."""
        logger.info("Battery monitoring loop started")
        
        while self.is_running and self.sensor_initialized:
            try:
                # Read sensor values
                if self._read_sensor():
                    # Log percentage at significant drops
                    if (self._last_printed_percentage is None or 
                        self._battery_percentage <= self._last_printed_percentage - 10):
                        logger.info(
                            f"Battery: {self._battery_percentage:.1f}% "
                            f"({self._voltage:.2f}V, {self._current:.1f}mA, "
                            f"state: {self._charging_state.value})"
                        )
                        self._last_printed_percentage = self._battery_percentage
                    
                    # Check for critical battery
                    self._check_critical_battery()
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Battery monitoring error: {e}")
                time.sleep(2)
        
        logger.info("Battery monitoring loop ended")

    def _initiate_shutdown(self) -> None:
        """Initiate system shutdown."""
        import subprocess
        import os
        
        try:
            logger.critical("Executing: sudo shutdown now")
            subprocess.Popen(['sudo', 'shutdown', 'now'])
        except Exception as e:
            logger.error(f"Failed to initiate shutdown: {e}")
        
        # Give shutdown command time to execute
        time.sleep(2)
        os._exit(0)

    def start(self) -> bool:
        """
        Start the battery monitoring thread.
        
        Returns:
            True if started successfully, False otherwise
        """
        if not self.sensor_initialized:
            logger.error("Cannot start battery monitoring: sensor not initialized")
            return False
        
        if not self.is_running:
            # Do a burst of quick reads to pre-fill the smoothing buffers
            self._burst_initial_reads()
            
            self.is_running = True
            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()
            logger.info("Battery monitoring started")
            return True
            
        logger.warning("Battery monitoring already running")
        return False

    def _burst_initial_reads(self, count: int = 5) -> None:
        """
        Do rapid initial reads to pre-fill smoothing buffers.
        
        Args:
            count: Number of quick reads to perform
        """
        logger.debug(f"Performing {count} initial burst reads...")
        for i in range(count):
            self._read_sensor()
            if i < count - 1:  # Don't sleep after the last read
                time.sleep(0.1)
        logger.debug("Initial burst reads complete")

    def stop(self) -> bool:
        """
        Stop the battery monitoring thread.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if self.is_running:
            self.is_running = False
            if self.thread:
                self.thread.join(timeout=5.0)
                if self.thread.is_alive():
                    logger.warning("Monitoring thread did not stop cleanly")
            logger.info("Battery monitoring stopped")
            return True
            
        return False

    def is_charging(self) -> bool:
        """
        Check if the battery is currently charging.
        
        Returns:
            True if charging, False otherwise
        """
        return self._charging_state == ChargingState.CHARGING

    def get_battery_status(self, include_debug: bool = False) -> Dict[str, Any]:
        """
        Return current battery status as a dictionary.
        
        Args:
            include_debug: If True, include raw values for debugging
        
        Returns:
            Dictionary containing all battery status information
        """
        with self._lock:
            status = {
                'current_mA': round(self._current, 2),
                'voltage_V': round(self._voltage, 3),
                'power_mW': round(self._power, 2),
                'percentage': round(self._battery_percentage, 1),
                'normalized_percentage': self._normalized_percentage,
                'capacity_mAh': self.battery_capacity_mAh,
                'charging_state': self._charging_state.value,
                'is_charging': self._charging_state == ChargingState.CHARGING,
                'is_full': self._charging_state == ChargingState.FULL,
                'discharge_rate_mA': round(self._discharge_rate_mA, 2),
                'estimated_time_remaining_min': (
                    round(self._estimated_time_remaining_min, 1) 
                    if self._estimated_time_remaining_min else None
                ),
                'sensor_initialized': self.sensor_initialized,
                'last_reading_time': self._last_reading_time,
            }
            
            if include_debug:
                # Add debug info for verifying charging detection
                directed_current = -self._current if self.charging_current_negative else self._current
                status['debug'] = {
                    'raw_current_mA': self._current,
                    'directed_current_mA': round(directed_current, 2),
                    'charging_threshold_mA': self.charging_current_threshold_mA,
                    'charging_current_negative': self.charging_current_negative,
                    'would_be_charging': directed_current > self.charging_current_threshold_mA,
                    'discharge_samples': len(self.discharge_rate_history),
                }
            
            return status

    def get_battery_percentage(self) -> float:
        """Return the raw battery percentage."""
        return self._battery_percentage

    def get_normalized_percentage(self) -> int:
        """Return the normalized (smoothed) battery percentage."""
        return self._normalized_percentage

    def read_instant(self) -> Dict[str, Any]:
        """
        Get instant sensor readings without affecting smoothing buffers.
        
        Useful for quick checks or debugging. Does not update internal state.
        
        Returns:
            Dictionary with raw voltage, current, power, and calculated percentage
        """
        if not self.sensor_initialized:
            return {'error': 'Sensor not initialized'}
        
        try:
            voltage = self.ina260.voltage
            current = self.ina260.current
            power = self.ina260.power
            percentage = self.calculate_battery_percentage(voltage)
            
            # Determine charging state from current
            directed_current = -current if self.charging_current_negative else current
            if directed_current > self.charging_current_threshold_mA:
                state = "charging"
            elif directed_current < -self.charging_current_threshold_mA:
                state = "discharging"
            else:
                state = "idle"
            
            return {
                'voltage_V': round(voltage, 3),
                'current_mA': round(current, 2),
                'power_mW': round(power, 2),
                'percentage': round(percentage, 1),
                'charging_state': state,
            }
        except Exception as e:
            return {'error': str(e)}

    def get_estimated_time_remaining(self) -> Optional[float]:
        """
        Get estimated time remaining in minutes.
        
        Returns:
            Estimated minutes remaining, or None if not available
        """
        return self._estimated_time_remaining_min

    def calibrate_charging_direction(self, duration_seconds: int = 10) -> Optional[bool]:
        """
        Helper method to calibrate charging current direction.
        
        Run this while the battery is DEFINITELY CHARGING to determine
        whether charging current appears as positive or negative.
        
        Args:
            duration_seconds: How long to sample the current
            
        Returns:
            True if charging current is negative, False if positive,
            None if unable to determine
        """
        if not self.sensor_initialized:
            logger.error("Cannot calibrate: sensor not initialized")
            return None
        
        logger.info(f"Calibrating charging direction for {duration_seconds} seconds...")
        logger.info("Make sure the battery is CHARGING during this test!")
        
        readings = []
        for _ in range(duration_seconds * 2):  # Read every 0.5 seconds
            try:
                readings.append(self.ina260.current)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error during calibration: {e}")
        
        if not readings:
            return None
        
        avg_current = sum(readings) / len(readings)
        logger.info(f"Average current during charging: {avg_current:.2f} mA")
        
        if abs(avg_current) < 20:
            logger.warning("Current too low to determine direction. Is the battery actually charging?")
            return None
        
        is_negative = avg_current < 0
        logger.info(f"Charging current appears to be {'NEGATIVE' if is_negative else 'POSITIVE'}")
        logger.info(f"Set charging_current_negative={is_negative} in your configuration")
        
        return is_negative


# Example usage and testing
if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Battery Module Test")
    print("=" * 50)
    
    # Create battery module instance
    # Adjust charging_current_negative based on your wiring!
    battery = BatteryModule(
        charging_current_negative=True,  # True = negative current means charging
        use_voltage_curve=False,
    )
    
    if battery.sensor_initialized:
        # Quick test: read instant values before starting monitoring
        print("\nInstant reading (no smoothing):")
        instant = battery.read_instant()
        for key, value in instant.items():
            print(f"  {key}: {value}")
        
        # Start monitoring
        battery.start()
        
        print("\n" + "=" * 60)
        print("Monitoring... (Ctrl+C to stop)")
        print("Plug in charger to test charging detection!")
        print("=" * 60)
        
        try:
            while True:
                status = battery.get_battery_status(include_debug=True)
                debug = status.get('debug', {})
                
                # Compact status line
                print(f"\n{status['voltage_V']:.2f}V | "
                      f"{status['current_mA']:+.0f}mA | "
                      f"{status['power_mW']:.0f}mW | "
                      f"{status['normalized_percentage']}% | "
                      f"{status['charging_state'].upper()}")
                
                # Show directed current for debugging charging detection
                print(f"  → directed: {debug.get('directed_current_mA', 0):+.0f}mA "
                      f"(threshold: ±{debug.get('charging_threshold_mA', 0)}mA) "
                      f"| samples: {debug.get('discharge_samples', 0)}")
                
                if status['estimated_time_remaining_min']:
                    hours = int(status['estimated_time_remaining_min'] // 60)
                    mins = int(status['estimated_time_remaining_min'] % 60)
                    print(f"  → time remaining: {hours}h {mins}m "
                          f"(avg draw: {status['discharge_rate_mA']:.0f}mA)")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\nStopping...")
            battery.stop()
    else:
        print("Failed to initialize battery sensor")