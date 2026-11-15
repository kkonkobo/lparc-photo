import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    from lparc_photo.theme import stylesheet

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(stylesheet())
    return app
