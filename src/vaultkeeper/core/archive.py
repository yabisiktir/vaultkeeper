"""An injectable archive extraction/creation seam.

Ports the essential behaviour of LazWorks ``ZipManager`` (which shells out to
the 7-Zip CLI). Keeping it behind a protocol lets the consumers — installer
creation, doc organiser, backup restore, publishing — be unit-tested with a
:class:`FakeArchiveExtractor` instead of requiring the binary on the test box.

VB grounding (``LazWorks Library/LazWorks Library Aids/ZipManager.vb``):

* Recognised archive extensions come from ``ZipManager.ZipExtensions`` — every
  entry can be extracted except ``.exe`` (recognised as a "zip extension" so the
  UI can *move* it, but not handed to 7-Zip for extraction).
* Extract command line: ``x "<archive>" -p1 -y -o"<dest>"`` — ``-p1`` supplies a
  dummy password so a password-protected archive fails fast instead of hanging
  on a prompt, ``-y`` answers yes to all, ``-o`` sets the output directory.
* Create command line: ``a "<archive>" <sources...>``.
* Exit codes (``ZipManager.ZipExitCode``): 0 completed, 1 warning (still
  produced output — treated as success), 2 fatal, 7 command-line error,
  8 out of memory, 255 cancelled.

Unlike the VB app, Vaultkeeper does NOT depend on 7-Zip for ERF/HAK — those are
decoded natively (see ``nwnfile/formats/erf_reader``). This seam is only for the
general compressed archives users download (zip/rar/7z/...).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from nwnfile.log import get_logger

logger = get_logger(__name__)

#: Recognised archive extensions mapped to "can 7-Zip extract it?" — verbatim
#: from ``ZipManager.ZipExtensions`` (case-insensitive; keys keep the leading dot).
ARCHIVE_EXTENSIONS: dict[str, bool] = {
    ".001": True,
    ".7z": True,
    ".arj": True,
    ".lha": True,
    ".lhz": True,
    ".lzma": True,
    ".rar": True,
    ".tar": True,
    ".taz": True,
    ".xz": True,
    ".z": True,
    ".zip": True,
    ".exe": False,
}

#: Exit codes 7-Zip returns that still leave usable output (0=ok, 1=warning).
_SUCCESS_CODES = frozenset({0, 1})

#: Human-readable text per 7-Zip exit code (ZipManager.ZipResult).
_EXIT_TEXT: dict[int, str] = {
    -1: "Unable to create the extraction command.",
    2: "A fatal error occurred (the archive may be password protected or corrupt).",
    7: "A command-line error occurred.",
    8: "Not enough memory to complete the operation.",
    255: "The operation was cancelled.",
}


def is_zip_extension(extension: str) -> bool:
    """True if the extension is a recognised archive (incl. ``.exe``).

    Mirrors ``ZipManager.IsZipExtension`` — used to decide which files count as
    "compressed downloads" for the *Move to Downloads* command.
    """
    return extension.lower() in ARCHIVE_EXTENSIONS


def is_extractable(extension: str) -> bool:
    """True if 7-Zip can extract this extension (i.e. not a bare ``.exe``)."""
    return ARCHIVE_EXTENSIONS.get(extension.lower(), False)


def archive_filter() -> str:
    """A file-dialog filter string of the recognised extensions (VB ZipFilter)."""
    return "*" + ";*".join(ARCHIVE_EXTENSIONS)


@dataclass
class ExtractResult:
    """The outcome of an extract/create operation."""

    ok: bool
    dest: Path
    files: list[Path] = field(default_factory=list)
    exit_code: int = 0
    error: str = ""


class ArchiveExtractor(Protocol):
    """The archive operations Vaultkeeper needs."""

    @property
    def available(self) -> bool:  # pragma: no cover - protocol
        """True if the backend can actually run (e.g. the CLI is present)."""
        ...

    def extract(self, archive: Path, dest: Path) -> ExtractResult:  # pragma: no cover
        """Extract ``archive`` into ``dest`` (created if needed)."""
        ...

    def create(
        self,
        archive: Path,
        sources: list[Path],
        *,
        base_dir: Path | None = None,
        exclude: list[str] | None = None,
    ) -> ExtractResult:  # pragma: no cover - protocol
        """Create ``archive`` containing ``sources`` (``exclude`` = name patterns)."""
        ...


def bundled_dir() -> Path | None:
    """Where the binaries we ship live, in a checkout or inside a frozen app.

    PyInstaller unpacks bundled data next to the executable (``sys._MEIPASS``);
    a source checkout has them under ``external/bin``. Both are checked so the
    same code path serves a developer and an installed user.
    """
    frozen = getattr(sys, "_MEIPASS", None)
    roots = [Path(frozen) / "external" / "bin"] if frozen else []
    roots.append(Path(__file__).resolve().parents[3] / "external" / "bin")
    return next((root for root in roots if root.is_dir()), None)


def platform_slug() -> str:
    """The ``external/bin`` subfolder for this machine."""
    if sys.platform == "darwin":
        return "macos"  # one universal binary covers arm64 and x86_64
    if sys.platform.startswith("win"):
        return "windows-x64"
    return "linux-arm64" if platform.machine() in ("aarch64", "arm64") else "linux-x64"


def bundled_sevenzip() -> Path | None:
    """The 7-Zip we ship for this platform, if it is present and runnable."""
    root = bundled_dir()
    if root is None:
        return None
    folder = root / platform_slug()
    for name in ("7zz", "7za.exe", "7z.exe"):
        candidate = folder / name
        if candidate.is_file():
            if not sys.platform.startswith("win") and not os.access(candidate, os.X_OK):
                try:
                    candidate.chmod(0o755)  # git can lose the bit; installers too
                except OSError:
                    continue
            return candidate
    return None


class SevenZipExtractor:
    """Default backend: shells out to the 7-Zip CLI (``7zz`` preferred, then ``7z``)."""

    #: Candidate executable names, most-preferred first. ``7zz`` is the modern
    #: single-file CLI we bundle (external/tools.toml); ``7z``/``7za`` are the
    #: names distro/homebrew packages install.
    _CANDIDATES = ("7zz", "7z", "7za")

    def __init__(self, exe: str | None = None) -> None:
        self._exe = exe or self._discover()

    @classmethod
    def _discover(cls) -> str | None:
        """The 7-Zip to use: the one we ship first, then whatever is on PATH.

        Ours first on purpose. There is no pure-Python fallback here, so a user
        without 7-Zip installed cannot open a mod archive at all — shipping it is
        what makes an installed build work on a clean machine. PATH is still
        searched, so a source checkout with no bundled binary keeps working.
        """
        bundled = bundled_sevenzip()
        if bundled is not None:
            return str(bundled)
        for name in cls._CANDIDATES:
            found = shutil.which(name)
            if found:
                return found
        return None

    @property
    def exe(self) -> str | None:
        return self._exe

    @property
    def available(self) -> bool:
        return self._exe is not None

    def extract(self, archive: Path, dest: Path) -> ExtractResult:
        if not self.available:
            return ExtractResult(
                ok=False, dest=dest, exit_code=-1, error="7-Zip is not available."
            )
        dest.mkdir(parents=True, exist_ok=True)
        # x <archive> -p1 -y -o<dest>  (see module docstring for the flags).
        code = self._run([self._exe, "x", str(archive), "-p1", "-y", f"-o{dest}"])
        ok = code in _SUCCESS_CODES
        files = (
            sorted(p for p in dest.rglob("*") if p.is_file()) if ok else []
        )
        return ExtractResult(
            ok=ok,
            dest=dest,
            files=files,
            exit_code=code,
            error="" if ok else self._exit_text(code),
        )

    def create(
        self,
        archive: Path,
        sources: list[Path],
        *,
        base_dir: Path | None = None,
        exclude: list[str] | None = None,
    ) -> ExtractResult:
        if not self.available:
            return ExtractResult(
                ok=False, dest=archive, exit_code=-1, error="7-Zip is not available."
            )
        archive.parent.mkdir(parents=True, exist_ok=True)
        # a <archive> <sources...> [-x!<pattern> ...] — run from base_dir so stored
        # paths are relative. -x! excludes by name/relative path (VB PublishMod).
        args = [self._exe, "a", str(archive), *(str(s) for s in sources)]
        args += [f"-x!{pattern}" for pattern in (exclude or [])]
        code = self._run(args, cwd=base_dir)
        ok = code in _SUCCESS_CODES and archive.is_file()
        return ExtractResult(
            ok=ok,
            dest=archive,
            files=[archive] if ok else [],
            exit_code=code,
            error="" if ok else self._exit_text(code),
        )

    def _run(self, args: list[str], *, cwd: Path | None = None) -> int:
        try:
            proc = subprocess.run(  # noqa: S603 - args are built from trusted paths
                args,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            logger.error("7-Zip invocation failed: %s", exc)
            return -1
        if proc.returncode != 0:
            logger.debug("7-Zip exit %s: %s", proc.returncode, proc.stderr.strip())
        return proc.returncode

    @staticmethod
    def _exit_text(code: int) -> str:
        return _EXIT_TEXT.get(code, f"7-Zip returned exit code {code}.")


class FakeArchiveExtractor:
    """Test backend: records calls and yields canned extracted files.

    ``contents`` maps an archive *name* (or full path string) to a dict of
    ``{relative_path: bytes}`` written into the destination on extract.
    """

    def __init__(
        self,
        *,
        available: bool = True,
        contents: dict[str, dict[str, bytes]] | None = None,
    ) -> None:
        self._available = available
        self._contents = contents or {}
        self.extract_calls: list[tuple[Path, Path]] = []
        self.create_calls: list[tuple[Path, list[Path]]] = []
        self.last_exclude: list[str] = []

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, archive: Path, dest: Path) -> ExtractResult:
        self.extract_calls.append((archive, dest))
        if not self._available:
            return ExtractResult(
                ok=False, dest=dest, exit_code=-1, error="7-Zip is not available."
            )
        dest.mkdir(parents=True, exist_ok=True)
        payload = self._contents.get(archive.name, self._contents.get(str(archive), {}))
        written: list[Path] = []
        for rel, data in payload.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(target)
        return ExtractResult(ok=True, dest=dest, files=sorted(written), exit_code=0)

    def create(
        self,
        archive: Path,
        sources: list[Path],
        *,
        base_dir: Path | None = None,
        exclude: list[str] | None = None,
    ) -> ExtractResult:
        self.create_calls.append((archive, list(sources)))
        self.last_exclude = list(exclude or [])
        if not self._available:
            return ExtractResult(
                ok=False, dest=archive, exit_code=-1, error="7-Zip is not available."
            )
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"FAKE-ARCHIVE")
        return ExtractResult(ok=True, dest=archive, files=[archive], exit_code=0)
