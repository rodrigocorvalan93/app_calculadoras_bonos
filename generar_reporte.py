# -*- coding: utf-8 -*-
# generar_reporte.py
#
# Genera el reporte HTML del comité de inversiones.
# Toma datos directamente de OMSweb_app (load_curve_last_table).
# Los gráficos son canvas 2D nativo — sin librerías externas.
#
# USO:
#   from generar_reporte import generar_reporte
#   generar_reporte(
#       username      = "delta_api",
#       password      = "D3lt41210*-*",
#       template_path = r"C:\Users\juan.paolicchi\...\Comite\reporte_comite_base.html",
#   )
# =============================================================================

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

import OMSweb_app as _app

# =============================================================================
# CONFIG
# =============================================================================

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}


# =============================================================================
# HELPERS
# =============================================================================

def _fmt_fecha(d: date) -> str:
    return f"{d.day} de {MESES_ES[d.month]} de {d.year}"


def _pct_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        is_pct = s.endswith('%')
        try:
            v = float(s.rstrip('%'))
            return v / 100.0 if is_pct else v
        except ValueError:
            return None
    try:
        v = float(val)
        return None if not np.isfinite(v) else v
    except Exception:
        return None


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if 'Codigo' in df.columns and 'Código' not in df.columns:
        df = df.rename(columns={'Codigo': 'Código'})
    if 'Código' in df.columns:
        df = df[~df['Código'].astype(str).str.endswith(('j', 'v'))]
    return df.reset_index(drop=True)


def _get_tamar_rates() -> Tuple[Optional[float], Optional[float]]:
    try:
        import rentafija
        df_t = rentafija.inputs.get("tamar")
        if df_t is not None and not df_t.empty and "TAMAR" in df_t.columns:
            tna = float(df_t["TAMAR"].dropna().iloc[-1]) / 100.0
            tea = (1 + tna / 365) ** 365 - 1
            return tna, tea
    except Exception:
        pass
    return None, None


# =============================================================================
# DATOS DE CURVA → LISTAS PARA JS
# =============================================================================

def _curve_points(df: pd.DataFrame, tir_col: str = "TIREA") -> List[list]:
    """[[ticker, duration, tir_pct], ...]"""
    pts = []
    for _, r in _clean_df(df).iterrows():
        tir = _pct_float(r.get(tir_col))
        try:
            dur = float(r.get("Duration"))
        except Exception:
            continue
        if tir is None or not np.isfinite(dur) or not np.isfinite(tir):
            continue
        pts.append([str(r.get("Código", "")), round(dur, 4), round(tir * 100, 4)])
    return sorted(pts, key=lambda p: p[1])


def _bontam_points(df: pd.DataFrame, tamar_tea: float) -> List[list]:
    """[[ticker, duration, spread_pct], ...]"""
    pts = []
    for _, r in _clean_df(df).iterrows():
        tir = _pct_float(r.get("TIREA"))
        try:
            dur = float(r.get("Duration"))
        except Exception:
            continue
        if tir is None or not np.isfinite(dur) or not np.isfinite(tir):
            continue
        pts.append([str(r.get("Código", "")), round(dur, 4),
                    round((tir - tamar_tea) * 100, 4)])
    return sorted(pts, key=lambda p: p[1])


# =============================================================================
# TABLAS
# =============================================================================

def _tbl_boncap(pts):
    return "".join(
        f'<tr><td class="td-ticker">{t}</td><td>{d:.2f}</td>'
        f'<td class="td-val">{y:.2f}%</td></tr>'
        for t, d, y in pts
    )


def _tbl_boncer(pts):
    rows = ""
    for t, d, y in pts:
        cls = "td-pos" if y >= 0 else "td-neg"
        rows += (f'<tr><td class="td-ticker">{t}</td><td>{d:.2f}</td>'
                 f'<td class="td-val {cls}">{y:.2f}%</td></tr>')
    return rows


def _tbl_bontam(pts):
    rows = ""
    for t, d, sp in pts:
        cls  = "td-pos" if sp >= 0 else "td-neg"
        sign = "+" if sp >= 0 else ""
        rows += (f'<tr><td class="td-ticker">{t}</td><td>{d:.2f}</td>'
                 f'<td class="td-val {cls}">{sign}{sp:.2f}%</td></tr>')
    return rows


# =============================================================================
# JAVASCRIPT DE GRÁFICOS (canvas 2D nativo)
# =============================================================================

_CHART_JS = r"""
<script>
(function() {

var FONT = "'Barlow','Calibri','Gill Sans',Arial,sans-serif";

/* ── Ajuste polinómico grado 2 ── */
function poly2(xs, ys) {
  var n=xs.length,sx=0,sx2=0,sx3=0,sx4=0,sy=0,sxy=0,sx2y=0;
  for(var i=0;i<n;i++){var x=xs[i],y=ys[i];sx+=x;sx2+=x*x;sx3+=x*x*x;sx4+=x*x*x*x;sy+=y;sxy+=x*y;sx2y+=x*x*y;}
  var A=[[n,sx,sx2],[sx,sx2,sx3],[sx2,sx3,sx4]],B=[sy,sxy,sx2y];
  for(var c=0;c<3;c++){
    var mx=c;for(var r=c+1;r<3;r++)if(Math.abs(A[r][c])>Math.abs(A[mx][c]))mx=r;
    var t=A[c];A[c]=A[mx];A[mx]=t;var tb=B[c];B[c]=B[mx];B[mx]=tb;
    for(var r2=c+1;r2<3;r2++){var f=A[r2][c]/A[c][c];B[r2]-=f*B[c];for(var j=c;j<3;j++)A[r2][j]-=f*A[c][j];}
  }
  var co=[0,0,0];
  for(var i2=2;i2>=0;i2--){co[i2]=B[i2];for(var j2=i2+1;j2<3;j2++)co[i2]-=A[i2][j2]*co[j2];co[i2]/=A[i2][i2];}
  return co;
}

function niceStep(range, target) {
  var s=range/target, mag=Math.pow(10,Math.floor(Math.log10(s)));
  var opts=[1,2,2.5,5,10];
  for(var i=0;i<opts.length;i++) if(opts[i]*mag>=s) return opts[i]*mag;
  return s;
}

/* ── Anti-solapamiento de labels ── */
function resolveOverlaps(labels) {
  /* labels: [{x, y, text, align}]
     Empuja verticalmente labels que se solapan */
  var H_STEP = 11;   // px mínimos entre líneas de texto
  var W_APPROX = 7;  // px por carácter (aprox)
  var changed = true, MAX_ITER = 20, iter = 0;
  while (changed && iter++ < MAX_ITER) {
    changed = false;
    for (var i = 0; i < labels.length; i++) {
      for (var j = i+1; j < labels.length; j++) {
        var a = labels[i], b = labels[j];
        var aw = a.text.length * W_APPROX;
        var bw = b.text.length * W_APPROX;
        var ax1 = a.align==='left' ? a.x : a.x - aw;
        var ax2 = ax1 + aw;
        var bx1 = b.align==='left' ? b.x : b.x - bw;
        var bx2 = bx1 + bw;
        var overlapX = ax1 < bx2 && ax2 > bx1;
        var overlapY = Math.abs(a.y - b.y) < H_STEP;
        if (overlapX && overlapY) {
          /* Empujar el de abajo hacia arriba */
          if (a.y >= b.y) { a.y += H_STEP * 0.6; }
          else             { b.y += H_STEP * 0.6; }
          changed = true;
        }
      }
    }
  }
}

function drawChart(id, data, color, yAxisLabel, zeroLine) {
  var cv = document.getElementById(id);
  if (!cv) return;
  var dpr = window.devicePixelRatio || 1;
  var W = cv.parentElement.clientWidth || 360;
  var H = 260;
  cv.width  = W * dpr;
  cv.height = H * dpr;
  cv.style.width  = W + 'px';
  cv.style.height = H + 'px';
  var ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);

  var ML=54, MR=16, MT=14, MB=36;
  var PW=W-ML-MR, PH=H-MT-MB;

  var xs=data.map(function(d){return d[1];}),
      ys=data.map(function(d){return d[2];});
  var xMin=Math.min.apply(null,xs), xMax=Math.max.apply(null,xs);
  var yMin=Math.min.apply(null,ys), yMax=Math.max.apply(null,ys);
  var xPad=Math.max((xMax-xMin)*0.08,0.06);
  var yPad=Math.max((yMax-yMin)*0.12,1.0);
  var XL=Math.max(0,xMin-xPad), XR=xMax+xPad;
  var yStep=niceStep(yMax-yMin+yPad*2,6);
  var YB=Math.floor((yMin-yPad)/yStep)*yStep;
  var YT=Math.ceil((yMax+yPad)/yStep)*yStep;

  function px(x){return ML+(x-XL)/(XR-XL)*PW;}
  function py(y){return MT+PH-(y-YB)/(YT-YB)*PH;}

  /* Fondo */
  ctx.fillStyle='white'; ctx.fillRect(0,0,W,H);

  /* Grid Y */
  var y=YB;
  while(y<=YT+1e-9){
    var yp=py(y), isZ=Math.abs(y)<1e-9;
    ctx.beginPath(); ctx.moveTo(ML,yp); ctx.lineTo(ML+PW,yp);
    ctx.strokeStyle=(isZ&&zeroLine)?'#9badb8':'#eaeef2';
    ctx.lineWidth=(isZ&&zeroLine)?1.3:0.8; ctx.stroke();
    ctx.font='9.5px '+FONT; ctx.fillStyle='#7a90a4'; ctx.textAlign='right';
    ctx.fillText(y.toFixed(1)+'%', ML-6, yp+3.5);
    y=Math.round((y+yStep)*1e9)/1e9;
  }

  /* Grid X */
  var xStep=niceStep(XR-XL,5), xx=Math.ceil(XL/xStep)*xStep;
  while(xx<=XR+1e-9){
    var xp=px(xx);
    ctx.beginPath(); ctx.moveTo(xp,MT); ctx.lineTo(xp,MT+PH);
    ctx.strokeStyle='#eaeef2'; ctx.lineWidth=0.8; ctx.stroke();
    ctx.font='9.5px '+FONT; ctx.fillStyle='#7a90a4'; ctx.textAlign='center';
    ctx.fillText(xx.toFixed(xx<1?2:1), xp, MT+PH+14);
    xx=Math.round((xx+xStep)*1e9)/1e9;
  }

  /* Borde */
  ctx.strokeStyle='#d8e2ed'; ctx.lineWidth=0.8;
  ctx.strokeRect(ML,MT,PW,PH);

  /* Curva NSS punteada */
  if(data.length>=3){
    var co=poly2(xs,ys);
    ctx.save();
    ctx.beginPath(); ctx.rect(ML,MT,PW,PH); ctx.clip();
    ctx.beginPath();
    var first=true;
    for(var k=0;k<=100;k++){
      var xk=XL+(XR-XL)*k/100, yk=co[0]+co[1]*xk+co[2]*xk*xk;
      if(first){ctx.moveTo(px(xk),py(yk));first=false;}else ctx.lineTo(px(xk),py(yk));
    }
    ctx.strokeStyle=color; ctx.lineWidth=1.8;
    ctx.setLineDash([6,4]); ctx.globalAlpha=0.5; ctx.stroke();
    ctx.restore(); ctx.setLineDash([]); ctx.globalAlpha=1;
  }

  /* Puntos */
  var R=5;
  for(var i=0;i<data.length;i++){
    var d=data[i], xp2=px(d[1]), yp2=py(d[2]);
    ctx.beginPath(); ctx.arc(xp2,yp2+1.5,R+1,0,Math.PI*2);
    ctx.fillStyle='rgba(0,0,0,0.07)'; ctx.fill();
    ctx.beginPath(); ctx.arc(xp2,yp2,R,0,Math.PI*2);
    ctx.fillStyle=color; ctx.fill();
    ctx.strokeStyle='white'; ctx.lineWidth=1.5; ctx.stroke();
  }

  /* Labels — anti-solapamiento */
  var labelObjs = [];
  ctx.font='bold 9px '+FONT;
  for(var i=0;i<data.length;i++){
    var d=data[i], xp3=px(d[1]), yp3=py(d[2]);
    var toRight = xp3 < ML+PW*0.72;
    labelObjs.push({
      x: toRight ? xp3+R+4 : xp3-R-4,
      y: yp3 - 6,       /* arriba del punto por defecto */
      text: d[0],
      align: toRight ? 'left' : 'right',
      ptX: xp3, ptY: yp3
    });
  }
  resolveOverlaps(labelObjs);
  for(var i=0;i<labelObjs.length;i++){
    var lb=labelObjs[i];
    ctx.textAlign=lb.align;
    ctx.strokeStyle='white'; ctx.lineWidth=2.8; ctx.lineJoin='round';
    ctx.strokeText(lb.text, lb.x, lb.y);
    ctx.fillStyle=color; ctx.fillText(lb.text, lb.x, lb.y);
  }

  /* ── Label eje Y — centrado exacto ── */
  ctx.save();
  ctx.translate(12, MT + PH/2);   /* centro vertical del plot */
  ctx.rotate(-Math.PI/2);
  ctx.textAlign='center';
  ctx.textBaseline='middle';
  ctx.font='9.5px '+FONT;
  ctx.fillStyle='#7a90a4';
  ctx.fillText(yAxisLabel, 0, 0);
  ctx.restore();

  /* ── Label eje X ── */
  ctx.textAlign='center';
  ctx.textBaseline='alphabetic';
  ctx.font='9.5px '+FONT;
  ctx.fillStyle='#7a90a4';
  ctx.fillText('Duration (años)', ML+PW/2, H-4);
}

/* Datos inyectados por Python */
var _C1_BONCAP      = %%BONCAP%%;
var _C1_BONCER_FULL = %%BONCER%%;
var _C1_BONTAM      = %%BONTAM%%;

var _BONCER_EXCL = {"PARP":true,"CUAP":true};
var _boncer_show_all = false;

function _boncer_data() {
  if (_boncer_show_all) return _C1_BONCER_FULL;
  return _C1_BONCER_FULL.filter(function(d){return !_BONCER_EXCL[d[0]];});
}

function _c1Draw() {
  drawChart('c1-cv-boncap', _C1_BONCAP,    '#1e6fba', 'TIR TEA (%)',          false);
  drawChart('c1-cv-boncer', _boncer_data(), '#1a7a46', 'Tasa real (%)',         true);
  drawChart('c1-cv-bontam', _C1_BONTAM,    '#b85a1a', 'Spread vs TAMAR (%)',   true);
}

document.addEventListener('DOMContentLoaded', function() {
  var btn = document.getElementById('c1-btn-excl');
  if (btn) {
    btn.addEventListener('click', function() {
      _boncer_show_all = !_boncer_show_all;
      btn.textContent = _boncer_show_all ? '✕  Excluir PARP y CUAP' : '+  Incluir PARP y CUAP';
      btn.style.background  = _boncer_show_all ? '#fff3e8' : '#f0f4f8';
      btn.style.color       = _boncer_show_all ? '#b85a1a' : '#5f7080';
      btn.style.borderColor = _boncer_show_all ? '#b85a1a' : '#d8e2ed';
      _c1Draw();
    });
  }
  var _orig = window.goTo;
  if (typeof _orig === 'function') {
    window.goTo = function(idx) { _orig(idx); if(idx===1) setTimeout(_c1Draw,60); };
  }
});
window.addEventListener('load', function(){ setTimeout(_c1Draw,60); });
window.addEventListener('resize', _c1Draw);

})();
</script>
"""

_CAP1_CSS = """
.c1-charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 16px;
}
.c1-chart-body {
  padding: 4px 8px 6px;
  line-height: 0;
}
.c1-chart-body canvas {
  display: block;
  width: 100%;
}
@media (max-width: 900px) {
  .c1-charts-grid { grid-template-columns: 1fr; }
}
"""



# =============================================================================
# COMBINAR TAMAR + DUALES PARA BONTAM
# =============================================================================

# Bonos a excluir del GRÁFICO BONCER por defecto (distorsionan la curva)
_BONCER_EXCL_DEFAULT = {"PARP", "CUAP"}

def _combine_bontam(df_tamar: pd.DataFrame, df_dual: pd.DataFrame) -> pd.DataFrame:
    """Une df_tamar y df_dual (dualtamar con sufijo v) para el gráfico BONTAM.
    Los dualtamar tienen sufijo v en el código (TTJ26v) — los incluimos
    limpiando el sufijo para mostrar el ticker sin v."""
    frames = []
    # TAMAR: filtro normal (excluye j/v)
    clean_t = _clean_df(df_tamar)
    if not clean_t.empty:
        frames.append(clean_t)
    # Dualtamar: vienen con sufijo v, los incluimos explícitamente
    # limpiando el sufijo del ticker para el gráfico
    if df_dual is not None and not df_dual.empty:
        df_d = df_dual.copy()
        if 'Codigo' in df_d.columns and 'Código' not in df_d.columns:
            df_d = df_d.rename(columns={'Codigo': 'Código'})
        if 'Código' in df_d.columns:
            # Filtrar solo los que terminan en v (dualtamar)
            df_d = df_d[df_d['Código'].astype(str).str.endswith('v')].copy()
            # Limpiar el sufijo v para mostrar el ticker limpio
            df_d['Código'] = df_d['Código'].astype(str).str.rstrip('v')
        if not df_d.empty:
            frames.append(df_d.reset_index(drop=True))
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    if 'Código' in combined.columns:
        combined = combined.drop_duplicates(subset='Código', keep='first')
    return combined.reset_index(drop=True)


# =============================================================================
# CAP 1 HTML
# =============================================================================

def _build_cap1_html(df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna) -> str:

    tamar_tea_str = f"{tamar_tea * 100:.2f}%"
    tamar_tna_str = f"{tamar_tna * 100:.3f}%"

    boncap_pts = _curve_points(df_lecap)
    boncer_pts = _curve_points(df_cer)
    # Combinar TAMAR + Duales para BONTAM
    df_bontam_all = _combine_bontam(df_tamar, df_dual)
    bontam_pts = _bontam_points(df_bontam_all, tamar_tea)

    boncap_json = json.dumps(boncap_pts, ensure_ascii=False)
    boncer_json = json.dumps(boncer_pts, ensure_ascii=False)
    bontam_json = json.dumps(bontam_pts, ensure_ascii=False)

    chart_js = (_CHART_JS
                .replace("%%BONCAP%%", boncap_json)
                .replace("%%BONCER%%", boncer_json)
                .replace("%%BONTAM%%", bontam_json))

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">01</div>
  <div class="slide-section-stripe" style="background:#1a3a5c"></div>
  <div class="slide-section-titles">
    <h2>Curvas de Rendimiento</h2>
    <div class="slide-section-sub">TIR TEA por instrumento y duration · Tasa fija, CER real y spread TAMAR</div>
  </div>
</div>

<div class="metodo-box">
  <strong>Metodología.</strong> BONCAP: TIR TEA por descuento de flujos sobre precio limpio.
  BONCER: tasa real pura (<em>usar_cer_pago=False</em>), sin incorporar path de inflación.
  BONTAM: spread sobre la última TAMAR TEA ({tamar_tea_str} — TNA {tamar_tna_str}).
</div>

