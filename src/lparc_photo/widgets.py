"""Stage widgets: live preview with framing overlay, review screen, empty states, toast."""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .imaging import QualityReport, Rect
from .presets import OutputSize

STAGE_BG = QColor("#0b0c0f")
ACCENT = QColor("#4f8cff")
OK = QColor("#34d399")


def fit_rect(content_w: int, content_h: int, area: QRectF) -> QRectF:
    scale = min(area.width() / content_w, area.height() / content_h)
    w, h = content_w * scale, content_h * scale
    return QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)


def draw_pill(p: QPainter, text: str, anchor: QPointF, align: Qt.AlignmentFlag, color: QColor = QColor(0, 0, 0, 170)) -> None:
    fm = p.fontMetrics()
    w, h = fm.horizontalAdvance(text) + 24, fm.height() + 12
    x = anchor.x() - (w / 2 if align & Qt.AlignmentFlag.AlignHCenter else 0)
    rect = QRectF(x, anchor.y() - (h if align & Qt.AlignmentFlag.AlignBottom else 0), w, h)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(rect, h / 2, h / 2)
    p.setPen(QColor("#f2f4f7"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class CameraView(QWidget):
    """Shows the live frame, dims everything outside the crop and draws a face guide.
    Drag moves the crop, the mouse wheel zooms."""

    dragged = Signal(float, float)  # delta in frame pixels
    wheeled = Signal(float)  # wheel notches

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.image: QImage | None = None
        self.crop: Rect | None = None
        self.mirror = False
        self.face_locked = False
        self.hint = ""
        self.countdown = 0
        self._flash = 0.0
        self._drag_from: QPointF | None = None
        self._flash_anim = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=320)
        self._flash_anim.valueChanged.connect(self._set_flash)

    def set_frame(self, image: QImage, crop: Rect | None, face_locked: bool, hint: str) -> None:
        self.image, self.crop, self.face_locked, self.hint = image, crop, face_locked, hint
        self.update()

    def flash(self) -> None:
        self._flash_anim.start()

    def _set_flash(self, value: float) -> None:
        self._flash = value
        self.update()

    def _image_rect(self) -> QRectF:
        return fit_rect(self.image.width(), self.image.height(), QRectF(self.rect()).adjusted(16, 16, -16, -16))

    def _crop_on_screen(self, target: QRectF) -> QRectF:
        s = target.width() / self.image.width()
        x = self.crop.x * s
        if self.mirror:
            x = target.width() - x - self.crop.w * s
        return QRectF(target.x() + x, target.y() + self.crop.y * s, self.crop.w * s, self.crop.h * s)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), STAGE_BG)
        if self.image is None:
            return
        target = self._image_rect()
        p.save()
        if self.mirror:
            p.translate(target.center().x(), 0)
            p.scale(-1, 1)
            p.translate(-target.center().x(), 0)
        p.drawImage(target, self.image)
        p.restore()

        if self.crop is not None:
            crop = self._crop_on_screen(target)
            outside = QPainterPath()
            outside.addRect(target)
            hole = QPainterPath()
            hole.addRect(crop)
            p.fillPath(outside.subtracted(hole), QColor(0, 0, 0, 165))
            p.setPen(QPen(QColor(255, 255, 255, 230), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(crop)
            guide = QRectF(0, 0, crop.width() * 0.54, crop.height() * 0.56)
            guide.moveCenter(QPointF(crop.center().x(), crop.y() + crop.height() * 0.48))
            pen = QPen(OK if self.face_locked else QColor(255, 255, 255, 150), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawEllipse(guide)

            if self.countdown:
                font = QFont(self.font())
                font.setPointSizeF(crop.height() * 0.22)
                font.setWeight(QFont.Weight.Bold)
                p.setFont(font)
                p.setPen(QColor(255, 255, 255, 235))
                p.drawText(crop, Qt.AlignmentFlag.AlignCenter, str(self.countdown))
                p.setFont(self.font())

        p.setFont(self.font())
        draw_pill(p, f"{self.image.width()} × {self.image.height()}", target.topLeft() + QPointF(12, 12), Qt.AlignmentFlag.AlignLeft)
        if self.hint:
            color = QColor(OK.red(), OK.green(), OK.blue(), 200) if self.face_locked else QColor(0, 0, 0, 170)
            draw_pill(p, self.hint, QPointF(target.center().x(), target.bottom() - 14), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, color)
        if self._flash > 0:
            p.fillRect(target, QColor(255, 255, 255, int(220 * self._flash)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.image is not None:
            self._drag_from = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is None or self.image is None:
            return
        delta = event.position() - self._drag_from
        self._drag_from = event.position()
        s = self._image_rect().width() / self.image.width()
        dx = delta.x() / s
        self.dragged.emit(-dx if self.mirror else dx, delta.y() / s)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_from = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event) -> None:
        self.wheeled.emit(event.angleDelta().y() / 120)


class ImageFit(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        if self.image is None:
            return
        target = fit_rect(self.image.width(), self.image.height(), QRectF(self.rect()).adjusted(8, 8, -8, -8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawRoundedRect(target.translated(0, 6), 6, 6)
        p.drawImage(target, self.image)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(target)


BACKGROUNDS = (("original", "Original"), ("white", "Blanc"), ("blue", "Bleu clair"), ("custom", "Autre…"))


def swatch_icon(colour: QColor | None) -> QIcon:
    """A colour dot; None draws the "keep the real background" symbol."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    disc = QRectF(3, 3, size - 6, size - 6)
    if colour is None:
        p.setPen(QPen(QColor("#9aa0a6"), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(disc)
        p.drawLine(QPointF(9, 23), QPointF(23, 9))
    else:
        p.setPen(QPen(QColor(255, 255, 255, 70), 1.5))
        p.setBrush(colour)
        p.drawEllipse(disc)
    p.end()
    return QIcon(pixmap)


class BackgroundPicker(QWidget):
    """Original / white / light blue / custom. Emits the key the user clicked; the owner decides
    what happens (a click on "custom" opens a colour dialog) and calls `select` to show the result."""

    chosen = Signal(str)

    def __init__(self, columns: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        for i, (key, text) in enumerate(BACKGROUNDS):
            button = QPushButton(text, objectName="swatch", checkable=True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, k=key: self.chosen.emit(k))
            self.group.addButton(button)
            self.buttons[key] = button
            grid.addWidget(button, i // columns, i % columns)
        self.buttons["original"].setIcon(swatch_icon(None))
        self.buttons["white"].setIcon(swatch_icon(QColor(255, 255, 255)))

    def set_colours(self, blue: tuple[int, int, int], custom: tuple[int, int, int]) -> None:
        self.buttons["blue"].setIcon(swatch_icon(QColor(*blue)))
        self.buttons["custom"].setIcon(swatch_icon(QColor(*custom)))

    def select(self, key: str) -> None:
        self.buttons[key].setChecked(True)

    def set_replacement_enabled(self, enabled: bool) -> None:
        for key, button in self.buttons.items():
            button.setEnabled(enabled or key == "original")


def chip(text: str, level: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("chip")
    label.setProperty("level", level)
    return label


class ReviewView(QWidget):
    accepted = Signal()
    rejected = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("review")
        self.title = QLabel(objectName="reviewTitle", alignment=Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel(objectName="muted", alignment=Qt.AlignmentFlag.AlignCenter)
        self.image = ImageFit()
        self.backgrounds = BackgroundPicker(columns=4)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        retake = QPushButton("Reprendre   Échap", objectName="secondary")
        save = QPushButton("Enregistrer   ↵", objectName="primary")
        retake.clicked.connect(self.rejected)
        save.clicked.connect(self.accepted)
        for b in (retake, save):
            b.setMinimumHeight(44)
            b.setMinimumWidth(190)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        chips_row = QHBoxLayout()
        chips_row.addStretch()
        chips_row.addLayout(self.chips)
        chips_row.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(retake)
        buttons.addSpacing(12)
        buttons.addWidget(save)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.image, 1)
        picker_row = QHBoxLayout()
        picker_row.addStretch()
        picker_row.addWidget(QLabel("Fond", objectName="muted"))
        picker_row.addSpacing(4)
        picker_row.addWidget(self.backgrounds)
        picker_row.addStretch()
        layout.addLayout(picker_row)
        layout.addLayout(chips_row)
        layout.addSpacing(4)
        layout.addLayout(buttons)

    def show_result(self, image: QImage, matricule: str, size: OutputSize, report: QualityReport,
                    face_found: bool | None) -> None:
        """`face_found` is None when automatic framing was off, so detection never ran."""
        self.title.setText(f"Matricule {matricule}")
        self.subtitle.setText(size.describe())
        self.image.set_image(image)
        while (item := self.chips.takeAt(0)) is not None:
            item.widget().deleteLater()
        self.chips.addWidget(chip("Netteté OK", "ok") if not report.blurry else chip("Photo peut-être floue", "warn"))
        if report.too_dark:
            self.chips.addWidget(chip("Trop sombre", "warn"))
        elif report.too_bright:
            self.chips.addWidget(chip("Surexposée", "warn"))
        else:
            self.chips.addWidget(chip("Exposition OK", "ok"))
        if face_found is not None:
            self.chips.addWidget(chip("Visage détecté", "ok") if face_found else chip("Aucun visage détecté", "warn"))
        if report.upscaled:
            self.chips.addWidget(chip("Agrandie : caméra en basse résolution", "warn"))


class MessageView(QWidget):
    """Empty and error states for the stage."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = QLabel(objectName="messageTitle", alignment=Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel(objectName="muted", alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.body.setFixedWidth(460)
        self.button = QPushButton(objectName="secondary")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action = None
        self.button.clicked.connect(lambda: self._action and self._action())
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.title)
        body_row = QHBoxLayout()
        body_row.addStretch()
        body_row.addWidget(self.body)
        body_row.addStretch()
        layout.addLayout(body_row)
        layout.addSpacing(12)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def show_message(self, title: str, body: str, button: str | None = None, action=None) -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.button.setVisible(button is not None)
        self.button.setText(button or "")
        self._action = action


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.hide()
        self._timer = QTimer(self, singleShot=True, interval=2800)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str, level: str = "ok") -> None:
        self.setText(text)
        self.setProperty("level", level)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, 24)
        self.raise_()
        self.show()
        self._timer.start()
