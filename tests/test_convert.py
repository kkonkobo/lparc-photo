from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import Qt

from lparc_photo import convert
from lparc_photo.convert_dialog import CHECK, ConvertDialog


def make(path: Path, fmt: str, size=(120, 150), colour=(200, 120, 40), dpi=300, alpha=False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "RGBA" if alpha else "RGB"
    image = Image.new(mode, size, colour + ((0,) if alpha else ()))
    if alpha:  # an opaque square in a transparent frame
        image.paste(Image.new("RGBA", (40, 40), colour + (255,)), (40, 50))
    image.save(path, format=fmt, dpi=(dpi, dpi), **({"quality": 95} if fmt == "JPEG" else {}))
    return path


@pytest.fixture
def folder(tmp_path):
    make(tmp_path / "001.png", "PNG")
    make(tmp_path / "002.png", "PNG", dpi=600)
    make(tmp_path / "003.jpg", "JPEG")
    make(tmp_path / "004.jpg", "PNG")  # a PNG saved under a .jpg name
    make(tmp_path / "005.PNG", "PNG")
    make(tmp_path / "logo.png", "PNG", alpha=True)
    (tmp_path / "notes.txt").write_text("not a photo")
    (tmp_path / "broken.png").write_bytes(b"\x89PNG\r\n\x1a\nnot really")
    make(tmp_path / "sub" / "006.png", "PNG")
    return tmp_path


def by_name(photos):
    return {p.path.name: p for p in photos}


def test_scan_reads_formats_from_content(folder):
    photos, unreadable = convert.scan(folder)
    found = by_name(photos)
    assert set(found) == {"001.png", "002.png", "003.jpg", "004.jpg", "005.PNG", "logo.png"}
    assert found["004.jpg"].format == "png" and not found["004.jpg"].extension_matches
    assert found["003.jpg"].format == "jpeg" and found["003.jpg"].extension_matches
    assert found["005.PNG"].extension_matches
    assert found["002.png"].dpi == 600 and found["001.png"].width == 120
    assert found["logo.png"].has_alpha and not found["001.png"].has_alpha
    assert [u.path.name for u in unreadable] == ["broken.png"]


def test_scan_subfolders_and_skips_set_aside_originals(folder):
    photos, _ = convert.scan(folder, recursive=True)
    assert "006.png" in by_name(photos)
    make(folder / convert.ORIGINALS_DIR / "old.png", "PNG")
    photos, _ = convert.scan(folder, recursive=True)
    assert "old.png" not in by_name(photos)


def test_png_to_jpeg_keeps_size_dpi_and_original(folder):
    photo = by_name(convert.scan(folder)[0])["002.png"]
    result = convert.convert(photo, "jpeg", quality=92)
    assert result.status == "converted" and result.target == folder / "002.jpg"
    with Image.open(folder / "002.jpg") as img:
        assert img.format == "JPEG" and img.size == (120, 150)
        assert tuple(round(v) for v in img.info["dpi"]) == (600, 600)
        assert np.abs(np.asarray(img).reshape(-1, 3).mean(0) - (200, 120, 40)).max() < 4
    assert not (folder / "002.png").exists()
    assert (folder / convert.ORIGINALS_DIR / "002.png").exists()
    assert not list(folder.glob(".*convert-tmp"))


def test_jpeg_to_png_and_back(folder):
    photo = by_name(convert.scan(folder)[0])["003.jpg"]
    assert convert.convert(photo, "png").status == "converted"
    with Image.open(folder / "003.png") as img:
        assert img.format == "PNG"
    back = by_name(convert.scan(folder)[0])["003.png"]
    assert convert.convert(back, "jpeg", keep_original=False).status == "converted"
    assert (folder / "003.jpg").exists() and not (folder / "003.png").exists()


def test_misnamed_png_becomes_a_real_jpeg_under_the_same_name(folder):
    photo = by_name(convert.scan(folder)[0])["004.jpg"]
    assert convert.needs_conversion(photo, "jpeg")
    assert convert.convert(photo, "jpeg").status == "converted"
    with Image.open(folder / "004.jpg") as img:
        assert img.format == "JPEG"
    with Image.open(folder / convert.ORIGINALS_DIR / "004.jpg") as img:
        assert img.format == "PNG"  # the untouched original


def test_misnamed_png_converted_in_place_without_keeping(folder):
    photo = by_name(convert.scan(folder)[0])["004.jpg"]
    assert convert.convert(photo, "jpeg", keep_original=False).status == "converted"
    with Image.open(folder / "004.jpg") as img:
        assert img.format == "JPEG"
    assert not (folder / convert.ORIGINALS_DIR).exists()


def test_misnamed_png_to_png_only_renames(folder):
    photo = by_name(convert.scan(folder)[0])["004.jpg"]
    assert convert.convert(photo, "png").status == "converted"
    with Image.open(folder / "004.png") as img:
        assert img.format == "PNG"


def test_transparency_becomes_white(folder):
    photo = by_name(convert.scan(folder)[0])["logo.png"]
    convert.convert(photo, "jpeg")
    with Image.open(folder / "logo.jpg") as img:
        px = np.asarray(img)
        assert px[2, 2].min() > 250  # transparent corner is white
        assert np.abs(px[70, 60].astype(int) - (200, 120, 40)).max() < 6  # opaque square kept


def test_already_right_format_is_skipped(folder):
    photo = by_name(convert.scan(folder)[0])["003.jpg"]
    result = convert.convert(photo, "jpeg")
    assert result.status == "skipped" and (folder / "003.jpg").exists()


def test_existing_target_is_not_overwritten_unless_asked(folder):
    make(folder / "001.jpg", "JPEG", colour=(10, 10, 200))  # a different photo already named 001.jpg
    photo = by_name(convert.scan(folder)[0])["001.png"]
    result = convert.convert(photo, "jpeg")
    assert result.status == "skipped" and "existe déjà" in result.message
    assert (folder / "001.png").exists()

    result = convert.convert(photo, "jpeg", replace_existing=True)
    assert result.status == "converted"
    with Image.open(folder / "001.jpg") as img:
        assert np.asarray(img).reshape(-1, 3).mean(0)[0] > 150  # now the converted (orange) photo
    kept = sorted(p.name for p in (folder / convert.ORIGINALS_DIR).iterdir())
    assert kept == ["001.jpg", "001.png"]  # both the replaced file and the original are kept


def test_discard_is_used_when_not_keeping(folder):
    discarded = []
    photo = by_name(convert.scan(folder)[0])["001.png"]
    result = convert.convert(photo, "jpeg", keep_original=False, discard=lambda p: (discarded.append(p.name), p.unlink()))
    assert result.status == "converted" and discarded == ["001.png"]


def test_failure_leaves_original_untouched(folder, monkeypatch):
    photo = by_name(convert.scan(folder)[0])["001.png"]
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(Image.Image, "save", boom)
    result = convert.convert(photo, "jpeg")
    assert result.status == "failed" and "disk full" in result.message
    assert (folder / "001.png").exists() and not (folder / "001.jpg").exists()
    assert not (folder / convert.ORIGINALS_DIR).exists()
    assert not list(folder.glob(".*convert-tmp"))


def test_original_name_clash_in_backup_folder(folder):
    make(folder / convert.ORIGINALS_DIR / "001.png", "PNG")
    photo = by_name(convert.scan(folder)[0])["001.png"]
    convert.convert(photo, "jpeg")
    assert sorted(p.name for p in (folder / convert.ORIGINALS_DIR).iterdir()) == ["001 (2).png", "001.png"]


def test_human_size():
    assert convert.human_size(512) == "512 o"
    assert convert.human_size(2048) == "2,0 Ko"
    assert convert.human_size(3 * 1024 * 1024) == "3,0 Mo"


# --------------------------------------------------------------------------- dialog

@pytest.fixture
def dialog(qapp, folder, monkeypatch):
    monkeypatch.setattr("lparc_photo.convert_dialog.QMessageBox.exec", lambda self: 0)
    d = ConvertDialog(folder, "jpeg")
    yield d
    d.close()
    d.deleteLater()
    qapp.processEvents()


def checked_names(d):
    return {d.photos[r].path.name for r in d._checked_rows()}


def test_dialog_preselects_what_needs_converting(dialog):
    assert checked_names(dialog) == {"001.png", "002.png", "004.jpg", "005.PNG", "logo.png"}
    assert "Convertir 5 photos en JPEG" == dialog.convert_button.text()
    assert "6 photos : 5 PNG, 1 JPEG" in dialog.summary.text()
    assert "1 avec une extension" in dialog.summary.text() and "1 fichier illisible" in dialog.summary.text()


def test_dialog_selection_buttons_and_target_switch(dialog):
    dialog._select("jpeg")
    assert checked_names(dialog) == {"003.jpg"}
    dialog._select("none")
    assert not dialog.convert_button.isEnabled()
    dialog.to_png.setChecked(True)  # switching target re-selects what needs converting to PNG
    assert checked_names(dialog) == {"003.jpg", "004.jpg"}
    assert dialog.quality_box.isHidden()


def test_dialog_converts_selection_and_rescans(dialog, folder):
    dialog._select("none")
    for row, photo in enumerate(dialog.photos):
        if photo.path.name in ("001.png", "004.jpg"):
            dialog.table.item(row, CHECK).setCheckState(Qt.CheckState.Checked)
    assert dialog.convert_button.text() == "Convertir 2 photos en JPEG"
    dialog._convert()
    assert [r.status for r in dialog.last_results] == ["converted", "converted"]
    formats = {p.path.name: p.format for p in dialog.photos}
    assert formats["001.jpg"] == "jpeg" and formats["004.jpg"] == "jpeg" and "001.png" not in formats
    assert (folder / convert.ORIGINALS_DIR / "001.png").exists()


def test_dialog_without_keeping_sends_originals_to_trash(dialog, folder, monkeypatch):
    trashed = []
    monkeypatch.setattr("lparc_photo.convert_dialog.move_to_trash", lambda p: (trashed.append(p.name), p.unlink()))
    monkeypatch.setattr("lparc_photo.convert_dialog.QMessageBox.question", lambda *a, **k: dialog_yes())
    dialog.keep_check.setChecked(False)
    dialog._select("png")
    dialog._convert()
    assert sorted(trashed) == ["001.png", "002.png", "005.PNG", "logo.png"]  # 004.jpg is converted in place
    assert not (folder / convert.ORIGINALS_DIR).exists()


def dialog_yes():
    from PySide6.QtWidgets import QMessageBox
    return QMessageBox.StandardButton.Yes


def test_dialog_cancel_on_trash_confirmation(dialog, folder, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr("lparc_photo.convert_dialog.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    dialog.keep_check.setChecked(False)
    dialog._convert()
    assert (folder / "001.png").exists() and not (folder / "001.jpg").exists()


def test_main_window_opens_converter_on_output_folder(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from lparc_photo import app as app_module
    monkeypatch.setattr(app_module, "QSettings", lambda *_: QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    opened = {}
    monkeypatch.setattr("lparc_photo.convert_dialog.ConvertDialog.exec",
                        lambda self: opened.update(folder=self.folder, target=self.target()))
    win = app_module.MainWindow()
    win.output_dir = tmp_path
    make(tmp_path / "x.png", "PNG")
    win._open_converter()
    assert opened == {"folder": tmp_path, "target": "jpeg"}
    win.close()
    win.deleteLater()
    qapp.processEvents()
