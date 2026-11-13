"""Agencias: alta con codigo unico, ficha, inventario por seccion con
antiguedad, hoja de conteo, kardex, bajas protegidas y alcance del operador."""
from datetime import timedelta

from conftest import INSPECCION_OK, PASSWORD, iniciarSesion


def _agenciaNorte(admin, escenario):
    zonaNorte = escenario['repartidor2']['zonaId']
    norte = admin.post('/almacen', {'nombre': 'Agencia Norte', 'calle': 'Av. Norte 1', 'zonaId': zonaNorte,
                                    'codigo': 'nor01'}).get_json()['content']
    admin.post('/tarifa', {'zonaOrigenId': escenario['zona']['id'], 'zonaDestinoId': zonaNorte,
                           'precioBase': '15.00', 'precioPorKg': '2.00', 'diasEntrega': 2})
    cliente = admin.post('/cliente', {'nombre': 'Pedro Norte', 'telefono': '966777888'}).get_json()['content']
    direccion = admin.post('/direccion-cliente', {'clienteId': cliente['id'], 'zonaId': zonaNorte,
                                                  'calle': 'Calle Norte 22'}).get_json()['content']
    r = admin.post('/pedido', {'clienteId': cliente['id'], 'almacenId': escenario['almacen']['id'],
                               'direccionEntregaId': direccion['id'], 'yaEnAlmacen': True,
                               'bultos': [{'pesoKg': 1, 'largoCm': 10, 'anchoCm': 10, 'altoCm': 10}] * 2,
                               **INSPECCION_OK})
    assert r.status_code == 201, r.get_json()
    return norte, r.get_json()['content']


def _operador(client, admin, agenciaId, usuario='opera', dni='40000003'):
    r = admin.post('/usuario', {'nombre': 'Operador Centro', 'usuario': usuario, 'email': f'{usuario}@test.pe',
                                'dni': dni, 'celular': '987654321', 'password': PASSWORD, 'rol': 'operador',
                                'agenciaId': agenciaId})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['content'], iniciarSesion(client, usuario)


