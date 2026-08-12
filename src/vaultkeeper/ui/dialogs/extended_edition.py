"""Ask where the Enhanced Edition user-files folder is (VB ExtendedEditionDialogue).

Shown at first run when an Enhanced Edition install is found but its user-files
folder cannot be located — the folder NWN:EE only creates once it has been
launched at least once (``firsttimeexecution.htm``). The user browses to it, or
ticks *Disable Enhanced Edition detection at start-up* to stop the tool guessing
and set the folder themselves later (VB ``PrivateExtendedDisabled``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExtendedEditionDialog(QDialog):
    """Solicit the EE user-files folder, or let detection be turned off."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neverwinter Nights Enhanced Edition Information")

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel(
                "It looks like you have Neverwinter Nights: Enhanced Edition "
                "installed, but its user-files folder could not be found.\n\n"
                "Start the Enhanced Edition once to create it, then browse to it "
                "below — or disable detection and set the folder yourself later."
            )
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("User Files:"))
        self.user_folder_edit = QLineEdit()
        self.user_folder_edit.textChanged.connect(self._update_save_enabled)
        row.addWidget(self.user_folder_edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        outer.addLayout(row)

        self.disable_check = QCheckBox(
            "Disable Enhanced Edition detection at start-up"
        )
        self.disable_check.toggled.connect(self._update_save_enabled)
        outer.addWidget(self.disable_check)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self._update_save_enabled()

    # -- results ----------------------------------------------------------- #
    @property
    def user_folder(self) -> str:
        """The chosen folder, or "" when detection was disabled instead."""
        if self.detection_disabled:
            return ""
        return self.user_folder_edit.text().strip().rstrip("/\\")

    @property
    def detection_disabled(self) -> bool:
        return self.disable_check.isChecked()

    # -- internals --------------------------------------------------------- #
    def _folder_is_valid(self) -> bool:
        text = self.user_folder_edit.text().strip().rstrip("/\\")
        return bool(text) and Path(text).is_dir()

    def _update_save_enabled(self) -> None:
        """Save is available once a real folder is picked, or detection is off.

        VB ``MandatoryFoldersSpecified`` OR the disable box — either resolves the
        start-up question, which is the whole point of the dialog.
        """
        save = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setEnabled(self.detection_disabled or self._folder_is_valid())

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select the Enhanced Edition user-files folder"
        )
        if chosen:
            self.user_folder_edit.setText(chosen)
