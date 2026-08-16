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

from urllib.parse import urlsplit

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

from vaultkeeper.ui import geometry
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
        self._prereqs: list[dict] = []  # required projects expanded into their files
        self._name_touched = False
        #: Set while a transfer is running, so a second click cannot start one.
        self._busy = False
        self._job = None
        self._on_job_done = None
        self._release = lambda: None
        self._files_total = 1
        self._file_index = 0
        self._file_label = ""
        #: The project URL the current file list came from, so a mod created by
        #: downloading it can be given its page.
        self._fetched_url = ""
        #: Mods already asked about this sitting (VB ``WebLinkMessages``).
        self._link_asked: set[str] = set()
        self.setWindowTitle("Download Project")
        self.setWindowIcon(R.get_icon("DownloadProject_16x"))
        geometry.remember(self, "DownloadProjectDialog", 640, 560)

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
        url_row.addWidget(self._build_rules_button())
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
        # "If you don't want to use these files, select all the files and press
        # the Space Bar" (newtopic4) — which needs more than one row selectable.
        self.file_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.file_tree.installEventFilter(self)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._on_files_menu)
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
        self.cancel_button = QPushButton("Cancel download")
        self.cancel_button.setToolTip("Stop the transfer and remove the part-file")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.cancel_button.setVisible(False)
        buttons.addWidget(self.cancel_button)
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

    def eventFilter(self, watched, event):  # noqa: N802 (Qt override)
        """Space toggles every selected file, not only the current one.

        Qt's own Space handling ticks the current row and ignores the rest of
        the selection, which makes "select all the files and press the Space
        Bar" tick exactly one of them.
        """
        from PySide6.QtCore import QEvent

        if (
            watched is self.file_tree
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Space
        ):
            selected = self.file_tree.selectedItems()
            if len(selected) > 1:
                # Everything follows the current row, so a mixed selection ends
                # up consistent rather than each row flipping its own way.
                current = self.file_tree.currentItem() or selected[0]
                wanted = (
                    Qt.CheckState.Unchecked
                    if current.checkState(0) == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                for item in selected:
                    item.setCheckState(0, wanted)
                return True
        return super().eventFilter(watched, event)

    def _on_files_menu(self, point) -> None:
        """Copy the file name or its direct link (VB CmCopyFilename / CmCopyLink)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication, QMenu

        index = self.file_tree.indexOfTopLevelItem(self.file_tree.currentItem())
        vsi = self._files[index] if 0 <= index < len(self._files) else None
        menu = QMenu(self)

        name = menu.addAction("Copy File Name to Clipboard")
        name.setEnabled(vsi is not None)
        name.triggered.connect(
            lambda: QApplication.clipboard().setText(vsi.filename if vsi else "")
        )
        link = menu.addAction("Copy Direct File Link to Clipboard")
        # Only when there is a link to copy — a menu entry that silently copies
        # an empty string is worse than one that is greyed out.
        link.setEnabled(bool(vsi and (vsi.direct_url or vsi.counter_url)))
        link.triggered.connect(
            lambda: QApplication.clipboard().setText(
                (vsi.direct_url or vsi.counter_url) if vsi else ""
            )
        )
        menu.exec(
            self.file_tree.viewport().mapToGlobal(point) if point else QCursor.pos()
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

    def populate_required(self, bundles: list) -> None:
        """Show the module's required projects as a checklist (VB ``LvRequirements``).

        Each Vault requirement has been expanded into its files; a ticked one is
        downloaded into its own mod folder alongside the module. Requirements
        already in the store, external pages, and any that could not be read are
        shown but cannot be ticked. Whether the tickable ones start ticked follows
        the *Include prerequisites* setting.
        """
        from PySide6.QtCore import Qt as _Qt

        self._prereqs = bundles
        self.required_list.clear()
        include = self.controller._settings().vault_include_prerequisites
        for bundle in bundles:
            title = bundle.get("title", "")
            item = QTreeWidgetItem([title, bundle.get("url", "")])
            if bundle.get("have"):
                item.setText(0, f"{title}  — already in your store")
                bundle["selected"] = False
            elif bundle.get("external"):
                item.setText(0, f"{title}  — external page (double-click to open)")
                item.setToolTip(0, "Not a Vault project — opens in your browser.")
                bundle["selected"] = False
            elif not bundle.get("files"):
                item.setText(0, f"{title}  — could not be read from the Vault")
                bundle["selected"] = False
            else:
                folder = bundle.get("mod_folder") or title
                n = len(bundle["files"])
                item.setText(0, f"{title}  →  {folder}  ({n} file{'' if n == 1 else 's'})")
                item.setFlags(item.flags() | _Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, _Qt.CheckState.Checked if include else _Qt.CheckState.Unchecked
                )
                bundle["selected"] = include
            self.required_list.addTopLevelItem(item)
        has = bool(bundles)
        self.required_label.setText(
            "Required projects (ticked ones are downloaded too):" if has else ""
        )
        self.required_label.setVisible(has)
        self.required_list.setVisible(has)

    def _selected_prereqs(self) -> list:
        """The prerequisite bundles the user has ticked (with ``selected`` set)."""
        from PySide6.QtCore import Qt as _Qt

        out = []
        for index, bundle in enumerate(self._prereqs):
            item = self.required_list.topLevelItem(index)
            checkable = item is not None and bool(
                item.flags() & _Qt.ItemFlag.ItemIsUserCheckable
            )
            picked = dict(bundle)
            picked["selected"] = (
                checkable and item.checkState(0) == _Qt.CheckState.Checked
            )
            out.append(picked)
        return out

    def _on_required_double_clicked(self, item: QTreeWidgetItem) -> None:
        """Open an external requirement's page in the browser.

        Vault requirements are handled by ticking them; this stays useful for the
        external pages there is nothing here to download.
        """
        index = self.required_list.indexOfTopLevelItem(item)
        bundle = self._prereqs[index] if 0 <= index < len(self._prereqs) else {}
        if bundle.get("external"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(bundle.get("url", "")))

    def _on_name_edited(self, _text: str) -> None:
        self._name_touched = True

    # -- Actions ----------------------------------------------------------- #
    def _on_fetch(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.status.setText("Retrieving…")
        project = self.controller.fetch_vault_project(url)
        self.populate_files(project["files"])
        self._required = project["required"]
        # Expand each required project into its files (VB LvRequirements), so a
        # single download can grab the prerequisites too. This fetches each
        # requirement's page, so it is done here on the retrieve, not the download.
        self.populate_required(
            self.controller.expand_prerequisites(
                self._required, exclude_mod=self.mod_name_edit.text().strip()
            )
        )
        if not project["files"]:
            self.status.setText(self._nothing_found(url))
            return
        self._apply_project_rule(project)
        self._fetched_url = url
        self._show_rules_revision()
        self._offer_web_link(url)

    def _build_rules_button(self):
        """The download-rules toggle (``newtopic5.htm``).

        "You can click the Project Download Rules Preferences icon to view and
        change which rules are applied… Disable *Apply Project Download File
        rules* to show all available files." The preference existed and was
        honoured, but only in Advanced Settings — three dialogs away from the
        moment it matters, which is reading "3 files the download rules hold
        back" and wanting to see them.

        Toggling re-fetches when a project is already on screen, because the
        held-back files were dropped before the list was built; without that the
        setting would appear to do nothing.
        """
        from PySide6.QtWidgets import QToolButton

        from vaultkeeper.config.settings import load_settings

        self.rules_button = QToolButton()
        self.rules_button.setIcon(R.get_icon("DownloadRules_16x"))
        self.rules_button.setCheckable(True)
        self.rules_button.setChecked(load_settings().vault_apply_project_rules)
        self.rules_button.setToolTip(
            "Apply the published project download rules.\n"
            "Turn this off to see every file a project offers."
        )
        self.rules_button.toggled.connect(self._on_rules_toggled)
        return self.rules_button

    def _on_rules_toggled(self, applied: bool) -> None:
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        settings.vault_apply_project_rules = applied
        save_settings(settings)
        self.status.setText(
            "Download rules applied."
            if applied
            else "Download rules off — every file the project offers is listed."
        )
        if self._fetched_url:
            self._on_fetch()

    def _apply_project_rule(self, project: dict) -> None:
        """Put the download where the published rules say it belongs.

        The mod folder and group are *defaults*, not decisions: a name the user
        has typed is never overwritten, and the group combo stays editable. The
        status line says when files were held back, because a list quietly two
        rows shorter than the web page is worse than one that explains itself.
        """
        folder, group = project.get("mod_folder", ""), project.get("group", "")
        if folder and not self._name_touched:
            self.mod_name_edit.setText(folder)
        if group:
            self.group_combo.setCurrentText(group)
        held = project.get("excluded", 0)
        if held:
            self.status.setText(
                f"{self.status.text()} {held} file{'s' if held != 1 else ''} the "
                "download rules hold back (superseded or not needed) "
                "not shown."
            )

    def _nothing_found(self, url: str) -> str:
        """Why nothing came back — "No files found" blames the wrong thing.

        A Nexus address is the common case, and it is not a failure anything here
        can fix: Nexus answers 403 to programs, by policy. Saying so, and saying
        what to do instead, is the difference between a dead end and a detour.
        """
        rules = self.controller.download_rules()
        host = urlsplit(url).netloc.lower()
        if "nexusmods." in host:
            return (
                "Nexus Mods does not allow other programs to read its pages, so "
                "nothing here can fetch this. Download the files in your browser, "
                "then use Add Files to Mod."
            )
        if not rules.is_vault_project_url(url) and not rules.is_rolovault_url(url):
            return (
                "That is not a Neverwinter Vault project address. Paste the "
                "project's page URL — it looks like "
                "https://neverwintervault.org/project/…"
            )
        return "No downloadable files found on that project page."

    def _show_rules_revision(self) -> None:
        """Name the download rules in force, now that they have been loaded.

        Which revision answered matters when a download behaves oddly, and the
        rules are published separately from the application — so the number is
        worth stating rather than leaving someone to guess. Not shown before the
        first fetch: reading it is what loads them.
        """
        revision = getattr(self.controller.download_rules(), "revision", 0)
        if revision:
            self.setWindowTitle(f"Download Project  —  Rules revision {revision}")

    def _offer_web_link(self, url: str) -> None:
        """Record this project as the mod's web page (VB ``UpdateWebLink``).

        A mod that was downloaded from a page has a page, and remembering it is
        what lets *Check for Mod Updates* work later. An existing, different link
        is never overwritten without asking, and asking twice for the same mod in
        one sitting is asking once too often.
        """
        mod = self.mod_name_edit.text().strip()
        if not mod or mod in self._link_asked:
            return
        md = self.controller.pd.mod_item(mod)
        if md is None or md.is_group_item or md.web_link == url:
            return
        self._link_asked.add(mod)
        if md.web_link:
            from PySide6.QtWidgets import QMessageBox

            answer = QMessageBox.question(
                self,
                "Mod's Web Page",
                f"Update the web page link for '{mod}'?\n\n"
                f"Old: {md.web_link}\nNew: {url}",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.controller.set_mod_web_link(mod, url)

    # -- Running a transfer ------------------------------------------------- #
    def start_job(self, work, on_done) -> None:
        """Run ``work`` on a worker thread and hand its result to ``on_done``.

        The window that opened this dialog is disabled for the duration: the job
        creates mods and rewrites the store, and nothing else in the application
        expects that to happen underneath it.
        """
        from vaultkeeper.ui.background import BackgroundJob, claim

        self._busy = True
        self._on_job_done = on_done
        for button in (self.retrieve_button, self.download_button, self.install_button):
            button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate until the first bytes land
        self._release = claim(self)

        self._job = BackgroundJob(work, parent=self)
        self._job.step.connect(self._on_step)
        self._job.bytes_progress.connect(self._on_bytes)
        self._job.phase.connect(self._on_phase)
        self._job.done.connect(self._job_done)
        self._job.failed.connect(self._job_failed)
        self._job.cancelled_early.connect(self._job_cancelled)
        self._job.start()

    def _finish_job(self) -> None:
        self._busy = False
        self._job = None
        self._release()
        self._release = lambda: None
        self.retrieve_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.install_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

    def _job_done(self, result) -> None:
        handler, self._on_job_done = self._on_job_done, None
        self._finish_job()
        if handler is not None:
            handler(result)
        self._render_files()

    def _job_failed(self, message: str) -> None:
        self._on_job_done = None
        self._finish_job()
        self.status.setText(f"That did not work: {message}")
        self._render_files()

    def _job_cancelled(self) -> None:
        self._on_job_done = None
        self._finish_job()
        self.status.setText(
            "Cancelled. The part-downloaded file was removed; nothing else was changed."
        )
        self._render_files()

    def _on_cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Stopping…")

    # -- Progress (signals, so these always arrive on the UI thread) -------- #
    def _on_step(self, label: str, index: int, count: int) -> None:
        self._file_label = label
        self._file_index = index
        self._files_total = count
        self.progress.setRange(0, 0)
        self.status.setText(f"Downloading {label} ({index + 1} of {count})…")

    def _on_bytes(self, done: int, total: int) -> None:
        where = f"{self._file_label} ({self._file_index + 1} of {self._files_total})"
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(
                f"Downloading {where} — {_fmt_size(done)} of {_fmt_size(total)}"
            )
        else:
            self.status.setText(f"Downloading {where} — {_fmt_size(done)} so far")

    def _on_phase(self, label: str, done: int, total: int) -> None:
        """What the job is doing once the downloading is over.

        Extracting and installing take as long as the download and used to say
        nothing at all, leaving the last "downloaded 1.2 GB of 1.2 GB" on screen
        under a full bar — which looks stuck rather than busy.
        """
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(f"{label} — {done:,} of {total:,}")
        else:
            self.progress.setRange(0, 0)  # no count to show: busy, not measurable
            self.status.setText(f"{label}…")

    def _job_callbacks(self, job):
        """Progress callbacks that emit rather than touch widgets from the worker."""

        def on_progress(index: int, count: int, vsi) -> None:
            job.step.emit(vsi.description or vsi.filename or "file", index, count)

        def on_bytes(vsi, done: int, total: int) -> None:
            job.raise_if_cancelled()
            job.bytes_progress.emit(done, total)

        def on_phase(label: str, done: int, total: int) -> None:
            job.phase.emit(label, done, total)

        return on_progress, on_bytes, on_phase

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
        page_url = self._fetched_url

        prereqs = self._selected_prereqs()

        def work(job):
            on_progress, on_bytes, _ = self._job_callbacks(job)
            results = self.controller.download_project(
                files, mod, group=group, page_url=page_url,
                on_progress=on_progress, on_bytes=on_bytes,
            )
            # The page has just told us what it requires; recording it here
            # saves asking the Vault the same question again through Auto
            # (newtopic17.htm).
            self.controller.record_project_dependencies(mod, self._required)
            # VB downloads the ticked required projects in the same pass, each into
            # its own mod folder.
            prereq_report = self.controller.download_prerequisites(
                prereqs, on_progress=on_progress, on_bytes=on_bytes
            )
            return results, prereq_report

        def done(payload) -> None:
            results, prereq_report = payload
            ok = sum(1 for r in results if r.ok)
            verb = "Updated" if ok else "No files downloaded to"
            extra = ""
            got = prereq_report["downloaded"]
            if got:
                extra += f" Also fetched required project(s): {', '.join(got)}."
            unresolved = prereq_report["unresolved"]
            if unresolved:
                extra += f" Could not fetch: {', '.join(unresolved)}."
            self.status.setText(
                f"Downloaded {ok} of {len(results)} file(s). {verb} mod '{mod}'.{extra}"
            )
            if ok:
                self.offer_old_downloads(mod, [r.info for r in results if r.ok])

        self.start_job(work, done)

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
        page_url = self._fetched_url

        def work(job):
            on_progress, on_bytes, on_phase = self._job_callbacks(job)
            return self.controller.install_downloaded_project(
                files, mod, group=group, page_url=page_url,
                required=self._required,
                on_progress=on_progress, on_bytes=on_bytes, on_phase=on_phase,
            )

        def done(result) -> None:
            if result["built"]:
                self.status.setText(f"Installed '{mod}'. {result['install_message']}")
            else:
                self.status.setText(
                    f"Downloaded {result['downloaded']} of {result['total']} file(s), "
                    f"but could not build the installer for '{mod}'."
                )
            if result["downloaded"]:
                self.offer_old_downloads(mod, files)

        self.start_job(work, done)

    def offer_old_downloads(self, mod: str, downloaded: list) -> None:
        """Offer to clear out what this download appears to have replaced.

        Only ever *offers*: nothing here decides that two archives are versions
        of each other, and the previous release of a mod is sometimes the last
        copy in existence.
        """
        names = [
            (info.local_filename or info.filename)
            for info in downloaded
            if (info.local_filename or info.filename)
        ]
        old = self.controller.superseded_downloads(mod, names)
        if not old:
            return
        from vaultkeeper.ui.dialogs.old_downloads import OldDownloadsDialog

        dlg = OldDownloadsDialog(mod, old, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.action:
            return
        result = self.controller.remove_old_downloads(
            dlg.checked_paths(), to_history=dlg.action == "history"
        )
        self.status.setText(f"{self.status.text()} {result['message']}")

    def closeEvent(self, event) -> None:
        """Refuse to close mid-job — the signals would arrive at a deleted dialog."""
        if self._busy:
            event.ignore()
            self.status.setText("Cancel the download first, or wait for it to finish.")
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._busy:
            self.status.setText("Cancel the download first, or wait for it to finish.")
            return
        super().reject()
