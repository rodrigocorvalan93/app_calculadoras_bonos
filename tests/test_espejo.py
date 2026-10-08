"""Espejo parquet — la firma debe atar al CONTENIDO, no sólo al tamaño (A06)."""
from __future__ import annotations

from backend.services import espejo


def test_espejo_rechaza_parquet_ajeno_del_mismo_tamano(tmp_path) -> None:
    """Un parquet ajeno del MISMO tamaño (réplica / restauración parcial) no
    debe pasar por copia fiel: la firma incluye un digest de contenido. El
    xlsx y el sidecar quedan intactos; cambia sólo el parquet."""
    espejo.reset_memo()
    xlsx = tmp_path / "base.xlsx"
    xlsx.write_bytes(b"EXCEL-CANONICO")
    pq = tmp_path / "base.parquet"
    pq.write_bytes(b"A" * 4096)
    assert espejo.marcar_espejo(str(pq), str(xlsx))
    assert espejo.espejo_valido(str(pq), str(xlsx))             # copia fiel recién marcada

    # Reemplazo el parquet por otro del MISMO tamaño y distinto contenido.
    pq.write_bytes(b"B" * 4096)
    espejo.reset_memo()                                          # sin el memo (OneDrive no lo comparte)
    assert espejo.espejo_valido(str(pq), str(xlsx)) is False     # antes de A06 daba True (sólo miraba el tamaño)

    # Volver al contenido original (re-firmado) lo revalida.
    pq.write_bytes(b"A" * 4096)
    espejo.marcar_espejo(str(pq), str(xlsx))
    espejo.reset_memo()
    assert espejo.espejo_valido(str(pq), str(xlsx))


def test_firma_vieja_sin_hash_cae_a_la_regla_de_tamano(tmp_path) -> None:
    """Un sidecar anterior a A06 (sin `pq_sha256`) sigue validando por tamaño:
    no invalidamos todos los espejos existentes al desplegar."""
    import json

    espejo.reset_memo()
    xlsx = tmp_path / "b.xlsx"
    xlsx.write_bytes(b"xlsx")
    pq = tmp_path / "b.parquet"
    pq.write_bytes(b"Z" * 100)
    f = espejo.firma(str(xlsx)) or {}
    # firma vieja: con huella del xlsx + pq_size pero SIN pq_sha256
    with open(espejo.sidecar_path(str(pq)), "w", encoding="utf-8") as fh:
        json.dump({**f, "pq_size": 100}, fh)
    assert espejo.espejo_valido(str(pq), str(xlsx)) is True
