"""Formatted mod notes in the notes pane (VB ``RtModNotes``, a ``RichTextBoxPlus``).

Converts :mod:`vaultkeeper.core.rich_rtf` paragraphs to and from the pane's
``QTextDocument`` and provides the formatting bar: bold, italic, underline,
strike-through, font, size, text colour, highlight, alignment and Clear
Formatting. The pane's shortcuts (Ctrl+B/I/U) are scoped to the pane so they
never take a key from another text field. Text with no colour of its own follows
the light/dark theme.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontInfo,
    QGuiApplication,
    QIcon,
    QImage,
    QKeySequence,
    QPalette,
    QPixmap,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFontComboBox,
    QTextEdit,
    QToolBar,
    QWidget,
)

from vaultkeeper.core.rich_rtf import Paragraph, Style
from vaultkeeper.ui import resources as R

_ALIGN_TO_QT = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
    "justify": Qt.AlignmentFlag.AlignJustify,
}


def char_format(style: Style) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if style.bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if style.italic:
        fmt.setFontItalic(True)
    if style.underline:
        fmt.setFontUnderline(True)
    if style.strike:
        fmt.setFontStrikeOut(True)
    if style.font:
        fmt.setFontFamilies([style.font])
    if style.size:
        fmt.setFontPointSize(style.size)
    if style.color is not None:
        fmt.setForeground(QColor(*style.color))
    if style.background is not None:
        fmt.setBackground(QColor(*style.background))
    return fmt


def fill_notes(edit: QTextEdit, paragraphs: list[Paragraph]) -> None:
    """Show ``paragraphs`` in the pane (replacing what is there)."""
    doc = edit.document()
    doc.clear()
    cursor = QTextCursor(doc)
    for index, para in enumerate(paragraphs):
        block = QTextBlockFormat()
        block.setAlignment(_ALIGN_TO_QT.get(para.align, Qt.AlignmentFlag.AlignLeft))
        if index == 0:
            cursor.setBlockFormat(block)
        else:
            cursor.insertBlock(block, QTextCharFormat())
        for text, style in para.runs:
            cursor.insertText(text, char_format(style))
    edit.setCurrentCharFormat(QTextCharFormat())
    doc.setModified(False)


def _style_of(fmt: QTextCharFormat) -> Style:
    def rgb(brush_prop: int) -> tuple[int, int, int] | None:
        if not fmt.hasProperty(brush_prop):
            return None
        color = fmt.brushProperty(brush_prop).color()
        return (color.red(), color.green(), color.blue())

    families = fmt.fontFamilies() if fmt.hasProperty(QTextFormat.Property.FontFamilies) else None
    font = families[0] if isinstance(families, list) and families else None
    size = fmt.fontPointSize() if fmt.hasProperty(QTextFormat.Property.FontPointSize) else None
    return Style(
        bold=fmt.fontWeight() >= QFont.Weight.Bold,
        italic=fmt.fontItalic(),
        underline=fmt.fontUnderline(),
        strike=fmt.fontStrikeOut(),
        font=font or None,
        size=size or None,
        color=rgb(QTextFormat.Property.ForegroundBrush),
        background=rgb(QTextFormat.Property.BackgroundBrush),
    )


def notes_paragraphs(doc: QTextDocument) -> list[Paragraph]:
    """The pane's content as paragraphs of styled runs."""
    paragraphs: list[Paragraph] = []
    align_of = {v: k for k, v in _ALIGN_TO_QT.items()}
    block = doc.begin()
    while block.isValid():
        flags = block.blockFormat().alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
        para = Paragraph(align=align_of.get(flags, "left"))
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                text = fragment.text().replace(" ", "\n")
                para.add(text, _style_of(fragment.charFormat()))
            it += 1
        paragraphs.append(para)
        block = block.next()
    while paragraphs and not paragraphs[-1].runs and len(paragraphs) > 1:
        paragraphs.pop()
    return paragraphs


