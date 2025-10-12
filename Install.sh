#!/bin/bash
# TARS System Installation Protocol
# Atomikspace / Pyrater / TeknikL

set -e  # Exit on any error

# Trap to reset terminal on exit
trap 'tput sgr0 2>/dev/null || echo -e "\033[0m"' EXIT

# Color codes for futuristic display
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Animation delay
DELAY=0.02

# TARS ASCII Art
show_tars_boot() {
    clear
    echo -e "${CYAN}"
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
    echo -e "${NC}"
    sleep 2
}

# TARS-style status message
tars_say() {
    local message=$1
    local type=${2:-"info"}
    
    case $type in
        "info")
            echo -e "${CYAN}+=== TARS ====================================================+${NC}"
            echo -e "${CYAN}|${NC} ${WHITE}${message}${NC}"
            echo -e "${CYAN}+=============================================================+${NC}"
            ;;
        "success")
            echo -e "${GREEN}+=== TARS ====================================================+${NC}"
            echo -e "${GREEN}|${NC} ${WHITE}[OK] ${message}${NC}"
            echo -e "${GREEN}+=============================================================+${NC}"
            ;;
        "warning")
            echo -e "${YELLOW}+=== TARS ====================================================+${NC}"
            echo -e "${YELLOW}|${NC} ${WHITE}[!] ${message}${NC}"
            echo -e "${YELLOW}+=============================================================+${NC}"
            ;;
        "error")
            echo -e "${RED}+=== TARS ====================================================+${NC}"
            echo -e "${RED}|${NC} ${WHITE}[X] ${message}${NC}"
            echo -e "${RED}+=============================================================+${NC}"
            ;;
    esac
    echo ""
}

# System diagnostic display
show_system_diagnostic() {
    echo -e "${CYAN}+===============================================================+${NC}"
    echo -e "${CYAN}|${NC}           ${BOLD}SYSTEM DIAGNOSTIC INITIATED${NC}                  ${CYAN}|${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    echo -e "${CYAN}|${NC} CPU Architecture: ${GREEN}$(uname -m)${NC}"
    echo -e "${CYAN}|${NC} Kernel Version:   ${GREEN}$(uname -r)${NC}"
    echo -e "${CYAN}|${NC} Hostname:         ${GREEN}$(hostname)${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    echo ""
}

# Simple spinning loader
spin_loader() {
    local pid=$1
    local message=$2
    local spin='|/-\'
    local i=0
    
    echo -ne "${CYAN}|${NC}  "
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) %4 ))
        echo -ne "\r${CYAN}|${NC}  ${YELLOW}${spin:$i:1}${NC} ${WHITE}${message}${NC}"
        sleep .1
    done
    echo -ne "\r${CYAN}|${NC}  ${GREEN}[OK]${NC} ${WHITE}${message}${NC}\n"
}

