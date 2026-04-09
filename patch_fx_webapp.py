#!/usr/bin/env python3
"""
patch_fx_webapp.py — Aplica los 3 parches de FX A3500 en tiempo real a OMSweb_app.py

Uso:
    python patch_fx_webapp.py OMSweb_app.py

Hace backup automático (.bak) antes de modificar.

Prerequisito: OMSdata.py ya debe tener las funciones:
  get_fx_hoy, refresh_a3500_in_rentafija, fx_status_text, invalidate_fx_cache
(ver parche_fx_unificado.py)
"""
import sys
import shutil

if len(sys.argv) < 2:
    print("Uso: python patch_fx_webapp.py /ruta/a/OMSweb_app.py")
    sys.exit(1)

path = sys.argv[1]

# Backup
shutil.copy2(path, path + ".bak")
print(f"Backup creado: {path}.bak")

with open(path, "r", encoding="utf-8") as f:
    src = f.read()

applied = 0

# ═══════════════════════════════════════════════════════════════════════
# PATCH 1: _curvas_live — agregar invalidate + refresh + fx_status_text
# ═══════════════════════════════════════════════════════════════════════

OLD_1 = """        @st.fragment(run_every=refresh_interval)
        def _curvas_live():
            # Invalidar cache para forzar re-fetch
            st.caption(f"\U0001f534 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}")"""

NEW_1 = """        @st.fragment(run_every=refresh_interval)
        def _curvas_live():
            # Refrescar FX A3500 en cada ciclo live (>>> PATCH FX 04/2026)
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))

            st.caption(f"\U0001f534 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}  |  {fx_status_text()}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}  |  {fx_status_text()}")"""

if OLD_1 in src:
    src = src.replace(OLD_1, NEW_1, 1)
    applied += 1
    print("  \u2714 PATCH 1: _curvas_live — FX refresh + caption")
else:
    print("  \u2718 PATCH 1: _curvas_live — NO ENCONTRADO (ya parcheado?)")

# ═══════════════════════════════════════════════════════════════════════
# PATCH 2: _mercado_live — agregar invalidate + refresh + fx_status_text
# ═══════════════════════════════════════════════════════════════════════

OLD_2 = """        @st.fragment(run_every=refresh_interval)
        def _mercado_live():
            st.caption(f"\U0001f534 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}")"""

NEW_2 = """        @st.fragment(run_every=refresh_interval)
        def _mercado_live():
            # Refrescar FX A3500 en cada ciclo live (>>> PATCH FX 04/2026)
            invalidate_fx_cache()
            refresh_a3500_in_rentafija(session=get_session(username, password))

            st.caption(f"\U0001f534 LIVE  |  Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}  |  {fx_status_text()}" if auto_refresh else f"Actualizado: {datetime.now().strftime('%H:%M:%S')}  |  Plazo: {plazo}  |  {fx_status_text()}")"""

if OLD_2 in src:
    src = src.replace(OLD_2, NEW_2, 1)
    applied += 1
    print("  \u2714 PATCH 2: _mercado_live — FX refresh + caption")
else:
    print("  \u2718 PATCH 2: _mercado_live — NO ENCONTRADO (ya parcheado?)")

# ═══════════════════════════════════════════════════════════════════════
# PATCH 3: tab_futuros — borrar get_a3500_spot_fallback, usar get_fx_hoy
# ═══════════════════════════════════════════════════════════════════════

OLD_3 = """        def get_a3500_spot_fallback(default: float = 1300.0) -> float:
            import requests
            api_key = os.environ.get("MAE_API_KEY")
            if not api_key:
                return float(default)
            try:
                url = "https://openapi.mae.com.ar/openapi/v1/marketdata/" + "dolar"
                headers = {"X-API-Key": api_key}
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                data = res.json()
                return float(data.get("precio") or data.get("price") or default)
            except Exception:
                return float(default)

        colS1, colS2 = st.columns([1, 1])
        with colS1:
            a3500_auto = get_a3500_spot_fallback()
            a3500 = st.number_input("A3500 spot (mayorista)", value=float(a3500_auto), step=0.5)
        with colS2:
            st.caption("Si no hay MAE_API_KEY, us\u00e1 input manual.")"""

NEW_3 = """        colS1, colS2 = st.columns([1, 1])
        with colS1:
            # >>> PATCH FX 04/2026: usa get_fx_hoy() con waterfall MAE → BYMA DLR/SPOT → serie
            a3500_auto = get_fx_hoy(session=get_session(username, password))
            a3500 = st.number_input("A3500 spot (mayorista)", value=float(a3500_auto), step=0.5)
        with colS2:
            st.caption(fx_status_text())"""

if OLD_3 in src:
    src = src.replace(OLD_3, NEW_3, 1)
    applied += 1
    print("  \u2714 PATCH 3: tab_futuros — get_fx_hoy reemplaza get_a3500_spot_fallback")
else:
    print("  \u2718 PATCH 3: tab_futuros — NO ENCONTRADO (ya parcheado?)")

# ═══════════════════════════════════════════════════════════════════════
# Guardar resultado
# ═══════════════════════════════════════════════════════════════════════

with open(path, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{'='*60}")
print(f"  {applied}/3 patches aplicados exitosamente")
print(f"  Archivo guardado: {path}")
print(f"  Backup disponible: {path}.bak")
print(f"{'='*60}")

if applied < 3:
    print("\n⚠️  Algunos patches no se aplicaron.")
    print("   Posibles causas:")
    print("   - Ya fueron aplicados previamente")
    print("   - El archivo fue modificado manualmente")
    print("   - Diferencias de encoding/whitespace")
