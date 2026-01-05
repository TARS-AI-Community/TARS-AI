"""
Atomik Wake Word Detection System
Author: Olivier Dion (@atomikspace)
Email: olivierdion1@hotmail.com
License: All Rights Reserved
"""

import numpy as np
import sounddevice as sd
from collections import deque
import pickle
import os
import time
import sys
from scipy.fftpack import dct

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

class WakeWordSystem:
    def __init__(self, wake_word="hey tars", sample_rate=16000, threshold=0.6, augment_data=True):
        self.wake_word = wake_word
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.augment_data = augment_data
        self.mfcc_extractor = MFCCExtractor(sample_rate=sample_rate)
        self.vad = VoiceActivityDetector(sample_rate=sample_rate)
        self.buffer = deque(maxlen=sample_rate * 3)
        self.templates = []
        self.last_detection_time = 0
        self.cooldown = 1.5
        self.last_check_time = 0
        self.check_interval = 0.1

    def createModel(self, num_templates=5):
        if self.load_templates():
            #print(f"Loaded Atomik model for '{self.wake_word}'")
            return True

        print("=" * 60)
        print(f"SETUP: Record '{self.wake_word}' {num_templates} times")
        print("=" * 60)
        print()
        print("HOW IT WORKS:")
        print("- The system will listen for you to start speaking")
        print("- Say your wake word clearly")
        print("- It automatically stops recording when you finish")
        print("- Augments each recording (speed/pitch variations)")
        print("- To start over, delete the hey_tars_templates.pkl file in ~/.local/share/tars_ai")
        print()
        print("TIPS FOR BEST RESULTS:")
        print("- Speak naturally at normal volume")
        print("- Say the phrase the same way you'll use it")
        print("- Record in the same environment you'll use it")
        print("- Keep background noise consistent")
        print("- Vary slightly between recordings (speed/tone)")
        print()
        print("Press ENTER when ready to start recording...")
        input()
        print()

        for i in range(num_templates):
            print(f"\nRecording {i+1}/{num_templates}")
            success = self.record_template()
            if not success:
                print("Retrying...")
                self.record_template()
            time.sleep(1)

        self.save_templates()
        print(f"\nTraining complete. Created {len(self.templates)} templates.")
        return True

    def listenForWakeWord(self):
        #print(f"Say '{self.wake_word.upper()}' to trigger detection")        
        detected_flag = False

        def audio_callback(indata, frames, time_info, status):
            nonlocal detected_flag
            audio_np = indata[:, 0]
            self.buffer.extend(audio_np)

            detected, confidence = self.detect()
            if detected:
                #print(f"\nWake word detected! Confidence: {confidence:.2f}")
                detected_flag = True

        with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=audio_callback, blocksize=512):
            while not detected_flag:
                time.sleep(0.05)
        return True

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
        augmented = [audio,
                     self.time_stretch(audio, 0.9),
                     self.time_stretch(audio, 1.1),
                     self.pitch_shift(audio, -2),
                     self.pitch_shift(audio, 2),
                     self.add_noise(audio, 0.003)]
        return augmented

    def record_template(self):
        for i in range(3, 0, -1):
            print(f"   {i}...")
            time.sleep(1)

        print(f"\n   Listening... SAY '{self.wake_word.upper()}' now!")

        recording = []
        speech_started = False
        silence_count = 0
        max_silence_frames = 15

        def callback(indata, frames, time_info, status):
            nonlocal speech_started, silence_count
            audio_chunk = indata[:, 0]

            if not speech_started:
                if self.vad.is_speech(audio_chunk):
                    speech_started = True
                    print("   Recording...", end="", flush=True)
                    recording.extend(audio_chunk)
            else:
                recording.extend(audio_chunk)
                if self.vad.is_speech(audio_chunk):
                    silence_count = 0
                    print("█", end="", flush=True)
                else:
                    silence_count += 1
                    print(".", end="", flush=True)

        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                            callback=callback, blocksize=512):
            while not speech_started or silence_count < max_silence_frames:
                time.sleep(0.01)

        audio_array = np.array(recording, dtype=np.float32)
        audio_array = self.vad.trim_silence(audio_array)

        duration = len(audio_array) / self.sample_rate
        energy = np.sqrt(np.mean(audio_array ** 2))

        print(f"   Duration: {duration:.1f}s, Audio level: {energy:.4f}")

        if duration < 0.3:
            print("   Too short! Try again and speak the full phrase.")
            return False

        if duration > 3.0:
            print("   Too long! Keep it under 3 seconds.")
            return False

        if energy < 0.005:
            print("   Audio too quiet! Increase mic volume or speak louder.")
            return False

        mfcc = self.mfcc_extractor.extract_mfcc(audio_array)
        if mfcc is None:
            print("   Failed to extract features")
            return False

        self.templates.append(mfcc)
        templates_added = 1

        if self.augment_data:
            augmented_audios = self.augment_audio(audio_array)
            for aug_audio in augmented_audios[1:]:  
                aug_mfcc = self.mfcc_extractor.extract_mfcc(aug_audio)
                if aug_mfcc is not None:
                    self.templates.append(aug_mfcc)
                    templates_added += 1

            print(f"   Created {templates_added} templates (1 original + {templates_added-1} augmented)")
        else:
            print(f"   Template {len(self.templates)} recorded successfully!")

        return True

    def cosine_similarity(self, mfcc1, mfcc2):
        v1, v2 = mfcc1.flatten(), mfcc2.flatten()
        min_len = min(len(v1), len(v2))
        v1, v2 = v1[:min_len], v2[:min_len]
        dot = np.dot(v1, v2)
        norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
        return 0.0 if norm1 == 0 or norm2 == 0 else dot / (norm1 * norm2)

    def detect(self):
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
        if max_sim >= self.threshold:
            self.last_detection_time = time.time()
            return True, max_sim
        return False, max_sim

    def save_templates(self, filename=None):
        home = os.path.expanduser("~")
        data_dir = os.path.join(home, ".local", "share", "tars_ai")
        os.makedirs(data_dir, exist_ok=True)
        filename = filename or f"{self.wake_word.replace(' ', '_')}_templates.pkl"
        filepath = os.path.join(data_dir, filename)
        with open(filepath, "wb") as f:
            pickle.dump(self.templates, f)

    def load_templates(self, filename=None):
        home = os.path.expanduser("~")
        data_dir = os.path.join(home, ".local", "share", "tars_ai")
        filename = filename or f"{self.wake_word.replace(' ', '_')}_templates.pkl"
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                self.templates = pickle.load(f)
            return True
        return False
    
    def delete_templates(self, filename=None):
        home = os.path.expanduser("~")
        data_dir = os.path.join(home, ".local", "share", "tars_ai")
        filename = filename or f"{self.wake_word.replace(' ', '_')}_templates.pkl"
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
        