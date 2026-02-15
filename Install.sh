#!/bin/bash
# TARS System Installation Protocol
# Atomikspace / Pyrater / TeknikL

set -e

if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    echo ""
    echo "+================================================================+"
    echo "| NOTICE: Script run with sudo - will set ownership to: $SUDO_USER"
    echo "+================================================================+"
    echo ""
    sleep 2
else
    ACTUAL_USER="$(whoami)"
fi

DELAY=0.02
PI_VERSION=""
INSTALL_RETROPIE=false
INSTALL_RASPOTIFY=false
HAS_DEVICE_SECTION=false

show_tars_boot() {
    clear
    cat << "EOF"
    +=============================================+
    |                                             |
    |     ████████╗ █████╗ ██████╗ ███████╗       |
    |     ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝       |
    |        ██║   ███████║██████╔╝███████╗       |
    |        ██║   ██╔══██║██╔══██╗╚════██║       |
    |        ██║   ██║  ██║██║  ██║███████║       |
    |        ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝       |
    |                                             |
    +=============================================+
EOF
    sleep 2
}

tars_say() {
    local message=$1
    local type=${2:-"info"}
    
    case $type in
        "info")
            echo "+=== TARS ====================================================+"
            echo "| ${message}"
            echo "+=============================================================+"
            ;;
        "success")
            echo "+=== TARS ====================================================+"
            echo "| [OK] ${message}"
            echo "+=============================================================+"
            ;;
        "warning")
            echo "+=== TARS ====================================================+"
            echo "| [!] ${message}"
            echo "+=============================================================+"
            ;;
        "error")
            echo "+=== TARS ====================================================+"
            echo "| [X] ${message}"
            echo "+=============================================================+"
            ;;
    esac
    echo ""
}

select_pi_version() {
    local tars_data_dir="$HOME/.local/share/tars_ai"
    local pi_version_file="$tars_data_dir/pi_version"
    local config_file="src/config.ini"
    local has_device_section=false

    if [ -f "$config_file" ] && grep -q '^\[DEVICE\]' "$config_file"; then
        has_device_section=true
        HAS_DEVICE_SECTION=true
    fi

    if [ "$has_device_section" = false ]; then
        PI_VERSION="pi5"
        HAS_DEVICE_SECTION=false
        tars_say "No [DEVICE] section found, defaulting to PI5" "info"
        mkdir -p "$tars_data_dir"
        echo "$PI_VERSION" > "$pi_version_file"
        _display_profile_summary
        return
    fi

    echo ""
    echo "+===============================================================+"
    echo "|           RASPBERRY PI VERSION SELECTION                      |"
    echo "+===============================================================+"
    echo "|                                                               |"
    echo "|  Select your Raspberry Pi model:                              |"
    echo "|                                                               |"
    echo "|  1) Raspberry Pi 5      - Full features, all local processing |"
    echo "|  2) Raspberry Pi 4      - Most features, some cloud fallbacks |"
    echo "|  3) Raspberry Pi 3      - Lite mode, Piper TTS, cloud STT       |"
    echo "|  4) Raspberry Pi Zero 2 - Minimal, Piper TTS, cloud STT        |"
    echo "|                                                               |"
    echo "+===============================================================+"
    echo ""

    while true; do
        read -p "Enter your choice [1-4]: " choice
        case $choice in
            1)
                PI_VERSION="pi5"
                tars_say "Selected: Raspberry Pi 5 (Full Installation)" "success"
                break
                ;;
            2)
                PI_VERSION="pi4"
                tars_say "Selected: Raspberry Pi 4 (Standard Installation)" "success"
                break
                ;;
            3)
                PI_VERSION="pi3"
                tars_say "Selected: Raspberry Pi 3 (Lite Installation)" "success"
                break
                ;;
            4)
                PI_VERSION="pizero2"
                tars_say "Selected: Raspberry Pi Zero 2 (Minimal Installation)" "success"
                break
                ;;
            *)
                echo "Invalid selection. Please enter 1, 2, 3, or 4."
                ;;
        esac
    done

    mkdir -p "$tars_data_dir"
    echo "$PI_VERSION" > "$pi_version_file"

    _display_profile_summary

    read -p "Continue with this profile? [y/n]: " -r CONFIRM
    if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
        tars_say "Installation cancelled by user." "warning"
        exit 0
    fi
}

_display_profile_summary() {
    echo ""
    echo "+===============================================================+"
    echo "| INSTALLATION PROFILE: ${PI_VERSION^^}"
    echo "+===============================================================+"
    
    case $PI_VERSION in
        "pi5")
            echo "| Features: Full local STT, TTS, embeddings, UI, vision"
            echo "| Memory:   Full embedding-based memory"
            echo "| Size:     ~2.5GB+ dependencies"
            ;;
        "pi4")
            echo "| Features: Vosk STT, Piper/eSpeak TTS, embeddings, UI"
            echo "| Memory:   Full embedding-based memory"
            echo "| Size:     ~1.5GB+ dependencies"
            ;;
        "pi3")
            echo "| Features: Cloud STT, Piper/eSpeak TTS, keyword memory, no UI"
            echo "| Memory:   Lite keyword-based memory"
            echo "| Size:     ~500MB dependencies"
            ;;
        "pizero2")
            echo "| Features: OpenAI STT, Piper/eSpeak TTS, keyword memory, no UI"
            echo "| Memory:   Lite keyword-based memory"
            echo "| Size:     ~300MB dependencies"
            ;;
    esac
    
    echo "+===============================================================+"
    echo ""
}

