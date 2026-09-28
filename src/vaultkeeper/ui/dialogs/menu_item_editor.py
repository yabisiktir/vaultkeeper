"""The Run / Web menu item editor (VB ``MenuItemEditor``).

One item at a time, as NIT edits them: the menu text (at most 35 characters,
with a counter that turns amber then red as it fills, and no repeat of another
item's text) and the location: a program file for the Run menu, a web address
for the Web menu. Save stays off until the location is usable: an existing
file, or a well-formed URL that answers when Save is pressed.

A new web item starts from a web address on the clipboard, and picks one up
when you come back from the browser that Browse opened (VB ``CheckOnActivate``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.urls import is_url
from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.theme import status_colour

MAX_CHARACTERS = 35  # VB MenuItemEditor.MaxCharacters


def web_page_exists(url: str) -> bool:
    """Whether ``url`` answers (VB ``WebPageExists``), with a short timeout."""
    from urllib.request import Request, urlopen

    for method in ("HEAD", "GET"):
        try:
            with urlopen(Request(url, method=method), timeout=8) as response:  # noqa: S310
                if response.status < 400:
                    return True
        except Exception:  # noqa: BLE001 - any failure means "cannot be opened"
            continue
    return False


def _menu_text_for(program: Path) -> str:
    """NIT's suggested menu text for a program: its name, capitalised."""
    if program.name.lower() == "acrord32.exe":
        return "Adobe Acrobat Reader"
    stem = program.stem
    return stem[:1].upper() + stem[1:]


