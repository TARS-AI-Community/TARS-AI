"""
module_mic.py — Shared microphone utilities.

Detects the default input device's native sample rate once, provides
resampling helpers, and a shared audio hub so every consumer can read
from the same physical mic without ALSA exclusion conflicts.

USB audio devices typically don't support ALSA dsnoop (shared capture),
so only one PortAudio stream can access the device at a time. The
_AudioHub singleton manages that single stream and dispatches audio to
all registered consumers (callback-based and read-based).
"""

import os
import time
import threading
import collections
import numpy as np
from math import gcd

# Prevent pygame/SDL from grabbing ALSA devices exclusively.
# TARS uses sounddevice (PortAudio) for all mic input — SDL audio is unused.
# This must be set before pygame.init() or sounddevice import triggers PA init.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sounddevice as sd

try:
    import soxr as _soxr
    _HAS_SOXR = True
except ImportError:
    from scipy.signal import resample_poly as _resample_poly
    _HAS_SOXR = False

MODEL_RATE = 16000

# ── Singleton device info ──────────────────────────────────────────

_device_info = None  # cached (device_idx, native_rate)
_device_lock = threading.Lock()


def _is_real_hw_device(info):
    """Return True if the device looks like real hardware, not an ALSA plugin.

    ALSA plugin devices (default, dmix, etc.) report 128 channels which is
    a dead giveaway. Real USB mics report 1-2 channels.
    """
    return 1 <= info.get("max_input_channels", 0) <= 32


def _find_input_device():
    """Try to find a working input device. Returns (idx, rate) or raises."""
    # 1. Try the system default — but only if it looks like real hardware.
    #    ALSA plugin devices (e.g. "default") report 128 channels and may
    #    hide the actual hardware rate, causing wrong device selection.
    idx = sd.default.device[0]
    if idx is not None and idx >= 0:
        info = sd.query_devices(idx, kind="input")
        if _is_real_hw_device(info):
            return idx, int(info.get("default_samplerate", MODEL_RATE))

    # 2. Default failed or is a plugin — scan for real hardware devices
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if _is_real_hw_device(dev):
            rate = int(dev.get("default_samplerate", MODEL_RATE))
            return i, rate

    # 3. Fall back to any device with input channels (including plugins)
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) >= 1:
            rate = int(dev.get("default_samplerate", MODEL_RATE))
            return i, rate

    # 4. Last resort: ask PortAudio C-level for the default input
    try:
        from sounddevice import _lib
        pa_idx = _lib.Pa_GetDefaultInputDevice()
        if pa_idx >= 0:
            info = sd.query_devices(pa_idx, kind="input")
            return pa_idx, int(info.get("default_samplerate", MODEL_RATE))
    except Exception:
        pass

    raise RuntimeError("No input audio device found")


def get_device_info(retries=4, backoff=1.0):
    """Return (device_idx, native_sample_rate), cached after first call.

    Retries with backoff to handle USB audio devices that aren't ready at boot.
    """
    global _device_info
    if _device_info is not None:
        return _device_info

    with _device_lock:
        # Double-check under lock
        if _device_info is not None:
            return _device_info

        for attempt in range(retries):
            try:
                if attempt > 0:
                    sd._terminate()
                    sd._initialize()
                    time.sleep(backoff * attempt)

                idx, rate = _find_input_device()
                _device_info = (idx, rate)
                return _device_info
            except Exception as e:
                if attempt < retries - 1:
                    continue
                print(f"WARNING: Could not detect mic after {retries} attempts ({e}), using defaults")
                _device_info = (None, MODEL_RATE)
    return _device_info


def get_native_rate():
    """Return the default input device's native sample rate."""
    return get_device_info()[1]


def get_device_idx():
    """Return the default input device index (or None)."""
    return get_device_info()[0]


# ── Resampling helpers ─────────────────────────────────────────────

