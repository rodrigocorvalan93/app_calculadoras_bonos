"""Especie ad-hoc — parseo seguro de ficha, armado por formulario, cálculo en
vivo (reusa pricing vía obj_override), persistencia a especies.py y endpoints."""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import adhoc, bond_universe


# ── Parseo de ficha pegada ───────────────────────────────────────────────────
def test_parse_ficha_aritmetica_y_comentarios():
    """La ficha pegada admite comentarios y aritmética de listas ([0]*6 + [4]),
    que ast.literal_eval NO soporta."""
    text = '''
    # una ficha cualquiera
    AL9 = {
        "Nombre Security": "X",      # comentario inline
        "Código": "AL9",
        "Amortización": ([0]*6 + [4] + [8]*3),
        "Cupón / Spread": [0.125, 0.5],
        "Valor Nominal": 100.,
    }
    AL9 = rentafija.Bono(AL9)   # el wrapper se ignora
    '''
    name, ficha = adhoc.parse_ficha(text)
    assert name == "AL9"
    assert ficha["Código"] == "AL9"
    assert ficha["Amortización"] == [0, 0, 0, 0, 0, 0, 4, 8, 8, 8]
    assert ficha["Cupón / Spread"] == [0.125, 0.5]


def test_parse_ficha_solo_dict():
    _name, ficha = adhoc.parse_ficha('{"Código": "Z1", "Valor Nominal": 100.}')
    assert ficha["Código"] == "Z1"


@pytest.mark.parametrize("bad", [
    '{"Código": __import__("os").system("echo x")}',
    '{"Código": open("/etc/passwd").read()}',
    '{"Código": [x for x in range(3)]}',
    '{"Código": foo}',
])
def test_parse_ficha_rechaza_expresiones_peligrosas(bad):
    with pytest.raises(ValueError):
        adhoc.parse_ficha(bad)


def test_parse_ficha_sin_dict_ni_codigo():
    with pytest.raises(ValueError):
        adhoc.parse_ficha("x = 1")
    with pytest.raises(ValueError):
        adhoc.parse_ficha('{"Nombre Security": "sin codigo"}')


# ── Armado por formulario ────────────────────────────────────────────────────
def test_coupon_dates_regular():
    d = adhoc.coupon_dates(date(2025, 7, 1), date(2028, 7, 1), 2)
    assert d[-1] == date(2028, 7, 1) and d[0] > date(2025, 7, 1)
    assert len(d) == 6                                   # 3 años × semestral
    # espaciado ~6 meses
    assert (d[1].year - d[0].year) * 12 + (d[1].month - d[0].month) == 6


def test_coupon_dates_valida():
    with pytest.raises(ValueError):
        adhoc.coupon_dates(date(2028, 1, 1), date(2027, 1, 1), 2)   # venc <= emision
    with pytest.raises(ValueError):
        adhoc.coupon_dates(date(2025, 1, 1), date(2028, 1, 1), 5)   # freq no divide 12


def test_build_ficha_amortizacion_suma_vn():
    ficha = adhoc.build_ficha_from_form({
        "codigo": "ADHOCA", "emision": "01/07/2025", "vencimiento": "01/07/2028",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5",
        "tipo_amortizacion": "AMORTIZABLE", "cuotas_finales": "3", "valor_nominal": "100",
    })
    assert round(sum(ficha["Amortización"]), 6) == 100.0
    assert ficha["Fechas de cupón"][-1] == "01/07/2028"
    assert ficha["Step-up"] is False and ficha["Cupón / Spread"] == 5.0


def test_build_ficha_custom_amort_valida_largo():
    with pytest.raises(ValueError):
        adhoc.build_ficha_from_form({
            "codigo": "ADHOCB", "emision": "01/07/2025", "vencimiento": "01/07/2027",
            "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5",
            "tipo_amortizacion": "AMORTIZABLE", "amortizacion_custom": "50,50",  # 2 ≠ 4 cupones
        })


def test_build_ficha_codigo_invalido():
    with pytest.raises(ValueError):
        adhoc.build_ficha_from_form({"codigo": "no valido", "emision": "01/07/2025",
                                     "vencimiento": "01/07/2027"})


# ── Cálculo en vivo ──────────────────────────────────────────────────────────
def test_compute_fija_y_cer():
    bond_universe.ensure_loaded()   # prime rentafija.inputs (CER/A3500 del backup)
    # FIJA amortizable
    ficha = adhoc.build_ficha_from_form({
        "codigo": "ADHOCF", "emision": "01/07/2025", "vencimiento": "01/07/2028",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5",
        "tipo_amortizacion": "AMORTIZABLE", "cuotas_finales": "2", "valor_nominal": "100",
    })
    tok, code = adhoc.register(ficha)
    m = adhoc.compute(tok, "precio", 95.0)
    assert m["error"] is None
    assert m["tirea"] == m["tirea"] and m["duration"] > 0 and len(m["cashflows"]) > 0
    # inversión precio↔tir: al pedir esa TIR el precio vuelve cerca de 95
    m2 = adhoc.compute(tok, "tir", m["tirea"])
    assert abs(m2["precio_pct"] - 95.0) < 0.5

    # CER bullet: el índice aplicado es CER
    fc = adhoc.build_ficha_from_form({
        "codigo": "ADHOCC", "emision": "01/07/2025", "vencimiento": "01/07/2028",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "4", "ajuste": "CER",
        "tipo_amortizacion": "BULLET", "valor_nominal": "100",
    })
    tk2, _ = adhoc.register(fc)
    mc = adhoc.compute(tk2, "precio", 100.0)
    assert mc["error"] is None and mc["index_applied"]["kind"] == "CER"


