"""Posiciones — clasificación fina de tenencias SIN ficha en especies.py
(services.clasificacion): tipo de instrumento por texto (plazo fijo, caución,
cheques, pagarés, fideicomisos, FCI), Ajuste × Tasa de 'Delta - Especies' y
Clase de Activo como último recurso. Antes todo eso caía a la Clase cruda del
Excel: en Delta Ahorro, 'Renta Fija' 47 % del PN en una sola línea."""
from __future__ import annotations

import pytest

from backend.services import clasificacion as C


def _cl(esp, clase=None, info=None, cod=None) -> str:
    return C.clasificar(esp, clase, info, cod)[0]


def test_tipo_por_descripcion_con_tildes_y_abreviaturas() -> None:
    assert _cl("PLAZO FIJO BANCO MACRO 15/10/2026", "Renta Fija") == "Plazos Fijos"
    assert _cl("P.FIJO UVA BANCO NACION", "Renta Fija") == "Plazos Fijos UVA"
    assert _cl("CAUCIÓN COLOCADORA 7 DÍAS", "Renta Fija") == "Caución"
    assert _cl("CHEQUE PAGO DIFERIDO NO GARANTIZADO 05/11/26", "Renta Fija") == "Cheques No Garantizados"
    assert _cl("CPD AVALADO SGR 12/11/26", "Renta Fija") == "Cheques Garantizados"
    assert _cl("ECHEQ 30/11/26", "Renta Fija") == "Cheques"            # sin dato de garantía: no se inventa
    assert _cl("PAGARÉ BURSÁTIL NO GARANTIZADO 20/12/26", "Renta Fija") == "Pagarés No Garantizados"
    assert _cl("PAGARE AVALADO 20/12/26", "Renta Fija") == "Pagarés Garantizados"
    assert _cl("FF SECUBONO 250 VDF A BADLAR", "Renta Fija") == "Fideicomisos TAMAR/BADLAR"
    assert _cl("FIDEICOMISO FINANCIERO ABC VDFB", "Renta Fija") == "Fideicomisos Financieros"
    assert _cl("FCI CERRADO INFRAESTRUCTURA", "Renta Fija") == "FCI Cerrados"
    assert _cl("FCI DELTA PESOS CLASE B", "Liquidez") == "FCI Money Markets"
    assert _cl("FONDO COMUN DE INVERSION XYZ", "Renta Fija") == "FCI"
    # un ON común no matchea ningún tipo: sigue la cadena (base → clase)
    assert C.clasificar("ON YPF CLASE XX 2027", "Renta Fija") == ("Renta Fija", "sin_regla")
    assert C.clasificar("OTROS ACTIVOS NETOS", "Otros Activos Netos") == ("Otros Activos Netos", "sin_regla")
    assert C.clasificar("", "") == ("(sin clasif.)", "clase")
    assert C.clasificar(None, "Acciones") == ("Acciones", "clase")
    assert C.clasificar("APPLE", "CEDEARs") == ("CEDEARs", "clase")


def test_liquidez_fci_por_codigo_vs_caja() -> None:
    """Delta valúa los FCI de liquidez con ticker + cuotapartes; la caja va
    con códigos tipo '$' / 'USD' (o sin código) y sigue siendo Liquidez."""
    assert C.clasificar("DELTA PESOS CLASE B", "Liquidez", None, "DELPESB") == ("FCI Money Markets", "clase")
    assert C.clasificar("CAJA PESOS", "Liquidez", None, "$") == ("Liquidez", "sin_regla")
    assert _cl("DOLARES", "Liquidez", None, "USD") == "Liquidez"
    assert _cl("CAJA", "Liquidez", None, None) == "Liquidez"


