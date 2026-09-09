# -*- coding: utf-8 -*-
"""Caché SQLite para canales, grupos y EPG."""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Tuple

from . import kodi_utils as ku

DB_NAME = "launcherm3u.db"

_EPG_INDEX = None
_EPG_INDEX_TS = 0.0

_NORM_RE = re.compile(r"[^a-z0-9]+")
_BRACKETS_RE = re.compile(r"\[.*?\]|\(.*?\)")
_QUALITY_RE = re.compile(
    r"\b(hd|fhd|uhd|4k|8k|hevc|h265|h264|sd|hq|fhd|fullhd)\b", re.I
)


def db_path() -> str:
    return os.path.join(ku.ensure_profile(), DB_NAME)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-16384")
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                channel_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                tvg_id TEXT,
                tvg_name TEXT,
                tvg_logo TEXT,
                tvg_chno INTEGER,
                group_name TEXT,
                radio INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_channels_group ON channels(group_name);
            CREATE INDEX IF NOT EXISTS idx_channels_name ON channels(name);
            CREATE INDEX IF NOT EXISTS idx_channels_tvg_id ON channels(tvg_id);
            CREATE INDEX IF NOT EXISTS idx_channels_group_order
                ON channels(group_name, tvg_chno, name COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS epg_channels (
                id TEXT PRIMARY KEY,
                display_name TEXT
            );

            CREATE TABLE IF NOT EXISTS programmes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                start_ts INTEGER NOT NULL,
                stop_ts INTEGER NOT NULL,
                title TEXT,
                description TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_prog_channel_time
                ON programmes(channel_id, start_ts, stop_ts);

            CREATE TABLE IF NOT EXISTS favorites (
                url TEXT PRIMARY KEY,
                name TEXT,
                added_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recents (
                url TEXT PRIMARY KEY,
                name TEXT,
                tvg_logo TEXT,
                channel_id INTEGER,
                watched_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS locked_channels (
                url TEXT PRIMARY KEY,
                name TEXT,
                added_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_recents_watched
                ON recents(watched_at DESC);
            """
        )


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str, default: Optional[str] = None) -> Optional[str]:
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def get_metas(*keys: str) -> Dict[str, str]:
    """Lee varias claves en una sola conexión."""
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM meta WHERE key IN ({placeholders})", keys
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def clear_playlist() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM channels")
        conn.execute("DELETE FROM groups")


def clear_epg() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM programmes")
        conn.execute("DELETE FROM epg_channels")
    invalidate_epg_index()


def normalize_epg_key(value: str) -> str:
    """Normaliza ids/nombres para emparejar M3U ↔ XMLTV."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = _BRACKETS_RE.sub(" ", text)
    text = _QUALITY_RE.sub(" ", text)
    if text.endswith(".tv"):
        text = text[:-3]
    text = text.replace("&", " and ")
    return _NORM_RE.sub("", text)


def invalidate_epg_index() -> None:
    global _EPG_INDEX, _EPG_INDEX_TS
    _EPG_INDEX = None
    _EPG_INDEX_TS = 0.0


def get_epg_index(force: bool = False) -> Dict[str, Dict[str, str]]:
    """
    Índice EPG:
      - by_lower: id exacto en minúsculas -> id real
      - by_norm: clave normalizada (id o display-name) -> id real
    """
    global _EPG_INDEX, _EPG_INDEX_TS
    if _EPG_INDEX is not None and not force and (time.time() - _EPG_INDEX_TS) < 300:
        return _EPG_INDEX

    by_lower: Dict[str, str] = {}
    by_norm: Dict[str, str] = {}
    with connect() as conn:
        rows = conn.execute("SELECT id, display_name FROM epg_channels").fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT DISTINCT channel_id AS id, channel_id AS display_name "
                "FROM programmes"
            ).fetchall()
        for row in rows:
            cid = (row["id"] or "").strip()
            if not cid:
                continue
            by_lower[cid.lower()] = cid
            for candidate in (cid, row["display_name"] or ""):
                key = normalize_epg_key(candidate)
                if key and key not in by_norm:
                    by_norm[key] = cid
                # Variante sin sufijo .tv ya cubierta por normalize;
                # también indexar "la1tv" si el id es La1.TV
                if candidate.lower().endswith(".tv"):
                    key2 = normalize_epg_key(candidate[:-3])
                    if key2 and key2 not in by_norm:
                        by_norm[key2] = cid

    _EPG_INDEX = {"by_lower": by_lower, "by_norm": by_norm}
    _EPG_INDEX_TS = time.time()
    return _EPG_INDEX


def resolve_epg_channel_id(
    tvg_id: str = "",
    tvg_name: str = "",
    name: str = "",
) -> str:
    """
    Resuelve el channel id XMLTV a usar para consultas EPG.
    Prueba tvg-id, tvg-name y nombre del canal con coincidencia flexible.
    """
    index = get_epg_index()
    by_lower = index["by_lower"]
    by_norm = index["by_norm"]
    if not by_lower and not by_norm:
        return (tvg_id or "").strip()

    candidates = []
    for value in (tvg_id, tvg_name, name):
        text = (value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    for text in candidates:
        low = text.lower()
        if low in by_lower:
            return by_lower[low]
        # Sufijos habituales IPTV / TDTChannels
        for suffix in (".tv", ".TV"):
            alt = text + suffix
            if alt.lower() in by_lower:
                return by_lower[alt.lower()]
        if low.endswith(".tv") and low[:-3] in by_lower:
            return by_lower[low[:-3]]

    for text in candidates:
        key = normalize_epg_key(text)
        if key and key in by_norm:
            return by_norm[key]

    return (tvg_id or "").strip()


def count_epg_links() -> Tuple[int, int]:
    """Devuelve (canales_con_epg, total_canales)."""
    get_epg_index(force=True)
    with connect() as conn:
        channels = conn.execute(
            "SELECT tvg_id, tvg_name, name FROM channels WHERE INSTR(name, '#') = 0"
        ).fetchall()
        prog_ids = {
            row[0]
            for row in conn.execute("SELECT DISTINCT channel_id FROM programmes")
        }
    if not channels:
        return 0, 0
    linked = 0
    for ch in channels:
        epg_id = resolve_epg_channel_id(ch["tvg_id"], ch["tvg_name"], ch["name"])
        if epg_id and epg_id in prog_ids:
            linked += 1
    return linked, len(channels)


def replace_epg(channels: Iterable[Tuple[str, str]], programmes: Iterable[tuple]) -> int:
    clear_epg()
    channel_rows = list(channels)
    programme_rows = list(programmes)
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO epg_channels(id, display_name) VALUES (?, ?)",
            channel_rows,
        )
        conn.executemany(
            """
            INSERT INTO programmes(channel_id, start_ts, stop_ts, title, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            programme_rows,
        )
    set_meta("epg_loaded_at", str(int(time.time())))
    set_meta("programme_count", str(len(programme_rows)))
    invalidate_epg_index()
    return len(programme_rows)


def now_playing_map(tvg_ids: List[str], now_ts: Optional[int] = None) -> Dict[str, sqlite3.Row]:
    """Devuelve el programa actual indexado por el tvg_id/original pedido."""
    if not tvg_ids:
        return {}
    now_ts = now_ts or int(time.time())
    original_to_epg: Dict[str, str] = {}
    epg_ids: List[str] = []
    for tid in tvg_ids:
        epg_id = resolve_epg_channel_id(tid)
        if not epg_id:
            continue
        original_to_epg[tid] = epg_id
        epg_ids.append(epg_id)
    if not epg_ids:
        return {}

    unique_ids = list(dict.fromkeys(epg_ids))
    placeholders = ",".join("?" * len(unique_ids))
    sql = f"""
        SELECT p.* FROM programmes p
        INNER JOIN (
            SELECT channel_id, MAX(start_ts) AS max_start
            FROM programmes
            WHERE channel_id IN ({placeholders})
              AND start_ts <= ? AND stop_ts > ?
            GROUP BY channel_id
        ) cur ON p.channel_id = cur.channel_id AND p.start_ts = cur.max_start
    """
    params = unique_ids + [now_ts, now_ts]
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    by_epg = {row["channel_id"]: row for row in rows}
    return {
        original: by_epg[epg_id]
        for original, epg_id in original_to_epg.items()
        if epg_id in by_epg
    }


def now_playing_for_channels(
    channels: List[sqlite3.Row], now_ts: Optional[int] = None
) -> Dict[int, sqlite3.Row]:
    """Programa actual indexado por id interno del canal M3U."""
    if not channels:
        return {}
    now_ts = now_ts or int(time.time())
    channel_to_epg: Dict[int, str] = {}
    epg_ids: List[str] = []
    for ch in channels:
        epg_id = resolve_epg_channel_id(ch["tvg_id"], ch["tvg_name"], ch["name"])
        if not epg_id:
            continue
        channel_to_epg[int(ch["id"])] = epg_id
        epg_ids.append(epg_id)
    if not epg_ids:
        return {}

    unique_ids = list(dict.fromkeys(epg_ids))
    placeholders = ",".join("?" * len(unique_ids))
    sql = f"""
        SELECT p.* FROM programmes p
        INNER JOIN (
            SELECT channel_id, MAX(start_ts) AS max_start
            FROM programmes
            WHERE channel_id IN ({placeholders})
              AND start_ts <= ? AND stop_ts > ?
            GROUP BY channel_id
        ) cur ON p.channel_id = cur.channel_id AND p.start_ts = cur.max_start
    """
    with connect() as conn:
        rows = conn.execute(sql, unique_ids + [now_ts, now_ts]).fetchall()
    by_epg = {row["channel_id"]: row for row in rows}
    return {
        cid: by_epg[epg_id]
        for cid, epg_id in channel_to_epg.items()
        if epg_id in by_epg
    }


def get_now_and_next(
    tvg_id: str,
    now_ts: Optional[int] = None,
    tvg_name: str = "",
    name: str = "",
) -> Tuple[Optional[sqlite3.Row], Optional[sqlite3.Row]]:
    epg_id = resolve_epg_channel_id(tvg_id, tvg_name, name)
    if not epg_id:
        return None, None
    now_ts = now_ts or int(time.time())
    with connect() as conn:
        now_row = conn.execute(
            """
            SELECT * FROM programmes
            WHERE channel_id=? AND start_ts <= ? AND stop_ts > ?
            ORDER BY start_ts DESC LIMIT 1
            """,
            (epg_id, now_ts, now_ts),
        ).fetchone()
        next_row = conn.execute(
            """
            SELECT * FROM programmes
            WHERE channel_id=? AND start_ts > ?
            ORDER BY start_ts ASC LIMIT 1
            """,
            (epg_id, now_ts),
        ).fetchone()
        # Hueco entre programas: mostrar el más cercano futuro o el último reciente
        if now_row is None and next_row is None:
            now_row = conn.execute(
                """
                SELECT * FROM programmes
                WHERE channel_id=? AND stop_ts <= ?
                ORDER BY stop_ts DESC LIMIT 1
                """,
                (epg_id, now_ts),
            ).fetchone()
            next_row = conn.execute(
                """
                SELECT * FROM programmes
                WHERE channel_id=? AND start_ts > ?
                ORDER BY start_ts ASC LIMIT 1
                """,
                (epg_id, now_ts),
            ).fetchone()
    return now_row, next_row


def get_programmes(tvg_id: str, from_ts: int, to_ts: int,
                   tvg_name: str = "", name: str = "") -> List[sqlite3.Row]:
    epg_id = resolve_epg_channel_id(tvg_id, tvg_name, name)
    if not epg_id:
        return []
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT * FROM programmes
                WHERE channel_id=? AND stop_ts >= ? AND start_ts <= ?
                ORDER BY start_ts ASC
                """,
                (epg_id, from_ts, to_ts),
            )
        )

def replace_playlist(channels: Iterable[dict], batch_size: int = 2500,
                     yield_ui: bool = False) -> int:
    """Sustituye la lista atómicamente; un fallo conserva la anterior."""
    group_counts: Dict[str, int] = {}
    total = 0
    batch = []
    monitor = None
    if yield_ui:
        try:
            import xbmc

            if callable(getattr(xbmc, "Monitor", None)):
                monitor = xbmc.Monitor()
        except Exception:
            monitor = None

    def flush(conn, rows):
        if not rows:
            return
        conn.executemany(
            """
            INSERT INTO channels(name, url, tvg_id, tvg_name, tvg_logo, tvg_chno, group_name, radio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    with connect() as conn:
        conn.execute("DELETE FROM channels")
        conn.execute("DELETE FROM groups")
        for ch in channels:
            try:
                if monitor is not None and monitor.abortRequested():
                    raise RuntimeError("Carga M3U cancelada")
            except RuntimeError:
                raise
            except Exception:
                pass
            name = ch.get("name") or "Canal"
            # Separadores IPTV: cualquier nombre con # (####, ###, ##, # ...)
            if "#" in name:
                continue
            group = ch.get("group_name") or "Sin grupo"
            group_counts[group] = group_counts.get(group, 0) + 1
            batch.append(
                (
                    name,
                    ch.get("url") or "",
                    ch.get("tvg_id") or "",
                    ch.get("tvg_name") or "",
                    ch.get("tvg_logo") or "",
                    ch.get("tvg_chno"),
                    group,
                    1 if ch.get("radio") else 0,
                )
            )
            if len(batch) >= batch_size:
                flush(conn, batch)
                total += len(batch)
                batch = []
                if yield_ui and total % 10000 == 0:
                    try:
                        import xbmc

                        xbmc.sleep(0)
                    except Exception:
                        pass
        flush(conn, batch)
        total += len(batch)
        conn.executemany(
            "INSERT INTO groups(name, channel_count) VALUES (?, ?)",
            sorted(group_counts.items(), key=lambda x: x[0].lower()),
        )
        now = str(int(time.time()))
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (("playlist_loaded_at", now), ("channel_count", str(total))),
        )
    return total


def list_groups() -> List[sqlite3.Row]:
    """Lee el resumen precalculado, evitando GROUP BY sobre canales."""
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT name, channel_count
                FROM groups
                WHERE channel_count > 0
                ORDER BY name COLLATE NOCASE
                """
            )
        )


def count_channels(group_name: Optional[str] = None, query: Optional[str] = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM channels WHERE INSTR(name, '#') = 0"
    params: list = []
    if group_name:
        sql += " AND group_name=?"
        params.append(group_name)
    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    with connect() as conn:
        return int(conn.execute(sql, params).fetchone()["c"])


def list_channels(group_name: Optional[str] = None, query: Optional[str] = None,
                  offset: int = 0, limit: Optional[int] = 100) -> List[sqlite3.Row]:
    """Lista canales. Omite nombres con # (separadores IPTV)."""
    sql = (
        "SELECT id, name, url, tvg_id, tvg_name, tvg_logo, tvg_chno, group_name, radio "
        "FROM channels WHERE INSTR(name, '#') = 0"
    )
    params: list = []
    if group_name:
        sql += " AND group_name=?"
        params.append(group_name)
    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY COALESCE(tvg_chno, 999999), name COLLATE NOCASE"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with connect() as conn:
        return list(conn.execute(sql, params))


def get_channel(channel_id: int) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM channels WHERE id=?", (channel_id,)
        ).fetchone()


def get_channel_by_url(url: str) -> Optional[sqlite3.Row]:
    if not url:
        return None
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM channels WHERE url=? AND INSTR(name, '#') = 0 LIMIT 1",
            (url,),
        ).fetchone()


