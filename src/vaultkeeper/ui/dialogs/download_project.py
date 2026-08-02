"""DownloadProjectDialog — download a Vault project to create/update a mod.

Mirrors the VB ``DownloadProject`` experience: "Download a project from the
Neverwinter Vault to create or update a Mod". You paste the project's page address
(URL) and click **Retrieve**; the dialog derives an editable **Mod folder name** and
**Group**, lists the project's files (ticked to keep), and **Download** creates the
mod (if new) and pulls the files into its ``_Downloads`` folder, ready for Create
Installer. Required prerequisite projects are surfaced so they can be fetched too.

The scrape/download go through the controller (injected HTTP client), so the network
is mockable and the population/selection logic is directly testable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
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
    """Retrieve a Vault project and download it into a new/updated mod."""

    def __init__(
        self,
        controller,
        mod_names: list[str] | None = None,
        default_mod: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._files: list = []
        self._required: list[dict] = []
        self._name_touched = False
        #: Set while a transfer is running, so a second click cannot start one.
        self._busy = False
        self._files_total = 0
        self._file_index = 0
        self._file_label = ""
        self.setWindowTitle("Download Project")
        self.setWindowIcon(R.get_icon("DownloadProject_16x"))
        self.resize(640, 560)

        layout = QVBoxLayout(self)

        # Purpose + instructions (VB LbDownloadProject / LbDownloadHelp).
        heading = QLabel(
            "Download a project from the Neverwinter Vault to create or update a mod."
        )
        heading.setStyleSheet("font-weight: bold;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        hint = QLabel(
            "Enter the project's page address (URL) below and click Retrieve."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # URL + Retrieve (VB LbUrl "Project Web Address (URL)" / BtRetrieve).
        layout.addWidget(QLabel("Project web address (URL):"))
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://neverwintervault.org/project/…")
        self.url_edit.returnPressed.connect(self._on_fetch)
        self.retrieve_button = QPushButton("Retrieve")
        self.retrieve_button.clicked.connect(self._on_fetch)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.retrieve_button)
        layout.addLayout(url_row)

        # Project configuration: what mod the download becomes (VB "Project
        # Configuration": Mod Folder Name + Group + Project Files). Hidden until a
        # project is retrieved so the empty dialog isn't cluttered with blank fields.
        self.config_box = QGroupBox("Project configuration")
        config = QVBoxLayout(self.config_box)
        form = QFormLayout()
        self.project_label = QLabel("—")
        self.project_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Project:", self.project_label)
        self.mod_name_edit = QLineEdit(default_mod)
        self.mod_name_edit.setPlaceholderText("New mod folder name")
        self.mod_name_edit.textEdited.connect(self._on_name_edited)
        self.mod_name_edit.editingFinished.connect(self._render_files)
        form.addRow("Mod folder name:", self.mod_name_edit)
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItems(self._group_names())
        form.addRow("Group:", self.group_combo)
        config.addLayout(form)

        config.addWidget(QLabel("Project files (tick the ones to download):"))
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["File", "Size", "Status"])
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        config.addWidget(self.file_tree, 1)
        self.config_box.setVisible(False)
        layout.addWidget(self.config_box, 4)

        # Required prerequisite projects (VB Required Projects).
        self.required_label = QLabel("Required projects (double-click to load a URL):")
        self.required_label.setVisible(False)
        layout.addWidget(self.required_label)
        self.required_list = QTreeWidget()
        self.required_list.setHeaderLabels(["Required Project", "URL"])
        self.required_list.setRootIsDecorated(False)
        self.required_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.required_list.setMaximumHeight(96)
        self.required_list.setVisible(False)
        self.required_list.itemDoubleClicked.connect(self._on_required_double_clicked)
        layout.addWidget(self.required_list)

        # Keep content top-aligned and the button bar at the bottom when the
        # configuration area is hidden (empty state).
        layout.addStretch(1)

        # Actions.
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.download_button = QPushButton("Download")
        self.download_button.setToolTip("Download the ticked files into the mod's downloads")
        self.download_button.clicked.connect(self._on_download)
        self.download_button.setEnabled(False)
        buttons.addWidget(self.download_button)
        self.install_button = QPushButton("Install")
        self.install_button.setToolTip(
            "Download the ticked files, build the installer, and install the mod"
        )
        self.install_button.clicked.connect(self._on_install)
        self.install_button.setEnabled(False)
        buttons.addWidget(self.install_button)
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhDownloadProject", self))
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _group_names(self) -> list[str]:
        try:
            return self.controller.group_names()
        except Exception:
            return []

    # -- Population -------------------------------------------------------- #
    def populate_files(self, files: list) -> None:
        """Store the scraped files, reveal the configuration, and render the list."""
        self._files = files
        has_files = bool(files)
        self.config_box.setVisible(has_files)
        self.download_button.setEnabled(has_files)
        self.install_button.setEnabled(has_files)
        # Pre-fill the mod name + project label from the project title (VB derives
        # the Mod Folder Name from the project); respect a name the user has typed.
        title = files[0].project_title if files else ""
        if title:
            nice = self.controller.suggested_mod_name(title)
            self.project_label.setText(nice or title)
            if not self._name_touched and not self.mod_name_edit.text().strip():
                self.mod_name_edit.setText(nice)
        self._render_files()
        self.status.setText(
            f"{len(files)} file(s) found." if files else "No files found."
        )

    def _render_files(self) -> None:
        """(Re)build the file rows, flagging files already in the target mod's downloads."""
        from PySide6.QtGui import QBrush, QColor

        from vaultkeeper.vault.scraper_info import FileStatus

        self.controller.mark_download_status(self._files, self.mod_name_edit.text().strip())
        self.file_tree.clear()
        for vsi in self._files:
            downloaded = vsi.status == FileStatus.DOWNLOADED
            item = QTreeWidgetItem(
                [
                    vsi.description or vsi.filename,
                    _fmt_size(vsi.byte_size),
                    "Already downloaded" if downloaded else "",
                ]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Already-downloaded files are unticked by default (don't re-fetch) + dimmed.
            item.setCheckState(
                0, Qt.CheckState.Unchecked if downloaded else Qt.CheckState.Checked
            )
            if downloaded:
                dim = QBrush(QColor(0x88, 0x88, 0x88))
                for col in range(3):
                    item.setForeground(col, dim)
            self.file_tree.addTopLevelItem(item)

    def checked_files(self) -> list:
        """The files the user has ticked."""
        result = []
        for index in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                result.append(self._files[index])
        return result

    def populate_required(self, projects: list) -> None:
        """Show the project's required prerequisites (VB Required-Projects field)."""
        self._required = projects
        self.required_list.clear()
        for proj in projects:
            self.required_list.addTopLevelItem(
                QTreeWidgetItem([proj["title"], proj["url"]])
            )
        has = bool(projects)
        self.required_label.setVisible(has)
        self.required_list.setVisible(has)

    def _on_required_double_clicked(self, item: QTreeWidgetItem) -> None:
        """Load a required project's URL into the retrieve box (so it can be fetched)."""
        self.url_edit.setText(item.text(1))

    def _on_name_edited(self, _text: str) -> None:
        self._name_touched = True

    # -- Actions ----------------------------------------------------------- #
    def _on_fetch(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.status.setText("Retrieving…")
        self.populate_files(self.controller.scrape_project(url))
        self.populate_required(self.controller.project_required_projects(url))

    # -- Progress ---------------------------------------------------------- #
    def _start_transfer(self, count: int) -> None:
        """Show the progress bar and lock the buttons for the duration.

        The transfer runs on the UI thread, and a Vault file can be well over a
        gigabyte, so :meth:`_on_bytes` keeps the event loop turning while it does.
        That also means a second click would arrive *during* the first download —
        hence the lock.
        """
        self._busy = True
        for button in (self.retrieve_button, self.download_button, self.install_button):
            button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until the first bytes land
        self._files_total = count
        self._file_index = 0

    def _end_transfer(self) -> None:
        self._busy = False
        self.retrieve_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.install_button.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

    def _on_file(self, index: int, total: int, vsi) -> None:
        self._file_index = index
        self._file_label = vsi.description or vsi.filename or "file"
        self.status.setText(f"Downloading {self._file_label} ({index + 1} of {total})…")

    def _on_bytes(self, vsi, done: int, total: int) -> None:
        """Report progress through one file and let the window repaint."""
        from PySide6.QtWidgets import QApplication

        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(
                f"Downloading {self._file_label} "
                f"({self._file_index + 1} of {self._files_total}) — "
                f"{_fmt_size(done)} of {_fmt_size(total)}"
            )
        else:
            self.status.setText(
                f"Downloading {self._file_label} — {_fmt_size(done)} so far"
            )
        QApplication.processEvents()

    def _on_download(self) -> None:
        if self._busy:
            return
        files = self.checked_files()
        mod = self.mod_name_edit.text().strip()
        if not files:
            self.status.setText("Tick at least one file to download.")
            return
        if not mod:
            self.status.setText("Enter a mod folder name to download into.")
            self.mod_name_edit.setFocus()
            return
        group = self.group_combo.currentText().strip() or None
        self._start_transfer(len(files))
        try:
            results = self.controller.download_project(
                files, mod, group=group,
                on_progress=self._on_file, on_bytes=self._on_bytes,
            )
        finally:
            self._end_transfer()
        ok = sum(1 for r in results if r.ok)
        verb = "Updated" if ok else "No files downloaded to"
        self.status.setText(
            f"Downloaded {ok} of {len(results)} file(s). {verb} mod '{mod}'."
        )
        self._render_files()  # newly-downloaded files now show "Already downloaded"

    def _on_install(self) -> None:
        """Download the ticked files, build the installer, and install the mod."""
        if self._busy:
            return
        files = self.checked_files()
        mod = self.mod_name_edit.text().strip()
        if not files:
            self.status.setText("Tick at least one file to install.")
            return
        if not mod:
            self.status.setText("Enter a mod folder name to install into.")
            self.mod_name_edit.setFocus()
            return
        group = self.group_combo.currentText().strip() or None
        self._start_transfer(len(files))
        try:
            result = self.controller.install_downloaded_project(
                files, mod, group=group,
                on_progress=self._on_file, on_bytes=self._on_bytes,
            )
        finally:
            self._end_transfer()
        if result["built"]:
            self.status.setText(
                f"Installed '{mod}'. {result['install_message']}"
            )
        else:
            self.status.setText(
                f"Downloaded {result['downloaded']} of {result['total']} file(s), "
                f"but could not build the installer for '{mod}'."
            )
        self._render_files()
