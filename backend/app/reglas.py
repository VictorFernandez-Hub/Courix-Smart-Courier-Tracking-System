"""Reglas de negocio puras (sin base de datos): estados, transiciones,
catalogos y calculo de tarifas. Se pueden probar sin levantar la app."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


from app.core.validacion import (
    CENTIMO,
)


ESTADOS_CATALOGO = [
    ('pendiente', 1), ('en_almacen', 2), ('en_transito', 3), ('en_agencia_destino', 4),
    ('asignado', 5), ('recogido', 6), ('en_camino', 7), ('entregado', 8),
    ('no_entregado', 9), ('por_devolver', 10), ('devuelto', 11), ('cancelado', 12), ('extraviado', 13),
]

# Mapa de transiciones validas, segun el diagrama de estados del negocio.
# "pendiente" y "en_almacen" se alcanzan por sus rutas dedicadas (crear
# pedido, /ingresar-almacen); "asignado" por /tomar o /agregar-pedido (o el
# reintento desde "no_entregado"); "entregado" SOLO por /entregar-y-cobrar,
# que es donde se exige el cobro y la evidencia.
#
# Logistica inversa: un envio que no se pudo entregar vuelve a la agencia
# al cerrar la ruta (queda listo para reintentar) o, si se agotaron los
# intentos o el destinatario lo rechazo, pasa a "por_devolver". Si se
# repartia en otra ciudad, viaja de regreso al origen en un manifiesto y
# alli se entrega al remitente ("devuelto").
TRANSICIONES_VALIDAS = {
    'pendiente': ['cancelado'],
    # El remitente desiste antes de que salga: se le devuelve en la agencia
    'en_almacen': ['por_devolver', 'cancelado', 'extraviado'],
    # en_transito y en_agencia_destino se alcanzan SOLO por los manifiestos
    # (despachar / recibir por escaneo). Si un bulto nunca llega (faltante),
    # o aparece tarde (se recibe sobre el manifiesto cerrado) o un admin lo
    # declara extraviado para indemnizar al cliente.
    'en_transito': ['extraviado'],
    'en_agencia_destino': ['por_devolver', 'cancelado', 'extraviado'],
    'asignado': ['recogido', 'en_camino', 'cancelado'],
    'recogido': ['en_camino', 'cancelado'],
    'en_camino': ['entregado', 'no_entregado'],
    'no_entregado': ['asignado', 'por_devolver', 'cancelado'],
    'por_devolver': ['devuelto', 'extraviado'],
    'entregado': [],    # estado final, sin salida
    'devuelto': [],     # final: el remitente recibio su paquete de vuelta
    'cancelado': [],    # estado final, sin salida
    'extraviado': [],   # final: se perdio, corresponde indemnizar
}

# Quien puede ejecutar cada transicion por /pedido/<id>/estado. Para el rol
# repartidor se exige ademas que el pedido este asignado a el.
ROLES_POR_ESTADO_DESTINO = {
    'recogido': ('admin', 'repartidor'),
    'en_camino': ('admin', 'repartidor'),
    'no_entregado': ('admin', 'repartidor'),
    'asignado': ('admin', 'operador', 'repartidor'),  # reintento de entrega
    'por_devolver': ('admin', 'operador'),            # la agencia lo tiene y debe volver al remitente
    'devuelto': ('admin', 'operador'),                # se entrego al remitente en la agencia de origen
    'cancelado': ('admin',),
    'extraviado': ('admin',),
}
# Estos cambios dejan constancia escrita obligatoria (quien recibio, que paso)
ESTADOS_CON_COMENTARIO = ('devuelto', 'extraviado')

ESTADOS_FINALES = ('entregado', 'devuelto', 'cancelado', 'extraviado')
ESTADOS_ACTIVOS = ('pendiente', 'en_almacen', 'en_transito', 'en_agencia_destino', 'asignado', 'recogido',
                   'en_camino', 'no_entregado', 'por_devolver')
# Lo que impide cerrar una ruta: paquetes que el repartidor aun no resolvio.
# Los "no_entregado" no bloquean: al cerrar la ruta vuelven a la agencia.
ESTADOS_PEDIDO_PENDIENTES_EN_RUTA = ('asignado', 'recogido', 'en_camino')

MOTIVOS_NO_ENTREGA = ('cliente_ausente', 'direccion_incorrecta', 'rechazado', 'zona_inaccesible', 'reprogramado', 'otro')
MODALIDADES_PAGO = ('contra_entrega', 'prepagado', 'credito')
METODOS_PAGO = ('efectivo', 'yape', 'plin', 'tarjeta', 'transferencia')
PRIORIDADES = ('normal', 'urgente')
TIPOS_INCIDENCIA_VALIDOS = ('reclamo', 'producto_danado', 'direccion_incorrecta', 'retraso', 'faltante', 'otro')
# Plazo para resolver una incidencia segun su prioridad (horas). El Libro de
# Reclamaciones (INDECOPI) da 15 dias habiles como maximo: aqui es menos.
PRIORIDADES_INCIDENCIA = {'alta': 24, 'media': 72, 'baja': 120}
# Las que nacen urgentes: perdida o dano de mercaderia
PRIORIDAD_POR_TIPO = {'faltante': 'alta', 'producto_danado': 'alta', 'reclamo': 'media', 'retraso': 'media',
                      'direccion_incorrecta': 'media', 'otro': 'baja'}

# ---- Dinero que sale ----
TIPOS_REEMBOLSO = ('devolucion_flete', 'indemnizacion')
# Se devuelve el flete solo si el servicio no se presto
ESTADOS_CON_DEVOLUCION_FLETE = ('cancelado', 'extraviado')
CONCEPTOS_CARGO = ('devolucion', 'redireccion')

# ---- Entrega: quien recibe ----
RELACIONES_RECEPTOR = ('titular', 'familiar', 'trabajador', 'porteria', 'otro')

# ---- Recojo a domicilio ----
# pendiente -> asignada -> recogida -> admitida (ya se registraron sus envios)
#                       -> fallida (-> reprogramar -> pendiente)
# cualquier estado no final -> cancelada
ESTADOS_RECOJO = ('pendiente', 'asignada', 'recogida', 'fallida', 'admitida', 'cancelada')
FRANJAS_RECOJO = ('manana', 'tarde')
MOTIVOS_FALLO_RECOJO = ('cliente_ausente', 'direccion_incorrecta', 'paquete_no_listo', 'otro')

# ---- Red de agencias: manifiestos de despacho ----
# abierto -> (despachar) -> en_transito -> (cerrar recepcion) -> recibido | recibido_con_diferencias
ESTADOS_MANIFIESTO = ('abierto', 'en_transito', 'recibido', 'recibido_con_diferencias')
MANIFIESTOS_ACTIVOS = ('abierto', 'en_transito')
TIPOS_EVENTO_BULTO = ('admitido', 'manifestado', 'retirado_de_manifiesto', 'despachado',
                      'recibido_en_destino', 'faltante', 'recibido_tarde')

# Lo unico que ve el publico en el rastreo: nunca comentarios internos.
MENSAJES_PUBLICOS = {
    'pendiente': 'Registramos tu envío',
    'en_almacen': 'Tu paquete llegó a nuestro almacén',
    'en_transito': 'Tu paquete está viajando hacia la agencia de destino',
    'en_agencia_destino': 'Tu paquete llegó a la agencia de destino',
    'asignado': 'Tu paquete fue asignado a un repartidor',
    'recogido': 'El repartidor recogió tu paquete',
    'en_camino': 'Tu paquete está en camino',
    'entregado': 'Tu paquete fue entregado',
    'no_entregado': 'No pudimos entregar tu paquete en este intento',
    'devuelto': 'Tu paquete fue devuelto',
    'cancelado': 'El envío fue cancelado',
}

ALFABETO_GUIA = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # sin 0/O, 1/I/L

# ---- Admision: servicio, inspeccion y cotizacion ----
TIPOS_SERVICIO = ('estandar', 'express')
ESTADOS_PRODUCTO = ('bueno', 'con_detalles', 'danado')
# 'rechazado' = no cumple las condiciones de transporte: el envio no se admite
EMBALAJES = ('adecuado', 'reforzado', 'rechazado')
# El peso facturable se cobra por tramos de medio kilo, redondeando hacia arriba
PASO_PESO_KG = Decimal('0.5')


def puedeTransicionar(estadoActual, estadoNuevo):
    """Funcion pura (sin base de datos): segun el diagrama de estados, se
    puede pasar de 'estadoActual' a 'estadoNuevo'? Ver tests/test_estados.py."""
    return estadoNuevo in TRANSICIONES_VALIDAS.get(estadoActual, [])


def calcularMontoTarifa(tarifa, pesoKg):
    """monto = precioBase + pesoKg * precioPorKg, siempre en Decimal."""
    peso = Decimal(str(pesoKg or 0))
    monto = Decimal(tarifa.precioBase) + peso * Decimal(tarifa.precioPorKg)
    return monto.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def pesoVolumetrico(largoCm, anchoCm, altoCm, factor):
    """Espacio que ocupa un paquete expresado en kg: largo x ancho x alto (cm)
    / factor. El estandar de la industria es 5000 (1 m3 = 200 kg)."""
    volumen = Decimal(str(largoCm)) * Decimal(str(anchoCm)) * Decimal(str(altoCm))
    return (volumen / Decimal(factor)).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def redondearPeso(pesoKg):
    """2.1 kg -> 2.5 kg; 2.5 -> 2.5; 0.2 -> 0.5. Nunca menos de un tramo."""
    peso = Decimal(str(pesoKg or 0))
    if peso <= 0:
        return PASO_PESO_KG
    return ((peso / PASO_PESO_KG).to_integral_value(rounding=ROUND_CEILING) * PASO_PESO_KG).quantize(CENTIMO)


def resumirBultos(bultos, factor):
    """Cada bulto se cobra por el MAYOR entre su peso real y su volumetrico
    (una caja grande y liviana ocupa el espacio de una pesada). Devuelve los
    bultos con sus pesos calculados y los totales del envio."""
    detalle, real, volumetrico, facturable = [], Decimal('0'), Decimal('0'), Decimal('0')
    for b in bultos:
        vol = pesoVolumetrico(b['largoCm'], b['anchoCm'], b['altoCm'], factor)
        peso = Decimal(str(b['pesoKg']))
        mayor = max(peso, vol)
        detalle.append({**b, 'pesoVolumetricoKg': vol, 'pesoFacturableKg': mayor})
        real += peso
        volumetrico += vol
        facturable += mayor
    return detalle, {
        'pesoRealKg': real.quantize(CENTIMO),
        'pesoVolumetricoKg': volumetrico.quantize(CENTIMO),
        'pesoFacturableKg': redondearPeso(facturable),
    }


def cotizar(tarifa, pesoFacturableKg, valorDeclarado, porcentajeSeguro):
    """flete = max(precio minimo, base + kg facturables x precio/kg)
    seguro = valor declarado x % de seguro
    total  = flete + seguro"""
    peso = Decimal(str(pesoFacturableKg or 0))
    calculado = (Decimal(tarifa.precioBase) + peso * Decimal(tarifa.precioPorKg)).quantize(
        CENTIMO, rounding=ROUND_HALF_UP)
    minimo = aDecimal(getattr(tarifa, 'precioMinimo', None))
    flete = max(calculado, minimo)
    seguro = (aDecimal(valorDeclarado) * Decimal(str(porcentajeSeguro)) / Decimal('100')).quantize(
        CENTIMO, rounding=ROUND_HALF_UP)
    return {
        'tarifaId': tarifa.id,
        'tipoServicio': getattr(tarifa, 'tipoServicio', 'estandar'),
        'diasEntrega': getattr(tarifa, 'diasEntrega', None),
        'pesoFacturableKg': str(peso.quantize(CENTIMO)),
        'precioBase': str(aDecimal(tarifa.precioBase)),
        'precioPorKg': str(aDecimal(tarifa.precioPorKg)),
        'fleteCalculado': str(calculado),
        'precioMinimo': str(minimo),
        'minimoAplicado': minimo > calculado,
        'flete': str(flete),
        'valorDeclarado': str(aDecimal(valorDeclarado)),
        'porcentajeSeguro': str(porcentajeSeguro),
        'seguro': str(seguro),
        'total': str(flete + seguro),
    }


def aDecimal(valor):
    return Decimal(str(valor if valor is not None else 0)).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def ahoraUtc():
    return datetime.now(timezone.utc).replace(tzinfo=None)
