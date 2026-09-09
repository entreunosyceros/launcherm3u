# -*- coding: utf-8 -*-
"""Comprobación e instalación de actualizaciones vía GitHub Releases."""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import xbmc
import xbmcgui
import xbmcvfs

from . import downloader
from . import kodi_utils as ku

GITHUB_REPO = "entreunosyceros/launcherm3u"
GITHUB_RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
ADDON_ID = "plugin.video.launcherm3u"

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def _parse_version(text: str) -> tuple:
    match = _VERSION_RE.search((text or "").strip())
    if not match:
        return tuple()
    parts = []
    for chunk in match.group(1).split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def current_version() -> str:
    try:
        return ku.ADDON.getAddonInfo("version") or "0"
    except Exception:
        return "0"


def _fetch_remote_text(url: str) -> str:
    url = downloader.normalize_http_url(url)
    if not url:
        return ""
    headers = downloader.build_request_headers()
    headers["Accept"] = "application/vnd.github+json"
    headers["User-Agent"] = headers.get("User-Agent") or f"LauncherM3U/{current_version()}"
    last_error = None
    for ctx in downloader._ssl_contexts():
        try:
            request = Request(url, headers=headers)
            open_kwargs = {"timeout": 25}
            if ctx is not None:
                open_kwargs["context"] = ctx
            with urlopen(request, **open_kwargs) as response:
                raw = response.read(512 * 1024)
            return raw.decode("utf-8", errors="replace").strip()
        except (HTTPError, URLError, OSError) as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return ""


def _pick_zip_asset(assets: list) -> str:
    """Elige el ZIP de instalación entre los assets del release."""
    if not assets:
        return ""
    ranked = []
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "")
        if not url or not name.endswith(".zip"):
            continue
        score = 0
        if "launcherm3u" in name:
            score += 30
        if "plugin.video.launcherm3u" in name:
            score += 40
        if name.startswith("launcherm3u-"):
            score += 10
        ranked.append((score, url))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def is_trusted_zip_url(url: str) -> bool:
    """Solo acepta ZIPs de releases del repo oficial."""
    text = (url or "").strip().lower()
    if not text.startswith("https://") or ".zip" not in text:
        return False
    if "github.com/entreunosyceros/launcherm3u/releases/download/" in text:
        return True
    if "githubusercontent.com" in text and "launcherm3u" in text:
        return True
    return False


