"""Avisos al destinatario: correo (SMTP) y WhatsApp (Cloud API oficial de Meta).

Patron "outbox":
  1. encolarAviso() agrega las filas en la MISMA transaccion que el cambio de
     estado (si la operacion falla, no queda un aviso de algo que no paso).
  2. Despues del commit, despacharAvisos() los envia en segundo plano: el
     repartidor no espera a que responda Meta o el servidor de correo.
  3. Lo que falle queda "fallido" y se reintenta con `flask reenviar-avisos`
     (programalo con cron cada 10 minutos).

Un canal solo se usa si esta configurado y el cliente tiene ese dato. Si no
hay ninguno, no se encola nada (no se llena la tabla de basura).

WhatsApp exige PLANTILLAS aprobadas por Meta para escribirle primero a un
cliente. Hay que crearlas en WhatsApp Manager con estos nombres y variables
(ver PLANTILLAS_WHATSAPP); el texto puede adaptarse.
"""
import json
import logging
import smtplib
import ssl
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage

from flask import current_app

from app.extensions import conexion
from app.models import ClienteModel, EntregaModel, NotificacionModel, PedidoModel
from app.reglas import MOTIVOS_NO_ENTREGA, ahoraUtc

logger = logging.getLogger('courrier')

MAX_INTENTOS_AVISO = 3

MOTIVOS_TEXTO = {
    'cliente_ausente': 'no encontramos a nadie', 'direccion_incorrecta': 'la direccion no es correcta',
    'rechazado': 'el envio fue rechazado', 'zona_inaccesible': 'no pudimos acceder a la zona',
    'reprogramado': 'se reprogramo la entrega', 'otro': 'un inconveniente en la ruta',
}
assert set(MOTIVOS_TEXTO) == set(MOTIVOS_NO_ENTREGA)

# evento -> (asunto del correo, texto, nombre de plantilla WhatsApp, variables de la plantilla en orden)
PLANTILLAS = {
    'registrado': (
        'Tu envio {guia} fue registrado',
        'Hola {nombre}: registramos tu envio {guia}{deRemitente}. Entrega estimada: {fecha}.\n'
        'Siguelo aqui: {enlace}',
        'envio_registrado', ('nombre', 'guia', 'fecha', 'enlace'),
    ),
    'en_camino': (
        'Tu envio {guia} llega hoy',
        'Hola {nombre}: tu envio {guia} salio a reparto y llega hoy.{avisoPin}\nSiguelo aqui: {enlace}',
        'envio_en_camino', ('nombre', 'guia', 'enlace'),
    ),
    'entregado': (
        'Tu envio {guia} fue entregado',
        'Hola {nombre}: tu envio {guia} fue entregado a {receptor}. Gracias por confiar en Courrier Express.',
        'envio_entregado', ('nombre', 'guia', 'receptor'),
    ),
    'no_entregado': (
        'No pudimos entregar tu envio {guia}',
        'Hola {nombre}: hoy no pudimos entregar tu envio {guia} ({motivo}). '
        'Te contactaremos para coordinar un nuevo intento.\nSiguelo aqui: {enlace}',
        'envio_no_entregado', ('nombre', 'guia', 'motivo'),
    ),
}
PLANTILLAS_WHATSAPP = {evento: (p[2], p[3]) for evento, p in PLANTILLAS.items()}


# ------------------------------------------------------------ canales ----

def whatsappConfigurado(config=None):
    config = config or current_app.config
    return bool(config['WHATSAPP_TOKEN'] and config['WHATSAPP_PHONE_ID'])


def correoConfigurado(config=None):
    return bool((config or current_app.config)['SMTP_HOST'])


def telefonoInternacional(telefono, codigoPais):
    """987654321 -> 51987654321 (formato que pide WhatsApp, sin '+')."""
    digitos = ''.join(c for c in (telefono or '') if c.isdigit())
    if not digitos:
        return None
    if (telefono or '').strip().startswith('+') or len(digitos) > 9:
        return digitos
    # En Peru los celulares tienen 9 digitos y empiezan con 9; un fijo
    # (01-4567890) tambien puede tener 9 digitos pero no tiene WhatsApp.
    return codigoPais + digitos if len(digitos) == 9 and digitos.startswith('9') else None


def _postJson(url, cuerpo, cabeceras, timeout=10):
    """POST JSON con la libreria estandar (sin dependencias extra)."""
    peticion = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method='POST',
                                      headers={'Content-Type': 'application/json', **cabeceras})
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return json.loads(respuesta.read().decode() or '{}')
    except urllib.error.HTTPError as error:
        detalle = error.read().decode(errors='replace')[:300]
        raise RuntimeError(f'HTTP {error.code}: {detalle}')


def _enviarWhatsapp(config, destino, plantilla, variables):
    url = (f"https://graph.facebook.com/{config['WHATSAPP_API_VERSION']}/"
           f"{config['WHATSAPP_PHONE_ID']}/messages")
    cuerpo = {
        'messaging_product': 'whatsapp',
        'to': destino,
        'type': 'template',
        'template': {
            'name': plantilla,
            'language': {'code': config['WHATSAPP_IDIOMA']},
            'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(v)} for v in variables]}],
        },
    }
    respuesta = _postJson(url, cuerpo, {'Authorization': f"Bearer {config['WHATSAPP_TOKEN']}"})
    mensajes = respuesta.get('messages') or [{}]
    return mensajes[0].get('id')


