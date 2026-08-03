"""API JSON para el add-in de Excel (tiempo real, reemplazo del feed Reuters).

Diseño:
- El add-in sondea `/excel/v1/seq` (entero plano, ~µs) cada 1 s y sólo cuando
  la secuencia avanzó baja `/excel/v1/snapshot` — el mismo patrón seq→refresh
  que usa la web (static/js/app.js).
- El snapshot se construye UNA vez por ventana de 1 s y se cachean los bytes ya
  serializados (patrón cache_seq, acá para JSON): N libros de Excel conectados
  cuestan 1 build por tick + N lookups de dict — el costo del server no escala
  con la cantidad de usuarios.
- Todo sale de caches en memoria (store del WS, fx, futuros, cauciones, MAE):
  cero I/O en el path de request → target p95 < 50 ms.

Auth: token POR USUARIO (header `X-OMS-Token` o `?token=`), habilitado/cortado
por el superuser desde /admin. El gating corre en el middleware auth_guard de
main.py; acá los handlers asumen request ya autenticada. `/excel/manifest.xml`
es público (es el instalador del add-in, no expone datos).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, FrozenSet, Optional, Tuple

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse, Response

from backend.config import settings
from backend.services import (
    cauciones as cauciones_svc,
    dolares as dolares_svc,
    futuros as futuros_svc,
    fx as fx_svc,
    historico as historico_svc,
    mae as mae_svc,
    marketdata_store as mds,
)

logger = logging.getLogger("backend.excel")

router = APIRouter(prefix="/excel", tags=["excel"])

# Un build por segundo como máximo aunque la seq avance varias veces adentro
# (los libros sondean a 1 Hz: más frescura que eso no llega a ninguna celda).
_MIN_BUILD_INTERVAL = 1.0
# Con la seq quieta (fuera de rueda) refresca igual cada tanto: SIOPEL/MAE/fx
# no pasan por el store y no bumpean la seq.
_STALE_TTL = 5.0
_MAX_CACHE_ENTRIES = 32     # querys distintas de ?codes= reales son un puñado

_cache: Dict[str, Tuple[int, float, bytes]] = {}
_cache_lock = threading.Lock()


def _q(snap: mds.MarketSnapshot) -> Dict[str, Any]:
    """Snapshot de una especie en dict compacto (sin None: el JSON de ~2k
    símbolos baja a la mitad y Excel trata ausente == sin dato)."""
    d: Dict[str, Any] = {}
    for k, v in (
        ("last", snap.last), ("bid", snap.bid), ("ask", snap.offer),
        ("bid_size", snap.bid_size), ("ask_size", snap.offer_size),
        ("last_size", snap.last_size), ("open", snap.open), ("close", snap.close),
        ("high", snap.high), ("low", snap.low), ("vol", snap.volume),
        ("nominal", snap.nominal), ("trades", snap.trade_count),
        ("vwap", snap.vwap()), ("last_ts", snap.last_ts), ("close_date", snap.close_ts),
    ):
        if v is not None:
            d[k] = v
    try:
        if snap.last is not None and snap.close:
            d["var"] = snap.last / snap.close - 1.0
    except (TypeError, ZeroDivisionError):
        pass
    return d


def _build(codes: Optional[FrozenSet[str]]) -> Dict[str, Any]:
    """Arma el snapshot completo desde los caches en memoria. Corre a lo sumo
    1 vez/s (ver _snapshot_bytes); el resto de los requests comparten bytes."""
    store = mds.get_store()
    seq = store.seq()
    quotes: Dict[str, Dict[str, Any]] = {}
    extras: Dict[str, Any] = {}
    for sym, snap in store.get_many(store.symbols()).items():
        if snap is None:
            continue
        if sym.startswith("DLR/"):
            continue                      # futuros: sección propia con tasas
        parts = sym.split(" - ")
        if len(parts) == 4 and parts[0] == "MERV":
            code, plazo = parts[2], parts[3]
            if code in ("PESOS", "DOLAR"):
                continue                  # cauciones: sección propia por plazo
            if plazo in ("CI", "24hs"):
                if codes and code not in codes:
                    continue
                quotes.setdefault(code, {})[plazo] = _q(snap)
                continue
        if not codes:
            extras[sym] = _q(snap)        # índices y símbolos crudos no estándar

    out: Dict[str, Any] = {"seq": seq, "ts": time.time(),
                           "quotes": quotes, "extras": extras}
    # Secciones livianas (siempre van, con o sin filtro ?codes=). Cada una es
    # failure-silent: un hiccup de una fuente no debe dejar sin datos al resto.
    try:
        f24, fci = fx_svc.get_fx("24hs"), fx_svc.get_fx("CI")
        out["fx"] = {"mep": f24.usb, "ccl": f24.ccl, "canje": f24.canje,
                     "mep_base": f24.usb_base, "ccl_base": f24.ccl_base,
                     "mep_ci": fci.usb, "ccl_ci": fci.ccl}
    except Exception:  # noqa: BLE001
        logger.exception("[excel] fx section failed")
        out["fx"] = {}
    try:
        out["mayorista"] = dolares_svc.official_fx()
    except Exception:  # noqa: BLE001
        logger.exception("[excel] mayorista section failed")
        out["mayorista"] = {}
    try:
        out["futuros"] = {"may": futuros_svc.rows("may"), "min": futuros_svc.rows("min")}
    except Exception:  # noqa: BLE001
        logger.exception("[excel] futuros section failed")
        out["futuros"] = {}
    try:
        out["cauciones"] = {
            "ARS": cauciones_svc.byma_rows("PESOS", include_close_only=True),
            "USD": cauciones_svc.byma_rows("DOLAR", include_close_only=True),
        }
    except Exception:  # noqa: BLE001
        logger.exception("[excel] cauciones section failed")
        out["cauciones"] = {}
    try:
        if mae_svc.enabled():
            # Fila default (max volumen, compat con hojas viejas) + "plazos":
            # {CI: {...}, 24hs: {...}} para que OMS.QUOTE(...; "CI"; "mae")
            # pueda elegir segmento (antes pedir CI devolvía t+1 en silencio).
            def _mae_row(t: str):
                row = mae_svc.match(t)
                if row is not None:
                    pl = mae_svc.match_por_plazo(t)
                    if pl:
                        row = {**row, "plazos": pl}
                return row
            out["mae"] = {t: _mae_row(t) for t in mae_svc.tickers()}
            out["mae_cauciones"] = mae_svc.cauciones_rows()
    except Exception:  # noqa: BLE001
        logger.exception("[excel] mae section failed")
    try:
        # Sólo viaja cuando hay algo que avisar (broker conectado sin market
        # data → precios posiblemente viejos): el taskpane lo muestra en ámbar.
        # Sin esto Excel repetía el engaño de la web: seq avanzando por MAE y
        # celdas con los precios persistidos de la última rueda buena.
        from backend.services import feed_health
        h = feed_health.snapshot()
        if h.get("warn"):
            out["health"] = {"warn": h["warn"]}
    except Exception:  # noqa: BLE001
        logger.exception("[excel] health section failed")
    return out


def _snapshot_bytes(codes_key: str) -> bytes:
    store = mds.get_store()
    cur_seq = store.seq()
    now = time.monotonic()
    with _cache_lock:
        ent = _cache.get(codes_key)
        if ent is not None:
            seq_b, at, body = ent
            if (now - at) < _MIN_BUILD_INTERVAL or (seq_b == cur_seq and (now - at) < _STALE_TTL):
                return body
    codes = frozenset(c for c in codes_key.split(",") if c) if codes_key else None
    data = _build(codes)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)))
        _cache[codes_key] = (data["seq"], time.monotonic(), body)
    return body


@router.get("/v1/seq", response_class=PlainTextResponse)
async def excel_seq() -> PlainTextResponse:
    """Secuencia del store (texto plano). El add-in la sondea 1/s y sólo baja
    el snapshot cuando avanzó — mismo contrato que /market/seq, pero bajo el
    esquema de auth por token del add-in."""
    return PlainTextResponse(str(mds.get_store().seq()),
                             headers={"Cache-Control": "no-store"})


@router.get("/v1/ping")
async def ping(request: Request) -> Dict[str, Any]:
    """Chequeo de token para el botón 'Probar conexión' del taskpane."""
    u = getattr(request.state, "user", None) or {}
    return {"ok": True, "user": u.get("username")}


@router.get("/v1/snapshot")
async def snapshot(codes: str = Query("", description="Filtro opcional: ESPECIES separadas por coma")) -> Response:
    key = ",".join(sorted({c.strip().upper() for c in codes.split(",") if c.strip()}))
    body = _snapshot_bytes(key)
    return Response(content=body, media_type="application/json",
                    headers={"Cache-Control": "no-store"})


@router.get("/v1/hist/{serie}")
async def hist(serie: str, days: Optional[int] = Query(None, ge=1)) -> Dict[str, Any]:
    """Serie macro histórica (reemplaza los RHistory del modelo Reuters).
    Series: las de backend.services.historico (a3500, badlar, tamar, CER, UVA…);
    el key matchea case-insensitive."""
    c = historico_svc.ensure_loaded()
    key = next((k for k in c["series"] if k.lower() == serie.strip().lower()), serie)
    out = historico_svc.series_points(key, days=days)
    out["serie"] = key
    return out


# ── Manifest del add-in (público: es el instalador, no expone datos) ─────────
_MANIFEST_ID = "7c1f4c1e-9b0a-4b6e-9a51-0f2a9e6d4bb1"

_MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0"
           xmlns:ov="http://schemas.microsoft.com/office/taskpaneappversionoverrides"
           xsi:type="TaskPaneApp">
  <Id>{app_id}</Id>
  <Version>1.0.0.0</Version>
  <ProviderName>Mesa</ProviderName>
  <DefaultLocale>es-AR</DefaultLocale>
  <DisplayName DefaultValue="OMS Bonos"/>
  <Description DefaultValue="Cotizaciones de la calculadora de bonos en tiempo real (reemplazo Reuters)."/>
  <IconUrl DefaultValue="{base}/static/icons/icon-192.png"/>
  <HighResolutionIconUrl DefaultValue="{base}/static/icons/icon-512.png"/>
  <SupportUrl DefaultValue="{base}/"/>
  <AppDomains>
    <AppDomain>{base}</AppDomain>
  </AppDomains>
  <Hosts>
    <Host Name="Workbook"/>
  </Hosts>
  <Requirements>
    <Sets DefaultMinVersion="1.1">
      <Set Name="SharedRuntime" MinVersion="1.1"/>
    </Sets>
  </Requirements>
  <DefaultSettings>
    <SourceLocation DefaultValue="{base}/static/excel/taskpane.html"/>
  </DefaultSettings>
  <Permissions>ReadWriteDocument</Permissions>
  <VersionOverrides xmlns="http://schemas.microsoft.com/office/taskpaneappversionoverrides" xsi:type="VersionOverridesV1_0">
    <Hosts>
      <Host xsi:type="Workbook">
        <Runtimes>
          <Runtime resid="OMS.Page.Url" lifetime="long"/>
        </Runtimes>
        <AllFormFactors>
          <ExtensionPoint xsi:type="CustomFunctions">
            <Script>
              <SourceLocation resid="OMS.Functions.Script.Url"/>
            </Script>
            <Page>
              <SourceLocation resid="OMS.Page.Url"/>
            </Page>
            <Metadata>
              <SourceLocation resid="OMS.Functions.Metadata.Url"/>
            </Metadata>
            <Namespace resid="OMS.Namespace"/>
          </ExtensionPoint>
        </AllFormFactors>
        <DesktopFormFactor>
          <FunctionFile resid="OMS.Page.Url"/>
          <ExtensionPoint xsi:type="PrimaryCommandSurface">
            <OfficeTab id="TabHome">
              <Group id="OMS.Group">
                <Label resid="OMS.Group.Label"/>
                <Icon>
                  <bt:Image size="16" resid="OMS.Icon.16"/>
                  <bt:Image size="32" resid="OMS.Icon.32"/>
                  <bt:Image size="80" resid="OMS.Icon.80"/>
                </Icon>
                <Control xsi:type="Button" id="OMS.Taskpane.Button">
                  <Label resid="OMS.Taskpane.Label"/>
                  <Supertip>
                    <Title resid="OMS.Taskpane.Label"/>
                    <Description resid="OMS.Taskpane.Tooltip"/>
                  </Supertip>
                  <Icon>
                    <bt:Image size="16" resid="OMS.Icon.16"/>
                    <bt:Image size="32" resid="OMS.Icon.32"/>
                    <bt:Image size="80" resid="OMS.Icon.80"/>
                  </Icon>
                  <Action xsi:type="ShowTaskpane">
                    <TaskpaneId>OMSTaskpane</TaskpaneId>
                    <SourceLocation resid="OMS.Page.Url"/>
                  </Action>
                </Control>
              </Group>
            </OfficeTab>
          </ExtensionPoint>
        </DesktopFormFactor>
      </Host>
    </Hosts>
    <Resources>
      <bt:Images>
        <bt:Image id="OMS.Icon.16" DefaultValue="{base}/static/icons/icon-192.png"/>
        <bt:Image id="OMS.Icon.32" DefaultValue="{base}/static/icons/icon-192.png"/>
        <bt:Image id="OMS.Icon.80" DefaultValue="{base}/static/icons/icon-192.png"/>
      </bt:Images>
      <bt:Urls>
        <bt:Url id="OMS.Page.Url" DefaultValue="{base}/static/excel/taskpane.html"/>
        <bt:Url id="OMS.Functions.Script.Url" DefaultValue="{base}/static/excel/functions.js"/>
        <bt:Url id="OMS.Functions.Metadata.Url" DefaultValue="{base}/static/excel/functions.json"/>
      </bt:Urls>
      <bt:ShortStrings>
        <bt:String id="OMS.Namespace" DefaultValue="OMS"/>
        <bt:String id="OMS.Group.Label" DefaultValue="OMS Bonos"/>
        <bt:String id="OMS.Taskpane.Label" DefaultValue="OMS Bonos"/>
      </bt:ShortStrings>
      <bt:LongStrings>
        <bt:String id="OMS.Taskpane.Tooltip" DefaultValue="Configurar la conexión en tiempo real con la calculadora de bonos."/>
      </bt:LongStrings>
    </Resources>
  </VersionOverrides>
</OfficeApp>
"""


