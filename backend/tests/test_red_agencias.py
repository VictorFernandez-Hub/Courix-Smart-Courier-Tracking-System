"""Fase 2 - Red de agencias: agencia destino, manifiestos de despacho,
recepcion por escaneo, faltantes/sobrantes y operador por agencia."""
import pytest

from conftest import PASSWORD, INSPECCION_OK, iniciarSesion


def bulto(peso=1):
    return {'pesoKg': peso, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}


@pytest.fixture
def red(escenario, admin):
    """Agencia Norte (zona del repartidor 2), tarifa Centro -> Norte y un
    destinatario con direccion en el Norte."""
    zonaNorte = escenario['repartidor2']['zonaId']
    zonaCentro = escenario['zona']['id']
    norte = admin.post('/almacen', {'nombre': 'Agencia Norte', 'calle': 'Av. Norte 1', 'zonaId': zonaNorte}).get_json()['content']
    admin.post('/tarifa', {'zonaOrigenId': zonaCentro, 'zonaDestinoId': zonaNorte, 'precioBase': '15.00',
                           'precioPorKg': '2.00', 'diasEntrega': 2})
    cliente = admin.post('/cliente', {'nombre': 'Pedro Norte', 'telefono': '966777888'}).get_json()['content']
    direccion = admin.post('/direccion-cliente', {'clienteId': cliente['id'], 'zonaId': zonaNorte,
                                                  'calle': 'Calle Norte 22'}).get_json()['content']

    def envioAlNorte(bultos=None, **extra):
        datos = {'clienteId': cliente['id'], 'almacenId': escenario['almacen']['id'],
                 'direccionEntregaId': direccion['id'], 'yaEnAlmacen': True,
                 'bultos': bultos or [bulto()], **INSPECCION_OK, **extra}
        r = admin.post('/pedido', datos)
        assert r.status_code == 201, r.get_json()
        pedido = r.get_json()['content']
        codigos = [b['codigo'] for b in admin.get(f"/pedido/{pedido['id']}/bultos").get_json()['content']]
        return pedido, codigos

    def abrirManifiesto():
        r = admin.post('/manifiesto', {'agenciaOrigenId': escenario['almacen']['id'], 'agenciaDestinoId': norte['id']})
        assert r.status_code == 201, r.get_json()
        return r.get_json()['content']['id']

    return {'norte': norte, 'envioAlNorte': envioAlNorte, 'abrirManifiesto': abrirManifiesto}


DESPACHO = {'transportista': 'Transportes Andinos SAC', 'placa': 'abc-123', 'precinto': 'PR-0091'}


def estadoDe(admin, pedidoId):
    estados = {e['id']: e['nombre'] for e in admin.get('/estados').get_json()['content']}
    return estados[admin.get(f'/pedido/{pedidoId}').get_json()['content']['estadoId']]


# ------------------------------------------------------- agencia destino ----

def test_envio_a_otra_zona_se_asigna_a_la_agencia_destino(escenario, red):
    pedido, _ = red['envioAlNorte']()
    assert pedido['agenciaDestinoId'] == red['norte']['id']
    local = escenario['nuevoPedido']()
    assert local['agenciaDestinoId'] == local['almacenId']  # local: se reparte desde el origen


def test_envio_remoto_no_se_reparte_desde_el_origen(escenario, red):
    pedido, _ = red['envioAlNorte']()
    disponibles = escenario['repa2'].get('/pedidos/disponibles').get_json()['content']
    assert pedido['id'] not in [p['id'] for p in disponibles]
    r = escenario['repa2'].post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor2']['id']})
    assert r.status_code == 409


# ------------------------------------------------------- flujo completo ----

