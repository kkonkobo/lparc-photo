"""Window to find photos in a folder and convert a selection between JPEG and PNG."""

from pathlib import Path

from PySide6.QtCore import QFile, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import convert
from .convert import Photo

FORMAT_NAMES = {"jpeg": "JPEG", "png": "PNG"}
CHECK, NAME, FORMAT, SIZE, WEIGHT, NOTE = range(6)


def move_to_trash(path: Path) -> None:
    """Send to the system trash, so a mistaken conversion can still be undone."""
    if not QFile.moveToTrash(str(path)):
        raise OSError(f"impossible de mettre {path.name} à la corbeille")


class ConvertDialog(QDialog):
    def __init__(self, folder: Path, target: str = "jpeg", quality: int = 95, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Convertir des photos")
        self.setMinimumSize(900, 600)
        self.resize(1040, 680)
        self.folder = folder
        self.photos: list[Photo] = []
        self.unreadable: list[convert.Unreadable] = []

        # Folder
        self.folder_label = QLabel(objectName="muted", wordWrap=True)
        change = QPushButton("Changer de dossier…", objectName="secondary")
        change.clicked.connect(self._choose_folder)
        self.recursive_check = QCheckBox("Inclure les sous-dossiers")
        self.recursive_check.toggled.connect(self.rescan)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(self.recursive_check)
        folder_row.addWidget(change)

        # Detection summary and quick selection
        self.summary = QLabel(objectName="dialogSummary", wordWrap=True)
        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Sélectionner :", objectName="muted"))
        for text, rule in (("À convertir", "needed"), ("Les PNG", "png"), ("Les JPEG", "jpeg"), ("Tout", "all"), ("Aucune", "none")):
            button = QPushButton(text, objectName="secondary")
            button.clicked.connect(lambda _c=False, r=rule: self._select(r))
            select_row.addWidget(button)
        select_row.addStretch()

        # Table and preview
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Fichier", "Format", "Dimensions", "Taille", "Remarque"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        for column in (CHECK, FORMAT, SIZE, WEIGHT, NOTE):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(lambda item: item.column() == CHECK and self._update_action())
        self.table.currentCellChanged.connect(lambda row, *_: self._preview(row))
        self.table.cellDoubleClicked.connect(self._toggle_row)

        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, objectName="convertPreview")
        self.preview.setFixedSize(QSize(220, 284))
        self.preview_caption = QLabel(objectName="hint", wordWrap=True, alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview_caption.setFixedWidth(220)
        preview_col = QVBoxLayout()
        preview_col.addWidget(self.preview)
        preview_col.addWidget(self.preview_caption)
        preview_col.addStretch()
        middle = QHBoxLayout()
        middle.addWidget(self.table, 1)
        middle.addSpacing(8)
        middle.addLayout(preview_col)

        # Options
        self.to_jpeg = QRadioButton("JPEG")
        self.to_png = QRadioButton("PNG (sans perte)")
        self.target_group = QButtonGroup(self)
        self.target_group.addButton(self.to_jpeg)
        self.target_group.addButton(self.to_png)
        (self.to_png if target == "png" else self.to_jpeg).setChecked(True)
        self.to_jpeg.toggled.connect(self._on_target_changed)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal, minimum=70, maximum=100, value=quality)
        self.quality_slider.setFixedWidth(160)
        self.quality_label = QLabel(f"{quality} %", objectName="muted")
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v} %"))
        self.quality_box = QWidget()
        q = QHBoxLayout(self.quality_box)
        q.setContentsMargins(12, 0, 0, 0)
        q.addWidget(QLabel("Qualité"))
        q.addWidget(self.quality_slider)
        q.addWidget(self.quality_label)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Convertir en :"))
        target_row.addWidget(self.to_jpeg)
        target_row.addWidget(self.to_png)
        target_row.addWidget(self.quality_box)
        target_row.addStretch()

        self.keep_check = QCheckBox(f"Conserver les fichiers d'origine (dossier « {convert.ORIGINALS_DIR} »)")
        self.keep_check.setChecked(True)
        self.keep_check.setToolTip("Sinon, les fichiers d'origine sont mis à la corbeille.")
        self.replace_check = QCheckBox("Remplacer un fichier du même nom s'il existe déjà")
        self.replace_check.setToolTip("Le fichier remplacé est conservé ou mis à la corbeille, comme l'original.")
        options = QVBoxLayout()
        options.addLayout(target_row)
        options.addWidget(self.keep_check)
        options.addWidget(self.replace_check)

        self.action_hint = QLabel(objectName="muted")
        self.convert_button = QPushButton(objectName="primary")
        self.convert_button.setMinimumHeight(40)
        self.convert_button.clicked.connect(self._convert)
        close = QPushButton("Fermer", objectName="secondary")
        close.setMinimumHeight(40)
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.action_hint, 1)
        bottom.addWidget(close)
        bottom.addWidget(self.convert_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addLayout(folder_row)
        layout.addWidget(self.summary)
        layout.addLayout(select_row)
        layout.addLayout(middle, 1)
        layout.addLayout(options)
        layout.addLayout(bottom)

        self._on_target_changed()
        self.rescan()

    # ------------------------------------------------------------------ data

    def target(self) -> str:
        return "jpeg" if self.to_jpeg.isChecked() else "png"

    def rescan(self) -> None:
        self.folder_label.setText(str(self.folder))
        self.folder_label.setToolTip(str(self.folder))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.photos, self.unreadable = convert.scan(self.folder, self.recursive_check.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_table()
        self._select("needed")
        self._update_summary()
        if self.photos:
            self.table.setCurrentCell(0, NAME)
        else:
            self._preview(-1)

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.photos))
        for row, photo in enumerate(self.photos):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, CHECK, check)
            name = str(photo.path.relative_to(self.folder))
            self.table.setItem(row, NAME, QTableWidgetItem(name))
            self.table.setItem(row, FORMAT, QTableWidgetItem(FORMAT_NAMES[photo.format]))
            self.table.setItem(row, SIZE, QTableWidgetItem(f"{photo.width} × {photo.height}"))
            self.table.setItem(row, WEIGHT, QTableWidgetItem(convert.human_size(photo.bytes)))
            self.table.setItem(row, NOTE, QTableWidgetItem(self._note(photo)))
        self.table.blockSignals(False)

    def _note(self, photo: Photo) -> str:
        notes = []
        if not photo.extension_matches:
            notes.append(f"{FORMAT_NAMES[photo.format]} nommé « {photo.path.suffix} »")
        if photo.has_alpha:
            notes.append("transparence")
        return " · ".join(notes)

    def _checked_rows(self) -> list[int]:
        return [r for r in range(self.table.rowCount()) if self.table.item(r, CHECK).checkState() == Qt.CheckState.Checked]

    # ------------------------------------------------------------ selection

    def _select(self, rule: str) -> None:
        target = self.target()
        self.table.blockSignals(True)
        for row, photo in enumerate(self.photos):
            chosen = {"needed": convert.needs_conversion(photo, target), "png": photo.format == "png",
                      "jpeg": photo.format == "jpeg", "all": True, "none": False}[rule]
            self.table.item(row, CHECK).setCheckState(Qt.CheckState.Checked if chosen else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_action()

    def _toggle_row(self, row: int, _column: int) -> None:
        item = self.table.item(row, CHECK)
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _on_target_changed(self) -> None:
        self.quality_box.setVisible(self.to_jpeg.isChecked())
        if self.photos:
            self._select("needed")
            self._update_summary()

    def _update_summary(self) -> None:
        if not self.photos:
            text = "Aucune photo JPEG ou PNG dans ce dossier."
        else:
            counts = {f: sum(p.format == f for p in self.photos) for f in ("png", "jpeg")}
            text = f"{len(self.photos)} photo{'s' * (len(self.photos) > 1)} : {counts['png']} PNG, {counts['jpeg']} JPEG"
            if mismatched := sum(not p.extension_matches for p in self.photos):
                text += f" · {mismatched} avec une extension qui ne correspond pas au contenu"
            needed = sum(convert.needs_conversion(p, self.target()) for p in self.photos)
            text += f" · {needed} à convertir en {FORMAT_NAMES[self.target()]}"
        if self.unreadable:
            text += f" · {len(self.unreadable)} fichier{'s' * (len(self.unreadable) > 1)} illisible{'s' * (len(self.unreadable) > 1)} ignoré{'s' * (len(self.unreadable) > 1)}"
        self.summary.setText(text)

    def _update_action(self) -> None:
        rows = self._checked_rows()
        target = self.target()
        work = [r for r in rows if convert.needs_conversion(self.photos[r], target)]
        already = len(rows) - len(work)
        n = len(work)
        self.convert_button.setText(f"Convertir {n} photo{'s' * (n > 1)} en {FORMAT_NAMES[target]}" if n else "Convertir")
        self.convert_button.setEnabled(n > 0)
        hint = f"{len(rows)} sélectionnée{'s' * (len(rows) > 1)}"
        if already:
            hint += f", dont {already} déjà en {FORMAT_NAMES[target]} (ignorée{'s' * (already > 1)})"
        self.action_hint.setText(hint if rows else "Cochez les photos à convertir.")

    # ---------------------------------------------------------------- preview

    def _preview(self, row: int) -> None:
        if row < 0 or row >= len(self.photos):
            self.preview.setPixmap(QPixmap())
            self.preview.setText("")
            self.preview_caption.setText("")
            return
        photo = self.photos[row]
        pixmap = QPixmap(str(photo.path))
        if pixmap.isNull():
            self.preview.setText("Aperçu indisponible")
        else:
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
        dpi = f" · {photo.dpi} dpi" if photo.dpi else ""
        self.preview_caption.setText(f"{photo.path.name}\n{FORMAT_NAMES[photo.format]} · {photo.width} × {photo.height}{dpi}")

    # ------------------------------------------------------------- actions

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Dossier à convertir", str(self.folder))
        if folder:
            self.folder = Path(folder)
            self.rescan()

    def _convert(self) -> None:
        target = self.target()
        todo = [self.photos[r] for r in self._checked_rows() if convert.needs_conversion(self.photos[r], target)]
        if not todo:
            return
        if not self.keep_check.isChecked():
            answer = QMessageBox.question(
                self, "Fichiers d'origine",
                f"Les {len(todo)} fichiers d'origine seront mis à la corbeille après conversion. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return

        progress = QProgressDialog("Conversion…", "Arrêter", 0, len(todo), self)
        progress.setWindowTitle("Conversion")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        results = []
        for i, photo in enumerate(todo):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"{photo.path.name}  ({i + 1}/{len(todo)})")
            progress.setValue(i)
            QApplication.processEvents()
            results.append(convert.convert(photo, target, self.quality_slider.value(), self.keep_check.isChecked(),
                                           self.replace_check.isChecked(), discard=move_to_trash))
        progress.setValue(len(todo))
        self.last_results = results
        self._report(results, len(todo), target)
        self.rescan()

    def _report(self, results: list[convert.Result], planned: int, target: str) -> None:
        done = [r for r in results if r.status == "converted"]
        skipped = [r for r in results if r.status == "skipped"]
        failed = [r for r in results if r.status == "failed"]
        lines = [f"{len(done)} photo{'s' * (len(done) > 1)} convertie{'s' * (len(done) > 1)} en {FORMAT_NAMES[target]}."]
        if done and self.keep_check.isChecked():
            lines.append(f"Les originaux sont dans le dossier « {convert.ORIGINALS_DIR} ».")
        elif done:
            lines.append("Les originaux sont dans la corbeille.")
        if len(results) < planned:
            lines.append(f"Arrêté avant la fin : {planned - len(results)} non traitée{'s' * (planned - len(results) > 1)}.")
        detail = [f"Ignorée : {r.source.name} ({r.message})" for r in skipped] + \
                 [f"Échec : {r.source.name} ({r.message})" for r in failed]
        if skipped and any("existe déjà" in r.message for r in skipped):
            lines.append("Pour remplacer les fichiers existants, cochez « Remplacer un fichier du même nom ».")
        box = QMessageBox(self)
        box.setWindowTitle("Conversion terminée")
        box.setIcon(QMessageBox.Icon.Warning if failed else QMessageBox.Icon.Information)
        box.setText("\n".join(lines))
        if detail:
            box.setInformativeText(f"{len(skipped)} ignorée{'s' * (len(skipped) > 1)}, {len(failed)} échec{'s' * (len(failed) > 1)}.")
            box.setDetailedText("\n".join(detail))
        box.exec()
