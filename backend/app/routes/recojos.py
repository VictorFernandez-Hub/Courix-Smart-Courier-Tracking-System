"""Recojo a domicilio (paso 1 del proceso operativo).

  pendiente -> (asignar repartidor) -> asignada -> (recoger) -> recogida
            -> (admitir envios en agencia) -> admitida
  asignada -> (no se pudo) -> fallida -> (reprogramar) -> pendiente
  pendiente | asignada | fallida -> cancelada
"""
from datetime import date

from flask import Blueprint, request

from app.extensions import conexion
from app.models import (
    AlmacenModel, ClienteModel, DireccionModel, PedidoModel, RepartidorModel, SolicitudRecojoModel, UsuarioModel,
)
from app.admision import ahoraLocal
from app.core.seguridad import requiereRol, auditar, rolActual, usuarioActualId, ROLES_STAFF
from app.core.validacion import ErrorNegocio, ErrorValidacion, cuerpoJson, decimalPositivo, entero, opcion, texto
from app.reglas import FRANJAS_RECOJO, MOTIVOS_FALLO_RECOJO, ahoraUtc
from app.servicios import agenciaDelUsuario, bultosAdmitidosDeRecojo, exigirMiAgencia, miRepartidor, obtener

bp = Blueprint('recojos', __name__)

ESTADOS_ABIERTOS = ('pendiente', 'asignada', 'fallida')


def _fecha(data, campo):
    valor = data.get(campo)
    try:
        fecha = date.fromisoformat(valor) if isinstance(valor, str) else None
    except ValueError:
        fecha = None
    if not fecha:
        raise ErrorValidacion(f'El campo "{campo}" debe ser una fecha AAAA-MM-DD')
    if fecha < ahoraLocal().date():
        raise ErrorValidacion('La fecha de recojo no puede ser anterior a hoy')
    return fecha


def _serializar(r):
    remitente = conexion.session.get(ClienteModel, r.remitenteId)
    direccion = conexion.session.get(DireccionModel, r.direccionId)
    agencia = conexion.session.get(AlmacenModel, r.agenciaId)
    repartidor = conexion.session.get(RepartidorModel, r.repartidorId) if r.repartidorId else None
    usuarioRep = conexion.session.get(UsuarioModel, repartidor.usuarioId) if repartidor else None
    envios = conexion.session.query(PedidoModel.codigoGuia).filter_by(solicitudRecojoId=r.id).all()
    return {
        'id': r.id,
        'codigo': r.codigo,
        'estado': r.estado,
        'remitente': {'id': r.remitenteId, 'nombre': remitente.nombre if remitente else None,
                      'telefono': remitente.telefono if remitente else None},
        'direccion': {'calle': direccion.calle if direccion else None,
                      'referencia': direccion.referencia if direccion else None},
        'agencia': {'id': r.agenciaId, 'nombre': agencia.nombre if agencia else None},
        'zonaId': r.zonaId,
        'fechaProgramada': r.fechaProgramada.isoformat(),
        'franja': r.franja,
        'bultosEstimados': r.bultosEstimados,
        'pesoEstimadoKg': str(r.pesoEstimadoKg) if r.pesoEstimadoKg is not None else None,
        'notas': r.notas,
        'repartidor': {'id': repartidor.id, 'nombre': usuarioRep.nombre if usuarioRep else None} if repartidor else None,
        'bultosRecogidos': r.bultosRecogidos,
        'motivoFallo': r.motivoFallo,
        'comentario': r.comentario,
        'envios': [e.codigoGuia for e in envios],
        **_cuadre(r),
    }


def _cuadre(r):
    """Recogido contra admitido: lo que falta admitir (o un faltante)."""
    if r.estado not in ('recogida', 'admitida') or not r.bultosRecogidos:
        return {'bultosAdmitidos': None, 'pendientesDeAdmitir': None, 'conDiferencia': False}
    admitidos = bultosAdmitidosDeRecojo(r.id)
    pendientes = max(r.bultosRecogidos - admitidos, 0)
    # Recogido hace mas de un dia y aun incompleto: algo se perdio en el camino
    atrasado = bool(r.fechaRecojo and (ahoraUtc() - r.fechaRecojo).days >= 1)
    return {'bultosAdmitidos': admitidos, 'pendientesDeAdmitir': pendientes,
            'conDiferencia': pendientes > 0 and atrasado}