select_thirdparty_apps() {
    echo ""
    echo "+===============================================================+"
    echo "|           3RD PARTY APPLICATIONS                              |"
    echo "+===============================================================+"
    echo "|                                                               |"
    echo "|  Would you like to install optional 3rd party applications?   |"
    echo "|                                                               |"
    echo "|  NOTE: You can skip this now and run the installer again      |"
    echo "|  later once you are satisfied with the main installation.     |"
    echo "|                                                               |"
    echo "+===============================================================+"
    echo ""

    read -p "Install 3rd party applications? [y/n]: " -r THIRDPARTY_REPLY
    echo ""

    if [[ ! $THIRDPARTY_REPLY =~ ^[Yy]$ ]]; then
        tars_say "Skipping 3rd party applications. Run this installer again when ready." "info"
        return
    fi

    echo "+===============================================================+"
    echo "|           3RD PARTY APPLICATION SELECTION                     |"
    echo "+===============================================================+"
    echo "|                                                               |"
    echo "|  Select applications to install (toggle with number):         |"
    echo "|                                                               |"
    echo "|  1) RetroPie   - Retro gaming emulation platform              |"
    echo "|     [!] WARNING: Installation takes approximately 60 minutes  |"
    echo "|         depending on your Pi model and network speed.         |"
    echo "|                                                               |"
    echo "|  2) Raspotify  - Spotify Connect client for Raspberry Pi      |"
    echo "|     Turns your Pi into a Spotify speaker (requires Premium)   |"
    echo "|                                                               |"
    echo "+===============================================================+"
    echo ""

    local retropie_selected=false
    local raspotify_selected=false

    while true; do
        local retropie_mark="[ ]"
        local raspotify_mark="[ ]"
        if [ "$retropie_selected" = true ]; then
            retropie_mark="[X]"
        fi
        if [ "$raspotify_selected" = true ]; then
            raspotify_mark="[X]"
        fi

        echo "  ${retropie_mark} 1) RetroPie (~60 min install)"
        echo "  ${raspotify_mark} 2) Raspotify (~2 min install)"
        echo ""
        echo "  Enter a number to toggle, or 'done' to confirm: "

        read -p "  > " toggle_choice

        case $toggle_choice in
            1)
                if [ "$retropie_selected" = true ]; then
                    retropie_selected=false
                else
                    retropie_selected=true
                fi
                ;;
            2)
                if [ "$raspotify_selected" = true ]; then
                    raspotify_selected=false
                else
                    raspotify_selected=true
                fi
                ;;
            done|DONE|Done|d|D)
                break
                ;;
            *)
                echo "  Invalid selection. Enter 1-2 to toggle or 'done' to confirm."
                ;;
        esac
        echo ""
    done

    local selected_apps=""
    if [ "$retropie_selected" = true ]; then
        INSTALL_RETROPIE=true
        selected_apps="${selected_apps}    - RetroPie (estimated ~60 minutes)\n"
    fi
    if [ "$raspotify_selected" = true ]; then
        INSTALL_RASPOTIFY=true
        selected_apps="${selected_apps}    - Raspotify (estimated ~2 minutes)\n"
    fi

    if [ -n "$selected_apps" ]; then
        echo ""
        echo "+===============================================================+"
        echo "|           PLEASE CONFIRM                                      |"
        echo "+===============================================================+"
        echo "|                                                               |"
        echo "|  You have selected:                                           |"
        echo -e "|  ${selected_apps}|"
        echo "|                                                               |"
        echo "|  Make sure you have a stable power supply and network         |"
        echo "|  connection before proceeding.                                |"
        echo "|                                                               |"
        echo "|  You can always skip this and run the installer again later.  |"
        echo "|                                                               |"
        echo "+===============================================================+"
        echo ""

        read -p "Are you sure you want to proceed? [y/n]: " -r CONFIRM1
        echo ""

        if [[ ! $CONFIRM1 =~ ^[Yy]$ ]]; then
            INSTALL_RETROPIE=false
            INSTALL_RASPOTIFY=false
            tars_say "3rd party installation cancelled. Run this installer again when ready." "info"
            return
        fi

        local queued=""
        [ "$INSTALL_RETROPIE" = true ] && queued="${queued} RetroPie"
        [ "$INSTALL_RASPOTIFY" = true ] && queued="${queued} Raspotify"
        tars_say "Queued for installation:${queued}" "success"
    else
        tars_say "No 3rd party applications selected." "info"
    fi
}

