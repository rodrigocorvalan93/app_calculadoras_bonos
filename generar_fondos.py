# -*- coding: utf-8 -*-
# generar_fondos.py
#
# Lee RF_Detalle_Carteras.xlsm y genera:
#   1. Slides de fondos embebibles en el HTML del comité
#   2. Una presentación PPTX separada
#
# USO:
#   from generar_fondos import generar_fondos_html, generar_fondos_pptx
#
#   html_slides = generar_fondos_html(
#       rf_detalle_path = r"C:\...\RF_Detalle_Carteras.xlsm"
#   )
#
#   generar_fondos_pptx(
#       rf_detalle_path = r"C:\...\RF_Detalle_Carteras.xlsm",
#       output_path     = r"C:\...\comite_fondos.pptx",
#       template_path   = r"C:\...\Presentación_Comité_Claude.pptx",  # opcional
#   )
# =============================================================================

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# =============================================================================
# CONFIGURACIÓN DE FONDOS
# =============================================================================

# Cada fondo define:
#   sheet_rf:  sheet en RF_Detalle_Carteras.xlsm
#   col_metr:  columna (0-indexed) donde están los valores de métricas (TIR, Duration, Patrimonio)
#   col_pct:   columna (0-indexed) del % de participación de cada instrumento
#   col_monto: columna (0-indexed) del monto nominal
#   nombre:    nombre para mostrar
#   tipo_vcp:  título del gráfico de variaciones VCP
#   tiene_tir: True si muestra TIR en KPIs (Multimercado no la muestra en la slide)

FONDOS = [
    {
        "id":         "performance",
        "nombre":     "Delta Performance",
        "sheet_rf":   "Cash Management",
        "col_metr":   13,   # PERFORMANCE
        "col_pct":    14,
        "col_monto":  None,
        "tiene_tir":  True,
        "tipo_vcp":   "Renta Fija T+0",
        "peers_label":"Performance",
    },
    {
        "id":         "ahorro_plus",
        "nombre":     "Delta Ahorro Plus",
        "sheet_rf":   "Cash Management",
        "col_metr":   10,   # AHORRO PLUS
        "col_pct":    11,
        "col_monto":  None,
        "tiene_tir":  True,
        "tipo_vcp":   'T+1 "Agresivo"',
        "peers_label":"Ahorro Plus",
    },
    {
        "id":         "retorno_real",
        "nombre":     "Delta Retorno Real",
        "sheet_rf":   "CER",
        "col_metr":   7,
        "col_pct":    8,
        "col_monto":  None,
        "tiene_tir":  True,
        "tipo_vcp":   "CER (Inflación)",
        "peers_label":"Delta Retorno Real",
    },
    {
        "id":         "multimercado",
        "nombre":     "Delta Multimercado I",
        "sheet_rf":   "Largo Plazo",
        "col_metr":   16,
        "col_pct":    17,
        "col_monto":  None,
        "tiene_tir":  False,
        "tipo_vcp":   "Total Return (Renta Mixta)",
        "peers_label":"Multimercado I",
    },
]

# Mapeo subcategoría RF_Detalle → tipo de ajuste para gráfico
AJUSTE_MAP = {
    "ARS Fija":               "Tasa Fija",
    "ARS BADLAR":             "Tasa Fija",
    "ARS TAMAR":              "TAMAR",
    "CER Fija":               "CER/UVA",
    "UVA Fija":               "CER/UVA",
    "Dual (Fija/TAMAR) Fija": "Duales",
    "USD Fija":               "Hard-Dollar",
    "USD en Dólares":         "Hard-Dollar",
    "USB en Dólares":         "Hard-Dollar",
    "USD-Linked Fija":        "Dólar-Linked",
    "Acciones":               "Acciones",
    "RV":                     "Acciones",
    "Caja":                   "Caja",
    "Money Market":           "Caja",
}

# Categorías nivel 1 que van directo a Caja
CAJA_L1 = {"Caja y Equivalentes", "Caja", "Money Market", "Cuenta Corriente"}

# Colores por tipo de ajuste
AJUSTE_COLORS = {
    "Tasa Fija":    "#1e6fba",
    "CER/UVA":      "#4ea8e8",
    "TAMAR":        "#0f2557",
    "Duales":       "#6b93c4",
    "Hard-Dollar":  "#b85a1a",
    "Dólar-Linked": "#e8a020",
    "Acciones":     "#5a9e6f",
    "Caja":         "#8896a5",
}

AJUSTE_ORDER = ["Tasa Fija", "CER/UVA", "TAMAR", "Duales",
                "Hard-Dollar", "Dólar-Linked", "Acciones", "Caja"]

# =============================================================================
# LECTURA DE RF_DETALLE
# =============================================================================

def _read_sheet(path: str, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=None,
                         engine="openpyxl")


def _get_metrics(df: pd.DataFrame, col_metr: int) -> dict:
    """Extrae métricas clave del encabezado del sheet."""
    def _v(row):
        v = df.iloc[row, col_metr]
        return float(v) if not pd.isna(v) else None

    return {
        "duration":   _v(0),   # fila 0: Vida Prom
        "tir":        _v(1),   # fila 1: TIR bruta
        "fee":        _v(2),   # fila 2: Fee
        "tir_neta":   _v(3),   # fila 3: TIR neta
        "patrimonio": _v(5),   # fila 5: Patrimonio
    }


