"""Gestion de usuarios (solo admin)."""

from flask import Blueprint
from werkzeug.security import generate_password_hash

from app.extensions import conexion
from app.models import (
    UsuarioModel, RepartidorModel,
)
from app.core.seguridad import (
    requiereRol, auditar, usuarioActualId, ROLES,
)
from app.core.validacion import (
    ErrorNegocio, cuerpoJson, texto, opcion, email, validarPassword,
)
from app.schemas import (
    UsuarioDto,
)
from app.servicios import (
    obtener, paginar, rutaActivaDe,
)


bp = Blueprint('usuarios', __name__)


def contarAdminsActivos(excluirId=None):
    query = conexion.session.query(UsuarioModel).filter_by(rol='admin', activo=True)
    if excluirId:
        query = query.filter(UsuarioModel.id != excluirId)
    return query.count()


@bp.route('/usuario', methods=['POST'])
@requiereRol('admin')
def crearUsuario():
    # Ya no existe el "modo arranque" sin token: el primer administrador se
    # crea solo por consola con `flask crear-admin`.
    data = cuerpoJson()
    nombre = texto(data, 'nombre', requerido=True, maximo=100, minimo=2)
    correo = email(data, 'email')
    rol = opcion(data, 'rol', ROLES, requerido=True)
    password = validarPassword(data.get('password'))

    if conexion.session.query(UsuarioModel).filter_by(email=correo).first():
        return {'message': 'Ya existe un usuario con ese email'}, 409

    nuevo = UsuarioModel(nombre=nombre, email=correo, passwordHash=generate_password_hash(password), rol=rol)
    conexion.session.add(nuevo)
    conexion.session.flush()
    auditar('usuario_creado', 'usuario', nuevo.id, {'rol': rol, 'email': correo})
    conexion.session.commit()

    return {
        'message': 'Usuario creado exitosamente',
        'content': {'id': nuevo.id, 'nombre': nuevo.nombre, 'rol': nuevo.rol},
    }, 201


@bp.route('/usuario/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarUsuario(id):
    data = cuerpoJson()
    usuario = obtener(UsuarioModel, id, 'Usuario no existe')

    if 'nombre' in data:
        usuario.nombre = texto(data, 'nombre', requerido=True, maximo=100, minimo=2)

    if 'rol' in data:
        nuevoRol = opcion(data, 'rol', ROLES, requerido=True)
        if nuevoRol != usuario.rol:
            if usuario.rol == 'admin' and contarAdminsActivos(excluirId=usuario.id) == 0:
                raise ErrorNegocio('No puedes quitar el rol al ultimo administrador activo', 409)
            if usuario.rol == 'repartidor' and rutaActivaDe(
                    getattr(conexion.session.query(RepartidorModel).filter_by(usuarioId=usuario.id).first(), 'id', -1)):
                raise ErrorNegocio('Este repartidor tiene una ruta activa; cierrala antes de cambiarle el rol', 409)
            auditar('rol_cambiado', 'usuario', usuario.id, {'de': usuario.rol, 'a': nuevoRol})
            usuario.rol = nuevoRol
            usuario.tokenVersion = (usuario.tokenVersion or 0) + 1

    conexion.session.commit()
    return {'message': 'Usuario actualizado exitosamente'}, 200


@bp.route('/usuario/<int:id>/password', methods=['POST'])
@requiereRol('admin')
def restablecerPassword(id):
    data = cuerpoJson()
    usuario = obtener(UsuarioModel, id, 'Usuario no existe')
    usuario.passwordHash = generate_password_hash(validarPassword(data.get('passwordNueva')))
    usuario.tokenVersion = (usuario.tokenVersion or 0) + 1
    usuario.intentosFallidos = 0
    usuario.bloqueadoHasta = None
    auditar('password_restablecida', 'usuario', usuario.id)
    conexion.session.commit()
    return {'message': 'Contrasena restablecida. El usuario debe iniciar sesion de nuevo'}, 200


@bp.route('/usuario/<int:id>/desactivar', methods=['POST'])
@requiereRol('admin')
def desactivarUsuario(id):
    usuario = obtener(UsuarioModel, id, 'Usuario no existe')
    if usuario.id == usuarioActualId():
        return {'message': 'No puedes desactivar tu propia cuenta'}, 400

    usuario.activo = False
    usuario.tokenVersion = (usuario.tokenVersion or 0) + 1  # sus sesiones abiertas mueren ya
    perfil = conexion.session.query(RepartidorModel).filter_by(usuarioId=usuario.id).first()
    if perfil:
        perfil.disponible = False
    auditar('usuario_desactivado', 'usuario', usuario.id)
    conexion.session.commit()
    return {'message': 'Usuario desactivado exitosamente'}, 200


@bp.route('/usuario/<int:id>/activar', methods=['POST'])
@requiereRol('admin')
def activarUsuario(id):
    usuario = obtener(UsuarioModel, id, 'Usuario no existe')
    usuario.activo = True
    usuario.intentosFallidos = 0
    usuario.bloqueadoHasta = None
    auditar('usuario_activado', 'usuario', usuario.id)
    conexion.session.commit()
    return {'message': 'Usuario activado exitosamente'}, 200


@bp.route('/usuarios', methods=['GET'])
@requiereRol('admin')
def listarUsuarios():
    query = conexion.session.query(UsuarioModel).order_by(UsuarioModel.id)
    return paginar(query, UsuarioDto()), 200
