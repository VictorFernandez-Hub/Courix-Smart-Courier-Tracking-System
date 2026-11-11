"""Incidencias y reclamos."""

from flask import Blueprint, request
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    PedidoModel, IncidenciaModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, usuarioActualId, ROLES_STAFF,
)
from app.core.validacion import (
    cuerpoJson, texto, opcion,
)
from app.reglas import (
    TIPOS_INCIDENCIA_VALIDOS,
)
from app.schemas import (
    IncidenciaDto,
)
from app.servicios import (
    exigirAccesoPedido, obtener, registrarHistorial,
)


bp = Blueprint('incidencias', __name__)


@bp.route('/pedido/<int:id>/incidencia', methods=['POST'])
@requiereLogin
def crearIncidencia(id):
    data = cuerpoJson()
    tipo = opcion(data, 'tipo', TIPOS_INCIDENCIA_VALIDOS, requerido=True)
    descripcion = texto(data, 'descripcion', requerido=True, maximo=2000, minimo=5)

    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)

    nueva = IncidenciaModel(pedidoId=id, usuarioId=usuarioActualId(), tipo=tipo, descripcion=descripcion)
    conexion.session.add(nueva)
    conexion.session.flush()
    # El historial solo guarda la referencia: la descripcion (que puede tener
    # datos sensibles) queda en la tabla de incidencias, con acceso restringido.
    registrarHistorial(id, pedido.estadoId, comentario=f'Incidencia #{nueva.id} registrada ({tipo})')
    conexion.session.commit()
    return {'message': 'Incidencia registrada exitosamente', 'content': IncidenciaDto().dump(nueva)}, 201


@bp.route('/incidencias', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarIncidencias():
    query = conexion.session.query(IncidenciaModel)
    estado = request.args.get('estado')
    if estado:
        query = query.filter_by(estado=estado)
    resultado = query.order_by(IncidenciaModel.fechaCreacion.desc(), IncidenciaModel.id.desc()).limit(500).all()
    return {'content': IncidenciaDto().dump(resultado, many=True)}, 200


@bp.route('/pedido/<int:id>/incidencias', methods=['GET'])
@requiereLogin
def listarIncidenciasDePedido(id):
    exigirAccesoPedido(obtener(PedidoModel, id, 'Pedido no existe'))
    resultado = conexion.session.query(IncidenciaModel).filter_by(pedidoId=id) \
        .order_by(IncidenciaModel.fechaCreacion.desc()).all()
    return {'content': IncidenciaDto().dump(resultado, many=True)}, 200


@bp.route('/incidencia/<int:id>/resolver', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def resolverIncidencia(id):
    data = cuerpoJson()
    resolucion = texto(data, 'resolucion', requerido=True, maximo=2000, minimo=5)
    incidencia = obtener(IncidenciaModel, id, 'Incidencia no existe', bloquear=True)
    if incidencia.estado == 'resuelta':
        return {'message': 'Esta incidencia ya estaba resuelta'}, 409

    incidencia.estado = 'resuelta'
    incidencia.resolucion = resolucion
    incidencia.fechaResolucion = func.now()
    auditar('incidencia_resuelta', 'incidencia', id)
    conexion.session.commit()
    return {'message': 'Incidencia marcada como resuelta'}, 200


@bp.route('/incidencia/<int:id>/en-proceso', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def marcarIncidenciaEnProceso(id):
    incidencia = obtener(IncidenciaModel, id, 'Incidencia no existe', bloquear=True)
    if incidencia.estado != 'abierta':
        return {'message': f'Solo se puede pasar a "en proceso" una incidencia abierta (esta esta "{incidencia.estado}")'}, 409
    incidencia.estado = 'en_proceso'
    conexion.session.commit()
    return {'message': 'Incidencia marcada como en proceso'}, 200
