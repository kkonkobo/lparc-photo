"""Main window: matricule → frame → capture → review → save."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QCameraPermission, QSettings, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, imaging, matting
from .camera import Camera, qimage_to_rgb, rgb_to_qimage
from .imaging import Face, QualityReport, Rect, crop_rect, face_crop_rect, matricule_error, smooth_rect
from .presets import DEFAULT_PRESET, PRESETS, OutputSize, mm_to_px, preset_by_key, px_to_mm
from .theme import stylesheet
from .updates import SITE_URL, UpdateChecker
from .widgets import BackgroundPicker, CameraView, MessageView, ReviewView, Toast

ASSETS = Path(__file__).parent / "assets"
DETECT_EVERY_S = 0.15
FACE_HOLD_S = 1.0
NO_FRAME_TIMEOUT_MS = 5000
MAX_ZOOM = 4.0
AUTO_ZOOM_MIN, AUTO_ZOOM_MAX = 0.7, 1.6  # how much the automatic frame can be widened or tightened
ORIGINALS_DIR = "originaux"
RECENT_LIMIT = 12

LIVE, REVIEW, MESSAGE = range(3)


@dataclass
class Capture:
    """One photo taken, before it is saved."""

    matricule: str
    pixels: np.ndarray  # the framed crop at camera resolution
    size: OutputSize
    report: QualityReport
    face_found: bool | None  # None when automatic framing was off
    alpha: np.ndarray | None = None  # the cut-out, computed once on first use


def section(title: str) -> QLabel:
    return QLabel(title, objectName="sectionTitle")


def card(*rows) -> QFrame:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)
    for row in rows:
        if isinstance(row, QWidget):
            layout.addWidget(row)
        else:
            layout.addLayout(row)
    return frame


def default_output_dir() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or Path.home()) / "LPARC Photos"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LPARC Photo")
        self.setMinimumSize(1000, 640)
        self.settings = QSettings("LPARC", "LPARC Photo")
        self.camera = Camera(self)
        self.media = QMediaDevices(self)
        self.updates = UpdateChecker(__version__, self)

        self.frame_size: tuple[int, int] | None = None
        self.crop: Rect | None = None
        self.face: Face | None = None
        self.face_seen_at = 0.0
        self.last_detect = 0.0
        self.face_locked = False
        self.manual_center = (0.5, 0.5)
        self.zoom = 1.0
        self.auto_zoom = 1.0
        self.background = "original"
        self.custom_colour: matting.Colour = (230, 230, 230)
        self.capturing = False
        self.frames_since_start = 0
        self.pending: Capture | None = None
        self.output_dir = default_output_dir()

        self._build()
        self._load_settings()
        self._wire()
        self._update_size_summary()

    # ---------------------------------------------------------------- layout

    def _build(self) -> None:
        self.view = CameraView()
        self.review = ReviewView()
        self.message = MessageView()
        self.stack = QStackedWidget(objectName="stage")
        for page in (self.view, self.review, self.message):
            self.stack.addWidget(page)
        self.toast = Toast(self.stack)

        # Photo
        self.matricule = QLineEdit(objectName="matricule", placeholderText="ex. 2024-0153", maxLength=100, clearButtonEnabled=True)
        self.matricule_msg = QLabel(objectName="error", wordWrap=True)
        self.matricule_msg.hide()
        self.capture_btn = QPushButton("Prendre la photo", objectName="capture")
        self.capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer_combo = QComboBox()
        for label, secs in (("Immédiat", 0), ("Retardateur 3 s", 3), ("Retardateur 5 s", 5)):
            self.timer_combo.addItem(label, secs)
        self.review_check = QCheckBox("Vérifier avant d'enregistrer")
        shortcut_hint = QLabel("↵ Entrée pour prendre la photo · Échap pour annuler", objectName="hint", wordWrap=True)
        photo_card = card(QLabel("Matricule"), self.matricule, self.matricule_msg, self.capture_btn,
                          row(self.timer_combo), self.review_check, shortcut_hint)

        # Camera
        self.camera_combo = QComboBox()
        self.camera_info = QLabel(objectName="hint")
        self.auto_check = QCheckBox("Cadrage automatique sur le visage")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, minimum=100, maximum=int(MAX_ZOOM * 100))
        self.zoom_label = QLabel(objectName="muted")
        self.mirror_check = QCheckBox("Aperçu en miroir")
        self.framing_hint = QLabel("Glissez l'image pour recadrer, molette pour zoomer.", objectName="hint", wordWrap=True)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_label)
        camera_card = card(self.camera_combo, self.camera_info, self.auto_check, zoom_row, self.framing_hint, self.mirror_check)

        # Background
        self.bg_picker = BackgroundPicker(columns=2)
        self.keep_original_check = QCheckBox(f"Conserver aussi l'original (dossier « {ORIGINALS_DIR} »)")
        self.bg_hint = QLabel(objectName="hint", wordWrap=True)
        background_card = card(self.bg_picker, self.keep_original_check, self.bg_hint)

        # Output
        self.preset_combo = QComboBox()
        for preset in PRESETS:
            self.preset_combo.addItem(preset.label, preset.key)
        self.custom_box = QWidget()
        self.w_spin, self.h_spin = QDoubleSpinBox(), QDoubleSpinBox()
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("mm", "mm")
        self.unit_combo.addItem("px", "px")
        self.dpi_spin = QSpinBox(minimum=72, maximum=1200, singleStep=50, suffix=" dpi")
        grid = QGridLayout(self.custom_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.addWidget(QLabel("Largeur", objectName="muted"), 0, 0)
        grid.addWidget(QLabel("Hauteur", objectName="muted"), 0, 1)
        grid.addWidget(QLabel("Unité", objectName="muted"), 0, 2)
        grid.addWidget(self.w_spin, 1, 0)
        grid.addWidget(self.h_spin, 1, 1)
        grid.addWidget(self.unit_combo, 1, 2)
        grid.addWidget(QLabel("Résolution", objectName="muted"), 2, 0, 1, 3)
        grid.addWidget(self.dpi_spin, 3, 0, 1, 3)
        # Size hints come from the widest possible value; let the grid share the card width instead.
        for widget in (self.w_spin, self.h_spin, self.unit_combo, self.dpi_spin):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(64)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)
        self.size_summary = QLabel(objectName="muted", wordWrap=True)
        self.size_warning = QLabel(objectName="warning", wordWrap=True)
        self.size_warning.hide()
        self.format_combo = QComboBox()
        self.format_combo.addItem("JPEG", "jpeg")
        self.format_combo.addItem("PNG (sans perte)", "png")
        self.quality_slider = QSlider(Qt.Orientation.Horizontal, minimum=70, maximum=100)
        self.quality_label = QLabel(objectName="muted")
        self.quality_row = QWidget()
        q = QHBoxLayout(self.quality_row)
        q.setContentsMargins(0, 0, 0, 0)
        q.addWidget(QLabel("Qualité"))
        q.addWidget(self.quality_slider, 1)
        q.addWidget(self.quality_label)
        output_card = card(self.preset_combo, self.custom_box, self.size_summary, self.size_warning,
                           self.format_combo, self.quality_row)

        # Folder
        self.folder_label = QLabel(objectName="muted", wordWrap=True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change = QPushButton("Changer…", objectName="secondary")
        open_ = QPushButton("Ouvrir", objectName="secondary")
        change.clicked.connect(self._choose_folder)
        open_.clicked.connect(self._open_folder)
        convert_btn = QPushButton("Convertir des photos JPEG ↔ PNG…", objectName="secondary")
        convert_btn.setToolTip("Retrouver les photos d'un dossier et les convertir d'un format à l'autre")
        convert_btn.clicked.connect(self._open_converter)
        folder_card = card(self.folder_label, row(change, open_), convert_btn)

        # Recent
        self.recent = QListWidget()
        self.recent.setViewMode(QListWidget.ViewMode.IconMode)
        self.recent.setIconSize(QSize(62, 80))
        self.recent.setGridSize(QSize(84, 112))
        self.recent.setMovement(QListWidget.Movement.Static)
        self.recent.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.recent.setMinimumHeight(120)
        self.recent.setToolTip("Double-cliquez pour ouvrir la photo")
        self.recent_empty = QLabel("Les photos de cette session apparaîtront ici.", objectName="hint", wordWrap=True)

        header = QHBoxLayout()
        header.addWidget(QLabel("LPARC Photo", objectName="appTitle"))
        header.addStretch()
        header.addWidget(QLabel(f"v{__version__}", objectName="hint"))

        self.update_text = QLabel(wordWrap=True)
        update_button = QPushButton("Télécharger", objectName="primary")
        update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        update_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SITE_URL)))
        self.update_banner = QFrame(objectName="updateBanner")
        banner = QHBoxLayout(self.update_banner)
        banner.setContentsMargins(12, 10, 10, 10)
        banner.addWidget(self.update_text, 1)
        banner.addWidget(update_button)
        self.update_banner.hide()
        self.update_check = QCheckBox("Vérifier les mises à jour au démarrage")

        body = QWidget(objectName="sidebarBody")
        side = QVBoxLayout(body)
        side.setContentsMargins(18, 18, 18, 18)
        side.setSpacing(8)
        side.addLayout(header)
        side.addWidget(self.update_banner)
        side.addSpacing(8)
        for title, widget in (("Photo", photo_card), ("Caméra", camera_card), ("Arrière-plan", background_card),
                              ("Format de sortie", output_card), ("Dossier d'enregistrement", folder_card)):
            side.addWidget(section(title))
            side.addWidget(widget)
            side.addSpacing(6)
        side.addWidget(section("Dernières photos"))
        side.addWidget(self.recent_empty)
        side.addWidget(self.recent)
        side.addSpacing(6)
        side.addWidget(section("Mises à jour"))
        side.addWidget(self.update_check)
        side.addStretch()
        self.recent.hide()

        scroll = QScrollArea(widgetResizable=True, objectName="sidebar")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.setFixedWidth(380)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(scroll)
        self.setCentralWidget(central)

        icon = ASSETS / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    # -------------------------------------------------------------- settings

    def _load_settings(self) -> None:
        s = self.settings
        self.auto_check.setChecked(s.value("auto_frame", True, bool))
        self.mirror_check.setChecked(s.value("mirror", False, bool))
        self.zoom = min(MAX_ZOOM, max(1.0, float(s.value("zoom", 1.0))))
        self.auto_zoom = min(AUTO_ZOOM_MAX, max(AUTO_ZOOM_MIN, float(s.value("auto_zoom", 1.0))))
        custom = QColor(s.value("background_custom", "#e6e6e6"))
        if custom.isValid():
            self.custom_colour = (custom.red(), custom.green(), custom.blue())
        self.keep_original_check.setChecked(s.value("keep_original", False, bool))
        saved_background = s.value("background", "original")
        self._apply_background(saved_background if saved_background in ("white", "blue", "custom") and matting.available() else "original")
        self.review_check.setChecked(s.value("review", True, bool))
        self.update_check.setChecked(s.value("check_updates", True, bool))
        self.timer_combo.setCurrentIndex(max(0, self.timer_combo.findData(int(s.value("countdown", 0)))))
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(s.value("format", "jpeg"))))
        self.quality_slider.setValue(int(s.value("quality", 95)))
        self.unit_combo.setCurrentIndex(max(0, self.unit_combo.findData(s.value("custom_unit", "mm"))))
        self._apply_unit_ranges()
        self.w_spin.setValue(float(s.value("custom_w", 35)))
        self.h_spin.setValue(float(s.value("custom_h", 45)))
        self.dpi_spin.setValue(int(s.value("custom_dpi", 300)))
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(s.value("preset", DEFAULT_PRESET))))
        self.output_dir = Path(s.value("output_dir", str(default_output_dir())))
        self._refresh_folder_label()
        if geometry := s.value("geometry"):
            self.restoreGeometry(geometry)
        else:
            self.resize(1240, 780)
        self._sync_controls()

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("auto_frame", self.auto_check.isChecked())
        s.setValue("mirror", self.mirror_check.isChecked())
        s.setValue("zoom", self.zoom)
        s.setValue("auto_zoom", self.auto_zoom)
        s.setValue("background", self.background)
        s.setValue("background_custom", QColor(*self.custom_colour).name())
        s.setValue("keep_original", self.keep_original_check.isChecked())
        s.setValue("review", self.review_check.isChecked())
        s.setValue("check_updates", self.update_check.isChecked())
        s.setValue("countdown", self.timer_combo.currentData())
        s.setValue("format", self.format_combo.currentData())
        s.setValue("quality", self.quality_slider.value())
        s.setValue("preset", self.preset_combo.currentData())
        s.setValue("custom_unit", self.unit_combo.currentData())
        s.setValue("custom_w", self.w_spin.value())
        s.setValue("custom_h", self.h_spin.value())
        s.setValue("custom_dpi", self.dpi_spin.value())
        s.setValue("output_dir", str(self.output_dir))
        if device := self._selected_device():
            s.setValue("camera_id", bytes(device.id()).hex())
        s.setValue("geometry", self.saveGeometry())

    # ---------------------------------------------------------------- wiring

    def _wire(self) -> None:
        self.camera.frameReady.connect(self._on_frame)
        self.camera.failed.connect(self._on_camera_failed)
        self.media.videoInputsChanged.connect(self._populate_cameras)
        self.camera_combo.currentIndexChanged.connect(self._start_selected_camera)
        self.view.dragged.connect(self._on_drag)
        self.view.wheeled.connect(self._on_wheel)
        self.review.accepted.connect(self._save_pending)
        self.review.rejected.connect(self._retake)
        self.updates.available.connect(self._on_update_available)
        self.bg_picker.chosen.connect(self._on_background_chosen)
        self.review.backgrounds.chosen.connect(self._on_background_chosen)
        self.capture_btn.clicked.connect(self._capture_requested)
        self.matricule.textChanged.connect(self._clear_matricule_error)
        self.auto_check.toggled.connect(self._sync_controls)
        self.mirror_check.toggled.connect(lambda on: setattr(self.view, "mirror", on))
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v} %"))
        self.quality_label.setText(f"{self.quality_slider.value()} %")
        self.format_combo.currentIndexChanged.connect(self._sync_controls)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        for spin in (self.w_spin, self.h_spin, self.dpi_spin):
            spin.valueChanged.connect(self._update_size_summary)
        self.recent.itemDoubleClicked.connect(lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole))))
        self.view.mirror = self.mirror_check.isChecked()

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._primary_action)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._cancel_action)

    def _sync_controls(self) -> None:
        auto = self.auto_check.isChecked()
        low, high, value = (AUTO_ZOOM_MIN, AUTO_ZOOM_MAX, self.auto_zoom) if auto else (1.0, MAX_ZOOM, self.zoom)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setRange(int(low * 100), int(high * 100))
        self.zoom_slider.setValue(int(value * 100))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{value:.1f}×")
        self.framing_hint.setText("Le cadre suit le visage. Molette pour serrer ou élargir, glisser pour cadrer à la main." if auto
                                  else "Glissez l'image pour recadrer, molette pour zoomer.")
        self.quality_row.setVisible(self.format_combo.currentData() == "jpeg")
        self.custom_box.setVisible(self.preset_combo.currentData() == "custom")

    # --------------------------------------------------------------- camera

    def start(self) -> None:
        """Called once the window is shown: ask for camera access where the OS requires it."""
        if self.update_check.isChecked():
            self.updates.check()
        app = QApplication.instance()
        permission = QCameraPermission()
        status = app.checkPermission(permission)
        if status == Qt.PermissionStatus.Denied:
            self._show_permission_denied()
        elif status == Qt.PermissionStatus.Granted or not getattr(sys, "frozen", False):
            # Unbundled dev runs inherit the terminal's camera permission and have no Info.plist to request with.
            self._populate_cameras()
        else:
            self._show_message("Autorisation de la caméra", "Autorisez l'accès à la caméra dans la fenêtre du système.")
            app.requestPermission(permission, self, self._on_permission)

    def _on_update_available(self, version: str) -> None:
        self.update_text.setText(f"La version {version} est disponible.")
        self.update_banner.show()

    def _on_permission(self, permission) -> None:
        if QApplication.instance().checkPermission(permission) == Qt.PermissionStatus.Granted:
            self._populate_cameras()
        else:
            self._show_permission_denied()

    def _show_permission_denied(self) -> None:
        url = ("x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
               if sys.platform == "darwin" else "ms-settings:privacy-webcam")
        self._show_message("Accès à la caméra refusé",
                           "LPARC Photo a besoin de la caméra. Autorisez-la dans les réglages de confidentialité, puis relancez l'application.",
                           "Ouvrir les réglages", lambda: QDesktopServices.openUrl(QUrl(url)))

    def _populate_cameras(self) -> None:
        current = self._selected_device()
        wanted = bytes(current.id()).hex() if current else self.settings.value("camera_id", "")
        devices = Camera.devices()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        for device in devices:
            self.camera_combo.addItem(device.description(), device)
        index = next((i for i, d in enumerate(devices) if bytes(d.id()).hex() == wanted), None)
        if index is None:
            default = QMediaDevices.defaultVideoInput()
            index = next((i for i, d in enumerate(devices) if d.id() == default.id()), 0)
        self.camera_combo.setCurrentIndex(index)
        self.camera_combo.blockSignals(False)
        if not devices:
            self.camera.stop()
            self.camera_info.setText("")
            self._show_message("Aucune caméra détectée", "Branchez une webcam ou activez la caméra, puis réessayez.",
                               "Réessayer", self._populate_cameras)
            return
        if current is None or bytes(current.id()).hex() != bytes(devices[index].id()).hex():
            self._start_selected_camera()

    def _selected_device(self):
        return self.camera_combo.currentData()

    def _start_selected_camera(self) -> None:
        device = self._selected_device()
        if device is None:
            return
        self.frame_size = self.crop = self.face = None
        self.frames_since_start = 0
        self._show_message("Démarrage de la caméra…", device.description())
        self.camera.start(device)
        fmt = self.camera.format
        self.camera_info.setText(f"{fmt.resolution().width()} × {fmt.resolution().height()} · {fmt.maxFrameRate():.0f} ips"
                                 if fmt else "")
        QTimer.singleShot(NO_FRAME_TIMEOUT_MS, self._check_frames_arrived)

    def _check_frames_arrived(self) -> None:
        if self.frames_since_start == 0 and self._selected_device() is not None:
            self._show_message("La caméra ne renvoie pas d'image",
                               "Elle est peut-être utilisée par une autre application (Teams, Zoom…) ou l'accès est bloqué.",
                               "Réessayer", self._start_selected_camera)

    def _on_camera_failed(self, message: str) -> None:
        self._show_message("Problème de caméra", message, "Réessayer", self._start_selected_camera)

    def _show_message(self, title: str, body: str, button: str | None = None, action=None) -> None:
        self.message.show_message(title, body, button, action)
        self.stack.setCurrentIndex(MESSAGE)

    # -------------------------------------------------------------- framing

    def output_size(self) -> OutputSize:
        preset = preset_by_key(self.preset_combo.currentData())
        if preset.size is not None:
            return preset.size
        dpi = self.dpi_spin.value()
        if self.unit_combo.currentData() == "mm":
            return OutputSize(mm_to_px(self.w_spin.value(), dpi), mm_to_px(self.h_spin.value(), dpi), dpi)
        return OutputSize(int(self.w_spin.value()), int(self.h_spin.value()), dpi)

    def _on_frame(self, image: QImage) -> None:
        self.frames_since_start += 1
        if self.stack.currentIndex() == MESSAGE and self.frames_since_start == 1:
            self.stack.setCurrentIndex(LIVE)
        if self.stack.currentIndex() != LIVE:
            return
        w, h = image.width(), image.height()
        if (w, h) != self.frame_size:
            self.frame_size = (w, h)
            self.crop = self.face = None
            self._update_size_summary()

        now = time.monotonic()
        auto = self.auto_check.isChecked()
        if auto and now - self.last_detect >= DETECT_EVERY_S:
            self.last_detect = now
            small = image.scaledToWidth(min(480, w), Qt.TransformationMode.FastTransformation)
            if face := imaging.detect_face(qimage_to_rgb(small)):
                self.face = face.scaled(w / small.width())
                self.face_seen_at = now
        self.face_locked = auto and self.face is not None and now - self.face_seen_at < FACE_HOLD_S

        aspect = self.output_size().aspect
        if self.face_locked:
            target = face_crop_rect(w, h, aspect, self.face, self.auto_zoom)
            hint = "Visage détecté · cadrage automatique"
        else:
            target = crop_rect(w, h, aspect, self.zoom, (self.manual_center[0] * w, self.manual_center[1] * h))
            hint = "Aucun visage détecté · placez la personne face à la caméra" if auto else ""
        self.crop = smooth_rect(self.crop, target, 0.3 if self.face_locked else 1.0)
        self.view.set_frame(image, self.crop, self.face_locked, hint)

    def _on_drag(self, dx: float, dy: float) -> None:
        if self.frame_size is None:
            return
        if self.auto_check.isChecked():
            # Start manual framing from where the automatic frame currently is.
            if self.crop:
                self._adopt_crop_as_manual(self.crop)
            self.auto_check.setChecked(False)
            self.toast.show_text("Cadrage manuel")
        w, h = self.frame_size
        cx, cy = self.manual_center
        rect = crop_rect(w, h, self.output_size().aspect, self.zoom, (cx * w + dx, cy * h + dy))
        self.manual_center = (rect.center[0] / w, rect.center[1] / h)

    def _adopt_crop_as_manual(self, crop: Rect) -> None:
        w, h = self.frame_size
        full = crop_rect(w, h, self.output_size().aspect)
        self.zoom = min(MAX_ZOOM, max(1.0, full.h / crop.h))
        self.manual_center = (crop.center[0] / w, crop.center[1] / h)

    def _on_wheel(self, notches: float) -> None:
        current = self.auto_zoom if self.auto_check.isChecked() else self.zoom
        self.zoom_slider.setValue(int(round(current * 1.08 ** notches * 100)))  # the slider clamps to its range

    def _on_zoom_slider(self, value: int) -> None:
        if self.auto_check.isChecked():
            self.auto_zoom = value / 100
        else:
            self.zoom = value / 100
        self.zoom_label.setText(f"{value / 100:.1f}×")

    # ----------------------------------------------------------- background

    def _background_colour(self) -> matting.Colour | None:
        return {"white": matting.WHITE, "blue": matting.LIGHT_BLUE, "custom": self.custom_colour}.get(self.background)

    def _on_background_chosen(self, key: str) -> None:
        if key == "custom":
            colour = QColorDialog.getColor(QColor(*self.custom_colour), self, "Couleur de l'arrière-plan")
            if not colour.isValid():  # dialog cancelled: keep what was selected
                self._apply_background(self.background)
                return
            self.custom_colour = (colour.red(), colour.green(), colour.blue())
        self._apply_background(key)
        if self.pending is not None:
            self._show_review()

    def _apply_background(self, key: str) -> None:
        self.background = key
        replaceable = matting.available()
        for picker in (self.bg_picker, self.review.backgrounds):
            picker.set_colours(matting.LIGHT_BLUE, self.custom_colour)
            picker.set_replacement_enabled(replaceable)
            picker.select(key)
        self.keep_original_check.setEnabled(key != "original")
        if not replaceable:
            self.bg_hint.setText("Le remplacement du fond n'est pas disponible dans cette installation.")
        elif key == "original":
            self.bg_hint.setText("La photo garde son arrière-plan réel.")
        else:
            self.bg_hint.setText("Le fond est remplacé à la prise de vue. Un siège sans dossier haut donne le meilleur résultat.")

    def _photo_for(self, capture: Capture):
        """The final image for `capture` with the selected background."""
        colour = self._background_colour()
        if colour is not None:
            try:
                if capture.alpha is None:
                    capture.alpha = matting.alpha_matte(capture.pixels)
                return imaging.render(matting.composite(capture.pixels, capture.alpha, colour), capture.size)
            except Exception as error:  # a broken install must not lose the photo
                self._apply_background("original")
                self.toast.show_text(f"Remplacement du fond impossible : {error}", "error")
        return imaging.render(capture.pixels, capture.size)

    # --------------------------------------------------------------- output

    def _apply_unit_ranges(self) -> None:
        mm = self.unit_combo.currentData() == "mm"
        for spin in (self.w_spin, self.h_spin):
            spin.setDecimals(1 if mm else 0)
            spin.setRange(5, 500) if mm else spin.setRange(50, 8000)
            spin.setSuffix(" mm" if mm else " px")

    def _on_unit_changed(self) -> None:
        dpi = self.dpi_spin.value()
        w, h = self.w_spin.value(), self.h_spin.value()
        to_mm = self.unit_combo.currentData() == "mm"
        self._apply_unit_ranges()
        self.w_spin.setValue(px_to_mm(int(w), dpi) if to_mm else mm_to_px(w, dpi))
        self.h_spin.setValue(px_to_mm(int(h), dpi) if to_mm else mm_to_px(h, dpi))
        self._update_size_summary()

    def _on_preset_changed(self) -> None:
        if self.preset_combo.currentData() == "custom":
            # Start the custom size from whatever was selected before.
            previous = self.settings.value("preset", DEFAULT_PRESET)
            base = preset_by_key(previous).size if previous != "custom" else None
            if base is not None:
                self.dpi_spin.setValue(base.dpi)
                mm = self.unit_combo.currentData() == "mm"
                self.w_spin.setValue(px_to_mm(base.width_px, base.dpi) if mm else base.width_px)
                self.h_spin.setValue(px_to_mm(base.height_px, base.dpi) if mm else base.height_px)
        self.settings.setValue("preset", self.preset_combo.currentData())
        self.crop = None
        self._sync_controls()
        self._update_size_summary()

    def _update_size_summary(self) -> None:
        size = self.output_size()
        self.size_summary.setText(size.describe())
        self.crop = None
        if self.frame_size:
            full = crop_rect(*self.frame_size, size.aspect)
            if full.w < size.width_px or full.h < size.height_px:
                self.size_warning.setText(f"La caméra ({self.frame_size[0]} × {self.frame_size[1]}) fournit moins de pixels "
                                          "que demandé : la photo sera agrandie et moins nette.")
                self.size_warning.show()
                return
        self.size_warning.hide()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier d'enregistrement", str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self._refresh_folder_label()

    def _open_converter(self) -> None:
        from .convert_dialog import ConvertDialog

        folder = self.output_dir if self.output_dir.is_dir() else Path.home()
        dialog = ConvertDialog(folder, self.format_combo.currentData(), self.quality_slider.value(), self)
        dialog.exec()

    def _open_folder(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))

    def _refresh_folder_label(self) -> None:
        home = str(Path.home())
        path = str(self.output_dir)
        self.folder_label.setText("~" + path[len(home):] if path.startswith(home) else path)
        self.folder_label.setToolTip(path)

    def _path_for(self, matricule: str) -> Path:
        return self.output_dir / f"{matricule}{imaging.FORMATS[self.format_combo.currentData()]}"

    # -------------------------------------------------------------- capture

    def _primary_action(self) -> None:
        if self.stack.currentIndex() == REVIEW:
            self._save_pending()
        elif self.stack.currentIndex() == LIVE:
            self._capture_requested()

    def _cancel_action(self) -> None:
        if self.stack.currentIndex() == REVIEW:
            self._retake()
        elif self.capturing:
            self._countdown_left = 0
            self.capturing = False
            self.view.countdown = 0
            self._set_busy(False)
            self.toast.show_text("Prise de vue annulée", "error")

    def _clear_matricule_error(self) -> None:
        self.matricule_msg.hide()
        self.matricule.setProperty("invalid", False)
        self.matricule.style().polish(self.matricule)

    def _matricule_failed(self, message: str) -> None:
        self.matricule_msg.setText(message)
        self.matricule_msg.show()
        self.matricule.setProperty("invalid", True)
        self.matricule.style().polish(self.matricule)
        self.matricule.setFocus()

    def _capture_requested(self) -> None:
        if self.capturing:
            return
        matricule = self.matricule.text().strip()
        if error := matricule_error(matricule):
            self._matricule_failed(error)
            return
        if self.camera.latest is None or self.crop is None:
            self.toast.show_text("La caméra n'est pas encore prête", "error")
            return
        path = self._path_for(matricule)
        if path.exists() and not self._confirm_replace(path, matricule):
            return
        self.capturing = True
        self._set_busy(True)
        self._countdown_left = self.timer_combo.currentData()
        self._tick()

    def _tick(self) -> None:
        if not self.capturing:
            return
        if self._countdown_left > 0:
            self.view.countdown = self._countdown_left
            self._countdown_left -= 1
            QTimer.singleShot(1000, self._tick)
            return
        self.view.countdown = 0
        self._take(self.matricule.text().strip())

    def _take(self, matricule: str) -> None:
        image = self.camera.latest
        crop = self.crop if self.frame_size == (image.width(), image.height()) else None
        if crop is None:
            crop = crop_rect(image.width(), image.height(), self.output_size().aspect)
        size = self.output_size()
        pixels = imaging.extract(qimage_to_rgb(image), crop)
        capture = Capture(matricule, pixels, size, imaging.assess(pixels, size),
                          self.face_locked if self.auto_check.isChecked() else None)
        self.view.flash()
        self.capturing = False
        if self.review_check.isChecked():
            self.pending = capture
            self._show_review()
            QTimer.singleShot(180, lambda: self.pending is not None and self.stack.setCurrentIndex(REVIEW))
        else:
            self._write(capture)
            self._set_busy(False)

    def _show_review(self) -> None:
        c = self.pending
        photo = self._photo_for(c)
        self.review.show_result(rgb_to_qimage(np.asarray(photo)), c.matricule, c.size, c.report, c.face_found)

    def _retake(self) -> None:
        self.pending = None
        self._set_busy(False)
        self.stack.setCurrentIndex(LIVE)

    def _save_pending(self) -> None:
        if self.pending is None:
            return
        if self._write(self.pending):
            self.pending = None
            self._set_busy(False)
            self.stack.setCurrentIndex(LIVE)

    def _write(self, capture: Capture) -> bool:
        path = self._path_for(capture.matricule)
        photo = self._photo_for(capture)
        fmt, quality = self.format_combo.currentData(), self.quality_slider.value()
        try:
            imaging.save(photo, path, fmt, capture.size.dpi, quality)
            if self._background_colour() is not None and self.keep_original_check.isChecked():
                original = imaging.render(capture.pixels, capture.size)
                imaging.save(original, path.parent / ORIGINALS_DIR / path.name, fmt, capture.size.dpi, quality)
        except OSError as error:
            QMessageBox.critical(self, "Enregistrement impossible", f"La photo n'a pas pu être enregistrée dans\n{path}\n\n{error}")
            return False
        self.toast.show_text(f"✓  Photo {path.name} enregistrée")
        self._add_recent(path, photo)
        self.matricule.clear()
        self.matricule.setFocus()
        return True

    def _set_busy(self, busy: bool) -> None:
        self.capture_btn.setEnabled(not busy)
        self.matricule.setReadOnly(busy)

    def _confirm_replace(self, path: Path, matricule: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Photo existante")
        box.setText(f"Une photo existe déjà pour le matricule « {matricule} ».")
        box.setInformativeText("Voulez-vous la remplacer par une nouvelle photo ?")
        existing = QPixmap(str(path))
        if not existing.isNull():
            box.setIconPixmap(existing.scaledToHeight(150, Qt.TransformationMode.SmoothTransformation))
        replace = box.addButton("Remplacer", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is replace

    def _add_recent(self, path: Path, photo) -> None:
        thumb = rgb_to_qimage(np.asarray(photo.convert("RGB")))
        item = QListWidgetItem(QIcon(QPixmap.fromImage(thumb.scaledToHeight(160, Qt.TransformationMode.SmoothTransformation))), path.stem)
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(str(path))
        self.recent.insertItem(0, item)
        while self.recent.count() > RECENT_LIMIT:
            self.recent.takeItem(self.recent.count() - 1)
        self.recent_empty.hide()
        self.recent.show()

    # ------------------------------------------------------------ lifecycle

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.move((self.stack.width() - self.toast.width()) // 2, 24)

    def closeEvent(self, event) -> None:
        self._save_settings()
        self.camera.stop()
        super().closeEvent(event)


def row(*widgets: QWidget) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def main() -> int:
    QApplication.setApplicationName("LPARC Photo")
    QApplication.setOrganizationName("LPARC")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    window = MainWindow()
    window.show()
    window.matricule.setFocus()
    QTimer.singleShot(0, window.start)
    return app.exec()