def lan_ip() -> Optional[str]:
    """IP LAN primaria del server (la de la ruta de salida). El connect() UDP no
    manda ningún paquete — sólo hace que el SO elija la interfaz. Para la
    tarjeta de instalación multi-máquina de /admin: el manifest tiene que
    apuntar a una dirección que TODAS las compus resuelvan, y el nombre NetBIOS
    de una notebook (DAM-NB-…) no lo es."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            return None if ip.startswith("127.") else ip
        except OSError:
            return None


@router.get("/manifest.xml")
async def manifest(request: Request, base: str = Query("")) -> Response:
    """Manifest del add-in con la URL base resuelta: `?base=` explícito (lo usa
    la tarjeta de instalación de /admin para fijar la IP), o app_base_url, o el
    host con el que se está bajando. Se descarga y se sideloadea en Excel — sin
    editar XML a mano. TODO el add-in queda clavado a esa base en esa máquina:
    para otra compu conviene bajarlo apuntado a la IP del server, no al nombre
    de la notebook."""
    base = (base or "").strip().rstrip("/")
    if base and not base.startswith(("http://", "https://")):
        base = ""                                    # sólo http(s); si no, fallback
    if not base:
        base = (settings.app_base_url or "").rstrip("/")
    if not base:
        base = f"{request.url.scheme}://{request.url.netloc}"
    xml = _MANIFEST_XML.format(app_id=_MANIFEST_ID, base=base)
    return Response(content=xml, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="oms-bonos-manifest.xml"'})