<div class="c1-charts-grid">
  <div class="chart-card">
    <div class="chart-card-header">
      <div class="chart-dot" style="background:#1a5fa8"></div>
      <span class="chart-title">BONCAP — TIR TEA</span>
      <span class="chart-sub">{len(boncap_pts)} instrumentos</span>
    </div>
    <div class="c1-chart-body"><canvas id="c1-cv-boncap"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-card-header">
      <div class="chart-dot" style="background:#1a7a46"></div>
      <span class="chart-title">BONCER — Tasa real</span>
      <span class="chart-sub">{len(boncer_pts)} instrumentos</span>
      <button id="c1-btn-excl" style="margin-left:8px;padding:2px 8px;font-size:10px;font-family:inherit;border:1px solid #dde3ec;border-radius:3px;background:#f4f6f9;color:#6b7c93;cursor:pointer;white-space:nowrap;">+&nbsp;&nbsp;Incluir PARP y CUAP</button>
    </div>
    <div class="c1-chart-body"><canvas id="c1-cv-boncer"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-card-header">
      <div class="chart-dot" style="background:#b85a1a"></div>
      <span class="chart-title">BONTAM — Spread vs TAMAR</span>
      <span class="chart-sub">TAMAR TEA {tamar_tea_str}</span>
    </div>
    <div class="c1-chart-body"><canvas id="c1-cv-bontam"></canvas></div>
  </div>
</div>

<div class="tables-row">
  <div class="mini-table-wrap">
    <div class="mini-table-title" style="color:#1a5fa8">BONCAP</div>
    <table class="mini-table">
      <thead><tr><th>Ticker</th><th>Duration</th><th>TIR TEA</th></tr></thead>
      <tbody>{_tbl_boncap(boncap_pts)}</tbody>
    </table>
  </div>
  <div class="mini-table-wrap">
    <div class="mini-table-title" style="color:#1a7a46">BONCER</div>
    <table class="mini-table">
      <thead><tr><th>Ticker</th><th>Duration</th><th>T. Real</th></tr></thead>
      <tbody>{_tbl_boncer(boncer_pts)}</tbody>
    </table>
  </div>
  <div class="mini-table-wrap">
    <div class="mini-table-title" style="color:#b85a1a">BONTAM</div>
    <table class="mini-table">
      <thead><tr><th>Ticker</th><th>Duration</th><th>Spread</th></tr></thead>
      <tbody>{_tbl_bontam(bontam_pts)}</tbody>
    </table>
  </div>
</div>

{chart_js}
""".strip()



# =============================================================================
# CAP 3 — FORWARDS
# =============================================================================

def _forward_matrix(df: pd.DataFrame, tir_col: str = "TIREA") -> tuple:
    """
    Calcula la matriz de tasas forward implícitas.
    fwd(i->j) = [(1+r_j)^d_j / (1+r_i)^d_i]^(1/(d_j-d_i)) - 1
    Devuelve (tickers, matrix_nxn) donde matrix[i][j] = fwd_pct o None si i>=j.
    """
    df2 = _clean_df(df)
    pts = []
    for _, r in df2.iterrows():
        tir = _pct_float(r.get(tir_col))
        try:
            dur = float(r.get("Duration"))
        except Exception:
            continue
        if tir is None or not np.isfinite(dur) or not np.isfinite(tir):
            continue
        pts.append((str(r.get("Codigo", r.get("Código", ""))), dur, tir))
    pts = sorted(pts, key=lambda x: x[1])
    if len(pts) < 2:
        return [], []
    n = len(pts)
    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            ti, ri = pts[i][1], pts[i][2]
            tj, rj = pts[j][1], pts[j][2]
            dt = tj - ti
            if dt < 1e-6:
                continue
            try:
                fwd = ((1 + rj) ** tj / (1 + ri) ** ti) ** (1.0 / dt) - 1.0
                if np.isfinite(fwd):
                    matrix[i][j] = round(fwd * 100, 3)
            except Exception:
                pass
    tickers = [p[0] for p in pts]
    return tickers, matrix


def _fwd_color_class(val: float, vmin: float, vmax: float) -> str:
    if vmax == vmin:
        return "hm-c3"
    ratio = (val - vmin) / (vmax - vmin)
    if ratio >= 0.75: return "hm-c1"
    if ratio >= 0.50: return "hm-c2"
    if ratio >= 0.25: return "hm-c3"
    if ratio >= 0.10: return "hm-c4"
    return "hm-c5"


def _build_fwd_table_html(tickers: list, matrix: list, table_id: str) -> str:
    if not tickers:
        return '<p style="color:#7a90a4;padding:14px;font-size:12px;">Sin datos suficientes.</p>'
    n = len(tickers)
    all_vals = [matrix[i][j] for i in range(n) for j in range(i+1, n) if matrix[i][j] is not None]
    vmin = min(all_vals) if all_vals else 0
    vmax = max(all_vals) if all_vals else 0

    headers = "".join(
        f'<th class="hm-th" data-col="{t}">{t}</th>' for t in tickers
    )
    rows_html = ""
    for i, ti in enumerate(tickers):
        cells = ""
        for j, tj in enumerate(tickers):
            if j <= i:
                cells += f'<td class="hm-cell hm-na" data-col="{tj}"></td>'
            elif matrix[i][j] is not None:
                val = matrix[i][j]
                cls = _fwd_color_class(val, vmin, vmax)
                sign = "+" if val >= 0 else ""
                cells += f'<td class="hm-cell {cls}" data-col="{tj}">{sign}{val:.2f}%</td>'
            else:
                cells += f'<td class="hm-cell hm-na" data-col="{tj}"></td>'
        rows_html += f'<tr><td class="hm-row-lbl" data-row="{ti}">{ti}</td>{cells}</tr>'

    return (
        f'<table class="hm-table" id="hm-{table_id}">'
        f'<thead><tr><th class="hm-row-lbl"></th>{headers}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
    )


def _build_fwd_checkboxes(tickers: list, table_id: str) -> str:
    if not tickers:
        return ""
    boxes = "".join(
        f'<label style="display:inline-flex;align-items:center;gap:4px;'
        f'margin:2px 5px 2px 0;font-size:10px;cursor:pointer;color:#1a2535;">'
        f'<input type="checkbox" checked data-table="{table_id}" data-ticker="{t}" '
        f'style="accent-color:#1e6fba;cursor:pointer;">'
        f'<span style="font-family:var(--font-body,Calibri,Arial)">{t}</span></label>'
        for t in tickers
    )
    return (
        f'<div class="fwd-filter" style="padding:7px 16px 9px;border-top:1px solid #d8e2ed;background:#f7f9fc;">'
        f'<span style="font-size:9px;font-weight:700;color:#5f7080;text-transform:uppercase;'
        f'letter-spacing:.8px;font-family:var(--font-title,Barlow,Arial);margin-right:8px;">Filtrar</span>'
        f'{boxes}'
        f'<button onclick="_fwdAll(\'{table_id}\',true)" style="margin-left:6px;padding:2px 8px;font-size:9px;'
        f'border:1px solid #d8e2ed;border-radius:3px;background:#f0f4f8;color:#5f7080;cursor:pointer;">Todos</button>'
        f'<button onclick="_fwdAll(\'{table_id}\',false)" style="padding:2px 8px;font-size:9px;'
        f'border:1px solid #d8e2ed;border-radius:3px;background:#f0f4f8;color:#5f7080;cursor:pointer;">Ninguno</button>'
        f'</div>'
    )


_FWD_JS = """
<script>
(function(){
  function applyFilter(tid){
    var boxes=document.querySelectorAll('input[data-table="'+tid+'"]');
    var active={};
    boxes.forEach(function(b){if(b.checked)active[b.dataset.ticker]=true;});
    var tbl=document.getElementById('hm-'+tid);
    if(!tbl)return;
    tbl.querySelectorAll('th[data-col]').forEach(function(th){th.style.display=active[th.dataset.col]?'':'none';});
    tbl.querySelectorAll('tbody tr').forEach(function(tr){
      var rl=tr.querySelector('[data-row]');
      if(!rl)return;
      var show=active[rl.dataset.row];
      tr.style.display=show?'':'none';
      if(show)tr.querySelectorAll('[data-col]').forEach(function(td){td.style.display=active[td.dataset.col]?'':'none';});
    });
  }
  window._fwdAll=function(tid,val){
    document.querySelectorAll('input[data-table="'+tid+'"]').forEach(function(b){b.checked=val;});
    applyFilter(tid);
  };
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('input[type=checkbox][data-table]').forEach(function(b){
      b.addEventListener('change',function(){applyFilter(b.dataset.table);});
    });
  });
})();
</script>
"""


def _build_cap3_html(df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna) -> str:
    tamar_tea_str = f"{tamar_tea * 100:.2f}%"
    df_bontam = _combine_bontam(df_tamar, df_dual)

    tk_bc, mx_bc = _forward_matrix(df_lecap)
    tk_bn, mx_bn = _forward_matrix(df_cer)
    # BONTAM: forward sobre spreads vs TAMAR (no sobre TIREA absoluta)
    df_bontam_spread = df_bontam.copy()
    if "TIREA" in df_bontam_spread.columns:
        df_bontam_spread["TIREA"] = df_bontam_spread["TIREA"].apply(
            lambda x: _pct_float(x) - tamar_tea if _pct_float(x) is not None else None
        )
    tk_bt, mx_bt = _forward_matrix(df_bontam_spread)

    tbl_bc = _build_fwd_table_html(tk_bc, mx_bc, "boncap")
    tbl_bn = _build_fwd_table_html(tk_bn, mx_bn, "boncer")
    tbl_bt = _build_fwd_table_html(tk_bt, mx_bt, "bontam")

    chk_bc = _build_fwd_checkboxes(tk_bc, "boncap")
    chk_bn = _build_fwd_checkboxes(tk_bn, "boncer")
    chk_bt = _build_fwd_checkboxes(tk_bt, "bontam")

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">03</div>
  <div class="slide-section-stripe" style="background:#1e6fba"></div>
  <div class="slide-section-titles">
    <h2>Tasas Forward Implícitas</h2>
    <div class="slide-section-sub">Matrices de tasas forward entre vencimientos · BONCAP · BONCER · BONTAM</div>
  </div>
</div>

<div class="metodo-box">
  <strong>Metodología.</strong>
  Cada celda (fila <em>i</em>, columna <em>j &gt; i</em>) representa la tasa forward TEA implícita
  derivada de la condición de no arbitraje:
  <em>fwd(i&#x2192;j) = [(1+r<sub>j</sub>)<sup>d<sub>j</sub></sup> / (1+r<sub>i</sub>)<sup>d<sub>i</sub></sup>]<sup>1/(d<sub>j</sub>&#x2212;d<sub>i</sub>)</sup> &#x2212; 1</em>.
  Fila = bono origen &nbsp;·&nbsp; Columna = bono destino &nbsp;·&nbsp; Triángulo superior.
  Verde&#x2009;=&#x2009;tasa mayor · Rojo&#x2009;=&#x2009;tasa menor.
  BONTAM: spreads vs TAMAR TEA ({tamar_tea_str}).
</div>

<div class="chart-card full-width" style="margin-bottom:14px;">
  <div class="chart-card-header">
    <div class="chart-dot" style="background:#1e6fba"></div>
    <span class="chart-title">Forward BONCAP — TIR TEA implícita entre vencimientos</span>
    <span class="chart-sub">TIR TEA %</span>
  </div>
  <div class="hm-wrap">{tbl_bc}</div>
  {chk_bc}
  <div class="chart-caption">Tasa forward TEA entre cada par de vencimientos BONCAP. Pendiente descendente sugiere expectativa de baja de tasas.</div>
</div>

<div class="chart-card full-width" style="margin-bottom:14px;">
  <div class="chart-card-header">
    <div class="chart-dot" style="background:#1a7a46"></div>
    <span class="chart-title">Forward BONCER — Tasa real implícita entre vencimientos</span>
    <span class="chart-sub">Tasa real %</span>
  </div>
  <div class="hm-wrap">{tbl_bn}</div>
  {chk_bn}
  <div class="chart-caption">Tasa real forward entre cada par de vencimientos BONCER. Captura la prima de tasa real que exige el mercado por cada tramo.</div>
</div>

<div class="chart-card full-width" style="margin-bottom:14px;">
  <div class="chart-card-header">
    <div class="chart-dot" style="background:#b85a1a"></div>
    <span class="chart-title">Forward BONTAM — Spread forward sobre TAMAR</span>
    <span class="chart-sub">Spread TEA %</span>
  </div>
  <div class="hm-wrap">{tbl_bt}</div>
  {chk_bt}
  <div class="chart-caption">Spread forward sobre TAMAR TEA entre cada par de BONTAM. Valores negativos indican expectativa de compresión de spreads.</div>
</div>

{_FWD_JS}
""".strip()


# =============================================================================
# CAP 4 — TOTAL RETURN
# =============================================================================

def _get_bond_tr_data(df: pd.DataFrame, bond_type: str, hoy: date) -> list:
    """
    Construye la lista de bonos para el Total Return del cap 4.
    Usa _bond_obj_copy de OMSweb_app para obtener VN exacto del cashflow.
    Fallback a aproximación si el objeto bono no está disponible.
    """
    from datetime import timedelta
    rows = []
    df2 = _clean_df(df)
    settle_str = hoy.strftime("%d/%m/%Y")

    for _, r in df2.iterrows():
        ticker = str(r.get("Código", ""))
        tir    = _pct_float(r.get("TIREA"))
        dur    = r.get("Duration")
        precio = r.get("Last Price") or r.get("Last") or r.get("Close")

        if tir is None or precio is None:
            continue
        try:
            dur_f    = float(dur)
            precio_f = float(precio)
        except Exception:
            continue
        if not np.isfinite(dur_f) or not np.isfinite(precio_f) or precio_f <= 0:
            continue

        # Intentar obtener datos exactos del objeto bono
        vn       = None
        dias_cal = None
        fpago    = None
        try:
            bond = _app._bond_obj_copy(ticker)
            if bond is not None:
                # Calcular tirea para poblar cashflow_cpn y fecha_settlement
                bond.calcula_tirea(precio_f / 100.0, settle_str)
                cf = bond.cashflow_cpn
                fs = bond.fecha_settlement
                if cf is not None and fs is not None and not cf.empty:
                    cf_fut = cf[cf["Fechas"] > fs]
                    if not cf_fut.empty:
                        # VN = suma de flujos futuros (último flujo = amortización + cupón final)
                        venc_row = cf_fut.iloc[-1]
                        vn       = round(float(venc_row["Total"]), 6)
                        fpago_dt = venc_row["Fechas"]
                        dias_cal = (fpago_dt - fs).days
                        fpago    = fpago_dt.strftime("%d/%m/%Y")
        except Exception:
            pass

        # Fallback si no se pudo obtener del objeto bono
        if vn is None:
            dias_cal = max(1, round(dur_f * 365))
            fpago    = (hoy + timedelta(days=dias_cal)).strftime("%d/%m/%Y")
            vn       = round(precio_f * (1 + tir) ** dur_f, 6)

        rows.append({
            "ticker":   ticker,
            "vn":       vn,
            "precio":   round(precio_f, 4),
            "dias_cal": dias_cal,
            "tir":      round(tir, 10),
            "dur":      round(dur_f, 4),
            "fpago":    fpago,
        })
    return sorted(rows, key=lambda x: x["dur"])


def _get_boncer_tr_data(df: pd.DataFrame, hoy: date) -> list:
    """
    Construye la lista de bonos CER para TR.
    cer_ini = valor del CER en la fecha de settlement del bono.
    flujo_vto = flujo final del cashflow (VN ajustado CER).
    Usa rentafija.inputs para el CER y el objeto bono para los flujos.
    """
    from datetime import timedelta
    rows = []
    df2 = _clean_df(df)
    settle_str = hoy.strftime("%d/%m/%Y")

    # Leer serie CER de rentafija.inputs
    cer_serie = None
    cer_hoy   = 730.0
    try:
        import rentafija
        df_cer_inp = rentafija.inputs.get("CER")
        if df_cer_inp is not None and not df_cer_inp.empty:
            cer_hoy   = float(df_cer_inp["CER"].dropna().iloc[-1])
            cer_serie = df_cer_inp
    except Exception:
        pass

    for _, r in df2.iterrows():
        ticker = str(r.get("Código", ""))
        tir    = _pct_float(r.get("TIREA"))
        dur    = r.get("Duration")
        precio = r.get("Last Price") or r.get("Last") or r.get("Close")

        if tir is None or precio is None:
            continue
        try:
            dur_f    = float(dur)
            precio_f = float(precio)
        except Exception:
            continue
        if not np.isfinite(dur_f) or not np.isfinite(precio_f) or precio_f <= 0:
            continue

        cer_ini   = None
        flujo_vto = None
        dias_cal  = None
        fpago     = None

        try:
            bond = _app._bond_obj_copy(ticker)
            if bond is not None:
                bond.calcula_tirea(precio_f / 100.0, settle_str)
                cf = bond.cashflow_cpn
                fs = bond.fecha_settlement
                if cf is not None and fs is not None and not cf.empty:
                    cf_fut = cf[cf["Fechas"] > fs]
                    if not cf_fut.empty:
                        venc_row  = cf_fut.iloc[-1]
                        flujo_vto = round(float(venc_row["Total"]), 6)
                        fpago_dt  = venc_row["Fechas"]
                        dias_cal  = (fpago_dt - fs).days
                        fpago     = fpago_dt.strftime("%d/%m/%Y")
                        # cer_ini: valor CER en la fecha de settlement
                        if cer_serie is not None:
                            try:
                                idx_fs = cer_serie.index.asof(fs) if hasattr(cer_serie.index, 'asof') else None
                                if idx_fs is not None:
                                    cer_ini = float(cer_serie.loc[idx_fs, "CER"])
                            except Exception:
                                pass
                        if cer_ini is None:
                            cer_ini = cer_hoy
        except Exception:
            pass

        # Fallback
        if dias_cal is None:
            dias_cal  = max(1, round(dur_f * 365))
            fpago     = (hoy + timedelta(days=dias_cal)).strftime("%d/%m/%Y")
        if cer_ini is None:
            cer_ini = cer_hoy
        if flujo_vto is None:
            flujo_vto = round(precio_f * (1 + max(tir, -0.5)) ** dur_f, 4)

        rows.append({
            "ticker":       ticker,
            "cer_ini":      round(cer_ini, 6),
            "precio":       round(precio_f, 4),
            "dias_cal":     dias_cal,
            "flujo_vto":    flujo_vto,
            "tir_real_hoy": round(tir, 10),
            "dur":          round(dur_f, 4),
            "fpago":        fpago,
        })
    return sorted(rows, key=lambda x: x["dur"])