install_retropie() {
    if [ "$INSTALL_RETROPIE" != true ]; then
        return 0
    fi

    echo ""
    echo "+===============================================================+"
    echo "|           RETROPIE INSTALLATION                               |"
    echo "+===============================================================+"
    echo "| Target device: ${PI_VERSION^^}"
    echo "+===============================================================+"
    echo ""

    tars_say "Installing RetroPie dependencies..." "info"
    sudo apt install -y git dialog xmlstarlet lsb-release 2>&1 | tail -10

    local retropie_dir="$HOME/RetroPie-Setup"

    if [ -d "$retropie_dir" ]; then
        echo "+===============================================================+"
        echo "| EXISTING RETROPIE-SETUP DETECTED"
        echo "+===============================================================+"
        echo "| Location: $retropie_dir"
        echo "+===============================================================+"
        echo ""

        read -p "Re-clone RetroPie-Setup? (overwrites existing) [y/n]: " -r RECLONE_REPLY
        echo ""

        if [[ $RECLONE_REPLY =~ ^[Yy]$ ]]; then
            tars_say "Removing existing RetroPie-Setup..." "info"
            sudo rm -rf "$retropie_dir"
        else
            tars_say "Keeping existing RetroPie-Setup directory." "info"
        fi
    fi

    if [ ! -d "$retropie_dir" ]; then
        tars_say "Cloning RetroPie-Setup repository..." "info"
        git clone --depth=1 https://github.com/RetroPie/RetroPie-Setup.git "$retropie_dir"
        tars_say "RetroPie-Setup cloned successfully." "success"
    fi

    sudo chown -R $ACTUAL_USER:$ACTUAL_USER "$retropie_dir"

    echo ""
    echo "+===============================================================+"
    echo "| RETROPIE SETUP READY"
    echo "+===============================================================+"
    echo "|                                                               |"
    echo "|  RetroPie-Setup has been downloaded to:                       |"
    echo "|  $retropie_dir"
    echo "|                                                               |"

    case $PI_VERSION in
        "pi5")
            echo "|  NOTE (Pi5): No official prebuilt image exists yet.           |"
            echo "|  RetroPie will be installed on top of your current Pi OS.     |"
            echo "|  The Pi 5 can handle Dreamcast, Saturn, PSP and more.         |"
            ;;
        "pi4")
            echo "|  NOTE (Pi4): Full RetroPie support. Most emulators will       |"
            echo "|  run smoothly including N64, PSX, and Dreamcast.              |"
            ;;
        "pi3")
            echo "|  NOTE (Pi3): RetroPie Lite. Best for 8/16-bit consoles        |"
            echo "|  (NES, SNES, Genesis, Game Boy). N64/PSX may struggle.        |"
            ;;
        "pizero2")
            echo "|  NOTE (Zero2): Minimal RetroPie. Works well for 8/16-bit      |"
            echo "|  consoles. Heavier emulators will likely not perform well.     |"
            ;;
    esac

    echo "|                                                               |"
    echo "+===============================================================+"
    echo ""

    read -p "Run RetroPie basic install now? (this can take a while) [y/n]: " -r RUN_SETUP_REPLY
    echo ""

    if [[ $RUN_SETUP_REPLY =~ ^[Yy]$ ]]; then
        tars_say "Running RetroPie basic install (non-interactive)..." "info"
        tars_say "This may take 30-60+ minutes depending on your Pi and network." "warning"
        echo ""

        cd "$retropie_dir"
        sudo ./retropie_packages.sh setup basic_install
        cd - > /dev/null

        tars_say "RetroPie basic install complete!" "success"

        tars_say "Configuring RetroPie for manual launch only..." "info"

        local autostart_file="/opt/retropie/configs/all/autostart.sh"
        if [ -f "$autostart_file" ]; then
            echo "# disabled - use launch_retropie.sh to start" | sudo tee "$autostart_file" > /dev/null
            tars_say "EmulationStation autostart disabled." "success"
        fi

        sudo systemctl stop asplashscreen 2>/dev/null
        sudo systemctl disable asplashscreen 2>/dev/null
        sudo systemctl mask asplashscreen 2>/dev/null
        tars_say "RetroPie splash screen disabled." "success"

        sudo systemctl set-default graphical.target 2>/dev/null
        sudo systemctl enable display-manager 2>/dev/null
        tars_say "Desktop boot target preserved." "success"

        echo ""
        echo "+===============================================================+"
        echo "| RetroPie is installed but will NOT start on boot.            |"
        echo "| To play, run: ./launch_retropie.sh                          |"
        echo "|                                                               |"
        echo "| To configure further or install optional packages, run:       |"
        echo "|   cd $retropie_dir"
        echo "|   sudo ./retropie_setup.sh                                    |"
        echo "+===============================================================+"
    else
        tars_say "RetroPie setup skipped. You can run it later with:" "info"
        echo "|  cd $retropie_dir"
        echo "|  sudo ./retropie_setup.sh"
        echo "|"
        echo "|  Then select 'Basic Install' from the menu."
        echo "+===============================================================+"
    fi

    echo ""
}

