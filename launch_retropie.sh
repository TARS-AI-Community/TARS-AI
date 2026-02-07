#!/bin/bash
# TARS System Retrogaming Protocol
# Atomikspace

[ "$EUID" -eq 0 ] && exit 1

TARS_DIR="$HOME/TARS-AI"
TARS_WAS_RUNNING=false

echo "=== RetroPie launch ==="

TARS_PID=$(pgrep -f "python.*App-Start.py" | head -1)
if [ -n "$TARS_PID" ]; then
    TARS_WAS_RUNNING=true
    TARS_PGID=$(ps -o pgid= -p "$TARS_PID" | tr -d ' ')
    echo "Waiting for TARS (PID=$TARS_PID, PGID=$TARS_PGID) to shut down..."

    for i in $(seq 1 10); do
        kill -0 "$TARS_PID" 2>/dev/null || break
        sleep 1
    done

    if kill -0 "$TARS_PID" 2>/dev/null; then
        echo "Forcing entire process group..."
        kill -9 -"$TARS_PGID" 2>/dev/null
        sleep 1
    fi

    pkill -9 -f "App-Start.py" 2>/dev/null
    pkill -9 -f "module_btcontroller" 2>/dev/null
    echo "TARS stopped."
fi

sleep 1

unset WAYLAND_DISPLAY
unset SDL_VIDEODRIVER
export DISPLAY=:0

echo "Launching emulationstation.sh..."
/opt/retropie/supplementary/emulationstation/emulationstation.sh
echo "EmulationStation exited."

if [ "$TARS_WAS_RUNNING" = true ]; then
    echo "Restarting TARS..."
    export WAYLAND_DISPLAY=wayland-0
    cd "$TARS_DIR"
    source src/.venv/bin/activate
    exec python App-Start.py
fi