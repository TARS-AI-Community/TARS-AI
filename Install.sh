#!/bin/bash
# TARS System Installation Protocol
# Atomikspace / Pyrater / TeknikL

set -e  # Exit on any error

# Detect the actual user (even if run with sudo)
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

# Animation delay
DELAY=0.02

# TARS ASCII Art
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
    |     TACTICAL AEROSPACE ROBOTICS             |
    |     SYSTEM INITIALIZATION                   |
    |                                             |
    |     [ HUMOR SETTING: 75% ]                  |
    |     [ HONESTY: 90% ]                        |
    |                                             |
    +=============================================+
EOF
    sleep 2
}

# TARS-style status message
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

# System diagnostic display
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

# Simple spinning loader
spin_loader() {
    local pid=$1
    local message=$2
    local spin='|/-\'
    local i=0
    
    echo -ne "|  "
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) %4 ))
        echo -ne "\r|  ${spin:$i:1} ${message}"
        sleep .1
    done
    echo -ne "\r|  [OK] ${message}\n"
}

# Function to retry pip install
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

# Detect OS version
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

# Install Chromium
install_chromium() {
    tars_say "Initiating chromium installation sequence..." "info"
    
    echo "+===============================================================+"
    echo "| CHROMIUM INSTALLATION PROTOCOL"
    echo "+===============================================================+"
    
    if apt-cache show chromium &>/dev/null; then
        echo "|  Package detected: chromium (Latest variant)"
        sudo apt install -y chromium sox libsox-fmt-all portaudio19-dev espeak-ng --fix-missing > /dev/null 2>&1 &
        spin_loader $! "Installing chromium runtime environment"
        CHROMIUM_CMD="chromium"
    elif apt-cache show chromium-browser &>/dev/null; then
        echo "|  Package detected: chromium-browser (Legacy variant)"
        sudo apt install -y chromium-browser sox libsox-fmt-all portaudio19-dev espeak-ng --fix-missing > /dev/null 2>&1 &
        spin_loader $! "Installing chromium-browser runtime environment"
        CHROMIUM_CMD="chromium-browser"
    else
        tars_say "Chromium package not found in repositories. Manual intervention required." "error"
        exit 1
    fi
    
    install_chromedriver
    
    sudo apt install -y xterm libcap-dev --fix-missing > /dev/null 2>&1 &
    spin_loader $! "Installing auxiliary dependencies"
    
    echo ""
}

# Install ChromeDriver
install_chromedriver() {
    tars_say "ChromeDriver installation protocol engaged..." "info"
    
    echo "+===============================================================+"
    echo "| CHROMEDRIVER CONFIGURATION"
    echo "+===============================================================+"
    
    # Check if already installed
    if command -v chromedriver &>/dev/null; then
        echo "| Status: Already present in system"
        VERSION=$(chromedriver --version 2>/dev/null | head -1)
        echo "| Version: $VERSION"
        echo "+===============================================================+"
        return 0
    fi
    
    # Try new package name first (chromium-driver)
    if apt-cache show chromium-driver &>/dev/null; then
        echo "| Method: Package Manager (chromium-driver)"
        echo "+===============================================================+"
        sudo apt install -y chromium-driver --fix-missing > /dev/null 2>&1 &
        spin_loader $! "Installing chromium-driver from repository"
        
        if command -v chromedriver &>/dev/null; then
            tars_say "ChromeDriver successfully installed." "success"
        else
            tars_say "ChromeDriver package installed but binary not found in PATH." "warning"
        fi
        return 0
    fi
    
    # Try old package name (chromium-chromedriver)
    if apt-cache show chromium-chromedriver &>/dev/null; then
        echo "| Method: Package Manager (chromium-chromedriver)"
        echo "+===============================================================+"
        sudo apt install -y chromium-chromedriver --fix-missing > /dev/null 2>&1 &
        spin_loader $! "Installing chromium-chromedriver from repository"
        
        if command -v chromedriver &>/dev/null; then
            tars_say "ChromeDriver successfully installed." "success"
        else
            tars_say "ChromeDriver package installed but binary not found in PATH." "warning"
        fi
        return 0
    fi
    
    # If we get here, ChromeDriver is not available via package manager
    echo "| Method: Not Available"
    echo "+===============================================================+"
    
    CHROMIUM_VERSION=$($CHROMIUM_CMD --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo "")
    
    if [ -n "$CHROMIUM_VERSION" ]; then
        MAJOR_VERSION=$(echo $CHROMIUM_VERSION | cut -d. -f1)
        echo "|  Chromium Version: $CHROMIUM_VERSION (Major: $MAJOR_VERSION)"
    fi
    
    # Detect architecture
    ARCH=$(uname -m)
    echo "|  Architecture: $ARCH"
    
    echo "|  "
    echo "|  ChromeDriver Status: OPTIONAL"
    echo "|  - Only needed for Selenium/web browser automation"
    echo "|  - Most TARS functions work without it"
    echo "|  - If needed, install manually or use 'chromium --headless'"
    echo "|  "
    echo ""
}

