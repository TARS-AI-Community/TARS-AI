<h1 align="center">TARS-AI</h2>

<p align="center">
    <a href="https://discord.gg/AmE2Gv9EUt">
      <img alt="discord invitation link" src="https://dcbadge.vercel.app/api/server/uXkqkz3mJJ?style=flat" align="center" />
    </a>
    <a href="https://www.youtube.com/@TARS-AI.py.youtube">
        <img src="https://img.shields.io/badge/YouTube-red?style=flat-square&logo=youtube&logoColor=white" alt="YouTube" align="center" />
    </a>
    <a href="https://www.instagram.com/tars.ai.py">
        <img src="https://img.shields.io/badge/Instagram-purple?style=flat-square&logo=instagram&logoColor=white" alt="Instagram" align="center" />
    </a>
    <a href="https://www.tiktok.com/@tars.ai.py">
        <img src="https://img.shields.io/badge/TikTok-black?style=flat-square&logo=tiktok&logoColor=white" alt="TikTok" align="center" />
    </a>
</p>

<p align="center"><a href="https://github.com/pyrater/TARS-AI"><img width=50% alt="" src="/media/tars-ai.png" /></a></p>

A recreation of the TARS robot from Interstellar, featuring AI capabilities and servo-driven movement. 

## Table of Contents
- [Hardware Requirements](#hardware-requirements)
- [Software Stack](#software-stack)
- [Build Modifications](#build-modifications)
- [License](#license)
- [Contributing](#contributing)
- [Additional Resources](#additional-resources)

## Hardware Requirements 

Everything here is **under development** and is subject to change.
The buck converter and USB power modules are the most important power components and there are many options depending on your build choices. If you have any questions ping us in the discord electrical channel.

| Category | Component | Description | Link |
|----------|-----------|-------------|------|
| **Printing** | Bambu Labs Printer | Compatible models: P1S, A1, X1C | - |
| | TPU Filament (Bambu) | For all "Flexor" parts | [Buy](https://us.store.bambulab.com/products/tpu-for-ams) |
| | TPU Filament (Alternative) | Overture TPU filament | [Buy](https://www.amazon.com/Overture-Filament-Flexible-Consumables-Dimensional/dp/B07VDP2S3P/) |
| | PETG Filament | For all non-Flexor parts | [Buy](https://us.store.bambulab.com/products/petg-hf) |
| | PLA Filament | Optional - for rapid prototyping | - |
| **Core Components** | Raspberry Pi 5 | Main computing unit | [Buy](https://www.amazon.com/Raspberry-Pi-Quad-core-Cortex-A76-Processor/dp/B0CTQ3BQLS/) |
| | 3.5" LCD Display | Interface display | [Buy](https://www.amazon.com/OSOYOO-3-5inch-Display-Protective-Raspberry/dp/B09CD9W6NQ/) |
| | 16-Channel PWM Servo Driver | I2C Interface | [Buy](https://www.amazon.com/gp/product/B00EIB0U7A/) |
| **Power Components** | Buck Converter | Power management | [Buy](https://www.amazon.com/gp/product/B07SGJSLDL/) |
| | USB power | 2x for Pi and display. Must have 5A minimum to drive a Raspberry Pi 5.| [Buy](https://www.amazon.com/gp/product/B07X5H4M42) |
| | Single LiPo Battery| 11.1v 3S 2200mAh| [Buy](https://www.amazon.com/gp/product/B0BYNSH6Q7) |
| | Wire Connectors| PCT-214 (optionally clips into v9 lower lid)| [Buy](https://www.amazon.com/smseace-Conductor-Connectors-Connection-Terminal/dp/B087PBHG9L) |
| **Servo Motors** | diymore MG996R | Digital servo motors (2x 90g servos per leg) | [Buy](https://www.amazon.com/diymore-6-Pack-MG996R-Digital-Helicopter/dp/B0CGRP59HJ/) |
| | MG996R 55g (Alternative to above) | Digital 55g high torque (2x per leg) | [Buy](https://www.amazon.com/gp/product/B0BMM1G74B) |
| | Micro servos (hands) | Digital servo motors (2x S51/9g micro servos per arm/hand) | [Buy](https://www.amazon.com/gp/product/B07L2SF3R4/) |
| **Drive Train** | Bearings | Motion support | [Buy](https://www.amazon.com/gp/product/B07FW26HD4/) |
| | Springs | Motion dampening | [Buy](https://www.amazon.com/gp/product/B076M6SFFP/) |
| | Metal Rods (Option 1) | Structural support | [Buy](https://www.amazon.com/gp/product/B01MAYQ12S/) |
| | Metal Rods (Option 2) | Alternative structural support | [Buy](https://www.amazon.com/gp/product/B0CTSX8SJS/) |
| | Linkage | Motion transfer | [Buy](https://www.amazon.com/gp/product/B0CRDRWYXW/) |
| | Servo Extension Wires | Connection cables | [Buy](https://www.amazon.com/OliYin-7-87in-Quadcopter-Extension-Futaba/dp/B0711TBZY2/) |
| **Audio System** | Raspberry Pi Microphone | Audio input | [Buy](https://www.amazon.com/gp/product/B086DRRP79/) |
| | Audio Amplifier | Sound processing | [Buy](https://www.amazon.com/dp/B0BTBS5NW2) |
| | Speaker | Audio output | [Buy](https://www.amazon.com/dp/B07GJ4GH67) |
| **Camera System** | Camera Module | Visual input | [Buy](https://a.co/d/50BbE8a) |
| | Camera Ribbon Cable | Camera connection | [Buy](https://www.amazon.com/Onyehn-Raspberry-Camera-Cable-Ribbon/dp/B07XZ5DX5H/) |
| **Fasteners** | M3 20mm Screws | Mounting (6x needed) | [Buy](https://www.amazon.com/gp/product/B0CR6DY4SS/) |
| | M3 14mm Screws | Mounting (40x needed) | [Buy](https://www.amazon.com/gp/product/B0D9GW9K4G/) |
| | M3 10mm Screws | Mounting (76x needed) | [Buy](https://www.amazon.com/gp/product/B0CR6G5XWC/) |
| | M3 Asstd Grub Screws | Mounting (6-8 needed) | [Buy](https://www.amazon.com/dp/B07N7C6HKP/) |
| | M2.x self tapping | Pi and servo controller mounts (8 needed) | [Buy](https://www.amazon.com/gp/product/B0BLY1MPLR/) |

## Wiring Guide for GPIO LCD Screen (if not using HDMI) and I2S Amplifier.
This section provides detailed instructions on how to wire an LCD display and an I2S amplifier to a Raspberry Pi, along with steps to calibrate the touchscreen and fine-tune the display. It assumes you are using an SPI-based LCD screen and an I2S amplifier for audio output.

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
- Enable SPI and I2S interfaces via sudo raspi-config under Interfacing Options.
- Refer to the [Adafruit MAX98357 guide](https://cdn-learn.adafruit.com/downloads/pdf/adafruit-max98357-i2s-class-d-mono-amp.pdf) for detailed amplifier setup.
- Test the audio and touchscreen thoroughly after setup.

## Software Stack

See [`ENVSETUP.md`](./ENVSETUP.md) for instructions on setting up the software environment.

[![GPTARS Software Demo](https://img.youtube.com/vi/4YObs8BV3Mc/0.jpg)](https://www.youtube.com/watch?v=4YObs8BV3Mc)

- **LLM**: Choice of:
  - OpenAI (Recommended)
  - Oobabooga
  - Tabby ([tabbyAPI](https://github.com/theroyallab/tabbyAPI))
  - Ollama (Soon)
- **Text-to-Speech**: Choice of:
  - Azure TTS
  - Local (E-speak)
  - Local (Piper TTS with custom Voice model) (Recommended)
  - XTTSv2 with voice cloning ([xtts-api-server](https://github.com/daswer123/xtts-api-server))
- **Speech-to-Text**:
  - Vosk
  - Whisper
- **Vision Handling**:
  - Saleforce Blip
- **Tool Utilization**:
  - Custom Module Engine

## Build Modifications
![print](./media/PrintComplete.jpg)
- Modified chassis bottom to accommodate SD card installation (See: "Chassis Bottom (Mod SD CARD).stl")

## License
[CC-BY-NU License](./LICENSE)

## Contributing
See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for instructions on contributing to this project.

## Additional Resources
Inspirations + Credits to:
- [@charliediaz](https://www.hackster.io/charlesdiaz/how-to-build-your-own-replica-of-tars-from-interstellar-224833)
- [@gptars](https://www.youtube.com/@gptars)
- [@poboisvert](https://github.com/poboisvert/GPTARS_Interstellar)

## Attribution 
### TARS Project Attribution Guidelines
As we continue to build and expand upon the TARS project, below are the guidelines for attribution and best practices when sharing or publishing work related to the TARS project:

#### General Attribution
- Clearly state that this project is based on the character TARS from the film *Interstellar*.
- When referencing or sharing the CAD designs:
  - Include a statement like: “Based on the mechanical puppet designs by Christopher Nolan, Nathan Crowley, and the production team who originally brought TARS to life—miniaturized CAD by Charlie Diaz, with additional modifications by the TARS-AI Community.”

#### Specific Guidelines for CAD and Scripts
- The original CAD files and scripts are provided by Charlie Diaz. If you modify or extend these, ensure to:
  - Credit Charlie Diaz as the original creator of the CAD files.
  - Clearly specify your contributions or modifications.

#### Usage of TARS’ Voice and Personality
  - “This project includes AI-generated elements inspired by Bill Irwin’s portrayal of TARS in the film *Interstellar*.”

#### Sharing Content Online
- When publishing content (e.g., YouTube videos, blog posts, or repository updates):
  - Attribute the original film’s production team and Charlie Diaz where applicable.
  - Include a disclaimer noting that this project is a fan-made initiative.

#### Legal Considerations
- Monetization is strictly prohibited.

#### Community Contribution
- Encourage contributors to follow these attribution guidelines when making modifications or additions to the project.
- Foster an open and respectful community by maintaining transparency in crediting the work of all contributors.

These guidelines ensure that the TARS project respects the intellectual property of the original creators while fostering a collaborative and innovative community. Let’s work together to keep this project thriving and inspiring!
