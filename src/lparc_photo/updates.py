"""Tell the user when a newer version exists. One small request at start-up, silent when offline."""

import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

SITE_URL = "https://lparc-photo.yibe.studio"
# Redirects to the newest release page, whose address ends in the version: .../releases/tag/v2.2.0
LATEST_URL = SITE_URL + "/latest"
TIMEOUT_MS = 8000


def parse_version(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def version_from_release_url(url: str) -> str | None:
    match = re.search(r"/releases/tag/v?(\d+(?:\.\d+)*)/?$", url)
    return match.group(1) if match else None


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


class UpdateChecker(QObject):
    available = Signal(str)  # the newer version, e.g. "2.3.0"

    def __init__(self, current: str, parent: QObject | None = None):
        super().__init__(parent)
        self.current = current
        self.manager = QNetworkAccessManager(self)

    def check(self) -> None:
        request = QNetworkRequest(QUrl(LATEST_URL))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(TIMEOUT_MS)
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"LPARC-Photo/{self.current}")
        reply = self.manager.head(request)
        reply.finished.connect(lambda: self._finished(reply))

    def _finished(self, reply) -> None:
        # Offline, blocked or malformed: say nothing. A photo booth must not nag about the network.
        if reply.error() == QNetworkReply.NetworkError.NoError:
            latest = version_from_release_url(reply.url().toString())
            if latest and is_newer(latest, self.current):
                self.available.emit(latest)
        reply.deleteLater()
