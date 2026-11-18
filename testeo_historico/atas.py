"""Escritor de los ficheros de ATAS que genera un escenario: `Logs/app_*.log`, `Database/*.cdb` y `CopyTrading.cnf`.

Formato (comprobado contra ficheros reales de ATAS; aquí solo la estructura, ningún dato):
  - log: `AAAA-MM-DD HH:MM:SS,mmm [hilo     ] INFO  clase          : mensaje`, hora de MADRID del reloj del PC, finales CRLF.
    Una operación escribe: orden a mercado registrada, `Order trade` (el fill), orden cambiada a Done, posición, stop y objetivo
    registrados, y al salir el fill del que toque, su Done, la cancelación del otro y la posición a 0.
  - decimales con COMA y Id de fill `<número>` hasta ATAS 8.0.14; con PUNTO y `<OrderId>_<número>` desde 8.0.15.
  - .cdb: `Version`, `Entity`, `Columns:`, `StartData`, filas CSV entrecomilladas, `EndData`; horas en UTC `MM/DD/AAAA HH:MM:SS`.
  - CopyTrading.cnf: JSON con BOM UTF-8.
"""

import json
import os
import random
from datetime import timedelta

from . import calendario
from .escenario import VALOR_TICK

CRLF = '\r\n'
COLUMNAS_MYTRADE = ('Route', 'AccountID', 'SecurityId', 'Id', 'OrderId', 'OrderDirection', 'Price', 'Time', 'Volume', 'OpenVolume',
                    'Commission', 'CommissionCurrency')
COLUMNAS_HISTORIA = ('Id', 'AccountID', 'SecurityId', 'OpenTime', 'OpenPrice', 'OpenVolume', 'CloseTime', 'ClosePrice',
                     'CloseVolume', 'PnL', 'TicksPnL', 'PricePnL', 'Commission', 'Comment', 'Reviewed', 'MissingDataCase')
COLUMNAS_PLAYBOOK = ('Id', 'Name', 'Description', 'Emoji', 'Color')
ESTRATEGIAS = (('1', 'Estrategia de ejemplo A', 'Entrada a mercado con stop y objetivo fijos.'),
               ('2', 'Estrategia de ejemplo B', 'Segunda estrategia de ejemplo.'))


def _numero(valor, coma):
    """Como los escribe ATAS: sin ceros sobrantes y con coma decimal hasta la 8.0.14."""
    texto = f'{round(valor, 2) + 0.0:.2f}'.rstrip('0').rstrip('.')            # + 0.0: que -0.0 no salga como «-0»
    return texto.replace('.', ',') if coma else texto


def _hora_cdb(t):
    return t.strftime('%m/%d/%Y %H:%M:%S')


