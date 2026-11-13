"""Boletas y facturas electronicas via Nubefact (PSE autorizado por SUNAT).

Reglas que aplica (SUNAT):
- Factura: solo a un RUC valido (digito verificador), con razon social y direccion.
- Boleta: con DNI (u otro documento); sin documento solo si el total es menor
  a S/ 700.
- Numeracion correlativa SIN saltos por serie (B001, F001): el numero se toma
  bloqueando la fila de la serie, en la misma transaccion.
- El servicio de courier esta gravado con IGV: gravada = total / 1.18.
- Un comprobante solo es valido cuando Nubefact lo acepta. Si la facturacion
  no esta configurada, NO se emite nada (no se consumen numeros).
- El numero se reserva y se GUARDA antes de llamar a Nubefact: si la llamada
  falla o se cae la conexion, el comprobante queda en "error" con su numero y
  se reintenta con el mismo (nunca un comprobante aceptado sin registro local).
- Un comprobante emitido no se borra: se anula o reduce con una NOTA DE
  CREDITO (serie BC01 / FC01) cuando se devuelve dinero al cliente.
- Si despues se cobra algo mas (cargo de devolucion, diferencia de tarifa),
  se emite otro comprobante solo por lo que falta facturar.
"""
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from flask import Blueprint, current_app

from app.extensions import conexion
from app.models import (
    AlmacenModel, ClienteModel, ComprobanteModel, PedidoModel, SerieComprobanteModel,
)
from app.finanzas import cargosPagados, fletePagado, reembolsado
from app.notificaciones import _postJson
from app.core.seguridad import auditar, requiereRol, usuarioActualId, ROLES_STAFF
from app.core.validacion import ErrorNegocio, ErrorValidacion, cuerpoJson, email, opcion, texto
from app.reglas import ahoraUtc
from app.servicios import agenciaReparto, exigirAccesoPedido, obtener

bp = Blueprint('comprobantes', __name__)

CENTIMO = Decimal('0.01')
LIMITE_BOLETA_SIN_DOC = Decimal('700.00')
PESOS_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def rucValido(ruc):
    """Digito verificador del RUC (modulo 11) y prefijos validos."""
    if not re.fullmatch(r'\d{11}', ruc or '') or ruc[:2] not in ('10', '15', '16', '17', '20'):
        return False
    resto = 11 - sum(int(d) * p for d, p in zip(ruc[:10], PESOS_RUC)) % 11
    verificador = {10: 0, 11: 1}.get(resto, resto)
    return verificador == int(ruc[10])


def desglosarIgv(total, porcentaje):
    """total incluye IGV: gravada = total / (1 + igv%), igv = total - gravada."""
    total = Decimal(total).quantize(CENTIMO)
    gravada = (total / (1 + Decimal(porcentaje) / 100)).quantize(CENTIMO, rounding=ROUND_HALF_UP)
    return gravada, total - gravada, total


def facturacionConfigurada():
    return bool(current_app.config['NUBEFACT_URL'] and current_app.config['NUBEFACT_TOKEN'])


VALIDOS = ('aceptado', 'pendiente')  # 'error' se reintenta; 'rechazado' no cuenta


def _totalPagado(pedidoId):
    """Lo cobrado al cliente por el servicio (flete + cargos) menos lo devuelto."""
    return fletePagado(pedidoId) + cargosPagados(pedidoId) - reembolsado(pedidoId, 'devolucion_flete')


def _facturado(pedidoId):
    """Total de boletas/facturas vigentes menos sus notas de credito."""
    filas = conexion.session.query(ComprobanteModel).filter(
        ComprobanteModel.pedidoId == pedidoId, ComprobanteModel.estado.in_(VALIDOS + ('error',))).all()
    total = Decimal('0.00')
    for c in filas:
        total += -Decimal(c.total) if c.tipo == 'nota' else Decimal(c.total)
    return total


def comprobanteVigente(pedidoId):
    """Ultima boleta/factura valida del envio: la que modifica una nota de credito."""
    return conexion.session.query(ComprobanteModel).filter(
        ComprobanteModel.pedidoId == pedidoId, ComprobanteModel.tipo.in_(('boleta', 'factura')),
        ComprobanteModel.estado.in_(VALIDOS)).order_by(ComprobanteModel.id.desc()).first()