def _get_composition(df: pd.DataFrame, col_pct: int) -> dict:
    """
    Recorre el árbol de tenencias (nivel 1/2/4) y acumula % por tipo de ajuste.
    Retorna dict {tipo: pct_decimal}.
    """
    result = {}
    current_l2 = None

    for i in range(27, min(len(df), 300)):
        nivel = df.iloc[i, 0]
        cat   = str(df.iloc[i, 2]) if not pd.isna(df.iloc[i, 2]) else ""
        pct   = df.iloc[i, col_pct]

        if pd.isna(nivel):
            continue
        nivel = float(nivel)

        if nivel == 1.0:
            current_l2 = None
            # ¿Es una categoría de Caja directo?
            if cat in CAJA_L1 and not pd.isna(pct) and float(pct) > 1e-6:
                result["Caja"] = result.get("Caja", 0) + float(pct)

        elif nivel == 2.0:
            current_l2 = cat
            tipo = AJUSTE_MAP.get(cat)
            if tipo and not pd.isna(pct) and float(pct) > 1e-6:
                result[tipo] = result.get(tipo, 0) + float(pct)

        # nivel 4 — instrumento individual: no sumamos (ya está en nivel 2)

    # Limpiar valores muy pequeños
    result = {k: v for k, v in result.items() if v > 0.001}
    return result


def _get_top5(df: pd.DataFrame, col_pct: int) -> list:
    """
    Extrae los top 5 instrumentos por % de participación.
    Retorna lista de {ticker, pct, descripcion}.
    Excluye versiones CI (contado inmediato) y duplicados.
    """
    instrumentos = []
    seen = set()

    for i in range(27, min(len(df), 300)):
        nivel = df.iloc[i, 0]
        if pd.isna(nivel) or float(nivel) != 4.0:
            continue
        ticker = str(df.iloc[i, 1]) if not pd.isna(df.iloc[i, 1]) else ""
        pct    = df.iloc[i, col_pct]

        if not ticker or pd.isna(pct) or float(pct) < 0.001:
            continue

        # Limpiar sufijo CI para deduplicar
        ticker_base = ticker.replace(" CI", "").strip()
        if ticker_base in seen:
            continue
        seen.add(ticker_base)

        # Fecha de vencimiento desde col 3 (Av Life en años → approx date)
        desc = str(df.iloc[i, 2]) if not pd.isna(df.iloc[i, 2]) else ""

        # Intentar extraer fecha del nombre del bono (ej "Vto. 30 11 2026")
        fecha_vto = None
        m = re.search(r"[Vv]to[.\s]+(\d{1,2})[.\s/]+(\d{1,2})[.\s/]+(\d{4})", desc)
        if m:
            try:
                fecha_vto = f"{int(m.group(1)):02d}-{_MESES_ABREV[int(m.group(2))]}-{m.group(3)}"
            except Exception:
                pass

        instrumentos.append({
            "ticker":    ticker_base,
            "pct":       round(float(pct), 6),
            "fecha_vto": fecha_vto or "",
        })

    # Ordenar por % desc y tomar top 5
    instrumentos.sort(key=lambda x: -x["pct"])
    return instrumentos[:5]


_MESES_ABREV = {
    1:"ene.", 2:"feb.", 3:"mar.", 4:"abr.", 5:"may.", 6:"jun.",
    7:"jul.", 8:"ago.", 9:"sep.", 10:"oct.", 11:"nov.", 12:"dic."
}


def _get_fecha_datos(df: pd.DataFrame) -> str:
    """Extrae la fecha de datos del sheet (fila 25, col 2)."""
    try:
        v = df.iloc[25, 2]
        if pd.isna(v):
            return date.today().strftime("%d-%b-%Y")
        if hasattr(v, "strftime"):
            return v.strftime("%d-%b-%Y")
        return str(v)[:10]
    except Exception:
        return date.today().strftime("%d-%b-%Y")


def _load_fondo(path: str, fondo: dict) -> dict:
    """Carga todos los datos de un fondo desde RF_Detalle."""
    df = _read_sheet(path, fondo["sheet_rf"])
    metr = _get_metrics(df, fondo["col_metr"])
    comp = _get_composition(df, fondo["col_pct"])
    top5 = _get_top5(df, fondo["col_pct"])
    fecha = _get_fecha_datos(df)

    return {
        **fondo,
        "metrics": metr,
        "composition": comp,
        "top5": top5,
        "fecha_datos": fecha,
    }


# =============================================================================
# FORMATEO
# =============================================================================

def _fmt_pn(v: float) -> str:
    if v is None: return "—"
    b = v / 1e9
    if b >= 1:
        return f"${b:,.2f}B".replace(",", "X").replace(".", ",").replace("X", ".")
    m = v / 1e6
    return f"${m:,.0f}M".replace(",", "X").replace(".", ",").replace("X", ".")

def _fmt_tir(v: float, is_cer: bool = False) -> str:
    if v is None: return "—"
    if is_cer:
        real = v - 0.20  # approx: TIR real ≈ TIR nominal - inflación esperada
        # Usar tir_neta directamente si disponible
        return f"CER+{real*100:.1f}%"
    return f"{v*100:.1f}%"