class MenuItemEditor(QDialog):
    """Create or change one Run-menu program or Web-menu link."""

    def __init__(
        self,
        kind: str,
        *,
        text: str = "",
        location: str = "",
        other_texts: list[str] | None = None,
        page_exists: Callable[[str], bool] = web_page_exists,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if kind not in ("run", "web"):
            raise ValueError(kind)
        self._web = kind == "web"
        self._creating = not (text or location)
        self._others = {t.replace("&", "") for t in other_texts or []}
        self._page_exists = page_exists
        self._check_clipboard = False
        operation = "Create" if self._creating else "Update"
        self.setWindowTitle(f"{operation} {'Web' if self._web else 'Run'} Menu Item")
        self.setWindowIcon(R.get_icon("ASPNETWeb_16x" if self._web else "FindinFiles_6299"))
        geometry.remember(self, "MenuItemEditor", 575, 260)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        info = QLabel(
            "The text you enter is displayed on the list of items that are displayed "
            f"when you click the {'Web' if self._web else 'Run'} menu. Usually, this is "
            + ("the web page title." if self._web else "the name of the program.")
        )
        info.setWordWrap(True)
        grid.addWidget(info, 0, 0, 1, 2)
        grid.addWidget(QLabel("Menu Text:"), 1, 0)
        text_row = QHBoxLayout()
        self.menu_text = QLineEdit(text)
        self.menu_text.setMaxLength(MAX_CHARACTERS)
        text_row.addWidget(self.menu_text, 1)
        self.char_count = QProgressBar()
        self.char_count.setRange(0, MAX_CHARACTERS)
        self.char_count.setTextVisible(True)
        self.char_count.setMinimumWidth(190)
        text_row.addWidget(self.char_count)
        grid.addLayout(text_row, 1, 1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(line, 2, 0, 1, 2)

        grid.addWidget(QLabel("Web Address (URL):" if self._web else "Program Location:"), 3, 0)
        location_row = QHBoxLayout()
        self.location = QLineEdit(location)
        location_row.addWidget(self.location, 1)
        self.browse = QToolButton()
        self.browse.setIcon(R.get_icon("ASPNETWeb_16x" if self._web else "FindinFiles_6299"))
        self.browse.setToolTip("Browse the web" if self._web else "Browse for file")
        self.browse.clicked.connect(self._on_browse)
        location_row.addWidget(self.browse)
        grid.addLayout(location_row, 3, 1)
        location_info = QLabel(
            "Paste or type in the address of the web page (URL) or click the Browse "
            "button to open your Browser."
            if self._web
            else "Type in the full path of the program's executable file or click the "
            "Browse button to select the file."
        )
        location_info.setWordWrap(True)
        grid.addWidget(location_info, 4, 1)
        grid.setColumnStretch(1, 1)

        footer = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer.addWidget(self.save_button)
        footer.addWidget(cancel)
        layout.addStretch(1)
        layout.addLayout(footer)

        if self._web and self._creating:
            clip = QGuiApplication.clipboard().text().strip()
            if is_url(clip):
                self.location.setText(clip)
        self.menu_text.textChanged.connect(self._validate)
        self.location.textChanged.connect(self._on_location_changed)
        self._validate()
        (self.menu_text if text else self.location).setFocus()

    # -- The two values ---------------------------------------------------- #
    @property
    def item_text(self) -> str:
        return self.menu_text.text().strip()

    @property
    def item_location(self) -> str:
        return self.location.text().strip()

    # -- Validation (VB TxMenuText_TextChanged / Tx*Location_TextChanged) --- #
    def _on_location_changed(self) -> None:
        if not self._web and not self.item_text:
            path = Path(self.item_location)
            if self.item_location and path.is_file():
                self.menu_text.setText(_menu_text_for(path))
        self._validate()

    def _location_ok(self) -> bool:
        if self._web:
            return is_url(self.item_location)
        return bool(self.item_location) and Path(self.item_location).is_file()

    def _validate(self) -> None:
        self._show_count()
        text = self.item_text
        self.status.setText("")
        if text and text.replace("&", "") in self._others:
            self._error("Menu Text has already been used.")
            self.save_button.setEnabled(False)
            return
        self.save_button.setEnabled(bool(text) and self._location_ok())

    def _show_count(self) -> None:
        used = len(self.menu_text.text().replace("&", ""))
        self.char_count.setValue(min(used, MAX_CHARACTERS))
        self.char_count.setFormat(f"{used} out of {MAX_CHARACTERS} characters used.")
        share = used / MAX_CHARACTERS
        # VB DisplayCharacterCount: green below 60 %, amber below 80 %, then red.
        colour = status_colour(
            "installed" if share < 0.6 else "overridden" if share < 0.8 else "duplicate"
        )
        palette = self.char_count.palette()
        palette.setColor(QPalette.ColorRole.Highlight, colour)
        self.char_count.setPalette(palette)

    def _say(self, message: str, *, error: bool = False) -> None:
        # Through the palette, not a style sheet (which would restyle tooltips).
        palette = self.palette()
        if error:
            palette.setColor(QPalette.ColorRole.WindowText, status_colour("duplicate"))
        self.status.setPalette(palette)
        self.status.setText(message)

    def _error(self, message: str) -> None:
        self._say(message, error=True)

    # -- Actions ----------------------------------------------------------- #
    def _on_browse(self) -> None:
        if self._web:
            # VB BhWebBrowseLocation: open the browser; the address is picked up
            # from the clipboard when this window is active again.
            QDesktopServices.openUrl(QUrl("https://neverwintervault.org/"))
            self._check_clipboard = True
            return
        start = self.item_location
        if start and not Path(start).is_dir():
            start = str(Path(start).parent)
        name = self.item_text or "a program or document to add to the Run menu"
        chosen, _ = QFileDialog.getOpenFileName(self, f"Select {name}", start)
        if chosen:
            self.location.setText(chosen)
            if self.save_button.isEnabled():
                self.save_button.setFocus()

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self._check_clipboard = self._web
            elif self._check_clipboard:
                self._check_clipboard = False
                clip = QGuiApplication.clipboard().text().strip()
                if not self.item_location and is_url(clip):
                    self.location.setText(clip)

    def _on_save(self) -> None:
        if self._web:
            self._say("Ensuring that the web page can be accessed...")
            self.repaint()
            if not self._page_exists(self.item_location):
                self._error("The web address (URL) you specified cannot be opened")
                self.save_button.setEnabled(False)
                return
        self.accept()
