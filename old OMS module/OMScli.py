#%% OMScli.py — VS Code / Jupyter (con highlight y speed_mode)
# =============================================================
# Nota 02/2026:
#   Se refactorizó para que las constantes/listas (CURVAS, FUTUROS_DLR, etc.)
#   vivan en OMSdata.py y así OMSweb_app no dependa de OMScli.

from __future__ import annotations

import threading
import time
from pathlib import Path
import re
from functools import lru_cache
from contextlib import suppress

import numpy as np
import pandas as pd
import requests
from IPython.display import display, clear_output
from pandas.tseries.offsets import MonthEnd

from dias_habiles import siguiente_dia_habil_ar
from plotter import graficar_duration_tem_nss

import OMSapi, OMSmktdata, OMSprices
from especies import BONDS
from OMSdata import (
    CURVAS,
    FUTUROS_DLR,
    CURVAS_LABELS,
    BYMA_TICKERS,
    get_a3500_spot,
    parsear_vencimiento,
    settlement_str_from_plazo,
)

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────
# ⚡ Si querés máxima velocidad (sin estilos/colores y con menos I/O),
#    poné esto en True o pasá speed_mode=True al start_auto_refresh:
SPEED_MODE_DEFAULT = False
EXCEL_OUTPUT = False  # poné False para evitar escribir .xlsx (aún más rápido)

