# -*- coding: utf-8 -*-
"""Pruebas unitarias del parser M3U (sin Kodi)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "plugin.video.launcherm3u", "resources")
)
sys.path.insert(0, ROOT)

from lib.m3u_parser import iter_channels_from_file, iter_channels_from_lines  # noqa: E402
from lib.epg_parser import parse_xmltv_time  # noqa: E402


SAMPLE = """#EXTM3U
#EXTINF:-1 tvg-id="ch1" tvg-name="One" tvg-logo="http://logo/1.png" tvg-chno="1" group-title="News",Channel One
http://example.com/1.ts
#EXTINF:-1 tvg-id="ch2" group-title="Sports;Extra" radio="false",Channel Two
http://example.com/2.m3u8
#EXTGRP:Music
#EXTINF:-1,Radio FM
http://example.com/radio
"""


class M3UParserTests(unittest.TestCase):
    def test_parse_lines(self):
        channels = list(iter_channels_from_lines(SAMPLE.splitlines()))
        self.assertEqual(len(channels), 3)
        self.assertEqual(channels[0]["name"], "Channel One")
        self.assertEqual(channels[0]["tvg_id"], "ch1")
        self.assertEqual(channels[0]["tvg_chno"], 1)
        self.assertEqual(channels[0]["group_name"], "News")
        self.assertEqual(channels[1]["group_name"], "Sports")
        self.assertEqual(channels[2]["group_name"], "Music")
        self.assertEqual(channels[2]["url"], "http://example.com/radio")

    def test_parse_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".m3u", delete=False, encoding="utf-8") as fh:
            fh.write(SAMPLE)
            path = fh.name
        try:
            channels = list(iter_channels_from_file(path))
            self.assertEqual(len(channels), 3)
        finally:
            os.unlink(path)

    def test_logo_variants_and_channel_name_with_comma(self):
        source = [
            "#EXTM3U",
            "#EXTINF:-1 tvg-logo='//cdn.example/logo.png?a=1&amp;b=2',News, Europe",
            "https://stream.example/live.m3u8",
        ]
        channels = list(iter_channels_from_lines(source))
        self.assertEqual(channels[0]["name"], "News, Europe")
        self.assertEqual(
            channels[0]["tvg_logo"],
            "https://cdn.example/logo.png?a=1&b=2",
        )


class EPGTimeTests(unittest.TestCase):
    def test_parse_with_offset(self):
        ts = parse_xmltv_time("20240101120000 +0000")
        self.assertIsNotNone(ts)
        self.assertEqual(ts, parse_xmltv_time("20240101120000+0000"))


if __name__ == "__main__":
    unittest.main()