def test_despacho_y_recepcion_completa(escenario, admin, red):
    pedido, codigos = red['envioAlNorte'](bultos=[bulto(), bulto(2)])
    mid = red['abrirManifiesto']()

    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0].lower()}).status_code == 201
    # un envio viaja completo
    r = admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)
    assert r.status_code == 409 and '1 de 2' in r.get_json()['message']
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[1]}).status_code == 201
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[1]}).status_code == 200  # doble escaneo

    assert admin.post(f'/manifiesto/{mid}/despachar', {'transportista': 'X'}).status_code == 400  # faltan datos
    r = admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['content']['placa'] == 'ABC-123'
    assert estadoDe(admin, pedido['id']) == 'en_transito'
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]}).status_code == 409  # ya despachado

    # recepcion en destino: el envio se libera solo cuando llegan todos sus bultos
    admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]})
    assert estadoDe(admin, pedido['id']) == 'en_transito'
    r = admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[1]})
    assert 'listo para reparto' in r.get_json()['message']
    assert estadoDe(admin, pedido['id']) == 'en_agencia_destino'
    assert admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[1]}).status_code == 200  # idempotente

    r = admin.post(f'/manifiesto/{mid}/cerrar-recepcion', {})
    assert r.status_code == 200 and r.get_json()['content']['estado'] == 'recibido'

    # ahora lo reparte el repartidor de la zona destino, no el del origen
    assert pedido['id'] not in [p['id'] for p in escenario['repa'].get('/pedidos/disponibles').get_json()['content']]
    assert pedido['id'] in [p['id'] for p in escenario['repa2'].get('/pedidos/disponibles').get_json()['content']]
    r = escenario['repa'].post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']})
    assert r.status_code == 400
    r = escenario['repa2'].post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor2']['id']})
    assert r.status_code == 200

    eventos = [e['tipo'] for e in admin.get(f"/pedido/{pedido['id']}/trazabilidad").get_json()['content']
               if e['bulto'] == codigos[0]]
    assert eventos == ['admitido', 'manifestado', 'despachado', 'recibido_en_destino']


def test_quitar_de_ruta_devuelve_a_la_agencia_destino(escenario, admin, red):
    pedido, codigos = red['envioAlNorte']()
    mid = red['abrirManifiesto']()
    admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]})
    admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)
    admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]})
    r = escenario['repa2'].post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor2']['id']})
    rutaId = r.get_json()['ruta']['id']
    assert escenario['repa2'].post(f"/ruta/{rutaId}/quitar-pedido/{pedido['id']}").status_code == 200
    assert estadoDe(admin, pedido['id']) == 'en_agencia_destino'


# ------------------------------------------------------- reglas de despacho ----

def test_reglas_de_armado_del_manifiesto(escenario, admin, red):
    mid = red['abrirManifiesto']()
    local = escenario['nuevoPedido']()
    codigoLocal = admin.get(f"/pedido/{local['id']}/bultos").get_json()['content'][0]['codigo']
    r = admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigoLocal})
    assert r.status_code == 409 and 'separalo' in r.get_json()['message']  # va a otra agencia
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': 'CE-NOEX-ISTE-1'}).status_code == 404
    assert admin.post(f'/manifiesto/{mid}/despachar', DESPACHO).status_code == 409  # vacio

    _, codigos = red['envioAlNorte']()
    admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]})
    otro = red['abrirManifiesto']()
    r = admin.post(f'/manifiesto/{otro}/bultos', {'codigo': codigos[0]})
    assert r.status_code == 409 and 'ya esta en el manifiesto' in r.get_json()['message']


def test_prepagado_sin_pago_no_sale_de_la_agencia(admin, red):
    pedido, codigos = red['envioAlNorte'](modalidadPago='prepagado')
    mid = red['abrirManifiesto']()
    r = admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]})
    assert r.status_code == 409 and 'pago' in r.get_json()['message']
    pendientes = admin.get(f"/despachos/pendientes?agencia_id={pedido['almacenId']}").get_json()['content']
    assert pendientes['destinos'][0]['pendientesDePago'] == 1
    admin.post('/pago', {'pedidoId': pedido['id'], 'monto': pedido['monto'], 'metodo': 'transferencia',
                         'estadoPago': 'pagado', 'referencia': 'OP-1'})
    assert admin.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]}).status_code == 201


