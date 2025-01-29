#!/bin/bash

# Start a full-screen terminal and execute TARS-AI
xterm -fa 'Monospace' -fs 12 -fullscreen -hold -e "
    cd .. &&
    source .venv/bin/activate &&
    python src/app.py
"