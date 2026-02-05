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
    fi

    if [ "$has_device_section" = false ]; then
        PI_VERSION="pi5"
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
    echo "|  3) Raspberry Pi 3      - Lite mode, cloud STT/TTS only       |"
    echo "|  4) Raspberry Pi Zero 2 - Minimal, cloud-only processing      |"
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
            echo "| Features: Cloud STT/TTS, keyword memory, no UI"
            echo "| Memory:   Lite keyword-based memory"
            echo "| Size:     ~500MB dependencies"
            ;;
        "pizero2")
            echo "| Features: OpenAI STT/TTS only, keyword memory, no UI"
            echo "| Memory:   Lite keyword-based memory"
            echo "| Size:     ~300MB dependencies"
            ;;
    esac
    
    echo "+===============================================================+"
    echo ""
}

generate_requirements() {
    local req_dir="$HOME/.local/share/tars_a"
    mkdir -p "$req_dir"
    local req_file="$req_dir/requirements_${PI_VERSION}.txt"
    
    tars_say "Generating requirements for ${PI_VERSION^^}..." "info"
    
    # Common requirements for ALL Pi versions
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
flask-cors                      # Cross-Origin Resource Sharing (CORS) for Flask
flask-socketio                  # WebSockets support for Flask
eventlet                        # Async support for Flask-SocketIO

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

COMMON

    # Pi5 only: lgpio for GPIO control
    if [[ "$PI_VERSION" == "pi5" ]]; then
        cat >> "$req_file" << 'LGPIO'

# === GPIO (Pi5 only) ===
lgpio                           # Required for Raspberry Pi 5 GPIO

LGPIO
    fi

    # Pi5 and Pi4: Add embedding and local processing
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

    # Pi5, Pi4, Pi3, PiZero2: Picovoice wake word (lightweight, works on all)
    cat >> "$req_file" << 'PICOVOICE'

# === WAKE WORD (All Pi versions) ===
pvporcupine                     # Wake word detection by Picovoice
pvrecorder                      # Recorder for Picovoice

PICOVOICE

    # Pi5, Pi4, Pi3: Add Vosk for local STT
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" || "$PI_VERSION" == "pi3" ]]; then
        cat >> "$req_file" << 'VOSK'

# === LOCAL STT (Pi3/Pi4/Pi5) ===
vosk                            # Offline speech recognition

VOSK
    fi

    # Pi5 and Pi4: Add local TTS options
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'LOCALTTS'

# === LOCAL TTS (Pi4/Pi5) ===
piper-tts                       # Local TTS with voice cloning support

LOCALTTS
    fi

    # Pi5 only: Add heavy processing (faster-whisper, fastrtc, silero)
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

    # Pi5 and Pi4: Add UI and camera support
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'UI'

# === UI & CAMERA (Pi4/Pi5) ===
pygame                          # Game development & multimedia support
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

    # Pi5 and Pi4: Add cloud TTS options
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'CLOUDTTS'

# === CLOUD TTS OPTIONS (Pi4/Pi5) ===
elevenlabs                      # External TTS using 11Labs API
azure-cognitiveservices-speech  # Azure TTS API

CLOUDTTS
    fi

    # Pi3 and Zero2: Add minimal cloud TTS
    if [[ "$PI_VERSION" == "pi3" || "$PI_VERSION" == "pizero2" ]]; then
        cat >> "$req_file" << 'CLOUDONLY'

# === CLOUD TTS (Pi3/Zero2) ===
elevenlabs                      # External TTS using 11Labs API

CLOUDONLY
    fi

    # Pi5 and Pi4: UI and heavy media support
    if [[ "$PI_VERSION" == "pi5" || "$PI_VERSION" == "pi4" ]]; then
        cat >> "$req_file" << 'DISCORD'

DISCORD
    fi

    # Pi5: YouTube support
    if [[ "$PI_VERSION" == "pi5" ]]; then
        cat >> "$req_file" << 'YOUTUBE'

# === MEDIA (Pi5) ===
yt-dlp                          # Youtube downloading
pandas                          # Data analysis

YOUTUBE
    fi

    tars_say "Requirements file generated: $req_file" "success"
    
    # Show what will be installed
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
    local config_file="config.ini"
    
    if [ -f "$config_file" ]; then
        tars_say "Updating config.ini with device profile..." "info"
        
        # Check if [DEVICE] section exists
        if grep -q "^\[DEVICE\]" "$config_file"; then
            # Update existing raspberry_version
            sed -i "s/^raspberry_version\s*=.*/raspberry_version = $PI_VERSION/" "$config_file"
        else
            # Add [DEVICE] section at the beginning of the file
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
    # Skip chromium for Pi3 and Zero2 (no UI)
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

main() {
    show_tars_boot
    
    # === NEW: Select Pi version first ===
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
    
    # Install base packages (reduced for lite profiles)
    tars_say "Installing system dependencies..." "info"
    
    if [[ "$PI_VERSION" == "pi5" ]]; then
        # Pi5: Full system dependencies + swig for lgpio + libcamera for picamera2
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng libcap-dev sox libsox-fmt-all git swig python3-libcamera python3-kms++ 2>&1 | tail -10
    elif [[ "$PI_VERSION" == "pi4" ]]; then
        # Pi4: Full system dependencies + libcamera for picamera2 (no swig needed)
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng libcap-dev sox libsox-fmt-all git python3-libcamera python3-kms++ 2>&1 | tail -10
    else
        # Minimal system dependencies for Pi3/Zero2
        sudo apt install -y python3-pip python3-venv python3-dev portaudio19-dev espeak-ng git 2>&1 | tail -10
    fi
    
    # Trixie ships liblgpio.so.1 but not the dev symlink liblgpio.so,
    # which causes "cannot find -llgpio" when pip builds the lgpio wheel.
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
        # Ensure system-site-packages is enabled (needed for libcamera)
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
    
    # === NEW: Generate requirements based on Pi version ===
    generate_requirements
    
    # Resolve package conflicts
    tars_say "Resolving potential package conflicts..." "info"
    sudo apt remove -y python3-simplejpeg python3-picamera2 2>&1 | tail -5 || true
    echo "|  [OK] System package conflicts resolved"
    echo ""
    
    tars_say "Upgrading package installer..." "info"
    if ! pip install --upgrade pip 2>&1 | tail -10; then
        echo "| [!] Pip upgrade had issues but continuing..."
    fi
    echo ""
    
    # Only install camera dependencies for Pi5/Pi4
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

    # === NEW: Update config.ini with device profile ===
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
    
    # Cleanup generated requirements file
    rm -f "$HOME/.local/share/tars_a/requirements_${PI_VERSION}.txt"
    
    echo ""    
    echo "*** Set your .env variables (API Keys) before running the program"
    echo ""
    
    # Show profile-specific notes
    case $PI_VERSION in
        "pi5")
            echo "*** Pi5: Full features enabled. All STT/TTS options available."
            ;;
        "pi4")
            echo "*** Pi4: Using Vosk STT and Piper TTS. FastRTC/Silero disabled."
            ;;
        "pi3")
            echo "*** Pi3: Lite mode. Using cloud STT/TTS. UI disabled."
            echo "*** Set ttsoption=openai or elevenlabs in config.ini"
            ;;
        "pizero2")
            echo "*** Zero2: Minimal mode. OpenAI STT/TTS only. UI disabled."
            echo "*** Requires OPENAI_API_KEY in .env"
            ;;
    esac
    
    echo ""
    echo "*** Run the program in Terminal mode the first times in the App-Start Menu ***"
    echo "IMPORTANT: Run your application as user '$ACTUAL_USER' (without sudo)"    
    echo "Start the program: python App-Start.py"
    echo ""
    echo "Enable the virtual environment: source .venv/bin/activate if not using App-Start.py"
    echo ""
}

main