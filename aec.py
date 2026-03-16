#!/usr/bin/env python3
"""
TARS-AI: Automatic AEC (Echo Cancellation) Setup & Tuning

On first boot (or when AEC is not configured), this script:
  1. Checks if AEC echo-cancel.conf exists and PipeWire has the echo_cancel_source
  2. If not configured, installs dependencies and tests WebRTC AEC parameter combos
  3. Picks the best config (lowest echo bleed RMS) and writes it permanently

Matches the real TARS-AI audio pipeline:
  - All audio at 16kHz (STT records 16k, TTS plays 16k)
  - TTS gain chain: normalize to 1.0, multiply by 1.5, clip
  - App applies mic_amp_gain in software for RMS detection

Usage:
  python3 aec.py          # Auto-detect and configure if needed
  python3 aec.py --force  # Force re-tuning even if already configured
"""

import configparser
import glob as glob_mod
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# Add the project venv's site-packages so we can import piper, soundfile, numpy
# (same packages the real app uses).  This is needed because App-Start.py calls
# check_aec_setup() from the system Python, outside the venv.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_venv_sp = glob_mod.glob(os.path.join(SCRIPT_DIR, "src", ".venv", "lib", "python*", "site-packages"))
for sp in _venv_sp:
    if sp not in sys.path:
        sys.path.insert(0, sp)

logging.basicConfig(
    level=logging.INFO,
    format="[AEC] %(message)s",
)
log = logging.getLogger("aec")

AEC_CONF = "/etc/pipewire/pipewire.conf.d/echo-cancel.conf"
AEC_DISABLED_MARKER = os.path.join(SCRIPT_DIR, ".aec_disabled")
TTS_GAIN = 1.5
MARKER_COMMENT = "# TARS-AI AEC Config (auto-tuned)"

# ── ANSI color codes (matching App-Start.py cyan/orange theme) ─────
_USE_COLOR = sys.stdout.isatty()

def _c(code, text):
    """Wrap text in ANSI color if stdout is a terminal."""
    if _USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text

def _cyan(text):    return _c("38;2;0;200;255", text)
def _orange(text):  return _c("38;2;255;150;0", text)
def _dim(text):     return _c("2", text)
def _bold(text):    return _c("1", text)
def _green(text):   return _c("38;2;0;255;100", text)
def _red(text):     return _c("38;2;255;60;60", text)
def _white(text):   return _c("97", text)


VALID_PCM_RATES = {8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000, 192000}
APP_PLAYBACK_RATE = 16000  # what sd.play() sends — the rate PipeWire sees from the app

# Lazy-detected: not available until detect_graph_rate() is called (after PipeWire starts)
_graph_rate = None


def _validate_rate(rate):
    """Check that a detected rate is a known valid PCM sample rate."""
    if rate in VALID_PCM_RATES:
        return rate
    # Accept rates close to valid ones (within 1%) for quirky hardware
    for valid in sorted(VALID_PCM_RATES):
        if abs(rate - valid) / valid < 0.01:
            return valid
    return None


