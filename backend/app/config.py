"""Configuracion central de la aplicacion, leida desde variables de entorno.

APP_ENV=production activa validaciones estrictas: si falta algo critico
(secreto JWT debil, CORS sin restringir, base de datos SQLite...), la app se
niega a arrancar en vez de quedar expuesta en silencio.
"""
import logging
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation


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
        # ---- Admision y cotizacion de envios ----
        FACTOR_VOLUMETRICO=_entero('FACTOR_VOLUMETRICO', 5000),
        SEGURO_PORCENTAJE=os.environ.get('SEGURO_PORCENTAJE', '1.0').strip(),
        VALOR_DECLARADO_MAXIMO=_entero('VALOR_DECLARADO_MAXIMO', 20000),
        MAX_BULTOS_POR_ENVIO=_entero('MAX_BULTOS_POR_ENVIO', 20),
        # Hora local del negocio respecto a UTC (Peru = -5, sin horario de verano).
        # Se usa para las fechas comprometidas de entrega.
        UTC_OFFSET_HORAS=int(os.environ.get('UTC_OFFSET_HORAS', '-5')),
        # ---- Entrega y recojo ----
        # Firma del receptor en el celular del repartidor (constancia de entrega)
        FIRMA_OBLIGATORIA=_booleano('FIRMA_OBLIGATORIA', True),
        # Intentos de PIN equivocados antes de bloquear la entrega
        MAX_INTENTOS_PIN=_entero('MAX_INTENTOS_PIN', 5),
        # Cargo por recojo a domicilio (se suma al primer envio del recojo)
        RECARGO_RECOJO=os.environ.get('RECARGO_RECOJO', '0.00').strip(),
        # ---- Contra entrega de mercaderia (recaudo) ----
        # % que el courier retiene de lo recaudado al liquidarle al remitente
        COMISION_RECAUDO_PORCENTAJE=os.environ.get('COMISION_RECAUDO_PORCENTAJE', '0').strip(),
        RECAUDO_MAXIMO=_entero('RECAUDO_MAXIMO', 10000),
        # ---- Excepciones y dinero ----
        # Devolver un envio al remitente cuesta este % del flete original
        CARGO_DEVOLUCION_PORCENTAJE=os.environ.get('CARGO_DEVOLUCION_PORCENTAJE', '50').strip(),
        # Rebaja maxima (%) sobre la tarifa que puede dar un operador; el admin no tiene tope
        DESCUENTO_MAXIMO_OPERADOR=_entero('DESCUENTO_MAXIMO_OPERADOR', 10),
        # Tope de indemnizacion cuando el cliente NO pago seguro (con seguro: el valor declarado)
        INDEMNIZACION_SIN_SEGURO=os.environ.get('INDEMNIZACION_SIN_SEGURO', '100.00').strip(),
        # ---- Avisos al cliente ----
        AVISOS_HABILITADOS=_booleano('AVISOS_HABILITADOS', True),
        # Tests: enviar en la misma peticion (en produccion va en segundo plano)
        AVISOS_SINCRONOS=_booleano('AVISOS_SINCRONOS', False),
        WHATSAPP_TOKEN=os.environ.get('WHATSAPP_TOKEN', '').strip(),
        WHATSAPP_PHONE_ID=os.environ.get('WHATSAPP_PHONE_ID', '').strip(),
        WHATSAPP_API_VERSION=os.environ.get('WHATSAPP_API_VERSION', 'v20.0').strip(),
        WHATSAPP_IDIOMA=os.environ.get('WHATSAPP_IDIOMA', 'es').strip(),
        CODIGO_PAIS_TELEFONO=os.environ.get('CODIGO_PAIS_TELEFONO', '51').strip(),
        # ---- Facturacion electronica (Nubefact) ----
        NUBEFACT_URL=os.environ.get('NUBEFACT_URL', '').strip(),
        NUBEFACT_TOKEN=os.environ.get('NUBEFACT_TOKEN', '').strip(),
        SERIE_BOLETA=os.environ.get('SERIE_BOLETA', 'B001').strip().upper(),
        SERIE_FACTURA=os.environ.get('SERIE_FACTURA', 'F001').strip().upper(),
        # Notas de credito (anulan o reducen una boleta/factura): serie propia
        SERIE_NOTA_BOLETA=os.environ.get('SERIE_NOTA_BOLETA', 'BC01').strip().upper(),
        SERIE_NOTA_FACTURA=os.environ.get('SERIE_NOTA_FACTURA', 'FC01').strip().upper(),
        IGV_PORCENTAJE=os.environ.get('IGV_PORCENTAJE', '18').strip(),
        # ---- Captcha y recuperacion de contrasena ----
        CAPTCHA_HABILITADO=_booleano('CAPTCHA_HABILITADO', True),
        MINUTOS_CAPTCHA=_entero('MINUTOS_CAPTCHA', 5),
        MINUTOS_RECUPERACION=_entero('MINUTOS_RECUPERACION', 30),
        # Base del enlace que llega por correo (la pantalla /restablecer del frontend)
        URL_FRONTEND=(os.environ.get('URL_FRONTEND') or (origenes[0] if origenes else 'http://localhost:5173')).rstrip('/'),
        SMTP_HOST=os.environ.get('SMTP_HOST', '').strip(),
        SMTP_PUERTO=_entero('SMTP_PUERTO', 587),
        SMTP_USUARIO=os.environ.get('SMTP_USUARIO', '').strip(),
        SMTP_PASSWORD=os.environ.get('SMTP_PASSWORD', ''),
        SMTP_REMITENTE=os.environ.get('SMTP_REMITENTE', '').strip(),
        # starttls (puerto 587) | ssl (puerto 465) | ninguno
        SMTP_SEGURIDAD=os.environ.get('SMTP_SEGURIDAD', 'starttls').strip().lower(),
    )

    try:
        if not (Decimal('0') <= Decimal(app.config['SEGURO_PORCENTAJE']) <= Decimal('100')):
            raise InvalidOperation
    except InvalidOperation:
        raise ConfiguracionInvalida('SEGURO_PORCENTAJE debe ser un numero entre 0 y 100 (ej. 1.0)')
    try:
        if not (Decimal('0') <= Decimal(app.config['COMISION_RECAUDO_PORCENTAJE']) <= Decimal('100')):
            raise InvalidOperation
    except InvalidOperation:
        raise ConfiguracionInvalida('COMISION_RECAUDO_PORCENTAJE debe ser un numero entre 0 y 100 (ej. 3)')
    try:
        if Decimal(app.config['RECARGO_RECOJO']) < 0:
            raise InvalidOperation
    except InvalidOperation:
        raise ConfiguracionInvalida('RECARGO_RECOJO debe ser un monto mayor o igual a 0 (ej. 5.00)')
    import re as _re
    if not _re.fullmatch(r'B[A-Z0-9]{3}', app.config['SERIE_BOLETA']) or \
            not _re.fullmatch(r'F[A-Z0-9]{3}', app.config['SERIE_FACTURA']):
        raise ConfiguracionInvalida('SERIE_BOLETA debe ser como B001 y SERIE_FACTURA como F001 (formato SUNAT)')
    if app.config['FACTOR_VOLUMETRICO'] <= 0:
        raise ConfiguracionInvalida('FACTOR_VOLUMETRICO debe ser mayor a 0 (el estandar es 5000)')

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
        if not app.config['CAPTCHA_HABILITADO']:
            errores.append('CAPTCHA_HABILITADO no puede desactivarse en produccion')
        if not app.config['URL_FRONTEND'].startswith('https://'):
            errores.append('URL_FRONTEND debe usar https:// en produccion (es el enlace de recuperacion)')
        if errores:
            raise ConfiguracionInvalida('Configuracion de produccion invalida:\n - ' + '\n - '.join(errores))

        if app.config['RATELIMIT_STORAGE_URI'].startswith('memory'):
            logging.getLogger('courrier').warning(
                'RATELIMIT_STORAGE_URI usa memoria: los limites no se comparten entre workers '
                'y se reinician en cada despliegue. Usa Redis (redis://...) con mas de un worker.'
            )
        if not app.config['SMTP_HOST']:
            logging.getLogger('courrier').warning(
                'SMTP_HOST no esta configurado: los correos de recuperacion de contrasena NO se enviaran.'
            )