install_raspotify() {
    if [ "$INSTALL_RASPOTIFY" != true ]; then
        return 0
    fi

    echo ""
    echo "+===============================================================+"
    echo "|           RASPOTIFY INSTALLATION                              |"
    echo "+===============================================================+"
    echo "| Spotify Connect client for Raspberry Pi                       |"
    echo "| Target device: ${PI_VERSION^^}"
    echo "+===============================================================+"
    echo ""

    tars_say "Installing Raspotify (Spotify Connect)..." "info"

    if ! command -v curl &> /dev/null; then
        sudo apt-get -y install curl 2>&1 | tail -5
    fi

    if curl -sL https://dtcooper.github.io/raspotify/install.sh | sh; then
        tars_say "Raspotify installed successfully!" "success"

        tars_say "Configuring device name as 'SpotiTars'..." "info"
        local raspotify_conf="/etc/raspotify/conf"
        if [ -f "$raspotify_conf" ]; then
            sudo sed -i 's/^#\?DEVICE_NAME=.*/DEVICE_NAME="SpotiTars"/' "$raspotify_conf"
            sudo sed -i 's/^#\?LIBRESPOT_BACKEND=.*/LIBRESPOT_BACKEND=alsa/' "$raspotify_conf"
            if ! grep -q '^LIBRESPOT_BACKEND=' "$raspotify_conf"; then
                echo 'LIBRESPOT_BACKEND=alsa' | sudo tee -a "$raspotify_conf" > /dev/null
            fi
            if grep -q '^#\?LIBRESPOT_DEVICE=' "$raspotify_conf"; then
                sudo sed -i 's/^#\?LIBRESPOT_DEVICE=.*/LIBRESPOT_DEVICE=hw:2,0/' "$raspotify_conf"
            else
                echo 'LIBRESPOT_DEVICE=hw:2,0' | sudo tee -a "$raspotify_conf" > /dev/null
            fi
            sudo systemctl restart raspotify
            tars_say "Device name set to 'SpotiTars'." "success"
            tars_say "Audio output set to USB PnP Audio Device (hw:2,0)." "success"
        else
            tars_say "Config file not found. Set name manually in /etc/raspotify/conf" "warning"
        fi
    else
        tars_say "Raspotify installation failed. You can try manually later:" "error"
        echo "|  curl -sL https://dtcooper.github.io/raspotify/install.sh | sh"
        echo "+===============================================================+"
        echo ""
        return 1
    fi

    echo ""
    echo "+===============================================================+"
    echo "| RASPOTIFY SETUP COMPLETE                                      |"
    echo "+===============================================================+"
    echo "|                                                               |"
    echo "|  Raspotify is now running as a system service.                |"
    echo "|                                                               |"
    echo "|  Your Pi will appear as 'SpotiTars' in Spotify Connect.        |"
    echo "|  Open Spotify on your phone/computer and look for it          |"
    echo "|  in the 'Connect to a device' menu.                           |"
    echo "|                                                               |"
    echo "|  NOTE: A Spotify Premium account is required.                 |"
    echo "|                                                               |"
    echo "|  To customize settings (device name, bitrate, etc):           |"
    echo "|    sudo nano /etc/raspotify/conf                              |"
    echo "|    sudo systemctl restart raspotify                           |"
    echo "|                                                               |"
    echo "|  Useful commands:                                             |"
    echo "|    sudo systemctl status raspotify   - Check status           |"
    echo "|    sudo systemctl restart raspotify  - Restart service        |"
    echo "|    sudo systemctl stop raspotify     - Stop service           |"
    echo "|                                                               |"
    echo "+===============================================================+"
    echo ""
}

