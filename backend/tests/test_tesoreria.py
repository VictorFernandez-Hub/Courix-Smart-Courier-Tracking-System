"""Dinero y correcciones: precio manual con motivo y tope de descuento,
credito con limite y cobranza, redireccion de envios, reembolsos con nota
de credito, indemnizaciones con tope, cierre de caja, cuadre de recojos e
incidencias con responsable y plazo."""
import sys
from datetime import date, timedelta

import pytest

import app.routes.comprobantes  # noqa: F401  (registra el modulo)
from conftest import INSPECCION_OK, PASSWORD, iniciarSesion
from test_red_agencias import estadoDe, red  # noqa: F401  (red es un fixture)


def _operador(client, admin, agenciaId, usuario='opcaja', dni='40000021'):
    r = admin.post('/usuario', {'nombre': 'Operador Caja', 'usuario': usuario, 'email': f'{usuario}@test.pe',
                                'dni': dni, 'celular': '987654321', 'password': PASSWORD, 'rol': 'operador',
                                'agenciaId': agenciaId})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['content'], iniciarSesion(client, usuario)


@pytest.fixture
def nubefact(app, monkeypatch):
    monkeypatch.setitem(app.config, 'NUBEFACT_URL', 'https://api.nubefact.test/ruta/123')
    monkeypatch.setitem(app.config, 'NUBEFACT_TOKEN', 'tok')
    enviados = []

    def postFalso(url, cuerpo, cabeceras, timeout=10):
        enviados.append(cuerpo)
        return {'aceptada_por_sunat': True, 'enlace_del_pdf': 'https://nubefact.test/x.pdf'}
    monkeypatch.setattr(sys.modules['app.routes.comprobantes'], '_postJson', postFalso)
    return enviados


# ------------------------------------------------------------ admision ----

def test_operador_tiene_tope_de_descuento_y_el_admin_no(client, escenario, admin):
    _, op = _operador(client, admin, escenario['almacen']['id'])
    base = {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
            'direccionEntregaId': escenario['direccion']['id'], 'yaEnAlmacen': True,
            'bultos': [{'pesoKg': 2, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}], **INSPECCION_OK}
    # tarifa 11.00; 10% de tope => minimo 9.90
    r = op.post('/pedido', {**base, 'monto': '9.00', 'motivoMonto': 'Cliente frecuente'})
    assert r.status_code == 403 and '9.90' in r.get_json()['message']
    assert op.post('/pedido', {**base, 'monto': '9.90', 'motivoMonto': 'Cliente frecuente'}).status_code == 201
    assert admin.post('/pedido', {**base, 'monto': '5.00', 'motivoMonto': 'Convenio corporativo'}).status_code == 201


# ------------------------------------------------------------- credito ----

