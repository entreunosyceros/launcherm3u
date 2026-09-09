# -*- coding: utf-8 -*-
"""Parser XMLTV en streaming (iterparse) para EPG grandes."""

from __future__ import annotations

import gzip
import re
from datetime import datetime, timezone
from typing import Generator, Iterable, List, Optional, Tuple
from xml.etree.ElementTree import iterparse

# 20240101120000 +0000 / 20240101120000+0000 / 20240101120000
TS_RE = re.compile(
    r"^(?P<date>\d{14})(?:\s*(?P<tz>[+-]\d{4}|[A-Z]{1,5}))?$"
)


def parse_xmltv_time(value: str) -> Optional[int]:
    if not value:
        return None
    value = value.strip()
    match = TS_RE.match(value)
    if not match:
        # Intento ISO suelto
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None

    date = match.group("date")
    tz = match.group("tz") or "+0000"
    try:
        dt = datetime.strptime(date, "%Y%m%d%H%M%S")
    except ValueError:
        return None

    if re.fullmatch(r"[+-]\d{4}", tz):
        sign = 1 if tz[0] == "+" else -1
        hours = int(tz[1:3])
        minutes = int(tz[3:5])
        offset = sign * (hours * 3600 + minutes * 60)
        # Interpretar como hora local del offset y convertir a UTC epoch
        epoch = int(dt.replace(tzinfo=timezone.utc).timestamp()) - offset
        return epoch

    # Sin offset usable: asumir UTC
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _text(elem) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _open_xml(path: str):
    """Abre XMLTV plano o gzip (por extensión o magic bytes)."""
    lower = (path or "").lower()
    use_gzip = lower.endswith(".gz") or lower.endswith(".gzip")
    if not use_gzip:
        try:
            with open(path, "rb") as fh:
                use_gzip = fh.read(2) == b"\x1f\x8b"
        except OSError:
            use_gzip = False
    if use_gzip:
        return gzip.open(path, "rb")
    return open(path, "rb")


def iter_epg(path: str) -> Tuple[List[Tuple[str, str]], Generator[tuple, None, None]]:
    """
    Devuelve (lista_canales, generador_programas).
    Los canales se materializan primero (suelen ser pocos);
    los programas se generan en streaming.
    """
    channels: List[Tuple[str, str]] = []

    # Primera pasada ligera solo para channels sería ideal, pero en XMLTV
    # channel suele ir antes. Hacemos una sola pasada con generador diferido.
    def programmes() -> Generator[tuple, None, None]:
        nonlocal channels
        channels_seen = set()
        with _open_xml(path) as fh:
            context = iterparse(fh, events=("end",))
            for _event, elem in context:
                tag = elem.tag
                if "}" in tag:
                    tag = tag.rsplit("}", 1)[-1]

                if tag == "channel":
                    cid = elem.get("id") or ""
                    display = ""
                    for child in elem:
                        ctag = child.tag.rsplit("}", 1)[-1]
                        if ctag == "display-name":
                            display = _text(child)
                            break
                    if cid and cid not in channels_seen:
                        channels_seen.add(cid)
                        channels.append((cid, display or cid))
                    elem.clear()
                elif tag == "programme":
                    cid = elem.get("channel") or ""
                    start_ts = parse_xmltv_time(elem.get("start", ""))
                    stop_ts = parse_xmltv_time(elem.get("stop", ""))
                    title = ""
                    desc = ""
                    for child in elem:
                        ctag = child.tag.rsplit("}", 1)[-1]
                        if ctag == "title" and not title:
                            title = _text(child)
                        elif ctag == "desc" and not desc:
                            desc = _text(child)
                    elem.clear()
                    if cid and start_ts is not None and stop_ts is not None:
                        yield (cid, start_ts, stop_ts, title, desc)
                else:
                    # Liberar memoria de nodos ya procesados de alto nivel
                    if tag in ("tv",):
                        elem.clear()

    # Materializar canales y programas en un solo recorrido es complicado
    # porque el caller necesita channels antes. Alternativa: dos pasadas
    # o acumular channels durante la inserción.
    # Aquí devolvemos un wrapper que rellena channels al consumir programmes.
    return channels, programmes()


def load_epg_into_lists(path: str) -> Tuple[List[Tuple[str, str]], List[tuple]]:
    """Carga EPG en listas (streaming de parseo; materializa al final)."""
    channels: List[Tuple[str, str]] = []
    programmes: List[tuple] = []
    channels_seen = set()

    with _open_xml(path) as fh:
        for _event, elem in iterparse(fh, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag == "channel":
                cid = elem.get("id") or ""
                display = ""
                for child in elem:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "display-name":
                        display = _text(child)
                        break
                if cid and cid not in channels_seen:
                    channels_seen.add(cid)
                    channels.append((cid, display or cid))
                elem.clear()
            elif tag == "programme":
                cid = elem.get("channel") or ""
                start_ts = parse_xmltv_time(elem.get("start", ""))
                stop_ts = parse_xmltv_time(elem.get("stop", ""))
                title = ""
                desc = ""
                for child in elem:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "title" and not title:
                        title = _text(child)
                    elif ctag == "desc" and not desc:
                        desc = _text(child)
                if cid and start_ts is not None and stop_ts is not None:
                    programmes.append((cid, start_ts, stop_ts, title, desc))
                elem.clear()
    return channels, programmes


def load_epg_batched(path: str, batch_size: int = 5000) -> Generator:
    """
    Genera lotes para inserción incremental.
    Yields: ("channels", [(id, name), ...]) o ("programmes", [tuples...])
    """
    channel_batch: List[Tuple[str, str]] = []
    programme_batch: List[tuple] = []
    channels_seen = set()
    channels_emitted = False

    with _open_xml(path) as fh:
        for _event, elem in iterparse(fh, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag == "channel":
                cid = elem.get("id") or ""
                display = ""
                for child in elem:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "display-name":
                        display = _text(child)
                        break
                if cid and cid not in channels_seen:
                    channels_seen.add(cid)
                    channel_batch.append((cid, display or cid))
                    if len(channel_batch) >= batch_size:
                        yield ("channels", channel_batch)
                        channel_batch = []
                elem.clear()
            elif tag == "programme":
                if channel_batch:
                    yield ("channels", channel_batch)
                    channel_batch = []
                    channels_emitted = True
                elif not channels_emitted:
                    channels_emitted = True

                cid = elem.get("channel") or ""
                start_ts = parse_xmltv_time(elem.get("start", ""))
                stop_ts = parse_xmltv_time(elem.get("stop", ""))
                title = ""
                desc = ""
                for child in elem:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "title" and not title:
                        title = _text(child)
                    elif ctag == "desc" and not desc:
                        desc = _text(child)
                if cid and start_ts is not None and stop_ts is not None:
                    programme_batch.append((cid, start_ts, stop_ts, title, desc))
                    if len(programme_batch) >= batch_size:
                        yield ("programmes", programme_batch)
                        programme_batch = []
                elem.clear()

    if channel_batch:
        yield ("channels", channel_batch)
    if programme_batch:
        yield ("programmes", programme_batch)
