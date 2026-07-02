"""Seed de usuarios — alta batch desde la línea de comandos.

Uso:
    python -m scripts.seed_users jpaolicchi:premium jrivasrivas:basico

Cada argumento es ``usuario:rol`` (rol ∈ superuser/premium/basico; si se omite
el ``:rol`` queda ``basico``). Crea cada usuario con una contraseña aleatoria
que se imprime UNA sola vez — compartila por un canal seguro y el usuario la
cambia con /forgot (o el superuser se la resetea desde el panel). Sólo se guarda
el hash+salt en el store, nunca la contraseña en claro.

Idempotente: un usuario que ya existe se saltea (no se duplica ni se pisa su
contraseña), así se puede correr de nuevo para sumar altas sin tocar las viejas.
"""
from __future__ import annotations

import secrets
import sys
from typing import List, Optional, Tuple

from backend.services import auth


def _parse(spec: str) -> Tuple[str, str]:
    """'usuario:rol' → (usuario, rol). Sin ':' ⇒ rol 'basico'."""
    if ":" in spec:
        user, role = spec.split(":", 1)
    else:
        user, role = spec, "basico"
    return user.strip(), (role.strip() or "basico")


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("uso: python -m scripts.seed_users usuario:rol [usuario:rol ...]")
        return 2
    created, skipped = 0, 0
    for spec in args:
        user, role = _parse(spec)
        if not user:
            continue
        if auth.get_user(user):
            print(f"= {user}: ya existe, se saltea")
            skipped += 1
            continue
        pwd = secrets.token_urlsafe(12)
        try:
            auth.create_user(user, pwd, role)
        except auth.AuthError as exc:
            print(f"! {user}: {exc}")
            continue
        print(f"+ {user} ({role}) — contraseña inicial: {pwd}")
        created += 1
    print(f"\nListo: {created} creados, {skipped} ya existían.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
