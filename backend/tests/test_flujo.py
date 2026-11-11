"""Flujo de negocio completo: tarifa, asignacion, entrega, cobro, liquidacion."""


def _flujoHastaEnCamino(escenario, **extra):
    repa = escenario['repa']
    pedido = escenario['nuevoPedido'](**extra)
    r = repa.post(f'/pedido/{pedido["id"]}/tomar', {'repartidorId': escenario['repartidor']['id']})
    assert r.status_code == 200, r.get_json()
    rutaId = r.get_json()['ruta']['id']
    if repa.get(f'/ruta/{rutaId}/detalle').get_json()['content']['estado'] == 'planificada':
        assert repa.post(f'/ruta/{rutaId}/iniciar').status_code == 200
    assert repa.post(f'/pedido/{pedido["id"]}/estado', {'estado': 'en_camino'}).status_code == 200
    return pedido, rutaId


def test_monto_se_calcula_con_la_tarifa_en_decimal(escenario):
    pedido = escenario['nuevoPedido']()  # 8.00 + 2 kg * 1.50
    assert pedido['monto'] == '11.00'
    assert pedido['tarifaId'] is not None
    assert pedido['codigoGuia'].startswith('CE-') and len(pedido['codigoGuia']) == 12


def test_contra_entrega_sin_tarifa_ni_monto_se_rechaza(escenario, admin):
    otra = admin.post('/zona', {'nombre': 'Sur'}).get_json()['content']
    direccion = admin.post('/direccion-cliente', {
        'clienteId': escenario['cliente']['id'], 'zonaId': otra['id'], 'calle': 'Calle Sur 1'}).get_json()['content']
    r = admin.post('/pedido', {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
                               'direccionEntregaId': direccion['id']})
    assert r.status_code == 400
    assert 'tarifa' in r.get_json()['message']


def test_repartidor_no_toma_pedidos_de_otra_zona(escenario):
    pedido = escenario['nuevoPedido']()
    r = escenario['repa2'].post(f'/pedido/{pedido["id"]}/tomar', {'repartidorId': escenario['repartidor2']['id']})
    assert r.status_code == 400


def test_entrega_exige_monto_exacto_y_es_idempotente(escenario):
    repa = escenario['repa']
    pedido, _ = _flujoHastaEnCamino(escenario)

    r = repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': 5, 'metodo': 'efectivo'})
    assert r.status_code == 409

    r = repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'metodo': 'yape'})
    assert r.status_code == 400  # yape sin numero de operacion

    r = repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'metodo': 'efectivo'})
    assert r.status_code == 200
    assert r.get_json()['content']['pago']['monto'] == '11.00'

    # reintento por mala senal: mismo resultado, sin duplicar el pago
    r2 = repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'metodo': 'efectivo'})
    assert r2.status_code == 200
    assert r2.get_json()['content']['pago']['id'] == r.get_json()['content']['pago']['id']


def test_entregado_solo_por_entregar_y_cobrar(escenario):
    pedido, _ = _flujoHastaEnCamino(escenario)
    r = escenario['repa'].post(f'/pedido/{pedido["id"]}/estado', {'estado': 'entregado'})
    assert r.status_code == 409


def test_prepagado_se_entrega_sin_cobro(escenario, admin):
    pedido, _ = _flujoHastaEnCamino(escenario, modalidadPago='prepagado')
    r = escenario['repa'].post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {})
    assert r.status_code == 200
    assert r.get_json()['content']['pago'] is None
    assert admin.post('/pago', {'pedidoId': pedido['id'], 'monto': '11.00', 'metodo': 'transferencia',
                                'estadoPago': 'pagado', 'referencia': 'OP-123'}).status_code == 201


def test_no_entregado_exige_motivo_y_limita_intentos(escenario, app):
    app.config['MAX_INTENTOS_ENTREGA'] = 2
    repa = escenario['repa']
    pedido, _ = _flujoHastaEnCamino(escenario)
    url = f'/pedido/{pedido["id"]}/estado'

    assert repa.post(url, {'estado': 'no_entregado'}).status_code == 400
    assert repa.post(url, {'estado': 'no_entregado', 'motivo': 'cliente_ausente'}).status_code == 200
    assert repa.post(url, {'estado': 'asignado'}).status_code == 200
    assert repa.post(url, {'estado': 'en_camino'}).status_code == 200
    assert repa.post(url, {'estado': 'no_entregado', 'motivo': 'cliente_ausente'}).status_code == 200
    # segundo fallo con maximo 2: ya no se puede reintentar
    assert repa.post(url, {'estado': 'asignado'}).status_code == 409
    # el repartidor no puede marcarlo devuelto: lo confirma el almacen
    assert repa.post(url, {'estado': 'devuelto'}).status_code == 403


