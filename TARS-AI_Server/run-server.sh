#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# TARS-AI Companion Server — Linux installer & launcher
# Just run: chmod +x run-server.sh && ./run-server.sh
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
SERVER="$SCRIPT_DIR/app-server.py"

echo ""
echo "  ================================================"
echo "   TARS-AI Companion Server"
echo "  ================================================"
echo ""

# ---------------------------------------------------------------------------
# Check app-server.py exists
# ---------------------------------------------------------------------------
if [ ! -f "$SERVER" ]; then
    echo "  [FAIL] app-server.py not found in $SCRIPT_DIR"
    echo "         Make sure run-server.sh is in the same folder as app-server.py"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1 — Require Python 3.11
# ---------------------------------------------------------------------------
echo "  [....] Checking Python 3.11..."

PYTHON_CMD=""

# Try python3.11 first
if command -v python3.11 &>/dev/null; then
    PYTHON_CMD="python3.11"
    PY_VER=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    echo "  [ OK ] Found Python $PY_VER"
else
    # Fallback: check if python3 happens to be 3.11
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$PY_MAJOR" = "3" ] && [ "$PY_MINOR" = "11" ]; then
            PYTHON_CMD="python3"
            echo "  [ OK ] Found Python $PY_VER"
        fi
    fi
    # Fallback: check if python happens to be 3.11
    if [ -z "$PYTHON_CMD" ] && command -v python &>/dev/null; then
        PY_VER=$(python --version 2>&1 | awk '{print $2}')
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$PY_MAJOR" = "3" ] && [ "$PY_MINOR" = "11" ]; then
            PYTHON_CMD="python"
            echo "  [ OK ] Found Python $PY_VER"
        fi
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo "  [FAIL] Python 3.11 not found."
    echo ""
    echo "         Install it via your package manager, e.g.:"
    echo "           sudo apt install python3.11 python3.11-venv"
    echo "           sudo dnf install python3.11"
    echo ""
    echo "         Or download: https://www.python.org/downloads/release/python-3119/"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 2 — Create venv if needed (recreate if wrong Python version)
# ---------------------------------------------------------------------------
echo "  [....] Setting up virtual environment..."

NEED_VENV=0
if [ -x "$VENV_PYTHON" ]; then
    # Check if existing venv uses Python 3.11
    VENV_VER=$("$VENV_PYTHON" --version 2>&1 | awk '{print $2}')
    VENV_MAJOR=$(echo "$VENV_VER" | cut -d. -f1)
    VENV_MINOR=$(echo "$VENV_VER" | cut -d. -f2)
    if [ "$VENV_MAJOR" = "3" ] && [ "$VENV_MINOR" = "11" ]; then
        echo "  [ OK ] Virtual environment already uses Python 3.11 - skipping."
    else
        echo "  [ !! ] Existing venv uses Python ${VENV_MAJOR}.${VENV_MINOR}, need 3.11 - recreating..."
        rm -rf "$VENV_DIR"
        NEED_VENV=1
    fi
else
    NEED_VENV=1
fi

if [ "$NEED_VENV" = "1" ]; then
    echo "         Creating .venv in $VENV_DIR..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "  [ OK ] Virtual environment created with Python 3.11."
fi

# ---------------------------------------------------------------------------
# Step 3 — Upgrade pip
# ---------------------------------------------------------------------------
echo "  [....] Upgrading pip..."
if "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel -q; then
    echo "  [ OK ] pip is up to date."
else
    echo "  [ !! ] pip upgrade failed - continuing anyway..."
fi

# ---------------------------------------------------------------------------
# Step 4 — Detect NVIDIA GPU
# ---------------------------------------------------------------------------
HAS_GPU=0
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    HAS_GPU=1
fi

# ---------------------------------------------------------------------------
# Step 5 — Install PyTorch (skip if already installed)
# ---------------------------------------------------------------------------
echo "  [....] Checking PyTorch..."

if "$VENV_PYTHON" -c "import torch" &>/dev/null; then
    TORCH_VER=$("$VENV_PYTHON" -c "import torch; print(torch.__version__)")
    echo "  [ OK ] PyTorch $TORCH_VER already installed - skipping."
else
    if [ "$HAS_GPU" = "1" ]; then
        echo "  [....] NVIDIA GPU detected - installing PyTorch CUDA 12.4 build..."
        echo "         (This is a large download ~2.5 GB, please wait)"
        "$VENV_PIP" install "torch>=2.6.0" "torchaudio>=2.6.0" "torchvision>=0.21.0" \
            --index-url https://download.pytorch.org/whl/cu124
    else
        echo "  [....] No NVIDIA GPU - installing PyTorch CPU build..."
        "$VENV_PIP" install "torch>=2.6.0" "torchaudio>=2.6.0" "torchvision>=0.21.0"
    fi
    if [ $? -ne 0 ]; then
        echo "  [FAIL] Failed to install PyTorch."
        exit 1
    fi
    echo "  [ OK ] PyTorch installed."
fi

# ---------------------------------------------------------------------------
# Step 6 — Install all other dependencies (skip if already present)
# ---------------------------------------------------------------------------
echo "  [....] Checking dependencies..."

if "$VENV_PYTHON" -c "import fastapi" &>/dev/null; then
    echo "  [ OK ] Dependencies already installed - skipping."
else
    echo "  [....] Installing packages (this may take several minutes on first run)..."
    echo ""

    "$VENV_PIP" install \
        "python-multipart" \
        "fastapi>=0.104.0" \
        "uvicorn[standard]>=0.24.0" \
        "faster-whisper>=1.0.0" \
        "piper-tts>=1.2.0" \
        "transformers>=4.51.0" \
        "accelerate>=0.27.0" \
        "Pillow>=10.0.0" \
        "diffusers>=0.27.0" \
        "sentence-transformers>=2.2.0" \
        "qrcode[pil]>=7.0" \
        "psutil>=5.9.0"

    if [ $? -ne 0 ]; then
        echo "  [FAIL] Failed to install dependencies."
        exit 1
    fi

    if [ "$HAS_GPU" = "1" ]; then
        echo "  [....] Installing bitsandbytes (GPU quantization)..."
        if ! "$VENV_PIP" install "bitsandbytes>=0.43.0"; then
            echo "  [ !! ] bitsandbytes install failed - continuing without it."
        fi
    fi

    echo "  [ OK ] Dependencies installed."
fi

# Note: llama-cpp-python is installed automatically by app-server.py at
# runtime using pre-built wheels. No compiler needed.

# ---------------------------------------------------------------------------
# Step 7 — Launch the server
# ---------------------------------------------------------------------------
echo ""

# Resolve LAN IP for display
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "")
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(ip -4 addr show scope global 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1 || echo "")
fi
[ -z "$LAN_IP" ] && LAN_IP="localhost"

echo "  ================================================"
if [ "$HAS_GPU" = "1" ]; then
    echo "   GPU : NVIDIA detected"
else
    echo "   GPU : None (CPU mode)"
fi
echo "   URL : http://${LAN_IP}:5678"
echo "  ================================================"
echo ""

"$VENV_PYTHON" "$SERVER" "$@"
