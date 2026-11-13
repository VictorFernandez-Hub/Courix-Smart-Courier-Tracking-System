"""Fase 1 - Admision: remitente/destinatario, bultos, peso volumetrico,
inspeccion, cotizacion por servicio y etiqueta."""
from decimal import Decimal

from conftest import INSPECCION_OK
from app.reglas import pesoVolumetrico, redondearPeso

FOTO = 'data:image/jpeg;base64,' + 'A' * 100


def bulto(peso, largo=10, ancho=10, alto=10, **extra):
    return {'pesoKg': peso, 'largoCm': largo, 'anchoCm': ancho, 'altoCm': alto, **extra}


def tarifaCentro(admin, servicio='estandar'):
    return [t for t in admin.get('/tarifas').get_json()['content'] if t['tipoServicio'] == servicio][0]


# ------------------------------------------------------- reglas puras ----

def test_peso_volumetrico_y_redondeo():
    assert pesoVolumetrico(50, 40, 30, 5000) == Decimal('12.00')
    assert redondearPeso(Decimal('2.1')) == Decimal('2.50')
    assert redondearPeso(Decimal('2.5')) == Decimal('2.50')
    assert redondearPeso(Decimal('0.2')) == Decimal('0.50')


# ------------------------------------------------------- cotizacion ----

def test_caja_grande_y_liviana_se_cobra_por_volumen(escenario):
    # 2 kg reales pero 50x40x30 cm = 12 kg volumetricos -> 8 + 12 x 1.50 = 26.00
    pedido = escenario['nuevoPedido'](bultos=[bulto(2, 50, 40, 30)])
    assert pedido['monto'] == '26.00'
    assert pedido['pesoFacturableKg'] == '12.00'
    assert pedido['pesoKg'] == 2.0


def test_peso_facturable_se_redondea_al_medio_kilo(escenario):
    pedido = escenario['nuevoPedido'](bultos=[bulto(2.1)])  # 2.5 kg -> 8 + 3.75
    assert pedido['monto'] == '11.75'


def test_varios_bultos_suman_y_cada_uno_tiene_codigo(escenario, admin):
    pedido = escenario['nuevoPedido'](bultos=[bulto(1), bulto(1.5), bulto(0.4)])  # 2.9 -> 3.0 kg
    assert pedido['monto'] == '12.50'
    bultos = admin.get(f"/pedido/{pedido['id']}/bultos").get_json()['content']
    assert [b['codigo'] for b in bultos] == [f"{pedido['codigoGuia']}-{n}" for n in (1, 2, 3)]


def test_precio_minimo_y_seguro_por_valor_declarado(escenario, admin):
    tarifa = tarifaCentro(admin)
    assert admin.put(f"/tarifa/{tarifa['id']}", {'precioMinimo': '15.00', 'diasEntrega': 2}).status_code == 200
    pedido = escenario['nuevoPedido'](bultos=[bulto(1)], valorDeclarado='500.00')
    # flete 8 + 1.5 = 9.50 < minimo 15.00; seguro 1% de 500 = 5.00
    assert pedido['monto'] == '20.00'
    assert pedido['costoSeguro'] == '5.00'
    assert pedido['fechaEntregaEstimada'] is not None


def test_cada_servicio_tiene_su_tarifa(escenario, admin):
    r = admin.post('/pedido', {**_base(escenario), 'tipoServicio': 'express'})
    assert r.status_code == 400 and 'express' in r.get_json()['message']
    zona = escenario['zona']['id']
    r = admin.post('/tarifa', {'zonaOrigenId': zona, 'zonaDestinoId': zona, 'tipoServicio': 'express',
                               'precioBase': '15.00', 'precioPorKg': '3.00', 'diasEntrega': 0})
    assert r.status_code == 201
    pedido = escenario['nuevoPedido'](tipoServicio='express')  # 15 + 2 x 3
    assert pedido['monto'] == '21.00' and pedido['tipoServicio'] == 'express'


def test_cotizar_no_guarda_nada(escenario, admin):
    antes = len(admin.get('/pedidos').get_json()['content'])
    r = admin.post('/cotizar', {'almacenId': escenario['almacen']['id'],
                                'direccionEntregaId': escenario['direccion']['id'],
                                'bultos': [bulto(2, 50, 40, 30)], 'valorDeclarado': '100'})
    assert r.status_code == 200
    c = r.get_json()['content']
    assert c['tarifaEncontrada'] and c['cotizacion']['total'] == '27.00'  # 26 + 1% de 100
    assert c['bultos'][0]['pesoVolumetricoKg'] == '12.00'
    assert len(admin.get('/pedidos').get_json()['content']) == antes


