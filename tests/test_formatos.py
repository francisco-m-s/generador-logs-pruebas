"""Contrato de formato con ATAS: lo generado se parsea con las MISMAS expresiones que usa el demonio ATAS (atasv4/fuentes.py),
copiadas aquí como especificación, y los ficheros son coherentes entre sí y con la verdad del escenario."""

import csv
import json
import os
import re
from datetime import date, datetime, timezone

import pytest

from testeo_historico import calendario, decisiones, escribir, generar

DIA = date(2026, 3, 10)

RE_PREFIJO = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) \[.{10}\] INFO  (.{15}): (.*)$')
RE_ORDEN = re.compile(r'(Order registered|Order changed) (\d+)/\S+ (Buy|Sell) (\w+) (\S+) on (\S+) at ([-\d.,]+)/([-\d.,]+) vol \S+ '
                      r'tif \w+\s+state (\w+)\s*(SL|TP)?\s*\.?\s*$')
RE_CANCELACION = re.compile(r'\bCancel order (\d+)/\S+ (Buy|Sell) (\w+) (\S+) on (\S+) at ([-\d.,]+)/([-\d.,]+) vol \S+ '
                            r'tif \w+\s+state \w+\s*(SL|TP)?\s*\.?\s*$')
RE_FILL = re.compile(r'Order trade (\d+)/(\S*?)/(\d+(?:_\d+)?) (Buy|Sell) (\S+) at ([-\d.,]+) vol (\d+(?:[.,]\d+)?)')
RE_CARTERA = re.compile(r'Portfolio changed (\S+) Bal:([-\d.,]+)/\S* Avl:\S* PnL:([-\d.,]+)/([-\d.,]+)')
RE_POSICION = re.compile(r'Position changed (\S+)/(\S+) vol (-?[\d.,]+) ')
RE_INICIO = re.compile(r'\bApp\s+: Started v(\S+)')
CONOCIDOS = (RE_ORDEN, RE_CANCELACION, RE_FILL, RE_CARTERA, RE_POSICION, RE_INICIO)


def _leer_log(carpeta):
    nombre = next(n for n in os.listdir(os.path.join(carpeta, 'Logs')) if n.startswith('app_'))
    with open(os.path.join(carpeta, 'Logs', nombre), 'rb') as f:
        crudo = f.read()
    return nombre, crudo, crudo.decode('utf-8').split('\r\n')[:-1]


def _leer_cdb(ruta):
    """Como read_cdb del demonio: cabecera `Columns:`, filas entre StartData y EndData, CSV con escape `\\`."""
    with open(ruta, 'r', encoding='utf-8') as f:
        lineas = f.read().splitlines()
    assert lineas[0] == 'Version: "9"' and lineas[1].startswith('Entity: "') and lineas[-1] == 'EndData' and lineas[3] == 'StartData'
    columnas = [c.strip() for c in next(csv.reader([lineas[2][len('Columns:'):]], skipinitialspace=True))]
    filas = [dict(zip(columnas, (v.strip() for v in next(csv.reader([l], skipinitialspace=True, escapechar='\\'))))) for l in lineas[4:-1]]
    return columnas, filas


@pytest.fixture
def dia(tmp_path):
    esc = generar(DIA, semilla=7, operaciones=4)
    escribir(esc, str(tmp_path))
    return esc, str(tmp_path)


def test_cada_linea_del_log_tiene_el_prefijo_de_atas_y_un_mensaje_conocido_y_termina_en_crlf(dia):
    esc, carpeta = dia
    _, crudo, lineas = _leer_log(carpeta)
    assert crudo.endswith(b'\r\n') and b'\n' not in crudo.replace(b'\r\n', b'')
    for linea in lineas:
        m = RE_PREFIJO.match(linea)
        assert m, linea
        assert sum(bool(rx.search(linea)) for rx in CONOCIDOS) == 1, linea          # el demonio busca sobre la línea entera


def test_el_log_va_en_orden_cronologico_en_hora_de_madrid_y_se_llama_como_su_dia(dia):
    esc, carpeta = dia
    nombre, _, lineas = _leer_log(carpeta)
    sellos = [RE_PREFIJO.match(l).group(1, 2) for l in lineas]
    assert sellos == sorted(sellos)
    assert nombre == 'app_20260310.log' and RE_INICIO.search(lineas[0]).group(1).startswith('8.0.15.')
    primera_orden = datetime.strptime(sellos[1][0], '%Y-%m-%d %H:%M:%S')
    assert primera_orden.hour in (14, 15, 16)             # ventana 09:30–12:00 de NY = 14:30–17:00 de Madrid ese día descuadrado


