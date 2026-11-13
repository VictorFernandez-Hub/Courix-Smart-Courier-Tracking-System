"""Ciclo de vida del pedido: registro, almacen, asignacion, estados, entrega."""
from decimal import Decimal

from flask import Blueprint, current_app, request
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    ClienteModel, DireccionModel, AlmacenModel, RepartidorModel, EstadoPedidoModel, ZonaModel,
    RutaModel, PedidoModel, HistorialEstadoModel, PagoModel, BultoModel, EntregaModel, SolicitudRecojoModel,
    ManifiestoModel, ManifiestoBultoModel, RecaudoModel, CargoAdicionalModel,
)
from app.core.correo import enviarCorreo
from app.notificaciones import despacharAvisos, encolarAviso
from app.finanzas import exigirCreditoDisponible, generarCargoDevolucion, saldoAlDevolver, cargosPendientes, fletePagado
from app.admision import (
    ahoraLocal, generarPin, pinEsCorrecto,
    elegirAgenciaDestino, aplicarInspeccion, calcularPesos, cotizarEnvio, fechaEstimada, guardarBultos, leerBultos, leerInspeccion,
    leerServicioYValor, serializarCotizacion,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, usuarioActualId, rolActual, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, texto, entero, dinero, decimalPositivo, coordenada,
    opcion, booleano, evidencia, dni,
)
from app.reglas import (
    ESTADOS_ACTIVOS, ESTADOS_CON_COMENTARIO, ESTADOS_FINALES, MANIFIESTOS_ACTIVOS, RELACIONES_RECEPTOR, METODOS_PAGO, MODALIDADES_PAGO, MOTIVOS_NO_ENTREGA, PRIORIDADES, ROLES_POR_ESTADO_DESTINO, TRANSICIONES_VALIDAS, aDecimal, puedeTransicionar,
)
from app.schemas import (
    BultoDto, HistorialEstadoDto, PagoDto, PedidoDto,
)
from app.servicios import (
    idsEstados, agenciaDondeEsta, asignarPedidoARuta, estadoListoParaReparto, exigirAccesoPedido, agenciaDelUsuario, agenciaReparto, esEnvioLocal, exigirMiAgencia,
    filtrarPorAgencia, exigirMiRepartidor, generarCodigoGuia, totalACobrar, bultosAdmitidosDeRecojo, idEstado, miRepartidor, nombreEstado, obtener, paginar, patronBusqueda, registrarHistorial, rutaActivaDe, validarRepartidorOperativo,
)


bp = Blueprint('pedidos', __name__)


