"""Ciclo de vida del pedido: registro, almacen, asignacion, estados, entrega."""
from decimal import Decimal

from flask import Blueprint, current_app, request
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    ClienteModel, DireccionModel, AlmacenModel, RepartidorModel, EstadoPedidoModel, TarifaZonaModel,
    RutaModel, PedidoModel, HistorialEstadoModel, PagoModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, usuarioActualId, rolActual, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorValidacion, cuerpoJson, texto, entero, dinero, decimalPositivo, coordenada,
    opcion, booleano, evidencia,
)
from app.reglas import (
    METODOS_PAGO, MODALIDADES_PAGO, MOTIVOS_NO_ENTREGA, PRIORIDADES, ROLES_POR_ESTADO_DESTINO, TRANSICIONES_VALIDAS, aDecimal, calcularMontoTarifa, puedeTransicionar,
)
from app.schemas import (
    HistorialEstadoDto, PagoDto, PedidoDto,
)
from app.servicios import (
    asignarPedidoARuta, buscarTarifa, exigirAccesoPedido, exigirMiRepartidor, generarCodigoGuia, idEstado, miRepartidor, nombreEstado, obtener, paginar, patronBusqueda, registrarHistorial, rutaActivaDe, validarRepartidorOperativo,
)


bp = Blueprint('pedidos', __name__)


