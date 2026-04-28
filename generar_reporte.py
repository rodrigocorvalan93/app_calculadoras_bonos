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


/* Posicionamiento de labels con líneas conector */
function resolveOverlaps(labels) {
  var H = 10, W_PX = 6.5;
  var changed = true, MAX_ITER = 30, iter = 0;
  while (changed && iter++ < MAX_ITER) {
    changed = false;
    for (var i = 0; i < labels.length; i++) {
      for (var j = i+1; j < labels.length; j++) {
        var a = labels[i], b = labels[j];
        var aw = a.text.length * W_PX;
        var bw = b.text.length * W_PX;
        var ax1 = a.align==="left" ? a.x : a.x - aw;
        var bx1 = b.align==="left" ? b.x : b.x - bw;
        var ox = ax1 < bx1 + bw && ax1 + aw > bx1;
        var oy = Math.abs(a.y - b.y) < H;
        if (ox && oy) {
          var mid = (a.y + b.y) / 2;
          if (a.ptY <= b.ptY) { a.y = mid - H*0.55; b.y = mid + H*0.55; }
          else                 { a.y = mid + H*0.55; b.y = mid - H*0.55; }
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
    var dist=Math.sqrt(Math.pow(lb.x-lb.ptX,2)+Math.pow(lb.y-lb.ptY,2));
    if(dist>18){
      ctx.save(); ctx.strokeStyle=color; ctx.lineWidth=0.7;
      ctx.globalAlpha=0.4; ctx.setLineDash([2,2]);
      ctx.beginPath(); ctx.moveTo(lb.ptX,lb.ptY);
      ctx.lineTo(lb.align==="left"?lb.x-2:lb.x+2,lb.y-1);
      ctx.stroke(); ctx.restore();
    }
    ctx.textAlign=lb.align;
    ctx.strokeStyle="white"; ctx.lineWidth=2.5; ctx.lineJoin="round";
    ctx.strokeText(lb.text,lb.x,lb.y);
    ctx.fillStyle=color; ctx.fillText(lb.text,lb.x,lb.y);
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
                cells += f'<td class="hm-cell {cls}" data-col="{tj}">{sign}{val:.1f}%</td>'
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


def _build_cap2_html(
    df_lecap:  pd.DataFrame,
    df_cer:    pd.DataFrame,
    df_tamar:  pd.DataFrame,
    df_dual:   pd.DataFrame,
    tamar_tea: float,
    tamar_tna: float,
    hoy:       date,
) -> str:
    """
    Cap 2 -- Tasas Implicitas.
    Panel A: TAMAR impl vs BONCAP (dos barras por bono: impl TNA + TIR BONCAP TNA).
    Panel B: TAMAR impl vs BONCER (dos barras por bono: impl TNA + TIR nominal BONCER TNA).

    Logica:
      spread_tna  = TNA(tir_bontam_tea) - tamar_tna_actual
      tamar_impl_tna_A = TNA(tir_boncap_tea) - spread_tna
      tamar_impl_tna_B = TNA(tir_nominal_boncer) - spread_tna

    TIR nominal BONCER = (1 + tir_real_tea) * cpi_acum^(1/dur) - 1  [TEA]
    donde cpi_acum = producto de inflaciones mensuales proyectadas en el horizonte del bono.
    """
    def _TEA_to_TNA(tea):
        return ((1 + tea) ** (1/365) - 1) * 365

    # Obtener proyeccion de inflacion mensual desde indices.py
    # El dict tiene formato {"Apr-26": 2.7, "May-26": 1.9, ...} (en %)
    try:
        import indices as _indices
        _proy = _indices.proyeccion_inflacion_mensual   # dict {"Apr-26": float, ...}
    except Exception:
        _proy = {}

    def _cpi_tea_para_dur(dur_years):
        """
        Calcula la CPI TEA equivalente para un horizonte de 'dur_years' anyos
        usando las inflaciones mensuales proyectadas.
        """
        if not _proy:
            return (1.030) ** 12 - 1  # fallback 3% mensual
        from datetime import date as _date
        import calendar as _cal
        # Armar lista de (anyo, mes, inflacion) ordenada
        month_map = {
            "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
            "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12
        }
        entries = []
        for k, v in _proy.items():
            parts = k.split("-")
            if len(parts) == 2:
                m = month_map.get(parts[0])
                y = int("20" + parts[1]) if len(parts[1]) == 2 else int(parts[1])
                if m:
                    entries.append((y, m, float(v)/100.0))
        entries.sort()

        # Tomar los primeros dur_years*12 meses (redondeado)
        n_months = max(1, round(dur_years * 12))
        # Anadiar meses de hoy en adelante
        result = []
        cur_y, cur_m = hoy.year, hoy.month
        for _ in range(n_months):
            # Buscar en entries
            val = next((v for (y,m,v) in entries if y==cur_y and m==cur_m), 0.015)
            result.append(val)
            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1

        if not result:
            return (1.030)**12 - 1

        cpi_acum = 1.0
        for c in result:
            cpi_acum *= (1 + c)
        # Anualizar: cpi_acum cubre dur_years anyos -> TEA
        cpi_tea = cpi_acum ** (1/max(dur_years, 1/12)) - 1
        return cpi_tea

    # Comparables BONCAP y BONCER
    BONCAP_COMP = {
        "TTJ26": ["T30J6"],
        "M31G6": ["S31G6"],
        "TTS26": ["S30S6"],
        "TTD26": ["T15E7"],
        "TMF27": ["T15E7", "T30A7"],
    }
    BONCER_COMP = {
        "TTJ26": ["TZX26"],
        "M31G6": ["X31L6", "X30S6"],
        "TTS26": ["X30S6"],
        "TTD26": ["TZXD6"],
        "TMF27": ["TZXM7"],
    }

    # Dicts de TIRs TEA
    def _tir_dict(df):
        d = {}
        for _, r in _clean_df(df).iterrows():
            t = str(r.get("Codigo", r.get("Codigo", ""))).strip()
            for col in df.columns:
                if col.lower() in ("codigo", "c\u00f3digo"):
                    v = r.get(col)
                    if v:
                        t = str(v).strip()
                        break
            tir = _pct_float(r.get("TIREA"))
            if t and tir is not None:
                d[t] = tir
                d[t.replace(" CI", "")] = tir
        return d

    lecap_tirs = _tir_dict(df_lecap)
    cer_tirs   = _tir_dict(df_cer)

    # Duraciones de los BONCER para el calculo de CPI path
    cer_durs = {}
    for _, r in _clean_df(df_cer).iterrows():
        for col in df_cer.columns:
            if col.lower() in ("codigo", "c\u00f3digo"):
                v = r.get(col)
                if v:
                    t = str(v).strip().replace(" CI", "")
                    try:
                        cer_durs[t] = float(r.get("Duration"))
                    except Exception:
                        pass
                    break

    df_all = _combine_bontam(df_tamar, df_dual)

    resultados = []
    for _, r in _clean_df(df_all).iterrows():
        ticker_raw = ""
        for col in df_all.columns:
            if col.lower() in ("codigo", "c\u00f3digo"):
                v = r.get(col)
                if v:
                    ticker_raw = str(v).strip()
                    break
        if not ticker_raw:
            continue

        ticker = ticker_raw.replace(" CI", "").strip().rstrip("v").strip()

        boncap_comps = BONCAP_COMP.get(ticker)
        if not boncap_comps:
            continue

        tir_bontam_tea = _pct_float(r.get("TIREA"))
        if tir_bontam_tea is None:
            continue
        try:
            dur_f = float(r.get("Duration", 0))
        except Exception:
            dur_f = 0.0

        tir_bontam_tna = _TEA_to_TNA(tir_bontam_tea)
        spread_tna = tir_bontam_tna - tamar_tna

        # Panel A: vs BONCAP
        comp_tna_a = None
        comp_tirs_a = [lecap_tirs[c] for c in boncap_comps if c in lecap_tirs]
        if comp_tirs_a:
            comp_tea_a = sum(comp_tirs_a) / len(comp_tirs_a)
            comp_tna_a = _TEA_to_TNA(comp_tea_a)
            impl_tna_a = comp_tna_a - spread_tna
        else:
            impl_tna_a = None

        # Panel B: vs BONCER usando CPI path de indices.py
        impl_tna_b = None
        comp_tna_b = None
        boncer_comps = BONCER_COMP.get(ticker, [])
        comp_tirs_b = [cer_tirs[c] for c in boncer_comps if c in cer_tirs]
        if comp_tirs_b:
            # Duracion del BONCER comparable (promedio si varios)
            dur_cer = sum(cer_durs.get(c, dur_f) for c in boncer_comps if c in cer_durs)
            n_cer = sum(1 for c in boncer_comps if c in cer_durs)
            dur_cer = dur_cer / n_cer if n_cer else dur_f
            dur_cer = max(dur_cer, 1/12)

            tir_real_tea_avg = sum(comp_tirs_b) / len(comp_tirs_b)
            cpi_tea = _cpi_tea_para_dur(dur_cer)
            # TIR nominal TEA del BONCER = (1 + real) * (1 + cpi_anual) - 1
            tir_nominal_tea = (1 + tir_real_tea_avg) * (1 + cpi_tea) - 1
            comp_tna_b   = _TEA_to_TNA(tir_nominal_tea)
            impl_tna_b   = comp_tna_b - spread_tna

        resultados.append({
            "ticker":     ticker,
            "dur":        dur_f,
            "spread_tna": spread_tna,
            "comp_a":     "/".join(boncap_comps),
            "comp_tna_a": comp_tna_a,
            "impl_tna_a": impl_tna_a,
            "comp_b":     "/".join(boncer_comps) if boncer_comps else "",
            "comp_tna_b": comp_tna_b,
            "impl_tna_b": impl_tna_b,
        })

    # Ordenar por duration y deduplicar
    resultados.sort(key=lambda x: x["dur"])
    seen, deduped = set(), []
    for r in resultados:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            deduped.append(r)
    resultados = deduped

    if not resultados:
        return """<div style="padding:40px;color:#888;text-align:center">Sin datos BONTAM.</div>"""

    def _safe(v, mult=100, dec=1):
        return round(v * mult, dec) if v is not None else 0

    tickers_js  = json.dumps([r["ticker"]    for r in resultados])
    impl_a_js   = json.dumps([_safe(r["impl_tna_a"]) for r in resultados])
    comp_a_js   = json.dumps([_safe(r["comp_tna_a"]) for r in resultados])
    impl_b_js   = json.dumps([_safe(r["impl_tna_b"]) for r in resultados])
    comp_b_js   = json.dumps([_safe(r["comp_tna_b"]) for r in resultados])
    tamar_tna_js = round(tamar_tna * 100, 2)

    # Describe CPI path used
    cpi_desc = "path CPI indices.py" if _proy else "fallback 3% mensual"
    # Get the first few monthly values for the subtitle
    if _proy:
        month_map2 = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                      "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        near_months = []
        cur_y, cur_m = hoy.year, hoy.month
        for _ in range(4):
            key_abbr = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                        7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}[cur_m]
            key = f"{key_abbr}-{str(cur_y)[2:]}"
            if key in _proy:
                near_months.append(f"{key}: {_proy[key]:.1f}%")
            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1
        cpi_desc = "CPI path: " + " | ".join(near_months) + " | ..."

    hoy_str      = hoy.strftime("%d/%m/%Y")
    tamar_tna_str = f"{tamar_tna*100:.2f}%"

    return f"""
<style>
.c2-wrap{{display:grid;grid-template-columns:1fr 1fr;gap:14px;height:100%;padding:0}}
.c2-panel{{background:white;border:1px solid #d0d9e4;border-radius:6px;
           overflow:hidden;display:flex;flex-direction:column}}
.c2-ph{{background:#0f2557;color:white;font-size:11px;font-weight:700;
        text-transform:uppercase;letter-spacing:.5px;padding:6px 14px;flex-shrink:0}}
.c2-pb{{flex:1;padding:8px 12px;overflow:hidden;display:flex;flex-direction:column;min-height:0}}
.c2-sub{{font-size:10px;color:#5f7080;flex-shrink:0;margin-bottom:4px}}
.c2-chart{{flex:1;min-height:0;position:relative}}
.c2-chart canvas{{position:absolute;top:0;left:0;width:100%;height:100%}}
.c2-nota{{font-size:9.5px;color:#7a90a4;flex-shrink:0;margin-top:4px;
          border-top:1px solid #edf0f3;padding-top:4px;line-height:1.35}}
</style>

<div class="c2-wrap">

  <div class="c2-panel">
    <div class="c2-ph">A &mdash; TAMAR Implicita vs BONCAP</div>
    <div class="c2-pb">
      <div class="c2-sub">
        TNA &nbsp;|&nbsp; Linea = TAMAR hoy ({tamar_tna_str}) &nbsp;|&nbsp; {hoy_str}
      </div>
      <div class="c2-chart"><canvas id="c2cvA"></canvas></div>
      <div class="c2-nota">
        <strong>Barras oscuras:</strong> TAMAR implicita TNA breakeven.
        <strong>Barras claras:</strong> TIR TNA del BONCAP comparable.
        Spread = TNA(BONTAM) &minus; TAMAR actual TNA. TAMAR impl = TIR BONCAP TNA &minus; Spread.
      </div>
    </div>
  </div>

  <div class="c2-panel">
    <div class="c2-ph">B &mdash; TAMAR Implicita vs BONCER</div>
    <div class="c2-pb">
      <div class="c2-sub">
        TNA &nbsp;|&nbsp; {cpi_desc}
      </div>
      <div class="c2-chart"><canvas id="c2cvB"></canvas></div>
      <div class="c2-nota">
        <strong>Barras oscuras:</strong> TAMAR implicita TNA.
        <strong>Barras claras:</strong> TIR nominal TNA del BONCER bajo path CPI proyectado.
        TIR nominal = (1 + TIR real) &times; CPI acumulado por duracion &minus; 1.
      </div>
    </div>
  </div>

</div>

<script>
(function(){{
  var tickers  = {tickers_js};
  var implA    = {impl_a_js};
  var compA    = {comp_a_js};
  var implB    = {impl_b_js};
  var compB    = {comp_b_js};
  var tamarAct = {tamar_tna_js};
  var DARK_A   = '#0f2557';
  var LIGHT_A  = '#6b93c4';
  var DARK_B   = '#1a5c2e';
  var LIGHT_B  = '#82c9a0';

  function drawDouble(cid, dark, light, cd, cl) {{
    var cv = document.getElementById(cid);
    if (!cv) return;
    var par = cv.parentElement;
    var W = par.clientWidth, H = par.clientHeight;
    if (!W||W<10||!H||H<10) {{
      setTimeout(function(){{drawDouble(cid,dark,light,cd,cl);}},150); return;
    }}
    var dpr = window.devicePixelRatio||1;
    cv.width=W*dpr; cv.height=H*dpr;
    cv.style.width=W+'px'; cv.style.height=H+'px';
    var ctx = cv.getContext('2d');
    ctx.scale(dpr,dpr);
    ctx.clearRect(0,0,W,H);

    var n  = tickers.length;
    var ML = 36, MR = 8, MT = 18, MB = 34;
    var PW = W-ML-MR, PH = H-MT-MB;

    var all = dark.concat(light).concat([tamarAct]);
    var maxV = Math.max.apply(null,all)*1.12;
    function sy(v){{return MT+PH-(v/maxV)*PH;}}

    // Grid
    for(var g=0;g<=5;g++){{
      var gv=maxV*g/5, gy=sy(gv);
      ctx.strokeStyle='#eaeef2';ctx.lineWidth=0.7;
      ctx.beginPath();ctx.moveTo(ML,gy);ctx.lineTo(W-MR,gy);ctx.stroke();
      ctx.font='8px Barlow,Calibri,Arial';
      ctx.fillStyle='#8090a0';ctx.textAlign='right';ctx.textBaseline='middle';
      ctx.fillText(gv.toFixed(0)+'%',ML-3,gy);
    }}

    // TAMAR line
    var ty=sy(tamarAct);
    ctx.strokeStyle='#c45000';ctx.lineWidth=1.6;ctx.setLineDash([5,3]);
    ctx.beginPath();ctx.moveTo(ML,ty);ctx.lineTo(W-MR,ty);ctx.stroke();
    ctx.setLineDash([]);
    ctx.font='bold 8px Barlow,Calibri,Arial';ctx.fillStyle='#c45000';
    ctx.textAlign='left';ctx.textBaseline='bottom';
    ctx.fillText('TAMAR '+tamarAct.toFixed(1)+'%',ML+4,ty-2);

    // Bars
    var grpW=PW/n, bw=Math.min(grpW*0.33,26), gap=Math.min(grpW*0.05,4);
    for(var i=0;i<n;i++){{
      var gx=ML+i*grpW+(grpW-2*bw-gap)/2;

      // dark bar
      var h1=Math.abs(sy(0)-sy(dark[i])), y1=sy(dark[i]);
      ctx.fillStyle=cd; ctx.fillRect(gx,y1,bw,h1);
      ctx.font='bold 8.5px Barlow,Calibri,Arial';
      ctx.fillStyle=cd;ctx.textAlign='center';ctx.textBaseline='bottom';
      ctx.fillText(dark[i].toFixed(1)+'%',gx+bw/2,y1-2);

      // light bar
      var h2=Math.abs(sy(0)-sy(light[i])), y2=sy(light[i]);
      ctx.fillStyle=cl; ctx.fillRect(gx+bw+gap,y2,bw,h2);
      ctx.font='bold 8.5px Barlow,Calibri,Arial';
      ctx.fillStyle='#444';ctx.textAlign='center';ctx.textBaseline='bottom';
      ctx.fillText(light[i].toFixed(1)+'%',gx+bw+gap+bw/2,y2-2);

      // ticker
      ctx.font='8.5px Barlow,Calibri,Arial';ctx.fillStyle='#333';
      ctx.textAlign='center';ctx.textBaseline='top';
      ctx.fillText(tickers[i],gx+bw+gap/2,MT+PH+4);
    }}

    // Legend
    var lx=ML, ly=H-11;
    ctx.font='8px Barlow,Calibri,Arial';ctx.textBaseline='middle';
    ctx.fillStyle=cd;ctx.fillRect(lx,ly-3,10,7);
    ctx.fillStyle='#333';ctx.textAlign='left';ctx.fillText('TAMAR impl TNA',lx+13,ly);
    lx+=95;
    ctx.fillStyle=cl;ctx.fillRect(lx,ly-3,10,7);
    ctx.fillStyle='#333';ctx.fillText('Target TNA',lx+13,ly);
  }}

  function renderAll(){{
    drawDouble('c2cvA',implA,compA,DARK_A,LIGHT_A);
    drawDouble('c2cvB',implB,compB,DARK_B,LIGHT_B);
  }}

  window.addEventListener('load',renderAll);
  window.addEventListener('resize',renderAll);
  window['drawC2Bar']=renderAll;

  (function patchGoTo(){{
    var p=window.goTo;
    if(typeof p!=='function'){{setTimeout(patchGoTo,100);return;}}
    window.goTo=function(idx){{
      p(idx);
      if(idx===2){{setTimeout(renderAll,80);setTimeout(renderAll,300);}}
    }};
  }})();
}})();
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

        # Para BONCERs necesitamos el precio en base-100 real (paridad)
        # Paridad puede llegar como "98.72%" (string) o 0.9872 (float fracción)
        # Si no está disponible, Last Price en pesos (~378) / (cer_hoy/100) → base-100
        _paridad_raw = r.get("Paridad")
        _last_price  = r.get("Last Price") or r.get("Last") or r.get("Close")
        try:
            if _paridad_raw is not None:
                _pstr = str(_paridad_raw).strip().replace(",", ".")
                if _pstr.endswith("%"):
                    precio = float(_pstr[:-1])          # "98.72%" → 98.72
                else:
                    _pf = float(_pstr)
                    precio = _pf * 100 if 0 < _pf < 5 else _pf   # 0.9872 → 98.72
            else:
                # Fallback: Last Price en pesos → normalizar por CER actual
                _lp = float(_last_price) if _last_price is not None else None
                precio = (_lp / (cer_hoy / 100)) if (_lp and _lp > 200) else _lp
        except Exception:
            precio = _last_price

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
      {{label:labelAct,data:dursAct.map(function(d,i){{return {{x:d,y:tirsAct[i]}};}}),
        borderColor:colorAct,backgroundColor:colorAct,
        pointRadius:5,pointHoverRadius:7,showLine:true,
        borderWidth:2.5,tension:0.3,fill:false}},
      {{label:labelBE,data:dursBE.map(function(d,i){{return {{x:d,y:tirsBE[i]}};}}),
        borderColor:colorBE,backgroundColor:colorBE,
        pointRadius:5,pointHoverRadius:7,showLine:true,
        borderWidth:2,borderDash:[6,4],tension:0.3,fill:false}},
    ]}},
    options:{{
      responsive:true,maintainAspectRatio:false,
      plugins:{{
        legend:{{display:true,position:'top',labels:{{boxWidth:12,font:{{size:10}},color:'#5f7080'}}}},
        tooltip:{{callbacks:{{label:function(c){{return labels[c.dataIndex]+': '+fmtY(c.parsed.y);}}}}}}
      }},
      scales:{{
        x:{{title:{{display:true,text:'Duration (años)',font:{{size:9}},color:'#7a90a4'}},
           grid:{{color:'#eaeef2'}},ticks:{{font:{{size:8}},color:'#7a90a4'}}}},
        y:{{title:{{display:true,text:'Tasa',font:{{size:9}},color:'#7a90a4'}},
           grid:{{color:'#eaeef2'}},
           ticks:{{font:{{size:8}},color:'#7a90a4',callback:function(v){{return fmtY(v);}}}}}}
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
  var bonosTF=BONCAP.filter(function(b){{return b.dias_cal>diasCal;}});
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

    var besTF=bonosTF.map(b=>{{
      var dR=b.dias_cal-diasCal;
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
      var isCur=bonosTF.some(function(b){{return Math.abs(b.tir-ey)<pasoTF/2+0.0001;}});
      var cells=bonosTF.map(b=>{{
        var dR=b.dias_cal-diasCal;
        const pS=b.vn/Math.pow(1+ey,dR/365);
        const tr=pS/b.precio-1-cf;
        const[bg,col]=colorTR(tr*100);
        return '<td style="background:'+bg+';color:'+col+'">'+(tr*100).toFixed(2)+'%</td>';
      }}).join('');
      const lbl=isCur?'→ '+(ey*100).toFixed(1)+'%':(ey*100).toFixed(1)+'%';
      return '<tr class="'+(isCur?'cur-row':'')+'"><td class="lbl">'+lbl+'</td>'+cells+'</tr>';
    }}).join('');

    chartTF=drawCurveChart('c4-chart-tf',
      bonosTF.map(function(b){{return b.ticker;}}),
      bonosTF.map(function(b){{return b.dur;}}), bonosTF.map(function(b){{return b.tir;}}),
      bonosTF.map(function(b){{return b.dur;}}), besTF,
      '#1e6fba','#b85a1a','Curva actual','Curva break-even',
      function(v){{return (v*100).toFixed(1)+'%';}}, chartTF);

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
  var bonosCER=BONCER.filter(function(b){{return b.dias_cal>diasCal+1;}});
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

    var besCER=bonosCER.map(b=>{{
      var dR=b.dias_cal-diasCal-1;
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
      var avgBE=besCER.reduce(function(s,v){{return s+v;}},0)/besCER.length;
      var isCur=Math.abs(avgBE-ey)<pasoCER/2+0.0001;
      var cells=bonosCER.map(b=>{{
        var dR=b.dias_cal-diasCal-1;
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
      bonosCER.map(function(b){{return b.ticker;}}),
      bonosCER.map(function(b){{return b.dur;}}), bonosCER.map(function(b){{return b.tir_real_hoy;}}),
      bonosCER.map(function(b){{return b.dur;}}), besCER,
      '#1a7a46','#b85a1a','Curva real actual','Curva real break-even',
      function(v){{return (v*100).toFixed(1)+'%';}}, chartCER);

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

// Cap4 lazy render — usa goToId hook en el sistema unificado
(function(){{
  var _c4init = false;

  window._c4Render = function() {{
    if (!_c4init) {{
      // Primera vez: renderizar ahora que el slide es visible
      render();
      _c4init = true;
    }} else {{
      // Re-navegaciones: re-renderizar para actualizar tamaño de charts
      if (chartTF) {{ chartTF.destroy(); chartTF = null; }}
      if (chartCER) {{ chartCER.destroy(); chartCER = null; }}
      render();
    }}
  }};

  // Hook en DOMContentLoaded — parchear goToId
  document.addEventListener('DOMContentLoaded', function() {{
    var _gti = window.goToId;
    if (typeof _gti === 'function') {{
      window.goToId = function(id) {{
        _gti(id);
        if (id === 'slide-4') {{
          requestAnimationFrame(function() {{
            requestAnimationFrame(window._c4Render);
          }});
        }}
      }};
    }}
    // También para goTo numérico
    var _gt = window.goTo;
    if (typeof _gt === 'function') {{
      window.goTo = function(idx) {{
        _gt(idx);
        if (idx === 4) {{
          requestAnimationFrame(function() {{
            requestAnimationFrame(window._c4Render);
          }});
        }}
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



def _ticker_to_vto(ticker: str, hoy: date) -> date:
    """Parsea fecha de vencimiento desde ticker LECAP/BONCAP (S30A6, T30J6, etc)."""
    import re as _re2, calendar as _cal
    _MES = {'E':1,'F':2,'M':3,'A':4,'Y':5,'J':6,'L':7,'G':8,'S':9,'O':10,'N':11,'D':12}
    t = ticker.strip().replace(' CI','').rstrip('jv')
    m = _re2.match(r'^[A-Za-z]+?(\d{1,2})([A-Za-z])(\d{1,2})$', t)
    if not m:
        return None
    day = int(m.group(1))
    mes = _MES.get(m.group(2).upper())
    yr  = int(m.group(3))
    if not mes:
        return None
    year = (2020 + yr) if yr < 10 else (2000 + yr)
    ld = _cal.monthrange(year, mes)[1]
    try:
        return date(year, mes, min(day, ld))
    except ValueError:
        return None


def _assign_bond_to_dus(dus_date: date, df_lecap: pd.DataFrame,
                        df_cer: pd.DataFrame, tamar_tea: float,
                        used_tickers: set = None) -> dict:
    """
    Para cada DUS asigna el mejor bono ARS:
    1. BONCAP/LECAP: siempre preferido. Se toma el que vence lo mas cerca
       DESPUES del DUS (o antes si no hay ninguno despues).
    2. BONCER proyectado (j): solo si no existe ningun BONCAP disponible.
    Usa _ticker_to_vto() para obtener la fecha exacta de vencimiento.
    """
    from datetime import timedelta
    hoy = date.today()

    def _vto(dur: float) -> date:  # fallback si ticker no parseable
        return hoy + timedelta(days=round(float(dur) * 365))

    if used_tickers is None:
        used_tickers = set()
    candidates_cap = []
    for _, r in _clean_df(df_lecap).iterrows():
        dur = r.get("Duration"); tir = _pct_float(r.get("TIREA"))
        if dur is None or tir is None: continue
        ticker = str(r["Código"])
        if ticker in used_tickers: continue  # ya asignado a otro DUS
        try:
            dur_f = float(dur)
            # Preferir fecha real del ticker sobre Duration
            vto = _ticker_to_vto(ticker, hoy) or _vto(dur_f)
        except:
            continue
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

    if best is None:  # Solo usar BONCER j si no hay ningun BONCAP disponible
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




def _get_futuros_auto(df_futuros_param, prev_snap, hoy):
    """Futuros DUS: parámetro → bymaapi.futuros_minorista → snapshot anterior"""
    # 1. Parámetro explícito
    if df_futuros_param is not None and hasattr(df_futuros_param,"empty") and not df_futuros_param.empty:
        print(f"[cap5] Usando df_futuros param ({len(df_futuros_param)} filas)")
        return df_futuros_param

    # 2. bymaapi.futuros_minorista
    try:
        import bymaapi as _ba
        fm = getattr(_ba, "futuros_minorista", None)
        if fm is not None and hasattr(fm,"empty") and not fm.empty:
            df = fm.copy()
            col_map = {"symbol":"Código","price":"Last Price",
                       "days_to_maturity":"Dias Vto","maturityDate":"Fecha Vto"}
            df = df.rename(columns={k:v for k,v in col_map.items()
                                    if k in df.columns and v not in df.columns})
            # Filtrar mayoristas
            if "Código" in df.columns:
                df = df[~df["Código"].astype(str).str.upper().str.endswith("A")].copy()
            df = df.reset_index(drop=True)
            print(f"[cap5] Usando futuros_minorista de bymaapi ({len(df)} contratos)")
            if len(df) > 0:
                cols_info = [c for c in ["Código","Last Price","Dias Vto","Fecha Vto"] if c in df.columns]
                print(f"[cap5]   cols={cols_info}, primero: {df[cols_info].iloc[0].to_dict()}")
            return df
    except ImportError:
        print("[cap5] bymaapi no disponible")
    except Exception as e:
        print(f"[cap5] Error futuros_minorista: {e}")

    # 3. Snapshot anterior
    if prev_snap and prev_snap.get("rofex"):
        print("[cap5] Usando ROFEX del snapshot anterior")
        rows = [{"Código": r.get("ticker",""), "Last Price": r.get("precio"),
                 "Dias Vto": r.get("dias"), "Fecha Vto": r.get("fecha_vto")}
                for r in prev_snap["rofex"] if r.get("precio") and r.get("dias")]
        if rows:
            return pd.DataFrame(rows)

    print("[cap5] Sin fuente de futuros — usando fallback sintético")
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

    # Helper: label de mes en español
    _MES_ES = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
               7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
    def _label_mes(d): return f"{_MES_ES.get(d.month, d.strftime('%b'))}-{d.strftime('%y')}"

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
                if dias_f <= 10:  # ignorar contratos casi vencidos (TIR distorsionada)
                    continue
                label  = _label_mes(mat_date)
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

    # Fallback si no hay futuros — usar fechas reales de fin de mes
    if not dus_contracts:
        print("[cap5] Sin datos de futuros — construyendo curva sintética (CPI 3%)")
        cpi_m = 0.03
        try:
            from pandas.tseries.offsets import MonthEnd
            for i in range(1, 11):
                mat    = (pd.Timestamp(hoy) + MonthEnd(i)).date()
                dias_f = (mat - hoy).days
                if dias_f <= 0: continue
                precio = round(spot * (1 + cpi_m) ** i, 1)
                tea    = (precio / spot) ** (365 / dias_f) - 1
                tna    = (precio / spot - 1) * 365 / dias_f
                deva_m = (precio / spot) ** (30  / dias_f) - 1
                dus_contracts.append({
                    "label":  _label_mes(mat),
                    "precio": precio, "dias": dias_f, "mat": mat,
                    "tea":    round(tea * 100, 4),
                    "tna":    round(tna * 100, 4),
                    "deva_m": round(deva_m * 100, 4),
                })
        except Exception as _fe:
            for i in range(1, 11):
                dias_f = i * 30
                mat = hoy + timedelta(days=dias_f)
                precio = round(spot * (1 + cpi_m) ** i, 1)
                tea = (precio / spot) ** (365 / dias_f) - 1
                tna = (precio / spot - 1) * 365 / dias_f
                deva_m = (precio / spot) ** (30 / dias_f) - 1
                dus_contracts.append({
                    "label":  _label_mes(mat),
                    "precio": precio, "dias": dias_f, "mat": mat,
                    "tea":    round(tea * 100, 4),
                    "tna":    round(tna * 100, 4),
                    "deva_m": round(deva_m * 100, 4),
                })

    # Calcular fwd mensual entre contratos
    for i, c in enumerate(dus_contracts):
        deva_m_raw = (c["precio"] / spot) ** (30 / max(c["dias"], 1)) - 1
        deva_acum  = c["precio"] / spot - 1
        if i == 0:
            fwd_m   = c["precio"] / spot - 1        # primer contrato vs spot
            dt      = max(c["dias"], 1)
            tna_fwd = fwd_m * 30 / dt
        else:
            prev    = dus_contracts[i - 1]
            fwd_m   = c["precio"] / prev["precio"] - 1
            dt      = max(c["dias"] - prev["dias"], 1)
            tna_fwd = fwd_m * 30 / dt
        c["fwd_m"]    = round(fwd_m    * 100, 4)
        c["tna_fwd"]  = round(tna_fwd  * 100, 4)
        c["deva_m"]   = round(deva_m_raw * 100, 4)
        c["deva_acum"]= round(deva_acum  * 100, 4)

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

    def _td(v, fmt="{:.1f}%", color=None, bold=False):
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
        "".join(f"<td>{c['tea']:.1f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>TNA Contrato</td>" +
        "".join(f"<td>{c['tna']:.1f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr class='c6-row-sep'><td class='c6-lbl'>Deva mensual implícita</td>" +
        "".join(f"<td>{c['deva_m']:.1f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>Fwd Contratos (mensual)</td>" +
        "".join(f"<td>{c['fwd_m']:.1f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr><td class='c6-lbl'>TNA FWD (norm. 30d)</td>" +
        "".join(f"<td>{c['tna_fwd']:.1f}%</td>" for c in dus_contracts) + "</tr>",

        "<tr class='c6-row-sep'><td class='c6-lbl'>Deva acumulada</td>" +
        "".join(f"<td>{c['deva_acum']:.1f}%</td>" for c in dus_contracts) + "</tr>",
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
            f'<td style="color:#1a7a46;font-weight:600">{s["tir_nom"]:.1f}%</td>'
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
            f'<td style="color:{"#1a7a46" if (s["sint_tea"] or 0)>=0 else "#c0392b"};font-weight:600">{("+" if s["sint_tea"]>=0 else "")}{s["sint_tea"]:.1f}%</td>'
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
          label: function(c){{return ' ' + c.dataset.label + ': ' + Math.round(c.parsed.y).toLocaleString('es-AR');}}
        }}}} }},
        scales: {{
          x: {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}}} }},
          y: {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}},
                 callback: function(v){{return v.toLocaleString('es-AR');}}}}, min:{y_min_js}, max:{y_max_js} }}
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
          label: function(c){{return ' ' + c.dataset.label + ': ' + (c.parsed.y != null ? c.parsed.y.toFixed(1) : '-') + '%';}}
        }}}} }},
        scales: {{
          x:  {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}, autoSkip:false}} }},
          y:  {{ grid:{{color:grid}}, ticks:{{color:tick, font:{{size:10,family:FONT}}, callback:function(v){{return v.toFixed(0)+'%';}}}},
                 title:{{display:true,text:'Distancia al techo (%)',color:tick,font:{{size:10,family:FONT}}}} }},
          y2: {{ position:'right', grid:{{drawOnChartArea:false}},
                 ticks:{{color:'#1a7a46',font:{{size:10,family:FONT}},callback:function(v){{return v.toFixed(1)+'%';}}}},
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
<style>
.snap-tbl {{border-collapse:collapse;width:100%;font-family:var(--font-body,'Calibri',Arial);font-size:11.5px;}}
.snap-tbl th {{background:#0f2557 !important;color:white !important;padding:5px 10px !important;text-align:center !important;font-size:10.5px !important;font-weight:600 !important;border-right:1px solid rgba(255,255,255,0.15) !important;}}
.snap-tbl td {{padding:4px 10px;text-align:center !important;border-bottom:1px solid #eaeef2 !important;border-right:1px solid #eaeef2 !important;}}
.snap-tbl td:first-child,.snap-tbl th:first-child {{text-align:left !important;font-weight:600 !important;color:#0f2557 !important;min-width:80px;}}
.snap-tbl tr:last-child td {{border-bottom:none;}}
.snap-tbl .td-val {{text-align:right;font-variant-numeric:tabular-nums;}}
.snap-tbl .td-pos {{color:#1a7a46;}}
.snap-tbl .td-neg {{color:#b85a1a;}}
.snap-tbl .td-ticker {{font-weight:700;color:#0f2557;}}
/* Movimientos — cards alineadas */
.c7-cards {{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;margin-top:6px}}
</style>
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
  <div class="snap-tbl-wrap" style="flex:0 0 auto">
    <table class="snap-tbl">
      <thead><tr><th>Variable</th><th>Valor</th></tr></thead>
      <tbody>
        <tr><td>TAMAR</td><td class="td-val">{tamar_str}</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="panel-label">BONCAP — Tasa fija</div>
<div style="overflow-x:auto"><table class="snap-tbl">
  <thead><tr><th>Ticker</th><th>Precio</th><th>TIR TEA</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_boncap(snap.get("boncap", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">BONCER — Ajuste CER</div>
<div style="overflow-x:auto"><table class="snap-tbl">
  <thead><tr><th>Ticker</th><th>Precio</th><th>T. Real</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_boncer(snap.get("boncer", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">BONTAM — Tasa variable</div>
<div style="overflow-x:auto"><table class="snap-tbl">
  <thead><tr><th>Ticker</th><th>Precio</th><th>TIR TEA</th><th>Spread</th><th>Duration</th></tr></thead>
  <tbody>{_tbl_bontam(snap.get("bontam", []))}</tbody>
</table></div>

<div class="panel-label" style="margin-top:18px">Inflación implícita break-even</div>
<div style="overflow-x:auto"><table class="snap-tbl">
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
    <table class="snap-tbl">
      <thead><tr><th>Variable</th><th>Anterior</th><th>Actual</th><th>Δ</th></tr></thead>
      <tbody>{fx_tabla}</tbody>
    </table>
  </div>
  <div>
    <div class="panel-label">Inflación implícita break-even (CPI bootstrap)</div>
    <table class="snap-tbl">
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
  font-size: 23px !important;
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
.mini-table thead th { background:#0f2557 !important; color:white !important; font-family:var(--font-title) !important; font-size:9.5px; text-align:center !important; padding:4px 8px !important; border-right:1px solid rgba(255,255,255,0.15) !important; }
.mini-table tbody td { text-align:center !important; padding:3px 8px !important; border-bottom:1px solid #eaeef2 !important; border-right:1px solid #eaeef2 !important; }
.mini-table tbody td:first-child, .mini-table thead th:first-child { text-align:left !important; }
.mini-table tbody td.td-val { text-align:right !important; font-variant-numeric:tabular-nums; }
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
    document.getElementById('nav-'   + current).classList.add('active');
    // Actualizar topbar mobile
    var tEl = document.getElementById('mobile-title');
    var sEl = document.getElementById('mobile-slide');
    if (tEl) tEl.textContent = slideTitles[idx] || 'Comité';
    if (sEl) sEl.textContent = (idx + 1) + ' / ' + total;
    // Cerrar sidebar al navegar en mobile (delay para que el click termine)
    setTimeout(closeSidebar, 80);
  }"""

    new_goto = """// ── Navegación unificada (slides numerados + fd-slides) ──
  var _currentFdId = null;
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
    var navId = targetId.replace('fd-slide-', 'fd-nav-').replace(/^slide-/, 'nav-');
    var navEl = document.getElementById(navId);
    if (navEl) navEl.classList.add('active');
    var tEl = document.getElementById('mobile-title');
    var sEl = document.getElementById('mobile-slide');
    if (tEl && slideTitles) tEl.textContent = slideTitles[parseInt(targetId.replace(/[^0-9]/g,''))] || 'Fondos';
    if (sEl) sEl.textContent = targetId;
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 60);
    setTimeout(closeSidebar, 80);
    if (targetId === 'slide-4' && typeof window._c4Render === 'function') {
      requestAnimationFrame(function() { requestAnimationFrame(window._c4Render); });
    }
  }
  function goTo(idx) {
    if (idx < 0 || idx >= total) return;
    _hideAll();
    _currentFdId = null;
    current = idx;
    var slideEl = document.getElementById('slide-' + current);
    var navEl2  = document.getElementById('nav-'   + current);
    if (slideEl) slideEl.classList.add('active');
    if (navEl2)  navEl2.classList.add('active');
    var tEl = document.getElementById('mobile-title');
    var sEl = document.getElementById('mobile-slide');
    if (tEl && slideTitles) tEl.textContent = slideTitles[idx] || 'Comité';
    if (sEl) sEl.textContent = (idx + 1) + ' / ' + total;
    setTimeout(closeSidebar, 80);
    setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 60);
    if (idx === 4 && typeof window._c4Render === 'function') {
      requestAnimationFrame(function() { requestAnimationFrame(window._c4Render); });
    }
  }"""

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
    vcp_data_path:   str        = None,   # CSV con variaciones VCP (opcional)
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

    # ── Aplicar paleta Delta y rediseñar carátula ────────────────────────
    # Paleta Delta: navy=#0841A5, orange=#F26B43, blue2=#4385EF, green=#328F58
    _LOGO_SRC = "data:image/png;base64,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"

    # Reemplazar cover slide con versión Delta branding
    _old_cover_inner = (
        '''<div class="cover-bg-circle" style="width:400px;height:400px;top:-120px;right:-100px;"></div>\n'''
        '''    <div class="cover-bg-circle" style="width:200px;height:200px;bottom:60px;right:200px;"></div>\n'''
        '''    <div class="cover-tag">Comité de Inversiones</div>\n'''
        '''    <h1 class="cover-h1">Análisis de Renta Fija<br>Argentina</h1>\n'''
        '''    <p class="cover-sub">Rendimientos, tasas implícitas y valuación relativa de los instrumentos\n'''
        '''    de tasa fija, ajuste CER y tasa variable referenciada a TAMAR.</p>'''
    )
    _new_cover_inner = (
        f'''<div class="cover-bg-circle" style="width:480px;height:480px;top:-140px;right:-120px;background:rgba(255,255,255,0.05)"></div>\n'''
        f'''    <div class="cover-bg-circle" style="width:260px;height:260px;bottom:30px;right:200px;background:rgba(254,136,0,0.12)"></div>\n'''
        f'''    <div style="position:absolute;top:36px;right:60px;"><img src="data:image/png;base64,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" style="height:44px;opacity:0.92" alt="Delta Asset Management"></div>\n'''
        f'''    <div class="cover-tag" style="margin-top:24px;font-size:10px;letter-spacing:4px;color:rgba(255,255,255,0.45)">Delta Asset Management</div>\n'''
        f'''    <h1 class="cover-h1" style="font-size:56px;margin-bottom:8px;line-height:1.05;letter-spacing:-1px">Comité de Inversiones</h1>\n'''
        f'''    <div style="font-size:24px;font-weight:300;color:rgba(255,255,255,0.7);margin-bottom:20px;letter-spacing:-0.2px">Análisis de Renta Fija Argentina</div>\n'''
        f'''    <p class="cover-sub" style="font-size:14px;max-width:500px">Rendimientos, tasas implícitas y valuación relativa de los instrumentos\n'''
        f'''    de tasa fija, ajuste CER y tasa variable referenciada a TAMAR.</p>'''
    )
    if _old_cover_inner in html:
        html = html.replace(_old_cover_inner, _new_cover_inner, 1)

    # Paleta: actualizar colores base en CSS del template
    for _old_c, _new_c in [
        ("#0f2557", "#0841A5"),   # navy → Delta navy
        ("#091840", "#062090"),   # dark navy → Delta dark
        ("#1a3878", "#1560c8"),   # mid navy → Delta mid
        ("#1e6fba", "#4385EF"),   # blue → Delta blue2
        ("#1a7a46", "#328F58"),   # green → Delta green
        ("#b85a1a", "#F26B43"),   # orange → Delta orange
    ]:
        html = html.replace(_old_c, _new_c)
    # ────────────────────────────────────────────────────────────────────
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
    # Patch nav onclicks para que usen window.goTo (con todos los patches de caps)
    import re as _re3
    html = _re3.sub(r'onclick="goTo\((\d+)\)"',
                    lambda m: f'onclick="(window.goTo||goTo)({m.group(1)})"', html)
    # Override mini-table CSS del template para centrar headers
    html = html.replace(
        '.mini-table thead th { background: var(--light); color: var(--muted); font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; padding: 5px 8px; border-bottom: 1px solid var(--border); text-align: left; }',
        '.mini-table thead th { background: #0f2557; color: white; font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; padding: 4px 8px; text-align: center; border-right: 1px solid rgba(255,255,255,0.15); }'
    )
    html = html.replace(
        '.mini-table tbody td { padding: 4px 8px; border-bottom: 1px solid #f0f2f5; color: var(--text); }',
        '.mini-table tbody td { padding: 3px 8px; text-align: center; border-bottom: 1px solid #eaeef2; border-right: 1px solid #eaeef2; color: var(--text); }'
    )
    html = _inject_css(html, _CAP1_CSS)
    html = _replace_cap1(html, _build_cap1_html(
        df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna))
    html = _replace_capN(html, "slide-2", _build_cap2_html(
        df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna, hoy))
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
    # Aplicar fallbacks techo/piso ANTES del snapshot (igual que en cap5)
    _spot_fb = _fx_data.get("spot") or 1398.0
    if not _fx_data.get("techo_hoy"): _fx_data["techo_hoy"] = _spot_fb * 1.18
    if not _fx_data.get("piso_hoy"):  _fx_data["piso_hoy"]  = _spot_fb * 0.60
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
            # Inyectar slide 12 (inputs VCP) antes de </body>
            from generar_fondos import generar_inputs_slide
            html = html.replace('</body>', generar_inputs_slide() + '\n</body>', 1)
            # Leer CSV de variaciones VCP si se provee, e inyectar valores pre-cargados
            if vcp_data_path:
                try:
                    import re as _re_vcp
                    _vcp_vals = {}
                    _ext = str(vcp_data_path).lower()

                    if _ext.endswith('.xlsx') or _ext.endswith('.xls'):
                        # --- Leer desde Excel de Segmento (Power BI export) ---
                        import pandas as _pd_vcp
                        _df_vcp = _pd_vcp.read_excel(vcp_data_path, header=0)
                        # Columnas: Moneda, Grupo, Subgrupo, Fondo, 7d, 30d, ...
                        # s1 = columna "7d", s30 = columna "30d"
                        # Mapeo fondo_id -> (nombre exacto en Excel, subgrupo)
                        _FONDO_MAP = {
                            "performance": {
                                "fondo":     "Delta Performance",
                                "benchmark": "Badlar Privada",
                                "peers":     "Peers RF T+0",
                                "industria": "Industria RF T+0",
                            },
                            "ahorro_plus": {
                                "fondo":     "Delta Ahorro Plus",
                                "benchmark": "Badlar Privada + 200 bps",
                                "peers":     "Peers RF T+1",
                                "industria": "Industria RF T+1",
                            },
                            "retorno_real": {
                                "fondo":     "Delta Retorno Real",
                                "benchmark": "Índice CER",
                                "peers":     "Peers RF CER",
                                "industria": "Industria RF CER",
                            },
                            "multimercado": {
                                "fondo":     "Delta Multimercado I",
                                "benchmark": "25% S&P Merval + 25% Índice CER + 25% A3500 + 25% CCL",
                                "peers":     "Peers Renta Mixta",
                                "industria": "Industria Renta Mixta",
                            },
                        }
                        _name_to_row = {}
                        for _, _r in _df_vcp.iterrows():
                            _fn = str(_r.get("Fondo", "") or "").strip()
                            if _fn and _fn != "nan":
                                _s1  = _r.get("7d")
                                _s30 = _r.get("30d")
                                try:
                                    _name_to_row[_fn] = (float(_s1)*100, float(_s30)*100)
                                except Exception:
                                    pass
                        for _fid, _names in _FONDO_MAP.items():
                            for _eid, _nombre in _names.items():
                                if _nombre in _name_to_row:
                                    _vcp_vals[(_fid, _eid)] = _name_to_row[_nombre]
                        print(f"[generar_reporte] VCP Excel: {len(_vcp_vals)} valores cargados")

                    else:
                        # --- Leer desde CSV (formato legacy: fondo,entidad,s1,s30) ---
                        import csv as _csv
                        with open(vcp_data_path, 'r', encoding='utf-8-sig') as _f:
                            for _row in _csv.reader(_f):
                                if not _row or _row[0].strip().startswith('#'): continue
                                if _row[0].strip().lower() == 'fondo': continue
                                try:
                                    _fondo, _entidad, _s1, _s30 = [x.strip() for x in _row[:4]]
                                    _vcp_vals[(_fondo, _entidad)] = (float(_s1), float(_s30))
                                except (ValueError, IndexError):
                                    continue
                        print(f"[generar_reporte] VCP CSV: {len(_vcp_vals)} valores cargados")

                    # Inyectar valores en los inputs HTML
                    def _set_vcp_val(ht, inp_id, val):
                        # Find input tag containing this id and inject value
                        # Works regardless of attribute order or quote style
                        def _inject(m):
                            tag = m.group(0)
                            if 'value=' not in tag:
                                tag = tag.replace('placeholder=', f'value="{round(val,3)}" placeholder=')
                            return tag
                        return _re_vcp.sub(
                            r'<input[^>]*(?:id=["\']' + _re_vcp.escape(inp_id) + r'["\'][^>]*)>',
                            _inject,
                            ht
                        )
                    for (_fondo, _entidad), (_s1, _s30) in _vcp_vals.items():
                        html = _set_vcp_val(html, f'vcp-{_fondo}-s1-{_entidad}', _s1)
                        html = _set_vcp_val(html, f'vcp-{_fondo}-s30-{_entidad}', _s30)

                except Exception as _e:
                    print(f"[generar_reporte] Warning VCP: {_e}")
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

    # Sanitizar scripts para compatibilidad con Claude iframe
    import re as _re2
    _CHAR_MAP = {
        'á':'a','é':'e','í':'i','ó':'o','ú':'u',
        'Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U',
        'ñ':'n','Ñ':'N','ü':'u','Ü':'U',
        '—':'-','–':'-','→':'->','─':'-','·':'.',
        '•':'*','✕':'x','…':'...',
    }
    def _clean_scripts(m):
        body = m.group(2)
        for ch, rep in _CHAR_MAP.items():
            body = body.replace(ch, rep)
        body = _re2.sub(r'\bconst\b', 'var', body)
        body = _re2.sub(r'\blet\b', 'var', body)
        body = _re2.sub(r'\$\{([^}]+)\}', lambda x: "' + " + x.group(1) + " + '", body)
        body = body.replace('`', "'")
        body = _re2.sub(r'(\w+)\s*=>\s*\{', r'function(\1){', body)
        body = _re2.sub(r'\((\w[^)]*?)\)\s*=>\s*\{', r'function(\1){', body)
        return m.group(1) + body + m.group(3)
    html = _re2.sub(r'(<script[^>]*>)(.*?)(</script>)', _clean_scripts, html, flags=_re2.DOTALL)

    # ── Inyectar logo Delta en esquina superior derecha de todas las slides ──
    _LOGO_WHITE_FULL = "data:image/png;base64,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"
    _LOGO_BLUE       = "data:image/png;base64,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"

    # Cover: logo blanco con "Asset Management" — ya en el HTML de la cover
    # Slides 1-7: logo azul en esquina superior derecha
    # Inject <img class="slide-logo"> into each slide-chapter div
    import re as _re_logo
    def _add_logo_to_chapter(m):
        div_open = m.group(0)
        logo_tag = f'<img src="{_LOGO_BLUE}" alt="Delta" style="position:absolute;top:14px;right:18px;height:26px;opacity:0.85;z-index:10;pointer-events:none">'
        return div_open + logo_tag
    html = _re_logo.sub(
        r'<div class="slide-chapter[^"]*"[^>]*>',
        _add_logo_to_chapter,
        html
    )
    # ────────────────────────────────────────────────────────────────────────

        # ── Inyectar CSS override para títulos de sección más grandes ─────────
    html = html.replace(
        "</style>",
        ".slide-section-titles h2 { font-size: 26px !important; font-weight:600 !important; }"
        ".slide-section-num { font-size: 56px !important; }"
        "</style>",
        1
    )

    # ── Aplicar paleta Delta (reemplazar colores hardcoded en todo el HTML) ──
    for _old_c, _new_c in [
        ("#0f2557", "#0841A5"),   # navy → Delta navy
        ("#091840", "#062090"),   # dark navy
        ("#1a3878", "#1560c8"),   # mid navy
        ("#1e6fba", "#4385EF"),   # blue → Delta blue2
        ("#1a7a46", "#328F58"),   # green → Delta green
        ("#b85a1a", "#F26B43"),   # orange → Delta orange
        ("#c5d4e8", "#a8c4f0"),   # section num color (derived)
        ("'#0f2557'", "'#0841A5'"),  # JS string literals
        ('"#0f2557"', '"#0841A5"'),
        ("'#1e6fba'", "'#4385EF'"),
        ('"#1e6fba"', '"#4385EF"'),
        ("'#1a7a46'", "'#328F58'"),
        ('"#1a7a46"', '"#328F58"'),
        ("'#b85a1a'", "'#F26B43'"),
        ('"#b85a1a"', '"#F26B43"'),
    ]:
        html = html.replace(_old_c, _new_c)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[generar_reporte] ✓ Guardado: {output_path}")
    return output_path
