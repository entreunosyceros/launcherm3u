# Launcher M3U: el addon de Kodi para reproducir listas M3U con EPG (guía 2026)

> **Meta title (SEO):** Launcher M3U | Addon Kodi para listas M3U e IPTV con EPG  
> **Meta description:** Descubre Launcher M3U, el addon de Kodi para cargar listas M3U locales o por URL, ver la guía EPG XMLTV, favoritos, control parental y actualizaciones automáticas. Instalación paso a paso.  
> **Slug sugerido:** `/launcher-m3u-addon-kodi-listas-m3u-epg/`  
> **Keywords principales:** addon Kodi M3U, Launcher M3U, reproductor IPTV Kodi, EPG XMLTV Kodi, instalar addon desde ZIP Kodi

---

Si usas **Kodi** y trabajas con **listas M3U** (archivo local o URL remota), necesitas un addon que cargue rápido, no se quede congelado con miles de canales y muestre la programación cuando dispones de una guía **EPG XMLTV**. **Launcher M3U** (`plugin.video.launcherm3u`) es un **addon de vídeo para Kodi** desarrollado por **entreunosyceros**, pensado exactamente para eso: una interfaz tipo IPTV con grupos, canales, logos y ahora/siguiente, optimizada para listas grandes y con extras prácticos como favoritos, recientes, control parental con PIN y actualizaciones desde GitHub.

En esta guía te explicamos qué es Launcher M3U, en qué se diferencia de un cliente PVR, qué funciones aporta la versión **1.3.1** y cómo **instalar el addon en Kodi** de forma correcta.

## Qué es Launcher M3U y para quién está pensado

**Launcher M3U** es un plugin de vídeo escrito en Python para **Kodi 19 Matrix o superior**. Su objetivo es sencillo: abrir una lista **M3U/M3U8**, organizar los canales por grupos y reproducirlos con una experiencia cercana a un *launcher* IPTV, sin convertirte en administrador de un sintonizador PVR completo.

Es especialmente útil si:

- Tienes una **lista M3U** propia (archivo en el PC, NAS o USB) o una **URL de lista**.
- Quieres ver la **guía EPG** asociada (XMLTV, también comprimida en `.gz`).
- Manejas **listas grandes** (cientos o miles de canales) y necesitas caché, paginación y recargas en segundo plano.
- Prefieres un addon ligero, instalable desde ZIP, con código abierto en GitHub.

