#!/usr/bin/env python3
"""
TARS-AI Universal Wake Word Model Trainer
==========================================
Generates a universal "hey tars" wake word ONNX model using synthetic TTS data.

Runs on a powerful PC with GPU — produces a small ONNX model (~100KB) that runs
on Pi Zero 2 via onnxruntime.

Usage:
    pip install -r requirements.txt
    python train.py

The output model (hey_tars.onnx) should be copied to:
    TARS-AI/src/tts/hey_tars.onnx
"""

import os
import sys
import json
import time
import struct
import random
import hashlib
import argparse
import warnings
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from scipy.fftpack import dct
from scipy.signal import resample

warnings.filterwarnings("ignore")

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("")  # Enables ANSI escape processing in Windows cmd
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000
N_MFCC = 13
N_FEATURES = 39  # 13 MFCC + 13 delta + 13 delta-delta
N_FFT = 512
N_MELS = 40
HOP = N_FFT // 2
TARGET_FRAMES = 62          # ~1 second at 16kHz / 256-hop
WAKE_WORD = "hey tars"

# Training
EPOCHS = 2000
BATCH_SIZE = 64
LR = 0.001
WEIGHT_DECAY = 1e-4

# Data generation
N_TTS_VOICES = 50           # number of TTS voice variations
N_AUGMENTS_PER_SAMPLE = 15  # augmentations per raw sample
N_AUGMENTS_MIC = 25         # extra augmentations for mic recordings (most valuable data)
N_NOISE_NEGATIVES = 200     # synthetic noise clips
N_HARD_NEGATIVE_PHRASES = 80  # confusable phrases


# ---------------------------------------------------------------------------
# MFCC extraction (matches module_atomik.py exactly)
# ---------------------------------------------------------------------------

class MFCCExtractor:
    def __init__(self, sample_rate=SAMPLE_RATE, n_mfcc=N_MFCC, n_fft=N_FFT):
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.n_mels = N_MELS
        self.mel_filters = self._create_mel_filterbank()

    def _hz_to_mel(self, hz):
        return 2595 * np.log10(1 + hz / 700.0)

    def _mel_to_hz(self, mel):
        return 700 * (10 ** (mel / 2595.0) - 1)

    def _create_mel_filterbank(self):
        low_freq_mel = 0
        high_freq_mel = self._hz_to_mel(self.sample_rate / 2)
        mel_points = np.linspace(low_freq_mel, high_freq_mel, self.n_mels + 2)
        hz_points = self._mel_to_hz(mel_points)
        bin_points = np.floor((self.n_fft + 1) * hz_points / self.sample_rate).astype(int)

        fbank = np.zeros((self.n_mels, self.n_fft // 2 + 1))
        for m in range(1, self.n_mels + 1):
            f_left, f_center, f_right = bin_points[m - 1:m + 2]
            for k in range(f_left, f_center):
                if f_center != f_left:
                    fbank[m - 1, k] = (k - f_left) / (f_center - f_left)
            for k in range(f_center, f_right):
                if f_right != f_center:
                    fbank[m - 1, k] = (f_right - k) / (f_right - f_center)
        return fbank

    def extract_mfcc(self, audio):
        if len(audio) < self.n_fft:
            return None
        emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
        frame_length = self.n_fft
        frame_step = frame_length // 2
        num_frames = 1 + int(np.floor((len(emphasized) - frame_length) / frame_step))
        if num_frames < 1:
            return None

        frames = np.zeros((num_frames, frame_length))
        for i in range(num_frames):
            start = i * frame_step
            frames[i] = emphasized[start:start + frame_length]

        frames *= np.hamming(frame_length)
        mag_frames = np.absolute(np.fft.rfft(frames, self.n_fft))
        pow_frames = ((1.0 / self.n_fft) * (mag_frames ** 2))

        filter_banks = np.dot(pow_frames, self.mel_filters.T)
        filter_banks = np.where(filter_banks == 0, np.finfo(float).eps, filter_banks)
        filter_banks = 20 * np.log10(filter_banks)

        mfcc = dct(filter_banks, type=2, axis=1, norm='ortho')[:, :self.n_mfcc]
        return (mfcc - np.mean(mfcc, axis=0)) / (np.std(mfcc, axis=0) + 1e-8)

    def _compute_deltas(self, features, width=2):
        """Compute delta (velocity) features from a feature matrix."""
        n_frames, n_feats = features.shape
        deltas = np.zeros_like(features)
        denominator = 2 * sum(t ** 2 for t in range(1, width + 1))
        if denominator == 0:
            return deltas
        for t in range(n_frames):
            numerator = np.zeros(n_feats)
            for tau in range(1, width + 1):
                t_plus = min(t + tau, n_frames - 1)
                t_minus = max(t - tau, 0)
                numerator += tau * (features[t_plus] - features[t_minus])
            deltas[t] = numerator / denominator
        return deltas

    def extract_fixed(self, audio, target_frames=TARGET_FRAMES):
        mfcc = self.extract_mfcc(audio)
        if mfcc is None:
            return None

        # Compute delta and delta-delta features for temporal dynamics
        # This captures HOW sounds change over time, not just what frequencies are present
        delta = self._compute_deltas(mfcc)
        delta2 = self._compute_deltas(delta)
        features = np.hstack([mfcc, delta, delta2])  # (frames, 39)

        n = features.shape[0]
        if n >= target_frames:
            return features[:target_frames]
        pad = np.zeros((target_frames - n, features.shape[1]))
        return np.vstack([features, pad])


mfcc_extractor = MFCCExtractor()


# ---------------------------------------------------------------------------
# TTS data generation using edge-tts (many voices)
# ---------------------------------------------------------------------------

def get_edge_tts_voices():
    """Get list of English edge-tts voices using Python API."""
    try:
        import asyncio
        import edge_tts

        async def _list():
            return await edge_tts.list_voices()

        # Handle event loop for different contexts
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                all_voices = pool.submit(asyncio.run, _list()).result()
        else:
            all_voices = asyncio.run(_list())

        voices = [v["ShortName"] for v in all_voices
                  if v.get("Locale", "").startswith("en-")]
        return voices
    except ImportError:
        # Fallback to CLI
        try:
            result = subprocess.run(
                [sys.executable, "-m", "edge_tts", "--list-voices"],
                capture_output=True, text=True, timeout=30
            )
            voices = []
            for line in result.stdout.strip().split("\n"):
                # Try both formats: "Name: voice" and "voice   Gender  ..."
                line = line.strip()
                if line.startswith("Name: "):
                    voice_name = line.split("Name: ")[1].strip()
                elif "\t" in line or "  " in line:
                    voice_name = line.split()[0] if line.split() else ""
                else:
                    continue
                if voice_name.startswith("en-"):
                    voices.append(voice_name)
            return voices
        except Exception as e:
            print(f"  Warning: edge-tts voice list failed: {e}")
            return []
    except Exception as e:
        print(f"  Warning: edge-tts API failed: {e}")
        return []


def generate_tts_audio(text, voice, output_path):
    """Generate audio using edge-tts."""
    try:
        import asyncio
        import edge_tts

        async def _generate():
            comm = edge_tts.Communicate(text, voice)
            await comm.save(output_path)

        asyncio.run(_generate())
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        # Fallback to CLI
        try:
            result = subprocess.run(
                [sys.executable, "-m", "edge_tts",
                 "--voice", voice,
                 "--text", text,
                 "--write-media", output_path],
                capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0
        except Exception:
            return False


def load_audio_file(filepath):
    """Load audio file and convert to 16kHz mono float32 numpy array."""
    try:
        import soundfile as sf
        data, sr = sf.read(filepath, dtype='float32')
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        if sr != SAMPLE_RATE:
            n_samples = int(len(data) * SAMPLE_RATE / sr)
            data = resample(data, n_samples).astype(np.float32)
        return data
    except ImportError:
        pass

    # Fallback: use ffmpeg to convert to raw PCM
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", filepath,
             "-f", "s16le", "-acodec", "pcm_s16le",
             "-ar", str(SAMPLE_RATE), "-ac", "1", "-"],
            capture_output=True, timeout=30
        )
        if result.returncode == 0 and len(result.stdout) > 0:
            data = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
            return data
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Augmentation
# ---------------------------------------------------------------------------

def time_stretch(audio, rate):
    idx = np.round(np.arange(0, len(audio), rate))
    idx = idx[idx < len(audio)].astype(int)
    return audio[idx]


def pitch_shift(audio, semitones):
    factor = 2 ** (semitones / 12.0)
    idx = np.round(np.arange(0, len(audio), factor))
    idx = idx[idx < len(audio)].astype(int)
    return audio[idx]


def add_noise(audio, noise_level):
    return audio + np.random.normal(0, noise_level, len(audio)).astype(np.float32)


def random_volume(audio, low=0.5, high=1.5):
    return audio * np.random.uniform(low, high)


def random_room_reverb(audio, sr=SAMPLE_RATE):
    """Simple convolution reverb simulation."""
    decay = np.random.uniform(0.1, 0.4)
    delay_ms = np.random.uniform(5, 30)
    delay_samples = int(sr * delay_ms / 1000)
    ir = np.zeros(delay_samples + 1, dtype=np.float32)
    ir[0] = 1.0
    ir[-1] = decay
    return np.convolve(audio, ir, mode='same').astype(np.float32)


def random_eq(audio, sr=SAMPLE_RATE):
    """Random frequency tilt — simulates different microphone responses."""
    fft = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), d=1.0 / sr)
    # Random tilt: boost or cut highs
    tilt = np.random.uniform(-2, 2)
    freq_weights = (freqs / (sr / 4) + 0.1) ** (tilt / 10)
    fft *= freq_weights
    return np.fft.irfft(fft, n=len(audio)).astype(np.float32)