generate_requirements() {
    local req_dir="$HOME/.local/share/tars_a"
    mkdir -p "$req_dir"
    local req_file="$req_dir/requirements_${PI_VERSION}.txt"
    
    tars_say "Generating requirements for ${PI_VERSION^^}..." "info"
    
    cat > "$req_file" << 'COMMON'
# === COMMON REQUIREMENTS (All Pi versions) ===

# LLM Tools
openai                          # External LLM API
tiktoken                        # Token counting for OpenAI models

# Sound Processing Tools
pydub                           # Audio processing for TTS modifications
soundfile                       # Read & write sound files
sounddevice                     # Audio I/O for playing and capturing sound

# Chat UI & Web Frameworks
flask                           # Web framework for ChatUI
flask-cors                      # Cross-Origin Resource Sharing (CORS) for Flask
flask-socketio                  # WebSockets support for Flask
eventlet                        # Async support for Flask-SocketIO
Pillow                          # Image processing for ChatUI face animation

# Miscellaneous Utilities
configobj                       # Maintain comments in config.ini during updates
python-dotenv                   # Load environment variables from a .env file
requests                        # HTTP library for API interactions
joblib                          # Efficient serialization of Python objects
ddgs                            # web search parsing

# Servo Control
adafruit-circuitpython-pca9685  # PCA9685 servo controller libraries
adafruit-blinka
adafruit-circuitpython-busdevice
adafruit-circuitpython-servokit # Servo libraries (high-level servo control)

# Battery
adafruit-circuitpython-ina260   # INA260 sensor

# Discord
discord.py                      # Discord bot API

# Wake Word (Atomik)
scipy                           # Signal processing for wake word detection

# Multimedia
pygame                          # Game development & multimedia support

COMMON

    if [[ "$PI_VERSION" == "pi5" ]]; then
        cat >> "$req_file" << 'LGPIO'

# === GPIO (Pi5 only) ===
lgpio                           # Required for Raspberry Pi 5 GPIO

LGPIO
    fi

    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'EMBEDDINGS'

# === EMBEDDING & MEMORY (Pi4/Pi5) ===
sentence-transformers           # Sentence embeddings and semantic search

# Memory & Search Tools  
bm25s                           # BM25 ranking for information retrieval
pystemmer                       # Stem words for text processing
hyperdb-python                  # High-performance database library
scikit-learn                    # Predictive data analysis tools
flashrank                       # Lightweight re-ranker

EMBEDDINGS
    fi

    cat >> "$req_file" << 'PICOVOICE'

# === WAKE WORD (All Pi versions) ===
pvporcupine                     # Wake word detection by Picovoice
pvrecorder                      # Recorder for Picovoice

PICOVOICE

    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" || "$PI_VERSION" == "pi3" ]]; then
        cat >> "$req_file" << 'VOSK'

# === LOCAL STT (Pi3/Pi4/Pi5) ===
vosk                            # Offline speech recognition

VOSK
    fi

    cat >> "$req_file" << 'LOCALTTS'

# === LOCAL TTS (All Pi versions) ===
piper-tts                       # Local TTS with voice cloning support

LOCALTTS

    if [[ "$PI_VERSION" == "pi5" ]]; then
        cat >> "$req_file" << 'HEAVY'

# === HEAVY PROCESSING (Pi5 only) ===
faster-whisper                  # Local STT using Faster Whisper
silero-vad                      # Voice Activity Detection (VAD) using Silero
omegaconf                       # Required for silero speech
fastrtc[vad, stt, tts]          # FastRTC for real-time communication
librosa                         # Audio analysis and feature extraction

# Emotion Detection (Pi5 only)
optimum[onnxruntime]            # ONNX model optimization

HEAVY
    fi

    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'UI'

# === UI & CAMERA (Pi4/Pi5) ===
PyOpenGL                        # OpenGL support
PyOpenGL-accelerate             # OpenGL acceleration
picamera2                       # PI camera module
opencv-python                   # Video classes and modifiers
simplejpeg                      # Camera Requirement
numpy==2.1                      # Needed for image rotations
moviepy                         # Video editing and playback support
evdev                           # Handle Linux input devices

UI
    fi

    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'CLOUDTTS'

# === CLOUD TTS OPTIONS (Pi4/Pi5) ===
elevenlabs                      # External TTS using 11Labs API
azure-cognitiveservices-speech  # Azure TTS API

CLOUDTTS
    fi

    if [[ "$PI_VERSION" == "pi3" || "$PI_VERSION" == "pizero2" ]]; then
        cat >> "$req_file" << 'CLOUDONLY'

# === CLOUD TTS (Pi3/Zero2) ===
elevenlabs                      # External TTS using 11Labs API

CLOUDONLY
    fi

    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'DISCORD'

DISCORD
    fi

    if [[ "$PI_VERSION" == "pi5" ]]; then
        cat >> "$req_file" << 'YOUTUBE'

# === MEDIA (Pi5) ===
yt-dlp                          # Youtube downloading
pandas                          # Data analysis

YOUTUBE
    fi

    tars_say "Requirements file generated: $req_file" "success"
    
    echo "+===============================================================+"
    echo "| PACKAGES TO BE INSTALLED:"
    echo "+===============================================================+"
    grep -v "^#" "$req_file" | grep -v "^$" | while read line; do
        echo "|  - $line"
    done
    echo "+===============================================================+"
    echo ""
}

update_config_device() {
    if [ "$HAS_DEVICE_SECTION" = false ]; then
        tars_say "No [DEVICE] section in config — skipping device profile update." "info"
        return 0
    fi

    local config_file="config.ini"
    
    if [ -f "$config_file" ]; then
        tars_say "Updating config.ini with device profile..." "info"
        
        if grep -q "^\[DEVICE\]" "$config_file"; then
            sed -i "s/^raspberry_version\s*=.*/raspberry_version = $PI_VERSION/" "$config_file"
        else
            sed -i "1i\\
[DEVICE]\\
raspberry_version = $PI_VERSION\\
" "$config_file"
        fi
        
        tars_say "Device profile set to: $PI_VERSION" "success"
    fi
}

show_system_diagnostic() {
    echo "+===============================================================+"
    echo "|           SYSTEM DIAGNOSTIC INITIATED                         |"
    echo "+===============================================================+"
    echo "| CPU Architecture: $(uname -m)"
    echo "| Kernel Version:   $(uname -r)"
    echo "| Hostname:         $(hostname)"
    echo "| Pi Version:       ${PI_VERSION^^}"
    echo "+===============================================================+"
    echo ""
}

spin_loader() {
    local pid=$1
    local message=$2
    local timeout=${3:-300}
    local spin='|/-\'
    local i=0
    local elapsed=0
    
    echo -ne "|  "
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) %4 ))
        echo -ne "\r|  ${spin:$i:1} ${message} (${elapsed}s)"
        sleep 1
        elapsed=$((elapsed + 1))
        
        if [ $elapsed -ge $timeout ]; then
            kill -9 $pid 2>/dev/null || true
            echo -ne "\r|  [X] ${message} - TIMEOUT after ${timeout}s\n"
            return 1
        fi
    done
    
    wait $pid
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -ne "\r|  [OK] ${message} (${elapsed}s)\n"
        return 0
    else
        echo -ne "\r|  [X] ${message} - FAILED with exit code $exit_code\n"
        return 1
    fi
}

