"""CreateNwnFolderDialog — create an isolated NWN folder for a profile (VB ``CreateNwnFolder``).

Pick a **target** folder to create and a **source** NWN install to copy from; on
Create the source's contents are cloned into the target (see
``game/create_nwn_folder.py``).  The chosen target is returned so the caller can
point the profile's Game Installation path at it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.game.create_nwn_folder import create_nwn_folder, default_target
from vaultkeeper.ui import geometry


class CreateNwnFolderDialog(QDialog):
    """Create a new NWN game folder for a profile by cloning a source install."""

    def __init__(
        self,
        *,
        profile_name: str = "",
        source: str = "",
        parent_dir: str = "",
        is_ee: bool = True,
        config_ini_source: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_ee = is_ee
        self._config_ini_source = config_ini_source
        self.created_path: str = ""
        self.setWindowTitle("Create Neverwinter Nights Folder")
        geometry.remember(self, "CreateNwnFolderDialog", 560, 220)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Create a separate game folder for this profile by copying an "
                "existing Neverwinter Nights installation into a new location."
            )
        )

        self._target = QLineEdit()
        if parent_dir and profile_name:
            self._target.setText(
                str(default_target(Path(parent_dir), profile_name, is_ee=is_ee))
            )
        layout.addLayout(self._path_row("New folder (target):", self._target))

        self._source = QLineEdit(source)
        layout.addLayout(self._path_row("Copy from (source):", self._source))

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        create = QPushButton("Create")
        create.clicked.connect(self._on_create)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(create)
        bar.addWidget(cancel)
        layout.addLayout(bar)

    def _path_row(self, label: str, edit: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse(edit))
        row.addWidget(browse)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder", edit.text())
        if folder:
            edit.setText(folder)

    def _on_create(self) -> None:
        target = self._target.text().strip()
        source = self._source.text().strip()
        if not target or not source:
            self._status.setText("Please choose both a target and a source folder.")
            return
        if (
            QMessageBox.question(
                self,
                "Create Neverwinter Nights Folder",
                f"Copy the contents of\n{source}\ninto\n{target}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = create_nwn_folder(
            Path(target),
            Path(source),
            is_ee=self._is_ee,
            config_ini_source=Path(self._config_ini_source)
            if self._config_ini_source
            else None,
        )
        if result.ok:
            self.created_path = target
            QMessageBox.information(
                self, "Create Neverwinter Nights Folder", result.message
            )
            self.accept()
        else:
            self._status.setText(result.message)
