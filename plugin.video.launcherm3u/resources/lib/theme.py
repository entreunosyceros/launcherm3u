# -*- coding: utf-8 -*-
"""Paletas de color e iconos de la interfaz IPTV."""

from __future__ import annotations

import os
import shutil
from typing import Dict

import xbmcvfs

from . import kodi_utils as ku

# id de ajuste ui_palette -> colores AARRGGBB
PALETTES: Dict[int, Dict[str, str]] = {
    0: {  # Azul
        "name": "blue",
        "bg": "FF0B1220",
        "bg_tint": "332A6FDB",
        "header": "EE111827",
        "panel": "CC111827",
        "accent": "FF2563EB",
        "accent_soft": "992563EB",
        "accent_row": "FF1D4ED8",
        "accent_label": "FF93C5FD",
        "accent_mid": "FF60A5FA",
        "scroll": "FF3B82F6",
        "btn": "FF1F2937",
        "play": "FF16A34A",
        "play_dim": "FF15803D",
        "close": "FFDC2626",
        "close_dim": "FF7F1D1D",
    },
    1: {  # Verde
        "name": "green",
        "bg": "FF0A1410",
        "bg_tint": "3316A34A",
        "header": "EE0F1F17",
        "panel": "CC0F1F17",
        "accent": "FF16A34A",
        "accent_soft": "9916A34A",
        "accent_row": "FF15803D",
        "accent_label": "FF86EFAC",
        "accent_mid": "FF4ADE80",
        "scroll": "FF22C55E",
        "btn": "FF1F2937",
        "play": "FF2563EB",
        "play_dim": "FF1D4ED8",
        "close": "FFDC2626",
        "close_dim": "FF7F1D1D",
    },
    2: {  # Ámbar
        "name": "amber",
        "bg": "FF140F0A",
        "bg_tint": "33D97706",
        "header": "EE1C140A",
        "panel": "CC1C140A",
        "accent": "FFD97706",
        "accent_soft": "99D97706",
        "accent_row": "FFB45309",
        "accent_label": "FFFCD34D",
        "accent_mid": "FFFBBF24",
        "scroll": "FFF59E0B",
        "btn": "FF1F2937",
        "play": "FF16A34A",
        "play_dim": "FF15803D",
        "close": "FFDC2626",
        "close_dim": "FF7F1D1D",
    },
    3: {  # Rojo
        "name": "rose",
        "bg": "FF140A0E",
        "bg_tint": "33E11D48",
        "header": "EE1F0F14",
        "panel": "CC1F0F14",
        "accent": "FFE11D48",
        "accent_soft": "99E11D48",
        "accent_row": "FFBE123C",
        "accent_label": "FFFDA4AF",
        "accent_mid": "FFFB7185",
        "scroll": "FFF43F5E",
        "btn": "FF1F2937",
        "play": "FF16A34A",
        "play_dim": "FF15803D",
        "close": "FF9F1239",
        "close_dim": "FF881337",
    },
    4: {  # Violeta
        "name": "violet",
        "bg": "FF100A18",
        "bg_tint": "337C3AED",
        "header": "EE160F24",
        "panel": "CC160F24",
        "accent": "FF7C3AED",
        "accent_soft": "997C3AED",
        "accent_row": "FF6D28D9",
        "accent_label": "FFDDD6FE",
        "accent_mid": "FFA78BFA",
        "scroll": "FF8B5CF6",
        "btn": "FF1F2937",
        "play": "FF16A34A",
        "play_dim": "FF15803D",
        "close": "FFDC2626",
        "close_dim": "FF7F1D1D",
    },
    5: {  # Pizarra / neutro
        "name": "slate",
        "bg": "FF0B0F14",
        "bg_tint": "33475569",
        "header": "EE111827",
        "panel": "CC111827",
        "accent": "FF64748B",
        "accent_soft": "9964748B",
        "accent_row": "FF475569",
        "accent_label": "FFCBD5E1",
        "accent_mid": "FF94A3B8",
        "scroll": "FF94A3B8",
        "btn": "FF1E293B",
        "play": "FF0EA5E9",
        "play_dim": "FF0284C7",
        "close": "FFDC2626",
        "close_dim": "FF7F1D1D",
    },
}


def get_palette() -> Dict[str, str]:
    idx = ku.get_setting_int("ui_palette", 0)
    return PALETTES.get(idx, PALETTES[0])


