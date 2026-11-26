"""Atribución del rendimiento (pestaña Fondos): conversor de carteras diarias,
motor de contribuciones y ruta.

La fixture arma `Delta Bases` como `test_fondos` y le suma `Carteras/AAAAMMDD`
con dos Excel por día (composición con las 37 columnas reales + PN) para el
fondo ESCO 13 (Ahorro Plus, CAFCI 473): un bono que sube, uno que baja y se
compra a mitad de camino, un plazo fijo y un cheque que vencen, una acción con
un cambio de unidad y un bono que corta cupón. Los números esperados salen de
una cuenta independiente (diccionarios, sin numpy) de la misma definición.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import fondos as fsvc
from backend.services import fondos_attr as fattr
from backend.services import fondos_calc as fc
from backend.tools import fondos_carteras as fcart
from tests.test_fondos import R_AHORRO, R_BM_AHORRO, _armar_bases

COLS = ("Fecha CodFondo IsinCode Cod_Delta Instrumento Pago Geografía Ajuste Tasa Inversion|Sector Delta|Emisor / Sponsor|"
        "Clase de Activo|CNV_Local_Extranjero|Califica_Local|Call_Tiene|Fecha_Call|BLOOM|REUTERS|Precio_Elegido|CAFCI_BYMA|"
        "Plazo_Precio|Clasificacion_especifico|CAFCI_Nivel0|CAFCI_Nivel1|CAFCI_Nivel2|Vencimiento|Cantidad|Valor|Clasifica|"
        "Clasifica_Nivel2|Mesa_Nivel0|Mesa_Nivel1|Mesa_Nivel2|Mesa_Nivel3|Apertura|Clasifica_FCT").split("|")
COLS = COLS[0].split(" ")[:-1] + ["Inversion"] + COLS[1:]
HOY = dt.date(2026, 11, 26)
DIAS = [str(x)[:10] for x in pd.bdate_range("2026-11-02", "2026-11-25")]          # 18 ruedas
PN0 = 10_000_000_000.0
I_COMPRA, I_PF, I_CHEQUE, I_SALTO, I_CUPON = 6, 9, 12, 7, 10                      # índices de DIAS


def _tenencias(i: int) -> list:
    """Tenencias del fondo 13 al cierre de DIAS[i]: (isin, ticker, instr, ajuste, tasa, inversion, sector, vto, Q, V, clasif)."""
    gap = (dt.date.fromisoformat(DIAS[i]) - dt.date.fromisoformat(DIAS[0])).days
    out = [
        ("AR0000000001", "TZXD7", "Bonos", "CER", "Fija", "Boncer cero cupón 2027", "Government", "2027-12-15",
         1_000_000_000.0, 1_000_000_000.0 * 2.9 * 1.002 ** i, "Bonos Soberano CER Fija"),
        ("AR0000000002", "TMF28", "Bonos", "ARS", "TAMAR", "Bono TAMAR 2028", "Government", "2028-02-29",
         (500_000_000.0 if i < I_COMPRA else 800_000_000.0), (500_000_000.0 if i < I_COMPRA else 800_000_000.0) * 1.1 * 0.999 ** i,
         "Bonos Soberano ARS TAMAR"),
        ("AR0000000003", "CUPON", "Bonos", "USD-Linked", "Fija", "ON con cupón & amortización", "Petroleo & Gas", "2028-06-30",
         400_000_000.0, 400_000_000.0 * (1.05 if i < I_CUPON else 1.00) * 1.001 ** i, "Bonos Corporativo USD-Linked Fija"),
        ("ARXXXXXXXXXX", "GGAL AR", "Acciones", "NC", "NC", "GGAL AR / GRUPO FINANCIERO GALICIA", "Bancos", "",
         (10_000.0 if i < I_SALTO else 100_000.0), 10_000.0 * 7000.0 * 1.003 ** i, "Acciones"),
    ]
    if i < I_PF:                                   # plazo fijo: vence en DIAS[I_PF] (ese día ya no está)
        out.append(("Sin_Isin", "NC", "Plazos Fijos", "ARS", 36.5, "Plazos Fijos - BANCO X - 2026-11-02", "Caja y Equivalentes",
                    DIAS[I_PF], 1_000_000_000.0, 1_000_000_000.0 * (1 + 0.365 * gap / 365.0), "Plazos Fijos"))
    if i < I_CHEQUE:                               # cheque: descuento que llega a la par el día que vence
        falta = (dt.date.fromisoformat(DIAS[I_CHEQUE]) - dt.date.fromisoformat(DIAS[i])).days
        out.append(("Sin_Isin", "NC", "Cheques No Garantizados", "ARS", "NC", "*MAV999", "Otros", DIAS[I_CHEQUE],
                    200_000_000.0, 200_000_000.0 / (1 + 0.40 * falta / 365.0), "Cheques y Pagares"))
    return out


def _pn(i: int) -> float:
    return PN0 * 1.0007 ** i


def _armar_carteras(base) -> None:
    for i, dia in enumerate(DIAS):
        carpeta = base / "Carteras" / dia.replace("-", "")
        carpeta.mkdir(parents=True)
        filas = []
        for cod in (13, 4):                        # el 4 lleva la misma cartera: prueba el filtro por fondo
            ten = _tenencias(i)
            caja = _pn(i) - sum(t[9] for t in ten)
            ten.append(("Sin_Isin", "$", "Cuenta Corriente", "ARS", "NC", "BANCO X $", "Caja y Equivalentes", "", caja, caja,
                        "Caja y Equivalentes"))
            for isin, tk, instr, aj, tasa, inv, sector, vto, q, v, clasif in ten:
                fila = dict.fromkeys(COLS, "NC")
                fila.update({"Fecha": dia, "CodFondo": cod, "IsinCode": isin, "Cod_Delta": tk, "Instrumento": instr,
                             "Pago": "en Pesos", "Ajuste": aj, "Tasa": tasa, "Inversion": inv, "Sector Delta": sector,
                             "Vencimiento": pd.Timestamp(vto) if vto else None, "Cantidad": q, "Valor": v, "Clasifica": clasif})
                filas.append(fila)
        d8 = dia.replace("-", "")
        pd.DataFrame(filas, columns=COLS).to_excel(carpeta / f"{d8}_Delta_Composicion.xlsx", index=False)
        pd.DataFrame({"CodFondo": [13, 4, 99], "PN": [_pn(i), _pn(i), 1.0]}).to_excel(carpeta / f"{d8}_Delta_PN.xlsx", index=False)
    (base / "Carteras" / "Delta_Composicion.xlsx").write_bytes(b"no es una carpeta de dia")
    (base / "Carteras" / "20261199bis").mkdir()    # carpeta sin composición: se ignora


def _esperado(i0: int, i1: int, vcp, con_cupon: bool = True) -> dict:
    """La misma definición, a mano: contribución por tenencia entre DIAS[i0] y DIAS[i1]."""
    c: dict = {}
    w_abre: dict = {}
    for i in range(i0 + 1, i1 + 1):
        ayer = {(t[0], t[1], t[5], t[7]): t for t in _tenencias(i - 1)}
        hoy = {(t[0], t[1], t[5], t[7]): t for t in _tenencias(i)}
        F = vcp[i - 1] / vcp[i0]
        gap = (dt.date.fromisoformat(DIAS[i]) - dt.date.fromisoformat(DIAS[i - 1])).days
        for k, t in ayer.items():
            w = t[9] / _pn(i - 1)
            p0 = t[9] / t[8]
            if k in hoy:
                r = (hoy[k][9] / hoy[k][8]) / p0 - 1.0
                if k[1] == "CUPON" and i == I_CUPON and con_cupon:
                    r += 0.05 / p0                              # el cobro por VN del cronograma
                if abs(r) > fattr.SALTO:
                    r = 0.0
            elif t[2] == "Plazos Fijos":
                r = 36.5 / 100 * gap / 365.0
            elif t[2].startswith("Cheques"):
                r = 1.0 / p0 - 1.0
            else:
                r = 0.0
            lbl = k[1] if k[1] != "NC" else k[2]
            c[lbl] = c.get(lbl, 0.0) + w * r * F
            w_abre[lbl] = w_abre.get(lbl, 0.0) + w
    return {"c": c, "w": {k: v / (i1 - i0) for k, v in w_abre.items()}}


@pytest.fixture()
def bases(tmp_path, monkeypatch):
    base = tmp_path / "Delta Bases"
    _armar_bases(base)
    _armar_carteras(base)
    monkeypatch.setenv("FONDOS_BASES_DIR", str(base))
    monkeypatch.setenv("FONDOS_PREFS_PATH", str(tmp_path / "fondos_prefs.json"))
    monkeypatch.setenv("FONDOS_ATTR_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("FONDOS_ATTR_SUBPROCESO", "0")
    monkeypatch.setenv("FONDOS_ATTR_DIAS", "4000")           # la suite corre cualquier día: la ventana no poda nada
    fsvc.reset()
    fattr.reset()
    d = fsvc.cargar_ahora()
    assert d is not None, fsvc.estado()
    # cronograma de la ficha del bono con cupón (la fixture no tiene ese bono en el universo)
    cupon = np.datetime64(DIAS[I_CUPON])
    monkeypatch.setattr(fattr, "_pagos", lambda tk, isin, pago: ([(cupon + 1, 0.05)], False) if tk == "CUPON" else None)
    from backend.routes import fondos as rf
    rf._memo.clear()
    yield d
    fsvc.reset()
    fattr.reset()
    rf._memo.clear()


# ── conversor ────────────────────────────────────────────────────────────────
def test_lector_rapido_igual_a_pandas(tmp_path):
    df = pd.DataFrame({"CodFondo": [4, 13, 13, 7], "Inversion": ["A & B <x>", "ñandú «1»", None, "Plazos, con coma"],
                       "Cantidad": [1.5, 0, 2e9, None], "Valor": [10.25, -3.5, 1e12, 7],
                       "Vencimiento": [pd.Timestamp("2028-12-15"), None, pd.Timestamp("2027-01-16"), None], "Otra": list("abcd")})
    # (a) como lo escribe pandas (texto en línea) y (b) con tabla de textos compartidos (openpyxl a mano / Excel)
    a = tmp_path / "a.xlsx"
    df.to_excel(a, index=False)
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(list(df.columns))
    for fila in df.itertuples(index=False):
        ws.append([None if (v is None or v != v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in fila])
    b = tmp_path / "b.xlsx"
    wb.save(b)
    for p in (a, b):
        got = fcart.leer_xlsx_rapido(str(p), ["CodFondo", "Inversion", "Cantidad", "Valor", "Vencimiento"])
        assert got["CodFondo"] == [4.0, 13.0, 13.0, 7.0]
        assert got["Inversion"] == ["A & B <x>", "ñandú «1»", None, "Plazos, con coma"]
        assert got["Cantidad"] == [1.5, 0.0, 2e9, None] and got["Valor"] == [10.25, -3.5, 1e12, 7.0]
        assert [fcart._fecha(v) for v in got["Vencimiento"]] == ["2028-12-15", "", "2027-01-16", ""]
        with pytest.raises(fcart.FormatoInesperado):
            fcart.leer_xlsx_rapido(str(p), ["CodFondo", "No existe"])
    # un archivo que no es xlsx cae al lector de pandas, que explica el error
    malo = tmp_path / "malo.xlsx"
    malo.write_bytes(b"esto no es un zip")
    with pytest.raises(Exception):
        fcart.leer_xlsx(str(malo), ["CodFondo"])


def test_conversor_arma_el_cache_y_es_incremental(bases, tmp_path):
    cart = str(tmp_path / "Delta Bases" / "Carteras")
    out = str(tmp_path / "cache2")
    dias = fcart.dias_disponibles(cart)
    assert [d[0] for d in dias] == [x.replace("-", "") for x in DIAS] and all(d[2] for d in dias)
    r = fcart.correr(cart, out, 30, hoy=HOY)
    assert (r["total"], r["hechos"], r["errores"]) == (18, 18, []) and r["lectores"] == {"rapido": 18}
    un_dia = pd.read_parquet(f"{out}/20261125.parquet")
    assert set(un_dia.columns) == {"cod", "isin", "ticker", "inv", "instr", "ajuste", "pago", "sector", "clasif", "vto",
                                   "tasa", "q", "v"}
    f13 = un_dia[un_dia["cod"] == 13]
    assert len(f13) == 4 + 1 + 1 and set(un_dia["cod"]) == {4, 13, 99}        # 4 títulos + caja + la fila de PN
    assert float(f13[f13["instr"] == fcart.FILA_PN]["v"].iloc[0]) == pytest.approx(_pn(17))
    assert f13[f13["ticker"] == "TZXD7"]["vto"].iloc[0] == "2027-12-15"
    # segunda corrida: nada que hacer; un Excel que cambia se reconvierte; lo viejo se poda
    assert fcart.correr(cart, out, 30, hoy=HOY)["total"] == 0
    p = tmp_path / "Delta Bases" / "Carteras" / "20261110" / "20261110_Delta_PN.xlsx"
    pd.DataFrame({"CodFondo": [13], "PN": [5.0]}).to_excel(p, index=False)
    assert fcart.correr(cart, out, 30, hoy=HOY)["total"] == 1
    r = fcart.correr(cart, out, 10, hoy=HOY)                                   # ventana de 10 días: desde el 16/11
    assert r["total"] == 0 and sorted(x[:8] for x in os.listdir(out) if x.endswith(".parquet"))[0] == "20261116"
    assert fcart.main(["--carteras", str(tmp_path / "no-existe"), "--out", out, "--quiet"]) == 2


def test_conversor_como_proceso_aparte(bases, tmp_path, monkeypatch):
    """El camino de producción: `python -m backend.tools.fondos_carteras` sin importar el backend."""
    import subprocess
    out = tmp_path / "cache3"
    r = subprocess.run([sys.executable, "-m", "backend.tools.fondos_carteras", "--carteras",
                        str(tmp_path / "Delta Bases" / "Carteras"), "--out", str(out), "--dias", "4000", "--max", "3"],
                       cwd=str(fattr.REPO_ROOT), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in out.glob("*.parquet")) == ["20261123.parquet", "20261124.parquet", "20261125.parquet"]
    assert "3 día(s)" in r.stdout


# ── motor ────────────────────────────────────────────────────────────────────
def test_atribucion_contra_la_cuenta_a_mano(bases):
    d = bases
    est = fattr.armar_ahora()
    assert est["listo"] and not est["cargando"] and est["error"] is None
    fa = fattr.fondo(d, 473)
    assert fa is not None and [str(x) for x in fa.dias] == DIAS
    assert fa.pn == pytest.approx([_pn(i) for i in range(18)])
    col = d.col(473)
    y = d.vcp[:, col]
    pos = np.searchsorted(d.fechas, fa.dias)
    i1 = len(d.fechas) - 1
    i0 = int(pos[0])
    res = fattr.atribucion(fa, d, 473, None, "bm", i0, i1, "clasif")
    esp = _esperado(0, 17, y[pos])
    assert (res["desde"], res["hasta"], res["ruedas"], res["recortada"]) == (DIAS[0], DIAS[-1], 17, False)
    assert res["total"] == pytest.approx(y[i1] / y[i0] - 1) and res["total"] == pytest.approx((1 + R_AHORRO) ** 17 - 1, rel=1e-4)
    assert res["cartera"] == pytest.approx(sum(esp["c"].values()), rel=1e-9)
    assert res["cartera"] + res["residual"] == pytest.approx(res["total"], abs=1e-15)
    # por activo
    act = {r["nombre"]: r for r in res["suben"] + res["bajan"]}
    for lbl in ("TZXD7", "TMF28", "CUPON", "GGAL AR", "Plazos Fijos - BANCO X - 2026-11-02", "*MAV999"):
        assert act[lbl]["c"] == pytest.approx(esp["c"][lbl], rel=1e-9), lbl
        assert act[lbl]["w_prom"] == pytest.approx(esp["w"][lbl], rel=1e-9), lbl
    assert act["TMF28"]["c"] < 0 < act["TZXD7"]["c"] and act["TZXD7"]["grupo"] == "Bonos Soberano CER Fija"
    assert act["TZXD7"]["desc"] == "Boncer cero cupón 2027"
    # el bono que sube 0,2 % por rueda: retorno ≈ contribución ÷ peso
    assert act["TZXD7"]["ret"] == pytest.approx(1.002 ** 17 - 1, rel=0.02)
    # por tipo de activo: suma lo mismo, y la caja pesa pero no rinde
    grupos = {g["nombre"]: g for g in res["grupos"]}
    assert sum(g["c"] for g in res["grupos"]) == pytest.approx(res["cartera"], rel=1e-12)
    assert grupos["Caja y Equivalentes"]["c"] == 0.0 and grupos["Caja y Equivalentes"]["w_prom"] > 0.3
    assert grupos["Plazos Fijos"]["w_hoy"] == 0.0
    assert grupos["Plazos Fijos"]["c"] == pytest.approx(esp["c"]["Plazos Fijos - BANCO X - 2026-11-02"])
    assert grupos["Bonos Soberano CER Fija"]["w_hoy"] == pytest.approx(_tenencias(17)[0][9] / _pn(17))
    assert res["peso_abierto"] == pytest.approx(1.0, abs=1e-9)                 # la caja cierra el patrimonio
    # contra el benchmark: aporte = peso × (retorno − referencia); la cartera entera le saca cartera − benchmark
    assert res["ref"] == "75% Badlar + 25% A3500" and res["bench"] == pytest.approx((1 + R_BM_AHORRO) ** 23 - 1)
    assert res["exceso"] == pytest.approx(res["total"] - res["bench"])
    bv = d.bench[473][pos]
    aporte_bm = sum((bv[i] / bv[i - 1] - 1.0) * y[pos][i - 1] / y[pos][0] for i in range(1, 18))
    assert res["exceso_cartera"] == pytest.approx(res["cartera"] - aporte_bm, rel=1e-9)
    assert sum(g["e"] for g in res["grupos"]) == pytest.approx(res["exceso_cartera"], rel=1e-9)
    # honorario (1,5 % de la clase B) estimado por día corrido
    assert res["fee"] == pytest.approx(0.015) and res["fee_est"] == pytest.approx(-0.015 / 365 * 23, rel=0.02)
    assert res["otros"] == pytest.approx(res["residual"] - res["fee_est"])
    # reglas: un cobro sumado, dos vencimientos devengados, un salto sin atribuir (y a la vista)
    assert (res["cobros"], res["vencidos"], res["sin_precio"]) == (1, 2, 0)
    assert [(s["activo"], s["fecha"]) for s in res["saltos"]] == [("GGAL AR", DIAS[I_SALTO])]
    assert res["saltos"][0]["r"] == pytest.approx(1.003 / 10 - 1)
    # series del gráfico: cuotaparte vs cartera, y los grupos acumulados terminan en su contribución
    s = res["serie"]
    assert len(s["x"]) == len(s["fondo"]) == len(s["cartera"]) == 18 and s["fondo"][0] == 0.0 and s["cartera"][0] == 0.0
    assert s["cartera"][-1] == pytest.approx(res["cartera"] * 100, abs=1e-3)
    assert s["grupos"][0]["nombre"] == res["grupos"][0]["nombre"]
    assert s["grupos"][0]["y"][-1] == pytest.approx(res["grupos"][0]["c"] * 100, abs=1e-3)


def test_atribucion_ventanas_dimensiones_y_sin_ficha(bases, monkeypatch):
    d = bases
    fattr.armar_ahora()
    fa = fattr.fondo(d, 473)
    pos = np.searchsorted(d.fechas, fa.dias)
    y = d.vcp[:, d.col(473)][pos]
    i1 = len(d.fechas) - 1
    # ventana corta (últimas 5 ruedas): sin cupón ni vencimientos adentro
    res = fattr.atribucion(fa, d, 473, None, "bm", int(pos[12]), i1, "ajuste")
    esp = _esperado(12, 17, y)
    assert res["cartera"] == pytest.approx(sum(esp["c"].values()), rel=1e-9) and (res["cobros"], res["vencidos"]) == (0, 0)
    assert {g["nombre"] for g in res["grupos"]} == {"CER", "ARS", "USD-Linked", "NC"}
    # la ventana pedida arranca antes que las carteras: se recorta y se dice
    i_ytd = fc.corte_periodo(d.fechas, i1, "ytd")
    largo = fattr.atribucion(fa, d, 473, None, "bm", i_ytd, i1, "instr")
    assert largo["recortada"] and largo["desde"] == DIAS[0] and largo["pedido_desde"] == "2025-12-31"
    assert {g["nombre"] for g in largo["grupos"]} >= {"Bonos", "Acciones", "Plazos Fijos", "Cuenta Corriente"}
    # sin dos carteras en la ventana → None; una dimensión desconocida cae a la de default
    assert fattr.atribucion(fa, d, 473, None, "bm", i1, i1) is None
    assert fattr.atribucion(fa, d, 473, None, "bm", int(pos[12]), i1, "zzz")["dim"] == "clasif"
    # sin ficha (o sin corte visible en el precio) el cobro NO se inventa: el día del cupón queda como una caída
    monkeypatch.setattr(fattr, "_pagos", lambda *a: None)
    fattr.reset()
    fattr.armar_ahora()
    fb = fattr.fondo(d, 473)
    sin = fattr.atribucion(fb, d, 473, None, "bm", int(pos[0]), i1, "clasif")
    esp_sin = _esperado(0, 17, y, con_cupon=False)
    assert sin["cobros"] == 0 and sin["cartera"] == pytest.approx(sum(esp_sin["c"].values()), rel=1e-9)
    assert {r["nombre"]: r for r in sin["bajan"]}["CUPON"]["c"] == pytest.approx(esp_sin["c"]["CUPON"])
    # un fondo sin código de ESCO o sin carteras no tiene atribución
    assert fattr.fondo(d, 709) is None and fattr.fondo(d, 446) is None and fattr.fondo(d, 99999) is None


def test_cobro_en_dolares_en_un_fondo_en_pesos_usa_el_ccl(bases, monkeypatch):
    cupon = np.datetime64(DIAS[I_CUPON])
    # el bono paga 0,00005 USD por VN; con CCL = 1000 son los mismos 0,05 pesos por VN
    monkeypatch.setattr(fattr, "_pagos", lambda tk, isin, pago: ([(cupon, 0.00005)], True) if tk == "CUPON" else None)
    fattr.armar_ahora()
    arch = fattr._archivos()
    con = fattr._armar_fondo(13, arch, "ARS", lambda f: 1000.0)
    sin_fx = fattr._armar_fondo(13, arch, "ARS", None)
    assert int((con.ev_flag == fattr.F_COBRO).sum()) == 1 and int((sin_fx.ev_flag == fattr.F_COBRO).sum()) == 0
    e = int(np.flatnonzero(con.ev_flag == fattr.F_COBRO)[0])
    assert con.ev_r[e] == pytest.approx(1.0 / 1.05 * 1.001 - 1 + 0.05 / (1.05 * 1.001 ** (I_CUPON - 1)), rel=1e-9)
    # en un fondo en dólares el mismo cronograma va sin convertir (no hace falta el CCL)
    usd = fattr._armar_fondo(13, arch, "USD", None)
    e = int(np.flatnonzero(usd.ev_flag == fattr.F_COBRO)[0])
    assert usd.ev_r[e] == pytest.approx(1.0 / 1.05 * 1.001 - 1 + 0.00005 / (1.05 * 1.001 ** (I_CUPON - 1)), rel=1e-9)


def test_estado_sin_carpeta_de_carteras(tmp_path, monkeypatch):
    base = tmp_path / "Delta Bases"
    _armar_bases(base)
    monkeypatch.setenv("FONDOS_BASES_DIR", str(base))
    monkeypatch.setenv("FONDOS_ATTR_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("FONDOS_ATTR_SUBPROCESO", "0")
    fsvc.reset()
    fattr.reset()
    d = fsvc.cargar_ahora()
    est = fattr.armar_ahora()
    assert not est["listo"] and "Carteras" in est["error"]
    assert fattr.fondo(d, 473) is None
    fsvc.reset()
    fattr.reset()


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_http_atribucion(bases):
    fattr.armar_ahora()
    async with _client() as ac:
        det = await ac.get("/fondos/detalle", params={"f": 473, "rango": "d30"})
        assert "/fondos/atribucion?f=473&clase=B&vs=bm&rango=d30" in det.text.replace("&amp;", "&")
        r = await ac.get("/fondos/atribucion", params={"f": 473, "rango": "d30"})
        assert r.status_code == 200
        for txt in ("Explicado por la cartera", "Sin explicar", "Bonos Soberano CER Fija", "TZXD7", "Lo que más sumó",
                    "Lo que más restó", "TMF28", "1 cobro(s) de cupón", "2 vencimiento(s)", "GGAL AR", "vs referencia",
                    "Honorarios (estimado, adm. 1,50%)", "empiezan el 02/11/2026", "application/json"):
            assert txt in r.text, txt
        assert r.text.count("data-fondos-chart") == 2 and "Armando la historia" not in r.text
        assert "ON con cupón &amp; amortización" in r.text                     # la descripción va escapada
        aj = await ac.get("/fondos/atribucion", params={"f": 473, "rango": "d30", "dim": "ajuste", "vs": "cer"})
        assert aj.status_code == 200 and "USD-Linked" in aj.text and "vs CER" in aj.text
        assert 'class="seg-btn active" hx-get="/fondos/atribucion?f=473&amp;clase=&amp;vs=cer' in aj.text
        # el fondo 4 de ESCO (Renta) comparte los Excel: sale su propia atribución, con su benchmark
        renta = await ac.get("/fondos/atribucion", params={"f": 369, "rango": "d30"})
        assert "Badlar Privada + 200 bps" in renta.text and "Explicado por la cartera" in renta.text
        # fondo sin carteras / inexistente / ventana sin carteras: un vacío con la causa
        for params, txt in (({"f": 446}, "No hay carteras diarias de este fondo"),
                            ({"f": 709}, "No hay carteras diarias de este fondo"),
                            ({"f": 99999}, "No encontré ese fondo"),
                            ({"f": 473, "desde": "2025-03-03", "hasta": "2025-03-31"}, "No hay dos carteras")):
            x = await ac.get("/fondos/atribucion", params=params)
            assert x.status_code == 200 and txt in x.text, (params, x.text[:300])
        assert (await ac.get("/fondos/atribucion", params={"f": 473, "dim": "<x>", "rango": "??", "desde": "x"})).status_code == 200


@pytest.mark.asyncio
async def test_http_atribucion_mientras_se_arma_el_cache(bases, monkeypatch):
    """Con el caché armándose el bloque se vuelve a pedir solo y muestra el avance."""
    monkeypatch.setattr(fattr, "asegurar", lambda: {"cargando": True, "listo": False, "error": None, "version": 1,
                                                    "progreso": {"total": 250, "hechos": 37}})
    async with _client() as ac:
        r = await ac.get("/fondos/atribucion", params={"f": 473})
        assert r.status_code == 200 and "Armando la historia de carteras" in r.text
        assert "<b>37</b> de 250 días" in r.text and 'hx-trigger="load delay:4s"' in r.text
