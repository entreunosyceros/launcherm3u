# -*- coding: utf-8 -*-
"""Ventana principal estilo IPTV (grupos + canales + EPG)."""

from __future__ import annotations

import time
import threading

import xbmc
import xbmcgui

from . import cache
from . import kodi_utils as ku
from . import loader


# Controles XML
CTRL_GROUPS = 100
CTRL_CHANNELS = 200
CTRL_NOW_TITLE = 300
CTRL_NOW_TIME = 301
CTRL_NOW_PLOT = 302
CTRL_NEXT_TITLE = 303
CTRL_GROUP_TITLE = 310
CTRL_CHANNEL_TITLE = 311
CTRL_STATUS = 320
CTRL_LOGO = 330
CTRL_PLAY = 400
CTRL_RELOAD = 401
CTRL_SETTINGS = 402
CTRL_SEARCH = 403
CTRL_BROWSE = 404
CTRL_CLOSE = 405
CTRL_URL = 406

GLOBAL_WINDOW_ID = 10000
PROP_UI_RUNNING = "LauncherM3U.UIRunning"
PROP_SUPPRESS_OPEN = "LauncherM3U.SuppressAutoOpen"

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_SELECT = 7
ACTION_MOUSE_DOUBLE_CLICK = 103
ACTION_MOUSE_MOVE = 107
ACTION_CONTEXT_MENU = 117
ACTION_SHOW_INFO = 11

_TOOLBAR = {
    CTRL_SEARCH,
    CTRL_RELOAD,
    CTRL_BROWSE,
    CTRL_URL,
    CTRL_SETTINGS,
    CTRL_CLOSE,
    CTRL_PLAY,
}


