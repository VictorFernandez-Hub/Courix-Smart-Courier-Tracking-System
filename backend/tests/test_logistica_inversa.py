"""Caminos de excepcion: entrega fallida que vuelve a la agencia, devolucion
al remitente (local y de regreso por manifiesto), bultos faltantes que
llegan tarde, envios extraviados, contra entrega de mercaderia (recaudo) y
alcance por agencia en caja e incidencias."""
from conftest import ENTREGA_OK, PASSWORD, iniciarSesion
from test_red_agencias import DESPACHO, estadoDe, red  # noqa: F401  (red es un fixture)


def _enCamino(escenario, pedido):
    repa = escenario['repa']
    r = repa.post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']})
    assert r.status_code == 200, r.get_json()
    rutaId = r.get_json()['ruta']['id']
    if repa.get(f'/ruta/{rutaId}/detalle').get_json()['content']['estado'] == 'planificada':
        assert repa.post(f'/ruta/{rutaId}/iniciar').status_code == 200
    assert repa.post(f"/pedido/{pedido['id']}/estado", {'estado': 'en_camino'}).status_code == 200
    return rutaId


def _falla(escenario, pedido, motivo='cliente_ausente'):
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/estado", {'estado': 'no_entregado', 'motivo': motivo})
    assert r.status_code == 200, r.get_json()


def _operador(client, admin, agenciaId, usuario, dni):
    r = admin.post('/usuario', {'nombre': f'Operador {usuario}', 'usuario': usuario, 'email': f'{usuario}@test.pe',
                                'dni': dni, 'celular': '987654321', 'password': PASSWORD, 'rol': 'operador',
                                'agenciaId': agenciaId})
    assert r.status_code == 201, r.get_json()
    return iniciarSesion(client, usuario)


# --------------------------------------------- entrega fallida y reintento ----

def test_al_cerrar_la_ruta_el_no_entregado_vuelve_a_la_agencia_para_reintentar(escenario, admin):
    pedido = escenario['nuevoPedido']()
    rutaId = _enCamino(escenario, pedido)
    _falla(escenario, pedido)

    r = escenario['repa'].post(f'/ruta/{rutaId}/completar')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['paraReintentar'] == 1 and r.get_json()['porDevolver'] == 0
    assert estadoDe(admin, pedido['id']) == 'en_almacen'
    detalle = admin.get(f"/pedido/{pedido['id']}").get_json()['content']
    assert detalle['repartidorId'] is None and detalle['intentosEntrega'] == 1

    # Al dia siguiente se reintenta y se entrega
    disponibles = escenario['repa'].get('/pedidos/disponibles').get_json()['content']
    assert pedido['id'] in [p['id'] for p in disponibles]
    _enCamino(escenario, pedido)
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/entregar-y-cobrar", {**ENTREGA_OK, 'metodo': 'efectivo'})
    assert r.status_code == 200, r.get_json()


def test_rechazado_o_sin_intentos_pasa_a_devolucion_y_se_entrega_al_remitente(escenario, admin, app):
    pedido = escenario['nuevoPedido']()
    rutaId = _enCamino(escenario, pedido)
    _falla(escenario, pedido, motivo='rechazado')
    r = escenario['repa'].post(f'/ruta/{rutaId}/completar')
    assert r.get_json()['porDevolver'] == 1 and 'devolver al remitente' in r.get_json()['message']
    assert estadoDe(admin, pedido['id']) == 'por_devolver'

    # No puede volver a salir a reparto
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']})
    assert r.status_code == 409

    # Aparece en el inventario de la agencia como "por devolver"
    inv = admin.get(f"/almacen/{escenario['almacen']['id']}/inventario?seccion=por_devolver").get_json()['content']
    assert [f['id'] for f in inv] == [pedido['id']]

    url = f"/pedido/{pedido['id']}/estado"
    assert admin.post(url, {'estado': 'devuelto'}).status_code == 400  # exige constancia
    # El remitente paga el flete que el destinatario no pago + 50% de cargo por devolucion
    saldo = admin.get(f"/pedido/{pedido['id']}/saldo-devolucion").get_json()['content']
    assert saldo == {'flete': '11.00', 'cargos': '5.50', 'total': '16.50'}
    constancia = {'estado': 'devuelto', 'comentario': 'Lo retiro el remitente, DNI 44556677'}
    r = admin.post(url, constancia)
    assert r.status_code == 402 and '16.50' in r.get_json()['message']
    assert admin.post(url, {**constancia, 'metodo': 'efectivo'}).status_code == 200
    assert estadoDe(admin, pedido['id']) == 'devuelto'
    assert admin.get(f"/pedido/{pedido['id']}/saldo-devolucion").get_json()['content']['total'] == '0.00'


def test_maximo_de_intentos_bloquea_el_pool(escenario, admin, app):
    app.config['MAX_INTENTOS_ENTREGA'] = 1
    pedido = escenario['nuevoPedido']()
    rutaId = _enCamino(escenario, pedido)
    _falla(escenario, pedido)
    escenario['repa'].post(f'/ruta/{rutaId}/completar')
    assert estadoDe(admin, pedido['id']) == 'por_devolver'