def test_alta_con_codigo_unico_y_edicion_auditada(escenario, admin):
    centro = escenario['almacen']
    assert centro['codigo'].startswith('AG')  # codigo provisional cuando no se indica

    zona = escenario['zona']['id']
    r = admin.post('/almacen', {'nombre': 'Lima Sur', 'calle': 'Av. Sur 9', 'zonaId': zona, 'codigo': 'lim 01'})
    assert r.status_code == 201 and r.get_json()['content']['codigo'] == 'LIM01'
    sur = r.get_json()['content']

    assert admin.post('/almacen', {'nombre': 'lima sur', 'calle': 'Otra 1', 'zonaId': zona}).status_code == 409
    assert admin.post('/almacen', {'nombre': 'Lima Este', 'calle': 'Otra 1', 'zonaId': zona,
                                   'codigo': 'LIM01'}).status_code == 409
    assert admin.post('/almacen', {'nombre': 'Lima Este', 'calle': 'Otra 1', 'zonaId': zona,
                                   'codigo': 'L*1'}).status_code == 400

    r = admin.put(f"/almacen/{sur['id']}", {'horario': 'Lun-Sab 8:00-19:00', 'capacidadBultos': 200,
                                            'email': 'SUR@courrier.pe', 'nombre': 'Lima Sur'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['content']['email'] == 'sur@courrier.pe'
    actividad = admin.get(f"/almacen/{sur['id']}/actividad").get_json()['content']
    assert [a['accion'] for a in actividad] == ['almacen_editado', 'almacen_creado']
    # Solo se registran los campos que cambiaron (el nombre llego igual)
    assert 'nombre' not in actividad[0]['detalle'] and 'horario' in actividad[0]['detalle']


def test_responsable_debe_ser_personal_activo(escenario, admin):
    almacen = escenario['almacen']
    repa = admin.get('/usuarios').get_json()['content']
    repartidor = next(u for u in repa if u['rol'] == 'repartidor')
    assert admin.put(f"/almacen/{almacen['id']}", {'responsableId': repartidor['id']}).status_code == 400

    adminId = next(u for u in repa if u['rol'] == 'admin')['id']
    assert admin.put(f"/almacen/{almacen['id']}", {'responsableId': adminId}).status_code == 200
    ficha = admin.get(f"/almacen/{almacen['id']}").get_json()['content']
    assert ficha['responsable']['nombre'] == 'Admin'


def test_inventario_por_seccion_y_panel(escenario, admin):
    almacen = escenario['almacen']
    local = escenario['nuevoPedido']()                       # en almacen, se reparte aqui
    porIngresar = escenario['nuevoPedido'](yaEnAlmacen=False, bultos=None, monto='10.00', motivoMonto='Peso por confirmar')
    norte, remoto = _agenciaNorte(admin, escenario)          # en almacen, debe viajar al norte (2 bultos)

    r = admin.get(f"/almacen/{almacen['id']}/inventario")
    assert r.status_code == 200, r.get_json()
    datos = r.get_json()
    secciones = {f['id']: f['seccion'] for f in datos['content']}
    assert secciones == {local['id']: 'para_reparto', porIngresar['id']: 'por_ingresar',
                         remoto['id']: 'por_despachar'}
    assert datos['conteos']['por_despachar'] == 1 and datos['conteos']['para_reparto'] == 1
    fila = next(f for f in datos['content'] if f['id'] == remoto['id'])
    assert fila['bultos'] == 2 and fila['agenciaReparto'] == 'Agencia Norte' and fila['destinatario'] == 'Pedro Norte'

    soloStock = admin.get(f"/almacen/{almacen['id']}/inventario?seccion=stock").get_json()['content']
    assert {f['id'] for f in soloStock} == {local['id'], remoto['id']}
    buscado = admin.get(f"/almacen/{almacen['id']}/inventario?q={remoto['codigoGuia']}").get_json()['content']
    assert [f['id'] for f in buscado] == [remoto['id']]

    panel = admin.get('/almacenes/panel').get_json()
    centro = next(a for a in panel['content'] if a['id'] == almacen['id'])
    assert centro['metricas']['stockEnvios'] == 2 and centro['metricas']['stockBultos'] == 3
    assert panel['resumen']['porDespachar'] == 2 and panel['resumen']['paraReparto'] == 1
    nor = next(a for a in panel['content'] if a['id'] == norte['id'])
    assert nor['metricas']['stockBultos'] == 0  # todavia no viaja: no se cuenta en el destino


def test_paquete_quieto_se_marca_como_estancado(app, escenario, admin):
    from app.extensions import conexion
    from app.models import HistorialEstadoModel, PedidoModel

    almacen = escenario['almacen']
    pedido = escenario['nuevoPedido']()
    fila = admin.get(f"/almacen/{almacen['id']}/inventario").get_json()['content'][0]
    assert fila['estancado'] is False and fila['dias'] == 0

    hace5 = conexion.session.query(PedidoModel.fechaCreacion).filter_by(id=pedido['id']).scalar() - timedelta(days=5)
    conexion.session.query(HistorialEstadoModel).filter_by(pedidoId=pedido['id']).update({'fecha': hace5})
    conexion.session.commit()

    fila = admin.get(f"/almacen/{almacen['id']}/inventario").get_json()['content'][0]
    assert fila['estancado'] is True and fila['dias'] == 5
    assert admin.get('/almacenes/panel').get_json()['resumen']['estancados'] == 1
    soloEstancados = admin.get(f"/almacen/{almacen['id']}/inventario?estancados=true").get_json()['content']
    assert [f['id'] for f in soloEstancados] == [pedido['id']]


def test_hoja_de_conteo_y_kardex(escenario, admin):
    almacen = escenario['almacen']
    pedido = escenario['nuevoPedido']()
    r = admin.get(f"/almacen/{almacen['id']}/inventario/exportar")
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    texto = r.get_data(as_text=True)
    assert f"{pedido['codigoGuia']}-1" in texto and 'Encontrado' in texto
    acciones = [a['accion'] for a in admin.get(f"/almacen/{almacen['id']}/actividad").get_json()['content']]
    assert 'inventario_exportado' in acciones

    movimientos = admin.get(f"/almacen/{almacen['id']}/movimientos").get_json()
    assert movimientos['content'][0]['tipo'] == 'admitido'
    assert movimientos['content'][0]['bulto'] == f"{pedido['codigoGuia']}-1"


def test_baja_protegida_y_reactivacion(client, escenario, admin):
    almacen = escenario['almacen']
    escenario['nuevoPedido']()
    _operador(client, admin, almacen['id'])
    r = admin.post(f"/almacen/{almacen['id']}/desactivar", {'motivo': 'Cierre'})
    assert r.status_code == 409
    assert 'pedido(s) en curso' in r.get_json()['message'] and 'usuario(s) asignado(s)' in r.get_json()['message']

    vacia = admin.post('/almacen', {'nombre': 'Agencia Temporal', 'calle': 'Calle 1',
                                    'zonaId': escenario['zona']['id']}).get_json()['content']
    assert admin.post(f"/almacen/{vacia['id']}/desactivar", {'motivo': 'Local cerrado'}).status_code == 200
    ficha = admin.get(f"/almacen/{vacia['id']}").get_json()['content']
    assert ficha['almacen']['activo'] is False and ficha['almacen']['motivoDesactivacion'] == 'Local cerrado'
    assert admin.post(f"/almacen/{vacia['id']}/activar").status_code == 200
    assert admin.get(f"/almacen/{vacia['id']}").get_json()['content']['almacen']['motivoDesactivacion'] is None
    acciones = [a['accion'] for a in admin.get(f"/almacen/{vacia['id']}/actividad").get_json()['content']]
    assert acciones[:2] == ['almacen_activado', 'almacen_desactivado']


def test_operador_solo_ve_su_agencia(client, escenario, admin):
    almacen = escenario['almacen']
    norte, _ = _agenciaNorte(admin, escenario)
    _, op = _operador(client, admin, almacen['id'])

    panel = op.get('/almacenes/panel').get_json()['content']
    assert [a['id'] for a in panel] == [almacen['id']]
    assert op.get(f"/almacen/{almacen['id']}").status_code == 200
    assert op.get(f"/almacen/{almacen['id']}/inventario").status_code == 200
    assert op.get(f"/almacen/{norte['id']}").status_code == 404
    assert op.get(f"/almacen/{norte['id']}/inventario").status_code == 404
    assert op.put(f"/almacen/{almacen['id']}", {'horario': 'x'}).status_code == 403
    # La lista simple para selectores sigue mostrando toda la red
    assert len(op.get('/almacenes').get_json()['content']) == 2
