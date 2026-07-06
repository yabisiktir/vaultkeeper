"""Tests for the minimal RTF <-> text layer."""

from __future__ import annotations

from vaultkeeper.core.rtf import read_rtf_text, write_rtf


class TestRoundTrip:
    def test_simple_lines(self):
        lines = ["My Mod", "", "Completed      Time Played            User"]
        text = read_rtf_text(write_rtf(lines))
        assert text.split("\n")[:3] == lines

    def test_play_time_layout_round_trips(self):
        lines = [
            "A Samurai's Tale",
            "",
            "Completed      Time Played            User",
            "23 Feb 2017    150 hours 16 mins      Louis",
        ]
        text = read_rtf_text(write_rtf(lines))
        # The data line survives with its multiple-space columns intact.
        assert "23 Feb 2017    150 hours 16 mins      Louis" in text

    def test_special_chars_escaped(self):
        lines = ["braces {} and back\\slash"]
        text = read_rtf_text(write_rtf(lines))
        assert "braces {} and back\\slash" in text

    def test_unicode_round_trips(self):
        # A codepoint > 255 uses \uN with a fallback that must be skipped, not doubled.
        lines = ["Player ☃ name"]  # snowman
        text = read_rtf_text(write_rtf(lines))
        assert "Player ☃ name" in text

    def test_high_ansi_round_trips(self):
        lines = ["Vivienne \xe9"]  # e-acute (cp1252)
        text = read_rtf_text(write_rtf(lines))
        assert "Vivienne \xe9" in text


class TestReadForeignRtf:
    def test_skips_font_and_colour_tables(self):
        rtf = (
            r"{\rtf1\ansi\deff0"
            r"{\fonttbl{\f0\fnil Segoe UI;}}"
            r"{\colortbl ;\red0\green0\blue0;}"
            r"\f0\fs28 Hello\par World\par}"
        )
        text = read_rtf_text(rtf)
        assert "Segoe UI" not in text
        assert text.split("\n")[:2] == ["Hello", "World"]

    def test_ignores_star_destination(self):
        rtf = r"{\rtf1\ansi {\*\generator RichEd;}Body text\par}"
        text = read_rtf_text(rtf)
        assert "RichEd" not in text
        assert "Body text" in text

    def test_hex_escape_and_tab(self):
        rtf = r"{\rtf1\ansi caf\'e9\tab done\par}"
        text = read_rtf_text(rtf)
        assert text.startswith("caf\xe9\tdone")