def _exigirRepartidorDelRecojo(recojo):
    if rolActual() == 'repartidor':
        perfil = miRepartidor()
        if not perfil or perfil.id != recojo.repartidorId:
            raise ErrorNegocio('Este recojo no esta asignado a ti', 403)


@bp.route('/recojo', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearRecojo():
    data = cuerpoJson()
    remitente = obtener(ClienteModel, entero(data, 'remitenteId', requerido=True), 'El cliente no existe')
    if not remitente.activo:
        raise ErrorValidacion('El cliente esta desactivado')
    direccion = obtener(DireccionModel, entero(data, 'direccionId', requerido=True), 'La direccion no existe')
    if direccion.clienteId != remitente.id or not direccion.activo:
        raise ErrorValidacion('Esa direccion no pertenece al cliente')
    if not direccion.zonaId:
        raise ErrorValidacion('La direccion no tiene zona: asignale una para saber que agencia hace el recojo')
    agencia = conexion.session.query(AlmacenModel).filter_by(zonaId=direccion.zonaId, activo=True) \
        .order_by(AlmacenModel.id).first()
    if not agencia:
        raise ErrorValidacion('Ninguna agencia atiende la zona de esa direccion')
    exigirMiAgencia(agencia.id, 'Esa direccion la atiende otra agencia')

    recojo = SolicitudRecojoModel(
        remitenteId=remitente.id, direccionId=direccion.id, zonaId=direccion.zonaId, agenciaId=agencia.id,
        fechaProgramada=_fecha(data, 'fechaProgramada'),
        franja=opcion(data, 'franja', FRANJAS_RECOJO, requerido=True),
        bultosEstimados=entero(data, 'bultosEstimados', requerido=True, minimo=1, maximo=50),
        pesoEstimadoKg=decimalPositivo(data, 'pesoEstimadoKg'),
        notas=texto(data, 'notas', maximo=500),
        creadoPorId=usuarioActualId(),
    )
    conexion.session.add(recojo)
    conexion.session.flush()
    recojo.codigo = f'RC{recojo.id:06d}'
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo} registrado', 'content': _serializar(recojo)}, 201


