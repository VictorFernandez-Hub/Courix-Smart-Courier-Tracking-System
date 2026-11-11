"""Pruebas de la maquina de estados de un pedido (TRANSICIONES_VALIDAS /
puedeTransicionar en app/reglas.py). No requieren base de datos: solo ejercitan la
funcion pura, que es exactamente la que usan cambiarEstadoPedido,
entregarYCobrar y eliminarPedido para decidir si una transicion es valida.

Correr con:  pytest tests/test_estados.py -v
"""
from app.reglas import puedeTransicionar, TRANSICIONES_VALIDAS


def test_pendiente_solo_puede_cancelarse():
    assert puedeTransicionar('pendiente', 'cancelado') is True
    assert puedeTransicionar('pendiente', 'en_almacen') is False
    assert puedeTransicionar('pendiente', 'asignado') is False


def test_en_almacen_solo_puede_cancelarse():
    # "asignado" se alcanza por /pedido/<id>/tomar o /ruta/<id>/agregar-pedido,
    # no por el endpoint generico de cambio de estado.
    assert puedeTransicionar('en_almacen', 'cancelado') is True
    assert puedeTransicionar('en_almacen', 'asignado') is False


def test_flujo_feliz_completo():
    assert puedeTransicionar('asignado', 'en_camino') is True
    assert puedeTransicionar('en_camino', 'entregado') is True


def test_no_entregado_permite_reintentar_o_devolver():
    assert puedeTransicionar('no_entregado', 'asignado') is True
    assert puedeTransicionar('no_entregado', 'devuelto') is True
    assert puedeTransicionar('no_entregado', 'cancelado') is True
    assert puedeTransicionar('no_entregado', 'entregado') is False


def test_estados_finales_no_tienen_salida():
    for estadoFinal in ('entregado', 'devuelto', 'cancelado'):
        for estadoDestino in TRANSICIONES_VALIDAS:
            assert puedeTransicionar(estadoFinal, estadoDestino) is False, (
                f'"{estadoFinal}" es un estado final y no deberia poder pasar a "{estadoDestino}"'
            )


def test_no_se_puede_saltar_directo_de_asignado_a_entregado():
    # El repartidor tiene que pasar primero por "en_camino" (o registrar la
    # entrega con /entregar-y-cobrar, que internamente exige lo mismo).
    assert puedeTransicionar('asignado', 'entregado') is False


def test_estado_desconocido_no_tiene_transiciones():
    assert puedeTransicionar('estado_que_no_existe', 'cancelado') is False
