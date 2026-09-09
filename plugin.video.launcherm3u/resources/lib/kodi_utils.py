# -*- coding: utf-8 -*-
"""Helpers de acceso a Kodi (settings, rutas, diálogos)."""

from __future__ import annotations

import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_PATH = ADDON.getAddonInfo("path")
PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
HANDLE = -1
if len(sys.argv) > 1:
    try:
        HANDLE = int(sys.argv[1])
    except (TypeError, ValueError):
        HANDLE = -1


def is_plugin_call() -> bool:
    """True si se invocó como pluginsource (plugin://...)."""
    arg0 = sys.argv[0] if sys.argv else ""
    return arg0.startswith("plugin://") or HANDLE >= 0


def get_setting(key: str, default: str = "") -> str:
    value = ADDON.getSetting(key)
    return value if value not in (None, "") else default


def get_setting_bool(key: str, default: bool = False) -> bool:
    raw = ADDON.getSetting(key)
    if raw in (None, ""):
        return default
    if hasattr(ADDON, "getSettingBool"):
        return bool(ADDON.getSettingBool(key))
    return str(raw).strip().lower() == "true"


def get_setting_int(key: str, default: int = 0) -> int:
    raw = ADDON.getSetting(key)
    try:
        if raw not in (None, ""):
            return int(float(str(raw).strip()))
        if hasattr(ADDON, "getSettingInt"):
            return int(ADDON.getSettingInt(key))
    except (TypeError, ValueError):
        pass
    return default


def set_setting(key: str, value: str) -> None:
    ADDON.setSetting(key, value)


def set_setting_int(key: str, value: int) -> None:
    if hasattr(ADDON, "setSettingInt"):
        ADDON.setSettingInt(key, int(value))
    else:
        ADDON.setSetting(key, str(int(value)))


def set_setting_bool(key: str, value: bool) -> None:
    if hasattr(ADDON, "setSettingBool"):
        ADDON.setSettingBool(key, bool(value))
    else:
        ADDON.setSetting(key, "true" if value else "false")


def get_string(string_id: int) -> str:
    text = ADDON.getLocalizedString(string_id)
    return text if text else ""


def ensure_profile() -> str:
    if not xbmcvfs.exists(PROFILE_PATH):
        xbmcvfs.mkdirs(PROFILE_PATH)
    return PROFILE_PATH


def plugin_url(**params) -> str:
    return f"plugin://{ADDON_ID}/?{urlencode({k: v for k, v in params.items() if v is not None})}"


def parse_args() -> dict:
    if len(sys.argv) > 2 and sys.argv[2]:
        return dict(parse_qsl(sys.argv[2].lstrip("?")))
    return {}


def notify(message: str, time_ms: int = 3500) -> None:
    xbmcgui.Dialog().notification(ADDON_NAME, message, xbmcgui.NOTIFICATION_INFO, time_ms)


def notify_error(message: str, time_ms: int = 5000) -> None:
    xbmcgui.Dialog().notification(ADDON_NAME, message, xbmcgui.NOTIFICATION_ERROR, time_ms)


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def end_directory(succeeded: bool = True, update: bool = False) -> None:
    if HANDLE < 0:
        return
    xbmcplugin.endOfDirectory(HANDLE, succeeded=succeeded, updateListing=update, cacheToDisc=False)


def set_content(content: str = "videos") -> None:
    if HANDLE < 0:
        return
    xbmcplugin.setContent(HANDLE, content)


def add_directory_item(label: str, url: str, art: dict | None = None, info: dict | None = None,
                       is_folder: bool = True, total: int = 0) -> None:
    if HANDLE < 0:
        return
    list_item = xbmcgui.ListItem(label=label)
    if art:
        list_item.setArt(art)
    if info:
        list_item.setInfo("video", info)
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=is_folder, totalItems=total)


def add_playable_item(label: str, url: str, stream_url: str, art: dict | None = None,
                      info: dict | None = None, properties: dict | None = None) -> None:
    if HANDLE < 0:
        return
    list_item = xbmcgui.ListItem(label=label, path=stream_url)
    list_item.setProperty("IsPlayable", "true")
    if art:
        list_item.setArt(art)
    if info:
        list_item.setInfo("video", info)
    if properties:
        for key, value in properties.items():
            list_item.setProperty(key, str(value))
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=False)