def toggle_favorite(channel_id: int) -> bool:
    """Añade o quita favorito. Devuelve True si queda como favorito."""
    ch = get_channel(channel_id)
    if not ch or not ch["url"]:
        return False
    with connect() as conn:
        row = conn.execute(
            "SELECT url FROM favorites WHERE url=?", (ch["url"],)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM favorites WHERE url=?", (ch["url"],))
            return False
        conn.execute(
            "INSERT INTO favorites(url, name, added_at) VALUES (?, ?, ?)",
            (ch["url"], ch["name"] or "", int(time.time())),
        )
        return True


def is_favorite_url(url: str) -> bool:
    if not url:
        return False
    with connect() as conn:
        return (
            conn.execute(
                "SELECT 1 AS ok FROM favorites WHERE url=? LIMIT 1", (url,)
            ).fetchone()
            is not None
        )


def is_favorite(channel_id: int) -> bool:
    ch = get_channel(channel_id)
    return bool(ch and is_favorite_url(ch["url"] or ""))


def count_favorites() -> int:
    with connect() as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) AS c FROM favorites f
                INNER JOIN channels c ON c.url = f.url
                WHERE INSTR(c.name, '#') = 0
                """
            ).fetchone()["c"]
        )


def list_favorites(offset: int = 0, limit: Optional[int] = 100) -> List[sqlite3.Row]:
    sql = """
        SELECT c.id, c.name, c.url, c.tvg_id, c.tvg_name, c.tvg_logo,
               c.tvg_chno, c.group_name, c.radio
        FROM favorites f
        INNER JOIN channels c ON c.url = f.url
        WHERE INSTR(c.name, '#') = 0
        ORDER BY f.added_at DESC, c.name COLLATE NOCASE
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with connect() as conn:
        return list(conn.execute(sql, params))