def _fmt_dur(v: float) -> str:
    if v is None: return "—"
    if v < 0.15:
        return f"{round(v * 365)} días"
    return f"{v:.2f} años"

def _fmt_pct(v: float) -> str:
    return f"{round(v * 100)}%"


# =============================================================================
# GENERADOR HTML — slides de fondos
# =============================================================================

_FONDO_CSS = """
/* ── Slides de fondos Delta ── */
/* fd-slide hereda display/height/overflow de .slide-chapter */
/* Solo necesitamos el inner padding específico */
.fd-slide-inner {
  flex: 1;
  overflow-y: auto;
  padding: 28px 40px 20px;
}

/* Layout principal */
.fd-main {
  display: grid;
  grid-template-columns: 180px 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 16px;
  height: calc(100% - 20px);
}

/* Panel izquierdo KPIs */
.fd-kpi {
  grid-row: 1 / 3;
  background: #5f7080;
  border-radius: 6px;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 20px;
  color: white;
}
.fd-kpi-item {}
.fd-kpi-label {
  font-family: var(--font-title,'Barlow',Arial);
  font-size: 11px;
  font-weight: 600;
  color: rgba(255,255,255,0.75);
  text-transform: uppercase;
  letter-spacing: .6px;
  margin-bottom: 4px;
}
.fd-kpi-value {
  font-family: var(--font-title,'Barlow',Arial);
  font-size: 18px;
  font-weight: 700;
  color: white;
  line-height: 1.1;
}
.fd-kpi-date {
  font-family: var(--font-body,'Calibri',Arial);
  font-size: 10px;
  color: rgba(255,255,255,0.55);
  margin-top: 4px;
}

/* Cards de gráficos */
.fd-card {
  background: white;
  border: 1px solid #d8e2ed;
  border-radius: 7px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.fd-card-header {
  background: #0f2557;
  color: white;
  font-family: var(--font-title,'Barlow',Arial);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .6px;
  padding: 6px 12px;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  white-space: nowrap;
  flex-shrink: 0;
  width: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fd-card-body {
  flex: 1;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.fd-card-inner {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100%;
}

/* Top 5 tenencias */
.fd-top5-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-body,'Calibri',Arial);
}
.fd-top5-table tr {
  border-bottom: 1px solid #eaeef2;
}
.fd-top5-table td {
  padding: 4px 6px;
  font-size: 11.5px;
}
.fd-top5-ticker {
  font-weight: 700;
  color: #0f2557;
  min-width: 70px;
}
.fd-top5-pct {
  font-weight: 700;
  background: #5f7080;
  color: white;
  border-radius: 3px;
  padding: 2px 8px;
  text-align: center;
  min-width: 42px;
}
.fd-top5-fecha {
  color: #7a90a4;
  font-size: 10.5px;
}

/* Gráfico VCP — editable */
.fd-vcp-wrap {
  width: 100%;
}
.fd-vcp-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  border-bottom: 1px solid #d8e2ed;
  padding-bottom: 6px;
}
.fd-vcp-tab {
  font-size: 10px;
  font-family: var(--font-title,'Barlow',Arial);
  padding: 3px 10px;
  border: 1px solid #d8e2ed;
  border-radius: 4px;
  cursor: pointer;
  background: #f0f4f8;
  color: #5f7080;
  transition: background .15s;
}
.fd-vcp-tab.active {
  background: #0f2557;
  color: white;
  border-color: #0f2557;
}
.fd-vcp-inputs {
  display: none;
  grid-template-columns: auto 1fr 1fr;
  gap: 4px 8px;
  align-items: center;
  font-size: 10.5px;
  font-family: var(--font-body,'Calibri',Arial);
}
.fd-vcp-inputs.visible { display: grid; }
.fd-vcp-inputs label { color: #5f7080; white-space: nowrap; }
.fd-vcp-inputs input {
  width: 60px;
  border: 1px solid #d8e2ed;
  border-radius: 3px;
  padding: 2px 6px;
  font-size: 10.5px;
  text-align: center;
  font-family: var(--font-body,'Calibri',Arial);
}
.fd-vcp-hdr {
  font-size: 9px;
  font-weight: 700;
  color: #7a90a4;
  text-transform: uppercase;
  letter-spacing: .5px;
}
"""


