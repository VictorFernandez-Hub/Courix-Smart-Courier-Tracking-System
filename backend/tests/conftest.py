import os
import tempfile

import pytest

# Se fijan valores de prueba ANTES de crear la app (load_dotenv no pisa
# variables ya definidas). Base SQLite temporal: nunca toca tu MySQL real.
_dbTemporal = os.path.join(tempfile.mkdtemp(), 'courrier_test.db')
os.environ['APP_ENV'] = 'testing'
os.environ['DATABASE_URL'] = f'sqlite:///{_dbTemporal}'
os.environ['JWT_SECRET_KEY'] = 'clave-de-pruebas-no-usar-en-produccion-0123456789'
os.environ['RATELIMIT_ENABLED'] = 'false'
os.environ.pop('ORIGENES_PERMITIDOS', None)

from werkzeug.security import generate_password_hash  # noqa: E402

from app import crear_app  # noqa: E402
from app.cli import sembrarEstados  # noqa: E402
from app.extensions import conexion  # noqa: E402
from app.models import UsuarioModel  # noqa: E402

aplicacion = crear_app()

PASSWORD = 'ClaveSegura123'


@pytest.fixture
def app():
    with aplicacion.app_context():
        conexion.drop_all()
        conexion.create_all()
        sembrarEstados()
        conexion.session.add(UsuarioModel(
            nombre='Admin', email='admin@test.pe', passwordHash=generate_password_hash(PASSWORD), rol='admin'))
        conexion.session.commit()
        yield aplicacion
        conexion.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


class Api:
    """Pequeno helper para no repetir cabeceras en cada prueba."""

    def __init__(self, client, token=None):
        self.client = client
        self.token = token

    def _h(self):
        return {'Authorization': f'Bearer {self.token}'} if self.token else {}

    def get(self, url):
        return self.client.get(url, headers=self._h())

    def post(self, url, json=None):
        return self.client.post(url, json=json if json is not None else {}, headers=self._h())

    def put(self, url, json=None):
        return self.client.put(url, json=json or {}, headers=self._h())


def iniciarSesion(client, correo, password=PASSWORD):
    r = client.post('/login', json={'email': correo, 'password': password})
    assert r.status_code == 200, r.get_json()
    return Api(client, r.get_json()['accessToken'])


@pytest.fixture
def admin(client):
    return iniciarSesion(client, 'admin@test.pe')


@pytest.fixture
def escenario(client, admin):
    """Zona + almacen + tarifa + cliente con direccion + repartidor con perfil."""
    zona = admin.post('/zona', {'nombre': 'Centro'}).get_json()['content']
    otraZona = admin.post('/zona', {'nombre': 'Norte'}).get_json()['content']
    almacen = admin.post('/almacen', {'nombre': 'Almacen Centro', 'calle': 'Av. Principal 100', 'zonaId': zona['id']}).get_json()['content']
    admin.post('/tarifa', {'zonaOrigenId': zona['id'], 'zonaDestinoId': zona['id'], 'precioBase': '8.00', 'precioPorKg': '1.50'})
    cliente = admin.post('/cliente', {'nombre': 'Ana Torres', 'telefono': '987654321', 'dni': '12345678'}).get_json()['content']
    direccion = admin.post('/direccion-cliente', {
        'clienteId': cliente['id'], 'zonaId': zona['id'], 'calle': 'Jr. Bolivar 456'}).get_json()['content']

    def crearRepartidor(correo, zonaId):
        u = admin.post('/usuario', {'nombre': 'Repa', 'email': correo, 'password': PASSWORD, 'rol': 'repartidor'})
        assert u.status_code == 201, u.get_json()
        perfil = admin.post('/repartidor', {'usuarioId': u.get_json()['content']['id'], 'zonaId': zonaId}).get_json()['content']
        return perfil, iniciarSesion(client, correo)

    repartidor, repa = crearRepartidor('repa@test.pe', zona['id'])
    repartidor2, repa2 = crearRepartidor('repa2@test.pe', otraZona['id'])

    def nuevoPedido(**extra):
        datos = {'clienteId': cliente['id'], 'almacenId': almacen['id'], 'direccionEntregaId': direccion['id'],
                 'pesoKg': 2, 'yaEnAlmacen': True}
        datos.update(extra)
        r = admin.post('/pedido', datos)
        assert r.status_code == 201, r.get_json()
        return r.get_json()['content']

    return {
        'zona': zona, 'almacen': almacen, 'cliente': cliente, 'direccion': direccion,
        'repartidor': repartidor, 'repa': repa, 'repartidor2': repartidor2, 'repa2': repa2,
        'nuevoPedido': nuevoPedido,
    }