def test_base_delta_especies_ajuste_tasa_y_tipo() -> None:
    on_tamar = {"Ajuste": "ARS", "Tasa": "TAMAR", "Subclase de Activo": "Obligación Negociable"}
    assert C.clasificar("ON FANTASMA TAMAR", "Renta Fija", on_tamar, "ZONT1") == ("ON ARS TAMAR", "base")
    assert C.clasificar("ON X", "Renta Fija", {"Ajuste": "En pesos", "Tasa": "Fija"}) == ("ON ARS Fija", "base")
    # soberano / sub-soberano sin ficha: por la taxonomía de la base o la Clase del Excel
    sob = {"Ajuste": "CER", "Tasa": "Fija", "Subclase de Activo": "Títulos Públicos"}
    assert C.clasificar("BONCER 2027", "Títulos Públicos", sob, "TZZ27") == ("Soberano CER", "base")
    prov = {"Ajuste": "USD", "Tasa": "Fija", "Subclase de Activo": "Bono Provincial"}
    assert _cl("PROVINCIA DE X 2032", "Títulos Públicos", prov, "PXX32") == "Sub-soberano USD"
    assert _cl("LETRA X", "Títulos Públicos", {"Ajuste": "ARS", "Tasa": "Fija"}) == "Soberano ARS Fija"
    assert _cl("X", "", {"Ajuste": "ARS", "Tasa": "TAMAR"}) == "ARS TAMAR"        # nadie dice el emisor: sin prefijo
    # port de OMSposiciones._categoria_bono, con las etiquetas de las fichas
    assert C.categoria_ajuste_tasa("CER", "Fija") == "CER"
    assert C.categoria_ajuste_tasa("UVA", "Fija") == "UVA"
    assert C.categoria_ajuste_tasa("USD-Linked", "Fija") == "USD-Linked"
    assert C.categoria_ajuste_tasa("USD", "") == "USD" and C.categoria_ajuste_tasa("USB", None) == "USB"
    assert C.categoria_ajuste_tasa("Dual (CER/TAMAR)", "") == "Dual CER / TAMAR"
    assert C.categoria_ajuste_tasa("Dual (Fija/TAMAR)", "") == "Dual Fija / TAMAR"
    assert C.categoria_ajuste_tasa("ARS", "BADLAR") == "ARS BADLAR"
    assert C.categoria_ajuste_tasa("ARS", "Step Up") == "ARS Step Up"
    assert C.categoria_ajuste_tasa("ARS", "NC") == "ARS (s/tasa)"
    assert C.categoria_ajuste_tasa("", "TAMAR") == "ARS TAMAR"          # sólo Tasa → en pesos
    assert C.categoria_ajuste_tasa("NC", "NC") is None
    assert C.categoria_ajuste_tasa(float("nan"), None) is None
    # fideicomiso con fila en la base: el tipo sale de la Subclase y el grupo de la Tasa
    ff = {"Ajuste": "ARS", "Tasa": "BADLAR", "Subclase de Activo": "Fideicomiso Financiero"}
    assert C.clasificar("FF ABC SERIE 1 VDFA", "Renta Fija", ff, "FFAB1") == ("Fideicomisos TAMAR/BADLAR", "base")
    ff_cer = {"Ajuste": "CER", "Tasa": "Fija", "Subclase de Activo": "Fideicomiso Financiero"}
    assert _cl("FF ABC", "Renta Fija", ff_cer) == "Fideicomisos CER/UVA"
    ff_dlk = {"Ajuste": "USD-Linked", "Subclase de Activo": "Fideicomiso Financiero"}
    assert _cl("FF ABC", "Renta Fija", ff_dlk) == "Fideicomisos USD-Linked"
    ff_fija = {"Ajuste": "ARS", "Tasa": "Fija", "Subclase de Activo": "Fideicomiso Financiero"}
    assert _cl("FF ABC", "Renta Fija", ff_fija) == "Fideicomisos Tasa Fija"
    assert _cl("X", "Renta Fija", {"Subclase de Activo": "FCI Cerrado"}) == "FCI Cerrados"


def test_memo_no_confunde_distintas_filas_de_la_base() -> None:
    """El memo (2-3 clasificaciones por tenencia y request) se indexa también por
    los campos usados de la base: el mismo ticker con otra fila no hereda la
    categoría anterior, y una fila NO cargada no toma la de una cargada."""
    C._MEMO.clear()
    a = C.clasificar("ON X", "Renta Fija", {"Ajuste": "ARS", "Tasa": "TAMAR"}, "ZON1")
    b = C.clasificar("ON X", "Renta Fija", {"Ajuste": "ARS", "Tasa": "Fija"}, "ZON1")
    c = C.clasificar("ON X", "Renta Fija", None, "ZON1")
    assert (a, b, c) == (("ON ARS TAMAR", "base"), ("ON ARS Fija", "base"), ("Renta Fija", "sin_regla"))
    assert C.clasificar("ON X", "Renta Fija", {"Ajuste": "ARS", "Tasa": "TAMAR"}, "ZON1") == a   # hit
    assert len(C._MEMO) == 3
    # se vacía al llenarse, nunca crece sin límite
    C._MEMO.update({("k", i): ("x", "y") for i in range(C._MEMO_MAX)})
    C.clasificar("PLAZO FIJO", "Renta Fija")
    assert len(C._MEMO) == 1
    C._MEMO.clear()