retry_pip_install() {
    local n=1
    local max=5
    local delay=5
    local req_file="$HOME/.local/share/tars_a/requirements_${PI_VERSION}.txt"

    tars_say "Initiating Python dependency installation for ${PI_VERSION^^}..." "info"
    
    while true; do
        echo "+===============================================================+"
        echo "| Attempt: $n/$max"
        echo "+===============================================================+"
        
        if pip install -r "$req_file"; then
            tars_say "Python dependencies synchronized successfully." "success"
            break
        else
            if [[ $n -lt $max ]]; then
                tars_say "Connection interference detected. Retrying in $delay seconds..." "warning"
                for ((i=delay; i>0; i--)); do
                    echo -ne "\r|  >>> Retry countdown: $i seconds... "
                    sleep 1
                done
                echo ""
                ((n++))
            else
                tars_say "Critical failure. Unable to establish connection after $max attempts." "error"
                exit 1
            fi
        fi
    done
}

detect_os_version() {
    tars_say "Analyzing operating system parameters..." "info"
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_VERSION_ID=$VERSION_ID
        OS_VERSION_CODENAME=$VERSION_CODENAME
        
        echo "+===============================================================+"
        echo "| OPERATING SYSTEM DETECTED"
        echo "+===============================================================+"
        echo "| System:   $PRETTY_NAME"
        echo "| Codename: $VERSION_CODENAME"
        echo "| Version:  $VERSION_ID"
        echo "+===============================================================+"
        echo ""
        sleep 1
    else
        tars_say "Unable to determine OS version. Proceeding with adaptive protocol." "warning"
        OS_VERSION_CODENAME="unknown"
    fi
}

install_chromium() {
    if [[ "$PI_VERSION" == "pi3" || "$PI_VERSION" == "pizero2" ]]; then
        tars_say "Skipping Chromium installation (UI disabled for ${PI_VERSION^^})" "info"
        return 0
    fi

    tars_say "Initiating chromium installation sequence..." "info"
    
    echo "+===============================================================+"
    echo "| CHROMIUM INSTALLATION PROTOCOL"
    echo "+===============================================================+"
    
    if apt-cache show chromium &>/dev/null; then
        echo "|  Package detected: chromium (Latest variant)"
        
        if ! sudo apt install -y chromium sox libsox-fmt-all portaudio19-dev espeak-ng libcap-dev --fix-missing 2>&1 | tee /tmp/chromium-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
            tars_say "Chromium installation encountered issues. Check /tmp/chromium-install.log" "warning"
        fi
        CHROMIUM_CMD="chromium"
    elif apt-cache show chromium-browser &>/dev/null; then
        echo "|  Package detected: chromium-browser (Legacy variant)"
        
        if ! sudo apt install -y chromium-browser sox libsox-fmt-all portaudio19-dev espeak-ng libcap-dev --fix-missing 2>&1 | tee /tmp/chromium-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
            tars_say "Chromium-browser installation encountered issues. Check /tmp/chromium-install.log" "warning"
        fi
        CHROMIUM_CMD="chromium-browser"
    else
        tars_say "Chromium package not found in repositories. Manual intervention required." "error"
        exit 1
    fi
    
    install_chromedriver
    
    echo ""
}

install_chromedriver() {
    tars_say "ChromeDriver installation protocol engaged..." "info"
    
    echo "+===============================================================+"
    echo "| CHROMEDRIVER CONFIGURATION"
    echo "+===============================================================+"
    
    if command -v chromedriver &>/dev/null; then
        echo "| Status: Already present in system"
        VERSION=$(chromedriver --version 2>/dev/null | head -1)
        echo "| Version: $VERSION"
        echo "+===============================================================+"
        return 0
    fi
    
    if apt-cache show chromium-driver &>/dev/null; then
        echo "| Method: Package Manager (chromium-driver)"
        echo "+===============================================================+"
        
        if ! sudo apt install -y chromium-driver 2>&1 | tee /tmp/chromedriver-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
            tars_say "ChromeDriver installation encountered issues. Check /tmp/chromedriver-install.log" "warning"
        fi
    else
        tars_say "ChromeDriver not found in repositories" "warning"
    fi
}

create_desktop_shortcut() {
    if [[ "$PI_VERSION" == "pi3" || "$PI_VERSION" == "pizero2" ]]; then
        tars_say "Skipping desktop shortcut (no UI for ${PI_VERSION^^})" "info"
        return 0
    fi

    tars_say "Creating desktop shortcut..." "info"

    local install_dir
    install_dir="$(cd .. && pwd)"

    local desktop_dir
    if [ -n "$SUDO_USER" ]; then
        desktop_dir="$(eval echo ~$SUDO_USER)/Desktop"
    else
        desktop_dir="$HOME/Desktop"
    fi

    mkdir -p "$desktop_dir"

    local desktop_file="${desktop_dir}/TARS"
    cat > "$desktop_file" << LAUNCHER
#!/bin/bash
echo "=== TARS Launcher ==="
echo ""
cd "${install_dir}" || { echo "ERROR: Could not cd to ${install_dir}"; read -p "Press Enter to close..."; exit 1; }
source src/.venv/bin/activate || { echo "ERROR: Could not activate venv"; read -p "Press Enter to close..."; exit 1; }
python App-Start.py
echo ""
read -p "Press Enter to close..."
LAUNCHER

    chmod +x "$desktop_file"
    sudo chown $ACTUAL_USER:$ACTUAL_USER "$desktop_file" 2>/dev/null

    tars_say "Desktop shortcut created: $desktop_file" "success"
    echo "|  Double-click the TARS icon and select 'Execute in Terminal' to launch."
    echo ""
}

