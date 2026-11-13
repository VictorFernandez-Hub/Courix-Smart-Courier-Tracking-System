"""Rutas de reparto."""

from flask import Blueprint, current_app, request

from app.extensions import conexion
from app.finanzas import generarCargoDevolucion
from app.core.seguridad import usuarioActualId
from app.models import (
    RepartidorModel, RutaModel, PedidoModel, LiquidacionRutaModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, rolActual, esStaff,
)
from app.core.validacion import (
    cuerpoJson, entero,
)
from app.reglas import (
    ESTADOS_PEDIDO_PENDIENTES_EN_RUTA,
)
from app.schemas import (
    RutaDto,
)
from app.servicios import (
    agenciaDelUsuario, asignarPedidoARuta, construirDetalleRuta, devolverAAgencia, exigirAccesoRuta, filtrarRutasPorAgencia, crearRutaPara, efectivoEsperadoDeRuta, esDuenioDeLaRuta, exigirMiRepartidor, idEstado, idsEstados, miRepartidor, obtener, registrarHistorial, rutaActivaDe, validarRepartidorOperativo,
    estadoListoParaReparto,
)


bp = Blueprint('rutas', __name__)


@bp.route('/ruta', methods=['POST'])
@requiereRol('admin', 'repartidor')
def crearRuta():
    data = cuerpoJson()
    repartidorId = entero(data, 'repartidorId', requerido=True)

    if rolActual() != 'admin':
        perfil = miRepartidor()
        if not perfil or perfil.id != repartidorId:
            return {'message': 'Solo puedes crear una ruta para ti mismo'}, 403

    repartidor = obtener(RepartidorModel, repartidorId, 'Repartidor no existe', bloquear=True)
    validarRepartidorOperativo(repartidor)

    existente = rutaActivaDe(repartidorId)
    if existente:
        return {'message': f'Este repartidor ya tiene una ruta activa ({existente.codigo})'}, 409

    ruta = crearRutaPara(repartidor)
    conexion.session.commit()
    return {'message': f'Ruta {ruta.codigo} creada', 'content': construirDetalleRuta(ruta)}, 201


@bp.route('/ruta/<int:id>/agregar-pedido', methods=['POST'])
@requiereRol('admin', 'repartidor')
def agregarPedidoARuta(id):
    data = cuerpoJson()
    pedidoId = entero(data, 'pedidoId', requerido=True)

    ruta = obtener(RutaModel, id, 'Ruta no existe')
    if not esDuenioDeLaRuta(ruta):
        return {'message': 'No puedes modificar la ruta de otro repartidor'}, 403

    repartidor = obtener(RepartidorModel, ruta.repartidorId, 'Repartidor no existe', bloquear=True)
    conexion.session.refresh(ruta)
    if ruta.estado not in ('planificada', 'en_curso'):
        return {'message': f'No se pueden agregar pedidos a una ruta "{ruta.estado}"'}, 409
    validarRepartidorOperativo(repartidor)

    asignarPedidoARuta(pedidoId, repartidor, ruta, 'Agregado a la ruta')
    conexion.session.commit()
    return {'message': f'Pedido agregado a la ruta {ruta.codigo}', 'content': construirDetalleRuta(ruta)}, 200


@bp.route('/ruta/<int:id>/quitar-pedido/<int:pedidoId>', methods=['POST'])
@requiereRol('admin', 'repartidor')
def quitarPedidoDeRuta(id, pedidoId):
    ruta = obtener(RutaModel, id, 'Ruta no existe')
    if not esDuenioDeLaRuta(ruta):
        return {'message': 'No puedes modificar la ruta de otro repartidor'}, 403

    pedido = conexion.session.query(PedidoModel).filter_by(id=pedidoId, rutaId=id).with_for_update().first()
    if not pedido:
        return {'message': 'Ese pedido no pertenece a esta ruta'}, 404

    if pedido.estadoId != idEstado('asignado'):
        return {'message': 'Este pedido ya fue recogido/esta en camino, ya no se puede quitar de la ruta '
                           '(si hay un problema, usa cancelar o reporta una incidencia)'}, 409

    # Vuelve a la agencia desde donde se reparte (origen o destino)
    estadoPool = idEstado(estadoListoParaReparto(pedido))
    pedido.rutaId = None
    pedido.repartidorId = None
    pedido.estadoId = estadoPool
    registrarHistorial(pedido.id, estadoPool, comentario=f'Removido de la ruta {ruta.codigo}, vuelve al pool')
    conexion.session.commit()
    return {'message': 'Pedido removido de la ruta, disponible de nuevo en el pool'}, 200


