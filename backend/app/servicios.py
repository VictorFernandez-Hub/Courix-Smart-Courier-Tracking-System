"""Operaciones de negocio reutilizadas por varios endpoints (consultas,
asignacion de pedidos, caja, armado de respuestas)."""
import secrets

from flask import current_app
from sqlalchemy import func

from app.extensions import conexion
from app.models import (
    UsuarioModel, ZonaModel, ClienteModel, DireccionModel, AlmacenModel, RepartidorModel,
    EstadoPedidoModel, TarifaZonaModel, RutaModel, PedidoModel, HistorialEstadoModel,
    PagoModel, LiquidacionRutaModel, BultoModel, RecaudoModel,
)
from app.core.seguridad import (
    usuarioActualId, rolActual, esStaff,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, paginacion,
)
from app.reglas import (
    ALFABETO_GUIA, ESTADOS_ACTIVOS, aDecimal,
)


def idEstado(nombre):
    estado = conexion.session.query(EstadoPedidoModel).filter_by(nombre=nombre).first()
    if not estado:
        raise ErrorNegocio(f'El catalogo de estados no tiene "{nombre}". Ejecuta: flask sembrar', 500)
    return estado.id


def nombreEstado(estadoId):
    estado = conexion.session.get(EstadoPedidoModel, estadoId)
    return estado.nombre if estado else None


def idsEstados(nombres):
    return [e.id for e in conexion.session.query(EstadoPedidoModel)
            .filter(EstadoPedidoModel.nombre.in_(nombres)).all()]


def obtener(modelo, id, mensaje='No existe', bloquear=False):
    query = conexion.session.query(modelo).filter_by(id=id)
    if bloquear:
        query = query.with_for_update()
    objeto = query.first()
    if not objeto:
        raise ErrorNegocio(mensaje, 404)
    return objeto


def miRepartidor():
    if rolActual() != 'repartidor':
        return None
    return conexion.session.query(RepartidorModel).filter_by(usuarioId=usuarioActualId()).first()


def exigirMiRepartidor():
    perfil = miRepartidor()
    if not perfil:
        raise ErrorNegocio('Tu perfil de repartidor todavia no ha sido configurado', 403)
    return perfil


def agenciaDelUsuario():
    """Agencia a la que esta limitado el usuario actual. Solo aplica a
    operadores con agencia asignada; None = ve todas (admin)."""
    if rolActual() != 'operador':
        return None
    usuario = conexion.session.get(UsuarioModel, usuarioActualId())
    return usuario.agenciaId if usuario else None


def agenciaReparto(pedido):
    """Agencia desde donde sale el reparto final."""
    return pedido.agenciaDestinoId or pedido.almacenId


def esEnvioLocal(pedido):
    return agenciaReparto(pedido) == pedido.almacenId


def estadoListoParaReparto(pedido):
    """Un envio local se reparte desde el almacen de origen; uno a otra
    ciudad, cuando ya llego a la agencia de destino."""
    return 'en_almacen' if esEnvioLocal(pedido) else 'en_agencia_destino'


def agenciaDondeEsta(pedido):
    """Agencia que tiene fisicamente un envio en devolucion (por_devolver):
    la de reparto mientras no emprenda el regreso, la de origen despues."""
    return pedido.almacenId if pedido.retornoAlOrigen else agenciaReparto(pedido)


def faltaPagoPrepagado(pedido):
    """Un prepagado no sale de la agencia (ni en manifiesto ni a reparto)
    sin su pago confirmado."""
    if pedido.modalidadPago != 'prepagado':
        return False
    return not conexion.session.query(PagoModel.id).filter_by(pedidoId=pedido.id, estadoPago='pagado').first()


def filtrarRutasPorAgencia(query, agenciaId):
    """Rutas (y lo que cuelga de ellas: liquidaciones) de la zona de la agencia."""
    if not agenciaId:
        return query
    agencia = conexion.session.get(AlmacenModel, agenciaId)
    return query.filter(RutaModel.zonaId == (agencia.zonaId if agencia else -1))


def exigirAccesoRuta(ruta):
    propia = agenciaDelUsuario()
    if propia:
        agencia = conexion.session.get(AlmacenModel, propia)
        if not agencia or agencia.zonaId != ruta.zonaId:
            raise ErrorNegocio('Ruta no existe', 404)


