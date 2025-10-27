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

show_system_diagnostic() {
    echo "+===============================================================+"
    echo "|           SYSTEM DIAGNOSTIC INITIATED                         |"
    echo "+===============================================================+"
    echo "| CPU Architecture: $(uname -m)"
    echo "| Kernel Version:   $(uname -r)"
    echo "| Hostname:         $(hostname)"
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

    tars_say "Initiating Python dependency installation protocol..." "info"
    
    while true; do
        echo "+===============================================================+"
        echo "| Attempt: $n/$max"
        echo "+===============================================================+"
        
        if pip install -r requirements.txt; then
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
    tars_say "Initiating chromium installation sequence..." "info"
    
    echo "+===============================================================+"
    echo "| CHROMIUM INSTALLATION PROTOCOL"
    echo "+===============================================================+"
    
    if apt-cache show chromium &>/dev/null; then
        echo "|  Package detected: chromium (Latest variant)"
        
        if ! sudo apt install -y chromium sox libsox-fmt-all portaudio19-dev espeak-ng --fix-missing 2>&1 | tee /tmp/chromium-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
            tars_say "Chromium installation encountered issues. Check /tmp/chromium-install.log" "warning"
        fi
        CHROMIUM_CMD="chromium"
    elif apt-cache show chromium-browser &>/dev/null; then
        echo "|  Package detected: chromium-browser (Legacy variant)"
        
        if ! sudo apt install -y chromium-browser sox libsox-fmt-all portaudio19-dev espeak-ng --fix-missing 2>&1 | tee /tmp/chromium-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
            tars_say "Chromium-browser installation encountered issues. Check /tmp/chromium-install.log" "warning"
        fi
        CHROMIUM_CMD="chromium-browser"
    else
        tars_say "Chromium package not found in repositories. Manual intervention required." "error"
        exit 1
    fi
    
    install_chromedriver
    
    if ! sudo apt install -y xterm libcap-dev --fix-missing 2>&1 | tee /tmp/aux-install.log | grep -v "^Setting up\|^Preparing\|^Unpacking" | head -20; then
        tars_say "Auxiliary dependency installation encountered issues. Check /tmp/aux-install.log" "warning"
    fi
    
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
        
        if command -v chromedriver &>/dev/null; then
            tars_say "ChromeDriver installed successfully." "success"
        else
            tars_say "ChromeDriver installation verification failed." "error"
            exit 1
        fi
    else
        echo "| Method: Manual Installation (Latest Stable)"
        echo "+===============================================================+"
        
        tars_say "Fetching latest stable ChromeDriver version..." "info"
        
        LATEST_STABLE=$(curl -s https://chromedriver.storage.googleapis.com/LATEST_RELEASE)
        
        if [ -z "$LATEST_STABLE" ]; then
            tars_say "Unable to determine ChromeDriver version. Manual installation required." "error"
            exit 1
        fi
        
        echo "| Target Version: $LATEST_STABLE"
        
        DRIVER_URL="https://chromedriver.storage.googleapis.com/${LATEST_STABLE}/chromedriver_linux64.zip"
        TEMP_DIR=$(mktemp -d)
        
        echo "| Downloading from: $DRIVER_URL"
        
        if ! wget -q "$DRIVER_URL" -O "$TEMP_DIR/chromedriver.zip" 2>&1 | tail -5; then
            tars_say "ChromeDriver download failed. Check network connection." "error"
            rm -rf "$TEMP_DIR"
            exit 1
        fi
        
        if ! unzip -q "$TEMP_DIR/chromedriver.zip" -d "$TEMP_DIR"; then
            tars_say "ChromeDriver extraction failed." "error"
            rm -rf "$TEMP_DIR"
            exit 1
        fi
        
        sudo mv "$TEMP_DIR/chromedriver" /usr/local/bin/
        sudo chmod +x /usr/local/bin/chromedriver
        
        rm -rf "$TEMP_DIR"
        
        if command -v chromedriver &>/dev/null; then
            VERSION=$(chromedriver --version 2>/dev/null | head -1)
            echo "| Status: Installation Complete"
            echo "| Version: $VERSION"
            echo "+===============================================================+"
            tars_say "ChromeDriver deployed successfully." "success"
        else
            tars_say "ChromeDriver verification failed after installation." "error"
            exit 1
        fi
    fi
}

verify_installations() {
    tars_say "Verifying system dependencies..." "info"
    
    echo "+===============================================================+"
    echo "| DEPENDENCY VERIFICATION"
    echo "+===============================================================+"
    
    local MISSING_DEPS=()
    
    for cmd in python3 pip chromium chromedriver sox portaudio19-dev espeak-ng; do
        if command -v $cmd &>/dev/null || dpkg -l | grep -q $cmd; then
            echo "|  [OK] $cmd"
        else
            echo "|  [X] $cmd - NOT FOUND"
            MISSING_DEPS+=("$cmd")
        fi
    done
    
    echo "+===============================================================+"
    
    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        tars_say "Critical dependencies missing: ${MISSING_DEPS[*]}" "error"
        exit 1
    else
        tars_say "All dependencies verified and operational." "success"
    fi
}

main() {
    show_tars_boot
    show_system_diagnostic
    
    tars_say "Synchronizing package databases with repositories..." "info"
    echo "+===============================================================+"
    echo "| APT-GET UPDATE OUTPUT"
    echo "+===============================================================+"
    
    INITIAL_UPDATE_LOG="/tmp/tars-apt-initial-update.log"
    
    if ! sudo apt-get update 2>&1 | tee "$INITIAL_UPDATE_LOG"; then
        echo ""
        echo "+===============================================================+"
        echo "| [X] APT-GET UPDATE FAILED"
        echo "+===============================================================+"
        echo "| Full error log saved to: $INITIAL_UPDATE_LOG"
        echo "| "
        echo "| Troubleshooting steps:"
        echo "|   1. Check your internet connection"
        echo "|   2. Run: sudo rm -rf /var/lib/apt/lists/*"
        echo "|   3. Run: sudo mkdir -p /var/lib/apt/lists/partial"
        echo "|   4. Run: sudo apt-get update"
        echo "|   5. Check /etc/apt/sources.list for errors"
        echo "+===============================================================+"
        
        tars_say "Package database synchronization failed. Cannot proceed." "error"
        exit 1
    fi
    
    echo ""
    echo "+===============================================================+"
    echo "| [OK] Package databases synchronized successfully"
    echo "+===============================================================+"
    echo ""
    sleep 2
    
    tars_say "Upgrading system packages with apt-get upgrade..." "info"
    echo "+===============================================================+"
    echo "| APT-GET UPGRADE OUTPUT"
    echo "+===============================================================+"
    echo "| NOTE: This may take several minutes depending on updates..."
    echo "+===============================================================+"
    
    UPGRADE_LOG_FILE="/tmp/tars-apt-upgrade.log"
    
    echo ""
    if ! sudo apt-get upgrade -y 2>&1 | tee "$UPGRADE_LOG_FILE"; then
        echo ""
        echo "+===============================================================+"
        echo "| [!] APT-GET UPGRADE HAD ISSUES"
        echo "+===============================================================+"
        echo "| Full log saved to: $UPGRADE_LOG_FILE"
        echo "| "
        echo "| The script will continue, but some packages may not be current"
        echo "+===============================================================+"
        tars_say "Package upgrade completed with warnings. Continuing..." "warning"
        sleep 3
    else
        echo ""
        echo "+===============================================================+"
        echo "| [OK] System packages upgraded successfully"
        echo "+===============================================================+"
        echo ""
        sleep 2
    fi
    
    detect_os_version
    install_chromium
    verify_installations
    
    tars_say "Verifying project structure..." "info"
    if [ ! -d "src" ]; then
        tars_say "Critical error: 'src' directory not found. Installation cannot proceed." "error"
        exit 1
    fi
    echo "|  [OK] Project directory confirmed: src/"
    echo ""
    
    tars_say "Setting project permissions..." "info"
    sudo chattr -R -i . 2>/dev/null || true
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER .
    chmod -R 775 .
    echo "|  [OK] Ownership set to: $ACTUAL_USER"
    echo "|  [OK] All directories now writable (775)"
    
    mkdir -p src/modules src/logs src/data 2>/dev/null || true
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER src/modules src/logs src/data 2>/dev/null || true
    chmod -R 775 src/modules src/logs src/data 2>/dev/null || true
    echo "|  [OK] Critical subdirectories verified"
    echo ""
    
    cd src
    
    tars_say "Constructing Python virtual environment..." "info"
    
    if ! python3 -m venv .venv --system-site-packages 2>&1 | tee /tmp/venv-creation.log | tail -10; then
        echo "| [X] Virtual environment creation failed"
        echo "| See /tmp/venv-creation.log for details"
        exit 1
    fi
    echo ""
    
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "|  [OK] Virtual environment activated"
        echo ""
    else
        tars_say "Virtual environment activation failed. Critical system error." "error"
        exit 1
    fi
    
    tars_say "Configuring virtual environment permissions..." "info"
    cd ..
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER src/.venv/
    chmod -R 775 src/.venv/
    echo "|  [OK] Virtual environment permissions set (775)"
    cd src
    echo ""
    
    tars_say "Removing conflicting system packages..." "info"
    sudo apt remove -y python3-simplejpeg python3-picamera2 2>&1 | tail -5 || true
    echo "|  [OK] System package conflicts resolved"
    echo ""
    
    tars_say "Upgrading package installer..." "info"
    if ! pip install --upgrade pip 2>&1 | tail -10; then
        echo "| [!] Pip upgrade had issues but continuing..."
    fi
    echo ""
    
    tars_say "Installing critical Python modules..." "info"
    pip uninstall -y numpy simplejpeg picamera2 2>/dev/null || true
    
    if ! pip install --no-cache-dir numpy==2.1 simplejpeg picamera2 2>&1 | tee /tmp/core-deps.log | tail -20; then
        echo "| [!] Core dependency installation had issues"
        echo "| See /tmp/core-deps.log for details"
    fi
    echo ""
    
    retry_pip_install
    
    tars_say "Initializing configuration files..." "info"
    
    if [ ! -f "config.ini" ]; then
        cp config.ini.template config.ini
    fi
    sudo chown $ACTUAL_USER:$ACTUAL_USER config.ini 2>/dev/null
    chmod 664 config.ini
    echo "|  [OK] config.ini (writable, run: nano config.ini)"
    
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
    
    export DISPLAY=:0
    echo "|  Display configuration: $DISPLAY"
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
    

    # Check current directory and config.ini status
    CURRENT_DIR=$(pwd)
    echo "+===============================================================+"
    echo "| DEBUG: Current directory: $CURRENT_DIR"
    
    if [ -f "config.ini" ]; then
        echo "| DEBUG: config.ini FOUND in current directory"
        echo "+===============================================================+"
        echo ""
        echo "+===============================================================+"
        echo "| CMS APPLICATION LAUNCHER"
        echo "+===============================================================+"
        echo ""
        
        # Use a more explicit prompt with timeout
        read -t 30 -p "Would you like to run synchronize the config.ini file (recommended)? [y/n]: " -r REPLY
        echo ""
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            tars_say "Launching CMS application..." "info"
            echo ""
            
            # Ensure we're in the correct directory and virtual environment is active
            if [ -f ".venv/bin/activate" ]; then
                source .venv/bin/activate
                echo "| Virtual environment activated"
            fi
            
            # Check if app_csm.py exists
            if [ -f "app_cms.py" ]; then
                echo "| Executing: python app_csm.py"
                echo "+===============================================================+"
                echo ""
                python app_cms.py
            else
                tars_say "Error: app_cms.py not found in src directory." "error"
                echo "| Expected location: $CURRENT_DIR/app_cms.py"
                echo "| Contents of directory:"
                ls -la | grep "app_"
            fi
        else
            echo ""
            echo "CMS application launch skipped."
            echo "You can run it later with:"
            echo "  cd $(dirname $CURRENT_DIR)/src"
            echo "  source .venv/bin/activate"
            echo "  python app_cms.py"
        fi
    else
        echo "| DEBUG: config.ini NOT FOUND in current directory"
        echo "| Contents of current directory:"
        ls -la config* 2>/dev/null || echo "| No config files found"
        echo "+===============================================================+"
        echo ""
        echo "Note: CMS launcher requires config.ini to be present."
    fi
    
    echo ""
    
    # Check for wakeword template and offer deletion
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

    cat << "EOF"
    +==============================================================+
    |                                                              |
    |              [OK] INSTALLATION COMPLETE                      |
    |                                                              |
    |              All systems operational.                        |
    |              TARS unit ready for deployment.                 |
    |                                                              |
    |                                                              |
    +==============================================================+
EOF
    
    cd ..
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER . 2>/dev/null || true
    chmod -R 775 . 2>/dev/null || true
    cd src
    
    echo ""    
    echo "*** Set your .env variables (API Keys) before running the program"
    echo ""
    echo "*** Run the program in Terminal mode the first times in the App-Start Menu ***"
    echo "IMPORTANT: Run your application as user '$ACTUAL_USER' (without sudo)"    
    echo "Start the program: python App-Start.py"
    echo ""
    echo "Enable the virtual environment: source .venv/bin/activate if not using App-Start.py"
    echo ""
    
    
}

main