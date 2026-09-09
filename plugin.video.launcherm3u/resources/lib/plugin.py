# -*- coding: utf-8 -*-
"""Navegación del addon: grupos, canales, EPG y reproducción."""

from __future__ import annotations

import time

import xbmc
import xbmcgui
import xbmcplugin

from . import cache
from . import cleaner
from . import downloader
from . import kodi_utils as ku
from . import loader


def _art(logo: str = "") -> dict:
    icon = logo or "DefaultTVShows.png"
    return {"icon": icon, "thumb": icon, "poster": icon, "fanart": ku.ADDON.getAddonInfo("fanart")}


def _channel_art(ch) -> dict:
    logo = ch["tvg_logo"] if ku.get_setting_bool("show_channel_logos", True) else ""
    return _art(logo or "")


def _channel_item(ch, label: str, plot: str):
    play_url = ku.plugin_url(action="play", id=ch["id"])
    item = xbmcgui.ListItem(label=label, path=play_url)
    item.setProperty("IsPlayable", "false")
    item.setArt(_channel_art(ch))
    item.setInfo("video", {"title": ch["name"], "plot": plot, "mediatype": "video"})
    commands = []
    if ku.get_setting_bool("epg_enabled", False) and ch["tvg_id"]:
        commands.append(
            (
                ku.get_string(30210) or "Guía EPG",
                f"Container.Update({ku.plugin_url(action='epg', id=ch['id'])})",
            )
        )
    fav_label = (
        ku.get_string(30502)
        if cache.is_favorite(ch["id"])
        else ku.get_string(30501)
    ) or ("Quitar favorito" if cache.is_favorite(ch["id"]) else "Favorito")
    commands.append(
        (
            fav_label,
            f"RunPlugin({ku.plugin_url(action='toggle_favorite', id=ch['id'])})",
        )
    )
    lock_label = (
        ku.get_string(30607)
        if cache.is_locked(ch["id"])
        else ku.get_string(30606)
    ) or ("Desbloquear" if cache.is_locked(ch["id"]) else "Bloquear con PIN")
    commands.append(
        (
            lock_label,
            f"RunPlugin({ku.plugin_url(action='toggle_locked', id=ch['id'])})",
        )
    )
    commands.append(
        (
            ku.get_string(30200) or "Ajustes",
            "Addon.OpenSettings(plugin.video.launcherm3u)",
        )
    )
    item.addContextMenuItems(commands)
    return play_url, item


def root() -> None:
    """Cierra el plugin y abre la UI como script (videowindow requiere script)."""
    global_window = xbmcgui.Window(10000)

    # Kodi puede volver a ejecutar la URL raíz cuando se cierra WindowXML.
    # La marca de cierre hace que se abandone el contenedor en vez de relanzarla.
    try:
        closed_at = float(
            global_window.getProperty("LauncherM3U.SuppressAutoOpen") or "0"
        )
    except (TypeError, ValueError):
        closed_at = 0.0
    if closed_at and time.time() - closed_at < 8.0:
        global_window.clearProperty("LauncherM3U.SuppressAutoOpen")
        ku.end_directory(True)
        xbmc.executebuiltin("Action(Back)")
        return
    if closed_at:
        global_window.clearProperty("LauncherM3U.SuppressAutoOpen")

    # También evita dos instancias si Kodi invoca root mientras la UI sigue viva.
    if global_window.getProperty("LauncherM3U.UIRunning") == "1":
        ku.end_directory(True)
        return

    ku.end_directory(True)
    # RunScript permite Player(windowed=True) + control videowindow
    xbmc.executebuiltin(f"RunScript({ku.ADDON_ID},ui)")


