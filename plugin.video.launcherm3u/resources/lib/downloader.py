# -*- coding: utf-8 -*-
"""Descarga y almacenamiento local de M3U/EPG con soporte ETag."""

from __future__ import annotations

import gzip
import hashlib
import os
import ssl
import time
from html import unescape
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import xbmcvfs

from . import kodi_utils as ku


USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

_CHUNK_SIZE = 1024 * 1024


def build_request_headers() -> dict:
    """Cabeceras HTTP para descargas y (vía player) streams."""
    headers = {
        "User-Agent": (ku.get_setting("http_user_agent") or "").strip() or USER_AGENT,
        "Accept": "*/*",
        "Connection": "close",
    }
    referer = (ku.get_setting("http_referer") or "").strip()
    if referer:
        headers["Referer"] = referer
    origin = (ku.get_setting("http_origin") or "").strip()
    if origin:
        headers["Origin"] = origin
    extra = (ku.get_setting("http_extra_headers") or "").strip()
    for line in extra.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key:
            headers[key] = value
    return headers


def stream_headers_query() -> str:
    """Fragmento User-Agent=...&Referer=... para URLs de Kodi (|headers)."""
    from urllib.parse import quote

    headers = build_request_headers()
    # Solo cabeceras útiles en reproducción
    keys = ("User-Agent", "Referer", "Origin", "Cookie", "Authorization")
    parts = []
    for key in keys:
        value = headers.get(key)
        if value:
            parts.append(f"{key}={quote(value, safe='')}")
    # Extra headers explícitos también
    for key, value in headers.items():
        if key in keys or key in ("Accept", "Connection"):
            continue
        parts.append(f"{key}={quote(value, safe='')}")
    return "&".join(parts)


def apply_stream_url_headers(url: str) -> str:
    """Añade |User-Agent=... a la URL de stream si hay cabeceras custom."""
    url = (url or "").strip()
    if not url or "|" in url:
        return url
    # Solo si el usuario configuró algo distinto del UA por defecto
    custom_ua = (ku.get_setting("http_user_agent") or "").strip()
    referer = (ku.get_setting("http_referer") or "").strip()
    origin = (ku.get_setting("http_origin") or "").strip()
    extra = (ku.get_setting("http_extra_headers") or "").strip()
    if not (custom_ua or referer or origin or extra):
        return url
    query = stream_headers_query()
    return f"{url}|{query}" if query else url



def normalize_http_url(url: str) -> str:
    """
    Normaliza URLs remotas conservando query (?a=1&b=2), puerto y path .xml.gz.
    Tolera espacios al pegar y &amp; procedentes de HTML/ajustes.
    """
    text = unescape((url or "").strip())
    text = text.replace("\r", "").replace("\n", "").replace("\t", "")
    text = "".join(text.split())
    # Por si quedó doble entidad tras guardar en settings XML
    text = text.replace("&amp;", "&")
    if not text:
        return ""
    if text.lower().startswith("//"):
        text = "https:" + text
    if not text.lower().startswith(("http://", "https://")):
        text = "https://" + text
    return text


def url_indicates_gzip(url: str) -> bool:
    """True si el path de la URL apunta a un .gz (aunque haya ?query)."""
    path = urlsplit(url or "").path.lower()
    return path.endswith(".gz") or path.endswith(".gzip")


def _cache_dir() -> str:
    path = os.path.join(ku.ensure_profile(), "downloads")
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return path


def source_fingerprint(source: str) -> str:
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def local_path_for(kind: str, source: str) -> str:
    return os.path.join(_cache_dir(), f"{kind}_{source_fingerprint(source)}.dat")


def meta_path_for(kind: str, source: str) -> str:
    return os.path.join(_cache_dir(), f"{kind}_{source_fingerprint(source)}.meta")


