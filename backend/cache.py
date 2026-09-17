"""Small TTL cache with a LOCK-FREE hit path.

El hit es el 99 % de los accesos (curvas anchas: ~700 lecturas por request,
abanicadas en varios threads del pool). `cachetools.TTLCache` exige lock en
TODA operación (su `get` hace housekeeping mutante), así que el lock se volvía
un punto de contención bajo el fan-out. Acá la lectura es un `dict.get` plano
—atómico bajo el GIL en CPython— con chequeo de expiración manual; el lock
sólo se toma para escribir/evictar. Misma API pública que antes
(`get_or_compute / invalidate / clear`).

`AsyncSingleFlight` (abajo) es el complemento para el event loop: N requests
que piden la MISMA key fría comparten UN Future (un solo worker del pool
calcula, los demás hacen await) en vez de entrar todos al pool y dormir sobre
el compute-lock — con 8 workers compartidos, 8 pedidos idénticos de Escenario
dejaban sin worker al libro / a Mercado (auditoría de eficiencia E02).
"""
from __future__ import annotations

import asyncio
import itertools
import threading
import time
from typing import Any, Callable, Dict, Hashable, List, Optional, Tuple


class LockedTTLCache:
    def __init__(self, maxsize: int, ttl: int) -> None:
        self._ttl = float(ttl)
        self._maxsize = int(maxsize)
        self._store: Dict[Hashable, Tuple[Any, float]] = {}
        self._lock = threading.Lock()
        # Un lock POR clave para computar-una-sola-vez: cuando una entrada vence,
        # el primer thread computa y los demás esperan y leen el resultado fresco,
        # en vez de recomputar todos la misma clave (estampida que dispara p99).
        # Cada entrada es [lock, usuarios]: `usuarios` cuenta productor + esperadores
        # activos, así la poda (abajo) nunca descarta un lock que alguien está
        # usando — antes se podaba todo lock cuya clave no estuviera cacheada y
        # una fábrica en curso (que todavía no publicó) perdía su compute-once:
        # el siguiente thread creaba OTRO lock y computaba en paralelo (E09).
        self._compute_locks: Dict[Hashable, List[Any]] = {}

    def _tomar_slot(self, key: Hashable) -> List[Any]:
        with self._lock:
            ent = self._compute_locks.get(key)
            if ent is None:
                ent = [threading.Lock(), 0]
                self._compute_locks[key] = ent
            ent[1] += 1
            return ent

    def _soltar_slot(self, key: Hashable, ent: List[Any]) -> None:
        with self._lock:
            ent[1] -= 1
            # Sin usuarios y sin entrada cacheada (fábrica que devolvió None):
            # el lock ya no sirve para nada → se va acá mismo, no en la poda.
            if ent[1] <= 0 and key not in self._store and self._compute_locks.get(key) is ent:
                self._compute_locks.pop(key, None)

    def get_or_compute(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        now = time.monotonic()
        ent = self._store.get(key)            # lock-free: dict.get es atómico (GIL)
        if ent is not None and ent[1] > now:
            return ent[0]
        # Miss/vencida: serializamos el cómputo de ESTA clave (compute-once). El
        # hit path de arriba sigue sin tomar locks (99 % de los accesos).
        slot = self._tomar_slot(key)
        try:
            with slot[0]:
                now = time.monotonic()
                ent = self._store.get(key)    # re-chequeo: otro thread pudo computarla mientras esperábamos
                if ent is not None and ent[1] > now:
                    return ent[0]
                value = factory()
                # `None` no se cachea (mismo efecto que el wrapper anterior: se
                # recomputa la próxima) — ningún productor cachea None de todos modos.
                if value is not None:
                    with self._lock:
                        # pop+insert: la clave va SIEMPRE al final del dict (asignar
                        # una clave existente NO la mueve). Con TTL constante y expiry
                        # tomado al guardar, el orden de inserción ES el orden de
                        # expiry — invariante del que depende `_evict_locked` (O(k)).
                        now = time.monotonic()
                        self._store.pop(key, None)
                        self._store[key] = (value, now + self._ttl)
                        if len(self._store) > self._maxsize:
                            self._evict_locked(now)
                # `_compute_locks` crecía 1 entrada por clave única computada y sólo
                # se limpiaba en clear() → leak lineal en procesos de larga vida.
                # La poda va FUERA de la rama `value is not None`: un factory que
                # devuelve None seguido (bono roto re-pedido con precio nuevo en
                # cada poll) también deja su lock huérfano y antes sólo una clave
                # EXITOSA disparaba la limpieza.
                if len(self._compute_locks) > self._maxsize:
                    with self._lock:
                        self._prune_compute_locks_locked()
                return value
        finally:
            self._soltar_slot(key, slot)

    def _prune_compute_locks_locked(self) -> None:
        """Descarta los locks de cómputo huérfanos: claves ya no cacheadas Y sin
        productor ni esperadores activos. Llamar bajo `_lock`. Un lock en uso
        (usuarios > 0) se conserva siempre: la coordinación compute-once de esa
        clave no se pierde por presión de claves."""
        alive = set(self._store)
        self._compute_locks = {k: e for k, e in self._compute_locks.items()
                               if k in alive or e[1] > 0}

    def _evict_locked(self, now: float) -> None:
        # El dict está en orden de expiry (get_or_compute y touch reinsertan al
        # final): los expirados son un prefijo y "menor expiry" == el frente.
        # Antes esto hacía un sorted() de TODO el store (~16k claves en el cache
        # de curvas) BAJO el lock → spike de p99 justo con mercado activo. Ahora
        # es O(expirados + k), sin ordenar nada.
        drop = []
        for k, (_, exp) in self._store.items():
            if exp > now:
                break
            drop.append(k)
        for k in drop:
            del self._store[k]
        over = len(self._store) - self._maxsize
        if over > 0:
            batch = over + self._maxsize // 10 + 1
            for k in list(itertools.islice(self._store, batch)):
                del self._store[k]

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Lectura pura, lock-free (mismo hit path que get_or_compute): valor
        cacheado y vigente, o `default`. No computa ni toca TTLs."""
        ent = self._store.get(key)
        if ent is not None and ent[1] > time.monotonic():
            return ent[0]
        return default

    def touch(self, key: Hashable) -> bool:
        """Extiende el TTL de una entrada YA presente, SIN recomputar. Para un
        keep-warm gentil (no compite por el GIL recalculando). True si estaba."""
        now = time.monotonic()
        ent = self._store.get(key)
        if ent is None or ent[1] <= now:
            return False
        with self._lock:
            cur = self._store.pop(key, None)   # pop+insert → mantiene el orden
            if cur is None:                    # de inserción == orden de expiry
                return False                   # (invariante de _evict_locked)
            self._store[key] = (cur[0], now + self._ttl)
        return True

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            # Los locks en uso se conservan: un thread a mitad de fábrica sigue
            # coordinado; los libres se van con el store.
            self._compute_locks = {k: e for k, e in self._compute_locks.items() if e[1] > 0}


class AsyncSingleFlight:
    """Una sola ejecución en vuelo por key, coordinada EN EL EVENT LOOP.

    `run(key, executor, fn)`: si ya hay un Future para `key`, lo comparte
    (await, sin ocupar worker); si no, manda `fn` al executor y publica el
    Future. El Future se retira al terminar (éxito o error: cada nuevo pedido
    posterior vuelve a intentar). `shield` para que la cancelación de UN
    request (cliente que cerró) no cancele el cálculo que los otros esperan.
    Sólo se comparte el resultado del cálculo (de sólo lectura para los
    callers); lo que dependa del usuario (tenencias, permisos) sigue por
    request, fuera de esta capa."""

    def __init__(self) -> None:
        self._inflight: Dict[Hashable, "asyncio.Future"] = {}

    def __len__(self) -> int:
        return len(self._inflight)

    def run(self, key: Hashable, executor: Optional[Any], fn: Callable[[], Any]) -> "asyncio.Future":
        fut = self._inflight.get(key)
        if fut is None:
            fut = asyncio.get_running_loop().run_in_executor(executor, fn)
            self._inflight[key] = fut

            def _limpiar(f, k=key):
                if self._inflight.get(k) is f:
                    self._inflight.pop(k, None)

            fut.add_done_callback(_limpiar)
        return asyncio.shield(fut)

    def clear(self) -> None:
        self._inflight.clear()