# ------------------------------------- devolucion desde otra ciudad ----

def _llegarAlNorte(admin, red):
    pedido, codigos = red['envioAlNorte']()
    mid = red['abrirManifiesto']()
    for c in codigos:
        admin.post(f'/manifiesto/{mid}/bultos', {'codigo': c})
    assert admin.post(f'/manifiesto/{mid}/despachar', DESPACHO).status_code == 200
    for c in codigos:
        admin.post(f'/manifiesto/{mid}/recibir', {'codigo': c})
    assert estadoDe(admin, pedido['id']) == 'en_agencia_destino'
    return pedido, codigos


def test_devolucion_remota_viaja_de_regreso_al_origen(escenario, admin, red):
    centro, norte = escenario['almacen']['id'], red['norte']['id']
    pedido, codigos = _llegarAlNorte(admin, red)
    url = f"/pedido/{pedido['id']}/estado"
    assert admin.post(url, {'estado': 'por_devolver', 'comentario': 'Destinatario desistio'}).status_code == 200

    # En destino todavia no se puede entregar al remitente
    r = admin.post(url, {'estado': 'devuelto', 'comentario': 'x' * 10})
    assert r.status_code == 409 and 'manifiesto' in r.get_json()['message']

    inv = admin.get(f'/almacen/{norte}/inventario?seccion=por_devolver').get_json()['content']
    assert [f['id'] for f in inv] == [pedido['id']]
    pendientes = admin.get(f'/despachos/pendientes?agencia_id={norte}').get_json()['content']['destinos']
    assert pendientes == [{'agenciaDestino': {'id': centro, 'nombre': 'Almacen Centro'}, 'envios': 1, 'bultos': 1,
                           'pendientesDePago': 0, 'devoluciones': 1}]

    # Manifiesto de regreso Norte -> Centro (una devolucion no se manda a otra agencia)
    mid = admin.post('/manifiesto', {'agenciaOrigenId': norte, 'agenciaDestinoId': centro}).get_json()['content']['id']
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]}).status_code == 201
    assert admin.post(f'/manifiesto/{mid}/despachar', DESPACHO).status_code == 200
    assert estadoDe(admin, pedido['id']) == 'en_transito'
    # El despacho se guarda en UTC y cuenta en el dia local de la agencia que lo despacha
    assert admin.get(f'/almacen/{norte}').get_json()['content']['metricas']['manifiestosDespachadosHoy'] == 1
    porLlegar = admin.get(f'/almacen/{centro}/inventario?seccion=por_llegar').get_json()['content']
    assert [f['id'] for f in porLlegar] == [pedido['id']]

    r = admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]})
    assert 'Devolucion' in r.get_json()['message']
    assert estadoDe(admin, pedido['id']) == 'por_devolver'
    inv = admin.get(f'/almacen/{centro}/inventario?seccion=por_devolver').get_json()['content']
    assert [f['id'] for f in inv] == [pedido['id']]
    assert admin.post(url, {'estado': 'devuelto', 'comentario': 'Entregado al remitente en mostrador',
                            'metodo': 'yape', 'referencia': 'YP-1'}).status_code == 200


# --------------------------------------------- faltantes y extravios ----

def test_bulto_faltante_que_llega_tarde_completa_el_envio(escenario, admin, red):
    pedido, codigos = red['envioAlNorte'](bultos=[{'pesoKg': 1, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}] * 2)
    mid = red['abrirManifiesto']()
    for c in codigos:
        admin.post(f'/manifiesto/{mid}/bultos', {'codigo': c})
    admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)
    admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]})
    assert admin.post(f'/manifiesto/{mid}/cerrar-recepcion', {'observaciones': 'Falto una caja'}).status_code == 200
    assert estadoDe(admin, pedido['id']) == 'en_transito'
    incidencias = admin.get(f"/pedido/{pedido['id']}/incidencias").get_json()['content']
    assert incidencias[0]['tipo'] == 'faltante' and incidencias[0]['estado'] == 'abierta'

    r = admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[1]})
    assert r.status_code == 200 and 'despues del cierre' in r.get_json()['message']
    assert estadoDe(admin, pedido['id']) == 'en_agencia_destino'
    incidencias = admin.get(f"/pedido/{pedido['id']}/incidencias").get_json()['content']
    assert incidencias[0]['estado'] == 'resuelta'
    tipos = [m['tipo'] for m in admin.get(f"/pedido/{pedido['id']}/trazabilidad").get_json()['content']]
    assert 'recibido_tarde' in tipos


def test_envio_perdido_en_transito_se_declara_extraviado(escenario, admin, red):
    pedido, codigos = red['envioAlNorte']()
    mid = red['abrirManifiesto']()
    admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]})
    admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)
    admin.post(f'/manifiesto/{mid}/cerrar-recepcion', {'observaciones': 'No llego nada'})

    url = f"/pedido/{pedido['id']}/estado"
    assert admin.post(url, {'estado': 'cancelado'}).status_code == 409
    assert admin.post(url, {'estado': 'extraviado'}).status_code == 400  # exige constancia
    r = admin.post(url, {'estado': 'extraviado', 'comentario': 'Transportista confirma perdida del bulto'})
    assert r.status_code == 200
    assert estadoDe(admin, pedido['id']) == 'extraviado'


