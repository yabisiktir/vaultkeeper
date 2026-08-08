"""What to do with the downloads a fetch has just superseded (VB ``DownloadDeleteMsg``).

Shown after a download when the mod's folder still holds what looks like the
previous version. Three answers, and the order they appear in is the argument:

* **Keep in _History** — first, and the default. An old release of a mod is
  sometimes the only copy left anywhere; a folder costs nothing next to that.
* **Delete** — honours the recycle-bin preference, so it is still recoverable.
* **Leave them** — closing the dialog changes nothing.

Rows the matching is confident about arrive ticked; the rest are listed
unticked, because a folder is easier to tidy when you can see all of it, and
because the matching genuinely cannot tell two versions of a mod from two halves
of a set.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.controller import _fmt_size


class OldDownloadsDialog(QDialog):
    """Offers the superseded files for keeping or removing."""

    def __init__(self, mod_name: str, old, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._old = list(old)
        #: ``"history"`` | ``"delete"``; empty when the user left them alone.
        self.action = ""

        self.setWindowTitle("Previous Downloads")
        self.setWindowIcon(R.get_icon("DownloadProject_16x"))
        self.resize(640, 400)

        layout = QVBoxLayout(self)
        heading = QLabel(
            f"'{mod_name}' still holds files that the download appears to replace."
        )
        heading.setStyleSheet("font-weight: bold;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        note = QLabel(
            "Ticked files look like earlier versions of what was just downloaded. "
            "The rest are listed in case you want them gone too — check them before "
            "removing anything."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File", "Size"])
        self.files.setRootIsDecorated(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for entry in self._old:
            item = QTreeWidgetItem([entry.name, _size_of(entry.path)])
            item.setCheckState(
                0,
                Qt.CheckState.Checked if entry.suggested else Qt.CheckState.Unchecked,
            )
            item.setToolTip(0, str(entry.path))
            self.files.addTopLevelItem(item)
        layout.addWidget(self.files, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.history_button = QPushButton("Keep in _History")
        self.history_button.setToolTip(
            "Move them into the mod's _History folder, out of the way of the installer."
        )
        self.history_button.setDefault(True)
        self.history_button.clicked.connect(lambda: self._finish("history"))
        buttons.addWidget(self.history_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Remove them, honouring your recycle-bin setting.")
        self.delete_button.clicked.connect(lambda: self._finish("delete"))
        buttons.addWidget(self.delete_button)
        leave = QPushButton("Leave them")
        leave.clicked.connect(self.reject)
        buttons.addWidget(leave)
        layout.addLayout(buttons)

    def checked_paths(self) -> list:
        """The paths the user has ticked."""
        return [
            entry.path
            for index, entry in enumerate(self._old)
            if self.files.topLevelItem(index).checkState(0) == Qt.CheckState.Checked
        ]

    def _finish(self, action: str) -> None:
        if not self.checked_paths():
            self.reject()
            return
        self.action = action
        self.accept()


def _size_of(path) -> str:
    try:
        return _fmt_size(path.stat().st_size)
    except OSError:
        return ""