def test_faltantes_y_sobrantes_en_destino(admin, red):
    pedido, codigos = red['envioAlNorte'](bultos=[bulto(), bulto()])
    extra, codigosExtra = red['envioAlNorte']()
    mid = red['abrirManifiesto']()
    for c in codigos:
        admin.post(f'/manifiesto/{mid}/bultos', {'codigo': c})
    admin.post(f'/manifiesto/{mid}/despachar', DESPACHO)

    r = admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigosExtra[0]})
    assert r.status_code == 409 and 'SOBRANTE' in r.get_json()['message']

    admin.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]})
    assert admin.post(f'/manifiesto/{mid}/cerrar-recepcion', {}).status_code == 400  # exige observacion
    r = admin.post(f'/manifiesto/{mid}/cerrar-recepcion', {'observaciones': 'El chofer dice que no lo cargaron'})
    assert r.status_code == 200 and r.get_json()['content']['estado'] == 'recibido_con_diferencias'

    incidencias = [i for i in admin.get('/incidencias').get_json()['content'] if i['pedidoId'] == pedido['id']]
    assert len(incidencias) == 1 and incidencias[0]['tipo'] == 'faltante'
    assert codigos[1] in incidencias[0]['descripcion']
    assert estadoDe(admin, pedido['id']) == 'en_transito'  # no se reparte incompleto


# ------------------------------------------------------- operador por agencia ----

def test_operador_solo_opera_su_agencia(client, escenario, admin, red):
    centro = escenario['almacen']['id']
    base = {'password': PASSWORD, 'rol': 'operador', 'celular': '987000111'}
    assert admin.post('/usuario', {**base, 'nombre': 'Op Centro', 'usuario': 'opcentro', 'email': 'opc@test.pe',
                                   'dni': '40100100', 'agenciaId': centro}).status_code == 201
    assert admin.post('/usuario', {**base, 'nombre': 'Op Norte', 'usuario': 'opnorte', 'email': 'opn@test.pe',
                                   'dni': '40100200', 'agenciaId': red['norte']['id']}).status_code == 201
    opCentro, opNorte = iniciarSesion(client, 'opcentro'), iniciarSesion(client, 'opnorte')

    local = escenario['nuevoPedido']()  # Centro -> Centro: el operador Norte no lo ve
    assert opNorte.get(f"/pedido/{local['id']}").status_code == 404
    assert local['id'] not in [p['id'] for p in opNorte.get('/pedidos').get_json()['content']]
    assert opCentro.get(f"/pedido/{local['id']}").status_code == 200

    pedido, codigos = red['envioAlNorte']()
    assert opNorte.get(f"/pedido/{pedido['id']}").status_code == 200  # llega a su agencia: si lo ve

    # el operador Norte no puede abrir manifiestos que salgan del Centro
    r = opNorte.post('/manifiesto', {'agenciaOrigenId': centro, 'agenciaDestinoId': red['norte']['id']})
    assert r.status_code == 403
    assert opNorte.get('/despachos/pendientes?agencia_id=%d' % centro).status_code == 403
    assert opNorte.get('/despachos/pendientes').get_json()['content']['agenciaOrigenId'] == red['norte']['id']
    mid = opCentro.post('/manifiesto', {'agenciaDestinoId': red['norte']['id']}).get_json()['content']['id']
    assert opNorte.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]}).status_code == 403
    assert opCentro.post(f'/manifiesto/{mid}/bultos', {'codigo': codigos[0]}).status_code == 201
    assert opCentro.post(f'/manifiesto/{mid}/despachar', DESPACHO).status_code == 200
    # recibe solo la agencia destino
    assert opCentro.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]}).status_code == 403
    assert opNorte.post(f'/manifiesto/{mid}/recibir', {'codigo': codigos[0]}).status_code == 200


def test_operador_no_admite_en_otra_agencia(client, escenario, admin, red):
    admin.post('/usuario', {'password': PASSWORD, 'rol': 'operador', 'celular': '987000111', 'nombre': 'Op Norte',
                            'usuario': 'opnorte', 'email': 'opn@test.pe', 'dni': '40100200',
                            'agenciaId': red['norte']['id']})
    opNorte = iniciarSesion(client, 'opnorte')
    r = opNorte.post('/pedido', {'clienteId': escenario['cliente']['id'], 'almacenId': escenario['almacen']['id'],
                                 'direccionEntregaId': escenario['direccion']['id'], 'yaEnAlmacen': True,
                                 'bultos': [bulto()], **INSPECCION_OK})
    assert r.status_code == 403
