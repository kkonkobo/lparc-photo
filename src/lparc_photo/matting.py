"""Background replacement: cut the person out with MODNet and place them on a plain colour."""

from functools import cache

import cv2
import numpy as np

from .imaging import MODELS

MODEL = MODELS / "modnet.onnx"
# MODNet is most accurate with the shorter side near 512 px (768 scored worse on the PPM-100 benchmark).
REFERENCE_SIDE = 512

Colour = tuple[int, int, int]
WHITE: Colour = (255, 255, 255)
LIGHT_BLUE: Colour = (205, 224, 245)


def available() -> bool:
    return MODEL.exists()


@cache
def _session():
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    return ort.InferenceSession(str(MODEL), options, providers=["CPUExecutionProvider"])


def alpha_matte(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel opacity of the person, 0..1, at the resolution of `rgb`."""
    h, w = rgb.shape[:2]
    scale = REFERENCE_SIDE / min(h, w)
    nw = max(32, round(w * scale / 32) * 32)
    nh = max(32, round(h * scale / 32) * 32)
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    x = cv2.resize(rgb, (nw, nh), interpolation=interpolation).astype(np.float32)
    x = ((x - 127.5) / 127.5).transpose(2, 0, 1)[None]
    session = _session()
    matte = session.run(None, {session.get_inputs()[0].name: x})[0][0, 0]
    return cv2.resize(matte, (w, h), interpolation=cv2.INTER_LINEAR).clip(0, 1)


def _blur_fusion(image: np.ndarray, fg: np.ndarray, bg: np.ndarray, alpha: np.ndarray, radius: int):
    a = alpha[..., None]
    blurred_a = cv2.blur(alpha, (radius, radius))[..., None]
    blurred_fg = cv2.blur(fg * a, (radius, radius)) / (blurred_a + 1e-5)
    blurred_bg = cv2.blur(bg * (1 - a), (radius, radius)) / ((1 - blurred_a) + 1e-5)
    fg = blurred_fg + a * (image - a * blurred_fg - (1 - a) * blurred_bg)
    return np.clip(fg, 0, 1), blurred_bg


def estimate_foreground(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """The person's own colour at every pixel, float 0..1.

    Semi-transparent edge pixels (hair) are a mix of person and old background. Compositing them
    as they are carries a halo of the old wall onto the new colour, so the old background's share
    is estimated and removed first (Forte & Pitié, approximate fast foreground colour estimation)."""
    image = rgb.astype(np.float32) / 255
    scale = max(1, min(rgb.shape[:2]) // 512)
    fg, bg = _blur_fusion(image, image, image, alpha, 90 * scale | 1)
    fg, _ = _blur_fusion(image, fg, bg, alpha, 6 * scale | 1)
    return fg


def composite(rgb: np.ndarray, alpha: np.ndarray, colour: Colour) -> np.ndarray:
    """`rgb` with everything but the person replaced by `colour`."""
    a = alpha[..., None]
    out = estimate_foreground(rgb, alpha) * a + (np.array(colour, np.float32) / 255) * (1 - a)
    return (out * 255 + 0.5).clip(0, 255).astype(np.uint8)
