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

var FONT = "'Calibri', 'Gill Sans', Arial, sans-serif";

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

  var ML=52, MR=18, MT=14, MB=36;
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

  ctx.fillStyle='white'; ctx.fillRect(0,0,W,H);

  /* Grid Y */
  var y=YB;
  while(y<=YT+1e-9){
    var yp=py(y), isZ=Math.abs(y)<1e-9;
    ctx.beginPath(); ctx.moveTo(ML,yp); ctx.lineTo(ML+PW,yp);
    ctx.strokeStyle=(isZ&&zeroLine)?'#9badb8':'#e8ecf0';
    ctx.lineWidth=(isZ&&zeroLine)?1.2:0.8; ctx.stroke();
    ctx.font='10px '+FONT; ctx.fillStyle='#8896a5'; ctx.textAlign='right';
    ctx.fillText(y.toFixed(1)+'%', ML-6, yp+3.5);
    y=Math.round((y+yStep)*1e9)/1e9;
  }

  /* Grid X */
  var xStep=niceStep(XR-XL,5), xx=Math.ceil(XL/xStep)*xStep;
  while(xx<=XR+1e-9){
    var xp=px(xx);
    ctx.beginPath(); ctx.moveTo(xp,MT); ctx.lineTo(xp,MT+PH);
    ctx.strokeStyle='#e8ecf0'; ctx.lineWidth=0.8; ctx.stroke();
    ctx.font='10px '+FONT; ctx.fillStyle='#8896a5'; ctx.textAlign='center';
    ctx.fillText(xx.toFixed(xx<1?2:1), xp, MT+PH+14);
    xx=Math.round((xx+xStep)*1e9)/1e9;
  }

  ctx.strokeStyle='#dde3ec'; ctx.lineWidth=0.8;
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
    ctx.setLineDash([6,4]); ctx.globalAlpha=0.55; ctx.stroke();
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

  /* Labels */
  ctx.font='bold 9px '+FONT;
  for(var i=0;i<data.length;i++){
    var d=data[i], xp3=px(d[1]), yp3=py(d[2]), lbl=d[0];
    var toRight = xp3 < ML+PW*0.75;
    ctx.textAlign = toRight ? 'left' : 'right';
    var lx = toRight ? xp3+R+4 : xp3-R-4, ly=yp3-5;
    ctx.strokeStyle='white'; ctx.lineWidth=2.5; ctx.lineJoin='round';
    ctx.strokeText(lbl,lx,ly);
    ctx.fillStyle=color; ctx.fillText(lbl,lx,ly);
  }

  ctx.save(); ctx.translate(13,MT+PH/2); ctx.rotate(-Math.PI/2);
  ctx.textAlign='center'; ctx.font='10px '+FONT; ctx.fillStyle='#8896a5';
  ctx.fillText(yAxisLabel,0,0); ctx.restore();
  ctx.textAlign='center'; ctx.font='10px '+FONT; ctx.fillStyle='#8896a5';
  ctx.fillText('Duration (años)', ML+PW/2, H-4);
}

/* Datos inyectados por Python */
var _C1_BONCAP      = %%BONCAP%%;
var _C1_BONCER_FULL = %%BONCER%%;   /* todos los bonos CER */
var _C1_BONTAM      = %%BONTAM%%;

/* Bonos que se excluyen del gráfico BONCER por defecto */
var _BONCER_EXCL = {"PARP": true, "CUAP": true};
var _boncer_show_all = false;

function _boncer_data() {
  if (_boncer_show_all) return _C1_BONCER_FULL;
  return _C1_BONCER_FULL.filter(function(d){ return !_BONCER_EXCL[d[0]]; });
}

function _c1Draw() {
  drawChart('c1-cv-boncap', _C1_BONCAP,      '#1a5fa8', 'TIR TEA (%)',            false);
  drawChart('c1-cv-boncer', _boncer_data(),   '#1a7a46', 'Tasa real (%)',           true);
  drawChart('c1-cv-bontam', _C1_BONTAM,      '#b85a1a', 'Spread vs TAMAR (%)',     true);
}

function _c1Init() { _c1Draw(); }

/* Botón toggle PARP/CUAP */
document.addEventListener('DOMContentLoaded', function() {
  var btn = document.getElementById('c1-btn-excl');
  if (btn) {
    btn.addEventListener('click', function() {
      _boncer_show_all = !_boncer_show_all;
      btn.textContent = _boncer_show_all
        ? '✕  Excluir PARP y CUAP'
        : '+  Incluir PARP y CUAP';
      btn.style.background = _boncer_show_all ? '#fff3e8' : '#f4f6f9';
      btn.style.color      = _boncer_show_all ? '#b85a1a' : '#6b7c93';
      btn.style.borderColor= _boncer_show_all ? '#b85a1a' : '#dde3ec';
      _c1Draw();
    });
  }

  /* Hook goTo */
  var _orig = window.goTo;
  if (typeof _orig === 'function') {
    window.goTo = function(idx) {
      _orig(idx);
      if (idx === 1) setTimeout(_c1Init, 60);
    };
  }
});

window.addEventListener('load', function() { setTimeout(_c1Init, 60); });
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
# INJECT HELPERS
# =============================================================================

def _inject_css(html, css):
    return html.replace("</style>", css + "\n</style>", 1)


def _replace_cap1(html, cap1_inner):
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

    if tamar_tea is None and not df_tamar.empty and "TIREA" in df_tamar.columns:
        vals = df_tamar["TIREA"].apply(_pct_float).dropna()
        tamar_tea = float(vals.mean()) if not vals.empty else 0.2973
    if tamar_tna is None:
        tamar_tna = tamar_tea or 0.263

    print(f"  TAMAR: TNA={tamar_tna*100:.3f}%  TEA={tamar_tea*100:.3f}%")

    html = _inject_css(html, _CAP1_CSS)
    html = _replace_cap1(html, _build_cap1_html(
        df_lecap, df_cer, df_tamar, df_dual, tamar_tea, tamar_tna))
    html = _replace_fecha(html, fecha_str, fecha_yyyymmdd)
    html = _replace_tamar_texts(html, tamar_tna, tamar_tea)

    if output_path is None:
        output_dir  = Path(template_path).parent
        output_path = str(output_dir / f"reporte_comite_{fecha_yyyymmdd}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[generar_reporte] ✓ Guardado: {output_path}")
    return output_path
