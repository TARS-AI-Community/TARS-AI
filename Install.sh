#!/bin/bash
# New Build Script with Retry Mechanism for pip install
# v0.3 TeknikL

set -e  # Exit on any error

# Function to retry pip install if it fails
retry_pip_install() {
    local n=1
    local max=5  # Maximum number of attempts
    local delay=5 # Delay in seconds

    while true; do
        pip install -r requirements.txt && break || {
            if [[ $n -lt $max ]]; then
                echo "pip install failed (attempt $n/$max). Retrying in $delay seconds..."
                sleep $delay
                ((n++))
            else
                echo "pip install failed after $max attempts. Exiting."
                exit 1
            fi
        }
    done
}

# Update and upgrade system packages
sudo apt clean
sudo apt update -y

# Install necessary dependencies
sudo apt install -y chromium-browser chromium-chromedriver sox libsox-fmt-all portaudio19-dev espeak-ng

# Verify installations
chromium-browser --version
chromedriver --version
sox --version

# Ensure we are in the correct directory
if [ ! -d "src" ]; then
    echo "Error: 'src' directory not found!"
    exit 1
fi
cd src

# Create and activate Python virtual environment
python3 -m venv .venv

# Use correct method for activating venv in bash
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: Virtual environment activation script not found!"
    exit 1
fi

# Install additional dependencies
sudo apt-get install -y libcap-dev

# Upgrade pip
pip install --upgrade pip

# **Retry pip install on failure**
retry_pip_install

# Copy configuration files if they do not exist
if [ ! -f "config.ini" ]; then
    cp config.ini.template config.ini
    echo "Default config.ini created. Please edit it with necessary values."
fi

if [ ! -f "../.env" ]; then
    cp ../.env.template ../.env
    echo "Default .env created. Please edit it with necessary values."
fi

echo "Installation completed successfully!"