def test_tipo_emisor_soberano_subsoberano_on() -> None:
    """El desk lee soberano vs ON: prefijo por la Clasificación de la ficha
    ('Soberano' / 'Sub-soberano' / 'Corporativo …') o, sin ficha, por la
    taxonomía de la base, la descripción y la Clase de Activo del Excel."""
    assert C.tipo_emisor_ficha("Soberano") == "Soberano"
    assert C.tipo_emisor_ficha("Sub-soberano") == "Sub-soberano" and C.tipo_emisor_ficha("Sub-Soberano") == "Sub-soberano"
    assert C.tipo_emisor_ficha("Corporativo TAMAR") == "ON" and C.tipo_emisor_ficha("Corporativo Hard Dolar MEP") == "ON"
    assert C.tipo_emisor_ficha("") is None and C.tipo_emisor_ficha(None) is None
    assert C.con_emisor("ARS TAMAR", "ON") == "ON ARS TAMAR"
    assert C.con_emisor("Dual CER / TAMAR", "Soberano") == "Soberano Dual CER / TAMAR"
    assert C.con_emisor("Plazos Fijos", "ON") == "Plazos Fijos"          # instrumentos: sin prefijo
    assert C.con_emisor("Fideicomisos TAMAR/BADLAR", "ON") == "Fideicomisos TAMAR/BADLAR"
    assert C.con_emisor("ARS TAMAR", None) == "ARS TAMAR"
    n = C._norm
    assert C._tipo_emisor_texto(n("Títulos Públicos"), "", "") == "Soberano"
    assert C._tipo_emisor_texto(n("Letras del Tesoro"), "", "") == "Soberano"
    assert C._tipo_emisor_texto(n("Bono Provincial"), "", "") == "Sub-soberano"
    assert C._tipo_emisor_texto(n("Obligación Negociable"), "", "") == "ON"
    assert C._tipo_emisor_texto("", n("ON BANCO PROVINCIA CLASE 5"), "") == "ON"    # el token ON manda
    assert C._tipo_emisor_texto("", n("BONCAP 30/06/2027"), "") == "Soberano"
    assert C._tipo_emisor_texto("", n("PROVINCIA DE CORDOBA 2029"), "") == "Sub-soberano"
    assert C._tipo_emisor_texto("", "", n("Títulos Públicos")) == "Soberano"
    assert C._tipo_emisor_texto("", "", n("Renta Fija")) == "ON"                   # la RF de Delta son ONs
    assert C._tipo_emisor_texto("", n("ALGO 2027"), n("Otros")) is None


def test_tasa_y_calificacion_sin_ficha() -> None:
    assert C.tasa_para("Plazos Fijos", None) == "Fija"
    assert C.tasa_para("Cheques No Garantizados", None) == "Fija"
    assert C.tasa_para("Fideicomisos TAMAR/BADLAR", None) == "Variable"
    assert C.tasa_para("Fideicomisos TAMAR/BADLAR", {"Tasa": "BADLAR"}) == "BADLAR"
    assert C.tasa_para("ARS TAMAR", {"Tasa": "TAMAR"}) == "TAMAR"
    assert C.tasa_para("ARS Fija", {"Tasa": "Step Up"}) == "Step Up"
    assert C.tasa_para("FCI Money Markets", None) == "(sin clasif.)"
    assert C.calificacion_base({"Califica_Local": "A+(arg)"}) == "A+(arg)"
    assert C.calificacion_base({}) is None and C.calificacion_base(None) is None


def test_galileo_clasifica_ficha_se_lee_igual() -> None:
    """Galileo: `clase` = Clasifica_Ficha / instrumento del reporte — las
    mismas etiquetas finas que Delta (antes PF y caución eran 'Liquidez')."""
    assert _cl("*BIS131000155", "Cheques Garantizados") == "Cheques Garantizados"
    assert _cl("PF BANCO X", "Plazo Fijo") == "Plazos Fijos"
    assert _cl("CAUCION", "Caución") == "Caución"
    assert _cl("FCI X", "FCI Cerrados") == "FCI Cerrados"
    assert _cl("FF X", "Fideicomisos Financieros") == "Fideicomisos Financieros"
    assert _cl("Bonar 2030", "Soberano USD MEP") == "Soberano USD MEP"        # como antes


def test_composicion_estilo_delta_ahorro(monkeypatch) -> None:
    """Cartera estilo Delta Ahorro: lo que antes era 'Renta Fija' 47 % se abre
    como en la cartera manual del desk; los ONs sin ficha suman a ARS TAMAR /
    ARS Fija con los que sí la tienen; Tasa y Calificación también salen de
    la base para los sin ficha; la fila lleva la fuente (tooltip)."""
    from backend.routes import posiciones as P
    from backend.services import delta_especies

    class _B:                                   # ficha mínima
        def __init__(self, tipo="VARIABLE", index="TAMAR", clasif="Corporativo TAMAR"):
            self.industria = ""
            self.ajuste_sobre_capital = ""
            self.tipo_tasa_interes = tipo
            self.index = index
            self.moneda = "ARS"
            self.step_up = False
            self.vencimiento = None
            self.calificacion = "AA(arg)"
            self.clasificacion = clasif

    fichas = {"ONT1": _B(), "ONF1": _B("FIJA", ""), "SOBT1": _B(clasif="Soberano"),
              "PROV1": _B(clasif="Sub-soberano")}
    base = {"ZONT1": {"Ajuste": "ARS", "Tasa": "TAMAR", "Califica_Local": "A+(arg)"},
            "FFAB1": {"Ajuste": "ARS", "Tasa": "BADLAR", "Subclase de Activo": "Fideicomiso Financiero"}}
    monkeypatch.setattr(P, "_bono", lambda c: fichas.get(c))
    monkeypatch.setattr(delta_especies, "info", lambda c: base.get(c))
    hs = [
        {"cod_fondo": 2, "cod_delta": "ONT1", "especie": "ON REAL TAMAR", "valor": 100.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": "ZONT1", "especie": "ON FANTASMA TAMAR", "valor": 27.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": "ONF1", "especie": "ON REAL FIJA", "valor": 16.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "PLAZO FIJO BANCO MACRO", "valor": 44.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": "FFAB1", "especie": "FF ABC SERIE 1 VDFA", "valor": 43.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "CAUCION COLOCADORA 7 DIAS", "valor": 24.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "OTROS ACTIVOS NETOS", "valor": 19.0, "clase": "Otros Activos Netos"},
        {"cod_fondo": 2, "cod_delta": "DELPESB", "especie": "DELTA PESOS CLASE B", "valor": 10.0, "clase": "Liquidez"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "CHEQUE PAGO DIFERIDO NO GARANTIZADO", "valor": 9.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "CPD AVALADO SGR", "valor": 8.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": "FCIC1", "especie": "FCI CERRADO INFRA", "valor": 4.0, "clase": "Renta Fija"},
        {"cod_fondo": 2, "cod_delta": None, "especie": "PAGARE BURSATIL NO GARANTIZADO", "valor": 4.0, "clase": "Renta Fija"},
    ]
    s = P._composicion_summary(hs, pn=311.0)
    cats = {r["cat"]: r["monto"] for r in s["Categoría"]}
    # los ONs con ficha (Corporativo …) y el ON sin ficha (base + descripción
    # "ON …") caen en el MISMO grupo, con el prefijo que pide el desk
    assert cats == {
        "ON ARS TAMAR": 127.0, "Plazos Fijos": 44.0, "Fideicomisos TAMAR/BADLAR": 43.0, "Caución": 24.0,
        "Otros Activos Netos": 19.0, "ON ARS Fija": 16.0, "FCI Money Markets": 10.0,
        "Cheques No Garantizados": 9.0, "Cheques Garantizados": 8.0, "FCI Cerrados": 4.0,
        "Pagarés No Garantizados": 4.0,
    }
    assert s["Categoría"][0]["pct"] == pytest.approx(127.0 / 311.0)
    tasas = {r["cat"]: r["monto"] for r in s["Tasa"]}
    assert tasas["TAMAR"] == 127.0 and tasas["BADLAR"] == 43.0
    assert tasas["Fija"] == 16 + 44 + 24 + 9 + 8 + 4                # fija por naturaleza
    calif = {r["cat"]: r["monto"] for r in s["Calificación"]}
    assert calif["A+(arg)"] == 27.0 and calif["AA(arg)"] == 116.0   # la base aporta la nota del ON sin ficha
    # las filas enriquecidas llevan la fuente (tooltip) y el rating de la base
    rows = P._enrich(hs, 311.0, "24hs")
    by = {r["especie"]: r for r in rows}
    assert by["ON REAL TAMAR"]["cat_src"] == "ficha" and by["ON FANTASMA TAMAR"]["cat_src"] == "base"
    assert by["PLAZO FIJO BANCO MACRO"]["cat_src"] == "texto"
    assert by["OTROS ACTIVOS NETOS"]["cat_src"] == "sin_regla"
    assert by["ON FANTASMA TAMAR"]["rating"] == "A+(arg)" and by["PLAZO FIJO BANCO MACRO"]["rating"] == "—"
    assert sum(1 for r in rows if r["cat_src"] == "sin_regla") == 1
    # un fondo soberano: mismo TAMAR pero separado del corporativo, y el provincial aparte
    s13 = P._composicion_summary([
        {"cod_fondo": 13, "cod_delta": "SOBT1", "especie": "TAMAR SOB", "valor": 5.0, "clase": "Títulos Públicos"},
        {"cod_fondo": 13, "cod_delta": "PROV1", "especie": "TAMAR PROV", "valor": 2.0, "clase": "Títulos Públicos"},
        {"cod_fondo": 13, "cod_delta": "ONT1", "especie": "ON X", "valor": 1.0, "clase": "Renta Fija"},
    ], pn=10.0)
    assert [(r["cat"], r["monto"]) for r in s13["Categoría"]] == [
        ("Soberano ARS TAMAR", 5.0), ("Sub-soberano ARS TAMAR", 2.0), ("ON ARS TAMAR", 1.0)]
    assert {r["cat"]: r["monto"] for r in s13["Tasa"]} == {"TAMAR": 8.0}     # el cuadro Tasa no cambia


def test_reporte_que_pulir_en_la_base(monkeypatch) -> None:
    """/admin: tenencias Delta cuya Categoría no salió de ficha ni de la base —
    con ticker (cargar Ajuste/Tasa/Subclase en Delta - Especies o la ficha) y
    sin ticker sin regla (pasar la descripción). Acciones/CEDEARs, lo
    reconocido por descripción sin ticker y Galileo quedan afuera."""
    from backend.routes import posiciones as P
    from backend.services import delta_especies, positions

    class _B:
        industria = ""; ajuste_sobre_capital = ""; tipo_tasa_interes = "VARIABLE"; index = "TAMAR"  # noqa: E702
        moneda = "ARS"; step_up = False; vencimiento = None; calificacion = ""; clasificacion = "Corporativo TAMAR"  # noqa: E702

    monkeypatch.setattr(P, "_bono", lambda c: _B() if c == "ONT1" else None)
    monkeypatch.setattr(delta_especies, "info", lambda c: {"Ajuste": "ARS", "Tasa": "TAMAR"} if c == "ZONT1" else None)
    G = positions.GALILEO_OFFSET
    monkeypatch.setattr(positions, "_cache", {
        "loaded": True, "error": None, "paths": {}, "asof": "t", "by_code": {}, "pn": {},
        "fondos": {2: "Ahorro", 13: "Ahorro Plus"}, "galileo_nombres": {},
        "holdings": [
            {"cod_fondo": 2, "cod_delta": "ONT1", "especie": "ON REAL", "valor": 100.0, "clase": "Renta Fija"},
            {"cod_fondo": 2, "cod_delta": "ZONT1", "especie": "ON BASE", "valor": 50.0, "clase": "Renta Fija"},
            {"cod_fondo": 2, "cod_delta": "FFTX1", "especie": "FF ABC VDFA BADLAR", "valor": 40.0, "clase": "Renta Fija"},
            {"cod_fondo": 13, "cod_delta": "FFTX1", "especie": "FF ABC VDFA BADLAR", "valor": 10.0, "clase": "Renta Fija"},
            {"cod_fondo": 2, "cod_delta": "ZZZZ9", "especie": "ON RARO 2031", "valor": 30.0, "clase": "Renta Fija"},
            {"cod_fondo": 2, "cod_delta": "DELPESB", "especie": "DELTA PESOS B", "valor": 20.0, "clase": "Liquidez"},
            {"cod_fondo": 2, "cod_delta": "GGAL", "especie": "GALICIA", "valor": 9.0, "clase": "Acciones"},
            {"cod_fondo": 2, "cod_delta": None, "especie": "PLAZO FIJO MACRO", "valor": 8.0, "clase": "Renta Fija"},
            {"cod_fondo": 2, "cod_delta": None, "especie": "OTROS ACTIVOS NETOS", "valor": 7.0, "clase": "Otros Activos Netos"},
            {"cod_fondo": 2, "cod_delta": None, "especie": "COSA RARA", "valor": 6.0, "clase": "Renta Fija"},
            {"cod_fondo": G + 8, "cod_delta": None, "especie": "*BIS1", "valor": 5.0, "clase": "Cheques Garantizados",
             "es_especie": False},
        ],
    })
    rep = P.reporte_clasificacion()
    assert (rep["n_total"], rep["n_ficha"], rep["n_base"]) == (10, 1, 1)
    con = {r["code"]: r for r in rep["con_ticker"]}
    assert list(con) == ["FFTX1", "ZZZZ9", "DELPESB"]                      # por valor desc
    assert con["FFTX1"]["categoria"] == "Fideicomisos TAMAR/BADLAR" and con["FFTX1"]["fuente_txt"] == "descripción"
    assert con["FFTX1"]["n_filas"] == 2 and con["FFTX1"]["valor"] == 50.0 and con["FFTX1"]["n_fondos"] == 2
    assert "Ahorro" in con["FFTX1"]["fondos"] and "Ahorro Plus" in con["FFTX1"]["fondos"]
    assert con["ZZZZ9"]["categoria"] == "Renta Fija" and con["ZZZZ9"]["fuente_txt"] == "sin regla"
    assert con["DELPESB"]["categoria"] == "FCI Money Markets" and con["DELPESB"]["fuente_txt"] == "Clase de Activo"
    sin = [r["especie"] for r in rep["sin_ticker"]]
    assert sin == ["OTROS ACTIVOS NETOS", "COSA RARA"]                       # PF reconocido y Galileo: afuera
    assert rep["n_con_ticker"] == 3 and rep["n_sin_ticker"] == 2


@pytest.mark.asyncio
async def test_http_admin_muestra_que_pulir(monkeypatch, tmp_path) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.config import settings
    from backend.services import auth, positions

    monkeypatch.setattr(positions, "_cache", {
        "loaded": True, "error": None, "paths": {}, "asof": "t", "by_code": {}, "pn": {},
        "fondos": {2: "Ahorro"}, "galileo_nombres": {},
        "holdings": [{"cod_fondo": 2, "cod_delta": "ZZZZ9", "especie": "ON RARO 2031", "valor": 30.0,
                      "clase": "Renta Fija", "es_especie": True}],
    })
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "users.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    from backend.main import app

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            await ac.post("/login", data={"username": "su_test",
                                          "password": "clave-de-test-2026!", "next": "/admin"})
            ok = await ac.get("/admin/especies-faltantes")
            assert ok.status_code == 200
            assert "Clasificación de Posiciones" in ok.text and "ZZZZ9" in ok.text and "sin regla" in ok.text
    finally:
        auth.refresh()


@pytest.mark.asyncio
async def test_tabla_muestra_fuente_y_contador_sin_regla(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import positions

    monkeypatch.setattr(positions, "_cache", {
        "loaded": True, "error": None, "paths": {}, "asof": "t",
        "holdings": [
            {"cod_fondo": 7, "cod_delta": None, "especie": "PLAZO FIJO BANCO MACRO", "cantidad": None,
             "valor": 40.0, "clase": "Renta Fija"},
            {"cod_fondo": 7, "cod_delta": None, "especie": "OTROS ACTIVOS NETOS", "cantidad": None,
             "valor": 10.0, "clase": "Otros Activos Netos"},
        ],
        "pn": {7: 100.0}, "fondos": {7: "Test"}, "by_code": {},
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones/table?fondo=7&plazo=24hs")
        t = await ac.get("/posiciones/targets?fondo=7&plazo=24hs")
    assert r.status_code == 200 and t.status_code == 200
    assert "Plazos Fijos" in r.text and "1 sin regla fina" in r.text
    assert 'title="Categoría por la descripción de la cartera' in r.text
    assert "Plazos Fijos" in t.text                      # el cuadro Target vs Actual usa la misma categoría
