import numpy as np
import pytest
from PIL import Image

from lparc_photo import imaging
from lparc_photo.imaging import Rect, crop_rect, face_crop_rect, matricule_error
from lparc_photo.presets import PRESETS, OutputSize, mm_to_px, preset_by_key

LPARC = preset_by_key("lparc").size


def test_lparc_preset_matches_v1_output():
    assert (LPARC.width_px, LPARC.height_px, LPARC.dpi) == (413, 532, 300)
    assert (mm_to_px(35, 300), mm_to_px(45, 300)) == (413, 531)  # 532 kept for V1.2 compatibility


def test_all_presets_resolve():
    for preset in PRESETS:
        assert preset_by_key(preset.key) is preset


@pytest.mark.parametrize("fw,fh", [(1920, 1080), (640, 480), (1080, 1920), (500, 500)])
def test_crop_rect_is_centred_and_fits(fw, fh):
    r = crop_rect(fw, fh, LPARC.aspect)
    assert 0 <= r.x and r.x + r.w <= fw and 0 <= r.y and r.y + r.h <= fh
    assert abs(r.w / r.h - LPARC.aspect) < 0.01
    assert abs(r.center[0] - fw / 2) <= 1 and abs(r.center[1] - fh / 2) <= 1
    assert r.w == fw or r.h == fh  # uses the full frame on one side


def test_crop_rect_zoom_and_clamp():
    r = crop_rect(1920, 1080, LPARC.aspect, zoom=2, center=(0, 0))
    assert (r.x, r.y) == (0, 0)
    assert r.h == 540


def test_face_crop_puts_face_in_middle_and_stays_inside():
    face = Rect(900, 300, 200, 220)
    r = face_crop_rect(1920, 1080, LPARC.aspect, face)
    assert abs(r.center[0] - face.center[0]) <= 1
    assert abs(r.h - face.h / imaging.FACE_TO_CROP_HEIGHT) <= 2
    # face near the edge: crop is clamped, never outside the frame
    edge = face_crop_rect(1920, 1080, LPARC.aspect, Rect(0, 0, 300, 300))
    assert edge.x == 0 and edge.y == 0 and edge.h <= 1080


def test_face_too_big_falls_back_to_full_height():
    r = face_crop_rect(1280, 720, LPARC.aspect, Rect(400, 100, 600, 600))
    assert r.h == 720


def test_quality_flags():
    flat = np.full((532, 413, 3), 128, np.uint8)
    q = imaging.assess(flat, LPARC)
    assert q.blurry and not q.too_dark and not q.upscaled
    noisy = np.random.default_rng(0).integers(0, 255, (600, 500, 3), dtype=np.uint8)
    q = imaging.assess(noisy, LPARC)
    assert not q.blurry
    assert imaging.assess(np.zeros((100, 80, 3), np.uint8), LPARC).upscaled


def test_render_and_save_roundtrip(tmp_path):
    crop = np.random.default_rng(1).integers(0, 255, (900, 700, 3), dtype=np.uint8)
    size = OutputSize(413, 532, 300)
    img = imaging.render(crop, size)
    out = tmp_path / "sub" / "123.jpg"
    imaging.save(img, out, "jpeg", size.dpi)
    with Image.open(out) as saved:
        assert saved.size == (413, 532)
        assert saved.format == "JPEG"
        assert tuple(round(v) for v in saved.info["dpi"]) == (300, 300)
    imaging.save(img, tmp_path / "123.png", "png", 600)
    with Image.open(tmp_path / "123.png") as saved:
        assert tuple(round(v) for v in saved.info["dpi"]) == (600, 600)
    assert not list(tmp_path.rglob(".*.tmp"))


@pytest.mark.parametrize("value,ok", [
    ("2024-0153", True), ("AB 12", True), ("", False), ("   ", False),
    ("a/b", False), ("x:y", False), ("con", False), ("COM1.jpg", False), ("abc.", False),
])
def test_matricule_validation(value, ok):
    assert (matricule_error(value) is None) == ok


def test_face_detector_loads():
    assert not imaging._cascade().empty()
    assert imaging.detect_face(np.full((480, 640, 3), 120, np.uint8)) is None
