"""La verdad conocida de un escenario: lo que cualquier diario correcto tiene que reconstruir a partir de los ficheros generados.

Se calcula solo con el escenario, sin tocar ningún diario: es el oráculo contra el que se comprueba.
"""

from .escenario import VALOR_TICK


def decisiones(esc):
    """Una entrada por decisión (el líder y sus copias cuentan como una), en orden de apertura.

    `ticks` va por contrato y en positivo si es ganancia; `bruto_usd` es el resultado de la cuenta líder SIN comisiones: los
    ficheros generados traen comisión 0 y cada diario aplica las de su firma (Apex, por ejemplo, descuenta unos 1,02 $ por MNQ
    ida y vuelta), así que el neto de un diario será menor. Compara ticks, horas y tipo de cierre; el neto, solo si descuentas."""
    valor_tick = VALOR_TICK[esc.raiz]
    salida = []
    for op in esc.operaciones:
        if op.lider is not None:
            continue
        copias = sorted(o.cuenta for o in esc.operaciones if o.lider == op.cuenta and o.numero == op.numero)
        salida.append({
            'numero': op.numero, 'cuenta': op.cuenta, 'seguidoras': copias, 'simbolo': esc.simbolo, 'lado': op.lado,
            'contratos': op.contratos, 't_apertura_utc': op.t_entrada, 't_cierre_utc': op.salida.t,
            'precio_entrada': op.precio_entrada, 'precio_salida': op.salida.precio, 'tipo_cierre': op.salida.tipo,
            'ticks': op.ticks, 'bruto_usd': round(op.ticks * valor_tick * op.contratos, 2)})
    return sorted(salida, key=lambda d: d['t_apertura_utc'])


def resumen(esc):
    """Totales del día: decisiones, ganadoras/perdedoras (por signo de los ticks) y ticks y dólares brutos de la cuenta líder."""
    ds = decisiones(esc)
    return {'decisiones': len(ds), 'ganadoras': sum(d['ticks'] > 0 for d in ds), 'perdedoras': sum(d['ticks'] < 0 for d in ds),
            'ticks': round(sum(d['ticks'] for d in ds), 2), 'bruto_usd': round(sum(d['bruto_usd'] for d in ds), 2)}
