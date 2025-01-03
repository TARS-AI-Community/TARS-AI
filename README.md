<h1 align="center">TARS-AI</h2>

<p align="center">
    <a href="https://discord.gg/uXkqkz3mJJ">
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
- [@wizard.py](https://www.instagram.com/wizard.py/)
- [@poboisvert](https://github.com/poboisvert/GPTARS_Interstellar)

