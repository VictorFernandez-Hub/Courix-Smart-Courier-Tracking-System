"""Autenticacion, revocacion de sesiones y autorizacion por objeto."""
from conftest import Api, PASSWORD, iniciarSesion


def test_no_se_puede_crear_usuario_sin_token(client):
    r = client.post('/usuario', json={'nombre': 'X', 'email': 'x@test.pe', 'password': PASSWORD, 'rol': 'admin'})
    assert r.status_code == 401


def test_politica_de_password(admin):
    r = admin.post('/usuario', {'nombre': 'Op', 'email': 'op@test.pe', 'password': 'corta', 'rol': 'operador'})
    assert r.status_code == 400
    assert 'al menos 10' in r.get_json()['message']


def test_login_bloquea_tras_intentos_fallidos(client):
    for _ in range(5):
        assert client.post('/login', json={'email': 'admin@test.pe', 'password': 'mala-clave-1'}).status_code == 401
    r = client.post('/login', json={'email': 'admin@test.pe', 'password': PASSWORD})
    assert r.status_code == 429


def test_login_no_revela_si_el_email_existe(client):
    r1 = client.post('/login', json={'email': 'noexiste@test.pe', 'password': 'x'})
    r2 = client.post('/login', json={'email': 'admin@test.pe', 'password': 'x'})
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json()['message'] == r2.get_json()['message']


def test_desactivar_usuario_revoca_su_token_al_instante(client, admin):
    admin.post('/usuario', {'nombre': 'Op', 'email': 'op@test.pe', 'password': PASSWORD, 'rol': 'operador'})
    operador = iniciarSesion(client, 'op@test.pe')
    assert operador.get('/clientes').status_code == 200

    idOp = [u for u in admin.get('/usuarios').get_json()['content'] if u['email'] == 'op@test.pe'][0]['id']
    admin.post(f'/usuario/{idOp}/desactivar')
    assert operador.get('/clientes').status_code == 401


def test_cambio_de_rol_aplica_de_inmediato(client, admin):
    admin.post('/usuario', {'nombre': 'Op', 'email': 'op@test.pe', 'password': PASSWORD, 'rol': 'admin'})
    otro = iniciarSesion(client, 'op@test.pe')
    idOtro = [u for u in admin.get('/usuarios').get_json()['content'] if u['email'] == 'op@test.pe'][0]['id']
    admin.put(f'/usuario/{idOtro}', {'rol': 'operador'})
    # el token viejo (con rol admin) deja de servir
    assert otro.post('/zona', {'nombre': 'Hack'}).status_code == 401


def test_refresh_token(client):
    r = client.post('/login', json={'email': 'admin@test.pe', 'password': PASSWORD}).get_json()
    nuevo = client.post('/token/refresh', headers={'Authorization': f'Bearer {r["refreshToken"]}'})
    assert nuevo.status_code == 200
    assert Api(client, nuevo.get_json()['accessToken']).get('/usuarios').status_code == 200
    # un access token no sirve como refresh
    assert client.post('/token/refresh', headers={'Authorization': f'Bearer {r["accessToken"]}'}).status_code in (401, 422)


def test_cambiar_password_cierra_otras_sesiones(client):
    vieja = iniciarSesion(client, 'admin@test.pe')
    actual = iniciarSesion(client, 'admin@test.pe')
    r = actual.post('/usuario/me/password', {'passwordActual': PASSWORD, 'passwordNueva': 'OtraClave4567'})
    assert r.status_code == 200
    assert vieja.get('/usuarios').status_code == 401
    assert Api(client, r.get_json()['accessToken']).get('/usuarios').status_code == 200


def test_repartidor_no_ve_datos_de_clientes_ni_pedidos_ajenos(escenario):
    repa, repa2 = escenario['repa'], escenario['repa2']
    pedido = escenario['nuevoPedido']()
    assert repa.post(f'/pedido/{pedido["id"]}/tomar', {'repartidorId': escenario['repartidor']['id']}).status_code == 200

    assert repa2.get('/clientes').status_code == 403
    assert repa2.get(f'/cliente/{escenario["cliente"]["id"]}/direcciones').status_code == 403
    assert repa2.get(f'/pedido/{pedido["id"]}').status_code == 404
    assert repa2.get(f'/pedido/{pedido["id"]}/historial').status_code == 404
    assert repa2.get('/pedidos').get_json()['content'] == []
    assert len(repa2.get('/repartidores').get_json()['content']) == 1
    # el dueno si lo ve
    assert repa.get(f'/pedido/{pedido["id"]}').status_code == 200
    assert len(repa.get('/pedidos').get_json()['content']) == 1


def test_errores_internos_no_filtran_detalles(client, admin):
    r = admin.post('/pedido', {'clienteId': 'abc'})
    assert r.status_code == 400
    assert 'Traceback' not in r.get_data(as_text=True)


def test_cabeceras_de_seguridad(client):
    r = client.get('/')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'DENY'
    assert 'X-Request-ID' in r.headers
