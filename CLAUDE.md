# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

TARS-AI is a Python application recreating the TARS robot from *Interstellar* with real AI capabilities. It runs primarily on Raspberry Pi (pi4/pi5) and integrates voice, LLM, servo control, and a pygame UI.

## Running the Application

All commands assume the virtual environment at `src/.venv/`:

```bash
# Launcher UI (from project root) - pygame menu with auto-launch countdown
python App-Start.py

# Main app directly (from project root)
cd src && source .venv/bin/activate && python app.py

# With fullscreen UI
cd src && source .venv/bin/activate && python app.py show_ui=true

# Terminal/headless mode
cd src && source .venv/bin/activate && python app.py show_ui=false

# Servo calibration tool
cd src && source .venv/bin/activate && python app-servotester.py
```

## Configuration

Copy `src/config.ini.template` to `src/config.ini` and edit before running. Key sections:

- `[LLM]` - backend (`openai`, `grok`, `tabby`, `ooba`), model, API URL
- `[STT]` - wake word processor (`atomik`, `fastrtc`, `picovoice`), transcription engine
- `[TTS]` - voice engine (`piper`, `espeak`, `silero`, `alltalk`, `elevenlabs`, `minimax`, `openai`, `azure`)
- `[CHAR]` - character card path, user name/details
- `[SERVO]` - servo offsets (use `app-servotester.py` to calibrate)
- `[UI]` - display settings, screensaver, FPS

API keys go in `src/secrets/` (referenced by `module_secrets.py`).

## Architecture

### Entry & Boot Flow

`App-Start.py` (root) is the pygame launcher. It checks for git updates, reads `src/config.ini`, then spawns `src/app.py` via subprocess. `src/app.py` is the true main entry — it initializes all managers sequentially and starts threads.

### Module System (`src/modules/`)

All runtime logic lives in `module_*.py` files. Key ones:

- `module_config.py` — loads `config.ini`, detects Raspberry Pi version, returns device capability flags (`can_use_ui`, `can_use_vision`, etc.). Called at import time by nearly every other module.
- `module_main.py` — core orchestration: wake-word callbacks, utterance callbacks, Discord message callbacks, BT controller thread.
- `module_llm.py` — sends prompts to the configured LLM backend, handles streaming, emotion classification, and triggers movement via `module_engine.py`.
- `module_memory.py` / `module_memory_lite.py` — conversation memory. Full version uses HyperDB embeddings + BM25 hybrid RAG. Lite version is keyword-only (used on lower-memory devices). Memory files stored as `.pickle.gz` in `memory/`.
- `module_prompt.py` — assembles the full prompt sent to the LLM (character card + RAG memories + conversation history).
- `module_engine.py` — tool dispatcher: web search, vision, image generation, Home Assistant, servo movements. Called by `module_llm.py` when the LLM output contains tool invocations.
- `module_stt.py` — STTManager: microphone capture, VAD, wake word detection, transcription.
- `module_tts.py` — generates and plays audio from the configured TTS backend.
- `module_servoctl.py` — low-level servo control. Registers `on_start`/`on_end` callbacks so STT and UI pause during physical movement.
- `module_character.py` — CharacterManager: loads character JSON cards from `src/character/<NAME>/`.
- `module_ui.py` — pygame-based display (UIManager). Falls back to `UIManagerStub` (defined in `app.py`) when UI is disabled or unavailable.
- `module_chatui.py` — Flask web chat interface, runs on port 5012.
- `module_messageQue.py` — lightweight message queue for cross-module logging/display.

### Character Cards

Located in `src/character/TARS/`, `src/character/CASE/`, etc. Each is a JSON file defining personality, voice, and greeting. The active character is set via `character_card_path` in `[CHAR]` config.

### Memory Storage

`memory/` directory (adjacent to `src/`): `<CharName>.pickle.gz` (HyperDB vector store) and `<CharName>_topics.json` (topic index). Seeded from `memory/initial_memory.json`.

### Conditional Imports Pattern

Most modules use try/except around hardware-dependent imports (GPIO, camera, pygame, etc.) so the app degrades gracefully on non-Pi hardware. Check `module_config.py`'s capability flags before assuming a feature is available.

## Installation / Dependencies

```bash
# Full install (Raspberry Pi)
bash Install.sh
```

Python dependencies are in `src/requirements-server.txt`. The venv is created at `src/.venv/` by the install script.
