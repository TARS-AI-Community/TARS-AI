#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
source "$DIR/src/.venv/bin/activate"

# Allow Python to bind privileged ports (<1024) without running as root
PYTHON_BIN="$(readlink -f "$(which python3)")"
sudo setcap 'cap_net_bind_service=+ep' "$PYTHON_BIN" 2>/dev/null

python "$DIR/App-Start.py"
