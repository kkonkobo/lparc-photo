# PyInstaller spec. Build from the repo root: uv run pyinstaller packaging/lparc_photo.spec --noconfirm
# One-folder build (fast start-up). macOS gets a .app bundle, Windows a folder with "LPARC Photo.exe".

import os
import re
import sys

import cv2

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(SRC, "lparc_photo", "assets")
with open(os.path.join(SRC, "lparc_photo", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[SRC],
    datas=[
        (ASSETS, "lparc_photo/assets"),
        (os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"), "cv2/data"),
    ],
    excludes=["tkinter", "matplotlib", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
              "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)

# Optional Qt plugins (PDF image format, virtual keyboard) drag in QtPdf/QtQuick/QtQml, which the app never uses.
UNUSED = re.compile(r"Qt6?(Pdf|Quick|Qml|VirtualKeyboard)|qpdf|platforminputcontexts|qtvirtualkeyboard", re.IGNORECASE)
a.binaries = [b for b in a.binaries if not UNUSED.search(b[0])]
a.datas = [d for d in a.datas if not UNUSED.search(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LPARC Photo",
    icon=os.path.join(ASSETS, "icon.png"),  # converted to .ico/.icns by Pillow
    console=False,
    upx=False,
    target_arch=os.environ.get("LPARC_TARGET_ARCH") or None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="LPARC Photo", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="LPARC Photo.app",
        icon=os.path.join(ASSETS, "icon.png"),
        bundle_identifier="org.lparc.photo",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "LPARC Photo",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSCameraUsageDescription": "LPARC Photo utilise la caméra pour prendre les photos d'identité.",
            # Without this, macOS hides iPhone Continuity Cameras from the app.
            "NSCameraUseContinuityCameraDeviceType": True,
        },
    )
