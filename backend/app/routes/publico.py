"""Endpoints publicos sin login: rastreo y bot de WhatsApp."""

from flask import Blueprint, request

from app.extensions import conexion, limiter
from app.models import (
    ClienteModel, EstadoPedidoModel, PedidoModel, HistorialEstadoModel,
)
from app.reglas import (
    MENSAJES_PUBLICOS,
)
from app.servicios import (
    nombreEstado,
)


bp = Blueprint('publico', __name__)


@bp.route('/pedido/<int:id>/estado-actual', methods=['GET'])
@limiter.limit('30 per minute')
def estadoActualPedido(id):
    """Para el bot de WhatsApp. Exige el telefono registrado: sin el, la
    respuesta es identica a "no existe", asi nadie puede enumerar pedidos
    probando ids consecutivos."""
    noEncontrado = ({'message': 'No encontramos un pedido con ese numero y telefono'}, 404)
    telefonoConsulta = ''.join(c for c in request.args.get('telefono', '') if c.isdigit() or c == '+')[:20]
    if len(telefonoConsulta) < 6:
        return noEncontrado

    pedido = conexion.session.get(PedidoModel, id)
    cliente = conexion.session.get(ClienteModel, pedido.clienteId) if pedido else None
    if not cliente or cliente.telefono != telefonoConsulta:
        return noEncontrado

    estado = nombreEstado(pedido.estadoId)
    return {
        'pedido': pedido.id,
        'codigoGuia': pedido.codigoGuia,
        'cliente': cliente.nombre,
        'estado': estado,
        'mensaje': MENSAJES_PUBLICOS.get(estado),
    }, 200


@bp.route('/rastreo/<string:codigoGuia>', methods=['GET'])
@limiter.limit('30 per minute')
def rastrearPorCodigoGuia(codigoGuia):
    """Rastreo publico por codigo de guia. Solo devuelve mensajes fijos por
    estado: nunca comentarios internos, nombres, direcciones ni incidencias."""
    codigo = codigoGuia.strip().upper()
    if not (6 <= len(codigo) <= 30) or not all(c.isalnum() or c == '-' for c in codigo):
        return {'message': 'No encontramos ningun envio con ese codigo de guia'}, 404

    pedido = conexion.session.query(PedidoModel).filter_by(codigoGuia=codigo).first()
    if not pedido:
        return {'message': 'No encontramos ningun envio con ese codigo de guia'}, 404

    historial = conexion.session.query(HistorialEstadoModel).filter_by(pedidoId=pedido.id) \
        .order_by(HistorialEstadoModel.fecha, HistorialEstadoModel.id).all()
    nombres = {e.id: e.nombre for e in conexion.session.query(EstadoPedidoModel).all()}

    eventos = []
    ultimo = None
    for h in historial:
        estado = nombres.get(h.estadoId)
        if estado == ultimo:
            continue  # notas internas sobre el mismo estado (ej. incidencias) no se publican
        ultimo = estado
        eventos.append({
            'fecha': h.fecha.isoformat() if h.fecha else None,
            'estado': estado,
            'mensaje': MENSAJES_PUBLICOS.get(estado, ''),
        })

    return {
        'codigoGuia': pedido.codigoGuia,
        'estadoActual': nombres.get(pedido.estadoId),
        'historial': eventos,
    }, 200
