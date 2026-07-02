"""BYMA symbol helpers — same conventions the legacy app uses.

`MERV - XMEV - <code> - <plazo>` where plazo is `24hs` or `CI`. We
strip the calc-only suffixes `j` / `v` (used in `especies.py` to host
projected-CER and dual-TAMAR variants) before building the ticker —
those have no market-data counterpart.

El strip es CASE-SENSITIVE (sólo `j`/`v` minúscula): los sufijos de calc de
`especies.py` son siempre minúscula (`TX26j`, `TXMD9v`), mientras que los tickers
REALES de BYMA terminan en mayúscula. Un strip case-insensitive mutilaba
`SUPV` (Grupo Supervielle) → "SUP", que no existe → nunca levantaba precio.
"""
from __future__ import annotations

from typing import Iterable, List


def calc_to_md_code(calc_code: str) -> str:
    """`TX26j` / `TXMD9v` → `TX26` / `TXMD9` (strip los sufijos de calc j/v).

    Case-sensitive a propósito: `SUPV`/`METR`/etc. (tickers reales en mayúscula)
    NO se tocan; sólo se strippea la `j`/`v` minúscula de las variantes de calc."""
    c = str(calc_code).strip()
    return c[:-1] if c.endswith(("j", "v")) else c


def md_symbol(code: str, plazo: str = "24hs") -> str:
    base = calc_to_md_code(code)
    suf = "24hs" if str(plazo).lower().startswith("24") else "CI"
    return f"MERV - XMEV - {base} - {suf}"


def md_symbols(codes: Iterable[str], plazo: str = "24hs") -> List[str]:
    seen: set = set()
    out: List[str] = []
    for c in codes:
        s = md_symbol(c, plazo)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
