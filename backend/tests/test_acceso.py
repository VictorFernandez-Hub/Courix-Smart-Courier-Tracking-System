"""Login por nombre de usuario, captcha y recuperacion de contrasena."""
import pytest

import app.core.captcha as modCaptcha
import sys

import app.routes.auth  # noqa: F401
from conftest import PASSWORD, iniciarSesion

modAuth = sys.modules['app.routes.auth']  # (app.routes.auth como atributo es el blueprint)


@pytest.fixture
def conCaptcha(app, monkeypatch):
    """Activa el captcha y hace que todos los codigos sean 'AAAAA'."""
    app.config['CAPTCHA_HABILITADO'] = True
    monkeypatch.setattr(modCaptcha._aleatorio, 'choice', lambda secuencia: 'A')
    yield
    app.config['CAPTCHA_HABILITADO'] = False


def nuevoCaptcha(client):
    r = client.get('/captcha')
    assert r.status_code == 200
    contenido = r.get_json()['content']
    assert contenido['imagen'].startswith('data:image/png;base64,')
    return contenido['captchaId']


@pytest.fixture
def correos(monkeypatch):
    enviados = []
    monkeypatch.setattr(modAuth, 'enviarCorreo',
                        lambda destino, asunto, cuerpo, enlaceDesarrollo=None: enviados.append(
                            {'destino': destino, 'enlace': enlaceDesarrollo}))
    return enviados


# ------------------------------------------------------------ usuario ----

def test_login_es_por_usuario_y_no_por_email(client):
    assert client.post('/login', json={'usuario': 'ADMIN', 'password': PASSWORD}).status_code == 200
    r = client.post('/login', json={'usuario': 'admin@test.pe', 'password': PASSWORD})
    assert r.status_code == 401


def test_crear_usuario_valida_formato_y_duplicados(admin):
    base = {'nombre': 'Op', 'email': 'op@test.pe', 'dni': '40000002', 'celular': '987654321',
            'password': PASSWORD, 'rol': 'operador'}
    assert admin.post('/usuario', {**base, 'usuario': 'con espacio'}).status_code == 400
    assert admin.post('/usuario', {**base, 'usuario': 'ab'}).status_code == 400
    assert admin.post('/usuario', {**base, 'usuario': 'Op.Lima'}).status_code == 201
    r = admin.post('/usuario', {**base, 'email': 'otro@test.pe', 'usuario': 'op.lima'})
    assert r.status_code == 409


# ------------------------------------------------------------ captcha ----

def test_login_exige_captcha(client, conCaptcha):
    r = client.post('/login', json={'usuario': 'admin', 'password': PASSWORD})
    assert r.status_code == 400
    captchaId = nuevoCaptcha(client)
    r = client.post('/login', json={'usuario': 'admin', 'password': PASSWORD,
                                    'captchaId': captchaId, 'captchaRespuesta': 'XXXXX'})
    assert r.status_code == 400
    captchaId = nuevoCaptcha(client)
    r = client.post('/login', json={'usuario': 'admin', 'password': PASSWORD,
                                    'captchaId': captchaId, 'captchaRespuesta': 'aaaaa'})
    assert r.status_code == 200


def test_captcha_es_de_un_solo_uso(client, conCaptcha):
    captchaId = nuevoCaptcha(client)
    datos = {'usuario': 'admin', 'password': 'mala-clave-1', 'captchaId': captchaId, 'captchaRespuesta': 'AAAAA'}
    assert client.post('/login', json=datos).status_code == 401  # captcha ok, clave mala
    # el mismo captcha ya no sirve aunque la respuesta sea correcta
    assert client.post('/login', json={**datos, 'password': PASSWORD}).status_code == 400


def test_captcha_fallido_no_cuenta_como_intento_de_login(client, app, conCaptcha):
    for _ in range(app.config['MAX_INTENTOS_LOGIN'] + 1):
        client.post('/login', json={'usuario': 'admin', 'password': 'x',
                                    'captchaId': nuevoCaptcha(client), 'captchaRespuesta': 'ZZZZZ'})
    r = client.post('/login', json={'usuario': 'admin', 'password': PASSWORD,
                                    'captchaId': nuevoCaptcha(client), 'captchaRespuesta': 'AAAAA'})
    assert r.status_code == 200


# --------------------------------------------- recuperacion de contrasena ----