def filtrarPorAgencia(query, agenciaId):
    """Un operador de agencia solo ve los envios que salen o llegan a ella."""
    if not agenciaId:
        return query
    return query.filter((PedidoModel.almacenId == agenciaId) | (PedidoModel.agenciaDestinoId == agenciaId))


def exigirMiAgencia(agenciaId, mensaje='Solo puedes operar envios de tu agencia'):
    propia = agenciaDelUsuario()
    if propia and propia != agenciaId:
        raise ErrorNegocio(mensaje, 403)


def puedeVerPedido(pedido):
    if esStaff():
        propia = agenciaDelUsuario()
        return not propia or propia in (pedido.almacenId, agenciaReparto(pedido))
    perfil = miRepartidor()
    return perfil is not None and pedido.repartidorId == perfil.id


def exigirAccesoPedido(pedido):
    if not puedeVerPedido(pedido):
        # 404 en vez de 403 para no confirmar que el pedido existe.
        raise ErrorNegocio('Pedido no existe', 404)


def esDuenioDeLaRuta(ruta):
    if rolActual() == 'admin':
        return True
    perfil = miRepartidor()
    return perfil is not None and perfil.id == ruta.repartidorId


def registrarHistorial(pedidoId, estadoId, comentario=None, lat=None, lon=None, usuarioId='actual'):
    """Agrega la entrada a la sesion; el commit lo hace la operacion que la
    origina (todo o nada)."""
    entrada = HistorialEstadoModel(
        pedidoId=pedidoId,
        estadoId=estadoId,
        usuarioId=usuarioActualId() if usuarioId == 'actual' else usuarioId,
        latitud=lat,
        longitud=lon,
        comentario=comentario,
    )
    conexion.session.add(entrada)
    return entrada


def paginar(query, dto):
    pagina, porPagina = paginacion()
    total = query.order_by(None).count()
    resultado = query.offset((pagina - 1) * porPagina).limit(porPagina).all()
    return {
        'content': dto.dump(resultado, many=True),
        'paginacion': {
            'pagina': pagina,
            'porPagina': porPagina,
            'totalRegistros': total,
            'totalPaginas': (total + porPagina - 1) // porPagina,
        },
    }


def patronBusqueda(valor):
    """LIKE seguro: el texto del usuario no puede inyectar comodines % / _."""
    valor = valor.strip()[:100]
    escapado = valor.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escapado}%'


def generarCodigoGuia():
    """Codigo no secuencial (CE-7K3M-9QX2): nadie puede enumerar los envios
    de otros clientes probando numeros consecutivos."""
    for _ in range(20):
        bloque = lambda: ''.join(secrets.choice(ALFABETO_GUIA) for _ in range(4))  # noqa: E731
        codigo = f'CE-{bloque()}-{bloque()}'
        if not conexion.session.query(PedidoModel.id).filter_by(codigoGuia=codigo).first():
            return codigo
    raise ErrorNegocio('No se pudo generar un codigo de guia unico, intenta de nuevo', 500)


def buscarTarifa(zonaOrigenId, zonaDestinoId, servicio='estandar'):
    if not zonaOrigenId or not zonaDestinoId:
        return None
    return conexion.session.query(TarifaZonaModel).filter_by(
        zonaOrigenId=zonaOrigenId, zonaDestinoId=zonaDestinoId, tipoServicio=servicio, activo=True
    ).first()


def efectivoEsperadoDeRuta(rutaId):
    """Todo el efectivo que el repartidor cobro en la ruta: fletes contra
    entrega Y recaudos de mercaderia (que luego se pagan al remitente)."""
    fletes = conexion.session.query(func.coalesce(func.sum(PagoModel.monto), 0)).filter(
        PagoModel.rutaId == rutaId, PagoModel.metodo == 'efectivo', PagoModel.estadoPago == 'pagado'
    ).scalar()
    recaudos = conexion.session.query(func.coalesce(func.sum(RecaudoModel.monto), 0)).filter(
        RecaudoModel.rutaId == rutaId, RecaudoModel.metodo == 'efectivo'
    ).scalar()
    return aDecimal(fletes) + aDecimal(recaudos)


def rutasSinLiquidar(repartidorId):
    return conexion.session.query(RutaModel).outerjoin(
        LiquidacionRutaModel, LiquidacionRutaModel.rutaId == RutaModel.id
    ).filter(
        RutaModel.repartidorId == repartidorId,
        RutaModel.estado == 'completada',
        LiquidacionRutaModel.id.is_(None),
    ).count()