# Verify installations
verify_installations() {
    tars_say "Running system verification protocols..." "info"
    
    echo "+===============================================================+"
    echo "| INSTALLATION VERIFICATION"
    echo "+===============================================================+"
    
    if command -v chromium &>/dev/null; then
        VERSION=$(chromium --version 2>/dev/null)
        echo "| [OK] Chromium:     $VERSION"
    elif command -v chromium-browser &>/dev/null; then
        VERSION=$(chromium-browser --version 2>/dev/null)
        echo "| [OK] Chromium:     $VERSION"
    else
        echo "| [X] Chromium:     Not found"
    fi
    
    if command -v chromedriver &>/dev/null; then
        VERSION=$(chromedriver --version 2>/dev/null | head -1)
        echo "| [OK] ChromeDriver: $VERSION"
    else
        echo "| [--] ChromeDriver: Not installed (optional)"
    fi
    
    if command -v sox &>/dev/null; then
        VERSION=$(sox --version 2>/dev/null | head -1)
        echo "| [OK] SoX:          $VERSION"
    else
        echo "| [X] SoX:          Not found"
    fi
    
    echo "+===============================================================+"
    echo ""
    sleep 1
}

# Main installation
main() {
    show_tars_boot
    
    tars_say "This is no time for caution. Initializing installation sequence." "info"
    
    show_system_diagnostic
    
    # System update
    tars_say "Synchronizing package databases..." "info"
    sudo apt clean > /dev/null 2>&1
    sudo update-initramfs -u -k all > /dev/null 2>&1 || true
    sudo dpkg --configure -a > /dev/null 2>&1
    sudo apt update -y > /dev/null 2>&1 &
    spin_loader $! "Updating package repositories"
    echo ""
    
    detect_os_version
    install_chromium
    verify_installations
    
    # Directory check and permissions setup
    tars_say "Verifying project structure..." "info"
    if [ ! -d "src" ]; then
        tars_say "Critical error: 'src' directory not found. Installation cannot proceed." "error"
        exit 1
    fi
    echo "|  [OK] Project directory confirmed: src/"
    echo ""
    
    # Set permissions on ENTIRE project directory - AGGRESSIVE
    tars_say "Setting project permissions..." "info"
    # Remove any restrictive attributes
    sudo chattr -R -i . 2>/dev/null || true
    # Set ownership on everything to the actual user (not root)
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER .
    # Set permissions - 775 is more permissive
    chmod -R 775 .
    echo "|  [OK] Ownership set to: $ACTUAL_USER"
    echo "|  [OK] All directories now writable (775)"
    
    # Specifically ensure critical subdirectories exist and are writable
    mkdir -p src/modules src/logs src/data 2>/dev/null || true
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER src/modules src/logs src/data 2>/dev/null || true
    chmod -R 775 src/modules src/logs src/data 2>/dev/null || true
    echo "|  [OK] Critical subdirectories verified"
    echo ""
    
    cd src
    
    # Virtual environment
    tars_say "Constructing Python virtual environment..." "info"
    python3 -m venv .venv --system-site-packages > /dev/null 2>&1 &
    spin_loader $! "Building isolated Python environment"
    echo ""
    
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "|  [OK] Virtual environment activated"
        echo ""
    else
        tars_say "Virtual environment activation failed. Critical system error." "error"
        exit 1
    fi
    
    # Permissions
    tars_say "Configuring virtual environment permissions..." "info"
    cd ..
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER src/.venv/
    chmod -R 775 src/.venv/
    echo "|  [OK] Virtual environment permissions set (775)"
    cd src
    echo ""
    
    # Clean system packages
    tars_say "Removing conflicting system packages..." "info"
    sudo apt remove -y python3-simplejpeg python3-picamera2 > /dev/null 2>&1 || true
    echo "|  [OK] System package conflicts resolved"
    echo ""
    
    # Pip upgrade
    tars_say "Upgrading package installer..." "info"
    pip install --upgrade pip > /dev/null 2>&1 &
    spin_loader $! "Updating pip to latest version"
    echo ""
    
    # Core dependencies
    tars_say "Installing critical Python modules..." "info"
    pip uninstall -y numpy simplejpeg picamera2 > /dev/null 2>&1 || true
    pip install --no-cache-dir numpy==2.1 simplejpeg picamera2 > /dev/null 2>&1 &
    spin_loader $! "Installing NumPy, SimpleJPEG, and PiCamera2"
    echo ""
    
    # Requirements
    retry_pip_install
    
    # Configuration files
    tars_say "Initializing configuration files..." "info"
    
    # Create config.ini
    if [ ! -f "config.ini" ]; then
        cp config.ini.template config.ini
    fi
    # Always set proper permissions (fixes read-only issues)
    sudo chown $ACTUAL_USER:$ACTUAL_USER config.ini 2>/dev/null
    chmod 664 config.ini
    echo "|  [OK] config.ini (writable, run: nano config.ini)"
    
    # Create .env in parent directory
    cd ..
    if [ ! -f ".env" ]; then
        cp .env.template .env
    fi
    # Always set proper permissions (fixes read-only issues)
    sudo chown $ACTUAL_USER:$ACTUAL_USER .env 2>/dev/null
    chmod 664 .env
    echo "|  [OK] .env (writable, run: nano .env)"
    echo "|  Note: .env is hidden (starts with .) - use 'ls -la' to see it"
    
    # One more permission sweep on the entire directory
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER . 2>/dev/null || true
    chmod -R 775 . 2>/dev/null || true
    
    cd src
    echo ""
    
    # Display setup
    export DISPLAY=:0
    echo "|  Display configuration: $DISPLAY"
    echo ""
    
    # Final verification
    tars_say "Final system verification..." "info"
    cd ..
    
    # Final aggressive permission setting
    sudo chattr -R -i . 2>/dev/null || true
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER .
    chmod -R 775 .
    
    # Test that we can actually create files
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
    
    # Success message
    cat << "EOF"
    +==============================================================+
    |                                                              |
    |              [OK] INSTALLATION COMPLETE                      |
    |                                                              |
    |              All systems operational.                        |
    |              TARS unit ready for deployment.                 |
    |                                                              |
    |              "Safety first."                                 |
    |                                                              |
    |              [ HUMOR SETTING: 75% ]                          |
    |              [ SYSTEM STATUS: OPTIMAL ]                      |
    |                                                              |
    +==============================================================+
EOF
    
    # Final permission lockdown to ensure no issues
    cd ..
    sudo chown -R $ACTUAL_USER:$ACTUAL_USER . 2>/dev/null || true
    chmod -R 775 . 2>/dev/null || true
    cd src
    
    echo ""
    echo "IMPORTANT: Run your application as user '$ACTUAL_USER' (without sudo)"
    echo "Enable the virtual environment: source .venv/bin/activate "
    echo "Start the program: python app.py"
    
    sleep 2
}

# Execute main installation
main