def _pie_chart_js(canvas_id: str, labels: list, values: list, colors: list) -> str:
    """Genera JS para un donut chart con canvas 2D nativo."""
    data_js = json.dumps([round(v * 100, 2) for v in values])
    labels_js = json.dumps(labels)
    colors_js = json.dumps(colors)

    return f"""
<script>
(function(){{
  function drawPie_{canvas_id}(){{
    var cv = document.getElementById('{canvas_id}');
    if (!cv) return;
    var W = cv.parentElement.clientWidth;
    var H = cv.parentElement.clientHeight;
    if (!W || W < 10) {{ setTimeout(drawPie_{canvas_id}, 80); return; }}
    H = H || 180;
    var dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    var ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);

    var data   = {data_js};
    var labels = {labels_js};
    var colors = {colors_js};
    var total  = data.reduce(function(a,b){{return a+b;}}, 0);
    if (total <= 0) return;

    var cx = W * 0.42, cy = H / 2;
    var R  = Math.min(cx, cy) * 0.82;
    var ri = R * 0.52;  // donut hole

    var angle = -Math.PI / 2;
    for (var i = 0; i < data.length; i++) {{
      var slice = (data[i] / total) * 2 * Math.PI;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, R, angle, angle + slice);
      ctx.closePath();
      ctx.fillStyle = colors[i];
      ctx.fill();
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label si slice > 4%
      if (data[i] / total > 0.04) {{
        var mid = angle + slice / 2;
        var lr = R * 0.73;
        var tx = cx + Math.cos(mid) * lr;
        var ty = cy + Math.sin(mid) * lr;
        ctx.font = 'bold 9px Barlow,Calibri,Arial';
        ctx.fillStyle = data[i]/total > 0.15 ? 'white' : '#333';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(data[i].toFixed(1) + '%', tx, ty);
      }}
      angle += slice;
    }}

    // Hoyo del donut
    ctx.beginPath();
    ctx.arc(cx, cy, ri, 0, 2 * Math.PI);
    ctx.fillStyle = 'white';
    ctx.fill();

    // Leyenda
    var lx = cx + R + 10, ly = H / 2 - (labels.length * 13) / 2;
    ctx.font = '9px Barlow,Calibri,Arial';
    for (var j = 0; j < labels.length; j++) {{
      if (data[j] < 0.1) continue;
      ctx.fillStyle = colors[j];
      ctx.fillRect(lx, ly + j * 13, 8, 8);
      ctx.fillStyle = '#333';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(labels[j] + ': ' + data[j].toFixed(1) + '%', lx + 11, ly + j * 13);
    }}
  }}
  window.addEventListener('load', drawPie_{canvas_id});
  window.addEventListener('resize', drawPie_{canvas_id});
}})();
</script>
"""


def _bar_chart_js(canvas_id: str, labels: list, values: list, color: str) -> str:
    """Barra horizontal para tipo de ajuste."""
    data_js   = json.dumps([round(v * 100, 2) for v in values])
    labels_js = json.dumps(labels)

    return f"""
<script>
(function(){{
  function drawBar_{canvas_id}(){{
    var cv = document.getElementById('{canvas_id}');
    if (!cv) return;
    var W = cv.parentElement.clientWidth;
    var H = cv.parentElement.clientHeight;
    if (!W || W < 10) {{ setTimeout(drawBar_{canvas_id}, 80); return; }}
    H = H || 160;
    var dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    var ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.fillStyle = 'white'; ctx.fillRect(0, 0, W, H);

    var data   = {data_js};
    var labels = {labels_js};
    var n = labels.length;
    var ML = 78, MR = 48, MT = 6, MB = 6;
    var PW = W - ML - MR, PH = H - MT - MB;
    var rowH = PH / n;
    var maxVal = Math.max.apply(null, data) || 1;

    for (var i = 0; i < n; i++) {{
      var y = MT + i * rowH;
      var bw = (data[i] / 100) * PW;
      // bg
      ctx.fillStyle = '#f0f4f8';
      ctx.fillRect(ML, y + rowH*0.15, PW, rowH * 0.7);
      // bar
      ctx.fillStyle = '{color}';
      ctx.fillRect(ML, y + rowH*0.15, bw, rowH * 0.7);
      // label izq
      ctx.font = '9.5px Barlow,Calibri,Arial';
      ctx.fillStyle = '#333';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(labels[i], ML - 4, y + rowH / 2);
      // valor der
      ctx.textAlign = 'left';
      ctx.fillStyle = data[i] > 5 ? 'white' : '#333';
      if (data[i] > 8) {{
        ctx.fillText(data[i].toFixed(1) + '%', ML + bw - 28, y + rowH / 2);
      }} else {{
        ctx.fillStyle = '#333';
        ctx.fillText(data[i].toFixed(1) + '%', ML + bw + 3, y + rowH / 2);
      }}
    }}
  }}
  window.addEventListener('load', drawBar_{canvas_id});
  window.addEventListener('resize', drawBar_{canvas_id});
}})();
</script>
"""