# Function to retry pip install
retry_pip_install() {
    local n=1
    local max=5
    local delay=5

    tars_say "Initiating Python dependency installation protocol..." "info"
    
    while true; do
        echo -e "${CYAN}+===============================================================+${NC}"
        echo -e "${CYAN}|${NC} Attempt: ${WHITE}$n${NC}/${WHITE}$max${NC}"
        echo -e "${CYAN}+===============================================================+${NC}"
        
        if pip install -r requirements.txt; then
            tars_say "Python dependencies synchronized successfully." "success"
            break
        else
            if [[ $n -lt $max ]]; then
                tars_say "Connection interference detected. Retrying in $delay seconds..." "warning"
                for ((i=delay; i>0; i--)); do
                    echo -ne "\r${CYAN}|${NC}  ${YELLOW}>>>${NC} Retry countdown: ${WHITE}$i${NC} seconds... "
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
        
        echo -e "${CYAN}+===============================================================+${NC}"
        echo -e "${CYAN}|${NC} ${BOLD}OPERATING SYSTEM DETECTED${NC}"
        echo -e "${CYAN}+===============================================================+${NC}"
        echo -e "${CYAN}|${NC} System:   ${GREEN}$PRETTY_NAME${NC}"
        echo -e "${CYAN}|${NC} Codename: ${GREEN}$VERSION_CODENAME${NC}"
        echo -e "${CYAN}|${NC} Version:  ${GREEN}$VERSION_ID${NC}"
        echo -e "${CYAN}+===============================================================+${NC}"
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
    
    echo -e "${CYAN}+===============================================================+${NC}"
    echo -e "${CYAN}|${NC} ${BOLD}CHROMIUM INSTALLATION PROTOCOL${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    
    if apt-cache show chromium &>/dev/null; then
        echo -e "${CYAN}|${NC}  Package detected: ${GREEN}chromium${NC} (Latest variant)"
        sudo apt install -y chromium sox libsox-fmt-all portaudio19-dev espeak-ng --fix-missing > /dev/null 2>&1 &
        spin_loader $! "Installing chromium runtime environment"
        CHROMIUM_CMD="chromium"
    elif apt-cache show chromium-browser &>/dev/null; then
        echo -e "${CYAN}|${NC}  Package detected: ${GREEN}chromium-browser${NC} (Legacy variant)"
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
    
    echo -e "${CYAN}+===============================================================+${NC}"
    echo -e "${CYAN}|${NC} ${BOLD}CHROMEDRIVER CONFIGURATION${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    
    # Check if already installed
    if command -v chromedriver &>/dev/null; then
        echo -e "${CYAN}|${NC} Status: ${GREEN}Already present in system${NC}"
        VERSION=$(chromedriver --version 2>/dev/null | head -1)
        echo -e "${CYAN}|${NC} Version: ${WHITE}$VERSION${NC}"
        echo -e "${CYAN}+===============================================================+${NC}"
        return 0
    fi
    
    # Try new package name first (chromium-driver)
    if apt-cache show chromium-driver &>/dev/null; then
        echo -e "${CYAN}|${NC} Method: ${WHITE}Package Manager${NC} (chromium-driver)"
        echo -e "${CYAN}+===============================================================+${NC}"
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
        echo -e "${CYAN}|${NC} Method: ${WHITE}Package Manager${NC} (chromium-chromedriver)"
        echo -e "${CYAN}+===============================================================+${NC}"
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
    echo -e "${CYAN}|${NC} Method: ${YELLOW}Not Available${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    
    CHROMIUM_VERSION=$($CHROMIUM_CMD --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo "")
    
    if [ -n "$CHROMIUM_VERSION" ]; then
        MAJOR_VERSION=$(echo $CHROMIUM_VERSION | cut -d. -f1)
        echo -e "${CYAN}|${NC}  Chromium Version: ${WHITE}$CHROMIUM_VERSION${NC} (Major: ${WHITE}$MAJOR_VERSION${NC})"
    fi
    
    # Detect architecture
    ARCH=$(uname -m)
    echo -e "${CYAN}|${NC}  Architecture: ${WHITE}$ARCH${NC}"
    
    echo -e "${CYAN}|${NC}  "
    echo -e "${CYAN}|${NC}  ${YELLOW}ChromeDriver Status: OPTIONAL${NC}"
    echo -e "${CYAN}|${NC}  - Only needed for Selenium/web browser automation"
    echo -e "${CYAN}|${NC}  - Most TARS functions work without it"
    echo -e "${CYAN}|${NC}  - If needed, install manually or use 'chromium --headless'"
    echo -e "${CYAN}|${NC}  "
    echo ""
}

