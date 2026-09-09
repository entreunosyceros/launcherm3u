# -*- coding: utf-8 -*-
"""Punto de entrada del addon Launcher M3U (plugin + script)."""

from __future__ import annotations

import os
import sys

_ADDON_DIR = os.path.dirname(__file__)
_LIB_DIR = os.path.join(_ADDON_DIR, "resources", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, os.path.join(_ADDON_DIR, "resources"))

from lib import kodi_utils as ku  # noqa: E402


def _script_mode() -> bool:
    """Invocado vía RunScript / extensión script (sin handle de plugin)."""
    if not ku.is_plugin_call():
        return True
    # args tipo RunScript(id, ui)
    if len(sys.argv) > 1:
        arg = str(sys.argv[1]).lower()
        if arg in ("ui", "mode=ui", "script"):
            return True
    return False


def main() -> None:
    if _script_mode():
        try:
            from lib.ui_window import open_main

            open_main()
        except Exception as exc:
            ku.log(f"UI script error: {exc}", level=3)
            ku.notify_error(str(exc))
        return

    from lib.plugin import route  # noqa: E402

    params = ku.parse_args()
    action = (params.get("action") or "root").lower()
    try:
        route(params)
    except Exception as exc:
        ku.log(f"Unhandled error: {exc}", level=3)
        ku.notify_error(str(exc))
        if action not in (
            "refresh",
            "clean",
            "browse_m3u",
            "url_m3u",
            "browse_epg",
            "url_epg",
            "check_update",
            "toggle_favorite",
            "toggle_locked",
            "set_pin",
            "clear_locks",
            "audio_tracks",
            "subtitle_tracks",
            "settings",
            "ui",
            "root",
        ):
            ku.end_directory(False)


if __name__ == "__main__":
    main()
