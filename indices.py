
# -*- coding: utf-8 -*-
#%% Última versión de indices — adaptado a API BCRA v4 (con 'detalle')
# Extrae todos los índices necesarios para cálculos de renta fija argentina.

# =============================================================================
# Imports
# =============================================================================

import urllib3

import OMSsecrets  # noqa: F401 — auto-carga secrets.txt a os.environ
import dias_habiles
from utils import *  # trae: datetime, timedelta, pd, np, MonthEnd, requests, json, os, io, URLError, etc.

# Desactiva la advertencia al usar verify=False en requests.get
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================================================================
# Helpers generales
# =============================================================================

def _df_vacio_bcra():
    """DataFrame vacío estándar con columnas ['fecha', 'valor'].""" 
    return pd.DataFrame(columns=["fecha", "valor"])


def save_to_json(data_dict: dict, filename: str = "bcra_data_backup.json") -> None:
    """
    Guarda un diccionario de DataFrames en JSON.
    Cada DF debe tener índice 'fecha' (date) y UNA sola columna de valores.
    """
    payload = {}
    for key, df in data_dict.items():
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        tmp = df.copy()
        # nos aseguramos índice fecha
        if "fecha" in tmp.columns:
            tmp = tmp.set_index("fecha")
        tmp.index = pd.to_datetime(tmp.index)
        tmp.index.name = "fecha"
        payload[key] = tmp.to_json(orient="index", date_format="iso")

    with open(filename, "w") as f:
        json.dump(payload, f)


def load_from_json(filename: str = "bcra_data_backup.json") -> dict:
    """
    Carga el backup en formato JSON y devuelve {clave: DataFrame}.
    Índice = 'fecha' (datetime.date).
    """
    if not os.path.exists(filename):
        return {}

    with open(filename, "r") as f:
        raw = json.load(f)

    out = {}
    for key, txt in raw.items():
        df = pd.read_json(io.StringIO(txt), orient="index")
        df.index = pd.to_datetime(df.index).date
        df.index.name = "fecha"
        out[key] = df
    return out


# =============================================================================
# Llamadas API BCRA v4
# =============================================================================

