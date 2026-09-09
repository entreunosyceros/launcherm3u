# -*- coding: utf-8 -*-
"""Regresiones del núcleo optimizado usando stubs mínimos de Kodi."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "plugin.video.launcherm3u", "resources")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeMonitor:
    def abortRequested(self):
        return False


class FakePlayer:
    last_play = None
    playing = False

    def play(self, item, listitem=None, windowed=False, *args, **kwargs):
        FakePlayer.last_play = (item, listitem, bool(windowed))
        FakePlayer.playing = True

    def stop(self):
        FakePlayer.playing = False

    def isPlaying(self):
        return FakePlayer.playing


class FakeListItem:
    def __init__(self, label="", path="", **kwargs):
        self.label = label
        self.path = path
        self.properties = {}

    def setInfo(self, *_args, **_kwargs):
        pass

    def setArt(self, *_args, **_kwargs):
        pass

    def setProperty(self, key, value):
        self.properties[key] = value

    def setMimeType(self, *_args):
        pass

    def setContentLookup(self, *_args):
        pass


class FakeWindow:
    properties = {}

    def __init__(self, _window_id):
        pass

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, "")

    def clearProperty(self, key):
        self.properties.pop(key, None)


class OptimizedCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = tempfile.TemporaryDirectory()

        xbmc = types.ModuleType("xbmc")
        xbmc.Player = FakePlayer
        xbmc.Monitor = FakeMonitor
        xbmc.sleep = lambda _ms: None
        xbmc.executebuiltin = lambda *_args: None
        xbmc.LOGINFO = 1
        xbmc.LOGERROR = 3
        xbmc.LOGWARNING = 2
        xbmc.log = lambda *_args, **_kwargs: None
        sys.modules["xbmc"] = xbmc

        xbmcgui = types.ModuleType("xbmcgui")
        xbmcgui.ListItem = FakeListItem
        xbmcgui.WindowXML = object
        xbmcgui.Window = FakeWindow
        sys.modules["xbmcgui"] = xbmcgui

        xbmcplugin = types.ModuleType("xbmcplugin")
        sys.modules["xbmcplugin"] = xbmcplugin

        vfs = types.ModuleType("xbmcvfs")
        vfs.exists = os.path.exists
        vfs.mkdirs = lambda path: os.makedirs(path, exist_ok=True)
        vfs.delete = lambda path: os.remove(path) if os.path.exists(path) else True
        vfs.translatePath = lambda path: path
        sys.modules["xbmcvfs"] = vfs

        ku = types.ModuleType("lib.kodi_utils")
        ku.ensure_profile = lambda: cls.profile.name
        ku.get_setting = lambda _key, default="": default
        ku.get_setting_bool = lambda _key, default=False: default
        ku.get_setting_int = lambda _key, default=0: default
        ku.set_setting = lambda *_args, **_kwargs: None
        ku.set_setting_bool = lambda *_args, **_kwargs: None
        ku.set_setting_int = lambda *_args, **_kwargs: None
        ku.get_string = lambda _id: ""
        ku.notify_error = lambda *_args: None
        ku.notify = lambda *_args: None
        ku.log = lambda *_args, **_kwargs: None
        ku.ADDON = types.SimpleNamespace(
            openSettings=lambda: None,
            getAddonInfo=lambda key: "1.3.0" if key == "version" else "",
        )
        ku.ADDON_ID = "plugin.video.launcherm3u"
        ku.end_directory = lambda *_args, **_kwargs: None
        ku.plugin_url = lambda **_kwargs: "plugin://plugin.video.launcherm3u/"
        sys.modules["lib.kodi_utils"] = ku

        cls.cache = importlib.import_module("lib.cache")
        cls.downloader = importlib.import_module("lib.downloader")
        # Expose ku on downloader for header tests
        cls.downloader.ku = ku
        cls.player = importlib.import_module("lib.player")
        cls.cache.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.profile.cleanup()

    @staticmethod
    def channels(count):
        for number in range(count):
            yield {
                "name": f"Channel {number:05d}",
                "url": f"http://stream/{number}.m3u8",
                "tvg_id": f"id{number}",
                "tvg_chno": number,
                "group_name": "Even" if number % 2 == 0 else "Odd",
            }

    def test_atomic_playlist_and_pagination(self):
        self.cache.replace_playlist(self.channels(1000), batch_size=250)
        self.assertEqual(self.cache.count_channels(), 1000)
        self.assertEqual(len(self.cache.list_channels(offset=100, limit=75)), 75)
        groups = {row["name"]: row["channel_count"] for row in self.cache.list_groups()}
        self.assertEqual(groups, {"Even": 500, "Odd": 500})

        def broken():
            yield from self.channels(10)
            raise ValueError("broken input")

        with self.assertRaises(ValueError):
            self.cache.replace_playlist(broken(), batch_size=5)
        self.assertEqual(self.cache.count_channels(), 1000)

    def test_ten_thousand_channels_baseline(self):
        started = time.monotonic()
        self.cache.replace_playlist(self.channels(10000), batch_size=2500)
        elapsed = time.monotonic() - started
        self.assertEqual(self.cache.count_channels(), 10000)
        self.assertLess(elapsed, 15.0)

    def test_player_uses_exact_channel_without_playlist(self):
        self.cache.replace_playlist(self.channels(3))
        rows = self.cache.list_channels(limit=3)
        target = rows[1]
        FakePlayer.last_play = None
        self.assertTrue(self.player.play_channel(target["id"], windowed=False))
        self.assertEqual(FakePlayer.last_play[0], target["url"])
        self.assertFalse(FakePlayer.last_play[2])

    def test_http_download_is_streamed_to_atomic_destination(self):
        payload = b"#EXTM3U\n" + b"x" * (2 * 1024 * 1024)

        class Headers(dict):
            def get(self, key, default=None):
                return super().get(key, default)

        class Response:
            headers = Headers()

            def __init__(self):
                self.offset = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def geturl(self):
                return "https://example.invalid/list.m3u"

            def read(self, size):
                part = payload[self.offset : self.offset + size]
                self.offset += len(part)
                return part

        dest = os.path.join(self.profile.name, "download.dat")
        meta = os.path.join(self.profile.name, "download.meta")
        with mock.patch.object(self.downloader, "urlopen", return_value=Response()):
            path, refreshed = self.downloader.fetch_url(
                "https://example.invalid/list.m3u",
                dest,
                meta,
                12,
                force=True,
                require_playlist=True,
            )
        self.assertTrue(refreshed)
        self.assertEqual(path, dest)
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), payload)
        self.assertFalse(os.path.exists(dest + ".part"))
        self.assertTrue(self.downloader.looks_like_playlist(dest))

    def test_rejects_html_error_page_as_playlist(self):
        html_path = os.path.join(self.profile.name, "error.html")
        with open(html_path, "wb") as fh:
            fh.write(b"<!DOCTYPE html><html><body>Not found</body></html>")
        self.assertFalse(self.downloader.looks_like_playlist(html_path))

    def test_normalize_http_url_keeps_query_and_gz(self):
        cases = [
            (
                "https://www.tdtchannels.com/epg/TV.xml.gz",
                "https://www.tdtchannels.com/epg/TV.xml.gz",
            ),
            (
                " http://nombredominio.cc:80/xmltv.php?usuario=nombre&password=pass ",
                "http://nombredominio.cc:80/xmltv.php?usuario=nombre&password=pass",
            ),
            (
                "http://ejemplo.cc/xmltv.php?usuario=nombre&amp;password=pass",
                "http://ejemplo.cc/xmltv.php?usuario=nombre&password=pass",
            ),
            (
                "www.tdtchannels.com/epg/TV.xml.gz",
                "https://www.tdtchannels.com/epg/TV.xml.gz",
            ),
        ]
        for raw, expected in cases:
            self.assertEqual(self.downloader.normalize_http_url(raw), expected)

        self.assertTrue(
            self.downloader.url_indicates_gzip(
                "https://www.tdtchannels.com/epg/TV.xml.gz?cache=1"
            )
        )
        self.assertFalse(
            self.downloader.url_indicates_gzip(
                "http://nombredominio.cc:80/xmltv.php?usuario=nombre&password=pass"
            )
        )

    def test_looks_like_xmltv(self):
        good = os.path.join(self.profile.name, "guide.xml")
        bad = os.path.join(self.profile.name, "login.html")
        with open(good, "wb") as fh:
            fh.write(b"<?xml version='1.0'?><tv><channel id='a'></channel></tv>")
        with open(bad, "wb") as fh:
            fh.write(b"<!DOCTYPE html><html><body>login</body></html>")
        self.assertTrue(self.downloader.looks_like_xmltv(good))
        self.assertFalse(self.downloader.looks_like_xmltv(bad))

    def test_local_gz_xmltv_is_decompressed(self):
        import gzip

        gz_path = os.path.join(self.profile.name, "TV.xml.gz")
        xml = b"<?xml version='1.0'?><tv><channel id='La1.TV'><display-name>La 1</display-name></channel></tv>"
        with gzip.open(gz_path, "wb") as fh:
            fh.write(xml)
        self.assertTrue(self.downloader.looks_like_xmltv(gz_path))
        plain = self.downloader.ensure_plain_xmltv(gz_path)
        self.assertTrue(os.path.exists(plain))
        self.assertFalse(self.downloader.file_is_gzip(plain))
        self.assertTrue(self.downloader.looks_like_xmltv(plain))
        with open(plain, "rb") as fh:
            self.assertIn(b"<tv>", fh.read())

        epg = importlib.import_module("lib.epg_parser")
        channels = []
        for kind, batch in epg.load_epg_batched(gz_path, batch_size=10):
            if kind == "channels":
                channels.extend(batch)
        self.assertEqual(channels[0][0], "La1.TV")

    def test_url_tvg_and_favorites_recents(self):
        m3u = importlib.import_module("lib.m3u_parser")
        header = '#EXTM3U url-tvg="https://www.tdtchannels.com/epg/TV.xml.gz"'
        self.assertEqual(
            m3u.extract_url_tvg_from_header(header),
            "https://www.tdtchannels.com/epg/TV.xml.gz",
        )
        path = os.path.join(self.profile.name, "list.m3u")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n")
            fh.write('#EXTINF:-1 tvg-id="La1.TV",La 1\nhttp://example/1\n')
        meta = m3u.peek_playlist_meta(path)
        self.assertIn("tdtchannels.com", meta["url_tvg"])

        self.cache.replace_playlist(
            [
                {
                    "name": "La 1",
                    "url": "http://example/1",
                    "tvg_id": "La1.TV",
                    "tvg_name": "La 1",
                    "tvg_logo": "",
                    "tvg_chno": 1,
                    "group_name": "Gen",
                    "radio": False,
                }
            ]
        )
        ch = self.cache.list_channels(limit=1)[0]
        self.assertTrue(self.cache.toggle_favorite(ch["id"]))
        self.assertTrue(self.cache.is_favorite(ch["id"]))
        self.assertEqual(self.cache.count_favorites(), 1)
        self.cache.add_recent(ch["id"])
        self.assertEqual(self.cache.count_recents(), 1)
        self.assertFalse(self.cache.toggle_favorite(ch["id"]))
        self.assertTrue(self.cache.toggle_locked(ch["id"]))
        self.assertTrue(self.cache.is_locked(ch["id"]))
        self.assertEqual(self.cache.count_locked(), 1)
        self.assertFalse(self.cache.toggle_locked(ch["id"]))
        self.assertEqual(self.cache.count_locked(), 0)

    def test_update_version_compare_and_headers(self):
        updates = importlib.import_module("lib.updates")
        self.assertTrue(updates.is_newer("1.4.0", "1.3.0"))
        self.assertFalse(updates.is_newer("1.3.0", "1.3.0"))
        release = updates.parse_github_release(
            json.dumps(
                {
                    "tag_name": "v1.4.0",
                    "html_url": "https://github.com/entreunosyceros/launcherm3u/releases/tag/v1.4.0",
                    "body": "fixes",
                    "assets": [
                        {
                            "name": "launcherm3u-1.4.0.zip",
                            "browser_download_url": "https://github.com/entreunosyceros/launcherm3u/releases/download/v1.4.0/launcherm3u-1.4.0.zip",
                        }
                    ],
                }
            )
        )
        self.assertEqual(release["version"], "1.4.0")
        self.assertIn("launcherm3u-1.4.0.zip", release["url"])
        self.assertEqual(updates.GITHUB_REPO, "entreunosyceros/launcherm3u")
        self.downloader.ku.get_setting = (
            lambda key, default="": {
                "http_user_agent": "TestAgent/1.0",
                "http_referer": "https://ref.example/",
            }.get(key, default)
        )
        headers = self.downloader.build_request_headers()
        self.assertEqual(headers["User-Agent"], "TestAgent/1.0")
        self.assertEqual(headers["Referer"], "https://ref.example/")
        url = self.downloader.apply_stream_url_headers("http://stream/1")
        self.assertIn("|", url)
        self.assertIn("User-Agent=", url)

    def test_every_toolbar_button_dispatches_once(self):
        ui = importlib.import_module("lib.ui_window")
        window = object.__new__(ui.MainWindow)
        window._ctrl_guard = {}
        window._page_size = 100
        events = []
        window._do_search = lambda: events.append("search")
        window._do_reload = lambda: events.append("reload")
        window._do_browse = lambda: events.append("browse")
        window._do_url = lambda: events.append("url")
        window._play_selected = lambda: events.append("play")
        window.close = lambda: events.append("close")
        ui.ku.ADDON = types.SimpleNamespace(
            openSettings=lambda: events.append("settings")
        )

        expected = [
            (ui.CTRL_SEARCH, "search"),
            (ui.CTRL_RELOAD, "reload"),
            (ui.CTRL_BROWSE, "browse"),
            (ui.CTRL_URL, "url"),
            (ui.CTRL_SETTINGS, "settings"),
            (ui.CTRL_CLOSE, "close"),
            (ui.CTRL_PLAY, "play"),
        ]
        for control_id, _name in expected:
            self.assertTrue(window._run_control(control_id))

        self.assertEqual(events, [name for _control_id, name in expected])

    def test_close_marker_prevents_automatic_reopen(self):
        plugin = importlib.import_module("lib.plugin")
        calls = []
        plugin.ku.end_directory = lambda *_args, **_kwargs: calls.append("end")
        plugin.xbmc.executebuiltin = lambda command: calls.append(command)
        FakeWindow.properties[ui_prop := "LauncherM3U.SuppressAutoOpen"] = str(
            time.time()
        )

        plugin.root()

        self.assertEqual(calls, ["end", "Action(Back)"])
        self.assertNotIn(ui_prop, FakeWindow.properties)


if __name__ == "__main__":
    unittest.main()
