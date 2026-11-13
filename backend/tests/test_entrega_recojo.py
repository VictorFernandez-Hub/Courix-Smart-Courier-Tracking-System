"""Fase 3 - Entrega con constancia (receptor, DNI, firma, PIN), recojo a
domicilio y cumplimiento del plazo (SLA)."""
import sys
from datetime import date, datetime, timedelta

import pytest

from conftest import ENTREGA_OK, FIRMA, INSPECCION_OK

import app.routes.pedidos  # noqa: F401
import app.routes.reportes  # noqa: F401
modPedidos = sys.modules['app.routes.pedidos']


def enCamino(escenario, **extra):
    repa = escenario['repa']
    pedido = escenario['nuevoPedido'](**extra)
    repa.post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']})
    repa.post(f"/pedido/{pedido['id']}/estado", {'estado': 'en_camino'})
    return pedido


def entregar(escenario, pedido, **extra):
    return escenario['repa'].post(f"/pedido/{pedido['id']}/entregar-y-cobrar",
                                  {'monto': pedido['monto'], 'metodo': 'efectivo', **ENTREGA_OK, **extra})


# ------------------------------------------------------- constancia ----

def test_entrega_exige_receptor_dni_y_firma(escenario, admin):
    pedido = enCamino(escenario)
    sinNombre = {k: v for k, v in ENTREGA_OK.items() if k != 'nombreReceptor'}
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/entregar-y-cobrar", {'monto': pedido['monto'], **sinNombre})
    assert r.status_code == 400
    assert entregar(escenario, pedido, dniReceptor='').status_code == 400
    assert entregar(escenario, pedido, firma='').status_code == 400
    r = entregar(escenario, pedido, relacionReceptor='porteria', latitud=-12.05, longitud=-77.04)
    assert r.status_code == 200, r.get_json()

    c = admin.get(f"/pedido/{pedido['id']}/entrega").get_json()['content']
    assert c['nombreReceptor'] == 'Ana Torres' and c['dniReceptor'] == '12345678'
    assert c['relacion'] == 'porteria' and c['firma'] == FIRMA and c['latitud'] == -12.05
    assert escenario['repa'].get(f"/pedido/{pedido['id']}/entrega").status_code == 403


def test_firma_opcional_si_se_configura(escenario, app, monkeypatch):
    monkeypatch.setitem(app.config, 'FIRMA_OBLIGATORIA', False)
    assert entregar(escenario, enCamino(escenario), firma='').status_code == 200


# ------------------------------------------------------- PIN ----

def test_pin_se_muestra_una_vez_y_nunca_se_expone(escenario, admin):
    pedido = escenario['nuevoPedido'](entregaConPin=True)
    pin = pedido['pinEntrega']
    assert len(pin) == 6 and pin.isdigit()
    assert pedido['requierePin'] is True and 'pinHash' not in pedido
    texto = admin.get(f"/pedido/{pedido['id']}").get_data(as_text=True) + admin.get('/pedidos').get_data(as_text=True)
    assert pin not in texto and 'pinHash' not in texto


def _pinIncorrecto(pin):
    return '000000' if pin != '000000' else '111111'


def test_entrega_con_pin(escenario, app, monkeypatch):
    monkeypatch.setitem(app.config, 'MAX_INTENTOS_PIN', 2)
    pedido = enCamino(escenario, entregaConPin=True)
    pin = pedido['pinEntrega']
    assert entregar(escenario, pedido).status_code == 400                         # sin PIN
    r = entregar(escenario, pedido, pin=_pinIncorrecto(pin))
    assert r.status_code == 400 and 'Quedan 1' in r.get_json()['message']
    assert entregar(escenario, pedido, pin=_pinIncorrecto(pin)).status_code == 400
    assert entregar(escenario, pedido, pin=pin).status_code == 423                # bloqueado aun con el correcto


def test_regenerar_pin_desbloquea_y_anula_el_anterior(escenario, admin, app, monkeypatch):
    monkeypatch.setitem(app.config, 'MAX_INTENTOS_PIN', 1)
    pedido = enCamino(escenario, entregaConPin=True)
    viejo = pedido['pinEntrega']
    entregar(escenario, pedido, pin=_pinIncorrecto(viejo))
    assert entregar(escenario, pedido, pin=viejo).status_code == 423

    nuevo = admin.post(f"/pedido/{pedido['id']}/pin").get_json()['content']['pinEntrega']
    monkeypatch.setitem(app.config, 'MAX_INTENTOS_PIN', 5)
    if nuevo != viejo:  # (1 en un millon de que coincidan)
        assert entregar(escenario, pedido, pin=viejo).status_code == 400          # el anterior ya no sirve
    r = entregar(escenario, pedido, pin=nuevo)
    assert r.status_code == 200, r.get_json()
    assert admin.get(f"/pedido/{pedido['id']}/entrega").get_json()['content']['pinVerificado'] is True
    assert admin.post(f"/pedido/{pedido['id']}/pin").status_code == 409          # ya entregado


# ------------------------------------------------------- recojo ----