# Meses en castellano (3 letras)
MESES_3L = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}
# Regex: MES (3 letras) + AÑO (2 dígitos) + SUFIJO ALFABÉTICO OPCIONAL
CODIGO_REGEX = re.compile(r"[A-Z]+/([A-ZÁ]{3})(\d{2})([A-Z]*)$")


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main(plazo: str = "24hs", speed_mode: bool = SPEED_MODE_DEFAULT):
    """Descarga BYMA, calcula métricas y muestra curvas + ROFEX."""
    now = pd.Timestamp.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🕒 Última actualización: {ts}\n")

    # 1) Login
    session = OMSapi.login("delta_api", "D3lt41210*-*")

    # 2) BYMA masivo (bulk) — solo tickers "reales" (uppercase)
    tickers_curvas = sorted({c for lst in CURVAS.values() for c in lst})
    symbols = [f"MERV - XMEV - {c} - {plazo}" for c in tickers_curvas]
    raw_md = OMSmktdata.bulk_market_data(session, symbols)

    px = OMSprices.last_price(raw_md).rename(
        columns={"last": "Last Price", "close": "Close Price", "variation": "Variación"}
    )

    # Extracción de código vectorizada
    idx = px.index.to_series()
    px["Código"] = idx.str.split(" - ", expand=True).iloc[:, 2]
    px = px.loc[px["Código"].isin(tickers_curvas)].copy()

    # Settlement explícito (mejora CI vs 24hs)
    settle = settlement_str_from_plazo(plazo)

    # Métricas por especie (memo simple por corrida)
    _metrics_cache = {}

    def _metrics_for(code, price):
        key = (code, float(price) if pd.notna(price) else None, settle)
        if key not in _metrics_cache:
            _metrics_cache[key] = BONDS[code].metrics(price, settlement_date=settle)
        return _metrics_cache[key]

    metrics = pd.DataFrame(
        (_metrics_for(c, p) for c, p in zip(px["Código"].values, px["Last Price"].values)),
        index=px["Código"].values,
    ).reset_index().rename(columns={"index": "Código"})

    tabla_base = px.reset_index(drop=True).merge(metrics, on="Código", how="left")

    # ── Helpers de tablas ─────────────────────────────────────────────
    def tabla_curva(df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
        """Subtabla ordenada por Duration y con tem_spread incremental."""
        sub = df[df["Código"].isin(tickers)].copy()
        tem_aux = pd.to_numeric(sub["TEM"], errors="coerce")
        if np.nanmax(np.abs(tem_aux)) < 1.5:
            tem_aux = tem_aux * 100
        sub["tem_spread"] = tem_aux.diff().fillna(0)

        front = ["Código", "Close Price", "Last Price", "Variación"]
        cols_rest = [c for c in sub.columns if c not in front]
        return sub[front + cols_rest].sort_values("Duration").reset_index(drop=True)

    def tabla_futuros(session, symbols, a3500_spot: float) -> pd.DataFrame:
        """ROFEX: Settlement (SE) como Close, Last (LA), Variación vs Close,
        y TNA/TEA implícitas vs spot A3500. Acepta sufijos 'A'."""
        raw = OMSmktdata.bulk_market_data(session, symbols)
        px = OMSprices.last_price(raw).rename(
            columns={"last": "Last Price", "close": "Close Price", "variation": "Variación"}
        )
        if px.empty or "Last Price" not in px.columns:
            return pd.DataFrame(
                columns=[
                    "Código",
                    "Close Price",
                    "Last Price",
                    "Variación",
                    "Dias Vto",
                    "Tasa Directa",
                    "TNA",
                    "TEA",
                    "Canal",
                ]
            )

        px["Código"] = px.index

        # Close desde SE si falta
        if "Close Price" not in px.columns:
            px["Close Price"] = [raw.get(sym, {}).get("SE", {}).get("price") for sym in symbols]

        # Variación vs Close si falta
        if "Variación" not in px.columns:
            with np.errstate(divide="ignore", invalid="ignore"):
                px["Variación"] = px["Last Price"] / px["Close Price"] - 1

        now = pd.Timestamp.now()
        codigos = px["Código"].astype(str)
        uniques = codigos.unique()
        maturity_map = {c: parsear_vencimiento(c) for c in uniques}
        px["maturity"] = codigos.map(maturity_map)

        # Canal: Mayorista si termina en 'A'
        def _canal(c: str) -> str:
            m = CODIGO_REGEX.search(str(c))
            suf = (m.group(3) if m else "")
            return "Mayorista" if (suf and suf.endswith("A")) else "Minorista"

        px["Canal"] = codigos.map(_canal)

        # Dias a vto
        px["Dias Vto"] = (px["maturity"] - now).dt.days.astype("Int64")

        # Tasa directa y TNA/TEA (evitar días <= 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            tasa_dir = px["Last Price"] / float(a3500_spot) - 1
            dias = (px["maturity"] - now).dt.days
            dias_pos = dias.where(dias > 0)
            TNA = tasa_dir * (365 / dias_pos)
            TEA = (1 + tasa_dir) ** (365 / dias_pos) - 1

        out = px[["Código", "Close Price", "Last Price", "Variación", "Dias Vto", "maturity", "Canal"]].copy()
        out["Tasa Directa"] = tasa_dir.astype(float)
        out["TNA"] = TNA.astype(float)
        out["TEA"] = TEA.astype(float)

        out = out.sort_values(by="maturity").reset_index(drop=True)
        return out.drop(columns=["maturity"])

    # ── Estilos (colores y barras) ────────────────────────────────────
    def style_row(row):
        col = "green" if row["Variación"] > 0 else "red" if row["Variación"] < 0 else "black"
        return pd.Series({"Last Price": f"color:{col}; font-weight:bold;", "Variación": f"color:{col};"})

    def style_curva(df):
        fmt = {
            "Close Price": "{:,.4f}",
            "Last Price": "{:,.4f}",
            "Variación": "{:+.2%}",
            "TIREA": "{:.2%}",
            "TNA": "{:.2%}",
            "TEM": "{:.2%}",
            "Paridad": "{:,.4f}",
            "Duration": "{:.4f}",
            "tem_spread": "{:+.2%}",
        }
        lim = pd.to_numeric(df["Variación"], errors="coerce").abs().max()
        vmin, vmax = (-lim, lim) if np.isfinite(lim) and lim > 0 else (-1.0, 1.0)
        return (
            df.style.format(fmt)
            .apply(style_row, axis=1)
            .bar(subset=["Variación"], align="mid", color=["#fa7a7a", "#8bf58b"], vmin=vmin, vmax=vmax)
        )

    def style_futuros(df):
        if df.empty:
            return df

        safe_int = lambda x: "" if pd.isna(x) else f"{int(x)}"
        fmt = {
            "Close Price": "{:,.2f}",
            "Last Price": "{:,.2f}",
            "Variación": "{:+.2%}",
            "Tasa Directa": "{:+.2%}",
            "TNA": "{:.2%}",
            "TEA": "{:.2%}",
        }
        lim = pd.to_numeric(df["Variación"], errors="coerce").abs().max()
        vmin, vmax = (-lim, lim) if np.isfinite(lim) and lim > 0 else (-1.0, 1.0)

        def _hl_by_canal(row):
            if row.get("Canal") == "Mayorista":
                return ["background-color: #fff2cc"] * len(row)
            else:
                return [""] * len(row)

        sty = (
            df.style.format(fmt)
            .format({"Dias Vto": safe_int})
            .apply(_hl_by_canal, axis=1)
            .bar(subset=["Variación"], align="mid", color=["#fa7a7a", "#8bf58b"], vmin=vmin, vmax=vmax)
        )
        return sty

    # 4) Render y export
    out_dir = Path("curvas")
    out_dir.mkdir(exist_ok=True)

    for nombre, lista in CURVAS.items():
        df_curva = tabla_curva(tabla_base, lista)

        label = CURVAS_LABELS.get(nombre, nombre)
        print(f"\n== Métricas {label} ({plazo}) ==\n")
        if speed_mode:
            display(df_curva.head(25))
        else:
            display(style_curva(df_curva))

        if EXCEL_OUTPUT:
            df_curva.to_excel(out_dir / f"curva_{nombre}.xlsx", index=False)

    # 5) Futuros ROFEX dólar A3500
    A3500_SPOT = get_a3500_spot()
    df_fut = tabla_futuros(session, FUTUROS_DLR, A3500_SPOT)

    print(f"\n== Futuros ROFEX – dólar A3500  (spot: {A3500_SPOT:,.2f}) ==\n")
    if speed_mode:
        display(df_fut.head(30))
    else:
        display(style_futuros(df_fut))

    if EXCEL_OUTPUT:
        df_fut.to_excel(out_dir / "futuros_rofx.xlsx", index=False)

    print("\n✔ Tablas actualizadas" + (" y archivos .xlsx generados" if EXCEL_OUTPUT else ""))


# ──────────────────────────────────────────────────────────────────────
# Auto-refresh (hilo)
# ──────────────────────────────────────────────────────────────────────

_refresh_thread = None
_stop_flag = False


def start_auto_refresh(interval: int = 90, plazo: str = "24hs", speed_mode: bool = SPEED_MODE_DEFAULT):
    """Ejecuta main(plazo) cada `interval` segundos en un hilo daemon."""
    global _refresh_thread, _stop_flag

    if _refresh_thread and _refresh_thread.is_alive():
        print("⚠️  Ya hay un auto-refresh corriendo. Deténlo primero.")
        return

    _stop_flag = False

    def _worker():
        global _stop_flag, _refresh_thread
        try:
            while not _stop_flag:
                clear_output(wait=True)
                print("⏰", pd.Timestamp.now().strftime("%H:%M:%S"), f"— refresh ({plazo}, speed={speed_mode})")
                try:
                    main(plazo, speed_mode=speed_mode)
                except Exception as err:
                    print("⚠️", err)
                for _ in range(interval):
                    if _stop_flag:
                        break
                    time.sleep(1)
        finally:
            _stop_flag = False
            _refresh_thread = None
            print("🛑 Auto-refresh detenido (cleanup).")

    _refresh_thread = threading.Thread(target=_worker, daemon=True)
    _refresh_thread.start()
    print(f"▶️  Auto-refresh cada {interval}s iniciado (speed_mode={speed_mode}).")


def stop_auto_refresh():
    """Detiene el hilo de auto-refresh si existe."""
    global _stop_flag
    if _refresh_thread and _refresh_thread.is_alive():
        _stop_flag = True
    else:
        print("No hay auto-refresh activo.")


# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