def _pagador(pedido):
    """Quien paga: en contra entrega, el destinatario; si no, el remitente."""
    if pedido.modalidadPago == 'contra_entrega' or not pedido.remitenteId:
        return conexion.session.get(ClienteModel, pedido.clienteId)
    return conexion.session.get(ClienteModel, pedido.remitenteId)


def _siguienteNumero(serie, tipo):
    fila = conexion.session.query(SerieComprobanteModel).filter_by(serie=serie).with_for_update().first()
    if not fila:
        fila = SerieComprobanteModel(serie=serie, tipo=tipo, ultimoNumero=0)
        conexion.session.add(fila)
        conexion.session.flush()
    fila.ultimoNumero += 1
    return fila.ultimoNumero


def _serializar(c):
    return {
        'id': c.id, 'tipo': c.tipo, 'serie': c.serie, 'numero': c.numero,
        'numeroCompleto': f'{c.serie}-{c.numero:08d}',
        'clienteTipoDoc': c.clienteTipoDoc, 'clienteNumDoc': c.clienteNumDoc, 'clienteNombre': c.clienteNombre,
        'descripcion': c.descripcion, 'gravada': str(c.gravada), 'igv': str(c.igv), 'total': str(c.total),
        'estado': c.estado, 'mensajeSunat': c.mensajeSunat, 'enlacePdf': c.enlacePdf,
        'comprobanteRefId': c.comprobanteRefId, 'motivoNota': c.motivoNota,
        'fechaEmision': c.fechaEmision.isoformat(),
    }


def _enviarANubefact(c):
    """Envia el comprobante y actualiza su estado segun la respuesta."""
    config = current_app.config
    cuerpo = {
        'operacion': 'generar_comprobante',
        'tipo_de_comprobante': {'factura': 1, 'boleta': 2, 'nota': 3}[c.tipo],
        'serie': c.serie,
        'numero': c.numero,
        'sunat_transaction': 1,
        'cliente_tipo_de_documento': c.clienteTipoDoc,
        'cliente_numero_de_documento': c.clienteNumDoc or '-',
        'cliente_denominacion': c.clienteNombre,
        'cliente_direccion': c.clienteDireccion or '',
        'cliente_email': c.clienteEmail or '',
        'fecha_de_emision': c.fechaEmision.strftime('%d-%m-%Y'),
        'moneda': 1,  # soles
        'porcentaje_de_igv': float(config['IGV_PORCENTAJE']),
        'total_gravada': float(c.gravada),
        'total_igv': float(c.igv),
        'total': float(c.total),
        'enviar_automaticamente_a_la_sunat': True,
        'enviar_automaticamente_al_cliente': bool(c.clienteEmail),
        'items': [{
            'unidad_de_medida': 'ZZ',  # servicio
            'codigo': f'ENV-{c.pedidoId}',
            'descripcion': c.descripcion,
            'cantidad': 1,
            'valor_unitario': float(c.gravada),
            'precio_unitario': float(c.total),
            'subtotal': float(c.gravada),
            'tipo_de_igv': 1,  # gravado - operacion onerosa
            'igv': float(c.igv),
            'total': float(c.total),
            'anticipo_regularizacion': False,
        }],
    }
    if c.tipo == 'nota':
        original = conexion.session.get(ComprobanteModel, c.comprobanteRefId)
        anulaTodo = Decimal(c.total) >= Decimal(original.total)
        cuerpo.update({
            'documento_que_se_modifica_tipo': 1 if original.tipo == 'factura' else 2,
            'documento_que_se_modifica_serie': original.serie,
            'documento_que_se_modifica_numero': original.numero,
            # Catalogo 09: 1 = anulacion de la operacion, 9 = disminucion en el valor
            'tipo_de_nota_de_credito': 1 if anulaTodo else 9,
        })
    try:
        respuesta = _postJson(config['NUBEFACT_URL'], cuerpo, {'Authorization': f"Token token=\"{config['NUBEFACT_TOKEN']}\""},
                              timeout=20)
    except Exception as error:  # noqa: BLE001  caida/timeout: se reintenta con el mismo numero
        c.estado = 'error'
        c.mensajeSunat = str(error)[:500]
        return
    if respuesta.get('errors'):
        c.estado = 'error'
        c.mensajeSunat = str(respuesta['errors'])[:500]
        return
    c.enlacePdf = respuesta.get('enlace_del_pdf') or respuesta.get('enlace')
    c.codigoHash = respuesta.get('codigo_hash')
    c.mensajeSunat = (respuesta.get('sunat_description') or '')[:500] or None
    if respuesta.get('aceptada_por_sunat'):
        c.estado = 'aceptado'
    elif respuesta.get('sunat_responsecode') not in (None, '', '0'):
        c.estado = 'rechazado'
    else:
        c.estado = 'pendiente'  # Nubefact lo recibio; SUNAT confirma despues


