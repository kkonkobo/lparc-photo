"""`LPARC Photo --self-test <portrait> <report.json>`: check, without a window or a camera, that the
packaged app can find a face and cut out a background. The build pipeline runs it on every
platform; the report goes to a file because a windowed Windows app has no console."""

import json
import sys
import time
import traceback
from pathlib import Path


def run(image_path: str, report_path: str) -> int:
    report: dict = {"ok": False, "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        import numpy as np
        from PIL import Image

        from . import __version__, imaging, matting
        from .presets import preset_by_key

        report["version"] = __version__
        rgb = np.asarray(Image.open(image_path).convert("RGB"))
        size = preset_by_key("lparc").size

        t = time.perf_counter()
        face = imaging.detect_face(rgb)
        report["face_s"] = round(time.perf_counter() - t, 3)
        report["face_found"] = face is not None
        if face is None:
            raise RuntimeError("no face found in the test portrait")

        crop = imaging.extract(rgb, imaging.face_crop_rect(rgb.shape[1], rgb.shape[0], size.aspect, face))
        t = time.perf_counter()
        alpha = matting.alpha_matte(crop)
        report["matting_first_s"] = round(time.perf_counter() - t, 3)
        t = time.perf_counter()
        alpha = matting.alpha_matte(crop)
        report["matting_s"] = round(time.perf_counter() - t, 3)
        t = time.perf_counter()
        photo = imaging.render(matting.composite(crop, alpha, matting.WHITE), size)
        report["composite_s"] = round(time.perf_counter() - t, 3)

        corners = np.asarray(photo)[:12, :12].mean(), np.asarray(photo)[:12, -12:].mean()
        report.update(crop=list(crop.shape[:2]), person_share=round(float(alpha.mean()), 3),
                      top_corners_brightness=[round(float(c), 1) for c in corners])
        # A head-and-shoulders portrait: the person fills a good part of the frame, the top corners are background.
        report["ok"] = bool(0.2 < alpha.mean() < 0.9 and min(corners) > 245)
    except Exception:
        report["error"] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0 if report["ok"] else 1
