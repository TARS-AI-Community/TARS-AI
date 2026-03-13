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

    # --- Three-tier threshold model ---
    # LOW: Unknown embeddings must be this similar to count as "same person"
    CONSISTENCY_THRESHOLD = 0.55
    # MID: Minimum score for soft-match (near-miss strengthening, cross-contam check, auto-merge)
    SOFT_MATCH_THRESHOLD = 0.65
    # HIGH: Positive identification threshold (overridden by config speaker_id_threshold)
    DEFAULT_THRESHOLD = 0.75

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

        # Last extracted embedding — used by name_current_speaker for direct enrollment
        self._last_embedding: Optional[list] = None

        # Pending name: set when the LLM calls identify_speaker_name before
        # auto-enrollment has fired.  _auto_enroll checks this and uses it
        # as the profile name instead of Unknown_*.
        self._pending_name: Optional[str] = None

        # Voice memory file path and in-memory cache
        self._memory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory", "voice_memory.json"
        )
        self._voice_data: dict = {"speakers": []}  # In-memory cache of voice_memory.json
        self._file_lock = threading.Lock()          # Protects voice_memory.json reads/writes

        # Passive observer queue
        self._audio_queue = collections.deque()
        self._queue_lock = threading.Lock()
        self._observer_thread = None
        self._running = False

        # Event set when the observer finishes processing the most-recently
        # submitted audio item. Lets the ROUND log wait for the result.
        self._identification_done = threading.Event()
        self._identification_done.set()  # initially "done" (nothing pending)

        if self.enabled:
            os.makedirs(os.path.dirname(self._memory_path), exist_ok=True)
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

    def _save_voice_data(self):
        """Atomically write voice data cache to disk. Must be called under _file_lock."""
        # Keep a backup of the last good state before overwriting
        bak_path = self._memory_path + '.bak'
        if os.path.exists(self._memory_path) and os.path.getsize(self._memory_path) > 2:
            try:
                import shutil
                shutil.copy2(self._memory_path, bak_path)
            except Exception:
                pass
        tmp_path = self._memory_path + '.tmp'
        with open(tmp_path, 'w') as f:
            json.dump(self._voice_data, f, indent=2)
        os.replace(tmp_path, self._memory_path)  # atomic on POSIX

    def _load_voice_memory(self):
        """Load enrolled speaker embeddings from JSON file into the manager and cache."""
        # Try primary file first, fall back to .bak if corrupt/empty
        for path in [self._memory_path, self._memory_path + '.bak']:
            if not os.path.exists(path) or os.path.getsize(path) < 2:
                continue
            try:
                with self._file_lock:
                    with open(path, 'r') as f:
                        self._voice_data = json.load(f)

                for speaker in self._voice_data.get("speakers", []):
                    name = speaker["name"]
                    embeddings = speaker.get("embeddings", [])
                    if embeddings:
                        self._manager.add(name, embeddings)
                        queue_message(f"INFO: Speaker ID restored '{name}' ({len(embeddings)} vectors)")

                if path != self._memory_path:
                    queue_message(f"WARNING: Loaded voice memory from backup ({path})")
                return

            except Exception as e:
                queue_message(f"WARNING: Failed to load voice memory from {path}: {e}")

        queue_message("INFO: No voice memory found — starting fresh")

    def _add_speaker_to_memory(self, name: str, embeddings, role: str = "guest"):
        """Add embedding(s) for a speaker to voice memory cache, disk, and manager.

        Args:
            name: Speaker name.
            embeddings: A single embedding (list of floats) or a list of embeddings.
            role: Speaker role ("admin", "guest", "unknown").
        """
        # Normalize: accept single embedding or list of embeddings
        if embeddings and not isinstance(embeddings[0], list):
            embeddings = [embeddings]

        with self._file_lock:
            # Find or create speaker entry in cache
            speaker_entry = None
            for s in self._voice_data.get("speakers", []):
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
                self._voice_data.setdefault("speakers", []).append(speaker_entry)

            # Deduplicate: skip embeddings that are near-identical to existing ones
            # (cosine sim > 0.99 means essentially the same voice sample)
            existing = speaker_entry["embeddings"]
            for emb in embeddings:
                is_dup = False
                for ex in existing:
                    if self._cosine_similarity(emb, ex) > 0.99:
                        is_dup = True
                        break
                if not is_dup:
                    existing.append(emb)
            speaker_entry["last_seen"] = time.time()

            # Keep at most 10 embeddings per speaker (most recent)
            if len(speaker_entry["embeddings"]) > 10:
                speaker_entry["embeddings"] = speaker_entry["embeddings"][-10:]

            # Snapshot ALL embeddings for the sherpa manager update (must be
            # done under lock since we read from the live voice_data dict).
            all_embeddings = list(speaker_entry["embeddings"])

            # Write cache to disk (atomic)
            try:
                self._save_voice_data()
            except Exception as e:
                queue_message(f"WARNING: Failed to save voice memory: {e}")

        # Update the in-memory sherpa manager.  sherpa's add() replaces the
        # speaker's representative vector with the average of the provided
        # embeddings, so we must pass ALL stored embeddings — not just the
        # new ones — to keep the manager in sync with the JSON file.
        try:
            self._manager.remove(name)
        except Exception:
            pass
        self._manager.add(name, all_embeddings)

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
        """Compute speaker match score using top-2 average cosine similarity.

        Using the average of the top 2 scores (instead of just the max) prevents
        a single outlier embedding from inflating the score.  With only 1 stored
        embedding, returns the single score.
        """
        try:
            with self._file_lock:
                # Deep-copy the embeddings we need so we don't hold the lock during cosine math
                stored_embeddings = None
                for speaker in self._voice_data.get("speakers", []):
                    if speaker["name"] == speaker_name:
                        stored_embeddings = list(speaker.get("embeddings", []))
                        break
            if stored_embeddings:
                scores = sorted(
                    [self._cosine_similarity(embedding, stored) for stored in stored_embeddings],
                    reverse=True
                )
                # Top-2 average (or single score if only 1 embedding)
                top_n = min(2, len(scores))
                return sum(scores[:top_n]) / top_n
        except Exception:
            pass
        return 0.0

    def identify_speaker(self, embedding: list, skip_margin: bool = False) -> tuple:
        """Identify speaker from embedding using cosine similarity.

        Uses sherpa-onnx manager for initial candidate search, then validates
        with our own cosine similarity check against stored embeddings.

        Args:
            embedding: Voice embedding vector to identify.
            skip_margin: If True, skip the margin-vs-runner-up ambiguity check.
                Useful for barge-in where we only need "is this any known speaker?"
                rather than precise identification between similar speakers.

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
            if not name:
                return ("", 0.0)

            # Validate: compute our own best cosine similarity score
            score = self._compute_best_score(embedding, name)

            # Also compute scores against ALL other speakers for comparison
            # A match is only reliable if the best score is significantly
            # above the runner-up (margin check)
            runner_up_score = 0.0
            with self._file_lock:
                for speaker in self._voice_data.get("speakers", []):
                    if speaker["name"] != name:
                        other_embs = speaker.get("embeddings", [])
                        if other_embs:
                            other_best = max(
                                self._cosine_similarity(embedding, stored)
                                for stored in other_embs
                            )
                            runner_up_score = max(runner_up_score, other_best)

            margin = score - runner_up_score

            # Simple check: is this voice known or not?
            if score < threshold:
                queue_message(f"INFO: Speaker ID rejected '{name}' — score {score:.3f} below threshold {threshold}")
                return ("", 0.0)

            # If margin between best and runner-up is too small, it's ambiguous
            # Skip this check for barge-in — we just need "any known speaker"
            MIN_MARGIN = 0.05
            if not skip_margin and runner_up_score > 0 and margin < MIN_MARGIN:
                queue_message(f"INFO: Speaker ID ambiguous — '{name}' score {score:.3f} vs runner-up {runner_up_score:.3f} (margin {margin:.3f})")
                return ("", 0.0)

            queue_message(f"INFO: Speaker ID: '{name}' score={score:.3f} (runner-up={runner_up_score:.3f}, margin={margin:.3f})")
            return (name, score)

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

        Immediately replaces the stale speaker from the previous round with
        a pending Unknown tag so that the ROUND log for THIS utterance
        always has a speaker identity — either a known name once identification
        completes, or the Unknown tag if it doesn't match anyone.
        """
        if not self.enabled or not self._running:
            return
        # Replace stale speaker state with a fresh Unknown tag.  The background
        # observer will overwrite this with the real identification result.
        # If identification fails or times out, the Unknown tag remains —
        # the ROUND log never shows "?" for an active utterance.
        with self._lock:
            # Always create a fresh Unknown tag for each new utterance.
            # The old session ID may belong to a different person; the observer
            # thread will overwrite this with the real result once identification
            # completes.  If the same unknown person speaks again, _handle_unknown
            # will match them via embedding consistency and reuse their profile.
            self._unknown_session_id = f"Unknown_{int(time.time())}"
            self.current_speaker = self._unknown_session_id
            self.current_confidence = 0.0
            self.last_identified_time = time.time()
            self._identification_done.clear()
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

    def wait_for_identification(self, timeout: float = 2.0) -> bool:
        """Block until the background observer finishes identifying the current utterance.

        Returns True if identification completed within timeout, False if it timed out.
        Call this just before reading current_speaker in the ROUND log so the result
        is always for the current utterance, not the previous one.
        """
        return self._identification_done.wait(timeout=timeout)

    def _process_utterance(self, audio_float32: np.ndarray, sample_rate: int):
        """Extract embedding, identify speaker, handle enrollment."""
        try:
            embedding = self.extract_embedding(audio_float32, sample_rate)
            if embedding is None:
                return

            # Cache the latest embedding for direct enrollment via identify_speaker_name
            with self._lock:
                self._last_embedding = embedding

            # Try to identify
            name, confidence = self.identify_speaker(embedding)

            if name:
                is_unknown_profile = name.startswith("Unknown_")

                if is_unknown_profile:
                    # Re-matched an enrolled unknown — keep their session ID so
                    # identify_speaker_name can rename the right profile later
                    with self._lock:
                        self.current_speaker = name
                        self.current_confidence = confidence
                        self.last_identified_time = time.time()
                        self._unknown_session_id = name
                        self._pending_name_request = True
                        self._unknown_embeddings.clear()
                        self._unknown_count = 0
                    # Strengthen their profile with this new embedding
                    self._add_speaker_to_memory(name, embedding)
                else:
                    # Known named speaker — update state and rename any pending unknown memories
                    old_tag = None
                    with self._lock:
                        old_tag = self._unknown_session_id
                        self.current_speaker = name
                        self.current_confidence = confidence
                        self.last_identified_time = time.time()
                        self._unknown_embeddings.clear()
                        self._unknown_count = 0
                        self._unknown_session_id = None

                    # Retroactively rename memories from the unknown session
                    if old_tag:
                        self._rename_speaker_in_memories(old_tag, name)

                    # Add this embedding to strengthen their profile
                    self._add_speaker_to_memory(name, embedding)

            else:
                # No positive match — treat as unknown speaker
                # (near-miss strengthening disabled to prevent profile poisoning from marginal matches)
                self._handle_unknown(embedding)

        except Exception as e:
            queue_message(f"ERROR: Speaker ID _process_utterance failed: {e}")
        finally:
            # Always signal completion so ROUND log never blocks indefinitely
            self._identification_done.set()

    # Near-miss uses the mid-tier threshold
    NEAR_MISS_THRESHOLD = SOFT_MATCH_THRESHOLD

    def _find_near_miss(self, embedding: list):
        """Check if embedding nearly matches an existing NAMED speaker.

        Returns (name, score) if a named (non-Unknown) speaker scores between
        NEAR_MISS_THRESHOLD and the identification threshold. Returns None if
        no near-miss found or if the best match is an Unknown_* profile.
        """
        threshold = float(self.config.get("STT", {}).get(
            "speaker_id_threshold", self.DEFAULT_THRESHOLD
        ))

        best_name = None
        best_score = 0.0
        # Use _compute_best_score (top-2 avg) — same method as identify_speaker —
        # so there's no gap where identify_speaker rejects but near-miss also misses.
        for speaker_name in self.get_enrolled_speakers():
            if speaker_name.startswith("Unknown_"):
                continue  # Only consider named speakers
            score = self._compute_best_score(embedding, speaker_name)
            if score > best_score:
                best_score = score
                best_name = speaker_name

        if best_name and self.NEAR_MISS_THRESHOLD <= best_score < threshold:
            return (best_name, best_score)
        return None

    # Unknown consistency uses the low-tier threshold
    UNKNOWN_CONSISTENCY_THRESH = CONSISTENCY_THRESHOLD

    def _handle_unknown(self, embedding: list):
        """Handle an unrecognized voice embedding.

        Sets current_speaker to a unique Unknown tag so memories get tagged.
        Collects unknown samples and triggers enrollment after reaching
        the threshold count. If a new unknown voice doesn't match the
        buffered samples, resets the buffer (different person).
        """
        should_enroll = False
        with self._lock:
            # Check if this embedding is consistent with buffered unknowns
            # (i.e., same person). If not, reset — different unknown speaker.
            if self._unknown_embeddings:
                avg_sim = np.mean([
                    self._cosine_similarity(embedding, prev)
                    for prev in self._unknown_embeddings
                ])
                if avg_sim < self.UNKNOWN_CONSISTENCY_THRESH:
                    queue_message(f"INFO: Unknown voice changed (sim={avg_sim:.2f}), resetting buffer")
                    self._unknown_embeddings.clear()
                    self._unknown_count = 0
                    self._unknown_session_id = None

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

    # Maximum number of stale Unknown_* profiles before cleanup
    MAX_UNKNOWN_PROFILES = 5

    # Auto-merge uses the mid-tier threshold
    AUTO_MERGE_THRESHOLD = SOFT_MATCH_THRESHOLD

    def _auto_enroll(self):
        """Auto-enroll an unknown speaker after consistent voice samples.

        Before creating a new Unknown profile, checks if the collected
        embeddings match an existing NAMED speaker above AUTO_MERGE_THRESHOLD.
        If so, merges the embeddings into that speaker's profile instead of
        creating a competing Unknown — this strengthens weak initial
        enrollments over time.

        Otherwise, enrolls under a unique session ID (e.g. "Unknown_1709640000")
        so that multiple unknown speakers stay separate.
        """
        # Snapshot and clear buffer under lock
        with self._lock:
            if not self._unknown_embeddings:
                return
            embeddings_to_enroll = list(self._unknown_embeddings)
            pending = self._pending_name
            session_name = self._unknown_session_id or f"Unknown_{int(time.time())}"
            self._unknown_embeddings.clear()
            self._unknown_count = 0
            self._pending_name = None

        # If the LLM already told us the name, use it directly
        if pending:
            queue_message(f"INFO: Auto-enrolling as '{pending}' (pending name from LLM)")
            role = "admin" if not self.get_enrolled_speakers() else "guest"
            self._add_speaker_to_memory(pending, embeddings_to_enroll, role=role)
            with self._lock:
                old_tag = self._unknown_session_id
                self.current_speaker = pending
                self.current_confidence = 0.9
                self.last_identified_time = time.time()
                self._unknown_session_id = None
                self._pending_name_request = False
            if old_tag:
                self._rename_speaker_in_memories(old_tag, pending)
            return

        # CHECK: do these embeddings match an existing NAMED speaker?
        # Use the average of all collected embeddings as the representative vector.
        avg_embedding = np.mean(embeddings_to_enroll, axis=0).tolist()
        best_named = None
        best_named_score = 0.0
        with self._file_lock:
            for speaker in self._voice_data.get("speakers", []):
                sp_name = speaker["name"]
                if sp_name.startswith("Unknown_"):
                    continue
                sp_embs = speaker.get("embeddings", [])
                if not sp_embs:
                    continue
                score = max(
                    self._cosine_similarity(avg_embedding, stored)
                    for stored in sp_embs
                )
                if score > best_named_score:
                    best_named_score = score
                    best_named = sp_name

        if best_named and best_named_score >= self.AUTO_MERGE_THRESHOLD:
            # Merge into the existing named speaker — don't create a new Unknown
            queue_message(
                f"INFO: Auto-enroll merging into '{best_named}' "
                f"(score={best_named_score:.3f}) instead of creating '{session_name}'"
            )
            self._add_speaker_to_memory(best_named, embeddings_to_enroll)

            with self._lock:
                old_tag = self._unknown_session_id
                self.current_speaker = best_named
                self.current_confidence = best_named_score
                self.last_identified_time = time.time()
                self._unknown_session_id = None
                self._pending_name_request = False

            # Retroactively rename any memories tagged with the Unknown session
            if old_tag:
                self._rename_speaker_in_memories(old_tag, best_named)
            return

        # No match — enroll as a new Unknown profile
        queue_message(f"INFO: Auto-enrolling new voice as '{session_name}' (will ask for name)")

        # Enroll all collected embeddings in one batch (single disk write)
        self._add_speaker_to_memory(session_name, embeddings_to_enroll, role="unknown")

        # Update current state — keep _unknown_session_id so identify_speaker_name
        # knows which profile to rename
        with self._lock:
            self.current_speaker = session_name
            self.current_confidence = 0.7
            self.last_identified_time = time.time()
            self._pending_name_request = True

        # Clean up stale Unknown_* profiles to prevent unbounded growth
        self._cleanup_stale_unknowns()

    # === Memory Renaming ===

    def _cleanup_stale_unknowns(self):
        """Remove oldest Unknown_* profiles from voice memory if too many accumulate."""
        remove_names = set()
        try:
            with self._file_lock:
                unknowns = [s for s in self._voice_data.get("speakers", []) if s["name"].startswith("Unknown_")]
                if len(unknowns) <= self.MAX_UNKNOWN_PROFILES:
                    return

                # Sort by created time, keep the newest MAX_UNKNOWN_PROFILES
                unknowns.sort(key=lambda s: s.get("created", 0))
                to_remove = unknowns[:-self.MAX_UNKNOWN_PROFILES]
                remove_names = {s["name"] for s in to_remove}

                self._voice_data["speakers"] = [s for s in self._voice_data["speakers"] if s["name"] not in remove_names]
                self._save_voice_data()

            # Also remove from in-memory manager (outside file lock)
            for name in remove_names:
                try:
                    self._manager.remove(name)
                except Exception:
                    pass

            if remove_names:
                queue_message(f"INFO: Cleaned up {len(remove_names)} stale Unknown profiles")

        except Exception as e:
            queue_message(f"WARNING: Failed to clean up unknown profiles: {e}")

    def _rename_speaker_in_memories(self, old_name: str, new_name: str):
        """Retroactively rename speaker tags in memory documents.

        Updates both HyperDB (full memory) and lite memory JSON files.
        Called automatically when an unknown speaker is identified.
        """
        count = 0
        try:
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

        # Update voice memory cache + disk
        merged_embeddings = []
        with self._file_lock:
            old_entry = None
            existing_entry = None
            for speaker in self._voice_data.get("speakers", []):
                if speaker["name"] == old_name:
                    old_entry = speaker
                elif speaker["name"] == new_name:
                    existing_entry = speaker

            if old_entry is None:
                queue_message(f"WARNING: Speaker '{old_name}' not found in voice memory")
                return False

            old_embeddings = old_entry.get("embeddings", [])

            if existing_entry is not None:
                # Target name already exists — merge embeddings into existing profile
                existing_entry["embeddings"].extend(old_embeddings)
                if len(existing_entry["embeddings"]) > 10:
                    existing_entry["embeddings"] = existing_entry["embeddings"][-10:]
                existing_entry["last_seen"] = time.time()
                merged_embeddings = existing_entry["embeddings"]
                # Remove the old entry
                self._voice_data["speakers"] = [s for s in self._voice_data["speakers"] if s["name"] != old_name]
            else:
                # Simple rename — no collision
                old_entry["name"] = new_name
                old_entry["last_seen"] = time.time()
                if old_entry.get("role") == "unknown":
                    old_entry["role"] = "guest"
                merged_embeddings = old_embeddings

            try:
                self._save_voice_data()
            except Exception as e:
                queue_message(f"WARNING: Failed to save voice memory: {e}")
                return False

        # Update sherpa-onnx manager: remove old, re-add with new name
        try:
            self._manager.remove(old_name)
            if merged_embeddings:
                # Re-add under new name (replaces existing if already present)
                try:
                    self._manager.remove(new_name)
                except Exception:
                    pass
                self._manager.add(new_name, merged_embeddings)
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
                "Do NOT guess their name from conversation history or memory — this could be a completely different person. "
                "Naturally ask them who they are. Only call identify_speaker_name when they EXPLICITLY state their name in THIS message."
            )
        return f"Current speaker identified as: {speaker}"

    def name_current_speaker(self, name: str) -> str:
        """Single entry point for all speaker-naming decisions.

        Called by the LLM handler when identify_speaker_name fires.
        Handles four scenarios:
          1. Speaker already identified as this name → no-op
          2. Speaker is a known DIFFERENT person → tag only (no profile change)
          3. Speaker is unknown but voice matches another profile → tag only (cross-contam guard)
          4. Speaker is unknown → set pending name for auto-enroll, or rename/enroll now

        Returns a human-readable status message for logging.
        """
        with self._lock:
            current = self.current_speaker
            last_emb = self._last_embedding
            old_session = self._unknown_session_id

        is_unknown = not current or current == "Unknown" or current.startswith("Unknown_")

        # --- Case 1: Already this name ---
        if current == name:
            return f"Speaker already identified as '{name}'"

        # --- Case 2: Known different person (not Unknown) ---
        # If the voice matches the current speaker's profile, this is likely
        # a name correction (e.g. STT heard "Bra" but they said "Brian").
        # Safe to rename since voice ID already confirmed the speaker.
        if not is_unknown and current:
            if last_emb:
                score = self._compute_best_score(last_emb, current)
                if score >= self.SOFT_MATCH_THRESHOLD:
                    # Voice matches current profile — treat as a rename
                    renamed = self.rename_speaker(current, name)
                    if renamed:
                        return f"Renamed speaker '{current}' to '{name}' (voice confirmed, score={score:.3f})"
            return (
                f"Ignored — current speaker is '{current}', "
                f"not enrolling '{name}' from their voice"
            )

        # --- Case 3: Cross-contamination check ---
        if last_emb:
            best_other_name = None
            best_other_score = 0.0
            for existing in self.get_enrolled_speakers():
                if existing == name or existing.startswith("Unknown_"):
                    continue
                s = self._compute_best_score(last_emb, existing)
                if s > best_other_score:
                    best_other_score = s
                    best_other_name = existing

            if best_other_name and best_other_score >= self.SOFT_MATCH_THRESHOLD:
                with self._lock:
                    self.current_speaker = name
                    self.last_identified_time = time.time()
                return (
                    f"Tagged as '{name}' (voice matches '{best_other_name}' at "
                    f"{best_other_score:.3f} — profile NOT updated to prevent cross-contamination)"
                )

        # --- Case 4: Unknown speaker → name them ---
        already_enrolled = name in self.get_enrolled_speakers()

        if already_enrolled:
            # Name exists in voice memory. Tag as this person, and soft-update
            # their profile if embedding is close enough.
            with self._lock:
                self.current_speaker = name
                self.last_identified_time = time.time()

            # Clean up the old Unknown_* profile — it's now identified
            if old_session and old_session.startswith("Unknown_"):
                self.remove_speaker(old_session)
                queue_message(f"INFO: Removed stale profile '{old_session}' (now identified as '{name}')")
                with self._lock:
                    self._unknown_embeddings.clear()
                    self._unknown_count = 0
                    self._unknown_session_id = None

            if last_emb:
                score = self._compute_best_score(last_emb, name)
                if score >= self.SOFT_MATCH_THRESHOLD:
                    self._add_speaker_to_memory(name, last_emb)
                    return f"Tagged as '{name}' (soft-updated profile, score={score:.3f})"
                else:
                    return f"Tagged as '{name}' (voice too different, score={score:.3f} — profile NOT updated)"
            return f"Tagged as '{name}' (no embedding — profile NOT updated)"

        # New name for an unknown speaker
        # Try to rename the existing Unknown_* profile first
        if old_session and old_session.startswith("Unknown_"):
            renamed = self.rename_speaker(old_session, name)
            if renamed:
                with self._lock:
                    self._pending_name = None
                    self._pending_name_request = False
                return f"Speaker identified as '{name}' (was '{old_session}')"

        # Unknown_* not yet auto-enrolled (< 3 samples).
        # Store the name as pending — _auto_enroll will use it when it fires.
        with self._lock:
            self._pending_name = name
            self.current_speaker = name
            self.last_identified_time = time.time()

        # Also try immediate enrollment from buffered embeddings + last_embedding
        with self._lock:
            embedding = self._last_embedding
            extra = list(self._unknown_embeddings) if self._unknown_embeddings else []

        if embedding is not None:
            all_embeddings = extra + [embedding] if extra else [embedding]
            role = "admin" if not self.get_enrolled_speakers() else "guest"
            self._add_speaker_to_memory(name, all_embeddings, role=role)
            with self._lock:
                self.current_speaker = name
                self.current_confidence = 1.0
                self.last_identified_time = time.time()
                self._unknown_embeddings.clear()
                self._unknown_count = 0
                self._unknown_session_id = None
                self._pending_name = None
                self._pending_name_request = False
            # Retroactively rename memories from the Unknown session
            if old_session:
                self._rename_speaker_in_memories(old_session, name)
            return f"Enrolled speaker '{name}' from voice ({len(all_embeddings)} vectors)"

        # No embedding at all — just set pending name for later
        return f"Name '{name}' stored as pending (will apply on next auto-enroll)"

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

            # Also remove from cache + disk
            with self._file_lock:
                self._voice_data["speakers"] = [s for s in self._voice_data.get("speakers", []) if s["name"] != name]
                self._save_voice_data()

            queue_message(f"INFO: Removed speaker '{name}'")
            return result

        except Exception as e:
            queue_message(f"WARNING: Failed to remove speaker '{name}': {e}")
            return False