@bp.route('/cotizar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cotizarEnvioEndpoint():
    """Cotizacion en vivo para el mostrador: no guarda nada."""
    data = cuerpoJson()
    almacen = obtener(AlmacenModel, entero(data, 'almacenId', requerido=True), 'El almacen no existe')
    direccionId = entero(data, 'direccionEntregaId')
    if direccionId:
        zonaDestinoId = obtener(DireccionModel, direccionId, 'La direccion de entrega no existe').zonaId
    else:
        zonaDestinoId = entero(data, 'zonaDestinoId', requerido=True)
    servicio, valorDeclarado = leerServicioYValor(data)
    bultos = leerBultos(data, requerido=False)
    pesoSuelto = None if bultos else decimalPositivo(data, 'pesoKg', maximo=Decimal('1000'))

    detalle, pesos = calcularPesos(bultos, pesoSuelto)
    cotizacion = cotizarEnvio(almacen.zonaId, zonaDestinoId, servicio, pesos['pesoFacturableKg'], valorDeclarado)
    recojo = _recojoParaAdmitir(entero(data, 'solicitudRecojoId'), almacen.id, entero(data, 'remitenteId'), 0)
    _aplicarRecargoRecojo(cotizacion, recojo)
    estimada = fechaEstimada(cotizacion)
    destinoId = elegirAgenciaDestino(almacen, zonaDestinoId)
    destino = conexion.session.get(AlmacenModel, destinoId) if destinoId else None
    return {'content': {
        'agenciaDestino': {'id': destino.id, 'nombre': destino.nombre, 'esLocal': destino.id == almacen.id}
        if destino else None,
        'sinCobertura': destino is None,
        'tarifaEncontrada': cotizacion is not None,
        'pesos': {k: (str(v) if v is not None else None) for k, v in pesos.items()},
        'bultos': [{'pesoVolumetricoKg': str(b['pesoVolumetricoKg']), 'pesoFacturableKg': str(b['pesoFacturableKg'])}
                   for b in (detalle or [])],
        'cotizacion': cotizacion,
        'fechaEntregaEstimada': estimada.isoformat() if estimada else None,
    }}, 200


@bp.route('/pedido', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearPedido():
    """Admision del envio. Con yaEnAlmacen=true el paquete esta en el
    mostrador: se exige pesar y medir cada bulto e inspeccionarlo. Sin el
    (pre-registro, ej. tienda online) basta un peso estimado; los bultos y la
    inspeccion se registran al recibirlo con /ingresar-almacen."""
    data = cuerpoJson()
    clienteId = entero(data, 'clienteId', requerido=True)        # destinatario
    remitenteId = entero(data, 'remitenteId')
    almacenId = entero(data, 'almacenId', requerido=True)
    direccionId = entero(data, 'direccionEntregaId', requerido=True)
    prioridad = opcion(data, 'prioridad', PRIORIDADES, defecto='normal')
    modalidad = opcion(data, 'modalidadPago', MODALIDADES_PAGO, defecto='contra_entrega')
    servicio, valorDeclarado = leerServicioYValor(data)
    yaEnAlmacen = booleano(data, 'yaEnAlmacen', defecto=False)
    bultos = leerBultos(data, requerido=yaEnAlmacen)
    inspeccion = leerInspeccion(data) if yaEnAlmacen else None
    pesoSuelto = None if bultos else decimalPositivo(data, 'pesoKg', maximo=Decimal('1000'))
    montoManual = dinero(data, 'monto')
    motivoMonto = texto(data, 'motivoMonto', maximo=200, minimo=5)
    conPin = booleano(data, 'entregaConPin', defecto=False)
    recojoId = entero(data, 'solicitudRecojoId')
    montoRecaudo = dinero(data, 'montoRecaudo', maximo=Decimal(current_app.config['RECAUDO_MAXIMO'])) or Decimal('0.00')
    if montoRecaudo > 0 and not remitenteId:
        # El dinero del producto es del remitente: sin el no hay a quien liquidarle
        raise ErrorValidacion('Para cobrar el producto contra entrega indica el remitente (a quien se le paga lo recaudado)')

    cliente = obtener(ClienteModel, clienteId, 'El destinatario no existe')
    if not cliente.activo:
        raise ErrorValidacion('El destinatario esta desactivado')
    if remitenteId:
        remitente = obtener(ClienteModel, remitenteId, 'El remitente no existe')
        if not remitente.activo:
            raise ErrorValidacion('El remitente esta desactivado')
    direccion = obtener(DireccionModel, direccionId, 'La direccion de entrega no existe')
    if direccion.clienteId != clienteId or not direccion.activo:
        raise ErrorValidacion('Esa direccion no pertenece al destinatario indicado')
    almacen = obtener(AlmacenModel, almacenId, 'El almacen no existe')
    if not almacen.activo:
        raise ErrorValidacion('El almacen esta desactivado')
    exigirMiAgencia(almacenId, 'Solo puedes admitir envios en tu agencia')

    detalleBultos, pesos = calcularPesos(bultos, pesoSuelto)
    cotizacion = cotizarEnvio(almacen.zonaId, direccion.zonaId, servicio, pesos['pesoFacturableKg'], valorDeclarado)
    recojo = _recojoParaAdmitir(recojoId, almacenId, remitenteId, len(bultos) if bultos else 1)
    _aplicarRecargoRecojo(cotizacion, recojo)
    montoTarifa = Decimal(cotizacion['total']) if cotizacion else None

    # Cobertura: si la zona de destino no tiene agencia activa nadie puede
    # repartirlo (antes se trataba como local y lo llevaba un repartidor de
    # otra zona sin que nadie se enterara)
    agenciaDestinoId = elegirAgenciaDestino(almacen, direccion.zonaId)
    if agenciaDestinoId is None:
        zonaDestino = conexion.session.get(ZonaModel, direccion.zonaId)
        raise ErrorValidacion(f'Sin cobertura: ninguna agencia activa reparte en la zona '
                              f'"{zonaDestino.nombre if zonaDestino else direccion.zonaId}"')

    tarifaId = None
    if montoManual is None:
        if montoTarifa is None:
            # Ninguna modalidad se admite sin precio: un envio a S/ 0 es
            # ingreso perdido (o una deuda que nunca se cobra)
            raise ErrorValidacion(f'No hay una tarifa de servicio {servicio} entre la zona del almacen y la del '
                                  'destino: ingresa el monto manualmente (con el motivo) o registra la tarifa')
        monto, tarifaId = montoTarifa, cotizacion['tarifaId']
    else:
        monto = montoManual
        if not motivoMonto:
            raise ErrorValidacion('Indica el motivo del precio manual (ej. "convenio corporativo", "sin tarifa")')
        if montoTarifa is not None and monto < montoTarifa and rolActual() != 'admin':
            tope = Decimal(current_app.config['DESCUENTO_MAXIMO_OPERADOR'])
            minimo = (montoTarifa * (100 - tope) / 100).quantize(Decimal('0.01'))
            if monto < minimo:
                raise ErrorNegocio(f'Un operador puede rebajar hasta {tope}% de la tarifa (minimo S/ {minimo}). '
                                   'Para un descuento mayor pide autorizacion a un administrador', 403)

    if monto <= 0:
        raise ErrorValidacion('El envio debe tener un monto mayor a 0')

    remitenteObj = conexion.session.get(ClienteModel, remitenteId) if remitenteId else None
    if modalidad == 'credito':
        # A credito paga el remitente, despues: debe ser cliente aprobado y con cupo
        if not remitenteObj:
            raise ErrorValidacion('Un envio a credito necesita el remitente (es quien paga despues)')
        exigirCreditoDisponible(remitenteObj, monto, ahoraLocal())

    estadoInicial = idEstado('en_almacen' if yaEnAlmacen else 'pendiente')
    pedido = PedidoModel(
        codigoGuia=generarCodigoGuia(),
        clienteId=clienteId,
        remitenteId=remitenteId,
        usuarioId=usuarioActualId(),
        almacenId=almacenId,
        agenciaDestinoId=agenciaDestinoId,
        direccionEntregaId=direccionId,
        estadoId=estadoInicial,
        prioridad=prioridad,
        modalidadPago=modalidad,
        monto=monto,
        montoRecaudo=montoRecaudo,
        tarifaId=tarifaId,
        tipoServicio=servicio,
        valorDeclarado=valorDeclarado,
        costoSeguro=Decimal(cotizacion['seguro']) if cotizacion else Decimal('0.00'),
        pesoKg=float(pesos['pesoRealKg']) if pesos['pesoRealKg'] is not None else None,
        pesoFacturableKg=pesos['pesoFacturableKg'],
        detalleCotizacion=serializarCotizacion(cotizacion, pesos),
        fechaEntregaEstimada=fechaEstimada(cotizacion),
        descripcionProducto=texto(data, 'descripcionProducto', maximo=500),
        notas=texto(data, 'notas', maximo=1000),
        solicitudRecojoId=recojo.id if recojo else None,
    )
    pin = generarPin(pedido) if conPin else None
    conexion.session.add(pedido)
    conexion.session.flush()
    if recojo:
        recojo.estado = 'admitida'

    if inspeccion:
        aplicarInspeccion(pedido, inspeccion)
    if detalleBultos:
        guardarBultos(pedido, detalleBultos)

    if montoManual is not None:
        auditar('monto_manual', 'pedido', pedido.id, {'montoTarifa': montoTarifa, 'montoIngresado': montoManual,
                                                      'motivo': motivoMonto})

    registrarHistorial(pedido.id, estadoInicial,
                       comentario='Envio registrado' + (
                           f' e inspeccionado en agencia ({len(detalleBultos)} bulto(s))' if yaEnAlmacen else ''))
    avisos = encolarAviso(pedido, 'registrado')
    conexion.session.commit()
    despacharAvisos(avisos)

    contenido = PedidoDto().dump(pedido)
    if pin:
        # Unica vez que el PIN sale del sistema: el operador se lo da al
        # remitente (y si el destinatario tiene correo, tambien le llega).
        contenido['pinEntrega'] = pin
        if cliente.email:
            enviarCorreo(
                cliente.email, f'Courrier Express - Codigo de entrega del envio {pedido.codigoGuia}',
                f'Hola {cliente.nombre}:\n\nTienes un envio en camino (guia {pedido.codigoGuia}).\n'
                f'Al recibirlo, dale este codigo al repartidor: {pin}\n\n'
                'No lo compartas con nadie mas: sin el codigo no se entrega el paquete.\n')
    return {'message': 'Pedido creado exitosamente', 'content': contenido}, 201


def _recojoParaAdmitir(recojoId, almacenId, remitenteId, bultosNuevos):
    """Valida que un envio pueda salir del recojo indicado y que no se admitan
    mas bultos de los que el repartidor declaro haber recogido (un bulto de
    mas es de otro cliente o un error de conteo: se investiga, no se admite)."""
    if not recojoId:
        return None
    recojo = obtener(SolicitudRecojoModel, recojoId, 'La solicitud de recojo no existe')
    if recojo.estado not in ('recogida', 'admitida'):
        raise ErrorValidacion(f'El recojo {recojo.codigo} todavia no fue recogido (estado: {recojo.estado})')
    if recojo.agenciaId != almacenId:
        raise ErrorValidacion('Lo recogido se admite en la agencia que hizo el recojo')
    if remitenteId and recojo.remitenteId != remitenteId:
        raise ErrorValidacion('El remitente no coincide con el cliente del recojo')
    if recojo.bultosRecogidos and bultosNuevos:
        admitidos = bultosAdmitidosDeRecojo(recojo.id)
        if admitidos + bultosNuevos > recojo.bultosRecogidos:
            raise ErrorValidacion(
                f'El repartidor recogio {recojo.bultosRecogidos} bulto(s) en el recojo {recojo.codigo} y ya se '
                f'admitieron {admitidos}: no se pueden admitir {bultosNuevos} mas. Si sobra un paquete, reportalo')
    return recojo


def _aplicarRecargoRecojo(cotizacion, recojo):
    """El recargo de recojo se cobra una sola vez: en el primer envio."""
    recargo = Decimal(current_app.config['RECARGO_RECOJO'])
    if not cotizacion or not recojo or recargo <= 0:
        return
    if conexion.session.query(PedidoModel.id).filter_by(solicitudRecojoId=recojo.id).first():
        return
    cotizacion['recargoRecojo'] = str(aDecimal(recargo))
    cotizacion['total'] = str(aDecimal(Decimal(cotizacion['total']) + recargo))


@bp.route('/pedido/<int:id>/ingresar-almacen', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def ingresarAlmacen(id):
    """Recepcion fisica de un envio pre-registrado: se pesa, se mide y se
    inspecciona. Si el monto salio de la tarifa y aun no hay pago, se
    recalcula con el peso facturable real."""
    data = cuerpoJson()
    bultos = leerBultos(data, requerido=True)
    inspeccion = leerInspeccion(data)
    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)

    if pedido.estadoId != idEstado('pendiente'):
        return {'message': 'Solo se puede registrar el ingreso de un pedido que este en estado "pendiente"'}, 409
    exigirMiAgencia(pedido.almacenId, 'Este envio se recibe en otra agencia')

    detalleBultos, pesos = calcularPesos(bultos)
    pedido.pesoKg = float(pesos['pesoRealKg'])
    pedido.pesoFacturableKg = pesos['pesoFacturableKg']

    tienePago = conexion.session.query(PagoModel.id).filter_by(pedidoId=id).first()
    if pedido.tarifaId and not tienePago:
        almacen = conexion.session.get(AlmacenModel, pedido.almacenId)
        direccion = conexion.session.get(DireccionModel, pedido.direccionEntregaId)
        cotizacion = cotizarEnvio(almacen.zonaId if almacen else None, direccion.zonaId if direccion else None,
                                  pedido.tipoServicio, pesos['pesoFacturableKg'], pedido.valorDeclarado)
        if cotizacion:
            nuevoMonto = Decimal(cotizacion['total'])
            if nuevoMonto != aDecimal(pedido.monto):
                auditar('monto_recalculado_por_peso', 'pedido', id, {'antes': pedido.monto, 'despues': nuevoMonto})
                pedido.monto = nuevoMonto
            pedido.tarifaId = cotizacion['tarifaId']
            pedido.costoSeguro = Decimal(cotizacion['seguro'])
            pedido.detalleCotizacion = serializarCotizacion(cotizacion, pesos)
            pedido.fechaEntregaEstimada = fechaEstimada(cotizacion) or pedido.fechaEntregaEstimada

    aplicarInspeccion(pedido, inspeccion)
    guardarBultos(pedido, detalleBultos)

    estadoEnAlmacen = idEstado('en_almacen')
    pedido.estadoId = estadoEnAlmacen
    registrarHistorial(id, estadoEnAlmacen, comentario=texto(data, 'comentario', maximo=500) or
                       f'Paquete recibido e inspeccionado en agencia ({len(detalleBultos)} bulto(s))')
    conexion.session.commit()
    return {'message': 'Ingreso al almacen registrado exitosamente', 'content': PedidoDto().dump(pedido)}, 200


@bp.route('/pedido/<int:id>/etiqueta', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def etiquetaPedido(id):
    """Datos para imprimir una etiqueta por bulto. No incluye el contenido
    del paquete ni el DNI (una etiqueta que dice "celular" invita al robo)."""
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    if nombreEstado(pedido.estadoId) == 'cancelado':
        return {'message': 'El pedido esta cancelado: no se imprime etiqueta'}, 409
    bultos = conexion.session.query(BultoModel).filter_by(pedidoId=id).order_by(BultoModel.numero).all()
    if not bultos:
        return {'message': 'Registra la recepcion en almacen (bultos e inspeccion) antes de imprimir la etiqueta'}, 409

    destinatario = conexion.session.get(ClienteModel, pedido.clienteId)
    remitente = conexion.session.get(ClienteModel, pedido.remitenteId) if pedido.remitenteId else None
    direccion = conexion.session.get(DireccionModel, pedido.direccionEntregaId)
    zona = conexion.session.get(ZonaModel, direccion.zonaId) if direccion and direccion.zonaId else None
    almacen = conexion.session.get(AlmacenModel, pedido.almacenId)
    destino = conexion.session.get(AlmacenModel, agenciaReparto(pedido))
    cobrar = totalACobrar(pedido)

    auditar('etiqueta_impresa', 'pedido', id)
    conexion.session.commit()
    return {'content': {
        'codigoGuia': pedido.codigoGuia,
        'tipoServicio': pedido.tipoServicio,
        'prioridad': pedido.prioridad,
        'modalidadPago': pedido.modalidadPago,
        'montoACobrar': str(cobrar) if cobrar > 0 else None,
        'pesoFacturableKg': str(pedido.pesoFacturableKg) if pedido.pesoFacturableKg is not None else None,
        'fechaCreacion': pedido.fechaCreacion.isoformat() if pedido.fechaCreacion else None,
        'fechaEntregaEstimada': pedido.fechaEntregaEstimada.isoformat() if pedido.fechaEntregaEstimada else None,
        'origen': {'agencia': almacen.nombre if almacen else None},
        'agenciaDestino': {'nombre': destino.nombre if destino else None, 'esLocal': esEnvioLocal(pedido)},
        'remitente': {'nombre': remitente.nombre, 'telefono': remitente.telefono} if remitente else None,
        'destinatario': {
            'nombre': destinatario.nombre if destinatario else None,
            'telefono': destinatario.telefono if destinatario else None,
            'calle': direccion.calle if direccion else None,
            'referencia': direccion.referencia if direccion else None,
            'zona': zona.nombre if zona else None,
        },
        'bultos': [{'codigo': b.codigo, 'numero': b.numero, 'total': len(bultos),
                    'pesoFacturableKg': str(b.pesoFacturableKg)} for b in bultos],
    }}, 200


@bp.route('/pedido/<int:id>/bultos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def bultosPedido(id):
    obtener(PedidoModel, id, 'Pedido no existe')
    bultos = conexion.session.query(BultoModel).filter_by(pedidoId=id).order_by(BultoModel.numero).all()
    return {'content': BultoDto().dump(bultos, many=True)}, 200


@bp.route('/pedidos', methods=['GET'])
@requiereLogin
def listarPedidos():
    query = filtrarPorAgencia(conexion.session.query(PedidoModel), agenciaDelUsuario())

    if rolActual() == 'repartidor':
        perfil = exigirMiRepartidor()
        query = query.filter(PedidoModel.repartidorId == perfil.id)

    nombre = request.args.get('estado')
    if nombre:
        estado = conexion.session.query(EstadoPedidoModel).filter_by(nombre=nombre).first()
        query = query.filter(PedidoModel.estadoId == (estado.id if estado else -1))

    if request.args.get('atrasados') in ('1', 'true'):
        # Fecha comprometida vencida y todavia sin entregar
        query = query.filter(PedidoModel.fechaEntregaEstimada < ahoraLocal(),
                             PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS)))

    clienteId = request.args.get('cliente_id', type=int)
    if clienteId:
        query = query.filter(PedidoModel.clienteId == clienteId)

    buscar = request.args.get('q')
    if buscar:
        patron = patronBusqueda(buscar)
        query = query.join(ClienteModel, PedidoModel.clienteId == ClienteModel.id).filter(
            PedidoModel.codigoGuia.ilike(patron, escape='\\') |
            ClienteModel.nombre.ilike(patron, escape='\\') |
            ClienteModel.telefono.ilike(patron, escape='\\')
        )

    query = query.order_by(PedidoModel.fechaCreacion.desc(), PedidoModel.id.desc())
    return paginar(query, PedidoDto()), 200


@bp.route('/pedidos/disponibles', methods=['GET'])
@requiereRol('admin', 'repartidor')
def listarPedidosDisponibles():
    # Listos para reparto: locales en su almacen, o ya llegados a la agencia de destino
    agenciaRep = func.coalesce(PedidoModel.agenciaDestinoId, PedidoModel.almacenId)
    query = conexion.session.query(PedidoModel).filter(
        PedidoModel.repartidorId.is_(None),
        ((PedidoModel.estadoId == idEstado('en_almacen')) & (agenciaRep == PedidoModel.almacenId)) |
        (PedidoModel.estadoId == idEstado('en_agencia_destino')),
    )

    if rolActual() == 'repartidor':
        zonaId = exigirMiRepartidor().zonaId  # el repartidor solo ve el pool de SU zona
        if not zonaId:
            return {'content': []}, 200
    else:
        zonaId = request.args.get('zona_id', type=int)

    if zonaId:
        query = query.join(AlmacenModel, agenciaRep == AlmacenModel.id).filter(AlmacenModel.zonaId == zonaId)

    # Urgentes primero, luego los mas antiguos.
    query = query.order_by((PedidoModel.prioridad == 'urgente').desc(), PedidoModel.fechaCreacion)
    return {'content': PedidoDto().dump(query.limit(200).all(), many=True)}, 200


@bp.route('/pedido/<int:id>/tomar', methods=['POST'])
@requiereRol('admin', 'repartidor')
def tomarPedido(id):
    data = cuerpoJson()
    repartidorId = entero(data, 'repartidorId', requerido=True)

    if rolActual() != 'admin':
        perfil = miRepartidor()
        if not perfil or perfil.id != repartidorId:
            return {'message': 'Solo puedes tomar pedidos para ti mismo'}, 403

    # Bloquear al repartidor serializa sus operaciones: dos clics simultaneos
    # no pueden crearle dos rutas activas.
    repartidor = obtener(RepartidorModel, repartidorId, 'Repartidor no existe', bloquear=True)
    validarRepartidorOperativo(repartidor)

    pedido, ruta = asignarPedidoARuta(id, repartidor, rutaActivaDe(repartidor.id), 'Repartidor tomo el pedido')
    conexion.session.commit()

    return {
        'message': 'Pedido asignado exitosamente',
        'content': PedidoDto().dump(pedido),
        'ruta': {'id': ruta.id, 'codigo': ruta.codigo},
    }, 200


@bp.route('/pedido/<int:id>/estado', methods=['POST'])
@requiereLogin
def cambiarEstadoPedido(id):
    data = cuerpoJson()
    nuevo = opcion(data, 'estado', list(TRANSICIONES_VALIDAS), requerido=True)
    comentario = texto(data, 'comentario', maximo=500)
    lat = coordenada(data, 'latitud', 'lat')
    lon = coordenada(data, 'longitud', 'lon')

    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    exigirAccesoPedido(pedido)
    actual = nombreEstado(pedido.estadoId)

    if nuevo == 'entregado':
        return {'message': 'Para registrar una entrega usa "Entregar y cobrar" (exige cobro y evidencia)'}, 409

    if not puedeTransicionar(actual, nuevo):
        opciones = ', '.join(e for e in TRANSICIONES_VALIDAS.get(actual, []) if e != 'entregado') or 'ninguno (es un estado final)'
        return {'message': f'No se puede pasar de "{actual}" a "{nuevo}". Desde "{actual}" solo se permite: {opciones}'}, 409

    if rolActual() not in ROLES_POR_ESTADO_DESTINO.get(nuevo, ()):
        if nuevo == 'cancelado':
            return {'message': 'Solo un administrador puede cancelar un pedido'}, 403
        return {'message': f'Tu rol no puede marcar un pedido como "{nuevo}"'}, 403

    if rolActual() == 'repartidor':
        perfil = miRepartidor()
        if not perfil or pedido.repartidorId != perfil.id:
            return {'message': 'Este pedido no esta asignado a ti'}, 403

    if nuevo in ESTADOS_CON_COMENTARIO and not comentario:
        raise ErrorValidacion('Deja constancia de lo ocurrido en el comentario '
                              '(ej. quien recibio la devolucion y su DNI, o que se sabe del paquete)')

    if nuevo == 'no_entregado':
        motivo = opcion(data, 'motivo', MOTIVOS_NO_ENTREGA, requerido=True)
        pedido.intentosEntrega = (pedido.intentosEntrega or 0) + 1
        pedido.motivoNoEntrega = motivo
        comentario = f'Intento {pedido.intentosEntrega} fallido ({motivo})' + (f': {comentario}' if comentario else '')

    elif nuevo == 'asignado':  # reintento
        maximo = current_app.config['MAX_INTENTOS_ENTREGA']
        if (pedido.intentosEntrega or 0) >= maximo:
            return {'message': f'El pedido ya tuvo {maximo} intentos fallidos: debe devolverse al remitente'}, 409
        ruta = conexion.session.get(RutaModel, pedido.rutaId) if pedido.rutaId else None
        if not ruta or ruta.estado not in ('planificada', 'en_curso'):
            return {'message': 'La ruta de este pedido ya no esta activa: al cerrarla vuelve a la agencia'}, 409
        comentario = comentario or 'Se reprograma la entrega'

    elif nuevo == 'por_devolver':
        # La agencia que tiene el paquete en la mano es la que lo marca
        enOrigen = actual == 'en_almacen'
        exigirMiAgencia(pedido.almacenId if enOrigen else agenciaReparto(pedido),
                        'Solo la agencia que tiene el paquete puede iniciar la devolucion')
        if enOrigen and _enManifiestoActivo(pedido.id):
            return {'message': 'El envio esta en un manifiesto abierto: retiralo del manifiesto antes de devolverlo'}, 409
        pedido.retornoAlOrigen = enOrigen
        pedido.repartidorId = None
        pedido.rutaId = None
        # Si el paquete ya salio a repartirse o viajo, devolverlo tiene costo.
        # Si el remitente desiste antes de que salga de la agencia, no.
        cargo = None if enOrigen else generarCargoDevolucion(pedido, usuarioActualId())
        auditar('devolucion_iniciada', 'pedido', id, {'estadoAnterior': actual, 'intentos': pedido.intentosEntrega,
                                                      'cargo': cargo.monto if cargo else None})
        comentario = comentario or ('Devolucion al remitente: ' + (
            'lo retira en la agencia de origen' if enOrigen or esEnvioLocal(pedido)
            else 'debe regresar a la agencia de origen en un manifiesto'))

    elif nuevo == 'cancelado':
        pedido.repartidorId = None
        pedido.rutaId = None
        auditar('pedido_cancelado', 'pedido', id, {'estadoAnterior': actual, 'comentario': comentario})

    elif nuevo == 'devuelto':
        if agenciaDondeEsta(pedido) != pedido.almacenId:
            return {'message': 'El paquete todavia esta en la agencia de destino: primero debe volver a la '
                               'agencia de origen en un manifiesto (Despachos)'}, 409
        exigirMiAgencia(pedido.almacenId, 'La devolucion se entrega en la agencia de origen')
        cobrado = _cobrarDevolucion(pedido, data)
        auditar('pedido_devuelto', 'pedido', id, {'intentos': pedido.intentosEntrega, 'constancia': comentario,
                                                  'cobrado': cobrado})
        if cobrado:
            comentario = f'{comentario} (cobrado al remitente: S/ {cobrado})'

    elif nuevo == 'extraviado':
        pedido.repartidorId = None
        pedido.rutaId = None
        # El valor declarado (y si se cobro seguro) es la base de la indemnizacion
        auditar('pedido_extraviado', 'pedido', id, {
            'estadoAnterior': actual, 'valorDeclarado': aDecimal(pedido.valorDeclarado),
            'costoSeguro': aDecimal(pedido.costoSeguro), 'comentario': comentario})

    idNuevo = idEstado(nuevo)
    pedido.estadoId = idNuevo
    registrarHistorial(id, idNuevo, comentario=comentario, lat=lat, lon=lon)
    avisos = encolarAviso(pedido, nuevo) if nuevo in ('en_camino', 'no_entregado') else []
    conexion.session.commit()
    despacharAvisos(avisos)

    return {'message': f'Pedido actualizado a "{nuevo}"'}, 200


def _cobrarDevolucion(pedido, data):
    """El remitente retira su paquete pagando lo pendiente: el flete si era
    contra entrega (el destinatario nunca lo pago) y el cargo de devolucion."""
    flete, cargos = saldoAlDevolver(pedido)
    total = flete + cargos
    if total <= 0:
        return None
    metodo = opcion(data, 'metodo', METODOS_PAGO)
    if not metodo:
        raise ErrorNegocio(f'Para entregar la devolucion cobra S/ {total} al remitente '
                           f'(flete S/ {flete} + cargo de devolucion S/ {cargos}): indica el metodo de pago', 402)
    referencia = texto(data, 'referencia', maximo=60)
    if metodo != 'efectivo' and not referencia:
        raise ErrorValidacion(f'Para pagos con {metodo} ingresa el numero de operacion')
    if flete > 0:
        conexion.session.add(PagoModel(pedidoId=pedido.id, monto=flete, metodo=metodo, referencia=referencia,
                                       estadoPago='pagado', fechaPago=func.now(), registradoPorId=usuarioActualId()))
    for cargo in cargosPendientes(pedido.id):
        cargo.estado = 'pagado'
        cargo.metodo = metodo
        cargo.referencia = referencia
        cargo.fechaPago = func.now()
        cargo.cobradoPorId = usuarioActualId()
    return total


@bp.route('/pedido/<int:id>/saldo-devolucion', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def saldoDevolucion(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    flete, cargos = saldoAlDevolver(pedido)
    return {'content': {'flete': str(flete), 'cargos': str(cargos), 'total': str(flete + cargos)}}, 200


@bp.route('/pedido/<int:id>/redireccionar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def redireccionarPedido(id):
    """Corrige la direccion de entrega (la causa mas comun de una entrega
    fallida) sin cancelar y volver a crear el envio.

    - Antes de que salga del origen (pendiente / en_almacen): cualquier
      direccion del destinatario; si cambia de zona se recalcula la agencia
      de reparto y el flete (si ya pago, la diferencia se cobra aparte).
    - Ya en la agencia de reparto (en_agencia_destino, o una devolucion que
      aun no emprendio el regreso): solo direcciones que reparte esa misma
      agencia. Si estaba por devolver, vuelve a quedar listo para reparto y
      se reinician los intentos (es otra direccion)."""
    data = cuerpoJson()
    direccionId = entero(data, 'direccionEntregaId', requerido=True)
    motivo = texto(data, 'motivo', requerido=True, minimo=5, maximo=300)

    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    exigirAccesoPedido(pedido)
    actual = nombreEstado(pedido.estadoId)
    direccion = obtener(DireccionModel, direccionId, 'La direccion no existe')
    if direccion.clienteId != pedido.clienteId or not direccion.activo:
        raise ErrorValidacion('La direccion debe ser una direccion activa del mismo destinatario')
    if direccion.id == pedido.direccionEntregaId:
        raise ErrorValidacion('Es la misma direccion que ya tiene el envio')

    almacen = conexion.session.get(AlmacenModel, pedido.almacenId)
    nuevaAgencia = elegirAgenciaDestino(almacen, direccion.zonaId)
    if nuevaAgencia is None:
        raise ErrorValidacion('Sin cobertura: ninguna agencia activa reparte en la zona de esa direccion')
    anterior = conexion.session.get(DireccionModel, pedido.direccionEntregaId)
    cambios = {'direccionAnterior': anterior.calle if anterior else None, 'direccionNueva': direccion.calle,
               'motivo': motivo, 'estado': actual}

    if actual in ('pendiente', 'en_almacen'):
        if actual == 'en_almacen' and _enManifiestoActivo(pedido.id):
            return {'message': 'El envio esta en un manifiesto abierto: retiralo antes de cambiar el destino'}, 409
        exigirMiAgencia(pedido.almacenId, 'El destino se corrige en la agencia de origen')
        if nuevaAgencia != agenciaReparto(pedido):
            cambios['agenciaAnterior'] = agenciaReparto(pedido)
            cambios['agenciaNueva'] = nuevaAgencia
            pedido.agenciaDestinoId = nuevaAgencia
            _recotizarPorRedireccion(pedido, almacen, direccion, cambios)
    elif actual == 'en_agencia_destino' or (actual == 'por_devolver' and not pedido.retornoAlOrigen):
        exigirMiAgencia(agenciaReparto(pedido), 'Solo la agencia que tiene el paquete puede reprogramarlo')
        if nuevaAgencia != agenciaReparto(pedido) and not (esEnvioLocal(pedido) and nuevaAgencia == pedido.almacenId):
            return {'message': 'Esa direccion la reparte otra agencia: el paquete ya esta aqui. Inicia una devolucion '
                               'o registra un envio nuevo'}, 409
        if actual == 'por_devolver':
            listo = idEstado(estadoListoParaReparto(pedido))
            pedido.estadoId = listo
            cambios['intentosAnteriores'] = pedido.intentosEntrega
            pedido.intentosEntrega = 0
            pedido.motivoNoEntrega = None
            # Ya no se devuelve: el cargo de devolucion no corresponde
            for cargo in cargosPendientes(pedido.id):
                if cargo.concepto == 'devolucion':
                    cargo.estado = 'anulado'
    else:
        return {'message': f'No se puede cambiar la direccion de un envio "{actual}"'}, 409

    pedido.direccionEntregaId = direccion.id
    auditar('pedido_redireccionado', 'pedido', id, cambios)
    registrarHistorial(id, pedido.estadoId, comentario=f'Nueva direccion de entrega: {direccion.calle} ({motivo})')
    conexion.session.commit()
    return {'message': 'Direccion de entrega actualizada', 'content': PedidoDto().dump(pedido)}, 200


def _recotizarPorRedireccion(pedido, almacen, direccion, cambios):
    """Otra zona = otra tarifa. Sin pago aun: se actualiza el monto. Ya
    pagado: la diferencia a favor del courier queda como cargo pendiente."""
    if not pedido.tarifaId:
        return  # precio manual: lo decide el operador
    cotizacion = cotizarEnvio(almacen.zonaId, direccion.zonaId, pedido.tipoServicio, pedido.pesoFacturableKg,
                              pedido.valorDeclarado)
    if not cotizacion:
        raise ErrorValidacion('No hay tarifa hacia la zona de la nueva direccion: registrala antes de redirigir')
    nuevo = aDecimal(cotizacion['total'])
    cambios['montoAnterior'] = aDecimal(pedido.monto)
    cambios['montoNuevo'] = nuevo
    if fletePagado(pedido.id) == 0:
        pedido.monto = nuevo
        pedido.tarifaId = cotizacion['tarifaId']
    elif nuevo > aDecimal(pedido.monto):
        conexion.session.add(CargoAdicionalModel(
            pedidoId=pedido.id, concepto='redireccion', monto=nuevo - aDecimal(pedido.monto),
            descripcion='Diferencia de tarifa por cambio de destino', registradoPorId=usuarioActualId()))
    pedido.fechaEntregaEstimada = fechaEstimada(cotizacion)


def _enManifiestoActivo(pedidoId):
    return conexion.session.query(ManifiestoBultoModel.id).join(
        ManifiestoModel, ManifiestoBultoModel.manifiestoId == ManifiestoModel.id
    ).filter(ManifiestoBultoModel.pedidoId == pedidoId, ManifiestoModel.estado.in_(MANIFIESTOS_ACTIVOS)).first() is not None


@bp.route('/pedido/<int:id>/entregar-y-cobrar', methods=['POST'])
@requiereRol('admin', 'repartidor')
def entregarYCobrar(id):
    """Registra la entrega y, si el pedido es contra entrega, el cobro: todo
    en una sola transaccion. Es idempotente: si el celular reintenta la
    peticion por mala senal, la segunda llamada devuelve el mismo resultado
    en vez de un error."""
    data = cuerpoJson()
    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)

    if rolActual() == 'repartidor':
        perfil = miRepartidor()
        if not perfil or pedido.repartidorId != perfil.id:
            return {'message': 'Este pedido no esta asignado a ti'}, 403

    actual = nombreEstado(pedido.estadoId)
    pagoExistente = conexion.session.query(PagoModel).filter_by(pedidoId=id).first()

    if actual == 'entregado':
        return {
            'message': 'Este pedido ya estaba registrado como entregado',
            'content': {'pedido': PedidoDto().dump(pedido), 'pago': PagoDto().dump(pagoExistente) if pagoExistente else None},
        }, 200

    if not puedeTransicionar(actual, 'entregado'):
        return {'message': f'No se puede entregar un pedido en estado "{actual}"'}, 409

    foto = evidencia(data, requerido=current_app.config['EVIDENCIA_OBLIGATORIA'])
    nombreReceptor = texto(data, 'nombreReceptor', requerido=True, maximo=100, minimo=3)
    dniReceptor = dni(data, 'dniReceptor')
    if not dniReceptor:
        raise ErrorValidacion('Registra el DNI de quien recibe el paquete')
    relacion = opcion(data, 'relacionReceptor', RELACIONES_RECEPTOR, defecto='titular')
    firma = data.get('firma')
    if firma in (None, ''):
        if current_app.config['FIRMA_OBLIGATORIA']:
            raise ErrorValidacion('Falta la firma de quien recibe')
        firma = None
    else:
        firma = evidencia(data, 'firma')

    if pedido.requierePin:
        maximo = current_app.config['MAX_INTENTOS_PIN']
        if (pedido.pinIntentos or 0) >= maximo:
            return {'message': 'El codigo de entrega se bloqueo por intentos fallidos. '
                               'Comunicate con la agencia para que lo regeneren'}, 423
        pinIngresado = data.get('pin')
        if not isinstance(pinIngresado, str) or not pinIngresado.strip():
            # Campo vacio = formulario incompleto, no un intento: no consume intentos
            raise ErrorValidacion('Este envio se entrega con codigo: pide el PIN al destinatario')
        if not pinEsCorrecto(pedido, pinIngresado):
            pedido.pinIntentos = (pedido.pinIntentos or 0) + 1
            restantes = maximo - pedido.pinIntentos
            if restantes <= 0:
                auditar('pin_bloqueado', 'pedido', id, {'repartidorId': pedido.repartidorId})
            # Se guarda el intento aunque la entrega no proceda
            conexion.session.commit()
            return {'message': f'Codigo de entrega incorrecto. Quedan {max(restantes, 0)} intento(s)'}, 400
    nuevoPago = None
    nuevoRecaudo = None
    metodo = opcion(data, 'metodo', METODOS_PAGO, defecto='efectivo')
    referencia = texto(data, 'referencia', maximo=60)
    debeRecaudo = aDecimal(pedido.montoRecaudo) > 0 and not conexion.session.query(RecaudoModel.id).filter_by(
        pedidoId=id).first()
    debeFlete = pedido.modalidadPago == 'contra_entrega' and not pagoExistente and aDecimal(pedido.monto) > 0
    if (debeFlete or debeRecaudo) and metodo != 'efectivo' and not referencia:
        raise ErrorValidacion(f'Para pagos con {metodo} ingresa el numero de operacion')

    if debeRecaudo:
        montoProducto = dinero(data, 'montoRecaudo')
        if montoProducto is not None and montoProducto != aDecimal(pedido.montoRecaudo):
            return {'message': f'El monto del producto cobrado (S/ {montoProducto}) no coincide con el que pidio el '
                               f'remitente (S/ {aDecimal(pedido.montoRecaudo)}). Cobra el monto exacto o reporta '
                               'una incidencia'}, 409
        nuevoRecaudo = RecaudoModel(
            pedidoId=id, remitenteId=pedido.remitenteId, monto=aDecimal(pedido.montoRecaudo), metodo=metodo,
            referencia=referencia, repartidorId=pedido.repartidorId, rutaId=pedido.rutaId,
            registradoPorId=usuarioActualId(),
        )
        conexion.session.add(nuevoRecaudo)

    if debeFlete:
        montoCobrado = dinero(data, 'monto')
        if montoCobrado is not None and montoCobrado != aDecimal(pedido.monto):
            return {'message': f'El monto cobrado (S/ {montoCobrado}) no coincide con el del pedido (S/ {aDecimal(pedido.monto)}). '
                               'Cobra el monto exacto o reporta una incidencia'}, 409
        nuevoPago = PagoModel(
            pedidoId=id,
            monto=aDecimal(pedido.monto),
            metodo=metodo,
            referencia=referencia,
            estadoPago='pagado',
            fechaPago=func.now(),
            repartidorId=pedido.repartidorId,
            rutaId=pedido.rutaId,
            registradoPorId=usuarioActualId(),
        )
        conexion.session.add(nuevoPago)

    estadoEntregado = idEstado('entregado')
    pedido.estadoId = estadoEntregado
    pedido.fechaEntrega = func.now()
    pedido.motivoNoEntrega = None
    if foto:
        pedido.evidenciaEntrega = foto
    conexion.session.add(EntregaModel(
        pedidoId=id, nombreReceptor=nombreReceptor, dniReceptor=dniReceptor, relacion=relacion, firma=firma,
        pinVerificado=bool(pedido.requierePin), repartidorId=pedido.repartidorId, usuarioId=usuarioActualId(),
        latitud=coordenada(data, 'latitud', 'lat'), longitud=coordenada(data, 'longitud', 'lon'),
    ))
    registrarHistorial(
        id, estadoEntregado,
        comentario=texto(data, 'comentario', maximo=500) or (
            'Entregado y cobrado' if (nuevoPago or nuevoRecaudo) else 'Entregado'),
        lat=coordenada(data, 'latitud', 'lat'), lon=coordenada(data, 'longitud', 'lon'),
    )
    avisos = encolarAviso(pedido, 'entregado')
    conexion.session.commit()
    despacharAvisos(avisos)

    cobrado = (aDecimal(nuevoPago.monto) if nuevoPago else aDecimal(0)) + \
        (aDecimal(nuevoRecaudo.monto) if nuevoRecaudo else aDecimal(0))
    return {
        'message': f'Pedido entregado. Cobrado: S/ {cobrado}' if cobrado else 'Pedido entregado exitosamente',
        'content': {
            'pedido': PedidoDto().dump(pedido),
            'pago': PagoDto().dump(nuevoPago) if nuevoPago else None,
            'recaudo': str(aDecimal(nuevoRecaudo.monto)) if nuevoRecaudo else None,
            'totalCobrado': str(cobrado),
        },
    }, 200


@bp.route('/pedido/<int:id>', methods=['GET'])
@requiereLogin
def obtenerPedido(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    contenido = PedidoDto().dump(pedido)
    contenido['tieneEvidencia'] = conexion.session.query(PedidoModel.id).filter(
        PedidoModel.id == id, PedidoModel.evidenciaEntrega.isnot(None)).first() is not None
    return {'content': contenido}, 200


@bp.route('/pedido/<int:id>/evidencia', methods=['GET'])
@requiereLogin
def evidenciaPedido(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    if not pedido.evidenciaEntrega:
        return {'message': 'Este pedido no tiene foto de evidencia'}, 404
    return {'content': pedido.evidenciaEntrega}, 200


@bp.route('/pedido/<int:id>', methods=['DELETE'])
@requiereRol('admin')
def eliminarPedido(id):
    """No borra la fila: la marca como cancelada para conservar el historial
    (auditoria, reportes, reclamos)."""
    data = cuerpoJson()
    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    actual = nombreEstado(pedido.estadoId)

    if not puedeTransicionar(actual, 'cancelado'):
        return {'message': f'No se puede cancelar un pedido en estado "{actual}" (es un estado final o no admite cancelacion)'}, 409

    comentario = texto(data, 'comentario', maximo=500) or 'Pedido cancelado por un administrador'
    estadoCancelado = idEstado('cancelado')
    pedido.estadoId = estadoCancelado
    pedido.repartidorId = None
    pedido.rutaId = None
    auditar('pedido_cancelado', 'pedido', id, {'estadoAnterior': actual, 'comentario': comentario})
    registrarHistorial(id, estadoCancelado, comentario=comentario)
    conexion.session.commit()

    return {'message': f'Pedido {id} marcado como cancelado (no se elimino de la base de datos)'}, 200


@bp.route('/pedido/<int:id>/historial', methods=['GET'])
@requiereLogin
def historialPedido(id):
    exigirAccesoPedido(obtener(PedidoModel, id, 'Pedido no existe'))
    resultado = conexion.session.query(HistorialEstadoModel).filter_by(pedidoId=id) \
        .order_by(HistorialEstadoModel.fecha, HistorialEstadoModel.id).all()
    return {'content': HistorialEstadoDto().dump(resultado, many=True)}, 200


@bp.route('/pedido/<int:id>/entrega', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def constanciaEntrega(id):
    """Constancia de entrega (para reclamos): quien recibio, firma y foto."""
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    entrega = conexion.session.query(EntregaModel).filter_by(pedidoId=id).first()
    if not entrega:
        return {'message': 'Este pedido no tiene una entrega registrada'}, 404
    return {'content': {
        'nombreReceptor': entrega.nombreReceptor,
        'dniReceptor': entrega.dniReceptor,
        'relacion': entrega.relacion,
        'pinVerificado': entrega.pinVerificado,
        'firma': entrega.firma,
        'foto': pedido.evidenciaEntrega,
        'latitud': entrega.latitud,
        'longitud': entrega.longitud,
        'fecha': entrega.fecha.isoformat() if entrega.fecha else None,
    }}, 200


@bp.route('/pedido/<int:id>/pin', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def regenerarPin(id):
    """Nuevo codigo de entrega (el remitente lo perdio o se bloqueo por
    intentos). El anterior deja de servir. Queda auditado."""
    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    exigirAccesoPedido(pedido)
    if nombreEstado(pedido.estadoId) in ESTADOS_FINALES:
        raise ErrorNegocio('El envio ya esta cerrado', 409)
    pin = generarPin(pedido)
    auditar('pin_regenerado', 'pedido', id)
    conexion.session.commit()
    return {'message': 'Nuevo codigo de entrega generado. El anterior ya no sirve',
            'content': {'pinEntrega': pin}}, 200


@bp.route('/pedido/<int:id>/avisos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def avisosDelPedido(id):
    """Avisos enviados al destinatario (para responder "nunca me avisaron")."""
    from app.models import NotificacionModel
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    filas = conexion.session.query(NotificacionModel).filter_by(pedidoId=id)         .order_by(NotificacionModel.id).all()
    return {'content': [{
        'evento': f.evento, 'canal': f.canal, 'estado': f.estado, 'intentos': f.intentos, 'error': f.error,
        'fecha': (f.fechaEnvio.isoformat() + 'Z') if f.fechaEnvio else None,
    } for f in filas]}, 200
