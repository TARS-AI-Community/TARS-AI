"""
Visual Detection Manager
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
import os
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
import cv2
import numpy as np
import pygame
from pathlib import Path

_ONNX_MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}

def _ensure_models(models_dir: Path):
    """Download any missing ONNX model files."""
    import urllib.request
    models_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in _ONNX_MODELS.items():
        dest = models_dir / filename
        if not dest.exists():
            print(f"INFO: Downloading missing model {filename}...")
            try:
                urllib.request.urlretrieve(url, dest)
                print(f"INFO: Downloaded {filename} ({dest.stat().st_size // 1024} KB)")
            except Exception as e:
                print(f"WARNING: Could not download {filename}: {e}")


class BaseDetector:
    name = "DETECTOR"

    def __init__(self):
        self.enabled = True

    def detect(self, frame_bgr, gray):
        raise NotImplementedError

    def cleanup(self):
        pass


class FaceDetector(BaseDetector):
    name = "FACE"

    def __init__(self):
        super().__init__()
        self.classifier = None
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.classifier = cv2.CascadeClassifier(cascade_path)
            if self.classifier.empty():
                print("WARNING: Face detector cascade file is empty")
                self.classifier = None
                self.enabled = False
        except Exception as e:
            print(f"WARNING: Face detector init failed: {e}")
            self.classifier = None
            self.enabled = False

    def detect(self, frame_bgr, gray):
        if self.classifier is None:
            return []

        faces = self.classifier.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )

        detections = []
        for (x, y, w, h) in faces:
            detections.append({
                'bbox': (x, y, w, h),
                'label': 'FACE',
                'color': (0, 255, 255)
            })
        return detections


class MotionDetector(BaseDetector):
    name = "MOTION"

    def __init__(self, threshold=25, min_area=500):
        super().__init__()
        self.prev_gray = None
        self.threshold = threshold
        self.min_area = min_area

    def detect(self, frame_bgr, gray):
        if self.prev_gray is None:
            self.prev_gray = gray.copy()
            return []

        delta = cv2.absdiff(self.prev_gray, gray)
        self.prev_gray = gray.copy()

        thresh = cv2.threshold(delta, self.threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        thresh = cv2.GaussianBlur(thresh, (21, 21), 0)

        overlay = np.zeros_like(frame_bgr)
        overlay[:, :, 1] = thresh
        alpha = (thresh.astype(np.float32) / 255.0 * 0.4)

        return [{'mask': overlay, 'alpha': alpha}]


class QRBarcodeDetector(BaseDetector):
    name = "QR/BAR"

    def __init__(self):
        super().__init__()
        self.qr_detector = cv2.QRCodeDetector()
        self.barcode_detector = None
        try:
            self.barcode_detector = cv2.barcode.BarcodeDetector()
        except AttributeError:
            pass

    def detect(self, frame_bgr, gray):
        detections = []

        retval, decoded_info, points, _ = self.qr_detector.detectAndDecodeMulti(frame_bgr)
        if retval and points is not None:
            for i, pts in enumerate(points):
                pts = pts.astype(int)
                x, y, w, h = cv2.boundingRect(pts)
                data = decoded_info[i] if i < len(decoded_info) and decoded_info[i] else "QR"
                label = f"QR: {data[:20]}" if data != "QR" else "QR"
                detections.append({
                    'bbox': (x, y, w, h),
                    'label': label,
                    'color': (255, 0, 255)
                })

        if self.barcode_detector is not None:
            ok, decoded, points_bc = self.barcode_detector.detectAndDecode(frame_bgr)
            if ok and points_bc is not None:
                for i, pts in enumerate(points_bc):
                    pts = pts.astype(int)
                    x, y, w, h = cv2.boundingRect(pts)
                    data = decoded[i] if i < len(decoded) and decoded[i] else "BARCODE"
                    label = f"BC: {data[:20]}" if data != "BARCODE" else "BARCODE"
                    detections.append({
                        'bbox': (x, y, w, h),
                        'label': label,
                        'color': (255, 165, 0)
                    })

        return detections


class EdgeDetector(BaseDetector):
    name = "EDGE"

    def __init__(self, low=30, high=80):
        super().__init__()
        self.low = low
        self.high = high

    def detect(self, frame_bgr, gray):
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, self.low, self.high)

        overlay = np.zeros_like(frame_bgr)
        overlay[:, :, 0] = edges
        overlay[:, :, 1] = edges
        overlay[:, :, 2] = 0

        alpha = (edges.astype(np.float32) / 255.0) * 0.9

        return [{'mask': overlay, 'alpha': alpha}]


class BodyDetector(BaseDetector):
    name = "BODY"

    def __init__(self):
        super().__init__()
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame_bgr, gray):
        boxes, weights = self.hog.detectMultiScale(
            gray,
            winStride=(8, 8),
            padding=(4, 4),
            scale=1.05
        )

        detections = []
        for (x, y, w, h), weight in zip(boxes, weights):
            if weight < 0.3:
                continue
            detections.append({
                'bbox': (x, y, w, h),
                'label': 'BODY',
                'color': (0, 200, 0)
            })
        return detections


class FaceRecognitionDetector(BaseDetector):
    name = "FACE ID"

    MODELS_DIR = Path(__file__).parent / "models"
    FACES_DIR = Path(__file__).parent.parent.parent / "vision" / "faces"
    DB_FILE = FACES_DIR / "known_faces.npz"

    YUNET_MODEL = "face_detection_yunet_2023mar.onnx"
    SFACE_MODEL = "face_recognition_sface_2021dec.onnx"

    COSINE_THRESHOLD = 0.363
    TRAINING_SAMPLES = 10

    def __init__(self):
        super().__init__()
        self.detector = None
        self.recognizer = None
        self.known_names = []
        self.known_embeddings = []

        self.training_mode = False
        self.training_samples = []
        self.training_name = None
        self.training_status = ""
        self.has_unknown = False

        try:
            _ensure_models(self.MODELS_DIR)
            yunet_path = str(self.MODELS_DIR / self.YUNET_MODEL)
            sface_path = str(self.MODELS_DIR / self.SFACE_MODEL)

            self.detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320))
            self.recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
            self._load_database()
        except Exception as e:
            print(f"WARNING: Face recognition init failed: {e}")
            self.enabled = False

    def _load_database(self):
        self.FACES_DIR.mkdir(parents=True, exist_ok=True)
        if self.DB_FILE.exists():
            data = np.load(str(self.DB_FILE), allow_pickle=True)
            self.known_names = data['names'].tolist()
            self.known_embeddings = [data[f'emb_{i}'] for i in range(len(self.known_names))]

    def _save_database(self):
        self.FACES_DIR.mkdir(parents=True, exist_ok=True)
        save_dict = {'names': np.array(self.known_names, dtype=object)}
        for i, emb in enumerate(self.known_embeddings):
            save_dict[f'emb_{i}'] = emb
        np.savez(str(self.DB_FILE), **save_dict)

    def start_training(self, name):
        self.training_mode = True
        self.training_samples = []
        self.training_name = name
        self.training_status = f"0/{self.TRAINING_SAMPLES}"

    def _finish_training(self):
        if not self.training_samples:
            self.training_status = "NO FACE"
            self.training_mode = False
            return

        avg_embedding = np.mean(self.training_samples, axis=0)
        avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)

        if self.training_name in self.known_names:
            idx = self.known_names.index(self.training_name)
            self.known_embeddings[idx] = avg_embedding
        else:
            self.known_names.append(self.training_name)
            self.known_embeddings.append(avg_embedding)

        self._save_database()
        self.training_status = "SAVED"
        self.training_mode = False

    def delete_face(self, name):
        if name in self.known_names:
            idx = self.known_names.index(name)
            self.known_names.pop(idx)
            self.known_embeddings.pop(idx)
            self._save_database()
            return True
        return False

    def _identify(self, embedding):
        if not self.known_embeddings:
            return "UNKNOWN", 0.0

        best_name = "UNKNOWN"
        best_score = 0.0

        for name, known_emb in zip(self.known_names, self.known_embeddings):
            score = self.recognizer.match(embedding, known_emb,
                                          cv2.FaceRecognizerSF_FR_COSINE)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score < self.COSINE_THRESHOLD:
            return "UNKNOWN", best_score

        return best_name, best_score

    def detect(self, frame_bgr, gray):
        if self.detector is None or self.recognizer is None:
            return []

        h, w = frame_bgr.shape[:2]
        self.detector.setInputSize((w, h))

        _, faces = self.detector.detect(frame_bgr)
        if faces is None:
            return []

        detections = []
        found_unknown = False
        for face in faces:
            bbox = face[:4].astype(int)
            x, y, fw, fh = bbox

            aligned = self.recognizer.alignCrop(frame_bgr, face)
            embedding = self.recognizer.feature(aligned)

            if self.training_mode:
                self.training_samples.append(embedding.copy())
                count = len(self.training_samples)
                self.training_status = f"{count}/{self.TRAINING_SAMPLES}"

                if count >= self.TRAINING_SAMPLES:
                    self._finish_training()

                label = f"TRAIN: {self.training_status}"
                color = (0, 165, 255)
            else:
                name, score = self._identify(embedding)
                pct = int(score * 100)
                label = f"{name} {pct}%" if name != "UNKNOWN" else "UNKNOWN"
                color = (255, 200, 0) if name != "UNKNOWN" else (0, 0, 255)
                if name == "UNKNOWN":
                    found_unknown = True

            detections.append({
                'bbox': (x, y, fw, fh),
                'label': label,
                'color': color
            })

        self.has_unknown = found_unknown
        return detections


class DetectionManager:

    PRIMARY_COLOR = (0, 255, 255)
    BORDER_COLOR = (0, 200, 220)
    ACCENT_COLOR = (0, 120, 150)
    BG_PANEL = (10, 25, 30)
    TEXT_COLOR = (0, 240, 200)
    ACTIVE_BG = (20, 60, 80, 220)
    INACTIVE_BG = (40, 15, 15, 200)
    INACTIVE_BORDER = (150, 60, 60, 200)
    INACTIVE_TEXT = (150, 80, 80)

    BUTTON_WIDTH = 90
    BUTTON_HEIGHT = 32
    BUTTON_SPACING = 8
    BUTTON_MARGIN_LEFT = 10
    BUTTON_MARGIN_TOP = 10

    TRAIN_BG = (60, 40, 10, 220)
    TRAIN_ACTIVE_BG = (40, 80, 20, 220)
    TRAIN_BORDER = (200, 160, 0)
    TRAIN_TEXT = (200, 180, 0)

    def __init__(self):
        self.detectors = []
        self._init_default_detectors()
        self._button_rects = []
        self._train_button_rect = None
        self._last_camera_x = None
        self._last_camera_y = None
        self._last_camera_w = None
        self._last_click_time = 0
        self._click_cooldown = 300
        self._button_font = None
        self._last_labels = []

        self._name_input_active = False
        self._name_input_text = ""
        self._name_input_rect = None

        self._delete_button_rect = None
        self._delete_menu_active = False
        self._delete_menu_rects = []
        self._delete_menu_names = []

    def _init_default_detectors(self):
        face = FaceDetector()
        self.detectors.append(face)

        motion = MotionDetector()
        motion.enabled = False
        self.detectors.append(motion)

        qr_barcode = QRBarcodeDetector()
        qr_barcode.enabled = False
        self.detectors.append(qr_barcode)

        edge = EdgeDetector()
        edge.enabled = False
        self.detectors.append(edge)

        body = BodyDetector()
        body.enabled = False
        self.detectors.append(body)

        face_id = FaceRecognitionDetector()
        face_id.enabled = False
        self.detectors.append(face_id)

    def add_detector(self, detector):
        self.detectors.append(detector)
        self._last_camera_w = None

    def remove_detector(self, detector):
        if detector in self.detectors:
            detector.cleanup()
            self.detectors.remove(detector)
            self._last_camera_w = None

    def has_detectors(self):
        return len(self.detectors) > 0

    def toggle_detector(self, index):
        if 0 <= index < len(self.detectors):
            self.detectors[index].enabled = not self.detectors[index].enabled

    def _get_face_id_detector(self):
        for d in self.detectors:
            if isinstance(d, FaceRecognitionDetector):
                return d
        return None

    def _build_button_rects(self, camera_x, camera_y, camera_w):
        self._button_rects = []
        self._train_button_rect = None
        self._delete_button_rect = None
        self._last_camera_x = camera_x
        self._last_camera_y = camera_y
        self._last_camera_w = camera_w

        x = camera_x - self.BUTTON_WIDTH + self.BUTTON_MARGIN_LEFT + 15
        start_y = camera_y + self.BUTTON_MARGIN_TOP

        row = 0
        for i in range(len(self.detectors)):
            y = start_y + row * (self.BUTTON_HEIGHT + self.BUTTON_SPACING)
            self._button_rects.append(pygame.Rect(x, y, self.BUTTON_WIDTH, self.BUTTON_HEIGHT))
            row += 1

            face_id = self._get_face_id_detector()
            if face_id is not None and self.detectors[i] is face_id and face_id.enabled:
                if face_id.has_unknown or face_id.training_mode:
                    y = start_y + row * (self.BUTTON_HEIGHT + self.BUTTON_SPACING)
                    self._train_button_rect = pygame.Rect(x, y, self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
                    row += 1

                if face_id.known_names:
                    y = start_y + row * (self.BUTTON_HEIGHT + self.BUTTON_SPACING)
                    self._delete_button_rect = pygame.Rect(x, y, self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
                    row += 1

    def _ensure_font(self):
        if self._button_font is None:
            try:
                self._button_font = pygame.font.Font("UI/pixelmix.ttf", 14)
            except Exception:
                self._button_font = pygame.font.SysFont("monospace", 14)

    def draw_buttons(self, surface, camera_x, camera_y, camera_w):
        if not self.detectors:
            return

        self._ensure_font()

        face_id = self._get_face_id_detector()
        train_should_show = (face_id is not None and face_id.enabled and
                             (face_id.has_unknown or face_id.training_mode))
        train_is_showing = self._train_button_rect is not None
        delete_should_show = (face_id is not None and face_id.enabled and
                              len(face_id.known_names) > 0)
        delete_is_showing = self._delete_button_rect is not None

        needs_rebuild = (len(self._button_rects) != len(self.detectors) or
                         camera_x != self._last_camera_x or
                         camera_y != self._last_camera_y or
                         camera_w != self._last_camera_w or
                         train_should_show != train_is_showing or
                         delete_should_show != delete_is_showing)
        if needs_rebuild:
            self._build_button_rects(camera_x, camera_y, camera_w)

        for i, detector in enumerate(self.detectors):
            rect = self._button_rects[i]
            active = detector.enabled

            if active:
                bg_color = self.ACTIVE_BG
                border_color = (*self.PRIMARY_COLOR, 255)
                text_color = self.PRIMARY_COLOR
            else:
                bg_color = self.INACTIVE_BG
                border_color = self.INACTIVE_BORDER
                text_color = self.INACTIVE_TEXT

            pygame.draw.rect(surface, bg_color, rect)
            pygame.draw.rect(surface, border_color, rect, 2)

            inner_rect = rect.inflate(-4, -4)
            pygame.draw.rect(surface, (*self.ACCENT_COLOR, 150), inner_rect, 1)

            bracket_size = 6
            pygame.draw.line(surface, border_color, rect.topleft,
                             (rect.left + bracket_size, rect.top), 2)
            pygame.draw.line(surface, border_color, rect.topleft,
                             (rect.left, rect.top + bracket_size), 2)
            pygame.draw.line(surface, border_color, rect.topright,
                             (rect.right - bracket_size, rect.top), 2)
            pygame.draw.line(surface, border_color,
                             (rect.right - 1, rect.top),
                             (rect.right - 1, rect.top + bracket_size), 2)

            text_surface = self._button_font.render(detector.name, True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

        if self._train_button_rect is not None:
            rect = self._train_button_rect
            face_id = self._get_face_id_detector()
            is_training = face_id is not None and face_id.training_mode

            if is_training:
                bg = self.TRAIN_ACTIVE_BG
                border = (0, 255, 0)
                text_color = (0, 255, 0)
                label = face_id.training_status
            else:
                bg = self.TRAIN_BG
                border = self.TRAIN_BORDER
                text_color = self.TRAIN_TEXT
                label = "TRAIN"

            pygame.draw.rect(surface, bg, rect)
            pygame.draw.rect(surface, border, rect, 2)
            text_surface = self._button_font.render(label, True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

        if self._delete_button_rect is not None:
            rect = self._delete_button_rect
            bg = (50, 10, 10, 220)
            border = (200, 60, 60)
            text_color = (200, 80, 80)
            pygame.draw.rect(surface, bg, rect)
            pygame.draw.rect(surface, border, rect, 2)
            text_surface = self._button_font.render("DELETE", True, text_color)
            text_rect = text_surface.get_rect(center=rect.center)
            surface.blit(text_surface, text_rect)

        if self._delete_menu_active:
            self._draw_delete_menu(surface)

        if self._name_input_active:
            self._draw_name_input(surface)

    def _draw_delete_menu(self, surface):
        self._ensure_font()
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        face_id = self._get_face_id_detector()
        if not face_id or not face_id.known_names:
            self._delete_menu_active = False
            return

        self._delete_menu_names = list(face_id.known_names)
        item_h = 32
        padding = 10
        box_w = 280
        box_h = 40 + len(self._delete_menu_names) * (item_h + 4) + padding
        box_x = (sw - box_w) // 2
        box_y = (sh - box_h) // 2

        pygame.draw.rect(surface, (10, 25, 30), (box_x, box_y, box_w, box_h))
        pygame.draw.rect(surface, (200, 60, 60), (box_x, box_y, box_w, box_h), 2)

        title = self._button_font.render("DELETE FACE:", True, (200, 80, 80))
        surface.blit(title, (box_x + 10, box_y + 10))

        self._delete_menu_rects = []
        for i, name in enumerate(self._delete_menu_names):
            iy = box_y + 38 + i * (item_h + 4)
            item_rect = pygame.Rect(box_x + 10, iy, box_w - 20, item_h)
            self._delete_menu_rects.append(item_rect)

            pygame.draw.rect(surface, (40, 10, 10), item_rect)
            pygame.draw.rect(surface, (150, 50, 50), item_rect, 1)

            name_surf = self._button_font.render(name, True, (200, 150, 150))
            name_rect = name_surf.get_rect(midleft=(item_rect.x + 10, item_rect.centery))
            surface.blit(name_surf, name_rect)

            x_surf = self._button_font.render("X", True, (255, 80, 80))
            x_rect = x_surf.get_rect(midright=(item_rect.right - 10, item_rect.centery))
            surface.blit(x_surf, x_rect)

        hint = self._button_font.render("ESC to close", True, (100, 100, 100))
        surface.blit(hint, (box_x + 10, box_y + box_h - 20))

    def _draw_name_input(self, surface):
        self._ensure_font()
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        box_w, box_h = 280, 100
        box_x = (sw - box_w) // 2
        box_y = (sh - box_h) // 2
        box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
        self._name_input_rect = box_rect

        pygame.draw.rect(surface, (10, 25, 30), box_rect)
        pygame.draw.rect(surface, self.PRIMARY_COLOR, box_rect, 2)

        title = self._button_font.render("ENTER NAME:", True, self.PRIMARY_COLOR)
        surface.blit(title, (box_x + 10, box_y + 10))

        field_rect = pygame.Rect(box_x + 10, box_y + 35, box_w - 20, 28)
        pygame.draw.rect(surface, (5, 15, 20), field_rect)
        pygame.draw.rect(surface, self.ACCENT_COLOR, field_rect, 1)

        name_text = self._button_font.render(self._name_input_text + "_", True, (0, 255, 200))
        surface.blit(name_text, (field_rect.x + 5, field_rect.y + 6))

        hint = self._button_font.render("ENTER to confirm", True, (100, 100, 100))
        surface.blit(hint, (box_x + 10, box_y + 72))

    def handle_key_event(self, event):
        if self._delete_menu_active:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._delete_menu_active = False
                return True
            return True

        if not self._name_input_active:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if self._name_input_text.strip():
                    face_id = self._get_face_id_detector()
                    if face_id:
                        face_id.start_training(self._name_input_text.strip())
                self._name_input_active = False
                self._name_input_text = ""
                return True
            elif event.key == pygame.K_ESCAPE:
                self._name_input_active = False
                self._name_input_text = ""
                return True
            elif event.key == pygame.K_BACKSPACE:
                self._name_input_text = self._name_input_text[:-1]
                return True
            elif event.unicode and len(self._name_input_text) < 20:
                self._name_input_text += event.unicode
                return True

        return False

    def handle_click(self, pos):
        if self._name_input_active:
            return True

        if self._delete_menu_active:
            for i, rect in enumerate(self._delete_menu_rects):
                if rect.collidepoint(pos):
                    face_id = self._get_face_id_detector()
                    if face_id and i < len(self._delete_menu_names):
                        face_id.delete_face(self._delete_menu_names[i])
                        if not face_id.known_names:
                            self._delete_menu_active = False
                            self._last_camera_w = None
                    return True
            self._delete_menu_active = False
            return True

        now = pygame.time.get_ticks()
        if now - self._last_click_time < self._click_cooldown:
            return False

        if self._delete_button_rect is not None and self._delete_button_rect.collidepoint(pos):
            self._last_click_time = now
            self._delete_menu_active = True
            return True

        if self._train_button_rect is not None and self._train_button_rect.collidepoint(pos):
            self._last_click_time = now
            face_id = self._get_face_id_detector()
            if face_id and not face_id.training_mode:
                self._name_input_active = True
                self._name_input_text = ""
            return True

        for i, rect in enumerate(self._button_rects):
            if rect.collidepoint(pos):
                self._last_click_time = now
                self.toggle_detector(i)
                if isinstance(self.detectors[i], FaceRecognitionDetector):
                    self._last_camera_w = None
                return True
        return False

    def get_detection_summary(self):
        """Return a short text summary of recent detections for the LLM."""
        if not self._last_labels:
            return ""
        return "Detected: " + ", ".join(self._last_labels)

    def process_frame(self, frame):
        if not self.detectors or not any(d.enabled for d in self.detectors):
            self._last_labels = []
            return frame

        frame_array = pygame.surfarray.array3d(frame)
        frame_array = np.transpose(frame_array, (1, 0, 2))
        frame_array = np.ascontiguousarray(frame_array)

        frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        all_detections = []
        for detector in self.detectors:
            if detector.enabled:
                all_detections.extend(detector.detect(frame_bgr, gray))

        self._last_labels = [d['label'] for d in all_detections if 'label' in d]

        frame_float = frame_bgr.astype(np.float32)
        for det in all_detections:
            if 'mask' in det:
                overlay = det['mask'].astype(np.float32)
                alpha = det['alpha'][:, :, np.newaxis]
                frame_float = frame_float * (1.0 - alpha) + overlay * alpha + frame_float * alpha
        frame_bgr = np.clip(frame_float, 0, 255).astype(np.uint8)

        for det in all_detections:
            if 'mask' in det:
                continue
            x, y, w, h = det['bbox']
            color = det['color']
            label = det['label']

            cv2.rectangle(frame_bgr, (x, y), (x + w, y + h), color, 2)
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
            cv2.rectangle(frame_bgr, (x, y - 28), (x + label_size[0] + 8, y), color, -1)
            cv2.putText(frame_bgr, label, (x + 4, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb = np.transpose(frame_rgb, (1, 0, 2))
        return pygame.surfarray.make_surface(frame_rgb)