def rutaActivaDe(repartidorId):
    return conexion.session.query(RutaModel).filter(
        RutaModel.repartidorId == repartidorId,
        RutaModel.estado.in_(['planificada', 'en_curso']),
    ).order_by(RutaModel.fecha.desc()).first()


def validarRepartidorOperativo(repartidor):
    if not repartidor.disponible:
        raise ErrorNegocio('Este repartidor esta marcado como no disponible. Cambia la disponibilidad antes de tomar pedidos', 409)
    if not repartidor.zonaId:
        raise ErrorNegocio('Este repartidor no tiene una zona asignada. Pide a un administrador que la configure', 409)
    usuario = conexion.session.get(UsuarioModel, repartidor.usuarioId)
    if not usuario or not usuario.activo:
        raise ErrorNegocio('El usuario de este repartidor esta inactivo', 409)
    if rutasSinLiquidar(repartidor.id) > current_app.config['MAX_RUTAS_SIN_LIQUIDAR']:
        raise ErrorNegocio('Este repartidor tiene rutas completadas sin liquidar en caja. '
                           'Debe entregar el efectivo cobrado antes de tomar mas pedidos', 409)


def crearRutaPara(repartidor):
    ruta = RutaModel(zonaId=repartidor.zonaId, repartidorId=repartidor.id, estado='planificada')
    conexion.session.add(ruta)
    conexion.session.flush()  # obtiene el id SIN hacer commit (no suelta los bloqueos)
    ruta.codigo = f'RTA{ruta.id:05d}'
    return ruta


def asignarPedidoARuta(pedidoId, repartidor, ruta, comentario):
    """Logica comun de /pedido/<id>/tomar y /ruta/<id>/agregar-pedido. El
    llamador ya bloqueo la fila del repartidor; aqui se bloquea la del pedido
    hasta el commit, para que dos repartidores no tomen el mismo paquete."""
    pedido = obtener(PedidoModel, pedidoId, 'Pedido no existe', bloquear=True)

    if pedido.repartidorId is not None or pedido.rutaId is not None:
        raise ErrorNegocio('Este pedido ya fue tomado por otro repartidor', 409)
    if pedido.estadoId != idEstado(estadoListoParaReparto(pedido)):
        if esEnvioLocal(pedido):
            raise ErrorNegocio('Este pedido todavia no ha ingresado fisicamente al almacen', 409)
        raise ErrorNegocio('Este envio todavia no llega a la agencia de destino', 409)

    if faltaPagoPrepagado(pedido):
        raise ErrorNegocio(f'El envio {pedido.codigoGuia} es prepagado y no tiene el pago confirmado: '
                           'no puede salir a reparto', 409)
    if (pedido.intentosEntrega or 0) >= current_app.config['MAX_INTENTOS_ENTREGA']:
        raise ErrorNegocio(f'El envio {pedido.codigoGuia} ya agoto sus intentos de entrega: debe devolverse '
                           'al remitente', 409)

    # El repartidor debe ser de la zona de la agencia donde esta el paquete
    almacen = conexion.session.get(AlmacenModel, agenciaReparto(pedido))
    if not almacen or almacen.zonaId != repartidor.zonaId or (ruta and ruta.zonaId != repartidor.zonaId):
        raise ErrorNegocio('Este pedido pertenece a una zona distinta a la del repartidor', 400)

    if ruta is None:
        ruta = crearRutaPara(repartidor)

    enRuta = conexion.session.query(PedidoModel).filter(
        PedidoModel.rutaId == ruta.id, PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS))
    ).count()
    if enRuta >= current_app.config['MAX_PEDIDOS_POR_RUTA']:
        raise ErrorNegocio(f'La ruta ya tiene el maximo de {current_app.config["MAX_PEDIDOS_POR_RUTA"]} pedidos activos', 409)

    estadoAsignado = idEstado('asignado')
    pedido.repartidorId = repartidor.id
    pedido.rutaId = ruta.id
    pedido.estadoId = estadoAsignado
    registrarHistorial(pedido.id, estadoAsignado, comentario=f'{comentario} (ruta {ruta.codigo})')
    return pedido, ruta


