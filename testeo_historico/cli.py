"""Línea de órdenes:  python -m testeo_historico  generar | calendario | dias"""

import argparse
import calendar as cal
import json
import os
from datetime import date, datetime

from . import atas, calendario, escenario, verdad
from .precios import PreciosCSV

DIAS = ('lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom')


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f'fecha no válida: {texto!r} (formato AAAA-MM-DD)')


def _json(valor):
    return valor.isoformat() if isinstance(valor, (datetime, date)) else str(valor)


def _madrid(t):
    return t.astimezone(calendario.MADRID).strftime('%H:%M')


def cmd_calendario(args):
    f = args.fecha
    s = calendario.sesion(f)
    print(f'{f.isoformat()} ({DIAS[f.weekday()]}): {s.estado}' + (f' ({s.motivo})' if s.motivo else ''))
    if s.estado == 'cerrado':
        return 0
    inicio, fin = calendario.ventana_operativa(f)
    print(f'  sesión CME      {s.apertura_utc:%Y-%m-%d %H:%M} UTC → {s.cierre_utc:%Y-%m-%d %H:%M} UTC')
    print(f'  horario normal  {_madrid(s.rth_inicio_utc)}–{_madrid(s.rth_fin_utc)} Madrid')
    print(f'  ventana 09:30–12:00 NY = {_madrid(inicio)}–{_madrid(fin)} Madrid')
    desfase = calendario.diferencia_madrid_nueva_york(f)
    print(f'  Madrid − Nueva York: {desfase:g} h' + ('   ← DÍA DESCUADRADO (EE. UU. y la UE en horarios distintos)' if desfase != 6 else ''))
    print(f'  contrato frontal MNQ: {calendario.contrato_frontal(f)}')
    return 0


def cmd_dias(args):
    anio, mes = args.mes
    print(f'{anio}-{mes:02d}')
    for dia in range(1, cal.monthrange(anio, mes)[1] + 1):
        f = date(anio, mes, dia)
        estado, motivo = calendario.estado_del_dia(f)
        marca = '  descuadre horario' if estado != 'cerrado' and calendario.descuadre_horario(f) else ''
        print(f'  {f.isoformat()} {DIAS[f.weekday()]}  {estado:<17}{motivo}{marca}')
    return 0


def cmd_generar(args):
    precios = PreciosCSV(args.precios_csv) if args.precios_csv else None
    esc = escenario.generar(args.fecha, semilla=args.semilla, operaciones=args.operaciones, contratos=args.contratos, raiz=args.simbolo,
                            seguidoras=args.seguidoras, version_atas=args.version_atas, precios=precios, desfase_pc_s=args.desfase_pc)
    rutas = atas.escribir(esc, args.salida)
    esperado = verdad.decisiones(esc)
    ruta_verdad = os.path.join(args.salida, 'verdad.json')
    with open(ruta_verdad, 'w', encoding='utf-8') as f:
        json.dump({'fecha': esc.fecha, 'simbolo': esc.simbolo, 'version_atas': esc.version_atas, 'resumen': verdad.resumen(esc),
                   'decisiones': esperado}, f, default=_json, ensure_ascii=False, indent=2)
    print(f'{esc.fecha.isoformat()} {esc.simbolo} (ATAS {esc.version_atas}): {len(esperado)} decisiones, {len(esc.cuentas)} cuentas')
    for nombre, ruta in {**rutas, 'verdad': ruta_verdad}.items():
        print(f'  {nombre:<9} {ruta}')
    print(f'  resumen   {verdad.resumen(esc)}')
    return 0


def _mes(texto):
    try:
        anio, mes = texto.split('-')
        return int(anio), int(mes)
    except ValueError:
        raise argparse.ArgumentTypeError(f'mes no válido: {texto!r} (formato AAAA-MM)')


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m testeo_historico',
                                description='Operaciones ficticias con verdad conocida, en días de mercado reales, en formato ATAS.')
    sub = p.add_subparsers(dest='orden', required=True)
    g = sub.add_parser('generar', help='escribe los ficheros de ATAS de un día y su verdad.json')
    g.add_argument('fecha', type=_fecha, help='día de calendario real, AAAA-MM-DD')
    g.add_argument('--salida', required=True, help='carpeta que hará de carpeta de ATAS (se crea si no existe)')
    g.add_argument('--semilla', type=int, default=1)
    g.add_argument('--operaciones', type=int, default=5)
    g.add_argument('--contratos', type=int, default=1)
    g.add_argument('--simbolo', choices=sorted(escenario.VALOR_TICK), default='MNQ')
    g.add_argument('--seguidoras', type=int, default=1, help='cuentas que copian al líder')
    g.add_argument('--version-atas', choices=escenario.VERSIONES_ATAS, default='8.0.15')
    g.add_argument('--desfase-pc', type=float, default=0.0, help='segundos que el reloj del PC se adelanta (+) o atrasa (−)')
    g.add_argument('--precios-csv', help='precios reales (cabecera utc,precio) en lugar del camino sintético')
    g.set_defaults(funcion=cmd_generar)
    c = sub.add_parser('calendario', help='estado, horarios y descuadre de un día real')
    c.add_argument('fecha', type=_fecha)
    c.set_defaults(funcion=cmd_calendario)
    d = sub.add_parser('dias', help='todos los días de un mes con su estado y los descuadres horarios')
    d.add_argument('mes', type=_mes, help='AAAA-MM')
    d.set_defaults(funcion=cmd_dias)
    args = p.parse_args(argv)
    try:
        return args.funcion(args)
    except (calendario.DiaSinSesion, ValueError) as e:
        print(f'error: {e}')
        return 2