def _read_meta(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    meta = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    key, value = line.rstrip("\n").split("=", 1)
                    meta[key] = value
    except OSError:
        return {}
    return meta


def _write_meta(path: str, meta: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            for key, value in meta.items():
                fh.write(f"{key}={value}\n")
    except OSError as exc:
        ku.log(f"No se pudo guardar meta: {exc}", level=3)


def _is_fresh(meta: dict, max_age_hours: int) -> bool:
    try:
        fetched = float(meta.get("fetched", "0"))
    except ValueError:
        return False
    return (time.time() - fetched) < max_age_hours * 3600


def _copy_stream(src, out) -> None:
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        out.write(chunk)


def _materialize_download(raw_path: str, dest_path: str, compressed: bool) -> None:
    """Publica atómicamente el fichero, descomprimiendo sin cargarlo en RAM."""
    ready = dest_path + ".ready"
    try:
        with open(raw_path, "rb") as source, open(ready, "wb") as out:
            if compressed:
                try:
                    with gzip.GzipFile(fileobj=source, mode="rb") as decoded:
                        _copy_stream(decoded, out)
                except OSError:
                    source.seek(0)
                    out.seek(0)
                    out.truncate()
                    _copy_stream(source, out)
            else:
                # Algunos servidores envían gzip aunque no lo indiquen en cabeceras
                magic = source.read(2)
                source.seek(0)
                if magic == b"\x1f\x8b":
                    try:
                        with gzip.GzipFile(fileobj=source, mode="rb") as decoded:
                            _copy_stream(decoded, out)
                    except OSError:
                        source.seek(0)
                        out.seek(0)
                        out.truncate()
                        _copy_stream(source, out)
                else:
                    _copy_stream(source, out)
        if os.path.getsize(ready) == 0:
            raise IOError("Descarga vacía")
        os.replace(ready, dest_path)
    finally:
        for path in (raw_path, ready):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


def looks_like_playlist(path: str) -> bool:
    """True si el fichero parece una lista M3U y no una página HTML de error."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    if not head:
        return False
    # UTF-8 BOM
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    text = head.decode("utf-8", errors="replace").lstrip().lower()
    if text.startswith("<!doctype") or text.startswith("<html") or text.startswith("<head"):
        return False
    if "#extm3u" in text or "#extinf" in text:
        return True
    # Listas mínimas sin cabecera EXTINF
    return "http://" in text or "https://" in text or "rtmp://" in text


def looks_like_xmltv(path: str) -> bool:
    """True si el fichero parece XMLTV (y no HTML de login/error)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
    except OSError:
        return False
    if not head:
        return False
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:]
    # Guía aún comprimida: mirar dentro del gzip
    if head.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(filename=path, mode="rb") as gz:
                head = gz.read(8192)
        except OSError:
            return False
        if not head:
            return False
        if head.startswith(b"\xef\xbb\xbf"):
            head = head[3:]
    text = head.decode("utf-8", errors="replace").lstrip().lower()
    if text.startswith("<!doctype") or text.startswith("<html") or text.startswith("<head"):
        return False
    return (
        text.startswith("<?xml")
        or "<tv" in text
        or "<channel" in text
        or "<programme" in text
    )


def file_is_gzip(path: str) -> bool:
    lower = (path or "").lower()
    if lower.endswith(".gz") or lower.endswith(".gzip"):
        return True
    try:
        with open(path, "rb") as fh:
            return fh.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def ensure_plain_xmltv(path: str, source_key: str = "") -> str:
    """
    Si el XMLTV viene en .gz, lo descomprime a caché y devuelve la ruta plana.
    Así el parser siempre recibe XML legible aunque la copia VFS pierda la extensión.
    """
    if not path or not os.path.exists(path):
        return path
    if not file_is_gzip(path):
        return path
    dest = local_path_for("epg", source_key or path)
    # Evitar sobrescribir el propio origen si ya es el destino de caché
    if os.path.abspath(dest) == os.path.abspath(path):
        dest = path + ".xml"
    try:
        if (
            os.path.exists(dest)
            and os.path.getsize(dest) > 0
            and os.path.getmtime(dest) >= os.path.getmtime(path)
            and looks_like_xmltv(dest)
            and not file_is_gzip(dest)
        ):
            return dest
        raw_tmp = dest + ".gzpart"
        with open(path, "rb") as src, open(raw_tmp, "wb") as out:
            _copy_stream(src, out)
        _materialize_download(raw_tmp, dest, compressed=True)
        if not looks_like_xmltv(dest):
            raise IOError("El archivo .gz no contiene una guía XMLTV válida")
        return dest
    except Exception as exc:
        ku.log(f"No se pudo descomprimir XMLTV gzip: {exc}", level=3)
        raise IOError(f"No se pudo leer el archivo .gz ({exc})") from exc


def _ssl_contexts():
    """Primero verificación normal; luego fallback sin verificar (Android TV)."""
    try:
        yield ssl.create_default_context()
    except Exception:
        pass
    try:
        yield ssl._create_unverified_context()
    except Exception:
        yield None


def _fetch_via_urllib(url: str, dest_path: str, headers: dict) -> dict:
    """Descarga con urllib. Devuelve cabeceras útiles."""
    last_error = None
    for ctx in _ssl_contexts():
        try:
            request = Request(url, headers=headers)
            open_kwargs = {"timeout": 90}
            if ctx is not None:
                open_kwargs["context"] = ctx
            with urlopen(request, **open_kwargs) as response:
                raw_path = dest_path + ".part"
                with open(raw_path, "wb") as out:
                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                encoding = (response.headers.get("Content-Encoding", "") or "").lower()
                ctype = (response.headers.get("Content-Type", "") or "").lower()
                compressed = (
                    "gzip" in encoding
                    or "gzip" in ctype
                    or "x-gzip" in ctype
                    or url_indicates_gzip(url)
                )
                _materialize_download(raw_path, dest_path, compressed)
                return {
                    "etag": response.headers.get("ETag", "") or "",
                    "last_modified": response.headers.get("Last-Modified", "") or "",
                    "final_url": (
                        response.geturl()
                        if callable(getattr(response, "geturl", None))
                        else url
                    ),
                }
        except HTTPError as exc:
            if exc.code == 304:
                raise
            last_error = exc
            # 4xx/5xx no se arreglan cambiando SSL
            if 400 <= int(exc.code) < 600:
                raise
            ku.log(f"urllib HTTPError status={exc.code}", level=3)
        except (URLError, ssl.SSLError, OSError) as exc:
            last_error = exc
            ku.log(f"urllib intento fallido ({type(exc).__name__})", level=2)
            continue
        except Exception as exc:
            last_error = exc
            ku.log(f"urllib intento fallido ({type(exc).__name__})", level=2)
            continue
    if last_error:
        raise last_error
    raise IOError("Descarga urllib fallida")


def _fetch_via_vfs(url: str, dest_path: str) -> None:
    """Descarga usando el VFS de Kodi (HTTPS/redes del sistema)."""
    raw_path = dest_path + ".part"
    try:
        if xbmcvfs.exists(raw_path):
            xbmcvfs.delete(raw_path)
    except Exception:
        pass

    gzip_hint = url_indicates_gzip(url)
    copy_fn = getattr(xbmcvfs, "copy", None)
    if callable(copy_fn) and copy_fn(url, raw_path):
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            _materialize_download(raw_path, dest_path, gzip_hint)
            return

    with xbmcvfs.File(url) as src:
        with open(raw_path, "wb") as out:
            if hasattr(src, "readBytes"):
                while True:
                    chunk = src.readBytes(_CHUNK_SIZE)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8", errors="replace")
                    out.write(chunk)
            else:
                while True:
                    chunk = src.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8", errors="replace")
                    out.write(chunk)
    _materialize_download(raw_path, dest_path, gzip_hint)
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise IOError("Descarga VFS vacía")


def _download_looks_valid(
    dest_path: str, require_playlist: bool, require_xmltv: bool
) -> bool:
    if require_playlist:
        return looks_like_playlist(dest_path)
    if require_xmltv:
        return looks_like_xmltv(dest_path)
    return True


def fetch_url(
    url: str,
    dest_path: str,
    meta_file: str,
    max_age_hours: int,
    force: bool = False,
    require_playlist: bool = False,
    require_xmltv: bool = False,
) -> Tuple[str, bool]:
    """Devuelve (ruta_local, refreshed). urllib primero; si falla, VFS de Kodi."""
    meta = _read_meta(meta_file)
    if not force and os.path.exists(dest_path) and _is_fresh(meta, max_age_hours):
        if _download_looks_valid(dest_path, require_playlist, require_xmltv):
            return dest_path, False

    url = normalize_http_url(url)
    if not url:
        raise ValueError("URL vacía")

    # No pedir gzip: evita cuerpos comprimidos mal anunciados en Android/TV.
    # Aceptamos XMLTV/M3U y respuestas comprimidas (.xml.gz / xmltv.php).
    headers = build_request_headers()
    headers["Accept"] = "application/xml,text/xml,application/gzip,*/*"
    if not force:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    last_error = None
    try:
        info = _fetch_via_urllib(url, dest_path, headers)
        if require_playlist and not looks_like_playlist(dest_path):
            raise IOError("La URL no devolvió una lista M3U válida")
        if require_xmltv:
            if file_is_gzip(dest_path):
                dest_path = ensure_plain_xmltv(dest_path, source_key=url)
            if not looks_like_xmltv(dest_path):
                raise IOError("La URL no devolvió una guía XMLTV válida")
        _write_meta(
            meta_file,
            {
                "fetched": str(time.time()),
                "etag": info.get("etag", ""),
                "last_modified": info.get("last_modified", ""),
                "url": url,
            },
        )
        return dest_path, True
    except HTTPError as exc:
        if exc.code == 304 and os.path.exists(dest_path):
            meta["fetched"] = str(time.time())
            _write_meta(meta_file, meta)
            return dest_path, False
        last_error = exc
        ku.log(f"urllib HTTPError status={exc.code}", level=3)
    except Exception as exc:
        last_error = exc
        ku.log(f"urllib falló ({type(exc).__name__}), probando VFS", level=3)

    try:
        _fetch_via_vfs(url, dest_path)
        if require_playlist and not looks_like_playlist(dest_path):
            raise IOError("La URL no devolvió una lista M3U válida")
        if require_xmltv:
            if file_is_gzip(dest_path):
                dest_path = ensure_plain_xmltv(dest_path, source_key=url)
            if not looks_like_xmltv(dest_path):
                raise IOError("La URL no devolvió una guía XMLTV válida")
        _write_meta(
            meta_file,
            {"fetched": str(time.time()), "etag": "", "last_modified": "", "url": url},
        )
        return dest_path, True
    except Exception as exc:
        ku.log(f"VFS también falló ({type(exc).__name__})", level=3)
        if (
            os.path.exists(dest_path)
            and os.path.getsize(dest_path) > 0
            and _download_looks_valid(dest_path, require_playlist, require_xmltv)
        ):
            ku.log("Usando copia en caché tras fallo de descarga")
            return dest_path, False
        reason = type(last_error or exc).__name__
        detail = str(last_error or exc)
        if isinstance(last_error, HTTPError):
            detail = f"HTTP {last_error.code}"
        raise IOError(f"No se pudo descargar la URL ({reason}: {detail})") from exc


def vfs_exists(path: str) -> bool:
    if not path:
        return False
    if xbmcvfs.exists(path):
        return True
    if path.endswith("/") or path.endswith("\\"):
        return xbmcvfs.exists(path.rstrip("/\\"))
    try:
        with xbmcvfs.File(path) as fh:
            _ = fh.size() if hasattr(fh, "size") else True
            return True
    except Exception:
        return os.path.exists(path)


def copy_vfs_to_temp(vfs_path: str, kind: str) -> str:
    """Copia un archivo VFS a disco local para parsers que necesitan open() nativo."""
    dest = local_path_for(kind, vfs_path)
    chunk_size = 1024 * 1024
    with xbmcvfs.File(vfs_path) as src, open(dest, "wb") as out:
        if hasattr(src, "readBytes"):
            while True:
                chunk = src.readBytes(chunk_size)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                out.write(chunk)
        else:
            while True:
                data = src.read(chunk_size)
                if not data:
                    break
                if isinstance(data, str):
                    data = data.encode("utf-8", errors="replace")
                out.write(data)
    if not os.path.exists(dest):
        raise FileNotFoundError(vfs_path)
    if kind == "epg":
        return ensure_plain_xmltv(dest, source_key=vfs_path)
    return dest


def resolve_local_readable(kind: str, path: str) -> str:
    """Resuelve una ruta local/VFS a un fichero legible con open() de Python."""
    source = (path or "").strip()
    if not source:
        raise ValueError("empty path")

    translated = xbmcvfs.translatePath(source) if source.startswith("special://") else source
    if "special://" in translated:
        translated = xbmcvfs.translatePath(translated)

    candidates = [translated, source]
    last_error = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if not vfs_exists(candidate) and not os.path.exists(candidate):
                continue
            if os.path.isfile(candidate):
                resolved = candidate
            else:
                resolved = copy_vfs_to_temp(candidate, kind)
            if kind == "epg":
                return ensure_plain_xmltv(resolved, source_key=source)
            return resolved
        except Exception as exc:
            last_error = exc
            ku.log(f"No se pudo abrir {candidate}: {exc}", level=3)
            continue

    msg = translated or source
    if last_error:
        raise FileNotFoundError(f"{msg} ({last_error})")
    raise FileNotFoundError(msg)


def resolve_source(
    kind: str,
    is_remote: bool,
    path: str,
    url: str,
    max_age_hours: int,
    force: bool = False,
) -> Optional[str]:
    """Resuelve una fuente local o remota a una ruta de archivo usable."""
    path = (path or "").strip()
    url = (url or "").strip()

    def _as_remote(value: str) -> bool:
        low = (value or "").strip().lower()
        return low.startswith(("http://", "https://", "//", "www."))

    if _as_remote(url):
        url = normalize_http_url(url)
    else:
        url = url.replace("\r", "").replace("\n", "")

    if _as_remote(path):
        path = normalize_http_url(path)

    # Autodetectar URL aunque el tipo esté mal configurado
    if not is_remote and url.lower().startswith(("http://", "https://")) and not path:
        is_remote = True
    if not is_remote and path.lower().startswith(("http://", "https://")):
        url = path
        is_remote = True
    if is_remote and not url and path.lower().startswith(("http://", "https://")):
        url = path

    if is_remote:
        if not url:
            return None
        url = normalize_http_url(url)
        dest = local_path_for(kind, url)
        meta = meta_path_for(kind, url)
        resolved, _ = fetch_url(
            url,
            dest,
            meta,
            max_age_hours,
            force=force,
            require_playlist=(kind == "m3u"),
            require_xmltv=(kind == "epg"),
        )
        return resolved

    if not path:
        return None
    return resolve_local_readable(kind, path)