def _hex_to_rgb(color: str):
    c = color[-6:]
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _ensure_white(media_dir: str) -> None:
    path = os.path.join(media_dir, "white.png")
    if os.path.exists(path):
        return
    try:
        from PIL import Image
        Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(path)
    except Exception:
        src = os.path.join(
            ku.ADDON_PATH, "resources", "skins", "Default", "media", "white.png"
        )
        if os.path.exists(src):
            shutil.copy2(src, path)


def _draw_icon_button(path: str, kind: str, bg_hex: str, fg=(255, 255, 255)) -> None:
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg = _hex_to_rgb(bg_hex)
    margin = 4
    draw.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=14,
        fill=bg + (255,),
    )
    # Glyphs simples centrados
    cx = cy = size // 2
    if kind == "search":
        draw.ellipse([20, 18, 42, 40], outline=fg + (255,), width=3)
        draw.line([(40, 38), (48, 48)], fill=fg + (255,), width=3)
    elif kind == "reload":
        draw.arc([18, 18, 46, 46], start=40, end=300, fill=fg + (255,), width=3)
        draw.polygon([(46, 18), (52, 30), (40, 28)], fill=fg + (255,))
    elif kind == "file":
        draw.rounded_rectangle([22, 16, 42, 48], radius=3, outline=fg + (255,), width=3)
        draw.line([(28, 26), (36, 26)], fill=fg + (255,), width=2)
        draw.line([(28, 32), (36, 32)], fill=fg + (255,), width=2)
        draw.line([(28, 38), (34, 38)], fill=fg + (255,), width=2)
    elif kind == "url":
        draw.ellipse([16, 24, 32, 40], outline=fg + (255,), width=3)
        draw.ellipse([32, 24, 48, 40], outline=fg + (255,), width=3)
        draw.line([(28, 32), (36, 32)], fill=fg + (255,), width=3)
    elif kind == "settings":
        draw.ellipse([24, 24, 40, 40], outline=fg + (255,), width=3)
        for ang in range(0, 360, 45):
            import math
            rad = math.radians(ang)
            x1 = cx + int(10 * math.cos(rad))
            y1 = cy + int(10 * math.sin(rad))
            x2 = cx + int(18 * math.cos(rad))
            y2 = cy + int(18 * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=fg + (255,), width=3)
    elif kind == "close":
        draw.line([(22, 22), (42, 42)], fill=fg + (255,), width=4)
        draw.line([(42, 22), (22, 42)], fill=fg + (255,), width=4)
    img.save(path)


def _build_icons(media_dir: str, palette: Dict[str, str]) -> None:
    icons = os.path.join(media_dir, "icons")
    os.makedirs(icons, exist_ok=True)
    mapping = {
        "search": palette["btn"],
        "search_focus": palette["accent"],
        "reload": palette["btn"],
        "reload_focus": palette["accent"],
        "file": palette["btn"],
        "file_focus": palette["accent"],
        "url": palette["btn"],
        "url_focus": palette["accent"],
        "settings": palette["btn"],
        "settings_focus": palette["accent"],
        "close": palette["close_dim"],
        "close_focus": palette["close"],
    }
    kind_of = {
        "search": "search",
        "search_focus": "search",
        "reload": "reload",
        "reload_focus": "reload",
        "file": "file",
        "file_focus": "file",
        "url": "url",
        "url_focus": "url",
        "settings": "settings",
        "settings_focus": "settings",
        "close": "close",
        "close_focus": "close",
    }
    for name, bg in mapping.items():
        _draw_icon_button(os.path.join(icons, f"{name}.png"), kind_of[name], bg)