def test_liquidacion_de_caja(escenario, admin):
    repa = escenario['repa']
    pedido, rutaId = _flujoHastaEnCamino(escenario)
    repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'metodo': 'efectivo'})

    r = repa.post(f'/ruta/{rutaId}/completar')
    assert r.status_code == 200
    assert r.get_json()['efectivoPorLiquidar'] == '11.00'

    pendientes = admin.get('/liquidaciones/pendientes').get_json()['content']
    assert pendientes[0]['montoEsperado'] == '11.00'

    # diferencia sin explicacion -> rechazado
    assert admin.post(f'/ruta/{rutaId}/liquidar', {'montoEntregado': '10.00'}).status_code == 400
    r = admin.post(f'/ruta/{rutaId}/liquidar', {'montoEntregado': '10.00', 'observacion': 'Falto un sol, se descuenta'})
    assert r.status_code == 201
    assert r.get_json()['content']['diferencia'] == '-1.00'
    assert admin.post(f'/ruta/{rutaId}/liquidar', {'montoEntregado': '11.00'}).status_code == 409


def test_rutas_sin_liquidar_bloquean_tomar_pedidos(escenario, app):
    app.config['MAX_RUTAS_SIN_LIQUIDAR'] = 0
    repa = escenario['repa']
    pedido, rutaId = _flujoHastaEnCamino(escenario)
    repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'metodo': 'efectivo'})
    repa.post(f'/ruta/{rutaId}/completar')

    otro = escenario['nuevoPedido']()
    r = repa.post(f'/pedido/{otro["id"]}/tomar', {'repartidorId': escenario['repartidor']['id']})
    assert r.status_code == 409
    assert 'liquidar' in r.get_json()['message']


def test_rastreo_publico_no_filtra_informacion_interna(escenario, admin, client):
    pedido = escenario['nuevoPedido']()
    admin.post(f'/pedido/{pedido["id"]}/incidencia', {'tipo': 'reclamo', 'descripcion': 'Cliente con deuda pendiente'})

    r = client.get(f'/rastreo/{pedido["codigoGuia"].lower()}')
    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    assert 'deuda' not in cuerpo and 'Incidencia' not in cuerpo and 'Ana' not in cuerpo
    assert r.get_json()['estadoActual'] == 'en_almacen'


def test_estado_actual_publico_exige_telefono(escenario, client):
    pedido = escenario['nuevoPedido']()
    assert client.get(f'/pedido/{pedido["id"]}/estado-actual').status_code == 404
    assert client.get(f'/pedido/{pedido["id"]}/estado-actual?telefono=999999999').status_code == 404
    r = client.get(f'/pedido/{pedido["id"]}/estado-actual?telefono=987654321')
    assert r.status_code == 200 and r.get_json()['cliente'] == 'Ana Torres'


def test_listado_de_pedidos_no_incluye_la_foto(escenario):
    repa = escenario['repa']
    pedido, _ = _flujoHastaEnCamino(escenario)
    foto = 'data:image/jpeg;base64,' + 'A' * 100
    repa.post(f'/pedido/{pedido["id"]}/entregar-y-cobrar', {'monto': '11.00', 'evidenciaEntrega': foto})
    fila = repa.get('/pedidos').get_json()['content'][0]
    assert 'evidenciaEntrega' not in fila
    assert repa.get(f'/pedido/{pedido["id"]}/evidencia').get_json()['content'] == foto


def test_no_se_desactiva_almacen_con_pedidos_en_curso(escenario, admin):
    escenario['nuevoPedido']()
    assert admin.post(f'/almacen/{escenario["almacen"]["id"]}/desactivar').status_code == 409


def test_reporte_resumen(escenario, admin):
    escenario['nuevoPedido']()
    r = admin.get('/reportes/resumen').get_json()['content']
    assert r['totalPedidos'] == 1
    assert r['pedidosPorEstado']['en_almacen'] == 1
