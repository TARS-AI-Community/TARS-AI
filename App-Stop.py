import os
import subprocess

def stop_tars_ai():
    # Ensure DISPLAY is set for GUI applications
    display = os.getenv("DISPLAY", ":0")

    subprocess.run(["killall", "xterm"], check=False)

if __name__ == "__main__":
    stop_tars_ai()