@bp.route('/rutas', methods=['GET'])
@requiereLogin
def listarRutas():
    query = conexion.session.query(RutaModel)
    if rolActual() == 'repartidor':
        query = query.filter_by(repartidorId=exigirMiRepartidor().id)
    else:
        query = filtrarRutasPorAgencia(query, agenciaDelUsuario())
        repartidorId = request.args.get('repartidor_id', type=int)
        if repartidorId:
            query = query.filter_by(repartidorId=repartidorId)
    estado = request.args.get('estado')
    if estado:
        query = query.filter_by(estado=estado)
    resultado = query.order_by(RutaModel.fecha.desc(), RutaModel.id.desc()).limit(200).all()
    return {'content': RutaDto().dump(resultado, many=True)}, 200


@bp.route('/ruta/<int:id>/detalle', methods=['GET'])
@requiereLogin
def detalleRuta(id):
    ruta = obtener(RutaModel, id, 'Ruta no existe')
    if not (esStaff() or esDuenioDeLaRuta(ruta)):
        return {'message': 'No puedes ver la ruta de otro repartidor'}, 403
    if esStaff():
        exigirAccesoRuta(ruta)
    return {'content': construirDetalleRuta(ruta)}, 200


@bp.route('/repartidor/<int:repartidorId>/ruta-activa', methods=['GET'])
@requiereLogin
def rutaActivaDeRepartidor(repartidorId):
    if not esStaff():
        perfil = miRepartidor()
        if not perfil or perfil.id != repartidorId:
            return {'message': 'No puedes ver la ruta de otro repartidor'}, 403

    ruta = rutaActivaDe(repartidorId)
    if not ruta:
        return {'message': 'Este repartidor no tiene una ruta activa'}, 404
    return {'content': construirDetalleRuta(ruta)}, 200


@bp.route('/ruta/<int:id>/iniciar', methods=['POST'])
@requiereRol('admin', 'repartidor')
def iniciarRuta(id):
    ruta = obtener(RutaModel, id, 'Ruta no existe', bloquear=True)
    if not esDuenioDeLaRuta(ruta):
        return {'message': 'No puedes modificar la ruta de otro repartidor'}, 403
    if ruta.estado != 'planificada':
        return {'message': f'Solo se puede iniciar una ruta "planificada" (esta esta "{ruta.estado}")'}, 409
    if not conexion.session.query(PedidoModel.id).filter_by(rutaId=id).first():
        return {'message': 'La ruta no tiene pedidos todavia'}, 409

    ruta.estado = 'en_curso'
    conexion.session.commit()
    return {'message': 'Ruta iniciada'}, 200


@bp.route('/ruta/<int:id>/completar', methods=['POST'])
@requiereRol('admin', 'repartidor')
def completarRuta(id):
    ruta = obtener(RutaModel, id, 'Ruta no existe', bloquear=True)
    if not esDuenioDeLaRuta(ruta):
        return {'message': 'No puedes modificar la ruta de otro repartidor'}, 403
    if ruta.estado != 'en_curso':
        return {'message': f'Solo se puede completar una ruta "en_curso" (esta esta "{ruta.estado}")'}, 409

    pendientes = conexion.session.query(PedidoModel).filter(
        PedidoModel.rutaId == id, PedidoModel.estadoId.in_(idsEstados(ESTADOS_PEDIDO_PENDIENTES_EN_RUTA))
    ).count()
    if pendientes > 0:
        return {'message': f'Todavia hay {pendientes} pedido(s) sin resolver en esta ruta '
                           '(entregalos, marca el intento fallido, o quitalos de la ruta antes de completarla)'}, 409

    # Los no entregados vuelven fisicamente a la agencia con el repartidor:
    # quedan listos para reintentar otro dia, o para devolver al remitente.
    noEntregados = conexion.session.query(PedidoModel).filter(
        PedidoModel.rutaId == id, PedidoModel.estadoId == idEstado('no_entregado')).with_for_update().all()
    maximo = current_app.config['MAX_INTENTOS_ENTREGA']
    destinos = []
    for p in noEntregados:
        destino = devolverAAgencia(p, ruta, maximo)
        if destino == 'por_devolver':
            generarCargoDevolucion(p, usuarioActualId())
        destinos.append(destino)
    porDevolver = destinos.count('por_devolver')
    paraReintentar = len(destinos) - porDevolver

    ruta.estado = 'completada'
    esperado = efectivoEsperadoDeRuta(id)
    if esperado == 0:
        # No hay efectivo que rendir: la liquidacion se cierra sola.
        conexion.session.add(LiquidacionRutaModel(
            rutaId=id, repartidorId=ruta.repartidorId, montoEsperado=0, montoEntregado=0, diferencia=0,
            observacion='Sin cobros en efectivo', recibidoPorId=None,
        ))
    conexion.session.commit()
    mensaje = 'Ruta completada'
    if destinos:
        mensaje += f'. Entrega {len(destinos)} paquete(s) no entregado(s) en la agencia'
        if porDevolver:
            mensaje += f' ({porDevolver} para devolver al remitente)'
    if esperado > 0:
        mensaje += f'. Debes liquidar S/ {esperado} en caja'
    return {
        'message': mensaje,
        'efectivoPorLiquidar': str(esperado),
        'paraReintentar': paraReintentar,
        'porDevolver': porDevolver,
    }, 200
