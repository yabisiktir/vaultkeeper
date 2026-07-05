"""CRC-32 checksums.

The VB app stores a CRC-32 per file in its database and uses CRC equality to
decide whether an install copy can be skipped (see the install engine). Those
stored values are standard CRC-32 (ISO 3309 / zlib), so Python's ``zlib.crc32``
reproduces them exactly — important if we ever import a legacy store, and
required for the small-file collision guard (:data:`constants.NO_CRC_CHECK_MAX_BYTES`).

Returned as a signed/unsigned-agnostic ``int`` in the range 0..0xFFFFFFFF, which
matches how the value is compared (equality only). ``zlib`` releases the GIL for
large buffers, so this parallelises across threads.
"""

from __future__ import annotations

import zlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB streaming chunk


def crc32_bytes(data: bytes) -> int:
    """CRC-32 of an in-memory buffer (0..0xFFFFFFFF)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def crc32_file(path: str | Path) -> int:
    """Stream a file and return its CRC-32 (0..0xFFFFFFFF).

    Raises ``OSError`` if the file cannot be read (caller decides how to treat a
    CRC failure — the VB app flags such files rather than crashing).
    """
    crc = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF
