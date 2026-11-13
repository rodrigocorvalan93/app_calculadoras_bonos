"""Optimizador de cartera (q-Entropy Pooling) — motor + endpoint."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from backend.services import cartera_opt
from backend.services.optimizador import engine


# ── Motor ────────────────────────────────────────────────────────────────────

def _panel_sintetico(j=300, n=4, seed=7):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((j, n)) * 0.01 + np.array([0.0004, 0.0002, 0.0001, 0.0003])
    return X


def test_prepare_series_rellena_solo_huecos_cortos() -> None:
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    s = pd.Series(np.linspace(1.0, 30.0, 30), index=idx)
    s.iloc[0:3] = np.nan     # sin historia inicial: se respeta
    s.iloc[10:12] = np.nan   # hueco corto (2): se rellena
    s.iloc[18:28] = np.nan   # hueco largo (10): NO se rellena, ni parcialmente
    df = engine.prepare_series(pd.DataFrame({"A": s, "B": s}), max_gap_fill=5)
    out = df["A"]
    assert out.iloc[0:3].isna().all(), "los NaN de inicio quedan intactos"
    assert out.iloc[10:12].notna().all(), "el hueco corto se interpola"
    assert out.iloc[18:28].isna().all(), "el hueco largo queda entero sin rellenar"


def test_pairwise_covariance_es_psd_y_marca_pares_flojos() -> None:
    rng = np.random.default_rng(3)
    j = 200
    base = rng.standard_normal(j)
    df = pd.DataFrame({
        "A": base + rng.standard_normal(j) * 0.2,
        "B": -base + rng.standard_normal(j) * 0.2,
        "C": base * 0.5 + rng.standard_normal(j) * 0.2,
    })
    df.loc[: df.index[150], "C"] = np.nan        # C con poca historia
    sigma, diag = engine.pairwise_covariance(df, min_obs=30)
    assert diag["pairwise"] is True
    assert np.linalg.eigvalsh(sigma).min() >= -1e-10
    assert sigma.shape == (3, 3) and np.allclose(sigma, sigma.T)


def test_entropy_prog_q2_es_la_proyeccion_euclidea() -> None:
    """Con prior uniforme, minimizar la divergencia de Tsallis q=2 (chi²) es
    exactamente la proyección L2 sobre el conjunto factible (resultado central
    de la tesis). Se verifica contra un QP independiente (SLSQP)."""
    rng = np.random.default_rng(11)
    j = 40
    p = np.full(j, 1.0 / j)
    v = rng.standard_normal(j)
    A = v.reshape(1, -1)
    b = np.array([-0.05])                 # E[v] <= -0.05: obliga a moverse
    aeq = np.ones((1, j))
    beq = np.array([1.0])

    p2 = engine.entropy_prog(p, A, b, aeq, beq, family="T", q=2.0)

    from scipy.optimize import minimize
    res = minimize(
        lambda x: float(np.sum((x - p) ** 2)),
        p.copy(),
        jac=lambda x: 2.0 * (x - p),
        bounds=[(0.0, None)] * j,
        constraints=[
            {"type": "eq", "fun": lambda x: float(np.sum(x) - 1.0)},
            {"type": "ineq", "fun": lambda x: float(b[0] - v @ x)},
        ],
        method="SLSQP", options={"maxiter": 2000, "ftol": 1e-14},
    )
    assert res.success
    assert float(v @ p2) <= b[0] + 1e-6, "el posterior cumple el view"
    assert np.max(np.abs(p2 - res.x)) < 1e-4
    # Shannon también cumple pero queda (débilmente) más lejos en L2
    p1 = engine.entropy_prog(p, A, b, aeq, beq, family="S")
    assert np.linalg.norm(p2 - p) <= np.linalg.norm(p1 - p) + 1e-10


def test_ranking_rows_invierte_el_signo_para_tir() -> None:
    X = np.array([[1.0, 2.0], [3.0, 1.0]])
    # mejor primero = columna 0. En TIR (lower_is_better): E[x0 - x1] <= 0.
    A, b = engine.ranking_rows(X, [0, 1], lower_is_better=True)
    assert np.allclose(A[0], X[:, 0] - X[:, 1]) and b[0] == 0.0
    # En precios: E[x0] >= E[x1]  ->  fila = x1 - x0.
    A2, _ = engine.ranking_rows(X, [0, 1], lower_is_better=False)
    assert np.allclose(A2[0], X[:, 1] - X[:, 0])


def test_mean_variance_respeta_tope_y_suma_uno() -> None:
    X = _panel_sintetico()
    mu = X.mean(axis=0)
    sigma = np.cov(X.T)
    w = engine.mean_variance(mu, sigma, delta=2.5, max_weight=0.40)
    assert abs(w.sum() - 1.0) < 1e-8
    assert w.max() <= 0.40 + 1e-8 and w.min() >= -1e-12
    with pytest.raises(ValueError):
        engine.mean_variance(mu, sigma, max_weight=0.20)   # 4 activos × 20% < 100%


def test_run_qep_con_ranking_mueve_el_posterior() -> None:
    rng = np.random.default_rng(5)
    j = 400
    dy = rng.standard_normal((j, 3)) * 0.001
    dy[:, 0] += 0.0005                      # el activo 0 AMPLIA spread en el prior
    dur = np.array([5.0, 7.0, 3.0])
    x_ret = -dy * dur[None, :]
    # view: el activo 0 es el MEJOR (comprime más) — contradice al prior → ata
    res = engine.run_qep(dy, x_ret, ranking_idx=[0, 1, 2], lower_is_better=True,
                         q=2.0, confidence=1.0, max_weight=1.0)
    ve = res["views_efecto"]
    assert ve is not None and any(ve["binding"])
    assert ve["dist_qep"] > 0 and ve["dist_ep"] > 0
    # el view baja E[dy] del activo 0 -> su retorno esperado de PRECIO mejora
    mu_prior = res["modelos"]["prior"]["mu"]
    mu_qep = res["modelos"]["qep"]["mu"]
    assert mu_qep[0] > mu_prior[0]
    # y el posterior cumple las desigualdades del ranking sobre dy
    p_post = res["modelos"]["qep"]["p"]
    assert float((dy[:, 0] - dy[:, 1]) @ p_post) <= 1e-8
    assert float((dy[:, 1] - dy[:, 2]) @ p_post) <= 1e-8


# ── Adaptador (sin universo: invariante precios o durations override) ───────

def _csv_precios(j=80, n=3, seed=2) -> bytes:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2026-01-01", periods=j)
    px = 100.0 * np.exp(np.cumsum(rng.standard_normal((j, n)) * 0.01, axis=0))
    df = pd.DataFrame(px, index=idx.strftime("%d/%m/%Y"),
                      columns=["AAA", "BBB", "CCC"])
    return df.to_csv(sep=";", decimal=",").encode()


def _csv_tir(j=80, seed=4) -> bytes:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2026-01-01", periods=j)
    niveles = 8.0 + np.cumsum(rng.standard_normal((j, 2)) * 0.05, axis=0)  # en %
    df = pd.DataFrame(niveles, index=idx.strftime("%d/%m/%Y"), columns=["GGG", "HHH"])
    return df.to_csv(sep=";", decimal=",").encode()


def test_parse_tabla_csv_es_ar() -> None:
    df = cartera_opt.parse_tabla("datos.csv", _csv_precios())
    assert df.shape == (80, 3) and df.index.is_monotonic_increasing
    assert str(df.index[0].date()) == "2026-01-01"


def test_detectar_escala() -> None:
    idx = pd.date_range("2026-01-01", periods=3)
    assert cartera_opt.detectar_escala(pd.DataFrame({"a": [450.0, 460, 470]}, index=idx))[0] == "bps"
    assert cartera_opt.detectar_escala(pd.DataFrame({"a": [8.5, 8.6, 8.4]}, index=idx))[0] == "porcentaje"
    assert cartera_opt.detectar_escala(pd.DataFrame({"a": [0.085, 0.086, 0.084]}, index=idx))[0] == "decimal"


def test_run_precios_sin_universo() -> None:
    ctx = cartera_opt.run("datos.csv", _csv_precios(), invariante="precios",
                          ranking_texto="AAA > BBB", max_peso=0.6)
    assert len(ctx["filas"]) == 3
    total = sum(r["w_qep"] for r in ctx["filas"])
    assert abs(total - 1.0) < 1e-6
    assert ctx["diag"]["activos"] == 3


def test_run_tir_con_durations_override() -> None:
    ctx = cartera_opt.run("tir.csv", _csv_tir(), invariante="tir",
                          ranking_texto="GGG > HHH", max_peso=0.8,
                          duraciones_override={"GGG": 5.0, "HHH": 2.0})
    assert ctx["diag"]["activos"] == 2
    assert "porcentaje" in ctx["detalle_invariante"]
    assert all(r["duration"] for r in ctx["filas"])


def test_run_errores_claros() -> None:
    with pytest.raises(ValueError, match="Formato no soportado"):
        cartera_opt.run("datos.txt", b"x", invariante="precios")
    with pytest.raises(ValueError, match="ranking"):
        cartera_opt.run("d.csv", _csv_precios(), invariante="precios",
                        ranking_texto="AAA > ZZZ")


# ── Endpoint HTTP ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_http_optimizador() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/optimizador")
        ok = await ac.post(
            "/optimizador/run",
            files={"archivo": ("datos.csv", _csv_precios(), "text/csv")},
            data={"invariante": "precios", "ranking": "AAA > BBB",
                  "q": "2", "confianza": "100", "max_peso": "60", "delta": "2,5"},
        )
        malo = await ac.post(
            "/optimizador/run",
            files={"archivo": ("datos.txt", b"hola", "text/plain")},
            data={"invariante": "precios"},
        )
    assert page.status_code == 200 and "Optimizador" in page.text
    assert ok.status_code == 200 and "Pesos óptimos" in ok.text
    assert malo.status_code == 200 and "No se pudo optimizar" in malo.text


# ── Gating superuser (como Alertas) ─────────────────────────────────────────

@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.services import auth

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


@pytest.mark.asyncio
async def test_optimizador_solo_superuser(auth_on) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    def _client() -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")

    async with _client() as su:
        await su.post("/login", data={"username": "su_test",
                                      "password": "clave-de-test-2026!", "next": "/yas"})
        nav = await su.get("/yas")
        assert ">Optimizador<" in nav.text                 # el superuser la ve en la nav
        assert (await su.get("/optimizador")).status_code == 200
        await su.post("/admin/users", data={"username": "prem",
                                            "password": "clave123", "role": "premium"})
    async with _client() as ac:
        await ac.post("/login", data={"username": "prem", "password": "clave123",
                                      "next": "/yas"})
        nav = await ac.get("/yas")
        assert ">Optimizador<" not in nav.text             # premium no la ve
        assert (await ac.get("/optimizador")).status_code == 403
        r = await ac.post("/optimizador/run",
                          files={"archivo": ("d.csv", b"a;b\n", "text/csv")},
                          data={"invariante": "precios"})
        assert r.status_code == 403                        # el subárbol también
