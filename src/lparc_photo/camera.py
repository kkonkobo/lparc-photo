"""Live camera feed through Qt Multimedia (AVFoundation on macOS, Media Foundation on Windows)."""

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QCameraFormat,
    QMediaCaptureSession,
    QMediaDevices,
    QVideoFrame,
    QVideoSink,
)

# More pixels than this only slows the preview down: even a 600 dpi ID photo
# needs about 1063 px of height.
MAX_PIXELS = 2560 * 1440
MIN_FPS = 14


def best_format(device: QCameraDevice) -> QCameraFormat | None:
    """Highest resolution at a usable frame rate, capped at MAX_PIXELS."""
    formats = list(device.videoFormats())
    if not formats:
        return None

    def area(f: QCameraFormat) -> int:
        return f.resolution().width() * f.resolution().height()

    fluid = [f for f in formats if f.maxFrameRate() >= MIN_FPS] or formats
    capped = [f for f in fluid if area(f) <= MAX_PIXELS]
    if not capped:
        return min(fluid, key=area)
    return max(capped, key=lambda f: (area(f), f.maxFrameRate()))


def qimage_to_rgb(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h, stride = image.width(), image.height(), image.bytesPerLine()
    buf = np.frombuffer(image.constBits(), np.uint8, count=stride * h)
    return buf.reshape(h, stride)[:, : w * 3].reshape(h, w, 3).copy()


def rgb_to_qimage(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    data = np.ascontiguousarray(rgb)
    return QImage(data.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class Camera(QObject):
    frameReady = Signal(QImage)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._session = QMediaCaptureSession(self)
        self._sink = QVideoSink(self)
        self._session.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._camera: QCamera | None = None
        self.latest: QImage | None = None
        self.format: QCameraFormat | None = None

    @staticmethod
    def devices() -> list[QCameraDevice]:
        return list(QMediaDevices.videoInputs())

    def start(self, device: QCameraDevice) -> None:
        self.stop()
        camera = QCamera(device, self)
        self.format = best_format(device)
        if self.format is not None:
            camera.setCameraFormat(self.format)
        camera.errorOccurred.connect(self._on_error)
        self._session.setCamera(camera)
        self._camera = camera
        camera.start()

    def stop(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._session.setCamera(None)
            self._camera.deleteLater()
            self._camera = None
        self.latest = None

    def _on_error(self, _error: QCamera.Error, message: str) -> None:
        self.failed.emit(message or "Erreur inconnue de la caméra.")

    def _on_frame(self, frame: QVideoFrame) -> None:
        image = frame.toImage()
        if image.isNull():
            return
        self.latest = image
        self.frameReady.emit(image)
