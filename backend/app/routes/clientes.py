"""Clientes (remitentes y destinatarios) y sus direcciones de entrega.

Ademas del alta, el modulo cubre lo que el mostrador necesita en el dia a
dia: edicion con auditoria, deduplicacion por documento, ficha 360 (envios,
cobranza, incidencias), historial como remitente y destinatario, gestion de
direcciones (principal, edicion, baja) y exportacion para el administrador.
"""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, request
from sqlalchemy import and_, case, func, or_, union_all

from app.extensions import conexion
from app.models import (
    AuditoriaModel, ClienteModel, DireccionModel, EstadoPedidoModel, IncidenciaModel, PagoModel,
    PedidoModel, UsuarioModel,
)
from app.core.seguridad import (
    requiereRol, auditar, usuarioActualId, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorNegocio, ErrorValidacion, cuerpoJson, texto, entero, coordenada, email, telefono,
    booleano, opcion, documentoIdentidad, paginacion,
)
from app.reglas import ESTADOS_ACTIVOS, aDecimal
from app.schemas import (
    ClienteDto, DireccionDto, PedidoDto,
)
from app.servicios import (
    agenciaDelUsuario, exigirZonaActiva, filtrarPorAgencia, idsEstados, obtener, patronBusqueda,
)


bp = Blueprint('clientes', __name__)

TIPOS_CLIENTE = ('persona', 'empresa')
ORDENES = ('nombre', 'recientes', 'actividad')
# Campos editables y como se validan. El orden importa solo para el mensaje.
CAMPOS_AUDITABLES = ('tipoCliente', 'nombre', 'tipoDocumento', 'dni', 'telefono', 'telefonoAlternativo',
                     'email', 'notas', 'recibeAvisos')


# ------------------------------------------------------------ Helpers ----

def _leerCliente(data, actual=None):
    """Valida el cuerpo de alta/edicion. En edicion solo cambia lo que llega
    (un campo ausente conserva su valor)."""
    def presente(campo):
        return actual is None or campo in data

    valores = {}
    if presente('nombre'):
        valores['nombre'] = texto(data, 'nombre', requerido=True, maximo=100, minimo=2)
    if presente('telefono'):
        valores['telefono'] = telefono(data, requerido=True)
    if presente('telefonoAlternativo'):
        valores['telefonoAlternativo'] = telefono(data, 'telefonoAlternativo')
    if presente('email'):
        valores['email'] = email(data, requerido=False)
    if presente('notas'):
        valores['notas'] = texto(data, 'notas', maximo=1000)
    if presente('dni') or presente('tipoDocumento'):
        fuente = data if actual is None else {
            'tipoDocumento': data.get('tipoDocumento', actual.tipoDocumento),
            'dni': data.get('dni', actual.dni),
        }
        valores['tipoDocumento'], valores['dni'] = documentoIdentidad(fuente)

    tipoDoc = valores.get('tipoDocumento', actual.tipoDocumento if actual else None)
    numDoc = valores.get('dni', actual.dni if actual else None)
    tipoCliente = opcion(data, 'tipoCliente', TIPOS_CLIENTE)
    if tipoCliente is None:
        tipoCliente = actual.tipoCliente if actual else (
            'empresa' if tipoDoc == 'RUC' and (numDoc or '').startswith('20') else 'persona')
    if tipoCliente == 'empresa' and tipoDoc != 'RUC':
        raise ErrorValidacion('Una empresa se registra con su RUC (para poder emitirle factura)')
    if tipoCliente == 'persona' and tipoDoc == 'RUC' and (numDoc or '').startswith('20'):
        raise ErrorValidacion('Un RUC que empieza en 20 pertenece a una empresa: marca el cliente como empresa')
    valores['tipoCliente'] = tipoCliente
    return valores


def _exigirDocumentoUnico(numero, excluirId=None):
    """Un mismo documento no puede pertenecer a dos clientes: evita fichas
    duplicadas que parten el historial y la cobranza en dos."""
    if not numero:
        return
    query = conexion.session.query(ClienteModel).filter(ClienteModel.dni == numero)
    if excluirId:
        query = query.filter(ClienteModel.id != excluirId)
    existente = query.first()
    if existente:
        estado = '' if existente.activo else ' (desactivado: puedes reactivarlo)'
        raise ErrorNegocio(f'Ya existe un cliente con ese documento: {existente.nombre} '
                           f'(#{existente.id}){estado}', 409)


