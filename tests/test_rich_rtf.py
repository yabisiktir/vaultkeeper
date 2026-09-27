"""Formatted mod notes (logic audit 3i N4): RTF <-> styled runs."""

from __future__ import annotations

from vaultkeeper.core.rich_rtf import (
    Paragraph,
    Style,
    plain_paragraphs,
    read_rich_rtf,
    write_rich_rtf,
)
from vaultkeeper.core.rtf import read_rtf_text

BACKSLASH = chr(92)

#: What a Windows RichTextBox writes for a formatted note.
RICHTEXTBOX = (
    r"{\rtf1\ansi\ansicpg1252\deff0\nouicompat\deflang2057{\fonttbl{\f0\fnil\fcharset0 "
    r"Segoe UI;}{\f1\fnil\fcharset0 Consolas;}}" "\r\n"
    r"{\colortbl ;\red255\green0\blue0;\red0\green0\blue0;\red255\green255\blue0;}" "\r\n"
    r"{\*\generator Riched20 10.0.19041}\viewkind4\uc1 " "\r\n"
    r"\pard\f0\fs18\lang2057 Plain \b bold\b0  and \i italic\i0  and \ul under\ulnone .\par" "\r\n"
    r"\cf1 red \cf2 black \highlight3 marked\highlight0\par" "\r\n"
    r"\pard\qc\f1\fs24 Centred caf\'e9 " + BACKSLASH + "u8364?" + r"\par" "\r\n"
    r"\pard\strike gone\strike0\par" "\r\n"
    r"}"
)


def test_a_richtextbox_note_keeps_its_formatting() -> None:
    paras = read_rich_rtf(RICHTEXTBOX)
    assert [p.text for p in paras] == [
        "Plain bold and italic and under.",
        "red black marked",
        "Centred café €",
        "gone",
    ]
    runs = dict((text, style) for text, style in paras[0].runs)
    assert runs["bold"].bold and runs["italic"].italic and runs["under"].underline
    assert runs["Plain "].font == "Segoe UI" and runs["Plain "].size == 9
    second = {text: style for text, style in paras[1].runs}
    assert second["red "].color == (255, 0, 0)
    assert second["black "].color is None  # black follows the theme
    assert second["marked"].background == (255, 255, 0)
    assert paras[2].align == "center" and paras[2].runs[0][1].font == "Consolas"
    assert paras[2].runs[0][1].size == 12
    assert paras[3].runs[0][1].strike and paras[3].align == "left"


def test_writing_and_reading_back_is_lossless() -> None:
    paras = [
        Paragraph([("Title", Style(bold=True, size=14, font="Georgia"))], align="center"),
        Paragraph([("plain ", Style()), ("red", Style(color=(200, 0, 0), italic=True))]),
        Paragraph([]),
        Paragraph([("brace {x} \\ tab\tüñ € 🐉", Style(background=(255, 255, 0)))]),
    ]
    again = read_rich_rtf(write_rich_rtf(paras))
    assert [(p.runs, p.align) for p in again] == [(p.runs, p.align) for p in paras]


def test_the_plain_text_reader_still_reads_formatted_notes() -> None:
    # Play-time parsing and search use the plain reader.
    text = read_rtf_text(write_rich_rtf(plain_paragraphs("one\ntwo")))
    assert text.strip("\n") == "one\ntwo"
    assert read_rtf_text(RICHTEXTBOX).startswith("Plain bold and italic")
