"""Reglas de dinero compartidas: credito de clientes, cargos adicionales,
reembolsos y saldos de un envio. Todo en Decimal."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app
from sqlalchemy import func

from app.extensions import conexion
from app.models import CargoAdicionalModel, ClienteModel, PagoModel, PedidoModel, ReembolsoModel
from app.core.validacion import CENTIMO, ErrorNegocio
from app.reglas import aDecimal
from app.servicios import idsEstados

# Envios a credito que ya no se cobran (no se presto el servicio)
SIN_DEUDA = ('cancelado', 'extraviado')


def fletePagado(pedidoId):
    return aDecimal(conexion.session.query(func.coalesce(func.sum(PagoModel.monto), 0)).filter(
        PagoModel.pedidoId == pedidoId, PagoModel.estadoPago == 'pagado').scalar())


def cargosPagados(pedidoId):
    return aDecimal(conexion.session.query(func.coalesce(func.sum(CargoAdicionalModel.monto), 0)).filter(
        CargoAdicionalModel.pedidoId == pedidoId, CargoAdicionalModel.estado == 'pagado').scalar())


def cargosPendientes(pedidoId):
    return conexion.session.query(CargoAdicionalModel).filter_by(pedidoId=pedidoId, estado='pendiente').all()


def reembolsado(pedidoId, tipo=None):
    query = conexion.session.query(func.coalesce(func.sum(ReembolsoModel.monto), 0)).filter(
        ReembolsoModel.pedidoId == pedidoId)
    if tipo:
        query = query.filter(ReembolsoModel.tipo == tipo)
    return aDecimal(query.scalar())


def porcentaje(monto, pct):
    return (aDecimal(monto) * Decimal(str(pct)) / Decimal('100')).quantize(CENTIMO, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------ credito ----

def _pedidosCreditoPendientes(clienteId):
    """Envios a credito del cliente (como pagador = remitente) sin pago."""
    pagados = conexion.session.query(PagoModel.pedidoId).filter(PagoModel.estadoPago == 'pagado')
    return conexion.session.query(PedidoModel).filter(
        PedidoModel.remitenteId == clienteId, PedidoModel.modalidadPago == 'credito',
        PedidoModel.estadoId.notin_(idsEstados(SIN_DEUDA)), PedidoModel.id.notin_(pagados),
    )


def estadoDeCuenta(cliente, ahora):
    pendientes = _pedidosCreditoPendientes(cliente.id).order_by(PedidoModel.fechaCreacion).all()
    plazo = timedelta(days=cliente.diasCredito or 0)
    filas, deuda, vencido = [], Decimal('0.00'), Decimal('0.00')
    for p in pendientes:
        vence = p.fechaCreacion + plazo if p.fechaCreacion else None
        estaVencido = bool(vence and vence < ahora)
        deuda += aDecimal(p.monto)
        if estaVencido:
            vencido += aDecimal(p.monto)
        filas.append({'pedidoId': p.id, 'codigoGuia': p.codigoGuia, 'monto': str(aDecimal(p.monto)),
                      'fecha': p.fechaCreacion.isoformat() if p.fechaCreacion else None,
                      'vence': vence.isoformat() if vence else None, 'vencido': estaVencido,
                      'diasAtraso': (ahora - vence).days if estaVencido else 0})
    limite = aDecimal(cliente.limiteCredito)
    return {
        'clienteId': cliente.id, 'creditoHabilitado': bool(cliente.creditoHabilitado),
        'limiteCredito': str(limite), 'diasCredito': cliente.diasCredito,
        'deuda': str(deuda), 'vencido': str(vencido), 'disponible': str(max(limite - deuda, Decimal('0.00'))),
        'pedidos': filas,
    }


def exigirCreditoDisponible(cliente, monto, ahora):
    """Un envio a credito necesita cliente aprobado, sin deuda vencida y con
    cupo para el monto nuevo."""
    if not cliente.creditoHabilitado:
        raise ErrorNegocio(f'{cliente.nombre} no tiene credito aprobado: cobra el envio (prepagado o contra entrega) '
                           'o pide a un administrador que le habilite credito', 409)
    cuenta = estadoDeCuenta(cliente, ahora)
    if Decimal(cuenta['vencido']) > 0:
        raise ErrorNegocio(f'{cliente.nombre} tiene S/ {cuenta["vencido"]} de deuda vencida: regulariza antes de '
                           'enviar a credito', 409)
    if Decimal(cuenta['deuda']) + aDecimal(monto) > aDecimal(cliente.limiteCredito):
        raise ErrorNegocio(f'Excede el limite de credito de {cliente.nombre}: disponible S/ {cuenta["disponible"]}, '
                           f'este envio S/ {aDecimal(monto)}', 409)


def pendientesDeCobro(clienteId, ids=None):
    query = _pedidosCreditoPendientes(clienteId)
    if ids:
        query = query.filter(PedidoModel.id.in_(ids))
    return query.order_by(PedidoModel.fechaCreacion).with_for_update().all()


# ------------------------------------------------------ devoluciones ----

def generarCargoDevolucion(pedido, usuarioId):
    """Devolver al remitente cuesta un % del flete. Se cobra al entregarle
    el paquete (o se suma a su cuenta si es cliente con credito)."""
    pct = Decimal(current_app.config['CARGO_DEVOLUCION_PORCENTAJE'])
    if pct <= 0 or aDecimal(pedido.monto) <= 0:
        return None
    if conexion.session.query(CargoAdicionalModel.id).filter(
            CargoAdicionalModel.pedidoId == pedido.id, CargoAdicionalModel.concepto == 'devolucion',
            CargoAdicionalModel.estado != 'anulado').first():
        return None
    cargo = CargoAdicionalModel(pedidoId=pedido.id, concepto='devolucion', monto=porcentaje(pedido.monto, pct),
                                descripcion=f'Devolucion al remitente ({pct}% del flete)', registradoPorId=usuarioId)
    conexion.session.add(cargo)
    return cargo


def saldoAlDevolver(pedido):
    """Lo que el remitente debe pagar para retirar su devolucion: el flete
    si nunca se cobro (contra entrega) y los cargos pendientes."""
    flete = Decimal('0.00')
    if pedido.modalidadPago == 'contra_entrega' and fletePagado(pedido.id) == 0:
        flete = aDecimal(pedido.monto)
    cargos = sum((aDecimal(c.monto) for c in cargosPendientes(pedido.id)), Decimal('0.00'))
    return flete, cargos


def remitenteDe(pedido):
    return conexion.session.get(ClienteModel, pedido.remitenteId) if pedido.remitenteId else None
