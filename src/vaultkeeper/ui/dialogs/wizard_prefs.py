"""Installer-wizard SelectMany prompt (VB ``MsgPreferences``).

Presented at Create-Installer time when a mod's installer wizard defines optional
*preferences* (SelectMany). The user checks the ones they want; unchecked items are
excluded from the installer. **Continue** keeps the checked set; **None** excludes
every preference (VB's Cancel button).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class WizardPreferencesDialog(QDialog):
    """A checkbox list of optional wizard files (VB ``MsgPreferences``)."""

    def __init__(
        self,
        title: str,
        prompt: str,
        preferences: list[dict],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel(prompt)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._boxes: list[tuple[QCheckBox, str]] = []
        for pref in preferences:
            box = QCheckBox(pref["display"])
            box.setChecked(bool(pref.get("checked", True)))
            layout.addWidget(box)
            self._boxes.append((box, pref["key"]))

        buttons = QDialogButtonBox()
        self._continue = buttons.addButton(
            "Continue", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("None", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def checked_keys(self) -> set[str]:
        """The keys of the ticked preferences."""
        return {key for box, key in self._boxes if box.isChecked()}

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        title: str,
        prompt: str,
        preferences: list[dict],
    ) -> set[str] | None:
        """Show the dialog; return the kept keys, or ``None`` if the user chose *None*."""
        dlg = cls(title, prompt, preferences, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.checked_keys()
        return None  # VB "None" button → exclude every preference
