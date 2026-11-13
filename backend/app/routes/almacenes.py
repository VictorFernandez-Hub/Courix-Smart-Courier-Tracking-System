"""Agencias / almacenes de la red.

Ademas del alta y edicion, el modulo responde lo que el jefe de agencia
pregunta todos los dias: que paquetes tengo fisicamente (y desde cuando),
que debo despachar, que tengo listo para reparto, que me esta llegando, que
esta en la calle, quien trabaja aqui y que movimientos hubo. Incluye la hoja
de inventario para el conteo fisico y una bitacora de cambios.

Secciones del inventario de una agencia (agencia de reparto = destino, o el
origen si el envio es local):
- por_ingresar:  admitido en esta agencia pero el paquete aun no llega al mostrador
- por_despachar: en esta agencia, debe viajar a otra (va en un manifiesto)
- para_reparto:  en esta agencia y se reparte desde aqui
- por_llegar:    viene en camino desde otra agencia (manifiesto en transito)
- en_reparto:    salio con un repartidor de esta agencia
- por_devolver:  esta aqui y debe volver al remitente (entregarlo en el
                 origen, o despacharlo de regreso si se repartia aqui)
"""
import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, request
from sqlalchemy import String, and_, case, func, literal, or_, select, union_all
from sqlalchemy.orm import aliased

from app.extensions import conexion
from app.models import (
    AlmacenModel, AuditoriaModel, BultoModel, ClienteModel, EstadoPedidoModel, EventoBultoModel,
    HistorialEstadoModel, ManifiestoBultoModel, ManifiestoModel, PedidoModel, SolicitudRecojoModel,
    UsuarioModel, ZonaModel,
)
from app.core.seguridad import (
    requiereRol, requiereLogin, auditar, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, texto, entero, coordenada, telefono, email, paginacion,
)
from app.admision import ahoraLocal
from app.reglas import ESTADOS_ACTIVOS
from app.schemas import AlmacenDto
from app.servicios import (
    agenciaDelUsuario, exigirZonaActiva, idsEstados, obtener, patronBusqueda,
)


bp = Blueprint('almacenes', __name__)

# Un paquete que lleva mas de estos dias quieto en la agencia es una alerta:
# se olvido en un estante, falta despacharlo o el cliente no lo recoge.
DIAS_ESTANCADO = 3
SECCIONES = ('por_ingresar', 'por_despachar', 'para_reparto', 'por_llegar', 'en_reparto', 'por_devolver')
SECCIONES_STOCK = ('por_despachar', 'para_reparto', 'por_devolver')  # lo que esta fisicamente en la agencia
ESTADOS_EN_REPARTO = ('asignado', 'recogido', 'en_camino', 'no_entregado')
CAMPOS_AUDITABLES = ('nombre', 'codigo', 'calle', 'referencia', 'zonaId', 'telefono', 'email', 'horario',
                     'responsableId', 'capacidadBultos', 'latitud', 'longitud')
TIPOS_MOVIMIENTO = ('admitido', 'manifestado', 'retirado_de_manifiesto', 'despachado', 'recibido_en_destino',
                    'faltante', 'recibido_tarde')


# ------------------------------------------------------------ Helpers ----

def _agenciaReparto():
    return func.coalesce(PedidoModel.agenciaDestinoId, PedidoModel.almacenId)


def _idsPorNombre():
    return {e.nombre: e.id for e in conexion.session.query(EstadoPedidoModel).all()}


