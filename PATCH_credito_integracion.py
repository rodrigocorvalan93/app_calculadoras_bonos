# =============================================================================
# PATCH: Integración OMScredit en OMSweb_app.py
# =============================================================================
#
# 3 cambios puntuales. Copiar/pegar en las ubicaciones indicadas.
#
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# CAMBIO 1: Import (agregar al bloque de imports, después de "import OMSticker")
# ─────────────────────────────────────────────────────────────────────────────

import OMScredit


# ─────────────────────────────────────────────────────────────────────────────
# CAMBIO 2: En la pestaña YAS, DESPUÉS de mostrar las métricas principales
#           (después del bloque "Fila secundaria" con s1,s2,s3,s4),
#           agregar este bloque:
# ─────────────────────────────────────────────────────────────────────────────

                    # ── Crédito del emisor ──
                    credit = OMScredit.get_credit_for_bond(yas_code)
                    if credit:
                        with st.expander(
                            f"📊 Crédito emisor: {credit.get('compania', '')} — Score {credit.get('score', '?')}/5",
                            expanded=False,
                        ):
                            cr1, cr2, cr3, cr4, cr5 = st.columns(5)
                            with cr1:
                                _sc = credit.get("score")
                                st.metric("Score", f"{_sc:.1f}" if _sc else "—")
                            with cr2:
                                _sv = credit.get("score_solvencia")
                                st.metric("Solvencia", f"{_sv:.1f}" if _sv else "—")
                            with cr3:
                                _sl = credit.get("score_liquidez")
                                st.metric("Liquidez", f"{_sl:.1f}" if _sl else "—")
                            with cr4:
                                st.metric("Sector", credit.get("sector", "—"))
                            with cr5:
                                st.metric("Last Q", credit.get("last_q", "—"))

                            cr6, cr7, cr8, cr9 = st.columns(4)
                            with cr6:
                                _nd = credit.get("net_debt_ebitda")
                                st.metric("Net Debt/EBITDA", f"{_nd:.2f}x" if _nd is not None else "—")
                            with cr7:
                                _ei = credit.get("ebitda_net_interest")
                                st.metric("EBITDA/Interest", f"{_ei:.1f}x" if _ei is not None else "—")
                            with cr8:
                                _cr = credit.get("current_ratio")
                                st.metric("Current Ratio", f"{_cr:.2f}x" if _cr is not None else "—")
                            with cr9:
                                _pp = credit.get("pasivo_pn")
                                st.metric("Pasivo/PN", f"{_pp:.2f}x" if _pp is not None else "—")

                            _com = credit.get("comentario")
                            if _com:
                                st.caption(f"💬 {_com}")


# ─────────────────────────────────────────────────────────────────────────────
# CAMBIO 3: Nueva pestaña "Crédito Corp." — agregar en la lista de tabs
#           y el bloque with correspondiente.
# ─────────────────────────────────────────────────────────────────────────────

# 3a. En la línea de st.tabs, agregar "Crédito Corp." al final:
#
# ANTES:
#   tab_curvas, tab_mercado, tab_cauciones, tab_fwds, tab_graficos, tab_futuros, tab_tr, tab_yas, tab_comp, tab_breakeven = st.tabs(
#       ["Curvas", "Mercado", "Cauciones", "Forwards", "Gráficos", "Futuros", "Total Return", "Análisis Yields", "Comparador Yields", "Breakeven Inflación"]
#   )
#
# DESPUÉS:
#   tab_curvas, tab_mercado, tab_cauciones, tab_fwds, tab_graficos, tab_futuros, tab_tr, tab_yas, tab_comp, tab_breakeven, tab_credito = st.tabs(
#       ["Curvas", "Mercado", "Cauciones", "Forwards", "Gráficos", "Futuros", "Total Return", "Análisis Yields", "Comparador Yields", "Breakeven Inflación", "Crédito Corp."]
#   )