class MainWindow(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self._group = None  # None = todos
        self._special = None  # favorites | recents | None
        self._query = None
        self._selected_id = None
        self._ready = False
        self._preview_id = None
        self._preview_mode = False
        self._closing = False
        self._ctrl_guard = {}
        self._channel_guard_at = 0.0
        self._page_size = max(25, min(500, ku.get_setting_int("page_size", 100)))
        self._offset = 0
        self._total_channels = 0
        self._loading_page = False
        self._selected_position = 0
        self._last_epg_id = 0
        self._last_epg_at = 0.0
        self._reload_thread = None
        self._reload_result = None
        self._update_checked = False

    def onInit(self):
        """
        Kodi vuelve a llamar onInit al regresar del reproductor y vacía los
        controles list. Hay que repoblar siempre si están vacíos.
        """
        first_run = not self._ready
        self._ready = True
        try:
            if first_run:
                for cid, sid, fallback in (
                    (CTRL_PLAY, 30402, "Pantalla completa"),
                ):
                    try:
                        self.getControl(cid).setLabel(ku.get_string(sid) or fallback)
                    except Exception:
                        pass

                cache.init_db()
                if cache.count_channels() == 0:
                    try:
                        loader.ensure_data(force=False, show_progress=False)
                    except Exception as exc:
                        ku.notify_error(str(exc))

            needs_reload = first_run
            try:
                needs_reload = needs_reload or self.getControl(CTRL_GROUPS).size() == 0
            except Exception:
                needs_reload = True

            if needs_reload:
                self._preview_id = None
                self._preview_mode = False
                self._set_status()
                self._load_groups()
                pages = max(1, self._selected_position // self._page_size + 1)
                self._load_channels(initial_pages=pages)
                self._restore_group_selection()
                try:
                    self.setFocusId(CTRL_CHANNELS)
                except Exception:
                    pass
                item = self.getControl(CTRL_CHANNELS).getSelectedItem()
                if item:
                    self._update_epg_from_listitem(item)
                    if ku.get_setting_bool("auto_preview", False):
                        self._preview_selected()
                if first_run:
                    self._maybe_auto_refresh()
                    self._maybe_check_updates()
        except Exception as exc:
            ku.log(f"UI init error: {exc}", level=3)
            ku.notify_error(str(exc))

    def _restore_group_selection(self):
        """Resalta el grupo activo tras recargar la lista."""
        try:
            ctrl = self.getControl(CTRL_GROUPS)
            target_group = self._group or ""
            target_special = self._special or ""
            for idx in range(ctrl.size()):
                item = ctrl.getListItem(idx)
                if (item.getProperty("special") or "") != target_special:
                    continue
                if (item.getProperty("group") or "") == target_group:
                    ctrl.selectItem(idx)
                    return
            if ctrl.size() > 0:
                ctrl.selectItem(0)
        except Exception:
            pass

    def _update_channel_status(self):
        loaded = min(self._offset, self._total_channels)
        try:
            if self._special == "favorites":
                label = f"{ku.get_string(30500) or 'Favoritos'}: {self._total_channels}"
            elif self._special == "recents":
                label = f"{ku.get_string(30503) or 'Recientes'}: {self._total_channels}"
            elif self._group:
                label = f"{self._group}: {self._total_channels} canales"
            else:
                label = (
                    f"{ku.get_string(30202) or 'Todos'}: "
                    f"{self._total_channels} canales"
                )
            if loaded < self._total_channels:
                label += f" · {loaded} cargados"
            self.getControl(CTRL_STATUS).setLabel(label)
        except Exception:
            pass

    def _on_group_click(self):
        ctrl = self.getControl(CTRL_GROUPS)
        item = ctrl.getSelectedItem()
        if not item:
            return
        special = item.getProperty("special") or ""
        group = item.getProperty("group") or None
        self._special = special or None
        self._group = None if self._special else (group if group else None)
        self._query = None
        self._preview_id = None
        self._selected_position = 0
        self._load_channels()
        self.setFocusId(CTRL_CHANNELS)
        ch_item = self.getControl(CTRL_CHANNELS).getSelectedItem()
        if ch_item:
            self._update_epg_from_listitem(ch_item)

    def _do_search(self):
        keyboard = xbmc.Keyboard(self._query or "", ku.get_string(30204) or "Buscar")
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return
        query = keyboard.getText().strip()
        self._query = query or None
        self._group = None
        self._special = None
        self._preview_id = None
        self._selected_position = 0
        self._load_channels()

    def _channel_context_menu(self):
        channel_id = self._selected_channel_id()
        labels = []
        actions = []
        if channel_id:
            if cache.is_favorite(channel_id):
                labels.append(ku.get_string(30502) or "Quitar de favoritos")
            else:
                labels.append(ku.get_string(30501) or "Añadir a favoritos")
            actions.append("fav")
            if cache.is_locked(channel_id):
                labels.append(ku.get_string(30607) or "Desbloquear canal")
            else:
                labels.append(ku.get_string(30606) or "Bloquear canal con PIN")
            actions.append("lock")
        labels.append(ku.get_string(30510) or "Pista de audio")
        actions.append("audio")
        labels.append(ku.get_string(30511) or "Subtítulos")
        actions.append("subs")
        labels.append(ku.get_string(30543) or "Buscar actualizaciones")
        actions.append("update")
        choice = xbmcgui.Dialog().select(
            ku.get_string(30504) or "Opciones", labels
        )
        if choice < 0:
            return
        action = actions[choice]
        if action == "fav" and channel_id:
            added = cache.toggle_favorite(channel_id)
            ku.notify(
                ku.get_string(30501 if added else 30502)
                or ("Favorito" if added else "Quitado")
            )
            # Refrescar grupos (contadores) y lista si estamos en favoritos
            pos = self._selected_position
            self._load_groups()
            self._restore_group_selection()
            self._selected_position = pos
            self._load_channels(
                initial_pages=max(1, pos // self._page_size + 1)
            )
        elif action == "lock" and channel_id:
            from . import parental

            result = parental.toggle_channel_lock(channel_id)
            if result is True:
                ku.notify(ku.get_string(30608) or "Canal bloqueado")
            elif result is False:
                ku.notify(ku.get_string(30609) or "Canal desbloqueado")
            pos = self._selected_position
            self._selected_position = pos
            self._load_channels(
                initial_pages=max(1, pos // self._page_size + 1)
            )
        elif action == "audio":
            from . import player as zap

            zap.select_audio_stream()
        elif action == "subs":
            from . import player as zap

            zap.select_subtitle_stream()
        elif action == "update":
            from . import updates

            updates.notify_if_update(force=True)

    def _set_status(self):
        total = cache.count_channels()
        groups = len(cache.list_groups())
        label = f"{total} canales · {groups} grupos"
        try:
            self.getControl(CTRL_STATUS).setLabel(label)
        except Exception:
            pass

    def _maybe_auto_refresh(self):
        if not loader.maybe_scheduled_refresh_due():
            # Poda EPG ligera en apertura
            keep = ku.get_setting_int("epg_keep_hours", 72)
            if keep > 0 and ku.get_setting_bool("epg_enabled", False):
                try:
                    cache.prune_old_programmes(keep)
                except Exception:
                    pass
            return
        ku.notify(ku.get_string(30530) or "Recarga automática…")
        self._do_reload()

    def _maybe_check_updates(self):
        if self._update_checked:
            return
        self._update_checked = True
        if not ku.get_setting_bool("update_check_enabled", True):
            return

        def worker():
            try:
                from . import updates

                updates.notify_if_update(force=False)
            except Exception as exc:
                ku.log(f"update check: {exc}", level=2)

        threading.Thread(
            target=worker, name="LauncherM3U-UpdateCheck", daemon=True
        ).start()

    def _load_groups(self):
        ctrl = self.getControl(CTRL_GROUPS)
        ctrl.reset()
        total = cache.count_channels()
        all_item = xbmcgui.ListItem(label=f"{ku.get_string(30202) or 'Todos'} ({total})")
        all_item.setProperty("group", "")
        all_item.setProperty("special", "")
        ctrl.addItem(all_item)

        fav_count = cache.count_favorites()
        fav_item = xbmcgui.ListItem(
            label=f"{ku.get_string(30500) or 'Favoritos'} ({fav_count})"
        )
        fav_item.setProperty("group", "")
        fav_item.setProperty("special", "favorites")
        ctrl.addItem(fav_item)

        recent_count = cache.count_recents()
        recent_item = xbmcgui.ListItem(
            label=f"{ku.get_string(30503) or 'Recientes'} ({recent_count})"
        )
        recent_item.setProperty("group", "")
        recent_item.setProperty("special", "recents")
        ctrl.addItem(recent_item)

        for group in cache.list_groups():
            item = xbmcgui.ListItem(label=f"{group['name']} ({group['channel_count']})")
            item.setProperty("group", group["name"])
            item.setProperty("special", "")
            ctrl.addItem(item)

    def _load_channels(self, initial_pages: int = 1):
        ctrl = self.getControl(CTRL_CHANNELS)
        ctrl.reset()
        self._offset = 0
        if self._special == "favorites":
            self._total_channels = cache.count_favorites()
        elif self._special == "recents":
            self._total_channels = cache.count_recents()
        else:
            self._total_channels = cache.count_channels(self._group, self._query)
        self._loading_page = False

        if self._query:
            title = f"{ku.get_string(30204) or 'Buscar'}: {self._query}"
        elif self._special == "favorites":
            title = ku.get_string(30500) or "Favoritos"
        elif self._special == "recents":
            title = ku.get_string(30503) or "Recientes"
        elif self._group:
            title = self._group
        else:
            title = ku.get_string(30202) or "Todos los canales"
        try:
            self.getControl(CTRL_GROUP_TITLE).setLabel(title)
        except Exception:
            pass

        for _ in range(max(1, initial_pages)):
            if self._offset >= self._total_channels:
                break
            self._append_channel_page()

        if ctrl.size() > 0:
            position = min(self._selected_position, ctrl.size() - 1)
            ctrl.selectItem(position)
            item = ctrl.getSelectedItem()
            if item:
                self._update_epg_from_listitem(item, force=True)
        else:
            self._clear_epg()
        self._update_channel_status()

    def _append_channel_page(self):
        if self._loading_page or self._offset >= self._total_channels:
            return
        self._loading_page = True
        started = time.monotonic()
        if self._special == "favorites":
            rows = cache.list_favorites(offset=self._offset, limit=self._page_size)
        elif self._special == "recents":
            rows = cache.list_recents(offset=self._offset, limit=self._page_size)
        else:
            rows = cache.list_channels(
                group_name=self._group,
                query=self._query,
                offset=self._offset,
                limit=self._page_size,
            )
        show_epg = ku.get_setting_bool("epg_enabled", False) and ku.get_setting_bool(
            "show_epg_in_list", True
        )
        now_map = {}
        if show_epg:
            now_map = cache.now_playing_for_channels(rows)

        items = []
        show_logos = ku.get_setting_bool("show_channel_logos", True)
        for ch in rows:
            chno = ch["tvg_chno"]
            name = f"{chno}. {ch['name']}" if chno else ch["name"]
            if cache.is_locked_url(ch["url"] or ""):
                name = f"{name}  ({ku.get_string(30604) or 'PIN'})"
            now = now_map.get(int(ch["id"]))
            label2 = ""
            if now:
                label2 = (
                    f"{loader.format_time(now['start_ts'])}-"
                    f"{loader.format_time(now['stop_ts'])}  {now['title']}"
                )
            elif self._group and ch["group_name"]:
                label2 = ch["group_name"]

            item = xbmcgui.ListItem(label=name, label2=label2)
            logo = (ch["tvg_logo"] or "DefaultTVShows.png") if show_logos else ""
            if logo:
                item.setArt({"icon": logo, "thumb": logo})
            epg_id = cache.resolve_epg_channel_id(
                ch["tvg_id"], ch["tvg_name"], ch["name"]
            )
            item.setProperty("channel_id", str(ch["id"]))
            item.setProperty("tvg_id", ch["tvg_id"] or "")
            item.setProperty("epg_id", epg_id or "")
            item.setProperty("tvg_name", ch["tvg_name"] or "")
            item.setProperty("channel_name", ch["name"] or "")
            item.setProperty("stream", ch["url"] or "")
            item.setProperty("logo", logo)
            items.append(item)

        self.getControl(CTRL_CHANNELS).addItems(items)
        self._offset += len(rows)
        self._loading_page = False
        ku.log(
            "ui_page offset={0} loaded={1} total={2} ms={3}".format(
                self._offset,
                len(rows),
                self._total_channels,
                int((time.monotonic() - started) * 1000),
            )
        )

    def _maybe_load_more(self):
        ctrl = self.getControl(CTRL_CHANNELS)
        try:
            position = ctrl.getSelectedPosition()
        except Exception:
            return
        self._selected_position = max(0, position)
        if position >= ctrl.size() - 12 and self._offset < self._total_channels:
            self._append_channel_page()
            self._update_channel_status()

    def _clear_epg(self):
        for cid, text in (
            (CTRL_CHANNEL_TITLE, ""),
            (CTRL_NOW_TITLE, "-"),
            (CTRL_NOW_TIME, ""),
            (CTRL_NEXT_TITLE, "-"),
        ):
            try:
                self.getControl(cid).setLabel(text)
            except Exception:
                pass
        try:
            self.getControl(CTRL_NOW_PLOT).setText("")
        except Exception:
            pass

    def _update_epg_from_listitem(self, listitem: xbmcgui.ListItem, force: bool = False):
        name = listitem.getLabel()
        logo = (
            listitem.getProperty("logo")
            if ku.get_setting_bool("show_channel_logos", True)
            else ""
        )
        try:
            channel_id = int(listitem.getProperty("channel_id") or 0)
        except ValueError:
            channel_id = 0
        self._selected_id = channel_id or None
        now = time.monotonic()
        if not force and channel_id == self._last_epg_id and now - self._last_epg_at < 0.25:
            return
        if not force and now - self._last_epg_at < 0.10:
            return
        self._last_epg_id = channel_id
        self._last_epg_at = now

        try:
            self.getControl(CTRL_CHANNEL_TITLE).setLabel(name)
        except Exception:
            pass
        try:
            self.getControl(CTRL_LOGO).setImage(logo or "")
        except Exception:
            pass

        if not ku.get_setting_bool("epg_enabled", False):
            try:
                self.getControl(CTRL_NOW_TITLE).setLabel("-")
                self.getControl(CTRL_NOW_TIME).setLabel("")
                self.getControl(CTRL_NOW_PLOT).setText("")
                self.getControl(CTRL_NEXT_TITLE).setLabel("-")
            except Exception:
                pass
            return

        tvg_id = listitem.getProperty("tvg_id")
        tvg_name = listitem.getProperty("tvg_name")
        channel_name = listitem.getProperty("channel_name") or name
        epg_id = listitem.getProperty("epg_id")
        # Preferir fila de BD: propiedades del ListItem a veces se pierden en skins
        if channel_id:
            ch = cache.get_channel(channel_id)
            if ch:
                tvg_id = ch["tvg_id"] or tvg_id
                tvg_name = ch["tvg_name"] or tvg_name
                channel_name = ch["name"] or channel_name
                epg_id = cache.resolve_epg_channel_id(tvg_id, tvg_name, channel_name)

        now_row, next_row = cache.get_now_and_next(
            epg_id or tvg_id, tvg_name=tvg_name, name=channel_name
        )
        if now_row:
            try:
                self.getControl(CTRL_NOW_TITLE).setLabel(now_row["title"] or "-")
                self.getControl(CTRL_NOW_TIME).setLabel(
                    f"{loader.format_time(now_row['start_ts'])} - {loader.format_time(now_row['stop_ts'])}"
                )
                self.getControl(CTRL_NOW_PLOT).setText(now_row["description"] or "")
            except Exception:
                pass
        else:
            try:
                self.getControl(CTRL_NOW_TITLE).setLabel(
                    ku.get_string(30213) or "Sin datos EPG"
                )
                self.getControl(CTRL_NOW_TIME).setLabel("")
                self.getControl(CTRL_NOW_PLOT).setText("")
            except Exception:
                pass

        if next_row:
            try:
                self.getControl(CTRL_NEXT_TITLE).setLabel(
                    f"{loader.format_time(next_row['start_ts'])}  {next_row['title'] or '-'}"
                )
            except Exception:
                pass
        else:
            try:
                self.getControl(CTRL_NEXT_TITLE).setLabel("-")
            except Exception:
                pass

    def _selected_channel_id(self) -> int:
        item = self.getControl(CTRL_CHANNELS).getSelectedItem()
        if not item:
            return 0
        try:
            return int(item.getProperty("channel_id") or 0)
        except ValueError:
            return 0

    def _set_preview_chrome(self, playing: bool) -> None:
        """Oculta el logo encima del vídeo mientras hay preview."""
        try:
            self.getControl(CTRL_LOGO).setVisible(not playing)
        except Exception:
            pass

    def _preview_selected(self) -> None:
        """Vista previa embebida (videowindow)."""
        item = self.getControl(CTRL_CHANNELS).getSelectedItem()
        if not item:
            return
        self._update_epg_from_listitem(item)
        try:
            channel_id = int(item.getProperty("channel_id") or 0)
        except ValueError:
            channel_id = 0
        if not channel_id:
            stream = item.getProperty("stream")
            if stream:
                from . import player as zap

                zap.stop_playback()
                self._set_preview_chrome(True)
                self._preview_mode = True
                li = xbmcgui.ListItem(path=stream)
                xbmc.Player().play(stream, li, True)
            return
        if channel_id == self._preview_id and self._preview_mode and xbmc.Player().isPlaying():
            return
        from . import player as zap

        self._set_preview_chrome(True)
        if zap.preview_channel(channel_id):
            self._preview_id = channel_id
            self._preview_mode = True
        else:
            self._set_preview_chrome(False)
            self._preview_mode = False

    def _play_selected(self) -> None:
        """Pantalla completa del canal seleccionado (o el de la vista previa)."""
        try:
            self._selected_position = self.getControl(CTRL_CHANNELS).getSelectedPosition()
        except Exception:
            pass
        channel_id = (
            self._preview_id
            if self._preview_mode and self._preview_id
            else (self._selected_channel_id() or self._selected_id)
        )
        if not channel_id:
            item = self.getControl(CTRL_CHANNELS).getSelectedItem()
            stream = item.getProperty("stream") if item else ""
            if not stream:
                ku.notify(ku.get_string(30212) or "Canal no encontrado")
                return
            self._preview_mode = False
            self._set_preview_chrome(False)
            xbmc.Player().play(stream, xbmcgui.ListItem(path=stream), False)
            return

        from . import player as zap

        self._preview_mode = False
        self._preview_id = int(channel_id)
        self._selected_id = int(channel_id)
        self._set_preview_chrome(False)
        zap.play_channel(int(channel_id), notify_zap=False, windowed=False)

    def _activate_channel(self, fullscreen: bool = False) -> None:
        """
        Un clic / OK → vista previa.
        Doble clic (o ACTION_MOUSE_DOUBLE_CLICK) / Pantalla completa → fullscreen.
        """
        if fullscreen:
            self._play_selected()
            return
        now = time.monotonic()
        if now - self._channel_guard_at < 0.20:
            return
        self._channel_guard_at = now
        self._preview_selected()

    def _run_control(self, control_id: int) -> bool:
        """Ejecuta la acción del control. True si se gestionó."""
        now = time.monotonic()
        if control_id in _TOOLBAR or control_id == CTRL_GROUPS:
            last = self._ctrl_guard.get(control_id, 0.0)
            if now - last < 0.25:
                return True
            self._ctrl_guard[control_id] = now

        if control_id == CTRL_GROUPS:
            self._on_group_click()
            return True
        if control_id == CTRL_CHANNELS:
            self._activate_channel(fullscreen=False)
            return True
        if control_id == CTRL_PLAY:
            self._play_selected()
            return True
        if control_id == CTRL_RELOAD:
            self._do_reload()
            return True
        if control_id == CTRL_SETTINGS:
            old_palette = ku.get_setting_int("ui_palette", 0)
            old_logos = ku.get_setting_bool("show_channel_logos", True)
            old_epg = ku.get_setting_bool("epg_enabled", False)
            old_epg_key = loader.epg_source_key()
            old_show_epg = ku.get_setting_bool("show_epg_in_list", True)
            ku.ADDON.openSettings()
            self._page_size = max(
                25, min(500, ku.get_setting_int("page_size", 100))
            )
            if ku.get_setting_int("ui_palette", 0) != old_palette:
                ku.notify("Cierra y vuelve a abrir para aplicar la nueva paleta")
            logos_changed = (
                ku.get_setting_bool("show_channel_logos", True) != old_logos
            )
            show_epg_changed = (
                ku.get_setting_bool("show_epg_in_list", True) != old_show_epg
            )
            epg_enabled = ku.get_setting_bool("epg_enabled", False)
            if epg_enabled:
                remote = ku.get_setting_int("epg_type", 0) == 1
                path = (ku.get_setting("epg_path") or "").strip()
                url = (ku.get_setting("epg_url") or "").strip()
                if remote and not url:
                    self._do_epg_url()
                elif not remote and not path:
                    self._do_epg_browse()
                elif (
                    not old_epg
                    or loader.epg_source_key() != old_epg_key
                ):
                    self._do_epg_reload()
                elif show_epg_changed or logos_changed:
                    self._refresh_channel_page()
            elif old_epg or show_epg_changed or logos_changed:
                self._refresh_channel_page()
                if not epg_enabled:
                    self._clear_epg()
            return True
        if control_id == CTRL_SEARCH:
            self._do_search()
            return True
        if control_id == CTRL_BROWSE:
            self._do_browse()
            return True
        if control_id == CTRL_URL:
            self._do_url()
            return True
        if control_id == CTRL_CLOSE:
            self.close()
            return True
        return False

    def _refresh_channel_page(self):
        try:
            self._selected_position = self.getControl(
                CTRL_CHANNELS
            ).getSelectedPosition()
        except Exception:
            pass
        self._load_channels(
            initial_pages=max(1, self._selected_position // self._page_size + 1)
        )
        try:
            item = self.getControl(CTRL_CHANNELS).getSelectedItem()
            if item:
                self._update_epg_from_listitem(item, force=True)
        except Exception:
            pass

    def _do_reload(
        self,
        m3u_path=None,
        m3u_url=None,
        m3u_remote=None,
        epg_path=None,
        epg_url=None,
        epg_remote=None,
    ):
        """Inicia recarga en segundo plano para no congelar la ventana."""
        if self._reload_thread and self._reload_thread.is_alive():
            ku.notify(ku.get_string(30100) or "La lista ya se está cargando")
            return

        self._reload_result = None
        self.getControl(CTRL_STATUS).setLabel(
            ku.get_string(30100) or "Cargando lista M3U..."
        )

        def worker():
            started = time.monotonic()
            try:
                total = loader.load_playlist(
                    force=True,
                    show_progress=False,
                    manage_busy=False,
                    m3u_path=m3u_path,
                    m3u_url=m3u_url,
                    m3u_remote=m3u_remote,
                )
                progs = None
                if ku.get_setting_bool("epg_enabled", False):
                    progs = loader.load_epg(
                        force=True,
                        show_progress=False,
                        manage_busy=False,
                        epg_path=epg_path,
                        epg_url=epg_url,
                        epg_remote=epg_remote,
                    )
                self._reload_result = (
                    True,
                    total,
                    progs,
                    int((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                import traceback

                ku.log(
                    f"Recarga en segundo plano: {exc}\n{traceback.format_exc()}",
                    level=3,
                )
                self._reload_result = (False, str(exc), None, 0)

        self._reload_thread = threading.Thread(
            target=worker, name="LauncherM3U-Reload", daemon=True
        )
        self._reload_thread.start()

    def _do_epg_reload(self, epg_path=None, epg_url=None, epg_remote=None):
        if self._reload_thread and self._reload_thread.is_alive():
            ku.notify(ku.get_string(30110) or "Cargando EPG...")
            return

        self._reload_result = None
        self.getControl(CTRL_STATUS).setLabel(
            ku.get_string(30110) or "Cargando EPG..."
        )

        def worker():
            started = time.monotonic()
            try:
                progs = loader.load_epg(
                    force=True,
                    show_progress=False,
                    manage_busy=False,
                    epg_path=epg_path,
                    epg_url=epg_url,
                    epg_remote=epg_remote,
                )
                self._reload_result = (
                    True,
                    None,
                    progs,
                    int((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                import traceback

                ku.log(
                    f"Recarga EPG en segundo plano: {exc}\n{traceback.format_exc()}",
                    level=3,
                )
                self._reload_result = (False, str(exc), None, 0)

        self._reload_thread = threading.Thread(
            target=worker, name="LauncherM3U-EPG", daemon=True
        )
        self._reload_thread.start()

    def _check_reload(self):
        result = self._reload_result
        if not result or (self._reload_thread and self._reload_thread.is_alive()):
            return
        self._reload_result = None
        ok, value, progs, elapsed = result
        if not ok:
            ku.notify_error(value)
            self._update_channel_status()
            return
        try:
            if value is not None:
                self._selected_position = 0
                self._load_groups()
                self._load_channels()
                msg = (ku.get_string(30214) or "Lista recargada: {0} canales").format(
                    value
                )
                if progs is not None:
                    try:
                        linked, total_ch = cache.count_epg_links()
                        msg += f" / EPG: {progs} ({linked}/{total_ch} enlazados)"
                    except Exception:
                        msg += f" / EPG: {progs}"
            else:
                self._refresh_channel_page()
                try:
                    linked, total_ch = cache.count_epg_links()
                    msg = (
                        f"EPG: {progs if progs is not None else 0} "
                        f"({linked}/{total_ch} enlazados)"
                    )
                except Exception:
                    msg = f"EPG: {progs if progs is not None else 0}"
            ku.log(f"reload_complete ms={elapsed}")
            ku.notify(msg)
        except Exception as exc:
            ku.log(f"reload UI update error: {exc}", level=3)
            ku.notify_error(str(exc))
            self._update_channel_status()

    def _do_browse(self):
        heading = ku.get_string(30220) or "Seleccionar archivo M3U local"
        path = xbmcgui.Dialog().browse(1, heading, "files", ".m3u|.m3u8|.txt", False, False, "")
        if not path:
            return
        ku.set_setting_int("m3u_type", 0)
        ku.set_setting("m3u_path", path)
        # Pasar la ruta explícita: setSetting no siempre es legible al instante
        self._do_reload(m3u_path=path, m3u_remote=False)

    def _do_url(self):
        current = ku.get_setting("m3u_url")
        keyboard = xbmc.Keyboard(current, ku.get_string(30015) or "URL del archivo M3U")
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return
        url = (keyboard.getText() or "").strip().replace("\r", "").replace("\n", "")
        from . import downloader

        url = downloader.normalize_http_url(url)
        if not url:
            ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
            return
        ku.set_setting_int("m3u_type", 1)
        ku.set_setting("m3u_url", url)
        ku.notify(ku.get_string(30221) or "Lista configurada")
        # Fuente explícita para el hilo: evita cargar la URL antigua de ajustes
        self._do_reload(m3u_url=url, m3u_remote=True)

    def _do_epg_browse(self):
        heading = ku.get_string(30060) or "Seleccionar archivo XMLTV local"
        path = xbmcgui.Dialog().browse(
            1, heading, "files", "", False, False, ""
        )
        if not path:
            return
        ku.set_setting_bool("epg_enabled", True)
        ku.set_setting_int("epg_type", 0)
        ku.set_setting("epg_path", path)
        self._do_epg_reload(epg_path=path, epg_remote=False)

    def _do_epg_url(self):
        current = ku.get_setting("epg_url")
        keyboard = xbmc.Keyboard(
            current, ku.get_string(30061) or "URL del archivo XMLTV"
        )
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return
        url = (keyboard.getText() or "").strip().replace("\r", "").replace("\n", "")
        from . import downloader

        url = downloader.normalize_http_url(url)
        if not url:
            ku.notify(ku.get_string(30222) or "No se seleccionó ningún archivo")
            return
        ku.set_setting_bool("epg_enabled", True)
        ku.set_setting_int("epg_type", 1)
        ku.set_setting("epg_url", url)
        self._do_epg_reload(epg_url=url, epg_remote=True)

    def close(self):
        if not self._closing:
            self._closing = True
            try:
                xbmcgui.Window(GLOBAL_WINDOW_ID).setProperty(
                    PROP_SUPPRESS_OPEN, str(time.time())
                )
            except Exception:
                pass
            try:
                from . import player as zap

                if self._preview_mode:
                    zap.stop_playback()
            except Exception:
                pass
        super().close()

    def onClick(self, control_id):
        self._check_reload()
        self._run_control(control_id)

    def onAction(self, action):
        self._check_reload()
        aid = action.getId()
        if aid in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()
            return

        focus = self.getFocusId()

        # Solo actualizar ficha al pasar el ratón; no cargar stream
        if aid == ACTION_MOUSE_MOVE:
            if focus == CTRL_CHANNELS:
                self._maybe_load_more()
                item = self.getControl(CTRL_CHANNELS).getSelectedItem()
                if item:
                    self._update_epg_from_listitem(item)
            return

        # Doble clic de ratón → pantalla completa
        if aid == ACTION_MOUSE_DOUBLE_CLICK:
            if focus == CTRL_CHANNELS:
                self._activate_channel(fullscreen=True)
            elif focus in _TOOLBAR:
                self._run_control(focus)
            return

        # Menú contextual / Info → favoritos, pistas, updates
        if aid in (ACTION_CONTEXT_MENU, ACTION_SHOW_INFO):
            self._channel_context_menu()
            return

        # Kodi convierte OK/Enter sobre controles en onClick(). No ejecutar aquí:
        # los diálogos modales (URL, Archivo, Buscar, Ajustes) se abrirían dos veces.
        if aid == ACTION_SELECT:
            return

        # Navegación con flechas: solo ficha EPG
        if focus == CTRL_CHANNELS:
            self._maybe_load_more()
            item = self.getControl(CTRL_CHANNELS).getSelectedItem()
            if item:
                self._update_epg_from_listitem(item)

    def onFocus(self, control_id):
        self._check_reload()
        tips = {
            CTRL_SEARCH: ku.get_string(30204) or "Buscar",
            CTRL_RELOAD: ku.get_string(30201) or "Recargar",
            CTRL_BROWSE: ku.get_string(30012) or "Archivo",
            CTRL_URL: ku.get_string(30013) or "URL",
            CTRL_SETTINGS: ku.get_string(30200) or "Ajustes",
            CTRL_CLOSE: ku.get_string(30403) or "Cerrar",
            CTRL_PLAY: ku.get_string(30402) or "Pantalla completa",
        }
        if control_id in tips:
            try:
                self.getControl(CTRL_STATUS).setLabel(tips[control_id])
            except Exception:
                pass
        if control_id == CTRL_CHANNELS:
            self._maybe_load_more()
            item = self.getControl(CTRL_CHANNELS).getSelectedItem()
            if item:
                self._update_epg_from_listitem(item)


def open_main() -> None:
    from .theme import prepare_skin

    xml = "launcherm3u-main.xml"
    path = prepare_skin()
    global_window = xbmcgui.Window(GLOBAL_WINDOW_ID)
    global_window.setProperty(PROP_UI_RUNNING, "1")
    try:
        window = MainWindow(xml, path, "Default", "1080i")
        window.doModal()
        del window
    finally:
        global_window.clearProperty(PROP_UI_RUNNING)
