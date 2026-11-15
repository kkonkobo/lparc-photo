"""Framing, quality checks and saving. Pure functions on RGB numpy arrays."""

import os
import re
import sys
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


# The Haar face box spans roughly eyebrows to chin. ID-photo rules put the whole
# head at ~70-80 % of the picture height, which works out to the box being about
# half of it, with the box centre (the nose) slightly above the middle.
FACE_TO_CROP_HEIGHT = 0.5
FACE_CENTER_FROM_TOP = 0.5


def face_crop_rect(frame_w: int, frame_h: int, aspect: float, face: Rect) -> Rect:
    h = face.h / FACE_TO_CROP_HEIGHT
    w = h * aspect
    scale = min(1.0, frame_w / w, frame_h / h)
    w, h = w * scale, h * scale
    cx = face.x + face.w / 2
    cy = face.y + face.h / 2 + (0.5 - FACE_CENTER_FROM_TOP) * h
    full = crop_rect(frame_w, frame_h, aspect)
    return crop_rect(frame_w, frame_h, aspect, zoom=full.h / h, center=(cx, cy))


def smooth_rect(prev: Rect | None, target: Rect, factor: float = 0.25) -> Rect:
    """Ease the crop towards `target` so auto-framing does not jitter."""
    if prev is None:
        return target
    def lerp(a: int, b: int) -> int:
        return int(round(a + (b - a) * factor))
    return Rect(lerp(prev.x, target.x), lerp(prev.y, target.y), lerp(prev.w, target.w), lerp(prev.h, target.h))


def _cascade_path() -> str:
    name = "haarcascade_frontalface_default.xml"
    candidates = [os.path.join(cv2.data.haarcascades, name)]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "cv2", "data", name))
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(name)


@cache
def _cascade() -> cv2.CascadeClassifier:
    return cv2.CascadeClassifier(_cascade_path())


DETECT_WIDTH = 480


def detect_face(rgb: np.ndarray) -> Rect | None:
    """Largest frontal face, in full-frame coordinates."""
    h, w = rgb.shape[:2]
    scale = DETECT_WIDTH / w if w > DETECT_WIDTH else 1.0
    small = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
    min_side = max(40, int(min(gray.shape) * 0.15))
    faces = _cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_side, min_side))
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return Rect(int(x / scale), int(y / scale), int(fw / scale), int(fh / scale))


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
