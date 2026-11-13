"""Red de agencias: clasificacion, despacho y recepcion (pasos 6, 7 y 8).

Flujo:
  1. En la agencia de origen se abre un manifiesto hacia una agencia destino
     y se ESCANEAN los bultos (lector de codigo/QR o digitando el codigo).
  2. Al despachar, el manifiesto se cierra (no se agrega ni se quita nada),
     los envios pasan a "en_transito" y se registra transportista y precinto.
  3. En destino se escanea cada bulto al bajarlo del vehiculo. Cuando llegan
     todos los bultos de un envio, este pasa a "en_agencia_destino" y queda
     disponible para los repartidores de esa zona.
  4. Al cerrar la recepcion, cada bulto no escaneado genera una incidencia
     de tipo "faltante" automaticamente. Si el bulto aparece despues (vino en
     otro vehiculo), se escanea igual sobre el manifiesto cerrado: el envio
     se completa y la incidencia se resuelve sola.

Devoluciones: un envio "por_devolver" que esta en la agencia de reparto
viaja de regreso a su agencia de origen con el mismo mecanismo (manifiesto
destino = agencia de origen). Al llegar completo queda "por_devolver" en el
origen, listo para entregarlo al remitente.
"""
from flask import Blueprint, request
from sqlalchemy import and_, func, or_

from app.extensions import conexion
from app.models import (
    AlmacenModel, BultoModel, ClienteModel, IncidenciaModel, ManifiestoBultoModel, ManifiestoModel,
    PedidoModel, EventoBultoModel, UsuarioModel,
)
from app.admision import registrarEvento
from app.core.seguridad import requiereRol, auditar, usuarioActualId, ROLES_STAFF
from app.core.validacion import ErrorNegocio, ErrorValidacion, cuerpoJson, entero, texto
from app.reglas import MANIFIESTOS_ACTIVOS, ahoraUtc
from app.servicios import (
    agenciaDelUsuario, agenciaReparto, esEnvioLocal, exigirAccesoPedido, exigirMiAgencia, faltaPagoPrepagado, idEstado,
    nombreEstado, obtener, registrarHistorial,
)

# Manifiestos sobre los que todavia se escanea en destino: en transito, o
# cerrados con faltantes (el bulto que llega tarde se recibe igual)
RECEPCION_ABIERTA = ('en_transito', 'recibido_con_diferencias')


def aplicarPlazo(incidencia):
    from app.routes.incidencias import aplicarPlazo as plazo  # evita import circular de blueprints
    plazo(incidencia)

bp = Blueprint('manifiestos', __name__)


# ------------------------------------------------------------ helpers ----

def _isoUtc(fecha):
    """Fechas que el codigo guarda en UTC (ahoraUtc): se envian con 'Z' para
    que el navegador las muestre en hora local. Las que pone la base con
    now() (fechaCreacion) ya estan en hora local del servidor MySQL."""
    return fecha.isoformat() + 'Z' if fecha else None


def _nombreAgencia(agenciaId):
    agencia = conexion.session.get(AlmacenModel, agenciaId)
    return agencia.nombre if agencia else None


def _bultoPorCodigo(data):
    codigo = texto(data, 'codigo', requerido=True, maximo=40)
    codigo = codigo.strip().upper()
    bulto = conexion.session.query(BultoModel).filter_by(codigo=codigo).first()
    if not bulto:
        raise ErrorNegocio(f'No existe ningun bulto con el codigo {codigo}', 404)
    return bulto


