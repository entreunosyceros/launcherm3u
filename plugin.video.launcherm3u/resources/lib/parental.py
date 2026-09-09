# -*- coding: utf-8 -*-
"""Control parental: PIN y canales bloqueados."""

from __future__ import annotations

import time
from typing import Optional

import xbmc
import xbmcgui

from . import cache
from . import kodi_utils as ku

# Tras un PIN correcto, no volver a pedirlo durante esta ventana.
_SESSION_SECONDS = 30 * 60
_session_ok_until = 0.0


def get_pin() -> str:
    return (ku.get_setting("parental_pin") or "").strip()


def set_pin(pin: str) -> None:
    ku.set_setting("parental_pin", (pin or "").strip())


def _enable_parental(enabled: bool = True) -> None:
    try:
        ku.set_setting_bool("parental_enabled", bool(enabled))
    except Exception:
        ku.set_setting("parental_enabled", "true" if enabled else "false")


def is_enabled() -> bool:
    return ku.get_setting_bool("parental_enabled", False) and bool(get_pin())


def session_valid() -> bool:
    return time.time() < _session_ok_until


def mark_session() -> None:
    global _session_ok_until
    _session_ok_until = time.time() + _SESSION_SECONDS


def clear_session() -> None:
    global _session_ok_until
    _session_ok_until = 0.0


def _ask_pin(heading: str) -> Optional[str]:
    """Pide un PIN numérico. None = cancelado."""
    try:
        value = xbmcgui.Dialog().numeric(0, heading)
    except Exception:
        keyboard = xbmc.Keyboard("", heading, True)
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return None
        value = keyboard.getText()
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def prompt_verify_pin(heading: str = "") -> bool:
    """Verifica el PIN configurado. True si correcto."""
    pin = get_pin()
    if not pin:
        return False
    entered = _ask_pin(heading or (ku.get_string(30610) or "Introduce el PIN"))
    if entered is None:
        return False
    if entered != pin:
        ku.notify_error(ku.get_string(30611) or "PIN incorrecto")
        return False
    mark_session()
    return True


def prompt_set_pin(force: bool = False) -> bool:
    """Define o cambia el PIN (doble introducción)."""
    if get_pin() and not force:
        if not prompt_verify_pin(ku.get_string(30612) or "PIN actual"):
            return False
    first = _ask_pin(ku.get_string(30613) or "Nuevo PIN (números)")
    if first is None:
        return False
    if len(first) < 4:
        ku.notify_error(ku.get_string(30614) or "El PIN debe tener al menos 4 dígitos")
        return False
    second = _ask_pin(ku.get_string(30615) or "Repite el PIN")
    if second is None:
        return False
    if first != second:
        ku.notify_error(ku.get_string(30616) or "Los PIN no coinciden")
        return False
    set_pin(first)
    _enable_parental(True)
    mark_session()
    ku.notify(ku.get_string(30617) or "PIN guardado")
    return True


def ensure_pin_ready() -> bool:
    """Asegura que hay PIN y control parental activo."""
    if is_enabled():
        return True
    if not xbmcgui.Dialog().yesno(
        ku.get_string(30600) or "Control parental",
        ku.get_string(30618)
        or "Para bloquear canales debes configurar un PIN. ¿Continuar?",
    ):
        return False
    return prompt_set_pin(force=True)


def ensure_channel_unlocked(channel_id: int) -> bool:
    """True si se puede reproducir el canal (no bloqueado o PIN OK)."""
    if not is_enabled():
        return True
    if not cache.is_locked(int(channel_id)):
        return True
    if session_valid():
        return True
    ok = prompt_verify_pin(
        ku.get_string(30619) or "Canal bloqueado — introduce el PIN"
    )
    return ok


def toggle_channel_lock(channel_id: int) -> Optional[bool]:
    """
    Bloquea/desbloquea un canal.
    Devuelve True si queda bloqueado, False si desbloqueado, None si cancelado.
    """
    cid = int(channel_id)
    if not cid:
        return None
    locked = cache.is_locked(cid)
    if locked:
        if not ensure_pin_ready():
            return None
        if not prompt_verify_pin(ku.get_string(30621) or "PIN para desbloquear"):
            return None
        cache.toggle_locked(cid)
        return False

    if not ensure_pin_ready():
        return None
    if not session_valid() and get_pin():
        if not prompt_verify_pin(ku.get_string(30622) or "PIN para bloquear"):
            return None
    cache.toggle_locked(cid)
    return True


def clear_all_locks() -> int:
    if not ensure_pin_ready():
        return -1
    if get_pin() and not prompt_verify_pin(
        ku.get_string(30623) or "PIN para quitar bloqueos"
    ):
        return -1
    cleared = cache.clear_locked_channels()
    ku.notify(
        (ku.get_string(30624) or "Bloqueos eliminados: {0}").format(cleared)
    )
    return cleared
