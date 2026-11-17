"""Window-level tests with a synthetic camera frame (no camera hardware needed)."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

from lparc_photo import app as app_module
from lparc_photo import matting
from lparc_photo.camera import rgb_to_qimage
from lparc_photo.presets import OutputSize

PORTRAIT = Path(__file__).parent / "data" / "portrait.jpg"


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setattr(app_module, "QSettings", lambda *_: QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    win = app_module.MainWindow()
    win.output_dir = tmp_path / "photos"
    win.auto_check.setChecked(False)
    win.review_check.setChecked(False)
    win.show()
    yield win
    win.close()


def feed(win, w=1280, h=720):
    rgb = np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)
    image = rgb_to_qimage(rgb)
    win.camera.latest = image
    win.stack.setCurrentIndex(app_module.LIVE)
    win._on_frame(image)
    return rgb


def test_capture_saves_photo_at_preset_size(window, tmp_path):
    feed(window)
    window.matricule.setText("2024-0153")
    window._capture_requested()
    out = tmp_path / "photos" / "2024-0153.jpg"
    assert out.exists()
    with Image.open(out) as img:
        assert img.size == (413, 532)
        assert tuple(round(v) for v in img.info["dpi"]) == (300, 300)
    assert window.matricule.text() == ""
    assert window.recent.count() == 1


def test_invalid_matricule_shows_inline_error(window, tmp_path):
    feed(window)
    window.matricule.setText("a/b")
    window._capture_requested()
    assert not (tmp_path / "photos").exists()
    assert not window.matricule_msg.isHidden()
    assert "/" in window.matricule_msg.text()


def test_custom_size_in_mm_and_png(window, tmp_path):
    feed(window, 1920, 1080)
    window.preset_combo.setCurrentIndex(window.preset_combo.findData("custom"))
    window.unit_combo.setCurrentIndex(window.unit_combo.findData("mm"))
    window.dpi_spin.setValue(600)
    window.w_spin.setValue(30)
    window.h_spin.setValue(40)
    window.format_combo.setCurrentIndex(window.format_combo.findData("png"))
    assert window.output_size() == OutputSize(709, 945, 600)
    feed(window, 1920, 1080)
    window.matricule.setText("X1")
    window._capture_requested()
    with Image.open(tmp_path / "photos" / "X1.png") as img:
        assert img.size == (709, 945)


def test_unit_switch_converts_values(window):
    window.preset_combo.setCurrentIndex(window.preset_combo.findData("custom"))
    window.unit_combo.setCurrentIndex(window.unit_combo.findData("mm"))
    window.dpi_spin.setValue(300)
    window.w_spin.setValue(35)
    window.h_spin.setValue(45)
    window.unit_combo.setCurrentIndex(window.unit_combo.findData("px"))
    assert (window.w_spin.value(), window.h_spin.value()) == (413, 531)


def test_existing_photo_needs_confirmation(window, tmp_path, monkeypatch):
    feed(window)
    window.matricule.setText("42")
    window._capture_requested()
    before = (tmp_path / "photos" / "42.jpg").stat().st_mtime_ns
    monkeypatch.setattr(window, "_confirm_replace", lambda *_: False)
    feed(window)
    window.matricule.setText("42")
    window._capture_requested()
    assert (tmp_path / "photos" / "42.jpg").stat().st_mtime_ns == before
    assert window.matricule.text() == "42"


def test_review_then_save(window, tmp_path):
    window.review_check.setChecked(True)
    feed(window)
    window.matricule.setText("R1")
    window._capture_requested()
    assert window.pending is not None
    assert not (tmp_path / "photos" / "R1.jpg").exists()
    window._save_pending()
    assert (tmp_path / "photos" / "R1.jpg").exists()
    assert window.stack.currentIndex() == app_module.LIVE


def test_low_resolution_camera_warns(window):
    window.preset_combo.setCurrentIndex(window.preset_combo.findData("id600"))
    feed(window, 640, 480)
    assert not window.size_warning.isHidden()


def test_drag_moves_crop_and_stays_in_frame(window):
    feed(window)
    window.zoom_slider.setValue(200)
    feed(window)
    before = window.crop
    window._on_drag(-5000, -5000)
    feed(window)
    assert (window.crop.x, window.crop.y) == (0, 0)
    assert window.crop != before


def feed_portrait(win):
    """A frame with a real-looking face, with automatic framing on."""
    win.auto_check.setChecked(True)
    image = rgb_to_qimage(np.asarray(Image.open(PORTRAIT).convert("RGB")))
    win.camera.latest = image
    win.stack.setCurrentIndex(app_module.LIVE)
    win.last_detect = 0.0
    win._on_frame(image)
    assert win.face_locked
    return image


def corner(path):
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))[:10, :10].reshape(-1, 3).mean(0)


def test_automatic_framing_puts_eyes_on_the_eye_line(window):
    feed_portrait(window)
    assert abs((window.face.eyes[1] - window.crop.y) / window.crop.h - 0.47) < 0.02


def test_white_background_is_saved_and_original_kept(window, tmp_path):
    feed_portrait(window)
    window._on_background_chosen("white")
    window.keep_original_check.setChecked(True)
    window.matricule.setText("W1")
    window._capture_requested()
    out, original = tmp_path / "photos" / "W1.jpg", tmp_path / "photos" / "originaux" / "W1.jpg"
    assert out.exists() and original.exists()
    assert corner(out).min() > 250  # white
    assert corner(original).max() < 235  # the real wall
    with Image.open(original) as img:
        assert img.size == (413, 532)


def test_original_background_writes_no_extra_file(window, tmp_path):
    feed_portrait(window)
    window.keep_original_check.setChecked(True)  # has no effect without a replaced background
    window.matricule.setText("O1")
    window._capture_requested()
    assert (tmp_path / "photos" / "O1.jpg").exists()
    assert not (tmp_path / "photos" / "originaux").exists()
    assert not window.keep_original_check.isEnabled()


def test_background_can_be_switched_on_the_review_screen(window, tmp_path):
    window.review_check.setChecked(True)
    feed_portrait(window)
    window.matricule.setText("R2")
    window._capture_requested()
    assert window.pending.alpha is None  # nothing computed while the original background is kept
    window.review.backgrounds.chosen.emit("blue")
    assert window.pending.alpha is not None and window.background == "blue"
    assert window.bg_picker.buttons["blue"].isChecked() and window.review.backgrounds.buttons["blue"].isChecked()
    window._save_pending()
    assert np.abs(corner(tmp_path / "photos" / "R2.jpg") - matting.LIGHT_BLUE).max() < 4


def test_custom_colour_and_cancelled_dialog(window, tmp_path, monkeypatch):
    feed_portrait(window)
    monkeypatch.setattr(app_module.QColorDialog, "getColor", lambda *a, **k: QColor(10, 200, 30))
    window._on_background_chosen("custom")
    assert window.background == "custom" and window.custom_colour == (10, 200, 30)
    window.matricule.setText("C1")
    window._capture_requested()
    assert np.abs(corner(tmp_path / "photos" / "C1.jpg") - (10, 200, 30)).max() < 6

    window._on_background_chosen("white")
    monkeypatch.setattr(app_module.QColorDialog, "getColor", lambda *a, **k: QColor())  # cancelled
    window._on_background_chosen("custom")
    assert window.background == "white" and window.bg_picker.buttons["white"].isChecked()


def test_cut_out_failure_keeps_the_photo(window, tmp_path, monkeypatch):
    feed_portrait(window)
    window._on_background_chosen("white")
    monkeypatch.setattr(matting, "alpha_matte", lambda _rgb: (_ for _ in ()).throw(RuntimeError("model broken")))
    window.matricule.setText("F1")
    window._capture_requested()
    assert (tmp_path / "photos" / "F1.jpg").exists()
    assert window.background == "original"


def test_zoom_control_adjusts_automatic_framing(window):
    feed_portrait(window)
    normal = window.crop.h
    assert (window.zoom_slider.minimum(), window.zoom_slider.maximum()) == (70, 160)
    window._on_wheel(3)
    assert window.auto_zoom > 1.2
    window.crop = None
    window._on_frame(window.camera.latest)
    assert window.crop.h < normal
    window.auto_check.setChecked(False)
    assert (window.zoom_slider.minimum(), window.zoom_slider.maximum()) == (100, 400)
