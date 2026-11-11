"""Configuracion central de la aplicacion, leida desde variables de entorno.

APP_ENV=production activa validaciones estrictas: si falta algo critico
(secreto JWT debil, CORS sin restringir, base de datos SQLite...), la app se
niega a arrancar en vez de quedar expuesta en silencio.
"""
import logging
import os
from datetime import timedelta


class ConfiguracionInvalida(RuntimeError):
    pass


def _entero(nombre, defecto):
    valor = os.environ.get(nombre)
    if valor in (None, ''):
        return defecto
    try:
        return int(valor)
    except ValueError:
        raise ConfiguracionInvalida(f'La variable {nombre} debe ser un numero entero (valor actual: "{valor}")')


def _booleano(nombre, defecto):
    valor = os.environ.get(nombre)
    if valor in (None, ''):
        return defecto
    return valor.strip().lower() in ('1', 'true', 'si', 'yes', 'on')


def cargarConfiguracion(app):
    entorno = os.environ.get('APP_ENV', 'development').strip().lower()
    esProduccion = entorno == 'production'

    try:
        urlBaseDatos = os.environ['DATABASE_URL']
        secretoJwt = os.environ['JWT_SECRET_KEY']
    except KeyError as faltante:
        raise ConfiguracionInvalida(f'Falta la variable de entorno obligatoria {faltante}')

    origenes = [o.strip() for o in os.environ.get('ORIGENES_PERMITIDOS', '').split(',') if o.strip()]

    app.config.update(
        APP_ENV=entorno,
        ES_PRODUCCION=esProduccion,
        SQLALCHEMY_DATABASE_URI=urlBaseDatos,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=secretoJwt,
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=_entero('JWT_ACCESS_MINUTOS', 30)),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(hours=_entero('JWT_REFRESH_HORAS', 12)),
        JWT_TOKEN_LOCATION=['headers'],
        # Tope del tamano de cualquier peticion: la foto de evidencia
        # comprimida pesa ~200-400 KB; 6 MB deja margen sin permitir abusos.
        MAX_CONTENT_LENGTH=_entero('MAX_PETICION_MB', 6) * 1024 * 1024,
        ORIGENES_PERMITIDOS=origenes,
        DOCS_HABILITADOS=_booleano('DOCS_HABILITADOS', not esProduccion),
        PROXY_SALTOS=_entero('PROXY_SALTOS', 0),
        RATELIMIT_ENABLED=_booleano('RATELIMIT_ENABLED', True),
        RATELIMIT_STORAGE_URI=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
        RATELIMIT_HEADERS_ENABLED=True,
        # ---- Reglas de negocio configurables ----
        MAX_INTENTOS_ENTREGA=_entero('MAX_INTENTOS_ENTREGA', 3),
        MAX_PEDIDOS_POR_RUTA=_entero('MAX_PEDIDOS_POR_RUTA', 40),
        MAX_RUTAS_SIN_LIQUIDAR=_entero('MAX_RUTAS_SIN_LIQUIDAR', 1),
        EVIDENCIA_OBLIGATORIA=_booleano('EVIDENCIA_OBLIGATORIA', False),
        MAX_INTENTOS_LOGIN=_entero('MAX_INTENTOS_LOGIN', 5),
        MINUTOS_BLOQUEO_LOGIN=_entero('MINUTOS_BLOQUEO_LOGIN', 15),
    )

    if not urlBaseDatos.startswith('sqlite'):
        # Sin esto MySQL cierra conexiones inactivas y la siguiente peticion
        # falla con "MySQL server has gone away".
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 280,
            'pool_size': _entero('DB_POOL_SIZE', 10),
            'max_overflow': _entero('DB_MAX_OVERFLOW', 20),
        }

    if esProduccion:
        errores = []
        if len(secretoJwt) < 32:
            errores.append('JWT_SECRET_KEY debe tener al menos 32 caracteres aleatorios '
                           '(genera uno con: python -c "import secrets; print(secrets.token_urlsafe(48))")')
        if not origenes:
            errores.append('ORIGENES_PERMITIDOS es obligatorio en produccion (ej. https://app.tuempresa.pe)')
        if '*' in origenes:
            errores.append('ORIGENES_PERMITIDOS no puede ser "*" en produccion')
        if urlBaseDatos.startswith('sqlite'):
            errores.append('DATABASE_URL no puede ser SQLite en produccion')
        if errores:
            raise ConfiguracionInvalida('Configuracion de produccion invalida:\n - ' + '\n - '.join(errores))

        if app.config['RATELIMIT_STORAGE_URI'].startswith('memory'):
            logging.getLogger('courrier').warning(
                'RATELIMIT_STORAGE_URI usa memoria: los limites no se comparten entre workers '
                'y se reinician en cada despliegue. Usa Redis (redis://...) con mas de un worker.'
            )