class NotesFormatBar(QToolBar):
    """The formatting bar above the notes pane."""

    def __init__(
        self,
        edit: QTextEdit,
        parent: QWidget | None = None,
        *,
        open_external: Callable[[], None] | None = None,
        find: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NotesFormatBar")
        self._edit = edit
        self._glyph_actions: list[tuple[QAction, str]] = []
        self.setIconSize(self.iconSize().scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio))

        # NIT's RichTextToolbar, in its order and with its icons and keys
        # (LazWorks RichTextToolbar.ButtonDesigner.vb): open with WordPad | cut,
        # copy, paste, paste as text | bold, italic, underline, strike-through,
        # colour | undo, redo | select all, find.
        if open_external is not None:
            self.open_external = self._button(
                "WordPad", "Open with your text editor", "Ctrl+O", open_external
            )
            self.addSeparator()
        self._button("Cut-006", "Cut", "Ctrl+X", edit.cut, scoped=False)
        self._button("CopyOffice2016", "Copy", "Ctrl+C", edit.copy, scoped=False)
        self._button("PasteW10", "Paste", "Ctrl+V", edit.paste, scoped=False)
        self._button("PasteText", "Paste as Text", "Ctrl+T", self._on_paste_text)
        self.addSeparator()

        self.bold = self._toggle("Bold_16x", "Bold", QKeySequence.StandardKey.Bold, self._on_bold)
        self.italic = self._toggle(
            "Italic_16x", "Italic", QKeySequence.StandardKey.Italic,
            lambda on: self._merge(lambda f: f.setFontItalic(on)),
        )
        self.underline = self._toggle(
            "Underline_16x", "Underline", QKeySequence.StandardKey.Underline,
            lambda on: self._merge(lambda f: f.setFontUnderline(on)),
        )
        self.strike = self._toggle(
            "StrikeThrough_16x", "Strike-through", "Ctrl+K",
            lambda on: self._merge(lambda f: f.setFontStrikeOut(on)),
        )
        color = QAction(self._glyph_icon("FontColor_16x"), "Font Colour…", self)
        self._glyph_actions.append((color, "FontColor_16x"))
        color.triggered.connect(self._on_color)
        self.addAction(color)
        self.addSeparator()
        self._button("UndoOffice2017", "Undo", "Ctrl+Z", edit.undo, scoped=False)
        self._button("RedoOffice2017", "Redo", "Ctrl+Y", edit.redo, scoped=False)
        self.addSeparator()
        self._button("SelectAllRows", "Select All", "Ctrl+A", edit.selectAll, scoped=False)
        if find is not None:
            self._button("Search16", "Find", "Ctrl+F", find, scoped=False)

        # Beyond NIT: font, size, highlight, alignment, clear formatting.
        self.addSeparator()
        self.font_box = QFontComboBox()
        self.font_box.setToolTip("Font")
        self.font_box.setMaximumWidth(160)
        self.font_box.currentFontChanged.connect(
            lambda font: self._merge(lambda f: f.setFontFamilies([font.family()]))
        )
        self.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.setToolTip("Size")
        self.size_box.addItems(["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28"])
        self.size_box.setMaximumWidth(56)
        self.size_box.textActivated.connect(self._on_size)
        self.addWidget(self.size_box)
        highlight = self.addAction(R.get_icon("fontandcolour x16x"), "Highlight…")
        highlight.triggered.connect(self._on_highlight)
        self.addSeparator()
        for label, align in (("Left", "left"), ("Centre", "center"), ("Right", "right")):
            action = self.addAction(label)
            action.setToolTip(f"Align {label.lower()}")
            action.triggered.connect(lambda _c=False, a=align: self._on_align(a))
        self.addSeparator()
        clear = self.addAction(R.get_icon("ClearDictionary_16x"), "Clear Formatting")
        clear.triggered.connect(self._on_clear)

        edit.currentCharFormatChanged.connect(self._sync)
        edit.cursorPositionChanged.connect(lambda: self._sync(edit.currentCharFormat()))
        self._sync(edit.currentCharFormat())

    # -- helpers ----------------------------------------------------------- #
    #: NIT's formatting glyphs are black line art; they are drawn in the text
    #: colour so they stay visible on a dark palette.
    _GLYPHS = ("Bold_16x", "Italic_16x", "Underline_16x", "StrikeThrough_16x", "FontColor_16x")

    def _glyph_icon(self, name: str) -> QIcon:
        """NIT's glyph, lightness-inverted on a dark palette so it stays legible.

        The glyphs are dark line work on a white fill; inverting lightness (hue
        and alpha kept) gives light lines on a dark fill. On a light palette the
        original icon is used as it is.
        """
        icon = R.get_icon(name)
        text = self.palette().color(QPalette.ColorRole.WindowText)
        if name not in self._GLYPHS or text.lightness() < 128:
            return icon
        pixmap = icon.pixmap(16, 16)
        if pixmap.isNull():
            return icon
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                if pixel.alpha():
                    h, sat, light, alpha = pixel.getHslF()
                    image.setPixelColor(x, y, QColor.fromHslF(max(h, 0.0), sat, 1 - light, alpha))
        tinted = QPixmap.fromImage(image)
        tinted.setDevicePixelRatio(pixmap.devicePixelRatio())
        return QIcon(tinted)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            for action, name in self._glyph_actions:
                action.setIcon(self._glyph_icon(name))

    def _toggle(self, icon: str, text: str, key, handler) -> QAction:  # noqa: ANN001
        action = QAction(self._glyph_icon(icon), text, self)
        self._glyph_actions.append((action, icon))
        action.setCheckable(True)
        if key is not None:
            action.setShortcut(QKeySequence(key))
            # Scoped to the notes pane: a window shortcut would take the key from
            # every other text field (see the Qt keyboard traps note).
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._edit.addAction(action)
            native = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
            action.setToolTip(f"{text} ({native})")
        action.toggled.connect(handler)
        self.addAction(action)
        return action

    def _button(
        self, icon: str, text: str, key: str, slot: Callable[[], None], *, scoped: bool = True
    ) -> QAction:
        """A plain toolbar button. ``scoped`` binds ``key`` to the notes pane only.

        Cut, copy, paste, undo, redo, select all and find are not bound here: the
        pane already has those keys (Qt's own, or the window's Find, which
        searches the notes when they have focus). The key is shown in the tip.
        """
        action = QAction(R.get_icon(icon), text, self)
        native = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
        action.setToolTip(f"{text} ({native})")
        if scoped:
            action.setShortcut(QKeySequence(key))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._edit.addAction(action)
        action.triggered.connect(lambda _c=False: slot())
        self.addAction(action)
        return action

    def _on_paste_text(self) -> None:
        """Paste the clipboard's plain text, in the formatting at the cursor."""
        text = QGuiApplication.clipboard().text()
        if text:
            self._edit.textCursor().insertText(text)

    def _merge(self, change) -> None:  # noqa: ANN001
        if getattr(self, "_syncing", False):
            return
        fmt = QTextCharFormat()
        change(fmt)
        cursor = self._edit.textCursor()
        cursor.mergeCharFormat(fmt)
        self._edit.mergeCurrentCharFormat(fmt)
        self._edit.setFocus()

    def _on_bold(self, on: bool) -> None:
        self._merge(lambda f: f.setFontWeight(QFont.Weight.Bold if on else QFont.Weight.Normal))

    def _on_size(self, text: str) -> None:
        try:
            size = float(text)
        except ValueError:
            return
        if size > 0:
            self._merge(lambda f: f.setFontPointSize(size))

    def _on_color(self) -> None:
        color = QColorDialog.getColor(self._edit.textColor(), self, "Text Colour")
        if color.isValid():
            self._merge(lambda f: f.setForeground(color))

    def _on_highlight(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.yellow, self, "Highlight")
        if color.isValid():
            self._merge(lambda f: f.setBackground(color))

    def _on_align(self, align: str) -> None:
        self._edit.setAlignment(_ALIGN_TO_QT[align])
        self._edit.document().setModified(True)

    def _on_clear(self) -> None:
        """Back to the theme's plain text (VB has no such button; convenient)."""
        cursor = self._edit.textCursor()
        cursor.setCharFormat(QTextCharFormat())
        self._edit.setCurrentCharFormat(QTextCharFormat())
        self._edit.document().setModified(True)

    def _sync(self, fmt: QTextCharFormat) -> None:
        self._syncing = True
        try:
            self.bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
            self.italic.setChecked(fmt.fontItalic())
            self.underline.setChecked(fmt.fontUnderline())
            self.strike.setChecked(fmt.fontStrikeOut())
            # With no font of its own the text is in the pane's font: show that.
            default = self._edit.font()
            families = fmt.fontFamilies() if fmt.hasProperty(
                QTextFormat.Property.FontFamilies
            ) else None
            family = families[0] if isinstance(families, list) and families else None
            # The family actually drawn (a nominal "Sans Serif" or the hidden
            # system UI font is not in the list, which then shows its first entry).
            shown = family or QFontInfo(default).family()
            if self.font_box.findText(shown) >= 0:
                self.font_box.setCurrentFont(QFont(shown))
            else:
                self.font_box.setCurrentIndex(-1)
                self.font_box.setEditText("Default font")
            size = fmt.fontPointSize() or default.pointSizeF()
            self.size_box.setEditText(f"{size:g}")
        finally:
            self._syncing = False