def resample(data, orig_sr, target_sr):
    """Resample audio from orig_sr to target_sr. No-op if rates match.

    Preserves dtype: int16 in -> int16 out, float in -> float32 out.
    """
    if orig_sr == target_sr:
        return data
    was_int = data.dtype == np.int16
    f = data.astype(np.float32) if was_int else np.asarray(data, dtype=np.float32)
    if _HAS_SOXR:
        out = _soxr.resample(f, orig_sr, target_sr)
    else:
        g = gcd(target_sr, orig_sr)
        out = _resample_poly(f, target_sr // g, orig_sr // g, axis=0)
    if was_int:
        return np.clip(out, -32768, 32767).astype(np.int16)
    return out.astype(np.float32)


def dev_frames(model_frames, native_rate=None):
    """Convert frame count from MODEL_RATE domain to native device domain."""
    if native_rate is None:
        native_rate = get_native_rate()
    if native_rate == MODEL_RATE:
        return model_frames
    return int(model_frames * native_rate / MODEL_RATE)


# ── Shared Audio Hub ───────────────────────────────────────────────
#
# One PortAudio stream, many consumers. Solves USB mic exclusion.
#

class _AudioHub:
    """Singleton that manages a single shared PortAudio input stream.

    Callback consumers register a function and receive raw audio at native rate.
    Read consumers get a thread-safe buffer they can pull chunks from.
    The stream starts when the first consumer arrives and stops 2s after
    the last consumer leaves (grace period avoids churn on USB devices).

    Thread safety: the PortAudio callback runs in a real-time thread and must
    not acquire locks or allocate memory. Consumer snapshots are atomically
    swapped (single pointer assignment under CPython's GIL) so the callback
    reads them lock-free.
    """

    _GRACE_PERIOD = 2.0  # seconds to keep stream alive after last consumer

    def __init__(self):
        self._lock = threading.Lock()
        self._stream = None
        self._native_rate = None
        self._grace_timer = None

        # Mutable dicts — only mutated under self._lock
        self._callbacks = {}   # {id: callback_fn}
        self._readers = {}     # {id: (deque, Event, dtype)}

        # Atomic snapshots — read lock-free by the audio callback.
        # Replaced (single pointer swap) under self._lock after any mutation.
        self._cb_snapshot = ()           # tuple of callback_fn
        self._rd_snapshot = ()           # tuple of (buf, evt)

        self._next_id = 0

    def _rebuild_snapshots(self):
        """Rebuild the lock-free snapshots. Must be called under self._lock."""
        self._cb_snapshot = tuple(self._callbacks.values())
        self._rd_snapshot = tuple(
            (buf, evt) for buf, evt, _dtype in self._readers.values()
        )

    def _on_audio(self, indata, frames, time_info, status):
        """Master callback — runs in PortAudio's real-time thread.

        No locks, no allocations beyond indata.copy(). Reads atomic snapshots.
        """
        # Single memcpy — required because PA reuses the indata buffer
        chunk = indata.copy()

        # Dispatch to callback consumers
        for cb in self._cb_snapshot:
            try:
                cb(chunk, frames, time_info, status)
            except Exception:
                pass

        # Buffer for read consumers (float32 only — int16 conversion in read())
        for buf, evt in self._rd_snapshot:
            buf.append(chunk)
            evt.set()

    def _ensure_stream(self):
        """Start the shared stream if not already running. Called under lock."""
        # Cancel any pending grace-period shutdown
        if self._grace_timer is not None:
            self._grace_timer.cancel()
            self._grace_timer = None

        if self._stream is not None:
            return
        idx, rate = get_device_info()
        self._native_rate = rate
        kwargs = dict(samplerate=rate, channels=1, callback=self._on_audio)
        if idx is not None and idx >= 0:
            kwargs["device"] = idx
        self._stream = sd.InputStream(**kwargs)
        self._stream.start()

    def _maybe_stop(self):
        """Schedule stream shutdown if no consumers remain. Called under lock."""
        if self._callbacks or self._readers:
            return
        # Delay shutdown to avoid USB device open/close churn
        if self._grace_timer is not None:
            self._grace_timer.cancel()
        self._grace_timer = threading.Timer(self._GRACE_PERIOD, self._shutdown)
        self._grace_timer.daemon = True
        self._grace_timer.start()

    def _shutdown(self):
        """Actually stop the stream (runs from grace timer thread)."""
        with self._lock:
            # Re-check: a new consumer may have arrived during grace period
            if self._callbacks or self._readers:
                return
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._grace_timer = None

    @property
    def native_rate(self):
        if self._native_rate is None:
            self._native_rate = get_native_rate()
        return self._native_rate

    # -- Callback consumer API --

    def register_callback(self, callback):
        """Register a callback consumer. Returns an ID for unregistering."""
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            self._callbacks[rid] = callback
            self._rebuild_snapshots()
            try:
                self._ensure_stream()
            except Exception:
                self._callbacks.pop(rid, None)
                self._rebuild_snapshots()
                raise
            return rid

    def unregister_callback(self, rid):
        """Remove a callback consumer by ID."""
        with self._lock:
            self._callbacks.pop(rid, None)
            self._rebuild_snapshots()
            self._maybe_stop()

    # -- Read consumer API --

    def register_reader(self, dtype="float32"):
        """Register a read-based consumer. Returns an ID."""
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            self._readers[rid] = (collections.deque(maxlen=500), threading.Event(), dtype)
            self._rebuild_snapshots()
            try:
                self._ensure_stream()
            except Exception:
                self._readers.pop(rid, None)
                self._rebuild_snapshots()
                raise
            return rid

    def unregister_reader(self, rid):
        """Remove a read-based consumer by ID."""
        with self._lock:
            self._readers.pop(rid, None)
            self._rebuild_snapshots()
            self._maybe_stop()

    def read(self, rid, n_native_frames):
        """Read n_native_frames of audio for a reader. Blocks until available.

        Returns (data, overflow) where data has shape (-1, 1).
        Dtype conversion (float32 -> int16) happens here, not in the audio thread.
        """
        entry = self._readers.get(rid)
        if entry is None:
            raise RuntimeError("Reader not registered — call start() or use as context manager")
        buf, evt, dtype = entry

        collected = []
        remaining = n_native_frames

        while remaining > 0:
            # Drain available chunks
            while buf and remaining > 0:
                chunk = buf.popleft()
                flat = chunk.ravel()
                if len(flat) <= remaining:
                    collected.append(flat)
                    remaining -= len(flat)
                else:
                    # Take what we need, push rest back
                    collected.append(flat[:remaining])
                    leftover = flat[remaining:]
                    buf.appendleft(leftover.reshape(-1, 1))
                    remaining = 0

            if remaining > 0:
                # Clear BEFORE checking to avoid lost-wakeup race:
                # if callback fires between empty-check and clear(),
                # the set() would be lost.
                evt.clear()
                if buf:
                    continue  # data arrived between drain loop and clear
                if not evt.wait(timeout=5.0):
                    # Timeout — return what we have padded with silence
                    target_dtype = np.int16 if dtype == "int16" else np.float32
                    if collected:
                        audio = np.concatenate(collected)
                    else:
                        audio = np.zeros(n_native_frames, dtype=target_dtype)
                    if len(audio) < n_native_frames:
                        pad = np.zeros(n_native_frames - len(audio), dtype=audio.dtype)
                        audio = np.concatenate([audio, pad])
                    audio = audio[:n_native_frames]
                    if dtype == "int16":
                        audio = np.clip(audio * 32768, -32768, 32767).astype(np.int16)
                    return audio.reshape(-1, 1), True

        audio = np.concatenate(collected)[:n_native_frames]

        # Convert to requested dtype (all buffered data is float32)
        if dtype == "int16":
            audio = np.clip(audio * 32768, -32768, 32767).astype(np.int16)

        return audio.reshape(-1, 1), False

    def flush_reader(self, rid, n=4, model_frames=2000):
        """Discard buffered audio for a reader (e.g. after TTS playback)."""
        entry = self._readers.get(rid)
        if entry is None:
            return
        buf, evt, _dtype = entry
        buf.clear()
        # Also consume ~0.5s of fresh audio to skip stale OS buffer
        total = dev_frames(model_frames, self.native_rate) * n
        consumed = 0
        deadline = time.monotonic() + 1.0
        while consumed < total and time.monotonic() < deadline:
            evt.clear()
            if buf:
                chunk = buf.popleft()
                consumed += chunk.size
            else:
                evt.wait(timeout=0.1)


# Global singleton
_hub = _AudioHub()


# ── Public stream helpers ──────────────────────────────────────────

def open_native_stream(**kwargs):
    """Open an audio stream at the device's native rate.

    If a callback is provided, registers it with the shared audio hub.
    Returns a _SharedCallbackStream (context-manager compatible).

    If no callback, returns a _SharedReadStream for read-based access.

    Note: blocksize is not honored by the shared hub — the PortAudio stream
    uses device defaults. Callback consumers receive whatever chunk size the
    device delivers (typically 256-1024 frames). Consumers must handle
    variable-size chunks.
    """
    callback = kwargs.pop("callback", None)
    # blocksize and other kwargs are consumed but not used by the shared hub
    kwargs.pop("blocksize", None)
    if callback:
        return _SharedCallbackStream(callback)
    return _SharedReadStream()


class _SharedCallbackStream:
    """Wrapper returned by open_native_stream(callback=...).

    Compatible with sd.InputStream context-manager protocol.
    """

    def __init__(self, callback):
        self._callback = callback
        self._rid = None

    def start(self):
        if self._rid is None:
            self._rid = _hub.register_callback(self._callback)

    def stop(self):
        pass  # stream stays alive for other consumers

    def close(self):
        if self._rid is not None:
            _hub.unregister_callback(self._rid)
            self._rid = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _SharedReadStream:
    """Wrapper returned by open_native_stream() without callback."""

    def __init__(self, dtype="float32"):
        self._dtype = dtype
        self._rid = None

    def start(self):
        if self._rid is None:
            self._rid = _hub.register_reader(self._dtype)

    def stop(self):
        pass

    def close(self):
        if self._rid is not None:
            _hub.unregister_reader(self._rid)
            self._rid = None

    def read(self, n_frames):
        if self._rid is None:
            raise RuntimeError("Stream not started — call start() or use as context manager")
        return _hub.read(self._rid, n_frames)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def flush_stream(stream, n=4, model_frames=2000):
    """Discard stale audio from stream buffer (e.g. after TTS playback)."""
    # For shared read streams, delegate to the hub
    if isinstance(stream, _SharedReadStream) and stream._rid is not None:
        _hub.flush_reader(stream._rid, n, model_frames)
        return
    # Legacy: raw sd.InputStream
    nr = get_native_rate()
    for _ in range(n):
        stream.read(dev_frames(model_frames, nr))


class ResamplingInputStream:
    """Read-based stream that transparently resamples to MODEL_RATE.

    Uses the shared audio hub — safe to use alongside callback consumers
    like the spectrum visualizer on the same USB mic.

    Usage::

        with ResamplingInputStream(dtype="int16") as mic:
            data, overflow = mic.read(4000)   # 4000 frames @ 16 kHz
            mic.flush()                        # discard stale audio
    """

    def __init__(self, **kwargs):
        self._dtype = kwargs.get("dtype", "float32")
        self._rid = None
        self._native_rate = get_native_rate()

    def __enter__(self):
        # Always buffer float32 in the hub; convert to requested dtype
        # AFTER resampling to avoid quantization noise before resample.
        self._rid = _hub.register_reader("float32")
        return self

    def __exit__(self, *exc):
        if self._rid is not None:
            _hub.unregister_reader(self._rid)
            self._rid = None
        return False

    def read(self, model_frames):
        """Read model_frames worth of audio, return resampled to MODEL_RATE."""
        n = dev_frames(model_frames, self._native_rate)
        raw, overflow = _hub.read(self._rid, n)
        data = resample(raw.ravel(), self._native_rate, MODEL_RATE)
        if self._dtype == "int16":
            data = np.clip(data * 32768, -32768, 32767).astype(np.int16)
        return data.reshape(-1, 1), overflow

    def read_exact(self, model_frames):
        """Like read() but guarantees exactly model_frames output samples."""
        data, overflow = self.read(model_frames)
        flat = data.ravel()
        if len(flat) > model_frames:
            flat = flat[:model_frames]
        elif len(flat) < model_frames:
            flat = np.pad(flat, (0, model_frames - len(flat)))
        return flat.reshape(-1, 1), overflow

    def flush(self, n=4, model_frames=2000):
        """Discard stale audio from the buffer."""
        if self._rid is not None:
            _hub.flush_reader(self._rid, n, model_frames)


def make_resampling_callback(user_callback):
    """Wrap an audio callback so it receives 16 kHz float32 mono audio.

    The resampling runs in the consumer's callback context (dispatched from
    the hub's audio thread). For heavy resampling on constrained hardware,
    consider buffering and resampling on a worker thread instead.

    ``user_callback(resampled_data, frames, time_info, status)`` where
    ``resampled_data`` is a float32 ndarray of shape ``(N,)`` at MODEL_RATE.
    """
    native_rate = get_native_rate()

    def _cb(indata, frames, time_info, status):
        audio = np.asarray(indata[:, 0], dtype=np.float32)
        if native_rate != MODEL_RATE:
            audio = resample(audio, native_rate, MODEL_RATE)
        user_callback(audio, len(audio), time_info, status)

    return _cb
