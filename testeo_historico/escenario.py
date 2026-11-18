"""Escenario de un día de mercado: cuentas, copias y operaciones ya resueltas (entrada, stop, objetivo y salida).

Todo es reproducible: la misma (fecha, semilla, parámetros) da exactamente el mismo escenario.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import calendario
from .precios import TICK, CaminoSintetico

VALOR_TICK = {'NQ': 5.0, 'MNQ': 0.5, 'ES': 12.5, 'MES': 1.25}          # dólares por tick y contrato
VERSIONES_ATAS = ('8.0.14', '8.0.15')                                   # 8.0.15 cambió el decimal (coma → punto) y el Id del fill


@dataclass(frozen=True)
class Cuenta:
    id: str
    balance_inicial: float = 25000.0


@dataclass(frozen=True)
class Salida:
    tipo: str            # 'TP' (objetivo), 'SL' (stop) o 'Mercado' (cierre a mercado al agotarse el tiempo)
    t: datetime          # UTC, hora del exchange
    precio: float


@dataclass(frozen=True)
class Operacion:
    numero: int          # la decisión: el líder y sus copias comparten número
    cuenta: str
    lado: str            # 'Buy' o 'Sell'
    contratos: int
    t_entrada: datetime  # UTC, hora del exchange
    precio_entrada: float
    sl: float
    tp: float
    salida: Salida
    lider: str = None    # cuenta líder, si ésta es una copia

    @property
    def sentido(self):
        return 1 if self.lado == 'Buy' else -1

    @property
    def ticks(self):
        """Ticks por contrato (positivo = ganancia)."""
        return round((self.salida.precio - self.precio_entrada) / TICK * self.sentido, 2)


@dataclass(frozen=True)
class Escenario:
    fecha: date
    simbolo: str                  # contrato, p. ej. MNQZ6
    version_atas: str
    cuentas: tuple
    copias: tuple                 # ((líder, seguidora), ...)
    operaciones: tuple
    semilla: int
    desfase_pc_s: float = 0.0     # lo que el reloj del PC va adelantado (+) o atrasado (−) respecto al exchange

    @property
    def raiz(self):
        return self.simbolo[:-2]


def _resolver_salida(precios, t_entrada, lado, sl, tp, duracion_max_s):
    """Recorre segundo a segundo: el objetivo se llena a su precio; el stop, al precio al que el mercado lo atraviesa."""
    sentido = 1 if lado == 'Buy' else -1
    for s in range(1, duracion_max_s + 1):
        t = t_entrada + timedelta(seconds=s)
        p = precios.precio(t)
        if (p - tp) * sentido >= 0:
            return Salida('TP', t, tp)
        if (p - sl) * sentido <= 0:
            return Salida('SL', t, p)
    t = t_entrada + timedelta(seconds=duracion_max_s)
    return Salida('Mercado', t, precios.precio(t))


def generar(fecha, semilla=1, operaciones=5, contratos=1, raiz='MNQ', seguidoras=1, version_atas='8.0.15', precios=None,
            stop_ticks=(12, 36), objetivo_ticks=(16, 48), duracion_max_s=1200, desfase_pc_s=0.0, prefijo_cuentas='APEX-00000'):
    """Un día de operativa ficticia en la ventana 09:30–12:00 de Nueva York de `fecha` (un `date` real).

    Las operaciones van seguidas, sin solaparse; cada una entra a mercado con stop y objetivo y sale por el que toque primero (o a
    mercado al cabo de `duracion_max_s`). Las `seguidoras` copian al líder unas décimas de segundo después, al mismo precio.
    Lanza `calendario.DiaSinSesion` si ese día el mercado está cerrado."""
    if version_atas not in VERSIONES_ATAS:
        raise ValueError(f'versión de ATAS no soportada: {version_atas} (válidas: {", ".join(VERSIONES_ATAS)})')
    if raiz not in VALOR_TICK:
        raise ValueError(f'símbolo no soportado: {raiz} (válidos: {", ".join(VALOR_TICK)})')
    inicio, fin = calendario.ventana_operativa(fecha)
    rng = random.Random(f'esc|{semilla}|{fecha.isoformat()}')
    precios = precios or CaminoSintetico(fecha, semilla)
    ids = [f'{prefijo_cuentas}-{i + 1:02d}' for i in range(1 + seguidoras)]
    lider, copiadoras = ids[0], ids[1:]
    ops, cursor = [], inicio + timedelta(seconds=rng.randint(60, 300))
    for numero in range(1, operaciones + 1):
        if cursor + timedelta(seconds=duracion_max_s) > fin:
            break
        t0 = cursor.replace(microsecond=0)
        p0 = precios.precio(t0)
        lado = rng.choice(('Buy', 'Sell'))
        sentido = 1 if lado == 'Buy' else -1
        sl = round(p0 - sentido * rng.randint(*stop_ticks) * TICK, 6)
        tp = round(p0 + sentido * rng.randint(*objetivo_ticks) * TICK, 6)
        salida = _resolver_salida(precios, t0, lado, sl, tp, duracion_max_s)
        ops.append(Operacion(numero, lider, lado, contratos, t0, p0, sl, tp, salida))
        for copia in copiadoras:
            desfase = timedelta(milliseconds=rng.randint(120, 900))
            ops.append(Operacion(numero, copia, lado, contratos, t0 + desfase, p0, sl, tp,
                                 Salida(salida.tipo, salida.t + desfase, salida.precio), lider=lider))
        cursor = salida.t + timedelta(seconds=rng.randint(30, 240))
    return Escenario(fecha, calendario.contrato_frontal(fecha, raiz), version_atas, tuple(Cuenta(i) for i in ids),
                     tuple((lider, c) for c in copiadoras), tuple(sorted(ops, key=lambda o: (o.t_entrada, o.cuenta))),
                     semilla, desfase_pc_s)
