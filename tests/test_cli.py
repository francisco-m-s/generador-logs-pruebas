"""Línea de órdenes: python -m testeo_historico generar | calendario | dias"""

import json
import os

from testeo_historico.cli import main


def test_calendario_marca_el_dia_descuadrado_y_el_cerrado(capsys):
    assert main(['calendario', '2026-03-10']) == 0
    salida = capsys.readouterr().out
    assert 'DÍA DESCUADRADO' in salida and '14:30–17:00 Madrid' in salida and 'MNQH6' in salida
    assert main(['calendario', '2026-04-03']) == 0
    assert 'cerrado (Viernes Santo)' in capsys.readouterr().out


def test_dias_lista_el_mes_con_festivos_y_descuadres(capsys):
    assert main(['dias', '2026-10']) == 0
    lineas = capsys.readouterr().out.splitlines()
    assert any('2026-10-28' in l and 'descuadre horario' in l for l in lineas)
    assert any('2026-10-24' in l and 'fin de semana' in l for l in lineas)
    assert not any('2026-11' in l for l in lineas)


def test_generar_escribe_los_ficheros_y_la_verdad(tmp_path, capsys):
    salida = str(tmp_path / 'atas')
    assert main(['generar', '2026-03-10', '--salida', salida, '--semilla', '7', '--operaciones', '3', '--seguidoras', '2']) == 0
    assert 'decisiones' in capsys.readouterr().out
    for ruta in ('Logs', os.path.join('Database', 'MyTrade.cdb'), os.path.join('Database', 'HistoryMyTrade.cdb'),
                 os.path.join('Database', 'Playbook.cdb'), 'CopyTrading.cnf', 'verdad.json'):
        assert os.path.exists(os.path.join(salida, ruta)), ruta
    with open(os.path.join(salida, 'verdad.json'), encoding='utf-8') as f:
        verdad = json.load(f)
    assert verdad['simbolo'] == 'MNQH6' and verdad['resumen']['decisiones'] == len(verdad['decisiones']) >= 1
    assert verdad['decisiones'][0]['seguidoras'] == ['APEX-00000-02', 'APEX-00000-03']


def test_un_dia_sin_mercado_da_un_error_claro_y_no_escribe_nada(tmp_path, capsys):
    salida = str(tmp_path / 'atas')
    assert main(['generar', '2026-04-03', '--salida', salida]) == 2
    assert 'Viernes Santo' in capsys.readouterr().out and not os.path.exists(salida)
