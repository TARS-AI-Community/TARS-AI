#!/usr/bin/env python3
"""
module_speaker_id.py

Passive Speaker Identification Module for TARS-AI.

Uses sherpa-onnx WeSpeaker embedding model to extract voice embeddings
from utterances and match them against enrolled speakers. Runs as a
background observer thread — never blocks the STT → LLM pipeline.

Speaker vectors are stored in a JSON-based Voice Memory file. Identification
uses cosine similarity with a recency-biased confidence window. Unknown
speakers are dynamically enrolled after multiple consistent samples.
"""

import os
import json
import time
import threading
import tarfile
import collections
import numpy as np
from typing import Optional
from urllib.request import urlretrieve

from modules.module_messageQue import queue_message
from modules.module_config import load_config, get_capabilities

CONFIG = load_config()
CAPABILITIES = get_capabilities()

# Conditional import — sherpa-onnx required for speaker embedding
sherpa_onnx = None
if CAPABILITIES is None or (CAPABILITIES.allowed_stt and "sherpa-onnx" in CAPABILITIES.allowed_stt):
    try:
        import sherpa_onnx as _sherpa_onnx
        sherpa_onnx = _sherpa_onnx
    except ImportError:
        pass


def _stt_dir():
    """Return the path to the stt models directory (src/stt/)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt")


# Global singleton
_speaker_id_instance = None


def get_speaker_id_manager():
    global _speaker_id_instance
    return _speaker_id_instance


class SpeakerIDManager:
    """Passive speaker identification using sherpa-onnx WeSpeaker embeddings.

    This module runs as an observer — it receives audio from STT after each
    utterance and identifies the speaker in the background without blocking
    the main STT → LLM pipeline.

    Voice Memory:
        Enrolled speakers are stored in a JSON file with their name and
        averaged embedding vectors. Two roles exist:
        - "admin": The primary user (auto-enrolled from first interactions)
        - "guest": Any additional enrolled speakers

    Soft Identification:
        Uses cosine similarity against enrolled speakers. If confidence > threshold
        within a recent time window, the speaker is assumed to be that person.
        Results are exposed via current_speaker for LLM prompt injection.

    Dynamic Enrollment:
        After collecting N consistent unknown embeddings, the system prompts
        for enrollment (or auto-enrolls as "admin" if no speakers exist yet).
    """

    # Default cosine similarity threshold for positive identification
    DEFAULT_THRESHOLD = 0.5
    # How long a speaker guess stays valid without new audio (seconds)
    RECENCY_WINDOW = 300  # 5 minutes
    # Number of consistent unknown samples before triggering enrollment
    ENROLLMENT_SAMPLE_COUNT = 3
    # Minimum audio duration (seconds) for a usable embedding
    MIN_AUDIO_DURATION = 1.0

    def __init__(self, config: dict):
        global _speaker_id_instance
        _speaker_id_instance = self

        self.config = config
        self.enabled = config.get("STT", {}).get("speaker_id_enabled", "False").lower() == "true"

        # Speaker state
        self.current_speaker: Optional[str] = None
        self.current_confidence: float = 0.0
        self.last_identified_time: float = 0.0
        self._lock = threading.Lock()

        # Embedding model
        self._extractor = None
        self._manager = None
        self._embedding_dim = 0

        # Dynamic enrollment buffer
        self._unknown_embeddings = []
        self._unknown_count = 0
        self._unknown_session_id: Optional[str] = None  # e.g. "Unknown_1709640000"
        self._pending_name_request = False  # True when TARS should ask the speaker's name

        # Voice memory file path
        self._memory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory", "voice_memory.json"
        )

        # Passive observer queue
        self._audio_queue = collections.deque()
        self._queue_lock = threading.Lock()
        self._observer_thread = None
        self._running = False

        if self.enabled:
            self._initialize()

    def _initialize(self):
        """Load the WeSpeaker embedding model and restore enrolled speakers."""
        if sherpa_onnx is None:
            queue_message("WARNING: Speaker ID requires sherpa-onnx, disabling")
            self.enabled = False
            return

        model_path = os.path.join(_stt_dir(), "wespeaker_en_voxceleb_resnet34.onnx")
        if not os.path.exists(model_path):
            if not self._download_model(model_path):
                self.enabled = False
                return

        try:
            extractor_config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=model_path,
                num_threads=2,
                provider="cpu",
            )
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(extractor_config)
            self._embedding_dim = self._extractor.dim
            self._manager = sherpa_onnx.SpeakerEmbeddingManager(self._embedding_dim)

            queue_message(f"INFO: Speaker ID loaded (dim={self._embedding_dim})")

            # Restore enrolled speakers from voice memory
            self._load_voice_memory()

        except Exception as e:
            queue_message(f"ERROR: Failed to initialize Speaker ID: {e}")
            self.enabled = False

    # === Model Download ===

    MODEL_URL = (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
        "speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx"
    )

    def _download_model(self, model_path: str) -> bool:
        """Download the WeSpeaker ONNX model if not present.

        Returns True if model is available after download, False on failure.
        """
        stt_dir = os.path.dirname(model_path)
        os.makedirs(stt_dir, exist_ok=True)

        queue_message("INFO: Downloading WeSpeaker speaker embedding model...")
        try:
            urlretrieve(self.MODEL_URL, model_path)
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            queue_message(f"INFO: WeSpeaker model downloaded ({size_mb:.1f} MB)")
            return True
        except Exception as e:
            queue_message(f"ERROR: Failed to download WeSpeaker model: {e}")
            # Clean up partial download
            if os.path.exists(model_path):
                os.remove(model_path)
            return False

    # === Voice Memory (JSON Storage) ===

    def _load_voice_memory(self):
        """Load enrolled speaker embeddings from JSON file into the manager."""
        if not os.path.exists(self._memory_path):
            return

        try:
            with open(self._memory_path, 'r') as f:
                data = json.load(f)

            for speaker in data.get("speakers", []):
                name = speaker["name"]
                embeddings = [emb for emb in speaker.get("embeddings", [])]
                if embeddings:
                    self._manager.add(name, embeddings)
                    queue_message(f"INFO: Speaker ID restored '{name}' ({len(embeddings)} vectors)")

        except Exception as e:
            queue_message(f"WARNING: Failed to load voice memory: {e}")

    def _add_speaker_to_memory(self, name: str, embedding: list, role: str = "guest"):
        """Add a new embedding for a speaker to voice memory JSON and manager."""
        os.makedirs(os.path.dirname(self._memory_path), exist_ok=True)

        # Load existing
        data = {"speakers": []}
        if os.path.exists(self._memory_path):
            try:
                with open(self._memory_path, 'r') as f:
                    data = json.load(f)
            except Exception:
                pass

        # Find or create speaker entry
        speaker_entry = None
        for s in data["speakers"]:
            if s["name"] == name:
                speaker_entry = s
                break

        if speaker_entry is None:
            speaker_entry = {
                "name": name,
                "role": role,
                "embeddings": [],
                "created": time.time(),
            }
            data["speakers"].append(speaker_entry)

        speaker_entry["embeddings"].append(embedding)
        speaker_entry["last_seen"] = time.time()

        # Keep at most 10 embeddings per speaker (most recent)
        if len(speaker_entry["embeddings"]) > 10:
            speaker_entry["embeddings"] = speaker_entry["embeddings"][-10:]

        try:
            with open(self._memory_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            queue_message(f"WARNING: Failed to save voice memory: {e}")

        # Update the in-memory manager
        self._manager.add(name, [embedding])

    def get_enrolled_speakers(self):
        """Return list of enrolled speaker names."""
        if self._manager is None:
            return []
        return list(self._manager.all_speakers)

    # === Embedding Extraction ===

    def extract_embedding(self, audio_float32: np.ndarray, sample_rate: int = 16000) -> Optional[list]:
        """Extract a speaker embedding from float32 audio data.

        Args:
            audio_float32: Audio samples as float32 array, values in [-1, 1].
            sample_rate: Sample rate of the audio (must be 16000).

        Returns:
            List of floats (embedding vector) or None if audio too short.
        """
        if self._extractor is None:
            return None

        # Check minimum duration
        duration = len(audio_float32) / sample_rate
        if duration < self.MIN_AUDIO_DURATION:
            return None

        try:
            stream = self._extractor.create_stream()
            stream.accept_waveform(sample_rate, audio_float32.flatten())
            stream.input_finished()

            if not self._extractor.is_ready(stream):
                return None

            embedding = self._extractor.compute(stream)
            return list(embedding)

        except Exception as e:
            queue_message(f"WARNING: Speaker embedding extraction failed: {e}")
            return None

    # === Soft Identification ===

    @staticmethod
    def _cosine_similarity(a, b):
        """Compute cosine similarity between two vectors."""
        a = np.array(a, dtype=np.float64)
        b = np.array(b, dtype=np.float64)
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return float(dot / norm) if norm > 0 else 0.0

    def _compute_best_score(self, embedding: list, speaker_name: str) -> float:
        """Compute the best cosine similarity between embedding and a speaker's stored embeddings."""
        try:
            if not os.path.exists(self._memory_path):
                return 0.0
            with open(self._memory_path, 'r') as f:
                data = json.load(f)
            for speaker in data.get("speakers", []):
                if speaker["name"] == speaker_name:
                    scores = [self._cosine_similarity(embedding, stored)
                              for stored in speaker.get("embeddings", [])]
                    return max(scores) if scores else 0.0
        except Exception:
            pass
        return 0.0

    def identify_speaker(self, embedding: list) -> tuple:
        """Identify speaker from embedding using cosine similarity.

        Returns:
            (speaker_name, confidence) where speaker_name is "" if no match
            exceeds the threshold.
        """
        if self._manager is None or self._manager.num_speakers == 0:
            return ("", 0.0)

        threshold = float(self.config.get("STT", {}).get(
            "speaker_id_threshold", self.DEFAULT_THRESHOLD
        ))

        try:
            name = self._manager.search(embedding, threshold)
            if name:
                score = self._compute_best_score(embedding, name)
                return (name, score)
            return ("", 0.0)

        except Exception as e:
            queue_message(f"WARNING: Speaker identification failed: {e}")
            return ("", 0.0)

    # === Passive Observer Thread ===

    def start(self):
        """Start the passive observer thread."""
        if not self.enabled:
            return
        self._running = True
        self._observer_thread = threading.Thread(
            target=self._observer_loop, name="SpeakerIDThread", daemon=True
        )
        self._observer_thread.start()
        queue_message("INFO: Speaker ID observer started")

    def stop(self):
        """Stop the passive observer thread."""
        self._running = False
        if self._observer_thread is not None:
            self._observer_thread.join(timeout=3)
            self._observer_thread = None

    def submit_audio(self, audio_float32: np.ndarray, sample_rate: int = 16000):
        """Submit audio for background speaker identification.

        Called by STT after each utterance. Non-blocking — audio is queued
        and processed by the observer thread.
        """
        if not self.enabled or not self._running:
            return
        with self._queue_lock:
            self._audio_queue.append((audio_float32, sample_rate))

    def _observer_loop(self):
        """Background loop that processes queued audio for speaker identification."""
        while self._running:
            audio_item = None
            with self._queue_lock:
                if self._audio_queue:
                    audio_item = self._audio_queue.popleft()

            if audio_item is None:
                time.sleep(0.1)
                continue

            audio_data, sample_rate = audio_item
            self._process_utterance(audio_data, sample_rate)

    def _process_utterance(self, audio_float32: np.ndarray, sample_rate: int):
        """Extract embedding, identify speaker, handle enrollment."""
        embedding = self.extract_embedding(audio_float32, sample_rate)
        if embedding is None:
            return

        # Log embedding extraction
        queue_message("INFO: Speaker embedding extracted")

        # Try to identify
        name, confidence = self.identify_speaker(embedding)

        if name:
            # Known speaker — update state and rename any pending unknown memories
            old_tag = None
            with self._lock:
                old_tag = self._unknown_session_id
                self.current_speaker = name
                self.current_confidence = confidence
                self.last_identified_time = time.time()
                self._unknown_embeddings.clear()
                self._unknown_count = 0
                self._unknown_session_id = None

            queue_message(f"INFO: Speaker identified as '{name}' (confidence: {confidence:.2f})")

            # Retroactively rename memories from the unknown session
            if old_tag:
                self._rename_speaker_in_memories(old_tag, name)

            # Add this embedding to strengthen their profile
            self._add_speaker_to_memory(name, embedding)

        else:
            # Unknown speaker
            self._handle_unknown(embedding)

    def _handle_unknown(self, embedding: list):
        """Handle an unrecognized voice embedding.

        Sets current_speaker to a unique Unknown tag so memories get tagged.
        Collects unknown samples and triggers enrollment after reaching
        the threshold count.
        """
        should_enroll = False
        with self._lock:
            self._unknown_embeddings.append(embedding)
            self._unknown_count += 1
            # Create a stable unknown session ID on first unknown sample
            if self._unknown_session_id is None:
                self._unknown_session_id = f"Unknown_{int(time.time())}"
            self.current_speaker = self._unknown_session_id
            self.current_confidence = 0.0
            self.last_identified_time = time.time()
            count = self._unknown_count
            session_id = self._unknown_session_id
            if self._unknown_count >= self.ENROLLMENT_SAMPLE_COUNT:
                should_enroll = True

        queue_message(f"INFO: Unknown speaker ({count}/{self.ENROLLMENT_SAMPLE_COUNT}) tagged as '{session_id}'")

        if should_enroll:
            self._auto_enroll()

    def _auto_enroll(self):
        """Auto-enroll an unknown speaker after consistent voice samples.

        Enrolls the voice as "Unknown" — does NOT assume a name. The LLM
        prompt will instruct TARS to ask the speaker's name. When the user
        responds, the identify_speaker_name() function call renames
        "Unknown" to the real name across voice memory and conversation logs.
        """
        if not self._unknown_embeddings:
            return

        old_tag = self._unknown_session_id
        name = "Unknown"
        role = "unknown"

        queue_message(f"INFO: Auto-enrolling new voice as '{name}' (will ask for name)")

        # Enroll all collected embeddings
        for emb in self._unknown_embeddings:
            self._add_speaker_to_memory(name, emb, role=role)

        # Update current state
        with self._lock:
            self.current_speaker = name
            self.current_confidence = 0.7
            self.last_identified_time = time.time()
            self._unknown_session_id = None
            self._pending_name_request = True

        # Retroactively rename memories tagged with the unknown session ID
        if old_tag:
            self._rename_speaker_in_memories(old_tag, name)

        # Reset enrollment buffer
        self._unknown_embeddings.clear()
        self._unknown_count = 0

    # === Memory Renaming ===

    def _rename_speaker_in_memories(self, old_name: str, new_name: str):
        """Retroactively rename speaker tags in memory documents.

        Updates both HyperDB (full memory) and lite memory JSON files.
        Called automatically when an unknown speaker is identified.
        """
        count = 0
        try:
            from modules.module_memory import MemoryManager as _FullMM
            from modules.module_stt import get_stt_manager
            # Access the live memory manager via the global instance
            stt = get_stt_manager()
            if stt is None:
                return
            # Get memory manager from module_main's globals
            import modules.module_main as _main
            mm = getattr(_main, 'memory_manager', None)
            if mm is None:
                return

            # HyperDB-based memory
            if hasattr(mm, 'hyper_db'):
                for entry in mm.hyper_db.dict():
                    doc = entry.get('document', {})
                    if doc.get('speaker') == old_name:
                        doc['speaker'] = new_name
                        count += 1
                if count > 0:
                    mm.hyper_db.save(mm.memory_db_path)

            # Lite memory (list of dicts)
            elif hasattr(mm, 'documents'):
                for doc in mm.documents:
                    if doc.get('speaker') == old_name:
                        doc['speaker'] = new_name
                        count += 1
                if count > 0:
                    mm._save_memory()

        except Exception as e:
            queue_message(f"WARNING: Failed to rename speaker in memories: {e}")

        if count > 0:
            queue_message(f"INFO: Renamed {count} memories from '{old_name}' to '{new_name}'")

    def rename_speaker(self, old_name: str, new_name: str) -> bool:
        """Manually rename a speaker across voice memory and conversation memories.

        Updates the voice_memory.json, the sherpa-onnx manager, and all
        HyperDB/lite memory documents tagged with the old name.

        Args:
            old_name: Current speaker name to rename.
            new_name: New name to assign.

        Returns:
            True if speaker was found and renamed.
        """
        if self._manager is None:
            return False

        # Update voice memory JSON
        try:
            if os.path.exists(self._memory_path):
                with open(self._memory_path, 'r') as f:
                    data = json.load(f)
                renamed = False
                for speaker in data.get("speakers", []):
                    if speaker["name"] == old_name:
                        speaker["name"] = new_name
                        renamed = True
                        break
                if not renamed:
                    queue_message(f"WARNING: Speaker '{old_name}' not found in voice memory")
                    return False
                with open(self._memory_path, 'w') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            queue_message(f"WARNING: Failed to rename in voice memory: {e}")
            return False

        # Update sherpa-onnx manager: remove old, re-add with new name
        try:
            # Get embeddings from voice memory before removing
            with open(self._memory_path, 'r') as f:
                data = json.load(f)
            embeddings = []
            for speaker in data.get("speakers", []):
                if speaker["name"] == new_name:
                    embeddings = speaker.get("embeddings", [])
                    break

            self._manager.remove(old_name)
            if embeddings:
                self._manager.add(new_name, embeddings)
        except Exception as e:
            queue_message(f"WARNING: Failed to update speaker manager: {e}")

        # Update conversation memories
        self._rename_speaker_in_memories(old_name, new_name)

        # Update current speaker if it matches
        with self._lock:
            if self.current_speaker == old_name:
                self.current_speaker = new_name

        queue_message(f"INFO: Renamed speaker '{old_name}' to '{new_name}'")
        return True

    # === Public API ===

    def get_current_speaker(self) -> Optional[str]:
        """Get the current speaker guess, respecting the recency window.

        Returns the speaker name if identified within the recency window,
        or None if no recent identification.
        """
        with self._lock:
            if self.current_speaker is None:
                return None
            elapsed = time.time() - self.last_identified_time
            if elapsed > self.RECENCY_WINDOW:
                return None
            return self.current_speaker

    def get_speaker_context(self) -> str:
        """Get a formatted string for LLM prompt injection.

        Returns empty string if no speaker identified or feature disabled.
        When the speaker is unknown, includes an instruction to ask their name.
        """
        if not self.enabled:
            return ""
        speaker = self.get_current_speaker()
        if speaker is None:
            return ""
        if speaker == "Unknown" or speaker.startswith("Unknown_"):
            return (
                "Current speaker: UNKNOWN. You do not know who is speaking. "
                "Naturally ask the speaker what their name is so you can remember them. "
                "When they tell you their name, call the identify_speaker_name function."
            )
        return f"Current speaker identified as: {speaker}"

    def enroll_speaker(self, name: str, audio_float32: np.ndarray, sample_rate: int = 16000) -> bool:
        """Manually enroll a speaker with a given name and audio sample.

        Args:
            name: Speaker name to enroll.
            audio_float32: Audio data as float32 array.
            sample_rate: Sample rate (must be 16000).

        Returns:
            True if enrollment succeeded, False otherwise.
        """
        if not self.enabled:
            return False

        embedding = self.extract_embedding(audio_float32, sample_rate)
        if embedding is None:
            queue_message(f"WARNING: Failed to extract embedding for enrollment of '{name}'")
            return False

        role = "admin" if not self.get_enrolled_speakers() else "guest"
        self._add_speaker_to_memory(name, embedding, role=role)
        queue_message(f"INFO: Manually enrolled speaker '{name}'")

        with self._lock:
            self.current_speaker = name
            self.current_confidence = 1.0
            self.last_identified_time = time.time()

        return True

    def remove_speaker(self, name: str) -> bool:
        """Remove a speaker from voice memory.

        Args:
            name: Speaker name to remove.

        Returns:
            True if speaker was found and removed.
        """
        if self._manager is None:
            return False

        try:
            result = self._manager.remove(name)

            # Also remove from JSON
            if os.path.exists(self._memory_path):
                with open(self._memory_path, 'r') as f:
                    data = json.load(f)
                data["speakers"] = [s for s in data.get("speakers", []) if s["name"] != name]
                with open(self._memory_path, 'w') as f:
                    json.dump(data, f, indent=2)

            queue_message(f"INFO: Removed speaker '{name}'")
            return result

        except Exception as e:
            queue_message(f"WARNING: Failed to remove speaker '{name}': {e}")
            return False