main() {
    show_tars_boot
    
    select_pi_version
    
    show_system_diagnostic
    detect_os_version
    
    tars_say "Executing system update protocol..." "info"
    echo "+===============================================================+"
    echo "| SYSTEM UPDATE IN PROGRESS"
    echo "+===============================================================+"
    if ! sudo apt update 2>&1 | tail -5; then
        tars_say "System update had warnings but continuing..." "warning"
    fi
    echo ""
    
    install_chromium
    
    tars_say "Installing system dependencies..." "info"
    
    if [[ "$PI_VERSION" == "pi5" ]]; then
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng libcap-dev sox libsox-fmt-all git swig python3-libcamera python3-kms++ 2>&1 | tail -10
    elif [[ "$PI_VERSION" == "pi4" ]]; then
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng libcap-dev sox libsox-fmt-all git python3-libcamera python3-kms++ 2>&1 | tail -10
    else
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng git 2>&1 | tail -10
    fi
    
    if [[ "$PI_VERSION" == "pi5" ]]; then
        local multiarch_lib="/usr/lib/aarch64-linux-gnu"
        if [ -f "$multiarch_lib/liblgpio.so.1" ] && [ ! -f "$multiarch_lib/liblgpio.so" ]; then
            tars_say "Creating lgpio dev symlink (Trixie fix)..." "info"
            sudo ln -sf "$multiarch_lib/liblgpio.so.1" "$multiarch_lib/liblgpio.so"
            sudo ldconfig
            tars_say "lgpio dev symlink created." "success"
        fi
    fi

    tars_say "Initializing Python virtual environment..." "info"
    
    cd src
    
    if [ -d ".venv" ]; then
        echo "+===============================================================+"
        echo "| EXISTING VIRTUAL ENVIRONMENT DETECTED"
        echo "+===============================================================+"
        echo "| Keeping existing environment - will install missing packages"
        echo "+===============================================================+"
        tars_say "Keeping existing virtual environment." "info"
        if [ -f ".venv/pyvenv.cfg" ]; then
            if grep -q "include-system-site-packages = false" .venv/pyvenv.cfg; then
                sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' .venv/pyvenv.cfg
                tars_say "Enabled system-site-packages in existing venv (needed for libcamera)." "info"
            fi
        fi
    else
        python3 -m venv --system-site-packages .venv
        tars_say "Virtual environment created (with system-site-packages for libcamera)." "success"
    fi
    
    source .venv/bin/activate
    tars_say "Virtual environment activated." "info"
    
    generate_requirements
    
    tars_say "Resolving potential package conflicts..." "info"
    sudo apt remove -y python3-simplejpeg python3-picamera2 2>&1 | tail -5 || true
    echo "|  [OK] System package conflicts resolved"
    echo ""
    
    tars_say "Upgrading package installer..." "info"
    if ! pip install --upgrade pip 2>&1 | tail -10; then
        echo "| [!] Pip upgrade had issues but continuing..."
    fi
    echo ""
    
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        tars_say "Installing critical Python modules..." "info"
        pip uninstall -y numpy simplejpeg picamera2 2>/dev/null || true
        
        if ! pip install --no-cache-dir numpy==2.1 simplejpeg picamera2 2>&1 | tee /tmp/core-deps.log | tail -20; then
            echo "| [!] Core dependency installation had issues"
            echo "| See /tmp/core-deps.log for details"
        fi
        echo ""
    fi
    
    retry_pip_install
    
    tars_say "Initializing configuration files..." "info"

    if [ ! -f "config.ini" ]; then
        cp config.ini.template config.ini
    fi
    sudo chown $ACTUAL_USER:$ACTUAL_USER config.ini 2>/dev/null
    chmod 664 config.ini
    echo "|  [OK] config.ini (writable, run: nano config.ini)"

    update_config_device

    if [ ! -f "dashboard.ini" ]; then
        cp dashboard.template.ini dashboard.ini
    fi
    sudo chown $ACTUAL_USER:$ACTUAL_USER dashboard.ini 2>/dev/null
    chmod 664 dashboard.ini
    echo "|  [OK] dashboard.ini (writable, run: nano dashboard.ini)"
    
    cd ..
    if [ ! -f ".env" ]; then
        cp .env.template .env
    fi
    sudo chown $ACTUAL_USER:$ACTUAL_USER .env 2>/dev/null
    chmod 664 .env
    echo "|  [OK] .env (writable, run: nano .env)"
    echo "|  Note: .env is hidden (starts with .) - use 'ls -la' to see it"
    
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER . 2>/dev/null || true
    chmod -R 775 . 2>/dev/null || true
    
    cd src
    echo ""
    
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:0
        echo "|  Display configuration set: $DISPLAY"
    else
        echo "|  Display configuration preserved: $DISPLAY"
    fi
    echo ""
    
    tars_say "Final system verification..." "info"
    cd ..
    
    sudo chattr -R -i . 2>/dev/null || true
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER .
    chmod -R 775 .
    
    TEST_DIRS=("src/modules" "src/logs" "src/data" "src")
    ALL_WRITABLE=true
    
    for dir in "${TEST_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            if sudo -u $ACTUAL_USER touch "$dir/.test_write" 2>/dev/null; then
                rm "$dir/.test_write"
                echo "|  [OK] $dir is writable"
            else
                echo "|  [X] $dir is NOT writable - manual fix needed"
                ALL_WRITABLE=false
            fi
        fi
    done
    
    if [ "$ALL_WRITABLE" = false ]; then
        echo "|  "
        echo "|  [!] WARNING: Some directories are not writable!"
        echo "|  Run these commands manually:"
        echo "|      cd ~/TARS-AI"
        echo "|      sudo chown -R $ACTUAL_USER:$ACTUAL_USER ."
        echo "|      chmod -R 775 ."
    else
        echo "|  [OK] All directories verified writable"
    fi
    echo ""
    cd src
    

    CURRENT_DIR=$(pwd)
    
    if [ -f "config.ini" ]; then
        echo "+===============================================================+"
        echo "| CONFIG SYNCHRONIZATION"
        echo "+===============================================================+"
        
        tars_say "Synchronizing config.ini file..." "info"
        
        if [ -f ".venv/bin/activate" ]; then
            source .venv/bin/activate
        fi
        
        if [ -f "app_cms.py" ]; then
            echo "| Executing: python app_cms.py"
            echo "+===============================================================+"
            echo ""
            python app_cms.py
            tars_say "Config synchronization complete." "success"
        else
            tars_say "Warning: app_cms.py not found. Skipping config sync." "warning"
        fi
    else
        tars_say "Warning: config.ini not found. Skipping config sync." "warning"
    fi
    
    echo ""
    
    WAKEWORD_DIR="$HOME/.local/share/tars_ai"
    
    if [ -d "$WAKEWORD_DIR" ]; then
        echo "+===============================================================+"
        echo "| WAKEWORD TEMPLATE DETECTED"
        echo "+===============================================================+"
        echo "| Location: $WAKEWORD_DIR"
        echo "+===============================================================+"
        echo ""
        
        read -t 30 -p "Would you like to delete the wakeword template in order to create a new one? [y/n]: " -r WAKEWORD_REPLY
        echo ""
        
        if [[ $WAKEWORD_REPLY =~ ^[Yy]$ ]]; then
            tars_say "Removing wakeword template directory..." "info"
            
            if rm -rf "$WAKEWORD_DIR" 2>/dev/null; then
                tars_say "Wakeword template directory successfully removed." "success"
            else
                tars_say "Failed to remove wakeword template directory. You may need to remove it manually." "warning"
                echo "| Run manually: rm -rf $WAKEWORD_DIR"
            fi
        else
            echo ""
            echo "Wakeword template directory preserved."
            echo "You can delete it later with: rm -rf $WAKEWORD_DIR"
        fi
        echo ""
    fi

    cat << EOF
    +==============================================================+
    |                                                              |
    |              [OK] INSTALLATION COMPLETE                      |
    |                                                              |
    |              Device Profile: ${PI_VERSION^^}
    |              All systems operational.                        |
    |              TARS unit ALMOST ready for deployment.          |
    |                                                              |
    +==============================================================+
EOF
    
    cd ..
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER . 2>/dev/null || true
    chmod -R 775 . 2>/dev/null || true
    cd src
    
    rm -f "$HOME/.local/share/tars_a/requirements_${PI_VERSION}.txt"
    
    echo ""    
    echo "*** Set your .env variables (API Keys) before running the program"
    echo ""
    
    case $PI_VERSION in
        "pi5")
            echo "*** Pi5: Full features enabled. All STT/TTS options available."
            ;;
        "pi4")
            echo "*** Pi4: Using Vosk STT and Piper TTS. FastRTC/Silero disabled."
            ;;
        "pi3")
            echo "*** Pi3: Lite mode. Using cloud STT. Piper TTS available locally."
            echo "*** Set ttsoption=piper, openai, or elevenlabs in config.ini"
            ;;
        "pizero2")
            echo "*** Zero2: Minimal mode. OpenAI STT. Piper TTS available locally."
            echo "*** Set ttsoption=piper for local TTS or openai for cloud TTS"
            ;;
    esac
    
    echo ""
    echo "*** Run the program in Terminal mode the first times in the App-Start Menu ***"
    echo "IMPORTANT: Run your application as user '$ACTUAL_USER' (without sudo)"    
    echo "Start the program: python App-Start.py"
    echo ""
    echo "Enable the virtual environment: source .venv/bin/activate if not using App-Start.py"
    echo ""
    
    create_desktop_shortcut
    select_thirdparty_apps
    install_retropie
    install_raspotify
}

main