# 3b. Agregar este bloque ANTES del bloque "with tab_breakeven:" (o después, da igual):

    # ─────────────────────────
    # Crédito Corporativo
    # ─────────────────────────
    with tab_credito:
        st.subheader("Scoring Crediticio — Corporativos Argentina USD")
        st.caption(
            "Score interno (1-5) basado en ratios de solvencia y liquidez. "
            "Datos del último balance disponible. "
            "Fuente: equipo de Research RV — Delta Asset Management."
        )

        df_credit = OMScredit.get_all_issuers_df()

        if df_credit.empty:
            st.warning("No se encontró credit_scores.json. Corré export_credit_scores.py para generarlo.")
        else:
            # Filtros
            col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
            with col_f1:
                sectors = sorted(df_credit["Sector"].dropna().unique())
                sel_sector = st.multiselect("Sector", options=sectors, default=[], key="cred_sector")
            with col_f2:
                score_min = st.slider("Score mínimo", 1.0, 5.0, 1.0, 0.5, key="cred_score_min")
            with col_f3:
                solo_con_ons = st.toggle("Solo con ONs cargadas", value=False, key="cred_solo_ons")

            df_show = df_credit.copy()
            if sel_sector:
                df_show = df_show[df_show["Sector"].isin(sel_sector)]
            df_show = df_show[pd.to_numeric(df_show["Score"], errors="coerce") >= score_min]
            if solo_con_ons:
                df_show = df_show[df_show["ONs cargadas"] > 0]

            # Columnas para la tabla principal (sin comentario que es muy largo)
            cols_main = [
                "Emisor", "Ticker", "Sector", "Score", "Solvencia", "Liquidez",
                "Net Debt/EBITDA", "EBITDA/Interest", "Current Ratio",
                "Pasivo/PN", "% ST Debt", "ONs cargadas", "Last Q",
            ]
            cols_main = [c for c in cols_main if c in df_show.columns]

            st.dataframe(
                OMScredit.style_credit_table(df_show[cols_main]),
                width="stretch",
                height=min(680, 40 + 35 * len(df_show)),
            )

            # Detalle de un emisor
            st.markdown("### Detalle emisor")
            emisor_opts = df_show["Ticker"].tolist()
            if emisor_opts:
                sel_emisor = st.selectbox("Emisor", options=emisor_opts, key="cred_emisor_detail")
                credit_data = OMScredit.get_credit(sel_emisor)
                if credit_data:
                    st.markdown(f"**{credit_data.get('compania', '')}** — {credit_data.get('sector', '')}")

                    _com = credit_data.get("comentario")
                    if _com:
                        st.info(f"💬 {_com}")

                    # ONs del emisor
                    bonds = OMScredit.get_bonds_for_issuer(sel_emisor)
                    if bonds:
                        st.markdown(f"**ONs cargadas ({len(bonds)}):** {', '.join(bonds)}")

                        # Si hay datos de mercado, mostrar TIR/Duration de cada ON
                        bond_rows = []
                        settle = _settlement_date_str(plazo)
                        snap = _global_snapshot(username, password, plazo)
                        if snap is not None and not snap.empty:
                            for bond_code in bonds:
                                # Buscar en snapshot (puede ser con D para MEP)
                                bond_snap = snap[snap["Código"] == bond_code]
                                if bond_snap.empty:
                                    # Probar con D (MEP)
                                    bond_snap = snap[snap["Código"] == bond_code[:-1] + "D"]
                                if not bond_snap.empty:
                                    last_px = pd.to_numeric(bond_snap.iloc[0].get("last"), errors="coerce")
                                    if np.isfinite(last_px):
                                        m = metrics_for_price(bond_code, last_px, "hdmep", settle)
                                        bond_rows.append({
                                            "Código": bond_code,
                                            "Last": last_px,
                                            "TIREA": m.get("TIREA", np.nan),
                                            "TNA": m.get("TNA", np.nan),
                                            "Duration": m.get("Duration", np.nan),
                                        })

                        if bond_rows:
                            df_bonds = pd.DataFrame(bond_rows)
                            fmt_bonds = {
                                "Last": "{:,.4f}",
                                "TIREA": "{:.2%}",
                                "TNA": "{:.2%}",
                                "Duration": "{:.4f}",
                            }
                            st.dataframe(
                                df_bonds.style.format(fmt_bonds, na_rep="—"),
                                width="stretch",
                                height=min(400, 40 + 35 * len(df_bonds)),
                            )
                        elif bonds:
                            st.caption("Sin datos de mercado para estas ONs (mercado cerrado o sin marketdata).")
                    else:
                        st.caption("Este emisor no tiene ONs cargadas en especies.py.")
