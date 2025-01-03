# Raspberry Pi LCD and I2S Amplifier Wiring Guide & Calibration

This guide provides detailed instructions on how to wire an LCD display and an I2S amplifier to a Raspberry Pi, along with steps to calibrate the touchscreen and fine-tune the display. It assumes you are using an SPI-based LCD screen and an I2S amplifier for audio output.

---

## LCD Wiring

To wire the LCD display to your Raspberry Pi, use the following pinout configuration:

| **LCD Pin**       | **Raspberry Pi GPIO Pin** | **Description**                                      |
|--------------------|---------------------------|------------------------------------------------------|
| 1, 17             | 3.3V (Pin 1 or 17)        | 3.3V power supply.                                   |
| 2, 4              | 5V (Pin 2 or 4)           | 5V power supply for the backlight (if required).     |
| 6, 9, 14, 20, 25  | GND (Pin 6, 9, etc.)       | Ground connections.                                  |
| 11                | GPIO17 (Pin 11)           | Touch IRQ (optional, for touch input).              |
| 18                | GPIO24 (Pin 18)           | LCD Register Select (DC/RS).                        |
| 19                | GPIO10 (Pin 19, SPI MOSI) | SPI MOSI (data sent to the LCD).                    |
| 21                | GPIO9 (Pin 21, SPI MISO)  | SPI MISO (data received from touchscreen).          |
| 22                | GPIO25 (Pin 22)           | LCD Reset pin.                                       |
| 23                | GPIO11 (Pin 23, SPI SCLK) | SPI Clock for LCD and touchscreen.                  |
| 24                | GPIO8 (Pin 24, SPI CE0)   | SPI Chip Select for LCD.                            |
| 26                | GPIO7 (Pin 26, SPI CE1)   | SPI Chip Select for touchscreen.                    |

---

## Connecting the I2S Amplifier

For audio output, connect an I2S amplifier to the Raspberry Pi’s I2S (PCM) pins as follows:

| **Raspberry Pi Pin** | **GPIO Pin** | **Function**                          | **Connect to Amplifier**               |
|-----------------------|--------------|---------------------------------------|----------------------------------------|
| Pin 12               | GPIO18       | I2S Bit Clock (BCLK)                  | BCLK                                   |
| Pin 35               | GPIO19       | I2S Left/Right Clock (LRCLK)          | LRCLK                                  |
| Pin 40               | GPIO21       | I2S Data Out (DOUT)                   | DIN (Audio Data Input to Amplifier)    |
| Pin 6                | GND          | Ground                                | GND (Amplifier Ground)                 |
| Pin 2 or 4           | 5V           | Power Supply                          | VIN (Amplifier Power Input)            |

**Note**: Enable the I2S interface on the Raspberry Pi by following the instructions in the [Adafruit MAX98357 guide](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pi-i2s-tweaks).

---

## Touchscreen Calibration
To calibrate the touchscreen, follow these steps:


### Step 1: Install the Calibration Tool
sudo apt-get update
sudo apt-get install xinput-calibrator


### Step 2: Run the Calibration Tool
xinput_calibrator
Touch the targets as instructed. The tool will generate calibration offsets.


### Step 3: Save the Calibration Data
Save the output data to a configuration file:

sudo nano /usr/share/X11/xorg.conf.d/99-calibration.conf
Paste the calibration data and save the file.


### Step 4: Reboot
sudo reboot


### Step 5: Verify Calibration
Interact with the desktop to ensure accurate touch. If needed, rerun the calibration tool or manually adjust the values in 99-calibration.conf.


**Additional Notes**
Enable SPI and I2S interfaces via sudo raspi-config under Interfacing Options.
Refer to the Adafruit MAX98357 guide for detailed amplifier setup.
Test the audio and touchscreen thoroughly after setup.