"""Contra entrega de mercaderia (recaudo).

Una tienda (remitente) envia un producto y pide que el courier le cobre el
precio al destinatario. Ese dinero NO es ingreso del courier: es una deuda
con el remitente que se le paga en una liquidacion, menos la comision.

Ciclo de un recaudo:
  cobrado en la puerta (/entregar-y-cobrar)
    -> en caja: el efectivo ya se rindio al liquidar la ruta del repartidor
       (los pagos digitales llegan directo a la cuenta: no esperan nada)
    -> liquidado: se le pago al remitente

Solo lo que esta "en caja" se puede liquidar: no se le paga al remitente un
efectivo que el repartidor todavia tiene en el bolsillo.
"""
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, current_app, request
from sqlalchemy import case, func, or_

from app.extensions import conexion
from app.models import (
    ClienteModel, LiquidacionRecaudoModel, LiquidacionRutaModel, PedidoModel, RecaudoModel,
)
from app.core.seguridad import requiereRol, auditar, usuarioActualId, ROLES_STAFF
from app.core.validacion import CENTIMO, ErrorNegocio, ErrorValidacion, cuerpoJson, entero, opcion, texto
from app.reglas import METODOS_PAGO, aDecimal
from app.servicios import agenciaDelUsuario, filtrarPorAgencia, obtener

bp = Blueprint('recaudos', __name__)


def _visibles():
    query = conexion.session.query(RecaudoModel).join(PedidoModel, RecaudoModel.pedidoId == PedidoModel.id)
    return filtrarPorAgencia(query, agenciaDelUsuario())


def _enCaja():
    """Condicion: el dinero ya esta en poder de la empresa."""
    rendidas = conexion.session.query(LiquidacionRutaModel.rutaId)
    return or_(RecaudoModel.metodo != 'efectivo', RecaudoModel.rutaId.is_(None), RecaudoModel.rutaId.in_(rendidas))


def _comision(monto):
    porcentaje = Decimal(current_app.config['COMISION_RECAUDO_PORCENTAJE'])
    return porcentaje, (monto * porcentaje / Decimal('100')).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def _fila(recaudo, pedido, enCaja):
    return {
        'id': recaudo.id,
        'pedidoId': pedido.id,
        'codigoGuia': pedido.codigoGuia,
        'monto': str(aDecimal(recaudo.monto)),
        'metodo': recaudo.metodo,
        'referencia': recaudo.referencia,
        'fechaCobro': recaudo.fechaCobro.isoformat() if recaudo.fechaCobro else None,
        'liquidacionId': recaudo.liquidacionId,
        'estado': 'liquidado' if recaudo.liquidacionId else ('en_caja' if enCaja else 'con_repartidor'),
    }


