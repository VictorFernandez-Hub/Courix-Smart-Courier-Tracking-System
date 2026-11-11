"""Indicadores del negocio."""
from decimal import Decimal

from flask import Blueprint
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    ClienteModel, RepartidorModel, EstadoPedidoModel, RutaModel, PedidoModel, PagoModel,
    IncidenciaModel, LiquidacionRutaModel,
)
from app.core.seguridad import (
    requiereRol, ROLES_STAFF,
)
from app.reglas import (
    aDecimal,
)
from app.servicios import (
    efectivoEsperadoDeRuta, idEstado,
)


bp = Blueprint('reportes', __name__)


@bp.route('/reportes/resumen', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def resumenReportes():
    conteos = dict(conexion.session.query(PedidoModel.estadoId, func.count(PedidoModel.id))
                   .group_by(PedidoModel.estadoId).all())
    estados = conexion.session.query(EstadoPedidoModel).order_by(EstadoPedidoModel.orden).all()
    porEstado = {e.nombre: conteos.get(e.id, 0) for e in estados}

    sumaPorEstadoPago = dict(conexion.session.query(PagoModel.estadoPago, func.coalesce(func.sum(PagoModel.monto), 0))
                             .group_by(PagoModel.estadoPago).all())

    entregados = porEstado.get('entregado', 0)
    alPrimerIntento = conexion.session.query(PedidoModel).filter(
        PedidoModel.estadoId == idEstado('entregado'), PedidoModel.intentosEntrega == 0
    ).count() if entregados else 0

    efectivoPorLiquidar = sum(
        (efectivoEsperadoDeRuta(r.id) for r in conexion.session.query(RutaModel).outerjoin(
            LiquidacionRutaModel, LiquidacionRutaModel.rutaId == RutaModel.id
        ).filter(RutaModel.estado.in_(['en_curso', 'completada']), LiquidacionRutaModel.id.is_(None)).all()),
        Decimal('0.00'),
    )

    return {
        'content': {
            'totalPedidos': sum(conteos.values()),
            'pedidosPorEstado': porEstado,
            'totalClientes': conexion.session.query(ClienteModel).filter_by(activo=True).count(),
            'totalRepartidores': conexion.session.query(RepartidorModel).count(),
            'repartidoresDisponibles': conexion.session.query(RepartidorModel).filter_by(disponible=True).count(),
            'rutasActivas': conexion.session.query(RutaModel).filter(RutaModel.estado.in_(['planificada', 'en_curso'])).count(),
            'totalCobrado': str(aDecimal(sumaPorEstadoPago.get('pagado', 0))),
            'totalPorCobrar': str(aDecimal(sumaPorEstadoPago.get('pendiente', 0))),
            'efectivoPorLiquidar': str(efectivoPorLiquidar),
            'tasaEntregaPrimerIntento': round(alPrimerIntento * 100 / entregados, 1) if entregados else None,
            'incidenciasAbiertas': conexion.session.query(IncidenciaModel).filter(
                IncidenciaModel.estado != 'resuelta').count(),
        }
    }, 200
