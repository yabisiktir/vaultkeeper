"""Tests for reconstructing Python dict/list from .NET collection NRBF graphs.

Builds valid NRBF streams for a serialized Dictionary<String,Int32> and a
List<Int32> (the record encoding itself is already covered by test_nrbf) and
checks the collection reconstruction.
"""

from __future__ import annotations

import struct

from vaultkeeper.persistence.nrbf.collections import simplify
from vaultkeeper.persistence.nrbf.reader import read_nrbf


def _lps(s: str) -> bytes:
    data = s.encode("utf-8")
    n, out = len(data), bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            break
    return bytes(out) + data


def _header(root_id: int = 1) -> bytes:
    return struct.pack("<Biiii", 0, root_id, -1, 1, 0)


def _end() -> bytes:
    return bytes([11])


def _sys_class(
    oid: int,
    name: str,
    member_names: list[str],
    binary_types: list[int],
    additional: list[bytes],
    values: bytes,
) -> bytes:
    b = bytes([4]) + struct.pack("<i", oid) + _lps(name) + struct.pack("<i", len(member_names))
    for m in member_names:
        b += _lps(m)
    b += bytes(binary_types)
    for a in additional:
        b += a
    return b + values


def _bos(oid: int, s: str) -> bytes:
    return bytes([6]) + struct.pack("<i", oid) + _lps(s)


def _obj_array(oid: int, elements: list[bytes]) -> bytes:
    return bytes([16]) + struct.pack("<ii", oid, len(elements)) + b"".join(elements)


def _kvp(oid: int, key_oid: int, key: str, val: int) -> bytes:
    return _sys_class(
        oid,
        "System.Collections.Generic.KeyValuePair`2[[System.String],[System.Int32]]",
        ["key", "value"],
        [1, 0],
        [bytes([8])],  # value: Int32
        _bos(key_oid, key) + struct.pack("<i", val),
    )


def test_reconstructs_dictionary() -> None:
    kvps = _obj_array(10, [_kvp(11, 12, "a", 7), _kvp(13, 14, "b", 9)])
    values = struct.pack("<i", 0) + bytes([10]) + struct.pack("<i", 2) + kvps
    dict_rec = _sys_class(
        1,
        "System.Collections.Generic.Dictionary`2[[System.String],[System.Int32]]",
        ["Version", "Comparer", "HashSize", "KeyValuePairs"],
        [0, 3, 0, 5],  # Primitive, SystemClass, Primitive, ObjectArray
        [bytes([8]), _lps("SomeComparer"), bytes([8])],
        values,
    )
    result = simplify(read_nrbf(_header(1) + dict_rec + _end()))
    assert result == {"a": 7, "b": 9}


def test_reconstructs_list() -> None:
    items = (
        bytes([15])
        + struct.pack("<ii", 20, 4)
        + bytes([8])
        + struct.pack("<iiii", 10, 20, 30, 0)
    )
    values = items + struct.pack("<i", 3) + struct.pack("<i", 99)  # _size=3, _version=99
    list_rec = _sys_class(
        1,
        "System.Collections.Generic.List`1[[System.Int32]]",
        ["_items", "_size", "_version"],
        [7, 0, 0],  # PrimitiveArray, Primitive, Primitive
        [bytes([8]), bytes([8]), bytes([8])],
        values,
    )
    # _items holds 4 slots but _size is 3 -> only the first 3 are real.
    assert simplify(read_nrbf(_header(1) + list_rec + _end())) == [10, 20, 30]