@bp.route('/pedido/<int:id>/comprobantes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def comprobantesDelPedido(id):
    pedido = obtener(PedidoModel, id, 'Pedido no existe')
    exigirAccesoPedido(pedido)
    filas = conexion.session.query(ComprobanteModel).filter_by(pedidoId=id).order_by(ComprobanteModel.id).all()
    pagador = _pagador(pedido)
    return {'content': {
        'comprobantes': [_serializar(c) for c in filas],
        'totalPagado': str(_totalPagado(id)),
        'facturacionConfigurada': facturacionConfigurada(),
        'sugerido': {'nombre': pagador.nombre if pagador else '', 'numDoc': (pagador.dni or '') if pagador else '',
                     'email': (pagador.email or '') if pagador else ''},
    }}, 200


@bp.route('/pedido/<int:id>/comprobante', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def emitirComprobante(id):
    data = cuerpoJson()
    tipo = opcion(data, 'tipo', ('boleta', 'factura'), requerido=True)
    numDoc = (texto(data, 'numDoc', maximo=15) or '').strip().upper()
    nombre = texto(data, 'nombre', requerido=True, maximo=150, minimo=3)
    direccion = texto(data, 'direccion', maximo=200)
    correo = email(data, 'email', requerido=False)

    pedido = obtener(PedidoModel, id, 'Pedido no existe', bloquear=True)
    exigirAccesoPedido(pedido)
    if not facturacionConfigurada():
        raise ErrorNegocio('La facturacion electronica no esta configurada (NUBEFACT_URL y NUBEFACT_TOKEN). '
                           'No se emitio nada', 409)
    if _totalPagado(id) <= 0:
        raise ErrorNegocio('Registra el pago del envio antes de emitir el comprobante', 409)
    total = _totalPagado(id) - _facturado(id)
    if total <= 0:
        vigente = comprobanteVigente(id)
        numero = f' ({vigente.serie}-{vigente.numero:08d})' if vigente else ''
        raise ErrorNegocio(f'Todo lo cobrado en este envio ya esta facturado{numero}', 409)

    if tipo == 'factura':
        if not rucValido(numDoc):
            raise ErrorValidacion('La factura requiere un RUC valido de 11 digitos')
        if not direccion:
            raise ErrorValidacion('La factura requiere la direccion fiscal del cliente')
        tipoDoc, serie = '6', current_app.config['SERIE_FACTURA']
    else:
        if not numDoc:
            if total >= LIMITE_BOLETA_SIN_DOC:
                raise ErrorValidacion('Una boleta de S/ 700 o mas requiere el DNI del cliente (norma SUNAT)')
            tipoDoc = '-'
        elif re.fullmatch(r'\d{8}', numDoc):
            tipoDoc = '1'  # DNI
        elif re.fullmatch(r'[A-Z0-9]{9,12}', numDoc):
            tipoDoc = '4'  # carnet de extranjeria
        else:
            raise ErrorValidacion('El documento debe ser un DNI de 8 digitos o un carnet de extranjeria')
        serie = current_app.config['SERIE_BOLETA']

    gravada, igv, total = desglosarIgv(total, current_app.config['IGV_PORCENTAJE'])
    origen = conexion.session.get(AlmacenModel, pedido.almacenId)
    destino = conexion.session.get(AlmacenModel, agenciaReparto(pedido))
    hoyLocal = (ahoraUtc() + timedelta(hours=current_app.config['UTC_OFFSET_HORAS'])).date()
    comprobante = ComprobanteModel(
        pedidoId=id, tipo=tipo, serie=serie, numero=_siguienteNumero(serie, tipo),
        clienteTipoDoc=tipoDoc, clienteNumDoc=numDoc or None, clienteNombre=nombre,
        clienteDireccion=direccion, clienteEmail=correo,
        descripcion=(f'Servicio de envio {pedido.tipoServicio} - guia {pedido.codigoGuia} '
                     f'({origen.nombre if origen else ""} a {destino.nombre if destino else ""})')[:250],
        gravada=gravada, igv=igv, total=total, emitidoPorId=usuarioActualId(), fechaEmision=hoyLocal,
    )
    conexion.session.add(comprobante)
    conexion.session.flush()
    auditar('comprobante_emitido', 'comprobante', comprobante.id, {
        'numero': f'{serie}-{comprobante.numero:08d}', 'total': total})
    enviarGuardado(comprobante)
    return {'message': f'Comprobante {serie}-{comprobante.numero:08d}: {comprobante.estado}',
            'content': _serializar(comprobante)}, 201


def enviarGuardado(comprobante):
    """Guarda el numero ANTES de llamar al PSE y el resultado DESPUES."""
    comprobante.estado = 'error'
    comprobante.mensajeSunat = 'Pendiente de envio'
    conexion.session.commit()
    _enviarANubefact(comprobante)
    conexion.session.commit()


def emitirNotaCredito(pedido, monto, motivo):
    """Nota de credito sobre el comprobante vigente del envio por el monto
    devuelto (la deja en la sesion; el llamador la envia con enviarGuardado).
    Sin comprobante emitido no hay nada que anular: devuelve None."""
    original = comprobanteVigente(pedido.id)
    if not original:
        return None
    if not facturacionConfigurada():
        raise ErrorNegocio('El envio tiene comprobante pero la facturacion no esta configurada: no se puede '
                           'emitir la nota de credito', 409)
    monto = min(Decimal(monto), Decimal(original.total))
    serie = current_app.config['SERIE_NOTA_FACTURA' if original.tipo == 'factura' else 'SERIE_NOTA_BOLETA']
    gravada, igv, total = desglosarIgv(monto, current_app.config['IGV_PORCENTAJE'])
    hoyLocal = (ahoraUtc() + timedelta(hours=current_app.config['UTC_OFFSET_HORAS'])).date()
    nota = ComprobanteModel(
        pedidoId=pedido.id, tipo='nota', serie=serie, numero=_siguienteNumero(serie, 'nota'),
        clienteTipoDoc=original.clienteTipoDoc, clienteNumDoc=original.clienteNumDoc,
        clienteNombre=original.clienteNombre, clienteDireccion=original.clienteDireccion,
        clienteEmail=original.clienteEmail, descripcion=f'Devolucion - {motivo}'[:250],
        gravada=gravada, igv=igv, total=total, emitidoPorId=usuarioActualId(), fechaEmision=hoyLocal,
        comprobanteRefId=original.id, motivoNota=motivo[:200],
    )
    conexion.session.add(nota)
    conexion.session.flush()
    auditar('nota_credito_emitida', 'comprobante', nota.id, {
        'numero': f'{serie}-{nota.numero:08d}', 'modifica': f'{original.serie}-{original.numero:08d}', 'total': total})
    return nota


@bp.route('/comprobante/<int:id>/reenviar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def reenviarComprobante(id):
    """Reintenta con el MISMO numero (no se pierde el correlativo)."""
    comprobante = obtener(ComprobanteModel, id, 'Comprobante no existe', bloquear=True)
    exigirAccesoPedido(conexion.session.get(PedidoModel, comprobante.pedidoId))
    if comprobante.estado not in ('error', 'pendiente'):
        raise ErrorNegocio(f'No se reenvia un comprobante en estado "{comprobante.estado}"', 409)
    if not facturacionConfigurada():
        raise ErrorNegocio('La facturacion electronica no esta configurada', 409)
    _enviarANubefact(comprobante)
    conexion.session.commit()
    return {'message': f'Comprobante {comprobante.serie}-{comprobante.numero:08d}: {comprobante.estado}',
            'content': _serializar(comprobante)}, 200
