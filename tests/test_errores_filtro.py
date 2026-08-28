"""Filtro anti-ruido del proactor de Windows (errores._FiltroProactor): los
ConnectionResetError cosméticos de asyncio (`_call_connection_lost`, WinError
10054 — clientes que abortan keep-alives con RST) no deben tapar el log del
servicio ni llenar el ring de "Errores recientes" de /admin. Cualquier otro
error de asyncio sigue pasando."""
from __future__ import annotations

import logging

from backend.services import errores


def _rec(msg: str, exc: BaseException | None) -> logging.LogRecord:
    ei = (type(exc), exc, None) if exc is not None else None
    return logging.LogRecord("asyncio", logging.ERROR, __file__, 1, msg, None, ei)


def test_filtro_solo_el_patron_exacto() -> None:
    f = errores._FiltroProactor()
    ruido = "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)"
    # el ruido exacto → afuera (reset y aborted)
    assert f.filter(_rec(ruido, ConnectionResetError(10054, "WinError 10054"))) is False
    assert f.filter(_rec(ruido, ConnectionAbortedError())) is False
    # mismo mensaje pero otra excepción → pasa
    assert f.filter(_rec(ruido, RuntimeError("otra cosa"))) is True
    # excepción de conexión en OTRO contexto → pasa
    assert f.filter(_rec("error real leyendo el socket del feed", ConnectionResetError())) is True
    # registros sin exc_info → pasan
    assert f.filter(_rec("warning normal de asyncio", None)) is True


def test_ring_no_se_llena_con_ruido() -> None:
    errores.install()
    with errores._lock:
        errores._BUF.clear()
    log = logging.getLogger("asyncio")
    try:
        raise ConnectionResetError(10054, "Se ha forzado la interrupción de una conexión")
    except ConnectionResetError:
        log.error("Exception in callback _ProactorBasePipeTransport._call_connection_lost(...)",
                  exc_info=True)
    log.warning("esto sí es un problema real de asyncio")
    msgs = " | ".join(e["msg"] for e in errores.ultimos(10))
    assert "problema real" in msgs
    assert "_call_connection_lost" not in msgs
