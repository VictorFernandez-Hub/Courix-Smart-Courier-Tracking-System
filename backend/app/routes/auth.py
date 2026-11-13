"""Login (por nombre de usuario + captcha), refresh token, cuenta del usuario
actual y recuperacion de contrasena por correo."""
import hashlib
import secrets
from datetime import timedelta

from flask import Blueprint, current_app
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import conexion, limiter
from app.models import (
    UsuarioModel, RecuperacionPasswordModel,
)
from app.core.captcha import generarCaptcha, verificarCaptcha
from app.core.correo import enviarCorreo
from app.core.seguridad import (
    requiereLogin, auditar, ipCliente,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, texto, validarPassword,
)
from app.reglas import (
    ahoraUtc,
)
from app.schemas import (
    UsuarioDto,
)


bp = Blueprint('auth', __name__)


HASH_FICTICIO = generate_password_hash('contrasena-ficticia-para-tiempo-constante')
MENSAJE_RECUPERACION = ('Si los datos corresponden a una cuenta activa, enviamos un enlace al correo registrado. '
                        'Revisa tu bandeja de entrada y la carpeta de spam.')
ENLACE_INVALIDO = 'El enlace no es válido o ya venció. Solicita uno nuevo'


def respuestaSesion(usuario):
    return {
        'accessToken': create_access_token(identity=usuario),
        'refreshToken': create_refresh_token(identity=usuario),
        'usuario': {'id': usuario.id, 'nombre': usuario.nombre, 'usuario': usuario.nombreUsuario,
                    'email': usuario.email, 'rol': usuario.rol, 'agenciaId': usuario.agenciaId},
    }


def _hashToken(token):
    return hashlib.sha256(token.encode()).hexdigest()


@bp.route('/captcha', methods=['GET'])
@limiter.limit('30 per minute')
def nuevoCaptcha():
    return {'content': generarCaptcha()}, 200, {'Cache-Control': 'no-store'}


@bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = cuerpoJson()
    # Primero el captcha: un bot sin resolverlo no llega a probar contrasenas
    # (ni a provocar el bloqueo de la cuenta de otra persona).
    verificarCaptcha(data)

    nombre = texto(data, 'usuario', requerido=True, maximo=30).lower()
    password = data.get('password')
    if not isinstance(password, str) or not password:
        raise ErrorValidacion('El campo "password" es obligatorio')

    usuario = conexion.session.query(UsuarioModel).filter_by(nombreUsuario=nombre).first()
    ahora = ahoraUtc()

    if usuario and usuario.bloqueadoHasta and usuario.bloqueadoHasta > ahora:
        minutos = max(1, int((usuario.bloqueadoHasta - ahora).total_seconds() // 60) + 1)
        return {'message': f'Cuenta bloqueada temporalmente por intentos fallidos. Intenta en {minutos} minuto(s)'}, 429

    if not usuario:
        check_password_hash(HASH_FICTICIO, password)  # mismo tiempo de respuesta: no revela si el usuario existe
        return {'message': 'Usuario o contraseña incorrectos'}, 401

    if not check_password_hash(usuario.passwordHash, password):
        usuario.intentosFallidos = (usuario.intentosFallidos or 0) + 1
        if usuario.intentosFallidos >= current_app.config['MAX_INTENTOS_LOGIN']:
            usuario.bloqueadoHasta = ahora + timedelta(minutes=current_app.config['MINUTOS_BLOQUEO_LOGIN'])
            usuario.intentosFallidos = 0
            auditar('login_bloqueado', 'usuario', usuario.id, usuarioId=usuario.id)
        conexion.session.commit()
        return {'message': 'Usuario o contraseña incorrectos'}, 401

    if not usuario.activo:
        return {'message': 'Usuario inactivo'}, 403

    usuario.intentosFallidos = 0
    usuario.bloqueadoHasta = None
    usuario.ultimoLogin = ahora
    conexion.session.commit()

    return {'message': 'Login exitoso', **respuestaSesion(usuario)}, 200


@bp.route('/password/olvide', methods=['POST'])
@limiter.limit('5 per 15 minutes')
def solicitarRecuperacion():
    """Envia un enlace de un solo uso al correo registrado del usuario.
    La respuesta es SIEMPRE la misma: no revela si el usuario o correo existe."""
    data = cuerpoJson()
    verificarCaptcha(data)
    identificador = texto(data, 'identificador', requerido=True, maximo=120).lower()

    campo = UsuarioModel.email if '@' in identificador else UsuarioModel.nombreUsuario
    usuario = conexion.session.query(UsuarioModel).filter(campo == identificador).first()
    if not usuario or not usuario.activo:
        return {'message': MENSAJE_RECUPERACION}, 200

    ahora = ahoraUtc()
    pendientes = conexion.session.query(RecuperacionPasswordModel).filter(
        RecuperacionPasswordModel.usuarioId == usuario.id,
        RecuperacionPasswordModel.usadoEn.is_(None),
        RecuperacionPasswordModel.expira > ahora,
    ).all()
    # Anti-spam: como maximo un correo cada 2 minutos por cuenta
    if any(p.fechaCreacion and p.fechaCreacion > ahora - timedelta(minutes=2) for p in pendientes):
        return {'message': MENSAJE_RECUPERACION}, 200
    for anterior in pendientes:  # solo el ultimo enlace enviado sirve
        anterior.usadoEn = ahora

    token = secrets.token_urlsafe(32)
    minutos = current_app.config['MINUTOS_RECUPERACION']
    conexion.session.add(RecuperacionPasswordModel(
        usuarioId=usuario.id, tokenHash=_hashToken(token), expira=ahora + timedelta(minutes=minutos),
        ipSolicitud=ipCliente(), fechaCreacion=ahora,
    ))
    auditar('recuperacion_solicitada', 'usuario', usuario.id, usuarioId=usuario.id)
    conexion.session.commit()

    enlace = f"{current_app.config['URL_FRONTEND']}/restablecer?token={token}"
    enviarCorreo(
        usuario.email,
        'Courrier Express - Recupera tu contraseña',
        f'Hola {usuario.nombre}:\n\n'
        f'Recibimos una solicitud para restablecer la contraseña del usuario "{usuario.nombreUsuario}".\n\n'
        f'Abre este enlace para crear una nueva (vence en {minutos} minutos y solo sirve una vez):\n{enlace}\n\n'
        'Si no fuiste tú, ignora este correo: tu contraseña actual sigue funcionando.\n',
        enlaceDesarrollo=enlace,
    )
    return {'message': MENSAJE_RECUPERACION}, 200


@bp.route('/password/restablecer', methods=['POST'])
@limiter.limit('10 per 15 minutes')
def restablecerConToken():
    data = cuerpoJson()
    token = data.get('token')
    if not isinstance(token, str) or not (20 <= len(token) <= 100):
        raise ErrorNegocio(ENLACE_INVALIDO, 400)
    nueva = validarPassword(data.get('passwordNueva'))

    ahora = ahoraUtc()
    solicitud = conexion.session.query(RecuperacionPasswordModel).filter_by(
        tokenHash=_hashToken(token)).with_for_update().first()
    if not solicitud or solicitud.usadoEn is not None or solicitud.expira < ahora:
        raise ErrorNegocio(ENLACE_INVALIDO, 400)
    usuario = conexion.session.get(UsuarioModel, solicitud.usuarioId)
    if not usuario or not usuario.activo:
        raise ErrorNegocio(ENLACE_INVALIDO, 400)

    usuario.passwordHash = generate_password_hash(nueva)
    usuario.tokenVersion = (usuario.tokenVersion or 0) + 1  # cierra todas las sesiones abiertas
    usuario.intentosFallidos = 0
    usuario.bloqueadoHasta = None
    conexion.session.query(RecuperacionPasswordModel).filter(
        RecuperacionPasswordModel.usuarioId == usuario.id,
        RecuperacionPasswordModel.usadoEn.is_(None),
    ).update({RecuperacionPasswordModel.usadoEn: ahora}, synchronize_session=False)
    auditar('password_recuperada', 'usuario', usuario.id, usuarioId=usuario.id)
    conexion.session.commit()
    return {'message': 'Contraseña actualizada. Ya puedes iniciar sesión con tu nueva contraseña'}, 200


@bp.route('/token/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refrescarToken():
    # El refresh token tiene vida maxima fija (JWT_REFRESH_HORAS): la sesion
    # no se puede extender indefinidamente. El user_lookup_loader ya verifico
    # que el usuario siga activo y que su tokenVersion no haya cambiado.
    return {'accessToken': create_access_token(identity=current_user)}, 200


@bp.route('/usuario/me', methods=['GET'])
@requiereLogin
def miPerfil():
    return {'content': UsuarioDto().dump(current_user)}, 200


@bp.route('/usuario/me/password', methods=['POST'])
@requiereLogin
@limiter.limit('5 per minute')
def cambiarMiPassword():
    data = cuerpoJson()
    actual = data.get('passwordActual')
    nueva = data.get('passwordNueva')
    if not isinstance(actual, str) or not check_password_hash(current_user.passwordHash, actual):
        raise ErrorNegocio('La contrasena actual no es correcta', 400)
    validarPassword(nueva)
    if check_password_hash(current_user.passwordHash, nueva):
        raise ErrorValidacion('La nueva contrasena debe ser distinta a la actual')

    current_user.passwordHash = generate_password_hash(nueva)
    current_user.tokenVersion = (current_user.tokenVersion or 0) + 1  # cierra las demas sesiones
    auditar('password_cambiada', 'usuario', current_user.id)
    conexion.session.commit()
    return {'message': 'Contrasena actualizada', **respuestaSesion(current_user)}, 200