def add_recent(channel_id: int, max_items: int = 40) -> None:
    ch = get_channel(channel_id)
    if not ch or not ch["url"]:
        return
    now = int(time.time())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO recents(url, name, tvg_logo, channel_id, watched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                name=excluded.name,
                tvg_logo=excluded.tvg_logo,
                channel_id=excluded.channel_id,
                watched_at=excluded.watched_at
            """,
            (
                ch["url"],
                ch["name"] or "",
                ch["tvg_logo"] or "",
                int(ch["id"]),
                now,
            ),
        )
        # Mantener solo los N más recientes
        conn.execute(
            """
            DELETE FROM recents WHERE url NOT IN (
                SELECT url FROM recents ORDER BY watched_at DESC LIMIT ?
            )
            """,
            (max(5, int(max_items)),),
        )


def count_recents() -> int:
    with connect() as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) AS c FROM recents r
                INNER JOIN channels c ON c.url = r.url
                WHERE INSTR(c.name, '#') = 0
                """
            ).fetchone()["c"]
        )


def list_recents(offset: int = 0, limit: Optional[int] = 100) -> List[sqlite3.Row]:
    sql = """
        SELECT c.id, c.name, c.url, c.tvg_id, c.tvg_name, c.tvg_logo,
               c.tvg_chno, c.group_name, c.radio
        FROM recents r
        INNER JOIN channels c ON c.url = r.url
        WHERE INSTR(c.name, '#') = 0
        ORDER BY r.watched_at DESC
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with connect() as conn:
        return list(conn.execute(sql, params))


def prune_old_programmes(keep_hours: int) -> int:
    """Borra programas terminados hace más de keep_hours. Devuelve filas borradas."""
    if keep_hours <= 0:
        return 0
    cutoff = int(time.time()) - int(keep_hours) * 3600
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM programmes WHERE stop_ts < ?", (cutoff,)
        )
        deleted = cur.rowcount if cur.rowcount is not None else 0
        if deleted:
            row = conn.execute("SELECT COUNT(*) AS c FROM programmes").fetchone()
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("programme_count", str(int(row["c"]))),
            )
        return int(deleted or 0)


def toggle_locked(channel_id: int) -> bool:
    """Añade o quita bloqueo parental. Devuelve True si queda bloqueado."""
    ch = get_channel(channel_id)
    if not ch or not ch["url"]:
        return False
    with connect() as conn:
        row = conn.execute(
            "SELECT url FROM locked_channels WHERE url=?", (ch["url"],)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM locked_channels WHERE url=?", (ch["url"],))
            return False
        conn.execute(
            "INSERT INTO locked_channels(url, name, added_at) VALUES (?, ?, ?)",
            (ch["url"], ch["name"] or "", int(time.time())),
        )
        return True


def is_locked_url(url: str) -> bool:
    if not url:
        return False
    with connect() as conn:
        return (
            conn.execute(
                "SELECT 1 AS ok FROM locked_channels WHERE url=? LIMIT 1", (url,)
            ).fetchone()
            is not None
        )


def is_locked(channel_id: int) -> bool:
    ch = get_channel(channel_id)
    return bool(ch and is_locked_url(ch["url"] or ""))


def clear_locked_channels() -> int:
    with connect() as conn:
        cur = conn.execute("DELETE FROM locked_channels")
        return int(cur.rowcount or 0)


def count_locked() -> int:
    with connect() as conn:
        return int(
            conn.execute("SELECT COUNT(*) AS c FROM locked_channels").fetchone()["c"]
        )


def wipe_all() -> None:
    clear_playlist()
    clear_epg()
    with connect() as conn:
        conn.execute("DELETE FROM meta")
        conn.execute("DELETE FROM favorites")
        conn.execute("DELETE FROM recents")
        conn.execute("DELETE FROM locked_channels")