@pytest.fixture
def recojo(escenario, admin):
    manana = (date.today() + timedelta(days=1)).isoformat()
    datos = {'remitenteId': escenario['cliente']['id'], 'direccionId': escenario['direccion']['id'],
             'fechaProgramada': manana, 'franja': 'manana', 'bultosEstimados': 2}
    r = admin.post('/recojo', datos)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['content'], datos


def test_validaciones_al_registrar_un_recojo(admin, recojo):
    _, datos = recojo
    assert admin.post('/recojo', {**datos, 'fechaProgramada': '2020-01-01'}).status_code == 400
    assert admin.post('/recojo', {**datos, 'franja': 'noche'}).status_code == 400
    assert admin.post('/recojo', {**datos, 'bultosEstimados': 0}).status_code == 400


def test_recojo_completo_hasta_la_admision(escenario, admin, app, recojo, monkeypatch):
    monkeypatch.setitem(app.config, 'RECARGO_RECOJO', '5.00')
    r, _ = recojo
    assert r['estado'] == 'pendiente' and r['agencia']['id'] == escenario['almacen']['id']

    # solo un repartidor de la zona del recojo
    assert admin.post(f"/recojo/{r['id']}/asignar", {'repartidorId': escenario['repartidor2']['id']}).status_code == 400
    assert admin.post(f"/recojo/{r['id']}/asignar", {'repartidorId': escenario['repartidor']['id']}).status_code == 200

    mios = escenario['repa'].get('/mis-recojos').get_json()['content']
    assert [x['id'] for x in mios] == [r['id']]
    assert escenario['repa2'].post(f"/recojo/{r['id']}/recoger", {'bultosRecogidos': 2}).status_code == 403

    # no se admite lo que todavia no se recogio
    base = {'clienteId': escenario['cliente']['id'], 'remitenteId': escenario['cliente']['id'],
            'almacenId': escenario['almacen']['id'], 'direccionEntregaId': escenario['direccion']['id'],
            'yaEnAlmacen': True, 'bultos': [{'pesoKg': 2, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}],
            **INSPECCION_OK, 'solicitudRecojoId': r['id']}
    assert admin.post('/pedido', base).status_code == 400

    assert escenario['repa'].post(f"/recojo/{r['id']}/recoger", {'bultosRecogidos': 2}).status_code == 200
    p1 = admin.post('/pedido', base).get_json()['content']
    assert p1['monto'] == '16.00'  # 11.00 de tarifa + 5.00 de recargo de recojo
    p2 = admin.post('/pedido', base).get_json()['content']
    assert p2['monto'] == '11.00'  # el recargo se cobra una sola vez
    final = admin.get(f"/recojo/{r['id']}").get_json()['content']
    assert final['estado'] == 'admitida' and sorted(final['envios']) == sorted([p1['codigoGuia'], p2['codigoGuia']])

    otro = admin.post('/cliente', {'nombre': 'Otro', 'telefono': '911222333'}).get_json()['content']
    assert admin.post('/pedido', {**base, 'remitenteId': otro['id']}).status_code == 400  # remitente distinto


def test_recojo_fallido_se_reprograma(escenario, admin, recojo):
    r, datos = recojo
    admin.post(f"/recojo/{r['id']}/asignar", {'repartidorId': escenario['repartidor']['id']})
    assert escenario['repa'].post(f"/recojo/{r['id']}/fallido", {'motivo': 'cliente_ausente'}).status_code == 200
    r2 = admin.post(f"/recojo/{r['id']}/reprogramar", {'fechaProgramada': datos['fechaProgramada'], 'franja': 'tarde'})
    assert r2.status_code == 200
    c = r2.get_json()['content']
    assert c['estado'] == 'pendiente' and c['repartidor'] is None and c['franja'] == 'tarde'
    assert admin.post(f"/recojo/{r['id']}/cancelar", {'motivo': 'El cliente desistio'}).status_code == 200
    assert admin.post(f"/recojo/{r['id']}/cancelar", {}).status_code == 409


# ------------------------------------------------------- SLA ----

def test_atrasados_y_rastreo_con_fecha_comprometida(escenario, admin, client, monkeypatch):
    tarifa = admin.get('/tarifas').get_json()['content'][0]
    admin.put(f"/tarifa/{tarifa['id']}", {'diasEntrega': 0})
    pedido = escenario['nuevoPedido']()
    assert pedido['fechaEntregaEstimada'] is not None

    ids = lambda: [p['id'] for p in admin.get('/pedidos?atrasados=1').get_json()['content']]  # noqa: E731
    assert pedido['id'] not in ids()
    pasadoManana = lambda: datetime.now() + timedelta(days=2)  # noqa: E731
    monkeypatch.setattr(modPedidos, 'ahoraLocal', pasadoManana)
    monkeypatch.setattr(sys.modules['app.routes.reportes'], 'ahoraLocal', pasadoManana)
    assert pedido['id'] in ids()
    assert admin.get('/reportes/sla').get_json()['content']['atrasados'] == 1

    r = client.get(f"/rastreo/{pedido['codigoGuia']}").get_json()
    assert r['fechaEntregaEstimada'] == pedido['fechaEntregaEstimada'][:10]
