# -*- coding: utf-8 -*-
"""Limpieza de datos del addon (caché, descargas, thumbnails)."""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Optional, Tuple

import xbmc
import xbmcgui
import xbmcvfs

from . import cache
from . import kodi_utils as ku


def _size_of_path(path: str) -> int:
    total = 0
    if not path or not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def format_bytes(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num} B"


def _format_bytes(num: int) -> str:
    return format_bytes(num)


def _delete_path(path: str) -> Tuple[int, int]:
    """Elimina archivo o carpeta. Devuelve (archivos, bytes)."""
    if not path or not os.path.exists(path):
        return 0, 0
    files = 0
    bytes_freed = 0
    if os.path.isfile(path):
        try:
            bytes_freed = os.path.getsize(path)
            os.remove(path)
            return 1, bytes_freed
        except OSError as exc:
            ku.log(f"No se pudo borrar {path}: {exc}", level=3)
            return 0, 0

    for root, dirs, filenames in os.walk(path, topdown=False):
        for name in filenames:
            fp = os.path.join(root, name)
            try:
                bytes_freed += os.path.getsize(fp)
                os.remove(fp)
                files += 1
            except OSError as exc:
                ku.log(f"No se pudo borrar {fp}: {exc}", level=3)
        for name in dirs:
            dp = os.path.join(root, name)
            try:
                os.rmdir(dp)
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass
    return files, bytes_freed


def _vfs_listdir(path: str) -> List[str]:
    try:
        dirs, files = xbmcvfs.listdir(path)
        return [*(dirs or []), *(files or [])]
    except Exception:
        return []


def downloads_dir() -> str:
    return os.path.join(ku.ensure_profile(), "downloads")


def collect_logo_urls() -> List[str]:
    urls: List[str] = []
    try:
        cache.init_db()
        with cache.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT tvg_logo FROM channels WHERE tvg_logo IS NOT NULL AND tvg_logo != ''"
            ).fetchall()
            urls = [r["tvg_logo"] for r in rows if r["tvg_logo"]]
    except Exception as exc:
        ku.log(f"No se pudieron leer logos: {exc}", level=3)
    return urls


def clean_downloads() -> Dict[str, int]:
    path = downloads_dir()
    files, freed = _delete_path(path)
    # Recrear carpeta vacía
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return {"files": files, "bytes": freed}


def clean_database() -> Dict[str, int]:
    """Borra la base SQLite del addon (canales + EPG)."""
    path = cache.db_path()
    # Cerrar posibles handles dejando que GC recoja; forzar wipe lógico primero
    try:
        cache.wipe_all()
    except Exception:
        pass

    files, freed = 0, 0
    for suffix in ("", "-wal", "-shm"):
        candidate = path + suffix if suffix else path
        f, b = _delete_path(candidate)
        files += f
        freed += b

    # Recrear esquema vacío
    cache.init_db()
    return {"files": files, "bytes": freed}


def clean_addon_profile(keep_settings: bool = True) -> Dict[str, int]:
    """
    Vacía special://profile/addon_data/plugin.video.launcherm3u/
    Conserva settings.xml de Kodi (está fuera o gestionado por Kodi).
    """
    profile = ku.ensure_profile()
    files = 0
    freed = 0

    # Primero intentar wipe lógico
    try:
        cache.wipe_all()
    except Exception:
        pass

    if not os.path.isdir(profile):
        return {"files": 0, "bytes": 0}

    for name in os.listdir(profile):
        # settings del addon los gestiona Kodi en otro sitio; por si acaso no tocar settings.xml
        if keep_settings and name in ("settings.xml", "settings.xml.bak"):
            continue
        target = os.path.join(profile, name)
        f, b = _delete_path(target)
        files += f
        freed += b

    ku.ensure_profile()
    cache.init_db()
    return {"files": files, "bytes": freed}


def _textures_db_path() -> str:
    return xbmcvfs.translatePath("special://database/Textures13.db")


def _thumbnails_root() -> str:
    return xbmcvfs.translatePath("special://thumbnails/")