def totalACobrar(pedido):
    """Lo que el repartidor debe cobrar en la puerta: el flete (si es contra
    entrega y no esta pagado) mas el recaudo del producto (si no se cobro)."""
    total = aDecimal(0)
    if pedido.modalidadPago == 'contra_entrega' and not conexion.session.query(PagoModel.id).filter_by(
            pedidoId=pedido.id).first():
        total += aDecimal(pedido.monto)
    if aDecimal(pedido.montoRecaudo) > 0 and not conexion.session.query(RecaudoModel.id).filter_by(
            pedidoId=pedido.id).first():
        total += aDecimal(pedido.montoRecaudo)
    return total


def devolverAAgencia(pedido, ruta, maximoIntentos):
    """Cierre de ruta: un envio no entregado vuelve a la agencia. Si aun le
    quedan intentos queda listo para reintentar; si no (o lo rechazaron),
    pasa a devolucion al remitente. Devuelve el estado en que queda."""
    agotado = (pedido.intentosEntrega or 0) >= maximoIntentos or pedido.motivoNoEntrega == 'rechazado'
    destino = 'por_devolver' if agotado else estadoListoParaReparto(pedido)
    pedido.repartidorId = None
    pedido.rutaId = None
    pedido.estadoId = idEstado(destino)
    motivo = ('rechazado por el destinatario' if pedido.motivoNoEntrega == 'rechazado'
              else f'{pedido.intentosEntrega} intento(s) fallido(s)')
    registrarHistorial(pedido.id, pedido.estadoId, comentario=(
        f'Volvio a la agencia al cerrar la ruta {ruta.codigo}: ' +
        (f'{motivo}, se devolvera al remitente' if agotado else 'queda listo para reintentar la entrega')))
    return destino


def construirDetallePedido(pedido):
    """Lo que necesita el repartidor para entregar. Solo datos minimos del
    destinatario (sin DNI ni email: minimizacion de datos personales)."""
    cliente = conexion.session.get(ClienteModel, pedido.clienteId)
    direccion = conexion.session.get(DireccionModel, pedido.direccionEntregaId)
    return {
        'pedidoId': pedido.id,
        'codigoGuia': pedido.codigoGuia,
        'estado': nombreEstado(pedido.estadoId),
        'prioridad': pedido.prioridad,
        'monto': str(pedido.monto),
        'modalidadPago': pedido.modalidadPago,
        'montoRecaudo': str(aDecimal(pedido.montoRecaudo)),
        'totalACobrar': str(totalACobrar(pedido)),
        'tipoServicio': pedido.tipoServicio,
        'requierePin': bool(pedido.requierePin),
        'bultos': conexion.session.query(BultoModel.id).filter_by(pedidoId=pedido.id).count(),
        'intentosEntrega': pedido.intentosEntrega,
        'descripcionProducto': pedido.descripcionProducto,
        'notas': pedido.notas,
        'cliente': {
            'nombre': cliente.nombre if cliente else None,
            'telefono': cliente.telefono if cliente else None,
        },
        'direccionEntrega': {
            'etiqueta': direccion.etiqueta if direccion else None,
            'calle': direccion.calle if direccion else None,
            'referencia': direccion.referencia if direccion else None,
            'latitud': direccion.latitud if direccion else None,
            'longitud': direccion.longitud if direccion else None,
        },
    }


def construirDetalleRuta(ruta):
    pedidos = conexion.session.query(PedidoModel).filter_by(rutaId=ruta.id).all()
    return {
        'rutaId': ruta.id,
        'codigo': ruta.codigo,
        'estado': ruta.estado,
        'fecha': ruta.fecha.isoformat() if ruta.fecha else None,
        'zonaId': ruta.zonaId,
        'repartidorId': ruta.repartidorId,
        'totalPedidos': len(pedidos),
        'efectivoCobrado': str(efectivoEsperadoDeRuta(ruta.id)),
        'pedidos': [construirDetallePedido(p) for p in pedidos],
    }

def bultosAdmitidosDeRecojo(recojoId):
    """Bultos ya admitidos en agencia de los envios que salieron de un recojo
    (un envio pre-registrado sin bultos cuenta como 1)."""
    pedidos = conexion.session.query(PedidoModel.id).filter_by(solicitudRecojoId=recojoId).all()
    total = 0
    for (pedidoId,) in pedidos:
        total += conexion.session.query(BultoModel.id).filter_by(pedidoId=pedidoId).count() or 1
    return total


def exigirZonaActiva(zonaId):
    if zonaId is None:
        return None
    zona = obtener(ZonaModel, zonaId, 'La zona indicada no existe')
    if not zona.activo:
        raise ErrorValidacion('La zona indicada esta desactivada')
    return zona