def _xml_template(p: Dict[str, str]) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<window>
  <defaultcontrol>200</defaultcontrol>
  <controls>

    <control type="image">
      <left>0</left><top>0</top><width>1920</width><height>1080</height>
      <texture colordiffuse="{p["bg"]}">white.png</texture>
    </control>
    <control type="image">
      <left>0</left><top>0</top><width>1920</width><height>1080</height>
      <texture colordiffuse="{p["bg_tint"]}">white.png</texture>
    </control>

    <control type="image">
      <left>0</left><top>0</top><width>1920</width><height>72</height>
      <texture colordiffuse="{p["header"]}">white.png</texture>
    </control>
    <control type="label" id="1">
      <left>40</left><top>8</top><width>520</width><height>32</height>
      <label>Launcher M3U</label>
      <font>font14</font>
      <textcolor>FFFFFFFF</textcolor>
      <aligny>center</aligny>
    </control>
    <control type="label" id="320">
      <left>40</left><top>40</top><width>700</width><height>24</height>
      <label></label>
      <font>font12</font>
      <textcolor>FF94A3B8</textcolor>
      <align>left</align>
      <aligny>center</aligny>
    </control>

    <!-- Iconos cabecera (navegables y clicables) -->
    <control type="button" id="403">
      <left>1488</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/search_focus.png</texturefocus>
      <texturenofocus>icons/search.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>405</onleft>
      <onright>401</onright>
      <ondown>200</ondown>
    </control>
    <control type="button" id="401">
      <left>1552</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/reload_focus.png</texturefocus>
      <texturenofocus>icons/reload.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>403</onleft>
      <onright>404</onright>
      <ondown>200</ondown>
    </control>
    <control type="button" id="404">
      <left>1616</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/file_focus.png</texturefocus>
      <texturenofocus>icons/file.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>401</onleft>
      <onright>406</onright>
      <ondown>200</ondown>
    </control>
    <control type="button" id="406">
      <left>1680</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/url_focus.png</texturefocus>
      <texturenofocus>icons/url.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>404</onleft>
      <onright>402</onright>
      <ondown>200</ondown>
    </control>
    <control type="button" id="402">
      <left>1744</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/settings_focus.png</texturefocus>
      <texturenofocus>icons/settings.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>406</onleft>
      <onright>405</onright>
      <ondown>200</ondown>
    </control>
    <control type="button" id="405">
      <left>1808</left><top>8</top><width>56</width><height>56</height>
      <label></label>
      <texturefocus>icons/close_focus.png</texturefocus>
      <texturenofocus>icons/close.png</texturenofocus>
      <pulseonselect>false</pulseonselect>
      <onleft>402</onleft>
      <onright>403</onright>
      <ondown>200</ondown>
    </control>

    <control type="image">
      <left>32</left><top>96</top><width>380</width><height>944</height>
      <texture border="16" colordiffuse="{p["panel"]}">white.png</texture>
    </control>
    <control type="label">
      <left>56</left><top>116</top><width>330</width><height>36</height>
      <label>$LOCALIZE[30404]</label>
      <font>font14</font>
      <textcolor>{p["accent_label"]}</textcolor>
    </control>
    <control type="list" id="100">
      <left>48</left><top>166</top><width>330</width><height>844</height>
      <onright>200</onright>
      <onup>403</onup>
      <pagecontrol>101</pagecontrol>
      <scrolltime>200</scrolltime>
      <orientation>vertical</orientation>
      <itemlayout height="68" width="330">
        <control type="label">
          <left>16</left><top>4</top><width>298</width><height>60</height>
          <label>$INFO[ListItem.Label]</label>
          <font>font13</font>
          <textcolor>FFF8FAFC</textcolor>
          <selectedcolor>FFF8FAFC</selectedcolor>
          <shadowcolor>FF000000</shadowcolor>
          <aligny>center</aligny>
        </control>
      </itemlayout>
      <focusedlayout height="68" width="330">
        <control type="image">
          <left>0</left><top>4</top><width>330</width><height>60</height>
          <texture colordiffuse="{p["accent_soft"]}">white.png</texture>
        </control>
        <control type="label">
          <left>16</left><top>4</top><width>298</width><height>60</height>
          <label>$INFO[ListItem.Label]</label>
          <font>font13</font>
          <textcolor>FFFFFFFF</textcolor>
          <selectedcolor>FFFFFFFF</selectedcolor>
          <shadowcolor>FF000000</shadowcolor>
          <aligny>center</aligny>
        </control>
      </focusedlayout>
    </control>
    <control type="scrollbar" id="101">
      <left>384</left><top>166</top><width>18</width><height>844</height>
      <texturesliderbackground colordiffuse="FF0F172A">white.png</texturesliderbackground>
      <texturesliderbar colordiffuse="FF475569">white.png</texturesliderbar>
      <texturesliderbarfocus colordiffuse="{p["scroll"]}">white.png</texturesliderbarfocus>
      <textureslidernib colordiffuse="FFE2E8F0">white.png</textureslidernib>
      <textureslidernibfocus colordiffuse="FFFFFFFF">white.png</textureslidernibfocus>
      <orientation>vertical</orientation>
      <showonepage>false</showonepage>
      <onleft>100</onleft>
      <onright>200</onright>
    </control>

    <control type="image">
      <left>432</left><top>96</top><width>900</width><height>944</height>
      <texture border="16" colordiffuse="{p["panel"]}">white.png</texture>
    </control>
    <control type="label" id="310">
      <left>456</left><top>116</top><width>850</width><height>36</height>
      <label>$LOCALIZE[30405]</label>
      <font>font14</font>
      <textcolor>{p["accent_label"]}</textcolor>
    </control>
    <control type="list" id="200">
      <left>448</left><top>166</top><width>840</width><height>844</height>
      <onleft>100</onleft>
      <onright>400</onright>
      <onup>403</onup>
      <pagecontrol>201</pagecontrol>
      <scrolltime tween="quadratic">200</scrolltime>
      <orientation>vertical</orientation>
      <itemlayout height="92" width="840">
        <control type="image">
          <left>0</left><top>4</top><width>840</width><height>84</height>
          <texture colordiffuse="FF0F172A">white.png</texture>
        </control>
        <control type="image">
          <left>12</left><top>14</top><width>64</width><height>64</height>
          <texture background="true">$INFO[ListItem.Property(logo)]</texture>
          <aspectratio>keep</aspectratio>
        </control>
        <control type="label">
          <left>92</left><top>10</top><width>720</width><height>36</height>
          <label>$INFO[ListItem.Label]</label>
          <font>font14</font>
          <textcolor>FFFFFFFF</textcolor>
          <aligny>center</aligny>
        </control>
        <control type="label">
          <left>92</left><top>46</top><width>720</width><height>32</height>
          <label>$INFO[ListItem.Label2]</label>
          <font>font12</font>
          <textcolor>FF94A3B8</textcolor>
          <aligny>center</aligny>
        </control>
      </itemlayout>
      <focusedlayout height="92" width="840">
        <control type="image">
          <left>0</left><top>4</top><width>840</width><height>84</height>
          <texture colordiffuse="{p["accent_row"]}">white.png</texture>
        </control>
        <control type="image">
          <left>12</left><top>14</top><width>64</width><height>64</height>
          <texture background="true">$INFO[ListItem.Property(logo)]</texture>
          <aspectratio>keep</aspectratio>
        </control>
        <control type="label">
          <left>92</left><top>10</top><width>720</width><height>36</height>
          <label>$INFO[ListItem.Label]</label>
          <font>font14</font>
          <textcolor>FFFFFFFF</textcolor>
          <aligny>center</aligny>
        </control>
        <control type="label">
          <left>92</left><top>46</top><width>720</width><height>32</height>
          <label>$INFO[ListItem.Label2]</label>
          <font>font12</font>
          <textcolor>FFE2E8F0</textcolor>
          <aligny>center</aligny>
        </control>
      </focusedlayout>
    </control>
    <control type="scrollbar" id="201">
      <left>1294</left><top>166</top><width>22</width><height>844</height>
      <texturesliderbackground colordiffuse="FF0F172A">white.png</texturesliderbackground>
      <texturesliderbar colordiffuse="FF475569">white.png</texturesliderbar>
      <texturesliderbarfocus colordiffuse="{p["scroll"]}">white.png</texturesliderbarfocus>
      <textureslidernib colordiffuse="FFE2E8F0">white.png</textureslidernib>
      <textureslidernibfocus colordiffuse="FFFFFFFF">white.png</textureslidernibfocus>
      <orientation>vertical</orientation>
      <showonepage>false</showonepage>
      <onleft>200</onleft>
      <onright>400</onright>
    </control>

    <control type="image">
      <left>1352</left><top>96</top><width>536</width><height>944</height>
      <texture border="16" colordiffuse="{p["panel"]}">white.png</texture>
    </control>
    <control type="label">
      <left>1376</left><top>116</top><width>480</width><height>36</height>
      <label>$LOCALIZE[30406]</label>
      <font>font14</font>
      <textcolor>{p["accent_label"]}</textcolor>
    </control>

    <control type="image">
      <left>1376</left><top>160</top><width>488</width><height>274</height>
      <texture colordiffuse="FF020617">white.png</texture>
    </control>
    <control type="image" id="330">
      <left>1488</left><top>206</top><width>260</width><height>160</height>
      <texture>DefaultTVShows.png</texture>
      <aspectratio>keep</aspectratio>
      <visible>!Player.HasVideo</visible>
    </control>
    <control type="videowindow" id="350">
      <left>1376</left><top>160</top><width>488</width><height>274</height>
      <visible>Player.HasVideo</visible>
    </control>

    <control type="label" id="311">
      <left>1376</left><top>448</top><width>488</width><height>40</height>
      <label></label>
      <font>font14</font>
      <textcolor>FFFFFFFF</textcolor>
      <align>center</align>
    </control>

    <control type="label">
      <left>1376</left><top>500</top><width>488</width><height>28</height>
      <label>$LOCALIZE[30407]</label>
      <font>font12</font>
      <textcolor>{p["accent_mid"]}</textcolor>
    </control>
    <control type="label" id="300">
      <left>1376</left><top>528</top><width>488</width><height>56</height>
      <label>-</label>
      <font>font13</font>
      <textcolor>FFFFFFFF</textcolor>
      <wrapmultiline>true</wrapmultiline>
    </control>
    <control type="label" id="301">
      <left>1376</left><top>588</top><width>488</width><height>28</height>
      <label></label>
      <font>font12</font>
      <textcolor>FF94A3B8</textcolor>
    </control>
    <control type="textbox" id="302">
      <left>1376</left><top>624</top><width>488</width><height>140</height>
      <font>font12</font>
      <textcolor>FFCBD5E1</textcolor>
      <autoscroll time="3000" delay="4000" repeat="5000">true</autoscroll>
    </control>

    <control type="label">
      <left>1376</left><top>776</top><width>488</width><height>28</height>
      <label>$LOCALIZE[30408]</label>
      <font>font12</font>
      <textcolor>{p["accent_mid"]}</textcolor>
    </control>
    <control type="label" id="303">
      <left>1376</left><top>808</top><width>488</width><height>50</height>
      <label>-</label>
      <font>font13</font>
      <textcolor>FFE2E8F0</textcolor>
      <wrapmultiline>true</wrapmultiline>
    </control>

    <control type="button" id="400">
      <left>1376</left><top>900</top><width>488</width><height>64</height>
      <label>$LOCALIZE[30402]</label>
      <font>font14</font>
      <textcolor>FFFFFFFF</textcolor>
      <focusedcolor>FFFFFFFF</focusedcolor>
      <texturefocus colordiffuse="{p["play"]}">white.png</texturefocus>
      <texturenofocus colordiffuse="{p["play_dim"]}">white.png</texturenofocus>
      <align>center</align>
      <aligny>center</aligny>
      <onleft>200</onleft>
    </control>

  </controls>
