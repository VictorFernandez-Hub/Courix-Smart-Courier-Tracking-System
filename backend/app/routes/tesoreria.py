"""Tesoreria: el dinero que entra y sale fuera del cobro normal del flete.

- Cargos adicionales (devolucion, redireccion): se cobran en mostrador.
- Reembolsos: devolucion del flete de un servicio no prestado (con nota de
  credito si ya habia comprobante) e indemnizaciones por perdida o dano,
  con tope en el valor declarado (si pago seguro) o en el maximo sin seguro.
- Credito: estado de cuenta del cliente, cartera por cobrar y cobranza.
- Cierre de caja: arqueo de cada cajero contra lo que el sistema registra.
"""
import json
from decimal import Decimal

from flask import Blueprint, current_app
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    CargoAdicionalModel, CierreCajaModel, ClienteModel, IncidenciaModel, LiquidacionRecaudoModel,
    LiquidacionRutaModel, PagoModel, PedidoModel, ReembolsoModel, UsuarioModel,
)
from app.admision import ahoraLocal
from app.core.seguridad import requiereRol, auditar, rolActual, usuarioActualId, ROLES_STAFF
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, booleano, cuerpoJson, dinero, entero, opcion, texto,
)
from app.finanzas import (
    cargosPagados, estadoDeCuenta, fletePagado, pendientesDeCobro, reembolsado,
)
from app.reglas import ESTADOS_CON_DEVOLUCION_FLETE, METODOS_PAGO, TIPOS_REEMBOLSO, aDecimal
from app.servicios import agenciaDelUsuario, exigirAccesoPedido, nombreEstado, obtener
from app.routes.comprobantes import emitirNotaCredito, enviarGuardado, _serializar as serializarComprobante

bp = Blueprint('tesoreria', __name__)


def _metodoYReferencia(data, requerido=True):
    metodo = opcion(data, 'metodo', METODOS_PAGO, requerido=requerido)
    referencia = texto(data, 'referencia', maximo=60)
    if metodo and metodo != 'efectivo' and not referencia:
        raise ErrorValidacion(f'Para {metodo} ingresa el numero de operacion')
    return metodo, referencia


def _dumpCargo(c):
    return {'id': c.id, 'pedidoId': c.pedidoId, 'concepto': c.concepto, 'monto': str(aDecimal(c.monto)),
            'descripcion': c.descripcion, 'estado': c.estado, 'metodo': c.metodo, 'referencia': c.referencia,
            'fechaPago': c.fechaPago.isoformat() if c.fechaPago else None,
            'fechaCreacion': c.fechaCreacion.isoformat() if c.fechaCreacion else None}


def _dumpReembolso(r):
    return {'id': r.id, 'pedidoId': r.pedidoId, 'tipo': r.tipo, 'monto': str(aDecimal(r.monto)), 'metodo': r.metodo,
            'referencia': r.referencia, 'motivo': r.motivo, 'beneficiarioId': r.beneficiarioId,
            'incidenciaId': r.incidenciaId, 'comprobanteId': r.comprobanteId,
            'fecha': r.fecha.isoformat() if r.fecha else None}


# ------------------------------------------------------------- cargos ----

