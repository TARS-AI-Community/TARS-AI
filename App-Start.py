import os
import subprocess
import time

def stop_tars_ai():
    # Kill xterm and the Python app
    subprocess.Popen("killall xterm", shell=True)
    subprocess.Popen("pkill -f 'python app.py'", shell=True)

def run_tars_ai():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")
    
    # Set environment variables to suppress logs
    os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    
    # Modified xterm command with better color settings and no -hold
    command = (
        f"DISPLAY={display} xterm "
        "-fa 'Monospace' -fs 20 "
        "-bg black -fg white "  # Set explicit colors (black background, white text)
        "-fullscreen "
        "-e \""
        "cd src && "
        "source .venv/bin/activate && "
        "python app.py"
        "\""
    )
    
    subprocess.Popen(command, shell=True, executable="/bin/bash")

if __name__ == "__main__":
    stop_tars_ai()
    time.sleep(0.1)
    run_tars_ai()