</window>
'''


def prepare_skin() -> str:
    """
    Genera XML + iconos en el perfil del addon y devuelve la ruta raíz
    para WindowXML (debe contener resources/skins/...).
    """
    palette = get_palette()
    root = os.path.join(ku.ensure_profile(), "ui_skin")
    skin_1080 = os.path.join(root, "resources", "skins", "Default", "1080i")
    media = os.path.join(root, "resources", "skins", "Default", "media")
    icons_dst = os.path.join(media, "icons")
    os.makedirs(skin_1080, exist_ok=True)
    os.makedirs(icons_dst, exist_ok=True)

    _ensure_white(media)

    # Preferir iconos pregenerados del addon (sin depender de Pillow en Kodi)
    bundled = os.path.join(
        ku.ADDON_PATH, "resources", "skins", "Default", "media", "icons", palette["name"]
    )
    if os.path.isdir(bundled):
        for name in os.listdir(bundled):
            src = os.path.join(bundled, name)
            dst = os.path.join(icons_dst, name)
            if os.path.isfile(src) and (
                not os.path.exists(dst)
                or os.path.getsize(src) != os.path.getsize(dst)
            ):
                shutil.copy2(src, dst)
    else:
        try:
            _build_icons(media, palette)
        except Exception as exc:
            ku.log(f"No se pudieron generar iconos: {exc}", level=3)

    xml_path = os.path.join(skin_1080, "launcherm3u-main.xml")
    xml = _xml_template(palette)
    current = ""
    try:
        with open(xml_path, "r", encoding="utf-8") as fh:
            current = fh.read()
    except OSError:
        pass
    if current != xml:
        with open(xml_path, "w", encoding="utf-8") as fh:
            fh.write(xml)

    if not xbmcvfs.exists(skin_1080):
        xbmcvfs.mkdirs(skin_1080)
    return root
