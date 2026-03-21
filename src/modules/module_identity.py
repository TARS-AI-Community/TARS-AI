"""
module_identity.py

Identity Coordinator for TARS-AI.

Cross-references speaker identification (voice) and face recognition (vision)
to produce a unified identity context for the LLM prompt and memory tagging.

Voice identification determines "who is speaking" (authoritative).
Face recognition provides "who is present" (supplementary context).

Degrades gracefully: works with voice-only, face-only, or both.
"""

import threading
import time
from typing import Optional
from modules.module_messageQue import queue_message

# Global singleton
_identity_instance = None


def get_identity_manager():
    global _identity_instance
    return _identity_instance


class IdentityManager:
    """Fuses speaker ID (voice) and face recognition (vision) into unified identity."""

    def __init__(self, speaker_id_manager=None, ui_manager=None):
        global _identity_instance
        _identity_instance = self

        self._speaker_id = speaker_id_manager
        self._ui_manager = ui_manager

    def _get_detection_manager(self):
        """Safely retrieve the DetectionManager from ui_manager."""
        if self._ui_manager is None:
            return None
        return getattr(self._ui_manager, 'detection_manager', None)

    def _get_face_id_detector(self):
        """Safely retrieve the FaceRecognitionDetector."""
        dm = self._get_detection_manager()
        if dm is None:
            return None
        return dm._get_face_id_detector()

    def get_recognized_faces(self):
        """Get structured face recognition results from the detection manager.

        Returns:
            List of dicts with 'name' and 'confidence' keys, e.g.
            [{"name": "Alice", "confidence": 0.85}, {"name": "UNKNOWN", "confidence": 0.0}]
        """
        dm = self._get_detection_manager()
        if dm is None:
            return []
        try:
            return dm.get_recognized_faces()
        except Exception:
            return []

    def get_current_speaker(self) -> Optional[str]:
        """Get the current speaker, preferring voice ID.

        Falls back to face recognition if voice has no result and exactly
        one known face is detected (assumes the visible person is speaking).
        """
        # Voice is authoritative for "who is speaking"
        if self._speaker_id is not None and self._speaker_id.enabled:
            speaker = self._speaker_id.get_current_speaker()
            if speaker is not None:
                return speaker

        # Fallback: if exactly one known face is visible, assume they're speaking
        faces = self.get_recognized_faces()
        known_faces = [f for f in faces if f["name"] != "UNKNOWN"]
        if len(known_faces) == 1:
            return known_faces[0]["name"]

        return None

    def get_present_people(self) -> list:
        """Get list of visually present people, excluding the current speaker.

        Returns:
            List of dicts: [{"name": "Bob", "confidence": 0.85}]
        """
        speaker = None
        if self._speaker_id is not None and self._speaker_id.enabled:
            speaker = self._speaker_id.get_current_speaker()

        faces = self.get_recognized_faces()
        present = []
        for face in faces:
            if face["name"] == "UNKNOWN":
                continue
            if face["name"] == speaker:
                continue
            present.append(face)
        return present

    def get_identity_context(self) -> str:
        """Build a unified identity context string for LLM prompt injection.

        Combines voice speaker identification with face recognition presence.
        Falls back gracefully when either system is unavailable.
        """
        # Get voice-based speaker context
        voice_speaker = None
        voice_is_unknown = False
        if self._speaker_id is not None and self._speaker_id.enabled:
            raw = self._speaker_id.get_current_speaker()
            if raw is not None:
                if raw == "Unknown" or raw.startswith("Unknown_"):
                    voice_is_unknown = True
                else:
                    voice_speaker = raw

        # Get face recognition results
        faces = self.get_recognized_faces()
        known_faces = [f for f in faces if f["name"] != "UNKNOWN"]
        has_unknown_face = any(f["name"] == "UNKNOWN" for f in faces)

        # Build context parts
        parts = []
        mentioned = set()  # Track names already mentioned to avoid duplication

        if voice_speaker:
            # Voice matched a known speaker
            mentioned.add(voice_speaker)
            face_confirms = any(f["name"] == voice_speaker for f in known_faces)
            if face_confirms:
                parts.append(f"Current speaker identified as: {voice_speaker} (voice and face match)")
            else:
                parts.append(f"Current speaker identified as: {voice_speaker}")
        elif voice_is_unknown:
            # Voice detected but speaker not recognized
            # Check if face recognition can help
            if len(known_faces) == 1:
                face_name = known_faces[0]["name"]
                mentioned.add(face_name)
                parts.append(
                    f"Current speaker: voice not recognized, but face matches {face_name}. "
                    f"Ask if this is {face_name} speaking. "
                    "When they confirm or tell you their name, call the identify_speaker_name function."
                )
            else:
                parts.append(
                    "Current speaker: UNKNOWN. You do not know who is speaking. "
                    "Naturally ask the speaker what their name is so you can remember them. "
                    "When they tell you their name, call the identify_speaker_name function."
                )
        elif len(known_faces) == 1 and not has_unknown_face:
            # No voice ID but exactly one known face visible
            mentioned.add(known_faces[0]["name"])
            parts.append(f"Visually identified: {known_faces[0]['name']} (face recognition only)")

        # Add "also present" for additional visible people not already mentioned
        present = [f["name"] for f in known_faces if f["name"] not in mentioned]

        if present:
            parts.append(f"Also present (visual): {', '.join(present)}")

        if has_unknown_face and not voice_is_unknown:
            parts.append("An unrecognized person is also visible on camera.")

        return " ".join(parts)

    def get_active_user_name(self, fallback: str) -> str:
        """Get the best-known user name for conversation display.

        Voice path (speaker ID enabled):
          identified name > last named speaker > "Unknown"
          NEVER returns config fallback — that causes flip-flopping.

        Webui/text or speaker ID disabled:
          Returns the config fallback name.
        """
        # Webui/text interactions use config name directly
        try:
            from modules.module_router import get_active_route
            if get_active_route().get("source") == "webui":
                return fallback
        except Exception:
            pass

        speaker = self.get_current_speaker()
        if speaker and speaker != "Unknown" and not speaker.startswith("Unknown_"):
            return speaker
        if self._speaker_id is not None and self._speaker_id.enabled:
            if speaker and (speaker == "Unknown" or speaker.startswith("Unknown_")):
                # Active utterance being processed — genuinely unknown.
                # Don't assume last speaker (could be someone else).
                return "Unknown"
            # speaker is None → recency expired, no active utterance.
            # Safe to use last named speaker to avoid config flip-flop.
            last = self._speaker_id.get_last_named_speaker()
            if last:
                return last
            return "Unknown"
        return fallback

    def auto_train_face(self, name: str):
        """Auto-start face training when a speaker identifies themselves by name.

        Called after identify_speaker_name renames a voice profile. Enables face ID
        temporarily if it is disabled so the person in front of the camera gets enrolled.
        """
        face_id = self._get_face_id_detector()
        if face_id is None:
            return

        if face_id.training_mode:
            return

        # If face ID is disabled but models are loaded, enable it temporarily
        if not face_id.enabled:
            if face_id.detector is None or face_id.recognizer is None:
                queue_message(f"INFO: Identity fusion — face ID models not loaded, skipping face enroll for '{name}'")
                return
            queue_message(f"INFO: Identity fusion — temporarily enabling face ID to enroll '{name}'")
            face_id.enabled = True
            face_id._temp_enabled = True

        queue_message(f"INFO: Identity fusion — auto-training face for '{name}'")
        face_id.start_training(name)

    def enable_background_detection(self, fps: float = 5.0):
        """Start a background thread that runs face detection even when the camera
        view is not open in the UI. Safe to call multiple times — only starts once.

        Also ensures the FaceRecognitionDetector is enabled if models are loaded,
        since it starts disabled by default.

        Args:
            fps: Frames per second to process. 5.0 gives responsive detection
                 without excessive CPU load.
        """
        if getattr(self, '_bg_detection_thread', None) is not None:
            return  # already running

        dm = self._get_detection_manager()
        if dm is None:
            return

        camera = getattr(self._ui_manager, 'camera_module', None)
        if camera is None:
            return

        # Enable the face ID detector if models loaded but it's toggled off
        face_id = dm._get_face_id_detector()
        self._bg_enabled_face_id = False
        if face_id is not None and not face_id.enabled:
            if face_id.detector is not None and face_id.recognizer is not None:
                face_id.enabled = True
                self._bg_enabled_face_id = True

        self._bg_detection_stop = threading.Event()

        def _worker():
            interval = 1.0 / max(fps, 0.5)
            while not self._bg_detection_stop.is_set():
                try:
                    frame = camera.get_frame()
                    if frame is not None:
                        dm.process_frame(frame)
                except Exception:
                    pass
                time.sleep(interval)

        self._bg_detection_thread = threading.Thread(target=_worker, daemon=True)
        self._bg_detection_thread.start()
        queue_message("INFO: Presence gate — background face detection started")

    def disable_background_detection(self):
        """Stop the background detection thread if running."""
        stop = getattr(self, '_bg_detection_stop', None)
        if stop is not None:
            stop.set()
        self._bg_detection_thread = None
        self._bg_detection_stop = None
