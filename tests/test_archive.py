"""Tests for the archive extraction/creation seam (core/archive.py)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from vaultkeeper.core.archive import (
    ARCHIVE_EXTENSIONS,
    FakeArchiveExtractor,
    SevenZipExtractor,
    archive_filter,
    is_extractable,
    is_zip_extension,
)


class TestExtensionPredicates:
    def test_values_match_vb_zipextensions(self):
        # Every recognised extension can be extracted except a bare .exe.
        assert ARCHIVE_EXTENSIONS[".zip"] is True
        assert ARCHIVE_EXTENSIONS[".7z"] is True
        assert ARCHIVE_EXTENSIONS[".rar"] is True
        assert ARCHIVE_EXTENSIONS[".exe"] is False

    def test_is_zip_extension_includes_exe_case_insensitively(self):
        assert is_zip_extension(".ZIP")
        assert is_zip_extension(".exe")  # recognised (movable) even if not extractable
        assert not is_zip_extension(".mod")

    def test_is_extractable_excludes_exe(self):
        assert is_extractable(".7z")
        assert not is_extractable(".exe")
        assert not is_extractable(".mod")

    def test_archive_filter_lists_all(self):
        flt = archive_filter()
        assert flt.startswith("*")
        assert "*.zip" in flt and "*.7z" in flt


class TestFakeArchiveExtractor:
    def test_extract_writes_canned_files_and_records_call(self, tmp_path):
        fake = FakeArchiveExtractor(
            contents={"pack.zip": {"a.txt": b"AAA", "sub/b.2da": b"BBB"}}
        )
        archive = tmp_path / "pack.zip"
        dest = tmp_path / "out"
        result = fake.extract(archive, dest)

        assert result.ok
        assert (dest / "a.txt").read_bytes() == b"AAA"
        assert (dest / "sub" / "b.2da").read_bytes() == b"BBB"
        assert {p.name for p in result.files} == {"a.txt", "b.2da"}
        assert fake.extract_calls == [(archive, dest)]

    def test_extract_unknown_archive_yields_empty(self, tmp_path):
        fake = FakeArchiveExtractor(contents={})
        result = fake.extract(tmp_path / "mystery.7z", tmp_path / "out")
        assert result.ok
        assert result.files == []

    def test_unavailable_backend_fails_cleanly(self, tmp_path):
        fake = FakeArchiveExtractor(available=False)
        result = fake.extract(tmp_path / "pack.zip", tmp_path / "out")
        assert not result.ok
        assert result.exit_code == -1
        assert "not available" in result.error

    def test_create_records_and_writes_placeholder(self, tmp_path):
        fake = FakeArchiveExtractor()
        src = tmp_path / "f.txt"
        src.write_text("x")
        archive = tmp_path / "made.7z"
        result = fake.create(archive, [src])
        assert result.ok
        assert archive.is_file()
        assert fake.create_calls == [(archive, [src])]


class TestSevenZipExtractorNoBinary:
    def test_unavailable_reports_gracefully(self, tmp_path):
        ext = SevenZipExtractor(exe=None)
        # Force "not available" regardless of the host having 7z.
        ext._exe = None
        assert not ext.available
        result = ext.extract(tmp_path / "x.zip", tmp_path / "out")
        assert not result.ok
        assert result.exit_code == -1


# A real end-to-end extraction, only when a 7-Zip CLI is actually installed.
_HAVE_7Z = SevenZipExtractor().available


@pytest.mark.integration
@pytest.mark.skipif(not _HAVE_7Z, reason="No 7-Zip CLI (7zz/7z) on this machine")
class TestSevenZipReal:
    def _make_zip(self, tmp_path: Path) -> Path:
        archive = tmp_path / "real.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("hello.txt", "hi there")
            zf.writestr("nested/data.2da", "2DA V2.0")
        return archive

    def test_extract_real_zip(self, tmp_path):
        archive = self._make_zip(tmp_path)
        dest = tmp_path / "extracted"
        result = SevenZipExtractor().extract(archive, dest)

        assert result.ok, result.error
        assert (dest / "hello.txt").read_text() == "hi there"
        assert (dest / "nested" / "data.2da").read_text() == "2DA V2.0"
        assert {p.name for p in result.files} == {"hello.txt", "data.2da"}

    def test_create_then_extract_round_trip(self, tmp_path):
        src_dir = tmp_path / "src"
        (src_dir / "sub").mkdir(parents=True)
        (src_dir / "top.txt").write_text("top")
        (src_dir / "sub" / "deep.txt").write_text("deep")

        archive = tmp_path / "bundle.7z"
        ext = SevenZipExtractor()
        made = ext.create(archive, [Path("top.txt"), Path("sub")], base_dir=src_dir)
        assert made.ok, made.error
        assert archive.is_file()

        dest = tmp_path / "back"
        got = ext.extract(archive, dest)
        assert got.ok, got.error
        assert (dest / "top.txt").read_text() == "top"
        assert (dest / "sub" / "deep.txt").read_text() == "deep"
