"""NIT's "Module Data IFO" table: save names for modules that do not give one.

VB ``ErfFileReader.ValidateModInfo`` / ``LoadModuleData``. When a module's
``module.ifo`` has no usable ``Mod_Name`` or its description cannot be read, the
save name and description come from this table, keyed by the module's file name.
NIT downloads the current table from its site and falls back to the copy it
ships; here the fetched copy is cached in the store's Data folder beside the
download rules, and the bundled copy is the floor.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from nwnfile.log import get_logger

log = get_logger(__name__)

#: File name of the published table (VB ``ModuleDataOnlineFile``).
MODULE_DATA_FILENAME = "Module Data IFO.txt"
#: Where NIT publishes it (VB ``BaseLazWorksUrl``).
MODULE_DATA_URL = "https://lazworks.azurewebsites.net/Module%20Data%20IFO.txt"

_BUNDLED = Path(__file__).resolve().parent / "data" / MODULE_DATA_FILENAME


def parse_module_data(text: str) -> dict[str, tuple[str, str]]:
    """``{module file name (lower): (save name, description)}`` (VB ``LoadModuleData``)."""
    table: dict[str, tuple[str, str]] = {}
    name = save = ""
    description: list[str] = []
    for line in [*text.splitlines(), "#Module:End"]:
        if line.startswith("#Module:"):
            if name:
                table[name.lower()] = (save, "\r\n".join(description).rstrip("\r\n"))
            name, save, description = line.split(":", 1)[1].strip(), "", []
        elif line.startswith("ModSavName="):
            save = line.split("=", 1)[1]
        else:
            description.append(line)
    return table


def _read(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1252", errors="replace")


@lru_cache(maxsize=8)
def _load(path: str, _mtime: float) -> dict[str, tuple[str, str]]:
    try:
        return parse_module_data(_read(Path(path)))
    except OSError:
        return {}


def load_module_data(data_dir: Path | None = None) -> dict[str, tuple[str, str]]:
    """The fetched copy in ``data_dir`` when there is one, else the bundled copy."""
    for path in ([Path(data_dir) / MODULE_DATA_FILENAME] if data_dir else []) + [_BUNDLED]:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        table = _load(str(path), mtime)
        if table:
            return table
    return {}


def fetch_module_data(http, data_dir: Path) -> bool:
    """Download the current table into ``data_dir`` (VB ``DownloadModuleData``)."""
    try:
        response = http.get(MODULE_DATA_URL, allow_redirects=True)
    except Exception as ex:  # offline, DNS, TLS: the bundled copy stands in
        log.info("Module Data IFO unavailable: %s", ex)
        return False
    if not getattr(response, "ok", False):
        return False
    content = getattr(response, "content", b"") or (getattr(response, "text", "") or "").encode()
    if not content.strip() or b"#Module:" not in content:
        return False
    try:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        (Path(data_dir) / MODULE_DATA_FILENAME).write_bytes(content)
    except OSError as ex:
        log.warning("Could not cache the Module Data IFO file: %s", ex)
        return False
    return True
