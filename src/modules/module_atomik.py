"""
Module: Atomik WakeWord
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import numpy as np
from collections import deque
import pickle
import os
import time
import sys
import json
from scipy.fftpack import dct

from modules.module_mic import open_native_stream, make_resampling_callback

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    def __init__(self, sample_rate=16000, energy_threshold=0.008, silence_duration=0.5):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_frames = int(silence_duration * sample_rate / 1024)

    def get_energy(self, audio_chunk):
        return np.sqrt(np.mean(audio_chunk ** 2))

    def is_speech(self, audio_chunk):
        return self.get_energy(audio_chunk) > self.energy_threshold

    def trim_silence(self, audio_array, chunk_size=1024):
        chunks = [audio_array[i:i+chunk_size] for i in range(0, len(audio_array), chunk_size)]

        start_idx = 0
        for i, chunk in enumerate(chunks):
            if self.is_speech(chunk):
                start_idx = max(0, i - 1)
                break

        end_idx = len(chunks)
        for i in range(len(chunks) - 1, -1, -1):
            if self.is_speech(chunks[i]):
                end_idx = min(len(chunks), i + 2)
                break

        start_sample = start_idx * chunk_size
        end_sample = min(end_idx * chunk_size, len(audio_array))

        return audio_array[start_sample:end_sample]


class MFCCExtractor:
    def __init__(self, sample_rate=16000, n_mfcc=13, n_fft=512):
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.n_mels = 40
        self.mel_filters = self.create_mel_filterbank()

    def hz_to_mel(self, hz):
        return 2595 * np.log10(1 + hz / 700.0)

    def mel_to_hz(self, mel):
        return 700 * (10**(mel / 2595.0) - 1)

    def create_mel_filterbank(self):
        low_freq_mel = 0
        high_freq_mel = self.hz_to_mel(self.sample_rate / 2)
        mel_points = np.linspace(low_freq_mel, high_freq_mel, self.n_mels + 2)
        hz_points = self.mel_to_hz(mel_points)
        bin_points = np.floor((self.n_fft + 1) * hz_points / self.sample_rate).astype(int)

        fbank = np.zeros((self.n_mels, self.n_fft // 2 + 1))
        for m in range(1, self.n_mels + 1):
            f_left, f_center, f_right = bin_points[m - 1:m + 2]
            for k in range(f_left, f_center):
                fbank[m - 1, k] = (k - f_left) / (f_center - f_left)
            for k in range(f_center, f_right):
                fbank[m - 1, k] = (f_right - k) / (f_right - f_center)
        return fbank

    def extract_mfcc(self, audio):
        if len(audio) < self.n_fft:
            return None

        emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
        frame_length = self.n_fft
        frame_step = frame_length // 2
        num_frames = 1 + int(np.floor((len(emphasized) - frame_length) / frame_step))

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

    def extract_fixed(self, audio, target_frames=62):
        """Extract MFCC + delta + delta-delta and pad/truncate to fixed frames."""
        mfcc = self.extract_mfcc(audio)
        if mfcc is None:
            return None

        # Check if delta features are needed (39 channels vs 13)
        # Set by WakeWordSystem when loading ONNX model
        use_deltas = getattr(self, '_use_deltas', False)

        if use_deltas:
            delta = self._compute_deltas(mfcc)
            delta2 = self._compute_deltas(delta)
            features = np.hstack([mfcc, delta, delta2])  # (frames, 39)
        else:
            features = mfcc

        n = features.shape[0]
        if n >= target_frames:
            return features[:target_frames]
        pad = np.zeros((target_frames - n, features.shape[1]))
        return np.vstack([features, pad])


# ---------------------------------------------------------------------------
# 1D CNN classifier — preserves temporal structure of MFCC frames
# ---------------------------------------------------------------------------

def _relu(x):
    return np.maximum(0, x)

def _sigmoid(x):
    x = np.clip(x, -500, 500)
    return 1.0 / (1.0 + np.exp(-x))

def _binary_cross_entropy(pred, target):
    pred = np.clip(pred, 1e-7, 1 - 1e-7)
    return -np.mean(target * np.log(pred) + (1 - target) * np.log(1 - pred))


def _conv1d(x, W, b):
    """1D convolution. x: (batch, time, channels), W: (kernel, in_ch, out_ch), b: (out_ch,).
    Returns (batch, time - kernel + 1, out_ch).
    """
    batch, T, C_in = x.shape
    K, _, C_out = W.shape
    T_out = T - K + 1
    # im2col: extract patches
    cols = np.zeros((batch, T_out, K * C_in), dtype=x.dtype)
    for t in range(T_out):
        cols[:, t, :] = x[:, t:t+K, :].reshape(batch, -1)
    # Matrix multiply: (batch, T_out, K*C_in) @ (K*C_in, C_out) -> (batch, T_out, C_out)
    W_flat = W.reshape(K * C_in, C_out)
    return cols @ W_flat + b


def _conv1d_backward(x, W, dout):
    """Backward pass for 1D convolution. Returns dW, db, dx."""
    batch, T, C_in = x.shape
    K, _, C_out = W.shape
    T_out = T - K + 1
    W_flat = W.reshape(K * C_in, C_out)

    # im2col forward patches (same as forward)
    cols = np.zeros((batch, T_out, K * C_in), dtype=x.dtype)
    for t in range(T_out):
        cols[:, t, :] = x[:, t:t+K, :].reshape(batch, -1)

    # dW: (K*C_in, C_out)
    dW_flat = np.einsum('bti,bto->io', cols, dout)
    dW = dW_flat.reshape(K, C_in, C_out)
    db = dout.sum(axis=(0, 1))

    # dx: scatter gradients back through patches
    dcols = dout @ W_flat.T  # (batch, T_out, K*C_in)
    dx = np.zeros_like(x)
    for t in range(T_out):
        dx[:, t:t+K, :] += dcols[:, t, :].reshape(batch, K, C_in)

    return dW, db, dx


def _maxpool1d(x, pool_size=2):
    """Max pool over time dimension. x: (batch, time, channels). Returns (batch, time//pool, channels)."""
    batch, T, C = x.shape
    T_out = T // pool_size
    x_trunc = x[:, :T_out * pool_size, :].reshape(batch, T_out, pool_size, C)
    return x_trunc.max(axis=2)


def _maxpool1d_backward(x, out, dout, pool_size=2):
    """Backward for max pool."""
    batch, T, C = x.shape
    T_out = T // pool_size
    x_trunc = x[:, :T_out * pool_size, :].reshape(batch, T_out, pool_size, C)
    mask = (x_trunc == out[:, :, np.newaxis, :])
    dx_trunc = (mask * dout[:, :, np.newaxis, :])
    dx = np.zeros_like(x)
    dx[:, :T_out * pool_size, :] = dx_trunc.reshape(batch, T_out * pool_size, C)
    return dx


class TinyClassifier:
    """1D CNN that preserves temporal structure of MFCC frames.

    Architecture: Conv(k=5, 32) -> ReLU -> MaxPool(2) -> Conv(k=3, 64) -> ReLU -> MaxPool(2)
                  -> GlobalAvgPool -> FC(64) -> ReLU -> FC(1) -> Sigmoid

    Trained with Adam optimizer, pure numpy. Runs on Pi Zero 2.
    """

    def __init__(self, n_frames, n_mfcc=13):
        self.n_frames = n_frames
        self.n_mfcc = n_mfcc

        # Conv1: kernel=5, 13 input channels, 32 output channels
        self.W_c1 = np.random.randn(5, n_mfcc, 32).astype(np.float32) * np.sqrt(2.0 / (5 * n_mfcc))
        self.b_c1 = np.zeros(32, dtype=np.float32)

        # Conv2: kernel=3, 32 input channels, 64 output channels
        self.W_c2 = np.random.randn(3, 32, 64).astype(np.float32) * np.sqrt(2.0 / (3 * 32))
        self.b_c2 = np.zeros(64, dtype=np.float32)

        # FC1: 64 -> 64
        self.W_f1 = np.random.randn(64, 64).astype(np.float32) * np.sqrt(2.0 / 64)
        self.b_f1 = np.zeros(64, dtype=np.float32)

        # FC2: 64 -> 1
        self.W_f2 = np.random.randn(64, 1).astype(np.float32) * np.sqrt(2.0 / 64)
        self.b_f2 = np.zeros(1, dtype=np.float32)

    def forward(self, X):
        """Forward pass. X: (batch, n_frames, n_mfcc). Returns (batch, 1)."""
        # Conv1 -> ReLU -> MaxPool
        self._x_input = X
        self._z_c1 = _conv1d(X, self.W_c1, self.b_c1)
        self._a_c1 = _relu(self._z_c1)
        self._p1 = _maxpool1d(self._a_c1, 2)

        # Conv2 -> ReLU -> MaxPool
        self._z_c2 = _conv1d(self._p1, self.W_c2, self.b_c2)
        self._a_c2 = _relu(self._z_c2)
        self._p2 = _maxpool1d(self._a_c2, 2)

        # Global average pooling over time -> (batch, 64)
        self._gap = self._p2.mean(axis=1)

        # FC1 -> ReLU
        self._z_f1 = self._gap @ self.W_f1 + self.b_f1
        self._a_f1 = _relu(self._z_f1)

        # FC2 -> Sigmoid
        self._z_f2 = self._a_f1 @ self.W_f2 + self.b_f2
        return _sigmoid(self._z_f2)

    def predict(self, mfcc_2d):
        """Single sample prediction. mfcc_2d: (n_frames, n_mfcc). Returns float 0..1."""
        return float(self.forward(mfcc_2d[np.newaxis, :, :])[0, 0])

    def _backward(self, X, yb, pred):
        """Compute gradients for all parameters."""
        bs = X.shape[0]
        # Output gradient
        dz_f2 = (pred - yb) / bs  # (bs, 1)

        dW_f2 = self._a_f1.T @ dz_f2
        db_f2 = dz_f2.sum(axis=0)

        da_f1 = dz_f2 @ self.W_f2.T
        dz_f1 = da_f1 * (self._z_f1 > 0).astype(np.float32)
        dW_f1 = self._gap.T @ dz_f1
        db_f1 = dz_f1.sum(axis=0)

        # Global avg pool backward: distribute gradient equally across time
        d_gap = dz_f1 @ self.W_f1.T  # (bs, 64)
        T2 = self._p2.shape[1]
        d_p2 = np.repeat(d_gap[:, np.newaxis, :], T2, axis=1) / T2

        # MaxPool2 backward
        d_a_c2 = _maxpool1d_backward(self._a_c2, self._p2, d_p2, 2)
        d_z_c2 = d_a_c2 * (self._z_c2 > 0).astype(np.float32)
        dW_c2, db_c2, d_p1 = _conv1d_backward(self._p1, self.W_c2, d_z_c2)

        # MaxPool1 backward
        d_a_c1 = _maxpool1d_backward(self._a_c1, self._p1, d_p1, 2)
        d_z_c1 = d_a_c1 * (self._z_c1 > 0).astype(np.float32)
        dW_c1, db_c1, _ = _conv1d_backward(X, self.W_c1, d_z_c1)

        return [dW_c1, db_c1, dW_c2, db_c2, dW_f1, db_f1, dW_f2, db_f2]

    def train(self, X, y, epochs=200, lr=0.001, batch_size=32, verbose=True):
        """Train with Adam optimizer. X: (n_samples, n_frames, n_mfcc), y: (n_samples,)."""
        n = len(X)
        params = [self.W_c1, self.b_c1, self.W_c2, self.b_c2,
                  self.W_f1, self.b_f1, self.W_f2, self.b_f2]
        ms = [np.zeros_like(p) for p in params]
        vs = [np.zeros_like(p) for p in params]
        beta1, beta2, eps_adam = 0.9, 0.999, 1e-8
        t = 0

        for epoch in range(epochs):
            idx = np.random.permutation(n)
            X_shuf, y_shuf = X[idx], y[idx]
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, n, batch_size):
                end = min(start + batch_size, n)
                Xb = X_shuf[start:end]
                yb = y_shuf[start:end].reshape(-1, 1)

                pred = self.forward(Xb)
                loss = _binary_cross_entropy(pred, yb)
                epoch_loss += loss
                n_batches += 1

                grads = self._backward(Xb, yb, pred)

                t += 1
                for i, (p, g) in enumerate(zip(params, grads)):
                    ms[i] = beta1 * ms[i] + (1 - beta1) * g
                    vs[i] = beta2 * vs[i] + (1 - beta2) * (g ** 2)
                    m_hat = ms[i] / (1 - beta1 ** t)
                    v_hat = vs[i] / (1 - beta2 ** t)
                    p -= lr * m_hat / (np.sqrt(v_hat) + eps_adam)

            avg_loss = epoch_loss / max(n_batches, 1)
            if verbose and (epoch + 1) % 100 == 0:
                preds = self.forward(X)
                acc = np.mean((preds.flatten() > 0.5) == y)
                print(f"   Epoch {epoch+1}/{epochs}: loss={avg_loss:.4f} acc={acc:.1%}")

    def get_weights(self):
        return {
            'n_frames': self.n_frames, 'n_mfcc': self.n_mfcc,
            'W_c1': self.W_c1, 'b_c1': self.b_c1,
            'W_c2': self.W_c2, 'b_c2': self.b_c2,
            'W_f1': self.W_f1, 'b_f1': self.b_f1,
            'W_f2': self.W_f2, 'b_f2': self.b_f2,
        }

    @classmethod
    def from_weights(cls, w):
        obj = cls(w['n_frames'], w['n_mfcc'])
        obj.W_c1, obj.b_c1 = w['W_c1'], w['b_c1']
        obj.W_c2, obj.b_c2 = w['W_c2'], w['b_c2']
        obj.W_f1, obj.b_f1 = w['W_f1'], w['b_f1']
        obj.W_f2, obj.b_f2 = w['W_f2'], w['b_f2']
        return obj


