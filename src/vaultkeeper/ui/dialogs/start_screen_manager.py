"""StartScreenManager — browse NWN start-screen (loadscreen) images (VB StartScreenManager).

VB's Start Screen Manager lets the user manage the image NWN shows on its main
menu. The NIT-managed loadscreen images are shown in a list (the active one
marked, auto-excluded ones dimmed) beside a preview of the selected image, with a
status summary.

The ribbon is the original's, in the original's order and with its own icons —
see ``_TOOLBAR`` and ``StartScreenManager.Designer.vb``: Previous/Next, Add
Folders/Add Files, Rename/Export/Delete, Install, Options, Help, Slide Show, and
the search box. The preview doubles as a navigation surface, as in VB: its left
edge goes back, its right edge forward, and the middle opens the image full size.

The Options menu carries what the help topic documents — Auto-Start Screen
Selection, add/remove this image from the auto-exclusion list, the Information
Report (which is also where exclusions are cleared), the slide-show interval and
continuous flag, the prefixed-screens editor, and Uninstall.

Not ported, deliberately: **Import Start Screen Files** and **Clear Exported
Start Screen Files**. Both are gated in VB on a Shared NIT Store, which this port
does not have — it is single-machine by design — so there is nothing for them to
import from or clear.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap
from vaultkeeper.ui.dialogs.settings_access import SettingsAccess
from vaultkeeper.ui.theme import status_colour

#: The preview is scaled to fit this box; loadscreens are wide, so max dim is width.
_PREVIEW_BOX = 480

#: How close to an edge of the preview counts as "back/forward" rather than
#: "open this image" (VB ``MousePosMargin``).
_EDGE_MARGIN = 40

# Dimmed colour for auto-excluded images (won't be picked by the slideshow).
def _excluded_colour() -> QColor:
    return status_colour("disabled")


class StartScreenManager(SettingsAccess, QDialog):
    """Browse the managed loadscreen images with a preview + auto-exclusion action."""

    def __init__(
        self, report: dict, controller=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("NWN's Start Screen Manager")
        self.setWindowIcon(R.get_icon("Image"))
        self.resize(760, 520)
        self._controller = controller
        self._report = report
        self._images: list[dict] = report.get("images", [])

        self._init_settings()
        self._slideshow_timer: QTimer | None = None

        outer = QVBoxLayout(self)
        outer.addWidget(self._build_toolbar())

        panes = QHBoxLayout()
        outer.addLayout(panes, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_row)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        panes.addWidget(self._list)

        right = QVBoxLayout()
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(300)
        # The preview is a navigation surface, as in VB: the cursor over its left
        # edge goes back, its right edge forward, and the middle opens the image.
        self._preview.setMouseTracking(True)
        self._preview.installEventFilter(self)
        self._preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._preview.customContextMenuRequested.connect(self._on_context_menu)
        right.addWidget(self._preview, 1)
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        right.addWidget(self._detail)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        right.addWidget(self._summary)
        panes.addLayout(right, 1)

        # Everything the original puts on its ribbon is on the ribbon. What is
        # left here is our own addition plus the dialog's Close.
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._add_hak_btn = QPushButton("Add Hak…")
        self._add_hak_btn.setToolTip(
            "Add TGA images extracted from a .hak file (not in the original tool)"
        )
        self._add_hak_btn.clicked.connect(self._on_add_hak)
        buttons.addWidget(self._add_hak_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        outer.addLayout(buttons)

        self._populate()

    # -- Toolbar, options, search ------------------------------------------ #
    #: The search box only appears past this many images (VB: "only enabled when
    #: you have 10 or more start screen images").
    SEARCH_THRESHOLD = 10

    #: The ribbon as ``StartScreenManager.Designer.vb`` builds it: ``RbPrevious,
    #: RbNext, |, RbAddFolders, RbAddFiles, |, RbRename, RbExport, RbDeleteFile,
    #: |, RbInstall, RbOptions, RbLoadscreenHelp, RbSlideshow`` — each icon the
    #: resource its ``.Image =`` line names. ``None`` is a separator.
    _TOOLBAR = (
        ("_prev_btn", "Previous", "Backwards_16x", "Show the previous image"),
        ("_next_btn", "Next", "Forwards_16x", "Show the next image"),
        None,
        ("_add_folder_btn", "Add Folders", "AddFolder_32x",
         "Add every TGA image found under a folder"),
        ("_add_files_btn", "Add Files", "AddImage_32x", "Add one or more TGA images"),
        None,
        ("_rename_btn", "Rename", "Rename_32x", "Rename the selected image"),
        ("_export_btn", "Export", "Export Arrow_32x",
         "Copy the selected image(s) to a folder"),
        ("_delete_btn", "Delete", "Exclude_32x", "Delete the selected image(s)"),
        None,
        ("_install_btn", "Install", "Install Package 32x32",
         "Install the selected image as NWN's start screen"),
    )

    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar()
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        bar.setIconSize(QSize(24, 24))
        bar.setMovable(False)

        handlers = {
            "_prev_btn": lambda: self._move(-1),
            "_next_btn": lambda: self._move(1),
            "_add_folder_btn": self._on_add_folder,
            "_add_files_btn": self._on_add_files,
            "_rename_btn": self._on_rename,
            "_export_btn": self._on_export,
            "_delete_btn": self._on_delete,
            "_install_btn": self._on_install,
        }
        for entry in self._TOOLBAR:
            if entry is None:
                bar.addSeparator()
                continue
            attr, label, icon, tip = entry
            button = QToolButton()
            button.setText(label)
            button.setIcon(R.get_icon(icon))
            button.setToolTip(tip)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.clicked.connect(handlers[attr])
            setattr(self, attr, button)
            bar.addWidget(button)

        self._options_btn = QToolButton()
        self._options_btn.setText("Options")
        self._options_btn.setIcon(R.get_icon("SettingsBlueCog_32x"))
        self._options_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        self._options_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._options_btn.setMenu(self._build_options_menu())
        bar.addWidget(self._options_btn)

        self._help_btn = QToolButton()
        self._help_btn.setText("Help")
        self._help_btn.setIcon(R.get_icon("HelpIcon"))
        self._help_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._help_btn.clicked.connect(self._on_help)
        bar.addWidget(self._help_btn)

        self._slideshow_btn = QToolButton()
        self._slideshow_btn.setText("Slide Show")
        self._slideshow_btn.setIcon(R.get_icon("StatusRun_16x"))
        self._slideshow_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._slideshow_btn.setToolTip(
            "Step through every image. Shift+click to cycle automatically."
        )
        self._slideshow_btn.clicked.connect(self._on_slideshow)
        bar.addWidget(self._slideshow_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Find image")  # VB BtSearch
        self._search.setClearButtonEnabled(True)
        self._search.setMaximumWidth(200)
        self._search.textChanged.connect(lambda text: self._find(text))
        self._search.installEventFilter(self)  # Escape closes it, as in VB
        self._search_action = bar.addWidget(self._search)
        return bar

    def _on_help(self) -> None:
        from vaultkeeper.ui.dialogs.help_viewer import HelpViewer

        self._help_viewer = HelpViewer.show_for_control("RbLoadscreenHelp", self)

    def _build_options_menu(self) -> QMenu:
        menu = QMenu(self)
        self._auto_action = QAction("Auto-Start Screen Selection", self)
        self._auto_action.setCheckable(True)
        self._auto_action.setChecked(self._setting("auto_loadscreen", False))
        self._auto_action.setToolTip(
            "Install the next image each time you close the game, so a different "
            "start screen greets you next launch"
        )
        self._auto_action.toggled.connect(
            lambda on: self._store_setting("auto_loadscreen", on)
        )
        menu.addAction(self._auto_action)

        # One entry that reads as Add or Remove for the selected image, rather
        # than a "Toggle" that never says which way it will go (VB shows exactly
        # one of RbAddAutoExclusion / RbRemoveAutoExclusion).
        self._exclusion_action = QAction("Add to Auto Exclusions List", self)
        self._exclusion_action.triggered.connect(self._on_toggle_exclude)
        menu.addAction(self._exclusion_action)

        self._report_action = QAction(R.get_icon("FilterOff"), "View Information Report", self)
        self._report_action.triggered.connect(self._on_info_report)
        menu.addAction(self._report_action)

        menu.addSeparator()
        self._continuous_action = QAction("Continuous Slide Show", self)
        self._continuous_action.setCheckable(True)
        self._continuous_action.setChecked(self._setting("slideshow_continuous", False))
        self._continuous_action.toggled.connect(
            lambda on: self._store_setting("slideshow_continuous", on)
        )
        menu.addAction(self._continuous_action)
        interval = QAction(R.get_icon("Time_Green_16x"), "Slide Show Interval…", self)
        interval.triggered.connect(self._on_slideshow_interval)
        menu.addAction(interval)

        menu.addSeparator()
        repair = QAction(
            R.get_icon("Hammer_Builder_16xLG"), "Repair Prefixed Image Exclusions", self
        )
        repair.setToolTip(
            "Exclude every prefixed image that is not excluded from the automatic cycle"
        )
        repair.triggered.connect(self._on_repair_prefixed)
        menu.addAction(repair)
        prefixes = QAction(R.get_icon("Hammer_Builder_16xLG"), "Prefixed Start Screens…", self)
        prefixes.triggered.connect(self._on_edit_prefixes)
        menu.addAction(prefixes)
        self._uninstall_action = QAction(
            R.get_icon("Uninstall"), "Uninstall the Start Screen's Mod", self
        )
        self._uninstall_action.setToolTip(
            "Put back whichever start screen the game would otherwise show"
        )
        self._uninstall_action.triggered.connect(self._on_uninstall)
        menu.addAction(self._uninstall_action)
        return menu

    # -- Navigation and search --------------------------------------------- #
    def _move(self, step: int) -> None:
        """Select the image ``step`` away, honouring an active search filter."""
        matches = self._matching_rows()
        if not matches:
            return
        row = self._list.currentRow()
        if row in matches:
            position = matches.index(row) + step
            if not 0 <= position < len(matches):
                return
            target = matches[position]
        else:
            target = matches[0] if step > 0 else matches[-1]
        self._list.setCurrentRow(target)

    def _matching_rows(self) -> list[int]:
        """Row indices matching the search box — every row when it is empty.

        VB: "The standard Start Screen navigation options will also use your
        search criteria", so Previous/Next walk the matches rather than the list.
        """
        needle = self._search.text().strip().lower()
        if not needle:
            return list(range(len(self._images)))
        return [i for i, row in enumerate(self._images) if needle in row["name"].lower()]

    def _find(self, text: str) -> None:
        matches = self._matching_rows()
        if text.strip() and matches and self._list.currentRow() not in matches:
            self._list.setCurrentRow(matches[0])
        self._update_action_state()

    def _close_search(self) -> None:
        """Clear the box (VB closes it on add / rename / delete)."""
        self._search.clear()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        from PySide6.QtCore import QEvent

        if watched is self._search and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._close_search()
                return True
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._move(-1 if event.key() == Qt.Key.Key_Up else 1)
                return True
        elif watched is self._preview and self._images:
            if event.type() == QEvent.Type.MouseMove:
                self._preview.setCursor(QCursor(self._zone_cursor(event.position().x())))
            elif event.type() == QEvent.Type.MouseButtonRelease:
                zone = self._zone(event.position().x())
                if zone:
                    self._move(zone)
                else:
                    self._on_show_image()
        return super().eventFilter(watched, event)

    def _zone(self, x: float) -> int:
        """-1 to go back, 1 to go forward, 0 to open the image (VB cursor zones)."""
        matches = self._matching_rows()
        row = self._list.currentRow()
        position = matches.index(row) if row in matches else -1
        if x <= _EDGE_MARGIN:
            return -1 if position > 0 else 0
        if x >= self._preview.width() - _EDGE_MARGIN:
            return 1 if -1 < position < len(matches) - 1 else 0
        return 0

    def _zone_cursor(self, x: float) -> Qt.CursorShape:
        return (
            Qt.CursorShape.PointingHandCursor
            if self._zone(x)
            else Qt.CursorShape.WhatsThisCursor
        )

    def _on_show_image(self) -> None:
        """Open the selected image full size (VB's Display Image)."""
        entry = self._current_entry()
        if entry is None:
            return
        from vaultkeeper.ui.dialogs.image_viewer import ImageViewer

        ImageViewer.show_for(Path(entry["path"]), parent=self)

    # -- Options actions --------------------------------------------------- #
    def _on_slideshow(self) -> None:
        """Step through the images; Shift+click cycles them automatically."""
        from PySide6.QtWidgets import QApplication

        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        if self._slideshow_timer is not None:
            self._stop_slideshow()
            return
        if not shift:
            self._move(1)
            return
        self._slideshow_timer = QTimer(self)
        self._slideshow_timer.setInterval(
            max(1, int(self._setting("slideshow_interval", 5))) * 1000
        )
        self._slideshow_timer.timeout.connect(self._slideshow_step)
        self._slideshow_timer.start()
        self._slideshow_btn.setText("Stop Slide Show")

    def _slideshow_step(self) -> None:
        matches = self._matching_rows()
        row = self._list.currentRow()
        last = matches and row == matches[-1]
        if last and not self._setting("slideshow_continuous", False):
            self._stop_slideshow()
            return
        if last:
            self._list.setCurrentRow(matches[0])  # wrap, per Continuous
        else:
            self._move(1)

    def _stop_slideshow(self) -> None:
        if self._slideshow_timer is not None:
            self._slideshow_timer.stop()
            self._slideshow_timer = None
        self._slideshow_btn.setText("Slide Show")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._stop_slideshow()  # a timer outliving its dialog would fire into nothing
        super().closeEvent(event)

    def _on_slideshow_interval(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        seconds, ok = QInputDialog.getInt(
            self,
            "Slide Show Interval",
            "Seconds each image is shown:",
            int(self._setting("slideshow_interval", 5)),
            1,
            120,
        )
        if ok:
            self._store_setting("slideshow_interval", seconds)

    def _on_info_report(self) -> None:
        """A summary of included/excluded images (VB RbInfoReport)."""
        included = [r["name"] for r in self._images if not r["excluded"]]
        excluded = [r["name"] for r in self._images if r["excluded"]]
        box = QMessageBox(self)
        box.setWindowTitle("Start Screen Information Report")
        box.setText(
            f"{len(self._images):,} start screen image(s): {len(included):,} included, "
            f"{len(excluded):,} excluded from the automatic cycle."
        )
        detail = ["Excluded:", *(f"  {name}" for name in excluded)] if excluded else []
        if detail:
            box.setDetailedText("\n".join(detail))
        if excluded and self._controller is not None:
            clear = box.addButton("Remove Exclusions", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is clear:
                self._on_clear_exclusions()
            return
        box.exec()

    def _on_uninstall(self) -> None:
        """Put back whatever start screen the game would otherwise use."""
        if self._controller is None:
            return
        if (
            QMessageBox.question(
                self,
                "Uninstall Start Screen",
                "Uninstall the managed start screen image?\n\nThe game falls back to "
                "another installed mod's start screen, or its own.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.uninstall_loadscreen()
        self._refresh()
        self._status(result.get("message", "Uninstalled."))

    def _on_repair_prefixed(self) -> None:
        """Re-exclude prefixed images that slipped out of the list (VB RbRepairPrefixed)."""
        if self._controller is None:
            return
        result = self._controller.repair_prefixed_exclusions()
        self._refresh()
        self._status(result["message"])
        QMessageBox.information(self, "Repair Prefixed Images", result["message"])

    def _on_edit_prefixes(self) -> None:
        if self._controller is None:
            return
        from vaultkeeper.ui.dialogs.prefix_editor import PrefixEditor

        PrefixEditor.edit(self._controller, parent=self)
        self._refresh()

    def _on_add_files(self) -> None:
        """Add individual TGA files (VB RbAddFiles, beside Add-from-folders)."""
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select start screen images", "", "TGA images (*.tga);;All files (*)"
        )
        if not files:
            return
        result = self._controller.add_loadscreen_images([Path(f) for f in files])
        self._close_search()
        self._refresh()
        self._status(result.get("message", f"Added {result.get('added', 0)} image(s)."))

    # -- Context menu ------------------------------------------------------ #
    def _on_context_menu(self, point) -> None:
        """The same operations as the toolbar (VB CmImages)."""
        menu = QMenu(self)
        for button in (
            self._install_btn,
            None,
            self._add_files_btn,
            self._add_folder_btn,
            self._add_hak_btn,
            None,
            self._rename_btn,
            self._delete_btn,
            self._export_btn,
        ):
            if button is None:
                menu.addSeparator()
                continue
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.addSeparator()
        menu.addAction(self._exclusion_action)
        menu.addAction(self._report_action)
        sender = self.sender()
        menu.exec(sender.mapToGlobal(point) if sender is not None else QCursor.pos())

    # -- Population -------------------------------------------------------- #
    def _populate(self, select: str | None = None) -> None:
        """Fill the list from the current report, optionally reselecting ``select``."""
        self._list.blockSignals(True)
        self._list.clear()
        for row in self._images:
            label = row["name"]
            if row["active"]:
                label = f"★ {label}"  # ★ active image
            item = QListWidgetItem(label)
            tips: list[str] = []
            if row["excluded"]:
                item.setForeground(_excluded_colour())
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                tips.append("Auto-excluded (skipped by the slideshow)")
            if row.get("prefixed"):
                tips.append(
                    "Prefixed (enabled)"
                    if row.get("filter_prefixed")
                    else "Prefixed (disabled)"
                )
            if tips:
                item.setToolTip(" · ".join(tips))
            self._list.addItem(item)
        self._list.blockSignals(False)

        self._summary.setText(self._report.get("summary", ""))
        has_controller = self._controller is not None
        # Exclusions are cleared from the Information Report, where the list of
        # what would be cleared is actually in front of you (VB RbInfoReport's
        # "Remove Exclusions").
        self._report_action.setEnabled(has_controller)

        if self._images:
            target = 0
            if select is not None:
                for i, row in enumerate(self._images):
                    if row["name"] == select:
                        target = i
                        break
            self._list.setCurrentRow(target)
        else:
            self._preview.setText("No loadscreen images to display.")
        self._update_action_state()

    def _on_row(self, row: int) -> None:
        self._preview.clear()
        self._detail.clear()
        if row < 0 or row >= len(self._images):
            self._update_action_state()
            return
        entry = self._images[row]
        self._update_action_state()
        pixmap = tga_to_pixmap(Path(entry["path"]), box=_PREVIEW_BOX)
        if pixmap is not None:
            self._preview.setPixmap(pixmap)
        else:
            self._preview.setText("(unable to preview this image)")

        flags = []
        if entry["active"]:
            flags.append("active")
        if entry["excluded"]:
            flags.append("auto-excluded")
        if entry.get("prefixed"):
            flags.append(
                "prefixed" if entry.get("filter_prefixed") else "prefixed (disabled)"
            )
        suffix = f"  — {', '.join(flags)}" if flags else ""
        self._detail.setText(f"{entry['name']}  ({entry['size_text']}){suffix}")

    # -- Actions ----------------------------------------------------------- #
    def _current_entry(self) -> dict | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._images):
            return self._images[row]
        return None

    def _refresh(self, select: str | None = None) -> None:
        self._report = self._controller.loadscreens_report()
        self._images = self._report.get("images", [])
        self._populate(select=select)

    def _on_toggle_exclude(self) -> None:
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        name = entry["name"]
        if entry["excluded"]:
            self._controller.remove_loadscreen_exclusion(name)
        else:
            self._controller.add_loadscreen_exclusion(name)
        self._refresh(select=name)

    def _on_clear_exclusions(self) -> None:
        if self._controller is None:
            return
        entry = self._current_entry()
        select = entry["name"] if entry else None
        self._controller.clear_loadscreen_exclusions()
        self._refresh(select=select)

    def _on_install(self) -> None:
        """Install the selected image as NWN's start screen (VB RbInstall)."""
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        name = entry["name"]
        result = self._controller.install_loadscreen(name)
        self._status(result.get("message", ""))
        self._refresh(select=name)

    def _on_add_folder(self) -> None:
        """Add TGA images found under a chosen folder (VB Add-from-Folders)."""
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Select a folder of TGA images")
        if not folder:
            return
        result = self._controller.add_loadscreen_folders([Path(folder)])
        self._status(result.get("message", ""))
        self._refresh()

    def _on_add_hak(self) -> None:
        """Add TGA images extracted from a chosen .hak file (VB Add-from-Hak)."""
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        hak, _ = QFileDialog.getOpenFileName(
            self, "Select a hak file", "", "Hak files (*.hak);;All files (*)"
        )
        if not hak:
            return
        result = self._controller.add_loadscreen_from_hak(Path(hak))
        self._status(result.get("message", ""))
        self._refresh()

    def _on_delete(self) -> None:
        """Delete the selected image(s) (VB RbDeleteFile)."""
        if self._controller is None:
            return
        entries = [self._images[i.row()] for i in self._list.selectedIndexes()]
        if not entries:
            entry = self._current_entry()
            entries = [entry] if entry else []
        if not entries:
            return
        from PySide6.QtWidgets import QMessageBox

        names = [e["name"] for e in entries]
        plural = "image" if len(names) == 1 else "images"
        if (
            QMessageBox.question(
                self,
                "Delete Start Screen Images",
                f"Delete {len(names)} start screen {plural}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_loadscreen_images(names)
        self._status(result.get("message", ""))
        self._refresh()

    def _on_export(self) -> None:
        """Export the selected image(s) to a chosen folder (VB RbExport)."""
        if self._controller is None:
            return
        entries = [self._images[i.row()] for i in self._list.selectedIndexes()]
        if not entries:
            entry = self._current_entry()
            entries = [entry] if entry else []
        if not entries:
            self._status("Select an image to export first.")
            return
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        target = QFileDialog.getExistingDirectory(self, "Export start screen images to…")
        if not target:
            return
        names = [e["name"] for e in entries]
        result = self._controller.export_loadscreen_images(names, Path(target))
        self._status(result.get("message", ""))

    def _on_rename(self) -> None:
        """Rename the selected image (VB RbRename — validation in the controller)."""
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        from PySide6.QtWidgets import QInputDialog

        old = entry["name"]
        new, ok = QInputDialog.getText(self, "Rename Image File", "New name:", text=old)
        if not ok or not new:
            return
        result = self._controller.rename_loadscreen_image(old, new)
        self._status(result.get("message", ""))
        self._refresh(select=result.get("name", old))

    def _status(self, text: str) -> None:
        if text:
            self._summary.setText(text)

    def _update_action_state(self) -> None:
        has_controller = self._controller is not None
        entry = self._current_entry()
        has_selection = entry is not None
        self._install_btn.setEnabled(has_controller and has_selection)
        self._delete_btn.setEnabled(has_controller and has_selection)
        self._rename_btn.setEnabled(has_controller and has_selection)
        self._export_btn.setEnabled(has_controller and has_selection)
        self._add_folder_btn.setEnabled(has_controller)
        self._add_files_btn.setEnabled(has_controller)
        self._add_hak_btn.setEnabled(has_controller)

        matches = self._matching_rows()
        row = self._list.currentRow()
        position = matches.index(row) if row in matches else -1
        self._prev_btn.setEnabled(position > 0)
        self._next_btn.setEnabled(-1 < position < len(matches) - 1)
        self._slideshow_btn.setEnabled(len(matches) > 1)

        # VB shows exactly one of RbAddAutoExclusion / RbRemoveAutoExclusion, so
        # the entry says which way it goes instead of being a "toggle".
        excluded = bool(entry and entry["excluded"])
        self._exclusion_action.setText(
            "Remove from Auto Exclusions List" if excluded
            else "Add to Auto Exclusions List"
        )
        self._exclusion_action.setIcon(
            R.get_icon("Remove_Minus_16x" if excluded else "action_add_16xLG")
        )
        self._exclusion_action.setEnabled(has_controller and has_selection)

        # The search box only exists past the threshold, as in VB. Hiding is done
        # on the toolbar's action: a QToolBar re-shows the widget itself.
        wanted = len(self._images) >= self.SEARCH_THRESHOLD and has_controller
        if not wanted and self._search.text():
            self._search.clear()  # a hidden filter must not keep filtering
        self._search_action.setVisible(wanted)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> StartScreenManager:
        """Build and show the manager for the controller's loadscreen report."""
        dlg = cls(controller.loadscreens_report(), controller, parent)
        dlg.show()
        return dlg
