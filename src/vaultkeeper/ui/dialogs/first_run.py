"""Confirm the two first-run choices that otherwise go wrong in silence.

NIT asks seven questions the first time it runs. Five of them the port can
answer for itself — it detects the edition, resolves the user-files folder, and
has working defaults for the rest, all reachable from Settings afterwards. Two
it cannot:

* **which installation**, when Steam, Beamdog and GOG are all present. Taking
  the first silently attaches the profile to a game folder the user may not
  play, and nothing on screen afterwards says which one was picked.
* **where the store goes**. It grows to the size of a whole mod collection, and
  the platform default is the system drive — wrong on the common arrangement of
  a small SSD and a large data disk.

Both are shown pre-filled with the best answer available, so the honest response
to this screen is usually to press Continue. It is shown once, and every field
on it remains editable in Settings.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


def _install_label(install) -> str:
    """A discovered install, described the way someone would recognise it."""
    kind = getattr(getattr(install, "kind", None), "name", "") or ""
    edition = getattr(getattr(install, "edition", None), "name", "") or ""
    marks = [m.title() for m in (kind, edition) if m and m != "UNKNOWN"]
    if getattr(install, "is_wine", False):
        marks.append("Wine")
    if getattr(install, "is_network", False):
        marks.append("network")
    suffix = f"  —  {', '.join(marks)}" if marks else ""
    return f"{install.root}{suffix}"


class FirstRunDialog(QDialog):
    """Two questions, both pre-answered."""

    def __init__(
        self,
        installs: list,
        store_options: list,
        recommended_store: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._installs = list(installs)
        self._store_options = list(store_options)

        self.setWindowTitle("Set up Vaultkeeper")
        self.setWindowIcon(R.get_icon("NIT_Icon_v5"))
        self.resize(680, 260)

        layout = QVBoxLayout(self)
        heading = QLabel("Confirm where your game and your mods live.")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        note = QLabel(
            "These are the two settings worth getting right up front. Both can be "
            "changed later under Settings."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()

        self.install_combo = QComboBox()
        for install in self._installs:
            self.install_combo.addItem(_install_label(install), str(install.root))
        install_row = QHBoxLayout()
        install_row.addWidget(self.install_combo, 1)
        browse_game = QPushButton("Browse…")
        browse_game.clicked.connect(self._browse_game)
        install_row.addWidget(browse_game)
        form.addRow("Neverwinter Nights:", _wrap(install_row))
        if len(self._installs) > 1:
            found = QLabel(f"{len(self._installs)} installations found — pick the one you play.")
            found.setEnabled(False)
            form.addRow("", found)

        self.store_combo = QComboBox()
        for option in self._store_options:
            self.store_combo.addItem(option.label, str(option.path))
        index = self.store_combo.findData(str(recommended_store))
        if index >= 0:
            self.store_combo.setCurrentIndex(index)
        store_row = QHBoxLayout()
        store_row.addWidget(self.store_combo, 1)
        browse_store = QPushButton("Browse…")
        browse_store.clicked.connect(self._browse_store)
        store_row.addWidget(browse_store)
        form.addRow("Keep mods in:", _wrap(store_row))
        hint = QLabel(
            "Downloaded archives and built installers live here, so it grows with "
            "your collection — tens of gigabytes is normal."
        )
        hint.setWordWrap(True)
        hint.setEnabled(False)
        form.addRow("", hint)
        layout.addLayout(form)
        layout.addStretch(1)

        buttons = QDialogButtonBox()
        buttons.addButton("Continue", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # -- Choices ------------------------------------------------------------ #
    @property
    def game_root(self) -> str:
        return self.install_combo.currentData() or self.install_combo.currentText()

    @property
    def store_root(self) -> str:
        return self.store_combo.currentData() or self.store_combo.currentText()

    def _browse_game(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Locate your Neverwinter Nights installation (the folder holding nwmain)"
        )
        if chosen:
            self.install_combo.insertItem(0, chosen, chosen)
            self.install_combo.setCurrentIndex(0)

    def _browse_store(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder for your mods")
        if chosen:
            self.store_combo.insertItem(0, chosen, chosen)
            self.store_combo.setCurrentIndex(0)

    # -- Whether to ask at all ---------------------------------------------- #
    @classmethod
    def worth_asking(cls, installs: list, store_options: list) -> bool:
        """Whether there is genuinely a choice to make.

        One installation and one place to put the store is not a question, and a
        dialog with nothing to decide is a dialog people learn to dismiss
        without reading — which is how the *next* one gets dismissed too.
        """
        return len(installs) > 1 or len(store_options) > 1


def _wrap(inner) -> QWidget:
    holder = QWidget()
    holder.setLayout(inner)
    inner.setContentsMargins(0, 0, 0, 0)
    return holder