# ------------------------------------------------- recaudo (COD) ----

def test_recaudo_exige_remitente(escenario, admin):
    datos = {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
             'direccionEntregaId': escenario['direccion']['id'], 'pesoKg': 1, 'montoRecaudo': '150.00'}
    r = admin.post('/pedido', datos)
    assert r.status_code == 400 and 'remitente' in r.get_json()['message']


def test_recaudo_se_cobra_rinde_en_caja_y_se_liquida_al_remitente(escenario, admin, app):
    app.config['COMISION_RECAUDO_PORCENTAJE'] = '2'
    tienda = admin.post('/cliente', {'nombre': 'Tienda Online SAC', 'telefono': '955111222'}).get_json()['content']
    pedido = escenario['nuevoPedido'](remitenteId=tienda['id'], montoRecaudo='150.00')
    assert pedido['montoRecaudo'] == '150.00'
    rutaId = _enCamino(escenario, pedido)

    detalle = escenario['repa'].get(f'/ruta/{rutaId}/detalle').get_json()['content']['pedidos'][0]
    assert detalle['totalACobrar'] == '161.00'  # flete 11.00 + producto 150.00

    r = escenario['repa'].post(f"/pedido/{pedido['id']}/entregar-y-cobrar",
                               {**ENTREGA_OK, 'metodo': 'efectivo', 'montoRecaudo': '149.00'})
    assert r.status_code == 409  # el producto se cobra exacto
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/entregar-y-cobrar", {**ENTREGA_OK, 'metodo': 'efectivo'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['content']['totalCobrado'] == '161.00'

    # Mientras el repartidor tiene el efectivo, no se le paga a la tienda
    pend = admin.get('/recaudos/pendientes').get_json()['content'][0]
    assert pend['total'] == '150.00' and pend['enCaja'] == '0.00' and pend['conRepartidor'] == '150.00'
    assert admin.post('/recaudos/liquidar', {'remitenteId': tienda['id'], 'metodo': 'efectivo'}).status_code == 409

    # La ruta rinde flete + recaudo
    r = escenario['repa'].post(f'/ruta/{rutaId}/completar')
    assert r.get_json()['efectivoPorLiquidar'] == '161.00'
    assert admin.post(f'/ruta/{rutaId}/liquidar', {'montoEntregado': '161.00'}).status_code == 201

    pend = admin.get('/recaudos/pendientes').get_json()['content'][0]
    assert pend['enCaja'] == '150.00' and pend['comision'] == '3.00' and pend['aPagar'] == '147.00'
    assert admin.post('/recaudos/liquidar', {'remitenteId': tienda['id'], 'metodo': 'yape'}).status_code == 400
    r = admin.post('/recaudos/liquidar', {'remitenteId': tienda['id'], 'metodo': 'transferencia',
                                          'referencia': 'OP-778899'})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['content']['montoPagado'] == '147.00'
    assert admin.get('/recaudos/pendientes').get_json()['content'] == []
    assert admin.get('/reportes/resumen').get_json()['content']['recaudoPorLiquidar'] == '0.00'
    liquidaciones = admin.get(f"/liquidaciones-recaudo?remitente_id={tienda['id']}").get_json()['content']
    assert liquidaciones[0]['envios'] == 1


# ------------------------------------------------- alcance por agencia ----

def test_operador_de_otra_agencia_no_opera_caja_ni_incidencias_ajenas(client, escenario, admin, red):
    pedido = escenario['nuevoPedido'](modalidadPago='prepagado')
    admin.post(f"/pedido/{pedido['id']}/incidencia", {'tipo': 'reclamo', 'descripcion': 'Cliente reclama demora'})
    incidencia = admin.get('/incidencias').get_json()['content'][0]

    ajeno = _operador(client, admin, red['norte']['id'], 'opnorte', '40000011')
    r = ajeno.post('/pago', {'pedidoId': pedido['id'], 'monto': pedido['monto'], 'metodo': 'efectivo',
                             'estadoPago': 'pagado'})
    assert r.status_code == 404
    assert ajeno.get('/incidencias').get_json()['content'] == []
    assert ajeno.post(f"/incidencia/{incidencia['id']}/resolver", {'resolucion': 'Cerrada sin revisar'}).status_code == 404
    assert ajeno.get('/reportes/resumen').get_json()['content']['totalPedidos'] == 0

    propio = _operador(client, admin, escenario['almacen']['id'], 'opcentro', '40000012')
    assert propio.post('/pago', {'pedidoId': pedido['id'], 'monto': pedido['monto'], 'metodo': 'efectivo',
                                 'estadoPago': 'pagado'}).status_code == 201
    assert len(propio.get('/incidencias').get_json()['content']) == 1
    assert propio.get('/reportes/resumen').get_json()['content']['totalPedidos'] == 1
    assert ajeno.get('/pagos').get_json()['content'] == []