# Arrays estáticos cap 4 — extraídos del template original
# TRAMOS: días calendario entre días hábiles consecutivos (para costoFondeo)
# CER_BASE_TN: serie proyectada del índice CER por día hábil
# HAB_MAP_RAW: mapa día hábil → días calendario y fecha dd/mm
_C4_TRAMOS_JS    = '[1, 5, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 4, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 4, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 4, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 2, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 4, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1, 1, 3, 1, 1, 1]'
_C4_CER_BASE_JS  = '[null, 725.8754977709119, 726.5451914941815, 727.2155030777926, 727.886433091784, 731.2503796056459, 731.9250322022195, 732.600307234198, 734.6298726878097, 735.3076432093056, 735.9860390428082, 739.3874181010393, 740.0695779404158, 740.7523671413895, 741.4357862846105, 742.119835951264, 744.1757739117229, 744.8623514946946, 745.5495625150799, 746.3327675232229, 747.1167952936819, 749.4738238266715, 750.2611512986546, 751.0493058636307, 751.8382883904668, 752.6280997489426, 755.0025155257164, 755.7956509268364, 756.5896195222196, 757.384422187142, 760.571991079956, 761.370977253937, 762.1708027684587, 762.971468505254, 763.7729753469825, 766.1825513422746, 766.9874314488884, 767.7931570876602, 768.5997291468274, 769.4071485155605, 771.3207126549873, 771.9596243741781, 772.5990653261229, 773.2390359492034, 773.8795366821647, 776.4468495004437, 777.0900073767142, 777.7336980029779, 778.3779218205301, 780.313796839356, 780.9601578423308, 781.6070542485598, 782.2544865015362, 782.9024550451205, 784.8495828636416, 785.4997010156195, 786.1503576830287, 786.8015533119401, 787.4532883487942, 790.0617564570347, 790.7123137821288, 791.3634067929839, 792.0150359306975, 793.9731445214148, 794.6269225848066, 795.2812389859988, 795.9360941682727, 796.5914885752745, 798.5609115865922, 799.2184673362796, 799.8765645344122, 800.5352036268326, 801.1943850597507, 803.175187869102, 803.8365431334616, 804.4984429748853, 805.8238781829693, 807.8161265455539, 808.4813032790918, 809.1470277363906, 809.6640714746246, 810.1814456030326, 811.7355524411631, 812.2542502428047, 812.7732794915643, 813.292640399236, 813.8123331777495, 815.3734048596677, 815.8944272435534, 816.4157825599617, 816.9374710216359, 817.4594928414555, 819.0275605806198, 819.5509179645355, 820.0746097730354, 820.5986362198161, 821.122997518711, 822.698092668465, 823.2237955168847, 823.7498342886367, 824.2762091983757, 824.8029204608931, 827.2263979608985, 827.8595090423956, 828.4931046703755, 829.1271852156818, 831.0323400682556, 831.668363996985, 832.3048747015214, 832.9418725544145, 833.5793579284997, 835.4947429105393, 836.1341821034534, 836.7741106860194, 837.4145290327878, 838.0554375185956, 839.9811075629316, 840.6239803590092, 841.2673451726195, 841.9112023803239, 842.5555523589724, 844.4915626934088, 845.1378875301041, 845.6959367105284, 846.2543543738859, 846.8131407634879, 848.4917147252847, 849.0519784561926, 849.6126121323136, 850.1736159979246, 850.7349902974635]'
_C4_HAB_MAP_JS   = '{"1": {"d": 1, "f": "01/04"}, "2": {"d": 6, "f": "06/04"}, "3": {"d": 7, "f": "07/04"}, "4": {"d": 8, "f": "08/04"}, "5": {"d": 9, "f": "09/04"}, "6": {"d": 10, "f": "10/04"}, "7": {"d": 13, "f": "13/04"}, "8": {"d": 14, "f": "14/04"}, "9": {"d": 15, "f": "15/04"}, "10": {"d": 16, "f": "16/04"}, "11": {"d": 17, "f": "17/04"}, "12": {"d": 20, "f": "20/04"}, "13": {"d": 21, "f": "21/04"}, "14": {"d": 22, "f": "22/04"}, "15": {"d": 23, "f": "23/04"}, "16": {"d": 24, "f": "24/04"}, "17": {"d": 27, "f": "27/04"}, "18": {"d": 28, "f": "28/04"}, "19": {"d": 29, "f": "29/04"}, "20": {"d": 30, "f": "30/04"}, "21": {"d": 34, "f": "04/05"}, "22": {"d": 35, "f": "05/05"}, "23": {"d": 36, "f": "06/05"}, "24": {"d": 37, "f": "07/05"}, "25": {"d": 38, "f": "08/05"}, "26": {"d": 41, "f": "11/05"}, "27": {"d": 42, "f": "12/05"}, "28": {"d": 43, "f": "13/05"}, "29": {"d": 44, "f": "14/05"}, "30": {"d": 45, "f": "15/05"}, "31": {"d": 48, "f": "18/05"}, "32": {"d": 49, "f": "19/05"}, "33": {"d": 50, "f": "20/05"}, "34": {"d": 51, "f": "21/05"}, "35": {"d": 52, "f": "22/05"}, "36": {"d": 56, "f": "26/05"}, "37": {"d": 57, "f": "27/05"}, "38": {"d": 58, "f": "28/05"}, "39": {"d": 59, "f": "29/05"}, "40": {"d": 62, "f": "01/06"}, "41": {"d": 63, "f": "02/06"}, "42": {"d": 64, "f": "03/06"}, "43": {"d": 65, "f": "04/06"}, "44": {"d": 66, "f": "05/06"}, "45": {"d": 69, "f": "08/06"}, "46": {"d": 70, "f": "09/06"}, "47": {"d": 71, "f": "10/06"}, "48": {"d": 72, "f": "11/06"}, "49": {"d": 73, "f": "12/06"}, "50": {"d": 77, "f": "16/06"}, "51": {"d": 78, "f": "17/06"}, "52": {"d": 79, "f": "18/06"}, "53": {"d": 80, "f": "19/06"}, "54": {"d": 83, "f": "22/06"}, "55": {"d": 84, "f": "23/06"}, "56": {"d": 85, "f": "24/06"}, "57": {"d": 86, "f": "25/06"}, "58": {"d": 87, "f": "26/06"}, "59": {"d": 90, "f": "29/06"}, "60": {"d": 91, "f": "30/06"}, "61": {"d": 92, "f": "01/07"}, "62": {"d": 93, "f": "02/07"}, "63": {"d": 94, "f": "03/07"}, "64": {"d": 97, "f": "06/07"}, "65": {"d": 98, "f": "07/07"}, "66": {"d": 99, "f": "08/07"}, "67": {"d": 101, "f": "10/07"}, "68": {"d": 104, "f": "13/07"}, "69": {"d": 105, "f": "14/07"}, "70": {"d": 106, "f": "15/07"}, "71": {"d": 107, "f": "16/07"}, "72": {"d": 108, "f": "17/07"}, "73": {"d": 111, "f": "20/07"}, "74": {"d": 112, "f": "21/07"}, "75": {"d": 113, "f": "22/07"}, "76": {"d": 114, "f": "23/07"}, "77": {"d": 115, "f": "24/07"}, "78": {"d": 118, "f": "27/07"}, "79": {"d": 119, "f": "28/07"}, "80": {"d": 120, "f": "29/07"}, "81": {"d": 121, "f": "30/07"}, "82": {"d": 122, "f": "31/07"}, "83": {"d": 125, "f": "03/08"}, "84": {"d": 126, "f": "04/08"}, "85": {"d": 127, "f": "05/08"}, "86": {"d": 128, "f": "06/08"}, "87": {"d": 129, "f": "07/08"}, "88": {"d": 132, "f": "10/08"}, "89": {"d": 133, "f": "11/08"}, "90": {"d": 134, "f": "12/08"}, "91": {"d": 135, "f": "13/08"}, "92": {"d": 136, "f": "14/08"}, "93": {"d": 140, "f": "18/08"}, "94": {"d": 141, "f": "19/08"}, "95": {"d": 142, "f": "20/08"}, "96": {"d": 143, "f": "21/08"}, "97": {"d": 146, "f": "24/08"}, "98": {"d": 147, "f": "25/08"}, "99": {"d": 148, "f": "26/08"}, "100": {"d": 149, "f": "27/08"}, "101": {"d": 150, "f": "28/08"}, "102": {"d": 153, "f": "31/08"}, "103": {"d": 154, "f": "01/09"}, "104": {"d": 155, "f": "02/09"}, "105": {"d": 156, "f": "03/09"}, "106": {"d": 157, "f": "04/09"}, "107": {"d": 160, "f": "07/09"}, "108": {"d": 161, "f": "08/09"}, "109": {"d": 162, "f": "09/09"}, "110": {"d": 163, "f": "10/09"}, "111": {"d": 164, "f": "11/09"}, "112": {"d": 167, "f": "14/09"}, "113": {"d": 168, "f": "15/09"}, "114": {"d": 169, "f": "16/09"}, "115": {"d": 170, "f": "17/09"}, "116": {"d": 171, "f": "18/09"}, "117": {"d": 174, "f": "21/09"}, "118": {"d": 175, "f": "22/09"}, "119": {"d": 176, "f": "23/09"}, "120": {"d": 177, "f": "24/09"}, "121": {"d": 178, "f": "25/09"}, "122": {"d": 181, "f": "28/09"}, "123": {"d": 182, "f": "29/09"}, "124": {"d": 183, "f": "30/09"}, "125": {"d": 184, "f": "01/10"}, "126": {"d": 185, "f": "02/10"}, "127": {"d": 188, "f": "05/10"}, "128": {"d": 189, "f": "06/10"}, "129": {"d": 190, "f": "07/10"}, "130": {"d": 191, "f": "08/10"}}'


def _build_cap4_html(
    df_lecap:  pd.DataFrame,
    df_cer:    pd.DataFrame,
    hoy: date,
) -> str:
    """
    Genera el HTML del cap 4 — Total Return interactivo.
    Mantiene la lógica JS del template original, solo reemplaza los datos.
    """
    boncap_data = _get_bond_tr_data(df_lecap, "lecap", hoy)
    boncer_data = _get_boncer_tr_data(df_cer, hoy)

    boncap_json = json.dumps(boncap_data, ensure_ascii=False)
    boncer_json = json.dumps(boncer_data, ensure_ascii=False)
    tramos_js    = _C4_TRAMOS_JS
    cer_base_js  = _C4_CER_BASE_JS
    hab_map_js   = _C4_HAB_MAP_JS

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">04</div>
  <div class="slide-section-stripe" style="background:#1e6fba"></div>
  <div class="slide-section-titles">
    <h2>Total Return por Escenario de Tasa</h2>
    <div class="slide-section-sub">Retorno total vs costo de fondeo · BONCAP · BONCER · Horizonte variable</div>
  </div>
</div>