# ---------------------------------------------------------------------------
# ONNX model wrapper — uses pre-trained universal model if available
# ---------------------------------------------------------------------------

class OnnxWakeWordModel:
    """Wraps an ONNX wake word model for inference via onnxruntime.
    Drop-in replacement for TinyClassifier.predict().
    """

    def __init__(self, onnx_path, meta_path=None):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(onnx_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

        # Load metadata if present
        self.meta = {}
        if meta_path and os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                self.meta = json.load(f)

    def predict(self, mfcc_2d):
        """Single sample prediction. mfcc_2d: (n_frames, n_mfcc). Returns float 0..1."""
        inp = mfcc_2d[np.newaxis, :, :].astype(np.float32)
        result = self.session.run([self.output_name], {self.input_name: inp})
        return float(result[0][0][0])


# ---------------------------------------------------------------------------
# Wake word system — CNN-based
# ---------------------------------------------------------------------------

_MODEL_TAG = "atomik"
TARGET_FRAMES = 62  # ~1 second at 16kHz with 512-FFT / 256-hop


class WakeWordSystem:
    # Set to True to force detection scores in console (overrides debug flag)
    DEBUG_DETECTION = False

    # Detection modes
    MODE_MODEL = "model"       # CNN/ONNX neural network (trained model)
    MODE_TEMPLATE = "template"  # Original cosine similarity (template matching)

    def __init__(self, wake_word="hey tars", sample_rate=16000, threshold=0.6, augment_data=True, debug=False, mode=None):
        self.wake_word = wake_word
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.augment_data = augment_data
        self.debug = debug or self.DEBUG_DETECTION
        self.mfcc_extractor = MFCCExtractor(sample_rate=sample_rate)
        self.vad = VoiceActivityDetector(sample_rate=sample_rate)
        self.buffer = deque(maxlen=sample_rate * 3)
        self.model = None  # OnnxWakeWordModel (model mode) or None (template mode)
        self._using_onnx = False
        self.last_detection_time = 0
        self.cooldown = 1.5
        self.last_check_time = 0
        self.check_interval = 0.1
        # Confirmation window: require 2 scores above threshold in 5 checks (0.5s)
        # to avoid single-frame false positives from transient sounds
        self._recent_scores = deque(maxlen=5)
        self._confirmation_count = 2
        self._last_debug_time = 0
        self._peak_score_since_debug = 0.0
        # Adaptive noise floor — tracks background noise level for SNR gating
        self._noise_floor = 0.005  # initial estimate
        self._noise_alpha = 0.02   # slow adaptation rate
        self._min_snr = 3.0        # minimum signal-to-noise ratio to consider
        # Template mode (original cosine similarity)
        self.templates = []
        # Mode: auto-detect if not specified
        # "model" = CNN/ONNX, "template" = cosine similarity
        self._mode = mode  # None = auto-detect during createModel()

    # --- Data collection helpers ---

    def _record_audio(self, prompt):
        """Record audio with VAD-based auto-stop. Returns float32 numpy array."""
        for i in range(3, 0, -1):
            print(f"   {i}...")
            time.sleep(1)

        print(f"\n   {prompt}")

        recording = []
        speech_started = False
        silence_count = 0
        max_silence_frames = 15

        def callback(audio_chunk, frames, time_info, status):
            nonlocal speech_started, silence_count

            if not speech_started:
                if self.vad.is_speech(audio_chunk):
                    speech_started = True
                    print("   Recording...", end="", flush=True)
                    recording.extend(audio_chunk)
            else:
                recording.extend(audio_chunk)
                if self.vad.is_speech(audio_chunk):
                    silence_count = 0
                    print("\u2588", end="", flush=True)
                else:
                    silence_count += 1
                    print("\u2591", end="", flush=True)

        with open_native_stream(callback=make_resampling_callback(callback),
                                blocksize=512):
            while not speech_started or silence_count < max_silence_frames:
                time.sleep(0.01)

        audio_array = np.array(recording, dtype=np.float32)
        audio_array = self.vad.trim_silence(audio_array)

        duration = len(audio_array) / self.sample_rate
        energy = np.sqrt(np.mean(audio_array ** 2))
        print(f"\n   Duration: {duration:.1f}s, Audio level: {energy:.4f}")

        if duration < 0.2 or energy < 0.003:
            return None
        return audio_array

    def _record_ambient(self, duration_sec=5):
        """Record ambient noise / background for negative samples."""
        print(f"\n   Recording {duration_sec}s of ambient noise...")
        recording = []
        start_time = [None]

        def callback(audio_chunk, frames, time_info, status):
            if start_time[0] is None:
                start_time[0] = time.time()
            recording.extend(audio_chunk)

        with open_native_stream(callback=make_resampling_callback(callback),
                                blocksize=512):
            while start_time[0] is None or time.time() - start_time[0] < duration_sec:
                time.sleep(0.1)

        print(f"   Captured {len(recording) / self.sample_rate:.1f}s of audio")
        return np.array(recording, dtype=np.float32)

    # --- Augmentation ---

    def time_stretch(self, audio, rate):
        idx = np.round(np.arange(0, len(audio), rate))
        idx = idx[idx < len(audio)].astype(int)
        return audio[idx]

    def pitch_shift(self, audio, semitones):
        factor = 2 ** (semitones / 12.0)
        idx = np.round(np.arange(0, len(audio), factor))
        idx = idx[idx < len(audio)].astype(int)
        return audio[idx]

    def add_noise(self, audio, noise_level=0.005):
        noise = np.random.normal(0, noise_level, len(audio))
        return audio + noise

    def augment_audio(self, audio):
        """Create augmented versions of an audio sample."""
        return [
            audio,
            self.time_stretch(audio, 0.9),
            self.time_stretch(audio, 1.1),
            self.pitch_shift(audio, -2),
            self.pitch_shift(audio, 2),
            audio * 0.8,
            audio * 1.2,
            self.add_noise(audio, 0.003),
            self.add_noise(audio, 0.006),
        ]

    def _audio_to_feature(self, audio):
        """Convert raw audio to a fixed-size 2D MFCC matrix for the CNN.
        Returns shape (TARGET_FRAMES, 13) preserving temporal structure.
        """
        mfcc = self.mfcc_extractor.extract_fixed(audio, target_frames=TARGET_FRAMES)
        if mfcc is None:
            return None
        return mfcc.astype(np.float32)

    def _random_slice(self, audio, duration_samples):
        """Extract a random slice of given length from audio."""
        if len(audio) <= duration_samples:
            return audio
        start = np.random.randint(0, len(audio) - duration_samples)
        return audio[start:start + duration_samples]

    def _generate_synthetic_negatives(self, n_clips=40):
        """Generate synthetic 1-second audio clips that mimic common false-positive sources.

        Creates a mix of: white/pink noise, speech-like babble (random formants),
        tonal sounds (music-like), clicks/pops, and low-frequency rumble.
        No external files needed.
        """
        sr = self.sample_rate
        n = sr  # 1 second
        clips = []

        for _ in range(n_clips):
            noise_type = np.random.choice([
                'white', 'pink', 'babble', 'tonal', 'rumble', 'clicks', 'mixed'
            ])

            if noise_type == 'white':
                # White noise at random volume
                clip = np.random.randn(n).astype(np.float32) * np.random.uniform(0.01, 0.1)

            elif noise_type == 'pink':
                # Pink noise (1/f) — sounds like fan/AC
                white = np.random.randn(n).astype(np.float32)
                fft = np.fft.rfft(white)
                freqs = np.fft.rfftfreq(n, d=1.0/sr)
                freqs[0] = 1.0  # avoid divide by zero
                fft /= np.sqrt(freqs)
                clip = np.fft.irfft(fft, n=n).astype(np.float32)
                clip *= np.random.uniform(0.01, 0.08) / (np.std(clip) + 1e-8)

            elif noise_type == 'babble':
                # Speech-like babble — random formant frequencies modulated over time
                clip = np.zeros(n, dtype=np.float32)
                n_voices = np.random.randint(2, 5)
                for _ in range(n_voices):
                    # Random fundamental + harmonics
                    f0 = np.random.uniform(80, 300)
                    t = np.arange(n) / sr
                    voice = np.zeros(n, dtype=np.float32)
                    for harmonic in range(1, np.random.randint(3, 8)):
                        freq = f0 * harmonic + np.random.uniform(-10, 10)
                        amp = 1.0 / (harmonic ** np.random.uniform(0.8, 1.5))
                        voice += amp * np.sin(2 * np.pi * freq * t).astype(np.float32)
                    # Amplitude envelope (speech-like bursts)
                    envelope = np.random.rand(20).astype(np.float32)
                    envelope = np.interp(np.linspace(0, len(envelope)-1, n), np.arange(len(envelope)), envelope)
                    clip += voice * envelope
                clip *= np.random.uniform(0.01, 0.06) / (np.std(clip) + 1e-8)

            elif noise_type == 'tonal':
                # Music-like tones — random notes
                t = np.arange(n) / sr
                clip = np.zeros(n, dtype=np.float32)
                n_notes = np.random.randint(1, 4)
                for _ in range(n_notes):
                    freq = np.random.choice([261, 294, 330, 349, 392, 440, 494, 523, 587, 659])
                    freq *= np.random.choice([0.5, 1.0, 2.0])  # octave variation
                    clip += np.sin(2 * np.pi * freq * t).astype(np.float32) * np.random.uniform(0.3, 1.0)
                clip *= np.random.uniform(0.01, 0.05) / (np.std(clip) + 1e-8)

            elif noise_type == 'rumble':
                # Low frequency rumble (truck, appliance)
                t = np.arange(n) / sr
                freq = np.random.uniform(20, 120)
                clip = np.sin(2 * np.pi * freq * t).astype(np.float32)
                clip += np.random.randn(n).astype(np.float32) * 0.02
                clip *= np.random.uniform(0.02, 0.08)

            elif noise_type == 'clicks':
                # Random clicks and pops
                clip = np.zeros(n, dtype=np.float32)
                n_clicks = np.random.randint(3, 15)
                for _ in range(n_clicks):
                    pos = np.random.randint(0, n - 100)
                    width = np.random.randint(5, 50)
                    clip[pos:pos+width] = np.random.uniform(-0.2, 0.2)
                clip += np.random.randn(n).astype(np.float32) * 0.005

            else:  # mixed
                # Combination of noise types
                white = np.random.randn(n).astype(np.float32) * 0.03
                t = np.arange(n) / sr
                tone = np.sin(2 * np.pi * np.random.uniform(100, 1000) * t).astype(np.float32) * 0.02
                babble = np.zeros(n, dtype=np.float32)
                f0 = np.random.uniform(100, 250)
                for h in range(1, 5):
                    babble += np.sin(2 * np.pi * f0 * h * t).astype(np.float32) / h
                envelope = np.random.rand(10).astype(np.float32)
                envelope = np.interp(np.linspace(0, len(envelope)-1, n), np.arange(len(envelope)), envelope)
                babble *= envelope * 0.02
                clip = white + tone + babble

            clips.append(clip[:n])

        return clips

    # --- Training ---

    def has_model(self):
        """Check if any wake word model (ONNX or templates) is available."""
        if os.path.exists(self._onnx_path()):
            return True
        if os.path.exists(self._templates_path()):
            return True
        return False

    def createModel(self, num_templates=5):
        if self._load_model():
            return True

        # No model found — check mode
        if self._mode == self.MODE_TEMPLATE:
            # Template mode — record wake word samples
            return self._create_template_model(num_templates)
        else:
            # Model mode — ONNX model must be trained externally
            print("=" * 60)
            print(f"  ATOMIK WAKE WORD — MODEL NOT FOUND")
            print("=" * 60)
            print()
            print(f"  No ONNX model found for '{self.wake_word}'.")
            print()
            print("  To create one:")
            print("    1. Run tools/wakeword-trainer/train.bat on a PC with GPU")
            print(f"    2. Copy hey_tars.onnx to src/tts/")
            print()
            print("  Or switch to template mode in config.ini:")
            print("    atomik_mode = template")
            print()
            print("  Falling back to template mode for now...")
            print()
            self._mode = self.MODE_TEMPLATE
            return self._create_template_model(num_templates)

    # --- Detection ---

    def listenForWakeWord(self):
        detected_flag = False

        def audio_callback(audio_np, frames, time_info, status):
            nonlocal detected_flag
            self.buffer.extend(audio_np)

            detected, confidence = self.detect()
            if detected:
                detected_flag = True

        with open_native_stream(callback=make_resampling_callback(audio_callback),
                                blocksize=512):
            while not detected_flag:
                time.sleep(0.05)
        return True

    def detect(self):
        # Template mode uses simpler detection path
        if self._mode == self.MODE_TEMPLATE:
            return self._detect_template()

        if self.model is None or len(self.buffer) < int(self.sample_rate * 1.0):
            return False, 0.0
        if time.time() - self.last_detection_time < self.cooldown:
            return False, 0.0
        if time.time() - self.last_check_time < self.check_interval:
            return False, 0.0
        self.last_check_time = time.time()

        audio_window = np.array(list(self.buffer)[-int(self.sample_rate):], dtype=np.float32)

        # --- Gate 1: Energy gate ---
        rms = np.sqrt(np.mean(audio_window ** 2))
        if rms < self.vad.energy_threshold:
            # Update noise floor from quiet frames
            self._noise_floor = (1 - self._noise_alpha) * self._noise_floor + self._noise_alpha * rms
            return False, 0.0

        # --- Gate 2: Adaptive SNR gate ---
        snr = rms / (self._noise_floor + 1e-8)
        if snr < self._min_snr:
            return False, 0.0

        # --- Gate 3: Crest factor — reject transient bangs/clicks ---
        # Bangs have very high peak relative to RMS. Speech is more uniform.
        peak = np.max(np.abs(audio_window))
        crest = peak / (rms + 1e-8)
        if crest > 15:  # bangs/clicks typically > 15, speech < 10
            return False, 0.0

        # --- Gate 4: Spectral speech gate ---
        # Speech concentrates energy in 300-3000Hz. Noise/bangs are broadband.
        fft_mag = np.abs(np.fft.rfft(audio_window))
        freqs = np.fft.rfftfreq(len(audio_window), 1.0 / self.sample_rate)
        speech_band = np.sum(fft_mag[(freqs >= 300) & (freqs <= 3000)])
        total_band = np.sum(fft_mag) + 1e-8
        speech_ratio = speech_band / total_band
        if speech_ratio < 0.30:
            return False, 0.0

        # --- Gate 5: Sub-300Hz ratio — reject low rumbles/thuds ---
        low_band = np.sum(fft_mag[freqs < 300])
        low_ratio = low_band / total_band
        if low_ratio > 0.60:  # rumbles/thuds have >60% energy below 300Hz
            return False, 0.0

        # Extract features
        feat = self._audio_to_feature(audio_window)
        if feat is None:
            return False, 0.0

        # Neural network inference - single forward pass
        score = self.model.predict(feat)

        # Speed-variation retry: if score is close but below threshold,
        # try time-stretched versions to catch slightly faster/slower speech.
        # Only triggers on "almost" matches — won't boost random noise.
        if self.threshold * 0.6 < score < self.threshold:
            for rate in [0.9, 1.1]:
                stretched = self.time_stretch(audio_window, rate)
                if len(stretched) < self.sample_rate:
                    stretched = np.pad(stretched, (0, self.sample_rate - len(stretched)))
                retry_feat = self._audio_to_feature(stretched[:self.sample_rate])
                if retry_feat is not None:
                    retry_score = self.model.predict(retry_feat)
                    if retry_score > score:
                        score = retry_score
                        if score >= self.threshold:
                            break

        # Confirmation window
        self._recent_scores.append(score)
        above_count = sum(1 for s in self._recent_scores if s >= self.threshold)

        # Debug output — single-line update (overwrites previous)
        if self.debug and score > 0.1:
            filled = int(score * 30)
            bar = "\u2588" * filled + "\u2591" * (30 - filled)
            print(f"\r  [atomik] {bar} {score:.3f}/{self.threshold:.3f} [{above_count}/{self._confirmation_count}]   ", end="", flush=True)

        if above_count >= self._confirmation_count:
            if not self._is_speech_like(audio_window):
                if self.debug:
                    print(f"\r  [atomik] rejected: not speech-like                                    ", flush=True)
                self._recent_scores.clear()
                return False, score

            self.last_detection_time = time.time()
            self._recent_scores.clear()
            if self.debug:
                print(f"\r  [atomik] >>> WAKE WORD DETECTED ({score:.3f}) <<<                        ", flush=True)
            return True, score

        return False, score

    def _is_speech_like(self, audio):
        """Check if audio has speech-like characteristics vs pure noise/transients.
        Uses zero-crossing rate, energy dynamics, and syllable counting."""
        try:
            # 1. Zero-crossing rate — speech has moderate ZCR
            signs = np.sign(audio)
            signs[signs == 0] = 1
            zcr = np.sum(np.abs(np.diff(signs))) / (2.0 * len(audio))
            if zcr > 0.20 or zcr < 0.002:
                return False

            # 2. Energy envelope analysis
            chunk_size = self.sample_rate // 20  # 50ms chunks
            n_chunks = max(1, len(audio) // chunk_size)
            energies = np.array([
                np.sqrt(np.mean(audio[i*chunk_size:(i+1)*chunk_size] ** 2))
                for i in range(n_chunks)
            ])

            if len(energies) < 3:
                return True

            energy_cv = np.std(energies) / (np.mean(energies) + 1e-8)
            if energy_cv < 0.15:
                return False

            # 3. Syllable peak counting
            smooth = np.convolve(energies, np.ones(3)/3, mode='same')
            threshold = np.mean(smooth) * 0.6
            above = smooth > threshold
            transitions = np.diff(above.astype(int))
            n_peaks = np.sum(transitions == 1)
            if n_peaks < 1 or n_peaks > 5:
                return False

            # 4. Speech duration
            speech_chunks = np.sum(energies > threshold)
            speech_duration = speech_chunks * chunk_size / self.sample_rate
            if speech_duration < 0.2 or speech_duration > 2.5:
                return False

            return True
        except Exception:
            return True

    # --- Template mode (original cosine similarity) ---

    def cosine_similarity(self, mfcc1, mfcc2):
        v1, v2 = mfcc1.flatten(), mfcc2.flatten()
        min_len = min(len(v1), len(v2))
        v1, v2 = v1[:min_len], v2[:min_len]
        dot = np.dot(v1, v2)
        norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
        return 0.0 if norm1 == 0 or norm2 == 0 else dot / (norm1 * norm2)

    def _detect_template(self):
        """Original template-based detection using cosine similarity."""
        if not self.templates or len(self.buffer) < int(self.sample_rate * 1.0):
            return False, 0.0
        if time.time() - self.last_detection_time < self.cooldown:
            return False, 0.0
        if time.time() - self.last_check_time < self.check_interval:
            return False, 0.0
        self.last_check_time = time.time()

        audio_window = np.array(list(self.buffer)[-int(self.sample_rate):], dtype=np.float32)
        if not self.vad.is_speech(audio_window[:1024]):
            return False, 0.0

        current_mfcc = self.mfcc_extractor.extract_mfcc(audio_window)
        if current_mfcc is None:
            return False, 0.0

        max_sim = max(self.cosine_similarity(current_mfcc, t) for t in self.templates)

        if self.debug and max_sim > 0.1:
            filled = int(max_sim * 30)
            bar = "\u2588" * filled + "\u2591" * (30 - filled)
            print(f"\r  [atomik:tmpl] {bar} {max_sim:.3f}/{self.threshold:.3f}   ", end="", flush=True)

        if max_sim >= self.threshold:
            self.last_detection_time = time.time()
            if self.debug:
                print(f"\r  [atomik:tmpl] >>> WAKE WORD DETECTED ({max_sim:.3f}) <<<                  ", flush=True)
            return True, max_sim
        return False, max_sim

    def _record_template(self):
        """Record a single wake word template for template mode."""
        audio = self._record_audio(f"SAY '{self.wake_word.upper()}' now!")
        if audio is None or len(audio) < self.sample_rate * 0.3:
            return False

        audio = self.vad.trim_silence(audio)
        mfcc = self.mfcc_extractor.extract_mfcc(audio)
        if mfcc is None:
            return False

        self.templates.append(mfcc)
        templates_added = 1

        if self.augment_data:
            for aug in self.augment_audio(audio)[1:]:
                aug_mfcc = self.mfcc_extractor.extract_mfcc(aug)
                if aug_mfcc is not None:
                    self.templates.append(aug_mfcc)
                    templates_added += 1
            print(f"   Created {templates_added} templates (1 original + {templates_added-1} augmented)")

        return True

    def _create_template_model(self, num_templates=5):
        """Original template recording flow for template mode."""
        print("=" * 60)
        print(f"  ATOMIK WAKE WORD — TEMPLATE MODE")
        print(f"  Wake word: '{self.wake_word}'")
        print("=" * 60)
        print()
        print("  Record your wake word 5 times.")
        print("  Speak naturally at normal volume.")
        print("  To retrain, delete hey_tars_templates.pkl in src/tts/")
        print()
        print("  Press ENTER when ready...")
        input()

        for i in range(num_templates):
            print(f"\n  Recording {i+1}/{num_templates}")
            if not self._record_template():
                print("   Retrying...")
                self._record_template()
            time.sleep(1)

        self._save_templates()
        print(f"\n  Training complete. Created {len(self.templates)} templates.")
        return True

    def _templates_path(self):
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts")
        return os.path.join(data_dir, f"{self.wake_word.replace(' ', '_')}_templates.pkl")

    def _save_templates(self):
        filepath = self._templates_path()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            pickle.dump(self.templates, f)

    def _load_templates(self):
        filepath = self._templates_path()
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                self.templates = pickle.load(f)
            print(f"   Loaded {len(self.templates)} templates (template mode, threshold={self.threshold:.2f})")
            return True
        return False

    # --- Model I/O ---

    def _onnx_path(self):
        """Path to the universal ONNX wake word model."""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tts")
        return os.path.join(data_dir, f"{self.wake_word.replace(' ', '_')}.onnx")

    def _load_model(self, filename=None):
        # --- If mode is explicitly set to template, only load templates ---
        if self._mode == self.MODE_TEMPLATE:
            return self._load_templates()

        # --- Try ONNX model (preferred) ---
        onnx_path = self._onnx_path()
        if os.path.exists(onnx_path):
            try:
                meta_path = onnx_path.replace(".onnx", "_meta.json")
                self.model = OnnxWakeWordModel(onnx_path, meta_path)
                self._using_onnx = True
                self._mode = self.MODE_MODEL
                # Detect if model expects delta features (39 channels) or static only (13)
                input_shape = self.model.session.get_inputs()[0].shape
                n_features = input_shape[-1] if len(input_shape) >= 3 else 13
                self.mfcc_extractor._use_deltas = (n_features > 13)
                size_kb = os.path.getsize(onnx_path) / 1024
                meta_info = ""
                if self.model.meta:
                    f1 = self.model.meta.get("f1_score", 0)
                    meta_info = f", f1={f1:.1%}"
                    # ONNX model was trained on clean synthetic TTS audio.
                    # Real mic audio scores higher, so bump the threshold.
                    self.threshold = min(self.threshold + 0.25, 0.95)
                print(f"INFO: Loaded universal ONNX model ({size_kb:.0f}KB{meta_info}, threshold={self.threshold:.2f})")
                return True
            except Exception as e:
                print(f"   Failed to load ONNX model: {e}")

        # --- Fallback to template mode (original cosine similarity) ---
        if self._load_templates():
            self._mode = self.MODE_TEMPLATE
            return True

        return False

    def delete_templates(self, filename=None):
        """Delete the template file."""
        filepath = self._templates_path()
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
