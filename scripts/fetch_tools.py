#!/usr/bin/env python3
"""Refresh the bundled native binaries in ``external/bin``.

Vaultkeeper shells out to 7-Zip to read the archives mods ship in, and there is
no pure-Python fallback: without it, installing a mod fails outright. So the
binary travels with us rather than being assumed on the user's PATH.

The binaries are **committed**, not fetched at build time. That keeps builds
offline and reproducible, avoids pinned URLs that rot — 7-Zip's own download page
serves several releases at once — and sidesteps a bootstrap problem, since the
Windows build of 7-Zip is itself distributed as a ``.7z``. About 12 MB for four
platforms, changing roughly once a year.

This script is the *updater*, run by hand when bumping the version:

    python scripts/fetch_tools.py            # refresh everything
    python scripts/fetch_tools.py --check    # verify what is committed

It records each download's SHA-256 in ``external/tools.toml`` so a later refresh
can prove it fetched the same bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "external" / "bin"

#: 7-Zip release to bundle. Bump here, then run this script.
SEVENZIP_VERSION = "26.02"
_V = SEVENZIP_VERSION.replace(".", "")

#: platform -> (download url, member to extract, name to install it as)
SEVENZIP: dict[str, tuple[str, str, str]] = {
    "macos": (f"https://www.7-zip.org/a/7z{_V}-mac.tar.xz", "7zz", "7zz"),
    "linux-x64": (f"https://www.7-zip.org/a/7z{_V}-linux-x64.tar.xz", "7zz", "7zz"),
    "linux-arm64": (f"https://www.7-zip.org/a/7z{_V}-linux-arm64.tar.xz", "7zz", "7zz"),
    # Windows ships as a .7z; 7za.exe inside it is the standalone console build.
    "windows-x64": (f"https://www.7-zip.org/a/7z{_V}-extra.7z", "7za.exe", "7za.exe"),
}

#: The licence obliges us to ship its terms with the binary.
LICENCE_MEMBER = "License.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, into: Path) -> Path:
    target = into / url.rsplit("/", 1)[-1]
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)
    return target


def unpack(archive: Path, into: Path) -> None:
    """Extract a downloaded archive. ``.7z`` needs a 7-Zip already on the machine."""
    if archive.name.endswith(".tar.xz"):
        with tarfile.open(archive) as tar:
            tar.extractall(into, filter="data")
        return
    for command in ("7zz", "7z", "7za"):
        if shutil.which(command):
            subprocess.run(
                [command, "x", "-y", f"-o{into}", str(archive)],
                check=True, stdout=subprocess.DEVNULL,
            )
            return
    raise SystemExit(
        f"{archive.name} is a .7z and no 7-Zip was found to unpack it.\n"
        "Install one (brew install sevenzip / apt install p7zip-full) and re-run."
    )


def find(root: Path, name: str) -> Path:
    hit = next((p for p in root.rglob(name) if p.is_file()), None)
    if hit is None:
        raise SystemExit(f"{name} not found in the downloaded archive")
    return hit


def refresh() -> dict[str, str]:
    """Download, verify and install every platform's binary. Returns checksums."""
    checksums: dict[str, str] = {}
    for platform, (url, member, install_as) in SEVENZIP.items():
        print(f"{platform}:")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            archive = download(url, work)
            checksums[platform] = sha256(archive)
            unpack(archive, work / "out")

            dest = BIN / platform
            dest.mkdir(parents=True, exist_ok=True)
            binary = find(work / "out", member)
            shutil.copy2(binary, dest / install_as)
            (dest / install_as).chmod(0o755)
            shutil.copy2(find(work / "out", LICENCE_MEMBER), dest / "License.txt")
            size = (dest / install_as).stat().st_size / 1e6
            print(f"  installed {install_as} ({size:.1f} MB) + License.txt")
    return checksums


def check() -> int:
    """Verify every platform has its binary and licence committed."""
    missing = []
    for platform, (_url, _member, install_as) in SEVENZIP.items():
        for name in (install_as, "License.txt"):
            path = BIN / platform / name
            if not path.is_file():
                missing.append(f"{platform}/{name}")
    for entry in missing:
        print(f"MISSING {entry}")
    if not missing:
        total = sum(p.stat().st_size for p in BIN.rglob("*") if p.is_file())
        print(f"all bundled tools present ({total / 1e6:.1f} MB)")
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="verify what is committed, fetch nothing"
    )
    args = parser.parse_args(argv)
    if args.check:
        return check()

    checksums = refresh()
    print("\nRecord these in external/tools.toml:")
    for platform, digest in checksums.items():
        print(f"  {platform}: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
