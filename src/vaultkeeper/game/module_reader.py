"""ErfModuleReader — reads a module's save name + description from a .mod/.nwm.

Concrete :class:`~vaultkeeper.game.game_mapper.ModuleInfoReader` for GameMapper's
cross-profile scan. Faithful port of ``ErfFileReader.vb`` + ``ErfFileReader.IfoReader.vb``:

1. Parse the ERF header (MOD/ERF/SAV, V1.0).
2. Read the English localized description from the ERF's localized-string list.
3. Find the ``module`` resource of type 2014 (IFO) in the ERF key list.
4. GFF-parse that ``module.ifo`` and return the English text of its ``Mod_Name``
   CExoLocString field — the module's save name.
5. Left-trim it and strip the illegal folder characters (``/:*?<>|"``).

Self-contained struct decoding (little-endian), so it doesn't depend on the generic
salvaged ERF/GFF readers. Returns ``None`` when the file isn't a readable module.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

from nwnfile.log import get_logger

from vaultkeeper.game.game_mapper import (
    READ_FAILURE_TEXT,
    UNKNOWN_SAVE_NAME,
    ModuleInfo,
)

log = get_logger(__name__)

#: Text when the module author defined no description (``ErfFileReader.NoDescription``).
NO_DESCRIPTION = "The author did not define a Mod description."
#: Characters stripped from a save name (``LazWorks Constants.IllegalFolderChars``).
_ILLEGAL_FOLDER_CHARS = '/:*?<>|"'
#: ERF container types this reader accepts.
_VALID_ERF_TYPES = frozenset({"MOD ", "ERF ", "SAV "})
#: Resource type of ``module.ifo`` inside the ERF key list.
_IFO_RESTYPE = 2014


def _u32(f: BinaryIO) -> int:
    return struct.unpack("<I", f.read(4))[0]


def _i32(f: BinaryIO) -> int:
    return struct.unpack("<i", f.read(4))[0]


def _i16(f: BinaryIO) -> int:
    return struct.unpack("<h", f.read(2))[0]


class ErfModuleReader:
    """Reads :class:`ModuleInfo` from an NWN ``.mod``/``.nwm`` (ERF) file."""

    def read(self, path: Path) -> ModuleInfo | None:
        try:
            with open(path, "rb") as f:
                erf_type = f.read(4).decode("ascii", "replace")
                version = f.read(4).decode("ascii", "replace")
                loc_count = _i32(f)
                _loc_size = _i32(f)
                keys_count = _i32(f)
                loc_offset = _i32(f)
                keys_offset = _i32(f)
                res_offset = _i32(f)

                if erf_type not in _VALID_ERF_TYPES and version != "V1.0":
                    return None

                description = _read_description(f, loc_count, loc_offset)
                res_id = _find_resource(f, keys_offset, keys_count, "module", _IFO_RESTYPE)
                save_name = UNKNOWN_SAVE_NAME
                if res_id != -1:
                    res_pos = _resource_position(f, res_offset, res_id)
                    save_name = _read_ifo_mod_name(f, res_pos) or UNKNOWN_SAVE_NAME

                save_name = save_name.lstrip()
                for ch in _ILLEGAL_FOLDER_CHARS:
                    save_name = save_name.replace(ch, "")

                return ModuleInfo(
                    save_name=save_name,
                    description=description,
                    mod_filename=path.name,
                )
        except (OSError, struct.error, UnicodeDecodeError) as ex:
            log.debug("Unable to read module %s: %s", path, ex)
            return None


def _read_description(f: BinaryIO, loc_count: int, loc_offset: int) -> str:
    """The English (language 0) localized description (``GetDescription``)."""
    if loc_count == 0:
        return NO_DESCRIPTION
    f.seek(loc_offset)
    for _ in range(loc_count):
        language_id = _i32(f)
        size = _i32(f)
        description = f.read(size).decode("ascii", "replace")
        if language_id == 0:
            return description
    return READ_FAILURE_TEXT


def _find_resource(
    f: BinaryIO, keys_offset: int, keys_count: int, key_name: str, res_type: int
) -> int:
    """ResId of the ``key_name``/``res_type`` entry in the key list, else -1 (``FindFile``)."""
    key_name = key_name.lower()
    f.seek(keys_offset)
    for _ in range(keys_count):
        resref = f.read(16).rstrip(b"\x00").decode("ascii", "replace").lower()
        res_id = _i32(f)
        rec_type = _i16(f)
        f.read(2)  # unused
        if resref == key_name and rec_type == res_type:
            return res_id
    return -1


def _resource_position(f: BinaryIO, res_offset: int, res_id: int) -> tuple[int, int]:
    """The (offset, size) of a resource in the file (``GetResourcePosition``)."""
    f.seek(res_offset + res_id * 8)
    offset = _u32(f)
    size = _i32(f)
    return offset, size


def _read_ifo_mod_name(f: BinaryIO, res_pos: tuple[int, int]) -> str | None:
    """GFF-parse ``module.ifo`` and return the English ``Mod_Name`` (``IfoReader``)."""
    base, _size = res_pos
    f.seek(base)
    ifo_type = f.read(4).decode("ascii", "replace")
    ifo_version = f.read(4).decode("ascii", "replace")
    struct_offset = _u32(f)
    _struct_count = _u32(f)
    field_offset = _u32(f)
    _field_count = _u32(f)
    label_offset = _u32(f)
    _label_count = _u32(f)
    field_data_offset = _u32(f)
    _field_data_count = _u32(f)
    field_indices_offset = _u32(f)
    _field_indices_count = _u32(f)
    _list_indices_offset = _u32(f)
    _list_indices_count = _u32(f)

    if ifo_type != "IFO " or ifo_version != "V3.2":
        return None

    # Top (root) struct — type must be 0xFFFFFFFF (-1 as signed).
    f.seek(base + struct_offset)
    struct_type = _i32(f)
    _struct_data_offset = _u32(f)
    struct_field_count = _u32(f)
    if struct_type != -1:
        return None

    # The root struct's field indices start at the field-indices array (offset 0),
    # mirroring the VB reader.
    f.seek(base + field_indices_offset)
    indices = [_u32(f) for _ in range(struct_field_count)]

    for index in indices:
        f.seek(base + field_offset + index * 12)
        _field_type = _i32(f)
        label_index = _u32(f)
        data_or_offset = _u32(f)
        if _read_label(f, base, label_offset, label_index) == "Mod_Name":
            return _read_cexolocstring(f, base, field_data_offset, data_or_offset)
    return None


def _read_label(f: BinaryIO, base: int, label_offset: int, label_index: int) -> str:
    f.seek(base + label_offset + label_index * 16)
    return f.read(16).rstrip(b"\x00").decode("ascii", "replace")


def _read_cexolocstring(
    f: BinaryIO, base: int, field_data_offset: int, data_offset: int
) -> str | None:
    """English substring (string id 0) of a CExoLocString field value."""
    f.seek(base + field_data_offset + data_offset)
    _total_size = _u32(f)
    _strref = _u32(f)
    count = _u32(f)
    for _ in range(count):
        string_id = _u32(f)
        string_len = _u32(f)
        contents = f.read(string_len).decode("ascii", "replace")
        if string_id == 0:
            return contents
    return None
