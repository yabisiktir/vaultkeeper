"""BIK → WBM movie conversion (VB ``NIT.ConvertBik`` / ``BgConverter``).

NWN:EE plays WebM (``.wbm``) movies, while classic NWN shipped Bink (``.bik``).
Create-Installer optionally converts a mod's ``.bik`` movies to ``.wbm`` (when the
profile's ``ConvertBikFiles`` preference is on) by shelling out to ``ffmpeg`` with the
exact command the original uses::

    ffmpeg -i <bik> -c:v libvpx -b:v 1M -c:a libvorbis -y -f webm <wbm>

The original bundles ``ffmpeg.exe`` in its install dir; this port discovers a usable
``ffmpeg`` on ``PATH`` (or a caller-supplied path), matching how the archive backend
finds ``7zz``. The runner is injected so the conversion is testable without ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path


def ffmpeg_command(ffmpeg: str, bik: Path, wbm: Path) -> list[str]:
    """The argv for converting ``bik`` → ``wbm`` (VB ``ConvertBik`` command line)."""
    return [
        ffmpeg,
        "-i",
        str(bik),
        "-c:v",
        "libvpx",
        "-b:v",
        "1M",
        "-c:a",
        "libvorbis",
        "-y",
        "-f",
        "webm",
        str(wbm),
    ]


class BikConverter:
    """Converts ``.bik`` movies to ``.wbm`` via ``ffmpeg`` (VB ``NIT.ConvertBik``)."""

    #: Candidate executable names, most-preferred first.
    _CANDIDATES = ("ffmpeg", "ffmpeg.exe")

    def __init__(
        self,
        exe: str | None = None,
        *,
        runner: Callable[[list[str]], int] | None = None,
    ) -> None:
        self._exe = exe or self._discover()
        self._runner = runner or self._run

    @classmethod
    def _discover(cls) -> str | None:
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

    @staticmethod
    def _run(argv: list[str]) -> int:
        try:
            proc = subprocess.run(argv, capture_output=True, check=False)  # noqa: S603
            return proc.returncode
        except OSError:
            return -1

    def convert(self, bik: Path, wbm: Path) -> bool:
        """Convert ``bik`` → ``wbm``; return True on success (VB ``ConvertBik``)."""
        if self._exe is None:
            return False
        wbm.parent.mkdir(parents=True, exist_ok=True)
        return self._runner(ffmpeg_command(self._exe, bik, wbm)) == 0


class FakeBikConverter:
    """Test double: records conversions and writes a stub ``.wbm`` for each."""

    def __init__(self, *, available: bool = True, succeed: bool = True) -> None:
        self._available = available
        self._succeed = succeed
        self.calls: list[tuple[Path, Path]] = []

    @property
    def available(self) -> bool:
        return self._available

    def convert(self, bik: Path, wbm: Path) -> bool:
        self.calls.append((bik, wbm))
        if not self._available or not self._succeed:
            return False
        wbm.parent.mkdir(parents=True, exist_ok=True)
        wbm.write_bytes(b"WEBM")
        return True