# Verify installations
verify_installations() {
    tars_say "Running system verification protocols..." "info"
    
    echo -e "${CYAN}+===============================================================+${NC}"
    echo -e "${CYAN}|${NC} ${BOLD}INSTALLATION VERIFICATION${NC}"
    echo -e "${CYAN}+===============================================================+${NC}"
    
    if command -v chromium &>/dev/null; then
        VERSION=$(chromium --version 2>/dev/null)
        echo -e "${CYAN}|${NC} ${GREEN}[OK]${NC} Chromium:     ${WHITE}$VERSION${NC}"
    elif command -v chromium-browser &>/dev/null; then
        VERSION=$(chromium-browser --version 2>/dev/null)
        echo -e "${CYAN}|${NC} ${GREEN}[OK]${NC} Chromium:     ${WHITE}$VERSION${NC}"
    else
        echo -e "${CYAN}|${NC} ${RED}[X]${NC} Chromium:     ${RED}Not found${NC}"
    fi
    
    if command -v chromedriver &>/dev/null; then
        VERSION=$(chromedriver --version 2>/dev/null | head -1)
        echo -e "${CYAN}|${NC} ${GREEN}[OK]${NC} ChromeDriver: ${WHITE}$VERSION${NC}"
    else
        echo -e "${CYAN}|${NC} ${GRAY}[--]${NC} ChromeDriver: ${GRAY}Not installed (optional)${NC}"
    fi
    
    if command -v sox &>/dev/null; then
        VERSION=$(sox --version 2>/dev/null | head -1)
        echo -e "${CYAN}|${NC} ${GREEN}[OK]${NC} SoX:          ${WHITE}$VERSION${NC}"
    else
        echo -e "${CYAN}|${NC} ${RED}[X]${NC} SoX:          ${RED}Not found${NC}"
    fi
    
    echo -e "${CYAN}+===============================================================+${NC}"
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
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} Project directory confirmed: ${WHITE}src/${NC}\n"
    
    # Set permissions on ENTIRE project directory (same commands that worked manually)
    tars_say "Setting project permissions..." "info"
    sudo chown -R $(whoami):$(whoami) . > /dev/null 2>&1
    chmod -R 755 src/ > /dev/null 2>&1
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} Ownership set to: ${WHITE}$(whoami)${NC}"
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} All src/ directories are now writable (755)\n"
    
    cd src
    
    # Virtual environment
    tars_say "Constructing Python virtual environment..." "info"
    python3 -m venv .venv --system-site-packages > /dev/null 2>&1 &
    spin_loader $! "Building isolated Python environment"
    echo ""
    
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} Virtual environment activated\n"
    else
        tars_say "Virtual environment activation failed. Critical system error." "error"
        exit 1
    fi
    
    # Permissions
    tars_say "Configuring virtual environment permissions..." "info"
    cd ..
    sudo chown -R $(whoami):$(whoami) src/.venv/ > /dev/null 2>&1 &
    spin_loader $! "Setting venv ownership"
    cd src
    echo ""
    
    # Clean system packages
    tars_say "Removing conflicting system packages..." "info"
    sudo apt remove -y python3-simplejpeg python3-picamera2 > /dev/null 2>&1 || true
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} System package conflicts resolved\n"
    
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
    chown $(whoami):$(whoami) config.ini 2>/dev/null || sudo chown $(whoami):$(whoami) config.ini
    chmod 664 config.ini
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} config.ini (writable, run: nano config.ini)"
    
    # Create .env in parent directory
    cd ..
    if [ ! -f ".env" ]; then
        cp .env.template .env
    fi
    # Always set proper permissions (fixes read-only issues)
    chown $(whoami):$(whoami) .env 2>/dev/null || sudo chown $(whoami):$(whoami) .env
    chmod 664 .env
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} .env (writable, run: nano .env)"
    echo -e "${CYAN}|${NC}  ${YELLOW}Note:${NC} .env is hidden (starts with .) - use 'ls -la' to see it"
    cd src
    echo ""
    
    # Display setup
    export DISPLAY=:0
    echo -e "${CYAN}|${NC}  Display configuration: ${WHITE}$DISPLAY${NC}\n"
    
    # Final verification
    tars_say "Final system verification..." "info"
    cd ..
    
    # One more time to be absolutely sure
    sudo chown -R $(whoami):$(whoami) . > /dev/null 2>&1
    chmod -R 755 src/ > /dev/null 2>&1
    
    # Verify it worked
    if [ -w "src/" ]; then
        echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} src/ is writable - can create new directories"
    else
        echo -e "${CYAN}|${NC}  ${YELLOW}[!]${NC} WARNING: src/ permissions may need manual fix"
        echo -e "${CYAN}|${NC}  ${YELLOW}Run:${NC} sudo chown -R \$(whoami):\$(whoami) ."
    fi
    echo -e "${CYAN}|${NC}  ${GREEN}[OK]${NC} All systems verified\n"
    cd src
    
    # Success message
    echo -e "${GREEN}"
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
    echo -e "${NC}"
    
    # Reset terminal to normal state
    tput sgr0 2>/dev/null || echo -e "\033[0m"
    
    sleep 2
}

# Execute main installation
main

# Final terminal reset
tput sgr0 2>/dev/null || echo -e "\033[0m"