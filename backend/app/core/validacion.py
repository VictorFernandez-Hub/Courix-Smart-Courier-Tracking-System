"""Validacion de entrada. Cada helper lanza ErrorValidacion (-> HTTP 400 con
un mensaje claro) en vez de dejar que un dato mal formado llegue a la base
de datos o provoque un error 500."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import request

CENTIMO = Decimal('0.01')
PATRON_EMAIL = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$')


class ErrorNegocio(Exception):
    """Error esperado que se devuelve al cliente tal cual (mensaje + status)."""

    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


class ErrorValidacion(ErrorNegocio):
    def __init__(self, mensaje):
        super().__init__(mensaje, 400)


def cuerpoJson():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ErrorValidacion('El cuerpo de la peticion debe ser un objeto JSON')
    return data


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and valor.strip() == '')


def texto(data, campo, requerido=False, maximo=255, minimo=0):
    valor = data.get(campo)
    if _vacio(valor):
        if requerido:
            raise ErrorValidacion(f'El campo "{campo}" es obligatorio')
        return None
    if not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
        raise ErrorValidacion(f'El campo "{campo}" debe ser texto')
    valor = str(valor).strip()
    if len(valor) > maximo:
        raise ErrorValidacion(f'El campo "{campo}" no puede superar {maximo} caracteres')
    if len(valor) < minimo:
        raise ErrorValidacion(f'El campo "{campo}" debe tener al menos {minimo} caracteres')
    return valor


def entero(data, campo, requerido=False, minimo=1, maximo=None):
    valor = data.get(campo)
    if _vacio(valor):
        if requerido:
            raise ErrorValidacion(f'El campo "{campo}" es obligatorio')
        return None
    if isinstance(valor, bool):
        raise ErrorValidacion(f'El campo "{campo}" debe ser un numero entero')
    try:
        if isinstance(valor, float) and not valor.is_integer():
            raise ValueError
        numero = int(valor)
    except (TypeError, ValueError):
        raise ErrorValidacion(f'El campo "{campo}" debe ser un numero entero')
    if minimo is not None and numero < minimo:
        raise ErrorValidacion(f'El campo "{campo}" debe ser mayor o igual a {minimo}')
    if maximo is not None and numero > maximo:
        raise ErrorValidacion(f'El campo "{campo}" debe ser menor o igual a {maximo}')
    return numero


def dinero(data, campo, requerido=False, minimo=Decimal('0'), maximo=Decimal('99999999.99')):
    """Siempre Decimal redondeado a centimos: nunca float para dinero."""
    valor = data.get(campo)
    if _vacio(valor):
        if requerido:
            raise ErrorValidacion(f'El campo "{campo}" es obligatorio')
        return None
    if isinstance(valor, bool):
        raise ErrorValidacion(f'El campo "{campo}" debe ser un monto valido')
    try:
        monto = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorValidacion(f'El campo "{campo}" debe ser un monto valido')
    if not monto.is_finite():
        raise ErrorValidacion(f'El campo "{campo}" debe ser un monto valido')
    monto = monto.quantize(CENTIMO, rounding=ROUND_HALF_UP)
    if minimo is not None and monto < minimo:
        raise ErrorValidacion(f'El campo "{campo}" no puede ser menor a {minimo}')
    if maximo is not None and monto > maximo:
        raise ErrorValidacion(f'El campo "{campo}" excede el maximo permitido')
    return monto


def decimalPositivo(data, campo, requerido=False, maximo=Decimal('10000')):
    """Para pesos/medidas: Decimal > 0."""
    valor = dinero(data, campo, requerido=requerido, minimo=None, maximo=maximo)
    if valor is not None and valor <= 0:
        raise ErrorValidacion(f'El campo "{campo}" debe ser mayor a 0')
    return valor


def coordenada(data, campo, tipo):
    valor = data.get(campo)
    if _vacio(valor):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ErrorValidacion(f'El campo "{campo}" debe ser numerico')
    limite = 90 if tipo == 'lat' else 180
    if not -limite <= numero <= limite:
        raise ErrorValidacion(f'El campo "{campo}" esta fuera de rango')
    return numero


def opcion(data, campo, opciones, defecto=None, requerido=False):
    valor = data.get(campo)
    if _vacio(valor):
        if requerido:
            raise ErrorValidacion(f'El campo "{campo}" es obligatorio')
        return defecto
    if valor not in opciones:
        raise ErrorValidacion(f'El campo "{campo}" debe ser uno de: {", ".join(opciones)}')
    return valor


def booleano(data, campo, defecto=False):
    valor = data.get(campo, defecto)
    if isinstance(valor, bool):
        return valor
    if valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str) and valor.lower() in ('true', 'false'):
        return valor.lower() == 'true'
    raise ErrorValidacion(f'El campo "{campo}" debe ser true o false')


def email(data, campo='email', requerido=True):
    valor = texto(data, campo, requerido=requerido, maximo=120)
    if valor is None:
        return None
    valor = valor.lower()
    if not PATRON_EMAIL.match(valor):
        raise ErrorValidacion('El email no tiene un formato valido')
    return valor


def telefono(data, campo='telefono', requerido=False):
    valor = texto(data, campo, requerido=requerido, maximo=20)
    if valor is None:
        return None
    limpio = re.sub(r'[\s\-()]', '', valor)
    if not re.fullmatch(r'\+?\d{6,15}', limpio):
        raise ErrorValidacion(f'El campo "{campo}" no es un telefono valido')
    return limpio


def dni(data, campo='dni'):
    valor = texto(data, campo, maximo=15)
    if valor is None:
        return None
    if not re.fullmatch(r'[A-Za-z0-9]{6,15}', valor):
        raise ErrorValidacion('El DNI/documento solo puede tener letras y numeros (6 a 15 caracteres)')
    return valor.upper()


def validarPassword(password):
    """Politica minima: 10+ caracteres, al menos una letra y un numero."""
    if not isinstance(password, str) or len(password) < 10:
        raise ErrorValidacion('La contrasena debe tener al menos 10 caracteres')
    if len(password) > 128:
        raise ErrorValidacion('La contrasena no puede superar 128 caracteres')
    if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        raise ErrorValidacion('La contrasena debe incluir letras y numeros')
    return password


PATRON_IMAGEN = re.compile(r'^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$')
MAX_EVIDENCIA_CARACTERES = 4 * 1024 * 1024  # ~3 MB de imagen real


def evidencia(data, campo='evidenciaEntrega', requerido=False):
    valor = data.get(campo)
    if _vacio(valor):
        if requerido:
            raise ErrorValidacion('La foto de evidencia de entrega es obligatoria')
        return None
    if not isinstance(valor, str) or len(valor) > MAX_EVIDENCIA_CARACTERES:
        raise ErrorValidacion('La foto de evidencia es demasiado grande (maximo ~3 MB)')
    if not PATRON_IMAGEN.match(valor):
        raise ErrorValidacion('La evidencia debe ser una imagen JPEG, PNG o WEBP')
    return valor


def paginacion():
    pagina = request.args.get('pagina', 1, type=int) or 1
    porPagina = request.args.get('por_pagina', 20, type=int) or 20
    return max(pagina, 1), min(max(porPagina, 1), 100)