def _comoParticipante(clienteId):
    """Pedidos en los que el cliente envia o recibe."""
    return or_(PedidoModel.clienteId == clienteId, PedidoModel.remitenteId == clienteId)


def _comoPagador(clienteId):
    """Misma regla que comprobantes: en contra entrega paga el destinatario,
    si no, el remitente (si se registro)."""
    pagaDestinatario = or_(PedidoModel.modalidadPago == 'contra_entrega', PedidoModel.remitenteId.is_(None))
    return or_(
        and_(pagaDestinatario, PedidoModel.clienteId == clienteId),
        and_(~pagaDestinatario, PedidoModel.remitenteId == clienteId),
    )


def _pedidosVisibles():
    return filtrarPorAgencia(conexion.session.query(PedidoModel), agenciaDelUsuario())


def _actividadPorCliente():
    """Subconsulta (clienteId, ultimaActividad, envios) uniendo los dos roles.
    Un pedido donde remitente y destinatario son el mismo cuenta una vez."""
    agencia = agenciaDelUsuario()

    def rol(columna, excluirMismo=False):
        q = conexion.session.query(columna.label('cid'), PedidoModel.fechaCreacion.label('fecha'),
                                   PedidoModel.estadoId.label('estado')).filter(columna.isnot(None))
        if excluirMismo:
            q = q.filter(PedidoModel.clienteId != columna)
        return filtrarPorAgencia(q, agencia).statement

    union = union_all(rol(PedidoModel.clienteId), rol(PedidoModel.remitenteId, excluirMismo=True)).subquery()
    activos = idsEstados(ESTADOS_ACTIVOS) or [-1]
    return conexion.session.query(
        union.c.cid.label('cid'),
        func.max(union.c.fecha).label('ultima'),
        func.count().label('envios'),
        func.sum(case((union.c.estado.in_(activos), 1), else_=0)).label('en_curso'),
    ).group_by(union.c.cid).subquery()


def _filtrosListado(query):
    estado = request.args.get('estado', 'activos')
    if estado == 'activos':
        query = query.filter(ClienteModel.activo.is_(True))
    elif estado == 'inactivos':
        query = query.filter(ClienteModel.activo.is_(False))

    tipo = request.args.get('tipo')
    if tipo in TIPOS_CLIENTE:
        query = query.filter(ClienteModel.tipoCliente == tipo)

    if request.args.get('avisos') in ('si', 'no'):
        query = query.filter(ClienteModel.recibeAvisos.is_(request.args['avisos'] == 'si'))

    buscar = request.args.get('q')
    if buscar:
        patron = patronBusqueda(buscar)
        limpio = patronBusqueda(''.join(c for c in buscar if c not in ' -().'))
        query = query.filter(
            ClienteModel.nombre.ilike(patron, escape='\\') |
            ClienteModel.telefono.ilike(limpio, escape='\\') |
            ClienteModel.telefonoAlternativo.ilike(limpio, escape='\\') |
            ClienteModel.dni.ilike(limpio, escape='\\') |
            ClienteModel.email.ilike(patron, escape='\\')
        )
    return query


def _dumpCliente(cliente, extra=None):
    datos = ClienteDto().dump(cliente)
    if extra:
        datos.update(extra)
    return datos


# ---------------------------------------------------------- Listados ----

