"""Perfiles de repartidor y disponibilidad."""

from flask import Blueprint

from app.extensions import conexion
from app.models import (
    UsuarioModel, RepartidorModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, usuarioActualId, rolActual,
)
from app.core.validacion import (
    ErrorNegocio, cuerpoJson, texto, entero, booleano, telefono,
)
from app.schemas import (
    RepartidorDto,
)
from app.servicios import (
    exigirZonaActiva, miRepartidor, obtener, rutaActivaDe,
)


bp = Blueprint('repartidores', __name__)


@bp.route('/repartidores', methods=['GET'])
@requiereLogin
def listarRepartidores():
    query = conexion.session.query(RepartidorModel)
    if rolActual() == 'repartidor':
        query = query.filter_by(usuarioId=usuarioActualId())  # solo su propio perfil
    return {'content': RepartidorDto().dump(query.all(), many=True)}, 200


@bp.route('/repartidor', methods=['POST'])
@requiereRol('admin')
def crearRepartidor():
    data = cuerpoJson()
    usuarioId = entero(data, 'usuarioId', requerido=True)
    usuario = obtener(UsuarioModel, usuarioId, 'Usuario no existe')
    if usuario.rol != 'repartidor':
        return {'message': 'Ese usuario no tiene el rol "repartidor"'}, 400
    if conexion.session.query(RepartidorModel).filter_by(usuarioId=usuarioId).first():
        return {'message': 'Este usuario ya tiene un perfil de repartidor'}, 409

    zonaId = entero(data, 'zonaId')
    exigirZonaActiva(zonaId)
    nuevo = RepartidorModel(
        usuarioId=usuarioId,
        zonaId=zonaId,
        telefono=telefono(data),
        vehiculo=texto(data, 'vehiculo', maximo=50),
        placa=texto(data, 'placa', maximo=20),
    )
    conexion.session.add(nuevo)
    conexion.session.commit()
    return {'content': RepartidorDto().dump(nuevo)}, 201


@bp.route('/repartidor/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarRepartidor(id):
    data = cuerpoJson()
    repartidor = obtener(RepartidorModel, id, 'Repartidor no existe', bloquear=True)

    if 'zonaId' in data:
        nuevaZona = entero(data, 'zonaId')
        if nuevaZona != repartidor.zonaId:
            exigirZonaActiva(nuevaZona)
            if rutaActivaDe(repartidor.id):
                raise ErrorNegocio('No se puede cambiar la zona mientras el repartidor tiene una ruta activa', 409)
            repartidor.zonaId = nuevaZona
    if 'telefono' in data:
        repartidor.telefono = telefono(data)
    if 'vehiculo' in data:
        repartidor.vehiculo = texto(data, 'vehiculo', maximo=50)
    if 'placa' in data:
        repartidor.placa = texto(data, 'placa', maximo=20)
    if 'disponible' in data:
        repartidor.disponible = booleano(data, 'disponible')

    conexion.session.commit()
    return {'message': 'Repartidor actualizado exitosamente', 'content': RepartidorDto().dump(repartidor)}, 200


@bp.route('/repartidor/<int:id>/disponibilidad', methods=['POST'])
@requiereRol('admin', 'repartidor')
def cambiarDisponibilidadRepartidor(id):
    data = cuerpoJson()
    if 'disponible' not in data:
        return {'message': 'Falta el campo "disponible" (true o false)'}, 400
    disponible = booleano(data, 'disponible')

    repartidor = obtener(RepartidorModel, id, 'Repartidor no existe')
    if rolActual() != 'admin':
        perfil = miRepartidor()
        if not perfil or perfil.id != id:
            return {'message': 'Solo puedes cambiar tu propia disponibilidad'}, 403

    repartidor.disponible = disponible
    conexion.session.commit()
    return {
        'message': 'Ya estas disponible para recibir pedidos' if disponible else 'Quedaste marcado como no disponible',
        'content': RepartidorDto().dump(repartidor),
    }, 200
