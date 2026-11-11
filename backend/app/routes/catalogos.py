"""Zonas, tarifas, almacenes y catalogo de estados."""

from flask import Blueprint, request

from app.extensions import conexion
from app.models import (
    ZonaModel, AlmacenModel, EstadoPedidoModel, TarifaZonaModel, PedidoModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorNegocio, cuerpoJson, texto, entero, dinero, coordenada, telefono,
)
from app.reglas import (
    ESTADOS_ACTIVOS,
)
from app.schemas import (
    AlmacenDto, EstadoPedidoDto, TarifaZonaDto, ZonaDto,
)
from app.servicios import (
    buscarTarifa, exigirZonaActiva, idsEstados, obtener,
)


bp = Blueprint('catalogos', __name__)


@bp.route('/zonas', methods=['GET'])
@requiereLogin
def listarZonas():
    query = conexion.session.query(ZonaModel)
    if request.args.get('incluir_inactivas') != 'true':
        query = query.filter_by(activo=True)
    return {'content': ZonaDto().dump(query.order_by(ZonaModel.nombre).all(), many=True)}, 200


@bp.route('/zona', methods=['POST'])
@requiereRol('admin')
def crearZona():
    data = cuerpoJson()
    nueva = ZonaModel(
        nombre=texto(data, 'nombre', requerido=True, maximo=100),
        referencia=texto(data, 'referencia', maximo=500),
    )
    conexion.session.add(nueva)
    conexion.session.commit()
    return {'content': ZonaDto().dump(nueva)}, 201