def _enviarCorreo(config, destino, asunto, texto):
    mensaje = EmailMessage()
    mensaje['From'] = config['SMTP_REMITENTE'] or config['SMTP_USUARIO']
    mensaje['To'] = destino
    mensaje['Subject'] = f'Courrier Express - {asunto}'
    mensaje.set_content(texto)
    contexto = ssl.create_default_context()
    if config['SMTP_SEGURIDAD'] == 'ssl':
        servidor = smtplib.SMTP_SSL(config['SMTP_HOST'], config['SMTP_PUERTO'], context=contexto, timeout=15)
    else:
        servidor = smtplib.SMTP(config['SMTP_HOST'], config['SMTP_PUERTO'], timeout=15)
        if config['SMTP_SEGURIDAD'] == 'starttls':
            servidor.starttls(context=contexto)
    with servidor:
        if config['SMTP_USUARIO']:
            servidor.login(config['SMTP_USUARIO'], config['SMTP_PASSWORD'])
        servidor.send_message(mensaje)
    return None


# ------------------------------------------------------------ contenido ----

def _datos(pedido, evento):
    cliente = conexion.session.get(ClienteModel, pedido.clienteId)
    remitente = conexion.session.get(ClienteModel, pedido.remitenteId) if pedido.remitenteId else None
    entrega = conexion.session.query(EntregaModel).filter_by(pedidoId=pedido.id).first() \
        if evento == 'entregado' else None
    return {
        'nombre': (cliente.nombre.split()[0] if cliente and cliente.nombre else 'cliente'),
        'guia': pedido.codigoGuia,
        'deRemitente': f' de {remitente.nombre}' if remitente else '',
        'fecha': pedido.fechaEntregaEstimada.strftime('%d/%m/%Y') if pedido.fechaEntregaEstimada else 'por confirmar',
        'enlace': f"{current_app.config['URL_FRONTEND']}/rastreo?guia={pedido.codigoGuia}",
        'avisoPin': ' Ten a la mano tu codigo de entrega: el repartidor te lo pedira.' if pedido.requierePin else '',
        'receptor': entrega.nombreReceptor if entrega else 'la persona indicada',
        'motivo': MOTIVOS_TEXTO.get(pedido.motivoNoEntrega or 'otro', 'un inconveniente en la ruta'),
    }


# ------------------------------------------------------------ outbox ----

def encolarAviso(pedido, evento):
    """Agrega los avisos a la sesion actual (se guardan con el commit de la
    operacion). Devuelve las filas creadas."""
    config = current_app.config
    if not config['AVISOS_HABILITADOS'] or evento not in PLANTILLAS:
        return []
    cliente = conexion.session.get(ClienteModel, pedido.clienteId)
    if not cliente or not cliente.recibeAvisos:
        return []
    filas = []
    destinoWa = telefonoInternacional(cliente.telefono, config['CODIGO_PAIS_TELEFONO'])
    if whatsappConfigurado() and destinoWa:
        filas.append(NotificacionModel(pedidoId=pedido.id, evento=evento, canal='whatsapp', destino=destinoWa))
    if correoConfigurado() and cliente.email:
        filas.append(NotificacionModel(pedidoId=pedido.id, evento=evento, canal='email', destino=cliente.email))
    conexion.session.add_all(filas)
    return filas


def _enviarUno(notificacion):
    config = current_app.config
    pedido = conexion.session.get(PedidoModel, notificacion.pedidoId)
    asunto, texto, plantilla, variables = PLANTILLAS[notificacion.evento]
    datos = _datos(pedido, notificacion.evento)
    notificacion.intentos = (notificacion.intentos or 0) + 1
    try:
        if notificacion.canal == 'whatsapp':
            notificacion.idProveedor = _enviarWhatsapp(config, notificacion.destino, plantilla,
                                                       [datos[v] for v in variables])
        else:
            _enviarCorreo(config, notificacion.destino, asunto.format(**datos), texto.format(**datos))
        notificacion.estado = 'enviado'
        notificacion.error = None
        notificacion.fechaEnvio = ahoraUtc()
    except Exception as error:  # noqa: BLE001  un proveedor caido no debe tumbar nada
        notificacion.estado = 'fallido'
        notificacion.error = str(error)[:500]
        logger.warning('Aviso %s (%s) del pedido %s fallo: %s', notificacion.id, notificacion.canal,
                       notificacion.pedidoId, notificacion.error)


def procesarAvisos(ids):
    """Envia los avisos indicados (pendientes o fallidos con intentos libres)."""
    if not ids:
        return 0
    filas = conexion.session.query(NotificacionModel).filter(
        NotificacionModel.id.in_(ids), NotificacionModel.estado.in_(('pendiente', 'fallido')),
        NotificacionModel.intentos < MAX_INTENTOS_AVISO).all()
    for fila in filas:
        _enviarUno(fila)
    conexion.session.commit()
    return len(filas)


def despacharAvisos(filas):
    """Llamar DESPUES del commit. En segundo plano, salvo AVISOS_SINCRONOS."""
    ids = [f.id for f in filas if f.id]
    if not ids:
        return
    if current_app.config['AVISOS_SINCRONOS']:
        procesarAvisos(ids)
        return
    app = current_app._get_current_object()

    def tarea():
        with app.app_context():
            try:
                procesarAvisos(ids)
            finally:
                conexion.session.remove()
    threading.Thread(target=tarea, daemon=True).start()


def avisar(pedido, evento):
    """Atajo para cuando la operacion YA hizo commit: encola, guarda y envia."""
    filas = encolarAviso(pedido, evento)
    if filas:
        conexion.session.commit()
        despacharAvisos(filas)