def test_hay_dos_fills_por_operacion_y_una_fila_de_cdb_por_fill_y_otra_por_operacion(dia):
    esc, carpeta = dia
    _, _, lineas = _leer_log(carpeta)
    n = len(esc.operaciones)
    assert sum('Order trade' in l for l in lineas) == 2 * n
    _, mytrade = _leer_cdb(os.path.join(carpeta, 'Database', 'MyTrade.cdb'))
    _, historia = _leer_cdb(os.path.join(carpeta, 'Database', 'HistoryMyTrade.cdb'))
    assert len(mytrade) == 2 * n and len(historia) == n
    assert {f['Id'] for f in mytrade} == {RE_FILL.search(l).group(3) for l in lineas if 'Order trade' in l}


@pytest.mark.parametrize('version, coma', [('8.0.14', True), ('8.0.15', False)])
def test_las_dos_versiones_de_atas_cambian_el_decimal_y_el_id_del_fill(tmp_path, version, coma):
    esc = generar(DIA, semilla=7, operaciones=4, version_atas=version)
    escribir(esc, str(tmp_path))
    _, _, lineas = _leer_log(str(tmp_path))
    precios = [RE_FILL.search(l).group(6) for l in lineas if 'Order trade' in l]
    con_decimales = [p for p in precios if re.search(r'\d[.,]\d', p)]
    assert con_decimales
    assert all((',' in p) == coma and ('.' in p) == (not coma) for p in con_decimales)       # coma hasta 8.0.14; punto desde 8.0.15
    ids = [RE_FILL.search(l).group(3) for l in lineas if 'Order trade' in l]
    assert all(('_' in i) != coma for i in ids)
    assert RE_INICIO.search(lineas[0]).group(1).startswith(version)


def test_la_hora_de_mytrade_es_utc_y_la_del_log_es_madrid_mas_el_desfase_del_pc(tmp_path):
    esc = generar(DIA, semilla=7, operaciones=2, desfase_pc_s=3.2)
    escribir(esc, str(tmp_path))
    _, _, lineas = _leer_log(str(tmp_path))
    _, mytrade = _leer_cdb(os.path.join(str(tmp_path), 'Database', 'MyTrade.cdb'))
    primer_fill = next(l for l in lineas if 'Order trade' in l)
    m = RE_PREFIJO.match(primer_fill)
    t_log = datetime.strptime(f'{m.group(1)},{m.group(2)}', '%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=calendario.MADRID)
    t_exchange = esc.operaciones[0].t_entrada
    assert abs((t_log.astimezone(timezone.utc) - t_exchange).total_seconds() - 3.2) < 0.001
    assert datetime.strptime(mytrade[0]['Time'], '%m/%d/%Y %H:%M:%S') == t_exchange.replace(tzinfo=None, microsecond=0)


def test_la_historia_de_cierres_trae_volumenes_con_signo_y_los_ticks_de_la_verdad(tmp_path):
    esc = generar(DIA, semilla=7, operaciones=4, contratos=2)
    escribir(esc, str(tmp_path))
    _, historia = _leer_cdb(os.path.join(str(tmp_path), 'Database', 'HistoryMyTrade.cdb'))
    lider = [f for f in historia if f['AccountID'] == esc.cuentas[0].id]
    assert len(lider) == len(decisiones(esc))
    for fila, d in zip(lider, decisiones(esc)):
        firmado = 2 if d['lado'] == 'Buy' else -2
        assert float(fila['OpenVolume']) == firmado and float(fila['CloseVolume']) == -firmado
        assert float(fila['TicksPnL']) == d['ticks'] and float(fila['PnL']) == d['bruto_usd']


def test_el_copytrading_lleva_bom_y_lista_a_las_seguidoras(tmp_path):
    esc = generar(DIA, semilla=7, operaciones=2, seguidoras=2)
    escribir(esc, str(tmp_path))
    ruta = os.path.join(str(tmp_path), 'CopyTrading.cnf')
    with open(ruta, 'rb') as f:
        assert f.read(3) == b'\xef\xbb\xbf'
    with open(ruta, encoding='utf-8-sig') as f:
        ajustes = json.load(f)['CopyTradingManagerSettings']
    assert [(a['ProviderAccount'], [s['AccountId'] for s in a['FollowerAccounts']]) for a in ajustes] == \
        [(esc.copias[0][0], [c for _, c in esc.copias])]


def test_el_playbook_trae_las_estrategias_de_ejemplo(tmp_path):
    escribir(generar(DIA, semilla=1, operaciones=1), str(tmp_path))
    columnas, filas = _leer_cdb(os.path.join(str(tmp_path), 'Database', 'Playbook.cdb'))
    assert columnas == ['Id', 'Name', 'Description', 'Emoji', 'Color'] and [f['Name'] for f in filas] == ['Estrategia de ejemplo A', 'Estrategia de ejemplo B']