def _inventario(agenciaId=None):
    """Subconsulta (agencia_id, seccion, pedido_id): cada envio aparece en la
    seccion que le toca en la agencia que lo tiene a su cargo."""
    ids = _idsPorNombre()
    rep = _agenciaReparto()
    P = PedidoModel
    # En una devolucion que ya emprendio el regreso, el paquete es del origen
    dondeEsta = case((P.retornoAlOrigen.is_(True), P.almacenId), else_=rep)

    def seccion(nombre, columnaAgencia, condicion):
        consulta = select(columnaAgencia.label('agencia_id'), literal(nombre, type_=String).label('seccion'),
                          P.id.label('pedido_id')).where(condicion)
        if agenciaId:
            consulta = consulta.where(columnaAgencia == agenciaId)
        return consulta

    return union_all(
        seccion('por_ingresar', P.almacenId, P.estadoId == ids.get('pendiente')),
        seccion('por_despachar', P.almacenId, and_(P.estadoId == ids.get('en_almacen'), rep != P.almacenId)),
        seccion('para_reparto', P.almacenId, and_(P.estadoId == ids.get('en_almacen'), rep == P.almacenId)),
        seccion('para_reparto', rep, and_(P.estadoId == ids.get('en_agencia_destino'), rep != P.almacenId)),
        seccion('por_llegar', dondeEsta, P.estadoId == ids.get('en_transito')),
        seccion('en_reparto', rep, P.estadoId.in_([ids[n] for n in ESTADOS_EN_REPARTO if n in ids])),
        seccion('por_devolver', dondeEsta, P.estadoId == ids.get('por_devolver')),
    ).subquery('inventario')


def _ultimoCambio():
    """Desde cuando el envio esta en su estado actual (ultimo cambio)."""
    H = HistorialEstadoModel
    return (select(H.pedidoId.label('pedido_id'), func.max(H.fecha).label('desde'))
            .group_by(H.pedidoId).subquery('ultimo_cambio'))


def _bultosPorPedido():
    return (select(BultoModel.pedidoId.label('pedido_id'), func.count(BultoModel.id).label('n'),
                   func.sum(BultoModel.pesoKg).label('peso'))
            .group_by(BultoModel.pedidoId).subquery('bultos_pedido'))


def _ahoraDb():
    """Reloj de la base: las fechas se guardan con now() de la base, asi que
    las antiguedades se calculan con el mismo reloj (no el del servidor web)."""
    ahora = conexion.session.query(func.now()).scalar()
    if isinstance(ahora, str):
        ahora = datetime.fromisoformat(ahora)
    return ahora.replace(tzinfo=None) if ahora else datetime.now()


def _metricasPorAgencia(agenciaId=None):
    """{agenciaId: {seccion: {envios, bultos, estancados}}} en una sola consulta."""
    inv, ult, bul = _inventario(agenciaId), _ultimoCambio(), _bultosPorPedido()
    limite = _ahoraDb() - timedelta(days=DIAS_ESTANCADO)
    desde = func.coalesce(ult.c.desde, PedidoModel.fechaCreacion)
    filas = (conexion.session.query(
        inv.c.agencia_id, inv.c.seccion, func.count(inv.c.pedido_id),
        func.sum(func.coalesce(bul.c.n, 1)),
        func.sum(case((desde < limite, 1), else_=0)),
    ).select_from(inv)
        .join(PedidoModel, PedidoModel.id == inv.c.pedido_id)
        .outerjoin(ult, ult.c.pedido_id == inv.c.pedido_id)
        .outerjoin(bul, bul.c.pedido_id == inv.c.pedido_id)
        .group_by(inv.c.agencia_id, inv.c.seccion).all())
    resultado = {}
    for agencia, nombre, envios, bultos, estancados in filas:
        resultado.setdefault(agencia, {})[nombre] = {
            'envios': int(envios or 0), 'bultos': int(bultos or 0), 'estancados': int(estancados or 0)}
    return resultado


def _resumirMetricas(secciones, capacidad=None):
    vacio = {'envios': 0, 'bultos': 0, 'estancados': 0}
    porSeccion = {s: dict(secciones.get(s, vacio)) for s in SECCIONES}
    stockBultos = sum(porSeccion[s]['bultos'] for s in SECCIONES_STOCK)
    return {
        'secciones': porSeccion,
        'stockEnvios': sum(porSeccion[s]['envios'] for s in SECCIONES_STOCK),
        'stockBultos': stockBultos,
        'estancados': sum(porSeccion[s]['estancados'] for s in SECCIONES_STOCK),
        'ocupacion': round(stockBultos * 100 / capacidad) if capacidad else None,
    }


def _exigirAccesoAgencia(agenciaId):
    """Un operador solo ve su propia agencia (404: no se confirma que exista otra)."""
    propia = agenciaDelUsuario()
    if propia and propia != agenciaId:
        raise ErrorNegocio('Almacen no existe', 404)


