"""PortraitManager — manage the portraits your mods installed (VB PortraitManager).

Faithful to VB, the list is sourced from the profile's *installed* portraits
(``controller.installed_portraits_report`` → ``pd.InstalledList`` filtered to
portrait files), each tagged with the mod that installed it, and the selected
portrait's five size thumbnails (tiny / small / medium / large / huge) are shown.

The original's toolbar is reproduced: Previous/Next with keyboard equivalents,
**Find Portrait**, Exclude/Undo/Apply Excludes, Edit Portrait, Create Installer,
Select Source, an Options menu, a link out, and Help — all also reachable from a
right-click menu, as in VB, where ``ContextMenuManager`` builds the popup from the
same ribbon buttons. Moving the mouse across the thumbnails changes the cursor:
the left edge selects the previous portrait, the right edge the next, and the
middle opens the image in a TGA editor.

**Excluding is not deleting.** VB marks a portrait, then ``Apply Excludes`` writes
it into the mod's installer wizard and rebuilds the installer, so the Wizard
Builder can undo it later. An earlier version of this port had a ``Remove`` button
that called ``unlink()`` — an irreversible delete wearing a gentler word — which
is why the wizard route is the only one here now.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nwnfile.character import PORTRAIT_SIZES
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.constants import INSTALLER_UNKNOWN
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap
from vaultkeeper.ui.dialogs.help_viewer import help_button

_SIZE_BOXES = {"t": 32, "s": 64, "m": 96, "l": 128, "h": 160}
_SIZE_LABELS = {"t": "Tiny", "s": "Small", "m": "Medium", "l": "Large", "h": "Huge"}
_ROLE = Qt.ItemDataRole.UserRole

#: How close to an edge of the image strip counts as "go back/forward" rather
#: than "edit" (VB ``MousePosMargin``).
_EDGE_MARGIN = 40


class PortraitManager(QDialog):
    """Manage the portraits the profile's mods installed (VB PortraitManager)."""

    def __init__(
        self,
        controller,
        on_select: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_select = on_select
        self._settings = getattr(controller, "settings", None)
        # Before any widget: the image strip installs an event filter as it is
        # built, and Qt can deliver an event to it during construction.
        self._entries: list[dict] = []
        self._pending: set[str] = set()  # resrefs marked for exclusion
        self._last_direction = 1  # which way "always select next" should move
        self.setWindowIcon(R.get_icon("user"))
        self.resize(860, 560)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_toolbar())

        panes = QHBoxLayout()
        layout.addLayout(panes, 1)
        panes.addWidget(self._build_list())
        panes.addLayout(self._build_images(), 1)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("RbPortraitManagerHelp", self))
        buttons.addStretch(1)
        self._apply_button = QPushButton("Apply Excludes")
        self._apply_button.setToolTip(
            "Write the marked portraits into their mods' installer wizards and "
            "rebuild those installers"
        )
        self._apply_button.clicked.connect(self._on_apply_excludes)
        buttons.addWidget(self._apply_button)
        self._extract_button = QPushButton("Extract from Hak…")
        self._extract_button.setToolTip(
            "Pull a portrait set out of a .hak (not in the original tool)"
        )
        self._extract_button.clicked.connect(self._on_extract)
        self._extract_button.setEnabled(controller is not None)
        buttons.addWidget(self._extract_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._install_shortcuts()
        self._entries = self._load_entries()
        self._populate()

    # -- Construction ------------------------------------------------------ #
    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._prev_button = QPushButton("◀ Previous")
        self._prev_button.clicked.connect(lambda: self._move(-1))
        bar.addWidget(self._prev_button)
        self._next_button = QPushButton("Next ▶")
        self._next_button.clicked.connect(lambda: self._move(1))
        bar.addWidget(self._next_button)

        self._exclude_button = QPushButton("Exclude")
        self._exclude_button.setToolTip("Mark this portrait for exclusion (Del)")
        self._exclude_button.clicked.connect(self._on_exclude)
        bar.addWidget(self._exclude_button)

        self._edit_button = QPushButton("Edit Portrait")
        self._edit_button.setToolTip("Open the five image files in your TGA editor")
        self._edit_button.clicked.connect(self._on_edit)
        bar.addWidget(self._edit_button)

        self._installer_button = QPushButton("Create Installer")
        self._installer_button.setToolTip("Re-create this portrait's source mod's installer")
        self._installer_button.clicked.connect(self._on_create_installer)
        bar.addWidget(self._installer_button)

        self._select_button = QPushButton("Select Source")
        self._select_button.setToolTip("Select this portrait's mod in the main window")
        self._select_button.clicked.connect(self._on_select_mod)
        bar.addWidget(self._select_button)

        self._options_button = QToolButton()
        self._options_button.setText("Options")
        self._options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._options_button.setMenu(self._build_options_menu())
        bar.addWidget(self._options_button)

        self._link_button = QPushButton("Portrait Web Page")
        self._link_button.clicked.connect(self._on_link)
        bar.addWidget(self._link_button)

        bar.addStretch(1)
        self._find = QLineEdit()
        self._find.setPlaceholderText("Find Portrait")
        self._find.setClearButtonEnabled(True)
        self._find.setMaximumWidth(200)
        self._find.textChanged.connect(self._on_find)
        self._find.returnPressed.connect(lambda: self._on_find(self._find.text(), step=1))
        bar.addWidget(self._find)
        return bar

    def _build_options_menu(self) -> QMenu:
        menu = QMenu(self)
        self._override_action = QAction("Include Portraits in Override and Ovr", self)
        self._override_action.setCheckable(True)
        self._override_action.setChecked(self._setting("portrait_include_override", False))
        self._override_action.toggled.connect(self._on_toggle_override)
        menu.addAction(self._override_action)

        self._next_action = QAction("Always Select Next Portrait", self)
        self._next_action.setCheckable(True)
        self._next_action.setChecked(self._setting("portrait_always_select_next", True))
        self._next_action.toggled.connect(
            lambda on: self._store_setting("portrait_always_select_next", on)
        )
        menu.addAction(self._next_action)

        menu.addSeparator()
        report = QAction("Invalid Portrait Size Report", self)
        report.triggered.connect(self._on_size_report)
        menu.addAction(report)
        return menu

    def _build_list(self) -> QWidget:
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Portrait", "Sizes", "Mod"])
        self._tree.setMinimumWidth(360)
        self._tree.setRootIsDecorated(False)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.currentItemChanged.connect(self._on_row)
        self._tree.itemDoubleClicked.connect(lambda *_: self._on_edit())
        return self._tree

    def _build_images(self) -> QVBoxLayout:
        right = QVBoxLayout()
        # The strip is one widget so the cursor zones are measured across all five
        # thumbnails, as in VB, where the images sit on a single LpImages panel.
        self._strip = QWidget()
        self._strip.setMouseTracking(True)
        self._strip.installEventFilter(self)
        self._strip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._strip.customContextMenuRequested.connect(self._on_context_menu)
        thumbs = QHBoxLayout(self._strip)
        thumbs.setContentsMargins(0, 0, 0, 0)
        self._thumbs: dict[str, QLabel] = {}
        for size in PORTRAIT_SIZES:
            col = QVBoxLayout()
            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setFixedSize(_SIZE_BOXES[size] + 4, _SIZE_BOXES[size] + 4)
            image.setMouseTracking(True)
            self._thumbs[size] = image
            col.addWidget(image)
            col.addWidget(QLabel(_SIZE_LABELS[size], alignment=Qt.AlignmentFlag.AlignCenter))
            col.addStretch(1)
            thumbs.addLayout(col)
        thumbs.addStretch(1)
        right.addWidget(self._strip)
        self._caption = QLabel()
        self._caption.setWordWrap(True)
        right.addWidget(self._caption)
        right.addStretch(1)
        return right

    def _install_shortcuts(self) -> None:
        # VB: Left/Up/Backspace = previous, Right/Down/Enter = next, Del =
        # exclude, Ctrl+Z = undo. Arrows and Enter belong to the list widget, so
        # only the ones it does not already handle are bound here.
        for key in ("Backspace",):
            QShortcut(QKeySequence(key), self, activated=lambda: self._move(-1))
        QShortcut(QKeySequence("Del"), self, activated=self._on_exclude)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo_exclude)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._find.setFocus)

    # -- Settings ---------------------------------------------------------- #
    def _setting(self, name: str, default):
        return getattr(self._settings, name, default) if self._settings else default

    def _store_setting(self, name: str, value) -> None:
        if self._settings is None:
            return
        setattr(self._settings, name, value)
        save = getattr(self._controller, "save_settings", None)
        if callable(save):
            save()

    # -- Data -------------------------------------------------------------- #
    def _load_entries(self) -> list[dict]:
        if self._controller is None:
            return []
        report = self._controller.installed_portraits_report(
            include_override=self._setting("portrait_include_override", False)
        )
        return report["portraits"]

    def _populate(self, select: int = 0) -> None:
        self.setWindowTitle(
            f"Portrait Manager — Installed Portraits: {len(self._entries):,}"
            if self._entries
            else "Portrait Manager"
        )
        self._tree.blockSignals(True)
        self._tree.clear()
        for entry in self._entries:
            sizes = "".join(s for s in PORTRAIT_SIZES if s in entry["sizes"])
            marked = entry["resref"] in self._pending
            item = QTreeWidgetItem(
                [
                    f"{entry['resref']}  ✗" if marked else entry["resref"],
                    sizes,
                    entry["mod"] or "",
                ]
            )
            item.setData(0, _ROLE, entry)
            if marked:
                item.setToolTip(0, "Marked for exclusion — Apply Excludes to write it")
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)
        # Sized to the content: the names differ only near their ends
        # ("AdreannaMage01" / "…02"), so a default-width column truncates them
        # into a screenful of identical-looking rows.
        for column in range(self._tree.columnCount()):
            self._tree.resizeColumnToContents(column)
        if self._entries:
            self._tree.setCurrentItem(
                self._tree.topLevelItem(min(select, len(self._entries) - 1))
            )
        self._refresh_actions()

    def _current(self) -> dict | None:
        item = self._tree.currentItem()
        return item.data(0, _ROLE) if item is not None else None

    @staticmethod
    def _owning_mod(entry: dict | None) -> str:
        """The mod that installed this portrait, or ``""`` if none did.

        ``INSTALLER_UNKNOWN`` marks a file found in the game folder that no mod in
        the profile installed. It reads like a mod name in the list, but there is
        nothing behind it to exclude from or rebuild, so everything that needs a
        real mod must treat it as absent.
        """
        if entry is None:
            return ""
        mod = entry.get("mod") or ""
        return "" if mod == INSTALLER_UNKNOWN else mod

    def _index(self) -> int:
        item = self._tree.currentItem()
        return self._tree.indexOfTopLevelItem(item) if item is not None else -1

    # -- Enablement -------------------------------------------------------- #
    def _refresh_actions(self) -> None:
        entry = self._current()
        index = self._index()
        count = len(self._entries)
        has = entry is not None
        self._prev_button.setEnabled(index > 0)
        self._next_button.setEnabled(-1 < index < count - 1)
        self._exclude_button.setEnabled(bool(self._owning_mod(entry)))
        self._select_button.setEnabled(bool(self._owning_mod(entry)))
        self._installer_button.setEnabled(bool(self._owning_mod(entry)))
        self._apply_button.setEnabled(bool(self._pending))
        # VB hides these entirely until the matching path is configured, rather
        # than offering a button that cannot work.
        self._edit_button.setVisible(bool(self._setting("tga_editor_path", "")))
        self._edit_button.setEnabled(has)
        self._link_button.setVisible(bool(self._setting("portrait_image_web_page", "")))

        if entry is None:
            self._caption.setText(f"Installed portraits: {len(self._entries):,}")
            return
        note = ""
        if not entry.get("mod"):
            note = " — no mod in this profile claims it"
        elif entry["mod"] == "Unknown source":
            # The list is built from installed files, and files found in the game
            # folders that no managed mod installed carry this sentinel. Saying so
            # beats a column of "Unknown source" that reads like a failure.
            note = (
                " — found in the game folder, but no mod in this profile installed "
                "it, so it cannot be excluded or rebuilt"
            )
        # .get: the folder is caption decoration, not something to fail over.
        where = entry.get("folder") or "portraits"
        self._caption.setText(
            f"{entry['resref']} · {where}{note}\n"
            f"Installed portraits: {len(self._entries):,}"
            + (f" · {len(self._pending)} marked for exclusion" if self._pending else "")
        )

    # -- Navigation -------------------------------------------------------- #
    def _move(self, step: int) -> None:
        """Select the entry ``step`` away (VB ``MoveSelection``)."""
        self._last_direction = step
        index = self._index()
        target = (0 if step > 0 else len(self._entries) - 1) if index < 0 else index + step
        if 0 <= target < len(self._entries):
            self._tree.setCurrentItem(self._tree.topLevelItem(target))
            self._tree.scrollToItem(self._tree.topLevelItem(target))

    def _on_row(self, *_a) -> None:
        for image in self._thumbs.values():
            image.clear()
        entry = self._current()
        if entry is not None:
            for size in PORTRAIT_SIZES:
                path = entry["sizes"].get(size)
                if path is not None:
                    pixmap = tga_to_pixmap(path, box=_SIZE_BOXES[size])
                    if pixmap is not None:
                        self._thumbs[size].setPixmap(pixmap)
        self._refresh_actions()

    def _on_find(self, text: str, step: int = 0) -> None:
        """Select the first portrait whose name contains ``text`` (VB TsbSearch)."""
        needle = text.strip().lower()
        if not needle:
            return
        start = self._index() + step
        order = list(range(len(self._entries)))
        order = order[start:] + order[:start]  # wrap, so Enter walks the matches
        for index in order:
            if needle in self._entries[index]["resref"].lower():
                self._tree.setCurrentItem(self._tree.topLevelItem(index))
                self._tree.scrollToItem(self._tree.topLevelItem(index))
                return

    # -- The image strip's click zones ------------------------------------- #
    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        """Left edge = previous, right edge = next, middle = edit (VB LpImages)."""
        from PySide6.QtCore import QEvent

        if watched is self._strip and self._entries:
            if event.type() == QEvent.Type.MouseMove:
                self._strip.setCursor(QCursor(self._zone_cursor(event.position().x())))
            elif event.type() == QEvent.Type.MouseButtonRelease:
                zone = self._zone(event.position().x())
                if zone:
                    self._move(zone)
                elif not self._edit_button.isHidden():
                    self._on_edit()
        return super().eventFilter(watched, event)

    def _zone(self, x: float) -> int:
        """-1 to go back, 1 to go forward, 0 for the editable middle."""
        index = self._index()
        if x <= _EDGE_MARGIN:
            return -1 if index > 0 else 0
        if x >= self._strip.width() - _EDGE_MARGIN:
            return 1 if index < len(self._entries) - 1 else 0
        return 0

    def _zone_cursor(self, x: float) -> Qt.CursorShape:
        zone = self._zone(x)
        if zone:
            return Qt.CursorShape.PointingHandCursor
        if not self._edit_button.isHidden():
            return Qt.CursorShape.WhatsThisCursor
        return Qt.CursorShape.ArrowCursor

    # -- Context menu ------------------------------------------------------ #
    def _on_context_menu(self, point) -> None:
        """The same actions as the toolbar (VB ``ContextMenuManager.Define``)."""
        menu = QMenu(self)
        for button in (
            self._exclude_button,
            self._apply_button,
            None,
            self._edit_button,
            self._installer_button,
            self._select_button,
        ):
            if button is None:
                menu.addSeparator()
                continue
            if button.isHidden() and button is self._edit_button:
                continue
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.addSeparator()
        menu.addAction(self._override_action)
        menu.addAction(self._next_action)
        sender = self.sender()
        menu.exec(sender.mapToGlobal(point) if sender is not None else QCursor.pos())

    # -- Actions ----------------------------------------------------------- #
    def _on_toggle_override(self, on: bool) -> None:
        self._store_setting("portrait_include_override", on)
        self._entries = self._load_entries()
        self._populate()

    def _on_select_mod(self) -> None:
        entry = self._current()
        if entry and entry.get("mod") and self._on_select is not None:
            self._on_select(entry["mod"])
            self.accept()

    def _on_exclude(self) -> None:
        """Mark for exclusion (VB ``RbExclude``) — nothing is written yet."""
        entry = self._current()
        if entry is None or not entry.get("mod"):
            return
        self._pending.add(entry["resref"])
        index = self._index()
        self._populate(select=index)
        if self._setting("portrait_always_select_next", True):
            self._move(self._last_direction)

    def _on_undo_exclude(self) -> None:
        entry = self._current()
        if entry is not None:
            self._pending.discard(entry["resref"])
            self._populate(select=self._index())

    def _on_apply_excludes(self) -> None:
        """Write the marks into each mod's wizard and rebuild (VB RbApplyExcludes)."""
        if not self._pending or self._controller is None:
            return
        by_mod: dict[str, list[str]] = {}
        for entry in self._entries:
            if entry["resref"] in self._pending and entry.get("mod"):
                by_mod.setdefault(entry["mod"], []).append(entry["resref"])
        if not by_mod:
            return
        mods = ", ".join(sorted(by_mod))
        if (
            QMessageBox.question(
                self,
                "Apply Excludes",
                f"Exclude {len(self._pending)} portrait(s) from {mods} and rebuild "
                f"their installers?\n\nThe files are not deleted — the Wizard Builder "
                f"can put them back.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        messages = []
        for mod, resrefs in sorted(by_mod.items()):
            result = self._controller.exclude_portraits_from_installer(mod, resrefs)
            messages.append(result.get("message", ""))
        self._pending.clear()
        self._entries = self._load_entries()
        self._populate()
        QMessageBox.information(self, "Portrait Manager", "\n".join(m for m in messages if m))

    def _on_create_installer(self) -> None:
        entry = self._current()
        if entry is None or not entry.get("mod") or self._controller is None:
            return
        built = self._controller.create_installer(entry["mod"])
        self._entries = self._load_entries()
        self._populate(select=self._index())
        QMessageBox.information(
            self,
            "Portrait Manager",
            f"Rebuilt '{entry['mod']}'s installer."
            if built
            else f"Could not rebuild '{entry['mod']}'s installer.",
        )

    def _on_edit(self) -> None:
        """Open the portrait's five files in the configured TGA editor."""
        editor = self._setting("tga_editor_path", "")
        entry = self._current()
        if not editor or entry is None:
            return
        import subprocess

        files = [str(p) for _s, p in sorted(entry["sizes"].items()) if p.exists()]
        if not files:
            QMessageBox.information(
                self, "Edit Portrait", "None of this portrait's files are on disk."
            )
            return
        try:
            subprocess.Popen([editor, *files])  # noqa: S603 - a path the user chose
        except OSError as exc:
            QMessageBox.warning(self, "Edit Portrait", f"Could not run {editor}:\n{exc}")

    def _on_link(self) -> None:
        url = self._setting("portrait_image_web_page", "")
        if url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))

    def _on_size_report(self) -> None:
        """List portraits whose pixel size is wrong (VB TsInvalidPortraitSizes)."""
        if self._controller is None:
            return
        report = self._controller.invalid_portrait_sizes(
            include_override=self._setting("portrait_include_override", False)
        )
        invalid = report["invalid"]
        if not invalid:
            QMessageBox.information(
                self,
                "Invalid Portrait Size Report",
                f"All {report['checked']:,} portrait image sizes are valid.",
            )
            return
        lines = [
            f"{row['file']}  —  {row['actual'][0]}×{row['actual'][1]} "
            f"(expected {row['expected'][0]}×{row['expected'][1]})  [{row['mod']}]"
            for row in invalid
        ]
        box = QMessageBox(self)
        box.setWindowTitle("Invalid Portrait Size Report")
        box.setText(
            f"{len(invalid):,} of {report['checked']:,} portrait image files have an "
            f"invalid size."
        )
        box.setDetailedText("\n".join(lines))
        box.exec()

    def _on_extract(self) -> None:
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        hak, _ = QFileDialog.getOpenFileName(
            self, "Select a hak file", "", "Hak files (*.hak);;All files (*)"
        )
        if not hak:
            return
        result = self._controller.extract_hak_portraits(Path(hak))
        self._entries = self._load_entries()
        self._populate()
        QMessageBox.information(self, "Portrait Manager", result.get("message", ""))

    @classmethod
    def show_for(
        cls, controller, on_select=None, parent: QWidget | None = None
    ) -> PortraitManager:
        """Build and show the manager for the controller's installed portraits."""
        dlg = cls(controller, on_select, parent)
        dlg.show()
        return dlg
