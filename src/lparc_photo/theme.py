"""Dark theme: the photo is the brightest thing on screen."""

from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

_STYLESHEET = """
* { color: #e8eaed; font-size: 13px; }
QMainWindow, #stage { background: #0b0c0f; }
#sidebar { background: #15181d; border-left: 1px solid #23272e; }
QScrollArea { background: transparent; border: none; }
#sidebarBody { background: #15181d; }

#appTitle { font-size: 17px; font-weight: 600; }
#muted, #hint { color: #9aa0a6; }
#hint { font-size: 12px; }
#sectionTitle { color: #9aa0a6; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
#error { color: #f87171; font-size: 12px; }
#warning { color: #fbbf24; font-size: 12px; }
#card { background: #1b1f25; border: 1px solid #262b33; border-radius: 10px; }
QDialog { background: #15181d; }
#dialogSummary { font-size: 14px; font-weight: 600; }
#convertPreview { background: #0b0c0f; border: 1px solid #262b33; border-radius: 8px; color: #6b7280; }
QTableWidget { background: #0f1115; alternate-background-color: #13161b; border: 1px solid #262b33; border-radius: 8px;
    gridline-color: transparent; selection-background-color: #22304a; selection-color: white; }
QTableWidget::item { padding: 4px 6px; }
QTableWidget::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3a414c; background: #0f1115; }
QTableWidget::indicator:checked { background: #4f8cff; border-color: #4f8cff; image: url(@ASSETS/check.png); }
QHeaderView::section { background: #1b1f25; color: #9aa0a6; border: none; border-bottom: 1px solid #262b33; padding: 6px; font-weight: 600; }
QRadioButton { spacing: 6px; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 8px; border: 1px solid #3a414c; background: #0f1115; }
QRadioButton::indicator:checked { border: 4px solid #4f8cff; background: white; }
QProgressDialog QLabel { min-width: 320px; }
#updateBanner { background: #16263f; border: 1px solid #2c4a7c; border-radius: 10px; }
#updateBanner QLabel { font-weight: 600; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #0f1115; border: 1px solid #2d333c; border-radius: 7px;
    padding: 6px 9px; min-height: 20px; selection-background-color: #4f8cff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #4f8cff; }
QLineEdit[invalid="true"] { border-color: #f87171; }
QAbstractSpinBox QLineEdit { background: transparent; border: none; padding: 0 0 0 4px; min-height: 0; }
QAbstractSpinBox { padding-right: 22px; }
QAbstractSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; }
QAbstractSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; }
QAbstractSpinBox::up-arrow { image: url(@ASSETS/chevron-up.png); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url(@ASSETS/chevron.png); width: 10px; height: 10px; }
QAbstractSpinBox::up-arrow:hover, QAbstractSpinBox::down-arrow:hover { width: 12px; height: 12px; }#matricule { font-size: 20px; font-weight: 600; padding: 9px 12px; }
QComboBox::drop-down { border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url(@ASSETS/chevron.png); width: 14px; height: 14px; }
QComboBox QAbstractItemView { background: #1b1f25; border: 1px solid #2d333c; selection-background-color: #2b3a55; outline: none; }

QPushButton { border-radius: 8px; padding: 8px 14px; font-weight: 600; }
QPushButton#primary { background: #4f8cff; color: white; border: none; }
QPushButton#primary:hover { background: #6a9dff; }
QPushButton#primary:pressed { background: #3f74d9; }
QPushButton#primary:disabled { background: #2a3445; color: #7d8794; }
QPushButton#secondary { background: #242932; border: 1px solid #323843; }
QPushButton#secondary:hover { background: #2c323c; }
QPushButton#capture { background: #4f8cff; color: white; border: none; font-size: 15px; min-height: 46px; border-radius: 10px; }
QPushButton#capture:hover { background: #6a9dff; }
QPushButton#capture:pressed { background: #3f74d9; }
QPushButton#capture:disabled { background: #2a3445; color: #7d8794; }
QPushButton#swatch { background: #242932; border: 1px solid #323843; padding: 7px 10px; font-weight: 500; text-align: left; }
QPushButton#swatch:hover { background: #2c323c; }
QPushButton#swatch:checked { background: #22304a; border-color: #4f8cff; color: white; }
QPushButton#swatch:disabled { color: #6b7280; }
QPushButton#link { background: transparent; border: none; color: #8fb3ff; padding: 2px 4px; font-weight: 500; }
QPushButton#link:hover { color: #b5ccff; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3a414c; background: #0f1115; }
QCheckBox::indicator:checked { background: #4f8cff; border-color: #4f8cff; image: url(@ASSETS/check.png); }
QCheckBox:disabled { color: #6b7280; }

QSlider::groove:horizontal { height: 4px; background: #2d333c; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4f8cff; border-radius: 2px; }
QSlider::handle:horizontal { background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:disabled { background: #4b5260; }
QSlider::sub-page:horizontal:disabled { background: #3a414c; }

QListWidget { background: transparent; border: none; }
QListWidget::item { border-radius: 6px; padding: 4px; color: #c4c8ce; }
QListWidget::item:hover { background: #222730; }
QListWidget::item:selected { background: #2b3a55; }

#chip { border-radius: 11px; padding: 4px 11px; font-size: 12px; font-weight: 600; }
#chip[level="ok"] { background: #12352a; color: #6ee7b7; }
#chip[level="warn"] { background: #3a2c0f; color: #fcd34d; }
#reviewTitle { font-size: 20px; font-weight: 600; }
#messageTitle { font-size: 18px; font-weight: 600; }
#toast { background: #1d2a22; color: #a7f3d0; border: 1px solid #275c44; border-radius: 10px; padding: 10px 16px; font-weight: 600; }
#toast[level="error"] { background: #3a1717; color: #fecaca; border-color: #7f2a2a; }
QToolTip { background: #1b1f25; color: #e8eaed; border: 1px solid #2d333c; padding: 4px 6px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #2d333c; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def stylesheet() -> str:
    return _STYLESHEET.replace("@ASSETS", ASSETS.as_posix())
