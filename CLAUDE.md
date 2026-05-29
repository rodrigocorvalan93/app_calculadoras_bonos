# Conventions for Claude

## Performance — hard target

Any user-facing endpoint in the FastAPI rewrite (`backend/`) **must stay
under 50 ms p95 server-side** for the warm-cache path. This applies to
every phase, not just YAS.

- Measure with a 50- to 100-call sweep against the warmed endpoint
  before declaring a change done. Report `avg / p50 / p95 / p99`.
- If a change pushes p95 past 50 ms, fix it (cache, precompute,
  batch, drop the feature) before pushing.
- The numbers to beat as of Fase 1 finish: YAS `/yas/recompute`
  p50 ≈ 9 ms, p95 ≈ 10 ms, p99 ≈ 11 ms. Don't regress without a reason
  stated in the commit.

## Repo branch policy

Develop on the branch supplied by the session prompt (default:
`claude/laughing-turing-yG3tA`). Never push to `main` directly — always
open a PR. Don't create the PR unless the user explicitly asks for one.

## Don't touch unless necessary

- `rentafija.py`, `especies.py`, `utils.py`, `indices.py`, `OMSapi.py`,
  `OMSmktdata.py`, `OMSprices.py` — legacy but correct. Reuse, don't
  rewrite. Fix bugs in place when needed.
- `OMSweb_app.py` — Streamlit legacy. Read-only reference for porting
  business logic. Don't import from `backend/`.

## Thread-safety pattern for `rentafija.Bono`

The bond singletons in `especies.py` mutate state on every calc
(`calcula_tirea`, `genera_ticket`, etc.). Always go through
`backend.services.pricing._bond_obj_copy(code)` (per-code lock +
`copy.copy`) before mutating, the same pattern the legacy uses in
`OMSweb_app._bond_obj_copy`.

## Locale and formatting

`es-AR`: comma decimals, period thousands separator, `DD/MM/AAAA` dates.
Use the Jinja filters in `backend/locale_ar.py`
(`ar_pct / ar_num / ar_int / ar_money / ar_date / ar_pct_pp`).

## TNA convention table

Implemented in `backend.services.pricing.tna_convention`. First match
wins:

| Tipo de bono | Convención TNA | Detección |
|---|---|---|
| Dual TAMAR | 32/365 cap | `VARIABLE_CAP` + `index == TAMAR` |
| Tasa variable pura (BADLAR / TAMAR) | 90/365 | `tipo_tasa_interes == VARIABLE` |
| CER / CER PROY | 180/365 | `"CER" in ajuste_sobre_capital` |
| UVA / UVA PROY | 180/365 | `"UVA" in ajuste_sobre_capital` |
| DLK (A3500) | 90/365 | `"A3500" in ajuste_sobre_capital` |
| Hard-dollar | 180/360 | `_is_hard_dollar(obj)` |
| LECAP / bullets ARS | días_remanentes / 365 | default |

`freq_override` + `base_override` always win over auto-detection (label
shows `… custom`).

Hard-dollar detection is **decoupled from the FX leg**: `moneda` now
encodes the quote leg (USD = cable, USB = MEP), so `_is_hard_dollar` is
true when `moneda in ("USD","USB")` **or** the classification/industria
says hard-dollar — a MEP (USB) or pesos-quoted hard-dollar bond keeps
180/360, not the días/365 default.

## FX legs and native-dollar basis (corp + sovereign USD)

A hard-dollar bond is **one ficha calculated on its native dollar**, with
up to three BYMA legs feeding it.

- **Native ficha** = the `…C` (cable) or `…D` (MEP) species, `DIRTY`,
  `Moneda` = `USD` (cable) or `USB` (MEP). This is what the BYMA curves
  price off. Globales / cable-corps: `GD30C`, `YM34C`. Bonares / MEP-corps:
  `AL30D`, `YFCND`.
- **Clean reference** (optional, for bonds with a Bloomberg/Euroclear
  quote) = the `…O` / no-suffix species, `CLEAN`, `Moneda` `USD`. **Never
  used to price a BYMA leg** — reference only (YAS manual entry / comparador).

A BYMA price's **leg** comes from its ticker suffix: `…O` / base → ARS
(pesos), `…D` → MEP (USB), `…C` → cable (USD). Every leg resolves to the
same native ficha; the price is converted **leg → ARS → native** with the
implicit rates CCL (`USD/ARS`) and MEP (`USB/ARS`) from
`backend.services.fx`:

| native ↓ \ leg → | ARS (…O) | MEP (…D) | cable (…C) |
|---|---|---|---|
| cable (`…C`, USD) | `/ CCL` | `× MEP / CCL` | — |
| MEP (`…D`, USB) | `/ MEP` | — | `× CCL / MEP` |

The native leg is a no-op, so the **basic curve is FX-free** (native ficha
+ native ticker); the FX only powers the cross-leg O/D/C view and price
fallbacks. Implemented in
`backend.services.fx.normalize_price(price, leg, native, fx)`.

## Visual style (FastAPI rewrite)

Bloomberg palette + Notion/Apple/Linear typography. System sans
everywhere; numbers use `tabular-nums` instead of monospace. Dark
default with `[data-theme="light"]` available. No frameworks (no
Tailwind / Bootstrap / Google Fonts / JS libs beyond htmx + Alpine).

## Tests

`pytest -q` at the repo root. New backend features need a smoke test
that (a) exercises the calc, (b) hits the HTTP endpoint via
`httpx.AsyncClient` with `ASGITransport`.
