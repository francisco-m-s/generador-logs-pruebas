"""Fuentes de precio para resolver las operaciones: un camino sintético reproducible o precios REALES que tú aportas.

Las dos exponen `precio(t)`, con `t` un `datetime` con zona (UTC) o sin ella (se entiende UTC). Los precios van en la rejilla de ticks.
"""

import csv
import random
from bisect import bisect_right
from datetime import datetime, time, timedelta, timezone

from .calendario import CHICAGO

UTC = timezone.utc
TICK = 0.25
_SEGUNDOS = 26 * 3600                  # de la apertura de la sesión (17:00 CT del día anterior) a bastante después del cierre


def _a_utc(t):
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def _en_rejilla(precio, tick):
    return round(round(precio / tick) * tick, 6)


class CaminoSintetico:
    """Camino aleatorio ficticio, igual para la misma (fecha, semilla): un paso por segundo con ligera vuelta a la media.

    No imita ningún mercado real: sirve para que haya movimiento con el que llenar stops y objetivos."""

    def __init__(self, fecha, semilla=1, tick=TICK, precio_inicial=None, sigma_ticks=1.0):
        rng = random.Random(f'{semilla}|{fecha.isoformat()}')
        self.tick = tick
        self.inicio = datetime.combine(fecha - timedelta(days=1), time(17, 0), tzinfo=CHICAGO).astimezone(UTC)
        base = float(precio_inicial) if precio_inicial is not None else float(rng.randrange(15000, 26000, 25))
        x, camino = base, []
        for _ in range(_SEGUNDOS):
            x += rng.gauss(0.0, sigma_ticks * tick) - 0.0004 * (x - base)
            camino.append(x)
        self._camino = camino

    def precio(self, t):
        i = int((_a_utc(t) - self.inicio).total_seconds())
        return _en_rejilla(self._camino[min(max(i, 0), len(self._camino) - 1)], self.tick)


class PreciosCSV:
    """Precios REALES que aportas tú: CSV con cabecera `utc,precio` (hora UTC en ISO 8601, p. ej. 2026-03-10T14:30:00).

    `precio(t)` devuelve el último precio conocido en `t` o antes; sin datos anteriores, avisa con ValueError."""

    def __init__(self, ruta, tick=TICK):
        self.tick = tick
        filas = []
        with open(ruta, newline='', encoding='utf-8-sig') as f:
            for fila in csv.DictReader(f):
                filas.append((_a_utc(datetime.fromisoformat(fila['utc'].strip())), float(fila['precio'])))
        if not filas:
            raise ValueError(f'{ruta}: no tiene filas')
        filas.sort()
        self._t = [t for t, _ in filas]
        self._p = [p for _, p in filas]

    def precio(self, t):
        i = bisect_right(self._t, _a_utc(t)) - 1
        if i < 0:
            raise ValueError(f'sin precios anteriores a {t.isoformat()} (el primero es de {self._t[0].isoformat()})')
        return _en_rejilla(self._p[i], self.tick)
