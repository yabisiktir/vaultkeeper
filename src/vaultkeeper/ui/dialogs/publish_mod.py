"""PublishMod — package a mod as a distributable ``.7z`` (VB ``PublishMod``).

Prompts for an optional **Version** (appended to the mod name) and publishes the
mod into its ``_Published`` folder via ``ProfileController.publish_mod``. The live
archive-name label mirrors VB ``LbArchiveName``. If the mod has an installer
wizard, publishing re-roots its file references under the archive folder and
restores the original afterwards (handled in the controller).

The *Generate Installation Guide* option (VB ``CbGuide``) is shown disabled — the
VB RTF guide templates are not bundled, so that step is deferred. Captions come
from ``PublishMod.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

_HEADING = "Package your Mod for publishing (Uploading)"
_VERSION_HELP = (
    "Version text is appended to the Mod Name. Leave it blank if you do not want "
    "the compressed file name to include the version."
)


class PublishMod(QDialog):
    """Version prompt + publish action for a single mod."""

    def __init__(self, controller, mod_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mod_name = mod_name
        self.setWindowTitle(f"Publish {mod_name}")
        self.setWindowIcon(R.get_icon("VBExtension_16x"))
        self.resize(520, 240)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_HEADING))

        form = QFormLayout()
        self.version_edit = QLineEdit()
        self.version_edit.textChanged.connect(self._update_archive_name)
        form.addRow("Version:", self.version_edit)
        layout.addLayout(form)

        help_label = QLabel(_VERSION_HELP)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.archive_label = QLabel()
        layout.addWidget(self.archive_label)

        self.guide_check = QCheckBox("Generate Installation Guide")
        self.guide_check.setEnabled(False)  # deferred (templates not bundled)
        layout.addWidget(self.guide_check)

        layout.addStretch(1)

        buttons = QDialogButtonBox()
        self.publish_button = buttons.addButton(
            "Publish", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.publish_button.clicked.connect(self._on_publish)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_archive_name()

    def _update_archive_name(self) -> None:
        self.archive_label.setText(
            self._controller.publish_zip_name(self._mod_name, self.version_edit.text())
        )

    def _on_publish(self) -> None:
        result = self._controller.publish_mod(
            self._mod_name, version=self.version_edit.text()
        )
        if result["ok"]:
            QMessageBox.information(self, "Publish Mod", result["message"])
            self.accept()
        else:
            QMessageBox.warning(self, "Publish Mod", result["message"])

    @classmethod
    def show_for(
        cls, controller, mod_name: str, parent: QWidget | None = None
    ) -> PublishMod:
        """Build and show the publish dialog for a mod."""
        dlg = cls(controller, mod_name, parent)
        dlg.show()
        return dlg
