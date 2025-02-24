import os
import subprocess

def stop_tars_ai():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")
    
    command = (
        f"killall xterm"
    )
    
    subprocess.Popen(command, shell=True)

if __name__ == "__main__":
    stop_tars_ai()


