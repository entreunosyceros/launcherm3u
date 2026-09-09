# -*- coding: utf-8 -*-
"""Control único de reproducción para preview y pantalla completa."""

from __future__ import annotations

import time

import xbmc
import xbmcgui

from . import cache
from . import downloader
from . import kodi_utils as ku


class PlaybackController:
    """Mantiene una sola instancia de Player y el canal realmente activo."""

    def __init__(self) -> None:
        self.player = xbmc.Player()
        self.channel_id = 0
        self.url = ""
        self.windowed = False

    def stop(self) -> None:
        if self.player.isPlaying():
            try:
                self.player.stop()
            except Exception as exc:
                ku.log(f"Error deteniendo reproducción: {exc}", level=2)
        self.windowed = False

    def play(self, channel_id: int, windowed: bool) -> bool:
        from . import parental

        if not parental.ensure_channel_unlocked(int(channel_id)):
            return False

        ch = cache.get_channel(channel_id)
        if not ch or not ch["url"]:
            ku.notify_error(ku.get_string(30212) or "Canal no encontrado")
            return False

        url = downloader.apply_stream_url_headers(ch["url"])
        item = build_listitem(ch, with_epg=False, play_url=url)
        started = time.monotonic()
        try:
            self.player.play(url, item, bool(windowed))
        except Exception as exc:
            ku.log(f"Player.play falló: {exc}", level=3)
            ku.notify_error(ku.get_string(30212) or "No se pudo reproducir")
            return False

        self.channel_id = int(channel_id)
        self.url = url
        self.windowed = bool(windowed)
        try:
            cache.add_recent(int(channel_id))
        except Exception as exc:
            ku.log(f"No se pudo guardar reciente: {exc}", level=2)
        ku.log(
            "playback mode={0} channel={1} start_ms={2}".format(
                "preview" if windowed else "fullscreen",
                channel_id,
                int((time.monotonic() - started) * 1000),
            )
        )
        return True


_CONTROLLER = PlaybackController()


def _apply_stream_properties(item: xbmcgui.ListItem, url: str) -> None:
    headers_q = downloader.stream_headers_query()
    use_is = ku.get_setting_bool("use_inputstream", False)
    lower = (url or "").lower()
    is_hls = ".m3u8" in lower or "format=m3u8" in lower or "m3u8" in lower
    is_dash = ".mpd" in lower

    if use_is and (is_hls or is_dash):
        item.setProperty("inputstream", "inputstream.adaptive")
        item.setProperty(
            "inputstream.adaptive.manifest_type", "hls" if is_hls else "mpd"
        )
        if headers_q:
            item.setProperty("inputstream.adaptive.stream_headers", headers_q)
            item.setProperty("inputstream.adaptive.manifest_headers", headers_q)
            try:
                item.setProperty("inputstream.adaptive.common_headers", headers_q)
            except Exception:
                pass


def build_listitem(ch, with_epg: bool = False, play_url: str = "") -> xbmcgui.ListItem:
    name = ch["name"]
    logo = (
        ch["tvg_logo"] or "DefaultTVShows.png"
        if ku.get_setting_bool("show_channel_logos", True)
        else ""
    )
    title = name
    plot = ch["group_name"] or ""
    if with_epg:
        now_row, _ = cache.get_now_and_next(
            ch["tvg_id"] or "",
            tvg_name=ch["tvg_name"] or "",
            name=ch["name"] or "",
        )
        if now_row:
            title = f"{name} - {now_row['title']}"
            plot = now_row["description"] or now_row["title"] or plot

    url = play_url or downloader.apply_stream_url_headers(ch["url"] or "")
    item = xbmcgui.ListItem(label=name, path=url)
    item.setInfo("video", {"title": title, "plot": plot, "mediatype": "video"})
    if logo:
        item.setArt({"icon": logo, "thumb": logo, "poster": logo})
    item.setProperty("IsPlayable", "true")
    item.setProperty("channel_id", str(ch["id"]))
    item.setProperty("group_name", ch["group_name"] or "")
    try:
        if ".m3u8" in (ch["url"] or "").lower():
            item.setMimeType("application/x-mpegURL")
            item.setContentLookup(False)
    except Exception:
        pass
    _apply_stream_properties(item, ch["url"] or "")
    return item


def play_channel(channel_id: int, notify_zap: bool = False, windowed: bool = False) -> bool:
    """
    Reproduce un canal.
    - windowed=True: vista previa en videowindow
    - windowed=False: pantalla completa SOLO de ese canal (sin playlist)
    """
    return _CONTROLLER.play(int(channel_id), bool(windowed))


def preview_channel(channel_id: int) -> bool:
    return play_channel(channel_id, notify_zap=False, windowed=True)


def stop_playback() -> None:
    _CONTROLLER.stop()


def active_channel_id() -> int:
    return _CONTROLLER.channel_id


def select_audio_stream() -> None:
    player = _CONTROLLER.player
    if not player.isPlaying():
        ku.notify(ku.get_string(30512) or "No hay reproducción activa")
        return
    streams = []
    try:
        if hasattr(player, "getAvailableAudioStreams"):
            streams = list(player.getAvailableAudioStreams() or [])
    except Exception as exc:
        ku.log(f"Audio streams: {exc}", level=2)
    if not streams:
        ku.notify(ku.get_string(30513) or "No hay pistas de audio")
        return
    labels = [str(s) if s else f"Audio {i+1}" for i, s in enumerate(streams)]
    choice = xbmcgui.Dialog().select(
        ku.get_string(30510) or "Pista de audio", labels
    )
    if choice < 0:
        return
    try:
        player.setAudioStream(choice)
        ku.notify(labels[choice])
    except Exception as exc:
        ku.notify_error(str(exc))


def select_subtitle_stream() -> None:
    player = _CONTROLLER.player
    if not player.isPlaying():
        ku.notify(ku.get_string(30512) or "No hay reproducción activa")
        return
    streams = []
    try:
        if hasattr(player, "getAvailableSubtitleStreams"):
            streams = list(player.getAvailableSubtitleStreams() or [])
    except Exception as exc:
        ku.log(f"Subtitle streams: {exc}", level=2)

    labels = [ku.get_string(30514) or "Desactivar subtítulos"]
    labels.extend(
        [str(s) if s else f"Sub {i+1}" for i, s in enumerate(streams)]
    )
    choice = xbmcgui.Dialog().select(
        ku.get_string(30511) or "Subtítulos", labels
    )
    if choice < 0:
        return
    try:
        if choice == 0:
            if hasattr(player, "showSubtitles"):
                player.showSubtitles(False)
            ku.notify(ku.get_string(30514) or "Subtítulos desactivados")
            return
        idx = choice - 1
        player.setSubtitleStream(idx)
        if hasattr(player, "showSubtitles"):
            player.showSubtitles(True)
        ku.notify(labels[choice])
    except Exception as exc:
        ku.notify_error(str(exc))
