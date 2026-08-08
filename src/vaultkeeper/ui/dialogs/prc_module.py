"""PrcModuleDialog — install a PRC-ified Vault module from the Drive collection.

These are Neverwinter Vault modules rebuilt to run under PRC and published as
``.7z`` archives in a public Google Drive folder. The archive is only half the
story: what it *needs* is documented on the module's Vault page, which the folder
does not link to. Installing one therefore means pairing two sources, and the
dialog walks that pairing in four revealed steps:

1. **Choose the module** — browse the Drive folder (subfolders included) or paste
   a link to one archive.
2. **Confirm its Vault page** — searched for by the title in the file name, ranked
   here, and *chosen by the user*. The Vault's own relevance is poor and the
   ranking only sorts a shortlist: "A Call for Heroes" matches Selendi: A Call For
   Heroes 1, 2 and 3 with identical scores, and the wrong page means the wrong
   dependencies, which is a broken install rather than a wrong label.
3. **Settle the dependencies** — the archive's build tag (``[PRC8-CEP3]``) merged
   with the page's required projects. Where they disagree the user picks; the
   archive's answer is marked recommended, never imposed, because the page
   describes the original module and the archive is a rebuild. Anything already
   installed is shown as satisfied and left unticked rather than hidden.
4. **Install** — dependencies first, each as its own mod, then the module.

Every network call goes through the controller's injected HTTP client, so the
whole flow is testable offline.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

#: Column of the entry/candidate/plan trees the tick box lives on.
_TICK = 0


class PrcModuleDialog(QDialog):
    """Browse the PRC-ified Drive collection and install a module with its needs."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._entries: list = []
        self._folder_stack: list[str] = []
        self._candidates: list = []
        self._plan = None
        self._choice_groups: dict[str, QButtonGroup] = {}
        self._requirements: list = []
        self._page_url = ""
        self._name_touched = False
        #: The chosen archive: its Drive id, its file name, and the build tag in it.
        self._file_ident = ""
        self._archive_name = ""
        self._tags: tuple[str, ...] = ()
        #: Set while an install is running, so a second click cannot start one.
        self._busy = False
        self._job = None
        self._release = lambda: None
        self._step = (0, 1)
        self._step_label = ""
        self.setWindowTitle("Install a PRC-ified Vault Module")
        self.setWindowIcon(R.get_icon("0205_WebInsertHyperlink_32"))
        self.resize(760, 760)

        layout = QVBoxLayout(self)
        heading = QLabel(
            "Install a Neverwinter Vault module that has been rebuilt to run under PRC."
        )
        heading.setStyleSheet("font-weight: bold;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        hint = QLabel(
            "The Drive folder holds the rebuilt archive; the Vault page for the same "
            "module says what else it needs. Both are used, and you confirm each one."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._build_source_box(), 3)
        layout.addWidget(self._build_page_box(), 3)
        layout.addWidget(self._build_plan_box(), 3)
        layout.addWidget(self._build_install_box())

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel install")
        self.cancel_button.setToolTip("Stop the transfer and remove the part-file")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.cancel_button.setVisible(False)
        buttons.addWidget(self.cancel_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    # -- Step 1: the Drive folder ------------------------------------------ #
    def _build_source_box(self) -> QGroupBox:
        from vaultkeeper.vault.drive_folder import PRC_MODULES_FOLDER, folder_url

        box = QGroupBox("1. Choose the module")
        outer = QVBoxLayout(box)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(folder_url(PRC_MODULES_FOLDER))
        self.folder_edit.setPlaceholderText(
            "A Drive folder address, or a link to one module archive"
        )
        self.folder_edit.returnPressed.connect(self._on_browse)
        self.browse_button = QPushButton("Browse")
        self.browse_button.setToolTip("List the modules in this Drive folder")
        self.browse_button.clicked.connect(self._on_browse)
        self.up_button = QPushButton("Up")
        self.up_button.setToolTip("Back to the folder above")
        self.up_button.clicked.connect(self._on_up)
        self.up_button.setEnabled(False)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.browse_button)
        row.addWidget(self.up_button)
        outer.addLayout(row)

        self.entry_tree = QTreeWidget()
        self.entry_tree.setHeaderLabels(["Name", "Built for"])
        self.entry_tree.setRootIsDecorated(False)
        self.entry_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.entry_tree.itemDoubleClicked.connect(self._on_entry_activated)
        self.entry_tree.itemSelectionChanged.connect(self._on_entry_selected)
        outer.addWidget(self.entry_tree, 1)
        return box

    def _on_browse(self) -> None:
        """List the folder in the address box — or accept a link to a single file."""
        from vaultkeeper.vault.drive_folder import file_id, folder_id

        text = self.folder_edit.text().strip()
        if not text:
            return
        if not folder_id(text) and file_id(text):
            self._use_direct_file(file_id(text))
            return
        self.status.setText("Reading the Drive folder…")
        self.populate_entries(self.controller.drive_entries(text))

    def populate_entries(self, entries: list) -> None:
        """Show a folder's contents: subfolders first, then the module archives."""
        self._entries = entries
        self.entry_tree.clear()
        for entry in entries:
            label = entry.name if entry.is_folder else entry.title
            item = QTreeWidgetItem([label, ", ".join(entry.tags)])
            item.setIcon(
                0,
                R.get_icon("Folder_6221" if entry.is_folder else "DownloadProject_16x"),
            )
            self.entry_tree.addTopLevelItem(item)
        modules = sum(1 for e in entries if not e.is_folder)
        folders = len(entries) - modules
        self.status.setText(
            f"{modules} module(s) and {folders} subfolder(s). "
            "Double-click a folder to open it, or pick a module."
            if entries
            else "Nothing could be read from that folder address."
        )

    @property
    def selected_entry(self):
        """The highlighted Drive entry, or ``None``."""
        index = self.entry_tree.indexOfTopLevelItem(self.entry_tree.currentItem())
        return self._entries[index] if 0 <= index < len(self._entries) else None

    def _on_entry_activated(self, item: QTreeWidgetItem) -> None:
        entry = self.selected_entry
        if entry is None:
            return
        if entry.is_folder:
            self._folder_stack.append(self.folder_edit.text().strip())
            self.up_button.setEnabled(True)
            self.folder_edit.setText(entry.folder_url)
            self._on_browse()

    def _on_up(self) -> None:
        if not self._folder_stack:
            return
        self.folder_edit.setText(self._folder_stack.pop())
        self.up_button.setEnabled(bool(self._folder_stack))
        self._on_browse()

    def _on_entry_selected(self) -> None:
        """Selecting an archive opens step 2, seeded with the title in its file name."""
        entry = self.selected_entry
        if entry is None or entry.is_folder:
            return
        self._file_ident = entry.file_id
        self._archive_name = entry.name
        self._tags = entry.tags
        self.search_edit.setText(entry.title)
        self.page_box.setVisible(True)
        self._reset_from_page()
        if not self._name_touched:
            self.mod_name_edit.setText(self.controller.suggested_mod_name(entry.title))

    def _use_direct_file(self, ident: str) -> None:
        """A pasted link to one archive: no name and no build tag come with it.

        The folder listing is what supplies both, so a direct link starts step 2
        with an empty title for the user to type and no archive side to the
        dependency plan — everything then comes from the Vault page.
        """
        self._file_ident = ident
        self._archive_name = ""
        self._tags = ()
        self.entry_tree.clear()
        self._entries = []
        self.search_edit.clear()
        self.page_box.setVisible(True)
        self._reset_from_page()
        self.status.setText(
            "A direct link carries no module name or build tag — type the module's "
            "title below to find its Vault page."
        )

    # -- Step 2: the Vault page -------------------------------------------- #
    def _build_page_box(self) -> QGroupBox:
        box = QGroupBox("2. Confirm the module's Vault page")
        outer = QVBoxLayout(box)
        outer.addWidget(
            QLabel(
                "The Vault's search is not precise, so these are ranked but not "
                "chosen — pick the page for this module yourself."
            )
        )
        row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Module title to search the Vault for")
        self.search_edit.returnPressed.connect(self._on_search)
        self.search_button = QPushButton("Search the Vault")
        self.search_button.clicked.connect(self._on_search)
        row.addWidget(self.search_edit, 1)
        row.addWidget(self.search_button)
        outer.addLayout(row)

        self.candidate_tree = QTreeWidget()
        self.candidate_tree.setHeaderLabels(["Vault page", "Kind", "Match", "Address"])
        self.candidate_tree.setRootIsDecorated(False)
        self.candidate_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.candidate_tree.itemDoubleClicked.connect(lambda *_: self._on_use_page())
        outer.addWidget(self.candidate_tree, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.use_page_button = QPushButton("Use this page")
        self.use_page_button.setToolTip("Read this page's required projects")
        self.use_page_button.clicked.connect(self._on_use_page)
        row.addWidget(self.use_page_button)
        self.no_page_button = QPushButton("No Vault page")
        self.no_page_button.setToolTip(
            "Carry on with only the build tag in the archive's file name"
        )
        self.no_page_button.clicked.connect(self._on_no_page)
        row.addWidget(self.no_page_button)
        outer.addLayout(row)
        box.setVisible(False)
        self.page_box = box
        return box

    def _on_search(self) -> None:
        title = self.search_edit.text().strip()
        if not title:
            return
        self.status.setText(f"Searching the Vault for “{title}”…")
        self.populate_candidates(self.controller.find_vault_pages(title))

    def populate_candidates(self, candidates: list) -> None:
        """List the ranked pages. Nothing is selected — the choice is the user's."""
        self._candidates = candidates
        self.candidate_tree.clear()
        for candidate in candidates:
            self.candidate_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        candidate.title,
                        candidate.kind,
                        # Ranking adds a bonus for being a module, so a score can
                        # exceed 1 — shown as "105%" it reads like a broken gauge.
                        f"{min(candidate.score, 1.0):.0%}",
                        candidate.full_url,
                    ]
                )
            )
        self.status.setText(
            f"{len(candidates)} possible page(s) — choose the right one."
            if candidates
            else "The Vault search returned nothing for that title."
        )

    @property
    def selected_candidate(self):
        index = self.candidate_tree.indexOfTopLevelItem(self.candidate_tree.currentItem())
        return self._candidates[index] if 0 <= index < len(self._candidates) else None

    def _on_use_page(self) -> None:
        candidate = self.selected_candidate
        if candidate is None:
            self.status.setText("Select the Vault page for this module first.")
            return
        self._page_url = candidate.full_url
        self.status.setText(f"Reading what “{candidate.title}” needs…")
        self.populate_plan(
            self.controller.module_dependency_plan(self._tags, self._page_url)
        )

    def _on_no_page(self) -> None:
        """Proceed on the build tag alone, when the module has no Vault page."""
        self._page_url = ""
        self.populate_plan(self.controller.module_dependency_plan(self._tags, ""))

    # -- Step 3: the dependency plan --------------------------------------- #
    def _build_plan_box(self) -> QGroupBox:
        box = QGroupBox("3. Settle what it needs")
        outer = QVBoxLayout(box)

        self.choice_holder = QWidget()
        self.choice_layout = QVBoxLayout(self.choice_holder)
        self.choice_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.choice_holder)

        outer.addWidget(QLabel("Tick what should be downloaded and installed too:"))
        self.plan_tree = QTreeWidget()
        self.plan_tree.setHeaderLabels(["Requirement", "Known from", "Status"])
        self.plan_tree.setRootIsDecorated(False)
        self.plan_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.plan_tree, 1)
        box.setVisible(False)
        self.plan_box = box
        return box

    def _reset_from_page(self) -> None:
        """Clear everything downstream of the page choice (steps 3 and 4)."""
        self._plan = None
        self._page_url = ""
        self._clear_choices()
        self.plan_tree.clear()
        self.plan_box.setVisible(False)
        self.install_box.setVisible(False)

    def _clear_choices(self) -> None:
        self._choice_groups = {}
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def populate_plan(self, plan) -> None:
        """Show the merged plan: the conflicts to settle, then the settled list."""
        self._plan = plan
        self._clear_choices()
        for choice in plan.choices:
            self.choice_layout.addWidget(self._choice_widget(choice))
        self._render_plan()
        self.plan_box.setVisible(True)
        self.install_box.setVisible(True)
        if plan.choices:
            self.status.setText(
                f"{len(plan.choices)} disagreement(s) between the archive and its "
                "Vault page — answer each one to carry on."
            )
        else:
            self.status.setText(
                "Nothing to settle. Check the list, then name the mod and install."
            )
        self._update_install_enabled()

    def _choice_widget(self, choice) -> QGroupBox:
        """One family the two sources disagree about, as an unanswered set of options."""
        box = QGroupBox(f"Which {choice.family}?")
        inner = QVBoxLayout(box)
        question = QLabel(choice.question)
        question.setWordWrap(True)
        inner.addWidget(question)
        group = QButtonGroup(box)
        group.setExclusive(True)
        for option in choice.options:
            label = option.name
            if option is choice.recommended or option.name == choice.recommended.name:
                label += "  (recommended — it is what this archive was built for)"
            button = QRadioButton(label)
            button.setProperty("requirement_name", option.name)
            # Deliberately unchecked: a wrong CEP is a broken install, so the
            # recommendation is offered, never applied on the user's behalf.
            button.toggled.connect(self._on_choice_changed)
            group.addButton(button)
            inner.addWidget(button)
        self._choice_groups[choice.family] = group
        return box

    def _on_choice_changed(self, checked: bool) -> None:
        if not checked:
            return
        self._render_plan()
        self._update_install_enabled()

    def picks(self) -> dict[str, str]:
        """``{family: chosen name}`` for every conflict the user has answered."""
        out: dict[str, str] = {}
        for family, group in self._choice_groups.items():
            button = group.checkedButton()
            if button is not None:
                out[family] = button.property("requirement_name")
        return out

    @property
    def unanswered(self) -> list[str]:
        """Families still waiting on the user."""
        return [f for f, g in self._choice_groups.items() if g.checkedButton() is None]

    def _render_plan(self) -> None:
        """(Re)build the requirement rows for the answers given so far."""
        from PySide6.QtGui import QBrush

        from vaultkeeper.ui import theme

        if self._plan is None:
            return
        self._requirements = self._plan.resolve(self.picks())
        answered = set(self.picks())
        pending = {f for f in self._choice_groups if f not in answered}
        self.plan_tree.clear()
        installed_brush = QBrush(theme.status_colour("installed", self.palette()))
        dim_brush = QBrush(theme.status_colour("disabled", self.palette()))
        for requirement in self._requirements:
            if requirement.family in pending:
                continue  # not yet decided — don't show a guess as a decision
            installed = self.controller.satisfied_by(requirement.name)
            if installed:
                status = f"Already installed as '{installed}'"
            elif requirement.url:
                status = "Will be downloaded from the Vault"
            else:
                status = "No Vault page known — install this one yourself"
            item = QTreeWidgetItem([requirement.name, requirement.source, status])
            if requirement.url:
                # Satisfied requirements stay listed but unticked: seeing that CEP
                # is already there is the point, and re-fetching hundreds of
                # megabytes is not. Re-tick to reinstall one anyway.
                item.setCheckState(
                    _TICK,
                    Qt.CheckState.Unchecked if installed else Qt.CheckState.Checked,
                )
            # A build tag like PRC8 names no page, so there is nothing here to tick.
            # Such a row is given no check state at all, and Qt then draws no box —
            # which is what says so. Offering a box that could never do anything
            # would be worse than saying plainly that this one is the user's to
            # install. (Clearing ``ItemIsUserCheckable`` would not do it: a
            # QTreeWidgetItem carries that flag by default, set or not.)
            if installed:
                item.setForeground(2, installed_brush)
            elif not requirement.url:
                for col in range(3):
                    item.setForeground(col, dim_brush)
            self.plan_tree.addTopLevelItem(item)

    def checked_requirements(self) -> list:
        """The requirements the user has ticked for download."""
        shown = [r for r in self._requirements if r.family not in self.unanswered]
        out = []
        for index in range(self.plan_tree.topLevelItemCount()):
            if self.plan_tree.topLevelItem(index).checkState(_TICK) == Qt.CheckState.Checked:
                out.append(shown[index])
        return out

    # -- Step 4: install ---------------------------------------------------- #
    def _build_install_box(self) -> QGroupBox:
        box = QGroupBox("4. Install")
        outer = QVBoxLayout(box)
        form = QFormLayout()
        self.mod_name_edit = QLineEdit()
        self.mod_name_edit.setPlaceholderText("Mod folder name")
        self.mod_name_edit.textEdited.connect(self._on_name_edited)
        form.addRow("Mod folder name:", self.mod_name_edit)
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.addItems(self._group_names())
        form.addRow("Group:", self.group_combo)
        outer.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        self.install_button = QPushButton("Install module and ticked dependencies")
        self.install_button.clicked.connect(self._on_install)
        self.install_button.setEnabled(False)
        row.addWidget(self.install_button)
        outer.addLayout(row)

        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["Step", "Outcome"])
        self.result_tree.setRootIsDecorated(False)
        self.result_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_tree.setMaximumHeight(120)
        self.result_tree.setVisible(False)
        outer.addWidget(self.result_tree)
        box.setVisible(False)
        self.install_box = box
        return box

    def _group_names(self) -> list[str]:
        try:
            return self.controller.group_names()
        except Exception:
            return []

    def _on_name_edited(self, _text: str) -> None:
        self._name_touched = True

    def _update_install_enabled(self) -> None:
        self.install_button.setEnabled(
            self._plan is not None and not self.unanswered and not self._busy
        )

    # -- Progress (signals, so these always arrive on the UI thread) -------- #
    def _on_step(self, label: str, index: int, count: int) -> None:
        self._step_label = label
        self._step = (index, count)
        self.progress.setRange(0, 0)
        self.status.setText(f"Installing {label} ({index + 1} of {count})…")

    def _on_bytes(self, done: int, total: int) -> None:
        from vaultkeeper.ui.controller import _fmt_size

        index, count = self._step
        where = f"{self._step_label} ({index + 1} of {count})"
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(
                f"Downloading {where} — {_fmt_size(done)} of {_fmt_size(total)}"
            )
        else:
            self.status.setText(f"Downloading {where} — {_fmt_size(done)} so far")

    def _on_phase(self, label: str, done: int, total: int) -> None:
        """What the job is doing once a download is over.

        Extracting the archive and installing it take as long again as fetching it,
        and used to say nothing — leaving the last byte count on screen under a full
        bar, which looks stuck rather than busy.
        """
        index, count = self._step
        where = f"{self._step_label} ({index + 1} of {count})"
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status.setText(f"{label} for {where} — {done:,} of {total:,}")
        else:
            self.progress.setRange(0, 0)  # no count to show: busy, not measurable
            self.status.setText(f"{label} for {where}…")

    def _on_cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Stopping…")

    def _finish_job(self) -> None:
        self._busy = False
        self._job = None
        self._release()
        self._release = lambda: None
        self.cancel_button.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self._update_install_enabled()

    def _job_done(self, steps) -> None:
        mod = self.mod_name_edit.text().strip()
        self._finish_job()
        self.populate_results(steps)
        done = sum(1 for s in steps if s["ok"])
        module_ok = any(s["kind"] == "module" and s["ok"] for s in steps)
        self.status.setText(
            f"{done} of {len(steps)} step(s) succeeded. "
            + (f"'{mod}' is installed." if module_ok else f"'{mod}' was not installed.")
        )

    def _job_failed(self, message: str) -> None:
        self._finish_job()
        self.status.setText(f"That did not work: {message}")

    def _job_cancelled(self) -> None:
        self._finish_job()
        self.status.setText(
            "Cancelled. The part-downloaded file was removed. Anything installed "
            "before you stopped is still installed."
        )

    def _on_install(self) -> None:
        if self._busy:
            return
        mod = self.mod_name_edit.text().strip()
        if not mod:
            self.status.setText("Enter a mod folder name to install into.")
            self.mod_name_edit.setFocus()
            return
        if self.unanswered:
            self.status.setText(
                "Answer the outstanding question(s) above before installing: "
                + ", ".join(self.unanswered)
            )
            return
        requirements = self.checked_requirements()
        group = self.group_combo.currentText().strip() or None
        file_ident, archive = self._file_ident, self._archive_name
        page_url = self._page_url

        def work(job):
            def on_progress(index: int, count: int, label: str) -> None:
                job.step.emit(label, index, count)

            def on_bytes(info, done: int, total: int) -> None:
                job.raise_if_cancelled()
                job.bytes_progress.emit(done, total)

            def on_phase(label: str, done: int, total: int) -> None:
                job.phase.emit(label, done, total)

            return self.controller.install_prc_module(
                file_ident,
                mod,
                requirements,
                group=group,
                filename=archive,
                page_url=page_url,
                on_progress=on_progress,
                on_bytes=on_bytes,
                on_phase=on_phase,
            )

        self._start_job(work)

    def _start_job(self, work) -> None:
        """Run the install on a worker thread; the window behind is taken out of play."""
        from vaultkeeper.ui.background import BackgroundJob, claim

        self._busy = True
        self.install_button.setEnabled(False)
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

    def closeEvent(self, event) -> None:
        """Refuse to close mid-install — the signals would reach a deleted dialog."""
        if self._busy:
            event.ignore()
            self.status.setText("Cancel the install first, or wait for it to finish.")
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._busy:
            self.status.setText("Cancel the install first, or wait for it to finish.")
            return
        super().reject()

    def populate_results(self, steps: list[dict]) -> None:
        """Show what each install step did, so a partial failure names itself."""
        from PySide6.QtGui import QBrush

        from vaultkeeper.ui import theme

        self.result_tree.clear()
        failed = QBrush(theme.status_colour("duplicate", self.palette()))
        for step in steps:
            item = QTreeWidgetItem([step["name"], step["message"]])
            if not step["ok"]:
                for col in range(2):
                    item.setForeground(col, failed)
            self.result_tree.addTopLevelItem(item)
        self.result_tree.setVisible(bool(steps))