def parse_github_release(payload: str) -> dict:
    """Parsea la respuesta de /releases/latest."""
    text = (payload or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    version = tag.lstrip("vV")
    zip_url = _pick_zip_asset(data.get("assets") or [])
    page_url = str(data.get("html_url") or GITHUB_RELEASES_PAGE)
    notes = str(data.get("body") or "").strip()
    return {
        "version": version,
        "url": zip_url or page_url,
        "page": page_url,
        "notes": notes,
        "tag": tag,
    }


def parse_remote_manifest(payload: str) -> dict:
    """Compat: JSON simple o respuesta GitHub Releases."""
    text = (payload or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        data = json.loads(text)
        if "tag_name" in data or "assets" in data:
            return parse_github_release(text)
        return {
            "version": str(data.get("version") or "").lstrip("v"),
            "url": str(data.get("url") or data.get("download") or data.get("html_url") or ""),
            "page": str(data.get("html_url") or GITHUB_RELEASES_PAGE),
            "notes": str(data.get("notes") or data.get("body") or data.get("message") or ""),
        }
    first = text.splitlines()[0].strip().lstrip("v")
    return {"version": first, "url": GITHUB_RELEASES_PAGE, "page": GITHUB_RELEASES_PAGE, "notes": ""}


def is_newer(remote: str, local: str) -> bool:
    remote_v = _parse_version(remote)
    local_v = _parse_version(local)
    if not remote_v:
        return False
    size = max(len(remote_v), len(local_v))
    remote_v = remote_v + (0,) * (size - len(remote_v))
    local_v = local_v + (0,) * (size - len(local_v))
    return remote_v > local_v


def check_for_updates(force: bool = False) -> dict:
    """
    Consulta la última release de GitHub.
    Devuelve: checked, update, local, remote, url, page, notes, error
    """
    result = {
        "checked": False,
        "update": False,
        "local": current_version(),
        "remote": "",
        "url": "",
        "page": GITHUB_RELEASES_PAGE,
        "notes": "",
        "error": "",
    }
    if not ku.get_setting_bool("update_check_enabled", True) and not force:
        return result

    if not force:
        try:
            from . import cache

            last = int(cache.get_meta("update_last_check", "0") or 0)
        except Exception:
            last = 0
        if last and time.time() - last < 20 * 3600:
            return result

    try:
        payload = _fetch_remote_text(GITHUB_RELEASES_API)
        info = parse_github_release(payload)
        remote = info.get("version") or ""
        result["checked"] = True
        result["remote"] = remote
        result["url"] = info.get("url") or GITHUB_RELEASES_PAGE
        result["page"] = info.get("page") or GITHUB_RELEASES_PAGE
        result["notes"] = info.get("notes") or ""
        result["update"] = is_newer(remote, result["local"])
        stamp = str(int(time.time()))
        try:
            from . import cache

            cache.set_meta("update_last_check", stamp)
            if result["update"]:
                cache.set_meta("update_remote_version", remote)
                cache.set_meta("update_download_url", result["url"])
        except Exception:
            pass
    except Exception as exc:
        result["error"] = str(exc)
        ku.log(f"Update check failed: {exc}", level=2)
    return result


def _temp_zip_path(version: str) -> str:
    temp = xbmcvfs.translatePath("special://temp/")
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", version or "update")
    return os.path.join(temp, f"{ADDON_ID}-{safe}-update.zip")


def _validate_addon_zip(path: str) -> bool:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            expected = f"{ADDON_ID}/addon.xml"
            return expected in names or any(
                n.endswith(f"{ADDON_ID}/addon.xml") for n in names
            )
    except Exception as exc:
        ku.log(f"ZIP update inválido: {exc}", level=3)
        return False


def download_update_zip(url: str, dest_path: str, show_progress: bool = False) -> bool:
    """Descarga el ZIP de update a dest_path."""
    url = downloader.normalize_http_url(url)
    if not is_trusted_zip_url(url):
        ku.log(f"URL de update no confiable: {url}", level=3)
        return False

    headers = downloader.build_request_headers()
    headers["User-Agent"] = headers.get("User-Agent") or f"LauncherM3U/{current_version()}"
    headers["Accept"] = "application/octet-stream"

    progress = None
    if show_progress:
        progress = xbmcgui.DialogProgress()
        progress.create(
            ku.get_string(30544) or "Actualizaciones",
            ku.get_string(30632) or "Descargando actualización…",
        )

    try:
        last_error = None
        for ctx in downloader._ssl_contexts():
            try:
                request = Request(url, headers=headers)
                open_kwargs = {"timeout": 60}
                if ctx is not None:
                    open_kwargs["context"] = ctx
                with urlopen(request, **open_kwargs) as response:
                    total = int(response.headers.get("Content-Length") or 0)
                    done = 0
                    chunk_size = 64 * 1024
                    # Escritura vía ruta local (special://temp suele ser filesystem)
                    parent = os.path.dirname(dest_path)
                    if parent and not os.path.isdir(parent):
                        os.makedirs(parent, exist_ok=True)
                    with open(dest_path, "wb") as handle:
                        while True:
                            if progress and progress.iscanceled():
                                handle.close()
                                try:
                                    os.remove(dest_path)
                                except OSError:
                                    pass
                                return False
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            handle.write(chunk)
                            done += len(chunk)
                            if progress and total > 0:
                                pct = min(99, int(done * 100 / total))
                                progress.update(
                                    pct,
                                    ku.get_string(30632)
                                    or "Descargando actualización…",
                                )
                if progress:
                    progress.update(100)
                return os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0
            except (HTTPError, URLError, OSError) as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        return False
    except Exception as exc:
        ku.log(f"Download update failed: {exc}", level=3)
        return False
    finally:
        if progress:
            progress.close()


def install_update_from_zip(zip_path: str) -> bool:
    """Extrae el ZIP sobre special://home/addons e informa a Kodi."""
    if not zip_path or not os.path.isfile(zip_path):
        return False
    if not _validate_addon_zip(zip_path):
        ku.notify_error(ku.get_string(30633) or "ZIP de actualización no válido")
        return False

    addons = xbmcvfs.translatePath("special://home/addons/")
    if not addons:
        return False
    if not xbmcvfs.exists(addons):
        xbmcvfs.mkdirs(addons)

    # Rutas con barras que entiende el builtin Extract
    zip_uri = zip_path.replace("\\", "/")
    addons_uri = addons.replace("\\", "/")
    if not addons_uri.endswith("/"):
        addons_uri += "/"

    ku.notify(ku.get_string(30634) or "Instalando actualización…", time_ms=2500)
    xbmc.executebuiltin(f"Extract({zip_uri},{addons_uri})")

    monitor = xbmc.Monitor()
    # Esperar a que termine la extracción
    deadline = time.time() + 20
    addon_xml = os.path.join(addons, ADDON_ID, "addon.xml")
    while time.time() < deadline:
        if monitor.waitForAbort(0.4):
            return False
        if os.path.isfile(addon_xml):
            # Dar un poco más por si aún escribe
            monitor.waitForAbort(0.8)
            break

    xbmc.executebuiltin("UpdateLocalAddons")
    monitor.waitForAbort(1.5)
    xbmc.executebuiltin(f"EnableAddon({ADDON_ID})")
    return True


def apply_update(info: dict, show_progress: bool = False) -> bool:
    """Descarga e instala la actualización descrita por check_for_updates()."""
    url = str(info.get("url") or "")
    version = str(info.get("remote") or "update")
    if not is_trusted_zip_url(url):
        ku.notify_error(
            ku.get_string(30635)
            or "No hay ZIP de instalación en el release de GitHub"
        )
        return False

    dest = _temp_zip_path(version)
    try:
        if os.path.isfile(dest):
            os.remove(dest)
    except OSError:
        pass

    if not download_update_zip(url, dest, show_progress=show_progress):
        ku.notify_error(ku.get_string(30636) or "No se pudo descargar la actualización")
        return False

    ok = install_update_from_zip(dest)
    try:
        if os.path.isfile(dest):
            os.remove(dest)
    except OSError:
        pass

    if ok:
        ku.notify(
            (ku.get_string(30637) or "Actualizado a {0}. Reinicia el addon.").format(
                version
            ),
            time_ms=7000,
        )
        try:
            from . import cache

            cache.set_meta("update_installed_version", version)
        except Exception:
            pass
    else:
        ku.notify_error(ku.get_string(30638) or "No se pudo instalar la actualización")
    return ok


def _open_release_page(page: str) -> None:
    target = page or GITHUB_RELEASES_PAGE
    try:
        xbmc.executebuiltin(f"System.OpenLink({target})")
    except Exception:
        ku.notify(target, time_ms=8000)


def notify_if_update(force: bool = False) -> None:
    info = check_for_updates(force=force)
    if info.get("error") and force:
        ku.notify_error(info["error"])
        return
    if not info.get("checked") and not info.get("error"):
        if force:
            ku.notify(
                (ku.get_string(30541) or "Estás al día ({0})").format(info["local"])
            )
        return
    if not info.get("update"):
        if force:
            ku.notify(
                (ku.get_string(30541) or "Estás al día ({0})").format(info["local"])
            )
        return

    msg = (ku.get_string(30542) or "Nueva versión {0} (tienes {1})").format(
        info["remote"], info["local"]
    )
    page = info.get("page") or GITHUB_RELEASES_PAGE
    download = info.get("url") or ""
    ku.log(f"Update available {info['remote']} download={download}")

    auto_install = ku.get_setting_bool("update_auto_install", True)

    # Comprobación manual: diálogo con opciones
    if force:
        notes = (info.get("notes") or "").strip()
        body = msg
        if notes:
            first = notes.splitlines()[0].strip()
            if first:
                body = f"{msg}\n\n{first[:160]}"
        options = [
            ku.get_string(30639) or "Instalar ahora",
            ku.get_string(30630) or "Abrir página de descarga",
            ku.get_string(30631) or "Más tarde",
        ]
        choice = xbmcgui.Dialog().select(
            ku.get_string(30544) or "Actualizaciones", options
        )
        if choice == 0:
            apply_update(info, show_progress=True)
        elif choice == 1:
            _open_release_page(page)
        return

    # Arranque en segundo plano
    if auto_install and is_trusted_zip_url(download):
        ku.notify(msg, time_ms=4000)
        apply_update(info, show_progress=False)
        return

    ku.notify(f"{msg} — {page}", time_ms=8000)