def fetch_variable_data_api_v4(id_variable, fecha_desde, fecha_hasta,
                               offset=None, limit=None):
    """
    Obtiene datos de una variable (id_variable) desde 'fecha_desde' hasta 'fecha_hasta'
    usando la API v4 de Principales Variables del BCRA.

    Soporta el formato nuevo:
    {
      "results": [
        {
          "idVariable": 30,
          "detalle": [
            {"fecha": "2025-11-25", "valor": 658.180500},
            ...
          ]
        },
        ...
      ]
    }

    Y también el viejo (por compatibilidad):
    {
      "results": [
        {"idVariable": 30, "fecha": "2025-11-25", "valor": 658.180500},
        ...
      ]
    }

    Devuelve siempre un DataFrame con columnas: ['fecha', 'valor'] (fecha → date).
    Si hay error de red → None.
    Si la respuesta es válida pero vacía → DataFrame vacío con esas columnas.
    """
    base_url = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias"
    url = f"{base_url}/{id_variable}"

    params = {
        "desde": fecha_desde,
        "hasta": fecha_hasta,
    }
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    try:
        resp = requests.get(url, params=params, verify=False, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not isinstance(results, list) or len(results) == 0:
            print(f"[BCRA {id_variable}] 'results' vacío.")
            return pd.DataFrame(columns=["fecha", "valor"])

        filas = []
        for item in results:
            # Formato v4: tiene 'detalle'
            if "detalle" in item and isinstance(item["detalle"], list):
                for det in item["detalle"]:
                    fecha = det.get("fecha")
                    valor = det.get("valor")
                    if fecha is not None and valor is not None:
                        filas.append({"fecha": fecha, "valor": valor})
            else:
                # Formato viejo (v3-like): el registro ya trae 'fecha' y 'valor'
                fecha = item.get("fecha")
                valor = item.get("valor")
                if fecha is not None and valor is not None:
                    filas.append({"fecha": fecha, "valor": valor})

        if not filas:
            print(f"[BCRA {id_variable}] No se encontraron pares fecha/valor dentro de 'results'.")
            return pd.DataFrame(columns=["fecha", "valor"])

        df = pd.DataFrame(filas)
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
        return df

    except requests.exceptions.Timeout:
        print(f"[BCRA {id_variable}] Timeout consultando la API.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[BCRA {id_variable}] Error de red/HTTP: {e}")
        return None
    except ValueError:
        print(f"[BCRA {id_variable}] La respuesta de la API no es JSON válido.")
        return None


def fetch_principales_variables():
    """
    Trae el catálogo de variables monetarias disponibles en la API v4.
    Retorna un DataFrame (o None si hay error de red).
    No se usa en la lógica principal, pero lo dejamos global por si lo querés mirar.
    """
    url = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/"
    try:
        resp = requests.get(url, verify=False, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not isinstance(results, list):
            return pd.DataFrame()
        return pd.DataFrame(results)
    except requests.exceptions.RequestException as e:
        print(f"[BCRA catálogo] Error de red: {e}")
        return None


# Catálogo de variables: lazy (evita HTTP en import, solo se carga si se accede)
_principales_variables_df = None

def get_principales_variables_df():
    global _principales_variables_df
    if _principales_variables_df is None:
        tmp = fetch_principales_variables()
        _principales_variables_df = tmp if tmp is not None else pd.DataFrame()
    return _principales_variables_df


def __getattr__(name):
    """Backward compat: indices.principales_variables_df."""
    if name == "principales_variables_df":
        return get_principales_variables_df()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# =============================================================================
# Funciones auxiliares de proyección / calendario
# =============================================================================

def calcular_CER_diario_proyectado(df_inflamom, cer_inicial, fecha_inicial):
    """
    Proyecta el CER diario a partir de una serie de inflación mensual (df_inflamom)
    usando la metodología clásica del BCRA.

    df_inflamom: DataFrame indexado por fecha (datetime o date), columna 'inflacionmom'.
    cer_inicial: valor CER en fecha_inicial.
    fecha_inicial: date o datetime, último dato "observado" de CER.
    """
    if df_inflamom is None or df_inflamom.empty:
        raise ValueError("df_inflamom vacío en calcular_CER_diario_proyectado.")

    # Aseguramos índice tipo DatetimeIndex
    df_inflamom = df_inflamom.copy()
    df_inflamom.index = pd.to_datetime(df_inflamom.index)

    fecha_inicial = pd.to_datetime(fecha_inicial)

    rango_fechas = pd.date_range(
        start=fecha_inicial,
        end=df_inflamom.index.max() + MonthEnd(1),
        freq="D",
    )

    df_cer = pd.DataFrame(index=rango_fechas, columns=["CER"], dtype=float)
    df_cer.iloc[0, 0] = cer_inicial

    for fecha in rango_fechas[1:]:
        j_1 = (fecha - pd.DateOffset(months=1)).to_period("M")
        j_2 = (fecha - pd.DateOffset(months=2)).to_period("M")
        k = fecha.to_period("M").days_in_month
        k_1 = (fecha - pd.DateOffset(months=1)).to_period("M").days_in_month

        if fecha.day <= 15:
            # inflacion del mes j_2
            mask = df_inflamom.index.to_period("M") == j_2
        else:
            # inflacion del mes j_1
            mask = df_inflamom.index.to_period("M") == j_1

        if not mask.any():
            # si no tenemos ese mes, asumimos 0
            inflacion_mom = 0.0
        else:
            inflacion_mom = df_inflamom.loc[mask, "inflacionmom"].iloc[0]

        if fecha.day <= 15:
            F_t = (1 + inflacion_mom / 100.0) ** (1.0 / k_1)
        else:
            F_t = (1 + inflacion_mom / 100.0) ** (1.0 / k)

        df_cer.loc[fecha, "CER"] = df_cer.loc[fecha - pd.DateOffset(days=1), "CER"] * F_t

    df_cer.index = df_cer.index.date
    return df_cer


def proyectadeva(proyeccion_mensual, fecha_inicial, valor_inicial):
    """
    Proyecta la serie diaria del A3500 (tca3500) a partir de
    una proyección mensual de tipo de cambio oficial.

    proyeccion_mensual: dict {'YYYY-MM-DD': valor}
    fecha_inicial: 'YYYY-MM-DD' string
    valor_inicial: float
    """
    serie_temporal = []
    fechas = sorted(proyeccion_mensual.keys())
    fechas_dt = [datetime.strptime(fecha, "%Y-%m-%d").date() for fecha in fechas]

    fecha_siguiente = datetime.strptime(fecha_inicial, "%Y-%m-%d").date() + timedelta(days=1)
    proyeccion_anterior = valor_inicial

    for fecha_actual in fechas_dt:
        proyeccion_actual = proyeccion_mensual[fecha_actual.strftime("%Y-%m-%d")]

        while fecha_siguiente < fecha_actual:
            dias_entre_fechas = (fecha_actual - fecha_siguiente).days
            if dias_entre_fechas <= 0:
                break
            tasa_diaria = (proyeccion_actual / proyeccion_anterior) ** (1 / dias_entre_fechas)
            proyeccion_diaria = proyeccion_anterior * tasa_diaria

            serie_temporal.append((fecha_siguiente, proyeccion_diaria))
            fecha_siguiente += timedelta(days=1)
            proyeccion_anterior = proyeccion_diaria

    df = pd.DataFrame(serie_temporal, columns=["Fecha", "tca3500"])
    if df.empty:
        return df  # nada que proyectar
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df.set_index("Fecha", inplace=True)
    df.index = df.index.date
    return df


def _calendario_habiles_30_anios(fecha_inicio: datetime) -> np.ndarray:
    """
    Genera un array de fechas hábiles (sin fines de semana ni feriados de dias_habiles.ar_holidays)
    para los próximos 30 años calendario a partir del día siguiente a fecha_inicio.
    """
    inicio_fechas_futuras = fecha_inicio + pd.Timedelta(days=1)
    fechas_futuras = pd.date_range(inicio_fechas_futuras, periods=30 * 365, freq="D")
    fechas_futuras_habiles = np.array(
        [
            fecha
            for fecha in fechas_futuras
            if fecha.weekday() < 5
            and fecha.strftime("%Y-%m-%d") not in dias_habiles.ar_holidays
        ],
        dtype="datetime64[D]",
    )
    return fechas_futuras_habiles


def _calcular_start_date_por_backup(backup: dict, default_days_back: int = 365):
    """
    Calcula (start_date, end_date, no_hay_datos_nuevos) usando la info del backup.

    Lógica corregida para no dejar series "colgadas" (por ej. TAMAR):

    - Si no hay backup o está vacío → pedimos default_days_back días para atrás.
    - Si hay backup:
        * Para cada serie, tomamos la última fecha REAL (≤ hoy).
        * Si la MÍNIMA de esas fechas < hoy → pedimos desde (mínima + 1) hasta hoy.
        * Si la mínima ≥ hoy → ya estamos al día, no hace falta pedir nada nuevo.
    """
    hoy = datetime.now().date()

    if not backup:
        start = hoy - timedelta(days=default_days_back)
        return start.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d"), False

    ultimas = {}
    for k in ("a3500", "badlar", "CER", "UVA", "tamar", "inflamom"):
        df = backup.get(k)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        idx = pd.to_datetime(df.index).date
        mask = idx <= hoy
        if not mask.any():
            continue
        ultimas[k] = max(idx[mask])

    if not ultimas:
        start = hoy - timedelta(days=default_days_back)
        return start.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d"), False

    # Usamos la mínima última fecha entre las series para no saltearnos
    # días de ninguna serie (si alguna se quedó atrasada, la rellenamos).
    ultima_min = min(ultimas.values())

    if ultima_min >= hoy:
        # todas las series tienen al menos hasta hoy → nada nuevo
        return hoy.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d"), True

    start = ultima_min + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d"), False


# =============================================================================
# Proyecciones “hardcodeadas” (escenario base)
# =============================================================================

proyeccion_inflacion_mensual = {
    "Apr-26": 2.6+0.1,
    "May-26": 1.8+0.1,
    "Jun-26": 1.6+0.1,
    "Jul-26": 1.2+0.1,
    "Aug-26": 1.1+0.1,
    "Sep-26": 1.3+0.1,
    "Oct-26": 1.3+0.1,
    "Nov-26": 1.2+0.1,
    "Dec-26": 1.3+0.1,
    "Jan-27": 1.2+0.1,
    "Feb-27": 1.3,
    "Mar-27": 1.3,
    "Apr-27": 1.0,
    "May-27": 0.6,
    "Jun-27": 0.5,
    "Jul-27": 0.5,
    "Aug-27": 0.5,
    "Sep-27": 0.5,
    "Oct-27": 0.5,
    "Nov-27": 0.5,
    "Dec-27": 0.5,
    "Jan-28": 0.5,
    "Feb-28": 0.5,
    "Mar-28": 0.5,
    "Apr-28": 0.5,
    "May-28": 0.5,
    "Jun-28": 0.5,
    "Jul-28": 0.5,
    "Aug-28": 0.5,
    "Sep-28": 0.5,
    "Oct-28": 0.5,
    "Nov-28": 0.5,
    "Dec-28": 0.5,
    "Jan-29": 0.5,
    "Feb-29": 0.5,
    "Mar-29": 0.5,
    "Apr-29": 0.5,
    "May-29": 0.5,
    "Jun-29": 0.5,
    "Jul-29": 0.5,
    "Aug-29": 0.5,
    "Sep-29": 0.5,
    "Oct-29": 0.5,
    "Nov-29": 0.5,
    "Dec-29": 0.5,
    "Jan-30": 0.5,
    "Feb-30": 0.5,
    "Mar-30": 0.4,
    "Apr-30": 0.4,
    "May-30": 0.4,
    "Jun-30": 0.35,
    "Jul-30": 0.35,
    "Aug-30": 0.35,
    "Sep-30": 0.35,
    "Oct-30": 0.35,
    "Nov-30": 0.35,
    "Dec-30": 0.35,
}

proyeccion_devaoficial_escenariobase = {
    "2025-06-30": 1145.00,
    "2025-07-31": 1160.00,
    "2025-08-29": 1178.00,
    "2025-09-30": 1198.00,
    "2025-10-31": 1225.50,
    "2025-11-28": 1248.00,
    "2025-12-30": 1270.00,
    "2026-01-30": 1270.00,
    "2026-02-27": 1270.00,
    "2026-03-31": 1270.00,
    "2026-04-30": 1270.00,
    "2026-05-29": 1270.00,
    "2026-06-30": 1270.00,
    "2026-07-31": 1270.00,
    "2026-08-31": 1270.00,
    "2026-09-30": 1270.00,
    "2026-10-31": 1270.00,
    "2026-11-30": 1270.00,
}

import logging

# -----------------------------------------------------------------------------
# FX A3500 en tiempo real — waterfall: MAE → BYMA DLR/SPOT → serie → default
# Cache thread-safe 30s para no bombardear APIs en cada cálculo de bono.
# -----------------------------------------------------------------------------
import threading
import time as _time

_log_fx = logging.getLogger("indices_fx")

_FX_CACHE_TTL = 30
_fx_lock = threading.Lock()
_fx_cached = None
_fx_cached_ts = 0.0
_fx_cached_source = "none"


def _fx_cache_valid():
    return _fx_cached is not None and (_time.time() - _fx_cached_ts) < _FX_CACHE_TTL


def _fetch_fx_mae(timeout=2):
    api_key = os.getenv("MAE_API_KEY")
    if not api_key:
        return None  # sin key → fallback a BYMA / serie / default
    for intento in range(2):
        try:
            r = requests.get(
                "https://api.mae.com.ar/MarketData/v1/mercado/cotizaciones/forex",
                headers={"x-api-key": api_key},
                timeout=timeout,
            )
            if not r.ok:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue
            for plazo in ("000", "001"):
                for row in data:
                    if (row.get("ticker") == "UST$T"
                        and row.get("segmento") == "Mayorista"
                        and row.get("plazo") == plazo):
                        precio = float(row["precioUltimo"])
                        if precio > 0:
                            return precio
        except Exception:
            pass
    return None


def _fetch_fx_byma_dlr_spot(session):
    """DLR/SPOT desde BYMA — requiere session autenticada."""
    if session is None:
        return None
    try:
        resp = session.get(
            "https://api.latinsecurities.matrizoms.com.ar/rest/marketdata/get",
            params={"marketId": "ROFX", "symbol": "DLR/SPOT",
                    "entries": "LA,CL,SE", "depth": 1},
            timeout=2,
        )
        if not resp.ok:
            return None
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("LA", "SE", "CL"):
        val = data.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            p = val.get("price")
        elif isinstance(val, list) and val:
            p = val[0].get("price") if isinstance(val[0], dict) else val[0]
        else:
            continue
        if p is not None:
            try:
                pf = float(p)
                if pf > 0:
                    return pf
            except (ValueError, TypeError):
                pass
    return None


def _get_a3500_from_inputs(inputs_dict=None):
    """Último A3500 de la serie (el del día anterior)."""
    try:
        if inputs_dict is not None:
            df = inputs_dict.get("a3500")
        else:
            import rentafija
            df = rentafija.inputs.get("a3500")
        if df is not None and not df.empty:
            val = float(df.iloc[-1]["tca3500"])
            if val > 0:
                return val
    except Exception:
        pass
    return None


def get_fx_hoy(session=None, force_refresh=False, default=1200.0):
    """Waterfall: MAE → BYMA DLR/SPOT → serie rentafija → default. Cache 30s."""
    global _fx_cached, _fx_cached_ts, _fx_cached_source
    with _fx_lock:
        if not force_refresh and _fx_cache_valid():
            return _fx_cached
    fx = _fetch_fx_mae()
    if fx is not None:
        source = "MAE"
    else:
        fx = _fetch_fx_byma_dlr_spot(session)
        if fx is not None:
            source = "BYMA_DLR/SPOT"
        else:
            fx = _get_a3500_from_inputs()
            if fx is not None:
                source = "A3500_serie"
            else:
                fx = default
                source = "default"
    with _fx_lock:
        _fx_cached = fx
        _fx_cached_ts = _time.time()
        _fx_cached_source = source
    _log_fx.info(f"[FX] {fx:.4f} ({source})")
    return fx


def refresh_a3500_in_rentafija(session=None, force=False):
    """Obtiene FX actual y lo inyecta en rentafija.inputs['a3500'] para hoy."""
    import rentafija
    fx = get_fx_hoy(session=session, force_refresh=force)
    fecha_hoy = datetime.now().date().isoformat()
    try:
        rentafija.inputs['a3500'].loc[fecha_hoy, 'tca3500'] = fx
    except Exception as e:
        _log_fx.error(f"[FX] Error inyectando en rentafija: {e}")
    return fx


def fx_status_text():
    if _fx_cached is None:
        return "FX: sin datos"
    ts = datetime.fromtimestamp(_fx_cached_ts).strftime("%H:%M:%S") if _fx_cached_ts > 0 else "N/A"
    return f"FX A3500: {_fx_cached:,.4f} ({_fx_cached_source} @ {ts})"


def invalidate_fx_cache():
    global _fx_cached, _fx_cached_ts
    with _fx_lock:
        _fx_cached = None
        _fx_cached_ts = 0.0


# =============================================================================
# Daemon: refresca FX cada `interval` segundos para que get_fx_hoy() siempre
# encuentre cache caliente y no bloquee el render.
# =============================================================================

_fx_thread = None
_fx_thread_lock = threading.Lock()


def start_fx_background(session=None, interval: int = 10):
    """Daemon idempotente que llama a get_fx_hoy(force_refresh=True) cada
    `interval` segundos. Si ya hay uno corriendo, no spawnea otro.
    """
    global _fx_thread
    with _fx_thread_lock:
        if _fx_thread is not None and _fx_thread.is_alive():
            return _fx_thread

        def _loop():
            while True:
                try:
                    get_fx_hoy(session=session, force_refresh=True)
                except Exception as e:
                    _log_fx.warning(f"[FX bg] error: {e}")
                _time.sleep(interval)

        t = threading.Thread(target=_loop, daemon=True, name="fx-bg")
        t.start()
        _fx_thread = t
        return t


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Obtiene series históricas + proyecciones, con fallback a backup JSON.
    Devuelve un dict con las claves (para rentafija):

      'a3500', 'badlar', 'tamar', 'CER',
      'a3500_proyectado', 'badlar_proyectado', 'tamar_proyectado', 'cer_proyectado',
      'UVA', 'uva_proyectado',
      'inflamom'
    """
    # 1) Cargar backup (si existe)
    backup = load_from_json()
    hoy = datetime.now().date()

    # Aseguramos que existan claves básicas aunque estén vacías
    def _empty_series(colname):
        df = pd.DataFrame(columns=[colname])
        df.index.name = "fecha"
        return df

    a3500_hist = backup.get("a3500", _empty_series("tca3500"))
    badlar_hist = backup.get("badlar", _empty_series("BADLAR"))
    tamar_hist = backup.get("tamar", _empty_series("TAMAR"))
    cer_hist = backup.get("CER", _empty_series("CER"))
    uva_hist = backup.get("UVA", _empty_series("UVA"))
    inflamom_hist = backup.get("inflamom", _empty_series("inflacionmom"))

    # 2) Fechas a consultar en BCRA
    start_date, end_date, no_hay_datos_nuevos = _calcular_start_date_por_backup(backup, default_days_back=365)
    print(f"Ventana a consultar BCRA: {start_date} → {end_date} (no_hay_datos_nuevos={no_hay_datos_nuevos})")

    if no_hay_datos_nuevos:
        # Nada nuevo, usamos DFs vacíos "nuevos"
        a3500_new_df = _df_vacio_bcra()
        badlar_new_df = _df_vacio_bcra()
        tamar_new_df = _df_vacio_bcra()
        cer_new_df = _df_vacio_bcra()
        inflamom_new_df = _df_vacio_bcra()
        uva_new_df = _df_vacio_bcra()
        # POMO no lo usamos más abajo, lo ignoramos
    else:
        # A3500
        a3500_new_df = fetch_variable_data_api_v4(5, start_date, end_date)
        if a3500_new_df is None:
            print("ERROR: No se pudieron obtener los datos A3500. Usando solo backup.")
            a3500_new_df = _df_vacio_bcra()

        # BADLAR
        badlar_new_df = fetch_variable_data_api_v4(7, start_date, end_date)
        if badlar_new_df is None:
            print("ERROR: No se pudieron obtener los datos BADLAR. Usando solo backup.")
            badlar_new_df = _df_vacio_bcra()

        # TAMAR
        tamar_new_df = fetch_variable_data_api_v4(44, start_date, end_date)
        if tamar_new_df is None:
            print("ERROR: No se pudieron obtener los datos TAMAR. Usando solo backup.")
            tamar_new_df = _df_vacio_bcra()

        # CER
        cer_new_df = fetch_variable_data_api_v4(30, start_date, end_date)
        if cer_new_df is None:
            print("ERROR: No se pudieron obtener los datos CER. Usando solo backup.")
            cer_new_df = _df_vacio_bcra()

        # INFLAMOM
        inflamom_new_df = fetch_variable_data_api_v4(27, start_date, end_date)
        if inflamom_new_df is None:
            print("ERROR: No se pudieron obtener los datos INFLAMOM. Usando solo backup.")
            inflamom_new_df = _df_vacio_bcra()

        # UVA
        uva_new_df = fetch_variable_data_api_v4(31, start_date, end_date)
        if uva_new_df is None:
            print("ERROR: No se pudieron obtener los datos UVA. Usando solo backup.")
            uva_new_df = _df_vacio_bcra()

    # 3) Unificamos cada serie (histórico + nuevos)

    # A3500
    a3500_hist_df = a3500_hist.reset_index()
    a3500_hist_df.columns = ["fecha", "tca3500"]
    if not a3500_new_df.empty:
        a3500_new_df = a3500_new_df.rename(columns={"valor": "tca3500"})
        a3500_new_df = a3500_new_df[["fecha", "tca3500"]]
    frames = [df for df in (a3500_hist_df, a3500_new_df) if not df.empty]
    combined_df_a3500 = pd.concat(frames, ignore_index=True) if frames else a3500_hist_df.copy()
    if not combined_df_a3500.empty:
        combined_df_a3500["fecha"] = pd.to_datetime(combined_df_a3500["fecha"]).dt.date
        combined_df_a3500 = combined_df_a3500[combined_df_a3500["fecha"] <= hoy]
        combined_df_a3500 = (
            combined_df_a3500.sort_values("fecha")
            .drop_duplicates("fecha", keep="first")
            .set_index("fecha")
        )
        print(f"El último dólar A3500: {combined_df_a3500.iloc[-1].item()} // {combined_df_a3500.index[-1]} ")
    else:
        combined_df_a3500 = _empty_series("tca3500")

    # BADLAR
    badlar_hist_df = badlar_hist.reset_index()
    badlar_hist_df.columns = ["fecha", "BADLAR"]
    if not badlar_new_df.empty:
        badlar_new_df = badlar_new_df.rename(columns={"valor": "BADLAR"})
        badlar_new_df = badlar_new_df[["fecha", "BADLAR"]]
    frames = [df for df in (badlar_hist_df, badlar_new_df) if not df.empty]
    combined_df_badlar = pd.concat(frames, ignore_index=True) if frames else badlar_hist_df.copy()
    if not combined_df_badlar.empty:
        combined_df_badlar["fecha"] = pd.to_datetime(combined_df_badlar["fecha"]).dt.date
        combined_df_badlar = combined_df_badlar[combined_df_badlar["fecha"] <= hoy]
        combined_df_badlar = (
            combined_df_badlar.sort_values("fecha")
            .drop_duplicates("fecha", keep="first")
            .set_index("fecha")
        )
        print(f"El último Badlar: {combined_df_badlar.iloc[-1].item()} // {combined_df_badlar.index[-1]} ")
        badlar_aplicable = combined_df_badlar.tail(5)["BADLAR"].mean()
    else:
        combined_df_badlar = _empty_series("BADLAR")
        badlar_aplicable = 0.0

    # TAMAR
    tamar_hist_df = tamar_hist.reset_index()
    tamar_hist_df.columns = ["fecha", "TAMAR"]
    if not tamar_new_df.empty:
        tamar_new_df = tamar_new_df.rename(columns={"valor": "TAMAR"})
        tamar_new_df = tamar_new_df[["fecha", "TAMAR"]]
    frames = [df for df in (tamar_hist_df, tamar_new_df) if not df.empty]
    combined_df_tamar = pd.concat(frames, ignore_index=True) if frames else tamar_hist_df.copy()

    if combined_df_tamar.empty:
        print("WARNING: No hay datos de TAMAR. Usando BADLAR como proxy.")
        tmp = combined_df_badlar.reset_index()
        tmp.columns = ["fecha", "TAMAR"]
        combined_df_tamar = tmp

    combined_df_tamar["fecha"] = pd.to_datetime(combined_df_tamar["fecha"]).dt.date
    combined_df_tamar = combined_df_tamar[combined_df_tamar["fecha"] <= hoy]
    combined_df_tamar = (
        combined_df_tamar.sort_values("fecha")
        .drop_duplicates("fecha", keep="first")
        .set_index("fecha")
    )
    print(f"El último Tamar: {combined_df_tamar.iloc[-1].item()} // {combined_df_tamar.index[-1]} ")
    tamar_aplicable = combined_df_tamar.tail(5)["TAMAR"].mean()
    tamar_aplicable_10d = combined_df_tamar.tail(10)["TAMAR"].mean()
    tamar_aplicable_tem = 100 * (
        ((1 + ((tamar_aplicable_10d / 100) / (365 / 32))) ** (365 / 32)) ** (1 / 12) - 1
    )
    print(f"Tamar aplicable 5d: {tamar_aplicable}")
    print(f"Tamar aplicable 10d: {tamar_aplicable_10d}")
    print(f"Tamar aplicable 10d tem: {tamar_aplicable_tem:.6f}")

    # CER
    cer_hist_df = cer_hist.reset_index()
    cer_hist_df.columns = ["fecha", "CER"]
    if not cer_new_df.empty:
        cer_new_df = cer_new_df.rename(columns={"valor": "CER"})
        cer_new_df = cer_new_df[["fecha", "CER"]]
    frames = [df for df in (cer_hist_df, cer_new_df) if not df.empty]
    combined_df_cer = pd.concat(frames, ignore_index=True) if frames else cer_hist_df.copy()
    if not combined_df_cer.empty:
        combined_df_cer["fecha"] = pd.to_datetime(combined_df_cer["fecha"]).dt.date
        combined_df_cer = combined_df_cer[combined_df_cer["fecha"] <= hoy]
        combined_df_cer = (
            combined_df_cer.sort_values("fecha")
            .drop_duplicates("fecha", keep="first")
            .set_index("fecha")
        )
        print(f"El último CER:   {combined_df_cer.iloc[-1].item():.4f} // {combined_df_cer.index[-1]} ")
    else:
        combined_df_cer = _empty_series("CER")

    # INFLAMOM (histórico puro, sin proyección aún)
    inflamom_hist_df = inflamom_hist.reset_index()
    inflamom_hist_df.columns = ["fecha", "inflacionmom"]

    if not inflamom_new_df.empty:
        inflamom_new_df = inflamom_new_df.rename(columns={"valor": "inflacionmom"})
        inflamom_new_df = inflamom_new_df[["fecha", "inflacionmom"]]

    frames = [df for df in (inflamom_hist_df, inflamom_new_df) if not df.empty]
    combined_df_inflamom = pd.concat(frames, ignore_index=True) if frames else inflamom_hist_df.copy()

    if not combined_df_inflamom.empty:
        combined_df_inflamom["fecha"] = pd.to_datetime(combined_df_inflamom["fecha"]).dt.date
        combined_df_inflamom = combined_df_inflamom[combined_df_inflamom["fecha"] <= hoy]
        combined_df_inflamom = (
            combined_df_inflamom.sort_values("fecha")
            .drop_duplicates("fecha", keep="last")  # <- CLAVE: gana lo más nuevo
            .set_index("fecha")
        )
        print(f"El último dato inflación MOM (observado):  {combined_df_inflamom.iloc[-1].item():.4f} // {combined_df_inflamom.index[-1]} ")
    else:
        combined_df_inflamom = _empty_series("inflacionmom")
        print("WARNING: Serie de inflación MOM vacía.")


    # UVA
    uva_hist_df = uva_hist.reset_index()
    uva_hist_df.columns = ["fecha", "UVA"]
    if not uva_new_df.empty:
        uva_new_df = uva_new_df.rename(columns={"valor": "UVA"})
        uva_new_df = uva_new_df[["fecha", "UVA"]]
    frames = [df for df in (uva_hist_df, uva_new_df) if not df.empty]
    combined_df_uva = pd.concat(frames, ignore_index=True) if frames else uva_hist_df.copy()
    if not combined_df_uva.empty:
        combined_df_uva["fecha"] = pd.to_datetime(combined_df_uva["fecha"]).dt.date
        combined_df_uva = combined_df_uva[combined_df_uva["fecha"] <= hoy]
        combined_df_uva = (
            combined_df_uva.sort_values("fecha")
            .drop_duplicates("fecha", keep="first")
            .set_index("fecha")
        )
        print(f"El último UVA: {combined_df_uva.iloc[-1].item()} // {combined_df_uva.index[-1]}")
    else:
        combined_df_uva = _empty_series("UVA")

    # 4) Proyección inflación mensual + CER proyectado
    #    Armamos df de proyección base
    proy_inf_df = pd.DataFrame(list(proyeccion_inflacion_mensual.items()), columns=["d", "inflacionmomproy"])
    proy_inf_df["d"] = pd.to_datetime(proy_inf_df["d"], format="%b-%y").dt.strftime("%Y-%m-%d")
    proy_inf_df.set_index("d", inplace=True)
    proy_inf_df.index = (
        pd.to_datetime(proy_inf_df.index)
        .to_period("M")
        .to_timestamp("M")
        .date
    )
    proy_inf_df.rename(columns={"inflacionmomproy": "inflacionmom"}, inplace=True)
    proy_inf_df.index.name = "fecha"
    proy_inf_df.sort_index(inplace=True)

    # Combinamos proyección + histórico
    if not combined_df_inflamom.empty:
        df_inflamom_combinado = combined_df_inflamom.combine_first(proy_inf_df)
    else:
        df_inflamom_combinado = proy_inf_df.copy()
    df_inflamom_combinado.sort_index(inplace=True)

    # CER proyectado
    if not combined_df_cer.empty and not df_inflamom_combinado.empty:
        cer_inicial = combined_df_cer["CER"].iloc[-1]
        fecha_inicial_cer = combined_df_cer.index[-1]
        df_cer_proyectado = calcular_CER_diario_proyectado(
            df_inflamom_combinado,
            cer_inicial,
            fecha_inicial_cer,
        )
        cer_completo_escenario_base = pd.concat(
            [combined_df_cer.iloc[:-1], df_cer_proyectado],
            axis=0,
        )
    else:
        cer_completo_escenario_base = combined_df_cer.copy()

    cer_completo_escenario_base.to_csv("cer_completo.csv", header=["Proyeccion CER"])

    # UVA proyectado desde CER
    if not cer_completo_escenario_base.empty:
        uva_completo_escenario_base = cer_completo_escenario_base * 2.5217
        uva_completo_escenario_base.columns = ["UVA"]
    else:
        uva_completo_escenario_base = combined_df_uva.copy()

    # 5) Proyección BADLAR y TAMAR a 30 años hábiles
    if not combined_df_badlar.empty:
        hoy_badlar = pd.to_datetime(combined_df_badlar.index[-1])
        fechas_habiles_badlar = _calendario_habiles_30_anios(hoy_badlar)
        if len(fechas_habiles_badlar) > 0:
            nuevos_badlar = pd.DataFrame(
                {"BADLAR": [badlar_aplicable] * len(fechas_habiles_badlar)},
                index=pd.to_datetime(fechas_habiles_badlar).date,
            )
            nuevos_badlar.index.name = "fecha"
            badlar_serie_completa = pd.concat([combined_df_badlar, nuevos_badlar])
        else:
            badlar_serie_completa = combined_df_badlar.copy()
    else:
        badlar_serie_completa = combined_df_badlar.copy()

    if not combined_df_tamar.empty:
        hoy_tamar = pd.to_datetime(combined_df_tamar.index[-1])
        fechas_habiles_tamar = _calendario_habiles_30_anios(hoy_tamar)
        if len(fechas_habiles_tamar) > 0:
            nuevos_tamar = pd.DataFrame(
                {"TAMAR": [tamar_aplicable] * len(fechas_habiles_tamar)},
                index=pd.to_datetime(fechas_habiles_tamar).date,
            )
            nuevos_tamar.index.name = "fecha"
            tamar_serie_completa = pd.concat([combined_df_tamar, nuevos_tamar])
        else:
            tamar_serie_completa = combined_df_tamar.copy()
    else:
        tamar_serie_completa = combined_df_tamar.copy()

    # 6) Proyección A3500 (oficial)
    if not combined_df_a3500.empty:
        fecha_inicial_a3500 = combined_df_a3500.index[-1].strftime("%Y-%m-%d")
        valor_inicial_a3500 = combined_df_a3500.iloc[-1]["tca3500"]
        a3500_proy_escenario_base = proyectadeva(
            proyeccion_devaoficial_escenariobase,
            fecha_inicial_a3500,
            valor_inicial_a3500,
        )
        if not a3500_proy_escenario_base.empty:
            a3500_completo_escenario_base = pd.concat(
                [combined_df_a3500, a3500_proy_escenario_base],
                axis=0,
            )
        else:
            a3500_completo_escenario_base = combined_df_a3500.copy()
    else:
        a3500_completo_escenario_base = combined_df_a3500.copy()

    # 7) Empaquetado final
    data = {
        "a3500": combined_df_a3500,
        "badlar": combined_df_badlar,
        "tamar": combined_df_tamar,
        "CER": combined_df_cer,
        "a3500_proyectado": a3500_completo_escenario_base,
        "badlar_proyectado": badlar_serie_completa,
        "tamar_proyectado": tamar_serie_completa,
        "cer_proyectado": cer_completo_escenario_base,
        "UVA": combined_df_uva,
        "uva_proyectado": uva_completo_escenario_base,
        "inflamom": df_inflamom_combinado,
        "inflamom_observado": combined_df_inflamom,
    }

    # 8) Guardar backup
    #    - Históricas reales para todo.
    #    - En inflamom guardamos df_inflamom_combinado (hist + proy),
    #      pero al reconstruir combined_df_inflamom siempre recortamos a fechas ≤ hoy.
    backup_payload = {
        "a3500": combined_df_a3500,
        "badlar": combined_df_badlar,
        "tamar": combined_df_tamar,
        "CER": combined_df_cer,
        "UVA": combined_df_uva,
        "inflamom": combined_df_inflamom,
    }
    save_to_json(backup_payload)

    return data


if __name__ == "__main__":
    inputs = main()
    if isinstance(inputs, dict):
        print("Series disponibles:", list(inputs.keys()))
    if isinstance(inputs, dict):
        print("Series disponibles:", list(inputs.keys()))
