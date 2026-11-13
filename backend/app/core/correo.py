"""Envio de correos por SMTP (Gmail, Outlook, SES, Brevo, Mailgun...).

El envio corre en un hilo aparte: la respuesta HTTP tarda lo mismo exista o
no la cuenta, asi el tiempo de respuesta no revela que usuarios existen.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger('courrier')


def _enviar(config, destino, asunto, cuerpo):
    mensaje = EmailMessage()
    mensaje['From'] = config['SMTP_REMITENTE'] or config['SMTP_USUARIO']
    mensaje['To'] = destino
    mensaje['Subject'] = asunto
    mensaje.set_content(cuerpo)
    try:
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
        logger.info('Correo "%s" enviado', asunto)
    except Exception:  # noqa: BLE001  el fallo de correo no debe tumbar la peticion
        logger.exception('No se pudo enviar el correo "%s"', asunto)


def enviarCorreo(destino, asunto, cuerpo, enlaceDesarrollo=None):
    config = dict(current_app.config)
    if not config['SMTP_HOST']:
        if config['ES_PRODUCCION']:
            logger.error('SMTP_HOST no configurado: no se envio el correo "%s"', asunto)
        else:
            # Solo en desarrollo: sin servidor de correo, el enlace se muestra
            # en la consola del backend para poder probar el flujo.
            logger.warning('[DESARROLLO] SMTP no configurado. Correo "%s" para %s. Enlace: %s',
                           asunto, destino, enlaceDesarrollo or '(sin enlace)')
        return
    threading.Thread(target=_enviar, args=(config, destino, asunto, cuerpo), daemon=True).start()