def classic_root() -> None:
    """Listado clásico de respaldo."""
    ku.set_content("files")
    try:
        loader.ensure_data(force=False, show_progress=False)
    except Exception as exc:
        ku.log(f"Error cargando datos: {exc}", level=3)
        ku.notify_error(str(exc))
        ku.add_directory_item(
            ku.get_string(30200) or "Abrir ajustes",
            ku.plugin_url(action="settings"),
            art=_art(),
            is_folder=False,
        )
        ku.end_directory(False)
        return

    total = cache.count_channels()
    if total == 0:
        ku.add_directory_item(
            ku.get_string(30200) or "Abrir ajustes",
            ku.plugin_url(action="settings"),
            art=_art(),
            is_folder=False,
        )
        ku.add_directory_item(
            ku.get_string(30220) or "Seleccionar archivo M3U local",
            ku.plugin_url(action="browse_m3u"),
            art=_art("DefaultFile.png"),
            is_folder=False,
        )
        ku.add_directory_item(
            ku.get_string(30201) or "Recargar lista",
            ku.plugin_url(action="refresh"),
            art=_art(),
            is_folder=False,
        )
        ku.add_directory_item(
            ku.get_string(30300) or "Limpiar caché",
            ku.plugin_url(action="clean_menu"),
            art=_art("DefaultAddonPackage.png"),
            is_folder=True,
        )
        ku.end_directory()
        return

    ku.add_directory_item(
        ku.get_string(30400) or "Abrir interfaz IPTV",
        ku.plugin_url(action="ui"),
        art=_art("DefaultTVShows.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        f"[B]{ku.get_string(30202) or 'Todos los canales'}[/B] ({total})",
        ku.plugin_url(action="channels"),
        art=_art("DefaultTVShows.png"),
        info={"plot": ku.get_string(30203) or "Ver todos los canales"},
    )
    fav_n = cache.count_favorites()
    ku.add_directory_item(
        f"{ku.get_string(30500) or 'Favoritos'} ({fav_n})",
        ku.plugin_url(action="channels", special="favorites"),
        art=_art("DefaultFavourites.png"),
        is_folder=True,
    )
    recent_n = cache.count_recents()
    ku.add_directory_item(
        f"{ku.get_string(30503) or 'Recientes'} ({recent_n})",
        ku.plugin_url(action="channels", special="recents"),
        art=_art("DefaultAddonAlbumInfo.png"),
        is_folder=True,
    )
    ku.add_directory_item(
        ku.get_string(30204) or "Buscar",
        ku.plugin_url(action="search"),
        art=_art("DefaultAddonsSearch.png"),
        is_folder=True,
    )
    ku.add_directory_item(
        ku.get_string(30220) or "Seleccionar archivo M3U local",
        ku.plugin_url(action="browse_m3u"),
        art=_art("DefaultFile.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        ku.get_string(30201) or "Recargar lista",
        ku.plugin_url(action="refresh"),
        art=_art("DefaultAddonsUpdates.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        ku.get_string(30300) or "Limpiar caché",
        ku.plugin_url(action="clean_menu"),
        art=_art("DefaultAddonPackage.png"),
        info={"plot": ku.get_string(30301) or "Borrar caché, descargas y thumbnails del addon"},
        is_folder=True,
    )
    ku.add_directory_item(
        ku.get_string(30200) or "Ajustes",
        ku.plugin_url(action="settings"),
        art=_art("DefaultAddonService.png"),
        is_folder=False,
    )

    groups = cache.list_groups()
    for group in groups:
        label = f"{group['name']} ({group['channel_count']})"
        ku.add_directory_item(
            label,
            ku.plugin_url(action="channels", group=group["name"]),
            art=_art("DefaultFolder.png"),
            info={"plot": f"{group['channel_count']} canales"},
        )
    ku.end_directory()


def list_channels(group: str | None = None, query: str | None = None, page: int = 0,
                  special: str | None = None) -> None:
    ku.set_content("videos")
    page_size = max(25, ku.get_setting_int("page_size", 100))
    offset = page * page_size
    if special == "favorites":
        total = cache.count_favorites()
        channels = cache.list_favorites(offset=offset, limit=page_size)
    elif special == "recents":
        total = cache.count_recents()
        channels = cache.list_recents(offset=offset, limit=page_size)
    else:
        total = cache.count_channels(group_name=group, query=query)
        channels = cache.list_channels(
            group_name=group, query=query, offset=offset, limit=page_size
        )

    show_epg = ku.get_setting_bool("epg_enabled", False) and ku.get_setting_bool("show_epg_in_list", True)
    now_map = {}
    if show_epg:
        now_map = cache.now_playing_for_channels(channels)

    for ch in channels:
        name = ch["name"]
        chno = ch["tvg_chno"]
        label = f"{chno}. {name}" if chno else name
        if cache.is_favorite_url(ch["url"] or ""):
            label = f"[B]{label}[/B]"
        if cache.is_locked_url(ch["url"] or ""):
            label = f"{label} ({ku.get_string(30604) or 'PIN'})"
        plot = ch["group_name"] or ""
        now = now_map.get(int(ch["id"]))
        if now:
            label = f"{label}  [COLOR gray]{now['title']}[/COLOR]"
            plot = (
                f"{loader.format_time(now['start_ts'])}-"
                f"{loader.format_time(now['stop_ts'])}  {now['title']}\n"
                f"{now['description'] or ''}"
            )
        play_url, item = _channel_item(ch, label, plot)
        xbmcplugin.addDirectoryItem(ku.HANDLE, play_url, item, isFolder=False, totalItems=total)

    # Paginación
    if offset + page_size < total:
        next_label = ku.get_string(30211) or "Siguiente página"
        next_params = {
            "action": "channels",
            "page": str(page + 1),
        }
        if special:
            next_params["special"] = special
        else:
            next_params["group"] = group or ""
            next_params["q"] = query or ""
        ku.add_directory_item(
            f"[B]{next_label}[/B] ({offset + page_size}/{total})",
            ku.plugin_url(**next_params),
            art=_art("DefaultFolder.png"),
        )

    ku.end_directory()


def search() -> None:
    keyboard = xbmc.Keyboard("", ku.get_string(30204) or "Buscar")
    keyboard.doModal()
    if not keyboard.isConfirmed():
        ku.end_directory()
        return
    query = keyboard.getText().strip()
    if not query:
        ku.end_directory()
        return
    list_channels(query=query, page=0)


def show_epg(channel_id: int) -> None:
    ku.set_content("videos")
    ch = cache.get_channel(channel_id)
    if not ch:
        ku.notify_error(ku.get_string(30212) or "Canal no encontrado")
        ku.end_directory(False)
        return

    now_ts = int(time.time())
    from_ts = now_ts - 3600
    to_ts = now_ts + 12 * 3600
    programmes = cache.get_programmes(
        ch["tvg_id"], from_ts, to_ts, ch["tvg_name"] or "", ch["name"] or ""
    )

    if not programmes:
        ku.add_directory_item(
            ku.get_string(30213) or "Sin datos EPG para este canal",
            ku.plugin_url(action="play", id=ch["id"]),
            art=_channel_art(ch),
            is_folder=False,
        )
        ku.end_directory()
        return

    for prog in programmes:
        is_now = prog["start_ts"] <= now_ts < prog["stop_ts"]
        prefix = "* " if is_now else ""
        label = (
            f"{prefix}{loader.format_time(prog['start_ts'])}-"
            f"{loader.format_time(prog['stop_ts'])}  {prog['title'] or 'Programa'}"
        )
        item = xbmcgui.ListItem(label=label)
        item.setArt(_channel_art(ch))
        item.setInfo(
            "video",
            {
                "title": prog["title"] or "",
                "plot": prog["description"] or "",
                "mediatype": "video",
            },
        )
        item.setProperty("IsPlayable", "true")
        xbmcplugin.addDirectoryItem(
            ku.HANDLE,
            ku.plugin_url(action="play", id=ch["id"]),
            item,
            isFolder=False,
        )
    ku.end_directory()


def play(channel_id: int) -> None:
    from . import player as zap

    zap.play_channel(channel_id, notify_zap=True)


def refresh(silent: bool = True) -> None:
    """
    Recarga M3U/EPG sin DialogProgress modal (evita cuelgues desde Ajustes).
    """
    try:
        xbmc.executebuiltin("Dialog.Close(all,true)")
        xbmc.sleep(250)
        total = loader.load_playlist(force=True, show_progress=False, manage_busy=True)
        msg = (ku.get_string(30214) or "Lista recargada: {0} canales").format(total)
        if ku.get_setting_bool("epg_enabled", False):
            # manage_busy=False si el busy anterior ya se cerró; un solo ciclo busy vía ensure sería mejor
            progs = loader.load_epg(force=True, show_progress=False, manage_busy=True)
            msg += " / EPG: {0}".format(progs)
        ku.notify(msg)
    except Exception as exc:
        ku.log(f"Refresh error: {exc}", level=3)
        ku.notify_error(str(exc))
    try:
        xbmc.executebuiltin("Container.Refresh")
    except Exception:
        pass


def open_ui() -> None:
    ku.end_directory(True)
    xbmc.executebuiltin(f"RunScript({ku.ADDON_ID},ui)")


def open_settings() -> None:
    ku.ADDON.openSettings()


def browse_m3u() -> None:
    heading = ku.get_string(30220) or "Seleccionar archivo M3U local"
    path = xbmcgui.Dialog().browse(
        1,
        heading,
        "files",
        ".m3u|.m3u8|.txt",
        False,
        False,
        "",
    )
    if not path:
        ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
        return

    ku.set_setting_int("m3u_type", 0)
    ku.set_setting("m3u_path", path)
    ku.notify(f"{ku.get_string(30221) or 'Archivo M3U seleccionado'}: {path}")
    try:
        total = loader.load_playlist(
            force=True, show_progress=False, m3u_path=path, m3u_remote=False
        )
        msg = (ku.get_string(30214) or "Lista recargada: {0} canales").format(total)
        ku.notify(msg)
    except Exception as exc:
        ku.log(f"browse_m3u load error: {exc}", level=3)
        ku.notify_error(str(exc))
    xbmc.executebuiltin("Container.Refresh")


def url_m3u() -> None:
    current = ku.get_setting("m3u_url")
    keyboard = xbmc.Keyboard(current, ku.get_string(30015) or "URL del archivo M3U")
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return
    url = (keyboard.getText() or "").strip().replace("\r", "").replace("\n", "")
    url = downloader.normalize_http_url(url)
    if not url:
        ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
        return
    ku.set_setting_int("m3u_type", 1)
    ku.set_setting("m3u_url", url)
    ku.notify(ku.get_string(30221) or "Lista configurada")
    try:
        total = loader.load_playlist(
            force=True, show_progress=False, m3u_url=url, m3u_remote=True
        )
        msg = (ku.get_string(30214) or "Lista recargada: {0} canales").format(total)
        ku.notify(msg)
    except Exception as exc:
        ku.log(f"url_m3u load error: {exc}", level=3)
        ku.notify_error(str(exc))
    xbmc.executebuiltin("Container.Refresh")


def browse_epg() -> None:
    heading = ku.get_string(30060) or "Seleccionar archivo XMLTV local"
    path = xbmcgui.Dialog().browse(
        1,
        heading,
        "files",
        "",
        False,
        False,
        "",
    )
    if not path:
        ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
        return

    ku.set_setting_bool("epg_enabled", True)
    ku.set_setting_int("epg_type", 0)
    ku.set_setting("epg_path", path)
    ku.notify(f"{ku.get_string(30062) or 'Archivo EPG seleccionado'}: {path}")
    try:
        progs = loader.load_epg(
            force=True, show_progress=False, epg_path=path, epg_remote=False
        )
        ku.notify(f"EPG: {progs}")
        try:
            linked, total_ch = cache.count_epg_links()
            ku.notify(f"EPG enlazado: {linked}/{total_ch} canales")
        except Exception:
            pass
    except Exception as exc:
        ku.log(f"browse_epg load error: {exc}", level=3)
        ku.notify_error(str(exc))
    xbmc.executebuiltin("Container.Refresh")


def url_epg() -> None:
    current = ku.get_setting("epg_url")
    keyboard = xbmc.Keyboard(current, ku.get_string(30061) or "URL del archivo XMLTV")
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return
    url = (keyboard.getText() or "").strip().replace("\r", "").replace("\n", "")
    url = downloader.normalize_http_url(url)
    if not url:
        ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
        return
    ku.set_setting_bool("epg_enabled", True)
    ku.set_setting_int("epg_type", 1)
    ku.set_setting("epg_url", url)
    ku.notify(ku.get_string(30062) or "Guía EPG configurada")
    try:
        progs = loader.load_epg(
            force=True, show_progress=False, epg_url=url, epg_remote=True
        )
        ku.notify(f"EPG: {progs}")
        try:
            linked, total_ch = cache.count_epg_links()
            ku.notify(f"EPG enlazado: {linked}/{total_ch} canales")
        except Exception:
            pass
    except Exception as exc:
        ku.log(f"url_epg load error: {exc}", level=3)
        ku.notify_error(str(exc))
    xbmc.executebuiltin("Container.Refresh")


def clean_menu() -> None:
    ku.set_content("files")
    stats = cleaner.storage_stats()
    profile_size = cleaner.format_bytes(stats.get("profile_bytes", 0))
    ku.add_directory_item(
        f"[I]{ku.get_string(30302) or 'Espacio del addon'}: {profile_size}[/I]",
        ku.plugin_url(action="clean_menu"),
        art=_art("DefaultAddonService.png"),
        info={
            "plot": (
                f"DB: {cleaner.format_bytes(stats.get('db_bytes', 0))} | "
                f"Descargas: {cleaner.format_bytes(stats.get('downloads_bytes', 0))} | "
                f"Logos: {stats.get('logos', 0)}"
            )
        },
        is_folder=False,
    )
    ku.add_directory_item(
        ku.get_string(30303) or "Borrar descargas M3U/EPG",
        ku.plugin_url(action="clean", kind="downloads"),
        art=_art("DefaultFile.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        ku.get_string(30304) or "Borrar base de datos (canales/EPG)",
        ku.plugin_url(action="clean", kind="database"),
        art=_art("DefaultAddonAlbumInfo.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        ku.get_string(30305) or "Borrar thumbnails / logos",
        ku.plugin_url(action="clean", kind="thumbnails"),
        art=_art("DefaultPicture.png"),
        is_folder=False,
    )
    ku.add_directory_item(
        f"[B]{ku.get_string(30306) or 'Limpieza completa del addon'}[/B]",
        ku.plugin_url(action="clean", kind="full"),
        art=_art("DefaultAddonPackage.png"),
        info={"plot": ku.get_string(30301) or "Caché, descargas, BD y thumbnails"},
        is_folder=False,
    )
    ku.end_directory()


def run_clean(kind: str) -> None:
    cleaner.confirm_and_run(kind or "full")


def route(params: dict) -> None:
    action = (params.get("action") or "root").lower()
    if action == "root":
        root()
    elif action in ("classic", "list"):
        classic_root()
    elif action == "ui":
        open_ui()
    elif action == "channels":
        group = params.get("group") or None
        if group == "":
            group = None
        query = params.get("q") or None
        special = params.get("special") or None
        page = int(params.get("page") or 0)
        list_channels(group=group, query=query, page=page, special=special)
    elif action == "search":
        search()
    elif action == "epg":
        show_epg(int(params.get("id", "0")))
    elif action == "play":
        play(int(params.get("id", "0")))
    elif action == "refresh":
        refresh(silent=params.get("silent", "1") != "0")
    elif action == "browse_m3u":
        browse_m3u()
    elif action == "url_m3u":
        url_m3u()
    elif action == "browse_epg":
        browse_epg()
    elif action == "url_epg":
        url_epg()
    elif action == "clean_menu":
        clean_menu()
    elif action == "clean":
        run_clean(params.get("kind") or "full")
    elif action == "settings":
        open_settings()
    elif action == "check_update":
        from . import updates

        updates.notify_if_update(force=True)
    elif action == "audio_tracks":
        from . import player as zap

        zap.select_audio_stream()
    elif action == "subtitle_tracks":
        from . import player as zap

        zap.select_subtitle_stream()
    elif action == "toggle_favorite":
        try:
            cid = int(params.get("id", "0"))
        except ValueError:
            cid = 0
        if cid:
            added = cache.toggle_favorite(cid)
            ku.notify(
                ku.get_string(30501 if added else 30502)
                or ("Favorito" if added else "Quitado")
            )
        xbmc.executebuiltin("Container.Refresh")
    elif action == "toggle_locked":
        from . import parental

        try:
            cid = int(params.get("id", "0"))
        except ValueError:
            cid = 0
        if cid:
            result = parental.toggle_channel_lock(cid)
            if result is True:
                ku.notify(ku.get_string(30608) or "Canal bloqueado")
            elif result is False:
                ku.notify(ku.get_string(30609) or "Canal desbloqueado")
        xbmc.executebuiltin("Container.Refresh")
    elif action == "set_pin":
        from . import parental

        parental.prompt_set_pin(force=False)
    elif action == "clear_locks":
        from . import parental

        parental.clear_all_locks()
    else:
        root()
