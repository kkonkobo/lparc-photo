import pytest
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkReply

from lparc_photo import updates


@pytest.mark.parametrize("candidate,current,newer", [
    ("2.3.0", "2.2.0", True), ("2.2.1", "2.2.0", True), ("3.0", "2.9.9", True), ("2.10.0", "2.9.0", True),
    ("2.2.0", "2.2.0", False), ("2.2", "2.2.0", False), ("2.1.9", "2.2.0", False), ("v2.3.0", "2.2.0", True),
    ("garbage", "2.2.0", False), ("", "2.2.0", False),
])
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


@pytest.mark.parametrize("url,version", [
    ("https://github.com/kkonkobo/lparc-photo/releases/tag/v2.3.0", "2.3.0"),
    ("https://github.com/kkonkobo/lparc-photo/releases/tag/2.3.0/", "2.3.0"),
    ("https://github.com/kkonkobo/lparc-photo/releases", None),  # no release published
    ("https://lparc-photo.yibe.studio/latest", None),  # redirect not followed
    ("https://example.com/releases/tag/v2.3.0-beta", None),
])
def test_version_from_release_url(url, version):
    assert updates.version_from_release_url(url) == version


class FakeReply:
    def __init__(self, url, error=QNetworkReply.NetworkError.NoError):
        self._url, self._error, self.deleted = url, error, False

    def error(self):
        return self._error

    def url(self):
        return QUrl(self._url)

    def deleteLater(self):
        self.deleted = True


def run_check(qapp, url, error=QNetworkReply.NetworkError.NoError, current="2.2.0"):
    checker, seen = updates.UpdateChecker(current), []
    checker.available.connect(seen.append)
    reply = FakeReply(url, error)
    checker._finished(reply)
    assert reply.deleted
    return seen


def test_checker_announces_only_newer_versions(qapp):
    tag = "https://github.com/kkonkobo/lparc-photo/releases/tag/"
    assert run_check(qapp, tag + "v2.3.0") == ["2.3.0"]
    assert run_check(qapp, tag + "v2.2.0") == []
    assert run_check(qapp, tag + "v2.1.0") == []


def test_checker_is_silent_when_offline_or_confused(qapp):
    tag = "https://github.com/kkonkobo/lparc-photo/releases/tag/v9.9.9"
    assert run_check(qapp, tag, QNetworkReply.NetworkError.HostNotFoundError) == []
    assert run_check(qapp, tag, QNetworkReply.NetworkError.TimeoutError) == []
    assert run_check(qapp, "https://lparc-photo.yibe.studio/") == []
