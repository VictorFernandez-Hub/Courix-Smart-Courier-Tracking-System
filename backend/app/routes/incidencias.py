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
from datetime import timedelta

from app.admision import ahoraLocal
from app.core.seguridad import rolActual
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, entero, texto, opcion,
)
from app.models import UsuarioModel
from app.reglas import (
    PRIORIDAD_POR_TIPO, PRIORIDADES_INCIDENCIA, TIPOS_INCIDENCIA_VALIDOS,
)
from app.schemas import (
    IncidenciaDto,
)
from app.servicios import (
    agenciaDelUsuario, exigirAccesoPedido, filtrarPorAgencia, obtener, registrarHistorial,
)


def aplicarPlazo(incidencia, prioridad=None):
    """Prioridad segun el tipo (perdida o dano = alta) y fecha limite segun la prioridad."""
    incidencia.prioridad = prioridad or PRIORIDAD_POR_TIPO.get(incidencia.tipo, 'media')
    incidencia.fechaLimite = ahoraLocal() + timedelta(hours=PRIORIDADES_INCIDENCIA[incidencia.prioridad])


def _dump(incidencias):
    ahora = ahoraLocal()
    ids = {i.responsableId for i in incidencias if i.responsableId}
    nombres = {u.id: u.nombre for u in conexion.session.query(UsuarioModel).filter(
        UsuarioModel.id.in_(ids or {-1})).all()}
    filas = IncidenciaDto().dump(incidencias, many=True)
    for fila, i in zip(filas, incidencias):
        fila['responsable'] = nombres.get(i.responsableId)
        fila['vencida'] = bool(i.estado != 'resuelta' and i.fechaLimite and i.fechaLimite < ahora)
    return filas


def _exigirAccesoIncidencia(incidencia):
    exigirAccesoPedido(conexion.session.get(PedidoModel, incidencia.pedidoId))


bp = Blueprint('incidencias', __name__)


@bp.route('/pedido/<int:id>/incidencia', methods=['POST'])
@requiereLogin
def crearIncidencia(id):
    data = cuerpoJson()
    tipo = opcion(data, 'tipo', TIPOS_INCIDENCIA_VALIDOS, requerido=True)
    descripcion = texto(data, 'descripcion', requerido=True, maximo=2000, minimo=5)
    prioridad = opcion(data, 'prioridad', tuple(PRIORIDADES_INCIDENCIA))

    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)

    nueva = IncidenciaModel(pedidoId=id, usuarioId=usuarioActualId(), tipo=tipo, descripcion=descripcion)
    aplicarPlazo(nueva, prioridad)
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
    propia = agenciaDelUsuario()
    if propia:
        query = filtrarPorAgencia(query.join(PedidoModel, IncidenciaModel.pedidoId == PedidoModel.id), propia)
    estado = request.args.get('estado')
    if estado:
        query = query.filter(IncidenciaModel.estado.in_(estado.split(',')))
    if request.args.get('mias') in ('1', 'true'):
        query = query.filter(IncidenciaModel.responsableId == usuarioActualId())
    if request.args.get('vencidas') in ('1', 'true'):
        query = query.filter(IncidenciaModel.estado != 'resuelta', IncidenciaModel.fechaLimite < ahoraLocal())
    # Lo abierto primero, y dentro de eso lo que vence antes
    resultado = query.order_by((IncidenciaModel.estado == 'resuelta'), IncidenciaModel.fechaLimite,
                               IncidenciaModel.id.desc()).limit(500).all()
    return {'content': _dump(resultado)}, 200


@bp.route('/pedido/<int:id>/incidencias', methods=['GET'])
@requiereLogin
def listarIncidenciasDePedido(id):
    exigirAccesoPedido(obtener(PedidoModel, id, 'Pedido no existe'))
    resultado = conexion.session.query(IncidenciaModel).filter_by(pedidoId=id) \
        .order_by(IncidenciaModel.fechaCreacion.desc()).all()
    return {'content': _dump(resultado)}, 200


@bp.route('/incidencia/<int:id>/resolver', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def resolverIncidencia(id):
    data = cuerpoJson()
    resolucion = texto(data, 'resolucion', requerido=True, maximo=2000, minimo=5)
    incidencia = obtener(IncidenciaModel, id, 'Incidencia no existe', bloquear=True)
    _exigirAccesoIncidencia(incidencia)
    if incidencia.estado == 'resuelta':
        return {'message': 'Esta incidencia ya estaba resuelta'}, 409

    incidencia.estado = 'resuelta'
    incidencia.resolucion = resolucion
    incidencia.fechaResolucion = func.now()
    auditar('incidencia_resuelta', 'incidencia', id)
    conexion.session.commit()
    return {'message': 'Incidencia marcada como resuelta'}, 200


@bp.route('/incidencia/<int:id>/asignar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def asignarIncidencia(id):
    """Toda incidencia tiene un dueno: quien la atiende hasta resolverla.
    Cambiar la prioridad recalcula el plazo."""
    data = cuerpoJson()
    responsableId = entero(data, 'responsableId', requerido=True)
    prioridad = opcion(data, 'prioridad', tuple(PRIORIDADES_INCIDENCIA))
    incidencia = obtener(IncidenciaModel, id, 'Incidencia no existe', bloquear=True)
    _exigirAccesoIncidencia(incidencia)
    if incidencia.estado == 'resuelta':
        raise ErrorNegocio('La incidencia ya esta resuelta', 409)
    responsable = obtener(UsuarioModel, responsableId, 'El usuario no existe')
    if not responsable.activo or responsable.rol not in ('admin', 'operador'):
        raise ErrorValidacion('El responsable debe ser un administrador u operador activo')
    if rolActual() != 'admin' and responsableId != usuarioActualId():
        raise ErrorNegocio('Un operador solo puede tomar la incidencia para si mismo', 403)
    incidencia.responsableId = responsableId
    if prioridad and prioridad != incidencia.prioridad:
        aplicarPlazo(incidencia, prioridad)
    if incidencia.estado == 'abierta':
        incidencia.estado = 'en_proceso'
    auditar('incidencia_asignada', 'incidencia', id, {'responsable': responsable.nombre, 'prioridad': incidencia.prioridad})
    conexion.session.commit()
    return {'message': f'Incidencia asignada a {responsable.nombre}', 'content': _dump([incidencia])[0]}, 200


@bp.route('/incidencia/<int:id>/en-proceso', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def marcarIncidenciaEnProceso(id):
    incidencia = obtener(IncidenciaModel, id, 'Incidencia no existe', bloquear=True)
    _exigirAccesoIncidencia(incidencia)
    if incidencia.estado != 'abierta':
        return {'message': f'Solo se puede pasar a "en proceso" una incidencia abierta (esta esta "{incidencia.estado}")'}, 409
    incidencia.estado = 'en_proceso'
    if not incidencia.responsableId:
        incidencia.responsableId = usuarioActualId()  # quien la toma, la atiende
    conexion.session.commit()
    return {'message': 'Incidencia marcada como en proceso'}, 200
