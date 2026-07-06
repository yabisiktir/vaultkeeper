"""Minimal RTF <-> plain-text layer for the durable play-time / notes files.

NIT stores per-mod ``.Game Play Time.rtf`` files (and mod notes) as RTF written by
a Windows ``RichTextBox``. Those files are the *durable source* of play-time data —
PlayDataManager parses their plain text back out (``rtb.Text``) and re-writes them.
For a cross-platform port we need to (a) read the plain text out of an RTF written by
either NIT or us, and (b) write a valid RTF that Windows NIT can still open.

This is deliberately small: :func:`read_rtf_text` extracts text (skipping the
font/colour/stylesheet/info destination groups, honouring ``\\par``/``\\line``/
``\\tab``, the ``\\uc`` skip count, and ``\\uN`` / ``\\'xx`` escapes);
:func:`write_rtf` emits a plain ANSI RTF whose extracted text round-trips exactly.
It is not a general RTF renderer.
"""

from __future__ import annotations

#: Destination control words whose group contents are metadata, not body text.
_IGNORED_DESTINATIONS = frozenset(
    {
        "fonttbl", "colortbl", "stylesheet", "info", "generator", "pict",
        "themedata", "colorschememapping", "latentstyles", "datastore",
        "listtable", "listoverridetable", "revtbl",
    }
)


def write_rtf(lines: list[str]) -> str:
    """Write ``lines`` as a minimal ANSI RTF (one ``\\par`` per line, ``\\uc1``)."""
    body = "\\par\r\n".join(_escape(line) for line in lines)
    return (
        "{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1{\\fonttbl}\r\n" + body + "\\par\r\n}"
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
            # High-ANSI (cp1252) byte — no fallback char follows.
            out.append(f"\\'{code:02x}")
        else:
            # Unicode escape with a single '?' ANSI fallback char (matches \uc1).
            out.append(f"\\u{code}?")
    return "".join(out)


def read_rtf_text(rtf: str) -> str:
    """Extract the plain body text from an RTF document."""
    out: list[str] = []
    i = 0
    n = len(rtf)
    ignore_stack: list[bool] = []
    uc_stack: list[int] = []
    ctx = _Ctx(ignoring=False, uc=1)

    while i < n:
        ch = rtf[i]
        if ch == "{":
            ignore_stack.append(ctx.ignoring)
            uc_stack.append(ctx.uc)
            i += 1
        elif ch == "}":
            ctx.ignoring = ignore_stack.pop() if ignore_stack else False
            ctx.uc = uc_stack.pop() if uc_stack else 1
            i += 1
        elif ch == "\\":
            i = _consume_control(rtf, i, out, ctx)
        elif ch in "\r\n":
            i += 1  # literal source line breaks are not body text
        else:
            if not ctx.ignoring:
                out.append(ch)
            i += 1

    return "".join(out)


class _Ctx:
    """Mutable parse state threaded through control-word handling."""

    __slots__ = ("ignoring", "uc")

    def __init__(self, ignoring: bool, uc: int) -> None:
        self.ignoring = ignoring
        self.uc = uc


def _consume_control(rtf: str, i: int, out: list[str], ctx: _Ctx) -> int:
    """Handle the control word/symbol starting at ``rtf[i] == '\\'``; return new index."""
    n = len(rtf)
    nxt = rtf[i + 1] if i + 1 < n else ""

    if nxt == "'":
        # \'xx hex byte.
        try:
            byte = int(rtf[i + 2 : i + 4], 16)
            if not ctx.ignoring:
                out.append(bytes([byte]).decode("cp1252", "replace"))
        except ValueError:
            pass
        return i + 4

    if nxt and not nxt.isalpha():
        # Control symbol (\\, \{, \}, etc.).
        if not ctx.ignoring and nxt in "\\{}":
            out.append(nxt)
        return i + 2

    # Control word: letters, optional numeric parameter, optional delimiter space.
    j = i + 1
    while j < n and rtf[j].isalpha():
        j += 1
    word = rtf[i + 1 : j]
    param = ""
    if j < n and (rtf[j] == "-" or rtf[j].isdigit()):
        k = j + 1
        while k < n and rtf[k].isdigit():
            k += 1
        param = rtf[j:k]
        j = k
    if j < n and rtf[j] == " ":
        j += 1

    if word == "uc" and param:
        ctx.uc = int(param)
    elif word == "*" or word in _IGNORED_DESTINATIONS:
        ctx.ignoring = True
    elif not ctx.ignoring:
        if word in ("par", "line"):
            out.append("\n")
        elif word == "tab":
            out.append("\t")
        elif word == "u" and param:
            out.append(chr(int(param) % 0x10000))
            j = _skip_uc(rtf, j, ctx.uc)
    return j


def _skip_uc(rtf: str, j: int, uc: int) -> int:
    """Skip ``uc`` fallback tokens after a ``\\uN`` (a token is a char or an escape)."""
    n = len(rtf)
    skipped = 0
    while skipped < uc and j < n:
        if rtf[j] == "\\":
            if j + 1 < n and rtf[j + 1] == "'":
                j += 4
            else:
                j += 2
        else:
            j += 1
        skipped += 1
    return j
