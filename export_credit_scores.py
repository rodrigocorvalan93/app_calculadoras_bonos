#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_credit_scores.py

Exporta la hoja "Output (2)" del Excel de analistas a credit_scores.json.
Correr cada vez que los analistas actualicen el Excel.

Uso:
    python export_credit_scores.py

El Excel se busca en la ruta estándar de OneDrive de Delta.
El JSON se genera en el mismo directorio que este script
(= directorio de la app de bonos).
"""

import json
import os
from pathlib import Path

import openpyxl


def _find_excel() -> str:
    """Busca el Excel en la ruta OneDrive estándar."""
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    candidates = [
        Path(user_profile) / "DELTA ASSET MANAGEMENT S.A" / "Inversiones - Documentos"
        / "Equipo RV" / "9 - Otros" / "Corporativos Argentina - USD - Valores.xlsm",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise FileNotFoundError(
        f"No se encontró el Excel de crédito en:\n"
        + "\n".join(f"  {p}" for p in candidates)
    )


def export(excel_path: str = None, output_path: str = None):
    if excel_path is None:
        excel_path = _find_excel()
    if output_path is None:
        output_path = str(Path(__file__).parent / "credit_scores.json")

    print(f"Leyendo: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb["Output (2)"]

    def safe_float(v):
        if v is None or str(v).strip() in ('#N/A', '#VALUE!', '#REF!', '#DIV/0!'):
            return None
        try:
            return round(float(v), 6)
        except Exception:
            return None

    data = []
    for row in ws.iter_rows(min_row=7, max_row=200, min_col=1, max_col=40, values_only=True):
        if row[2] is None:
            continue

        ticker = row[37] if len(row) > 37 else None
        if ticker is None or str(ticker).strip() in ('#N/A', '#VALUE!', '#REF!', ''):
            continue
        ticker = str(ticker).strip().lower()

        last_q = row[0]
        if last_q and hasattr(last_q, 'strftime'):
            last_q = last_q.strftime('%Y-%m-%d')
        else:
            last_q = None

        r = {
            "ticker": ticker,
            "compania": str(row[2]).strip(),
            "sector": str(row[1]).strip() if row[1] else None,
            "last_q": last_q,
            "score": safe_float(row[11]),
            "score_solvencia": safe_float(row[16]),
            "score_liquidez": safe_float(row[20]),
            "net_debt_ebitda": safe_float(row[4]),
            "ebitda_net_interest": safe_float(row[5]),
            "ebitda_capex_net_interest": safe_float(row[6]),
            "current_ratio": safe_float(row[7]),
            "pasivo_pn": safe_float(row[8]),
            "liquidity_ratio": safe_float(row[9]),
            "pct_st_debt": safe_float(row[10]),
            "deuda_fin_neta_usd": safe_float(row[28]),
            "ebitda_usd": safe_float(row[29]),
            "comentario": str(row[33]).strip() if row[33] else None,
        }
        r = {k: v for k, v in r.items() if v is not None}
        data.append(r)

    wb.close()

    # Dedup por ticker (keep first = higher score)
    seen = set()
    deduped = []
    for r in data:
        t = r["ticker"]
        if t not in seen:
            seen.add(t)
            deduped.append(r)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(f"Exportados: {len(deduped)} emisores → {output_path}")
    print(f"Tamaño: {os.path.getsize(output_path):,} bytes")


if __name__ == "__main__":
    export()
