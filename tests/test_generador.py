"""El generador de escenarios: reproducible, coherente con el calendario y con una verdad calculable."""

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from testeo_historico import calendario, decisiones, escribir, generar, resumen
from testeo_historico.precios import CaminoSintetico, PreciosCSV

UTC = timezone.utc
DIA = date(2026, 3, 10)                 # día descuadrado: Madrid y Nueva York a 5 h


def _ficheros(carpeta):
    salida = {}
    for raiz, _, nombres in os.walk(carpeta):
        for n in nombres:
            ruta = os.path.join(raiz, n)
            with open(ruta, 'rb') as f:
                salida[os.path.relpath(ruta, carpeta)] = f.read()
    return salida


def test_la_misma_semilla_da_exactamente_los_mismos_ficheros(tmp_path):
    escribir(generar(DIA, semilla=7, operaciones=4), str(tmp_path / 'a'))
    escribir(generar(DIA, semilla=7, operaciones=4), str(tmp_path / 'b'))
    escribir(generar(DIA, semilla=8, operaciones=4), str(tmp_path / 'c'))
    assert _ficheros(tmp_path / 'a') == _ficheros(tmp_path / 'b')
    assert _ficheros(tmp_path / 'a') != _ficheros(tmp_path / 'c')


def test_un_dia_sin_mercado_no_se_puede_generar():
    for dia in (date(2026, 3, 14), date(2026, 4, 3), date(2026, 12, 25)):
        with pytest.raises(calendario.DiaSinSesion):
            generar(dia)


def test_las_operaciones_caen_en_la_ventana_no_se_solapan_y_salen_despues_de_entrar():
    esc = generar(DIA, semilla=3, operaciones=6)
    inicio, fin = calendario.ventana_operativa(DIA)
    lideres = [o for o in esc.operaciones if o.lider is None]
    assert len(lideres) >= 3
    for o in esc.operaciones:
        assert inicio <= o.t_entrada < o.salida.t <= fin + timedelta(seconds=1)
    for anterior, siguiente in zip(lideres, lideres[1:]):
        assert siguiente.t_entrada > anterior.salida.t


def test_cada_salida_es_coherente_con_su_tipo_y_sus_niveles():
    esc = generar(DIA, semilla=5, operaciones=8, duracion_max_s=300)
    tipos = set()
    for o in esc.operaciones:
        tipos.add(o.salida.tipo)
        if o.salida.tipo == 'TP':
            assert o.salida.precio == o.tp and o.ticks > 0
        elif o.salida.tipo == 'SL':
            assert (o.salida.precio - o.sl) * o.sentido <= 0 and o.ticks < 0
        assert (o.precio_entrada - o.sl) * o.sentido > 0 and (o.tp - o.precio_entrada) * o.sentido > 0
    assert tipos <= {'TP', 'SL', 'Mercado'}


def test_las_copias_repiten_al_lider_unas_decimas_despues_al_mismo_precio():
    esc = generar(DIA, semilla=2, operaciones=3, seguidoras=3)
    assert len(esc.cuentas) == 4 and len(esc.copias) == 3
    for lider in (o for o in esc.operaciones if o.lider is None):
        copias = [o for o in esc.operaciones if o.numero == lider.numero and o.lider == lider.cuenta]
        assert len(copias) == 3
        for c in copias:
            assert timedelta(milliseconds=120) <= c.t_entrada - lider.t_entrada <= timedelta(milliseconds=900)
            assert (c.precio_entrada, c.sl, c.tp, c.salida.precio, c.lado) == (lider.precio_entrada, lider.sl, lider.tp, lider.salida.precio, lider.lado)


def test_la_verdad_solo_cuenta_las_decisiones_del_lider():
    esc = generar(DIA, semilla=4, operaciones=5, seguidoras=2, contratos=2)
    ds = decisiones(esc)
    assert [d['numero'] for d in ds] == sorted(d['numero'] for d in ds) and len({d['numero'] for d in ds}) == len(ds)
    for d in ds:
        assert d['seguidoras'] == sorted(c.id for c in esc.cuentas[1:]) and d['contratos'] == 2
        assert d['bruto_usd'] == round(d['ticks'] * 0.5 * 2, 2)          # MNQ: 0,50 $ por tick y contrato
    r = resumen(esc)
    assert r['decisiones'] == len(ds) and r['ganadoras'] + r['perdedoras'] <= len(ds)
    assert r['ticks'] == round(sum(d['ticks'] for d in ds), 2)


@pytest.mark.parametrize('parametros, mensaje', [({'version_atas': '8.0.99'}, 'versión de ATAS'), ({'raiz': 'XYZ'}, 'símbolo')])
def test_los_parametros_invalidos_se_rechazan_con_un_mensaje_claro(parametros, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        generar(DIA, **parametros)


def test_el_camino_sintetico_va_siempre_en_la_rejilla_de_ticks_y_es_reproducible():
    a, b = CaminoSintetico(DIA, semilla=1), CaminoSintetico(DIA, semilla=1)
    t = calendario.ventana_operativa(DIA)[0]
    precios = [a.precio(t + timedelta(seconds=s)) for s in range(0, 3600, 7)]
    assert precios == [b.precio(t + timedelta(seconds=s)) for s in range(0, 3600, 7)]
    assert all(abs(p / 0.25 - round(p / 0.25)) < 1e-9 for p in precios) and len(set(precios)) > 5


def test_con_precios_reales_de_un_csv_las_salidas_salen_de_esos_precios(tmp_path):
    """Precios que solo suben un tick por segundo: toda compra llega a su objetivo y todo corto salta su stop."""
    inicio = calendario.ventana_operativa(DIA)[0] - timedelta(minutes=5)
    ruta = tmp_path / 'precios.csv'
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write('utc,precio\n')
        for s in range(0, 3 * 3600):
            f.write(f'{(inicio + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S")},{20000 + 0.25 * s}\n')
    esc = generar(DIA, semilla=1, operaciones=4, precios=PreciosCSV(str(ruta)))
    assert esc.operaciones
    for o in esc.operaciones:
        assert o.salida.tipo == ('TP' if o.lado == 'Buy' else 'SL')


def test_los_precios_csv_avisan_si_no_hay_datos_anteriores(tmp_path):
    ruta = tmp_path / 'p.csv'
    ruta.write_text('utc,precio\n2026-03-10T14:00:00,20000\n', encoding='utf-8')
    precios = PreciosCSV(str(ruta))
    assert precios.precio(datetime(2026, 3, 10, 15, 0, tzinfo=UTC)) == 20000
    with pytest.raises(ValueError, match='sin precios anteriores'):
        precios.precio(datetime(2026, 3, 10, 13, 0, tzinfo=UTC))