def _resumen(manifiesto):
    filas = conexion.session.query(ManifiestoBultoModel).filter_by(manifiestoId=manifiesto.id).all()
    return {
        'id': manifiesto.id,
        'codigo': manifiesto.codigo,
        'estado': manifiesto.estado,
        'agenciaOrigen': {'id': manifiesto.agenciaOrigenId, 'nombre': _nombreAgencia(manifiesto.agenciaOrigenId)},
        'agenciaDestino': {'id': manifiesto.agenciaDestinoId, 'nombre': _nombreAgencia(manifiesto.agenciaDestinoId)},
        'transportista': manifiesto.transportista,
        'placa': manifiesto.placa,
        'precinto': manifiesto.precinto,
        'observaciones': manifiesto.observaciones,
        'fechaCreacion': manifiesto.fechaCreacion.isoformat() if manifiesto.fechaCreacion else None,
        'fechaDespacho': _isoUtc(manifiesto.fechaDespacho),
        'fechaRecepcion': _isoUtc(manifiesto.fechaRecepcion),
        'totalBultos': len(filas),
        'bultosRecibidos': sum(1 for f in filas if f.recibido),
        'totalEnvios': len({f.pedidoId for f in filas}),
    }


def _detalle(manifiesto):
    filas = conexion.session.query(ManifiestoBultoModel, BultoModel, PedidoModel, ClienteModel) \
        .join(BultoModel, ManifiestoBultoModel.bultoId == BultoModel.id) \
        .join(PedidoModel, ManifiestoBultoModel.pedidoId == PedidoModel.id) \
        .join(ClienteModel, PedidoModel.clienteId == ClienteModel.id) \
        .filter(ManifiestoBultoModel.manifiestoId == manifiesto.id) \
        .order_by(PedidoModel.codigoGuia, BultoModel.numero).all()
    totales = dict(conexion.session.query(BultoModel.pedidoId, func.count(BultoModel.id))
                   .filter(BultoModel.pedidoId.in_({p.id for _, _, p, _ in filas} or {-1}))
                   .group_by(BultoModel.pedidoId).all())
    return {
        **_resumen(manifiesto),
        'bultos': [{
            'bultoId': b.id,
            'codigo': b.codigo,
            'numero': b.numero,
            'totalDelEnvio': totales.get(p.id, 1),
            'pesoFacturableKg': str(b.pesoFacturableKg),
            'pedidoId': p.id,
            'codigoGuia': p.codigoGuia,
            'destinatario': c.nombre,
            'estadoEnvio': nombreEstado(p.estadoId),
            'recibido': mb.recibido,
            'fechaRecepcion': _isoUtc(mb.fechaRecepcion),
        } for mb, b, p, c in filas],
    }


def _exigirAccesoManifiesto(manifiesto):
    propia = agenciaDelUsuario()
    if propia and propia not in (manifiesto.agenciaOrigenId, manifiesto.agenciaDestinoId):
        raise ErrorNegocio('Manifiesto no existe', 404)


# ------------------------------------------------------- consultas ----

