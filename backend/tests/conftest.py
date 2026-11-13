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
# El captcha se prueba aparte (test_acceso.py), activandolo en esas pruebas.
os.environ['CAPTCHA_HABILITADO'] = 'false'
os.environ.pop('ORIGENES_PERMITIDOS', None)

from werkzeug.security import generate_password_hash  # noqa: E402

from app import crear_app  # noqa: E402
from app.cli import sembrarEstados  # noqa: E402
from app.extensions import conexion  # noqa: E402
from app.models import UsuarioModel  # noqa: E402

aplicacion = crear_app()

PASSWORD = 'ClaveSegura123'

BULTO_2KG = {'bultos': [{'pesoKg': 2, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}]}
# Constancia de entrega minima: quien recibe, su DNI y su firma
FIRMA = 'data:image/png;base64,' + 'A' * 100
ENTREGA_OK = {'nombreReceptor': 'Ana Torres', 'dniReceptor': '12345678', 'firma': FIRMA}
INSPECCION_OK = {'estadoProducto': 'bueno', 'embalaje': 'adecuado', 'declaraSinProhibidos': True}


@pytest.fixture
def app():
    with aplicacion.app_context():
        conexion.drop_all()
        conexion.create_all()
        sembrarEstados()
        conexion.session.add(UsuarioModel(
            nombre='Admin', nombreUsuario='admin', email='admin@test.pe', passwordHash=generate_password_hash(PASSWORD), rol='admin'))
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


def iniciarSesion(client, usuario, password=PASSWORD):
    # Acepta 'op' o 'op@test.pe' (en las pruebas el usuario es la parte antes de la @)
    r = client.post('/login', json={'usuario': usuario.split('@')[0], 'password': password})
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
        u = admin.post('/usuario', {'nombre': 'Repa', 'usuario': correo.split('@')[0], 'email': correo,
                                    'dni': f'{abs(hash(correo)) % 10**8:08d}', 'celular': '987654321',
                                    'password': PASSWORD, 'rol': 'repartidor'})
        assert u.status_code == 201, u.get_json()
        perfil = admin.post('/repartidor', {'usuarioId': u.get_json()['content']['id'], 'zonaId': zonaId}).get_json()['content']
        return perfil, iniciarSesion(client, correo)

    repartidor, repa = crearRepartidor('repa@test.pe', zona['id'])
    repartidor2, repa2 = crearRepartidor('repa2@test.pe', otraZona['id'])

    def nuevoPedido(**extra):
        # Admision completa en mostrador: un bulto de 2 kg (10x10x10 cm = 0.2 kg
        # volumetrico, asi que se cobra el peso real) e inspeccion aprobada.
        datos = {'clienteId': cliente['id'], 'almacenId': almacen['id'], 'direccionEntregaId': direccion['id'],
                 'yaEnAlmacen': True, **BULTO_2KG, **INSPECCION_OK}
        datos.update(extra)
        r = admin.post('/pedido', datos)
        assert r.status_code == 201, r.get_json()
        return r.get_json()['content']

    return {
        'zona': zona, 'almacen': almacen, 'cliente': cliente, 'direccion': direccion,
        'repartidor': repartidor, 'repa': repa, 'repartidor2': repartidor2, 'repa2': repa2,
        'nuevoPedido': nuevoPedido,
    }
