"""Comprueba que no se cuela ninguna credencial ni dato personal antes de subir el repositorio a GitHub.

  python herramientas/comprobar_secretos.py                 # lo que git subiría (con repo) o el árbol sin lo ignorado (sin repo)
  python herramientas/comprobar_secretos.py --publico MAPA  # además, ERROR si queda algún ID real de la lista MAPA (JSON {real: ficticio})

Sale con código 1 si hay algún ERROR. NUNCA imprime el valor encontrado: solo NIVEL fichero:línea TIPO.
Solo biblioteca estándar. Lo usan `.githooks/pre-commit` y la integración continua."""

import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BYTES = 5_000_000

SECRETOS = {
    'BLOQUE_CLAVE_PRIVADA': re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    'CUENTA_DE_SERVICIO_GOOGLE': re.compile(r'"type"\s*:\s*"service_account"|"private_key_id"\s*:'),
    'API_KEY_GOOGLE': re.compile(r'AIza[0-9A-Za-z_\-]{35}'),
    'TOKEN_OAUTH_GOOGLE': re.compile(r'ya29\.[0-9A-Za-z_\-]{20,}'),
    'TOKEN_GITHUB': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}'),
    'CLAVE_AWS': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'TOKEN_SLACK': re.compile(r'xox[abprs]-[0-9A-Za-z\-]{10,}'),
}
_ASIGNA = r'(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*'
ASIGNACION_TEXTO = re.compile(_ASIGNA + r'[\'"]?[A-Za-z0-9_\-./+=]{16,}')
ASIGNACION_PY = re.compile(_ASIGNA + r'[\'"][A-Za-z0-9_\-./+=]{16,}[\'"]')      # en código solo cuenta lo que va entre comillas
RUTA_USUARIO = re.compile(r'(?i)\b[a-z]:[\\/]+users[\\/]+([^\\/\s"\'<>]+)')
USUARIOS_GENERICOS = {'usuario', 'user', 'tu_usuario', 'public', 'default', 'xxx'}
NOMBRE_SECRETO = re.compile(r'(?i)credencial|credential|service[_-]?account|\.pem$|\.p12$|\.pfx$|(^|[\\/])\.env|\.json$')
SIN_REPO_OMITIR_DIRS = {'backups', '__pycache__', '.pytest_cache', '.git'}
SIN_REPO_OMITIR_FICHEROS = {'cuentas.yaml', 'config.local.yaml', 'atas_v4.log'}


def ficheros_candidatos():
    """Rutas relativas de lo que se subiría: `git ls-files` si hay repositorio; si no, el árbol sin lo que .gitignore excluye."""
    try:
        r = subprocess.run(['git', '-C', RAIZ, 'ls-files', '--cached', '--others', '--exclude-standard'],
                           capture_output=True, text=True, encoding='utf-8', check=True)
        return [p for p in r.stdout.splitlines() if p]
    except (OSError, subprocess.CalledProcessError):
        pass
    out = []
    for d, ds, fs in os.walk(RAIZ):
        ds[:] = [x for x in ds if x not in SIN_REPO_OMITIR_DIRS]
        for f in fs:
            if f in SIN_REPO_OMITIR_FICHEROS or f.endswith(('.sqlite', '.sqlite-wal', '.sqlite-shm', '.pyc')):
                continue
            out.append(os.path.relpath(os.path.join(d, f), RAIZ))
    return out


def leer_texto(ruta):
    """Texto del fichero, o None si es binario o enorme (no se puede escanear como texto)."""
    try:
        if os.path.getsize(ruta) > MAX_BYTES:
            return None
        datos = open(ruta, 'rb').read()
    except OSError:
        return None
    return None if b'\x00' in datos else datos.decode('utf-8', errors='ignore')


def escanear(rel, texto, ids_reales):
    """[(nivel, línea, tipo)] de un fichero; sin valores."""
    hallazgos = []
    if NOMBRE_SECRETO.search(rel.replace(os.sep, '/')):
        hallazgos.append(('ERROR', 0, 'NOMBRE_DE_FICHERO_DE_SECRETO'))
    asignacion = ASIGNACION_PY if rel.endswith('.py') else ASIGNACION_TEXTO
    for n, linea in enumerate(texto.splitlines(), 1):
        for tipo, rx in SECRETOS.items():
            if rx.search(linea):
                hallazgos.append(('ERROR', n, tipo))
        if asignacion.search(linea):
            hallazgos.append(('ERROR', n, 'ASIGNACION_DE_SECRETO'))
        for m in RUTA_USUARIO.finditer(linea):
            if m.group(1).lower() not in USUARIOS_GENERICOS:
                hallazgos.append(('ERROR' if ids_reales is not None else 'AVISO', n, 'RUTA_CON_NOMBRE_DE_USUARIO'))
        for rx in (ids_reales or ()):
            if rx.search(linea):
                hallazgos.append(('ERROR', n, 'ID_REAL_SIN_ANONIMIZAR'))
    return hallazgos


def main(argv):
    global RAIZ
    if '--raiz' in argv:                                         # analizar otra carpeta (la exportación pública)
        RAIZ = os.path.abspath(argv[argv.index('--raiz') + 1])
    ids_reales = None
    if '--publico' in argv:
        mapa = json.load(open(argv[argv.index('--publico') + 1], encoding='utf-8'))
        ids_reales = [re.compile(r'(?<![0-9A-Za-z])' + re.escape(k) + r'(?!\d)', re.IGNORECASE) for k in mapa]
    errores = avisos = 0
    for rel in sorted(ficheros_candidatos()):
        ruta = os.path.join(RAIZ, rel)
        texto = leer_texto(ruta)
        hallazgos = escanear(rel, texto, ids_reales) if texto is not None else escanear(rel, '', ids_reales)
        for nivel, n, tipo in hallazgos:
            errores += nivel == 'ERROR'
            avisos += nivel == 'AVISO'
            print(f'{nivel} {rel.replace(os.sep, "/")}:{n} {tipo}')
    modo = 'PÚBLICO' if ids_reales is not None else 'PRIVADO'
    print(f'[{modo}] {errores} errores, {avisos} avisos.' + ('' if errores else ' Nada que bloquee la subida.'))
    return 1 if errores else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
