#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
$DIR/src/.venv/bin/activate
python "$DIR/App-Start.py"