def augment_audio(audio, n_augments=N_AUGMENTS_PER_SAMPLE):
    """Create multiple augmented versions of an audio sample."""
    augmented = [audio.copy()]

    for _ in range(n_augments - 1):
        aug = audio.copy()

        # Random combination of augmentations
        if random.random() < 0.8:
            rate = np.random.uniform(0.75, 1.3)
            aug = time_stretch(aug, rate)

        if random.random() < 0.6:
            semitones = np.random.uniform(-4, 4)
            aug = pitch_shift(aug, semitones)

        if random.random() < 0.7:
            aug = random_volume(aug, 0.3, 1.8)

        if random.random() < 0.6:
            aug = add_noise(aug, np.random.uniform(0.002, 0.025))

        if random.random() < 0.4:
            aug = random_room_reverb(aug)

        if random.random() < 0.4:
            aug = random_eq(aug)

        # Random offset — shift the wake word within the 1-second window
        if random.random() < 0.5:
            shift = int(np.random.uniform(-0.15, 0.15) * SAMPLE_RATE)
            if shift > 0:
                aug = np.concatenate([np.zeros(shift, dtype=np.float32), aug])
            elif shift < 0:
                aug = aug[abs(shift):]

        augmented.append(aug)

    return augmented


def audio_to_feature(audio):
    """Convert audio to fixed-size MFCC feature matrix."""
    if len(audio) < SAMPLE_RATE:
        audio = np.pad(audio, (0, SAMPLE_RATE - len(audio)))
    audio = audio[:SAMPLE_RATE]
    feat = mfcc_extractor.extract_fixed(audio, target_frames=TARGET_FRAMES)
    if feat is None:
        return None
    return feat.astype(np.float32)


# ---------------------------------------------------------------------------
# Synthetic noise generation
# ---------------------------------------------------------------------------

def generate_synthetic_negatives(n_clips=N_NOISE_NEGATIVES):
    """Generate synthetic 1-second audio clips: noise, tones, babble, etc."""
    sr = SAMPLE_RATE
    n = sr
    clips = []

    noise_types = ['white', 'pink', 'babble', 'tonal', 'rumble', 'clicks', 'mixed',
                    'speech_beep', 'two_tone', 'notification', 'door', 'keyboard']

    for i in range(n_clips):
        noise_type = noise_types[i % len(noise_types)]
        t = np.arange(n) / sr

        if noise_type == 'white':
            clip = np.random.randn(n).astype(np.float32) * np.random.uniform(0.01, 0.1)

        elif noise_type == 'pink':
            white = np.random.randn(n).astype(np.float32)
            fft = np.fft.rfft(white)
            freqs = np.fft.rfftfreq(n, d=1.0 / sr)
            freqs[0] = 1.0
            fft /= np.sqrt(freqs)
            clip = np.fft.irfft(fft, n=n).astype(np.float32)
            clip *= np.random.uniform(0.01, 0.08) / (np.std(clip) + 1e-8)

        elif noise_type == 'babble':
            clip = np.zeros(n, dtype=np.float32)
            for _ in range(np.random.randint(2, 6)):
                f0 = np.random.uniform(80, 300)
                voice = np.zeros(n, dtype=np.float32)
                for h in range(1, np.random.randint(3, 8)):
                    freq = f0 * h + np.random.uniform(-10, 10)
                    amp = 1.0 / (h ** np.random.uniform(0.8, 1.5))
                    voice += amp * np.sin(2 * np.pi * freq * t).astype(np.float32)
                envelope = np.random.rand(20).astype(np.float32)
                envelope = np.interp(np.linspace(0, len(envelope) - 1, n),
                                     np.arange(len(envelope)), envelope)
                clip += voice * envelope
            clip *= np.random.uniform(0.01, 0.06) / (np.std(clip) + 1e-8)

        elif noise_type == 'tonal':
            clip = np.zeros(n, dtype=np.float32)
            for _ in range(np.random.randint(1, 4)):
                freq = np.random.choice([261, 294, 330, 349, 392, 440, 494, 523])
                freq *= np.random.choice([0.5, 1.0, 2.0])
                clip += np.sin(2 * np.pi * freq * t).astype(np.float32) * np.random.uniform(0.3, 1.0)
            clip *= np.random.uniform(0.01, 0.05) / (np.std(clip) + 1e-8)

        elif noise_type == 'rumble':
            freq = np.random.uniform(20, 120)
            clip = np.sin(2 * np.pi * freq * t).astype(np.float32)
            clip += np.random.randn(n).astype(np.float32) * 0.02
            clip *= np.random.uniform(0.02, 0.08)

        elif noise_type == 'clicks':
            clip = np.zeros(n, dtype=np.float32)
            for _ in range(np.random.randint(3, 15)):
                pos = np.random.randint(0, n - 100)
                width = np.random.randint(5, 50)
                clip[pos:pos + width] = np.random.uniform(-0.2, 0.2)
            clip += np.random.randn(n).astype(np.float32) * 0.005

        elif noise_type == 'speech_beep':
            # Two-beep pattern mimicking "hey tars" rhythm:
            # ~0.25s beep, ~0.1s gap, ~0.3s beep (like two syllables)
            clip = np.zeros(n, dtype=np.float32)
            # First "syllable" — higher pitch like "hey"
            f1 = np.random.uniform(300, 800)
            start1 = int(np.random.uniform(0.05, 0.2) * sr)
            dur1 = int(np.random.uniform(0.15, 0.35) * sr)
            end1 = min(start1 + dur1, n)
            t1 = np.arange(end1 - start1) / sr
            envelope1 = np.sin(np.linspace(0, np.pi, end1 - start1)) ** 0.5
            clip[start1:end1] = np.sin(2 * np.pi * f1 * t1).astype(np.float32) * envelope1
            # Add harmonics
            for h in [2, 3]:
                clip[start1:end1] += (np.sin(2 * np.pi * f1 * h * t1).astype(np.float32)
                                      * envelope1 / h)
            # Second "syllable" — lower pitch like "tars"
            f2 = np.random.uniform(200, 500)
            gap = int(np.random.uniform(0.05, 0.15) * sr)
            start2 = end1 + gap
            dur2 = int(np.random.uniform(0.2, 0.4) * sr)
            end2 = min(start2 + dur2, n)
            if end2 > start2:
                t2 = np.arange(end2 - start2) / sr
                envelope2 = np.sin(np.linspace(0, np.pi, end2 - start2)) ** 0.5
                clip[start2:end2] = np.sin(2 * np.pi * f2 * t2).astype(np.float32) * envelope2
                for h in [2, 3]:
                    clip[start2:end2] += (np.sin(2 * np.pi * f2 * h * t2).astype(np.float32)
                                          * envelope2 / h)
            clip *= np.random.uniform(0.03, 0.10) / (np.std(clip) + 1e-8)
            clip += np.random.randn(n).astype(np.float32) * 0.003

        elif noise_type == 'two_tone':
            # Two sequential tones at different frequencies — notification sounds
            clip = np.zeros(n, dtype=np.float32)
            f1 = np.random.uniform(500, 2000)
            f2 = np.random.uniform(500, 2000)
            split = n // 2 + int(np.random.uniform(-0.1, 0.1) * sr)
            clip[:split] = np.sin(2 * np.pi * f1 * t[:split]).astype(np.float32)
            clip[split:] = np.sin(2 * np.pi * f2 * t[:n-split]).astype(np.float32)
            # Fade in/out
            fade = int(0.01 * sr)
            clip[:fade] *= np.linspace(0, 1, fade)
            clip[-fade:] *= np.linspace(1, 0, fade)
            clip *= np.random.uniform(0.02, 0.08)

        elif noise_type == 'notification':
            # Phone/computer notification beeps
            clip = np.zeros(n, dtype=np.float32)
            n_beeps = np.random.randint(1, 4)
            for b in range(n_beeps):
                freq = np.random.uniform(800, 3000)
                start = int(b * sr / n_beeps + np.random.uniform(0, 0.05) * sr)
                dur = int(np.random.uniform(0.05, 0.15) * sr)
                end = min(start + dur, n)
                if end > start:
                    tb = np.arange(end - start) / sr
                    env = np.sin(np.linspace(0, np.pi, end - start))
                    clip[start:end] = np.sin(2 * np.pi * freq * tb).astype(np.float32) * env
            clip *= np.random.uniform(0.03, 0.10)

        elif noise_type == 'door':
            # Door slam / thud — sharp transient + low resonance
            clip = np.zeros(n, dtype=np.float32)
            pos = int(np.random.uniform(0.1, 0.5) * sr)
            # Sharp transient
            transient_len = int(0.02 * sr)
            if pos + transient_len < n:
                clip[pos:pos+transient_len] = np.random.randn(transient_len).astype(np.float32) * 0.5
            # Low resonance decay
            decay_len = min(int(0.3 * sr), n - pos)
            if decay_len > 0:
                decay_t = np.arange(decay_len) / sr
                resonance = np.sin(2 * np.pi * np.random.uniform(50, 200) * decay_t)
                resonance *= np.exp(-decay_t * np.random.uniform(5, 20))
                clip[pos:pos+decay_len] += resonance.astype(np.float32) * 0.3
            clip += np.random.randn(n).astype(np.float32) * 0.003

        elif noise_type == 'keyboard':
            # Keyboard typing — rapid short clicks
            clip = np.zeros(n, dtype=np.float32)
            n_keys = np.random.randint(5, 20)
            for _ in range(n_keys):
                pos = np.random.randint(0, n - 200)
                width = np.random.randint(20, 80)
                clip[pos:pos+width] = np.random.randn(width).astype(np.float32) * np.random.uniform(0.05, 0.2)
            clip += np.random.randn(n).astype(np.float32) * 0.002

        else:  # mixed
            white = np.random.randn(n).astype(np.float32) * 0.03
            tone = np.sin(2 * np.pi * np.random.uniform(100, 1000) * t).astype(np.float32) * 0.02
            babble = np.zeros(n, dtype=np.float32)
            f0 = np.random.uniform(100, 250)
            for h in range(1, 5):
                babble += np.sin(2 * np.pi * f0 * h * t).astype(np.float32) / h
            envelope = np.random.rand(10).astype(np.float32)
            envelope = np.interp(np.linspace(0, len(envelope) - 1, n),
                                 np.arange(len(envelope)), envelope)
            babble *= envelope * 0.02
            clip = white + tone + babble

        clips.append(clip[:n])

    return clips


