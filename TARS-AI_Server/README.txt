================================================================================
  TARS-AI Companion Server
================================================================================

Offloads heavy AI workloads (STT, TTS, LLM, Vision, Image Generation,
Music Generation, Embeddings) from your Raspberry Pi to a powerful PC or server.

Requirements:
  - Python 3.10 or newer
  - NVIDIA GPU recommended (8+ GB VRAM for best performance)
  - Works on CPU too, just slower


================================================================================
  WINDOWS SETUP
================================================================================

1. Copy this entire TARS-AI_Server folder to your Windows PC.

2. Double-click run-server.bat

   That's it. The batch file will:
   - Find Python on your system
   - Create a virtual environment (.venv)
   - Install PyTorch (GPU or CPU, auto-detected)
   - Install all dependencies
   - Launch the server

   First run takes several minutes (downloads ~3-5 GB of packages).
   Subsequent runs start in seconds.

3. If you don't have Python installed:
   - Download from https://www.python.org/downloads/
   - IMPORTANT: Check "Add Python to PATH" during installation
   - Or install via terminal: winget install Python.Python.3.11


================================================================================
  MAC / LINUX SETUP
================================================================================

1. Copy this entire TARS-AI_Server folder to your machine.

2. Open a terminal in this folder and run:

   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip setuptools wheel

3. Install PyTorch:

   # Mac (Apple Silicon with MPS acceleration):
   pip install torch torchaudio

   # Linux with NVIDIA GPU:
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

   # Linux CPU only:
   pip install torch torchaudio

4. Install dependencies:

   pip install -r requirements-server.txt

   Note: If you get errors from the CUDA index on Mac/CPU, remove the first
   two lines from requirements-server.txt (the --index-url lines) and retry.

5. Start the server:

   python app-server.py

   Or with specific services only:

   python app-server.py --services stt llm tts


================================================================================
  ACCESSING THE SERVER
================================================================================

Once running, open a browser to:

   http://localhost:5678          Dashboard (live stats)
   http://localhost:5678/playground   Test all services interactively
   http://localhost:5678/ui       Settings (enable/disable services, models)
   http://localhost:5678/docs     API documentation

From other devices on your network, use your PC's IP address instead of
localhost (shown in the terminal when the server starts).


================================================================================
  CONNECTING YOUR TARS RPi
================================================================================

In your TARS RPi config.ini, point services to this server:

   [STT]
   stt_processor = external
   external_url = http://<server-ip>:5678

   [LLM]
   llm_backend = other
   base_url = http://<server-ip>:5678

   [TTS]
   ttsoption = other
   ttsurl = http://<server-ip>:5678

   [VISION]
   vision_processor = server_hosted
   base_url = http://<server-ip>:5678

   [STABLE_DIFFUSION]
   service = automatic1111
   url = http://<server-ip>:5678

Replace <server-ip> with your PC's local IP address (e.g. 192.168.1.100).


================================================================================
  SECURITY
================================================================================

To require authentication, set an API key in the Settings page
(http://localhost:5678/ui) or edit config-server.ini:

   [server]
   api_key = your-secret-key

Your TARS RPi sends this key automatically via the Authorization header.
The web UI uses a session cookie (login page appears automatically).


================================================================================
  COMMAND LINE OPTIONS
================================================================================

   python app-server.py                                  # All services, auto GPU
   python app-server.py --services stt llm               # Only STT + LLM
   python app-server.py --services musicgen              # Only Music Gen
   python app-server.py --llm-model Qwen/Qwen3-8B       # Larger LLM model
   python app-server.py --no-imagegen --no-embeddings    # Skip specific services
   python app-server.py --port 8080                      # Custom port
   python app-server.py --ssl-cert cert.pem --ssl-key key.pem  # HTTPS


================================================================================
  SERVICES
================================================================================

   STT        Speech-to-Text (faster-whisper, Silero VAD)
   TTS        Text-to-Speech (Piper ONNX voices)
   LLM        Chat / Language Model (Qwen, llama.cpp GGUF)
   Vision     Image captioning (BLIP, Moondream, Florence)
   ImageGen   Text-to-Image (Stable Diffusion via diffusers)
   MusicGen   Text-to-Music with vocals/lyrics (ACE-Step)
   Embeddings Sentence embeddings for RAG/memory

All services are optional. Enable/disable them in the Settings page or via
command line flags. Models are downloaded automatically on first use.


================================================================================
  TROUBLESHOOTING
================================================================================

"No module named torch"
   PyTorch didn't install. Run the PyTorch install command from step 3 above.

"CUDA out of memory"
   Too many services loaded for your GPU. Disable services you don't need
   in Settings, or use smaller models.

"Port already in use"
   Another instance is running, or another app uses port 5678.
   Use --port 8080 (or any free port).

Server starts but RPi can't connect
   - Make sure both devices are on the same network
   - Check firewall isn't blocking port 5678
   - Try the IP shown in the server terminal output

Models downloading slowly
   First run downloads models from HuggingFace (~1-10 GB per model).
   This is normal. Models are cached in the models/ folder for future runs.
