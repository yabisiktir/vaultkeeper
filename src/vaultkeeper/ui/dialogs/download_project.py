"""DownloadProjectDialog — download a Vault project's files (VB ``DownloadProject``).

Paste a Neverwinter Vault project URL, fetch its file list, tick the files to keep,
choose the target mod, and download them into that mod's ``_Downloads`` folder. The
scrape/download go through the controller (injected HTTP client), so the network is
mockable; the population and selection logic here is directly testable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.controller import _fmt_size


class DownloadProjectDialog(QDialog):
    """Fetch + download a Vault project into a mod's downloads folder."""

    def __init__(
        self,
        controller,
        mod_names: list[str],
        default_mod: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._files: list = []
        self.setWindowTitle("Download Project")
        self.setWindowIcon(R.get_icon("DownloadProject_16x"))
        self.resize(640, 480)

        layout = QVBoxLayout(self)

        # URL + fetch.
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Neverwinter Vault project URL…")
        self.fetch_button = QPushButton("Fetch")
        self.fetch_button.clicked.connect(self._on_fetch)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.fetch_button)
        layout.addLayout(url_row)

        # File list.
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["File", "Size"])
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.file_tree)

        # Target mod + download.
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Download into:"))
        self.mod_combo = QComboBox()
        self.mod_combo.addItems(mod_names)
        if default_mod and default_mod in mod_names:
            self.mod_combo.setCurrentText(default_mod)
        bottom.addWidget(self.mod_combo, 1)
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self._on_download)
        bottom.addWidget(self.download_button)
        layout.addLayout(bottom)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = QLabel("")
        layout.addWidget(self.status)

    # -- Population -------------------------------------------------------- #
    def populate_files(self, files: list) -> None:
        """Show the scraped files as checked rows."""
        self._files = files
        self.file_tree.clear()
        for vsi in files:
            item = QTreeWidgetItem(
                [vsi.description or vsi.filename, _fmt_size(vsi.byte_size)]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            self.file_tree.addTopLevelItem(item)
        self.status.setText(f"{len(files)} file(s) found." if files else "No files found.")

    def checked_files(self) -> list:
        """The files the user has ticked."""
        result = []
        for index in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                result.append(self._files[index])
        return result

    # -- Actions ----------------------------------------------------------- #
    def _on_fetch(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.status.setText("Fetching…")
        self.populate_files(self.controller.scrape_project(url))

    def _on_download(self) -> None:
        files = self.checked_files()
        mod = self.mod_combo.currentText()
        if not files or not mod:
            self.status.setText("Select a mod and at least one file.")
            return
        self.progress.setMaximum(len(files))

        def on_progress(index: int, total: int, vsi) -> None:
            self.progress.setValue(index)
            self.status.setText(f"Downloading {vsi.description or vsi.filename}…")

        results = self.controller.download_project(files, mod, on_progress=on_progress)
        self.progress.setValue(len(files))
        ok = sum(1 for r in results if r.ok)
        self.status.setText(f"Downloaded {ok} of {len(results)} file(s) into {mod}.")
