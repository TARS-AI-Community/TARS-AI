#New Build Script
#v0.1 TeknikL
#!/bin/sh
git clone https://github.com/pyrater/TARS-AI.git
cd TARS-AI/src
sudo apt update
sudo apt upgrade -y
sudo apt install -y chromium-browser
sudo apt install -y chromium-chromedriver
sudo apt install -y sox libsox-fmt-all
sudo apt install -y portaudio19-dev
chromium-browser --version
chromedriver --version
sox --version
#make the venv for python
python -m venv venv
source venv/bin/activate
#install pre requisites
pip install -r requirements.txt
#edit src/config.ini.example and save as config.ini
#edit ../.env.example and put in keys, and x if none, and save as .env