def test_recuperacion_completa(client, correos):
    vieja = iniciarSesion(client, 'admin')
    r = client.post('/password/olvide', json={'identificador': 'admin'})
    assert r.status_code == 200
    assert len(correos) == 1 and correos[0]['destino'] == 'admin@test.pe'
    token = correos[0]['enlace'].split('token=')[1]

    nueva = 'OtraClave456789'
    assert client.post('/password/restablecer', json={'token': token, 'passwordNueva': 'corta'}).status_code == 400
    r = client.post('/password/restablecer', json={'token': token, 'passwordNueva': nueva})
    assert r.status_code == 200

    assert vieja.get('/usuario/me').status_code == 401  # las sesiones abiertas se cierran
    assert client.post('/login', json={'usuario': 'admin', 'password': PASSWORD}).status_code == 401
    assert client.post('/login', json={'usuario': 'admin', 'password': nueva}).status_code == 200
    # el enlace no se puede reutilizar
    assert client.post('/password/restablecer', json={'token': token, 'passwordNueva': 'Tercera12345'}).status_code == 400


def test_recuperacion_no_revela_si_la_cuenta_existe(client, correos):
    r1 = client.post('/password/olvide', json={'identificador': 'noexiste'})
    r2 = client.post('/password/olvide', json={'identificador': 'admin@test.pe'})
    assert r1.status_code == r2.status_code == 200
    assert r1.get_json()['message'] == r2.get_json()['message']
    assert len(correos) == 1  # solo se envio a la cuenta real (buscada por email)


def test_recuperacion_limita_reenvios_y_solo_vale_el_ultimo(client, app, correos):
    from app.extensions import conexion
    from app.models import RecuperacionPasswordModel
    client.post('/password/olvide', json={'identificador': 'admin'})
    client.post('/password/olvide', json={'identificador': 'admin'})
    assert len(correos) == 1  # el segundo pedido en menos de 2 minutos no reenvia

    # Simula que pasaron 3 minutos y pide de nuevo: el primer enlace queda anulado
    from datetime import timedelta
    for fila in conexion.session.query(RecuperacionPasswordModel).all():
        fila.fechaCreacion = fila.fechaCreacion - timedelta(minutes=3)
    conexion.session.commit()
    client.post('/password/olvide', json={'identificador': 'admin'})
    assert len(correos) == 2
    primero = correos[0]['enlace'].split('token=')[1]
    segundo = correos[1]['enlace'].split('token=')[1]
    assert client.post('/password/restablecer', json={'token': primero, 'passwordNueva': 'OtraClave456789'}).status_code == 400
    assert client.post('/password/restablecer', json={'token': segundo, 'passwordNueva': 'OtraClave456789'}).status_code == 200


def test_recuperacion_exige_captcha(client, conCaptcha, correos):
    assert client.post('/password/olvide', json={'identificador': 'admin'}).status_code == 400
    r = client.post('/password/olvide', json={'identificador': 'admin', 'captchaId': nuevoCaptcha(client),
                                              'captchaRespuesta': 'AAAAA'})
    assert r.status_code == 200 and len(correos) == 1


def test_recuperacion_desbloquea_la_cuenta(client, app, correos):
    for _ in range(app.config['MAX_INTENTOS_LOGIN']):
        client.post('/login', json={'usuario': 'admin', 'password': 'mala-clave-1'})
    assert client.post('/login', json={'usuario': 'admin', 'password': PASSWORD}).status_code == 429
    client.post('/password/olvide', json={'identificador': 'admin'})
    token = correos[0]['enlace'].split('token=')[1]
    client.post('/password/restablecer', json={'token': token, 'passwordNueva': 'OtraClave456789'})
    assert client.post('/login', json={'usuario': 'admin', 'password': 'OtraClave456789'}).status_code == 200


def test_datos_personales_del_usuario(admin):
    base = {'nombre': 'Ana Ruiz', 'usuario': 'aruiz', 'email': 'aruiz@test.pe', 'password': PASSWORD,
            'rol': 'operador', 'celular': '+51 987-654-321', 'direccion': 'Av. Arequipa 123, Lima'}
    assert admin.post('/usuario', base).status_code == 400  # falta el DNI
    assert admin.post('/usuario', {**base, 'dni': '12'}).status_code == 400  # DNI invalido
    assert admin.post('/usuario', {**base, 'dni': '45678912', 'celular': 'abc'}).status_code == 400
    r = admin.post('/usuario', {**base, 'dni': '45678912'})
    assert r.status_code == 201, r.get_json()
    r = admin.post('/usuario', {**base, 'usuario': 'otra', 'email': 'otra@test.pe', 'dni': '45678912'})
    assert r.status_code == 409  # DNI repetido

    creado = [u for u in admin.get('/usuarios').get_json()['content'] if u['nombreUsuario'] == 'aruiz'][0]
    assert creado['dni'] == '45678912' and creado['celular'] == '+51987654321'
    assert creado['direccion'] == 'Av. Arequipa 123, Lima'
    assert admin.put(f"/usuario/{creado['id']}", {'celular': '912345678', 'direccion': 'Jr. Lima 5'}).status_code == 200
    editado = [u for u in admin.get('/usuarios').get_json()['content'] if u['id'] == creado['id']][0]
    assert editado['celular'] == '912345678' and editado['direccion'] == 'Jr. Lima 5'
