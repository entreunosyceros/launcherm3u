# -*- coding: utf-8 -*-
"""Carga orquestada de playlist y EPG (sin bloquear la UI)."""

from __future__ import annotations

import time

import xbmc
import xbmcgui

from . import cache
from . import downloader
from . import epg_parser
from . import kodi_utils as ku
from . import m3u_parser

_MONITOR = xbmc.Monitor()


def _m3u_is_remote() -> bool:
    return ku.get_setting_int("m3u_type", 0) == 1


def _epg_is_remote() -> bool:
    return ku.get_setting_int("epg_type", 0) == 1


def playlist_source_key() -> str:
    if _m3u_is_remote():
        return f"url:{ku.get_setting('m3u_url')}"
    return f"path:{ku.get_setting('m3u_path')}"


def epg_source_key() -> str:
    if _epg_is_remote():
        return f"url:{ku.get_setting('epg_url')}"
    return f"path:{ku.get_setting('epg_path')}"


def needs_playlist_refresh(force: bool = False) -> bool:
    if force:
        return True
    if cache.count_channels() == 0:
        return True
    meta = cache.get_metas("playlist_source", "playlist_loaded_at")
    loaded = meta.get("playlist_source")
    if loaded != playlist_source_key():
        return True
    try:
        loaded_at = int(meta.get("playlist_loaded_at", "0") or 0)
    except ValueError:
        return True
    max_age = ku.get_setting_int("cache_hours", 12) * 3600
    return (time.time() - loaded_at) > max_age


def needs_epg_refresh(force: bool = False) -> bool:
    if not ku.get_setting_bool("epg_enabled", False):
        return False
    if force:
        return True
    meta = cache.get_metas("programme_count", "epg_source", "epg_loaded_at")
    if meta.get("programme_count") in (None, "0"):
        return True
    if meta.get("epg_source") != epg_source_key():
        return True
    try:
        loaded_at = int(meta.get("epg_loaded_at", "0") or 0)
    except ValueError:
        return True
    max_age = ku.get_setting_int("cache_hours", 12) * 3600
    return (time.time() - loaded_at) > max_age


