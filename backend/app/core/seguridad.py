"""Autenticacion, autorizacion, cabeceras de seguridad, manejo de errores y
auditoria. Todo lo transversal a los endpoints vive aqui."""
import json
import logging
import uuid
from functools import wraps

from flask import g, request, jsonify
from flask_jwt_extended import current_user, verify_jwt_in_request
from werkzeug.exceptions import HTTPException

from app.extensions import conexion, jwt
from app.models import UsuarioModel, AuditoriaModel
from app.core.validacion import ErrorNegocio

logger = logging.getLogger('courrier')

ROLES = ('admin', 'operador', 'repartidor')
ROLES_STAFF = ('admin', 'operador')


# ---------------------------------------------------------------- JWT ----

@jwt.user_identity_loader
def _identidad(usuario):
    return str(usuario.id) if isinstance(usuario, UsuarioModel) else str(usuario)


@jwt.additional_claims_loader
def _claims(usuario):
    if isinstance(usuario, UsuarioModel):
        return {'rol': usuario.rol, 'nombre': usuario.nombre, 'ver': usuario.tokenVersion or 0}
    return {}


@jwt.user_lookup_loader
def _cargarUsuario(_header, payload):
    """Se ejecuta en CADA peticion autenticada: si el usuario fue desactivado o
    su tokenVersion cambio (cambio de rol / contrasena / desactivacion), el
    token queda invalido al instante, sin esperar a que expire."""
    try:
        usuarioId = int(payload['sub'])
    except (KeyError, TypeError, ValueError):
        return None
    usuario = conexion.session.get(UsuarioModel, usuarioId)
    if not usuario or not usuario.activo:
        return None
    if (usuario.tokenVersion or 0) != payload.get('ver', 0):
        return None
    return usuario


@jwt.user_lookup_error_loader
def _usuarioInvalido(_header, _payload):
    return {'message': 'Tu sesion ya no es valida, vuelve a iniciar sesion'}, 401


@jwt.unauthorized_loader
def _tokenFaltante(_error):
    return {'message': 'Debes iniciar sesion (falta el token de autenticacion)'}, 401


@jwt.invalid_token_loader
def _tokenInvalido(_error):
    return {'message': 'Token invalido'}, 401


@jwt.expired_token_loader
def _tokenExpirado(_header, _payload):
    return {'message': 'Tu sesion expiro, vuelve a iniciar sesion', 'codigo': 'token_expirado'}, 401


def usuarioActual():
    return current_user


def usuarioActualId():
    return current_user.id


def rolActual():
    # El rol se toma de la base de datos (no del token), asi un cambio de rol
    # aplica en la siguiente peticion.
    return current_user.rol


def esStaff():
    return current_user.rol in ROLES_STAFF


def requiereRol(*rolesPermitidos):
    def decorador(funcion):
        @wraps(funcion)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if current_user.rol not in rolesPermitidos:
                return {'message': f'Esta accion requiere el rol: {", ".join(rolesPermitidos)}'}, 403
            return funcion(*args, **kwargs)
        return wrapper
    return decorador


def requiereLogin(funcion):
    return requiereRol(*ROLES)(funcion)


# ---------------------------------------------------------- Auditoria ----

def ipCliente():
    return (request.remote_addr or '')[:45] if request else None


def auditar(accion, entidad, entidadId=None, detalle=None, usuarioId=None):
    """Agrega un registro de auditoria a la sesion actual: se guarda en el
    MISMO commit que la operacion auditada (si la operacion falla, tampoco
    queda un registro falso)."""
    if usuarioId is None:
        try:
            usuarioId = current_user.id if current_user else None
        except RuntimeError:
            usuarioId = None
    conexion.session.add(AuditoriaModel(
        usuarioId=usuarioId,
        accion=accion,
        entidad=entidad,
        entidadId=entidadId,
        detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None,
        ip=ipCliente(),
    ))


# ------------------------------------------------ Cabeceras y errores ----

def registrarSeguridadHttp(app):
    @app.before_request
    def _asignarRequestId():
        entrante = request.headers.get('X-Request-ID', '')
        g.requestId = entrante if (0 < len(entrante) <= 64 and entrante.replace('-', '').isalnum()) else uuid.uuid4().hex

    @app.after_request
    def _cabeceras(respuesta):
        respuesta.headers['X-Request-ID'] = getattr(g, 'requestId', '')
        respuesta.headers['X-Content-Type-Options'] = 'nosniff'
        respuesta.headers['X-Frame-Options'] = 'DENY'
        respuesta.headers['Referrer-Policy'] = 'no-referrer'
        respuesta.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        respuesta.headers['Cross-Origin-Resource-Policy'] = 'same-site'
        if not request.path.startswith('/docs'):
            # La API solo devuelve JSON: no hay nada que deba ejecutarse ni
            # embeberse. Swagger UI (/docs) necesita scripts propios.
            respuesta.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        if request.headers.get('Authorization'):
            respuesta.headers['Cache-Control'] = 'no-store'
        if app.config.get('ES_PRODUCCION'):
            respuesta.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return respuesta

    @app.errorhandler(ErrorNegocio)
    def _errorNegocio(error):
        conexion.session.rollback()
        return jsonify({'message': error.mensaje}), error.status

    @app.errorhandler(HTTPException)
    def _errorHttp(error):
        mensajes = {
            404: 'Recurso no encontrado',
            405: 'Metodo no permitido',
            413: 'La peticion es demasiado grande',
            415: 'El cuerpo debe enviarse como JSON',
            429: 'Demasiadas peticiones, espera un momento e intenta de nuevo',
        }
        return jsonify({'message': mensajes.get(error.code, error.description)}), error.code

    @app.errorhandler(Exception)
    def _errorInesperado(error):
        conexion.session.rollback()
        # El detalle va al log (con el requestId para rastrearlo), nunca al
        # cliente: un str(error) puede filtrar SQL, rutas o nombres de tablas.
        logger.exception('Error no controlado [requestId=%s] %s %s',
                         getattr(g, 'requestId', '-'), request.method, request.path)
        return jsonify({
            'message': 'Ocurrio un error inesperado. Si persiste, comunica este codigo a soporte.',
            'requestId': getattr(g, 'requestId', None),
        }), 500
