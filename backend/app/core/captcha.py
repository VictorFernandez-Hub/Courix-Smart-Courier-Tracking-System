"""Captcha propio (sin servicios externos ni claves de terceros).

- La imagen se dibuja en el servidor con Pillow: el texto nunca viaja en el
  HTML ni en el JSON, solo como pixeles distorsionados.
- Cada desafio sirve UNA sola vez (se borra al verificarlo, acierte o no),
  caduca a los MINUTOS_CAPTCHA y se guarda como HMAC, nunca en claro.
"""
import base64
import hashlib
import hmac
import io
import random
import secrets
from datetime import timedelta

from flask import current_app
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.extensions import conexion
from app.models import CaptchaModel
from app.core.validacion import ErrorNegocio
from app.reglas import ahoraUtc

# Sin caracteres que se confunden entre si (0/O, 1/I/L, 5/S, 2/Z, 8/B)
ALFABETO = 'ACDEFGHJKMNPQRTUVWXY34679'
LONGITUD = 5
ANCHO, ALTO = 180, 64

_aleatorio = random.SystemRandom()


class CaptchaInvalido(ErrorNegocio):
    def __init__(self, mensaje='El código de seguridad no es correcto. Intenta con el nuevo código'):
        super().__init__(mensaje, 400)


def _hash(captchaId, respuesta):
    clave = current_app.config['JWT_SECRET_KEY'].encode()
    return hmac.new(clave, f'{captchaId}:{respuesta}'.encode(), hashlib.sha256).hexdigest()


def _fuente(tamano):
    try:
        return ImageFont.load_default(size=tamano)
    except TypeError:  # Pillow sin FreeType: fuente basica
        return ImageFont.load_default()


def _dibujar(codigo):
    fondo = tuple(_aleatorio.randint(225, 245) for _ in range(3))
    imagen = Image.new('RGB', (ANCHO, ALTO), fondo)
    trazo = ImageDraw.Draw(imagen)

    # Ruido de fondo: puntos y lineas finas
    for _ in range(350):
        color = tuple(_aleatorio.randint(140, 210) for _ in range(3))
        trazo.point((_aleatorio.randrange(ANCHO), _aleatorio.randrange(ALTO)), fill=color)
    for _ in range(4):
        color = tuple(_aleatorio.randint(120, 190) for _ in range(3))
        trazo.line([(_aleatorio.randrange(ANCHO), _aleatorio.randrange(ALTO)) for _ in range(2)], fill=color, width=1)

    # Cada caracter con su propio tamano, color, giro y desplazamiento
    paso = (ANCHO - 20) // LONGITUD
    for i, caracter in enumerate(codigo):
        fuente = _fuente(_aleatorio.randint(34, 42))
        capa = Image.new('RGBA', (56, 64), (0, 0, 0, 0))
        color = tuple(_aleatorio.randint(20, 110) for _ in range(3)) + (255,)
        ImageDraw.Draw(capa).text((10, 4), caracter, font=fuente, fill=color)
        capa = capa.rotate(_aleatorio.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        x = 8 + i * paso + _aleatorio.randint(-4, 4)
        y = _aleatorio.randint(-6, 4)
        imagen.paste(capa, (x, y), capa)

    # Lineas que cruzan el texto (dificultan la segmentacion por OCR)
    for _ in range(2):
        color = tuple(_aleatorio.randint(40, 120) for _ in range(3))
        puntos = [(x, _aleatorio.randint(14, ALTO - 14)) for x in range(0, ANCHO + 1, 30)]
        trazo.line(puntos, fill=color, width=2)

    imagen = imagen.filter(ImageFilter.SMOOTH)
    salida = io.BytesIO()
    imagen.save(salida, format='PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(salida.getvalue()).decode()


def generarCaptcha():
    ahora = ahoraUtc()
    # Limpieza perezosa: los desafios vencidos se borran al crear nuevos
    conexion.session.query(CaptchaModel).filter(CaptchaModel.expira < ahora).delete(synchronize_session=False)

    captchaId = secrets.token_urlsafe(32)
    codigo = ''.join(_aleatorio.choice(ALFABETO) for _ in range(LONGITUD))
    conexion.session.add(CaptchaModel(
        id=captchaId,
        respuestaHash=_hash(captchaId, codigo),
        expira=ahora + timedelta(minutes=current_app.config['MINUTOS_CAPTCHA']),
    ))
    conexion.session.commit()
    return {'captchaId': captchaId, 'imagen': _dibujar(codigo), 'expiraEnSegundos': current_app.config['MINUTOS_CAPTCHA'] * 60}


def verificarCaptcha(data):
    """Valida (y consume) el captcha enviado en el cuerpo de la peticion.
    Lanza CaptchaInvalido si falta, vencio, ya se uso o no coincide."""
    if not current_app.config['CAPTCHA_HABILITADO']:
        return
    captchaId = data.get('captchaId')
    respuesta = data.get('captchaRespuesta')
    if not isinstance(captchaId, str) or not isinstance(respuesta, str) or not captchaId or not respuesta.strip():
        raise CaptchaInvalido('Escribe el código de seguridad de la imagen')
    if len(captchaId) > 43 or len(respuesta) > 20:
        raise CaptchaInvalido()

    desafio = conexion.session.get(CaptchaModel, captchaId)
    if desafio is None:
        raise CaptchaInvalido('El código de seguridad venció. Escribe el nuevo código')
    hashGuardado, expira = desafio.respuestaHash, desafio.expira

    # Se consume SIEMPRE y se confirma de inmediato: aunque luego la peticion
    # falle (y se haga rollback), este desafio ya no se puede reintentar.
    # Si dos peticiones llegan a la vez con el mismo id, solo una lo borra.
    borrados = conexion.session.query(CaptchaModel).filter_by(id=captchaId).delete(synchronize_session=False)
    conexion.session.commit()

    if borrados != 1 or expira < ahoraUtc():
        raise CaptchaInvalido('El código de seguridad venció. Escribe el nuevo código')
    normalizada = respuesta.strip().upper().replace(' ', '')
    if not hmac.compare_digest(hashGuardado, _hash(captchaId, normalizada)):
        raise CaptchaInvalido()
