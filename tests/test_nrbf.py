"""Tests for the MS-NRBF reader, driven by hand-constructed spec-accurate bytes.

No golden .NET files exist locally, so each fixture is built byte-by-byte to the
MS-NRBF spec and the reader's output is asserted — validating the reader against
the actual wire format, not against an encoder of our own.
"""

from __future__ import annotations

import struct
from datetime import datetime

from vaultkeeper.persistence.nrbf.reader import NrbfClass, read_nrbf


def _lps(s: str) -> bytes:
    """Length-prefixed UTF-8 string (7-bit varint length)."""
    data = s.encode("utf-8")
    n = len(data)
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out) + data


def _header(root_id: int = 1) -> bytes:
    return struct.pack("<Biiii", 0, root_id, -1, 1, 0)


def _dotnet_ticks(dt: datetime) -> int:
    delta = dt - datetime(1, 1, 1)
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return micros * 10


def test_read_string_root() -> None:
    stream = _header(1) + bytes([6]) + struct.pack("<i", 1) + _lps("hello") + bytes([11])
    assert read_nrbf(stream) == "hello"


def test_read_class_with_mixed_members() -> None:
    when = datetime(2020, 1, 2, 3, 4, 5)
    stream = (
        _header(1)
        + bytes([12]) + struct.pack("<i", 2) + _lps("NWN Installer Tool")  # BinaryLibrary
        + bytes([5]) + struct.pack("<i", 1) + _lps("ModData") + struct.pack("<i", 4)
        + _lps("Num") + _lps("Name") + _lps("Flag") + _lps("When")
        + bytes([0, 1, 0, 0])          # binary types: Primitive, String, Primitive, Primitive
        + bytes([8]) + bytes([1]) + bytes([13])  # additional: Int32 / Boolean / DateTime
        + struct.pack("<i", 2)         # library id
        + struct.pack("<i", 42)        # Num = 42
        + bytes([6]) + struct.pack("<i", 3) + _lps("Cool Mod")  # Name -> string object
        + bytes([1])                   # Flag = True
        + struct.pack("<Q", _dotnet_ticks(when))  # When
        + bytes([11])
    )
    obj = read_nrbf(stream)
    assert isinstance(obj, NrbfClass)
    assert obj.name == "ModData"
    assert obj.library == "NWN Installer Tool"
    assert obj.members["Num"] == 42
    assert obj.members["Name"] == "Cool Mod"
    assert obj.members["Flag"] is True
    assert obj.members["When"] == when


def test_read_object_array_and_reference() -> None:
    # An object array whose second element references the first (dedup).
    stream = (
        _header(1)
        + bytes([16]) + struct.pack("<ii", 1, 2)      # ArraySingleObject id=1 len=2
        + bytes([6]) + struct.pack("<i", 5) + _lps("shared")  # element 0 (id 5)
        + bytes([9]) + struct.pack("<i", 5)           # element 1: reference to id 5
        + bytes([11])
    )
    assert read_nrbf(stream) == ["shared", "shared"]


def test_read_primitive_array() -> None:
    stream = (
        _header(1)
        + bytes([15]) + struct.pack("<ii", 1, 3)  # ArraySinglePrimitive id=1 len=3
        + bytes([8])                                # primitive type Int32
        + struct.pack("<iii", 10, 20, 30)
        + bytes([11])
    )
    assert read_nrbf(stream) == [10, 20, 30]


def test_object_null_members() -> None:
    # A class with a single String member that is null.
    stream = (
        _header(1)
        + bytes([12]) + struct.pack("<i", 2) + _lps("Lib")
        + bytes([5]) + struct.pack("<i", 1) + _lps("Thing") + struct.pack("<i", 1)
        + _lps("Note")
        + bytes([1])              # binary type: String
        + struct.pack("<i", 2)    # library id
        + bytes([10])             # value: ObjectNull
        + bytes([11])
    )
    obj = read_nrbf(stream)
    assert obj.members["Note"] is None
