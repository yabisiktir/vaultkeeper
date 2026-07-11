"""ModPropertiesDialog — edit a mod's Rating / Best Weapon / Levels / Henchmen.

Ports the VB ``TlModProperties`` panel (NIT.Designer.vb — SbRating/SbWeapon/
TxLevelStart/TxLevelEnd/TxHenchmen), opened from the mod list's Properties action
(``MsProperties``). The original edits these inline in the mod-info area; the port
surfaces the same fields as a small dialog and persists them to ``ModData``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.state import Ratings, Weapon

#: "not specified" sentinel for the level/henchmen spinners (VB NullValue = -1).
_UNSET = -1


def _weapon_label(weapon: Weapon) -> str:
    return weapon.name.replace("_", " ").title().replace("Twobladed", "Two-Bladed")


class ModPropertiesDialog(QDialog):
    """Edit a single mod's rating, best weapon, level range and henchman count."""

    def __init__(self, mod_name: str, props: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Properties — {mod_name}")
        self._mod_name = mod_name

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.rating = QComboBox()
        for r in Ratings:
            self.rating.addItem(r.name.title(), r)
        self.rating.setCurrentIndex(self.rating.findData(props["rating"]))
        form.addRow("&Rating:", self.rating)

        self.weapon = QComboBox()
        for w in sorted(Weapon, key=lambda x: (x is not Weapon.NONE, _weapon_label(x))):
            self.weapon.addItem(_weapon_label(w), w)
        self.weapon.setCurrentIndex(self.weapon.findData(props["best_weapon"]))
        form.addRow("Best &Weapon:", self.weapon)

        self.level_start = self._level_spin(props["level_start"])
        form.addRow("Level &Start:", self.level_start)
        self.level_end = self._level_spin(props["level_end"])
        form.addRow("Level &End:", self.level_end)

        self.hench = QSpinBox()
        self.hench.setRange(_UNSET, 99)
        self.hench.setSpecialValueText("—")
        self.hench.setValue(props["hench_count"] if props["hench_count"] >= 0 else _UNSET)
        form.addRow("&Henchmen:", self.hench)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _level_spin(value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(_UNSET, 60)
        spin.setSpecialValueText("—")  # shown at the minimum (unspecified)
        spin.setValue(value if value >= 1 else _UNSET)
        return spin

    def values(self) -> dict:
        """The edited property values (level/henchmen ``-1`` = not specified)."""
        return {
            "rating": self.rating.currentData(),
            "best_weapon": self.weapon.currentData(),
            "level_start": self.level_start.value(),
            "level_end": self.level_end.value(),
            "hench_count": self.hench.value(),
        }
