"""Making macOS call the application by its name (VB has no equivalent — Windows
takes the name from the window).

The Apple menu, the Quit and About entries, the Force Quit list and the Dock
tooltip all read **CFBundleName** from the running bundle. Run from source, that
bundle is the Python interpreter's, so every one of them says "Python" — which
is what the owner saw. ``QApplication.setApplicationName`` does not reach any of
them; it is Qt's own name, not the OS's.

A packaged build has its own Info.plist with the right name already, so this
only steps in when the name would otherwise be wrong.

Done with ``ctypes`` over the Objective-C runtime rather than pyobjc: this is
four messages, and a GUI dependency for four messages is a poor trade.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

from nwnfile.log import get_logger

log = get_logger(__name__)

#: Names that mean "nobody set this" — the interpreter's own, in its variants.
_INTERPRETER_NAMES = {"python", "python3", "pythonw", ""}


def set_application_name(name: str) -> bool:
    """Tell macOS the application is called ``name``. True if it was changed.

    A no-op everywhere but macOS, and never fatal: a wrong name in the menu bar
    is a blemish, and nothing here is worth failing a launch over.
    """
    if sys.platform != "darwin":
        return False
    try:
        return _set_bundle_name(name)
    except Exception:
        log.exception("Could not set the macOS application name")
        return False


def _set_bundle_name(name: str) -> bool:
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.objc_msgSend.restype = ctypes.c_void_p

    def send(obj, selector: str, *args, restype=ctypes.c_void_p, argtypes=()):
        fn = ctypes.cast(
            objc.objc_msgSend,
            ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes),
        )
        return fn(obj, objc.sel_registerName(selector.encode()), *args)

    def nsstring(text: str):
        cls = ctypes.c_void_p(objc.objc_getClass(b"NSString"))
        return send(
            send(cls, "alloc"),
            "initWithUTF8String:",
            text.encode(),
            argtypes=[ctypes.c_char_p],
        )

    def text_of(pointer) -> str:
        if not pointer:
            return ""
        return (send(pointer, "UTF8String", restype=ctypes.c_char_p) or b"").decode()

    bundle = send(ctypes.c_void_p(objc.objc_getClass(b"NSBundle")), "mainBundle")
    info = send(bundle, "infoDictionary")
    if not info:
        return False

    key = nsstring("CFBundleName")
    current = text_of(send(info, "objectForKey:", key, argtypes=[ctypes.c_void_p]))
    if current.lower() not in _INTERPRETER_NAMES:
        # A packaged build already carries its own name; do not overwrite it.
        return False

    send(info, "setObject:forKey:", nsstring(name), key, argtypes=[ctypes.c_void_p] * 2)
    return (
        text_of(send(info, "objectForKey:", key, argtypes=[ctypes.c_void_p])) == name
    )
