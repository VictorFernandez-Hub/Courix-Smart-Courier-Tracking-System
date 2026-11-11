"""Reglas de negocio puras (sin base de datos): estados, transiciones,
catalogos y calculo de tarifas. Se pueden probar sin levantar la app."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


from app.core.validacion import (
    CENTIMO,
)


ESTADOS_CATALOGO = [
    ('pendiente', 1), ('en_almacen', 2), ('asignado', 3), ('recogido', 4),
    ('en_camino', 5), ('entregado', 6), ('no_entregado', 7),
    ('devuelto', 8), ('cancelado', 9),
]

# Mapa de transiciones validas, segun el diagrama de estados del negocio.
# "pendiente" y "en_almacen" se alcanzan por sus rutas dedicadas (crear
# pedido, /ingresar-almacen); "asignado" por /tomar o /agregar-pedido (o el
# reintento desde "no_entregado"); "entregado" SOLO por /entregar-y-cobrar,
# que es donde se exige el cobro y la evidencia.
TRANSICIONES_VALIDAS = {
    'pendiente': ['cancelado'],
    'en_almacen': ['cancelado'],
    'asignado': ['recogido', 'en_camino', 'cancelado'],
    'recogido': ['en_camino', 'cancelado'],
    'en_camino': ['entregado', 'no_entregado'],
    'no_entregado': ['asignado', 'devuelto', 'cancelado'],
    'entregado': [],   # estado final, sin salida
    'devuelto': [],    # estado final, sin salida
    'cancelado': [],   # estado final, sin salida
}

# Quien puede ejecutar cada transicion por /pedido/<id>/estado. Para el rol
# repartidor se exige ademas que el pedido este asignado a el.
ROLES_POR_ESTADO_DESTINO = {
    'recogido': ('admin', 'repartidor'),
    'en_camino': ('admin', 'repartidor'),
    'no_entregado': ('admin', 'repartidor'),
    'asignado': ('admin', 'operador', 'repartidor'),  # reintento de entrega
    'devuelto': ('admin', 'operador'),                # el almacen confirma que lo recibio
    'cancelado': ('admin',),
}

ESTADOS_FINALES = ('entregado', 'devuelto', 'cancelado')
ESTADOS_ACTIVOS = ('pendiente', 'en_almacen', 'asignado', 'recogido', 'en_camino', 'no_entregado')
ESTADOS_PEDIDO_PENDIENTES_EN_RUTA = ('asignado', 'recogido', 'en_camino', 'no_entregado')

MOTIVOS_NO_ENTREGA = ('cliente_ausente', 'direccion_incorrecta', 'rechazado', 'zona_inaccesible', 'reprogramado', 'otro')
MODALIDADES_PAGO = ('contra_entrega', 'prepagado', 'credito')
METODOS_PAGO = ('efectivo', 'yape', 'plin', 'tarjeta', 'transferencia')
PRIORIDADES = ('normal', 'urgente')
TIPOS_INCIDENCIA_VALIDOS = ('reclamo', 'producto_danado', 'direccion_incorrecta', 'retraso', 'otro')

# Lo unico que ve el publico en el rastreo: nunca comentarios internos.
MENSAJES_PUBLICOS = {
    'pendiente': 'Registramos tu envío',
    'en_almacen': 'Tu paquete llegó a nuestro almacén',
    'asignado': 'Tu paquete fue asignado a un repartidor',
    'recogido': 'El repartidor recogió tu paquete',
    'en_camino': 'Tu paquete está en camino',
    'entregado': 'Tu paquete fue entregado',
    'no_entregado': 'No pudimos entregar tu paquete en este intento',
    'devuelto': 'Tu paquete fue devuelto',
    'cancelado': 'El envío fue cancelado',
}

ALFABETO_GUIA = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # sin 0/O, 1/I/L


def puedeTransicionar(estadoActual, estadoNuevo):
    """Funcion pura (sin base de datos): segun el diagrama de estados, se
    puede pasar de 'estadoActual' a 'estadoNuevo'? Ver tests/test_estados.py."""
    return estadoNuevo in TRANSICIONES_VALIDAS.get(estadoActual, [])


def calcularMontoTarifa(tarifa, pesoKg):
    """monto = precioBase + pesoKg * precioPorKg, siempre en Decimal."""
    peso = Decimal(str(pesoKg or 0))
    monto = Decimal(tarifa.precioBase) + peso * Decimal(tarifa.precioPorKg)
    return monto.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def aDecimal(valor):
    return Decimal(str(valor if valor is not None else 0)).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def ahoraUtc():
    return datetime.now(timezone.utc).replace(tzinfo=None)
