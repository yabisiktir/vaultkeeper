"""Reconstruct Python dict/list from .NET generic collection NRBF graphs.

``Dictionary<K,V>`` serializes (ISerializable) as a class carrying a
``KeyValuePairs`` array of ``KeyValuePair<K,V>`` structs (plus Version/Comparer/
HashSize, which we ignore — the comparer is only needed by a *writer*). ``List<T>``
serializes with ``_items`` (a T[] array) and ``_size``. These helpers turn those
NrbfClass graphs into ordinary Python containers so the domain mapper can consume
them. User classes are left as :class:`NrbfClass` for the mapper to interpret.
"""

from __future__ import annotations

from typing import Any

from vaultkeeper.persistence.nrbf.reader import NrbfClass

_DICT_PREFIX = "System.Collections.Generic.Dictionary`"
_LIST_PREFIX = "System.Collections.Generic.List`"
_KVP_KEY = "key"
_KVP_VALUE = "value"


def is_net_dict(obj: Any) -> bool:
    return isinstance(obj, NrbfClass) and obj.name.startswith(_DICT_PREFIX)


def is_net_list(obj: Any) -> bool:
    return isinstance(obj, NrbfClass) and obj.name.startswith(_LIST_PREFIX)


def net_dict(obj: NrbfClass) -> dict[Any, Any]:
    """Reconstruct a Python dict from a serialized .NET Dictionary NrbfClass."""
    pairs = obj.members.get("KeyValuePairs") or []
    result: dict[Any, Any] = {}
    for kv in pairs:
        if isinstance(kv, NrbfClass):
            result[kv.members[_KVP_KEY]] = kv.members[_KVP_VALUE]
    return result


def net_list(obj: NrbfClass) -> list[Any]:
    """Reconstruct a Python list from a serialized .NET List NrbfClass."""
    items = obj.members.get("_items") or []
    size = obj.members.get("_size", len(items))
    return list(items[:size])


def simplify(value: Any) -> Any:
    """Recursively convert .NET Dictionary/List graphs to Python dict/list.

    Keys/values are simplified too; user classes (e.g. ModData) are returned as
    NrbfClass with their members simplified, for the domain mapper to interpret.
    """
    if is_net_dict(value):
        return {simplify(k): simplify(v) for k, v in net_dict(value).items()}
    if is_net_list(value):
        return [simplify(v) for v in net_list(value)]
    if isinstance(value, list):
        return [simplify(v) for v in value]
    if isinstance(value, NrbfClass):
        value.members = {k: simplify(v) for k, v in value.members.items()}
        return value
    return value