@bp.route('/clientes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarClientes():
    """Sin `pagina`: lista simple (hasta 500) para los selectores de
    admision, pedidos y recojos. Con `pagina`: listado de gestion paginado,
    con filtros, orden, actividad de cada cliente y resumen general."""
    if 'pagina' not in request.args:
        query = conexion.session.query(ClienteModel)
        if request.args.get('incluir_inactivos') != 'true':
            query = query.filter_by(activo=True)
        buscar = request.args.get('q')
        if buscar:
            patron = patronBusqueda(buscar)
            query = query.filter(
                ClienteModel.nombre.ilike(patron, escape='\\') |
                ClienteModel.telefono.ilike(patron, escape='\\') |
                ClienteModel.dni.ilike(patron, escape='\\')
            )
        resultado = query.order_by(ClienteModel.nombre).limit(500).all()
        return {'content': ClienteDto().dump(resultado, many=True)}, 200

    actividad = _actividadPorCliente()
    query = _filtrosListado(
        conexion.session.query(ClienteModel, actividad.c.ultima, actividad.c.envios, actividad.c.en_curso)
        .outerjoin(actividad, actividad.c.cid == ClienteModel.id)
    )
    orden = request.args.get('orden', 'nombre')
    if orden == 'recientes':
        query = query.order_by(ClienteModel.fechaCreacion.desc(), ClienteModel.id.desc())
    elif orden == 'actividad':
        # (ultima IS NULL) primero en falso: los que nunca enviaron quedan al final (MySQL no tiene NULLS LAST)
        query = query.order_by(actividad.c.ultima.is_(None), actividad.c.ultima.desc(), ClienteModel.nombre)
    else:
        query = query.order_by(ClienteModel.nombre, ClienteModel.id)

    pagina, porPagina = paginacion()
    total = query.order_by(None).count()
    filas = query.offset((pagina - 1) * porPagina).limit(porPagina).all()
    contenido = [_dumpCliente(c, {
        'ultimaActividad': ultima.isoformat() if ultima else None,
        'totalEnvios': int(envios or 0),
        'enviosEnCurso': int(enCurso or 0),
    }) for c, ultima, envios, enCurso in filas]

    resumen = conexion.session.query(
        func.count(ClienteModel.id),
        func.sum(case((ClienteModel.activo.is_(True), 1), else_=0)),
        func.sum(case((ClienteModel.tipoCliente == 'empresa', 1), else_=0)),
        func.sum(case((and_(ClienteModel.activo.is_(True), ClienteModel.dni.is_(None)), 1), else_=0)),
        func.sum(case((and_(ClienteModel.activo.is_(True), ClienteModel.recibeAvisos.is_(False)), 1), else_=0)),
    ).one()
    return {
        'content': contenido,
        'paginacion': {
            'pagina': pagina, 'porPagina': porPagina, 'totalRegistros': total,
            'totalPaginas': (total + porPagina - 1) // porPagina,
        },
        'resumen': {
            'total': int(resumen[0] or 0),
            'activos': int(resumen[1] or 0),
            'inactivos': int(resumen[0] or 0) - int(resumen[1] or 0),
            'empresas': int(resumen[2] or 0),
            'sinDocumento': int(resumen[3] or 0),
            'sinAvisos': int(resumen[4] or 0),
        },
    }, 200


@bp.route('/clientes/verificar', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def verificarDuplicados():
    """Mientras se llena el formulario: avisa si el documento ya existe
    (bloquea) o si el telefono/correo ya los usa otro cliente (solo advierte:
    una familia puede compartir telefono)."""
    excluir = request.args.get('excluir', type=int)

    def coincidencias(columna, valor):
        if not valor:
            return []
        q = conexion.session.query(ClienteModel).filter(columna == valor)
        if excluir:
            q = q.filter(ClienteModel.id != excluir)
        return [{'id': c.id, 'nombre': c.nombre, 'activo': bool(c.activo)} for c in q.limit(5).all()]

    numDoc = ''.join(ch for ch in (request.args.get('dni') or '') if ch.isalnum()).upper()
    tel = ''.join(ch for ch in (request.args.get('telefono') or '') if ch.isdigit() or ch == '+')
    correo = (request.args.get('email') or '').strip().lower()
    return {'content': {
        'documento': coincidencias(ClienteModel.dni, numDoc),
        'telefono': coincidencias(ClienteModel.telefono, tel),
        'email': coincidencias(ClienteModel.email, correo),
    }}, 200


@bp.route('/clientes/exportar', methods=['GET'])
@requiereRol('admin')
def exportarClientes():
    """CSV para Excel (separador ; y BOM UTF-8). Exportar datos personales
    es una accion sensible: solo el administrador y queda auditada."""
    query = _filtrosListado(conexion.session.query(ClienteModel)).order_by(ClienteModel.nombre)
    clientes = query.all()

    def celda(valor):
        texto_ = '' if valor is None else str(valor)
        # Evita inyeccion de formulas al abrir el archivo en Excel
        return "'" + texto_ if texto_[:1] in ('=', '+', '-', '@') else texto_

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(['ID', 'Tipo', 'Nombre / Razon social', 'Tipo doc.', 'Documento', 'Telefono',
                       'Telefono alterno', 'Correo', 'Recibe avisos', 'Activo', 'Fecha de registro'])
    for c in clientes:
        escritor.writerow([celda(v) for v in (
            c.id, c.tipoCliente, c.nombre, c.tipoDocumento, c.dni, c.telefono, c.telefonoAlternativo,
            c.email, 'si' if c.recibeAvisos else 'no', 'si' if c.activo else 'no',
            c.fechaCreacion.strftime('%Y-%m-%d %H:%M') if c.fechaCreacion else '',
        )])
    auditar('clientes_exportados', 'cliente', None, {
        'registros': len(clientes), 'filtros': {k: v for k, v in request.args.items()}})
    conexion.session.commit()

    nombre = f'clientes_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    return Response('﻿' + salida.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{nombre}"'})


