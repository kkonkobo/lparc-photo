"""Window-level tests with a synthetic camera frame (no camera hardware needed)."""

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from lparc_photo import app as app_module
from lparc_photo.camera import rgb_to_qimage
from lparc_photo.presets import OutputSize


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
