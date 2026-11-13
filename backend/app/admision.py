"""Admision de envios en agencia: bultos, inspeccion y cotizacion.

Pasos 2 a 5 del proceso operativo:
  registro -> inspeccion y embalaje -> cotizacion -> guia y etiqueta
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from flask import current_app

from app.extensions import conexion
from app.models import AlmacenModel, BultoModel, EventoBultoModel
from app.core.seguridad import usuarioActualId
from app.servicios import buscarTarifa
from app.core.validacion import (
    ErrorValidacion, booleano, decimalPositivo, dinero, evidencia, opcion, texto,
)
from app.reglas import (
    EMBALAJES, ESTADOS_PRODUCTO, TIPOS_SERVICIO, ahoraUtc, cotizar, redondearPeso, resumirBultos,
)

MAX_PESO_BULTO_KG = Decimal('500')
MAX_LADO_CM = Decimal('300')


def leerBultos(data, requerido):
    """Valida la lista de bultos: peso real (balanza) y medidas (cinta)."""
    bultos = data.get('bultos')
    if bultos in (None, []):
        if requerido:
            raise ErrorValidacion('Registra al menos un bulto con su peso y sus medidas')
        return None
    if not isinstance(bultos, list):
        raise ErrorValidacion('"bultos" debe ser una lista')
    maximo = current_app.config['MAX_BULTOS_POR_ENVIO']
    if len(bultos) > maximo:
        raise ErrorValidacion(f'Un envio admite como maximo {maximo} bultos')

    leidos = []
    for i, b in enumerate(bultos, start=1):
        if not isinstance(b, dict):
            raise ErrorValidacion(f'El bulto {i} no tiene un formato valido')
        try:
            leidos.append({
                'pesoKg': decimalPositivo(b, 'pesoKg', requerido=True, maximo=MAX_PESO_BULTO_KG),
                'largoCm': decimalPositivo(b, 'largoCm', requerido=True, maximo=MAX_LADO_CM),
                'anchoCm': decimalPositivo(b, 'anchoCm', requerido=True, maximo=MAX_LADO_CM),
                'altoCm': decimalPositivo(b, 'altoCm', requerido=True, maximo=MAX_LADO_CM),
                'descripcion': texto(b, 'descripcion', maximo=120),
            })
        except ErrorValidacion as error:
            raise ErrorValidacion(f'Bulto {i}: {error.mensaje}')
    return leidos


def leerInspeccion(data):
    """Verificacion del producto y del embalaje al recibirlo en agencia."""
    estadoProducto = opcion(data, 'estadoProducto', ESTADOS_PRODUCTO, requerido=True)
    embalaje = opcion(data, 'embalaje', EMBALAJES, requerido=True)
    observaciones = texto(data, 'observacionesInspeccion', maximo=1000)
    foto = evidencia(data, 'fotoInspeccion')

    if not booleano(data, 'declaraSinProhibidos', defecto=False):
        raise ErrorValidacion('El remitente debe declarar que el envio no contiene articulos prohibidos '
                              '(explosivos, inflamables, dinero, drogas, armas, animales vivos...)')
    if embalaje == 'rechazado':
        raise ErrorValidacion('Embalaje rechazado: el paquete no cumple las condiciones de transporte. '
                              'Pide al cliente que lo reembale antes de admitirlo')
    if estadoProducto != 'bueno' and not observaciones:
        raise ErrorValidacion('Describe en las observaciones los detalles o danos del producto')
    if estadoProducto == 'danado' and not foto:
        raise ErrorValidacion('Si el producto llega danado, toma una foto: es el respaldo ante un reclamo')

    return {
        'estadoProducto': estadoProducto,
        'embalaje': embalaje,
        'declaraSinProhibidos': True,
        'observacionesInspeccion': observaciones,
        'fotoInspeccion': foto,
    }


def leerServicioYValor(data):
    servicio = opcion(data, 'tipoServicio', TIPOS_SERVICIO, defecto='estandar')
    valor = dinero(data, 'valorDeclarado', maximo=Decimal(current_app.config['VALOR_DECLARADO_MAXIMO']))
    return servicio, (valor or Decimal('0.00'))


def calcularPesos(bultos, pesoKgSuelto=None):
    """Con bultos: pesos reales y volumetricos. Sin bultos (pre-registro):
    solo el peso estimado que dio el cliente."""
    if bultos:
        return resumirBultos(bultos, current_app.config['FACTOR_VOLUMETRICO'])
    if pesoKgSuelto is not None:
        return None, {'pesoRealKg': pesoKgSuelto, 'pesoVolumetricoKg': None,
                      'pesoFacturableKg': redondearPeso(pesoKgSuelto)}
    return None, {'pesoRealKg': None, 'pesoVolumetricoKg': None, 'pesoFacturableKg': None}


def cotizarEnvio(zonaOrigenId, zonaDestinoId, servicio, pesoFacturable, valorDeclarado):
    """Devuelve el desglose de la cotizacion, o None si no hay tarifa."""
    tarifa = buscarTarifa(zonaOrigenId, zonaDestinoId, servicio)
    if not tarifa or pesoFacturable is None:
        return None
    return cotizar(tarifa, pesoFacturable, valorDeclarado, current_app.config['SEGURO_PORCENTAJE'])


def ahoraLocal():
    """Hora local del negocio (naive), comparable con fechaEntregaEstimada."""
    return ahoraUtc() + timedelta(hours=current_app.config['UTC_OFFSET_HORAS'])


def _hashPin(pedido, pin):
    clave = current_app.config['JWT_SECRET_KEY'].encode()
    return hmac.new(clave, f'{pedido.codigoGuia}:{pin}'.encode(), hashlib.sha256).hexdigest()


def generarPin(pedido):
    """PIN de 6 digitos. Solo se guarda su HMAC: ni la base ni la API lo
    exponen; se muestra una unica vez al admitir (o al regenerarlo)."""
    pin = f'{secrets.randbelow(10 ** 6):06d}'
    pedido.requierePin = True
    pedido.pinHash = _hashPin(pedido, pin)
    pedido.pinIntentos = 0
    return pin


def pinEsCorrecto(pedido, pin):
    if not isinstance(pin, str) or not pin.strip().isdigit() or not pedido.pinHash:
        return False
    return hmac.compare_digest(pedido.pinHash, _hashPin(pedido, pin.strip()))


def fechaEstimada(cotizacion):
    """Fin del dia (hora local del negocio) en que vence el plazo. Se calcula
    con la fecha LOCAL: despues de las 7 pm en Lima ya es "manana" en UTC, y
    sumar dias a la fecha UTC prometia un dia de mas.
    diasEntrega = 0 significa entrega el mismo dia."""
    if not cotizacion or cotizacion.get('diasEntrega') is None:
        return None
    hoyLocal = (ahoraUtc() + timedelta(hours=current_app.config['UTC_OFFSET_HORAS'])).date()
    vence = hoyLocal + timedelta(days=int(cotizacion['diasEntrega']))
    return datetime.combine(vence, time(23, 59))


def aplicarInspeccion(pedido, inspeccion):
    for campo, valor in inspeccion.items():
        setattr(pedido, campo, valor)
    pedido.inspeccionadoPorId = usuarioActualId()
    pedido.fechaInspeccion = ahoraUtc()


def elegirAgenciaDestino(origen, zonaDestinoId):
    """Agencia que hara el reparto final: la agencia activa de la zona de la
    direccion de entrega. Si el destino esta en la zona del origen se
    reparte desde el origen (envio local). None = zona sin cobertura."""
    if zonaDestinoId is None or origen.zonaId == zonaDestinoId:
        return origen.id
    otra = conexion.session.query(AlmacenModel).filter_by(zonaId=zonaDestinoId, activo=True) \
        .order_by(AlmacenModel.id).first()
    return otra.id if otra else None


def registrarEvento(bulto, tipo, agenciaId=None, manifiestoId=None):
    conexion.session.add(EventoBultoModel(
        bultoId=bulto.id, pedidoId=bulto.pedidoId, tipo=tipo, agenciaId=agenciaId,
        manifiestoId=manifiestoId, usuarioId=usuarioActualId(),
    ))


def guardarBultos(pedido, bultosDetalle):
    """Reemplaza los bultos del envio. El codigo de cada bulto es la guia +
    su numero: es lo que va en el QR de la etiqueta."""
    conexion.session.query(BultoModel).filter_by(pedidoId=pedido.id).delete(synchronize_session=False)
    for numero, b in enumerate(bultosDetalle, start=1):
        conexion.session.add(BultoModel(
            pedidoId=pedido.id,
            numero=numero,
            codigo=f'{pedido.codigoGuia}-{numero}' if pedido.codigoGuia else None,
            pesoKg=b['pesoKg'],
            largoCm=b['largoCm'],
            anchoCm=b['anchoCm'],
            altoCm=b['altoCm'],
            pesoVolumetricoKg=b['pesoVolumetricoKg'],
            pesoFacturableKg=b['pesoFacturableKg'],
            descripcion=b.get('descripcion'),
        ))
    conexion.session.flush()
    for bulto in conexion.session.query(BultoModel).filter_by(pedidoId=pedido.id).all():
        registrarEvento(bulto, 'admitido', agenciaId=pedido.almacenId)


def serializarCotizacion(cotizacion, pesos):
    return json.dumps({**(cotizacion or {}), 'pesos': {k: (str(v) if v is not None else None)
                                                        for k, v in pesos.items()}}, ensure_ascii=False)
