# =============================================================================
# INTEGRACIÓN TAB CAUCIONES en OMSweb_app.py
# =============================================================================
#
# PASO 1: Agregar import al inicio del archivo (junto a los otros imports):
#
#     import OMScauciones
#
# PASO 2: Donde se definen las tabs, agregar "Cauciones":
#
#   ANTES:
#     tab_curvas, tab_mercado, tab_fwds, tab_graficos, tab_futuros, tab_tr, tab_yas, tab_comp, tab_breakeven = st.tabs(
#         ["Curvas", "Mercado", "Forwards", "Gráficos", "Futuros", "Total Return", "Análisis Yields", "Comparador Yields", "Breakeven Inflación"]
#     )
#
#   DESPUÉS:
#     tab_curvas, tab_mercado, tab_fwds, tab_graficos, tab_futuros, tab_cauciones, tab_tr, tab_yas, tab_comp, tab_breakeven = st.tabs(
#         ["Curvas", "Mercado", "Forwards", "Gráficos", "Futuros", "Cauciones", "Total Return", "Análisis Yields", "Comparador Yields", "Breakeven Inflación"]
#     )
#
# PASO 3: Agregar el bloque de abajo DESPUÉS de tab_futuros y ANTES de tab_tr.
#         Copiar todo lo que está entre los marcadores START/END:
#
# ========================= START BLOQUE CAUCIONES =========================

    # ─────────────────────────
    # Cauciones
    # ─────────────────────────
    with tab_cauciones:
        st.subheader("Monitor de Cauciones — BYMA")
        st.caption("Tasas TNA por plazo. Datos en tiempo real. Sin cálculo de TIR (se negocia directo por TNA).")

        col_cfg1, col_cfg2 = st.columns([1, 1])
        with col_cfg1:
            caucion_plazos_mode = st.radio(
                "Plazos",
                options=["Principales (1-7, 14, 21, 28, 35, 60, 90, 120)", "Todos (1 a 30)"],
                horizontal=True,
                key="caucion_plazos_mode",
            )
        with col_cfg2:
            caucion_mostrar_usd = st.toggle("Mostrar Dólares", value=False, key="caucion_usd")

        if caucion_plazos_mode.startswith("Todos"):
            plazos_cauc = list(range(1, 31))
        else:
            plazos_cauc = None  # usa default del módulo (principales)

        @st.fragment(run_every=refresh_interval)
        def _cauciones_live():
            ts = datetime.now().strftime("%H:%M:%S")
            st.caption(
                f"🔴 LIVE  |  Actualizado: {ts}" if auto_refresh
                else f"Actualizado: {ts}"
            )

            session = get_session(username, password)

            # ── Pesos ──
            st.markdown("### Cauciones en Pesos (ARS)")
            df_pesos = OMScauciones.fetch_cauciones(session, moneda="PESOS", plazos=plazos_cauc)
            if df_pesos is None or df_pesos.empty:
                st.info("Sin datos de cauciones en pesos (mercado cerrado o sin respuesta).")
            else:
                st.dataframe(
                    OMScauciones.style_cauciones(df_pesos),
                    width="stretch",
                    height=min(520, 40 + 35 * len(df_pesos)),
                )

            # ── Dólares (toggle) ──
            if caucion_mostrar_usd:
                st.markdown("### Cauciones en Dólares (USD)")
                df_usd = OMScauciones.fetch_cauciones(session, moneda="DOLAR", plazos=plazos_cauc)
                if df_usd is None or df_usd.empty:
                    st.info("Sin datos de cauciones en dólares (poca liquidez o mercado cerrado).")
                else:
                    st.dataframe(
                        OMScauciones.style_cauciones(df_usd),
                        width="stretch",
                        height=min(520, 40 + 35 * len(df_usd)),
                    )

        _cauciones_live()

# ========================= END BLOQUE CAUCIONES ===========================