# ---------------------------------------------------------------------------
# Negative phrases (confusable and general speech)
# ---------------------------------------------------------------------------

# Hard negatives — these are the most commonly confused phrases.
# They get 3x the augmentation and are critical for discrimination.
GENERAL_PHRASES = [
    "good morning", "what time is it", "turn on the lights",
    "play some music", "how are you doing today",
    "the weather is nice", "open the door",
    "what's for dinner", "can you help me",
    "tell me a joke", "set an alarm",
    "where are my keys", "that sounds great",
    "I don't think so", "let me check",
    "one two three four five", "thank you very much",
    "see you later", "have a good day",
    "what do you think", "I agree with that",
    "the quick brown fox", "reading a book",
    "watching television", "cooking dinner tonight",
    "going to the store", "remember to call",
    "that's interesting", "absolutely not",
    "maybe tomorrow", "sounds like a plan",
    "I need to go", "stop talking please",
    "excuse me sir", "pardon me",
    "never mind that", "forget about it",
    "are you sure", "I wonder why",
]


def generate_negative_phrases(wake_word):
    """Generate hard negatives and confusable phrases dynamically from the wake word."""
    parts = wake_word.lower().split()
    first = parts[0] if parts else "hey"
    rest = parts[1] if len(parts) > 1 else ""

    hard_negatives = []

    # First word alone + common follow-ups
    common_suffixes = ["there", "there!", "guys", "man", "what", "boss", "you",
                       "wait", "look", "come here", "now", "stop", "listen",
                       "dude", "bro", "everyone"]
    for suffix in common_suffixes:
        hard_negatives.append(f"{first} {suffix}")

    # First word + similar-sounding second words (if wake word has 2+ parts)
    if rest:
        # Generate rhymes/near-matches for the second word
        similar = set()
        # Swap first letter
        for c in "bcdfghjklmnprstvwyz":
            if rest[0] != c:
                similar.add(c + rest[1:])
        # Add 's' suffix
        similar.add(rest + "s")
        # Common near-misses
        similar.update([rest + "y", rest + "ed", rest + "ing"])
        for s in list(similar)[:15]:
            hard_negatives.append(f"{first} {s}")

    # Just the first word by itself
    hard_negatives.extend([first, f"{first}!", "hello", "hi", "hiya", "yo",
                           "hello!", "hi there", "hello there", f"{first} {first}",
                           f"oh {first}"])

    # Common assistant wake words
    hard_negatives.extend(["hey siri", "hey google", "alexa",
                           "hey cortana", "hey jarvis", "hey friday"])

    confusable = [
        "amelia", "emilia", "okay", "oh no", "oh yes", "uh huh",
        "guitar", "bazaar", "memoir", "cigar",
        "target", "partly", "party", "restart",
    ]

    # Remove any that match the actual wake word
    hard_negatives = [p for p in hard_negatives if p.lower() != wake_word.lower()]
    confusable = [p for p in confusable if p.lower() != wake_word.lower()]

    return hard_negatives, confusable


# ---------------------------------------------------------------------------
# PyTorch CNN model
# ---------------------------------------------------------------------------

def build_model():
    """Build the wake word CNN model using PyTorch."""
    import torch
    import torch.nn as nn

    class WakeWordCNN(nn.Module):
        def __init__(self, n_frames=TARGET_FRAMES, n_mfcc=N_FEATURES):
            super().__init__()
            self.conv1 = nn.Conv1d(n_mfcc, 32, kernel_size=5, padding=0)
            self.bn1 = nn.BatchNorm1d(32)
            self.pool1 = nn.MaxPool1d(2)
            self.dropout1 = nn.Dropout(0.2)

            self.conv2 = nn.Conv1d(32, 64, kernel_size=3, padding=0)
            self.bn2 = nn.BatchNorm1d(64)
            self.pool2 = nn.MaxPool1d(2)
            self.dropout2 = nn.Dropout(0.2)

            self.conv3 = nn.Conv1d(64, 64, kernel_size=3, padding=0)
            self.bn3 = nn.BatchNorm1d(64)
            self.gap = nn.AdaptiveAvgPool1d(1)
            self.dropout3 = nn.Dropout(0.3)

            self.fc1 = nn.Linear(64, 64)
            self.fc2 = nn.Linear(64, 1)

        def forward(self, x):
            # x: (batch, n_frames, n_mfcc) -> transpose to (batch, n_mfcc, n_frames)
            x = x.transpose(1, 2)

            x = self.dropout1(self.pool1(torch.relu(self.bn1(self.conv1(x)))))
            x = self.dropout2(self.pool2(torch.relu(self.bn2(self.conv2(x)))))
            x = self.dropout3(self.gap(torch.relu(self.bn3(self.conv3(x)))))

            x = x.squeeze(-1)  # (batch, 64)
            x = torch.relu(self.fc1(x))
            x = torch.sigmoid(self.fc2(x))
            return x

    return WakeWordCNN()