Repositorio oficial: [github.com/entreunosyceros/launcherm3u](https://github.com/entreunosyceros/launcherm3u)  
Descargas: [Releases de Launcher M3U](https://github.com/entreunosyceros/launcherm3u/releases)

## Addon de vídeo frente a cliente PVR: una distinción importante

Muchos usuarios buscan un “**IPTV Simple Client** para Kodi” y esperan la rejilla nativa de *TV en vivo*. Conviene aclararlo por SEO y por expectativas reales:

- Un **cliente PVR** (como IPTV Simple) integra canales en la sección de televisión de Kodi y usa la guía EPG del sistema.
- **Launcher M3U** es un **plugin de vídeo**: la navegación y la EPG se muestran **dentro del propio addon**. La sensación de uso (grupos, canales, programa actual) es similar en simplicidad, pero no sustituye la API PVR.

Si tu prioridad es zapping rápido, vista previa y gestión de listas M3U sin configurar un backend PVR, Launcher M3U encaja mejor. Si necesitas la guía EPG global de Kodi en “TV en vivo”, deberás valorar un cliente PVR.

## Características principales del addon Kodi M3U

### Interfaz IPTV propia

Al abrir el addon verás un layout pensado para el salón: **grupos a un lado**, **canales en el centro** (con logo y, si hay EPG, el programa en emisión) y panel de detalle con **ahora / a continuación**. Un clic o OK inicia la **vista previa embebida**; la reproducción a pantalla completa lanza exactamente el canal activo, sin playlists confusas.

### Listas M3U locales o por URL

Puedes cargar la lista desde:

- un **archivo M3U local** (recomendado usar el selector del propio addon), o
- una **URL HTTP/HTTPS** de playlist.

El parseo se hace **línea a línea**, con inserción por lotes en base de datos, pensado para no ahogar la memoria cuando la lista es enorme.

### Guía EPG XMLTV (también .gz)

Si activas la EPG, Launcher M3U admite fuente **local o remota**, incluyendo ficheros **XMLTV comprimidos en `.gz`**. Además puede aprovechar el atributo **`url-tvg`** de la cabecera M3U para asociar automáticamente la guía cuando la playlist lo declara. La interfaz muestra programa actual y siguiente, y puedes recargar sin perder la caché anterior si algo falla.

### Rendimiento: SQLite, caché y listas grandes

El núcleo del addon usa **caché SQLite**, descargas con **ETag/Last-Modified**, publicación atómica de la caché y **lista incremental** en la UI (no materializa todos los canales de golpe). La recarga puede ejecutarse en **segundo plano**, y hay opciones de **recarga programada** y **poda de EPG antigua** para no hinchar la base de datos.

Para listas grandes, valores orientativos:

| Ajuste | Sugerencia |
|--------|------------|
| Canales por página | 100–200 |
| Horas de validez de la caché | 12–24 |
| Mostrar programa actual en lista | Activado si el EPG no es desmesurado |

### Favoritos, recientes y búsqueda

Marca canales como **favoritos**, vuelve a los **recientes** y localiza emisoras con la búsqueda integrada. El menú contextual del canal concentra acciones frecuentes sin salir de la interfaz.

### Control parental con PIN

En hogares compartidos importa el **control parental**. Launcher M3U permite **bloquear canales con un PIN** (mínimo 4 dígitos). Al reproducir un canal bloqueado se solicita el código; tras validarlo hay una sesión de unos 30 minutos para no interrumpir el zapping. Desde ajustes puedes activar el control parental, cambiar el PIN o limpiar bloqueos.

### Cabeceras HTTP, audio, subtítulos y streams HLS/DASH

Algunas listas o CDNs exigen **User-Agent**, **Referer** u otras cabeceras. El addon permite configurarlas de forma global. También ofrece selector de **pistas de audio y subtítulos**, y puede apoyarse en **InputStream Adaptive** cuando el stream es HLS/DASH (si tienes ese addon instalado).

### Actualizaciones desde GitHub Releases

Desde la versión **1.3.1**, Launcher M3U comprueba **GitHub Releases** del repositorio oficial. Puedes buscar actualizaciones a mano (con opciones para **instalar ahora**, abrir la página del release o posponer) o activar la **descarga e instalación automática** del ZIP de update. Solo se aceptan paquetes del repo oficial, para reducir riesgos de fuentes no confiables.

## Cómo instalar Launcher M3U en Kodi (desde ZIP)

La forma recomendada de **instalar un addon desde ZIP en Kodi** es usar el paquete de release, no el botón “Code → Download ZIP” del repositorio (ese archivo es el código del proyecto, no el addon empaquetado, y suele fallar la instalación).

### Pasos recomendados

1. Entra en la página de [Releases](https://github.com/entreunosyceros/launcherm3u/releases) y descarga el asset  
   **`plugin.video.launcherm3u-x.y.z.zip`** (por ejemplo `plugin.video.launcherm3u-1.3.1.zip`).
2. En Kodi, activa si hace falta **Orígenes desconocidos** (Ajustes del sistema → Add-ons).
3. Ve a **Add-ons → Instalar desde un archivo ZIP** y elige el ZIP descargado.
4. Si una instalación anterior falló, **cierra Kodi por completo** y reintenta: el instalador a veces deja el estado inconsistente tras un ZIP incorrecto.

### Instalación copiando la carpeta

También puedes copiar la carpeta `plugin.video.launcherm3u` a la ruta de addons de tu plataforma:

- **Linux:** `~/.kodi/addons/`
- **Windows:** `%APPDATA%\Kodi\addons\`
- **Android:** `Android/data/org.xbmc.kodi/files/.kodi/addons/`

Después, en **Mis add-ons → Add-ons de vídeo → Launcher M3U**, actívalo y configura la lista.

## Primer uso: configurar M3U y EPG

1. Abre **Launcher M3U**.
2. Configura la lista desde **Ajustes** o con el botón **Archivo** de la interfaz.
3. (Opcional) Activa la **EPG XMLTV** e indica fichero o URL.
4. Navega por grupos y canales; usa vista previa o pantalla completa.
5. **Recargar** actualiza datos en segundo plano; si la descarga falla, se conserva la caché previa siempre que sea posible.
6. Usa el menú contextual para favoritos, bloqueo con PIN, audio o subtítulos.

Si notas iconos o texturas antiguas, o cambias a menudo de lista, la sección de **limpieza de caché** (descargas, base de datos, thumbnails o limpieza completa) ayuda a dejar el addon en estado limpio sin reinstalar Kodi entero.

## Requisitos técnicos

- **Kodi 19 Matrix** o posterior (Python 3).
- Opcional: **InputStream Adaptive** para aprovechar mejor HLS/DASH.
- Conexión a Internet si usas listas o EPG remotas y para comprobar updates en GitHub.

Licencia del proyecto: **GPL-2.0-or-later**. El código y las releases están en GitHub, lo que facilita auditar el addon, reportar issues y actualizar con paquetes firmados por el flujo de Releases.

## Por qué Launcher M3U destaca entre los addons M3U para Kodi

Hay muchos *players* de listas, pero Launcher M3U concentra varias decisiones de producto que importan en el día a día:

1. **Enfoque en listas grandes** (streaming de parseo, SQLite, UI incremental).  
2. **EPG usable** dentro del addon, con soporte `.gz` y `url-tvg`.  
3. **UX de salón**: preview, pantalla completa del canal activo, favoritos y recientes.  
4. **Hogar**: control parental con PIN.  
5. **Mantenimiento**: limpieza de caché y **updates automáticos** desde el repo oficial.

Si buscas un **addon Kodi para listas M3U** que no te obligue a montar un PVR completo, es una opción sólida, documentada y en evolución activa (versión actual de referencia: **1.3.1**).

## Preguntas frecuentes (FAQ)

### ¿Launcher M3U es lo mismo que IPTV Simple Client?

No. IPTV Simple es un **cliente PVR**. Launcher M3U es un **plugin de vídeo** con interfaz propia y EPG integrada en el addon.

### ¿Puedo usar una lista M3U8 o solo M3U?

Sí: el flujo está orientado a playlists M3U/M3U8 y a la reproducción de los streams que referencian (incluyendo escenarios HLS con InputStream Adaptive cuando aplica).

### ¿Dónde descargo el ZIP correcto?

En [GitHub Releases](https://github.com/entreunosyceros/launcherm3u/releases), el archivo `plugin.video.launcherm3u-….zip`. Evita el ZIP genérico del botón Code de GitHub.

### ¿Las actualizaciones se instalan solas?

Puedes activar **Descargar e instalar actualizaciones automáticamente** en los ajustes del addon. En la comprobación manual también puedes elegir **Instalar ahora**.

### ¿Sirve para Android TV, Windows y Linux?

Sí, siempre que ejecutes un Kodi compatible (19+). La ruta de addons cambia según el sistema, pero el ZIP de instalación es el mismo.

## Conclusión

**Launcher M3U** es un **addon de Kodi para reproducir listas M3U** con una experiencia IPTV clara: grupos, canales, logos, EPG XMLTV, favoritos, control parental y un motor de caché pensado para listas grandes. Si quieres instalarlo hoy, descarga el ZIP oficial desde GitHub Releases, instálalo desde archivo en Kodi y configura tu playlist en pocos minutos.

**Enlaces útiles**

- Proyecto: [https://github.com/entreunosyceros/launcherm3u](https://github.com/entreunosyceros/launcherm3u)  
- Descargas: [https://github.com/entreunosyceros/launcherm3u/releases](https://github.com/entreunosyceros/launcherm3u/releases)

---

### Notas para el editor / CMS

- Inserta la captura de interfaz (alt: `Interfaz Launcher M3U en Kodi con grupos canales y EPG`) y el icono del addon cerca del H1.  
- Añade `Article` / `SoftwareApplication` schema si tu plantilla lo permite.  
- Enlaza internamente a otras guías: “cómo instalar addons desde ZIP en Kodi”, “qué es una lista M3U”, “EPG XMLTV explicado”.  
- CTA final: botón “Descargar Launcher M3U” → URL del último Release.
