"""Pagos y liquidacion de caja de los repartidores."""
from decimal import Decimal

from flask import Blueprint, request
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    UsuarioModel, RepartidorModel, RutaModel, PedidoModel, PagoModel, LiquidacionRutaModel,
)
from app.core.seguridad import (
    requiereRol, auditar, usuarioActualId, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorValidacion, cuerpoJson, texto, entero, dinero, opcion,
)
from app.reglas import (
    METODOS_PAGO, aDecimal,
)
from app.schemas import (
    LiquidacionRutaDto, PagoDto,
)
from app.servicios import (
    efectivoEsperadoDeRuta, nombreEstado, obtener, paginar,
)


bp = Blueprint('caja', __name__)


@bp.route('/liquidaciones/pendientes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def liquidacionesPendientes():
    rutas = conexion.session.query(RutaModel).outerjoin(
        LiquidacionRutaModel, LiquidacionRutaModel.rutaId == RutaModel.id
    ).filter(RutaModel.estado == 'completada', LiquidacionRutaModel.id.is_(None)) \
        .order_by(RutaModel.fecha).all()

    contenido = []
    for ruta in rutas:
        repartidor = conexion.session.get(RepartidorModel, ruta.repartidorId)
        usuario = conexion.session.get(UsuarioModel, repartidor.usuarioId) if repartidor else None
        contenido.append({
            'rutaId': ruta.id,
            'codigo': ruta.codigo,
            'fecha': ruta.fecha.isoformat() if ruta.fecha else None,
            'repartidorId': ruta.repartidorId,
            'repartidorNombre': usuario.nombre if usuario else None,
            'montoEsperado': str(efectivoEsperadoDeRuta(ruta.id)),
        })
    return {'content': contenido}, 200


@bp.route('/liquidaciones', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarLiquidaciones():
    query = conexion.session.query(LiquidacionRutaModel).order_by(LiquidacionRutaModel.id.desc())
    return paginar(query, LiquidacionRutaDto()), 200


@bp.route('/ruta/<int:id>/liquidar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def liquidarRuta(id):
    data = cuerpoJson()
    montoEntregado = dinero(data, 'montoEntregado', requerido=True)
    observacion = texto(data, 'observacion', maximo=1000)

    ruta = obtener(RutaModel, id, 'Ruta no existe', bloquear=True)
    if ruta.estado != 'completada':
        return {'message': 'Solo se puede liquidar una ruta completada'}, 409
    if conexion.session.query(LiquidacionRutaModel.id).filter_by(rutaId=id).first():
        return {'message': 'Esta ruta ya fue liquidada'}, 409

    esperado = efectivoEsperadoDeRuta(id)
    diferencia = montoEntregado - esperado
    if diferencia != 0 and not observacion:
        raise ErrorValidacion(f'Hay una diferencia de S/ {diferencia}: explica el motivo en "observacion"')

    liquidacion = LiquidacionRutaModel(
        rutaId=id, repartidorId=ruta.repartidorId, montoEsperado=esperado, montoEntregado=montoEntregado,
        diferencia=diferencia, observacion=observacion, recibidoPorId=usuarioActualId(),
    )
    conexion.session.add(liquidacion)
    conexion.session.flush()
    auditar('ruta_liquidada', 'ruta', id, {'esperado': esperado, 'entregado': montoEntregado, 'diferencia': diferencia})
    conexion.session.commit()

    return {
        'message': 'Liquidacion registrada' + (f' con una diferencia de S/ {diferencia}' if diferencia else ''),
        'content': LiquidacionRutaDto().dump(liquidacion),
    }, 201


@bp.route('/pagos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarPagos():
    query = conexion.session.query(PagoModel)
    estadoPago = request.args.get('estado_pago')
    if estadoPago:
        query = query.filter_by(estadoPago=estadoPago)
    metodo = request.args.get('metodo')
    if metodo:
        query = query.filter_by(metodo=metodo)

    respuesta = paginar(query.order_by(PagoModel.id.desc()), PagoDto())
    total = conexion.session.query(func.coalesce(func.sum(PagoModel.monto), 0)).filter_by(estadoPago='pagado').scalar()
    respuesta['totalCobrado'] = str(aDecimal(total))
    return respuesta, 200


@bp.route('/pagos/existentes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def pedidosConPagoRegistrado():
    crudos = request.args.get('pedido_ids', '')
    ids = [int(x) for x in crudos.split(',')[:200] if x.strip().isdigit()]
    if not ids:
        return {'content': []}, 200
    resultado = conexion.session.query(PagoModel.pedidoId).filter(PagoModel.pedidoId.in_(ids)).all()
    return {'content': [r[0] for r in resultado]}, 200


@bp.route('/pago', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearPago():
    """Pagos registrados en oficina: prepagados, credito, o regularizacion de
    un contra entrega antiguo. El cobro en la calle va por /entregar-y-cobrar."""
    data = cuerpoJson()
    pedidoId = entero(data, 'pedidoId', requerido=True)
    monto = dinero(data, 'monto', requerido=True, minimo=Decimal('0.01'))
    metodo = opcion(data, 'metodo', METODOS_PAGO, requerido=True)
    estadoPago = opcion(data, 'estadoPago', ('pendiente', 'pagado'), defecto='pendiente')
    referencia = texto(data, 'referencia', maximo=60)

    pedido = obtener(PedidoModel, pedidoId, 'Pedido no existe', bloquear=True)
    estado = nombreEstado(pedido.estadoId)
    if estado == 'cancelado':
        return {'message': 'No se puede registrar un pago para un pedido cancelado'}, 409
    if pedido.modalidadPago == 'contra_entrega' and estado != 'entregado':
        return {'message': 'Este pedido es contra entrega: el cobro se registra al entregarlo'}, 409
    if conexion.session.query(PagoModel.id).filter_by(pedidoId=pedidoId).first():
        return {'message': 'Ya existe un pago registrado para este pedido'}, 409
    if estadoPago == 'pagado' and metodo != 'efectivo' and not referencia:
        raise ErrorValidacion(f'Para pagos con {metodo} ingresa el numero de operacion')

    pago = PagoModel(
        pedidoId=pedidoId, monto=monto, metodo=metodo, referencia=referencia, estadoPago=estadoPago,
        fechaPago=func.now() if estadoPago == 'pagado' else None, registradoPorId=usuarioActualId(),
    )
    conexion.session.add(pago)
    conexion.session.flush()
    detalle = {'monto': monto, 'metodo': metodo, 'estadoPago': estadoPago}
    if monto != aDecimal(pedido.monto):
        detalle['montoPedido'] = aDecimal(pedido.monto)
    auditar('pago_registrado', 'pago', pago.id, detalle)
    conexion.session.commit()
    return {'content': PagoDto().dump(pago)}, 201


@bp.route('/pago/<int:id>/marcar-pagado', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def marcarPagoComoPagado(id):
    data = cuerpoJson()
    pago = obtener(PagoModel, id, 'Pago no existe', bloquear=True)
    if pago.estadoPago == 'pagado':
        return {'message': 'Este pago ya estaba registrado como pagado'}, 409
    referencia = texto(data, 'referencia', maximo=60)
    if referencia:
        pago.referencia = referencia
    if pago.metodo != 'efectivo' and not pago.referencia:
        raise ErrorValidacion(f'Para pagos con {pago.metodo} ingresa el numero de operacion')

    pago.estadoPago = 'pagado'
    pago.fechaPago = func.now()
    auditar('pago_marcado_pagado', 'pago', id)
    conexion.session.commit()
    return {'message': 'Pago registrado exitosamente'}, 200
