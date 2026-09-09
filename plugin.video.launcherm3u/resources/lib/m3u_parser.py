# -*- coding: utf-8 -*-
"""Parser M3U en streaming (línea a línea) para listas grandes."""

from __future__ import annotations

import html
import re
from typing import Dict, Generator, Iterable, Optional

ATTR_RE = re.compile(
    r"""([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s,]+))"""
)
URL_TVG_RE = re.compile(
    r"""url-tvg\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s"']+))""",
    re.IGNORECASE,
)


def _split_metadata(payload: str) -> tuple[str, str]:
    """Separa metadatos/nombre por la primera coma que esté fuera de comillas."""
    quote = ""
    for index, char in enumerate(payload):
        if char in ('"', "'"):
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
        elif char == "," and not quote:
            return payload[:index], payload[index + 1 :]
    return payload, payload


def _normalise_logo(value: str) -> str:
    logo = html.unescape((value or "").strip())
    if logo.startswith("//"):
        logo = "https:" + logo
    return logo


def extract_url_tvg_from_header(line: str) -> str:
    """Extrae url-tvg de una línea #EXTM3U."""
    if not line or not line.upper().startswith("#EXTM3U"):
        return ""
    match = URL_TVG_RE.search(line)
    if not match:
        return ""
    value = next((part for part in match.groups() if part), "") or ""
    value = html.unescape(value.strip())
    if value.startswith("//"):
        value = "https:" + value
    return value


def peek_playlist_meta(path: str) -> Dict[str, str]:
    """Lee metadatos de cabecera (url-tvg, etc.) sin parsear toda la lista."""
    meta = {"url_tvg": ""}
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, errors="replace") as fh:
                for _ in range(30):
                    line = fh.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    if line.upper().startswith("#EXTM3U"):
                        meta["url_tvg"] = extract_url_tvg_from_header(line)
                        return meta
                    if line.startswith("#EXTINF"):
                        break
            return meta
        except OSError:
            continue
    return meta


def _parse_extinf(line: str) -> Dict[str, Optional[str]]:
    """Parsea #EXTINF:-1 attrs...,Name"""
    payload = line[8:].strip()  # after #EXTINF:
    attrs: Dict[str, Optional[str]] = {
        "name": "",
        "tvg_id": "",
        "tvg_name": "",
        "tvg_logo": "",
        "tvg_chno": None,
        "group_name": "",
        "radio": False,
    }

    if "," in payload:
        meta, name = _split_metadata(payload)
        attrs["name"] = name.strip()
    else:
        meta = payload
        attrs["name"] = payload.strip()

    for match in ATTR_RE.finditer(meta):
        key = match.group(1)
        value = next(
            (part for part in match.groups()[1:] if part is not None), ""
        )
        key_l = key.lower()
        if key_l == "tvg-id":
            attrs["tvg_id"] = value.strip()
        elif key_l == "tvg-name":
            attrs["tvg_name"] = value.strip()
        elif key_l == "tvg-logo":
            attrs["tvg_logo"] = _normalise_logo(value)
        elif key_l == "tvg-chno":
            try:
                attrs["tvg_chno"] = int(re.sub(r"[^\d]", "", value) or "0") or None
            except ValueError:
                attrs["tvg_chno"] = None
        elif key_l == "group-title":
            attrs["group_name"] = value.split(";")[0].strip() or "Sin grupo"
        elif key_l == "radio":
            attrs["radio"] = value.strip().lower() == "true"

    if not attrs["group_name"]:
        attrs["group_name"] = "Sin grupo"
    if not attrs["name"]:
        attrs["name"] = attrs["tvg_name"] or "Canal"
    return attrs


def iter_channels_from_lines(lines: Iterable[str]) -> Generator[dict, None, None]:
    pending: Optional[dict] = None
    current_group = "Sin grupo"

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTGRP:"):
            current_group = line.split(":", 1)[1].strip() or "Sin grupo"
            continue
        if line.startswith("#EXTINF:"):
            pending = _parse_extinf(line)
            if not pending.get("group_name") or pending["group_name"] == "Sin grupo":
                pending["group_name"] = current_group
            continue
        if line.startswith("#"):
            continue
        if pending is None:
            pending = {
                "name": line,
                "tvg_id": "",
                "tvg_name": "",
                "tvg_logo": "",
                "tvg_chno": None,
                "group_name": current_group,
                "radio": False,
            }
        pending["url"] = line
        yield pending
        pending = None


def iter_channels_from_file(path: str) -> Generator[dict, None, None]:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, errors="strict") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                if encoding != "latin-1" and "\ufffd" in sample:
                    continue
                yield from iter_channels_from_lines(fh)
                return
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        yield from iter_channels_from_lines(fh)
    if last_error:
        pass
