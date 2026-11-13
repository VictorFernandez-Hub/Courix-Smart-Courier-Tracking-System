"""Zonas, tarifas y catalogo de estados (las agencias estan en almacenes.py)."""

from flask import Blueprint, request

from app.extensions import conexion
from app.models import (
    ZonaModel, AlmacenModel, EstadoPedidoModel, TarifaZonaModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorNegocio, cuerpoJson, texto, entero, dinero, opcion,
)
from app.reglas import (
    TIPOS_SERVICIO,
)
from app.schemas import (
    EstadoPedidoDto, TarifaZonaDto, ZonaDto,
)
from app.servicios import (
    buscarTarifa, exigirZonaActiva, obtener,
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
    servicio = opcion(data, 'tipoServicio', TIPOS_SERVICIO, defecto='estandar')
    precioBase = dinero(data, 'precioBase', requerido=True)
    precioPorKg = dinero(data, 'precioPorKg', requerido=True)
    precioMinimo = dinero(data, 'precioMinimo') or 0
    dias = entero(data, 'diasEntrega', minimo=0, maximo=60)
    exigirZonaActiva(origen)
    exigirZonaActiva(destino)

    if buscarTarifa(origen, destino, servicio):
        return {'message': f'Ya existe una tarifa {servicio} activa para ese par de zonas, edita esa en vez de crear otra'}, 409

    nueva = TarifaZonaModel(zonaOrigenId=origen, zonaDestinoId=destino, tipoServicio=servicio, precioBase=precioBase,
                            precioPorKg=precioPorKg, precioMinimo=precioMinimo, diasEntrega=dias)
    conexion.session.add(nueva)
    conexion.session.flush()
    auditar('tarifa_creada', 'tarifa', nueva.id, {'servicio': servicio, 'precioBase': precioBase,
                                                  'precioPorKg': precioPorKg, 'precioMinimo': precioMinimo})
    conexion.session.commit()
    return {'content': TarifaZonaDto().dump(nueva)}, 201


@bp.route('/tarifa/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarTarifa(id):
    data = cuerpoJson()
    tarifa = obtener(TarifaZonaModel, id, 'Tarifa no existe')
    campos = ('precioBase', 'precioPorKg', 'precioMinimo', 'diasEntrega')
    antes = {c: getattr(tarifa, c) for c in campos}
    if 'precioBase' in data:
        tarifa.precioBase = dinero(data, 'precioBase', requerido=True)
    if 'precioPorKg' in data:
        tarifa.precioPorKg = dinero(data, 'precioPorKg', requerido=True)
    if 'precioMinimo' in data:
        tarifa.precioMinimo = dinero(data, 'precioMinimo') or 0
    if 'diasEntrega' in data:
        tarifa.diasEntrega = entero(data, 'diasEntrega', minimo=0, maximo=60)
    auditar('tarifa_editada', 'tarifa', id, {'antes': antes, 'despues': {c: getattr(tarifa, c) for c in campos}})
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


@bp.route('/estados', methods=['GET'])
def listarEstados():
    resultado = conexion.session.query(EstadoPedidoModel).order_by(EstadoPedidoModel.orden).all()
    return {'content': EstadoPedidoDto().dump(resultado, many=True)}, 200
