#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
source "$DIR/src/.venv/bin/activate"

# Allow Python to bind privileged ports (<1024) without running as root
PYTHON_BIN="$(readlink -f "$(which python3)")"
sudo setcap 'cap_net_bind_service=+ep' "$PYTHON_BIN" 2>/dev/null

# Reboot mode to kill old process and relaunch
# Usage: tars-launcher.sh --reboot <old_pid> <python> <app.py> [args...]
if [ "$1" = "--reboot" ]; then
    OLD_PID="$2"
    shift 2  # remaining args: python app.py [args...]

    sleep 1  # let HTTP response reach the browser

    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        # Find the parent terminal (lxterminal) of the old process
        OLD_TERMINAL_PID=$(ps -o ppid= -p "$OLD_PID" 2>/dev/null | tr -d ' ')

        kill "$OLD_PID" 2>/dev/null
        for i in $(seq 1 10); do
            kill -0 "$OLD_PID" 2>/dev/null || break
            sleep 0.5
        done
        # Force kill if still alive
        kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null

        # Close the old terminal window
        if [ -n "$OLD_TERMINAL_PID" ] && kill -0 "$OLD_TERMINAL_PID" 2>/dev/null; then
            kill "$OLD_TERMINAL_PID" 2>/dev/null
        fi
    fi

    # Relaunch in a visible terminal if display is available
    export DISPLAY=:0
    if command -v lxterminal &>/dev/null; then
        # Build the command string for lxterminal
        CMD=""
        for arg in "$@"; do
            CMD="$CMD \"$arg\""
        done
        lxterminal --working-directory="$DIR" --command="bash -c '$CMD; exec bash'" &
    else
        exec "$@"
    fi
    exit 0
fi

python "$DIR/App-Start.py" "$@"