@bp.route('/zona/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarZona(id):
    data = cuerpoJson()
    zona = obtener(ZonaModel, id, 'Zona no existe')
    if 'nombre' in data:
        zona.nombre = texto(data, 'nombre', requerido=True, maximo=100)
    if 'referencia' in data:
        zona.referencia = texto(data, 'referencia', maximo=500)
    conexion.session.commit()
    return {'message': 'Zona actualizada exitosamente', 'content': ZonaDto().dump(zona)}, 200


@bp.route('/zona/<int:id>/desactivar', methods=['POST'])
@requiereRol('admin')
def desactivarZona(id):
    zona = obtener(ZonaModel, id, 'Zona no existe')
    almacenesActivos = conexion.session.query(AlmacenModel).filter_by(zonaId=id, activo=True).count()
    if almacenesActivos:
        raise ErrorNegocio(f'La zona tiene {almacenesActivos} almacen(es) activo(s); desactivalos primero', 409)
    zona.activo = False
    auditar('zona_desactivada', 'zona', id)
    conexion.session.commit()
    return {'message': 'Zona desactivada exitosamente'}, 200


@bp.route('/zona/<int:id>/activar', methods=['POST'])
@requiereRol('admin')
def activarZona(id):
    zona = obtener(ZonaModel, id, 'Zona no existe')
    zona.activo = True
    conexion.session.commit()
    return {'message': 'Zona activada exitosamente'}, 200




@bp.route('/tarifas', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarTarifas():
    resultado = conexion.session.query(TarifaZonaModel).filter_by(activo=True).all()
    return {'content': TarifaZonaDto().dump(resultado, many=True)}, 200


@bp.route('/tarifa', methods=['POST'])
@requiereRol('admin')
def crearTarifa():
    data = cuerpoJson()
    origen = entero(data, 'zonaOrigenId', requerido=True)
    destino = entero(data, 'zonaDestinoId', requerido=True)
    precioBase = dinero(data, 'precioBase', requerido=True)
    precioPorKg = dinero(data, 'precioPorKg', requerido=True)
    exigirZonaActiva(origen)
    exigirZonaActiva(destino)

    if buscarTarifa(origen, destino):
        return {'message': 'Ya existe una tarifa activa para ese par de zonas, edita esa en vez de crear otra'}, 409

    nueva = TarifaZonaModel(zonaOrigenId=origen, zonaDestinoId=destino, precioBase=precioBase, precioPorKg=precioPorKg)
    conexion.session.add(nueva)
    conexion.session.flush()
    auditar('tarifa_creada', 'tarifa', nueva.id, {'precioBase': precioBase, 'precioPorKg': precioPorKg})
    conexion.session.commit()
    return {'content': TarifaZonaDto().dump(nueva)}, 201


@bp.route('/tarifa/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarTarifa(id):
    data = cuerpoJson()
    tarifa = obtener(TarifaZonaModel, id, 'Tarifa no existe')
    antes = {'precioBase': tarifa.precioBase, 'precioPorKg': tarifa.precioPorKg}
    if 'precioBase' in data:
        tarifa.precioBase = dinero(data, 'precioBase', requerido=True)
    if 'precioPorKg' in data:
        tarifa.precioPorKg = dinero(data, 'precioPorKg', requerido=True)
    auditar('tarifa_editada', 'tarifa', id, {'antes': antes, 'despues': {
        'precioBase': tarifa.precioBase, 'precioPorKg': tarifa.precioPorKg}})
    conexion.session.commit()
    return {'message': 'Tarifa actualizada exitosamente', 'content': TarifaZonaDto().dump(tarifa)}, 200


@bp.route('/tarifa/<int:id>', methods=['DELETE'])
@requiereRol('admin')
def eliminarTarifa(id):
    tarifa = obtener(TarifaZonaModel, id, 'Tarifa no existe')
    tarifa.activo = False
    auditar('tarifa_desactivada', 'tarifa', id)
    conexion.session.commit()
    return {'message': 'Tarifa desactivada exitosamente'}, 200


@bp.route('/almacen', methods=['POST'])
@requiereRol('admin')
def crearAlmacen():
    data = cuerpoJson()
    zonaId = entero(data, 'zonaId', requerido=True)
    exigirZonaActiva(zonaId)
    nuevo = AlmacenModel(
        nombre=texto(data, 'nombre', requerido=True, maximo=100),
        calle=texto(data, 'calle', requerido=True, maximo=300),
        zonaId=zonaId,
        telefono=telefono(data),
        latitud=coordenada(data, 'latitud', 'lat'),
        longitud=coordenada(data, 'longitud', 'lon'),
    )
    conexion.session.add(nuevo)
    conexion.session.commit()
    return {'content': AlmacenDto().dump(nuevo)}, 201


@bp.route('/almacen/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarAlmacen(id):
    data = cuerpoJson()
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')

    if 'nombre' in data:
        almacen.nombre = texto(data, 'nombre', requerido=True, maximo=100)
    if 'calle' in data:
        almacen.calle = texto(data, 'calle', requerido=True, maximo=300)
    if 'zonaId' in data:
        nuevaZona = entero(data, 'zonaId', requerido=True)
        if nuevaZona != almacen.zonaId:
            exigirZonaActiva(nuevaZona)
            activos = conexion.session.query(PedidoModel).filter(
                PedidoModel.almacenId == id, PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS))
            ).count()
            if activos:
                raise ErrorNegocio(f'No se puede cambiar la zona: el almacen tiene {activos} pedido(s) en curso', 409)
            almacen.zonaId = nuevaZona
    if 'telefono' in data:
        almacen.telefono = telefono(data)
    if 'latitud' in data:
        almacen.latitud = coordenada(data, 'latitud', 'lat')
    if 'longitud' in data:
        almacen.longitud = coordenada(data, 'longitud', 'lon')

    conexion.session.commit()
    return {'message': 'Almacen actualizado exitosamente', 'content': AlmacenDto().dump(almacen)}, 200


@bp.route('/almacenes', methods=['GET'])
@requiereLogin
def listarAlmacenes():
    query = conexion.session.query(AlmacenModel)
    if request.args.get('incluir_inactivos') != 'true':
        query = query.filter_by(activo=True)
    return {'content': AlmacenDto().dump(query.order_by(AlmacenModel.nombre).all(), many=True)}, 200


@bp.route('/almacen/<int:id>/desactivar', methods=['POST'])
@requiereRol('admin')
def desactivarAlmacen(id):
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    activos = conexion.session.query(PedidoModel).filter(
        PedidoModel.almacenId == id, PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS))
    ).count()
    if activos:
        raise ErrorNegocio(f'El almacen tiene {activos} pedido(s) en curso; no se puede desactivar todavia', 409)
    almacen.activo = False
    auditar('almacen_desactivado', 'almacen', id)
    conexion.session.commit()
    return {'message': 'Almacen desactivado exitosamente'}, 200


@bp.route('/almacen/<int:id>/activar', methods=['POST'])
@requiereRol('admin')
def activarAlmacen(id):
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    almacen.activo = True
    conexion.session.commit()
    return {'message': 'Almacen activado exitosamente'}, 200


@bp.route('/estados', methods=['GET'])
def listarEstados():
    resultado = conexion.session.query(EstadoPedidoModel).order_by(EstadoPedidoModel.orden).all()
    return {'content': EstadoPedidoDto().dump(resultado, many=True)}, 200