def _vcp_chart_js(fondo_id: str) -> str:
    """JS para el gráfico de variaciones VCP — lee inputs del formulario."""
    return f"""
<script>
(function(){{
  function drawVcp_{fondo_id}(){{
    var cv = document.getElementById('vcp-cv-{fondo_id}');
    if (!cv) return;
    var W = cv.parentElement.clientWidth;
    if (!W || W < 10) {{ setTimeout(drawVcp_{fondo_id}, 80); return; }}
    var H = 140;
    var dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    var ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.fillStyle = 'white'; ctx.fillRect(0, 0, W, H);

    // Leer valores del formulario
    function v(id){{ var el=document.getElementById(id); return el?parseFloat(el.value)||0:0; }}
    var entities = ['fondo','benchmark','peers','industria'];
    var labels   = [
      document.getElementById('vcp-lbl-{fondo_id}') ?
        document.getElementById('vcp-lbl-{fondo_id}').value || '{fondo_id}' : '{fondo_id}',
      'Benchmark','Peers','Industria'
    ];
    var s1 = entities.map(function(e){{ return v('vcp-{fondo_id}-s1-'+e); }});
    var s30= entities.map(function(e){{ return v('vcp-{fondo_id}-s30-'+e); }});

    var all = s1.concat(s30);
    var maxV = Math.max.apply(null, all.map(Math.abs)) || 0.01;
    var n = 4;
    var ML = 8, MR = 8, MT = 18, MB = 22;
    var PW = W - ML - MR, PH = H - MT - MB;
    var grpW = PW / n;
    var barW = grpW * 0.28;

    // Eje 0
    var zero = MT + PH * maxV / (2 * maxV);
    ctx.strokeStyle = '#d8e2ed'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(ML, zero); ctx.lineTo(ML+PW, zero); ctx.stroke();

    var colors1  = '#1e6fba';
    var colors30 = '#1a7a46';

    for (var i = 0; i < n; i++) {{
      var gx = ML + i * grpW + grpW * 0.1;

      // Barra semana
      var h1 = s1[i] / maxV * PH / 2;
      ctx.fillStyle = colors1;
      if (h1 >= 0) ctx.fillRect(gx, zero - h1, barW, h1);
      else ctx.fillRect(gx, zero, barW, -h1);

      // Barra 30d
      var h30 = s30[i] / maxV * PH / 2;
      ctx.fillStyle = colors30;
      if (h30 >= 0) ctx.fillRect(gx + barW + 2, zero - h30, barW, h30);
      else ctx.fillRect(gx + barW + 2, zero, barW, -h30);

      // Label valor semana
      ctx.font = 'bold 8.5px Barlow,Calibri,Arial';
      ctx.fillStyle = colors1; ctx.textAlign = 'center';
      var vsy = h1 >= 0 ? zero - h1 - 3 : zero + (-h1) + 10;
      ctx.fillText((s1[i]*100).toFixed(1)+'%', gx + barW/2, vsy);

      // Label valor 30d
      ctx.fillStyle = colors30;
      var v30y = h30 >= 0 ? zero - h30 - 3 : zero + (-h30) + 10;
      ctx.fillText((s30[i]*100).toFixed(1)+'%', gx + barW + 2 + barW/2, v30y);

      // Label entidad
      ctx.fillStyle = '#333'; ctx.font = '8.5px Barlow,Calibri,Arial';
      ctx.fillText(labels[i], gx + barW + 2, H - 6);
    }}

    // Leyenda
    ctx.fillStyle = colors1;  ctx.fillRect(ML, 5, 8, 7);
    ctx.fillStyle = '#333'; ctx.font = '8px Barlow,Calibri,Arial'; ctx.textAlign='left';
    ctx.fillText('Últ. semana', ML+11, 12);
    ctx.fillStyle = colors30; ctx.fillRect(ML+80, 5, 8, 7);
    ctx.fillText('Últ. 30d', ML+92, 12);
  }}
  window.addEventListener('load', drawVcp_{fondo_id});
  // Redibujar cuando cambian inputs
  document.addEventListener('input', function(e){{
    if (e.target && e.target.id && e.target.id.indexOf('vcp-{fondo_id}') === 0)
      drawVcp_{fondo_id}();
  }});
  window.addEventListener('resize', drawVcp_{fondo_id});
  window['drawVcp_{fondo_id}'] = drawVcp_{fondo_id};
}})();
</script>
"""


