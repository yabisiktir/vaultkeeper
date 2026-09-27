"""Formatted RTF for mod notes: RTF <-> paragraphs of styled runs.

NIT's notes pane is a Windows ``RichTextBox``: notes can carry bold, italic,
underline, strike-through, fonts, sizes, colours, highlights and alignment. The
plain-text layer in :mod:`vaultkeeper.core.rtf` loses all of that, so a note NIT
formatted lost its formatting the moment it was edited here (logic audit 3i N4).

This module reads the subset a ``RichTextBox`` writes (and Word/WordPad files
commonly carry) into :class:`Paragraph` objects, and writes them back as RTF the
Windows control opens. It knows nothing about Qt; the notes pane converts runs to
and from a ``QTextDocument``. Pictures, tables and fields are skipped (their text,
if any, is kept). Pure black text and "auto" colour both read as *no colour*, so
the note follows the light/dark theme; everything else round-trips.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field, replace

#: Destinations whose content is not body text (and that are not the tables).
_SKIPPED_DESTINATIONS = frozenset(
    {
        "stylesheet", "info", "generator", "pict", "themedata", "colorschememapping",
        "latentstyles", "datastore", "listtable", "listoverridetable", "revtbl",
        "object", "header", "footer", "footnote", "xmlnstbl", "rsidtbl", "mmathPr",
        "pgdsctbl", "bkmkstart", "bkmkend", "fldinst", "nonshppict", "shp",
        "filetbl", "listtext", "pntext", "pntxta", "pntxtb",
    }
)

#: Named symbols → text.
_SYMBOLS = {
    "emdash": "\u2014", "endash": "\u2013", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "bullet": "\u2022", "tab": "\t",
    "emspace": "\u2003", "enspace": "\u2002", "qmspace": "\u2005", "~": "\u00a0",
}

_ALIGN = {"ql": "left", "qc": "center", "qr": "right", "qj": "justify"}


@dataclass(frozen=True)
class Style:
    """Character formatting of a run. ``None`` means "the default"."""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    font: str | None = None
    size: float | None = None  # points
    color: tuple[int, int, int] | None = None
    background: tuple[int, int, int] | None = None


@dataclass
class Paragraph:
    runs: list[tuple[str, Style]] = field(default_factory=list)
    align: str = "left"

    @property
    def text(self) -> str:
        return "".join(text for text, _style in self.runs)

    def add(self, text: str, style: Style) -> None:
        if not text:
            return
        if self.runs and self.runs[-1][1] == style:
            self.runs[-1] = (self.runs[-1][0] + text, style)
        else:
            self.runs.append((text, style))


def plain_paragraphs(text: str) -> list[Paragraph]:
    """Paragraphs for unformatted text (one per line)."""
    return [Paragraph([(line, Style())] if line else []) for line in text.split("\n")]


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
@dataclass
class _State:
    style: Style = field(default_factory=Style)
    skip: bool = False
    uc: int = 1
    dest: str = ""  # "fonttbl" / "colortbl" / ""
    font_no: int | None = None
    # Raw indexes, resolved against the tables when text is emitted.
    fnum: int | None = None
    cf: int | None = None
    cb: int | None = None


def read_rich_rtf(rtf: str) -> list[Paragraph]:
    """Paragraphs of styled runs from an RTF document."""
    fonts: dict[int, str] = {}
    colors: list[tuple[int, int, int] | None] = []
    color = [0, 0, 0]
    color_set = False
    font_name: list[str] = []
    codepage = "cp1252"

    paragraphs: list[Paragraph] = [Paragraph()]
    align = "left"
    stack: list[_State] = []
    st = _State()
    high = [0]  # pending high surrogate from a \u pair
    i, n = 0, len(rtf)

    def resolved(state: _State) -> Style:
        style = state.style
        font = fonts.get(state.fnum) if state.fnum is not None else None
        fg = colors[state.cf] if state.cf is not None and 0 <= state.cf < len(colors) else None
        bg = colors[state.cb] if state.cb is not None and 0 <= state.cb < len(colors) else None
        if fg == (0, 0, 0):
            fg = None  # black = the theme's text colour
        return replace(style, font=font or None, color=fg, background=bg)

    def emit(text: str) -> None:
        if st.skip or not text:
            return
        if st.dest == "fonttbl":
            font_name.append(text)
            return
        if st.dest == "colortbl":
            return
        paragraphs[-1].add(text, resolved(st))

    def end_paragraph() -> None:
        paragraphs[-1].align = align
        paragraphs.append(Paragraph())

    while i < n:
        ch = rtf[i]
        if ch == "{":
            stack.append(replace(st))
            i += 1
            continue
        if ch == "}":
            if st.dest == "fonttbl" and st.font_no is not None and font_name:
                name = "".join(font_name).strip().rstrip(";").strip()
                if name:
                    fonts[st.font_no] = name
                font_name.clear()
            st = stack.pop() if stack else _State()
            i += 1
            continue
        if ch in "\r\n":
            i += 1
            continue
        if ch != "\\":
            if st.dest == "colortbl" and ch == ";":
                colors.append(tuple(color) if color_set else None)
                color, color_set = [0, 0, 0], False
            elif st.dest == "fonttbl" and ch == ";":
                if st.font_no is not None and font_name:
                    fonts[st.font_no] = "".join(font_name).strip()
                font_name.clear()
            else:
                emit(ch)
            i += 1
            continue

        nxt = rtf[i + 1] if i + 1 < n else ""
        if nxt == "'":
            with contextlib.suppress(ValueError, LookupError):
                emit(bytes([int(rtf[i + 2 : i + 4], 16)]).decode(codepage, "replace"))
            i += 4
            continue
        if nxt == "*":
            st.skip = True
            i += 2
            continue
        if nxt and not nxt.isalpha():
            if nxt in "\\{}":
                emit(nxt)
            elif nxt == "~":
                emit("\u00a0")
            elif nxt == "-":
                pass  # optional hyphen
            elif nxt == "_":
                emit("\u2011")
            i += 2
            continue

        j = i + 1
        while j < n and rtf[j].isalpha():
            j += 1
        word = rtf[i + 1 : j]
        param: int | None = None
        if j < n and (rtf[j] == "-" or rtf[j].isdigit()):
            k = j + 1
            while k < n and rtf[k].isdigit():
                k += 1
            try:
                param = int(rtf[j:k])
            except ValueError:
                param = None
            j = k
        if j < n and rtf[j] == " ":
            j += 1
        i = j
        on = param != 0

        if word in _SKIPPED_DESTINATIONS:
            st.skip = True
        elif word == "fonttbl":
            st.dest = "fonttbl"
        elif word == "colortbl":
            st.dest = "colortbl"
        elif st.dest == "fonttbl" and word == "f" and param is not None:
            st.font_no = param
            font_name.clear()
        elif st.dest == "colortbl":
            if word in ("red", "green", "blue") and param is not None:
                color[("red", "green", "blue").index(word)] = param
                color_set = True
        elif word == "ansicpg" and param:
            codepage = f"cp{param}"
        elif word == "uc" and param is not None:
            st.uc = param
        elif word == "u" and param is not None:
            unit = param % 0x10000
            if 0xD800 <= unit < 0xDC00:
                high[0] = unit  # first half of a surrogate pair
            elif 0xDC00 <= unit < 0xE000 and high[0]:
                emit(chr(0x10000 + ((high[0] - 0xD800) << 10) + (unit - 0xDC00)))
                high[0] = 0
            else:
                emit(chr(unit))
            i = _skip_fallback(rtf, i, st.uc)
        elif word in ("par", "sect") or word == "line":
            if not st.skip and not st.dest:
                end_paragraph()
        elif word in _SYMBOLS:
            emit(_SYMBOLS[word])
        elif word == "pard":
            align = "left"
        elif word in _ALIGN:
            align = _ALIGN[word]
        elif word == "plain":
            st.style, st.fnum, st.cf, st.cb = Style(), None, None, None
        elif word == "b":
            st.style = replace(st.style, bold=on)
        elif word == "i":
            st.style = replace(st.style, italic=on)
        elif word in ("ul", "uld", "uldb", "ulw", "ulth", "uldash"):
            st.style = replace(st.style, underline=on)
        elif word == "ulnone":
            st.style = replace(st.style, underline=False)
        elif word in ("strike", "striked"):
            st.style = replace(st.style, strike=on)
        elif word == "f" and param is not None:
            st.fnum = param
        elif word == "fs" and param is not None:
            st.style = replace(st.style, size=param / 2 if param else None)
        elif word == "cf" and param is not None:
            st.cf = param
        elif word in ("highlight", "cb", "chcbpat") and param is not None:
            st.cb = param or None

    paragraphs[-1].align = align
    # A RichTextBox ends every document with \par: drop the empty tail.
    while len(paragraphs) > 1 and not paragraphs[-1].runs:
        paragraphs.pop()
    return paragraphs


def _skip_fallback(rtf: str, j: int, uc: int) -> int:
    n = len(rtf)
    skipped = 0
    while skipped < uc and j < n:
        if rtf[j] == "\\":
            j += 4 if j + 1 < n and rtf[j + 1] == "'" else 2
        elif rtf[j] in "{}":
            break
        else:
            j += 1
        skipped += 1
    return j


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
_DEFAULT_FONT = "Segoe UI"


def write_rich_rtf(paragraphs: list[Paragraph]) -> str:
    """RTF a Windows ``RichTextBox`` opens, carrying the runs' formatting."""
    fonts: list[str] = [_DEFAULT_FONT]
    colors: list[tuple[int, int, int]] = []

    def font_index(name: str | None) -> int:
        if not name:
            return 0
        if name not in fonts:
            fonts.append(name)
        return fonts.index(name)

    def color_index(rgb: tuple[int, int, int]) -> int:
        if rgb not in colors:
            colors.append(rgb)
        return colors.index(rgb) + 1  # entry 0 is "auto"

    body: list[str] = []
    for para in paragraphs:
        line = ["\\pard"]
        if para.align != "left":
            line.append({"center": "\\qc", "right": "\\qr", "justify": "\\qj"}[para.align])
        line.append(" ")
        for text, style in para.runs:
            # No \\f for the default font: \\deff0 applies, and it reads back as None.
            codes = [f"\\f{font_index(style.font)}"] if style.font else []
            if style.size:
                codes.append(f"\\fs{round(style.size * 2)}")
            if style.bold:
                codes.append("\\b")
            if style.italic:
                codes.append("\\i")
            if style.underline:
                codes.append("\\ul")
            if style.strike:
                codes.append("\\strike")
            if style.color is not None:
                codes.append(f"\\cf{color_index(style.color)}")
            if style.background is not None:
                codes.append(f"\\highlight{color_index(style.background)}")
            prefix = "".join(codes) + " " if codes else ""
            line.append("{" + prefix + _escape(text) + "}")
        line.append("\\par\r\n")
        body.append("".join(line))

    font_table = "".join(
        f"{{\\f{index}\\fnil\\fcharset0 {_escape(name)};}}" for index, name in enumerate(fonts)
    )
    color_table = ";" + "".join(f"\\red{r}\\green{g}\\blue{b};" for r, g, b in colors)
    return (
        "{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1"
        f"{{\\fonttbl{font_table}}}\r\n{{\\colortbl {color_table}}}\r\n"
        + "".join(body)
        + "}"
    )


def _escape(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\t":
            out.append("\\tab ")
        elif code < 128:
            out.append(ch)
        elif code < 256:
            out.append(f"\\'{code:02x}")
        elif code > 0xFFFF:
            # Outside the BMP: a UTF-16 surrogate pair, each as a signed \\u.
            code -= 0x10000
            for half in (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)):
                out.append(f"\\u{half - 65536}?")
        else:
            out.append(f"\\u{code if code < 32768 else code - 65536}?")
    return "".join(out)
