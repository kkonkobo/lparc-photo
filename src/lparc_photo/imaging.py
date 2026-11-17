"""Framing, quality checks and saving. Pure functions on RGB numpy arrays."""

import math
import os
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .presets import OutputSize


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


def crop_rect(frame_w: int, frame_h: int, aspect: float, zoom: float = 1.0,
              center: tuple[float, float] | None = None) -> Rect:
    """Largest `aspect` (w/h) rectangle that fits the frame, shrunk by `zoom`,
    centred on `center` (default: frame centre) and clamped inside the frame."""
    if frame_w / frame_h > aspect:
        h = frame_h
        w = h * aspect
    else:
        w = frame_w
        h = w / aspect
    zoom = max(1.0, zoom)
    w, h = int(w / zoom), int(h / zoom)
    cx, cy = center if center else (frame_w / 2, frame_h / 2)
    x = int(round(min(max(cx - w / 2, 0), frame_w - w)))
    y = int(round(min(max(cy - h / 2, 0), frame_h - h)))
    return Rect(x, y, w, h)


MODELS = Path(__file__).parent / "models"


@dataclass(frozen=True)
class Face:
    """A detected face. `eyes` and `mouth` are the midpoints between the two eyes and the two mouth corners."""

    box: Rect
    eyes: tuple[float, float]
    mouth: tuple[float, float]

    @property
    def eye_mouth(self) -> float:
        return math.dist(self.eyes, self.mouth)

    def scaled(self, s: float) -> "Face":
        b = self.box
        return Face(Rect(int(b.x * s), int(b.y * s), int(b.w * s), int(b.h * s)),
                    (self.eyes[0] * s, self.eyes[1] * s), (self.mouth[0] * s, self.mouth[1] * s))


# ID-photo framing, measured from the eyes and mouth because that distance barely changes with
# hairstyle or head covering. Calibrated on a set of test portraits: the photo is about six times
# the eye-to-mouth distance tall, which leaves room for large hair above and shoulders below.
EYE_MOUTH_TO_HEIGHT = 0.165
EYE_LINE_FROM_TOP = 0.47


def face_crop_rect(frame_w: int, frame_h: int, aspect: float, face: Face, zoom: float = 1.0) -> Rect:
    """Crop that frames `face` as an ID photo. `zoom` above 1 frames tighter, below 1 wider."""
    h = face.eye_mouth / (EYE_MOUTH_TO_HEIGHT * zoom)
    full = crop_rect(frame_w, frame_h, aspect)
    h = min(h, full.h)
    center = (face.eyes[0], face.eyes[1] + (0.5 - EYE_LINE_FROM_TOP) * h)
    return crop_rect(frame_w, frame_h, aspect, zoom=full.h / h, center=center)


def smooth_rect(prev: Rect | None, target: Rect, factor: float = 0.25) -> Rect:
    """Ease the crop towards `target` so auto-framing does not jitter."""
    if prev is None:
        return target
    def lerp(a: int, b: int) -> int:
        return int(round(a + (b - a) * factor))
    return Rect(lerp(prev.x, target.x), lerp(prev.y, target.y), lerp(prev.w, target.w), lerp(prev.h, target.h))


@cache
def _face_detector() -> cv2.FaceDetectorYN:
    # Loaded from bytes, not a path: OpenCV cannot open files under non-ASCII Windows user folders.
    model = np.frombuffer((MODELS / "yunet.onnx").read_bytes(), np.uint8)
    return cv2.FaceDetectorYN.create("onnx", model, np.empty(0, np.uint8), (320, 320), 0.6, 0.3, 50)


DETECT_SIDE = 640


def detect_face(rgb: np.ndarray) -> Face | None:
    """Largest face in the frame, in full-frame coordinates."""
    h, w = rgb.shape[:2]
    scale = min(1.0, DETECT_SIDE / max(w, h))
    small = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    detector = _face_detector()
    detector.setInputSize((small.shape[1], small.shape[0]))
    _, faces = detector.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    if faces is None or len(faces) == 0:
        return None
    # x, y, w, h, right eye, left eye, nose, right mouth corner, left mouth corner, score
    f = max(faces, key=lambda f: f[2] * f[3])[:14] / scale
    return Face(Rect(int(f[0]), int(f[1]), int(f[2]), int(f[3])),
                ((f[4] + f[6]) / 2, (f[5] + f[7]) / 2), ((f[10] + f[12]) / 2, (f[11] + f[13]) / 2))


@dataclass(frozen=True)
class QualityReport:
    sharpness: float
    brightness: float
    upscaled: bool

    @property
    def blurry(self) -> bool:
        return self.sharpness < 60

    @property
    def too_dark(self) -> bool:
        return self.brightness < 70

    @property
    def too_bright(self) -> bool:
        return self.brightness > 200

    @property
    def ok(self) -> bool:
        return not (self.blurry or self.too_dark or self.too_bright or self.upscaled)


def assess(crop: np.ndarray, size: OutputSize) -> QualityReport:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    # Measure sharpness at a fixed scale so the threshold does not depend on camera resolution.
    norm = cv2.resize(gray, (400, int(400 * gray.shape[0] / gray.shape[1])), interpolation=cv2.INTER_AREA)
    sharpness = float(cv2.Laplacian(norm, cv2.CV_64F).var())
    return QualityReport(
        sharpness=sharpness,
        brightness=float(gray.mean()),
        upscaled=crop.shape[1] < size.width_px or crop.shape[0] < size.height_px,
    )


def extract(rgb: np.ndarray, rect: Rect) -> np.ndarray:
    return np.ascontiguousarray(rgb[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w])


def render(crop: np.ndarray, size: OutputSize) -> Image.Image:
    return Image.fromarray(crop).resize((size.width_px, size.height_px), Image.Resampling.LANCZOS)


FORMATS = {"jpeg": ".jpg", "png": ".png"}


def save(image: Image.Image, path: Path, fmt: str, dpi: int, quality: int = 95) -> None:
    """Write via a temp file so a crash never leaves a half-written photo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    if fmt == "png":
        image.save(tmp, format="PNG", dpi=(dpi, dpi), optimize=True)
    else:
        image.save(tmp, format="JPEG", dpi=(dpi, dpi), quality=quality, subsampling=0, optimize=True)
    os.replace(tmp, path)


_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def matricule_error(value: str) -> str | None:
    """Why `value` cannot be used as a file name on Windows or macOS, or None if it can."""
    v = value.strip()
    if not v:
        return "Saisissez un matricule."
    if bad := sorted(set(_INVALID.findall(v))):
        shown = " ".join(c if c.isprintable() else "?" for c in bad)
        return f"Caractères non autorisés : {shown}"
    if v.endswith("."):
        return "Le matricule ne peut pas finir par un point."
    if v.split(".")[0].upper() in _RESERVED:
        return "Ce nom est réservé par Windows."
    if len(v) > 100:
        return "Matricule trop long (100 caractères max)."
    return None