@bp.route('/recojos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarRecojos():
    query = conexion.session.query(SolicitudRecojoModel)
    propia = agenciaDelUsuario()
    if propia:
        query = query.filter(SolicitudRecojoModel.agenciaId == propia)
    estado = request.args.get('estado')
    if estado:
        query = query.filter(SolicitudRecojoModel.estado.in_(estado.split(',')))
    fecha = request.args.get('fecha')
    if fecha:
        try:
            query = query.filter(SolicitudRecojoModel.fechaProgramada == date.fromisoformat(fecha))
        except ValueError:
            raise ErrorValidacion('fecha debe tener el formato AAAA-MM-DD')
    recojos = query.order_by(SolicitudRecojoModel.fechaProgramada, SolicitudRecojoModel.franja,
                             SolicitudRecojoModel.id).limit(300).all()
    contenido = [_serializar(r) for r in recojos]
    if request.args.get('con_diferencias') in ('1', 'true'):
        contenido = [c for c in contenido if c['conDiferencia']]
    return {'content': contenido}, 200


@bp.route('/recojo/<int:id>', methods=['GET'])
@requiereRol('admin', 'operador', 'repartidor')
def obtenerRecojo(id):
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe')
    if rolActual() != 'repartidor':
        exigirMiAgencia(recojo.agenciaId)
    _exigirRepartidorDelRecojo(recojo)
    return {'content': _serializar(recojo)}, 200


@bp.route('/mis-recojos', methods=['GET'])
@requiereRol('repartidor')
def misRecojos():
    perfil = miRepartidor()
    if not perfil:
        return {'content': []}, 200
    recojos = conexion.session.query(SolicitudRecojoModel).filter(
        SolicitudRecojoModel.repartidorId == perfil.id, SolicitudRecojoModel.estado == 'asignada',
    ).order_by(SolicitudRecojoModel.fechaProgramada, SolicitudRecojoModel.franja).all()
    return {'content': [_serializar(r) for r in recojos]}, 200


@bp.route('/recojo/<int:id>/asignar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def asignarRecojo(id):
    data = cuerpoJson()
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe', bloquear=True)
    exigirMiAgencia(recojo.agenciaId)
    if recojo.estado not in ('pendiente', 'asignada'):
        raise ErrorNegocio(f'No se puede asignar un recojo en estado "{recojo.estado}"', 409)
    repartidor = obtener(RepartidorModel, entero(data, 'repartidorId', requerido=True), 'Repartidor no existe')
    usuario = conexion.session.get(UsuarioModel, repartidor.usuarioId)
    if not usuario or not usuario.activo:
        raise ErrorValidacion('El usuario de ese repartidor esta inactivo')
    if repartidor.zonaId != recojo.zonaId:
        raise ErrorValidacion('El repartidor debe ser de la zona del recojo')
    recojo.repartidorId = repartidor.id
    recojo.estado = 'asignada'
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo} asignado', 'content': _serializar(recojo)}, 200


@bp.route('/recojo/<int:id>/recoger', methods=['POST'])
@requiereRol('admin', 'repartidor')
def marcarRecogido(id):
    data = cuerpoJson()
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe', bloquear=True)
    _exigirRepartidorDelRecojo(recojo)
    if recojo.estado != 'asignada':
        raise ErrorNegocio(f'No se puede marcar como recogido un recojo en estado "{recojo.estado}"', 409)
    recojo.bultosRecogidos = entero(data, 'bultosRecogidos', requerido=True, minimo=1, maximo=50)
    recojo.comentario = texto(data, 'comentario', maximo=500)
    recojo.estado = 'recogida'
    recojo.fechaRecojo = ahoraUtc()
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo}: {recojo.bultosRecogidos} bulto(s) recogido(s). '
                       'Llevalos a la agencia para su admision', 'content': _serializar(recojo)}, 200


@bp.route('/recojo/<int:id>/fallido', methods=['POST'])
@requiereRol('admin', 'repartidor')
def marcarFallido(id):
    data = cuerpoJson()
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe', bloquear=True)
    _exigirRepartidorDelRecojo(recojo)
    if recojo.estado != 'asignada':
        raise ErrorNegocio(f'No se puede marcar como fallido un recojo en estado "{recojo.estado}"', 409)
    recojo.motivoFallo = opcion(data, 'motivo', MOTIVOS_FALLO_RECOJO, requerido=True)
    recojo.comentario = texto(data, 'comentario', maximo=500)
    recojo.estado = 'fallida'
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo} marcado como no realizado', 'content': _serializar(recojo)}, 200


@bp.route('/recojo/<int:id>/reprogramar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def reprogramarRecojo(id):
    data = cuerpoJson()
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe', bloquear=True)
    exigirMiAgencia(recojo.agenciaId)
    if recojo.estado not in ESTADOS_ABIERTOS:
        raise ErrorNegocio(f'No se puede reprogramar un recojo en estado "{recojo.estado}"', 409)
    recojo.fechaProgramada = _fecha(data, 'fechaProgramada')
    recojo.franja = opcion(data, 'franja', FRANJAS_RECOJO, requerido=True)
    recojo.estado = 'pendiente'
    recojo.repartidorId = None
    recojo.motivoFallo = None
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo} reprogramado', 'content': _serializar(recojo)}, 200


@bp.route('/recojo/<int:id>/cancelar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def cancelarRecojo(id):
    data = cuerpoJson()
    recojo = obtener(SolicitudRecojoModel, id, 'Recojo no existe', bloquear=True)
    exigirMiAgencia(recojo.agenciaId)
    if recojo.estado not in ESTADOS_ABIERTOS:
        raise ErrorNegocio(f'No se puede cancelar un recojo en estado "{recojo.estado}"', 409)
    recojo.estado = 'cancelada'
    recojo.comentario = texto(data, 'motivo', maximo=500)
    auditar('recojo_cancelado', 'recojo', id, {'motivo': recojo.comentario})
    conexion.session.commit()
    return {'message': f'Recojo {recojo.codigo} cancelado', 'content': _serializar(recojo)}, 200
