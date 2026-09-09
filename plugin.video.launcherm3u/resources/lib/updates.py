# -*- coding: utf-8 -*-
"""Comprobación de actualizaciones vía GitHub Releases."""

from __future__ import annotations

import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import downloader
from . import kodi_utils as ku

GITHUB_REPO = "entreunosyceros/launcherm3u"
GITHUB_RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
)
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"

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
    # GitHub API recomienda este Accept y un UA identificable
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


def notify_if_update(force: bool = False) -> None:
    info = check_for_updates(force=force)
    if info.get("error") and force:
        ku.notify_error(info["error"])
        return
    if not info.get("checked") and not info.get("error"):
        # Throttle: sin aviso
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
    msg = f"{msg} — {page}"
    ku.notify(msg, time_ms=8000)
    ku.log(f"Update available {info['remote']} download={info.get('url')}")
