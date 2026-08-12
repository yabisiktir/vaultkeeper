"""Convert an Official/Premium ``.nwm`` module so the Toolset can open it
(newtopic59.htm — "How can I open Official and Premium Mods in the Toolset?").

The Toolset refuses a module whose extension is ``.nwm``; the same bytes under a
``.mod`` name open fine. That is the whole trick, and the rest of the topic is
making the copy installable and — on the Enhanced Edition — dragging along the
haks and tlks the module names so the Toolset does not open it full of missing
references.

This module owns only the *reading* half: what a module says it needs. The
copying, mod creation and install belong to the controller, which has the
profile and the game folders.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.log import get_logger

log = get_logger(__name__)

#: The group converted modules land in, chosen to sort to the bottom of the list
#: (VB ``ZZZ. NIT Converted NWM Mods``) — they are working files, not something
#: you play, and the topic says to delete them when the Toolset is done.
CONVERTED_GROUP = "ZZZ. NIT Converted NWM Mods"

#: The one mod that carries every converted module's hak/tlk references on EE
#: (VB ``NIT Dependencies for Converted Files``).
CONVERTED_DEPS_MOD = "NIT Dependencies for Converted Files"


def module_dependencies(nwm_path: Path) -> tuple[list[str], list[str]]:
    """The haks and tlk a module names, read from its ``module.ifo``.

    Returns ``(hak_names, tlk_names)`` — bare resource names without extension,
    as they appear in ``Mod_HakList`` / ``Mod_CustomTlk``. An unreadable module
    yields two empty lists rather than raising: the conversion is still worth
    doing without the dependency mod, it just leaves the Toolset to grumble
    about missing haks.
    """
    try:
        from nwnfile.formats.erf_reader import ErfReader
        from nwnfile.formats.gff import read_gff
        from nwnfile.hak_stack import hak_names_from_module

        reader = ErfReader()
        info = reader.read_info(nwm_path)
        if info is None:
            return [], []
        ifo = next(
            (r for r in info.resources if r.resref.lower() == "module" and r.res_type == 2014),
            None,
        )
        if ifo is None:
            return [], []
        module = read_gff(reader.read_resource_bytes(nwm_path, ifo)).root
        haks = [h for h in hak_names_from_module(module) if h]
        tlk = module.get("Mod_CustomTlk")
        tlks = [str(tlk)] if tlk else []
        return haks, tlks
    except Exception:  # pragma: no cover - defensive; a bad module is not fatal
        log.exception("Could not read dependencies from %s", nwm_path)
        return [], []
