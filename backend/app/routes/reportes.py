"""Indicadores del negocio. Un operador de agencia ve solo los de su agencia
(envios que salen o llegan a ella, rutas y repartidores de su zona)."""
from decimal import Decimal

from flask import Blueprint
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    AlmacenModel, ClienteModel, RepartidorModel, EstadoPedidoModel, RutaModel, PedidoModel, PagoModel,
    IncidenciaModel, LiquidacionRutaModel, RecaudoModel,
)
from app.core.seguridad import (
    requiereRol, ROLES_STAFF,
)
from app.reglas import (
    aDecimal,
)
from app.servicios import (
    agenciaDelUsuario, efectivoEsperadoDeRuta, filtrarPorAgencia, filtrarRutasPorAgencia, idEstado, idsEstados,
)
from app.admision import ahoraLocal
from app.reglas import ESTADOS_ACTIVOS

# Envios cuyo flete ya no se va a cobrar
SIN_COBRO = ('cancelado', 'extraviado', 'devuelto')

bp = Blueprint('reportes', __name__)


def _pedidos(*columnas):
    query = conexion.session.query(*columnas) if columnas else conexion.session.query(PedidoModel)
    return filtrarPorAgencia(query, agenciaDelUsuario())


def _sumaUnida(modelo):
    """SUM(modelo.monto) de los envios visibles para el usuario."""
    query = conexion.session.query(func.coalesce(func.sum(modelo.monto), 0)).select_from(modelo).join(PedidoModel, modelo.pedidoId == PedidoModel.id)
    return filtrarPorAgencia(query, agenciaDelUsuario())


@bp.route('/reportes/resumen', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def resumenReportes():
    propia = agenciaDelUsuario()
    conteos = dict(_pedidos(PedidoModel.estadoId, func.count(PedidoModel.id))
                   .group_by(PedidoModel.estadoId).all())
    estados = conexion.session.query(EstadoPedidoModel).order_by(EstadoPedidoModel.orden).all()
    porEstado = {e.nombre: conteos.get(e.id, 0) for e in estados}

    cobrado = _sumaUnida(PagoModel).filter(PagoModel.estadoPago == 'pagado').scalar()

    # Por cobrar = flete de todo envio vigente que aun no tiene un pago
    # confirmado (contra entrega en camino, prepagados y credito sin pagar)
    pagados = conexion.session.query(PagoModel.pedidoId).filter(PagoModel.estadoPago == 'pagado')
    porCobrar = _pedidos(func.coalesce(func.sum(PedidoModel.monto), 0)).filter(
        PedidoModel.estadoId.notin_(idsEstados(SIN_COBRO)), PedidoModel.id.notin_(pagados)).scalar()

    # Recaudos: dinero de remitentes que el courier tiene en su poder
    recaudoPorLiquidar = _sumaUnida(RecaudoModel).filter(RecaudoModel.liquidacionId.is_(None)).scalar()

    entregados = porEstado.get('entregado', 0)
    alPrimerIntento = _pedidos().filter(
        PedidoModel.estadoId == idEstado('entregado'), PedidoModel.intentosEntrega == 0
    ).count() if entregados else 0

    rutasAbiertas = filtrarRutasPorAgencia(conexion.session.query(RutaModel).outerjoin(
        LiquidacionRutaModel, LiquidacionRutaModel.rutaId == RutaModel.id
    ).filter(RutaModel.estado.in_(['en_curso', 'completada']), LiquidacionRutaModel.id.is_(None)), propia)
    efectivoPorLiquidar = sum((efectivoEsperadoDeRuta(r.id) for r in rutasAbiertas.all()), Decimal('0.00'))

    repartidores = conexion.session.query(RepartidorModel)
    if propia:
        agencia = conexion.session.get(AlmacenModel, propia)
        repartidores = repartidores.filter(RepartidorModel.zonaId == (agencia.zonaId if agencia else -1))
    incidencias = filtrarPorAgencia(conexion.session.query(IncidenciaModel).join(
        PedidoModel, IncidenciaModel.pedidoId == PedidoModel.id), propia)

    return {
        'content': {
            'totalPedidos': sum(conteos.values()),
            'pedidosPorEstado': porEstado,
            'totalClientes': conexion.session.query(ClienteModel).filter_by(activo=True).count(),
            'totalRepartidores': repartidores.count(),
            'repartidoresDisponibles': repartidores.filter(RepartidorModel.disponible.is_(True)).count(),
            'rutasActivas': filtrarRutasPorAgencia(conexion.session.query(RutaModel).filter(
                RutaModel.estado.in_(['planificada', 'en_curso'])), propia).count(),
            'totalCobrado': str(aDecimal(cobrado)),
            'totalPorCobrar': str(aDecimal(porCobrar)),
            'recaudoPorLiquidar': str(aDecimal(recaudoPorLiquidar)),
            'efectivoPorLiquidar': str(efectivoPorLiquidar),
            'tasaEntregaPrimerIntento': round(alPrimerIntento * 100 / entregados, 1) if entregados else None,
            'incidenciasAbiertas': incidencias.filter(IncidenciaModel.estado != 'resuelta').count(),
            'alcance': 'agencia' if propia else 'red',
        }
    }, 200


@bp.route('/reportes/sla', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def reporteSla():
    """Cumplimiento del plazo comprometido (fechaEntregaEstimada)."""
    ahora = ahoraLocal()
    activos = _pedidos().filter(PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS)))
    conPlazo = activos.filter(PedidoModel.fechaEntregaEstimada.isnot(None))
    atrasados = conPlazo.filter(PedidoModel.fechaEntregaEstimada < ahora).count()
    finDeHoy = ahora.replace(hour=23, minute=59, second=59)
    vencenHoy = conPlazo.filter(PedidoModel.fechaEntregaEstimada >= ahora,
                                PedidoModel.fechaEntregaEstimada <= finDeHoy).count()

    entregados = _pedidos().filter(
        PedidoModel.estadoId == idEstado('entregado'), PedidoModel.fechaEntregaEstimada.isnot(None),
        PedidoModel.fechaEntrega.isnot(None))
    total = entregados.count()
    aTiempo = entregados.filter(PedidoModel.fechaEntrega <= PedidoModel.fechaEntregaEstimada).count()
    return {'content': {
        'activos': activos.count(),
        'atrasados': atrasados,
        'vencenHoy': vencenHoy,
        'entregadosConPlazo': total,
        'porcentajeATiempo': round(aTiempo * 100 / total, 1) if total else None,
    }}, 200
