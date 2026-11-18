# Generador de logs de pruebas

*Operaciones ficticias con verdad conocida, sobre días de mercado reales, en formato ATAS.*

Genera **operaciones ficticias con su verdad conocida** sobre **días de mercado reales** y las escribe en los formatos de la plataforma
ATAS (logs, `.cdb` y `CopyTrading.cnf`). Sirve para probar un diario de operaciones, un backtest de gestión o cualquier lector de
ficheros de ATAS **sin usar los datos de nadie**.

> Los precios y las operaciones son inventados (o los precios, tuyos). Lo real es el **calendario**: qué días hay sesión, a qué hora
> UTC empieza y acaba cada una, los festivos de EE. UU., los cierres anticipados y los días en que EE. UU. y España tienen el
> cambio de hora desfasado. Ahí es donde fallan los diarios mal hechos.

## Por qué «días reales»
Casi todo el año Madrid va 6 horas por delante de Nueva York, pero EE. UU. y la Unión Europea cambian de hora en fechas distintas:
durante unas tres semanas en primavera y una en otoño la diferencia es de **5 horas**, y la ventana 09:30–12:00 de Nueva York cae
a las 14:30–17:00 de Madrid en vez de a las 15:30–18:00. El día CME, además, cambia a las 17:00 de Chicago. Un diario que
asigne mal una operación a su sesión o a su hora falla justo esos días; con este generador los pruebas a propósito.

```
python -m testeo_historico calendario 2026-03-10
  2026-03-10 (mar): normal
    ventana 09:30–12:00 NY = 14:30–17:00 Madrid
    Madrid − Nueva York: 5 h   ← DÍA DESCUADRADO (EE. UU. y la UE en horarios distintos)
```

## Instalación
Python 3.9 o superior. Sin dependencias salvo `tzdata` (Windows no trae la base de zonas horarias).

```
pip install -r requirements.txt          # o: pip install .
```

## Uso
```
python -m testeo_historico generar 2026-03-10 --salida carpeta_de_atas --semilla 7 --operaciones 4 --seguidoras 1
python -m testeo_historico calendario 2026-04-03          # Viernes Santo: cerrado
python -m testeo_historico dias 2026-10                   # el mes entero, con festivos y descuadres horarios
```
`generar` escribe en la carpeta que le indiques (que hace de carpeta de ATAS) y una `verdad.json` con lo que cualquier diario correcto
tiene que reconstruir. Opciones: `--contratos`, `--simbolo` (NQ, MNQ, ES, MES), `--version-atas` (8.0.14 u 8.0.15),
`--desfase-pc` (segundos que el reloj del PC se adelanta o atrasa) y `--precios-csv`.

Desde Python:

```python
from datetime import date
from testeo_historico import generar, escribir, decisiones

esc = generar(date(2026, 3, 10), semilla=7, operaciones=4)
escribir(esc, 'carpeta_de_atas')
esperado = decisiones(esc)        # [{'numero': 1, 'cuenta': ..., 'ticks': 3.0, 'tipo_cierre': 'Mercado', ...}, ...]
```

La misma `(fecha, semilla, parámetros)` da **exactamente los mismos ficheros**, byte a byte.

## Qué escribe
| Fichero | Contenido |
|---|---|
| `Logs/app_AAAAMMDD.log` | Hora de Madrid del reloj del PC, con milisegundos. Por operación: orden a mercado, fill, stop y objetivo, salida y cancelación del otro, posición y cartera. |
| `Database/MyTrade.cdb` | Un fill por fila (entrada y salida), con hora UTC al segundo. |
| `Database/HistoryMyTrade.cdb` | Una fila por operación cerrada, con volumen con signo, ticks y PnL. |
| `Database/Playbook.cdb` | Estrategias de ejemplo. |
| `CopyTrading.cnf` | Cuenta líder y seguidoras (JSON con BOM). |
| `verdad.json` | Las decisiones esperadas: ticks, horas, tipo de cierre (`TP`, `SL`, `Mercado`) y resultado bruto. |

Las dos versiones de ATAS que cambian el formato están soportadas: hasta la **8.0.14** (decimal con coma, Id de fill numérico) y desde la
**8.0.15** (decimal con punto, Id de fill `<OrderId>_<n>`). Los formatos se han comprobado contra ficheros reales de ATAS (solo la
estructura) y `tests/test_formatos.py` los fija con las mismas expresiones regulares que usa el demonio de referencia.

## Precios reales (opcional)
Con `--precios-csv` las operaciones se resuelven sobre **tus** precios históricos en lugar del camino ficticio. CSV con cabecera
`utc,precio` (hora UTC en ISO 8601):

```
utc,precio
2026-03-10T14:30:00,21000.25
2026-03-10T14:30:01,21000.50
```
Los precios no se incluyen en este proyecto: aporta los que tengas licencia para usar.

## Cómo se usa para comprobar un diario
1. Genera varios días (normales, descuadrados, de cierre anticipado) y las dos versiones de ATAS.
2. Pasa los ficheros por tu diario.
3. Compara con `verdad.json`: **ticks, horas y tipo de cierre** deben coincidir exactamente. El resultado en dólares es **bruto**
   (los ficheros traen comisión 0); cada diario descuenta las de su firma.

El diario de referencia ([diario-operativa-atas](https://github.com/francisco-m-s/diario-operativa-atas)) reconstruye exactamente la
verdad en sus pruebas de integración: ambas versiones de ATAS, días descuadrados y de cierre anticipado, desfases del reloj del PC,
varios contratos y copias.

## Límites
- Los **festivos y cierres anticipados** siguen las reglas habituales de CME Group, pero CME puede cambiarlos cada año: verifica contra
  su calendario oficial antes de usarlos como verdad.
- El camino de precios sintético **no imita ningún mercado real**; sirve para que haya movimiento.
- Un solo símbolo por día y una sesión por log. Las órdenes son siempre a mercado con stop y objetivo (o cierre a mercado).
- Lo que no genera: reconexiones, saltos del reloj del PC en mitad de la sesión, fills parciales ni órdenes rechazadas.

## Tests
```
pip install -r requirements.txt
python -m pytest -q
```

## Seguridad al contribuir
No subas credenciales ni datos reales. Activa el *hook* una vez por clon: `git config core.hooksPath .githooks`; cada commit pasa por
`herramientas/comprobar_secretos.py`, que bloquea claves y credenciales y **nunca imprime el valor**.

## Licencia
MIT: software libre y gratuito. Ver [`LICENSE`](LICENSE).

## Aviso
Herramienta de pruebas: **no es asesoramiento financiero** ni garantiza resultados, y se ofrece «tal cual». ATAS, Rithmic y CME Group
son marcas de sus propietarios; este proyecto no está afiliado a ellas ni respaldado por ellas.
