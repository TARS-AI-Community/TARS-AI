#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sleep 1

if [ -f "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc"
fi

export DISPLAY=:0

lxterminal --working-directory="$SCRIPT_DIR" --command="bash -c 'python3 App-Start.py; exec bash'" &

echo "TARS-AI launched at $(date)" >> "$SCRIPT_DIR/autostart.log"