def _build_fondo_slide(fondo_data: dict, slide_num: int, total_slides: int) -> str:
    """Genera el HTML completo de la slide de un fondo."""
    fd   = fondo_data
    metr = fd["metrics"]
    comp = fd["composition"]
    top5 = fd["top5"]
    fid  = fd["id"]

    # KPIs
    pn_str  = _fmt_pn(metr.get("patrimonio"))
    dur_str = _fmt_dur(metr.get("duration"))
    is_cer  = (fd["sheet_rf"] == "CER")
    if is_cer:
        tir_neta = metr.get("tir_neta")
        tir_str = f"CER+{tir_neta*100:.1f}%" if tir_neta is not None else "—"
    else:
        tir_neta = metr.get("tir_neta") or metr.get("tir")
        tir_str = f"{tir_neta*100:.1f}%" if tir_neta is not None else "—"

    fecha_str = fd.get("fecha_datos", "—")

    # Datos de composición (torta)
    pie_labels = [k for k in AJUSTE_ORDER if comp.get(k, 0) > 0.001]
    pie_values = [comp.get(k, 0) for k in pie_labels]
    pie_colors = [AJUSTE_COLORS.get(k, "#888") for k in pie_labels]

    pie_js  = _pie_chart_js(f"pie-{fid}", pie_labels, pie_values, pie_colors)
    bar_js  = _bar_chart_js(f"bar-{fid}", pie_labels, pie_values, "#1e6fba")
    vcp_js  = _vcp_chart_js(fid)

    # Top 5
    top5_rows = ""
    for t in top5:
        pct_display = f"{round(t['pct'] * 100)}%"
        fecha_display = t.get("fecha_vto", "") or ""
        top5_rows += f"""
<tr>
  <td class="fd-top5-ticker">{t['ticker']}</td>
  <td><span class="fd-top5-pct">{pct_display}</span></td>
  <td class="fd-top5-fecha">{fecha_display}</td>
</tr>"""

    # Formulario VCP
    entities = [("fondo", fd["peers_label"]), ("benchmark", "Benchmark"),
                ("peers", "Peers"), ("industria", "Industria")]
    vcp_rows = f"""
<div class="fd-vcp-inputs visible" id="vcp-form-{fid}">
  <span class="fd-vcp-hdr"></span>
  <span class="fd-vcp-hdr">Últ. semana</span>
  <span class="fd-vcp-hdr">Últ. 30d</span>
  <input type="hidden" id="vcp-lbl-{fid}" value="{fd['peers_label']}">
"""
    for eid, elabel in entities:
        vcp_rows += f"""
  <label>{elabel}</label>
  <input type="number" step="0.01" id="vcp-{fid}-s1-{eid}"
         placeholder="0.00" style="width:55px">
  <input type="number" step="0.01" id="vcp-{fid}-s30-{eid}"
         placeholder="0.00" style="width:55px">
"""
    vcp_rows += "</div>"

    # Progreso
    pct_prog = round((slide_num / total_slides) * 100, 1)

    # Navegación — fondos van entre slide-6 y slide-7
    # Usamos goToId() que navega por ID de div en lugar de índice numérico
    fondo_ids = [f["id"] for f in FONDOS]
    prev_id = f"fd-slide-{fondo_ids[slide_num - 2]}" if slide_num > 1 else "slide-6"
    next_id = f"fd-slide-{fondo_ids[slide_num]}"     if slide_num < total_slides else "slide-7"

    prev_btn = f'<button class="slide-nav-btn" onclick="goToId(\'{prev_id}\')">← Anterior</button>'
    next_btn = f'<button class="slide-nav-btn" onclick="goToId(\'{next_id}\')">Siguiente →</button>'

    return f"""
<div class="slide-chapter fd-slide" id="fd-slide-{fid}">
  <div class="progress-bar">
    <div class="progress-fill" style="width:{pct_prog}%"></div>
  </div>
  <div class="slide-chapter-inner">

    <div style="margin-bottom:12px">
      <h2 style="font-family:var(--font-title,'Barlow',Arial);font-size:26px;font-weight:700;
                 color:#0f2557;line-height:1">{fd['nombre']}</h2>
      <div style="font-family:var(--font-body,'Calibri',Arial);font-size:13px;color:#5f7080;
                  margin-top:2px">Performance y posicionamiento</div>
    </div>

    <div class="fd-main">

      <!-- KPIs izquierda -->
      <div class="fd-kpi">
        <div class="fd-kpi-item">
          <div class="fd-kpi-label">Patrimonio</div>
          <div class="fd-kpi-value" style="font-size:16px">{pn_str}</div>
        </div>
        {f'<div class="fd-kpi-item"><div class="fd-kpi-label">TIR*</div><div class="fd-kpi-value">{tir_str}</div></div>' if fd.get("tiene_tir") else ""}
        <div class="fd-kpi-item">
          <div class="fd-kpi-label">Duration*</div>
          <div class="fd-kpi-value">{dur_str}</div>
        </div>
        <div class="fd-kpi-item">
          <div class="fd-kpi-label">Datos al</div>
          <div class="fd-kpi-date">{fecha_str}</div>
        </div>
      </div>

      <!-- Composición General (torta) -->
      <div class="fd-card">
        <div class="fd-card-header">Composición General</div>
        <div class="fd-card-body">
          <canvas id="pie-{fid}" style="width:100%;height:100%"></canvas>
        </div>
      </div>

      <!-- Tipo de Ajuste (barras) -->
      <div class="fd-card">
        <div class="fd-card-header">Tipo de Ajuste</div>
        <div class="fd-card-body">
          <canvas id="bar-{fid}" style="width:100%;height:100%"></canvas>
        </div>
      </div>

      <!-- Principales Tenencias (top 5) -->
      <div class="fd-card">
        <div class="fd-card-header">Principales Tenencias</div>
        <div class="fd-card-body" style="padding:6px 10px;align-items:flex-start">
          <table class="fd-top5-table">
            <tbody>{top5_rows}</tbody>
          </table>
        </div>
      </div>

      <!-- Variaciones VCP (editable) -->
      <div class="fd-card">
        <div class="fd-card-header">Variaciones VCP</div>
        <div class="fd-card-body" style="flex-direction:column;align-items:stretch;padding:8px 10px">
          <div style="font-family:var(--font-title,'Barlow',Arial);font-size:9.5px;font-weight:700;
                      color:#0f2557;margin-bottom:6px">{fd['tipo_vcp']}</div>
          <canvas id="vcp-cv-{fid}" style="width:100%;height:140px;margin-bottom:8px"></canvas>
          <div style="border-top:1px solid #d8e2ed;padding-top:6px">
            <div style="font-size:9px;color:#7a90a4;font-weight:600;font-family:var(--font-title,'Barlow',Arial);
                        margin-bottom:4px">✏ Completar datos (% como decimal, ej: 0.9 = 0.9%)</div>
            {vcp_rows}
          </div>
        </div>
      </div>

    </div>
  </div>

  <div class="slide-footer">
    <div class="slide-footer-left">Delta Asset Management &nbsp;·&nbsp; {fecha_str} &nbsp;·&nbsp; Uso interno</div>
    <div class="slide-nav-btns">
      {prev_btn}
      {next_btn}
    </div>
    <div class="slide-footer-right">{slide_num} / {total_slides}</div>
  </div>
</div>

{pie_js}
{bar_js}
{vcp_js}
"""


