import os
import subprocess
import time

def stop_tars_ai():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")
    
    command = (
        f"killall xterm"
    )
    
    subprocess.Popen(command, shell=True)

def run_tars_ai():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")

    # Set environment variable to suppress libcamera logs
    os.environ["LIBCAMERA_LOG_LEVELS"] = "3"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"  # Suppress the message

    command = (
        f"DISPLAY={display} xterm -fa 'Monospace' -fs 10 -fullscreen -hold -e \""
        "cd src && "  # Navigate into src first
        "source .venv/bin/activate && "  # Activate virtual environment inside src/
        "python app.py"  # Run the application
        "\""
    )

    subprocess.Popen(command, shell=True, executable="/bin/bash")

if __name__ == "__main__":
    stop_tars_ai()
    time.sleep(0.1)
    run_tars_ai()
