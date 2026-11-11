"""Login, refresh token y cuenta del usuario actual."""
from datetime import timedelta

from flask import Blueprint, current_app
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import conexion, limiter
from app.models import (
    UsuarioModel,
)
from app.core.seguridad import (
    requiereLogin, auditar,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, email, validarPassword,
)
from app.reglas import (
    ahoraUtc,
)
from app.schemas import (
    UsuarioDto,
)


bp = Blueprint('auth', __name__)


HASH_FICTICIO = generate_password_hash('contrasena-ficticia-para-tiempo-constante')


def respuestaSesion(usuario):
    return {
        'accessToken': create_access_token(identity=usuario),
        'refreshToken': create_refresh_token(identity=usuario),
        'usuario': {'id': usuario.id, 'nombre': usuario.nombre, 'email': usuario.email, 'rol': usuario.rol},
    }


@bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = cuerpoJson()
    correo = email(data, 'email')
    password = data.get('password')
    if not isinstance(password, str) or not password:
        raise ErrorValidacion('El campo "password" es obligatorio')

    usuario = conexion.session.query(UsuarioModel).filter_by(email=correo).first()
    ahora = ahoraUtc()

    if usuario and usuario.bloqueadoHasta and usuario.bloqueadoHasta > ahora:
        minutos = max(1, int((usuario.bloqueadoHasta - ahora).total_seconds() // 60) + 1)
        return {'message': f'Cuenta bloqueada temporalmente por intentos fallidos. Intenta en {minutos} minuto(s)'}, 429

    if not usuario:
        check_password_hash(HASH_FICTICIO, password)  # mismo tiempo de respuesta: no revela si el email existe
        return {'message': 'Credenciales incorrectas'}, 401

    if not check_password_hash(usuario.passwordHash, password):
        usuario.intentosFallidos = (usuario.intentosFallidos or 0) + 1
        if usuario.intentosFallidos >= current_app.config['MAX_INTENTOS_LOGIN']:
            usuario.bloqueadoHasta = ahora + timedelta(minutes=current_app.config['MINUTOS_BLOQUEO_LOGIN'])
            usuario.intentosFallidos = 0
            auditar('login_bloqueado', 'usuario', usuario.id, usuarioId=usuario.id)
        conexion.session.commit()
        return {'message': 'Credenciales incorrectas'}, 401

    if not usuario.activo:
        return {'message': 'Usuario inactivo'}, 403

    usuario.intentosFallidos = 0
    usuario.bloqueadoHasta = None
    usuario.ultimoLogin = ahora
    conexion.session.commit()

    return {'message': 'Login exitoso', **respuestaSesion(usuario)}, 200


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