class _Diario:
    """Acumula las líneas de log y las filas de los .cdb de un escenario."""

    def __init__(self, esc):
        self.esc = esc
        self.coma = esc.version_atas == '8.0.14'
        base = esc.semilla % 1000
        self._orden, self._etiqueta, self._fill = 2640000000 + base * 1000, 41000000 + base * 100, 1020000 + base * 100
        self._id_historia = 1000 + base
        self.lineas, self.mytrade, self.historia = [], [], []
        self.saldo = {c.id: c.balance_inicial for c in esc.cuentas}
        self.cerrado = {c.id: 0.0 for c in esc.cuentas}
        self._seq = 0

    # --- ids ---
    def orden(self):
        self._orden += 1
        self._etiqueta += 1
        return self._orden, self._etiqueta

    def id_fill(self, id_orden):
        self._fill += 1
        return str(self._fill) if self.coma else f'{id_orden}_{self._fill}'

    # --- líneas ---
    def linea(self, t_utc, cuenta, mensaje, hilo='Process', clase=None):
        """Añade una línea en hora de Madrid del reloj del PC (el exchange más el desfase configurado)."""
        t = (t_utc + timedelta(seconds=self.esc.desfase_pc_s)).astimezone(calendario.MADRID)
        sello = f'{t:%Y-%m-%d %H:%M:%S},{t.microsecond // 1000:03d}'
        clase = clase or f'Rithmic[{cuenta.split("-")[0]}]'[-15:]
        self._seq += 1
        self.lineas.append((t_utc, self._seq, f'{sello} [{hilo:<10}] INFO  {clase:<15}: {mensaje}'))

    def _orden_texto(self, evento, id_orden, etiqueta, lado, tipo, op, limite, parada, llenado, estado, marca=''):
        simbolo, n = f'{self.esc.simbolo}@CME', op.contratos
        return (f'{evento} {id_orden}/{etiqueta} {lado} {tipo} {simbolo} on {op.cuenta} at {_numero(limite, self.coma)}/'
                f'{_numero(parada, self.coma)} vol {llenado}/{n} tif GTC state {estado} {marca}.')

    def _fill_texto(self, id_orden, etiqueta, id_fill, lado, precio, n):
        return f'Order trade {id_orden}/{etiqueta}/{id_fill} {lado} {self.esc.simbolo}@CME at {_numero(precio, self.coma)} vol {n}.'

    def _posicion(self, t, op, volumen, precio):
        mensaje = f'Position changed {op.cuenta}/{self.esc.simbolo}@CME vol {volumen} avg {_numero(precio, self.coma)} pnl 0/0.'
        self.linea(t, op.cuenta, mensaje)

    def _cartera(self, t, op):
        saldo, cerrado = _numero(self.saldo[op.cuenta], self.coma), _numero(self.cerrado[op.cuenta], self.coma)
        self.linea(t, op.cuenta, f'Portfolio changed {op.cuenta} Bal:{saldo}/0/0 Avl: PnL:0/{cerrado} L:0 C:0.')

    def _fila_mytrade(self, op, id_orden, id_fill, lado, precio, t):
        self.mytrade.append(('', op.cuenta, f'{self.esc.simbolo}@CME', id_fill, str(id_orden), lado, _numero(precio, False),
                             _hora_cdb(t), str(op.contratos), '0', '0.0', ''))

    # --- una operación ---
    def operacion(self, op):
        ms = lambda t, n: t + timedelta(milliseconds=n)
        lado, opuesto = op.lado, ('Sell' if op.lado == 'Buy' else 'Buy')
        n, t0, t1 = op.contratos, op.t_entrada, op.salida.t
        id_e, tag_e = self.orden()
        id_sl, tag_sl = self.orden()
        id_tp, tag_tp = self.orden()
        # entrada a mercado
        self.linea(ms(t0, -25), op.cuenta, self._orden_texto('Order registered', id_e, tag_e, lado, 'Market', op, 0, 0, 0, 'Active'))
        fill_e = self.id_fill(id_e)
        self.linea(t0, op.cuenta, self._fill_texto(id_e, tag_e, fill_e, lado, op.precio_entrada, n))
        self._fila_mytrade(op, id_e, fill_e, lado, op.precio_entrada, t0)
        self.linea(ms(t0, 6), op.cuenta, self._orden_texto('Order changed', id_e, tag_e, lado, 'Market', op, 0, 0, n, 'Done'))
        self._posicion(ms(t0, 12), op, n * op.sentido, op.precio_entrada)
        self.linea(ms(t0, 30), op.cuenta, self._orden_texto('Order registered', id_sl, tag_sl, opuesto, 'Stop', op, 0, op.sl, 0, 'Active', 'SL'))
        self.linea(ms(t0, 38), op.cuenta, self._orden_texto('Order registered', id_tp, tag_tp, opuesto, 'Limit', op, op.tp, 0, 0, 'Active', 'TP'))
        self._cartera(ms(t0, 55), op)
        # salida: el que toque; el otro se cancela
        tipo = op.salida.tipo
        if tipo == 'Mercado':
            id_x, tag_x = self.orden()
            self.linea(ms(t1, -25), op.cuenta, self._orden_texto('Order registered', id_x, tag_x, opuesto, 'Market', op, 0, 0, 0, 'Active'))
            nombre, marca, pendientes = 'Market', '', ((id_sl, tag_sl, 'Stop', 0, op.sl, 'SL'), (id_tp, tag_tp, 'Limit', op.tp, 0, 'TP'))
        elif tipo == 'TP':
            id_x, tag_x, nombre, marca = id_tp, tag_tp, 'Limit', 'TP'
            pendientes = ((id_sl, tag_sl, 'Stop', 0, op.sl, 'SL'),)
        else:
            id_x, tag_x, nombre, marca = id_sl, tag_sl, 'Stop', 'SL'
            pendientes = ((id_tp, tag_tp, 'Limit', op.tp, 0, 'TP'),)
        limite, parada = (op.tp, 0) if tipo == 'TP' else ((0, op.sl) if tipo == 'SL' else (0, 0))
        fill_x = self.id_fill(id_x)
        self.linea(t1, op.cuenta, self._fill_texto(id_x, tag_x, fill_x, opuesto, op.salida.precio, n))
        self._fila_mytrade(op, id_x, fill_x, opuesto, op.salida.precio, t1)
        self.linea(ms(t1, 6), op.cuenta, self._orden_texto('Order changed', id_x, tag_x, opuesto, nombre, op, limite, parada, n, 'Done', marca))
        for i, (id_p, tag_p, tipo_p, lim_p, par_p, marca_p) in enumerate(pendientes):
            self.linea(ms(t1, 20 + 4 * i), op.cuenta,
                       self._orden_texto('Cancel order', id_p, tag_p, opuesto, tipo_p, op, lim_p, par_p, 0, 'Active', marca_p))
        self._posicion(ms(t1, 32), op, 0, 0)
        pnl = round(op.ticks * VALOR_TICK[self.esc.raiz] * n, 2)
        self.saldo[op.cuenta] = round(self.saldo[op.cuenta] + pnl, 2)
        self.cerrado[op.cuenta] = round(self.cerrado[op.cuenta] + pnl, 2)
        self._cartera(ms(t1, 50), op)
        self._fila_historia(op, pnl, t0, t1)

    def _fila_historia(self, op, pnl, t0, t1):
        self._id_historia += 1
        firmado = op.contratos * op.sentido
        self.historia.append((str(self._id_historia), op.cuenta, f'{self.esc.simbolo}@CME', _hora_cdb(t0), _numero(op.precio_entrada, False),
                              str(firmado), _hora_cdb(t1), _numero(op.salida.precio, False), str(-firmado), _numero(pnl, False),
                              _numero(op.ticks, False), _numero(op.ticks * 0.25, False), '', '', 'False', 'None'))