<style>
/* ── Cap 4 styles Delta ── */
.c4-controls {{
  display:flex; gap:20px; flex-wrap:wrap; align-items:flex-end;
  padding:12px 0 10px; border-bottom:1px solid #d8e2ed; margin-bottom:16px;
}}
.c4-ctrl-group {{ display:flex; flex-direction:column; gap:5px; }}
.c4-ctrl-label {{
  font-size:9px; font-weight:700; text-transform:uppercase;
  letter-spacing:.8px; color:#5f7080;
  font-family: var(--font-title,'Barlow',Arial,sans-serif);
}}
.c4-ctrl-row {{ display:flex; align-items:center; gap:8px; }}
.c4-ctrl-val {{
  font-size:13px; font-weight:700; min-width:70px;
  color:#0f2557; font-family: var(--font-title,'Barlow',Arial,sans-serif);
}}
.c4-ctrl-sep {{ width:1px; background:#d8e2ed; align-self:stretch; margin:0 6px; }}
.c4-step-info {{
  font-size:11px; color:#5f7080; padding:4px 10px;
  background:#f0f4f8; border-radius:5px; border:1px solid #d8e2ed; white-space:nowrap;
}}
input[type=range].c4-slider {{ width:120px; accent-color:#1e6fba; }}
.c4-section-label {{
  font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.8px; color:#1e6fba;
  border-left:3px solid #b85a1a; padding-left:8px; margin:18px 0 10px;
  font-family: var(--font-title,'Barlow',Arial,sans-serif);
}}
.c4-table-wrap {{ overflow-x:auto; margin-bottom:6px; }}
.c4-table {{ border-collapse:collapse; font-size:10.5px; }}
.c4-table th {{
  padding:6px 10px; font-size:9px; font-weight:700;
  text-transform:uppercase; color:#5f7080;
  background:#f0f4f8; border-bottom:1.5px solid #d8e2ed;
  white-space:nowrap; text-align:center;
  font-family: var(--font-title,'Barlow',Arial,sans-serif);
}}
.c4-table th.lbl {{ text-align:left; min-width:110px; }}
.c4-table td {{
  padding:4px 10px; text-align:center; font-weight:700;
  font-size:10.5px; border-bottom:1px solid #eaeef2; white-space:nowrap;
  font-family: var(--font-body,'Calibri',Arial,sans-serif);
}}
.c4-table td.lbl {{
  text-align:left; font-weight:500; color:#5f7080; background:#f7f9fc;
}}
.c4-table tr.cur-row td {{
  border-top:2px solid #1e6fba; border-bottom:2px solid #1e6fba;
}}
.c4-table tr.cur-row td.lbl {{ font-weight:700; color:#0f2557; }}
.th-sub {{ font-size:8px; font-weight:400; color:#7a90a4; display:block; margin-top:2px; }}
.th-be-tf  {{ font-size:8px; font-weight:700; color:#1e6fba; display:block; margin-top:1px; }}
.th-be-cer {{ font-size:8px; font-weight:700; color:#1a7a46; display:block; margin-top:1px; }}
.c4-no-bonos {{ padding:14px 0; font-size:12px; color:#5f7080; }}
.c4-chart-row {{
  display:grid; grid-template-columns:1fr 280px; gap:14px; margin-top:10px;
}}
.c4-chart-box {{
  border:1px solid #d8e2ed; border-radius:7px; overflow:hidden; background:#fff;
  box-shadow:0 1px 4px rgba(15,37,87,0.05);
}}
.c4-chart-header {{
  padding:7px 14px; background:#f7f9fc; border-bottom:1px solid #d8e2ed;
  font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.5px; color:#1e6fba;
  font-family: var(--font-title,'Barlow',Arial,sans-serif);
}}
.c4-chart-inner {{ padding:6px 4px 2px; }}
.c4-be-table {{ font-size:10.5px; padding:10px 14px; line-height:1.9; }}
.c4-be-row {{ display:flex; justify-content:space-between; gap:20px; }}
.c4-be-ticker {{ font-weight:700; color:#0f2557; min-width:52px; }}
.c4-be-actual {{ color:#5f7080; }}
.c4-be-delta-pos {{ font-weight:700; color:#1a7a46; }}
.c4-be-delta-neg {{ font-weight:700; color:#c0392b; }}
</style>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function() {{
const N_FILAS = 20;
const BONCAP  = {boncap_json};
const BONCER  = {boncer_json};
const TRAMOS  = {tramos_js};
const CER_BASE_TN = {cer_base_js};
const HAB_MAP_RAW = {hab_map_js};

function getMap(n){{
  const k=String(Math.min(n,130));
  return HAB_MAP_RAW[k]||{{d:n,f:'—'}};
}}

function costoFondeo(nHab,tna){{
  let a=1.0;
  for(let i=0;i<nHab;i++) a*=(1+tna/365*TRAMOS[i]);
  return a-1.0;
}}

function makeYields(piso,techo){{
  const out=[];
  for(let i=0;i<N_FILAS;i++) out.push(+(piso+i*(techo-piso)/(N_FILAS-1)).toFixed(6));
  return out;
}}

function colorTR(v){{
  if(v>=8)  return['#0d6b35','#fff'];
  if(v>=4)  return['#1a7a46','#fff'];
  if(v>=1)  return['#91cf60','#333'];
  if(v>=0)  return['#fee08b','#333'];
  if(v>=-3) return['#fc8d59','#fff'];
  return['#c0392b','#fff'];
}}

let chartTF=null, chartCER=null;

function drawCurveChart(canvasId,labels,dursAct,tirsAct,dursBE,tirsBE,colorAct,colorBE,labelAct,labelBE,fmtY,prevChart){{
  const ctx=document.getElementById(canvasId);
  if(!ctx) return null;
  if(prevChart) prevChart.destroy();
  return new Chart(ctx.getContext('2d'),{{
    type:'scatter',
    data:{{datasets:[
      {{label:labelAct,data:dursAct.map(function(d,i){{return {{x:d,y:tirsAct[i]}};}})),
        borderColor:colorAct,backgroundColor:colorAct,
        pointRadius:5,pointHoverRadius:7,showLine:true,
        borderWidth:2.5,tension:0.3,fill:false}},
      {{label:labelBE,data:dursBE.map(function(d,i){{return {{x:d,y:tirsBE[i]}};}})),
        borderColor:colorBE,backgroundColor:colorBE,
        pointRadius:5,pointHoverRadius:7,showLine:true,
        borderWidth:2,borderDash:[6,4],tension:0.3,fill:false}},
    ]}},
    options:{{
      responsive:true,maintainAspectRatio:false,
      plugins:{{
        legend:{{display:true,position:'top',labels:{{boxWidth:12,font:{{size:10}},color:'#5f7080'}}}},
        tooltip:{{callbacks:{{label:c=>labels[c.dataIndex]+': '+fmtY(c.parsed.y)}}}}
      }},
      scales:{{
        x:{{title:{{display:true,text:'Duration (años)',font:{{size:9}},color:'#7a90a4'}},
           grid:{{color:'#eaeef2'}},ticks:{{font:{{size:8}},color:'#7a90a4'}}}},
        y:{{title:{{display:true,text:'Tasa',font:{{size:9}},color:'#7a90a4'}},
           grid:{{color:'#eaeef2'}},
           ticks:{{font:{{size:8}},color:'#7a90a4',callback:v=>fmtY(v)}}}}
      }}
    }}
  }});
}}

function render(){{
  const nHab  =parseInt(document.getElementById('c4-hab').value);
  const fondeo=parseInt(document.getElementById('c4-fondeo').value)/100;
  const pisoTF =parseInt(document.getElementById('c4-piso-tf').value)/100;
  const techoTF=parseInt(document.getElementById('c4-techo-tf').value)/100;
  const pisoCER =parseInt(document.getElementById('c4-piso-cer').value)/100;
  const techoCER=parseInt(document.getElementById('c4-techo-cer').value)/100;

  const map=getMap(nHab);
  const diasCal=map.d; const fechaLiq=map.f;
  document.getElementById('c4-h-val').textContent='T+'+nHab+'h · '+diasCal+'d · '+fechaLiq;
  document.getElementById('c4-f-val').textContent=(fondeo*100).toFixed(0)+'%';
  document.getElementById('c4-piso-tf-val').textContent=(pisoTF*100).toFixed(0)+'%';
  document.getElementById('c4-techo-tf-val').textContent=(techoTF*100).toFixed(0)+'%';
  document.getElementById('c4-piso-cer-val').textContent=(pisoCER*100).toFixed(0)+'%';
  document.getElementById('c4-techo-cer-val').textContent=(techoCER*100).toFixed(0)+'%';

  const cf=costoFondeo(nHab,fondeo);
  document.getElementById('c4-step-info').textContent='Costo fondeo: '+(cf*100).toFixed(4)+'%';

  // ── TASA FIJA ──
  const bonosTF=BONCAP.filter(b=>b.dias_cal>diasCal);
  const tblTF=document.getElementById('c4-tbl-tf');
  const noTF=document.getElementById('c4-no-tf');

  if(!bonosTF.length){{
    tblTF.style.display='none'; noTF.style.display='block';
  }}else{{
    tblTF.style.display=''; noTF.style.display='none';
    const yTF=(techoTF>pisoTF)?makeYields(pisoTF,techoTF):makeYields(0.20,0.50);
    const pasoTF=(techoTF>pisoTF)?(techoTF-pisoTF)/(N_FILAS-1):0.015;
    const elStepTF=document.getElementById('c4-step-tf');
    if(elStepTF) elStepTF.textContent='Paso: '+(pasoTF*100).toFixed(2)+' pp · '+N_FILAS+' filas';

    const besTF=bonosTF.map(b=>{{
      const dR=b.dias_cal-diasCal;
      return Math.pow(b.vn/(b.precio*(1+cf)),365/dR)-1;
    }});

    document.getElementById('c4-thead-tf').innerHTML=
      '<tr><th class="lbl">Exit yield TEA</th>'+
      bonosTF.map((b,i)=>{{
        const d=(besTF[i]-b.tir)*100; const sg=d>=0?'+':'';
        return '<th>'+b.ticker+'<span class="th-sub">'+(b.tir*100).toFixed(2)+'% hoy · '+b.fpago+'</span>'+
               '<span class="th-be-tf">BE: '+(besTF[i]*100).toFixed(2)+'% ('+sg+d.toFixed(1)+'pp)</span></th>';
      }}).join('')+'</tr>';

    document.getElementById('c4-tbody-tf').innerHTML=yTF.map(ey=>{{
      const isCur=bonosTF.some(b=>Math.abs(b.tir-ey)<pasoTF/2+0.0001);
      const cells=bonosTF.map(b=>{{
        const dR=b.dias_cal-diasCal;
        const pS=b.vn/Math.pow(1+ey,dR/365);
        const tr=pS/b.precio-1-cf;
        const[bg,col]=colorTR(tr*100);
        return '<td style="background:'+bg+';color:'+col+'">'+(tr*100).toFixed(2)+'%</td>';
      }}).join('');
      const lbl=isCur?'→ '+(ey*100).toFixed(1)+'%':(ey*100).toFixed(1)+'%';
      return '<tr class="'+(isCur?'cur-row':'')+'"><td class="lbl">'+lbl+'</td>'+cells+'</tr>';
    }}).join('');

    chartTF=drawCurveChart('c4-chart-tf',
      bonosTF.map(b=>b.ticker),
      bonosTF.map(b=>b.dur), bonosTF.map(b=>b.tir),
      bonosTF.map(b=>b.dur), besTF,
      '#1e6fba','#b85a1a','Curva actual','Curva break-even',
      v=>(v*100).toFixed(1)+'%', chartTF);

    document.getElementById('c4-be-tf').innerHTML=
      '<div style="font-size:9px;font-weight:700;text-transform:uppercase;color:#5f7080;margin-bottom:8px;letter-spacing:.5px;font-family:var(--font-title,Barlow,Arial)">Break-even por bono</div>'+
      bonosTF.map((b,i)=>{{
        const d=(besTF[i]-b.tir)*100;
        const cls=d>=0?'c4-be-delta-pos':'c4-be-delta-neg';
        const sg=d>=0?'+':'';
        return '<div class="c4-be-row">'+
          '<span class="c4-be-ticker">'+b.ticker+'</span>'+
          '<span class="c4-be-actual">'+(b.tir*100).toFixed(2)+'% → '+(besTF[i]*100).toFixed(2)+'%</span>'+
          '<span class="'+cls+'">'+sg+d.toFixed(1)+'pp</span>'+
          '</div>';
      }}).join('');
  }}

  // ── CER ──
  const cerBaseTN=CER_BASE_TN[nHab]||CER_BASE_TN[1];
  const bonosCER=BONCER.filter(b=>b.dias_cal>diasCal+1);
  const tblCER=document.getElementById('c4-tbl-cer');
  const noCER=document.getElementById('c4-no-cer');

  if(!bonosCER.length){{
    tblCER.style.display='none'; noCER.style.display='block';
  }}else{{
    tblCER.style.display=''; noCER.style.display='none';
    const yCER=(techoCER>pisoCER)?makeYields(pisoCER,techoCER):makeYields(-0.06,0.15);
    const pasoCER=(techoCER>pisoCER)?(techoCER-pisoCER)/(N_FILAS-1):0.011;
    const elStepCER=document.getElementById('c4-step-cer');
    if(elStepCER) elStepCER.textContent='Paso: '+(pasoCER*100).toFixed(2)+' pp · '+N_FILAS+' filas';

    const besCER=bonosCER.map(b=>{{
      const dR=b.dias_cal-diasCal-1;
      const flujoTN=100*cerBaseTN/b.cer_ini;
      const pBE=b.precio*(1+cf);
      return Math.pow(flujoTN/pBE,365/dR)-1;
    }});

    document.getElementById('c4-thead-cer').innerHTML=
      '<tr><th class="lbl">Exit yield real TEA</th>'+
      bonosCER.map((b,i)=>{{
        const d=(besCER[i]-b.tir_real_hoy)*100; const sg=d>=0?'+':'';
        return '<th>'+b.ticker+'<span class="th-sub">'+(b.tir_real_hoy*100).toFixed(2)+'% real hoy · '+b.fpago+'</span>'+
               '<span class="th-be-cer">BE: '+(besCER[i]*100).toFixed(2)+'% ('+sg+d.toFixed(1)+'pp)</span></th>';
      }}).join('')+'</tr>';

    document.getElementById('c4-tbody-cer').innerHTML=yCER.map(ey=>{{
      const avgBE=besCER.reduce((s,v)=>s+v,0)/besCER.length;
      const isCur=Math.abs(avgBE-ey)<pasoCER/2+0.0001;
      const cells=bonosCER.map(b=>{{
        const dR=b.dias_cal-diasCal-1;
        const flujoTN=100*cerBaseTN/b.cer_ini;
        const pS=flujoTN/Math.pow(1+ey,dR/365);
        const tr=pS/b.precio-1-cf;
        const[bg,col]=colorTR(tr*100);
        return '<td style="background:'+bg+';color:'+col+'">'+(tr*100).toFixed(2)+'%</td>';
      }}).join('');
      const lbl=isCur?'→ '+(ey*100).toFixed(1)+'%':(ey*100).toFixed(1)+'%';
      return '<tr class="'+(isCur?'cur-row':'')+'"><td class="lbl">'+lbl+'</td>'+cells+'</tr>';
    }}).join('');

    chartCER=drawCurveChart('c4-chart-cer',
      bonosCER.map(b=>b.ticker),
      bonosCER.map(b=>b.dur), bonosCER.map(b=>b.tir_real_hoy),
      bonosCER.map(b=>b.dur), besCER,
      '#1a7a46','#b85a1a','Curva real actual','Curva real break-even',
      v=>(v*100).toFixed(1)+'%', chartCER);

    document.getElementById('c4-be-cer').innerHTML=
      '<div style="font-size:9px;font-weight:700;text-transform:uppercase;color:#5f7080;margin-bottom:8px;letter-spacing:.5px;font-family:var(--font-title,Barlow,Arial)">Break-even por bono</div>'+
      bonosCER.map((b,i)=>{{
        const d=(besCER[i]-b.tir_real_hoy)*100;
        const cls=d>=0?'c4-be-delta-pos':'c4-be-delta-neg';
        const sg=d>=0?'+':'';
        return '<div class="c4-be-row">'+
          '<span class="c4-be-ticker">'+b.ticker+'</span>'+
          '<span class="c4-be-actual">'+(b.tir_real_hoy*100).toFixed(2)+'% → '+(besCER[i]*100).toFixed(2)+'%</span>'+
          '<span class="'+cls+'">'+sg+d.toFixed(1)+'pp</span>'+
          '</div>';
      }}).join('');
  }}
}}

// Adjuntar listeners a los sliders
document.addEventListener('DOMContentLoaded',function(){{
  ['c4-hab','c4-fondeo','c4-piso-tf','c4-techo-tf','c4-piso-cer','c4-techo-cer'].forEach(id=>{{
    const el=document.getElementById(id);
    if(el) el.addEventListener('input',render);
  }});
  // No renderizar en DOMContentLoaded — el slide está oculto
  // Renderizar cuando el slide se vuelve visible
}});

// Lazy render del cap4: renderiza cuando el slide-4 se vuelve visible
(function(){{
  var _c4done = false;

  function _renderC4(){{
    if (_c4done) return;
    var cv1 = document.getElementById('c4-chart-tf');
    if (!cv1) return;
    // Verificar que el canvas tiene dimensiones (slide visible)
    var rect = cv1.getBoundingClientRect();
    if (rect.width < 10) {{
      setTimeout(_renderC4, 100);
      return;
    }}
    render();
    _c4done = true;
  }}

  // MutationObserver: detectar cuando slide-4 recibe clase 'active'
  function _setupC4Observer(){{
    var slide4 = document.getElementById('slide-4');
    if (!slide4) {{ setTimeout(_setupC4Observer, 100); return; }}
    var obs = new MutationObserver(function(){{
      if (slide4.classList.contains('active')) {{
        _c4done = false;  // permitir re-render si se navega varias veces
        setTimeout(_renderC4, 80);
      }}
    }});
    obs.observe(slide4, {{attributes: true, attributeFilter: ['class']}});
  }}

  // Engancharse al sistema de navegación unificado
  document.addEventListener('DOMContentLoaded', function(){{
    _setupC4Observer();
    // Parchear goToId para renderizar al navegar al slide-4
    var _origGoToId = window.goToId;
    if (typeof _origGoToId === 'function') {{
      window.goToId = function(id) {{
        _origGoToId(id);
        if (id === 'slide-4') {{ _c4done = false; setTimeout(_renderC4, 80); }}
      }};
    }}
  }});
}})();
}})();
</script>

<!-- Controles compartidos -->
<div class="c4-controls">
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Horizonte T+N (días hábiles)</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-hab" class="c4-slider" min="1" max="130" step="1" value="20">
      <div class="c4-ctrl-val" id="c4-h-val">—</div>
    </div>
  </div>
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Fondeo TNA</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-fondeo" class="c4-slider" min="0" max="100" step="1" value="26">
      <div class="c4-ctrl-val" id="c4-f-val">26%</div>
    </div>
  </div>
  <div class="c4-step-info" id="c4-step-info">—</div>
</div>

<!-- PANEL A: TASA FIJA -->
<div class="c4-section-label">A — Tasa Fija (BONCAP)</div>
<div class="c4-controls" style="padding:8px 0 10px;margin-bottom:10px;">
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Exit yield — Piso</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-piso-tf" class="c4-slider" min="10" max="59" step="1" value="20">
      <div class="c4-ctrl-val" id="c4-piso-tf-val">20%</div>
    </div>
  </div>
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Exit yield — Techo</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-techo-tf" class="c4-slider" min="11" max="60" step="1" value="50">
      <div class="c4-ctrl-val" id="c4-techo-tf-val">50%</div>
    </div>
  </div>
  <div class="c4-step-info" id="c4-step-tf">—</div>
</div>
<div class="c4-table-wrap">
  <table class="c4-table" id="c4-tbl-tf">
    <thead id="c4-thead-tf"></thead>
    <tbody id="c4-tbody-tf"></tbody>
  </table>
  <div class="c4-no-bonos" id="c4-no-tf" style="display:none">Sin bonos con vencimiento posterior al horizonte.</div>
</div>
<div class="c4-chart-row">
  <div class="c4-chart-box">
    <div class="c4-chart-header">Curva actual vs Break-even — BONCAP</div>
    <div class="c4-chart-inner"><canvas id="c4-chart-tf" height="200"></canvas></div>
  </div>
  <div class="c4-chart-box">
    <div class="c4-chart-header">Widening / compresión implícita</div>
    <div class="c4-be-table" id="c4-be-tf"></div>
  </div>
</div>

<!-- PANEL B: CER -->
<div class="c4-section-label">B — CER (BONCER)</div>
<div class="c4-controls" style="padding:8px 0 10px;margin-bottom:10px;">
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Exit yield real — Piso</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-piso-cer" class="c4-slider" min="-10" max="29" step="1" value="-6">
      <div class="c4-ctrl-val" id="c4-piso-cer-val">-6%</div>
    </div>
  </div>
  <div class="c4-ctrl-group">
    <div class="c4-ctrl-label">Exit yield real — Techo</div>
    <div class="c4-ctrl-row">
      <input type="range" id="c4-techo-cer" class="c4-slider" min="-9" max="30" step="1" value="15">
      <div class="c4-ctrl-val" id="c4-techo-cer-val">15%</div>
    </div>
  </div>
  <div class="c4-step-info" id="c4-step-cer">—</div>
</div>
<div class="c4-table-wrap">
  <table class="c4-table" id="c4-tbl-cer">
    <thead id="c4-thead-cer"></thead>
    <tbody id="c4-tbody-cer"></tbody>
  </table>
  <div class="c4-no-bonos" id="c4-no-cer" style="display:none">Sin bonos con vencimiento posterior al horizonte.</div>
</div>
<div class="c4-chart-row">
  <div class="c4-chart-box">
    <div class="c4-chart-header">Curva real actual vs Break-even — BONCER</div>
    <div class="c4-chart-inner"><canvas id="c4-chart-cer" height="200"></canvas></div>
  </div>
  <div class="c4-chart-box">
    <div class="c4-chart-header">Widening / compresión implícita</div>
    <div class="c4-be-table" id="c4-be-cer"></div>
  </div>
</div>
""".strip()



# =============================================================================
# CAP 5 — COBERTURA ROFEX
# =============================================================================

def _fetch_fx_data() -> dict:
    """
    Obtiene datos FX en tiempo real:
    - MEP, CCL: dolarapi.com
    - SPOT MULC: dolarapi.com (mayorista)
    - Bandas BCRA: descarga el XLSX oficial
    Devuelve dict con spot, mep, ccl, techo_hoy, piso_hoy, banda_serie
    """
    import urllib.request
    import json as _json

    result = {
        "spot": None, "mep": None, "ccl": None,
        "techo_hoy": None, "piso_hoy": None,
        "banda_serie": []   # [(fecha_str, techo, piso), ...]
    }

    # ── DolarApi ──────────────────────────────────────────────────────
    try:
        urls = {
            "mayorista": "https://dolarapi.com/v1/dolares/mayorista",
            "mep":       "https://dolarapi.com/v1/dolares/bolsa",
            "ccl":       "https://dolarapi.com/v1/dolares/contadoconliqui",
        }
        for key, url in urls.items():
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = _json.loads(r.read())
            if key == "mayorista":
                result["spot"] = float(d.get("venta") or d.get("compra") or 0) or None
            elif key == "mep":
                result["mep"] = float(d.get("venta") or d.get("compra") or 0) or None
            elif key == "ccl":
                result["ccl"] = float(d.get("venta") or d.get("compra") or 0) or None
    except Exception as e:
        print(f"[cap5] Warning FX fetch: {e}")

    # ── Bandas BCRA — XLSX ────────────────────────────────────────────
    try:
        import io, urllib.request
        xlsx_url = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/serie-completa-bandas-cambiarias.xlsx"
        req = urllib.request.Request(xlsx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        df_banda = pd.read_excel(io.BytesIO(data), header=None)
        # Encontrar la columna de fechas y valores
        # El XLSX tiene: col 0 = fecha, col 1 = piso, col 2 = techo (aprox)
        # Parsear buscando columna con fechas
        hoy_date = date.today()
        serie = []
        for _, row in df_banda.iterrows():
            try:
                fecha = pd.to_datetime(row.iloc[0], dayfirst=True).date()
                piso  = float(row.iloc[1])
                techo = float(row.iloc[2])
                if pd.isna(piso) or pd.isna(techo):
                    continue
                serie.append((fecha, techo, piso))
            except Exception:
                continue
        serie = sorted(serie, key=lambda x: x[0])
        result["banda_serie"] = serie
        # Techo/piso de hoy
        today_vals = [(t, pi) for (f, t, pi) in serie if f == hoy_date]
        if today_vals:
            result["techo_hoy"] = today_vals[-1][0]
            result["piso_hoy"]  = today_vals[-1][1]
        elif serie:
            result["techo_hoy"] = serie[-1][1]
            result["piso_hoy"]  = serie[-1][2]
    except Exception as e:
        print(f"[cap5] Warning banda BCRA: {e}")

    return result


def _get_banda_for_date(banda_serie: list, target_date: date):
    """Interpola/extrapola el techo y piso de banda para una fecha dada."""
    if not banda_serie:
        return None, None
    # Buscar el valor más cercano
    future = [(f, t, p) for f, t, p in banda_serie if f >= target_date]
    if future:
        return future[0][1], future[0][2]
    # Extrapolar desde el último valor con la tasa mensual implícita
    last_f, last_t, last_p = banda_serie[-1]
    days = (target_date - last_f).days
    if days <= 0 or len(banda_serie) < 2:
        return last_t, last_p
    # Tasa diaria implícita del último mes de datos
    prev_f, prev_t, prev_p = banda_serie[-30] if len(banda_serie) > 30 else banda_serie[0]
    d_prev = (last_f - prev_f).days or 1
    tasa_t = (last_t / prev_t) ** (1 / d_prev) - 1
    tasa_p = (last_p / prev_p) ** (1 / d_prev) - 1
    techo_ext = last_t * (1 + tasa_t) ** days
    piso_ext  = last_p * (1 + tasa_p) ** days
    return round(techo_ext, 2), round(piso_ext, 2)



def _assign_bond_to_dus(dus_date: date, df_lecap: pd.DataFrame,
                        df_cer: pd.DataFrame, tamar_tea: float,
                        used_tickers: set = None) -> dict:
    """
    Para cada DUS asigna el mejor bono ARS:
    1. BONCAP/LECAP que vence lo más cerca DESPUES del DUS (no antes si hay alternativa)
    2. Si no hay BONCAP a <=45 dias, BONCER proyectado (j) mas cercano
    """
    from datetime import timedelta

    def _vto(dur: float) -> date:
        return date.today() + timedelta(days=round(float(dur) * 365))

    if used_tickers is None:
        used_tickers = set()
    candidates_cap = []
    for _, r in _clean_df(df_lecap).iterrows():
        dur = r.get("Duration"); tir = _pct_float(r.get("TIREA"))
        if dur is None or tir is None: continue
        ticker = str(r["Código"])
        if ticker in used_tickers: continue  # ya asignado a otro DUS
        try: dur_f = float(dur); vto = _vto(dur_f)
        except: continue
        candidates_cap.append({
            "ticker": ticker, "tipo": "BONCAP",
            "tir_nom": round(tir * 100, 4), "dur": round(dur_f, 4),
            "vto": vto, "delta": (vto - dus_date).days,
        })

    best = None
    best_delta_abs = 9999
    if candidates_cap:
        after  = [c for c in candidates_cap if c["delta"] >= 0]
        before = [c for c in candidates_cap if c["delta"] <  0]
        if after:
            best = min(after, key=lambda c: c["delta"])
        elif before:
            best = max(before, key=lambda c: c["delta"])
        if best:
            best_delta_abs = abs(best["delta"])

    if best_delta_abs > 45:
        candidates_cer = []
        for _, r in _clean_df(df_cer).iterrows():
            ticker = str(r.get("Código", "")); dur = r.get("Duration")
            tir = _pct_float(r.get("TIREA"))
            if dur is None or tir is None: continue
            try: dur_f = float(dur); vto = _vto(dur_f)
            except: continue
            infl_anual = 0.42
            tir_nom = (1 + tir) * (1 + infl_anual) - 1
            candidates_cer.append({
                "ticker": ticker + "j", "tipo": "BONCER",
                "tir_nom": round(tir_nom * 100, 4), "dur": round(dur_f, 4),
                "vto": vto, "delta": abs((vto - dus_date).days),
            })
        # Filtrar CER ya usados
        candidates_cer = [c for c in candidates_cer if c["ticker"] not in used_tickers]
        if candidates_cer:
            best_cer = min(candidates_cer, key=lambda c: c["delta"])
            if best is None or best_cer["delta"] < best_delta_abs:
                best = best_cer

    return best



def _get_futuros_auto(df_futuros_param, prev_snap: dict, hoy: date) -> "pd.DataFrame | None":
    """
    Obtiene el DataFrame de futuros DUS en este orden de prioridad:
    1. df_futuros pasado como parámetro (ya procesado)
    2. futuros_minorista del módulo bymaapi (si está disponible en el entorno)
    3. Datos del snapshot del HTML anterior (JSON embebido)
    Retorna None si no hay ninguna fuente disponible.
    """
    from datetime import timedelta

    # 1. Parámetro explícito
    if df_futuros_param is not None and not df_futuros_param.empty:
        return df_futuros_param

    # 2. futuros_minorista de bymaapi (global del módulo)
    try:
        import bymaapi
        fm = getattr(bymaapi, "futuros_minorista", None)
        if fm is not None and not fm.empty:
            print("[cap5] Usando futuros_minorista de bymaapi")
            # Normalizar columnas: symbol/Código, price/Last Price, days_to_maturity/Dias Vto
            df = fm.copy()
            rename = {}
            if "symbol" in df.columns and "Código" not in df.columns:
                rename["symbol"] = "Código"
            if "price" in df.columns and "Last Price" not in df.columns:
                rename["price"] = "Last Price"
            if "days_to_maturity" in df.columns and "Dias Vto" not in df.columns:
                rename["days_to_maturity"] = "Dias Vto"
            if "maturityDate" in df.columns and "Fecha Vto" not in df.columns:
                rename["maturityDate"] = "Fecha Vto"
            if rename:
                df = df.rename(columns=rename)
            # Filtrar solo minorista (sin sufijo A)
            if "Código" in df.columns:
                df = df[~df["Código"].astype(str).str.endswith("A")].copy()
            return df.reset_index(drop=True)
    except Exception as e:
        pass

    # 3. Snapshot del HTML anterior
    if prev_snap and prev_snap.get("rofex"):
        print("[cap5] Usando precios ROFEX del comité anterior (sin datos frescos)")
        rofex = prev_snap["rofex"]
        rows = []
        for r in rofex:
            precio = r.get("precio")
            dias   = r.get("dias")
            fecha  = r.get("fecha_vto")
            ticker = r.get("ticker", "")
            if precio and dias:
                rows.append({
                    "Código":     ticker,
                    "Last Price": precio,
                    "Dias Vto":   dias,
                    "Fecha Vto":  fecha,
                })
        if rows:
            return pd.DataFrame(rows)

    return None



def _build_cap5_html(
    df_lecap:  pd.DataFrame,
    df_cer:    pd.DataFrame,
    df_tamar:  pd.DataFrame,
    df_dual:   pd.DataFrame,
    df_futuros: pd.DataFrame,
    tamar_tea: float,
    hoy: date,
) -> str:
    """Genera el HTML del cap 5 — Cobertura ROFEX."""
    from datetime import timedelta

    # ── Datos FX en tiempo real ──────────────────────────────────────
    fx = _fetch_fx_data()
    spot      = fx["spot"]
    mep       = fx["mep"]
    ccl       = fx["ccl"]
    techo_hoy = fx["techo_hoy"]
    piso_hoy  = fx["piso_hoy"]
    banda_serie = fx["banda_serie"]

    # Fallbacks si no se pudo obtener
    if spot      is None: spot      = 1398.0
    if mep       is None: mep       = spot * 1.025
    if ccl       is None: ccl       = spot * 1.06
    if techo_hoy is None: techo_hoy = spot * 1.18
    if piso_hoy  is None: piso_hoy  = spot * 0.60

    dist_techo = (techo_hoy / spot - 1) * 100

    def _fmt(v, dec=1):
        if v is None: return "—"
        return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # ── Futuros DUS ──────────────────────────────────────────────────
    # Si hay df_futuros de la API, usarlos; si no, construir de la curva
    dus_contracts = []
    if df_futuros is not None and not df_futuros.empty:
        for _, r in df_futuros.iterrows():
            # Soportar columnas de bymaapi (price, symbol, maturityDate, days_to_maturity)
            # y columnas normalizadas (Last Price, Código, Fecha Vto, Dias Vto)
            precio = None
            for col in ["price", "Last Price", "Close"]:
                v = r.get(col)
                if v is not None and not (isinstance(v, float) and np.isnan(v)) and float(v) > 0:
                    precio = float(v); break

            dias_raw = r.get("days_to_maturity") or r.get("Dias Vto") or r.get("dias_cal")
            mat_raw  = r.get("maturityDate")     or r.get("Fecha Vto")
            sym      = str(r.get("symbol") or r.get("Código") or "")

            if precio is None:
                continue
            # Filtrar solo minorista DLR (sin sufijo A) o DUS
            sym_upper = sym.upper()
            if not (sym_upper.startswith("DLR") or sym_upper.startswith("DUS")):
                continue
            if sym_upper.endswith("A"):  # mayorista — omitir
                continue
            try:
                # Fecha de vencimiento real
                if mat_raw is not None:
                    mat_date = pd.to_datetime(mat_raw).date()
                    dias_f   = (mat_date - hoy).days
                elif dias_raw is not None:
                    dias_f   = int(float(dias_raw))
                    mat_date = hoy + timedelta(days=dias_f)
                else:
                    continue
                if dias_f <= 0:
                    continue
                label  = mat_date.strftime("%b-%y").capitalize()
                tea    = (precio / spot) ** (365 / dias_f) - 1
                tna    = (precio / spot - 1) * 365 / dias_f
                deva_m = (precio / spot) ** (30  / dias_f) - 1
                dus_contracts.append({
                    "label":   label,
                    "precio":  round(precio, 1),
                    "dias":    dias_f,
                    "mat":     mat_date,
                    "tea":     round(tea   * 100, 4),
                    "tna":     round(tna   * 100, 4),
                    "deva_m":  round(deva_m * 100, 4),
                })
            except Exception:
                continue
        dus_contracts = sorted(dus_contracts, key=lambda x: x["dias"])[:10]

    # Fallback si no hay futuros
    if not dus_contracts:
        # Construir serie sintética con CPI T-2 proyectado (~3%)
        cpi_m = 0.03
        for i in range(1, 11):
            dias_f = i * 30
            mat    = hoy + timedelta(days=dias_f)
            precio = round(spot * (1 + cpi_m) ** i, 1)
            tea    = (precio / spot) ** (365 / dias_f) - 1
            tna    = (precio / spot - 1) * 365 / dias_f
            deva_m = (precio / spot) ** (30 / dias_f) - 1
            dus_contracts.append({
                "label":  mat.strftime("%b-%y").capitalize(),
                "precio": precio,
                "dias":   dias_f,
                "mat":    mat,
                "tea":    round(tea * 100, 4),
                "tna":    round(tna * 100, 4),
                "deva_m": round(deva_m * 100, 4),
            })

    # Calcular fwd mensual entre contratos
    for i, c in enumerate(dus_contracts):
        if i == 0:
            c["fwd_m"] = (c["precio"] / spot - 1) * 100
            c["tna_fwd"] = c["fwd_m"] / max(c["dias"], 1) * 30
            c["deva_acum"] = (c["precio"] / spot - 1) * 100
        else:
            prev = dus_contracts[i - 1]
            fwd = c["precio"] / prev["precio"] - 1
            dt  = max(c["dias"] - prev["dias"], 1)
            c["fwd_m"]    = round(fwd * 100, 4)
            c["tna_fwd"]  = round(fwd * 30 / dt * 100, 4)
            c["deva_acum"]= round((c["precio"] / spot - 1) * 100, 4)

    # ── Sintético por DUS ────────────────────────────────────────────
    sinteticos = []
    _used_tickers = set()
    for c in dus_contracts:
        bond = _assign_bond_to_dus(c["mat"], df_lecap, df_cer, tamar_tea, _used_tickers)
        if bond is None or c["dias"] == 0:
            sinteticos.append({
                "ticker": "—", "tipo": "", "tir_nom": None,
                "tcn_finish": None, "dif_ars": None, "sint_tea": None
            })
            continue
        _used_tickers.add(bond["ticker"])  # marcar como usado
        tir_nom = bond["tir_nom"] / 100.0
        tcn_finish = spot * (1 + tir_nom) ** (c["dias"] / 365)
        dif_ars = tcn_finish - c["precio"]
        sint_tea = (tcn_finish / c["precio"]) ** (365 / c["dias"]) - 1 if c["dias"] > 0 else 0
        sinteticos.append({
            "ticker":     bond["ticker"],
            "tipo":       bond["tipo"],
            "tir_nom":    round(bond["tir_nom"], 2),
            "tcn_finish": round(tcn_finish, 1),
            "dif_ars":    round(dif_ars, 1),
            "sint_tea":   round(sint_tea * 100, 2),
        })

    # ── Banda proyectada por DUS ─────────────────────────────────────
    bandas = []
    for c in dus_contracts:
        t, p = _get_banda_for_date(banda_serie, c["mat"])
        if t is None:
            t = techo_hoy * (1 + 0.03) ** (c["dias"] / 30)
            p = piso_hoy  * (1 - 0.01) ** (c["dias"] / 30)
        tcn_lib = sinteticos[dus_contracts.index(c)]["tcn_finish"]
        dist_rfx  = (t / c["precio"] - 1) * 100 if c["precio"] else None
        dist_lib  = (t / tcn_lib - 1) * 100 if tcn_lib else None
        spread    = (dist_rfx - dist_lib) if dist_rfx and dist_lib else None
        bandas.append({
            "techo": round(t, 1),
            "piso":  round(p, 1),
            "dist_rfx":  round(dist_rfx, 2) if dist_rfx else None,
            "dist_lib":  round(dist_lib, 2) if dist_lib else None,
            "spread":    round(spread, 2) if spread else None,
        })

    # ── Generar HTML de tablas ───────────────────────────────────────
    def _th(c): return f'<th>{c["label"]}<br><span style="font-weight:400;opacity:.7">{c["mat"].strftime("%b-%y")}</span></th>'
    headers = "".join(_th(c) for c in dus_contracts)

    def _td(v, fmt="{:.2f}%", color=None, bold=False):
        if v is None: return "<td>—</td>"
        try:
            text = fmt.format(v) if "{" in fmt else str(v)
        except Exception:
            text = str(v)
        style = ""
        if color: style += f"color:{color};"
        if bold:  style += "font-weight:600;"
        return f'<td style="{style}">{text}</td>'

    # Tabla A — DUS
    rows_a = [
        "<tr><td class='c6-lbl'>Precio (ARS/USD)</td>" +
        "".join(f"<td>{_fmt(c['precio'])}</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>Días calendario</td>" +
        "".join(f"<td>{c['dias']}</td>" for c in dus_contracts) + "</tr>",

        "<tr class='c6-row-hi'><td class='c6-lbl'>TIR Contrato (TEA)</td>" +
        "".join(f"<td>{c['tea']:.2f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>TNA Contrato</td>" +
        "".join(f"<td>{c['tna']:.2f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr class='c6-row-sep'><td class='c6-lbl'>Deva mensual implícita</td>" +
        "".join(f"<td>{c['deva_m']:.2f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>Fwd Contratos (mensual)</td>" +
        "".join(f"<td>{c['fwd_m']:.2f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>TNA FWD (norm. 30d)</td>" +
        "".join(f"<td>{c['tna_fwd']:.2f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr class='c6-row-sep'><td class='c6-lbl'>Deva acumulada</td>" +
        "".join(f"<td>{c['deva_acum']:.2f}%</td>" for c in dus_contracts) + "</tr>",
    ]

    # Tabla B — Sintéticos
    rows_b = [
        "<tr><td class='c6-lbl'>Bono ARS par</td>" +
        "".join(
            f'<td>{s["ticker"]} <span style="font-size:9px;color:#7a90a4">[{s["tipo"]}]</span></td>'
            if s["ticker"] != "—" else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",

        "<tr><td class='c6-lbl'>TIR Bono ARS (nominal)</td>" +
        "".join(
            f'<td style="color:#1a7a46;font-weight:600">{s["tir_nom"]:.2f}%</td>'
            if s["tir_nom"] else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",

        "<tr class='c6-row-hi'><td class='c6-lbl'>TCN finish</td>" +
        "".join(
            f'<td>{_fmt(s["tcn_finish"])}</td>' if s["tcn_finish"] else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",

        "<tr><td class='c6-lbl'>Dif vs ROFEX (ARS)</td>" +
        "".join(
            f'<td style="color:{"#1a7a46" if (s["dif_ars"] or 0)>=0 else "#c0392b"};font-weight:600">{_fmt(s["dif_ars"])}</td>'
            if s["dif_ars"] is not None else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",

        "<tr class='c6-row-hi'><td class='c6-lbl'>Sintético USDL (TEA)</td>" +
        "".join(
            f'<td style="color:{"#1a7a46" if (s["sint_tea"] or 0)>=0 else "#c0392b"};font-weight:600">{("+" if s["sint_tea"]>=0 else "")}{s["sint_tea"]:.2f}%</td>'
            if s["sint_tea"] is not None else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",
    ]

    # Tabla C — Bandas
    def _dist_td(v):
        if v is None: return "<td>—</td>"
        col = "#1a7a46" if v > 0 else "#c0392b"
        return f'<td style="color:{col}">{v:.1f}%</td>'

    def _spread_td(v):
        if v is None: return "<td>—</td>"
        col = "#1a7a46" if v > 1 else "#888"
        bold = "font-weight:600;" if v > 1 else ""
        return f'<td style="color:{col};{bold}">{v:.1f}%</td>'

    rows_c = [
        "<tr><td class='c6-lbl'>Precio ROFEX</td>" +
        "".join(f"<td>{_fmt(c['precio'])}</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>TCN libre (sin cobr.)</td>" +
        "".join(
            f"<td>{_fmt(s['tcn_finish'])}</td>" if s["tcn_finish"] else "<td>—</td>"
            for s in sinteticos
        ) + "</tr>",

        "<tr><td class='c6-lbl'>Techo banda (proy.)</td>" +
        "".join(f"<td>{_fmt(b['techo'])}</td>" for b in bandas) + "</tr>",

        "<tr><td class='c6-lbl'>Piso banda (proy.)</td>" +
        "".join(f"<td>{_fmt(b['piso'])}</td>" for b in bandas) + "</tr>",

        "<tr class='c6-row-hi'><td class='c6-lbl'>Dist. techo — ROFEX</td>" +
        "".join(_dist_td(b["dist_rfx"]) for b in bandas) + "</tr>",

        "<tr class='c6-row-hi'><td class='c6-lbl'>Dist. techo — carry libre</td>" +
        "".join(_dist_td(b["dist_lib"]) for b in bandas) + "</tr>",

        "<tr><td class='c6-lbl'>Spread dist. (rfx − libre)</td>" +
        "".join(_spread_td(b["spread"]) for b in bandas) + "</tr>",
    ]

    # ── Arrays para gráficos Chart.js ────────────────────────────────
    lbl_js    = str([c["label"] for c in dus_contracts])
    rfx_js    = str([c["precio"] for c in dus_contracts])
    libre_js  = str([s["tcn_finish"] for s in sinteticos])
    techo_js  = str([b["techo"] for b in bandas])
    piso_js   = str([b["piso"] for b in bandas])
    drfx_js   = str([b["dist_rfx"] for b in bandas])
    dlib_js   = str([b["dist_lib"] for b in bandas])
    dspr_js   = str([b["spread"] for b in bandas])
    spot_js   = str(round(spot, 1))
    y_min_js  = str(round(min(piso_js := [b["piso"] for b in bandas]) * 0.85, -2))
    y_max_js  = str(round(max(b["techo"] for b in bandas) * 1.08, -2))

    dist_spot_str = f"{dist_techo:.1f}%"
    techo_str = _fmt(techo_hoy)
    piso_str  = _fmt(piso_hoy)
    spot_str  = _fmt(spot)
    mep_str   = _fmt(mep)
    ccl_str   = _fmt(ccl)

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">05</div>
  <div class="slide-section-stripe" style="background:#1e6fba"></div>
  <div class="slide-section-titles">
    <h2>Cobertura ROFEX</h2>
    <div class="slide-section-sub">Curva DUS · Sintético tradicional · Distancia a banda cambiaria</div>
  </div>
</div>

<style>
.c6-fx-strip {{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;margin-top:6px}}
.c6-fx-card {{background:#f0f4f8;border:1px solid #d8e2ed;border-radius:7px;padding:9px 14px;flex:1;min-width:100px;box-shadow:0 1px 3px rgba(15,37,87,0.05)}}
.c6-fx-label {{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#5f7080;margin-bottom:3px;font-family:var(--font-title,'Barlow',Arial)}}
.c6-fx-val {{font-size:17px;font-weight:700;color:#0f2557;font-family:var(--font-title,'Barlow',Arial)}}
.c6-table-wrap {{overflow-x:auto;margin-bottom:4px}}
.c6-table {{border-collapse:collapse;font-size:11px;width:100%}}
.c6-table thead tr th {{background:#0f2557;color:white;padding:7px 10px;text-align:center;font-size:10px;font-weight:600;white-space:nowrap;font-family:var(--font-title,'Barlow',Arial)}}
.c6-lbl {{text-align:left!important;color:#5f7080;font-size:10.5px;background:#f7f9fc;border-right:1px solid #d8e2ed;min-width:170px;padding:5px 10px;font-family:var(--font-body,'Calibri',Arial)}}
.c6-table td {{padding:5px 10px;text-align:center;border-bottom:1px solid #eaeef2;white-space:nowrap;font-family:var(--font-body,'Calibri',Arial)}}
.c6-row-hi td {{background:#f0f5ff;font-weight:600}}
.c6-row-hi .c6-lbl {{background:#e8eef8;color:#0f2557}}
.c6-row-sep td {{border-top:1.5px solid #d8e2ed}}
</style>

<!-- Strip FX -->
<div class="c6-fx-strip">
  <div class="c6-fx-card">
    <div class="c6-fx-label">SPOT MULC</div>
    <div class="c6-fx-val">{spot_str}</div>
  </div>
  <div class="c6-fx-card">
    <div class="c6-fx-label">MEP</div>
    <div class="c6-fx-val">{mep_str}</div>
  </div>
  <div class="c6-fx-card">
    <div class="c6-fx-label">CCL</div>
    <div class="c6-fx-val">{ccl_str}</div>
  </div>
  <div class="c6-fx-card">
    <div class="c6-fx-label">Techo banda hoy</div>
    <div class="c6-fx-val" style="color:#1a7a46">{techo_str}</div>
  </div>
  <div class="c6-fx-card">
    <div class="c6-fx-label">Piso banda hoy</div>
    <div class="c6-fx-val" style="color:#b85a1a">{piso_str}</div>
  </div>
  <div class="c6-fx-card">
    <div class="c6-fx-label">Dist. SPOT al techo</div>
    <div class="c6-fx-val" style="color:#1a7a46">{dist_spot_str}</div>
  </div>
</div>

<!-- Panel A -->
<div class="panel-label">A — Curva de futuros ROFEX (DUS)</div>
<div class="metodo-box">
  <strong>Fórmulas.</strong>
  TIR TEA = (precio/SPOT)^(365/días)−1 &nbsp;·&nbsp;
  TNA = (precio/SPOT−1)×365/días &nbsp;·&nbsp;
  Fwd = precio<sub>i</sub>/precio<sub>i−1</sub>−1 &nbsp;·&nbsp;
  TNA FWD = fwd×30/días_tramo &nbsp;·&nbsp;
  Deva acum. = precio/SPOT−1.
</div>
<div class="c6-table-wrap"><table class="c6-table">
  <thead><tr><th class="c6-lbl"></th>{headers}</tr></thead>
  <tbody>{"".join(rows_a)}</tbody>
</table></div>

<!-- Panel B -->
<div class="panel-label" style="margin-top:20px">B — Sintético tradicional (bono ARS + cobertura ROFEX)</div>
<div class="metodo-box">
  <strong>Fórmulas.</strong>
  TCN finish = SPOT × (1+TIR_bono)^(días/365) &nbsp;·&nbsp;
  Sint. USDL = (TCN_finish/precio_ROFEX)^(365/días)−1 &nbsp;·&nbsp;
  Dif = TCN_finish−precio_ROFEX.
  <br>Para bonos <strong>CER</strong> se usa la TIR nominal bajo path CPI proyectado
  (<em>usar_cer_pago=True</em>). Para bonos <strong>TASA FIJA</strong> se usa la TIR TEA directamente.
  <br><em>Lógica de asignación:</em> se prioriza el BONCAP/LECAP más próximo al vencimiento del DUS.
  Si no hay tasa fija disponible en ese tramo, se usa el BONCER proyectado (versión j).
</div>
<div class="c6-table-wrap"><table class="c6-table">
  <thead><tr><th class="c6-lbl"></th>{headers}</tr></thead>
  <tbody>{"".join(rows_b)}</tbody>
</table></div>

<!-- Panel C -->
<div class="panel-label" style="margin-top:20px">C — Distancia a banda cambiaria</div>
<div class="metodo-box">
  <strong>Banda proyectada</strong> con datos oficiales del BCRA (serie completa diaria, deslizamiento T-2 por IPC).
  <br><strong>ROFEX:</strong> distancia del precio del futuro al techo de banda en esa fecha.
  <br><strong>Carry libre:</strong> TCN implícito del bono ARS sin cobertura = SPOT×(1+TIR_bono)^(días/365).
  Si este valor supera el techo, el carry sin cobertura ya sale de banda.
  <br><strong>Spread dist.</strong> = dist. ROFEX − dist. carry libre (positivo → ROFEX más lejos del techo).
</div>
<div class="c6-table-wrap"><table class="c6-table">
  <thead><tr><th class="c6-lbl"></th>{headers}</tr></thead>
  <tbody>{"".join(rows_c)}</tbody>
</table></div>

<!-- Gráficos -->
<div class="panel-label" style="margin-top:20px">Gráfico — banda, ROFEX y carry libre</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;font-size:12px;color:#5f7080">
  <span style="display:flex;align-items:center;gap:5px"><span style="width:28px;height:10px;background:#0f2557;opacity:.2;border-radius:0"></span>Banda cambiaria</span>
  <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:2px;background:#1e6fba"></span>Precio ROFEX</span>
  <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:2px;background:#b85a1a"></span>TCN carry libre</span>
  <span style="display:flex;align-items:center;gap:5px"><span style="width:20px;height:2px;background:#888;display:inline-block"></span>SPOT hoy</span>
</div>
<div style="position:relative;width:100%;height:280px"><canvas id="c5chart1"></canvas></div>

<div class="panel-label" style="margin-top:20px">Gráfico — distancia al techo y spread</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;font-size:12px;color:#5f7080">
  <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:2px;background:#1e6fba"></span>Dist. techo ROFEX</span>
  <span style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:2px;background:#b85a1a"></span>Dist. techo carry libre</span>
  <span style="display:flex;align-items:center;gap:5px"><span style="width:20px;height:2px;background:#1a7a46;display:inline-block"></span>Spread dist. (rfx−libre)</span>
</div>
<div style="position:relative;width:100%;height:200px"><canvas id="c5chart2"></canvas></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){{
  const lbl   = {lbl_js};
  const rfx   = {rfx_js};
  const libre = {libre_js};
  const techo = {techo_js};
  const piso  = {piso_js};
  const drfx  = {drfx_js};
  const dlib  = {dlib_js};
  const dspr  = {dspr_js};
  const spot  = {spot_js};
  const grid  = 'rgba(128,128,128,0.08)';
  const tick  = '#7a90a4';
  const FONT  = "'Barlow','Calibri',Arial,sans-serif";

  function initC5Charts() {{
    new Chart(document.getElementById('c5chart1'), {{
      type: 'line',
      data: {{ labels: lbl, datasets: [
        {{ label:'Techo', data:techo, borderColor:'#0f2557', backgroundColor:'rgba(15,37,87,0.06)',
           borderWidth:2, pointRadius:3, fill:'+1', tension:0.3 }},
        {{ label:'Piso',  data:piso,  borderColor:'#0f2557', backgroundColor:'rgba(15,37,87,0.06)',
           borderWidth:2, pointRadius:3, fill:false, tension:0.3 }},
        {{ label:'ROFEX', data:rfx,   borderColor:'#1e6fba', backgroundColor:'#1e6fba',
           borderWidth:2.5, pointRadius:5, fill:false, tension:0.2 }},
        {{ label:'Carry libre', data:libre, borderColor:'#b85a1a', backgroundColor:'#b85a1a',
           borderWidth:2.5, borderDash:[6,3], pointRadius:5, fill:false, tension:0.2 }},
        {{ label:'SPOT', data:Array(lbl.length).fill(spot), borderColor:'#888',
           borderWidth:1.5, borderDash:[3,3], pointRadius:0, fill:false }},
      ]}},
      options: {{ responsive:true, maintainAspectRatio:false,
        plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{
          label: c => ` ${{c.dataset.label}}: ${{Math.round(c.parsed.y).toLocaleString('es-AR')}}`
        }}}} }},
        scales: {{
          x: {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}}} }},
          y: {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}},
                 callback: v => v.toLocaleString('es-AR')}}, min:{y_min_js}, max:{y_max_js} }}
        }}
      }}
    }});

    new Chart(document.getElementById('c5chart2'), {{
      type: 'bar',
      data: {{ labels: lbl, datasets: [
        {{ label:'Dist. techo ROFEX',  data:drfx, backgroundColor:'#1e6fbabb', borderRadius:4 }},
        {{ label:'Dist. techo libre',  data:dlib, backgroundColor:'#b85a1abb', borderRadius:4 }},
        {{ label:'Spread dist.', data:dspr, type:'line', borderColor:'#1a7a46', backgroundColor:'#1a7a46',
           borderWidth:2, pointRadius:4, fill:false, tension:0.2, yAxisID:'y2' }},
      ]}},
      options: {{ responsive:true, maintainAspectRatio:false,
        plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{
          label: c => ` ${{c.dataset.label}}: ${{c.parsed.y != null ? c.parsed.y.toFixed(1) : '—'}}%`
        }}}} }},
        scales: {{
          x:  {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}, autoSkip:false}} }},
          y:  {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}, callback:v=>v.toFixed(0)+'%'}},
                 title:{{display:true,text:'Distancia al techo (%)',color:tick,font:{{size:10,family:FONT}}}} }},
          y2: {{ position:'right', grid:{{drawOnChartArea:false}},
                 ticks:{{color:'#1a7a46',font:{{size:10,family:FONT}},callback:v=>v.toFixed(1)+'%'}},
                 title:{{display:true,text:'Spread (%)',color:'#1a7a46',font:{{size:10,family:FONT}}}} }}
        }}
      }}
    }});
  }}

  // Inicializar cuando el slide 5 sea visible
  window.addEventListener('load', function() {{ setTimeout(initC5Charts, 80); }});
  document.addEventListener('DOMContentLoaded', function() {{
    var _orig = window.goTo;
    if (typeof _orig === 'function') {{
      window.goTo = function(idx) {{ _orig(idx); if(idx===5) setTimeout(initC5Charts, 80); }};
    }}
  }});
}})();
</script>
""".strip()




# =============================================================================
# CAP 7 — SNAPSHOT  (JSON embebido + tablas)
# CAP 6 — MOVIMIENTOS  (lee el JSON del HTML anterior)
# =============================================================================

import json as _json
import re  as _re
from pathlib import Path as _Path


# ── Helpers de parseo ────────────────────────────────────────────────────────

def _find_prev_html(template_path: str, hoy: date) -> tuple:
    """Busca el HTML de comité más reciente anterior a hoy en la misma carpeta."""
    folder = _Path(template_path).parent
    candidates = []
    for f in folder.glob("reporte_comite_????????.html"):
        try:
            fecha_str = f.stem.replace("reporte_comite_", "")
            if not fecha_str.isdigit() or len(fecha_str) != 8:
                continue
            fecha = date(int(fecha_str[:4]), int(fecha_str[4:6]), int(fecha_str[6:8]))
            if fecha < hoy:
                candidates.append((fecha, f))
        except Exception:
            continue
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return str(candidates[0][1]), candidates[0][0]


def _parse_snapshot(html_path: str) -> dict | None:
    """Extrae el JSON embebido del cap 7 de un HTML de reporte anterior."""
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = _re.search(
            r'<script type="application/json" id="reporte-snapshot">(.*?)</script>',
            content, _re.DOTALL
        )
        if not m:
            return None
        return _json.loads(m.group(1).strip())
    except Exception as e:
        print(f"[cap6] No se pudo parsear snapshot de {html_path}: {e}")
        return None


# ── Builders de datos para el snapshot ──────────────────────────────────────

def _bootstrap_infla(df_boncer: pd.DataFrame, df_boncap: pd.DataFrame) -> list:
    """CPI implícito mensual: (1+TIR_nom)/(1+TIR_real)^(1/12) - 1 por par."""
    pairs = []
    for _, rc in _clean_df(df_boncer).iterrows():
        dur_c = rc.get("Duration"); tir_r = _pct_float(rc.get("TIREA"))
        if dur_c is None or tir_r is None: continue
        best, best_d = None, 9999
        for _, rb in _clean_df(df_boncap).iterrows():
            dur_b = rb.get("Duration")
            if dur_b is None: continue
            d = abs(float(dur_b) - float(dur_c))
            if d < best_d: best_d = d; best = rb
        if best is None or best_d > 0.20: continue
        tir_n = _pct_float(best.get("TIREA"))
        if tir_n is None: continue
        try:
            pi_be = ((1 + tir_n) / (1 + tir_r)) ** (1/12) - 1
        except Exception:
            continue
        pairs.append({
            "ticker":       str(rc["Código"]),
            "boncap_target": str(best["Código"]),
            "tir_real":     round(tir_r, 6),
            "tir_nom":      round(tir_n, 6),
            "pi_be":        round(pi_be, 6),
            "duration":     round(float(dur_c), 4),
        })
    return sorted(pairs, key=lambda x: x["duration"])


def _build_snapshot_json(
    df_lecap, df_cer, df_tamar, df_dual,
    tamar_tna, tamar_tea,
    fx_data: dict,
    rofex_data: list,
    hoy: date,
) -> dict:
    """Construye el dict completo del snapshot para embeber en el cap 7."""
    # Guards de seguridad
    tamar_tea = tamar_tea if tamar_tea is not None else 0.2973
    tamar_tna = tamar_tna if tamar_tna is not None else tamar_tea * 0.885
    def _rows_boncap(df):
        out = []
        for _, r in _clean_df(df).iterrows():
            tir = _pct_float(r.get("TIREA"))
            dur = r.get("Duration")
            precio = r.get("Last Price") or r.get("Last") or r.get("Close")
            if tir is None or dur is None or precio is None: continue
            try: dur_f = float(dur); precio_f = float(precio)
            except: continue
            if not np.isfinite(dur_f) or not np.isfinite(precio_f): continue
            out.append({
                "ticker":   str(r["Código"]),
                "precio":   round(precio_f, 4),
                "tir_tea":  round(tir, 8),
                "duration": round(dur_f, 6),
            })
        return sorted(out, key=lambda x: x["duration"])

    def _rows_boncer(df):
        out = []
        for _, r in _clean_df(df).iterrows():
            tir = _pct_float(r.get("TIREA"))
            dur = r.get("Duration")
            precio = r.get("Last Price") or r.get("Last") or r.get("Close")
            if tir is None or dur is None or precio is None: continue
            try: dur_f = float(dur); precio_f = float(precio)
            except: continue
            if not np.isfinite(dur_f) or not np.isfinite(precio_f): continue
            out.append({
                "ticker":   str(r["Código"]),
                "precio":   round(precio_f, 4),
                "tir_real": round(tir, 8),
                "duration": round(dur_f, 6),
            })
        return sorted(out, key=lambda x: x["duration"])

    def _rows_bontam(df, tamar_tea):
        out = []
        for _, r in _clean_df(df).iterrows():
            tir = _pct_float(r.get("TIREA"))
            dur = r.get("Duration")
            precio = r.get("Last Price") or r.get("Last") or r.get("Close")
            if tir is None or dur is None or precio is None: continue
            try: dur_f = float(dur); precio_f = float(precio)
            except: continue
            if not np.isfinite(dur_f) or not np.isfinite(precio_f): continue
            spread = round(tir - tamar_tea, 8) if tamar_tea is not None else None
            out.append({
                "ticker":   str(r["Código"]),
                "precio":   round(precio_f, 4),
                "tir_tea":  round(tir, 8),
                "spread":   spread,
                "duration": round(dur_f, 6),
            })
        return sorted(out, key=lambda x: x["duration"])

    df_bontam_all = _combine_bontam(df_tamar, df_dual)
    boot = _bootstrap_infla(df_cer, df_lecap)

    return {
        "version":         4,
        "fecha_reporte":   hoy.strftime("%Y%m%d"),
        "fecha_valuacion": hoy.strftime("%Y-%m-%d"),
        "macro": {
            "tamar_tna": round(tamar_tna, 8) if tamar_tna is not None else None,
            "tamar_tea": round(tamar_tea, 8) if tamar_tea is not None else None,
        },
        "fx": {
            "spot":       fx_data.get("spot"),
            "mep":        fx_data.get("mep"),
            "ccl":        fx_data.get("ccl"),
            "techo_hoy":  fx_data.get("techo_hoy"),
            "piso_hoy":   fx_data.get("piso_hoy"),
            "dist_techo": round((fx_data.get("techo_hoy",0) / (fx_data.get("spot") or 1) - 1)*100, 4) if (fx_data.get("spot") and fx_data.get("techo_hoy")) else None,
        },
        "boncap":          _rows_boncap(df_lecap),
        "boncer":          _rows_boncer(df_cer),
        "bontam":          _rows_bontam(df_bontam_all, tamar_tea),
        "bootstrap_infla": boot,
        "rofex":           rofex_data or [],
    }


# ── CAP 7 HTML ──────────────────────────────────────────────────────────────

def _build_cap7_html(snap: dict, tamar_tna: float, tamar_tea: float) -> str:
    """Genera el HTML del cap 7 con tablas de datos y el JSON embebido."""

    fecha_val = snap.get("fecha_valuacion", "—")
    tamar_str = f"{tamar_tna*100:.3f}% TNA · {tamar_tea*100:.2f}% TEA"

    def _tbl_boncap(rows):
        html = ""
        for r in rows:
            tir_pct = r["tir_tea"] * 100
            cls = "td-pos" if tir_pct >= 0 else "td-neg"
            html += (f'<tr><td class="td-ticker">{r["ticker"]}</td>'
                     f'<td class="td-val">{r["precio"]:.4f}</td>'
                     f'<td class="td-val {cls}">{tir_pct:.2f}%</td>'
                     f'<td class="td-val">{r["duration"]:.3f}</td></tr>')
        return html

    def _tbl_boncer(rows):
        html = ""
        for r in rows:
            tir_pct = r["tir_real"] * 100
            cls = "td-pos" if tir_pct >= 0 else "td-neg"
            html += (f'<tr><td class="td-ticker">{r["ticker"]}</td>'
                     f'<td class="td-val">{r["precio"]:.4f}</td>'
                     f'<td class="td-val {cls}">{tir_pct:.2f}%</td>'
                     f'<td class="td-val">{r["duration"]:.3f}</td></tr>')
        return html

    def _tbl_bontam(rows):
        html = ""
        for r in rows:
            spr_pct = r["spread"] * 100
            cls = "td-pos" if spr_pct >= 0 else "td-neg"
            sign = "+" if spr_pct >= 0 else ""
            html += (f'<tr><td class="td-ticker">{r["ticker"]}</td>'
                     f'<td class="td-val">{r["precio"]:.4f}</td>'
                     f'<td class="td-val">{r["tir_tea"]*100:.2f}%</td>'
                     f'<td class="td-val {cls}">{sign}{spr_pct:.2f}%</td>'
                     f'<td class="td-val">{r["duration"]:.3f}</td></tr>')
        return html

    def _tbl_bootstrap(rows):
        html = ""
        for r in rows:
            pi_pct = r["pi_be"] * 100
            html += (f'<tr><td class="td-ticker">{r["ticker"]}</td>'
                     f'<td>{r["boncap_target"]}</td>'
                     f'<td class="td-val">{r["tir_real"]*100:.2f}%</td>'
                     f'<td class="td-val">{r["tir_nom"]*100:.2f}%</td>'
                     f'<td class="td-val td-pos">{pi_pct:.2f}%</td></tr>')
        return html

    snap_json = _json.dumps(snap, ensure_ascii=False, indent=2)

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">07</div>
  <div class="slide-section-stripe" style="background:#1e6fba"></div>
  <div class="slide-section-titles">
    <h2>Snapshot de Datos</h2>
    <div class="slide-section-sub">Precios · TIRs · Inflación implícita · JSON embebido para comparativas</div>
  </div>
</div>

<div class="metodo-box">
  <strong>Uso.</strong> Este capítulo centraliza todos los datos del comité y embebe un JSON
  (<code>id="reporte-snapshot"</code>) que el próximo reporte usa para calcular movimientos.
  Fecha de valuación: <strong>{fecha_val}</strong> · TAMAR: <strong>{tamar_str}</strong>
</div>

<div class="panel-label">Macro del día</div>
<div class="tables-row" style="margin-bottom:18px">
  <div class="mini-table-wrap" style="flex:0 0 auto">
    <table class="mini-table">
      <thead><tr><th>Variable</th><th>Valor</th></tr></thead>
      <tbody>
        <tr><td>TAMAR</td><td class="td-val">{tamar_str}</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="panel-label">BONCAP — Tasa fija</div>
<div style="overflow-x:auto"><table class="mini-table">
  <thead><tr><th>Ticker</th><th>Precio</th><th>TIR TEA</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_boncap(snap.get("boncap", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">BONCER — Ajuste CER</div>
<div style="overflow-x:auto"><table class="mini-table">
  <thead><tr><th>Ticker</th><th>Precio</th><th>T. Real</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_boncer(snap.get("boncer", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">BONTAM — Tasa variable</div>
<div style="overflow-x:auto"><table class="mini-table">
  <thead><tr><th>Ticker</th><th>Precio</th><th>TIR TEA</th><th>Spread</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_bontam(snap.get("bontam", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">Inflación implícita break-even</div>
<div style="overflow-x:auto"><table class="mini-table">
  <thead><tr><th>BONCER</th><th>BONCAP ref.</th><th>T. Real</th><th>TIR nom.</th><th>CPI BE mens.</th></tr></thead>
  <tbody>{_tbl_bootstrap(snap.get("bootstrap_infla", []))}</tbody>
</table></div>

<script type="application/json" id="reporte-snapshot">
{snap_json}
</script>
""".strip()


# ── CAP 6 HTML ──────────────────────────────────────────────────────────────

def _build_cap6_html(snap_hoy: dict, snap_ant: dict | None, fecha_ant: date | None) -> str:
    """Genera el HTML del cap 6 comparando snapshot hoy vs HTML anterior."""

    fecha_ant_str = fecha_ant.strftime("%d/%m/%Y") if fecha_ant else "—"

    # ── Helpers ──────────────────────────────────────────────────────────
    def _by_ticker(rows: list) -> dict:
        return {r["ticker"]: r for r in (rows or [])}

    def _sign_color(v, good_neg=False):
        """good_neg=True: negativo es bueno (TIR baja → precio sube)"""
        if v is None or not np.isfinite(float(v)): return "#888"
        if good_neg: return "#1a7a46" if v < 0 else "#b85a1a"
        return "#1a7a46" if v >= 0 else "#b85a1a"

    def _fmt(v, dec=1, pct=False, bps=False):
        if v is None or not np.isfinite(float(v)): return "—"
        if bps:  return f"{'+' if v>=0 else ''}{v:.1f} bps"
        if pct:  return f"{'+' if v>=0 else ''}{v:.2f}%"
        return f"{v:,.{dec}f}"

    # ── Calcular deltas por curva ─────────────────────────────────────
    ant_bc = _by_ticker(snap_ant.get("boncap", []) if snap_ant else [])
    ant_bn = _by_ticker(snap_ant.get("boncer", []) if snap_ant else [])
    ant_bt = _by_ticker(snap_ant.get("bontam", []) if snap_ant else [])

    def _deltas_boncap():
        rows = []
        for r in snap_hoy.get("boncap", []):
            a = ant_bc.get(r["ticker"])
            delta_tir = (r["tir_tea"] - a["tir_tea"]) * 10000 if a else None
            tr = (r["precio"] / a["precio"] - 1) * 100 if a else None
            rows.append({"ticker": r["ticker"], "tir": r["tir_tea"]*100,
                         "precio": r["precio"], "dur": r["duration"],
                         "delta_tir": delta_tir, "tr": tr})
        return rows

    def _deltas_boncer():
        rows = []
        for r in snap_hoy.get("boncer", []):
            a = ant_bn.get(r["ticker"])
            delta_tir = (r["tir_real"] - a["tir_real"]) * 10000 if a else None
            tr = (r["precio"] / a["precio"] - 1) * 100 if a else None
            rows.append({"ticker": r["ticker"], "tir": r["tir_real"]*100,
                         "precio": r["precio"], "dur": r["duration"],
                         "delta_tir": delta_tir, "tr": tr})
        return rows

    def _deltas_bontam():
        rows = []
        for r in snap_hoy.get("bontam", []):
            a = ant_bt.get(r["ticker"])
            delta_spr = (r["spread"] - a["spread"]) * 10000 if a else None
            tr = (r["precio"] / a["precio"] - 1) * 100 if a else None
            rows.append({"ticker": r["ticker"], "spread": r["spread"]*100,
                         "tir": r["tir_tea"]*100, "precio": r["precio"],
                         "dur": r["duration"], "delta_spr": delta_spr, "tr": tr})
        return rows

    bc_rows = _deltas_boncap()
    bn_rows = _deltas_boncer()
    bt_rows = _deltas_bontam()

    # ── Cards resumen ──────────────────────────────────────────────────
    def _avg_delta(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None and np.isfinite(float(r[key]))]
        return np.mean(vals) if vals else None

    def _count_dir(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None and np.isfinite(float(r[key]))]
        return sum(1 for v in vals if v > 0), sum(1 for v in vals if v < 0)

    avg_bc = _avg_delta(bc_rows, "delta_tir")
    avg_bn = _avg_delta(bn_rows, "delta_tir")
    avg_bt = _avg_delta(bt_rows, "delta_spr")
    sub_bc, baj_bc = _count_dir(bc_rows, "delta_tir")
    sub_bn, baj_bn = _count_dir(bn_rows, "delta_tir")
    sub_bt, baj_bt = _count_dir(bt_rows, "delta_spr")

    mac_hoy = snap_hoy.get("macro", {})
    mac_ant = snap_ant.get("macro", {}) if snap_ant else {}
    tamar_hoy = mac_hoy.get("tamar_tna")
    tamar_ant = mac_ant.get("tamar_tna")
    delta_tamar = (tamar_hoy - tamar_ant)*10000 if tamar_hoy and tamar_ant else None

    def _card(title, color, stat_bps, sub, pills):
        sc = _sign_color(stat_bps, good_neg=True)
        return f"""<div class="c7-card" style="border-top:3px solid {color}">
  <div class="c7-card-title" style="color:{color}">{title}</div>
  <div class="c7-card-stat" style="color:{sc}">{_fmt(stat_bps, bps=True)}</div>
  <div class="c7-card-sub">{sub}</div>
  <div class="c7-card-pills">{pills}</div>
</div>"""

    def _pills(sub, baj):
        return (f'<span class="c7-pill" style="background:#b85a1a22;color:#b85a1a">↑ {sub} subieron</span>'
                f'<span class="c7-pill" style="background:#1a7a4622;color:#1a7a46">↓ {baj} bajaron</span>')

    tamar_pills = ""
    if tamar_hoy and tamar_ant:
        tamar_pills = (f'<span class="c7-pill" style="background:#eee;color:#666">ant: {tamar_ant*100:.3f}%</span>'
                      f'<span class="c7-pill" style="background:#eee;color:#666">act: {tamar_hoy*100:.3f}%</span>')

    cards_html = (
        _card("TAMAR",  "#0f2557", delta_tamar, "variación TNA", tamar_pills) +
        _card("BONCAP", "#1e6fba", avg_bc,      "promedio Δ TIR", _pills(sub_bc, baj_bc)) +
        _card("BONCER", "#1a7a46", avg_bn,      "promedio Δ TIR real", _pills(sub_bn, baj_bn)) +
        _card("BONTAM", "#b85a1a", avg_bt,      "promedio Δ spread", _pills(sub_bt, baj_bt))
    )

    # ── Strip FX ──────────────────────────────────────────────────────
    fx_h = snap_hoy.get("fx", {})
    fx_a = snap_ant.get("fx", {}) if snap_ant else {}

    def _fx_card(label, key, inv=False, pct=False):
        v_h = fx_h.get(key); v_a = fx_a.get(key)
        delta = (v_h - v_a) if (v_h is not None and v_a is not None) else None
        col = _sign_color(delta, good_neg=inv)
        val_str = f"{v_h:,.1f}" if v_h else "—"
        d_str = (_fmt(delta, dec=1) if not pct else _fmt(delta, dec=2)) if delta is not None else "—"
        sign = "+" if (delta or 0) >= 0 else ""
        d_str = f"{sign}{d_str}" if delta is not None else "—"
        return (f'<div class="c7-fx-card"><div class="c7-fx-label">{label}</div>'
                f'<div class="c7-fx-val">{val_str}</div>'
                f'<div class="c7-fx-delta" style="color:{col}">{d_str}</div></div>')

    fx_strip = ('<div class="c7-fx-strip">' +
        _fx_card("SPOT MULC",        "spot",      inv=True) +
        _fx_card("MEP",              "mep",       inv=True) +
        _fx_card("CCL",              "ccl",       inv=True) +
        _fx_card("Techo banda",      "techo_hoy", inv=False) +
        _fx_card("Piso banda",       "piso_hoy",  inv=False) +
        _fx_card("Dist. al techo",   "dist_techo",inv=False, pct=True) +
        '</div>')

    # ── Datos para gráficos JS ─────────────────────────────────────────
    def _js(rows, key):
        filt = [r for r in rows if r.get(key) is not None and np.isfinite(float(r[key]))]
        return (str([r["ticker"] for r in filt]),
                str([round(float(r[key]), 1) for r in filt]))

    lbl_bc, dat_bc = _js(bc_rows, "delta_tir")
    lbl_bn, dat_bn = _js(bn_rows, "delta_tir")
    lbl_bt, dat_bt = _js(bt_rows, "delta_spr")

    # Total return — todos juntos ordenados
    tr_all = []
    for rows, col_c, col_d in [
        (bc_rows, "#1e6fba", "#0f4a80"),
        (bn_rows, "#1a7a46", "#0f5530"),
        (bt_rows, "#b85a1a", "#7a3a0e"),
    ]:
        for r in rows:
            tr = r.get("tr")
            if tr is None or not np.isfinite(float(tr)): continue
            tr_all.append({"t": r["ticker"], "v": round(float(tr), 2), "c": col_c, "ch": col_d})
    tr_all.sort(key=lambda x: x["v"], reverse=True)
    tr_json = _json.dumps(tr_all)

    # ── Bootstrap inflación Δ ──────────────────────────────────────────
    boot_hoy = {r["ticker"]: r for r in snap_hoy.get("bootstrap_infla", [])}
    boot_ant = {r["ticker"]: r for r in (snap_ant.get("bootstrap_infla", []) if snap_ant else [])}

    boot_rows = ""
    for ticker, r in boot_hoy.items():
        pi_h = r["pi_be"] * 100
        r_a  = boot_ant.get(ticker)
        pi_a = r_a["pi_be"] * 100 if r_a else None
        delta_pi = pi_h - pi_a if pi_a is not None else None
        col = "#888" if delta_pi is None or abs(delta_pi) < 0.05 else ("#b85a1a" if delta_pi > 0 else "#1a7a46")
        boot_rows += (
            f'<tr>'
            f'<td><span class="td-ticker">{ticker}</span></td>'
            f'<td>{r["boncap_target"]}</td>'
            f'<td class="td-val">{pi_h:.2f}%</td>'
            f'<td class="td-val">{f"{pi_a:.2f}%" if pi_a else "—"}</td>'
            f'<td style="color:{col};font-weight:600">'
            f'{f"{chr(43) if delta_pi>=0 else ""}{delta_pi:.2f} pp" if delta_pi is not None else "—"}'
            f'</td></tr>'
        )

    # ── Tabla FX detallada ─────────────────────────────────────────────
    def _fx_row(label, key, dec=1, inv=False):
        v_h = fx_h.get(key); v_a = fx_a.get(key)
        if v_h is None: return ""
        delta = (v_h - v_a) if v_a is not None else None
        col = _sign_color(delta, good_neg=inv) if delta is not None else "#888"
        sign = "+" if (delta or 0) >= 0 else ""
        d_str = f"{sign}{delta:,.{dec}f}" if delta is not None else "—"
        return (f'<tr><td>{label}</td>'
                f'<td>{f"{v_a:,.{dec}f}" if v_a else "—"}</td>'
                f'<td>{v_h:,.{dec}f}</td>'
                f'<td style="color:{col};font-weight:600">{d_str}</td></tr>')

    fx_tabla = (
        _fx_row("SPOT MULC",     "spot",      dec=1, inv=True) +
        _fx_row("MEP",           "mep",       dec=1, inv=True) +
        _fx_row("CCL",           "ccl",       dec=1, inv=True) +
        _fx_row("Techo banda",   "techo_hoy", dec=1, inv=False) +
        _fx_row("Piso banda",    "piso_hoy",  dec=1, inv=False) +
        _fx_row("Dist. al techo (pp)", "dist_techo", dec=2, inv=False)
    )

    return f"""
<div class="slide-section-header">
  <div class="slide-section-num">06</div>
  <div class="slide-section-stripe" style="background:#1e6fba"></div>
  <div class="slide-section-titles">
    <h2>Movimientos entre Comités</h2>
    <div class="slide-section-sub">Δ TIR en bps · Total return · FX y Banda · Inflación implícita · vs {fecha_ant_str}</div>
  </div>
</div>

<div class="metodo-box">
  <strong>Comparación vs {fecha_ant_str}.</strong>
  Δ positivo en TIR = precio baja (naranja). Verde = precio sube.
  <strong>Retorno</strong> = precio actual / precio comité anterior − 1.
  Fuente: JSON embebido del reporte anterior.
</div>

<style>
.c7-cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;margin-top:6px}}
.c7-card{{background:#fff;border:1px solid #d8e2ed;border-radius:7px;padding:14px 16px;box-shadow:0 1px 4px rgba(15,37,87,0.05)}}
.c7-card-title{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-family:var(--font-title,'Barlow',Arial)}}
.c7-card-stat{{font-size:22px;font-weight:700;color:#0f2557;margin-bottom:2px;line-height:1;font-family:var(--font-title,'Barlow',Arial)}}
.c7-card-sub{{font-size:9px;color:#5f7080;margin-bottom:8px}}
.c7-card-pills{{display:flex;gap:5px;flex-wrap:wrap}}
.c7-pill{{font-size:9px;font-weight:600;padding:2px 7px;border-radius:10px}}
.c7-fx-strip{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}
.c7-fx-card{{background:#f0f4f8;border:1px solid #d8e2ed;border-radius:7px;padding:9px 14px;flex:1;min-width:100px}}
.c7-fx-label{{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#5f7080;margin-bottom:2px;font-family:var(--font-title,'Barlow',Arial)}}
.c7-fx-val{{font-size:16px;font-weight:700;color:#0f2557;font-family:var(--font-title,'Barlow',Arial)}}
.c7-fx-delta{{font-size:11px;font-weight:600;margin-top:2px}}
</style>

<div class="c7-cards">{cards_html}</div>
{fx_strip}

<div class="panel-label" style="margin-top:4px">Δ TIR EN BPS POR BONO</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
  <div>
    <div style="font-size:10px;font-weight:700;color:#1e6fba;margin-bottom:4px;font-family:var(--font-title,'Barlow',Arial)">BONCAP</div>
    <div style="position:relative;width:100%;height:180px"><canvas id="c7cc"></canvas></div>
  </div>
  <div>
    <div style="font-size:10px;font-weight:700;color:#1a7a46;margin-bottom:4px;font-family:var(--font-title,'Barlow',Arial)">BONCER — Tasa real</div>
    <div style="position:relative;width:100%;height:180px"><canvas id="c7ce"></canvas></div>
  </div>
  <div>
    <div style="font-size:10px;font-weight:700;color:#b85a1a;margin-bottom:4px;font-family:var(--font-title,'Barlow',Arial)">BONTAM — Δ Spread</div>
    <div style="position:relative;width:100%;height:180px"><canvas id="c7cb"></canvas></div>
  </div>
</div>

<div class="panel-label">TOTAL RETURN · precio actual / precio comité anterior − 1</div>
<div style="display:flex;gap:14px;margin-bottom:8px;font-size:11px;color:#5f7080">
  <span><span style="width:10px;height:10px;border-radius:2px;background:#1e6fba;display:inline-block;margin-right:4px"></span>BONCAP</span>
  <span><span style="width:10px;height:10px;border-radius:2px;background:#1a7a46;display:inline-block;margin-right:4px"></span>BONCER</span>
  <span><span style="width:10px;height:10px;border-radius:2px;background:#b85a1a;display:inline-block;margin-right:4px"></span>BONTAM</span>
</div>
<div style="position:relative;width:100%;height:260px;margin-bottom:20px"><canvas id="c7tr"></canvas></div>

<div style="display:grid;grid-template-columns:auto 1fr;gap:24px;align-items:start">
  <div>
    <div class="panel-label">FX y Banda Cambiaria</div>
    <table class="mini-table">
      <thead><tr><th>Variable</th><th>Anterior</th><th>Actual</th><th>Δ</th></tr></thead>
      <tbody>{fx_tabla}</tbody>
    </table>
  </div>
  <div>
    <div class="panel-label">Inflación implícita break-even (CPI bootstrap)</div>
    <table class="mini-table">
      <thead><tr><th>BONCER</th><th>BONCAP ref.</th><th>CPI BE act.</th><th>CPI BE ant.</th><th>Δ</th></tr></thead>
      <tbody>{boot_rows}</tbody>
    </table>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function(){{
  var grid='rgba(128,128,128,0.08)', tick='#7a90a4';
  var FONT="'Barlow','Calibri',Arial,sans-serif";

  function barChart(id,labels,data,color){{
    var ctx=document.getElementById(id); if(!ctx)return;
    new Chart(ctx,{{type:'bar',
      data:{{labels:labels,datasets:[{{data:data,
        backgroundColor:data.map(function(v){{return v>=0?color+'cc':color+'88';}}),
        borderRadius:3,borderWidth:0}}]}},
      options:{{responsive:true,maintainAspectRatio:false,
        plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
          label:function(c){{return ' '+(c.parsed.y>=0?'+':'')+c.parsed.y.toFixed(1)+' bps';}}
        }},backgroundColor:'#0f2557',titleColor:'#fff',bodyColor:'rgba(255,255,255,.8)',padding:8,cornerRadius:4}}}},
        scales:{{
          x:{{grid:{{color:grid}},ticks:{{color:tick,font:{{size:9,family:FONT}},maxRotation:45}}}},
          y:{{grid:{{color:grid}},ticks:{{color:tick,font:{{size:9,family:FONT}},
            callback:function(v){{return (v>=0?'+':'')+v+' bps';}}}},border:{{dash:[3,3]}}}}
        }}
      }}
    }});
  }}

  function initC6(){{
    barChart('c7cc', {lbl_bc}, {dat_bc}, '#1e6fba');
    barChart('c7ce', {lbl_bn}, {dat_bn}, '#1a7a46');
    barChart('c7cb', {lbl_bt}, {dat_bt}, '#b85a1a');

    var trData={tr_json};
    var ctx=document.getElementById('c7tr');
    if(ctx && trData.length){{
      new Chart(ctx,{{type:'bar',
        data:{{labels:trData.map(function(d){{return d.t;}}),
          datasets:[{{data:trData.map(function(d){{return d.v;}}),
            backgroundColor:trData.map(function(d){{return d.c;}}),
            hoverBackgroundColor:trData.map(function(d){{return d.ch;}}),
            borderRadius:3,borderWidth:0}}]}},
        options:{{responsive:true,maintainAspectRatio:false,
          plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{
            label:function(c){{return ' '+(c.parsed.y>=0?'+':'')+c.parsed.y.toFixed(2)+'%';}}
          }},backgroundColor:'#0f2557',titleColor:'#fff',bodyColor:'rgba(255,255,255,.8)',padding:8,cornerRadius:4}}}},
          scales:{{
            x:{{grid:{{color:grid}},ticks:{{color:tick,font:{{size:9,family:FONT}},maxRotation:45,autoSkip:false}}}},
            y:{{grid:{{color:grid}},ticks:{{color:tick,font:{{size:9,family:FONT}},
              callback:function(v){{return (v>=0?'+':'')+v.toFixed(1)+'%';}}}},border:{{dash:[3,3]}}}}
          }}
        }}
      }});
    }}
  }}

  window.addEventListener('load', function(){{ setTimeout(initC6, 80); }});
  document.addEventListener('DOMContentLoaded', function(){{
    var _orig=window.goTo;
    if(typeof _orig==='function'){{
      window.goTo=function(idx){{ _orig(idx); if(idx===6) setTimeout(initC6,80); }};
    }}
  }});
}})();
</script>
""".strip()



# =============================================================================
# INJECT HELPERS
# =============================================================================

# =============================================================================
# DELTA CSS THEME — se inyecta en el <head> del template
# =============================================================================

_DELTA_CSS = """
/* ═══════════════════════════════════════════════════════
   DELTA ASSET MANAGEMENT — Tema visual
   Paleta: azul marino #0f2557 · acento #1e6fba
   Tipografía: Barlow (títulos/nros) + Calibri (cuerpo)
═══════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;500;600;700&display=swap');

:root {
  --navy:    #0f2557;
  --blue:    #1e6fba;
  --blue2:   #2980c4;
  --green:   #1a7a46;
  --orange:  #b85a1a;
  --amber:   #e8a020;
  --light:   #f0f4f8;
  --border:  #d8e2ed;
  --text:    #1a2535;
  --muted:   #5f7080;
  --sidebar: 230px;
  --font-title: 'Barlow', 'Calibri', Arial, sans-serif;
  --font-body:  'Calibri', 'Gill Sans', Arial, sans-serif;
}
html, body { font-family: var(--font-body) !important; }

/* ── Sidebar ── */
.sidebar { background: linear-gradient(180deg,#0a1b42 0%,#0f2557 65%,#132d68 100%) !important; }
.sidebar-brand { border-bottom: 1px solid rgba(255,255,255,0.09) !important; }
.sidebar-brand-tag { font-family: var(--font-title) !important; letter-spacing:3px; color:rgba(255,255,255,0.4) !important; }
.sidebar-brand-title { font-family: var(--font-title) !important; font-size:14px; font-weight:600; }
.sidebar-brand-date { color:rgba(255,255,255,0.35) !important; }
.nav-item.active { background:rgba(30,111,186,0.20) !important; border-left-color:#4ea8e8 !important; }
.nav-item:hover { background:rgba(255,255,255,0.04) !important; }
.nav-num { font-family: var(--font-title) !important; font-weight:700; color:rgba(255,255,255,0.28) !important; }
.nav-item.active .nav-num { color:#4ea8e8 !important; }
.nav-label { font-family: var(--font-body) !important; }
.nav-item.active .nav-label { color:rgba(255,255,255,0.95) !important; }
.sidebar-footer { color:rgba(255,255,255,0.22) !important; }

/* ── Progress bar ── */
.progress-fill { background: linear-gradient(90deg,#1e6fba,#4ea8e8) !important; }

/* ── Portada ── */
.slide-cover { background: linear-gradient(135deg,#091840 0%,#0f2557 55%,#1a3878 100%) !important; }
.cover-h1 { font-family: var(--font-title) !important; font-weight:700 !important; }
.cover-tag { font-family: var(--font-title) !important; }

/* ── Encabezado de sección ── */
.slide-section-header { border-bottom:2px solid #0f2557 !important; }
.slide-section-num {
  font-family: var(--font-title) !important;
  font-size: 52px !important;
  font-weight: 700 !important;
  color: #c5d4e8 !important;
  letter-spacing: -3px;
  line-height: 1;
}
.slide-section-titles h2 {
  font-family: var(--font-title) !important;
  font-size: 20px !important;
  font-weight: 600 !important;
  color: #0f2557 !important;
  letter-spacing: -0.3px;
}
.slide-section-sub { font-family: var(--font-body) !important; color:#5f7080 !important; }

/* ── Metodología ── */
.metodo-box { border-left:3px solid #1e6fba !important; background:#f0f4f8 !important; }

/* ── Chart cards ── */
.chart-card { border:1px solid #d8e2ed !important; border-radius:7px !important; box-shadow:0 1px 6px rgba(15,37,87,0.06) !important; }
.chart-card-header { background:#f7f9fc !important; border-bottom:1px solid #d8e2ed !important; }
.chart-title { font-family:var(--font-title) !important; font-weight:600 !important; color:#0f2557 !important; font-size:12px; }
.chart-sub { font-family:var(--font-body) !important; color:#7a90a4 !important; }

/* ── Mini tablas ── */
.mini-table thead th { background:#e8eef5 !important; color:#5f7080 !important; font-family:var(--font-title) !important; font-size:9.5px; }
.mini-table-title { font-family:var(--font-title) !important; font-size:11px !important; font-weight:700 !important; }

/* ── Footer ── */
.slide-footer { background:#f0f4f8 !important; border-top:1px solid #d8e2ed !important; }
.slide-footer-left, .slide-footer-right { color:#7a90a4 !important; font-family:var(--font-body) !important; }
.slide-nav-btn { border-color:#d8e2ed !important; color:#0f2557 !important; font-family:var(--font-body) !important; border-radius:5px !important; }
.slide-nav-btn:hover { background:#e8eef5 !important; }

/* ── Colores positivo/negativo ── */
.td-pos { color:#1a7a46 !important; }
.td-neg { color:#c0392b !important; }

/* ── Heatmap ── */
.hm-c1{background:#0d6b35 !important;} .hm-c2{background:#52a87a !important;}
.hm-c3{background:#f5c842 !important; color:#333 !important;}
.hm-c4{background:#e07a30 !important;} .hm-c5{background:#c0392b !important;}

/* ── Panel labels ── */
.panel-label { font-family:var(--font-title) !important; }

/* ── Comments ── */
.comments-label { font-family:var(--font-title) !important; color:#0f2557 !important; }
"""


def _inject_css(html, css):
    return html.replace("</style>", css + "\n</style>", 1)



def _replace_cap1(html, cap1_inner):
    return _replace_capN(html, 'slide-1', cap1_inner)

def _replace_cap1_OLD(html, cap1_inner):
    s1 = html.find('id="slide-1"')
    s2 = html.find('id="slide-2"')
    if s1 == -1 or s2 == -1:
        print("[generar_reporte] ⚠️  No se encontró slide-1 en el template.")
        return html
    segment = html[s1:s2]
    p_open  = segment.find('<div class="slide-chapter-inner">')
    p_close = segment.rfind('</div>\n    <div class="slide-footer">')
    if p_open == -1 or p_close == -1:
        print("[generar_reporte] ⚠️  No se encontró slide-chapter-inner.")
        return html
    open_tag = '<div class="slide-chapter-inner">'
    before = html[:s1 + p_open + len(open_tag)]
    after  = html[s1 + p_close:]
    return before + "\n\n" + cap1_inner + "\n\n    " + after



def _unify_navigation(html: str) -> str:
    """
    Reemplaza el goTo() original del template con una versión unificada
    que maneja tanto slides numerados (slide-N) como fd-slides (fd-slide-X).
    Elimina la necesidad de parchar goTo en cadena desde múltiples módulos.
    """
    old_goto = """function goTo(idx) {
    if (idx < 0 || idx >= total) return;
    document.getElementById('slide-' + current).classList.remove('active');
    document.getElementById('nav-'   + current).classList.remove('active');
    current = idx;
    document.getElementById('slide-' + current).classList.add('active');
    document.getElementById('nav-'   + current).classList.add('active');"""

    new_goto = """// ── Navegación unificada (slides numerados + fd-slides) ──
  var _currentFdId = null;   // id del fd-slide activo, o null
  function _hideAll() {
    document.querySelectorAll('.slide-chapter, .slide-cover').forEach(function(s) {
      s.classList.remove('active');
    });
    document.querySelectorAll('.nav-item').forEach(function(n) {
      n.classList.remove('active');
    });
  }
  function goToId(targetId) {
    _hideAll();
    var target = document.getElementById(targetId);
    if (!target) return;
    target.classList.add('active');
    _currentFdId = targetId.startsWith('fd-slide-') ? targetId : null;
    // Nav item
    var navId = targetId.replace('fd-slide-', 'fd-nav-').replace(/^slide-/, 'nav-');
    var navEl = document.getElementById(navId);
    if (navEl) navEl.classList.add('active');
    // Topbar mobile
    var tEl = document.getElementById('mobile-title');
    var sEl = document.getElementById('mobile-slide');
    if (tEl && slideTitles) tEl.textContent = slideTitles[parseInt(targetId.replace(/[^0-9]/g,''))] || 'Fondos';
    if (sEl) sEl.textContent = targetId;
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 60);
    setTimeout(closeSidebar, 80);
  }
  function goTo(idx) {
    if (idx < 0 || idx >= total) return;
    _hideAll();
    _currentFdId = null;
    current = idx;
    var slideEl = document.getElementById('slide-' + current);
    var navEl   = document.getElementById('nav-'   + current);
    if (slideEl) slideEl.classList.add('active');
    if (navEl)   navEl.classList.add('active');"""

    if old_goto in html:
        html = html.replace(old_goto, new_goto, 1)
    return html



def _apply_delta_theme_to_root(html: str) -> str:
    """Reemplaza el :root y @import del template con los valores Delta."""
    import re
    # Reemplazar @import de Google Fonts original
    html = html.replace(
        "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@300;400;500;600&display=swap');",
        "@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;500;600;700&family=Calibri&display=swap');"
    )
    # Reemplazar el bloque :root con los valores Delta
    old_root = """:root {
  --navy:    #1a3a5c;
  --blue:    #1a5fa8;
  --green:   #1a7a46;
  --orange:  #a84c1a;
  --amber:   #e8a020;
  --light:   #f4f6f9;
  --border:  #dde3ec;
  --text:    #2c3e50;
  --muted:   #6b7c93;
  --sidebar: 230px;
}"""
    new_root = """:root {
  --navy:    #0f2557;
  --blue:    #1e6fba;
  --green:   #1a7a46;
  --orange:  #b85a1a;
  --amber:   #e8a020;
  --light:   #f0f4f8;
  --border:  #d8e2ed;
  --text:    #1a2535;
  --muted:   #5f7080;
  --sidebar: 230px;
  --font-title: 'Barlow', 'Calibri', Arial, sans-serif;
  --font-body:  'Calibri', 'Gill Sans', Arial, sans-serif;
}"""
    html = html.replace(old_root, new_root, 1)
    # Reemplazar font-family del body
    html = html.replace(
        "font-family: 'Source Sans 3', sans-serif;",
        "font-family: var(--font-body, 'Calibri', Arial, sans-serif);"
    )
    # Reemplazar Playfair Display references
    html = html.replace("'Playfair Display', serif", "var(--font-title, 'Barlow', Arial, sans-serif)")
    # Reemplazar progress bar color
    html = html.replace(
        "background: linear-gradient(90deg, var(--blue), #5b9bd5);",
        "background: linear-gradient(90deg, #1e6fba, #4ea8e8);"
    )
    # Active nav highlight
    html = html.replace("border-left-color: #5b9bd5;", "border-left-color: #4ea8e8;")
    html = html.replace("color: #5b9bd5;", "color: #4ea8e8;")
    return html


def _replace_capN(html: str, slide_id: str, cap_inner: str) -> str:
    """Reemplaza el contenido de cualquier slide por su ID (slide-1, slide-3, etc.)"""
    sN     = html.find(f'id="{slide_id}"')
    sNext  = html.find(f'id="slide-{int(slide_id.split("-")[1])+1}"')
    if sN == -1:
        print(f"[generar_reporte] No se encontro {slide_id}")
        return html
    if sNext == -1:
        sNext = len(html)
    segment  = html[sN:sNext]
    p_open   = segment.find('<div class="slide-chapter-inner">')
    p_close  = segment.rfind('</div>\n    <div class="slide-footer">')
    if p_open == -1 or p_close == -1:
        return html
    open_tag = '<div class="slide-chapter-inner">'
    before   = html[:sN + p_open + len(open_tag)]
    after    = html[sN + p_close:]
    return before + "\n\n" + cap_inner + "\n\n    " + after


def _replace_fecha(html, fecha_str, fecha_yyyymmdd):
    html = re.sub(r'30 de March de 2026', fecha_str, html)
    html = re.sub(r'20260330', fecha_yyyymmdd, html)
    html = re.sub(r'<title>.*?</title>',
                  f'<title>Comité de Inversiones — Renta Fija — {fecha_str}</title>', html)
    return html


def _replace_tamar_texts(html, tamar_tna, tamar_tea):
    tna_str = f"{tamar_tna*100:.3f}% TNA"
    tea_str = f"{tamar_tea*100:.3f}% TEA"
    html = re.sub(r'TAMAR TEA \(\d+[\.,]\d+%\)',
                  f'TAMAR TEA ({tamar_tea*100:.2f}%)', html)
    html = re.sub(r'última TAMAR TEA \(\d+[\.,]\d+%\)',
                  f'última TAMAR TEA ({tamar_tea*100:.2f}%)', html)
    html = re.sub(r'<span>\d+[\.,]\d+%\s*TNA\s*—\s*\d+[\.,]\d+%\s*TEA</span>',
                  f'<span>{tna_str} — {tea_str}</span>', html)
    html = re.sub(r'TAMAR última</label><span>[^<]+</span>',
                  f'TAMAR última</label><span>{tna_str} — {tea_str}</span>', html)
    return html


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def generar_reporte(
    username:      str   = None,
    password:      str   = None,
    plazo:         str   = "24hs",
    template_path: str   = None,
    output_path:   str   = None,
    fecha_reporte: date  = None,
    tamar_tna:     float = None,
    tamar_tea:     float = None,
    rf_detalle_path: str        = None,
    df_futuros:      "pd.DataFrame" = None,
) -> str:
    """
    Genera el reporte HTML del comité de inversiones.

    Uso:
        from generar_reporte import generar_reporte
        generar_reporte(
            username      = "delta_api",
            password      = "D3lt41210*-*",
            template_path = r"C:\\...\\Comite\\reporte_comite_base.html",
        )
    """
    username = username or os.getenv("OMS_USER", "")
    password = password or os.getenv("OMS_PASS", "")
    if not username or not password:
        raise ValueError("Faltan credenciales.")

    hoy = fecha_reporte or date.today()
    fecha_str      = _fmt_fecha(hoy)
    fecha_yyyymmdd = hoy.strftime("%Y%m%d")

    if template_path is None:
        candidates = sorted(Path(".").glob("reporte_comite_*.html"), reverse=True)
        if not candidates:
            raise FileNotFoundError("No se encontró template HTML.")
        template_path = str(candidates[0])

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    print(f"[generar_reporte] Template: {template_path}")

    print("[generar_reporte] Trayendo datos...")
    df_lecap = _app.load_curve_last_table(username, password, "lecap",    plazo)
    df_cer   = _app.load_curve_last_table(username, password, "cer",      plazo)
    df_tamar = _app.load_curve_last_table(username, password, "tamar",    plazo)
    df_dual  = _app.load_curve_last_table(username, password, "dualtamar", plazo)
    _n_dual = len(df_dual[df_dual["Código"].astype(str).str.endswith("v")]) if df_dual is not None and not df_dual.empty and "Código" in df_dual.columns else 0
    print(f"  BONCAP: {len(_clean_df(df_lecap))} | "
          f"BONCER: {len(_clean_df(df_cer))} | "
          f"BONTAM: {len(_clean_df(df_tamar))} + {_n_dual} duales")

    if tamar_tna is None or tamar_tea is None:
        tna_auto, tea_auto = _get_tamar_rates()
        tamar_tna = tamar_tna or tna_auto
        tamar_tea = tamar_tea or tea_auto

    # Fallback 1: leer del DataFrame de TAMAR que ya bajamos
    if tamar_tea is None and df_tamar is not None and not df_tamar.empty:
        for col in ["TIREA", "TEA", "TIR"]:
            if col in df_tamar.columns:
                vals = df_tamar[col].apply(_pct_float).dropna()
                if not vals.empty:
                    tamar_tea = float(vals.mean())
                    break

    # Fallback 2: intentar leer de rentafija.inputs con distintas claves
    if tamar_tea is None:
        try:
            import rentafija
            for key in ["TAMAR", "tamar", "TM20", "tm20"]:
                df_t = rentafija.inputs.get(key)
                if df_t is not None and not df_t.empty:
                    col = df_t.columns[0]
                    val = float(df_t[col].dropna().iloc[-1])
                    # Si el valor viene en % (ej. 26.3) convertir a decimal
                    tamar_tea = val / 100.0 if val > 1 else val
                    break
        except Exception:
            pass

    # Fallback 3: valor por defecto razonable
    if tamar_tea is None:
        tamar_tea = 0.2973
        print("  ⚠ TAMAR no detectada — usando valor por defecto 29.73%")
    if tamar_tna is None:
        tamar_tna = tamar_tea * 0.885  # aproximación TNA ≈ TEA * 0.885

    print(f"  TAMAR: TNA={tamar_tna*100:.3f}%  TEA={tamar_tea*100:.3f}%")

    html = _apply_delta_theme_to_root(html)
    html = _unify_navigation(html)
    html = _inject_css(html, _CAP1_CSS)
    html = _replace_cap1(html, _build_cap1_html(
        df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna))
    html = _replace_capN(html, "slide-3", _build_cap3_html(
        df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna))
    html = _replace_capN(html, "slide-4", _build_cap4_html(
        df_lecap, df_cer, hoy))
    # Futuros: bymaapi global → parámetro → fallback snapshot (snapshot aún no cargado aquí)
    _df_futuros = _get_futuros_auto(df_futuros, None, hoy)
    html = _replace_capN(html, "slide-5", _build_cap5_html(
        df_lecap, df_cer, df_tamar, df_dual, _df_futuros, tamar_tea, hoy))

    # ── Caps 6 y 7: snapshot + movimientos ───────────────────────────
    _fx_data  = _fetch_fx_data()
    _snap_hoy = _build_snapshot_json(
        df_lecap, df_cer, df_tamar, df_dual,
        tamar_tna, tamar_tea, _fx_data, [], hoy
    )

    # Buscar HTML del comité anterior y parsear su snapshot
    _prev_path, _prev_fecha = _find_prev_html(template_path, hoy)
    _snap_ant = _parse_snapshot(_prev_path) if _prev_path else None
    if _snap_ant:
        print(f"  Comité anterior: {_prev_fecha.strftime('%d/%m/%Y')} ({_prev_path})")
    else:
        print("  Sin comité anterior — cap 6 sin deltas")

    html = _replace_capN(html, "slide-6", _build_cap6_html(_snap_hoy, _snap_ant, _prev_fecha))
    html = _replace_capN(html, "slide-7", _build_cap7_html(_snap_hoy, tamar_tna, tamar_tea))

    html = _replace_fecha(html, fecha_str, fecha_yyyymmdd)
    html = _replace_tamar_texts(html, tamar_tna, tamar_tea)

    if output_path is None:
        output_dir  = Path(template_path).parent
        output_path = str(output_dir / f"reporte_comite_{fecha_yyyymmdd}.html")

    # ── Embeber slides de fondos entre cap 6 y cap 7 ────────────────
    if rf_detalle_path and Path(rf_detalle_path).exists():
        try:
            from generar_fondos import generar_fondos_html, generar_fondos_pptx
            fondos_html = generar_fondos_html(rf_detalle_path)
            # Insertar entre slide-6 y slide-7
            marker7 = '<div class="slide-chapter" id="slide-7">'
            if marker7 in html:
                html = html.replace(marker7, fondos_html + '\n  ' + marker7, 1)
            else:
                # Fallback: antes del cierre del body
                html = html.replace('</body>', fondos_html + '\n</body>', 1)
            print(f"[generar_reporte] ✓ Slides de fondos embebidas (entre cap 6 y cap 7)")
            # Inyectar nav-items en el sidebar (después del nav-7)
            from generar_fondos import generar_fondos_nav_items
            nav_items = generar_fondos_nav_items()
            sidebar_marker = '</div>\n    <div class="sidebar-footer">'
            if sidebar_marker in html:
                html = html.replace(
                    sidebar_marker,
                    '\n' + nav_items + '\n    </div>\n    <div class="sidebar-footer">',
                    1
                )
                # También agregar CSS para que los fd-nav-items respondan al goToId()
                css_fd_nav = """<style>
.fd-nav-item { opacity: 0.75; }
.fd-nav-item.active { background: rgba(255,255,255,0.10) !important;
                      border-left-color: #b85a1a !important; opacity: 1; }
.fd-nav-item.active .nav-num  { color: #b85a1a !important; }
.fd-nav-item.active .nav-label { color: rgba(255,255,255,0.92) !important; font-weight:500; }
</style>"""
                html = html.replace('</head>', css_fd_nav + '\n</head>', 1)
            # PPTX separado
            pptx_out = str(Path(output_path).with_suffix('.pptx'))
            generar_fondos_pptx(rf_detalle_path, pptx_out, None)
            print(f"[generar_reporte] ✓ PPTX fondos: {pptx_out}")
        except Exception as e:
            import traceback
            print(f"[generar_reporte] ⚠ Fondos (omitido): {e}")
            traceback.print_exc()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[generar_reporte] ✓ Guardado: {output_path}")
    return output_path