# =============================================================================
# API PÚBLICA — HTML
# =============================================================================

def generar_fondos_nav_items(fondos: list = None) -> str:
    """
    Genera los <div class="nav-item"> para el sidebar del reporte HTML.
    Se insertan después del nav-item 07 (Snapshot).
    Cada item usa goToId() para navegar a los fd-slides.
    """
    fondos = fondos or FONDOS
    n = len(fondos)
    items = []
    for i, fd in enumerate(fondos, 1):
        num = f"{7 + i:02d}"
        items.append(f"""    <div class="nav-item fd-nav-item" onclick="goToId('fd-slide-{fd['id']}')" id="fd-nav-{fd['id']}">
      <span class="nav-num">{num}</span>
      <span class="nav-label">{fd['nombre']}<br>
        <span style="font-size:10px;opacity:.6">Composición · Top 5</span>
      </span>
    </div>""")
    return "\n".join(items)


def generar_fondos_html(
    rf_detalle_path: str,
    fondos: list = None,
) -> str:
    """
    Genera el HTML de las slides de fondos para embeber en el reporte.
    Retorna el HTML completo (CSS + slides + JS).
    """
    fondos = fondos or FONDOS
    slides_html = ""
    n = len(fondos)

    for i, fondo_cfg in enumerate(fondos, 1):
        try:
            fd = _load_fondo(rf_detalle_path, fondo_cfg)
            slides_html += _build_fondo_slide(fd, i, n)
        except Exception as e:
            print(f"[generar_fondos] Error en {fondo_cfg['nombre']}: {e}")
            continue

    # Script de navegación goToId() — compatibiliza con goTo() del reporte
    goto_js = """
<script>
function goToId(targetId) {
  var allSlides = document.querySelectorAll('.slide-chapter');
  allSlides.forEach(function(s) { s.classList.remove('active'); });
  var target = document.getElementById(targetId);
  if (target) {
    target.classList.add('active');
    var m = targetId.match(/^slide-([0-9]+)$/);
    if (m && typeof goTo === 'function') { goTo(parseInt(m[1])); }
    // Forzar resize para que los canvas nativos se redimensionen
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 60);
  }
  document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
  var navId = targetId.replace('fd-slide-', 'fd-nav-').replace(/^slide-/, 'nav-');
  var navEl = document.getElementById(navId);
  if (navEl) navEl.classList.add('active');
}
(function() {
  var _origGoTo = window.goTo;
  if (typeof _origGoTo === 'function') {
    window.goTo = function(idx) {
      document.querySelectorAll('.fd-slide').forEach(function(s) { s.classList.remove('active'); });
      _origGoTo(idx);
      setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 60);
    };
  }
})();
</script>
"""
    return f"<style>{_FONDO_CSS}</style>\n{slides_html}\n{goto_js}"


# =============================================================================
# API PÚBLICA — PPTX
# =============================================================================

