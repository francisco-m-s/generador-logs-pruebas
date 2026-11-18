"""Calendario de sesiones de días reales: festivos, cierres anticipados, descuadres horarios EE. UU.–España y contratos."""

from datetime import date, datetime, time, timezone

import pytest

from testeo_historico import calendario as cal

UTC = timezone.utc


@pytest.mark.parametrize('dia, estado, motivo', [
    (date(2026, 3, 14), 'cerrado', 'fin de semana'),
    (date(2026, 1, 1), 'cerrado', 'Año Nuevo'),
    (date(2026, 4, 3), 'cerrado', 'Viernes Santo'),           # Pascua 2026: 5 de abril
    (date(2027, 3, 26), 'cerrado', 'Viernes Santo'),          # Pascua 2027: 28 de marzo
    (date(2026, 12, 25), 'cerrado', 'Navidad'),
    (date(2026, 11, 26), 'cierre_anticipado', 'Thanksgiving'),
    (date(2026, 11, 27), 'cierre_anticipado', 'Día después de Thanksgiving'),
    (date(2026, 7, 3), 'cierre_anticipado', 'Día de la Independencia'),   # el 4 cae en sábado: se observa el viernes
    (date(2026, 9, 7), 'cierre_anticipado', 'Labor Day'),
    (date(2026, 3, 10), 'normal', ''),
])
def test_estado_del_dia(dia, estado, motivo):
    assert cal.estado_del_dia(dia) == (estado, motivo)


@pytest.mark.parametrize('dia, descuadrado', [
    (date(2026, 3, 10), True),      # EE. UU. cambió el 8/03 y la UE el 29/03: tres semanas con 5 h de diferencia
    (date(2026, 3, 27), True),
    (date(2026, 3, 31), False),
    (date(2026, 7, 15), False),
    (date(2026, 10, 28), True),     # la UE cambió el 25/10 y EE. UU. el 1/11
    (date(2026, 11, 2), False),
])
def test_los_dias_con_horarios_de_verano_distintos_estan_marcados(dia, descuadrado):
    assert cal.descuadre_horario(dia) is descuadrado
    assert cal.diferencia_madrid_nueva_york(dia) == (5 if descuadrado else 6)


def test_la_sesion_empieza_a_las_17_de_chicago_del_dia_anterior_y_la_ventana_sigue_a_nueva_york():
    primavera = cal.sesion(date(2026, 3, 10))                       # EE. UU. ya en horario de verano
    assert primavera.apertura_utc == datetime(2026, 3, 9, 22, 0, tzinfo=UTC)
    assert primavera.rth_inicio_utc == datetime(2026, 3, 10, 13, 30, tzinfo=UTC)
    assert cal.ventana_operativa(date(2026, 3, 10)) == (datetime(2026, 3, 10, 13, 30, tzinfo=UTC), datetime(2026, 3, 10, 16, 0, tzinfo=UTC))
    invierno = cal.sesion(date(2026, 11, 17))
    assert invierno.apertura_utc == datetime(2026, 11, 16, 23, 0, tzinfo=UTC)
    assert cal.ventana_operativa(date(2026, 11, 17)) == (datetime(2026, 11, 17, 14, 30, tzinfo=UTC), datetime(2026, 11, 17, 17, 0, tzinfo=UTC))


def test_en_madrid_la_ventana_cae_a_distinta_hora_segun_el_descuadre():
    def hora_madrid(t):
        return t.astimezone(cal.MADRID).time()
    inicio, fin = cal.ventana_operativa(date(2026, 3, 10))
    assert (hora_madrid(inicio), hora_madrid(fin)) == (time(14, 30), time(17, 0))
    inicio, fin = cal.ventana_operativa(date(2026, 11, 17))
    assert (hora_madrid(inicio), hora_madrid(fin)) == (time(15, 30), time(18, 0))


def test_un_cierre_anticipado_recorta_la_sesion_y_un_dia_cerrado_no_tiene_ventana():
    s = cal.sesion(date(2026, 11, 27))
    assert s.cierre_utc == datetime(2026, 11, 27, 18, 0, tzinfo=UTC) and s.rth_fin_utc == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert cal.ventana_operativa(date(2026, 11, 27), hasta=time(15, 0))[1] == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert cal.sesion(date(2026, 4, 3)).apertura_utc is None
    with pytest.raises(cal.DiaSinSesion, match='Viernes Santo'):
        cal.ventana_operativa(date(2026, 4, 3))


@pytest.mark.parametrize('dia, raiz, contrato', [
    (date(2026, 3, 11), 'MNQ', 'MNQH6'),
    (date(2026, 3, 12), 'MNQ', 'MNQM6'),      # el 20/03 vence marzo: se pasa al siguiente 8 días antes
    (date(2026, 11, 17), 'MNQ', 'MNQZ6'),
    (date(2026, 12, 11), 'NQ', 'NQH7'),
])
def test_contrato_frontal(dia, raiz, contrato):
    assert cal.contrato_frontal(dia, raiz) == contrato
