#!/usr/bin/env python3
"""
AEC Diagnostic Tool for TARS-AI
================================
Tests echo cancellation quality by playing audio through the AEC pipeline
and measuring how much leaks into the mic recording.

Usage:
    sudo python3 tools/aec-test.py              # Full diagnostic
    sudo python3 tools/aec-test.py --quick       # Quick single-phrase test
    sudo python3 tools/aec-test.py --loop 10     # Repeat test N times (stability check)
    sudo python3 tools/aec-test.py --silence      # Measure silence floor only
    sudo python3 tools/aec-test.py --latency      # Measure AEC latency
    sudo python3 tools/aec-test.py --compare      # Compare AEC performance
"""

import os
import sys
import time
import signal
import shutil
import tempfile
import argparse
import subprocess
import configparser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# Add venv site-packages so we can import project libs
import glob as glob_mod
_venv_sp = glob_mod.glob(os.path.join(PROJECT_DIR, "src", ".venv", "lib", "python*", "site-packages"))
for sp in _venv_sp:
    if sp not in sys.path:
        sys.path.insert(0, sp)

# ── ANSI colors ─────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()
def _c(code, text): return f"\033[{code}m{text}\033[0m" if _USE_COLOR else str(text)
def _cyan(t):   return _c("38;2;0;200;255", t)
def _green(t):  return _c("38;2;0;255;100", t)
def _red(t):    return _c("38;2;255;60;60", t)
def _yellow(t): return _c("38;2;255;200;0", t)
def _dim(t):    return _c("2", t)
def _bold(t):   return _c("1", t)

AEC_CONF = "/etc/pipewire/pipewire.conf.d/echo-cancel.conf"
APP_PLAYBACK_RATE = 16000

TEST_PHRASES = [
    "hey TARS, are you there?",
    "TARS, what is the weather like today?",
    "the quick brown fox jumps over the lazy dog and runs across the field",
    "This is a longer sentence to test how echo cancellation handles sustained speech",
    "Tell me about the history of space exploration and the Apollo missions",
]


# ── Helpers ──────────────────────────────────────────────────────────

def _get_actual_user():
    return os.environ.get("SUDO_USER", os.environ.get("USER", ""))

def _user_env():
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
    return None

def run_cmd(cmd, timeout=30, as_user=False):
    env = _user_env() if as_user else None
    prefix = []
    sudo_user = os.environ.get("SUDO_USER")
    if as_user and sudo_user:
        import pwd
        uid = pwd.getpwnam(sudo_user).pw_uid
        # sudo strips env vars — pass XDG_RUNTIME_DIR inline so pw-cli/pw-play work
        prefix_env = f"XDG_RUNTIME_DIR=/run/user/{uid}"
        prefix = ["sudo", "-u", sudo_user, "env", prefix_env]
    if isinstance(cmd, str):
        full_cmd = f"{' '.join(prefix)} {cmd}" if prefix else cmd
        return subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    return subprocess.run(prefix + cmd, shell=False, capture_output=True, text=True, timeout=timeout, env=env)


class Recorder:
    """Background WAV recorder using pw-record."""
    def __init__(self, target="echo_cancel_source"):
        self.proc = None
        self.target = target

    def start(self, outfile):
        env = _user_env() or os.environ.copy()
        cmd = ["pw-record", "--target", self.target, "--channels", "1", "--format", "s16", outfile]
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            import pwd
            uid = pwd.getpwnam(sudo_user).pw_uid
            cmd = ["sudo", "-u", sudo_user, "env", f"XDG_RUNTIME_DIR=/run/user/{uid}"] + cmd
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        time.sleep(0.3)
        if self.proc.poll() is not None:
            stderr = self.proc.stderr.read().decode(errors="replace").strip()
            print(f"  {_red('ERROR')}: pw-record failed: {stderr[:120]}")
            self.proc = None
            return False
        return True

    def stop(self):
        if self.proc:
            try:
                self.proc.send_signal(signal.SIGINT)
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
                self.proc.wait(timeout=3)
            self.proc = None


def play_audio(wav_file, target="echo_cancel_sink"):
    r = run_cmd(["pw-play", "--target", target, wav_file], timeout=30, as_user=True)
    return r.returncode == 0