def clean_thumbnails(logo_urls: Optional[List[str]] = None) -> Dict[str, int]:
    """
    Elimina de Textures13.db y de Thumbnails/ las imágenes asociadas a logos
    del addon (y URLs plugin:// del propio addon).
    """
    urls = logo_urls if logo_urls is not None else collect_logo_urls()
    db_path = _textures_db_path()
    thumbs_root = _thumbnails_root()
    files = 0
    freed = 0

    if not os.path.exists(db_path):
        ku.log("Textures13.db no encontrada")
        return {"files": 0, "bytes": 0}

    # Evitar corrupción: pedir a Kodi que libere cachés de imagen
    xbmc.executebuiltin("Dialog.Close(all,true)")

    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            to_delete: List[Tuple[int, str, str]] = []

            # Por URLs de logo conocidas
            for url in urls:
                rows = conn.execute(
                    "SELECT id, url, cachedurl FROM texture WHERE url=?", (url,)
                ).fetchall()
                for row in rows:
                    to_delete.append((row["id"], row["url"], row["cachedurl"] or ""))

            # Cualquier textura del propio plugin
            rows = conn.execute(
                "SELECT id, url, cachedurl FROM texture WHERE url LIKE ?",
                (f"%{ku.ADDON_ID}%",),
            ).fetchall()
            for row in rows:
                to_delete.append((row["id"], row["url"], row["cachedurl"] or ""))

            # Deduplicar por id
            seen = set()
            unique = []
            for item in to_delete:
                if item[0] in seen:
                    continue
                seen.add(item[0])
                unique.append(item)

            for texture_id, _url, cachedurl in unique:
                if cachedurl:
                    # cachedurl suele ser relativo tipo "a/abc.jpg"
                    thumb_path = cachedurl
                    if not os.path.isabs(thumb_path):
                        thumb_path = os.path.join(thumbs_root, cachedurl.replace("/", os.sep))
                    f, b = _delete_path(thumb_path)
                    files += f
                    freed += b
                conn.execute("DELETE FROM texture WHERE id=?", (texture_id,))

            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        ku.log(f"Error limpiando Textures13.db: {exc}", level=3)

    # Vaciar también caché temporal de imágenes de Kodi relacionada
    temp = xbmcvfs.translatePath("special://temp/")
    for name in _vfs_listdir(temp):
        lower = name.lower()
        if ku.ADDON_ID.lower() in lower or lower.startswith("launcherm3u"):
            f, b = _delete_path(os.path.join(temp, name))
            files += f
            freed += b

    return {"files": files, "bytes": freed}


def clean_temp_addon() -> Dict[str, int]:
    temp = xbmcvfs.translatePath("special://temp/")
    files = 0
    freed = 0
    for name in _vfs_listdir(temp):
        lower = name.lower()
        if ku.ADDON_ID.lower() in lower or "launcherm3u" in lower:
            f, b = _delete_path(os.path.join(temp, name))
            files += f
            freed += b
    return {"files": files, "bytes": freed}


def storage_stats() -> Dict[str, int]:
    profile = ku.PROFILE_PATH
    return {
        "profile_bytes": _size_of_path(profile),
        "db_bytes": _size_of_path(cache.db_path()),
        "downloads_bytes": _size_of_path(downloads_dir()),
        "logos": len(collect_logo_urls()),
    }


def clean_full() -> Dict[str, int]:
    """Limpieza completa estilo 'limpia Kodi' limitada al ámbito del addon."""
    logos = collect_logo_urls()
    totals = {"files": 0, "bytes": 0}

    for part in (
        clean_thumbnails(logos),
        clean_temp_addon(),
        clean_addon_profile(keep_settings=True),
    ):
        totals["files"] += part.get("files", 0)
        totals["bytes"] += part.get("bytes", 0)

    # Regenerar estructura mínima
    ku.ensure_profile()
    cache.init_db()
    if not xbmcvfs.exists(downloads_dir()):
        xbmcvfs.mkdirs(downloads_dir())

    # Refrescar cachés de UI
    xbmc.executebuiltin("Container.Refresh")
    return totals


def confirm_and_run(kind: str) -> None:
    """Diálogo de confirmación + ejecución de limpieza."""
    labels = {
        "downloads": ku.get_string(30310) or "¿Borrar descargas M3U/EPG en caché?",
        "database": ku.get_string(30311) or "¿Borrar base de datos de canales y EPG?",
        "thumbnails": ku.get_string(30312) or "¿Borrar thumbnails/logos cacheados por el addon?",
        "full": ku.get_string(30313)
        or "¿Limpieza completa del addon (caché, descargas, BD y thumbnails)?",
    }
    message = labels.get(kind, labels["full"])
    if not xbmcgui.Dialog().yesno(ku.ADDON_NAME, message):
        return

    progress = xbmcgui.DialogProgress()
    progress.create(ku.ADDON_NAME, ku.get_string(30314) or "Limpiando...")
    try:
        progress.update(20)
        if kind == "downloads":
            result = clean_downloads()
        elif kind == "database":
            result = clean_database()
        elif kind == "thumbnails":
            result = clean_thumbnails()
        else:
            progress.update(40)
            result = clean_full()
        progress.update(100)
    finally:
        progress.close()

    msg = (ku.get_string(30315) or "Limpieza terminada: {0} archivos, {1} liberados").format(
        result.get("files", 0),
        _format_bytes(result.get("bytes", 0)),
    )
    ku.notify(msg)
    xbmc.executebuiltin("Container.Refresh")