def test_compute_token_inexistente():
    assert "error" in adhoc.compute("deadbeef", "precio", 100.0)


# ── Persistencia a especies.py (contra archivo temporal) ─────────────────────
def test_guardar_append_y_roundtrip(tmp_path, monkeypatch):
    dst = tmp_path / "especies_fake.py"
    dst.write_text("import rentafija\n", encoding="utf-8")
    monkeypatch.setattr(adhoc, "_ESPECIES_PATH", dst)
    monkeypatch.setattr(adhoc, "especie_existe", lambda name: False)

    ficha = adhoc.build_ficha_from_form({
        "codigo": "ADHOCSAVE", "emision": "01/07/2025", "vencimiento": "01/07/2027",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5", "tipo_amortizacion": "BULLET",
    })
    tok, _ = adhoc.register(ficha)
    res = adhoc.guardar(tok)
    assert res["ok"] is True and res["codigo"] == "ADHOCSAVE"
    written = dst.read_text(encoding="utf-8")
    assert "ADHOCSAVE = rentafija.Bono(ADHOCSAVE)" in written
    # el archivo entero (import + comentario + dict + wrapper) re-parsea a la ficha
    name, back = adhoc.parse_ficha(written)
    assert name == "ADHOCSAVE" and back["Código"] == "ADHOCSAVE"


def test_guardar_no_duplica_en_segundo_click(tmp_path, monkeypatch):
    """Segundo guardado del mismo código NO re-escribe el dict (especies no se
    recarga en vivo → _saved_codes lo frena)."""
    dst = tmp_path / "especies_fake2.py"
    dst.write_text("import rentafija\n", encoding="utf-8")
    monkeypatch.setattr(adhoc, "_ESPECIES_PATH", dst)
    monkeypatch.setattr(adhoc, "_saved_codes", set())
    ficha = adhoc.build_ficha_from_form({
        "codigo": "NODUP", "emision": "01/07/2025", "vencimiento": "01/07/2027",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5", "tipo_amortizacion": "BULLET",
    })
    tok, _ = adhoc.register(ficha)
    assert adhoc.guardar(tok)["ok"] is True
    res2 = adhoc.guardar(tok)
    assert res2["ok"] is False and "existe" in res2["error"].lower()
    assert dst.read_text(encoding="utf-8").count("NODUP = rentafija.Bono(NODUP)") == 1
    assert adhoc.especie_existe("NODUP") is True   # el botón desaparece tras guardar


def test_guardar_no_pisa_existente(tmp_path, monkeypatch):
    dst = tmp_path / "e.py"
    dst.write_text("import rentafija\n", encoding="utf-8")
    monkeypatch.setattr(adhoc, "_ESPECIES_PATH", dst)
    monkeypatch.setattr(adhoc, "especie_existe", lambda name: True)
    ficha = adhoc.build_ficha_from_form({
        "codigo": "DUP1", "emision": "01/07/2025", "vencimiento": "01/07/2027",
        "frecuencia": "2", "tipo_tasa": "FIJA", "cupon": "5", "tipo_amortizacion": "BULLET",
    })
    tok, _ = adhoc.register(ficha)
    res = adhoc.guardar(tok)
    assert res["ok"] is False and "existe" in res["error"].lower()


# ── Endpoints ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nueva_endpoints():
    import re
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        pg = await ac.get("/nueva")
        assert pg.status_code == 200 and "Nueva especie" in pg.text and "nueva-grid" in pg.text

        form = {"entrada": "form", "codigo": "ENDPT1", "emision": "01/07/2025",
                "vencimiento": "01/07/2028", "frecuencia": "2", "tipo_tasa": "FIJA",
                "cupon": "5", "tipo_amortizacion": "AMORTIZABLE", "cuotas_finales": "2"}
        r = await ac.post("/nueva/parse", data=form)
        assert r.status_code == 200 and "Traceback" not in r.text
        assert "TIREA" in r.text and "Cashflows" in r.text and "Guardar" in r.text
        tok = re.search(r'name="token" value="([0-9a-f]+)"', r.text).group(1)

        r2 = await ac.post("/nueva/recompute", data={"token": tok, "mode": "tir", "value": "0,30"})
        assert r2.status_code == 200 and "Traceback" not in r2.text and "Precio" in r2.text

        # error de parseo → alert
        r3 = await ac.post("/nueva/parse", data={"entrada": "pegar", "ficha_text": '{"x": 1}'})
        assert r3.status_code == 200 and "alert-error" in r3.text

        # token expirado en recompute
        r4 = await ac.post("/nueva/recompute", data={"token": "deadbeef", "mode": "precio", "value": "100"})
        assert r4.status_code == 200 and "alert-error" in r4.text
