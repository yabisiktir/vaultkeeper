"""Reading and writing user preferences from a dialog.

``ProfileController`` has no ``settings`` attribute: it loads a fresh
:class:`~vaultkeeper.config.settings.Settings` on demand through ``_settings()``
and knows the file to write it back to. A dialog that reached for
``controller.settings`` would therefore get ``None`` and silently discard every
preference the user set — which is exactly what happened to the Portrait
Manager's and Start Screen Manager's Options menus before this existed.

The accessor is shared rather than repeated per dialog so there is one place
that knows the shape, and one place to fix if it changes.
"""

from __future__ import annotations


class SettingsAccess:
    """Mixin: ``_settings`` snapshot plus a persisting setter.

    Expects ``self._controller`` to be set before :meth:`_init_settings` runs.
    A controller may expose either ``_settings()`` (the real one) or a plain
    ``settings`` attribute (test doubles); both work.
    """

    def _init_settings(self) -> None:
        self._settings = self._load_settings()

    def _load_settings(self):
        getter = getattr(self._controller, "_settings", None)
        if callable(getter):
            return getter()
        return getattr(self._controller, "settings", None)

    def _setting(self, name: str, default):
        return getattr(self._settings, name, default) if self._settings else default

    def _store_setting(self, name: str, value) -> None:
        """Set a preference and write it to disk.

        Written immediately rather than on dialog close: these are toggles in an
        Options menu, and a menu that forgets what you picked because you closed
        the window the wrong way is worse than no menu.
        """
        if self._settings is None:
            return
        setattr(self._settings, name, value)

        save = getattr(self._controller, "save_settings", None)
        if callable(save):  # a host that manages persistence itself
            save()
            return
        path = getattr(self._controller, "_settings_path", None)
        if path is not None:
            from vaultkeeper.config.settings import save_settings

            save_settings(self._settings, path)