def detect_graph_rate():
    """Detect PipeWire's graph sample rate.  Call AFTER PipeWire is running.

    The AEC module's audio.rate should match PipeWire's default.clock.rate
    so it sits in the graph with zero internal resampling.  PipeWire handles
    all resampling between hardware devices and graph nodes.

    Returns a validated rate (e.g. 48000) or 48000 as safe fallback.
    """
    global _graph_rate

    # 1. Best source: PipeWire's own default clock rate
    try:
        r = subprocess.run(
            ["pw-cli", "info", "0"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "default.clock.rate" in line:
                    try:
                        raw = int(line.split("=")[-1].strip().strip('"'))
                        validated = _validate_rate(raw)
                        if validated:
                            _graph_rate = validated
                            return validated
                    except (ValueError, IndexError):
                        pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("pw-cli not available or timed out")

    # 2. Fallback: ALSA capture device rates (prefer input devices for mic)
    try:
        r2 = subprocess.run(
            ["sh", "-c", "cat /proc/asound/card*/stream* 2>/dev/null"],
            capture_output=True, text=True, timeout=5,
        )
        in_capture = False
        for line in r2.stdout.splitlines():
            if "Capture:" in line:
                in_capture = True
            elif "Playback:" in line:
                in_capture = False
            elif "Rates:" in line and in_capture:
                try:
                    raw = int(line.split("Rates:")[-1].strip().split()[0])
                    validated = _validate_rate(raw)
                    if validated:
                        _graph_rate = validated
                        return validated
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass

    # 3. Safe fallback
    log.warning("Could not detect audio rate — defaulting to 48000Hz")
    _graph_rate = 48000
    return 48000


def get_graph_rate():
    """Return the cached graph rate, detecting if needed."""
    if _graph_rate is None:
        return detect_graph_rate()
    return _graph_rate

# ── AEC parameter combinations to test ──────────────────────────────
# Format: (echo_supp, noise_supp, gain_control, extended_filter, high_pass, delay_agnostic, name)
CONFIGS = [
    # AGC ON — WebRTC manages mic gain
    (0, 0, True,  True,  False, False, "agc-baseline"),
    (1, 1, True,  True,  False, False, "agc-medium"),
    (2, 1, True,  True,  False, False, "agc-highsupp"),
    (2, 2, True,  True,  False, False, "agc-max"),
    (2, 2, True,  True,  True,  False, "agc-max-hpf"),
    (2, 2, True,  True,  True,  True,  "agc-max-all"),
    (2, 2, True,  True,  False, True,  "agc-max-delay"),
    # AGC OFF — raw cancellation, app handles gain
    (0, 0, False, True,  False, False, "raw-baseline"),
    (1, 1, False, True,  False, False, "raw-medium"),
    (2, 1, False, True,  False, False, "raw-highsupp"),
    (2, 2, False, True,  False, False, "raw-max"),
    (2, 2, False, True,  True,  False, "raw-max-hpf"),
    (2, 2, False, True,  True,  True,  "raw-max-all"),
    (2, 2, False, True,  False, True,  "raw-max-delay"),
]

# Test phrases for TTS playback
TEST_PHRASES = [
    "hey TARS, are you there?",
    "TARS, what is the weather like today?",
    "okay TARS",
    "the quick brown fox jumps over the lazy dog and runs across the field",
    "This is a longer sentence to test how echo cancellation handles sustained speech",
]


# ── Helpers ─────────────────────────────────────────────────────────

def read_mic_amp_gain():
    """Read mic_amp_gain from config.ini, default 10.0."""
    config = configparser.ConfigParser()
    config_path = os.path.join(SCRIPT_DIR, "src", "config.ini")
    try:
        config.read(config_path)
        return float(config.get("STT", "mic_amp_gain", fallback="10.0"))
    except Exception:
        return 10.0


def _get_actual_user():
    """Get the real (non-root) user when running under sudo."""
    return os.environ.get("SUDO_USER", os.environ.get("USER", ""))


def _get_actual_home():
    """Get the real user's home directory, even under sudo."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        return pwd.getpwnam(sudo_user).pw_dir
    return os.path.expanduser("~")


def _user_env():
    """Build env dict for running commands as the real user's PipeWire session."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        pw = pwd.getpwnam(sudo_user)
        uid = pw.pw_uid
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        env["HOME"] = pw.pw_dir
        env["USER"] = sudo_user
        return env
    return None  # inherit current env


def run_cmd(cmd, timeout=30, as_user=False):
    """Run a shell command, return CompletedProcess.

    as_user: if True and running under sudo, use the real user's env
             so PipeWire session commands work.
    """
    env = _user_env() if as_user else None
    prefix = []
    if as_user and os.environ.get("SUDO_USER"):
        # Drop privileges back to real user for session commands
        prefix = ["sudo", "-u", os.environ["SUDO_USER"]]
    if isinstance(cmd, str):
        full_cmd = f"{' '.join(prefix)} {cmd}" if prefix else cmd
        return subprocess.run(
            full_cmd, shell=True,
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    return subprocess.run(
        prefix + cmd, shell=False,
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def run_sudo(cmd, timeout=30):
    """Run a command with sudo."""
    if isinstance(cmd, str):
        return run_cmd(f"sudo {cmd}", timeout=timeout)
    return run_cmd(["sudo"] + cmd, timeout=timeout)


def pipewire_has_echo_source():
    """Check if echo_cancel_source exists in PipeWire."""
    r = run_cmd("pw-cli list-objects | grep echo_cancel_source", timeout=10, as_user=True)
    if r.returncode == 0 and "echo_cancel_source" in r.stdout:
        return True
    # Also try pw-dump
    r2 = run_cmd("pw-dump short 2>/dev/null | grep echo_cancel_source", timeout=10, as_user=True)
    return r2.returncode == 0 and "echo_cancel_source" in r2.stdout


def aec_module_installed():
    """Check if libpipewire-module-echo-cancel.so exists."""
    r = run_cmd("find /usr/lib -name 'libpipewire-module-echo-cancel.so' 2>/dev/null", timeout=10)
    return bool(r.stdout.strip())


def install_aec_dependencies():
    """Install PipeWire AEC dependencies."""
    log.info("Installing AEC dependencies...")
    r = run_sudo("apt-get install -y pipewire libspa-0.2-modules libwebrtc-audio-processing1 sox", timeout=120)
    if r.returncode != 0:
        log.error("Failed to install dependencies: %s", r.stderr)
        return False
    return aec_module_installed()


def restart_pipewire(timeout=15):
    """Restart PipeWire and wait for echo_cancel_source to appear."""
    run_cmd("systemctl --user restart pipewire pipewire-pulse", timeout=10, as_user=True)
    for _ in range(timeout):
        time.sleep(1)
        if pipewire_has_echo_source():
            time.sleep(1)  # extra settle time
            return True
    log.warning("echo_cancel_source not found after PipeWire restart")
    return False


def write_aec_config(supp, noise, gain_control, extended, hpf, delay_agnostic, label=""):
    """Write AEC config to /etc/pipewire/pipewire.conf.d/echo-cancel.conf"""
    gc = "true" if gain_control else "false"
    ext = "true" if extended else "false"
    hp = "true" if hpf else "false"
    da = "true" if delay_agnostic else "false"

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    label_line = f"\n# Winner: {label}  (tuned {ts})" if label else ""

    config_text = f"""{MARKER_COMMENT}{label_line}
context.modules = [
    {{
        name = libpipewire-module-echo-cancel
        args = {{
            audio.rate = {get_graph_rate()}
            audio.channels = 1
            aec.method = webrtc
            aec.args = {{
                webrtc.echo_suppression_level = {supp}
                webrtc.noise_suppression_level = {noise}
                webrtc.gain_control = {gc}
                webrtc.extended_filter = {ext}
                webrtc.high_pass_filter = {hp}
                webrtc.delay_agnostic = {da}
            }}
            capture.props = {{
                node.name = "echo_cancel_capture"
            }}
            source.props = {{
                node.name = "echo_cancel_source"
                node.description = "TARS Mic (Echo Cancelled)"
                media.class = "Audio/Source"
                priority.driver = 1000
                priority.session = 1000
            }}
            playback.props = {{
                node.name = "echo_cancel_playback"
            }}
            sink.props = {{
                node.name = "echo_cancel_sink"
                node.description = "TARS Speaker (Echo Cancel)"
                media.class = "Audio/Sink"
                priority.driver = 1000
                priority.session = 1000
            }}
        }}
    }}
]
"""
    # Ensure config directory exists
    conf_dir = os.path.dirname(AEC_CONF)
    run_sudo(f"mkdir -p {conf_dir}")

    # Write via sudo tee
    p = subprocess.Popen(
        ["sudo", "tee", AEC_CONF],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    p.communicate(input=config_text.encode())
    return p.returncode == 0


def ensure_pulse_defaults():
    """Set echo-cancelled devices as PulseAudio defaults."""
    home = _get_actual_home()
    pulse_dir = os.path.join(home, ".config", "pipewire", "pipewire-pulse.conf.d")
    os.makedirs(pulse_dir, exist_ok=True)
    conf_path = os.path.join(pulse_dir, "default-devices.conf")
    with open(conf_path, "w") as f:
        f.write('pulse.cmd = [\n')
        f.write('    { cmd = "set-default-source" args = "echo_cancel_source" }\n')
        f.write('    { cmd = "set-default-sink" args = "echo_cancel_sink" }\n')
        f.write(']\n')
    # Fix ownership if running under sudo (files were created as root)
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        pw = pwd.getpwnam(sudo_user)
        config_dir = os.path.join(home, ".config", "pipewire")
        for dirpath, dirnames, filenames in os.walk(config_dir):
            os.chown(dirpath, pw.pw_uid, pw.pw_gid)
            for fn in filenames:
                os.chown(os.path.join(dirpath, fn), pw.pw_uid, pw.pw_gid)


# ── TTS generation ──────────────────────────────────────────────────
# Uses the same PiperVoice Python library as module_piper.py / module_tts.py,
# then replicates the exact gain chain from play_audio_chunks():
#   1. PiperVoice.synthesize → wav (native sample rate, e.g. 22050)
#   2. Read as float32, resample to 16kHz
#   3. Normalize to peak 1.0
#   4. Multiply by 1.5 (TTS_GAIN)
#   5. Clip to [-1.0, 1.0]

_piper_voice = None  # lazy-loaded


def _load_piper_voice():
    """Load PiperVoice using the same method as module_piper.py."""
    global _piper_voice
    if _piper_voice is not None:
        return _piper_voice

    # Read character name from config, same as module_piper.py
    config = configparser.ConfigParser()
    config.read(os.path.join(SCRIPT_DIR, "src", "config.ini"))
    char_path = config.get("CHAR", "character_card_path", fallback="")
    char_name = os.path.splitext(os.path.basename(char_path))[0] if char_path else "TARS"
    model_path = os.path.join(SCRIPT_DIR, "src", "character", char_name, "voice", f"{char_name}.onnx")

    if not os.path.isfile(model_path):
        log.warning("Piper model not found: %s", model_path)
        return None

    # Check for LFS pointer (same as module_piper.py)
    try:
        with open(model_path, "rb") as f:
            if f.read(20).startswith(b"version https://git-lfs"):
                log.warning("Piper model is a Git LFS pointer, not the actual file")
                return None
    except Exception:
        pass

    try:
        from piper.voice import PiperVoice
        _piper_voice = PiperVoice.load(model_path)
        log.info("Loaded PiperVoice model: %s (rate=%dHz)", char_name, _piper_voice.config.sample_rate)
        return _piper_voice
    except ImportError:
        log.warning("piper.voice not available — pip install piper-tts?")
        return None
    except Exception as e:
        log.warning("Failed to load PiperVoice: %s", e)
        return None


def _apply_tts_gain_chain(data, src_rate):
    """Replicate the exact gain chain from module_tts.py play_audio_chunks().

    The real app does:
      1. Resample Piper output (22050Hz) → 16kHz
      2. Normalize to peak 1.0
      3. Multiply by 1.5 (TTS_GAIN), clip to [-1.0, 1.0]
      4. sd.play() at 16kHz → PipeWire receives 16kHz, resamples to graph rate

    We replicate steps 1-3 identically and output at 16kHz.  When pw-play
    sends this 16kHz audio to echo_cancel_sink, PipeWire does the same
    resampling it would do in production — so the AEC sees the exact same
    reference signal.  This is critical for accurate tuning.
    """
    import numpy as np

    # Step 1: Resample to 16kHz (same linear interp as module_tts.py:434-446)
    if src_rate != APP_PLAYBACK_RATE:
        ratio = APP_PLAYBACK_RATE / src_rate
        new_len = int(len(data) * ratio)
        indices = np.linspace(0, len(data) - 1, new_len)
        data = np.interp(indices, np.arange(len(data)), data)

    # Step 2: Normalize to peak 1.0 (module_tts.py:448-450)
    max_val = np.max(np.abs(data))
    if max_val > 0:
        data = data / max_val

    # Step 3: Apply gain and clip (module_tts.py:452-453)
    data = np.clip(data * TTS_GAIN, -1.0, 1.0)

    # NO upsample — output at 16kHz so PipeWire does the same resampling
    # to graph rate as it does in production with sd.play(data, 16000)
    return data


def generate_tts_wav(phrase, outfile, tmpdir):
    """Generate a TTS wav file matching the exact TARS-AI pipeline.

    Uses PiperVoice (same Python lib as the real app), falls back to espeak-ng + sox.
    Output: 16kHz mono wav — same rate the app sends via sd.play().
    PipeWire will resample to graph rate (e.g. 48kHz), same as production.
    """
    import numpy as np
    import wave as wave_mod

    voice = _load_piper_voice()

    if voice is not None:
        try:
            # Synthesize with PiperVoice (same as module_piper.py:synthesize)
            from io import BytesIO
            wav_buffer = BytesIO()
            with wave_mod.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(voice.config.sample_rate)
                if hasattr(voice, "synthesize_wav"):
                    voice.synthesize_wav(phrase, wf)
                elif hasattr(voice, "synthesize"):
                    voice.synthesize(phrase, wf)
                else:
                    raise AttributeError("PiperVoice has no synthesize method")

            # Read back as float32 (same as module_tts.py:431)
            wav_buffer.seek(0)
            import soundfile as sf
            data, sr = sf.read(wav_buffer, dtype="float32")

            # Apply the exact same gain chain as the real app
            data = _apply_tts_gain_chain(data, sr)

            # Write as 16-bit PCM wav at 16kHz (same as sd.play rate)
            pcm = (data * 32767).astype(np.int16)
            with wave_mod.open(outfile, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(APP_PLAYBACK_RATE)
                wf.writeframes(pcm.tobytes())
            return True

        except Exception as e:
            log.warning("PiperVoice synthesis failed: %s — falling back to espeak-ng", e)

    # Fallback: espeak-ng + sox (won't match TARS voice but still tests AEC)
    raw_file = os.path.join(tmpdir, "raw_tts.wav")
    r = subprocess.run(
        ["espeak-ng", "-w", raw_file, phrase],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        log.error("espeak-ng failed: %s", r.stderr)
        return False

    # Apply gain chain via sox, output at 16kHz (matching app playback rate)
    r = subprocess.run(
        ["sox", raw_file, outfile, "norm", "0", "vol", str(TTS_GAIN),
         "rate", str(APP_PLAYBACK_RATE), "channels", "1"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        log.error("sox processing failed: %s", r.stderr)
        return False
    return True


# ── Recording & measurement ─────────────────────────────────────────

class Recorder:
    """Background WAV recorder using pw-record targeting echo_cancel_source."""

    def __init__(self):
        self.proc = None

    def start(self, outfile):
        env = _user_env() or os.environ.copy()
        # Don't force --rate: let pw-record use echo_cancel_source's native
        # rate (= graph rate).  This avoids extra resampling during measurement.
        cmd = [
            "pw-record",
            "--target", "echo_cancel_source",
            "--channels", "1",
            "--format", "s16",
            outfile,
        ]
        # If running under sudo, drop to real user
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            cmd = ["sudo", "-u", sudo_user] + cmd
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        # Brief check that it didn't immediately die
        time.sleep(0.2)
        if self.proc.poll() is not None:
            stderr = self.proc.stderr.read().decode(errors="replace").strip()
            log.warning("pw-record failed to start: %s", stderr[:120])
            self.proc = None

    def stop(self):
        if self.proc:
            try:
                self.proc.send_signal(signal.SIGINT)
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
                self.proc.wait(timeout=3)
            self.proc = None

    def __del__(self):
        self.stop()


def play_through_aec_sink(wav_file):
    """Play a wav file through echo_cancel_sink."""
    r = run_cmd(
        ["pw-play", "--target", "echo_cancel_sink", wav_file],
        timeout=30,
        as_user=True,
    )
    return r.returncode == 0


def measure_rms(wav_file):
    """Measure RMS amplitude of a wav file using sox."""
    r = run_cmd(f"sox {wav_file} -n stat", timeout=10)
    # sox stat outputs to stderr
    output = r.stderr if r.stderr else r.stdout
    for line in output.splitlines():
        if "RMS     amplitude" in line:
            try:
                return float(line.split()[-1])
            except (ValueError, IndexError):
                pass
    return 0.000001


def measure_echo_bleed(play_file, rec_file, recorder):
    """Play audio through AEC sink while recording from AEC source, return raw RMS."""
    recorder.start(rec_file)
    time.sleep(0.5)  # let recorder settle

    play_through_aec_sink(play_file)

    time.sleep(1.5)  # capture echo tail
    recorder.stop()

    rms = measure_rms(rec_file)
    if rms == 0 or rms != rms:  # nan check
        rms = 0.000001
    return rms


def warmup_aec(phrase_files, recorder, tmpdir):
    """Play multiple phrases to let the adaptive filter fully converge.

    WebRTC's AEC needs several seconds of reference audio to build
    an accurate echo path model.  One short phrase (~2s) often isn't
    enough — play 2-3 to give it ~5-8s of training data.
    """
    warmup_rec = os.path.join(tmpdir, "warmup.wav")
    recorder.start(warmup_rec)
    time.sleep(0.3)
    # Play up to 3 phrases (or all if fewer available)
    for pf in phrase_files[:3]:
        play_through_aec_sink(pf)
        time.sleep(0.3)
    time.sleep(0.5)
    recorder.stop()


# ── Main logic ──────────────────────────────────────────────────────

def is_aec_configured():
    """Check if AEC is already properly configured and running."""
    if not os.path.isfile(AEC_CONF):
        return False
    if not pipewire_has_echo_source():
        return False
    return True


def is_aec_tuned():
    """Check if the existing config was auto-tuned (vs default from Install.sh)."""
    if not os.path.isfile(AEC_CONF):
        return False
    try:
        with open(AEC_CONF) as f:
            return MARKER_COMMENT in f.read()
    except Exception:
        return False


def run_tuning():
    """Test all AEC configs and return the best one."""
    mic_amp_gain = read_mic_amp_gain()
    recorder = Recorder()

    with tempfile.TemporaryDirectory(prefix="aec_tune_") as tmpdir:
        # Check sox is available
        if not shutil.which("sox"):
            log.error("sox not found. Install with: sudo apt install sox")
            return None

        # Generate test audio
        log.info("Generating %d test phrases...", len(TEST_PHRASES))
        phrase_files = []
        for i, phrase in enumerate(TEST_PHRASES):
            outfile = os.path.join(tmpdir, f"phrase_{i}.wav")
            if generate_tts_wav(phrase, outfile, tmpdir):
                phrase_files.append(outfile)
                log.info("  [%d/%d] Generated: %s", i + 1, len(TEST_PHRASES), phrase[:50])
            else:
                log.warning("  [%d/%d] Failed to generate: %s", i + 1, len(TEST_PHRASES), phrase[:50])

        if not phrase_files:
            log.error("No test phrases generated — cannot tune AEC")
            return None

        # Sanity check: verify mic can hear the speaker (no point testing if not)
        log.info("Verifying speaker-to-mic path...")
        check_rec = os.path.join(tmpdir, "sanity_check.wav")
        recorder.start(check_rec)
        time.sleep(0.3)
        play_through_aec_sink(phrase_files[0])
        time.sleep(0.5)
        recorder.stop()
        check_rms = measure_rms(check_rec)
        if check_rms < 0.00005:
            print(_red("  WARNING: Mic cannot hear the speaker (RMS too low)."))
            print(_red("  Check that your speaker and mic are connected and working."))
            print(_dim(f"  Measured RMS: {check_rms:.8f}"))
            log.error("Speaker-to-mic sanity check failed — aborting")
            return None

        # Record silence baseline
        log.info("Recording 3s of ambient silence...")
        silence_file = os.path.join(tmpdir, "silence.wav")
        recorder.start(silence_file)
        time.sleep(3)
        recorder.stop()
        silence_rms = measure_rms(silence_file)
        log.info("  Noise floor RMS: %.6f (amplified: %.6f)", silence_rms, silence_rms * mic_amp_gain)

        # Test each config
        results = []
        total = len(CONFIGS)
        start_time = time.time()

        try:
            for idx, (supp, noise, gc, ext, hpf, da, name) in enumerate(CONFIGS):
                elapsed = time.time() - start_time
                if idx > 0:
                    per_config = elapsed / idx
                    remaining = per_config * (total - idx)
                    eta = f" (ETA: {int(remaining // 60)}m{int(remaining % 60)}s)"
                else:
                    eta = ""

                # Progress bar
                filled = int((idx / total) * 20)
                bar = _cyan("█" * filled) + _dim("░" * (20 - filled))
                print(f"  [{bar}] {_white(f'{idx+1}/{total}')} {_orange(name)}{_dim(eta)}")
                log.info("  supp=%d noise=%d agc=%s ext=%s hpf=%s delay=%s",
                         supp, noise, gc, ext, hpf, da)

                # Write config and restart PipeWire
                if not write_aec_config(supp, noise, gc, ext, hpf, da):
                    log.warning("  Failed to write config — skipping")
                    continue

                if not restart_pipewire():
                    log.warning("  PipeWire failed to load config — skipping")
                    results.append((name, float("inf"), supp, noise, gc, ext, hpf, da))
                    continue

                # Warmup: play multiple phrases so adaptive filter converges
                warmup_aec(phrase_files, recorder, tmpdir)

                # Test each phrase
                rms_values = []
                for pi, pfile in enumerate(phrase_files):
                    rec_file = os.path.join(tmpdir, f"rec_{name}_p{pi}.wav")
                    rms = measure_echo_bleed(pfile, rec_file, recorder)
                    rms_values.append(rms)

                avg_rms = sum(rms_values) / len(rms_values)
                print(_dim(f"    => bleed: {avg_rms:.6f}  (amplified: {avg_rms * mic_amp_gain:.6f})"))
                results.append((name, avg_rms, supp, noise, gc, ext, hpf, da))
        finally:
            # Always clean up recorder even if an exception occurs
            recorder.stop()

        if not results:
            log.error("No configs tested successfully")
            return None

        # Sort by avg RMS (lower = better)
        results.sort(key=lambda x: x[1])

        print()
        print(_cyan("╔════╦══════════════════════╦════════════╦══════════════════════╗"))
        print(_cyan("║") + _bold(_white(" ##")) + " " + _cyan("║") + _bold(_white(" Config              ")) + " " + _cyan("║") + _bold(_white(" Avg RMS   ")) + " " + _cyan("║") + _bold(_white(" Amplified (app)    ")) + " " + _cyan("║"))
        print(_cyan("╠════╬══════════════════════╬════════════╬══════════════════════╣"))
        for rank, (name, avg, *_) in enumerate(results, 1):
            if avg == float("inf"):
                print(_cyan("║") + f" {rank:2d} " + _cyan("║") + f" {_red(name):<20s} " + _cyan("║") + f"  {_red('FAILED')}    " + _cyan("║") + "  ---                 " + _cyan("║"))
            else:
                if rank == 1:
                    n = _green(f"{name:<20s}")
                    v = _green(f"{avg:10.6f}")
                    a = _green(f"{avg * mic_amp_gain:10.6f}")
                    tag = _orange(" <<")
                elif rank <= 3:
                    n = _white(f"{name:<20s}")
                    v = _white(f"{avg:10.6f}")
                    a = _white(f"{avg * mic_amp_gain:10.6f}")
                    tag = "   "
                else:
                    n = _dim(f"{name:<20s}")
                    v = _dim(f"{avg:10.6f}")
                    a = _dim(f"{avg * mic_amp_gain:10.6f}")
                    tag = "   "
                print(_cyan("║") + f" {rank:2d} " + _cyan("║") + f" {n} " + _cyan("║") + f" {v} " + _cyan("║") + f" {a}{tag}         " + _cyan("║"))
        print(_cyan("╚════╩══════════════════════╩════════════╩══════════════════════╝"))

        best = results[0]
        print()
        print(_cyan("  TARS: ") + "Optimal config identified -> " + _green(_bold(best[0])))
        print(_dim(f"        Echo bleed RMS: {best[1]:.6f}"))

        return best  # (name, avg_rms, supp, noise, gc, ext, hpf, da)


def _prompt_user_ready():
    """Explain the tuning process and wait for the user to confirm."""
    rate = get_graph_rate()
    print()
    print(_cyan("╔═══════════════════════════════════════════════════════════════╗"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("║") + _orange("           ░█▀▀░█▀▀░█░█░█▀█░░░█▀▀░█▀█░█▀█░█▀▀░█▀▀░█░░          ") + _cyan("║"))
    print(_cyan("║") + _orange("           ░█▀▀░█░░░█▀█░█░█░░░█░░░█▀█░█░█░█░░░█▀▀░█░░          ") + _cyan("║"))
    print(_cyan("║") + _orange("           ░▀▀▀░▀▀▀░▀░▀░▀▀▀░░░▀▀▀░▀░▀░▀░▀░▀▀▀░▀▀▀░▀▀▀          ") + _cyan("║"))
    print(_cyan("║") + _bold(_white("               [ TARS-AI  AEC  TUNING  MODULE ]                ")) + _cyan("║"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("╠═══════════════════════════════════════════════════════════════╣"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("║") + f"   {_dim('Graph rate ....')} {_white(f'{rate}Hz')} {_dim('(auto-detected)')}" + "                     " + _cyan("║"))
    print(_cyan("║") + f"   {_dim('Duration .....')} {_white('~4-5 minutes')}" + "                                 " + _cyan("║"))
    print(_cyan("║") + f"   {_dim('Reboot .......')} {_green('not required')}" + "                                 " + _cyan("║"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("╠═══════════════════════════════════════════════════════════════╣"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("║") + _dim("   TARS will speak test phrases through the speaker while      ") + _cyan("║"))
    print(_cyan("║") + _dim("   recording from the mic. Each AEC config is scored by how    ") + _cyan("║"))
    print(_cyan("║") + _dim("   much speaker audio bleeds into the microphone.              ") + _cyan("║"))
    print(_cyan("║") + _dim("   The config with the lowest bleed wins.                      ") + _cyan("║"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("║") + _orange("   Any talking, music, or ambient noise near the mic will      ") + _cyan("║"))
    print(_cyan("║") + _orange("   corrupt the measurements and select a bad config.           ") + _cyan("║"))
    print(_cyan("║") + _orange("   Please keep the room quiet until tuning completes.          ") + _cyan("║"))
    print(_cyan("║") + "                                                               " + _cyan("║"))
    print(_cyan("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    try:
        resp = input(_cyan("  TARS: ") + "Ready to begin calibration? [Y/n]: ")
        if resp.strip().lower() in ("n", "no"):
            return False
    except (EOFError, KeyboardInterrupt):
        # Non-interactive (e.g. piped input or service) — proceed automatically
        log.info("Non-interactive mode — proceeding automatically")
    return True


def setup_aec(force=False):
    """Main entry point: check if AEC needs setup, and configure it."""


    # Check if AEC module is available
    if not aec_module_installed():
        log.info("AEC module not found, installing dependencies...")
        if not install_aec_dependencies():
            log.error("Could not install AEC module — AEC not available on this system")
            return False

    # Check if already configured
    if not force and is_aec_configured():
        log.info("AEC is already configured — nothing to do")
        log.info("  (use --force or aec=tune to re-tune)")
        return True

    if not force:
        # No flag and not configured — just install raw-max default
        log.info("AEC not configured — installing default config (raw-max-all)")
        apply_named_config("raw-max-all")
        return True

    log.info("Starting AEC auto-tune...")
    _clear_disabled_marker()

    # Prompt user before starting the noisy test
    if not _prompt_user_ready():
        log.info("Tuning cancelled by user")
        return False

    # Backup existing config
    if os.path.isfile(AEC_CONF):
        backup = AEC_CONF + ".backup"
        run_sudo(f"cp {AEC_CONF} {backup}")
        log.info("Backed up existing config to %s", backup)

    # Write a baseline config first so PipeWire has echo_cancel nodes
    # Use a reasonable default to start
    write_aec_config(2, 2, False, True, True, True)
    ensure_pulse_defaults()

    if not restart_pipewire(timeout=15):
        log.error("PipeWire could not start with AEC — check your audio hardware")
        return False

    # Detect graph rate now that PipeWire is confirmed running
    graph_rate = detect_graph_rate()
    print()
    print(_cyan("╠═══════════════════════════════════════════════════════════════╣"))
    print(_cyan("  TARS: ") + f"AEC module loaded. Graph rate: {_white(f'{graph_rate}Hz')}")
    print(_cyan("  TARS: ") + f"Testing {_white(f'{len(CONFIGS)}')} configs x {_white(f'{len(TEST_PHRASES)}')} phrases. " + _orange("Stay quiet..."))
    print(_cyan("╠═══════════════════════════════════════════════════════════════╣"))
    print()

    best = run_tuning()

    if best is None:
        log.error("Tuning failed — applying safe default config")
        write_aec_config(2, 2, False, True, True, True)
        ensure_pulse_defaults()
        restart_pipewire()
        return False

    # Apply the best config
    name, avg_rms, supp, noise, gc, ext, hpf, da = best
    print()
    print(_cyan("  TARS: ") + f"Applying optimal config -> {_green(_bold(name))}")
    write_aec_config(supp, noise, gc, ext, hpf, da, label=name)
    ensure_pulse_defaults()

    if restart_pipewire():
        print()
        print(_green("╔═══════════════════════════════════════════════════════════════╗"))
        print(_green("║") + "                                                               " + _green("║"))
        print(_green("║") + _bold(_white(f"   AEC ACTIVE: {name:<20s}")) + "                            " + _green("║"))
        print(_green("║") + _dim(f"   Echo bleed: {avg_rms:<10.6f}  Config: echo-cancel.conf") + "      " + _green("║"))
        print(_green("║") + "                                                               " + _green("║"))
        print(_green("║") + _cyan("   TARS: Echo cancellation calibrated and operational.") + "         " + _green("║"))
        print(_green("║") + "                                                               " + _green("║"))
        print(_green("╚═══════════════════════════════════════════════════════════════╝"))
        print()
        return True
    else:
        log.error("Failed to restart PipeWire with best config")
        return False


def _clear_disabled_marker():
    """Remove the .aec_disabled marker if it exists (user is re-enabling AEC)."""
    if os.path.isfile(AEC_DISABLED_MARKER):
        os.remove(AEC_DISABLED_MARKER)


def is_aec_disabled():
    """Check if user explicitly disabled AEC via aec=remove."""
    return os.path.isfile(AEC_DISABLED_MARKER)


def apply_named_config(config_name):
    """Apply a specific AEC config by name (e.g. 'raw-max-all', 'agc-medium').

    Skips the full tuning process — just writes the named config directly.
    Use this when you already know which config works best.
    """
    _clear_disabled_marker()
    # Find the config by name
    match = None
    for cfg in CONFIGS:
        if cfg[6] == config_name:
            match = cfg
            break

    if match is None:
        valid = [c[6] for c in CONFIGS]
        print(_red(f"  Unknown AEC config: '{config_name}'"))
        print(_dim(f"  Valid configs: {', '.join(valid)}"))
        return False

    supp, noise, gc, ext, hpf, da, name = match

    print()
    print(_cyan("╔═══════════════════════════════════════════════════════════════╗"))
    print(_cyan("║") + _bold(_white(f"  Applying AEC config: {name:<20s}")) + "                       " + _cyan("║"))
    print(_cyan("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(_dim(f"  supp={supp} noise={noise} agc={gc} ext={ext} hpf={hpf} delay={da}"))

    write_aec_config(supp, noise, gc, ext, hpf, da, label=f"{name} (manual)")
    ensure_pulse_defaults()

    if restart_pipewire():
        print()
        print(_green(f"  TARS: AEC config '{name}' applied and active."))
        print()
        return True
    else:
        log.error("Failed to restart PipeWire with config: %s", name)
        return False


def remove_aec():
    """Remove AEC configuration and restore original state.

    - Restores backup config if one exists, otherwise deletes the config
    - Removes the pulse default-devices override
    - Restarts PipeWire to apply changes
    """
    print()
    print(_orange("╔═══════════════════════════════════════════════════════════════╗"))
    print(_orange("║") + _bold(_white("              TARS-AI  AEC  Removal                            ")) + _orange("║"))
    print(_orange("╚═══════════════════════════════════════════════════════════════╝"))
    print()

    backup = AEC_CONF + ".backup"

    if os.path.isfile(backup):
        log.info("Restoring backup config from %s", backup)
        run_sudo(f"cp {backup} {AEC_CONF}")
        run_sudo(f"rm {backup}")
        log.info("Backup restored")
    elif os.path.isfile(AEC_CONF):
        log.info("No backup found — removing %s", AEC_CONF)
        run_sudo(f"rm {AEC_CONF}")
    else:
        log.info("No AEC config found — nothing to remove")

    # Remove pulse defaults override
    home = _get_actual_home()
    pulse_conf = os.path.join(home, ".config", "pipewire", "pipewire-pulse.conf.d", "default-devices.conf")
    if os.path.isfile(pulse_conf):
        os.remove(pulse_conf)
        log.info("Removed pulse defaults override: %s", pulse_conf)

    # Drop marker so auto-setup doesn't re-install on next boot
    with open(AEC_DISABLED_MARKER, "w") as f:
        f.write("AEC explicitly removed by user. Delete this file to re-enable auto-setup.\n")
    log.info("Created %s — AEC won't auto-install on next boot", AEC_DISABLED_MARKER)

    # Restart PipeWire to apply
    run_cmd("systemctl --user restart pipewire pipewire-pulse", timeout=10, as_user=True)
    time.sleep(2)

    if pipewire_has_echo_source():
        log.warning("echo_cancel_source still present — you may need to reboot")
    else:
        log.info("AEC removed — PipeWire running without echo cancellation")

    return True


if __name__ == "__main__":
    if "--remove" in sys.argv:
        try:
            remove_aec()
            sys.exit(0)
        except Exception as e:
            log.error("Remove failed: %s", e)
            sys.exit(1)

    # --apply <config-name>  (e.g. --apply raw-max-all)
    if "--apply" in sys.argv:
        idx = sys.argv.index("--apply")
        if idx + 1 < len(sys.argv):
            name = sys.argv[idx + 1]
            try:
                sys.exit(0 if apply_named_config(name) else 1)
            except Exception as e:
                log.error("Apply failed: %s", e)
                sys.exit(1)
        else:
            valid = [c[6] for c in CONFIGS]
            print(f"Usage: python3 aec.py --apply <config-name>")
            print(f"Available: {', '.join(valid)}")
            sys.exit(1)

    force = "--force" in sys.argv
    try:
        success = setup_aec(force=force)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log.info("\nAborted by user")
        sys.exit(130)
    except Exception as e:
        log.error("Unexpected error: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