def play_aec_sink(wav_file):
    return play_audio(wav_file, "echo_cancel_sink")


def measure_rms(wav_file):
    r = run_cmd(f"sox {wav_file} -n stat", timeout=10)
    output = r.stderr if r.stderr else r.stdout
    for line in output.splitlines():
        if "RMS     amplitude" in line:
            try:
                return float(line.split()[-1])
            except (ValueError, IndexError):
                pass
    return 0.0


def measure_peak(wav_file):
    r = run_cmd(f"sox {wav_file} -n stat", timeout=10)
    output = r.stderr if r.stderr else r.stdout
    for line in output.splitlines():
        if "Maximum amplitude" in line:
            try:
                return float(line.split()[-1])
            except (ValueError, IndexError):
                pass
    return 0.0


def get_duration(wav_file):
    r = run_cmd(f"soxi -D {wav_file}", timeout=10)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def generate_tts_wav(phrase, outfile, tmpdir):
    """Generate TTS wav matching TARS pipeline. Uses Piper, falls back to espeak."""
    try:
        import numpy as np

        # Try Piper first
        sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))
        from modules.module_piper import voice
        if voice:
            from io import BytesIO
            import wave as wave_mod
            import soundfile as sf

            wav_buffer = BytesIO()
            with wave_mod.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(voice.config.sample_rate)
                if hasattr(voice, "synthesize_wav"):
                    voice.synthesize_wav(phrase, wf)
                elif hasattr(voice, "synthesize"):
                    voice.synthesize(phrase, wf)

            wav_buffer.seek(0)
            data, sr = sf.read(wav_buffer, dtype="float32")

            # Match TARS gain chain: resample to 16k -> normalize -> 1.5x -> clip
            if sr != APP_PLAYBACK_RATE:
                try:
                    import soxr
                    data = soxr.resample(data, sr, APP_PLAYBACK_RATE)
                except ImportError:
                    from scipy.signal import resample_poly
                    from math import gcd
                    g = gcd(sr, APP_PLAYBACK_RATE)
                    data = resample_poly(data, APP_PLAYBACK_RATE // g, sr // g)

            peak = np.abs(data).max()
            if peak > 0:
                data = data / peak
            data = data * 1.5
            data = np.clip(data, -1.0, 1.0)

            pcm = (data * 32767).astype(np.int16)
            with wave_mod.open(outfile, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(APP_PLAYBACK_RATE)
                wf.writeframes(pcm.tobytes())
            return True
    except Exception as e:
        print(f"  {_dim(f'Piper unavailable ({e}), using espeak')}")

    # Fallback: espeak-ng
    raw_file = os.path.join(tmpdir, "raw_tts.wav")
    r = subprocess.run(["espeak-ng", "-w", raw_file, phrase], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        return False
    r = subprocess.run(
        ["sox", raw_file, outfile, "norm", "0", "vol", "1.5", "rate", str(APP_PLAYBACK_RATE), "channels", "1"],
        capture_output=True, text=True, timeout=15,
    )
    return r.returncode == 0


def rms_to_rating(rms):
    """Rate AEC quality based on echo bleed RMS."""
    if rms < 0.0005:
        return _green("EXCELLENT"), "Echo virtually eliminated"
    elif rms < 0.002:
        return _green("GOOD"), "Minimal echo leakage"
    elif rms < 0.005:
        return _yellow("FAIR"), "Some echo leakage — may cause false STT triggers"
    elif rms < 0.01:
        return _yellow("POOR"), "Significant echo — barge-in will be unreliable"
    else:
        return _red("FAILING"), "AEC not working effectively"


# ── Pre-flight checks ───────────────────────────────────────────────

def preflight():
    """Check that AEC infrastructure is working."""
    print(f"\n{_bold(_cyan('AEC DIAGNOSTIC TOOL'))}")
    print(f"{_dim('─' * 60)}\n")

    errors = []

    # Check pipewire running — use pw-cli which respects XDG_RUNTIME_DIR
    r = run_cmd("pw-cli info 0", timeout=5, as_user=True)
    pw_active = r.returncode == 0 and "core.name" in r.stdout
    print(f"  PipeWire service:    {_green('ACTIVE') if pw_active else _red('INACTIVE')}")
    if not pw_active:
        errors.append("PipeWire is not running")

    # Check echo-cancel module
    r = run_cmd("pw-cli list-objects | grep echo_cancel_source", timeout=10, as_user=True)
    aec_loaded = r.returncode == 0 and "echo_cancel_source" in r.stdout
    print(f"  Echo-cancel module:  {_green('LOADED') if aec_loaded else _red('NOT FOUND')}")
    if not aec_loaded:
        errors.append("echo_cancel_source not found — run: sudo python3 aec.py --force")

    # Check config exists
    conf_exists = os.path.isfile(AEC_CONF)
    print(f"  AEC config file:     {_green('FOUND') if conf_exists else _red('MISSING')}")
    if conf_exists:
        with open(AEC_CONF) as f:
            conf_text = f.read()
        if "library.name" in conf_text:
            print(f"  AEC method:          {_green('library.name (modern)')}")
        elif "aec.method" in conf_text:
            print(f"  AEC method:          {_yellow('aec.method (legacy)')}")

    # Check required tools
    for tool in ["pw-play", "pw-record", "sox"]:
        found = shutil.which(tool) is not None
        if not found:
            errors.append(f"{tool} not found — install it")
        print(f"  {tool:22s} {_green('OK') if found else _red('MISSING')}")

    # PipeWire version
    r = run_cmd("pipewire --version", timeout=5)
    for line in r.stdout.splitlines():
        if "Compiled" in line or "Linked" in line:
            print(f"  {_dim(line.strip())}")

    # Read mic amp gain
    config = configparser.ConfigParser()
    config.read(os.path.join(PROJECT_DIR, "src", "config.ini"))
    amp_gain = float(config.get("STT", "mic_amp_gain", fallback="10.0"))
    print(f"  Mic amp gain:        {amp_gain}x")

    print()
    if errors:
        for e in errors:
            print(f"  {_red('✗')} {e}")
        print()
        return False
    print(f"  {_green('✓')} All pre-flight checks passed\n")
    return True


# ── Tests ────────────────────────────────────────────────────────────

def test_silence_floor(tmpdir, recorder):
    """Measure the baseline noise floor with no audio playing."""
    print(f"\n{_bold('Test 1: Silence Floor')}")
    print(f"{_dim('  Recording 3s of silence from echo_cancel_source...')}")

    rec_file = os.path.join(tmpdir, "silence.wav")
    if not recorder.start(rec_file):
        print(f"  {_red('FAILED')}: Could not start recording")
        return None

    time.sleep(3.0)
    recorder.stop()

    rms = measure_rms(rec_file)
    peak = measure_peak(rec_file)
    print(f"  Silence RMS:   {rms:.6f}")
    print(f"  Silence Peak:  {peak:.6f}")

    if rms < 0.001:
        print(f"  {_green('PASS')} — Clean silence floor")
    elif rms < 0.005:
        print(f"  {_yellow('WARN')} — Elevated noise floor")
    else:
        print(f"  {_red('FAIL')} — Very noisy environment or mic issue")
    return rms


def test_echo_bleed(tmpdir, recorder, phrases=None, warmup=True):
    """Play TTS through AEC sink, record from AEC source, measure leakage."""
    if phrases is None:
        phrases = TEST_PHRASES

    print(f"\n{_bold('Test 2: Echo Bleed')}")

    # Generate TTS wav files
    wav_files = []
    for i, phrase in enumerate(phrases):
        wav_path = os.path.join(tmpdir, f"phrase_{i}.wav")
        print(f"  {_dim(f'Generating TTS: {phrase[:50]}...')}")
        if generate_tts_wav(phrase, wav_path, tmpdir):
            wav_files.append((phrase, wav_path))
        else:
            print(f"  {_yellow('SKIP')}: Failed to generate TTS for phrase {i}")

    if not wav_files:
        print(f"  {_red('FAILED')}: No TTS files generated")
        return None

    # Warmup AEC adaptive filter
    if warmup and len(wav_files) >= 2:
        print(f"  {_dim('Warming up AEC adaptive filter...')}")
        for _, wav_path in wav_files[:2]:
            rec_warmup = os.path.join(tmpdir, "warmup.wav")
            recorder.start(rec_warmup)
            time.sleep(0.3)
            play_aec_sink(wav_path)
            time.sleep(0.5)
            recorder.stop()
            try:
                os.remove(rec_warmup)
            except OSError:
                pass

    # Test each phrase
    results = []
    print(f"\n  {'Phrase':<55} {'RMS':>10} {'Rating':>12}")
    print(f"  {'─' * 55} {'─' * 10} {'─' * 12}")

    for phrase, wav_path in wav_files:
        rec_file = os.path.join(tmpdir, f"rec_{os.path.basename(wav_path)}")
        recorder.start(rec_file)
        time.sleep(0.5)
        play_aec_sink(wav_path)
        time.sleep(1.5)
        recorder.stop()

        rms = measure_rms(rec_file)
        rating, _ = rms_to_rating(rms)
        short = phrase[:52] + "..." if len(phrase) > 55 else phrase
        print(f"  {short:<55} {rms:>10.6f} {rating:>12}")
        results.append(rms)

    avg_rms = sum(results) / len(results) if results else 0
    rating, desc = rms_to_rating(avg_rms)
    print(f"\n  {'Average':.<55} {avg_rms:>10.6f} {rating:>12}")
    print(f"  {_dim(desc)}")
    return avg_rms


def test_latency(tmpdir, recorder):
    """Estimate AEC processing latency by measuring onset delay."""
    print(f"\n{_bold('Test 3: AEC Latency')}")
    print(f"  {_dim('Playing a sharp click and measuring delay in recording...')}")

    import numpy as np
    import wave as wave_mod

    # Generate a click (1ms impulse at 16kHz)
    click_file = os.path.join(tmpdir, "click.wav")
    sr = APP_PLAYBACK_RATE
    silence_pre = np.zeros(int(sr * 0.5), dtype=np.int16)   # 0.5s silence
    click = np.full(int(sr * 0.001), 16000, dtype=np.int16)  # 1ms click
    silence_post = np.zeros(int(sr * 1.0), dtype=np.int16)   # 1s silence
    audio = np.concatenate([silence_pre, click, silence_post])

    with wave_mod.open(click_file, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())

    rec_file = os.path.join(tmpdir, "latency_rec.wav")
    recorder.start(rec_file)
    time.sleep(0.5)

    t0 = time.perf_counter()
    play_aec_sink(click_file)
    t1 = time.perf_counter()

    time.sleep(1.0)
    recorder.stop()

    playback_time = t1 - t0
    rec_rms = measure_rms(rec_file)
    rec_peak = measure_peak(rec_file)

    print(f"  Playback duration:   {playback_time:.3f}s")
    print(f"  Recording RMS:       {rec_rms:.6f}")
    print(f"  Recording Peak:      {rec_peak:.6f}")

    if rec_peak < 0.01:
        print(f"  {_green('PASS')} — Click fully cancelled (no measurable leakage)")
    elif rec_peak < 0.05:
        print(f"  {_yellow('FAIR')} — Minor click leakage detected")
    else:
        print(f"  {_red('FAIL')} — Significant click leakage")

    return rec_rms


def test_loop(tmpdir, recorder, iterations):
    """Repeat echo bleed test to check AEC stability over time."""
    print(f"\n{_bold(f'Test: Stability ({iterations} iterations)')}")

    # Use just one phrase for speed
    phrase = TEST_PHRASES[0]
    wav_path = os.path.join(tmpdir, "loop_phrase.wav")
    if not generate_tts_wav(phrase, wav_path, tmpdir):
        print(f"  {_red('FAILED')}: Could not generate TTS")
        return

    # Warmup
    print(f"  {_dim('Warming up...')}")
    rec_warmup = os.path.join(tmpdir, "warmup.wav")
    recorder.start(rec_warmup)
    time.sleep(0.3)
    play_aec_sink(wav_path)
    time.sleep(0.5)
    recorder.stop()

    results = []
    print(f"\n  {'#':>4}  {'RMS':>10}  {'Rating':>12}  {'Trend':>8}")
    print(f"  {'─' * 4}  {'─' * 10}  {'─' * 12}  {'─' * 8}")

    for i in range(iterations):
        rec_file = os.path.join(tmpdir, f"loop_{i}.wav")
        recorder.start(rec_file)
        time.sleep(0.5)
        play_aec_sink(wav_path)
        time.sleep(1.5)
        recorder.stop()

        rms = measure_rms(rec_file)
        rating, _ = rms_to_rating(rms)
        results.append(rms)

        trend = ""
        if len(results) > 1:
            diff = rms - results[-2]
            if abs(diff) < 0.0001:
                trend = _dim("  ─")
            elif diff > 0:
                trend = _red(f" +{diff:.4f}")
            else:
                trend = _green(f" {diff:.4f}")

        print(f"  {i+1:>4}  {rms:>10.6f}  {rating:>12}  {trend}")

        try:
            os.remove(rec_file)
        except OSError:
            pass

    avg = sum(results) / len(results)
    mn, mx = min(results), max(results)
    spread = mx - mn
    rating, desc = rms_to_rating(avg)

    print(f"\n  Average: {avg:.6f}  Min: {mn:.6f}  Max: {mx:.6f}  Spread: {spread:.6f}")
    print(f"  Overall: {rating} — {desc}")

    if spread > avg * 0.5 and avg > 0.001:
        print(f"  {_yellow('NOTE')}: High variance — AEC may be unstable with current settings")


def _find_raw_devices():
    """Find the raw (non-AEC) USB playback sink and capture source via pw-cli.
    Skips HDMI and echo_cancel devices to find the actual hardware."""
    raw_sink = None
    raw_source = None
    r = run_cmd("pw-cli list-objects", timeout=10, as_user=True)
    if r.returncode != 0:
        return None, None

    current_name = None
    current_class = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if "node.name" in line and "echo_cancel" not in line:
            val = line.split("=")[-1].strip().strip('"')
            current_name = val
        if "media.class" in line:
            val = line.split("=")[-1].strip().strip('"')
            current_class = val
            if current_name:
                name_lower = current_name.lower()
                # Skip HDMI, built-in, and non-ALSA devices
                skip = "hdmi" in name_lower or "echo_cancel" in name_lower
                if not skip and "alsa" in name_lower:
                    if current_class == "Audio/Sink" and not raw_sink:
                        raw_sink = current_name
                    elif current_class == "Audio/Source" and not raw_source:
                        raw_source = current_name
            current_name = None
            current_class = None

    return raw_sink, raw_source


def test_compare(tmpdir):
    """Compare echo bleed with AEC vs without AEC (raw devices)."""
    print(f"\n{_bold(_cyan('AEC vs RAW COMPARISON'))}")
    print(f"{_dim('─' * 60)}")

    # Find the real ALSA USB devices (not HDMI, not echo_cancel)
    raw_sink, raw_source = _find_raw_devices()
    if not raw_sink or not raw_source:
        print(f"  {_red('FAILED')}: Could not find raw ALSA audio devices")
        return
    print(f"  {_dim(f'Raw sink:   {raw_sink}')}")
    print(f"  {_dim(f'Raw source: {raw_source}')}")
    print(f"  {_dim('AEC path: speaker -> echo_cancel_sink, mic <- echo_cancel_source')}")

    # Generate one test phrase
    phrase = TEST_PHRASES[3]  # longer phrase for better measurement
    wav_path = os.path.join(tmpdir, "compare_phrase.wav")
    print(f"  {_dim(f'Generating TTS: {phrase[:50]}...')}")
    if not generate_tts_wav(phrase, wav_path, tmpdir):
        print(f"  {_red('FAILED')}: Could not generate TTS")
        return

    # Warmup AEC
    print(f"  {_dim('Warming up AEC...')}")
    aec_rec = Recorder("echo_cancel_source")
    warmup_file = os.path.join(tmpdir, "warmup_cmp.wav")
    aec_rec.start(warmup_file)
    time.sleep(0.3)
    play_aec_sink(wav_path)
    time.sleep(0.5)
    aec_rec.stop()

    # Test WITH AEC
    print(f"\n  {_bold('With AEC:')}")
    aec_results = []
    for i in range(3):
        rec_file = os.path.join(tmpdir, f"aec_{i}.wav")
        aec_rec.start(rec_file)
        time.sleep(0.5)
        play_aec_sink(wav_path)
        time.sleep(1.5)
        aec_rec.stop()
        rms = measure_rms(rec_file)
        rating, _ = rms_to_rating(rms)
        print(f"    Run {i+1}: RMS={rms:.6f}  {rating}")
        aec_results.append(rms)

    # Test WITHOUT AEC — play to raw sink, record from raw source
    print(f"\n  {_bold('Without AEC (raw):')}")
    raw_rec = Recorder(raw_source)
    raw_results = []
    for i in range(3):
        rec_file = os.path.join(tmpdir, f"raw_{i}.wav")
        raw_rec.start(rec_file)
        time.sleep(0.5)
        play_audio(wav_path, raw_sink)
        time.sleep(1.5)
        raw_rec.stop()
        rms = measure_rms(rec_file)
        print(f"    Run {i+1}: RMS={rms:.6f}")
        raw_results.append(rms)

    # Summary
    aec_avg = sum(aec_results) / len(aec_results) if aec_results else 0
    raw_avg = sum(raw_results) / len(raw_results) if raw_results else 0

    print(f"\n  {'─' * 50}")
    aec_rating, aec_desc = rms_to_rating(aec_avg)
    print(f"  AEC average:   {aec_avg:.6f}  {aec_rating}")
    print(f"  Raw average:   {raw_avg:.6f}")

    if raw_avg > 0 and aec_avg > 0:
        reduction = ((raw_avg - aec_avg) / raw_avg) * 100
        ratio = raw_avg / aec_avg if aec_avg > 0.000001 else float('inf')
        print(f"\n  Echo reduction: {_bold(f'{reduction:.1f}%')}  ({ratio:.1f}x quieter with AEC)")
        if reduction > 90:
            print(f"  {_green('EXCELLENT')} — AEC is working very effectively")
        elif reduction > 70:
            print(f"  {_green('GOOD')} — AEC provides solid echo reduction")
        elif reduction > 40:
            print(f"  {_yellow('FAIR')} — AEC helping but could be better")
        else:
            print(f"  {_red('POOR')} — AEC providing minimal benefit")
    elif raw_avg == 0:
        print(f"\n  {_yellow('NOTE')}: Raw recording returned 0 RMS — raw device may not be capturing")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TARS-AI AEC Diagnostic Tool")
    parser.add_argument("--quick", action="store_true", help="Quick single-phrase test")
    parser.add_argument("--silence", action="store_true", help="Silence floor measurement only")
    parser.add_argument("--latency", action="store_true", help="AEC latency test only")
    parser.add_argument("--loop", type=int, metavar="N", help="Repeat echo test N times (stability)")
    parser.add_argument("--compare", action="store_true", help="Compare AEC vs raw (no AEC) echo bleed")
    parser.add_argument("--force", action="store_true", help="Run tests even if pre-flight checks fail")
    args = parser.parse_args()

    passed = preflight()
    if not passed and not args.force:
        print(f"  {_dim('Use --force to run tests anyway')}")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="aec_test_")
    os.chmod(tmpdir, 0o777)  # pw-record runs as real user, needs write access
    recorder = Recorder()

    try:
        if args.compare:
            test_compare(tmpdir)
        elif args.silence:
            test_silence_floor(tmpdir, recorder)
        elif args.latency:
            test_latency(tmpdir, recorder)
        elif args.loop:
            test_loop(tmpdir, recorder, args.loop)
        elif args.quick:
            silence_rms = test_silence_floor(tmpdir, recorder)
            test_echo_bleed(tmpdir, recorder, phrases=[TEST_PHRASES[0]])
        else:
            # Full diagnostic
            silence_rms = test_silence_floor(tmpdir, recorder)
            avg_rms = test_echo_bleed(tmpdir, recorder)
            test_latency(tmpdir, recorder)
            test_compare(tmpdir)

            # Summary
            print(f"\n{_bold(_cyan('SUMMARY'))}")
            print(f"{_dim('─' * 60)}")
            if silence_rms is not None:
                print(f"  Silence floor:  {silence_rms:.6f}")
            if avg_rms is not None:
                rating, desc = rms_to_rating(avg_rms)
                print(f"  Echo bleed:     {avg_rms:.6f}  {rating}")
                print(f"  {_dim(desc)}")
            print()
    except KeyboardInterrupt:
        print(f"\n  {_dim('Interrupted.')}")
        recorder.stop()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