@bp.route('/recaudos/pendientes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def recaudosPendientes():
    """Lo que se le debe a cada remitente: total, cuanto ya esta en caja (se
    puede pagar hoy) y cuanto lo tiene todavia un repartidor."""
    filas = _visibles().filter(RecaudoModel.liquidacionId.is_(None)).with_entities(
        RecaudoModel.remitenteId, func.count(RecaudoModel.id), func.sum(RecaudoModel.monto),
        func.sum(case((_enCaja(), RecaudoModel.monto), else_=0)),
    ).group_by(RecaudoModel.remitenteId).all()
    nombres = {c.id: c for c in conexion.session.query(ClienteModel).filter(
        ClienteModel.id.in_([f[0] for f in filas] or [-1])).all()}

    contenido = []
    for remitenteId, envios, total, liquidable in filas:
        liquidable = aDecimal(liquidable)
        porcentaje, comision = _comision(liquidable)
        cliente = nombres.get(remitenteId)
        contenido.append({
            'remitente': {'id': remitenteId, 'nombre': cliente.nombre if cliente else None,
                          'telefono': cliente.telefono if cliente else None},
            'envios': envios,
            'total': str(aDecimal(total)),
            'enCaja': str(liquidable),
            'conRepartidor': str(aDecimal(total) - liquidable),
            'porcentajeComision': str(porcentaje),
            'comision': str(comision),
            'aPagar': str(liquidable - comision),
        })
    contenido.sort(key=lambda c: Decimal(c['enCaja']), reverse=True)
    return {'content': contenido}, 200


@bp.route('/recaudos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarRecaudos():
    query = _visibles()
    remitenteId = request.args.get('remitente_id', type=int)
    if remitenteId:
        query = query.filter(RecaudoModel.remitenteId == remitenteId)
    if request.args.get('estado') == 'pendiente':
        query = query.filter(RecaudoModel.liquidacionId.is_(None))
    liquidacionId = request.args.get('liquidacion_id', type=int)
    if liquidacionId:
        query = query.filter(RecaudoModel.liquidacionId == liquidacionId)
    rendidas = {r for (r,) in conexion.session.query(LiquidacionRutaModel.rutaId).all()}
    filas = query.with_entities(RecaudoModel, PedidoModel).order_by(RecaudoModel.id.desc()).limit(500).all()
    return {'content': [
        _fila(r, p, r.metodo != 'efectivo' or r.rutaId is None or r.rutaId in rendidas) for r, p in filas
    ]}, 200


@bp.route('/recaudos/liquidar', methods=['POST'])
@requiereRol('admin')
def liquidarRecaudos():
    """Paga al remitente TODO lo que ya esta en caja a su nombre."""
    data = cuerpoJson()
    remitenteId = entero(data, 'remitenteId', requerido=True)
    metodo = opcion(data, 'metodo', METODOS_PAGO, requerido=True)
    referencia = texto(data, 'referencia', maximo=60)
    observacion = texto(data, 'observacion', maximo=1000)
    if metodo != 'efectivo' and not referencia:
        raise ErrorValidacion(f'Para pagar con {metodo} ingresa el numero de operacion')
    remitente = obtener(ClienteModel, remitenteId, 'El remitente no existe')

    recaudos = conexion.session.query(RecaudoModel).filter(
        RecaudoModel.remitenteId == remitenteId, RecaudoModel.liquidacionId.is_(None), _enCaja(),
    ).with_for_update().all()
    if not recaudos:
        raise ErrorNegocio('No hay recaudos en caja para este remitente (lo cobrado en efectivo se puede pagar '
                           'cuando el repartidor liquide su ruta)', 409)

    total = sum((aDecimal(r.monto) for r in recaudos), Decimal('0.00'))
    porcentaje, comision = _comision(total)
    liquidacion = LiquidacionRecaudoModel(
        remitenteId=remitenteId, envios=len(recaudos), montoRecaudado=total, porcentajeComision=porcentaje,
        comision=comision, montoPagado=total - comision, metodo=metodo, referencia=referencia,
        observacion=observacion, usuarioId=usuarioActualId(),
    )
    conexion.session.add(liquidacion)
    conexion.session.flush()
    liquidacion.codigo = f'LR{liquidacion.id:06d}'
    for r in recaudos:
        r.liquidacionId = liquidacion.id
    auditar('recaudo_liquidado', 'liquidacion_recaudo', liquidacion.id, {
        'remitente': remitente.nombre, 'envios': len(recaudos), 'recaudado': total, 'comision': comision,
        'pagado': total - comision, 'metodo': metodo})
    conexion.session.commit()
    return {'message': f'Liquidacion {liquidacion.codigo}: se pagan S/ {total - comision} a {remitente.nombre} '
                       f'({len(recaudos)} envio(s))', 'content': _dumpLiquidacion(liquidacion, remitente)}, 201


def _dumpLiquidacion(l, remitente=None):
    remitente = remitente or conexion.session.get(ClienteModel, l.remitenteId)
    return {
        'id': l.id, 'codigo': l.codigo,
        'remitente': {'id': l.remitenteId, 'nombre': remitente.nombre if remitente else None},
        'envios': l.envios, 'montoRecaudado': str(aDecimal(l.montoRecaudado)),
        'porcentajeComision': str(l.porcentajeComision), 'comision': str(aDecimal(l.comision)),
        'montoPagado': str(aDecimal(l.montoPagado)), 'metodo': l.metodo, 'referencia': l.referencia,
        'observacion': l.observacion, 'fecha': l.fecha.isoformat() if l.fecha else None,
    }


@bp.route('/liquidaciones-recaudo', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarLiquidacionesRecaudo():
    query = conexion.session.query(LiquidacionRecaudoModel)
    propia = agenciaDelUsuario()
    if propia:
        # Las que incluyen envios de su agencia
        ids = _visibles().with_entities(RecaudoModel.liquidacionId).filter(RecaudoModel.liquidacionId.isnot(None))
        query = query.filter(LiquidacionRecaudoModel.id.in_(ids))
    remitenteId = request.args.get('remitente_id', type=int)
    if remitenteId:
        query = query.filter(LiquidacionRecaudoModel.remitenteId == remitenteId)
    return {'content': [_dumpLiquidacion(l) for l in
                        query.order_by(LiquidacionRecaudoModel.id.desc()).limit(200).all()]}, 200
