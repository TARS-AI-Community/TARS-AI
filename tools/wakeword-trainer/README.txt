================================================================================
  TARS-AI Wake Word Trainer
================================================================================

Generates a universal "hey tars" wake word detection model using synthetic
TTS speech from dozens of voices. The output is a small ONNX model (~100KB)
that runs on any device including Raspberry Pi Zero 2.


================================================================================
  REQUIREMENTS
================================================================================

- Python 3.10+
- GPU recommended for training (NVIDIA with CUDA)
- Works on CPU too (just slower, ~10-30 minutes vs ~2-5 minutes on GPU)
- ~2GB disk space for temporary TTS audio generation
- Internet connection (for edge-tts voice synthesis)


================================================================================
  SETUP
================================================================================

1. Create a virtual environment:

   python -m venv .venv

   # Windows:
   .venv\Scripts\activate

   # Mac/Linux:
   source .venv/bin/activate

2. Install PyTorch:

   # GPU (NVIDIA):
   pip install torch --index-url https://download.pytorch.org/whl/cu124

   # CPU only:
   pip install torch

3. Install other dependencies:

   pip install -r requirements.txt


================================================================================
  USAGE
================================================================================

Basic training (uses defaults):

   python train.py

Custom options:

   python train.py --epochs 3000          # More epochs (better accuracy)
   python train.py --output my_model.onnx # Custom output filename
   python train.py --no-tts              # Skip TTS, reuse cached data

The training process:
   1. Generates "hey tars" audio using 50+ TTS voices (edge-tts)
   2. Generates negative audio (confusable phrases, general speech)
   3. Augments all samples (speed, pitch, noise, reverb, EQ)
   4. Generates synthetic noise samples (white, pink, babble, etc.)
   5. Trains a small CNN with PyTorch
   6. Exports to ONNX format

Training data is cached in training_data/ so subsequent runs with --no-tts
skip the slow TTS generation step.


================================================================================
  OUTPUT
================================================================================

Two files are generated:

   hey_tars.onnx        The wake word model (~100KB)
   hey_tars_meta.json   Metadata (threshold, accuracy, config)

Copy hey_tars.onnx to your TARS-AI installation:

   cp hey_tars.onnx /path/to/TARS-AI/src/tts/hey_tars.onnx

The model is used automatically by module_atomik.py when present.
If the ONNX model exists, the old per-user training step is skipped.


================================================================================
  HOW IT WORKS
================================================================================

The model is a small 1D CNN (Convolutional Neural Network):

   Input: 62 MFCC frames x 13 coefficients (1 second of 16kHz audio)
     |
   Conv1D(32 filters, kernel=5) -> BatchNorm -> ReLU -> MaxPool -> Dropout
     |
   Conv1D(64 filters, kernel=3) -> BatchNorm -> ReLU -> MaxPool -> Dropout
     |
   Conv1D(64 filters, kernel=3) -> BatchNorm -> ReLU -> GlobalAvgPool
     |
   FC(64) -> ReLU -> FC(1) -> Sigmoid

Output: probability (0.0 to 1.0) that the audio contains "hey tars"

The model learns temporal patterns in the MFCC spectrogram — it knows that
"hey tars" has a specific sequence of phonemes (breathy h, vowel ey, pause,
plosive t, vowel ar, sibilant s) and can distinguish it from similar-sounding
words because the CNN kernels slide across time.

Training data comes from edge-tts (Microsoft's TTS service) which provides
50+ English voices with different accents, genders, and speaking styles.
Each sample is augmented with speed/pitch/noise/reverb variations to make
the model robust to real-world conditions.