# ------------------------------------------------------- inspeccion ----

def _base(escenario, **extra):
    return {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
            'direccionEntregaId': escenario['direccion']['id'], 'yaEnAlmacen': True,
            'bultos': [bulto(2)], **INSPECCION_OK, **extra}


def test_recepcion_en_mostrador_exige_bultos_e_inspeccion(escenario, admin):
    datos = _base(escenario)
    assert admin.post('/pedido', {**datos, 'bultos': []}).status_code == 400
    assert admin.post('/pedido', {**datos, 'bultos': [{'pesoKg': 2}]}).status_code == 400  # sin medidas
    assert admin.post('/pedido', {**datos, 'declaraSinProhibidos': False}).status_code == 400
    assert admin.post('/pedido', {**datos, 'embalaje': 'rechazado'}).status_code == 400
    assert admin.post('/pedido', {**datos, 'estadoProducto': 'con_detalles'}).status_code == 400  # sin observaciones
    r = admin.post('/pedido', {**datos, 'estadoProducto': 'danado', 'observacionesInspeccion': 'Esquina golpeada'})
    assert r.status_code == 400 and 'foto' in r.get_json()['message']
    r = admin.post('/pedido', {**datos, 'estadoProducto': 'danado', 'observacionesInspeccion': 'Esquina golpeada',
                               'fotoInspeccion': FOTO})
    assert r.status_code == 201
    pedido = r.get_json()['content']
    assert pedido['estadoProducto'] == 'danado' and pedido['inspeccionadoPorId'] is not None
    assert 'fotoInspeccion' not in pedido  # la foto no viaja en los listados


def test_pre_registro_se_pesa_mide_e_inspecciona_al_recibirlo(escenario, admin):
    r = admin.post('/pedido', {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
                               'direccionEntregaId': escenario['direccion']['id'], 'pesoKg': 1})
    assert r.status_code == 201
    pedido = r.get_json()['content']
    assert pedido['monto'] == '9.50'  # estimado con el peso que dio el cliente
    assert admin.get(f"/pedido/{pedido['id']}/etiqueta").status_code == 409  # aun no hay bultos

    url = f"/pedido/{pedido['id']}/ingresar-almacen"
    assert admin.post(url, {'bultos': [bulto(1)]}).status_code == 400  # falta la inspeccion
    r = admin.post(url, {'bultos': [bulto(1, 50, 40, 30)], **INSPECCION_OK})
    assert r.status_code == 200
    assert r.get_json()['content']['monto'] == '26.00'  # recalculado con el volumetrico real


# ------------------------------------------------- remitente y etiqueta ----

def test_remitente_y_etiqueta(escenario, admin):
    remitente = admin.post('/cliente', {'nombre': 'Tienda Sol', 'telefono': '955555555', 'dni': '20123456'}).get_json()['content']
    assert admin.post('/pedido', _base(escenario, remitenteId=99999)).status_code == 404
    pedido = escenario['nuevoPedido'](remitenteId=remitente['id'], bultos=[bulto(1), bulto(2)],
                                      descripcionProducto='Celular Samsung')
    assert pedido['remitenteId'] == remitente['id']

    r = admin.get(f"/pedido/{pedido['id']}/etiqueta")
    assert r.status_code == 200
    e = r.get_json()['content']
    assert e['remitente']['nombre'] == 'Tienda Sol'
    assert e['destinatario']['nombre'] == escenario['cliente']['nombre']
    assert [b['numero'] for b in e['bultos']] == [1, 2] and e['bultos'][0]['total'] == 2
    assert e['montoACobrar'] == pedido['monto']  # contra entrega: el repartidor cobra
    texto = r.get_data(as_text=True)
    assert 'Samsung' not in texto and '12345678' not in texto  # ni contenido ni DNI en la etiqueta


def test_repartidor_no_imprime_etiquetas(escenario):
    pedido = escenario['nuevoPedido']()
    assert escenario['repa'].get(f"/pedido/{pedido['id']}/etiqueta").status_code == 403


def test_fecha_estimada_usa_la_fecha_local_y_admite_mismo_dia(app, monkeypatch):
    from datetime import datetime
    import app.admision as adm
    # 21:30 en Lima = 02:30 UTC del dia siguiente
    monkeypatch.setattr(adm, 'ahoraUtc', lambda: datetime(2026, 11, 12, 2, 30))
    with app.test_request_context():
        assert adm.fechaEstimada({'diasEntrega': 1}).date().isoformat() == '2026-11-12'
        assert adm.fechaEstimada({'diasEntrega': 0}).date().isoformat() == '2026-11-11'
        assert adm.fechaEstimada({'diasEntrega': None}) is None