@bp.route('/pedido', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearPedido():
    data = cuerpoJson()
    clienteId = entero(data, 'clienteId', requerido=True)
    almacenId = entero(data, 'almacenId', requerido=True)
    direccionId = entero(data, 'direccionEntregaId', requerido=True)
    prioridad = opcion(data, 'prioridad', PRIORIDADES, defecto='normal')
    modalidad = opcion(data, 'modalidadPago', MODALIDADES_PAGO, defecto='contra_entrega')
    peso = decimalPositivo(data, 'pesoKg', maximo=Decimal('1000'))
    montoManual = dinero(data, 'monto')
    yaEnAlmacen = booleano(data, 'yaEnAlmacen', defecto=False)

    cliente = obtener(ClienteModel, clienteId, 'El cliente no existe')
    if not cliente.activo:
        raise ErrorValidacion('El cliente esta desactivado')
    direccion = obtener(DireccionModel, direccionId, 'La direccion de entrega no existe')
    if direccion.clienteId != clienteId or not direccion.activo:
        raise ErrorValidacion('Esa direccion no pertenece al cliente indicado')
    almacen = obtener(AlmacenModel, almacenId, 'El almacen no existe')
    if not almacen.activo:
        raise ErrorValidacion('El almacen esta desactivado')

    tarifa = buscarTarifa(almacen.zonaId, direccion.zonaId)
    montoTarifa = calcularMontoTarifa(tarifa, peso) if tarifa else None

    tarifaId = None
    if montoManual is None:
        if montoTarifa is None:
            if modalidad == 'contra_entrega':
                raise ErrorValidacion('No hay una tarifa registrada entre la zona del almacen y la del destino: '
                                      'ingresa el monto manualmente o registra la tarifa')
            monto = Decimal('0.00')
        else:
            monto, tarifaId = montoTarifa, tarifa.id
    else:
        monto = montoManual

    if modalidad == 'contra_entrega' and monto <= 0:
        raise ErrorValidacion('Un pedido contra entrega debe tener un monto mayor a 0')

    estadoInicial = idEstado('en_almacen' if yaEnAlmacen else 'pendiente')
    pedido = PedidoModel(
        codigoGuia=generarCodigoGuia(),
        clienteId=clienteId,
        usuarioId=usuarioActualId(),
        almacenId=almacenId,
        direccionEntregaId=direccionId,
        estadoId=estadoInicial,
        prioridad=prioridad,
        modalidadPago=modalidad,
        monto=monto,
        tarifaId=tarifaId,
        pesoKg=float(peso) if peso is not None else None,
        descripcionProducto=texto(data, 'descripcionProducto', maximo=500),
        notas=texto(data, 'notas', maximo=1000),
    )
    conexion.session.add(pedido)
    conexion.session.flush()

    if montoManual is not None and montoTarifa is not None and montoManual != montoTarifa:
        auditar('monto_manual', 'pedido', pedido.id, {'montoTarifa': montoTarifa, 'montoIngresado': montoManual})

    registrarHistorial(pedido.id, estadoInicial,
                       comentario='Pedido registrado' + (' y confirmado en almacen' if yaEnAlmacen else ''))
    conexion.session.commit()

    return {'message': 'Pedido creado exitosamente', 'content': PedidoDto().dump(pedido)}, 201


@bp.route('/pedido/<int:id>/ingresar-almacen', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def ingresarAlmacen(id):
    data = cuerpoJson()
    peso = decimalPositivo(data, 'pesoKg', maximo=Decimal('1000'))
    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)

    if pedido.estadoId != idEstado('pendiente'):
        return {'message': 'Solo se puede registrar el ingreso de un pedido que este en estado "pendiente"'}, 409

    if peso is not None:
        pedido.pesoKg = float(peso)  # el peso real, medido en la balanza
        # Si el monto salio de la tarifa (no fue un precio pactado a mano),
        # se recalcula con el peso real mientras todavia no exista un pago.
        tieneP = conexion.session.query(PagoModel.id).filter_by(pedidoId=id).first()
        if pedido.tarifaId and not tieneP:
            tarifa = conexion.session.get(TarifaZonaModel, pedido.tarifaId)
            if tarifa:
                nuevoMonto = calcularMontoTarifa(tarifa, peso)
                if nuevoMonto != aDecimal(pedido.monto):
                    auditar('monto_recalculado_por_peso', 'pedido', id, {'antes': pedido.monto, 'despues': nuevoMonto})
                    pedido.monto = nuevoMonto

    estadoEnAlmacen = idEstado('en_almacen')
    pedido.estadoId = estadoEnAlmacen
    registrarHistorial(id, estadoEnAlmacen,
                       comentario=texto(data, 'comentario', maximo=500) or 'Paquete recibido fisicamente en el almacen')
    conexion.session.commit()
    return {'message': 'Ingreso al almacen registrado exitosamente', 'content': PedidoDto().dump(pedido)}, 200


@bp.route('/pedidos', methods=['GET'])
@requiereLogin
def listarPedidos():
    query = conexion.session.query(PedidoModel)

    if rolActual() == 'repartidor':
        perfil = exigirMiRepartidor()
        query = query.filter(PedidoModel.repartidorId == perfil.id)

    nombre = request.args.get('estado')
    if nombre:
        estado = conexion.session.query(EstadoPedidoModel).filter_by(nombre=nombre).first()
        query = query.filter(PedidoModel.estadoId == (estado.id if estado else -1))

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
    query = conexion.session.query(PedidoModel).filter_by(estadoId=idEstado('en_almacen'), repartidorId=None)

    if rolActual() == 'repartidor':
        zonaId = exigirMiRepartidor().zonaId  # el repartidor solo ve el pool de SU zona
        if not zonaId:
            return {'content': []}, 200
    else:
        zonaId = request.args.get('zona_id', type=int)

    if zonaId:
        query = query.join(AlmacenModel, PedidoModel.almacenId == AlmacenModel.id).filter(AlmacenModel.zonaId == zonaId)

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

    if nuevo == 'no_entregado':
        motivo = opcion(data, 'motivo', MOTIVOS_NO_ENTREGA, requerido=True)
        pedido.intentosEntrega = (pedido.intentosEntrega or 0) + 1
        pedido.motivoNoEntrega = motivo
        comentario = f'Intento {pedido.intentosEntrega} fallido ({motivo})' + (f': {comentario}' if comentario else '')

    elif nuevo == 'asignado':  # reintento
        maximo = current_app.config['MAX_INTENTOS_ENTREGA']
        if (pedido.intentosEntrega or 0) >= maximo:
            return {'message': f'El pedido ya tuvo {maximo} intentos fallidos: debe devolverse al almacen'}, 409
        ruta = conexion.session.get(RutaModel, pedido.rutaId) if pedido.rutaId else None
        if not ruta or ruta.estado not in ('planificada', 'en_curso'):
            return {'message': 'La ruta de este pedido ya no esta activa; debe devolverse al almacen'}, 409
        comentario = comentario or 'Se reprograma la entrega'

    elif nuevo == 'cancelado':
        pedido.repartidorId = None
        pedido.rutaId = None
        auditar('pedido_cancelado', 'pedido', id, {'estadoAnterior': actual, 'comentario': comentario})

    elif nuevo == 'devuelto':
        auditar('pedido_devuelto', 'pedido', id, {'intentos': pedido.intentosEntrega})

    idNuevo = idEstado(nuevo)
    pedido.estadoId = idNuevo
    registrarHistorial(id, idNuevo, comentario=comentario, lat=lat, lon=lon)
    conexion.session.commit()

    return {'message': f'Pedido actualizado a "{nuevo}"'}, 200


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
    nuevoPago = None

    if pedido.modalidadPago == 'contra_entrega' and not pagoExistente and aDecimal(pedido.monto) > 0:
        metodo = opcion(data, 'metodo', METODOS_PAGO, defecto='efectivo')
        referencia = texto(data, 'referencia', maximo=60)
        if metodo != 'efectivo' and not referencia:
            raise ErrorValidacion(f'Para pagos con {metodo} ingresa el numero de operacion')
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
    registrarHistorial(
        id, estadoEntregado,
        comentario=texto(data, 'comentario', maximo=500) or ('Entregado y cobrado' if nuevoPago else 'Entregado'),
        lat=coordenada(data, 'latitud', 'lat'), lon=coordenada(data, 'longitud', 'lon'),
    )
    conexion.session.commit()

    return {
        'message': 'Pedido entregado y pago registrado exitosamente' if nuevoPago else 'Pedido entregado exitosamente',
        'content': {'pedido': PedidoDto().dump(pedido), 'pago': PagoDto().dump(nuevoPago) if nuevoPago else None},
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
