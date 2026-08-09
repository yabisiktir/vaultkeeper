"""ImportLegacyStore — migrate a legacy NIT Store into Vaultkeeper's native store.

The original tool auto-migrated its ``.NET BinaryFormatter`` data at startup; this
port surfaces it as an explicit action. The user browses to a legacy NIT Store
folder, the dialog lists the profiles it contains, and importing one migrates its
``nit.ModData_Format_NNN`` mod list (via the NRBF reader) into a native
``Data/<profile>.json`` — optionally making it the active profile. File/install
tables rebuild from disk (the hybrid strategy), so only the user metadata is imported.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


class ImportLegacyStore(QDialog):
    """Browse a legacy NIT Store and import one of its profiles."""

    def __init__(self, parent: QWidget | None = None, *, on_imported=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Legacy NIT Store")
        self.setWindowIcon(R.get_icon("SettingsCogBlue"))
        geometry.remember(self, "ImportLegacyStore", 560, 380)
        self._on_imported = on_imported

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Migrate a legacy NIT Store's profiles into Vaultkeeper:")
        )

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to a legacy NIT Store folder…")
        self.path_edit.textChanged.connect(self._refresh_profiles)
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        layout.addWidget(QLabel("Profiles found:"))
        self.profiles = QListWidget()
        layout.addWidget(self.profiles, 1)

        self.make_active = QCheckBox("Make the imported profile active")
        self.make_active.setChecked(True)
        layout.addWidget(self.make_active)

        self.status = QLabel("")
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._import)
        self.import_button.setEnabled(False)
        buttons.addWidget(self.import_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.profiles.currentRowChanged.connect(
            lambda r: self.import_button.setEnabled(r >= 0)
        )

        # Pre-fill a detected NIT Store so existing users can import in one click
        # (setting the text triggers _refresh_profiles, which lists its profiles).
        from vaultkeeper.ui.session import detect_legacy_store

        detected = detect_legacy_store()
        if detected is not None:
            self.path_edit.setText(str(detected))

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Select a legacy NIT Store")
        if folder:
            self.path_edit.setText(folder)

    def _refresh_profiles(self, text: str) -> None:
        from vaultkeeper.ui.session import list_legacy_profiles

        self.profiles.clear()
        self.import_button.setEnabled(False)
        root = text.strip()
        if not root or not (Path(root) / "Data").is_dir():
            self.status.setText("")
            return
        try:
            names = list_legacy_profiles(root)
        except OSError:
            names = []
        for name in names:
            self.profiles.addItem(name)
        self.status.setText(f"{len(names)} profile(s) found." if names else "No profiles found.")

    def _import(self) -> None:
        item = self.profiles.currentItem()
        if item is None:
            return
        profile = item.text()
        from vaultkeeper.ui.session import import_legacy_profile

        try:
            path = import_legacy_profile(
                self.path_edit.text().strip(),
                profile,
                make_active=self.make_active.isChecked(),
            )
        except Exception as ex:  # noqa: BLE001 - surface any migration failure
            QMessageBox.warning(self, "Import Legacy NIT Store", f"Import failed: {ex}")
            return
        self.status.setText(f"Imported '{profile}'.")
        QMessageBox.information(
            self,
            "Import Legacy NIT Store",
            f"Imported '{profile}' to {path.name}."
            + (" It is now the active profile." if self.make_active.isChecked() else ""),
        )
        if self._on_imported is not None:
            self._on_imported(profile)

    @classmethod
    def show_for(cls, parent: QWidget | None = None, *, on_imported=None) -> ImportLegacyStore:
        """Build and show the import dialog."""
        dlg = cls(parent, on_imported=on_imported)
        dlg.show()
        return dlg