@bp.route('/pedido/<int:id>/cargos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def cargosDelPedido(id):
    exigirAccesoPedido(obtener(PedidoModel, id, 'Pedido no existe'))
    cargos = conexion.session.query(CargoAdicionalModel).filter_by(pedidoId=id).order_by(CargoAdicionalModel.id).all()
    return {'content': [_dumpCargo(c) for c in cargos]}, 200


@bp.route('/cargo/<int:id>/cobrar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cobrarCargo(id):
    data = cuerpoJson()
    metodo, referencia = _metodoYReferencia(data)
    cargo = obtener(CargoAdicionalModel, id, 'Cargo no existe', bloquear=True)
    exigirAccesoPedido(conexion.session.get(PedidoModel, cargo.pedidoId))
    if cargo.estado != 'pendiente':
        raise ErrorNegocio(f'Este cargo ya esta {cargo.estado}', 409)
    cargo.estado, cargo.metodo, cargo.referencia = 'pagado', metodo, referencia
    cargo.fechaPago = func.now()
    cargo.cobradoPorId = usuarioActualId()
    auditar('cargo_cobrado', 'cargo', id, {'monto': cargo.monto, 'metodo': metodo})
    conexion.session.commit()
    return {'message': f'Cargo de S/ {aDecimal(cargo.monto)} cobrado', 'content': _dumpCargo(cargo)}, 200


@bp.route('/cargo/<int:id>/anular', methods=['POST'])
@requiereRol('admin')
def anularCargo(id):
    data = cuerpoJson()
    motivo = texto(data, 'motivo', requerido=True, minimo=5, maximo=300)
    cargo = obtener(CargoAdicionalModel, id, 'Cargo no existe', bloquear=True)
    if cargo.estado != 'pendiente':
        raise ErrorNegocio('Solo se anula un cargo pendiente (uno cobrado se devuelve con un reembolso)', 409)
    cargo.estado = 'anulado'
    auditar('cargo_anulado', 'cargo', id, {'monto': cargo.monto, 'motivo': motivo})
    conexion.session.commit()
    return {'message': 'Cargo anulado', 'content': _dumpCargo(cargo)}, 200


# ---------------------------------------------------------- reembolsos ----

def _topeIndemnizacion(pedido):
    """Con seguro: hasta el valor declarado. Sin seguro: el menor entre el
    valor declarado (si lo hay) y el maximo sin seguro."""
    declarado = aDecimal(pedido.valorDeclarado)
    if aDecimal(pedido.costoSeguro) > 0:
        return declarado
    sinSeguro = aDecimal(current_app.config['INDEMNIZACION_SIN_SEGURO'])
    return min(declarado, sinSeguro) if declarado > 0 else sinSeguro


def _saldos(pedido):
    cobrado = fletePagado(pedido.id) + cargosPagados(pedido.id)
    devuelto = reembolsado(pedido.id, 'devolucion_flete')
    indemnizado = reembolsado(pedido.id, 'indemnizacion')
    tope = _topeIndemnizacion(pedido)
    return {
        'cobrado': cobrado, 'devuelto': devuelto,
        'devolucionDisponible': cobrado - devuelto if nombreEstado(pedido.estadoId) in ESTADOS_CON_DEVOLUCION_FLETE
        else Decimal('0.00'),
        'topeIndemnizacion': tope, 'indemnizado': indemnizado,
        'indemnizacionDisponible': max(tope - indemnizado, Decimal('0.00')),
    }


@bp.route('/pedido/<int:id>/reembolsos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def reembolsosDelPedido(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    filas = conexion.session.query(ReembolsoModel).filter_by(pedidoId=id).order_by(ReembolsoModel.id).all()
    return {'content': {'reembolsos': [_dumpReembolso(r) for r in filas],
                        'saldos': {k: str(v) for k, v in _saldos(pedido).items()},
                        'conSeguro': aDecimal(pedido.costoSeguro) > 0}}, 200


@bp.route('/pedido/<int:id>/reembolso', methods=['POST'])
@requiereRol('admin')
def registrarReembolso(id):
    data = cuerpoJson()
    tipo = opcion(data, 'tipo', TIPOS_REEMBOLSO, requerido=True)
    monto = dinero(data, 'monto', requerido=True, minimo=Decimal('0.01'))
    metodo, referencia = _metodoYReferencia(data)
    motivo = texto(data, 'motivo', requerido=True, minimo=5, maximo=500)
    incidenciaId = entero(data, 'incidenciaId')

    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    saldos = _saldos(pedido)
    estado = nombreEstado(pedido.estadoId)
    incidencia = None
    if incidenciaId:
        incidencia = obtener(IncidenciaModel, incidenciaId, 'Incidencia no existe', bloquear=True)
        if incidencia.pedidoId != id:
            raise ErrorValidacion('La incidencia no es de este envio')

    if tipo == 'devolucion_flete':
        if estado not in ESTADOS_CON_DEVOLUCION_FLETE:
            raise ErrorNegocio(f'Solo se devuelve el flete de un envio cancelado o extraviado (este esta "{estado}")', 409)
        if monto > saldos['devolucionDisponible']:
            raise ErrorNegocio(f'Se puede devolver hasta S/ {saldos["devolucionDisponible"]} (lo cobrado menos lo ya '
                               'devuelto)', 409)
        # Se le devuelve a quien pago
        beneficiario = pedido.clienteId if pedido.modalidadPago == 'contra_entrega' else (pedido.remitenteId or pedido.clienteId)
    else:
        danado = incidencia is not None and incidencia.tipo in ('producto_danado', 'faltante')
        if estado != 'extraviado' and not danado:
            raise ErrorNegocio('La indemnizacion corresponde a un envio extraviado o a una incidencia de producto '
                               'danado/faltante (indica incidenciaId)', 409)
        if monto > saldos['indemnizacionDisponible']:
            base = 'valor declarado (con seguro)' if aDecimal(pedido.costoSeguro) > 0 else 'maximo sin seguro'
            raise ErrorNegocio(f'La indemnizacion no puede superar S/ {saldos["indemnizacionDisponible"]} ({base}, '
                               'menos lo ya indemnizado)', 409)
        # La mercaderia es del remitente
        beneficiario = pedido.remitenteId or pedido.clienteId

    reembolso = ReembolsoModel(pedidoId=id, tipo=tipo, monto=monto, metodo=metodo, referencia=referencia, motivo=motivo,
                               beneficiarioId=beneficiario, incidenciaId=incidenciaId, usuarioId=usuarioActualId())
    conexion.session.add(reembolso)
    conexion.session.flush()
    nota = emitirNotaCredito(pedido, monto, motivo) if tipo == 'devolucion_flete' else None
    if nota:
        reembolso.comprobanteId = nota.id
    if incidencia:
        incidencia.compensacion = aDecimal(incidencia.compensacion) + monto
    auditar('reembolso_registrado', 'pedido', id, {'tipo': tipo, 'monto': monto, 'metodo': metodo, 'motivo': motivo,
                                                   'notaCredito': nota.id if nota else None})
    if nota:
        enviarGuardado(nota)  # hace commit (el numero queda guardado aunque falle el PSE)
    else:
        conexion.session.commit()
    mensaje = f'{"Devolucion" if tipo == "devolucion_flete" else "Indemnizacion"} de S/ {monto} registrada'
    if nota:
        mensaje += f'. Nota de credito {nota.serie}-{nota.numero:08d}: {nota.estado}'
    return {'message': mensaje, 'content': {
        'reembolso': _dumpReembolso(reembolso), 'notaCredito': serializarComprobante(nota) if nota else None}}, 201


# ------------------------------------------------------------- credito ----

@bp.route('/cliente/<int:id>/cuenta', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def cuentaCliente(id):
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    return {'content': estadoDeCuenta(cliente, ahoraLocal())}, 200


@bp.route('/cliente/<int:id>/credito', methods=['PUT'])
@requiereRol('admin')
def configurarCredito(id):
    data = cuerpoJson()
    cliente = obtener(ClienteModel, id, 'Cliente no existe', bloquear=True)
    habilitado = booleano(data, 'creditoHabilitado', defecto=bool(cliente.creditoHabilitado))
    limite = dinero(data, 'limiteCredito', maximo=Decimal('1000000'))
    dias = entero(data, 'diasCredito', minimo=1, maximo=120)
    if habilitado and not cliente.dni:
        raise ErrorValidacion('Para dar credito el cliente debe tener documento (RUC o DNI) registrado')
    antes = {'creditoHabilitado': cliente.creditoHabilitado, 'limiteCredito': aDecimal(cliente.limiteCredito),
             'diasCredito': cliente.diasCredito}
    cliente.creditoHabilitado = habilitado
    if limite is not None:
        cliente.limiteCredito = limite
    if dias is not None:
        cliente.diasCredito = dias
    if cliente.creditoHabilitado and aDecimal(cliente.limiteCredito) <= 0:
        raise ErrorValidacion('Indica un limite de credito mayor a 0')
    auditar('credito_configurado', 'cliente', id, {'antes': antes, 'despues': {
        'creditoHabilitado': habilitado, 'limiteCredito': aDecimal(cliente.limiteCredito),
        'diasCredito': cliente.diasCredito}})
    conexion.session.commit()
    return {'message': 'Credito actualizado', 'content': estadoDeCuenta(cliente, ahoraLocal())}, 200


@bp.route('/cliente/<int:id>/cobrar-credito', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cobrarCredito(id):
    """Cobranza: paga los envios a credito indicados (o todos, del mas
    antiguo al mas nuevo). Un pago por envio, para conciliar y facturar."""
    data = cuerpoJson()
    metodo, referencia = _metodoYReferencia(data)
    ids = data.get('pedidoIds')
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(x, int) for x in ids)):
        raise ErrorValidacion('pedidoIds debe ser una lista de ids')
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    pedidos = pendientesDeCobro(id, ids)
    if not pedidos:
        raise ErrorNegocio('No hay envios a credito pendientes de pago para este cliente', 409)
    if ids and len(pedidos) != len(set(ids)):
        raise ErrorNegocio('Algunos envios indicados no son deuda a credito pendiente de este cliente', 409)
    total = Decimal('0.00')
    for p in pedidos:
        existente = conexion.session.query(PagoModel).filter_by(pedidoId=p.id).with_for_update().first()
        if existente:  # pago pendiente registrado antes: se confirma
            existente.estadoPago, existente.metodo, existente.referencia = 'pagado', metodo, referencia
            existente.fechaPago, existente.registradoPorId = func.now(), usuarioActualId()
        else:
            conexion.session.add(PagoModel(pedidoId=p.id, monto=aDecimal(p.monto), metodo=metodo, referencia=referencia,
                                           estadoPago='pagado', fechaPago=func.now(), registradoPorId=usuarioActualId()))
        total += aDecimal(p.monto)
    auditar('credito_cobrado', 'cliente', id, {'envios': [p.codigoGuia for p in pedidos], 'total': total,
                                               'metodo': metodo})
    conexion.session.commit()
    return {'message': f'Cobrados S/ {total} de {len(pedidos)} envio(s) a {cliente.nombre}',
            'content': estadoDeCuenta(cliente, ahoraLocal())}, 200


@bp.route('/creditos/cartera', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def carteraCredito():
    """Cuentas por cobrar: clientes con credito y su deuda, vencida primero."""
    ahora = ahoraLocal()
    clientes = conexion.session.query(ClienteModel).filter(ClienteModel.creditoHabilitado.is_(True)).all()
    cartera = []
    for c in clientes:
        cuenta = estadoDeCuenta(c, ahora)
        cuenta['nombre'] = c.nombre
        cuenta['telefono'] = c.telefono
        cuenta['pedidos'] = len(cuenta['pedidos'])
        cartera.append(cuenta)
    cartera.sort(key=lambda x: (Decimal(x['vencido']), Decimal(x['deuda'])), reverse=True)
    return {'content': cartera, 'totales': {
        'deuda': str(sum((Decimal(x['deuda']) for x in cartera), Decimal('0.00'))),
        'vencido': str(sum((Decimal(x['vencido']) for x in cartera), Decimal('0.00'))),
    }}, 200


# -------------------------------------------------------- cierre de caja ----

def _ahoraDb():
    from datetime import datetime
    valor = conexion.session.query(func.now()).scalar()
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    return valor.replace(tzinfo=None, microsecond=0)


def _arqueo(usuarioId):
    """Movimientos del cajero desde su ultimo cierre, por metodo."""
    ultimo = conexion.session.query(CierreCajaModel).filter_by(usuarioId=usuarioId) \
        .order_by(CierreCajaModel.hasta.desc()).first()
    desde = ultimo.hasta if ultimo else None
    hasta = _ahoraDb()

    def ventana(columna):
        condicion = columna <= hasta
        return condicion if desde is None else (condicion & (columna > desde))

    porMetodo = {}
    lineas = []

    def sumar(concepto, metodo, monto, signo=1):
        monto = aDecimal(monto) * signo
        porMetodo[metodo] = porMetodo.get(metodo, Decimal('0.00')) + monto
        lineas.append({'concepto': concepto, 'metodo': metodo, 'monto': str(monto)})

    for p in conexion.session.query(PagoModel).filter(
            PagoModel.registradoPorId == usuarioId, PagoModel.estadoPago == 'pagado', PagoModel.rutaId.is_(None),
            ventana(PagoModel.fechaPago)).all():
        sumar(f'Flete envio #{p.pedidoId}', p.metodo, p.monto)
    for c in conexion.session.query(CargoAdicionalModel).filter(
            CargoAdicionalModel.cobradoPorId == usuarioId, CargoAdicionalModel.estado == 'pagado',
            ventana(CargoAdicionalModel.fechaPago)).all():
        sumar(f'Cargo {c.concepto} envio #{c.pedidoId}', c.metodo, c.monto)
    for l in conexion.session.query(LiquidacionRutaModel).filter(
            LiquidacionRutaModel.recibidoPorId == usuarioId, ventana(LiquidacionRutaModel.fecha)).all():
        sumar(f'Efectivo rendido de la ruta #{l.rutaId}', 'efectivo', l.montoEntregado)
    for r in conexion.session.query(ReembolsoModel).filter(
            ReembolsoModel.usuarioId == usuarioId, ventana(ReembolsoModel.fecha)).all():
        sumar(f'{r.tipo.replace("_", " ").capitalize()} envio #{r.pedidoId}', r.metodo, r.monto, -1)
    for l in conexion.session.query(LiquidacionRecaudoModel).filter(
            LiquidacionRecaudoModel.usuarioId == usuarioId, ventana(LiquidacionRecaudoModel.fecha)).all():
        sumar(f'Pago de recaudos {l.codigo}', l.metodo, l.montoPagado, -1)

    return {
        'desde': desde.isoformat() if desde else None, 'hasta': hasta.isoformat(), '_hasta': hasta, '_desde': desde,
        'efectivoEsperado': porMetodo.get('efectivo', Decimal('0.00')),
        'porMetodo': {k: str(v) for k, v in porMetodo.items()},
        'movimientos': lineas,
    }


def _publico(arqueo):
    datos = {k: v for k, v in arqueo.items() if not k.startswith('_')}
    datos['efectivoEsperado'] = str(arqueo['efectivoEsperado'])
    return datos


@bp.route('/caja/arqueo', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def verArqueo():
    return {'content': _publico(_arqueo(usuarioActualId()))}, 200


@bp.route('/caja/cierre', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cerrarCaja():
    data = cuerpoJson()
    contado = dinero(data, 'efectivoContado', requerido=True)
    observacion = texto(data, 'observacion', maximo=1000)
    # Serializa los cierres del mismo cajero (doble clic = un solo cierre)
    obtener(UsuarioModel, usuarioActualId(), 'Usuario no existe', bloquear=True)
    arqueo = _arqueo(usuarioActualId())
    if not arqueo['movimientos'] and contado == 0:
        raise ErrorNegocio('No hay movimientos desde tu ultimo cierre', 409)
    diferencia = contado - arqueo['efectivoEsperado']
    if diferencia != 0 and not observacion:
        raise ErrorValidacion(f'Hay una diferencia de S/ {diferencia}: explica el motivo en la observacion')
    cierre = CierreCajaModel(
        usuarioId=usuarioActualId(), agenciaId=agenciaDelUsuario(), desde=arqueo['_desde'], hasta=arqueo['_hasta'],
        efectivoEsperado=arqueo['efectivoEsperado'], efectivoContado=contado, diferencia=diferencia,
        detalle=json.dumps({'porMetodo': arqueo['porMetodo'], 'movimientos': arqueo['movimientos']}),
        observacion=observacion,
    )
    conexion.session.add(cierre)
    conexion.session.flush()
    cierre.codigo = f'CJ{cierre.id:06d}'
    auditar('caja_cerrada', 'cierre_caja', cierre.id, {'esperado': arqueo['efectivoEsperado'], 'contado': contado,
                                                       'diferencia': diferencia})
    conexion.session.commit()
    return {'message': f'Caja cerrada ({cierre.codigo})' + (f' con diferencia de S/ {diferencia}' if diferencia else ''),
            'content': _dumpCierre(cierre)}, 201


def _dumpCierre(c, nombres=None):
    detalle = json.loads(c.detalle) if c.detalle else {}
    usuario = (nombres or {}).get(c.usuarioId) or getattr(conexion.session.get(UsuarioModel, c.usuarioId), 'nombre', None)
    return {'id': c.id, 'codigo': c.codigo, 'usuario': usuario, 'agenciaId': c.agenciaId,
            'desde': c.desde.isoformat() if c.desde else None, 'hasta': c.hasta.isoformat(),
            'efectivoEsperado': str(aDecimal(c.efectivoEsperado)), 'efectivoContado': str(aDecimal(c.efectivoContado)),
            'diferencia': str(aDecimal(c.diferencia)), 'porMetodo': detalle.get('porMetodo', {}),
            'movimientos': len(detalle.get('movimientos', [])), 'observacion': c.observacion}


@bp.route('/caja/cierres', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarCierres():
    query = conexion.session.query(CierreCajaModel)
    if rolActual() != 'admin':
        propia = agenciaDelUsuario()
        query = query.filter(CierreCajaModel.agenciaId == propia) if propia else \
            query.filter(CierreCajaModel.usuarioId == usuarioActualId())
    cierres = query.order_by(CierreCajaModel.id.desc()).limit(100).all()
    nombres = {u.id: u.nombre for u in conexion.session.query(UsuarioModel).filter(
        UsuarioModel.id.in_({c.usuarioId for c in cierres} or {-1})).all()}
    return {'content': [_dumpCierre(c, nombres) for c in cierres]}, 200