def _leerAlmacen(data, actual=None):
    def presente(campo):
        return actual is None or campo in data

    valores = {}
    if presente('nombre'):
        valores['nombre'] = texto(data, 'nombre', requerido=True, maximo=100, minimo=3)
    if 'codigo' in data:
        codigo = texto(data, 'codigo', maximo=10)
        if codigo:
            codigo = codigo.upper().replace(' ', '')
            if not (2 <= len(codigo) <= 10) or not all(c.isalnum() or c == '-' for c in codigo):
                raise ErrorValidacion('El codigo debe tener de 2 a 10 letras, numeros o guiones (ej. LIM01)')
        elif actual is not None:
            raise ErrorValidacion('El codigo de la agencia no puede quedar vacio')
        valores['codigo'] = codigo
    if presente('calle'):
        valores['calle'] = texto(data, 'calle', requerido=True, maximo=300, minimo=3)
    if presente('referencia'):
        valores['referencia'] = texto(data, 'referencia', maximo=300)
    if presente('zonaId'):
        valores['zonaId'] = entero(data, 'zonaId', requerido=True)
    if presente('telefono'):
        valores['telefono'] = telefono(data)
    if presente('email'):
        valores['email'] = email(data, requerido=False)
    if presente('horario'):
        valores['horario'] = texto(data, 'horario', maximo=200)
    if presente('capacidadBultos'):
        valores['capacidadBultos'] = entero(data, 'capacidadBultos', minimo=1, maximo=1000000)
    if presente('responsableId'):
        valores['responsableId'] = entero(data, 'responsableId')
    for campo, alias in (('latitud', 'lat'), ('longitud', 'lon')):
        if presente(campo):
            valores[campo] = coordenada(data, campo, alias)
    if (valores.get('latitud') is None) != (valores.get('longitud') is None) and actual is None:
        raise ErrorValidacion('Indica latitud y longitud juntas (o ninguna)')
    return valores


def _exigirUnicos(valores, excluirId=None):
    def existe(condicion):
        query = conexion.session.query(AlmacenModel).filter(condicion)
        if excluirId:
            query = query.filter(AlmacenModel.id != excluirId)
        return query.first()

    if valores.get('nombre'):
        otro = existe(func.lower(AlmacenModel.nombre) == valores['nombre'].lower())
        if otro:
            raise ErrorNegocio(f'Ya existe una agencia llamada "{otro.nombre}"', 409)
    if valores.get('codigo'):
        otro = existe(AlmacenModel.codigo == valores['codigo'])
        if otro:
            raise ErrorNegocio(f'El codigo {valores["codigo"]} ya lo usa "{otro.nombre}"', 409)


def _validarResponsable(responsableId, almacenId=None):
    if responsableId is None:
        return
    usuario = obtener(UsuarioModel, responsableId, 'El responsable indicado no existe')
    if not usuario.activo or usuario.rol not in ROLES_STAFF:
        raise ErrorValidacion('El responsable debe ser un administrador u operador activo')
    if usuario.rol == 'operador' and usuario.agenciaId and usuario.agenciaId != almacenId:
        raise ErrorValidacion(f'{usuario.nombre} trabaja en otra agencia; reasignalo primero')


def _pedidosActivos(almacenId):
    return conexion.session.query(PedidoModel).filter(
        or_(PedidoModel.almacenId == almacenId, PedidoModel.agenciaDestinoId == almacenId),
        PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS)),
    ).count()


def _dumpAlmacen(almacen, zonas=None, responsables=None):
    datos = AlmacenDto().dump(almacen)
    if zonas is not None:
        datos['zona'] = zonas.get(almacen.zonaId)
    if responsables is not None:
        datos['responsable'] = responsables.get(almacen.responsableId)
    return datos


def _iso(fecha):
    return fecha.isoformat() if fecha else None


# ------------------------------------------------------------ Listados ----

