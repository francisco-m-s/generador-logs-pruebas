"""Calendario REAL de sesiones de los futuros de índices de CME (NQ, MNQ, ES, MES) para un día de calendario concreto.

Por qué importa para probar un diario de operaciones:
  - qué días hay sesión (fines de semana y festivos de EE. UU.);
  - a qué hora UTC empieza y acaba cada sesión (el día CME cambia a las 17:00 de Chicago, hora local);
  - la hora de Madrid de una hora de Nueva York: casi todo el año la diferencia es de 6 h, pero EE. UU. y la Unión Europea cambian
    de hora en fechas distintas y durante unas semanas la diferencia es de 5 h. Esos días «descuadrados» son los que rompen los
    diarios mal hechos.

APROXIMADO: los festivos y los cierres anticipados siguen las reglas habituales de CME Group, pero CME puede cambiarlos cada año.
Verifica contra el calendario oficial antes de usar esto como verdad.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
NUEVA_YORK = ZoneInfo('America/New_York')
CHICAGO = ZoneInfo('America/Chicago')
MADRID = ZoneInfo('Europe/Madrid')

CERRADOS = {'Año Nuevo', 'Viernes Santo', 'Navidad'}          # sin sesión; el resto de festivos cierra antes de tiempo
_LUNES, _JUEVES, _VIERNES = 0, 3, 4
_CODIGO_MES = {3: 'H', 6: 'M', 9: 'U', 12: 'Z'}


class DiaSinSesion(ValueError):
    """El mercado no abre ese día (fin de semana o festivo)."""


def _enesimo_dia(anio, mes, dia_semana, n):
    primero = date(anio, mes, 1)
    primero += timedelta(days=(dia_semana - primero.weekday()) % 7)
    return primero + timedelta(weeks=n - 1)


def _ultimo_dia(anio, mes, dia_semana):
    fin = (date(anio, mes + 1, 1) if mes < 12 else date(anio + 1, 1, 1)) - timedelta(days=1)
    return fin - timedelta(days=(fin.weekday() - dia_semana) % 7)


def _pascua(anio):
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ele = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ele) // 451
    mes, dia = divmod(h + ele - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _observado(f):
    """Un festivo en sábado se observa el viernes; en domingo, el lunes."""
    if f.weekday() == 5:
        return f - timedelta(days=1)
    return f + timedelta(days=1) if f.weekday() == 6 else f


def festivos(anio):
    """{fecha: nombre} de los festivos de EE. UU. que afectan a la sesión de los futuros de índices."""
    accion_de_gracias = _enesimo_dia(anio, 11, _JUEVES, 4)
    return {
        _observado(date(anio, 1, 1)): 'Año Nuevo',
        _enesimo_dia(anio, 1, _LUNES, 3): 'Martin Luther King',
        _enesimo_dia(anio, 2, _LUNES, 3): 'Presidents Day',
        _pascua(anio) - timedelta(days=2): 'Viernes Santo',
        _ultimo_dia(anio, 5, _LUNES): 'Memorial Day',
        _observado(date(anio, 6, 19)): 'Juneteenth',
        _observado(date(anio, 7, 4)): 'Día de la Independencia',
        _enesimo_dia(anio, 9, _LUNES, 1): 'Labor Day',
        accion_de_gracias: 'Thanksgiving',
        accion_de_gracias + timedelta(days=1): 'Día después de Thanksgiving',
        _observado(date(anio, 12, 25)): 'Navidad',
    }


def estado_del_dia(f):
    """('normal' | 'cierre_anticipado' | 'cerrado', motivo)."""
    if f.weekday() >= 5:
        return 'cerrado', 'fin de semana'
    nombre = festivos(f.year).get(f)
    if nombre is None:
        return 'normal', ''
    return ('cerrado' if nombre in CERRADOS else 'cierre_anticipado'), nombre


@dataclass(frozen=True)
class Sesion:
    fecha: date                     # fecha de la sesión CME («trade date»)
    estado: str                     # normal | cierre_anticipado | cerrado
    motivo: str                     # festivo o fin de semana; vacío si es un día normal
    apertura_utc: datetime = None   # 17:00 de Chicago del día natural anterior
    cierre_utc: datetime = None     # 16:00 de Chicago (12:00 si cierra antes)
    rth_inicio_utc: datetime = None  # 09:30 de Nueva York
    rth_fin_utc: datetime = None    # 16:00 de Nueva York (13:00 si cierra antes)


def _utc(f, hora, zona):
    return datetime.combine(f, hora, tzinfo=zona).astimezone(UTC)


def sesion(f):
    """La sesión CME de la fecha `f` (un `date`). Con el mercado cerrado, solo `estado` y `motivo` vienen rellenos."""
    estado, motivo = estado_del_dia(f)
    if estado == 'cerrado':
        return Sesion(f, estado, motivo)
    anticipado = estado == 'cierre_anticipado'
    return Sesion(
        f, estado, motivo,
        apertura_utc=_utc(f - timedelta(days=1), time(17, 0), CHICAGO),
        cierre_utc=_utc(f, time(12, 0) if anticipado else time(16, 0), CHICAGO),
        rth_inicio_utc=_utc(f, time(9, 30), NUEVA_YORK),
        rth_fin_utc=_utc(f, time(13, 0) if anticipado else time(16, 0), NUEVA_YORK))


def ventana_operativa(f, desde=time(9, 30), hasta=time(12, 0)):
    """(inicio_utc, fin_utc) de la ventana de operativa, dada en hora de Nueva York y recortada al horario de la sesión."""
    s = sesion(f)
    if s.estado == 'cerrado':
        raise DiaSinSesion(f'{f.isoformat()}: {s.motivo}')
    inicio, fin = _utc(f, desde, NUEVA_YORK), _utc(f, hasta, NUEVA_YORK)
    return max(inicio, s.rth_inicio_utc), min(fin, s.rth_fin_utc)


def diferencia_madrid_nueva_york(f):
    """Horas que Madrid va por delante de Nueva York ese día (normalmente 6; 5 en las semanas descuadradas)."""
    mediodia = datetime.combine(f, time(12, 0), tzinfo=UTC)
    return (mediodia.astimezone(MADRID).utcoffset() - mediodia.astimezone(NUEVA_YORK).utcoffset()) / timedelta(hours=1)


def descuadre_horario(f):
    """True si EE. UU. y la Unión Europea están en horarios de verano distintos (Madrid−Nueva York ≠ 6 h)."""
    return diferencia_madrid_nueva_york(f) != 6


def contrato_frontal(f, raiz='MNQ'):
    """Código del contrato trimestral frontal ese día (p. ej. MNQZ6). Se pasa al siguiente 8 días antes del vencimiento."""
    for anio in (f.year, f.year + 1):
        for mes in (3, 6, 9, 12):
            vencimiento = _enesimo_dia(anio, mes, _VIERNES, 3)
            if f < vencimiento - timedelta(days=8):
                return f'{raiz}{_CODIGO_MES[mes]}{anio % 10}'
    raise ValueError(f'sin contrato para {f}')