def _cdb(entidad, columnas, filas):
    cabecera = ['Version: "9"', f'Entity: "{entidad}"', 'Columns: ' + ', '.join(f'"{c}"' for c in columnas), 'StartData']
    cuerpo = [', '.join(f'"{v}"' if v != '' else '' for v in fila) for fila in filas]
    return CRLF.join(cabecera + cuerpo + ['EndData']) + CRLF


def _escribir(ruta, texto, codificacion='utf-8'):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'wb') as f:
        f.write(texto.encode(codificacion))


def escribir(esc, carpeta):
    """Escribe en `carpeta` (que hace de carpeta de ATAS) todos los ficheros del escenario. Devuelve {nombre: ruta}.

    No borra nada ni sobrescribe fuera de sus propios ficheros; si ya existen los suyos, los reescribe."""
    d = _Diario(esc)
    for op in esc.operaciones:
        d.operacion(op)
    rng = random.Random(f'inicio|{esc.semilla}|{esc.fecha.isoformat()}')
    primera = min(t for t, _, _ in d.lineas) - timedelta(minutes=30)
    d.linea(primera, '', f'Started v{esc.version_atas}.{rng.randint(100, 999)}', hilo='1', clase='App')
    lineas = [texto for _, _, texto in sorted(d.lineas)]
    dia_madrid = (primera + timedelta(seconds=esc.desfase_pc_s)).astimezone(calendario.MADRID)
    rutas = {'log': os.path.join(carpeta, 'Logs', f'app_{dia_madrid:%Y%m%d}.log'),
             'mytrade': os.path.join(carpeta, 'Database', 'MyTrade.cdb'),
             'historia': os.path.join(carpeta, 'Database', 'HistoryMyTrade.cdb'),
             'playbook': os.path.join(carpeta, 'Database', 'Playbook.cdb'),
             'copias': os.path.join(carpeta, 'CopyTrading.cnf')}
    _escribir(rutas['log'], CRLF.join(lineas) + CRLF)
    _escribir(rutas['mytrade'], _cdb('MyTrade', COLUMNAS_MYTRADE, d.mytrade))
    _escribir(rutas['historia'], _cdb('HistoryMyTrade', COLUMNAS_HISTORIA, d.historia))
    _escribir(rutas['playbook'], _cdb('Playbook', COLUMNAS_PLAYBOOK, [(i, n, desc, '', '') for i, n, desc in ESTRATEGIAS]))
    por_lider = {}
    for lider, seguidora in esc.copias:
        por_lider.setdefault(lider, []).append(seguidora)
    ajustes = {'CopyTradingManagerSettings': [
        {'ProviderAccount': lider,
         'FollowerAccounts': [{'AccountId': s, 'CopyRatio': 1.0, 'CopyReverse': False, 'FollowerPositions': []} for s in seguidoras],
         'CopyType': 'Orders', 'ManualConfirmation': False, 'ShowNotifications': False, 'UseHedgedMode': False}
        for lider, seguidoras in por_lider.items()]}
    _escribir(rutas['copias'], json.dumps(ajustes, indent=2), 'utf-8-sig')
    return rutas