# ------------------------------------------------------------ Ficha ----

@bp.route('/cliente', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearCliente():
    data = cuerpoJson()
    valores = _leerCliente(data)
    _exigirDocumentoUnico(valores['dni'])
    nuevo = ClienteModel(
        **valores,
        recibeAvisos=booleano(data, 'recibeAvisos', defecto=True),
        fechaConsentimiento=func.now(),  # mismo reloj que fechaCreacion y auditoria
        creadoPorId=usuarioActualId(),
    )
    conexion.session.add(nuevo)
    conexion.session.flush()
    auditar('cliente_creado', 'cliente', nuevo.id)
    conexion.session.commit()
    return {'content': ClienteDto().dump(nuevo)}, 201


@bp.route('/cliente/<int:id>', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def obtenerCliente(id):
    """Ficha 360: datos, direcciones y como se comporta como cliente."""
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    base = _pedidosVisibles().filter(_comoParticipante(id))

    porEstado = dict(
        base.join(EstadoPedidoModel, EstadoPedidoModel.id == PedidoModel.estadoId)
        .with_entities(EstadoPedidoModel.nombre, func.count(PedidoModel.id))
        .group_by(EstadoPedidoModel.nombre).all()
    )
    entregados = porEstado.get('entregado', 0)
    devueltos = porEstado.get('devuelto', 0)
    cerrados = entregados + devueltos

    idCancelado = idsEstados(['cancelado']) or [-1]
    pagador = _pedidosVisibles().filter(_comoPagador(id), PedidoModel.estadoId.notin_(idCancelado))
    facturado = aDecimal(pagador.with_entities(func.sum(PedidoModel.monto)).scalar())
    cobrado = aDecimal(pagador.join(PagoModel, PagoModel.pedidoId == PedidoModel.id)
                       .filter(PagoModel.estadoPago == 'pagado')
                       .with_entities(func.sum(PagoModel.monto)).scalar())
    fechas = base.with_entities(func.min(PedidoModel.fechaCreacion), func.max(PedidoModel.fechaCreacion)).one()
    incidencias = (base.join(IncidenciaModel, IncidenciaModel.pedidoId == PedidoModel.id)
                   .filter(IncidenciaModel.estado != 'resuelta')
                   .with_entities(func.count(IncidenciaModel.id)).scalar())

    direcciones = (conexion.session.query(DireccionModel).filter_by(clienteId=id, activo=True)
                   .order_by(DireccionModel.esPrincipal.desc(), DireccionModel.id).all())
    creador = conexion.session.get(UsuarioModel, cliente.creadoPorId) if cliente.creadoPorId else None

    return {'content': {
        'cliente': ClienteDto().dump(cliente),
        'creadoPor': creador.nombre if creador else None,
        'direcciones': DireccionDto().dump(direcciones, many=True),
        'estadisticas': {
            'enviados': base.filter(PedidoModel.remitenteId == id).count(),
            'recibidos': base.filter(PedidoModel.clienteId == id).count(),
            'total': sum(porEstado.values()),
            'enCurso': sum(porEstado.get(e, 0) for e in ESTADOS_ACTIVOS),
            'entregados': entregados,
            'devueltos': devueltos,
            'cancelados': porEstado.get('cancelado', 0),
            'tasaEntrega': round(entregados * 100 / cerrados, 1) if cerrados else None,
            'montoFacturado': str(facturado),
            'montoCobrado': str(cobrado),
            'saldoPendiente': str(max(facturado - cobrado, aDecimal(0))),
            'incidenciasAbiertas': int(incidencias or 0),
            'primerEnvio': fechas[0].isoformat() if fechas[0] else None,
            'ultimoEnvio': fechas[1].isoformat() if fechas[1] else None,
        },
    }}, 200


@bp.route('/cliente/<int:id>', methods=['PUT'])
@requiereRol(*ROLES_STAFF)
def editarCliente(id):
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    data = cuerpoJson()
    valores = _leerCliente(data, actual=cliente)
    if 'dni' in valores:
        _exigirDocumentoUnico(valores['dni'], excluirId=id)
    if 'recibeAvisos' in data:
        valores['recibeAvisos'] = booleano(data, 'recibeAvisos', defecto=True)

    # Se auditan los NOMBRES de los campos cambiados, no los valores:
    # la auditoria no debe convertirse en otra copia de datos personales.
    cambiados = [c for c in CAMPOS_AUDITABLES if c in valores and getattr(cliente, c) != valores[c]]
    if not cambiados:
        return {'message': 'No hubo cambios', 'content': ClienteDto().dump(cliente)}, 200
    if 'recibeAvisos' in cambiados:
        cliente.fechaConsentimiento = func.now()
    for campo in cambiados:
        setattr(cliente, campo, valores[campo])
    auditar('cliente_editado', 'cliente', id, {'campos': cambiados})
    conexion.session.commit()
    return {'message': 'Cliente actualizado', 'content': ClienteDto().dump(cliente)}, 200


@bp.route('/cliente/<int:id>/avisos', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def preferenciaAvisos(id):
    """El cliente pide (o deja de pedir) avisos de sus envios por WhatsApp o
    correo. Queda auditado: es su consentimiento (Ley 29733)."""
    data = cuerpoJson()
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    cliente.recibeAvisos = booleano(data, 'recibeAvisos', defecto=True)
    cliente.fechaConsentimiento = func.now()
    auditar('avisos_' + ('activados' if cliente.recibeAvisos else 'desactivados'), 'cliente', id)
    conexion.session.commit()
    return {'message': 'Preferencia de avisos actualizada', 'content': ClienteDto().dump(cliente)}, 200


@bp.route('/cliente/<int:id>/desactivar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def desactivarCliente(id):
    data = cuerpoJson()
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    enCurso = conexion.session.query(PedidoModel.id).filter(
        _comoParticipante(id), PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS) or [-1])
    ).count()
    if enCurso:
        raise ErrorNegocio(f'El cliente tiene {enCurso} envio(s) en curso. Espera a que se entreguen, '
                           'devuelvan o cancelen antes de desactivarlo', 409)
    cliente.activo = False
    cliente.motivoDesactivacion = texto(data, 'motivo', maximo=200)
    auditar('cliente_desactivado', 'cliente', id, {'motivo': cliente.motivoDesactivacion})
    conexion.session.commit()
    return {'message': 'Cliente desactivado exitosamente', 'content': ClienteDto().dump(cliente)}, 200


@bp.route('/cliente/<int:id>/activar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def activarCliente(id):
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    cliente.activo = True
    cliente.motivoDesactivacion = None
    auditar('cliente_activado', 'cliente', id)
    conexion.session.commit()
    return {'message': 'Cliente activado exitosamente', 'content': ClienteDto().dump(cliente)}, 200


@bp.route('/cliente/<int:id>/pedidos', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def pedidosDelCliente(id):
    """Historial del cliente en sus dos roles (remitente y destinatario)."""
    obtener(ClienteModel, id, 'Cliente no existe')
    rol = request.args.get('rol', 'todos')
    query = _pedidosVisibles()
    if rol == 'remitente':
        query = query.filter(PedidoModel.remitenteId == id)
    elif rol == 'destinatario':
        query = query.filter(PedidoModel.clienteId == id)
    else:
        query = query.filter(_comoParticipante(id))
    if request.args.get('estado'):
        query = query.filter(PedidoModel.estadoId.in_(idsEstados([request.args['estado']]) or [-1]))

    query = query.order_by(PedidoModel.fechaCreacion.desc(), PedidoModel.id.desc())
    pagina, porPagina = paginacion()
    total = query.order_by(None).count()
    pedidos = query.offset((pagina - 1) * porPagina).limit(porPagina).all()

    estados = {e.id: e.nombre for e in conexion.session.query(EstadoPedidoModel).all()}
    otrosIds = {p.remitenteId if p.clienteId == id else p.clienteId for p in pedidos} - {None}
    nombres = dict(conexion.session.query(ClienteModel.id, ClienteModel.nombre)
                   .filter(ClienteModel.id.in_(otrosIds)).all()) if otrosIds else {}
    contenido = []
    for p in pedidos:
        datos = PedidoDto().dump(p)
        esDestinatario = p.clienteId == id
        contraparte = p.remitenteId if esDestinatario else p.clienteId
        datos.update({
            'estado': estados.get(p.estadoId),
            'rolCliente': 'destinatario' if esDestinatario else 'remitente',
            'contraparte': nombres.get(contraparte) if contraparte != id else None,
        })
        contenido.append(datos)
    return {'content': contenido, 'paginacion': {
        'pagina': pagina, 'porPagina': porPagina, 'totalRegistros': total,
        'totalPaginas': (total + porPagina - 1) // porPagina,
    }}, 200


@bp.route('/cliente/<int:id>/actividad', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def actividadCliente(id):
    """Bitacora de la ficha: alta, ediciones, consentimiento, bajas y
    cambios en sus direcciones (quien y cuando)."""
    obtener(ClienteModel, id, 'Cliente no existe')
    idsDirecciones = [d for (d,) in conexion.session.query(DireccionModel.id).filter_by(clienteId=id).all()]
    condicion = and_(AuditoriaModel.entidad == 'cliente', AuditoriaModel.entidadId == id)
    if idsDirecciones:
        condicion = or_(condicion, and_(AuditoriaModel.entidad == 'direccion',
                                        AuditoriaModel.entidadId.in_(idsDirecciones)))
    filas = (conexion.session.query(AuditoriaModel, UsuarioModel.nombre)
             .outerjoin(UsuarioModel, UsuarioModel.id == AuditoriaModel.usuarioId)
             .filter(condicion).order_by(AuditoriaModel.fecha.desc(), AuditoriaModel.id.desc()).limit(50).all())
    return {'content': [{
        'id': a.id, 'accion': a.accion, 'entidad': a.entidad, 'detalle': a.detalle,
        'usuario': nombre, 'fecha': a.fecha.isoformat() if a.fecha else None,
    } for a, nombre in filas]}, 200


# ---------------------------------------------- Direcciones del cliente ----

def _leerDireccion(data, actual=None):
    def presente(campo):
        return actual is None or campo in data

    valores = {}
    if presente('zonaId'):
        valores['zonaId'] = entero(data, 'zonaId')
        exigirZonaActiva(valores['zonaId'])
    if presente('etiqueta'):
        valores['etiqueta'] = texto(data, 'etiqueta', maximo=50)
    if presente('calle'):
        valores['calle'] = texto(data, 'calle', requerido=True, maximo=300, minimo=3)
    if presente('referencia'):
        valores['referencia'] = texto(data, 'referencia', maximo=500)
    if presente('latitud'):
        valores['latitud'] = coordenada(data, 'latitud', 'lat')
    if presente('longitud'):
        valores['longitud'] = coordenada(data, 'longitud', 'lon')
    return valores


def _marcarPrincipal(direccion):
    conexion.session.query(DireccionModel).filter(
        DireccionModel.clienteId == direccion.clienteId, DireccionModel.id != direccion.id
    ).update({DireccionModel.esPrincipal: False}, synchronize_session=False)
    direccion.esPrincipal = True


def _pedidosActivosEnDireccion(direccionId):
    return conexion.session.query(PedidoModel.id).filter(
        PedidoModel.direccionEntregaId == direccionId,
        PedidoModel.estadoId.in_(idsEstados(ESTADOS_ACTIVOS) or [-1]),
    ).count()


@bp.route('/direccion-cliente', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearDireccionCliente():
    data = cuerpoJson()
    clienteId = entero(data, 'clienteId', requerido=True)
    cliente = obtener(ClienteModel, clienteId, 'El cliente no existe')
    if not cliente.activo:
        raise ErrorValidacion('El cliente esta desactivado')

    nueva = DireccionModel(clienteId=clienteId, **_leerDireccion(data))
    conexion.session.add(nueva)
    conexion.session.flush()
    tieneOtras = conexion.session.query(DireccionModel.id).filter(
        DireccionModel.clienteId == clienteId, DireccionModel.activo.is_(True), DireccionModel.id != nueva.id
    ).first()
    # La primera direccion del cliente siempre queda como principal
    if booleano(data, 'esPrincipal', defecto=False) or not tieneOtras:
        _marcarPrincipal(nueva)
    auditar('direccion_creada', 'direccion', nueva.id)
    conexion.session.commit()
    return {'content': DireccionDto().dump(nueva)}, 201


@bp.route('/direccion-cliente/<int:id>', methods=['PUT'])
@requiereRol(*ROLES_STAFF)
def editarDireccionCliente(id):
    direccion = obtener(DireccionModel, id, 'La direccion no existe')
    if not direccion.activo:
        raise ErrorValidacion('La direccion fue eliminada')
    data = cuerpoJson()
    valores = _leerDireccion(data, actual=direccion)
    cambiados = [c for c, v in valores.items() if getattr(direccion, c) != v]
    # Cambiar la calle de una direccion con envios en curso desviaria al
    # repartidor sin que nadie lo note: se pide crear una nueva.
    if {'calle', 'zonaId'} & set(cambiados) and _pedidosActivosEnDireccion(id):
        raise ErrorNegocio('Esta direccion tiene envios en curso: no se puede cambiar la calle ni la zona. '
                           'Registra una direccion nueva', 409)
    for campo in cambiados:
        setattr(direccion, campo, valores[campo])
    if booleano(data, 'esPrincipal', defecto=False):
        _marcarPrincipal(direccion)
        cambiados.append('esPrincipal')
    if cambiados:
        auditar('direccion_editada', 'direccion', id, {'campos': cambiados})
    conexion.session.commit()
    return {'content': DireccionDto().dump(direccion)}, 200


@bp.route('/direccion-cliente/<int:id>/principal', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def principalDireccionCliente(id):
    direccion = obtener(DireccionModel, id, 'La direccion no existe')
    if not direccion.activo:
        raise ErrorValidacion('La direccion fue eliminada')
    _marcarPrincipal(direccion)
    auditar('direccion_principal', 'direccion', id)
    conexion.session.commit()
    return {'content': DireccionDto().dump(direccion)}, 200


@bp.route('/direccion-cliente/<int:id>/desactivar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def desactivarDireccionCliente(id):
    """Baja logica: los envios antiguos siguen apuntando a ella."""
    direccion = obtener(DireccionModel, id, 'La direccion no existe')
    if _pedidosActivosEnDireccion(id):
        raise ErrorNegocio('Esta direccion tiene envios en curso; podras eliminarla cuando terminen', 409)
    direccion.activo = False
    eraPrincipal = direccion.esPrincipal
    direccion.esPrincipal = False
    if eraPrincipal:
        siguiente = (conexion.session.query(DireccionModel)
                     .filter(DireccionModel.clienteId == direccion.clienteId, DireccionModel.activo.is_(True),
                             DireccionModel.id != id)
                     .order_by(DireccionModel.id).first())
        if siguiente:
            siguiente.esPrincipal = True
    auditar('direccion_eliminada', 'direccion', id)
    conexion.session.commit()
    return {'message': 'Direccion eliminada'}, 200


@bp.route('/cliente/<int:clienteId>/direcciones', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarDireccionesCliente(clienteId):
    resultado = (conexion.session.query(DireccionModel).filter_by(clienteId=clienteId, activo=True)
                 .order_by(DireccionModel.esPrincipal.desc(), DireccionModel.id).all())
    return {'content': DireccionDto().dump(resultado, many=True)}, 200
