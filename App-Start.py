import os
import subprocess
import time

def display_tars_banner():
    banner = """
\033[1;36m
████████╗ █████╗ ██████╗ ███████╗
╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
   ██║   ███████║██████╔╝███████╗
   ██║   ██╔══██║██╔══██╗╚════██║
   ██║   ██║  ██║██║  ██║███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
\033[1;37m
╔═══════════════════════════════════════════╗
║     Tactical Aerospace Reconnaissance     ║
║          System - AI Interface            ║
╚═══════════════════════════════════════════╝
\033[0m
"""
    print(banner)

def display_humor_setting():
    humor = """
\033[1;33m[SYSTEM]\033[0m Humor setting: \033[1;32m75%\033[0m
\033[1;33m[SYSTEM]\033[0m Honesty setting: \033[1;32m90%\033[0m
\033[1;33m[SYSTEM]\033[0m Initializing TARS AI...
"""
    print(humor)
    time.sleep(0.5)

def stop_tars_ai():
    # Kill xterm and the Python app
    subprocess.Popen("killall xterm", shell=True)
    subprocess.Popen("pkill -f 'python app.py'", shell=True)

def run_tars_ai_fullscreen():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")
    
    # Set environment variables to suppress logs
    os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    
    # Modified xterm command with better color settings
    command = (
        f"DISPLAY={display} xterm "
        "-fa 'Monospace' -fs 10 "
        "-bg black -fg white "
        "-fullscreen "
        "-e \""
        "cd src && "
        "source .venv/bin/activate && "
        "python app.py"
        "\""
    )
    
    subprocess.Popen(command, shell=True, executable="/bin/bash")

def run_tars_ai_normal():
    # Set environment variables to suppress logs
    os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    
    # Run directly in current terminal
    command = (
        "cd src && "
        "source .venv/bin/activate && "
        "python app.py"
    )
    
    subprocess.run(command, shell=True, executable="/bin/bash")

if __name__ == "__main__":
    # Clear screen for better presentation
    os.system('clear')
    
    # Display TARS banner
    display_tars_banner()
    display_humor_setting()
    
    # Ask user for preference
    print("\033[1;36m[TARS]\033[0m Do you want to start in fullscreen mode?")
    choice = input("\033[1;37m      Enter 'y' for fullscreen or 'n' for normal terminal:\033[0m ").strip().lower()
    
    print()  # Empty line for spacing
    
    if choice == 'y' or choice == 'yes':
        print("\033[1;32m[SYSTEM]\033[0m Launching in fullscreen mode...")
        stop_tars_ai()
        time.sleep(0.1)
        run_tars_ai_fullscreen()
    else:
        print("\033[1;32m[SYSTEM]\033[0m Launching in normal mode...")
        print()
        run_tars_ai_normal()
