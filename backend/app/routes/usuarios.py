"""Gestion de usuarios (solo admin)."""

from flask import Blueprint
from werkzeug.security import generate_password_hash

from app.extensions import conexion
from app.models import (
    UsuarioModel, RepartidorModel, AlmacenModel,
)
from app.core.seguridad import (
    requiereRol, auditar, usuarioActualId, ROLES,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, texto, opcion, email, nombreUsuario, validarPassword,
    dni, telefono, entero,
)
from app.schemas import (
    UsuarioDto,
)
from app.servicios import (
    obtener, paginar, rutaActivaDe,
)


bp = Blueprint('usuarios', __name__)


def leerAgencia(data):
    """Agencia donde trabaja el usuario (opcional). Un operador con agencia
    solo ve y opera los envios que salen o llegan a ella."""
    agenciaId = entero(data, 'agenciaId')
    if agenciaId:
        agencia = obtener(AlmacenModel, agenciaId, 'La agencia no existe')
        if not agencia.activo:
            raise ErrorValidacion('La agencia esta desactivada')
    return agenciaId


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
    login = nombreUsuario(data, 'usuario')
    correo = email(data, 'email')
    rol = opcion(data, 'rol', ROLES, requerido=True)
    password = validarPassword(data.get('password'))
    documento = dni(data, 'dni')
    if not documento:
        raise ErrorValidacion('El DNI es obligatorio')
    celular = telefono(data, 'celular', requerido=True)
    direccion = texto(data, 'direccion', maximo=200)
    agenciaId = leerAgencia(data)

    if conexion.session.query(UsuarioModel).filter_by(nombreUsuario=login).first():
        return {'message': 'Ya existe un usuario con ese nombre de usuario'}, 409
    if conexion.session.query(UsuarioModel).filter_by(email=correo).first():
        return {'message': 'Ya existe un usuario con ese email'}, 409
    if conexion.session.query(UsuarioModel).filter_by(dni=documento).first():
        return {'message': 'Ya existe un usuario con ese DNI'}, 409

    nuevo = UsuarioModel(nombre=nombre, nombreUsuario=login, email=correo, dni=documento,
                         celular=celular, direccion=direccion, agenciaId=agenciaId,
                         passwordHash=generate_password_hash(password), rol=rol)
    conexion.session.add(nuevo)
    conexion.session.flush()
    auditar('usuario_creado', 'usuario', nuevo.id, {'rol': rol, 'usuario': login, 'email': correo})
    conexion.session.commit()

    return {
        'message': 'Usuario creado exitosamente',
        'content': {'id': nuevo.id, 'nombre': nuevo.nombre, 'usuario': nuevo.nombreUsuario, 'rol': nuevo.rol},
    }, 201


@bp.route('/usuario/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarUsuario(id):
    data = cuerpoJson()
    usuario = obtener(UsuarioModel, id, 'Usuario no existe')

    if 'nombre' in data:
        usuario.nombre = texto(data, 'nombre', requerido=True, maximo=100, minimo=2)

    if 'usuario' in data:
        login = nombreUsuario(data, 'usuario')
        if login != usuario.nombreUsuario:
            if conexion.session.query(UsuarioModel).filter(
                    UsuarioModel.nombreUsuario == login, UsuarioModel.id != usuario.id).first():
                return {'message': 'Ya existe un usuario con ese nombre de usuario'}, 409
            auditar('usuario_renombrado', 'usuario', usuario.id, {'de': usuario.nombreUsuario, 'a': login})
            usuario.nombreUsuario = login

    if 'email' in data:
        correo = email(data, 'email')
        if correo != usuario.email:
            if conexion.session.query(UsuarioModel).filter(
                    UsuarioModel.email == correo, UsuarioModel.id != usuario.id).first():
                return {'message': 'Ya existe un usuario con ese email'}, 409
            # El correo es el destino de la recuperacion de contrasena: queda auditado
            auditar('email_cambiado', 'usuario', usuario.id, {'de': usuario.email, 'a': correo})
            usuario.email = correo

    if 'dni' in data:
        documento = dni(data, 'dni')
        if documento and conexion.session.query(UsuarioModel).filter(
                UsuarioModel.dni == documento, UsuarioModel.id != usuario.id).first():
            return {'message': 'Ya existe un usuario con ese DNI'}, 409
        usuario.dni = documento

    if 'celular' in data:
        usuario.celular = telefono(data, 'celular')

    if 'direccion' in data:
        usuario.direccion = texto(data, 'direccion', maximo=200)

    if 'agenciaId' in data:
        nueva = leerAgencia(data)
        if nueva != usuario.agenciaId:
            auditar('agencia_cambiada', 'usuario', usuario.id, {'de': usuario.agenciaId, 'a': nueva})
            usuario.agenciaId = nueva
            # Cambia lo que puede ver: sus sesiones abiertas se renuevan
            usuario.tokenVersion = (usuario.tokenVersion or 0) + 1

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