def generar_fondos_pptx(
    rf_detalle_path: str,
    output_path: str,
    template_path: str = None,
    fondos: list = None,
) -> str:
    """
    Genera una presentación PPTX con las slides de fondos.
    Si se provee template_path, la usa como base (mantiene el diseño).
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        import io
    except ImportError:
        print("[generar_fondos] python-pptx no instalado. Instalá con: pip install python-pptx")
        return None

    fondos = fondos or FONDOS

    if template_path and Path(template_path).exists():
        prs = Presentation(template_path)
        # Eliminar slides existentes para reemplazar con datos frescos
        NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        xml_slides = prs.slides._sldIdLst
        for sld_id in list(xml_slides):
            r_id = sld_id.get(f'{{{NS}}}id')
            if r_id:
                try:
                    prs.part.drop_rel(r_id)
                except Exception:
                    pass
            xml_slides.remove(sld_id)
    else:
        prs = Presentation()
        prs.slide_width  = Inches(13.33)
        prs.slide_height = Inches(7.5)

    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    # Colores Delta
    NAVY   = RGBColor(0x0f, 0x25, 0x57)
    GRAY   = RGBColor(0x5f, 0x70, 0x80)
    WHITE  = RGBColor(0xff, 0xff, 0xff)
    BLUE   = RGBColor(0x1e, 0x6f, 0xba)

    # Usar layout en blanco (último disponible) o el primero
    n_layouts = len(prs.slide_layouts)
    slide_layout = prs.slide_layouts[min(6, n_layouts - 1)]

    for fondo_cfg in fondos:
        try:
            fd = _load_fondo(rf_detalle_path, fondo_cfg)
        except Exception as e:
            print(f"[generar_fondos] PPTX error {fondo_cfg['nombre']}: {e}")
            continue

        slide = prs.slides.add_slide(slide_layout)
        metr  = fd["metrics"]
        comp  = fd["composition"]
        top5  = fd["top5"]

        # ── Título ────────────────────────────────────────────────────
        txb = slide.shapes.add_textbox(Inches(0.4), Inches(0.2), Inches(9), Inches(0.55))
        tf  = txb.text_frame
        p   = tf.paragraphs[0]
        run = p.add_run()
        run.text = fd["nombre"]
        run.font.bold   = True
        run.font.size   = Pt(28)
        run.font.color.rgb = NAVY
        run.font.name   = "Barlow"

        txb2 = slide.shapes.add_textbox(Inches(0.4), Inches(0.72), Inches(9), Inches(0.3))
        p2   = txb2.text_frame.paragraphs[0]
        r2   = p2.add_run()
        r2.text = "Performance y posicionamiento"
        r2.font.size = Pt(13)
        r2.font.color.rgb = GRAY
        r2.font.name = "Calibri"

        # ── Panel KPI (rect gris) ─────────────────────────────────────
        kpi_box = slide.shapes.add_shape(
            1,  # MSO_SHAPE_TYPE.RECTANGLE
            Inches(0.25), Inches(1.1), Inches(2.1), Inches(5.8)
        )
        kpi_box.fill.solid()
        kpi_box.fill.fore_color.rgb = GRAY
        kpi_box.line.fill.background()

        def _add_kpi(y_inch, label, value):
            lbl = slide.shapes.add_textbox(Inches(0.35), Inches(y_inch), Inches(1.9), Inches(0.22))
            lp  = lbl.text_frame.paragraphs[0]
            lr  = lp.add_run()
            lr.text = label
            lr.font.size = Pt(8); lr.font.bold = True
            lr.font.color.rgb = RGBColor(0xd0, 0xd8, 0xe0)
            lr.font.name = "Barlow"

            val = slide.shapes.add_textbox(Inches(0.35), Inches(y_inch + 0.22), Inches(1.9), Inches(0.35))
            vp  = val.text_frame.paragraphs[0]
            vr  = vp.add_run()
            vr.text = value
            vr.font.size = Pt(16); vr.font.bold = True
            vr.font.color.rgb = WHITE
            vr.font.name = "Barlow"

        is_cer = fd["sheet_rf"] == "CER"
        tir_neta = metr.get("tir_neta") or metr.get("tir")
        if is_cer:
            tir_str = f"CER+{tir_neta*100:.1f}%" if tir_neta else "—"
        else:
            tir_str = f"{tir_neta*100:.1f}%" if tir_neta else "—"

        _add_kpi(1.3,  "Patrimonio",  _fmt_pn(metr.get("patrimonio")))
        if fd.get("tiene_tir"):
            _add_kpi(2.15, "TIR*", tir_str)
        _add_kpi(3.0,  "Duration*", _fmt_dur(metr.get("duration")))
        _add_kpi(3.85, "Datos al",  fd.get("fecha_datos", "—"))

        # ── Top 5 Tenencias ───────────────────────────────────────────
        t5_x = Inches(2.55); t5_y = Inches(4.1)
        hdr = slide.shapes.add_textbox(t5_x, Inches(3.85), Inches(4.3), Inches(0.24))
        hp  = hdr.text_frame.paragraphs[0]
        hr  = hp.add_run()
        hr.text = "Principales Tenencias"
        hr.font.size = Pt(9); hr.font.bold = True
        hr.font.color.rgb = NAVY; hr.font.name = "Barlow"

        for j, t in enumerate(top5):
            row_y = t5_y.inches + j * 0.28
            # Ticker
            tb_t = slide.shapes.add_textbox(Inches(2.55), Inches(row_y), Inches(1.2), Inches(0.26))
            pp   = tb_t.text_frame.paragraphs[0]
            rr   = pp.add_run()
            rr.text = t["ticker"]; rr.font.size = Pt(10.5)
            rr.font.bold = True; rr.font.color.rgb = NAVY; rr.font.name = "Calibri"
            # Pct badge
            pct_box = slide.shapes.add_shape(
                1, Inches(3.8), Inches(row_y + 0.02), Inches(0.55), Inches(0.22)
            )
            pct_box.fill.solid(); pct_box.fill.fore_color.rgb = GRAY
            pct_box.line.fill.background()
            pct_txb = slide.shapes.add_textbox(Inches(3.8), Inches(row_y + 0.02), Inches(0.55), Inches(0.22))
            pp2 = pct_txb.text_frame.paragraphs[0]
            pp2.alignment = 2  # center
            rr2 = pp2.add_run()
            rr2.text = _fmt_pct(t["pct"]); rr2.font.size = Pt(9)
            rr2.font.bold = True; rr2.font.color.rgb = WHITE; rr2.font.name = "Calibri"
            # Fecha
            tb_f = slide.shapes.add_textbox(Inches(4.42), Inches(row_y), Inches(1.4), Inches(0.26))
            pf   = tb_f.text_frame.paragraphs[0]
            rf   = pf.add_run()
            rf.text = t.get("fecha_vto", "") or ""
            rf.font.size = Pt(9.5); rf.font.color.rgb = GRAY; rf.font.name = "Calibri"

        # ── Nota VCP ─────────────────────────────────────────────────
        nota = slide.shapes.add_textbox(Inches(6.9), Inches(4.1), Inches(6.0), Inches(0.4))
        np_  = nota.text_frame.paragraphs[0]
        nr   = np_.add_run()
        nr.text = f"⚠ Variaciones VCP: completar en el HTML interactivo"
        nr.font.size = Pt(9); nr.font.color.rgb = RGBColor(0xb8, 0x5a, 0x1a)
        nr.font.name = "Calibri"

    prs.save(output_path)
    print(f"[generar_fondos] PPTX guardado: {output_path}")
    return output_path
