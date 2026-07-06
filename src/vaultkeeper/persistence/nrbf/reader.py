"""A minimal MS-NRBF (.NET BinaryFormatter) reader for legacy NIT Store migration.

Implements just the record/type surface the NIT payloads use (see
``rehaul/03_DATA_FORMAT_SPEC.md`` §4.3): the serialization header, class records
(with/without types, by-id reuse), binary strings, member references, nulls,
binary library, and single-dimension primitive/object/string arrays. Reading is
all the hybrid migration needs — comparer objects are skipped and object
references are resolved into a plain Python graph.

The parsed graph uses:
* :class:`NrbfClass` for class instances (``name``, ``library``, ``members``),
* ``list`` for arrays, ``dict`` values decoded to Python primitives,
* ``datetime`` for ``DateTime`` and ``timedelta`` for ``TimeSpan``.

References are resolved after the stream is read; the reader stops at
``MessageEnd`` and never reads trailing padding.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# -- Record type enumeration ---------------------------------------------- #
_SERIALIZED_STREAM_HEADER = 0
_CLASS_WITH_ID = 1
_SYSTEM_CLASS_WITH_MEMBERS = 2
_CLASS_WITH_MEMBERS = 3
_SYSTEM_CLASS_WITH_MEMBERS_AND_TYPES = 4
_CLASS_WITH_MEMBERS_AND_TYPES = 5
_BINARY_OBJECT_STRING = 6
_BINARY_ARRAY = 7
_MEMBER_PRIMITIVE_TYPED = 8
_MEMBER_REFERENCE = 9
_OBJECT_NULL = 10
_MESSAGE_END = 11
_BINARY_LIBRARY = 12
_OBJECT_NULL_MULTIPLE_256 = 13
_OBJECT_NULL_MULTIPLE = 14
_ARRAY_SINGLE_PRIMITIVE = 15
_ARRAY_SINGLE_OBJECT = 16
_ARRAY_SINGLE_STRING = 17

# -- BinaryType enumeration (member categories) --------------------------- #
_BT_PRIMITIVE = 0
_BT_STRING = 1
_BT_OBJECT = 2
_BT_SYSTEM_CLASS = 3
_BT_CLASS = 4
_BT_OBJECT_ARRAY = 5
_BT_STRING_ARRAY = 6
_BT_PRIMITIVE_ARRAY = 7

# -- PrimitiveType enumeration -------------------------------------------- #
_PT_BOOLEAN = 1
_PT_BYTE = 2
_PT_CHAR = 3
_PT_DECIMAL = 5
_PT_DOUBLE = 6
_PT_INT16 = 7
_PT_INT32 = 8
_PT_INT64 = 9
_PT_SBYTE = 10
_PT_SINGLE = 11
_PT_TIMESPAN = 12
_PT_DATETIME = 13
_PT_UINT16 = 14
_PT_UINT32 = 15
_PT_UINT64 = 16
_PT_STRING = 18

_DOTNET_EPOCH = datetime(1, 1, 1)


class NrbfError(ValueError):
    """Raised when the byte stream is not valid/expected NRBF."""


@dataclass
class NrbfClass:
    """A parsed .NET object instance."""

    name: str
    library: str | None
    members: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"NrbfClass({self.name!r}, members={list(self.members)})"


@dataclass
class _Ref:
    """An unresolved MemberReference (resolved after the full stream is read)."""

    id: int


@dataclass
class _ClassMeta:
    name: str
    library: str | None
    member_names: list[str]
    member_types: list[tuple[int, Any]]  # (binary_type, additional_info)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._d = data
        self._p = 0
        self.objects: dict[int, Any] = {}
        self.metas: dict[int, _ClassMeta] = {}
        self.libraries: dict[int, str] = {}
        self.root_id = 0

    # -- primitive stream reads ------------------------------------------- #
    def _take(self, n: int) -> bytes:
        if self._p + n > len(self._d):
            raise NrbfError("unexpected end of stream")
        chunk = self._d[self._p : self._p + n]
        self._p += n
        return chunk

    def _byte(self) -> int:
        return self._take(1)[0]

    def _int32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def _uint32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def _int64(self) -> int:
        return struct.unpack("<q", self._take(8))[0]

    def _uint64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def _double(self) -> float:
        return struct.unpack("<d", self._take(8))[0]

    def _single(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def _bool(self) -> bool:
        return self._byte() != 0

    def _string(self) -> str:
        length = self._varint()
        return self._take(length).decode("utf-8")

    def _varint(self) -> int:
        result = 0
        shift = 0
        while True:
            b = self._byte()
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return result

    def _datetime(self) -> datetime:
        raw = self._uint64()
        ticks = raw & 0x3FFFFFFFFFFFFFFF  # low 62 bits; top 2 = DateTimeKind
        return _DOTNET_EPOCH + timedelta(microseconds=ticks // 10)

    def _timespan(self) -> timedelta:
        return timedelta(microseconds=self._int64() // 10)

    # -- primitive value by type ------------------------------------------ #
    def _primitive(self, pt: int) -> Any:
        if pt == _PT_BOOLEAN:
            return self._bool()
        if pt == _PT_BYTE:
            return self._byte()
        if pt == _PT_CHAR:
            # A single UTF-8 char (length-prefixed in NRBF's Char encoding).
            return self._take(1).decode("latin-1")
        if pt == _PT_INT16:
            return struct.unpack("<h", self._take(2))[0]
        if pt == _PT_INT32:
            return self._int32()
        if pt == _PT_INT64:
            return self._int64()
        if pt == _PT_UINT16:
            return struct.unpack("<H", self._take(2))[0]
        if pt == _PT_UINT32:
            return self._uint32()
        if pt == _PT_UINT64:
            return self._uint64()
        if pt == _PT_SBYTE:
            return struct.unpack("<b", self._take(1))[0]
        if pt == _PT_SINGLE:
            return self._single()
        if pt == _PT_DOUBLE:
            return self._double()
        if pt == _PT_DATETIME:
            return self._datetime()
        if pt == _PT_TIMESPAN:
            return self._timespan()
        if pt == _PT_STRING:
            return self._string()
        raise NrbfError(f"unsupported primitive type {pt}")

    # -- class metadata --------------------------------------------------- #
    def _read_class_info(self) -> tuple[int, str, list[str]]:
        object_id = self._int32()
        name = self._string()
        member_count = self._int32()
        member_names = [self._string() for _ in range(member_count)]
        return object_id, name, member_names

    def _read_member_type_info(self, count: int) -> list[tuple[int, Any]]:
        binary_types = [self._byte() for _ in range(count)]
        types: list[tuple[int, Any]] = []
        for bt in binary_types:
            info: Any = None
            if bt in (_BT_PRIMITIVE, _BT_PRIMITIVE_ARRAY):
                info = self._byte()  # primitive type
            elif bt == _BT_SYSTEM_CLASS:
                info = self._string()  # class name
            elif bt == _BT_CLASS:
                info = (self._string(), self._int32())  # (type name, library id)
            types.append((bt, info))
        return types

    def _read_members(self, meta: _ClassMeta) -> dict[str, Any]:
        members: dict[str, Any] = {}
        for name, (bt, info) in zip(meta.member_names, meta.member_types, strict=True):
            if bt == _BT_PRIMITIVE:
                members[name] = self._primitive(info)
            else:
                members[name] = self._read_record()
        return members

    # -- records ---------------------------------------------------------- #
    def _read_record(self) -> Any:
        rec = self._byte()
        if rec == _BINARY_LIBRARY:
            lib_id = self._int32()
            self.libraries[lib_id] = self._string()
            return self._read_record()  # a library record precedes a real one
        if rec == _CLASS_WITH_MEMBERS_AND_TYPES:
            return self._read_class_with_types(with_library=True)
        if rec == _SYSTEM_CLASS_WITH_MEMBERS_AND_TYPES:
            return self._read_class_with_types(with_library=False)
        if rec == _CLASS_WITH_ID:
            object_id = self._int32()
            metadata_id = self._int32()
            meta = self.metas[metadata_id]
            obj = NrbfClass(meta.name, meta.library)
            self.objects[object_id] = obj
            obj.members = self._read_members(meta)
            return obj
        if rec == _BINARY_OBJECT_STRING:
            object_id = self._int32()
            value = self._string()
            self.objects[object_id] = value
            return value
        if rec == _MEMBER_REFERENCE:
            return _Ref(self._int32())
        if rec == _MEMBER_PRIMITIVE_TYPED:
            return self._primitive(self._byte())
        if rec == _OBJECT_NULL:
            return None
        if rec == _ARRAY_SINGLE_OBJECT:
            return self._read_object_array()
        if rec == _ARRAY_SINGLE_STRING:
            return self._read_object_array()  # elements are strings/refs/nulls
        if rec == _ARRAY_SINGLE_PRIMITIVE:
            return self._read_primitive_array()
        raise NrbfError(f"unsupported record type {rec} at offset {self._p - 1}")

    def _read_class_with_types(self, *, with_library: bool) -> NrbfClass:
        object_id, name, member_names = self._read_class_info()
        member_types = self._read_member_type_info(len(member_names))
        library = None
        if with_library:
            library = self.libraries.get(self._int32())
        meta = _ClassMeta(name, library, member_names, member_types)
        self.metas[object_id] = meta
        obj = NrbfClass(name, library)
        self.objects[object_id] = obj
        obj.members = self._read_members(meta)
        return obj

    def _read_array_info(self) -> tuple[int, int]:
        return self._int32(), self._int32()  # (object id, length)

    def _read_object_array(self) -> list[Any]:
        object_id, length = self._read_array_info()
        items: list[Any] = []
        while len(items) < length:
            rec = self._d[self._p]
            if rec == _OBJECT_NULL_MULTIPLE_256:
                self._p += 1
                items.extend([None] * self._byte())
            elif rec == _OBJECT_NULL_MULTIPLE:
                self._p += 1
                items.extend([None] * self._int32())
            else:
                items.append(self._read_record())
        self.objects[object_id] = items
        return items

    def _read_primitive_array(self) -> list[Any]:
        object_id, length = self._read_array_info()
        pt = self._byte()
        items = [self._primitive(pt) for _ in range(length)]
        self.objects[object_id] = items
        return items

    # -- top level -------------------------------------------------------- #
    def read(self) -> Any:
        header = self._byte()
        if header != _SERIALIZED_STREAM_HEADER:
            raise NrbfError("stream does not start with a serialization header")
        self.root_id = self._int32()
        self._int32()  # header id
        self._int32()  # major version
        self._int32()  # minor version

        while self._d[self._p] != _MESSAGE_END:
            self._read_record()
        return _resolve(self.objects.get(self.root_id), self.objects)


def _resolve(value: Any, objects: dict[int, Any], seen: set[int] | None = None) -> Any:
    """Replace _Ref placeholders with their objects, recursively."""
    seen = seen if seen is not None else set()
    if isinstance(value, _Ref):
        return _resolve(objects.get(value.id), objects, seen)
    if isinstance(value, NrbfClass):
        if id(value) in seen:
            return value
        seen.add(id(value))
        value.members = {k: _resolve(v, objects, seen) for k, v in value.members.items()}
        return value
    if isinstance(value, list):
        return [_resolve(v, objects, seen) for v in value]
    return value


def read_nrbf(data: bytes) -> Any:
    """Parse an MS-NRBF byte stream and return the resolved root object."""
    return _Reader(data).read()
