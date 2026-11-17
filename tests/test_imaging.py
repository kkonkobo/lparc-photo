import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lparc_photo import imaging, matting, selftest
from lparc_photo.imaging import Face, Rect, crop_rect, face_crop_rect, matricule_error
from lparc_photo.presets import PRESETS, OutputSize, mm_to_px, preset_by_key

LPARC = preset_by_key("lparc").size
PORTRAIT = Path(__file__).parent / "data" / "portrait.jpg"  # AI-generated, not a real person


@pytest.fixture(scope="module")
def portrait():
    return np.asarray(Image.open(PORTRAIT).convert("RGB"))


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


def test_finds_the_face_and_frames_it_as_an_id_photo(portrait):
    h, w = portrait.shape[:2]
    face = imaging.detect_face(portrait)
    assert face is not None
    assert face.mouth[1] > face.eyes[1]  # mouth below the eyes
    assert face.box.x < face.eyes[0] < face.box.x + face.box.w
    r = face_crop_rect(w, h, LPARC.aspect, face)
    assert 0 <= r.x and r.x + r.w <= w and 0 <= r.y and r.y + r.h <= h
    assert abs(r.w / r.h - LPARC.aspect) < 0.01
    assert abs((face.eyes[1] - r.y) / r.h - imaging.EYE_LINE_FROM_TOP) < 0.02  # eyes on the eye line
    assert abs(r.center[0] - face.eyes[0]) <= 2  # face centred
    assert abs(face.eye_mouth / r.h - imaging.EYE_MOUTH_TO_HEIGHT) < 0.01
    # shoulders and hair are inside: the photo is much taller than the face box
    assert r.h > 1.5 * face.box.h


def test_face_framing_zoom_and_limits():
    face = Face(Rect(900, 400, 160, 200), eyes=(980.0, 470.0), mouth=(980.0, 550.0))
    normal = face_crop_rect(1920, 1080, LPARC.aspect, face)
    assert face_crop_rect(1920, 1080, LPARC.aspect, face, zoom=1.4).h < normal.h < face_crop_rect(1920, 1080, LPARC.aspect, face, zoom=0.8).h
    # a face too close to the camera: the crop is the full frame height, never larger
    close = Face(Rect(600, 100, 700, 800), eyes=(950.0, 400.0), mouth=(950.0, 800.0))
    assert face_crop_rect(1920, 1080, LPARC.aspect, close).h == 1080
    # a face in the corner: clamped inside the frame
    corner = face_crop_rect(1920, 1080, LPARC.aspect, Face(Rect(0, 0, 160, 200), eyes=(80.0, 70.0), mouth=(80.0, 150.0)))
    assert corner.x == 0 and corner.y == 0


def test_scaled_face():
    face = Face(Rect(10, 20, 30, 40), eyes=(25.0, 35.0), mouth=(25.0, 50.0)).scaled(2)
    assert face.box == Rect(20, 40, 60, 80) and face.eyes == (50.0, 70.0) and face.eye_mouth == 30.0


def test_no_face_in_an_empty_frame():
    assert imaging.detect_face(np.full((480, 640, 3), 120, np.uint8)) is None


def test_cut_out_separates_person_from_background(portrait):
    h, w = portrait.shape[:2]
    face = imaging.detect_face(portrait)
    crop = imaging.extract(portrait, face_crop_rect(w, h, LPARC.aspect, face))
    alpha = matting.alpha_matte(crop)
    assert alpha.shape == crop.shape[:2] and alpha.dtype == np.float32
    ch, cw = alpha.shape
    assert alpha[: ch // 20, : cw // 20].max() < 0.05 and alpha[: ch // 20, -cw // 20:].max() < 0.05  # top corners are wall
    assert alpha[int(ch * 0.4):int(ch * 0.6), int(cw * 0.4):int(cw * 0.6)].min() > 0.95  # the face is solid

    for colour in (matting.WHITE, matting.LIGHT_BLUE, (10, 200, 30)):
        out = matting.composite(crop, alpha, colour)
        assert out.shape == crop.shape and out.dtype == np.uint8
        assert np.abs(out[: ch // 20, : cw // 20].reshape(-1, 3).mean(0) - colour).max() < 2  # background is exactly the colour
        middle = (slice(int(ch * 0.4), int(ch * 0.6)), slice(int(cw * 0.4), int(cw * 0.6)))
        assert np.abs(out[middle].astype(int) - crop[middle].astype(int)).mean() < 1  # the face is untouched


def test_foreground_estimate_removes_old_background_tint():
    # A grey disc on a red wall with a soft edge: edge pixels are pink until the wall's share is removed.
    yy, xx = np.mgrid[:200, :200]
    alpha = np.clip((80 - np.hypot(yy - 100, xx - 100)) / 12 + 0.5, 0, 1).astype(np.float32)
    person, wall = np.array([120, 120, 120], np.float32), np.array([255, 0, 0], np.float32)
    rgb = (alpha[..., None] * person + (1 - alpha[..., None]) * wall).astype(np.uint8)
    edge = (alpha > 0.3) & (alpha < 0.7)
    naive_redness = (rgb[edge][:, 0].astype(float) - rgb[edge][:, 2]).mean()
    fg = matting.estimate_foreground(rgb, alpha) * 255
    cleaned_redness = (fg[edge][:, 0] - fg[edge][:, 2]).mean()
    assert naive_redness > 100 and cleaned_redness < naive_redness * 0.25


def test_self_test_passes(tmp_path):
    report = tmp_path / "report.json"
    assert selftest.run(str(PORTRAIT), str(report)) == 0
    data = json.loads(report.read_text())
    assert data["ok"] and data["face_found"] and "error" not in data


def test_self_test_reports_failure(tmp_path):
    blank = tmp_path / "blank.jpg"
    Image.new("RGB", (640, 480), (120, 120, 120)).save(blank)
    report = tmp_path / "report.json"
    assert selftest.run(str(blank), str(report)) == 1
    assert "no face" in json.loads(report.read_text())["error"]


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