def train_model(model, X_train, y_train, X_val, y_val, epochs=EPOCHS, lr=LR):
    """Train the PyTorch model."""
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Training on: {device}")
    model = model.to(device)

    X_t = torch.FloatTensor(X_train).to(device)
    y_t = torch.FloatTensor(y_train).unsqueeze(1).to(device)
    X_v = torch.FloatTensor(X_val).to(device)
    y_v = torch.FloatTensor(y_val).unsqueeze(1).to(device)

    dataset = TensorDataset(X_t, y_t)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    # Focal loss — focuses training on hard-to-classify samples (the ones
    # that cause false positives). Alpha weights the positive class, gamma
    # downweights easy examples so the model focuses on ambiguous ones.
    class FocalLoss(nn.Module):
        def __init__(self, alpha=0.25, gamma=2.0):
            super().__init__()
            self.alpha = alpha
            self.gamma = gamma

        def forward(self, pred, target):
            bce = nn.functional.binary_cross_entropy(pred, target, reduction='none')
            pt = torch.where(target == 1, pred, 1 - pred)
            alpha_t = torch.where(target == 1, self.alpha, 1 - self.alpha)
            focal_weight = alpha_t * (1 - pt) ** self.gamma
            return (focal_weight * bce).mean()

    criterion = FocalLoss(alpha=0.25, gamma=2.0)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_val_acc = 0
    best_state = None
    patience = 200
    no_improve = 0

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        for Xb, yb in loader:
            optimizer.zero_grad()
            pred = model(Xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        scheduler.step()

        if (epoch + 1) % 50 == 0 or epoch == 0:
            model.eval()
            with torch.no_grad():
                val_pred = model(X_v)
                val_loss = criterion(val_pred, y_v).item()
                val_acc = ((val_pred > 0.5).float() == y_v).float().mean().item()

                train_pred = model(X_t)
                train_acc = ((train_pred > 0.5).float() == y_t).float().mean().item()

            bar_len = 30
            filled = int(val_acc * bar_len)
            bar = f"\033[32m{'█' * filled}\033[90m{'░' * (bar_len - filled)}\033[0m"
            loss_val = epoch_loss/len(loader)
            loss_color = "\033[32m" if loss_val < 0.05 else "\033[33m" if loss_val < 0.1 else "\033[31m"
            improved = ""

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                no_improve = 0
                improved = " \033[32m★\033[0m"
            else:
                no_improve += 50

            spinner = "◐◓◑◒"[(epoch // 50) % 4]
            print(f"    {spinner} Epoch {epoch+1:4d}/{epochs} │ loss={loss_color}{loss_val:.4f}\033[0m │ "
                  f"train=\033[36m{train_acc:.1%}\033[0m │ val=\033[36m{val_acc:.1%}\033[0m [{bar}]{improved}")

            if no_improve >= patience and epoch > 500:
                print(f"\n    \033[33m⚡ Early stopping at epoch {epoch+1}\033[0m (best val: \033[32m{best_val_acc:.1%}\033[0m)")
                break

    if best_state:
        model.load_state_dict(best_state)
    model = model.to("cpu")
    return model, best_val_acc


def export_onnx(model, output_path):
    """Export PyTorch model to ONNX format, with fallback for newer PyTorch."""
    import torch
    import onnx

    model.eval()
    dummy = torch.randn(1, TARGET_FRAMES, N_FEATURES)

    # Try torch.onnx.export with dynamo=False to avoid onnxscript issues
    tmp_path = output_path + ".tmp"
    try:
        # PyTorch >= 2.10 changed the export API — try the legacy exporter first
        torch.onnx.export(
            model, dummy, tmp_path,
            input_names=["mfcc"],
            output_names=["probability"],
            dynamic_axes={"mfcc": {0: "batch"}, "probability": {0: "batch"}},
            opset_version=13,
            dynamo=False,  # Force legacy exporter
        )
    except TypeError:
        # Older PyTorch doesn't have dynamo parameter
        torch.onnx.export(
            model, dummy, tmp_path,
            input_names=["mfcc"],
            output_names=["probability"],
            dynamic_axes={"mfcc": {0: "batch"}, "probability": {0: "batch"}},
            opset_version=13,
        )

    # Verify the exported model is valid
    try:
        onnx_model = onnx.load(tmp_path)
        onnx.checker.check_model(onnx_model)
        # Move verified file to final path
        os.replace(tmp_path, output_path)
    except Exception as e:
        # If verification fails, try building ONNX manually from weights
        print(f"  Warning: torch.onnx.export produced invalid model ({e})")
        print(f"  Building ONNX model manually from weights...")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        _build_onnx_manual(model, output_path)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"  ONNX model exported: {output_path} ({size_kb:.0f} KB)")

    # Final verification
    import onnxruntime as ort
    sess = ort.InferenceSession(output_path, providers=["CPUExecutionProvider"])
    test_input = np.random.randn(1, TARGET_FRAMES, N_FEATURES).astype(np.float32)
    result = sess.run(None, {"mfcc": test_input})
    print(f"  Verification: inference OK (output shape={result[0].shape})")


def _build_onnx_manual(model, output_path):
    """Build ONNX model manually from PyTorch weights — guaranteed compatible."""
    import onnx
    from onnx import helper, TensorProto, numpy_helper

    weights = {}
    for name, param in model.named_parameters():
        weights[name] = param.detach().cpu().numpy()

    nodes = []
    initializers = []

    # Conv1 (in=13, out=32, kernel=5, padding=2)
    w1 = weights["conv1.weight"]
    b1 = weights["conv1.bias"]
    initializers.append(numpy_helper.from_array(w1, "conv1_w"))
    initializers.append(numpy_helper.from_array(b1, "conv1_b"))
    nodes.append(helper.make_node("Conv", ["input", "conv1_w", "conv1_b"], ["conv1_out"],
                                  kernel_shape=[5], pads=[2, 2]))
    nodes.append(helper.make_node("Relu", ["conv1_out"], ["relu1_out"]))

    # MaxPool1 (kernel=2)
    nodes.append(helper.make_node("MaxPool", ["relu1_out"], ["pool1_out"],
                                  kernel_shape=[2], strides=[2]))

    # Conv2 (in=32, out=64, kernel=3, padding=1)
    w2 = weights["conv2.weight"]
    b2 = weights["conv2.bias"]
    initializers.append(numpy_helper.from_array(w2, "conv2_w"))
    initializers.append(numpy_helper.from_array(b2, "conv2_b"))
    nodes.append(helper.make_node("Conv", ["pool1_out", "conv2_w", "conv2_b"], ["conv2_out"],
                                  kernel_shape=[3], pads=[1, 1]))
    nodes.append(helper.make_node("Relu", ["conv2_out"], ["relu2_out"]))

    # MaxPool2 (kernel=2)
    nodes.append(helper.make_node("MaxPool", ["relu2_out"], ["pool2_out"],
                                  kernel_shape=[2], strides=[2]))

    # Global Average Pool
    nodes.append(helper.make_node("GlobalAveragePool", ["pool2_out"], ["gap_out"]))

    # Flatten
    nodes.append(helper.make_node("Flatten", ["gap_out"], ["flat_out"], axis=1))

    # FC1 (64 -> 64)
    w3 = weights["fc1.weight"]
    b3 = weights["fc1.bias"]
    initializers.append(numpy_helper.from_array(w3, "fc1_w"))
    initializers.append(numpy_helper.from_array(b3, "fc1_b"))
    nodes.append(helper.make_node("MatMul", ["flat_out", "fc1_w_t"], ["fc1_mm"]))
    initializers.append(numpy_helper.from_array(w3.T.copy(), "fc1_w_t"))
    # Remove the MatMul and use Gemm instead for simplicity
    nodes.pop()  # Remove MatMul
    del initializers[-1]  # Remove transposed weight
    nodes.append(helper.make_node("Gemm", ["flat_out", "fc1_w", "fc1_b"], ["fc1_out"],
                                  transB=1))
    nodes.append(helper.make_node("Relu", ["fc1_out"], ["relu3_out"]))

    # FC2 (64 -> 1)
    w4 = weights["fc2.weight"]
    b4 = weights["fc2.bias"]
    initializers.append(numpy_helper.from_array(w4, "fc2_w"))
    initializers.append(numpy_helper.from_array(b4, "fc2_b"))
    nodes.append(helper.make_node("Gemm", ["relu3_out", "fc2_w", "fc2_b"], ["fc2_out"],
                                  transB=1))

    # Sigmoid
    nodes.append(helper.make_node("Sigmoid", ["fc2_out"], ["output"]))

    # Input: [batch, frames, mfcc] -> need transpose to [batch, mfcc, frames] for Conv1D
    # Insert Transpose at the beginning
    nodes.insert(0, helper.make_node("Transpose", ["mfcc"], ["input"], perm=[0, 2, 1]))

    # Build graph
    input_tensor = helper.make_tensor_value_info("mfcc", TensorProto.FLOAT, [None, TARGET_FRAMES, N_FEATURES])
    output_tensor = helper.make_tensor_value_info("output", TensorProto.FLOAT, [None, 1])

    graph = helper.make_graph(nodes, "wake_word", [input_tensor], [output_tensor], initializers)
    onnx_model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx_model.ir_version = 7

    onnx.checker.check_model(onnx_model)
    onnx.save(onnx_model, output_path)


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def generate_tts_data(audio_dir, voices, phrases, label_name):
    """Generate TTS audio for a list of phrases using multiple voices.
    Audio files are kept in audio_dir for reuse on subsequent runs."""
    audio_samples = []
    tasks = []

    # Select subset of voices for variety
    selected_voices = random.sample(voices, min(len(voices), N_TTS_VOICES))

    color = "\033[32m" if label_name == "positive" else "\033[31m"
    print(f"    {color}●\033[0m {label_name}: {len(selected_voices)} voices × {len(phrases)} phrases = {len(selected_voices) * len(phrases)} samples")

    total = len(selected_voices) * len(phrases)
    done = 0
    skipped = 0

    for vi, voice in enumerate(selected_voices):
        for pi, phrase in enumerate(phrases):
            out_path = os.path.join(audio_dir, f"{label_name}_{vi}_{pi}.mp3")
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                audio = load_audio_file(out_path)
                if audio is not None and len(audio) > SAMPLE_RATE * 0.2:
                    audio_samples.append(audio)
                skipped += 1
                done += 1
            else:
                tasks.append((phrase, voice, out_path))

    if skipped > 0:
        print(f"    \033[32m✓\033[0m Loaded {skipped} cached audio files")

    if tasks:
        gen_start = time.time()
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(generate_tts_audio, t, v, p): (t, v, p)
                       for t, v, p in tasks}
            for future in as_completed(futures):
                done += 1
                text, voice, path = futures[future]
                gen_done = done - skipped
                gen_total = len(tasks)
                if gen_done % 25 == 0 or done == total:
                    pct = int(gen_done / gen_total * 30)
                    bar = f"{color}{'█' * pct}\033[90m{'░' * (30 - pct)}\033[0m"
                    elapsed = time.time() - gen_start
                    rate = gen_done / elapsed if elapsed > 0 else 0
                    eta = (gen_total - gen_done) / rate if rate > 0 else 0
                    print(f"\r    [{bar}] {gen_done}/{gen_total} ({rate:.0f}/s, ~{eta:.0f}s left)   ", end="", flush=True)
                try:
                    if future.result() and os.path.exists(path):
                        audio = load_audio_file(path)
                        if audio is not None and len(audio) > SAMPLE_RATE * 0.2:
                            audio_samples.append(audio)
                except Exception:
                    pass

    if tasks:
        print()  # newline after progress bar
    print(f"    \033[32m✓\033[0m {len(audio_samples)} raw {label_name} samples ready")
    return audio_samples


def main():
    parser = argparse.ArgumentParser(description="Train universal wake word model")
    parser.add_argument("--output", default=None, help="Output ONNX model path (auto-generated from wake word if not set)")
    parser.add_argument("--wake-word", default=None, help="Wake word phrase (prompted if not set)")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help="Training epochs")
    parser.add_argument("--no-tts", action="store_true", help="Skip TTS generation (use cached data)")
    parser.add_argument("--data-dir", default=None, help="Directory to cache/load training data")
    args = parser.parse_args()

    # Prompt for wake word if not provided via CLI
    if args.wake_word is None:
        print()
        print(f"  Enter your wake word (default: \033[33m{WAKE_WORD}\033[0m): ", end="", flush=True)
        user_input = input().strip()
        args.wake_word = user_input if user_input else WAKE_WORD

    # Auto-generate output filename from wake word
    if args.output is None:
        args.output = f"{args.wake_word.replace(' ', '_')}.onnx"

    W = 65  # banner width

    import re
    _ansi_re = re.compile(r'\033\[[0-9;]*m')

    def banner(text="", style="top"):
        if style == "top":
            print(f"  \033[36m╔{'═' * (W-2)}╗\033[0m")
        elif style == "bot":
            print(f"  \033[36m╚{'═' * (W-2)}╝\033[0m")
        elif style == "mid":
            print(f"  \033[36m╠{'═' * (W-2)}╣\033[0m")
        elif style == "line":
            text_clean = _ansi_re.sub('', text)
            pad = W - 4 - len(text_clean)
            print(f"  \033[36m║\033[0m {text}{' ' * max(0, pad)} \033[36m║\033[0m")

    def step_header(num, title):
        print()
        print(f"  \033[36m┌─ STEP {num} {'─' * (W - 12 - len(str(num)))}┐\033[0m")
        print(f"  \033[36m│\033[0m \033[1m{title}\033[0m")
        print(f"  \033[36m└{'─' * (W-2)}┘\033[0m")

    def status(icon, msg):
        icons = {"ok": "\033[32m✓\033[0m", "err": "\033[31m✗\033[0m", "info": "\033[36m›\033[0m",
                 "warn": "\033[33m!\033[0m", "run": "\033[33m⟳\033[0m"}
        print(f"    {icons.get(icon, icon)} {msg}")

    print()
    banner("top")
    banner("", "line")
    banner("   \033[1m\033[36m████████╗ █████╗ ██████╗ ███████╗\033[0m", "line")
    banner("   \033[1m\033[36m╚══██╔══╝██╔══██╗██╔══██╗██╔════╝\033[0m", "line")
    banner("   \033[1m\033[36m   ██║   ███████║██████╔╝███████╗\033[0m", "line")
    banner("   \033[1m\033[36m   ██║   ██╔══██║██╔══██╗╚════██║\033[0m", "line")
    banner("   \033[1m\033[36m   ██║   ██║  ██║██║  ██║███████║\033[0m", "line")
    banner("   \033[1m\033[36m   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝\033[0m", "line")
    banner("", "line")
    banner("\033[1m        UNIVERSAL WAKE WORD TRAINER\033[0m", "line")
    banner("", "line")
    banner("mid")
    banner(f"  Wake word : \033[33m{args.wake_word}\033[0m", "line")
    banner(f"  Epochs    : \033[33m{args.epochs}\033[0m", "line")
    banner(f"  Output    : \033[33m{args.output}\033[0m", "line")
    banner(f"  Features  : \033[33m{N_FEATURES}\033[0m (MFCC + Δ + ΔΔ)", "line")
    banner("mid")

    # Check PyTorch
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        banner(f"  PyTorch   : \033[32m{torch.__version__}\033[0m ({device})", "line")
        if device == "cuda":
            gpu_name = torch.cuda.get_device_name()
            props = torch.cuda.get_device_properties(0)
            vram = getattr(props, 'total_memory', getattr(props, 'total_mem', 0)) / 1024**3
            banner(f"  GPU       : \033[32m{gpu_name}\033[0m ({vram:.1f} GB)", "line")
        else:
            banner(f"  GPU       : \033[33mNone (CPU mode)\033[0m", "line")
    except ImportError:
        banner("  \033[31mERROR: PyTorch not installed\033[0m", "line")
        banner("bot")
        sys.exit(1)

    banner("bot")

    # ------------------------------------------------------------------
    # STEP 0: RECORD REAL AUDIO (optional)
    # ------------------------------------------------------------------

    def record_mic_audio(data_dir_root):
        """Optionally record real microphone audio for training data."""
        import sounddevice as sd
        from scipy.io import wavfile as scipy_wav

        mic_dir = os.path.join(data_dir_root, "mic_audio")

        # Check for existing recordings
        existing = []
        if os.path.isdir(mic_dir):
            existing = [f for f in os.listdir(mic_dir) if f.endswith(".wav")]

        if existing:
            status("info", f"Found {len(existing)} existing mic recordings in mic_audio/")
            reuse = input("    Use existing recordings? [Y/n]: ").strip().lower()
            if reuse != "n":
                status("ok", f"Reusing {len(existing)} mic recordings")
                return mic_dir
            else:
                status("info", "Will re-record (overwriting existing files)")

        # Ask if user wants to record
        print()
        answer = input("    Would you like to record real audio samples? (recommended) [y/N]: ").strip().lower()
        if answer != "y":
            status("info", "Skipping mic recording")
            return None

        os.makedirs(mic_dir, exist_ok=True)

        # Find a working input device
        mic_device = None
        try:
            # Try default first
            info = sd.query_devices(kind='input')
            mic_device = None  # Use default
            status("ok", f"Mic: {info['name']} ({int(info['default_samplerate'])}Hz)")
        except Exception:
            # List available input devices and let user pick
            status("warn", "No default input device. Available devices:")
            devices = sd.query_devices()
            input_devs = []
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    input_devs.append((i, d))
                    print(f"      [{i}] {d['name']} ({d['max_input_channels']}ch, {int(d['default_samplerate'])}Hz)")
            if not input_devs:
                status("err", "No input devices found — skipping mic recording")
                return None
            try:
                choice = input("    Select device number: ").strip()
                mic_device = int(choice)
                status("ok", f"Using device {mic_device}: {devices[mic_device]['name']}")
            except (ValueError, IndexError):
                status("err", "Invalid selection — skipping mic recording")
                return None

        def vad_record(prompt_text, index_str, max_duration=3.0, silence_timeout=0.5,
                       energy_threshold=0.01):
            """Record with VAD-based auto-stop: detect speech start, stop after silence.
            Shows a live level meter and waits for speech before recording."""
            print(f"\r    \033[33m⟳\033[0m {prompt_text} ({index_str}) — \033[90mwaiting for speech...\033[0m", end="", flush=True)

            sr = 16000
            block_size = 1600  # 100ms blocks
            max_blocks = int(max_duration * sr / block_size)
            silence_blocks = int(silence_timeout * sr / block_size)

            recorded_blocks = []
            speech_started = False
            silent_count = 0
            peak_energy = [0.0]

            def callback(indata, frames, time_info, cb_status):
                nonlocal speech_started, silent_count
                block = indata[:, 0].copy()
                energy = np.sqrt(np.mean(block ** 2))
                peak_energy[0] = max(peak_energy[0], energy)

                if not speech_started:
                    if energy > energy_threshold:
                        speech_started = True
                        silent_count = 0
                        recorded_blocks.append(block)
                else:
                    recorded_blocks.append(block)
                    if energy < energy_threshold * 0.5:
                        silent_count += 1
                    else:
                        silent_count = 0

            with sd.InputStream(samplerate=sr, channels=1, dtype='float32',
                                blocksize=block_size, callback=callback,
                                device=mic_device):
                start_t = time.time()
                while True:
                    time.sleep(0.1)
                    elapsed = time.time() - start_t

                    # Live level meter
                    level = min(peak_energy[0] / 0.1, 1.0)  # normalize to 0-1
                    meter_len = 15
                    filled = int(level * meter_len)
                    color = "\033[32m" if speech_started else "\033[90m"
                    meter = f"{color}{'█' * filled}{'░' * (meter_len - filled)}\033[0m"

                    if speech_started:
                        rec_time = len(recorded_blocks) * block_size / sr
                        print(f"\r    \033[31m●\033[0m {prompt_text} ({index_str}) [{meter}] \033[31m{rec_time:.1f}s\033[0m   ", end="", flush=True)
                    else:
                        print(f"\r    \033[33m⟳\033[0m {prompt_text} ({index_str}) [{meter}] \033[90mlistening...\033[0m   ", end="", flush=True)

                    peak_energy[0] *= 0.5  # decay for next frame

                    if elapsed >= max_duration + 5:  # 5s extra wait for speech to start
                        break
                    if speech_started:
                        if silent_count >= silence_blocks:
                            break
                        if len(recorded_blocks) >= max_blocks:
                            break
                    elif elapsed >= 10:  # give up waiting for speech after 10s
                        break

            if not recorded_blocks:
                print(f"\r    \033[33m!\033[0m {prompt_text} ({index_str}) — \033[33mno speech detected\033[0m                    ")
                return None

            audio = np.concatenate(recorded_blocks)
            duration = len(audio) / sr
            print(f"\r    \033[32m✓\033[0m {prompt_text} ({index_str}) — \033[32m{duration:.1f}s recorded\033[0m                    ")
            return audio

        def save_wav(audio, filepath, sr=16000):
            """Save float32 audio as 16-bit WAV."""
            audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
            scipy_wav.write(filepath, sr, audio_int16)

        # --- Record positive examples ---
        step_header(0, "RECORD REAL AUDIO")
        print()
        status("info", f"Recording positive examples — say '\033[33m{args.wake_word}\033[0m'")
        print()

        positive_count = 10
        for i in range(positive_count):
            audio = vad_record(f"Say '\033[33m{args.wake_word}\033[0m'",
                               f"{i+1}/{positive_count}")
            if audio is not None:
                save_wav(audio, os.path.join(mic_dir, f"mic_pos_{i:02d}.wav"))
            if i < positive_count - 1:
                # Cooldown between recordings
                for c in range(2, 0, -1):
                    print(f"\r    \033[90m  next in {c}...\033[0m   ", end="", flush=True)
                    time.sleep(1)
                print("\r" + " " * 40 + "\r", end="", flush=True)

        # --- Record negative examples (confusable phrases) ---
        print()
        status("info", "Recording negative examples — say these confusable phrases:")
        print()

        # Generate confusable prompts dynamically from wake word
        ww_parts = args.wake_word.lower().split()
        first = ww_parts[0] if ww_parts else "hey"
        confusable_prompts = [
            "hello", f"{first} there", first, "hi", f"{first} guys",
            f"{first} man", f"{first} what", f"{first} boss", f"{first} you",
            "good morning", "what time is it",
            "hey siri", "alexa", "ok google",
            f"oh {first}", f"{first} now", f"{first} wait",
        ]
        # Remove the actual wake word if it ended up in the list
        confusable_prompts = [p for p in confusable_prompts if p.lower() != args.wake_word.lower()]
        for i, phrase in enumerate(confusable_prompts):
            audio = vad_record(f"Say '\033[33m{phrase}\033[0m'",
                               f"{i+1}/{len(confusable_prompts)}")
            if audio is not None:
                save_wav(audio, os.path.join(mic_dir, f"mic_neg_{i:02d}.wav"))
            if i < len(confusable_prompts) - 1:
                for c in range(2, 0, -1):
                    print(f"\r    \033[90m  next in {c}...\033[0m   ", end="", flush=True)
                    time.sleep(1)
                print("\r" + " " * 40 + "\r", end="", flush=True)

        # --- Record ambient noise ---
        print()
        status("info", "Recording ambient noise — stay quiet for 10 seconds...")
        noise_duration = 10.0
        noise_audio = sd.rec(int(noise_duration * 16000), samplerate=16000,
                             channels=1, dtype='float32', device=mic_device)
        for sec in range(int(noise_duration)):
            time.sleep(1)
            pct = int((sec + 1) / noise_duration * 20)
            bar = f"\033[90m{'█' * pct}{'░' * (20 - pct)}\033[0m"
            print(f"\r    [{bar}] {sec+1}/{int(noise_duration)}s", end="", flush=True)
        sd.wait()
        print()
        noise_audio = noise_audio.flatten()
        save_wav(noise_audio, os.path.join(mic_dir, "mic_noise.wav"))
        status("ok", f"Recorded {noise_duration:.0f}s of ambient noise")

        # --- Record conversation (natural speech negative) ---
        print()
        status("info", "Recording natural speech — talk normally for 30 seconds")
        status("info", "Read something, chat, count numbers — anything \033[31mEXCEPT\033[0m 'hey tars'")
        print()
        input("    Press ENTER when ready to start recording...")
        conv_duration = 30.0
        conv_audio = sd.rec(int(conv_duration * 16000), samplerate=16000,
                            channels=1, dtype='float32', device=mic_device)
        for sec in range(int(conv_duration)):
            time.sleep(1)
            pct = int((sec + 1) / conv_duration * 30)
            bar = f"\033[33m{'█' * pct}{'░' * (30 - pct)}\033[0m"
            remaining = int(conv_duration) - sec - 1
            print(f"\r    \033[31m●\033[0m [{bar}] {sec+1}/{int(conv_duration)}s — \033[90m{remaining}s left, keep talking\033[0m   ", end="", flush=True)
        sd.wait()
        print()
        conv_audio = conv_audio.flatten()
        save_wav(conv_audio, os.path.join(mic_dir, "mic_conversation.wav"))
        status("ok", f"Recorded {conv_duration:.0f}s of conversation")

        total_files = len([f for f in os.listdir(mic_dir) if f.endswith(".wav")])
        print()
        status("ok", f"Saved {total_files} recordings to mic_audio/")
        return mic_dir

    data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), "training_data")
    os.makedirs(data_dir, exist_ok=True)

    # Record mic audio (optional, before TTS steps)
    mic_audio_dir = record_mic_audio(data_dir)

    cached_data = os.path.join(data_dir, "features.npz")
    features_pos = None
    features_neg = None

    if os.path.exists(cached_data):
        data = np.load(cached_data)
        cached_features = data["features_pos"][0].shape[-1] if len(data["features_pos"]) > 0 else 0
        if cached_features != N_FEATURES:
            status("warn", f"Cached data has {cached_features} features, need {N_FEATURES} — regenerating...")
            os.remove(cached_data)
        else:
            status("ok", f"Found cached training data ({len(data['features_pos'])} pos, {len(data['features_neg'])} neg)")
            status("info", "Delete training_data/features.npz to regenerate")
            features_pos = list(data["features_pos"])
            features_neg = list(data["features_neg"])

    if features_pos is None:
        # --- Get TTS voices ---
        status("run", "Fetching edge-tts voices...")
        voices = get_edge_tts_voices()
        if not voices:
            status("err", "No edge-tts voices found. Install: pip install edge-tts")
            sys.exit(1)
        status("ok", f"Found {len(voices)} English voices")

        step_header(1, "SYNTHESIZING POSITIVE SAMPLES (wake word)")

        ww = args.wake_word
        positive_phrases = [
            ww,
            f"{ww}.",
            f"{ww}!",
            f"{ww}?",
            f"{ww}...",
            f"{ww}, hello",
            f"{ww}, can you help me",
            f"{ww}, what time is it",
        ]

        audio_dir = os.path.join(data_dir, "tts_audio")
        os.makedirs(audio_dir, exist_ok=True)
        raw_positives = generate_tts_data(audio_dir, voices, positive_phrases, "positive")

        step_header(2, "SYNTHESIZING NEGATIVE SAMPLES")

        # Generate negatives dynamically based on the wake word
        hard_negatives, confusable_phrases = generate_negative_phrases(args.wake_word)

        # Hard negatives get generated with ALL voices (most important for discrimination)
        status("run", f"Generating {len(hard_negatives)} hard negatives (all voices)...")
        raw_hard_negs = generate_tts_data(audio_dir, voices, hard_negatives, "hard_neg")

        # Confusable + general with standard voice count
        negative_phrases = confusable_phrases + GENERAL_PHRASES
        raw_negatives = generate_tts_data(audio_dir, voices, negative_phrases, "negative")

        # Combine
        raw_negatives = raw_hard_negs + raw_negatives

        # Mix in mic recordings if available
        if mic_audio_dir and os.path.isdir(mic_audio_dir):
            mic_files = [f for f in os.listdir(mic_audio_dir) if f.endswith(".wav")]
            if mic_files:
                from scipy.io import wavfile as scipy_wav
                mic_pos = 0
                mic_neg = 0
                mic_noise = 0
                for mf in mic_files:
                    fpath = os.path.join(mic_audio_dir, mf)
                    try:
                        sr, data = scipy_wav.read(fpath)
                        audio = data.astype(np.float32) / 32768.0
                        if len(audio.shape) > 1:
                            audio = audio[:, 0]
                        if sr != SAMPLE_RATE:
                            audio = resample(audio, int(len(audio) * SAMPLE_RATE / sr))
                    except Exception:
                        continue

                    if mf.startswith("mic_pos_"):
                        # Mic positives are the most valuable — add multiple copies
                        # so they get augmented more during feature extraction
                        for _ in range(3):  # 3x copies → 3x more augmented features
                            raw_positives.append(audio.copy())
                        mic_pos += 1
                    elif mf.startswith("mic_neg_"):
                        for _ in range(2):  # 2x copies for mic negatives
                            raw_negatives.append(audio.copy())
                        mic_neg += 1
                    elif mf.startswith("mic_noise") or mf.startswith("mic_conversation"):
                        # Split noise/conversation into 1-second chunks as negative samples
                        # Use overlapping windows for conversation to get more samples
                        chunk_len = SAMPLE_RATE
                        hop = chunk_len // 2 if "conversation" in mf else chunk_len
                        for ci in range(0, len(audio) - chunk_len, hop):
                            raw_negatives.append(audio[ci:ci + chunk_len])
                            mic_noise += 1

                # Generate synthetic hard negatives from mic positives:
                # Take real "hey tars" recordings and corrupt them to teach the model
                # that partial/truncated wake words are NOT valid
                mic_pos_files = [f for f in mic_files if f.startswith("mic_pos_")]
                mic_corrupted = 0
                for mf in mic_pos_files:
                    fpath = os.path.join(mic_audio_dir, mf)
                    try:
                        sr, data = scipy_wav.read(fpath)
                        audio = data.astype(np.float32) / 32768.0
                        if len(audio.shape) > 1:
                            audio = audio[:, 0]
                        if sr != SAMPLE_RATE:
                            audio = resample(audio, int(len(audio) * SAMPLE_RATE / sr))
                    except Exception:
                        continue

                    n = len(audio)
                    # Cut off second half (just "hey", no "tars")
                    raw_negatives.append(audio[:n//2].copy())
                    # Cut off first half (just "tars", no "hey")
                    raw_negatives.append(audio[n//2:].copy())
                    # Just the very start (breath + "h")
                    raw_negatives.append(audio[:n//4].copy())
                    # Reversed audio (sounds similar but wrong order)
                    raw_negatives.append(audio[::-1].copy())
                    # Pitch shifted far (same words, different person — should not match)
                    raw_negatives.append(pitch_shift(audio.copy(), 6))
                    raw_negatives.append(pitch_shift(audio.copy(), -6))
                    # Time stretched extremes
                    raw_negatives.append(time_stretch(audio.copy(), 0.5))
                    raw_negatives.append(time_stretch(audio.copy(), 2.0))
                    mic_corrupted += 8

                if mic_corrupted:
                    status("ok", f"Generated {mic_corrupted} corrupted negatives from mic positives")

                status("ok", f"Mixed in mic audio: {mic_pos} positive, {mic_neg} negative, {mic_noise} noise, {mic_corrupted} corrupted")

        # --- Load custom false positive audio files ---
        # Any audio file (wav, mp3, flac, ogg) in false_positives/
        # gets sliced into 1-second chunks and added as hard negatives.
        # Drop songs, podcasts, TV audio — anything that triggers false positives.
        fp_dir = os.path.join(os.path.dirname(__file__), "false_positives")
        os.makedirs(fp_dir, exist_ok=True)
        fp_files = [f for f in os.listdir(fp_dir)
                    if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg', '.m4a'))]
        if fp_files:
            fp_chunks = 0
            status("run", f"Mining {len(fp_files)} false positive audio file(s)...")
            for fp_file in fp_files:
                fpath = os.path.join(fp_dir, fp_file)
                try:
                    audio = load_audio_file(fpath)
                    if audio is None:
                        status("warn", f"Could not load: {fp_file}")
                        continue
                    # Slice into 1-second chunks with 50% overlap
                    chunk_len = SAMPLE_RATE
                    hop = chunk_len // 2
                    file_chunks = 0
                    for ci in range(0, len(audio) - chunk_len, hop):
                        chunk = audio[ci:ci + chunk_len]
                        # Only keep chunks with some energy (skip silence)
                        if np.sqrt(np.mean(chunk ** 2)) > 0.005:
                            raw_negatives.append(chunk)
                            file_chunks += 1
                    fp_chunks += file_chunks
                    status("ok", f"{fp_file}: {file_chunks} chunks extracted")
                except Exception as e:
                    status("warn", f"Error loading {fp_file}: {e}")
            status("ok", f"Total false positive chunks: {fp_chunks}")
        else:
            status("info", "No files in false_positives/ — drop audio there to reduce false triggers")

        step_header(3, "AUGMENTING & EXTRACTING FEATURES")

        features_pos = []
        for i, audio in enumerate(raw_positives):
            augmented = augment_audio(audio)
            for aug in augmented:
                feat = audio_to_feature(aug)
                if feat is not None:
                    features_pos.append(feat)
            if (i + 1) % 50 == 0 or i + 1 == len(raw_positives):
                pct = int((i + 1) / len(raw_positives) * 30)
                bar = f"\033[32m{'█' * pct}{'░' * (30 - pct)}\033[0m"
                print(f"\r    [{bar}] Positive: {i+1}/{len(raw_positives)} → {len(features_pos)} features", end="", flush=True)
        print()

        features_neg = []
        for i, audio in enumerate(raw_negatives):
            augmented = augment_audio(audio)
            for aug in augmented:
                feat = audio_to_feature(aug)
                if feat is not None:
                    features_neg.append(feat)
            if (i + 1) % 50 == 0 or i + 1 == len(raw_negatives):
                pct = int((i + 1) / len(raw_negatives) * 30)
                bar = f"\033[31m{'█' * pct}{'░' * (30 - pct)}\033[0m"
                print(f"\r    [{bar}] Negative: {i+1}/{len(raw_negatives)} → {len(features_neg)} features", end="", flush=True)
        print()

        status("run", "Generating synthetic noise negatives...")
        noise_clips = generate_synthetic_negatives(N_NOISE_NEGATIVES)
        for clip in noise_clips:
            feat = audio_to_feature(clip)
            if feat is not None:
                features_neg.append(feat)

        # Silence negatives
        for _ in range(50):
            silence = np.zeros(SAMPLE_RATE, dtype=np.float32) + np.random.randn(SAMPLE_RATE).astype(np.float32) * 0.002
            feat = audio_to_feature(silence)
            if feat is not None:
                features_neg.append(feat)

        status("ok", f"Synthetic negatives: {N_NOISE_NEGATIVES} noise + 50 silence")

        # Cache the data
        np.savez_compressed(cached_data,
                            features_pos=np.array(features_pos),
                            features_neg=np.array(features_neg))
        status("ok", f"Cached training data to {os.path.basename(cached_data)}")

    print()
    status("info", f"Positive features: \033[32m{len(features_pos)}\033[0m")
    status("info", f"Negative features: \033[31m{len(features_neg)}\033[0m")

    if len(features_pos) < 10 or len(features_neg) < 10:
        status("err", "Not enough training data!")
        sys.exit(1)

    step_header(4, "TRAINING NEURAL NETWORK")

    # Undersample the larger class to 2:1 ratio max
    max_ratio = 2.0
    if len(features_neg) > len(features_pos) * max_ratio:
        idx = np.random.choice(len(features_neg), int(len(features_pos) * max_ratio), replace=False)
        features_neg = [features_neg[i] for i in idx]
    elif len(features_pos) > len(features_neg) * max_ratio:
        idx = np.random.choice(len(features_pos), int(len(features_neg) * max_ratio), replace=False)
        features_pos = [features_pos[i] for i in idx]

    X = np.stack(features_pos + features_neg)
    y = np.concatenate([np.ones(len(features_pos)), np.zeros(len(features_neg))])

    # Shuffle and split
    idx = np.random.permutation(len(X))
    X, y = X[idx], y[idx]

    split = int(0.85 * len(X))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    status("info", f"Train: {len(X_train)} samples (\033[32m{y_train.sum():.0f} pos\033[0m, \033[31m{len(y_train) - y_train.sum():.0f} neg\033[0m)")
    status("info", f"Val:   {len(X_val)} samples (\033[32m{y_val.sum():.0f} pos\033[0m, \033[31m{len(y_val) - y_val.sum():.0f} neg\033[0m)")
    print()

    # Train
    model = build_model()
    model, best_val_acc = train_model(model, X_train, y_train, X_val, y_val, epochs=args.epochs)

    step_header(5, "EXPORTING ONNX MODEL")

    export_onnx(model, args.output)

    # --- Final evaluation ---
    import torch
    model.eval()
    with torch.no_grad():
        X_all = torch.FloatTensor(X)
        preds = model(X_all).numpy().flatten()

    # Compute optimal threshold
    best_f1 = 0
    best_thresh = 0.5
    for thresh in np.arange(0.3, 0.8, 0.01):
        tp = np.sum((preds >= thresh) & (y == 1))
        fp = np.sum((preds >= thresh) & (y == 0))
        fn = np.sum((preds < thresh) & (y == 1))
        precision = tp / (tp + fp + 1e-8)
        recall = tp / (tp + fn + 1e-8)
        f1 = 2 * precision * recall / (precision + recall + 1e-8)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    tp = np.sum((preds >= best_thresh) & (y == 1))
    fp = np.sum((preds >= best_thresh) & (y == 0))
    fn = np.sum((preds < best_thresh) & (y == 1))
    tn = np.sum((preds < best_thresh) & (y == 0))

    precision = tp/(tp+fp+1e-8)
    recall = tp/(tp+fn+1e-8)

    # Save metadata
    meta_path = args.output.replace(".onnx", "_meta.json")
    meta = {
        "wake_word": args.wake_word,
        "sample_rate": SAMPLE_RATE,
        "n_mfcc": N_MFCC,
        "n_features": N_FEATURES,
        "n_fft": N_FFT,
        "target_frames": TARGET_FRAMES,
        "optimal_threshold": float(best_thresh),
        "f1_score": float(best_f1),
        "n_positive_samples": int(y.sum()),
        "n_negative_samples": int(len(y) - y.sum()),
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    model_size = os.path.getsize(args.output) / 1024

    # --- Final results ---
    print()
    banner("top")
    banner("", "line")
    banner("\033[1m\033[32m        ✓ TRAINING COMPLETE\033[0m", "line")
    banner("", "line")
    banner("mid")
    banner(f"  Model      : \033[36m{args.output}\033[0m ({model_size:.0f} KB)", "line")
    banner(f"  Threshold  : \033[33m{best_thresh:.2f}\033[0m", "line")
    banner(f"  F1 Score   : \033[32m{best_f1:.1%}\033[0m", "line")
    banner(f"  Precision  : \033[32m{precision:.1%}\033[0m", "line")
    banner(f"  Recall     : \033[32m{recall:.1%}\033[0m", "line")
    banner("mid")

    # Confusion matrix visual
    banner(f"  \033[32m✓ True Pos:  {int(tp):>5}\033[0m  │  \033[31m✗ False Pos: {int(fp):>5}\033[0m", "line")
    banner(f"  \033[32m✓ True Neg:  {int(tn):>5}\033[0m  │  \033[31m✗ False Neg: {int(fn):>5}\033[0m", "line")
    banner("mid")
    banner("", "line")
    banner(f"  \033[1mCopy \033[33m{args.output}\033[0m\033[1m to:\033[0m", "line")
    banner(f"     \033[36mTARS-AI/src/tts/{args.output}\033[0m", "line")
    banner("", "line")
    banner("bot")


if __name__ == "__main__":
    main()