@bp.route('/despachos/pendientes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def pendientesDeDespacho():
    """Clasificacion: envios en la agencia de origen que viajan a otra
    agencia y aun no estan en un manifiesto, agrupados por destino."""
    origen = request.args.get('agencia_id', type=int) or agenciaDelUsuario()
    if not origen:
        raise ErrorValidacion('Indica la agencia de origen (agencia_id)')
    exigirMiAgencia(origen)

    enManifiestoActivo = conexion.session.query(ManifiestoBultoModel.pedidoId) \
        .join(ManifiestoModel, ManifiestoBultoModel.manifiestoId == ManifiestoModel.id) \
        .filter(ManifiestoModel.estado.in_(MANIFIESTOS_ACTIVOS), ManifiestoBultoModel.recibido.is_(False))
    pedidos = conexion.session.query(PedidoModel).filter(
        PedidoModel.id.notin_(enManifiestoActivo),
        or_(
            # Ida: admitidos aqui que se reparten en otra agencia
            and_(PedidoModel.almacenId == origen, PedidoModel.estadoId == idEstado('en_almacen'),
                 PedidoModel.agenciaDestinoId.isnot(None), PedidoModel.agenciaDestinoId != origen),
            # Vuelta: devoluciones que estan aqui y deben regresar a su origen
            and_(PedidoModel.agenciaDestinoId == origen, PedidoModel.almacenId != origen,
                 PedidoModel.estadoId == idEstado('por_devolver'), PedidoModel.retornoAlOrigen.is_(False)),
        ),
    ).all()

    grupos = {}
    for p in pedidos:
        esRetorno = p.agenciaDestinoId == origen
        destinoId = p.almacenId if esRetorno else p.agenciaDestinoId
        g = grupos.setdefault(destinoId, {
            'agenciaDestino': {'id': destinoId, 'nombre': _nombreAgencia(destinoId)},
            'envios': 0, 'bultos': 0, 'pendientesDePago': 0, 'devoluciones': 0,
        })
        g['envios'] += 1
        g['bultos'] += conexion.session.query(BultoModel.id).filter_by(pedidoId=p.id).count()
        if esRetorno:
            g['devoluciones'] += 1
        elif faltaPagoPrepagado(p):
            g['pendientesDePago'] += 1
    return {'content': {'agenciaOrigenId': origen, 'destinos': list(grupos.values())}}, 200


@bp.route('/manifiestos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarManifiestos():
    query = conexion.session.query(ManifiestoModel)
    propia = agenciaDelUsuario()
    tipo = request.args.get('tipo')  # salida | llegada
    if propia:
        if tipo == 'salida':
            query = query.filter(ManifiestoModel.agenciaOrigenId == propia)
        elif tipo == 'llegada':
            query = query.filter(ManifiestoModel.agenciaDestinoId == propia)
        else:
            query = query.filter((ManifiestoModel.agenciaOrigenId == propia) |
                                 (ManifiestoModel.agenciaDestinoId == propia))
    estado = request.args.get('estado')
    if estado:
        query = query.filter(ManifiestoModel.estado.in_(estado.split(',')))
    manifiestos = query.order_by(ManifiestoModel.id.desc()).limit(200).all()
    return {'content': [_resumen(m) for m in manifiestos]}, 200


@bp.route('/manifiesto/<int:id>', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def obtenerManifiesto(id):
    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe')
    _exigirAccesoManifiesto(manifiesto)
    return {'content': _detalle(manifiesto)}, 200


# ------------------------------------------------------- despacho ----

def _esRetorno(pedido):
    """Devolucion que todavia esta en la agencia de reparto y debe volver al origen."""
    return (pedido.estadoId == idEstado('por_devolver') and not pedido.retornoAlOrigen
            and not esEnvioLocal(pedido))


def _validarParaManifiesto(pedido, manifiesto, bulto):
    """Ida: en_almacen en el origen, hacia su agencia de reparto, y pagado si
    es prepagado. Vuelta: por_devolver en la agencia de reparto, hacia el origen."""
    if _esRetorno(pedido):
        if agenciaReparto(pedido) != manifiesto.agenciaOrigenId:
            raise ErrorNegocio(f'La devolucion {pedido.codigoGuia} no esta en esta agencia', 409)
        if pedido.almacenId != manifiesto.agenciaDestinoId:
            raise ErrorNegocio(f'El bulto {bulto.codigo} es una devolucion que vuelve a '
                               f'{_nombreAgencia(pedido.almacenId)}, no a '
                               f'{_nombreAgencia(manifiesto.agenciaDestinoId)}: separalo', 409)
        return
    if pedido.estadoId != idEstado('en_almacen') or pedido.almacenId != manifiesto.agenciaOrigenId:
        raise ErrorNegocio(f'El envio {pedido.codigoGuia} no esta en esta agencia listo para despacho '
                           f'(estado: {nombreEstado(pedido.estadoId)})', 409)
    if agenciaReparto(pedido) != manifiesto.agenciaDestinoId:
        raise ErrorNegocio(f'El bulto {bulto.codigo} va a {_nombreAgencia(agenciaReparto(pedido))}, '
                           f'no a {_nombreAgencia(manifiesto.agenciaDestinoId)}: separalo', 409)
    if faltaPagoPrepagado(pedido):
        raise ErrorNegocio(f'El envio {pedido.codigoGuia} es prepagado y no tiene el pago confirmado: '
                           'no puede salir de la agencia', 409)


@bp.route('/manifiesto', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearManifiesto():
    data = cuerpoJson()
    propia = agenciaDelUsuario()
    origen = entero(data, 'agenciaOrigenId', requerido=not propia)
    if propia:
        if origen and origen != propia:
            raise ErrorNegocio('Solo puedes abrir manifiestos que salen de tu agencia', 403)
        origen = propia
    destino = entero(data, 'agenciaDestinoId', requerido=True)
    if origen == destino:
        raise ErrorValidacion('La agencia de destino debe ser distinta a la de origen')
    for agenciaId in (origen, destino):
        agencia = obtener(AlmacenModel, agenciaId, 'La agencia no existe')
        if not agencia.activo:
            raise ErrorValidacion(f'La agencia {agencia.nombre} esta desactivada')

    manifiesto = ManifiestoModel(agenciaOrigenId=origen, agenciaDestinoId=destino, estado='abierto',
                                 creadoPorId=usuarioActualId())
    conexion.session.add(manifiesto)
    conexion.session.flush()
    manifiesto.codigo = f'MF{manifiesto.id:06d}'
    conexion.session.commit()
    return {'message': f'Manifiesto {manifiesto.codigo} abierto', 'content': _detalle(manifiesto)}, 201


@bp.route('/manifiesto/<int:id>/bultos', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def agregarBulto(id):
    """Escaneo en origen: agrega un bulto al manifiesto abierto."""
    data = cuerpoJson()
    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe', bloquear=True)
    exigirMiAgencia(manifiesto.agenciaOrigenId, 'Solo la agencia de origen arma este manifiesto')
    if manifiesto.estado != 'abierto':
        raise ErrorNegocio('El manifiesto ya fue despachado: no se le pueden agregar bultos', 409)

    bulto = _bultoPorCodigo(data)
    pedido = obtener(PedidoModel, bulto.pedidoId, 'Pedido no existe', bloquear=True)
    _validarParaManifiesto(pedido, manifiesto, bulto)

    enOtro = conexion.session.query(ManifiestoModel.codigo) \
        .join(ManifiestoBultoModel, ManifiestoBultoModel.manifiestoId == ManifiestoModel.id) \
        .filter(ManifiestoBultoModel.bultoId == bulto.id, ManifiestoModel.estado.in_(MANIFIESTOS_ACTIVOS),
                ManifiestoBultoModel.recibido.is_(False)).first()
    if enOtro:
        if enOtro.codigo == manifiesto.codigo:
            return {'message': f'El bulto {bulto.codigo} ya estaba en este manifiesto',
                    'content': _detalle(manifiesto)}, 200
        raise ErrorNegocio(f'El bulto {bulto.codigo} ya esta en el manifiesto {enOtro.codigo}', 409)

    conexion.session.add(ManifiestoBultoModel(manifiestoId=id, bultoId=bulto.id, pedidoId=pedido.id))
    registrarEvento(bulto, 'manifestado', agenciaId=manifiesto.agenciaOrigenId, manifiestoId=id)
    conexion.session.commit()
    total = conexion.session.query(BultoModel.id).filter_by(pedidoId=pedido.id).count()
    return {'message': f'Bulto {bulto.numero} de {total} del envio {pedido.codigoGuia} agregado',
            'content': _detalle(manifiesto)}, 201


@bp.route('/manifiesto/<int:id>/bultos/<int:bultoId>', methods=['DELETE'])
@requiereRol(*ROLES_STAFF)
def quitarBulto(id, bultoId):
    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe', bloquear=True)
    exigirMiAgencia(manifiesto.agenciaOrigenId)
    if manifiesto.estado != 'abierto':
        raise ErrorNegocio('El manifiesto ya fue despachado: no se pueden quitar bultos', 409)
    fila = conexion.session.query(ManifiestoBultoModel).filter_by(manifiestoId=id, bultoId=bultoId).first()
    if not fila:
        raise ErrorNegocio('Ese bulto no esta en este manifiesto', 404)
    conexion.session.delete(fila)
    registrarEvento(conexion.session.get(BultoModel, bultoId), 'retirado_de_manifiesto',
                    agenciaId=manifiesto.agenciaOrigenId, manifiestoId=id)
    conexion.session.commit()
    return {'message': 'Bulto retirado del manifiesto', 'content': _detalle(manifiesto)}, 200


@bp.route('/manifiesto/<int:id>/despachar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def despacharManifiesto(id):
    data = cuerpoJson()
    transportista = texto(data, 'transportista', requerido=True, maximo=100, minimo=3)
    placa = texto(data, 'placa', requerido=True, maximo=15, minimo=5).upper()
    precinto = texto(data, 'precinto', maximo=40)

    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe', bloquear=True)
    exigirMiAgencia(manifiesto.agenciaOrigenId, 'Solo la agencia de origen despacha este manifiesto')
    if manifiesto.estado != 'abierto':
        raise ErrorNegocio('Este manifiesto ya fue despachado', 409)

    filas = conexion.session.query(ManifiestoBultoModel).filter_by(manifiestoId=id).all()
    if not filas:
        raise ErrorNegocio('El manifiesto esta vacio: escanea al menos un bulto', 409)

    porPedido = {}
    for f in filas:
        porPedido.setdefault(f.pedidoId, set()).add(f.bultoId)

    enTransito = idEstado('en_transito')
    enAlmacen = idEstado('en_almacen')
    destino = _nombreAgencia(manifiesto.agenciaDestinoId)
    for pedidoId, bultosIncluidos in porPedido.items():
        pedido = obtener(PedidoModel, pedidoId, 'Pedido no existe', bloquear=True)
        todos = {b.id for b in conexion.session.query(BultoModel.id).filter_by(pedidoId=pedidoId).all()}
        if todos - bultosIncluidos:
            # Un envio viaja completo: si una caja se queda, el destinatario
            # recibiria la mitad y nadie sabria donde esta el resto.
            raise ErrorNegocio(f'Faltan bultos del envio {pedido.codigoGuia}: escaneaste '
                               f'{len(bultosIncluidos)} de {len(todos)}. Un envio debe viajar completo', 409)
        if _esRetorno(pedido):
            pedido.retornoAlOrigen = True
            comentario = f'Devolucion: regresa a {destino} en el manifiesto {manifiesto.codigo}'
        elif pedido.estadoId != enAlmacen:
            raise ErrorNegocio(f'El envio {pedido.codigoGuia} ya no esta en almacen '
                               f'({nombreEstado(pedido.estadoId)}): retiralo del manifiesto', 409)
        elif faltaPagoPrepagado(pedido):
            raise ErrorNegocio(f'El envio {pedido.codigoGuia} es prepagado y no tiene el pago confirmado', 409)
        else:
            comentario = f'Despachado hacia {destino} en el manifiesto {manifiesto.codigo}'
        pedido.estadoId = enTransito
        registrarHistorial(pedidoId, enTransito, comentario=comentario)

    for f in filas:
        registrarEvento(conexion.session.get(BultoModel, f.bultoId), 'despachado',
                        agenciaId=manifiesto.agenciaOrigenId, manifiestoId=id)

    manifiesto.estado = 'en_transito'
    manifiesto.transportista = transportista
    manifiesto.placa = placa
    manifiesto.precinto = precinto
    manifiesto.despachadoPorId = usuarioActualId()
    manifiesto.fechaDespacho = ahoraUtc()
    auditar('manifiesto_despachado', 'manifiesto', id, {
        'bultos': len(filas), 'envios': len(porPedido), 'placa': placa, 'precinto': precinto})
    conexion.session.commit()
    return {'message': f'Manifiesto {manifiesto.codigo} despachado: {len(porPedido)} envio(s), {len(filas)} bulto(s)',
            'content': _detalle(manifiesto)}, 200


# ------------------------------------------------------- recepcion ----

@bp.route('/manifiesto/<int:id>/recibir', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def recibirBulto(id):
    """Escaneo en destino. Idempotente: escanear dos veces el mismo bulto no
    falla (pasa en la practica con lectores de codigo). Sobre un manifiesto
    ya cerrado con faltantes registra la llegada tardia de esos bultos."""
    data = cuerpoJson()
    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe', bloquear=True)
    exigirMiAgencia(manifiesto.agenciaDestinoId, 'Este manifiesto se recibe en otra agencia')
    if manifiesto.estado not in RECEPCION_ABIERTA:
        raise ErrorNegocio('Este manifiesto no esta en transito', 409)
    tarde = manifiesto.estado == 'recibido_con_diferencias'

    bulto = _bultoPorCodigo(data)
    fila = conexion.session.query(ManifiestoBultoModel).filter_by(manifiestoId=id, bultoId=bulto.id) \
        .with_for_update().first()
    if not fila:
        # Sobrante: llego algo que no figura en el manifiesto. No se recibe
        # aqui; se aparta y se reporta.
        raise ErrorNegocio(f'SOBRANTE: el bulto {bulto.codigo} no figura en el manifiesto {manifiesto.codigo}. '
                           'Apartalo y reportalo', 409)
    if fila.recibido:
        return {'message': f'El bulto {bulto.codigo} ya estaba recibido', 'content': _detalle(manifiesto)}, 200

    fila.recibido = True
    fila.fechaRecepcion = ahoraUtc()
    fila.recibidoPorId = usuarioActualId()
    registrarEvento(bulto, 'recibido_tarde' if tarde else 'recibido_en_destino',
                    agenciaId=manifiesto.agenciaDestinoId, manifiestoId=id)
    conexion.session.flush()

    mensaje = f'Bulto {bulto.codigo} recibido' + (' (llego despues del cierre)' if tarde else '')
    pendientes = conexion.session.query(ManifiestoBultoModel.id).filter_by(
        manifiestoId=id, pedidoId=bulto.pedidoId, recibido=False).count()
    if pendientes == 0:
        pedido = obtener(PedidoModel, bulto.pedidoId, 'Pedido no existe', bloquear=True)
        lugar = f'{_nombreAgencia(manifiesto.agenciaDestinoId)} (manifiesto {manifiesto.codigo})'
        if pedido.estadoId == idEstado('en_transito'):
            if pedido.retornoAlOrigen:
                llegada = idEstado('por_devolver')
                registrarHistorial(pedido.id, llegada, comentario=f'Devolucion recibida completa en {lugar}: '
                                   'lista para entregar al remitente')
                mensaje += f'. Devolucion {pedido.codigoGuia} completa: entregala al remitente'
            else:
                llegada = idEstado('en_agencia_destino')
                registrarHistorial(pedido.id, llegada, comentario=f'Recibido completo en {lugar}')
                mensaje += f'. Envio {pedido.codigoGuia} completo: listo para reparto'
            pedido.estadoId = llegada
        if tarde:
            _resolverFaltantes(pedido, manifiesto)
    conexion.session.commit()
    return {'message': mensaje, 'content': _detalle(manifiesto)}, 200


def _resolverFaltantes(pedido, manifiesto):
    """Llegaron todos los bultos que faltaban: la incidencia se cierra sola."""
    abiertas = conexion.session.query(IncidenciaModel).filter(
        IncidenciaModel.pedidoId == pedido.id, IncidenciaModel.tipo == 'faltante',
        IncidenciaModel.estado != 'resuelta').all()
    for incidencia in abiertas:
        incidencia.estado = 'resuelta'
        incidencia.resolucion = f'Los bultos faltantes llegaron despues del cierre del manifiesto {manifiesto.codigo}'
        incidencia.fechaResolucion = func.now()
    if abiertas:
        auditar('faltante_regularizado', 'manifiesto', manifiesto.id, {
            'pedido': pedido.codigoGuia, 'incidencias': [i.id for i in abiertas]})


@bp.route('/manifiesto/<int:id>/cerrar-recepcion', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cerrarRecepcion(id):
    data = cuerpoJson()
    observaciones = texto(data, 'observaciones', maximo=1000)
    manifiesto = obtener(ManifiestoModel, id, 'Manifiesto no existe', bloquear=True)
    exigirMiAgencia(manifiesto.agenciaDestinoId, 'Este manifiesto se recibe en otra agencia')
    if manifiesto.estado != 'en_transito':
        raise ErrorNegocio('Este manifiesto no esta en transito', 409)

    faltantes = conexion.session.query(ManifiestoBultoModel, BultoModel) \
        .join(BultoModel, ManifiestoBultoModel.bultoId == BultoModel.id) \
        .filter(ManifiestoBultoModel.manifiestoId == id, ManifiestoBultoModel.recibido.is_(False)).all()
    if faltantes and not observaciones:
        raise ErrorValidacion(f'Faltan {len(faltantes)} bulto(s). Escribe una observacion antes de cerrar '
                              '(ej. "el transportista indica que se quedaron en origen")')

    porPedido = {}
    for fila, bulto in faltantes:
        porPedido.setdefault(fila.pedidoId, []).append(bulto)
        registrarEvento(bulto, 'faltante', agenciaId=manifiesto.agenciaDestinoId, manifiestoId=id)
    for pedidoId, bultos in porPedido.items():
        codigos = ', '.join(b.codigo for b in bultos)
        incidencia = IncidenciaModel(
            pedidoId=pedidoId, usuarioId=usuarioActualId(), tipo='faltante',
            descripcion=f'No llegaron en el manifiesto {manifiesto.codigo}: {codigos}. '
                        f'Observacion de recepcion: {observaciones}')
        aplicarPlazo(incidencia)
        conexion.session.add(incidencia)
        conexion.session.flush()
        pedido = conexion.session.get(PedidoModel, pedidoId)
        registrarHistorial(pedidoId, pedido.estadoId,
                           comentario=f'Incidencia #{incidencia.id}: faltan {len(bultos)} bulto(s) en destino')

    manifiesto.estado = 'recibido_con_diferencias' if faltantes else 'recibido'
    manifiesto.observaciones = observaciones
    manifiesto.recibidoPorId = usuarioActualId()
    manifiesto.fechaRecepcion = ahoraUtc()
    auditar('manifiesto_recibido', 'manifiesto', id, {'faltantes': [b.codigo for _, b in faltantes]})
    conexion.session.commit()
    texto_ = 'Recepcion cerrada sin diferencias' if not faltantes else \
        f'Recepcion cerrada con {len(faltantes)} bulto(s) faltante(s): se registraron {len(porPedido)} incidencia(s)'
    return {'message': texto_, 'content': _detalle(manifiesto)}, 200


# ------------------------------------------------------- trazabilidad ----

@bp.route('/pedido/<int:id>/trazabilidad', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def trazabilidadPedido(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    filas = conexion.session.query(EventoBultoModel, BultoModel, UsuarioModel) \
        .join(BultoModel, EventoBultoModel.bultoId == BultoModel.id) \
        .outerjoin(UsuarioModel, EventoBultoModel.usuarioId == UsuarioModel.id) \
        .filter(EventoBultoModel.pedidoId == id) \
        .order_by(EventoBultoModel.fecha, EventoBultoModel.id).all()
    manifiestos = {m.id: m.codigo for m in conexion.session.query(ManifiestoModel).filter(
        ManifiestoModel.id.in_({e.manifiestoId for e, _, _ in filas if e.manifiestoId} or {-1})).all()}
    return {'content': [{
        'bulto': b.codigo,
        'tipo': e.tipo,
        'agencia': _nombreAgencia(e.agenciaId) if e.agenciaId else None,
        'manifiesto': manifiestos.get(e.manifiestoId),
        'usuario': u.nombreUsuario if u else None,
        'fecha': e.fecha.isoformat() if e.fecha else None,
    } for e, b, u in filas]}, 200