def test_credito_exige_aprobacion_limite_y_se_cobra(escenario, admin):
    tienda = admin.post('/cliente', {'nombre': 'Tienda Credito SAC', 'telefono': '955000111',
                                     'tipoDocumento': 'RUC', 'dni': '20100070970'}).get_json()['content']
    nuevo = lambda: admin.post('/pedido', {  # noqa: E731
        'clienteId': escenario['cliente']['id'], 'remitenteId': tienda['id'], 'almacenId': escenario['almacen']['id'],
        'direccionEntregaId': escenario['direccion']['id'], 'modalidadPago': 'credito', 'yaEnAlmacen': True,
        'bultos': [{'pesoKg': 2, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}], **INSPECCION_OK})
    r = nuevo()
    assert r.status_code == 409 and 'credito aprobado' in r.get_json()['message']

    r = admin.put(f"/cliente/{tienda['id']}/credito", {'creditoHabilitado': True, 'limiteCredito': '20.00',
                                                       'diasCredito': 15})
    assert r.status_code == 200, r.get_json()
    primero = nuevo()
    assert primero.status_code == 201
    r = nuevo()  # 11 + 11 > 20
    assert r.status_code == 409 and 'limite de credito' in r.get_json()['message']

    cuenta = admin.get(f"/cliente/{tienda['id']}/cuenta").get_json()['content']
    assert cuenta['deuda'] == '11.00' and cuenta['disponible'] == '9.00' and len(cuenta['pedidos']) == 1
    cartera = admin.get('/creditos/cartera').get_json()
    assert cartera['totales']['deuda'] == '11.00'

    r = admin.post(f"/cliente/{tienda['id']}/cobrar-credito", {'metodo': 'transferencia', 'referencia': 'OP-1'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['content']['deuda'] == '0.00'
    assert nuevo().status_code == 201  # libero cupo


# ---------------------------------------------------------- redireccion ----

def test_redireccion_antes_de_salir_recalcula_agencia_y_flete(escenario, admin, red):
    pedido = escenario['nuevoPedido']()  # local, 11.00
    zonaNorte = escenario['repartidor2']['zonaId']
    nueva = admin.post('/direccion-cliente', {'clienteId': escenario['cliente']['id'], 'zonaId': zonaNorte,
                                              'calle': 'Av. Norte 500'}).get_json()['content']
    url = f"/pedido/{pedido['id']}/redireccionar"
    assert admin.post(url, {'direccionEntregaId': nueva['id']}).status_code == 400  # exige motivo
    r = admin.post(url, {'direccionEntregaId': nueva['id'], 'motivo': 'El cliente se mudo'})
    assert r.status_code == 200, r.get_json()
    actualizado = r.get_json()['content']
    assert actualizado['agenciaDestinoId'] == red['norte']['id']
    assert actualizado['monto'] == '19.00'  # tarifa Centro -> Norte: 15 + 2 kg x 2


def test_devolucion_se_reprograma_con_nueva_direccion(escenario, admin):
    repa = escenario['repa']
    pedido = escenario['nuevoPedido']()
    ruta = repa.post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']}).get_json()['ruta']['id']
    repa.post(f'/ruta/{ruta}/iniciar')
    repa.post(f"/pedido/{pedido['id']}/estado", {'estado': 'en_camino'})
    repa.post(f"/pedido/{pedido['id']}/estado", {'estado': 'no_entregado', 'motivo': 'direccion_incorrecta'})
    admin.post(f"/pedido/{pedido['id']}/estado", {'estado': 'por_devolver'})
    assert admin.get(f"/pedido/{pedido['id']}/cargos").get_json()['content'][0]['estado'] == 'pendiente'

    otra = admin.post('/direccion-cliente', {'clienteId': escenario['cliente']['id'], 'zonaId': escenario['zona']['id'],
                                             'calle': 'Jr. Correcto 123'}).get_json()['content']
    r = admin.post(f"/pedido/{pedido['id']}/redireccionar", {'direccionEntregaId': otra['id'],
                                                              'motivo': 'Dato corregido por el remitente'})
    assert r.status_code == 200, r.get_json()
    assert estadoDe(admin, pedido['id']) == 'en_almacen'
    assert r.get_json()['content']['intentosEntrega'] == 0
    assert admin.get(f"/pedido/{pedido['id']}/cargos").get_json()['content'][0]['estado'] == 'anulado'


# ----------------------------------------------- reembolsos y notas ----

def test_cancelado_pagado_se_reembolsa_con_nota_de_credito(escenario, admin, nubefact):
    pedido = escenario['nuevoPedido'](modalidadPago='prepagado')
    admin.post('/pago', {'pedidoId': pedido['id'], 'monto': '11.00', 'metodo': 'efectivo', 'estadoPago': 'pagado'})
    r = admin.post(f"/pedido/{pedido['id']}/comprobante", {'tipo': 'boleta', 'numDoc': '12345678', 'nombre': 'Ana Torres'})
    assert r.status_code == 201, r.get_json()
    boleta = r.get_json()['content']

    url = f"/pedido/{pedido['id']}/reembolso"
    datos = {'tipo': 'devolucion_flete', 'monto': '11.00', 'metodo': 'efectivo', 'motivo': 'Cliente desistio'}
    assert admin.post(url, datos).status_code == 409  # aun no esta cancelado
    admin.post(f"/pedido/{pedido['id']}/estado", {'estado': 'cancelado'})
    assert admin.post(url, {**datos, 'monto': '12.00'}).status_code == 409  # mas de lo cobrado

    r = admin.post(url, datos)
    assert r.status_code == 201, r.get_json()
    nota = r.get_json()['content']['notaCredito']
    assert nota['tipo'] == 'nota' and nota['serie'] == 'BC01' and nota['comprobanteRefId'] == boleta['id']
    assert nota['estado'] == 'aceptado'
    enviado = nubefact[-1]
    assert enviado['tipo_de_comprobante'] == 3 and enviado['documento_que_se_modifica_serie'] == 'B001'
    assert enviado['tipo_de_nota_de_credito'] == 1  # anulacion total
    saldos = admin.get(f"/pedido/{pedido['id']}/reembolsos").get_json()['content']['saldos']
    assert saldos['devolucionDisponible'] == '0.00'


def test_indemnizacion_tiene_tope_sin_seguro(escenario, admin, app):
    app.config['INDEMNIZACION_SIN_SEGURO'] = '50.00'
    pedido = escenario['nuevoPedido']()  # sin valor declarado ni seguro
    admin.post(f"/pedido/{pedido['id']}/estado", {'estado': 'extraviado', 'comentario': 'Se perdio en almacen'})
    url = f"/pedido/{pedido['id']}/reembolso"
    datos = {'tipo': 'indemnizacion', 'metodo': 'transferencia', 'referencia': 'OP-9', 'motivo': 'Perdida en almacen'}
    r = admin.post(url, {**datos, 'monto': '80.00'})
    assert r.status_code == 409 and '50.00' in r.get_json()['message']
    assert admin.post(url, {**datos, 'monto': '50.00'}).status_code == 201


# -------------------------------------------------------- cierre de caja ----

def test_cierre_de_caja_cuadra_efectivo_y_separa_digitales(client, escenario, admin):
    _, op = _operador(client, admin, escenario['almacen']['id'])
    a = escenario['nuevoPedido'](modalidadPago='prepagado')
    b = escenario['nuevoPedido'](modalidadPago='prepagado')
    op.post('/pago', {'pedidoId': a['id'], 'monto': '11.00', 'metodo': 'efectivo', 'estadoPago': 'pagado'})
    op.post('/pago', {'pedidoId': b['id'], 'monto': '11.00', 'metodo': 'yape', 'estadoPago': 'pagado', 'referencia': 'Y1'})

    arqueo = op.get('/caja/arqueo').get_json()['content']
    assert arqueo['efectivoEsperado'] == '11.00' and arqueo['porMetodo'] == {'efectivo': '11.00', 'yape': '11.00'}
    assert op.post('/caja/cierre', {'efectivoContado': '10.00'}).status_code == 400  # diferencia sin explicar
    r = op.post('/caja/cierre', {'efectivoContado': '10.00', 'observacion': 'Falto un sol de vuelto'})
    assert r.status_code == 201 and r.get_json()['content']['diferencia'] == '-1.00'
    assert op.get('/caja/arqueo').get_json()['content']['movimientos'] == []
    assert len(admin.get('/caja/cierres').get_json()['content']) == 1


# ------------------------------------------------------ recojos ----

def test_no_se_admiten_mas_bultos_de_los_recogidos(escenario, admin):
    manana = (date.today() + timedelta(days=1)).isoformat()
    r = admin.post('/recojo', {'remitenteId': escenario['cliente']['id'], 'direccionId': escenario['direccion']['id'],
                               'fechaProgramada': manana, 'franja': 'manana', 'bultosEstimados': 1}).get_json()['content']
    admin.post(f"/recojo/{r['id']}/asignar", {'repartidorId': escenario['repartidor']['id']})
    escenario['repa'].post(f"/recojo/{r['id']}/recoger", {'bultosRecogidos': 1})
    caja = {'pesoKg': 1, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}
    base = {'clienteId': escenario['cliente']['id'], 'remitenteId': escenario['cliente']['id'],
            'almacenId': escenario['almacen']['id'], 'direccionEntregaId': escenario['direccion']['id'],
            'yaEnAlmacen': True, **INSPECCION_OK, 'solicitudRecojoId': r['id']}
    res = admin.post('/pedido', {**base, 'bultos': [caja, caja]})
    assert res.status_code == 400 and 'recogio 1' in res.get_json()['message']
    assert admin.post('/pedido', {**base, 'bultos': [caja]}).status_code == 201
    detalle = admin.get(f"/recojo/{r['id']}").get_json()['content']
    assert detalle['bultosAdmitidos'] == 1 and detalle['pendientesDeAdmitir'] == 0


# ------------------------------------------------------ incidencias ----

def test_incidencia_nace_con_prioridad_y_plazo_y_se_asigna(client, escenario, admin):
    pedido = escenario['nuevoPedido']()
    admin.post(f"/pedido/{pedido['id']}/incidencia", {'tipo': 'producto_danado', 'descripcion': 'Caja aplastada'})
    inc = admin.get('/incidencias').get_json()['content'][0]
    assert inc['prioridad'] == 'alta' and inc['fechaLimite'] and inc['vencida'] is False

    operador, op = _operador(client, admin, escenario['almacen']['id'])
    adminId = next(u for u in admin.get('/usuarios').get_json()['content'] if u['rol'] == 'admin')['id']
    assert op.post(f"/incidencia/{inc['id']}/asignar", {'responsableId': adminId}).status_code == 403
    r = op.post(f"/incidencia/{inc['id']}/asignar", {'responsableId': operador['id']})
    assert r.status_code == 200 and r.get_json()['content']['estado'] == 'en_proceso'
    assert [i['id'] for i in op.get('/incidencias?mias=1').get_json()['content']] == [inc['id']]

    # Compensacion por el dano: indemnizacion ligada a la incidencia
    r = admin.post(f"/pedido/{pedido['id']}/reembolso", {
        'tipo': 'indemnizacion', 'monto': '30.00', 'metodo': 'efectivo', 'motivo': 'Producto danado',
        'incidenciaId': inc['id']})
    assert r.status_code == 201, r.get_json()
    assert admin.get(f"/pedido/{pedido['id']}/incidencias").get_json()['content'][0]['compensacion'] == '30.00'