@bp.route('/almacenes', methods=['GET'])
@requiereLogin
def listarAlmacenes():
    """Lista simple para los selectores (admision, manifiestos, usuarios)."""
    query = conexion.session.query(AlmacenModel)
    if request.args.get('incluir_inactivos') != 'true':
        query = query.filter_by(activo=True)
    return {'content': AlmacenDto().dump(query.order_by(AlmacenModel.nombre).all(), many=True)}, 200


@bp.route('/almacenes/panel', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def panelAlmacenes():
    """Tablero de la red: cada agencia con su carga de trabajo del momento."""
    query = conexion.session.query(AlmacenModel)
    propia = agenciaDelUsuario()
    if propia:
        query = query.filter(AlmacenModel.id == propia)
    elif request.args.get('incluir_inactivos') != 'true':
        query = query.filter(AlmacenModel.activo.is_(True))
    almacenes = query.order_by(AlmacenModel.nombre).all()

    metricas = _metricasPorAgencia(propia)
    zonas = {z.id: z.nombre for z in conexion.session.query(ZonaModel).all()}
    responsables = {u.id: u.nombre for u in conexion.session.query(UsuarioModel).filter(
        UsuarioModel.id.in_({a.responsableId for a in almacenes if a.responsableId} or {-1})).all()}
    personal = dict(conexion.session.query(UsuarioModel.agenciaId, func.count(UsuarioModel.id))
                    .filter(UsuarioModel.activo.is_(True), UsuarioModel.agenciaId.isnot(None))
                    .group_by(UsuarioModel.agenciaId).all())

    contenido = []
    for a in almacenes:
        datos = _dumpAlmacen(a, zonas, responsables)
        datos['metricas'] = _resumirMetricas(metricas.get(a.id, {}), a.capacidadBultos)
        datos['personal'] = personal.get(a.id, 0)
        contenido.append(datos)

    activas = [c for c in contenido if c['activo']]

    def total(clave, seccion=None):
        return sum((c['metricas']['secciones'][seccion]['bultos'] if seccion else c['metricas'][clave])
                   for c in activas)

    return {'content': contenido, 'resumen': {
        'agencias': len(contenido),
        'activas': len(activas),
        'stockBultos': total('stockBultos'),
        'porDespachar': total(None, 'por_despachar'),
        'paraReparto': total(None, 'para_reparto'),
        'porLlegar': total(None, 'por_llegar'),
        'enReparto': total(None, 'en_reparto'),
        'porDevolver': total(None, 'por_devolver'),
        'estancados': total('estancados'),
        'diasEstancado': DIAS_ESTANCADO,
    }}, 200


# ------------------------------------------------------------ Ficha ----

@bp.route('/almacen/<int:id>', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def obtenerAlmacen(id):
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    _exigirAccesoAgencia(id)

    zona = conexion.session.get(ZonaModel, almacen.zonaId) if almacen.zonaId else None
    responsable = conexion.session.get(UsuarioModel, almacen.responsableId) if almacen.responsableId else None
    personal = (conexion.session.query(UsuarioModel).filter(UsuarioModel.agenciaId == id)
                .order_by(UsuarioModel.activo.desc(), UsuarioModel.nombre).all())

    hoy = func.date(func.now())
    admitidosHoy = conexion.session.query(PedidoModel).filter(
        PedidoModel.almacenId == id, func.date(PedidoModel.fechaCreacion) == hoy).count()
    entregadosHoy = conexion.session.query(PedidoModel).filter(
        _agenciaReparto() == id, func.date(PedidoModel.fechaEntrega) == hoy).count()
    # fechaDespacho se guarda en UTC: se compara con el dia local expresado en UTC
    inicioHoyUtc = (ahoraLocal().replace(hour=0, minute=0, second=0, microsecond=0)
                    - timedelta(hours=current_app.config['UTC_OFFSET_HORAS']))
    despachadosHoy = conexion.session.query(ManifiestoModel).filter(
        ManifiestoModel.agenciaOrigenId == id, ManifiestoModel.fechaDespacho >= inicioHoyUtc,
        ManifiestoModel.fechaDespacho < inicioHoyUtc + timedelta(days=1)).count()

    manifiestos = (conexion.session.query(ManifiestoModel).filter(
        or_(ManifiestoModel.agenciaOrigenId == id, ManifiestoModel.agenciaDestinoId == id),
        ManifiestoModel.estado.in_(('abierto', 'en_transito')),
    ).order_by(ManifiestoModel.id.desc()).limit(10).all())
    nombres = {a.id: a.nombre for a in conexion.session.query(AlmacenModel).all()}
    bultosManifiesto = dict(conexion.session.query(ManifiestoBultoModel.manifiestoId, func.count(ManifiestoBultoModel.id))
                            .filter(ManifiestoBultoModel.manifiestoId.in_([m.id for m in manifiestos] or [-1]))
                            .group_by(ManifiestoBultoModel.manifiestoId).all())

    recojosPendientes = conexion.session.query(SolicitudRecojoModel).filter(
        SolicitudRecojoModel.agenciaId == id,
        SolicitudRecojoModel.estado.in_(('pendiente', 'asignada', 'recogida')),
    ).count()

    return {'content': {
        'almacen': _dumpAlmacen(almacen),
        'zona': zona.nombre if zona else None,
        'responsable': {
            'id': responsable.id, 'nombre': responsable.nombre, 'celular': responsable.celular,
            'email': responsable.email, 'rol': responsable.rol,
        } if responsable else None,
        'metricas': {
            **_resumirMetricas(_metricasPorAgencia(id).get(id, {}), almacen.capacidadBultos),
            'admitidosHoy': admitidosHoy,
            'entregadosHoy': entregadosHoy,
            'manifiestosDespachadosHoy': despachadosHoy,
            'recojosPendientes': recojosPendientes,
            'diasEstancado': DIAS_ESTANCADO,
        },
        'personal': [{
            'id': u.id, 'nombre': u.nombre, 'usuario': u.nombreUsuario, 'rol': u.rol, 'celular': u.celular,
            'activo': bool(u.activo), 'ultimoLogin': _iso(u.ultimoLogin),
        } for u in personal],
        'manifiestos': [{
            'id': m.id, 'codigo': m.codigo, 'estado': m.estado,
            'sentido': 'salida' if m.agenciaOrigenId == id else 'llegada',
            'contraparte': nombres.get(m.agenciaDestinoId if m.agenciaOrigenId == id else m.agenciaOrigenId),
            'bultos': bultosManifiesto.get(m.id, 0),
            'transportista': m.transportista,
            'fecha': _iso(m.fechaDespacho or m.fechaCreacion),
        } for m in manifiestos],
    }}, 200


@bp.route('/almacen', methods=['POST'])
@requiereRol('admin')
def crearAlmacen():
    data = cuerpoJson()
    valores = _leerAlmacen(data)
    exigirZonaActiva(valores['zonaId'])
    _exigirUnicos(valores)
    _validarResponsable(valores.get('responsableId'))
    nuevo = AlmacenModel(**valores)
    conexion.session.add(nuevo)
    conexion.session.flush()
    if not nuevo.codigo:
        # Codigo provisional unico; el administrador puede cambiarlo
        candidato, n = f'AG{nuevo.id:02d}', nuevo.id
        while conexion.session.query(AlmacenModel.id).filter(AlmacenModel.codigo == candidato).first():
            n += 1
            candidato = f'AG{n:02d}'
        nuevo.codigo = candidato
    auditar('almacen_creado', 'almacen', nuevo.id)
    conexion.session.commit()
    return {'content': AlmacenDto().dump(nuevo)}, 201


@bp.route('/almacen/<int:id>', methods=['PUT'])
@requiereRol('admin')
def editarAlmacen(id):
    data = cuerpoJson()
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    valores = _leerAlmacen(data, actual=almacen)
    _exigirUnicos(valores, excluirId=id)
    if 'responsableId' in valores and valores['responsableId'] != almacen.responsableId:
        _validarResponsable(valores['responsableId'], id)

    if 'zonaId' in valores and valores['zonaId'] != almacen.zonaId:
        exigirZonaActiva(valores['zonaId'])
        activos = _pedidosActivos(id)
        if activos:
            raise ErrorNegocio(f'No se puede cambiar la zona: el almacen tiene {activos} pedido(s) en curso', 409)

    cambiados = [c for c in CAMPOS_AUDITABLES if c in valores and getattr(almacen, c) != valores[c]]
    for campo in cambiados:
        setattr(almacen, campo, valores[campo])
    if cambiados:
        # Solo los nombres de los campos: el valor ya esta en la ficha
        auditar('almacen_editado', 'almacen', id, {'campos': cambiados})
    conexion.session.commit()
    return {'message': 'Almacen actualizado exitosamente', 'content': AlmacenDto().dump(almacen)}, 200


@bp.route('/almacen/<int:id>/desactivar', methods=['POST'])
@requiereRol('admin')
def desactivarAlmacen(id):
    """Cerrar una agencia exige que no quede nada a medio camino: envios,
    manifiestos, recojos ni personal asignado."""
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    data = request.get_json(silent=True) or {}
    motivo = texto(data, 'motivo', maximo=200)

    bloqueos = []
    activos = _pedidosActivos(id)
    if activos:
        bloqueos.append(f'{activos} pedido(s) en curso')
    manifiestos = conexion.session.query(ManifiestoModel).filter(
        or_(ManifiestoModel.agenciaOrigenId == id, ManifiestoModel.agenciaDestinoId == id),
        ManifiestoModel.estado.in_(('abierto', 'en_transito'))).count()
    if manifiestos:
        bloqueos.append(f'{manifiestos} manifiesto(s) abierto(s) o en transito')
    recojos = conexion.session.query(SolicitudRecojoModel).filter(
        SolicitudRecojoModel.agenciaId == id,
        SolicitudRecojoModel.estado.in_(('pendiente', 'asignada', 'recogida'))).count()
    if recojos:
        bloqueos.append(f'{recojos} recojo(s) pendiente(s)')
    operadores = conexion.session.query(UsuarioModel).filter(
        UsuarioModel.agenciaId == id, UsuarioModel.activo.is_(True)).count()
    if operadores:
        bloqueos.append(f'{operadores} usuario(s) asignado(s) (reasignalos a otra agencia)')
    if bloqueos:
        # El mensaje empieza igual que antes para no romper a quien lo lea
        raise ErrorNegocio(f'El almacen tiene {"; ".join(bloqueos)}; no se puede desactivar todavia', 409)

    almacen.activo = False
    almacen.motivoDesactivacion = motivo
    auditar('almacen_desactivado', 'almacen', id, {'motivo': motivo} if motivo else None)
    conexion.session.commit()
    return {'message': 'Almacen desactivado exitosamente'}, 200


@bp.route('/almacen/<int:id>/activar', methods=['POST'])
@requiereRol('admin')
def activarAlmacen(id):
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    if almacen.zonaId:
        exigirZonaActiva(almacen.zonaId)
    almacen.activo = True
    almacen.motivoDesactivacion = None
    auditar('almacen_activado', 'almacen', id)
    conexion.session.commit()
    return {'message': 'Almacen activado exitosamente'}, 200


# ------------------------------------------------------------ Inventario ----

def _consultaInventario(id):
    """Envios de la agencia con su seccion, bultos, peso y antiguedad."""
    inv, ult, bul = _inventario(id), _ultimoCambio(), _bultosPorPedido()
    Destinatario = aliased(ClienteModel)
    Remitente = aliased(ClienteModel)
    Destino = aliased(AlmacenModel)
    desde = func.coalesce(ult.c.desde, PedidoModel.fechaCreacion).label('desde')
    query = (conexion.session.query(
        PedidoModel, inv.c.seccion, desde, func.coalesce(bul.c.n, 1).label('bultos'), bul.c.peso,
        Destinatario.nombre, Remitente.nombre, Destino.nombre, EstadoPedidoModel.nombre,
    ).select_from(inv)
        .join(PedidoModel, PedidoModel.id == inv.c.pedido_id)
        .join(EstadoPedidoModel, EstadoPedidoModel.id == PedidoModel.estadoId)
        .outerjoin(ult, ult.c.pedido_id == inv.c.pedido_id)
        .outerjoin(bul, bul.c.pedido_id == inv.c.pedido_id)
        .outerjoin(Destinatario, Destinatario.id == PedidoModel.clienteId)
        .outerjoin(Remitente, Remitente.id == PedidoModel.remitenteId)
        .outerjoin(Destino, Destino.id == _agenciaReparto()))

    seccion = request.args.get('seccion')
    if seccion == 'stock':
        query = query.filter(inv.c.seccion.in_(SECCIONES_STOCK))
    elif seccion in SECCIONES:
        query = query.filter(inv.c.seccion == seccion)
    if request.args.get('estancados') == 'true':
        query = query.filter(inv.c.seccion.in_(SECCIONES_STOCK),
                             desde < _ahoraDb() - timedelta(days=DIAS_ESTANCADO))
    q = (request.args.get('q') or '').strip()
    if q:
        patron = patronBusqueda(q)
        codigos = select(BultoModel.pedidoId).where(BultoModel.codigo.ilike(patron))
        query = query.filter(or_(PedidoModel.codigoGuia.ilike(patron), Destinatario.nombre.ilike(patron),
                                 Remitente.nombre.ilike(patron), PedidoModel.id.in_(codigos)))
    # Lo urgente primero y, dentro de eso, lo mas antiguo (primero en entrar, primero en salir)
    return query.order_by(case((PedidoModel.prioridad == 'urgente', 0), else_=1), desde.asc(), PedidoModel.id)


def _filaInventario(fila, ahora):
    pedido, seccion, desde, bultos, peso, destinatario, remitente, destino, estado = fila
    dias = (ahora - desde).days if desde else 0
    return {
        'id': pedido.id, 'codigoGuia': pedido.codigoGuia, 'seccion': seccion, 'estado': estado,
        'destinatario': destinatario, 'remitente': remitente, 'agenciaReparto': destino,
        'bultos': int(bultos or 0), 'pesoKg': float(peso) if peso is not None else pedido.pesoKg,
        'prioridad': pedido.prioridad, 'tipoServicio': pedido.tipoServicio, 'modalidadPago': pedido.modalidadPago,
        'desde': _iso(desde), 'dias': max(dias, 0),
        'estancado': seccion in SECCIONES_STOCK and dias >= DIAS_ESTANCADO,
    }


@bp.route('/almacen/<int:id>/inventario', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def inventarioAlmacen(id):
    obtener(AlmacenModel, id, 'Almacen no existe')
    _exigirAccesoAgencia(id)
    query = _consultaInventario(id)
    pagina, porPagina = paginacion()
    total = query.order_by(None).count()
    ahora = _ahoraDb()
    filas = query.offset((pagina - 1) * porPagina).limit(porPagina).all()
    conteos = {s: v['envios'] for s, v in _resumirMetricas(_metricasPorAgencia(id).get(id, {}))['secciones'].items()}
    return {
        'content': [_filaInventario(f, ahora) for f in filas],
        'conteos': conteos,
        'paginacion': {'pagina': pagina, 'porPagina': porPagina, 'totalRegistros': total,
                       'totalPaginas': (total + porPagina - 1) // porPagina},
    }, 200


@bp.route('/almacen/<int:id>/inventario/exportar', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def exportarInventario(id):
    """Hoja de conteo fisico: una fila por bulto, con columna para marcar
    lo encontrado en el estante. Queda auditada (tiene datos de clientes)."""
    almacen = obtener(AlmacenModel, id, 'Almacen no existe')
    _exigirAccesoAgencia(id)
    ahora = _ahoraDb()
    filas = [_filaInventario(f, ahora) for f in _consultaInventario(id).all()]
    codigos = {}
    for b in conexion.session.query(BultoModel).filter(
            BultoModel.pedidoId.in_([f['id'] for f in filas] or [-1])).order_by(BultoModel.numero).all():
        codigos.setdefault(b.pedidoId, []).append(b)

    def celda(valor):
        texto_ = '' if valor is None else str(valor)
        return "'" + texto_ if texto_[:1] in ('=', '+', '-', '@') else texto_

    nombresSeccion = {'por_ingresar': 'Por ingresar', 'por_despachar': 'Por despachar',
                      'para_reparto': 'Para reparto', 'por_llegar': 'Por llegar', 'en_reparto': 'En reparto'}
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(['Guia', 'Bulto', 'Peso kg', 'Seccion', 'Estado', 'Destinatario', 'Agencia de reparto',
                       'Prioridad', 'En la seccion desde', 'Dias', 'Encontrado (marcar)'])
    bultos = 0
    for f in filas:
        for b in codigos.get(f['id']) or [None]:
            bultos += 1
            escritor.writerow([celda(v) for v in (
                f['codigoGuia'] or f'#{f["id"]}', b.codigo if b else '', b.pesoKg if b else f['pesoKg'],
                nombresSeccion.get(f['seccion'], f['seccion']), f['estado'], f['destinatario'],
                f['agenciaReparto'], f['prioridad'], (f['desde'] or '')[:16].replace('T', ' '), f['dias'], '',
            )])
    auditar('inventario_exportado', 'almacen', id, {'envios': len(filas), 'bultos': bultos,
                                                     'filtros': {k: v for k, v in request.args.items()}})
    conexion.session.commit()
    nombre = f'inventario_{almacen.codigo or almacen.id}_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    return Response('﻿' + salida.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{nombre}"'})


# ------------------------------------------------------------ Movimientos ----

@bp.route('/almacen/<int:id>/movimientos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def movimientosAlmacen(id):
    """Kardex de la agencia: cada bulto que entro, se manifesto, salio, llego
    o falto aqui, con quien lo hizo."""
    obtener(AlmacenModel, id, 'Almacen no existe')
    _exigirAccesoAgencia(id)
    query = (conexion.session.query(EventoBultoModel, BultoModel.codigo, PedidoModel.codigoGuia,
                                    UsuarioModel.nombre, ManifiestoModel.codigo)
             .join(BultoModel, BultoModel.id == EventoBultoModel.bultoId)
             .join(PedidoModel, PedidoModel.id == EventoBultoModel.pedidoId)
             .outerjoin(UsuarioModel, UsuarioModel.id == EventoBultoModel.usuarioId)
             .outerjoin(ManifiestoModel, ManifiestoModel.id == EventoBultoModel.manifiestoId)
             .filter(EventoBultoModel.agenciaId == id))
    tipo = request.args.get('tipo')
    if tipo in TIPOS_MOVIMIENTO:
        query = query.filter(EventoBultoModel.tipo == tipo)
    pagina, porPagina = paginacion()
    total = query.order_by(None).count()
    filas = (query.order_by(EventoBultoModel.fecha.desc(), EventoBultoModel.id.desc())
             .offset((pagina - 1) * porPagina).limit(porPagina).all())
    return {
        'content': [{
            'id': e.id, 'tipo': e.tipo, 'pedidoId': e.pedidoId, 'bulto': bulto, 'codigoGuia': guia,
            'usuario': usuario, 'manifiesto': manifiesto, 'fecha': _iso(e.fecha),
        } for e, bulto, guia, usuario, manifiesto in filas],
        'paginacion': {'pagina': pagina, 'porPagina': porPagina, 'totalRegistros': total,
                       'totalPaginas': (total + porPagina - 1) // porPagina},
    }, 200


@bp.route('/almacen/<int:id>/actividad', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def actividadAlmacen(id):
    """Bitacora de la ficha: alta, ediciones, bajas, reactivaciones y
    exportaciones del inventario."""
    obtener(AlmacenModel, id, 'Almacen no existe')
    _exigirAccesoAgencia(id)
    filas = (conexion.session.query(AuditoriaModel, UsuarioModel.nombre)
             .outerjoin(UsuarioModel, UsuarioModel.id == AuditoriaModel.usuarioId)
             .filter(AuditoriaModel.entidad == 'almacen', AuditoriaModel.entidadId == id)
             .order_by(AuditoriaModel.fecha.desc(), AuditoriaModel.id.desc()).limit(50).all())
    return {'content': [{
        'id': a.id, 'accion': a.accion, 'detalle': a.detalle, 'usuario': nombre, 'fecha': _iso(a.fecha),
    } for a, nombre in filas]}, 200
