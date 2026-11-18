"""Generador de logs de pruebas: operaciones ficticias con verdad conocida, sobre días de mercado reales.

Genera, para un día de calendario REAL (con sus festivos, cierres anticipados y cambios de hora), operaciones ficticias con su
verdad conocida, escritas en los formatos de ATAS (logs, .cdb y CopyTrading.cnf). Sirve para probar un diario de operaciones sin
usar datos de nadie:

    from datetime import date
    from testeo_historico import generar, escribir, decisiones

    esc = generar(date(2026, 3, 10), semilla=7, operaciones=4)     # un día con descuadre horario EE. UU.–España
    escribir(esc, 'carpeta_de_atas')                               # ficheros listos para leer
    esperado = decisiones(esc)                                     # lo que el diario debe reconstruir
"""

from . import calendario
from .atas import escribir
from .escenario import Cuenta, Escenario, Operacion, Salida, generar
from .verdad import decisiones, resumen

__version__ = '0.1.0'
__all__ = ['calendario', 'escribir', 'generar', 'decisiones', 'resumen', 'Cuenta', 'Escenario', 'Operacion', 'Salida']