def _abort_requested() -> bool:
    monitor = globals().get("_MONITOR")
    if monitor is None:
        return False
    try:
        checker = getattr(monitor, "abortRequested", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def _busy(on: bool) -> None:
    if on:
        xbmc.executebuiltin("ActivateWindow(busydialognocancel)")
    else:
        xbmc.executebuiltin("Dialog.Close(busydialognocancel)")


def load_playlist(
    force: bool = False,
    show_progress: bool = False,
    manage_busy: bool = True,
    m3u_path: str | None = None,
    m3u_url: str | None = None,
    m3u_remote: bool | None = None,
) -> int:
    """
    Carga la playlist.
    Los parámetros m3u_* permiten forzar la fuente (evita leer ajustes
    obsoletos justo después de setSetting desde un hilo en segundo plano).
    """
    started = time.monotonic()
    cache.init_db()

    use_remote = _m3u_is_remote() if m3u_remote is None else bool(m3u_remote)
    path_setting = ku.get_setting("m3u_path") if m3u_path is None else m3u_path
    url_setting = ku.get_setting("m3u_url") if m3u_url is None else m3u_url
    source_key = f"url:{url_setting}" if use_remote else f"path:{path_setting}"
    has_override = m3u_path is not None or m3u_url is not None or m3u_remote is not None

    if not force and not has_override and not needs_playlist_refresh(False):
        return cache.count_channels()
    force = True if has_override else force

    progress = None
    busy_on = False
    if show_progress:
        progress = xbmcgui.DialogProgress()
        progress.create(ku.ADDON_NAME, ku.get_string(30100) or "Cargando lista M3U...")
    elif manage_busy:
        _busy(True)
        busy_on = True

    try:
        if progress:
            progress.update(10, ku.get_string(30100) or "Cargando lista M3U...")

        path = downloader.resolve_source(
            "m3u",
            use_remote,
            path_setting,
            url_setting,
            ku.get_setting_int("cache_hours", 12),
            force=force,
        )
        if not path:
            raise ValueError(ku.get_string(30101) or "Configura la lista M3U en ajustes.")

        if progress:
            progress.update(30, ku.get_string(30102) or "Analizando canales...")
            if progress.iscanceled():
                return cache.count_channels()
        elif _abort_requested():
            return cache.count_channels()

        if progress:
            progress.update(50, ku.get_string(30103) or "Guardando en caché...")

        # yield_ui solo en hilo de UI: crear xbmc.Monitor/sleep en workers
        # de Android provoca errores tipo "NoneType object is not callable".
        total = cache.replace_playlist(
            m3u_parser.iter_channels_from_file(path),
            batch_size=2500,
            yield_ui=bool(show_progress or manage_busy),
        )
        if total <= 0:
            raise ValueError(
                ku.get_string(30102)
                or "La lista no contiene canales válidos"
            )
        cache.set_meta("playlist_source", source_key)
        cache.set_meta("playlist_loaded_at", str(int(time.time())))
        _maybe_apply_url_tvg(path)
        ku.log(
            f"load_playlist channels={total} ms={int((time.monotonic() - started) * 1000)}"
        )
        if progress:
            progress.update(100, f"{total} canales")
        return total
    except FileNotFoundError as exc:
        raise ValueError(
            (ku.get_string(30223) or "Archivo local no encontrado o ilegible: {0}").format(exc)
        ) from exc
    except IOError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if progress:
            progress.close()
        elif busy_on:
            _busy(False)


def load_epg(
    force: bool = False,
    show_progress: bool = False,
    manage_busy: bool = True,
    epg_path: str | None = None,
    epg_url: str | None = None,
    epg_remote: bool | None = None,
) -> int:
    """
    Carga la guía XMLTV.
    Los parámetros epg_* permiten forzar la fuente (misma razón que m3u_*).
    """
    started = time.monotonic()
    cache.init_db()
    if not ku.get_setting_bool("epg_enabled", False):
        return 0

    use_remote = _epg_is_remote() if epg_remote is None else bool(epg_remote)
    path_setting = ku.get_setting("epg_path") if epg_path is None else epg_path
    url_setting = ku.get_setting("epg_url") if epg_url is None else epg_url
    source_key = f"url:{url_setting}" if use_remote else f"path:{path_setting}"
    has_override = epg_path is not None or epg_url is not None or epg_remote is not None

    if not force and not has_override and not needs_epg_refresh(False):
        try:
            return int(cache.get_meta("programme_count", "0") or 0)
        except ValueError:
            return 0
    force = True if has_override else force

    progress = None
    busy_on = False
    if show_progress:
        progress = xbmcgui.DialogProgress()
        progress.create(ku.ADDON_NAME, ku.get_string(30110) or "Cargando EPG...")
    elif manage_busy:
        _busy(True)
        busy_on = True

    try:
        path = downloader.resolve_source(
            "epg",
            use_remote,
            path_setting,
            url_setting,
            ku.get_setting_int("cache_hours", 12),
            force=force,
        )
        if not path:
            raise ValueError(ku.get_string(30111) or "Configura la guía EPG en ajustes.")

        if progress:
            progress.update(10, ku.get_string(30112) or "Parseando XMLTV...")
        total_programmes = 0
        with cache.connect() as conn:
            # El DELETE queda dentro de la transacción: cancelar conserva el EPG previo.
            conn.execute("DELETE FROM programmes")
            conn.execute("DELETE FROM epg_channels")
            for kind, batch in epg_parser.load_epg_batched(path, batch_size=2000):
                if progress and progress.iscanceled():
                    raise RuntimeError("Carga EPG cancelada")
                if _abort_requested():
                    raise RuntimeError("Carga EPG cancelada")
                if kind == "channels":
                    conn.executemany(
                        "INSERT OR REPLACE INTO epg_channels(id, display_name) VALUES (?, ?)",
                        batch,
                    )
                else:
                    conn.executemany(
                        """
                        INSERT INTO programmes(channel_id, start_ts, stop_ts, title, description)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    total_programmes += len(batch)
                    if progress:
                        pct = min(95, 10 + total_programmes // 200)
                        progress.update(pct, f"{total_programmes} programas")
            values = (
                ("epg_source", source_key),
                ("epg_loaded_at", str(int(time.time()))),
                ("programme_count", str(total_programmes)),
            )
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values,
            )
        cache.invalidate_epg_index()
        keep_hours = ku.get_setting_int("epg_keep_hours", 72)
        if keep_hours > 0:
            pruned = cache.prune_old_programmes(keep_hours)
            if pruned:
                ku.log(f"epg_pruned={pruned} keep_hours={keep_hours}")
                try:
                    total_programmes = int(cache.get_meta("programme_count", "0") or 0)
                except ValueError:
                    pass
        ku.log(
            f"load_epg programmes={total_programmes} "
            f"ms={int((time.monotonic() - started) * 1000)}"
        )
        if progress:
            progress.update(100, f"{total_programmes} programas")
        return total_programmes
    except FileNotFoundError as exc:
        raise ValueError(
            (ku.get_string(30223) or "Archivo local no encontrado o ilegible: {0}").format(exc)
        ) from exc
    except IOError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if progress:
            progress.close()
        elif busy_on:
            _busy(False)


def _maybe_apply_url_tvg(playlist_path: str) -> None:
    """Si el M3U trae url-tvg y la opción está activa, configura el EPG."""
    if not ku.get_setting_bool("auto_url_tvg", True):
        return
    try:
        meta = m3u_parser.peek_playlist_meta(playlist_path)
    except Exception as exc:
        ku.log(f"url-tvg peek: {exc}", level=2)
        return
    url_tvg = downloader.normalize_http_url(meta.get("url_tvg") or "")
    if not url_tvg:
        return
    current = (ku.get_setting("epg_url") or "").strip()
    ku.set_setting_bool("epg_enabled", True)
    ku.set_setting_int("epg_type", 1)
    if current != url_tvg:
        ku.set_setting("epg_url", url_tvg)
        ku.log(f"url-tvg aplicado: {url_tvg}")
        ku.notify(ku.get_string(30520) or "EPG detectado en la lista M3U")


def maybe_scheduled_refresh_due() -> bool:
    """True si toca recarga automática por horario."""
    hours = ku.get_setting_int("auto_refresh_hours", 0)
    if hours <= 0:
        return False
    try:
        loaded = int(cache.get_meta("playlist_loaded_at", "0") or 0)
    except ValueError:
        loaded = 0
    if not loaded:
        return True
    return (time.time() - loaded) >= hours * 3600


def ensure_data(force: bool = False, show_progress: bool = False) -> None:
    busy = False
    if not show_progress:
        _busy(True)
        busy = True
    try:
        load_playlist(force=force, show_progress=show_progress, manage_busy=False)
        if ku.get_setting_bool("epg_enabled", False):
            try:
                load_epg(force=force, show_progress=show_progress, manage_busy=False)
            except Exception as exc:
                ku.log(f"EPG error: {exc}", level=3)
                ku.notify_error(str(exc))
        # Poda ligera aunque no se recargue EPG completo
        keep_hours = ku.get_setting_int("epg_keep_hours", 72)
        if keep_hours > 0 and ku.get_setting_bool("epg_enabled", False):
            try:
                cache.prune_old_programmes(keep_hours)
            except Exception:
                pass
    finally:
        if busy:
            _busy(False)


def format_time(ts: int) -> str:
    try:
        return time.strftime("%H:%M", time.localtime(ts))
    except (OverflowError, ValueError, OSError):
        return "--:--"
