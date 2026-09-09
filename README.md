# Launcher M3U — Addon Kodi
<p align="center">
<img width="525" height="570" alt="icon" src="https://github.com/user-attachments/assets/5e1ed723-9014-4803-ac62-fa278fd67aec" />
</p>

Addon de vídeo en Python para cargar listas **M3U** (archivo local o URL) y opcionalmente una guía **EPG XMLTV**, con navegación por grupos similar a IPTV Simple Client.

## Características
<p align="center">
<img width="1917" height="1047" alt="m3ulauncher-interfaz" src="https://github.com/user-attachments/assets/266d4bdb-babd-413f-a1f8-131ba18a1039" />
</p>

- Interfaz IPTV propia (grupos + canales con logo + ahora/siguiente)
- Vista previa embebida y reproducción a pantalla completa del canal activo
- **Favoritos** y **recientes**
- **Control parental**: bloquear canales con PIN
- Lista M3U desde **archivo local** o **URL**
- Guía EPG XMLTV (local o URL, también `.gz`); auto `url-tvg` del M3U
- Cabeceras HTTP configurables (User-Agent, Referer, Origin…)
- Recarga automática programada y poda de EPG antigua
- Selector de **pistas de audio / subtítulos**
- Comprobación de **actualizaciones** desde GitHub Releases
- Caché **SQLite** + descarga con ETag/Last-Modified
- Parseo M3U línea a línea e inserción por lotes (listas grandes)
- Lista incremental: la interfaz no materializa todos los canales a la vez
- Descarga M3U/EPG por bloques y publicación atómica de la caché
- Recarga en segundo plano sin bloquear la navegación
- Búsqueda, limpieza de caché y soporte HLS/DASH
- Logos IPTV configurables desde **Apariencia**

## Instalación

### Desde ZIP (recomendado)

1. Descarga el asset de un [Release](https://github.com/entreunosyceros/launcherm3u/releases), **o** genera el paquete en este repo:
   ```bash
   python3 build_zip.py
   ```
2. Usa el archivo **`plugin.video.launcherm3u-1.3.0.zip`** (también se crea el alias `launcherm3u-1.3.0.zip`).
3. En Kodi: **Add-ons → Instalar desde un archivo ZIP** → elige ese ZIP.
4. Si una instalación anterior falló, **cierra Kodi por completo** y vuelve a intentarlo.

No uses **Code → Download ZIP** de GitHub: ese archivo es el repositorio (no el addon) y la instalación fallará.

### Copiar carpeta

1. Copia `plugin.video.launcherm3u` a:
   - Linux: `~/.kodi/addons/`
   - Windows: `%APPDATA%\Kodi\addons\`
   - Android: `Android/data/org.xbmc.kodi/files/.kodi/addons/`
2. En Kodi: **Ajustes → Add-ons → Mis add-ons → Add-ons de vídeo → Launcher M3U**
3. Activa el addon si hace falta y configura la lista M3U (y EPG si quieres)

## Uso

1. Configura la lista M3U (ajustes o botón **Archivo** en la interfaz)
2. Opcional: activa EPG XMLTV
3. Al abrir el addon verás: **grupos | canales | EPG**
4. Un clic / OK abre la vista previa; doble clic o **Pantalla completa** abre el canal activo
5. **Recargar** actualiza en segundo plano y conserva la caché anterior si falla
6. Menú contextual del canal: favoritos, **bloquear/desbloquear con PIN**, audio, subtítulos

### Control parental

1. Menú contextual del canal → **Bloquear canal con PIN** (la primera vez crea un PIN de al menos 4 dígitos)
2. Al reproducir un canal bloqueado se pide el PIN (sesión ~30 minutos)
3. En **Ajustes → Control parental**: activar, definir/cambiar PIN y quitar todos los bloqueos (los blqueos se quitarán según el PIN utilizado en cada canal bloqueado)

### Limpiar caché

Desde el menú → **Limpiar caché**, o **Ajustes → Rendimiento → Limpieza**:

- Descargas M3U/EPG
- Base de datos de canales/EPG
- Thumbnails/logos en la caché de texturas de Kodi
- Limpieza completa del addon

También puedes usar **Seleccionar archivo M3U local** en el menú del addon (más fiable que solo el selector de ajustes).

## Ajustes recomendados para listas grandes
<p align="center">
<img width="1918" height="1046" alt="guia-epg" src="https://github.com/user-attachments/assets/88760b22-7b9f-4a45-b226-4f40333e1963" />
</p>

| Ajuste | Sugerencia |
|--------|------------|
| Canales por página | 100–200 |
| Horas de validez de la caché | 12–24 |
| Mostrar programa actual | Activado (si el EPG no es enorme) |

## Empaquetado

```bash
python3 build_zip.py
```

Genera ZIPs compatibles con el instalador de Kodi (Info-ZIP). No empaquetes solo con `zipfile` de Python: en varios Kodi provoca *Failed to unpack* / *Unable to load addon.xml*.

## Estructura

```
plugin.video.launcherm3u/
├── addon.xml
├── default.py
└── resources/
    ├── settings.xml
    ├── icon.png
    ├── fanart.jpg
    ├── language/
    ├── skins/
    └── lib/
        ├── cache.py
        ├── downloader.py
        ├── m3u_parser.py
        ├── epg_parser.py
        ├── loader.py
        ├── player.py
        ├── parental.py
        ├── updates.py
        ├── theme.py
        ├── ui_window.py
        ├── plugin.py
        ├── cleaner.py
        └── kodi_utils.py
```

## Requisitos

- Kodi 19 Matrix o superior (Python 3)
- Opcional: InputStream Adaptive para HLS/DASH
- Para generar el ZIP: comando `zip` (Info-ZIP) en el PATH

## Nota

Este addon es un **plugin de vídeo**, no un cliente PVR. La experiencia es similar en simplicidad a IPTV Simple Client, pero la guía EPG se consulta dentro del addon (no en la rejilla nativa de “TV en vivo”).
