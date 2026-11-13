"""Modulo de clientes: documentos, duplicados, edicion auditada, ficha 360,
historial en ambos roles, direcciones y exportacion."""
from tests.conftest import BULTO_2KG, INSPECCION_OK, iniciarSesion  # noqa: F401

RUC_EMPRESA = '20100070970'


def _crear(admin, **datos):
    base = {'nombre': 'Cliente Prueba', 'telefono': '987000111'}
    base.update(datos)
    return admin.post('/cliente', base)


def test_documento_se_valida_y_clasifica(admin):
    r = _crear(admin, dni='45678912')
    assert r.status_code == 201
    assert r.get_json()['content']['tipoDocumento'] == 'DNI'
    assert r.get_json()['content']['tipoCliente'] == 'persona'

    r = _crear(admin, nombre='Supermercados SAC', dni=RUC_EMPRESA, telefono='014445566')
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['content']['tipoDocumento'] == 'RUC'
    assert r.get_json()['content']['tipoCliente'] == 'empresa'

    assert _crear(admin, dni='20100070971').status_code == 400               # verificador incorrecto
    assert _crear(admin, tipoDocumento='DNI', dni='1234567').status_code == 400
    assert _crear(admin, tipoCliente='empresa', dni='45678913').status_code == 400  # empresa sin RUC
    assert _crear(admin, tipoCliente='persona', dni='20131312955').status_code == 400
    assert _crear(admin, tipoDocumento='CE', dni='001234567').status_code == 201


def test_documento_duplicado_se_rechaza(admin):
    assert _crear(admin, dni='45678912').status_code == 201
    r = _crear(admin, nombre='Otra persona', dni='45678912')
    assert r.status_code == 409
    assert 'Ya existe' in r.get_json()['message']

    verif = admin.get('/clientes/verificar?dni=45678912&telefono=987000111').get_json()['content']
    assert len(verif['documento']) == 1 and len(verif['telefono']) == 1


def test_editar_cliente_audita_campos(admin):
    c = _crear(admin, dni='45678912').get_json()['content']
    otro = _crear(admin, nombre='Otro', dni='45678913', telefono='955000111').get_json()['content']

    r = admin.put(f'/cliente/{c["id"]}', {'nombre': 'Cliente Editado', 'notas': 'Atiende de 9 a 1'})
    assert r.status_code == 200
    assert r.get_json()['content']['nombre'] == 'Cliente Editado'
    assert r.get_json()['content']['dni'] == '45678912'  # lo que no llega se conserva

    # No puede tomar el documento de otro cliente
    assert admin.put(f'/cliente/{c["id"]}', {'dni': otro['dni']}).status_code == 409

    actividad = admin.get(f'/cliente/{c["id"]}/actividad').get_json()['content']
    acciones = [a['accion'] for a in actividad]
    assert 'cliente_editado' in acciones and 'cliente_creado' in acciones
    editado = next(a for a in actividad if a['accion'] == 'cliente_editado')
    assert 'nombre' in editado['detalle'] and 'Cliente Editado' not in editado['detalle']


def test_listado_paginado_con_resumen_y_filtros(admin):
    _crear(admin, nombre='Ana', dni='45678912')
    _crear(admin, nombre='Empresa SAC', dni=RUC_EMPRESA, telefono='014445566')
    baja = _crear(admin, nombre='Baja', telefono='955000222').get_json()['content']
    admin.post(f'/cliente/{baja["id"]}/desactivar', {'motivo': 'Duplicado'})

    r = admin.get('/clientes?pagina=1&por_pagina=10').get_json()
    assert r['paginacion']['totalRegistros'] == 2
    assert r['resumen'] == {'total': 3, 'activos': 2, 'inactivos': 1, 'empresas': 1,
                            'sinDocumento': 0, 'sinAvisos': 0}
    assert {'totalEnvios', 'ultimaActividad', 'enviosEnCurso'} <= set(r['content'][0])

    assert admin.get('/clientes?pagina=1&tipo=empresa').get_json()['paginacion']['totalRegistros'] == 1
    assert admin.get('/clientes?pagina=1&estado=inactivos').get_json()['content'][0]['nombre'] == 'Baja'
    assert admin.get('/clientes?pagina=1&q=0144455').get_json()['paginacion']['totalRegistros'] == 1
    assert admin.get('/clientes?pagina=1&orden=actividad').status_code == 200

    # La lista simple (selectores) sigue igual
    simple = admin.get('/clientes').get_json()
    assert 'paginacion' not in simple and len(simple['content']) == 2


def test_ficha_y_historial_en_ambos_roles(admin, escenario):
    destinatario = escenario['cliente']
    remitente = _crear(admin, nombre='Tienda Sol', dni='20123456', telefono='955555555').get_json()['content']
    r = admin.post('/pedido', {
        'clienteId': destinatario['id'], 'remitenteId': remitente['id'],
        'direccionEntregaId': escenario['direccion']['id'], 'almacenId': escenario['almacen']['id'],
        'descripcionProducto': 'Libros', **BULTO_2KG, **INSPECCION_OK,
    })
    assert r.status_code == 201, r.get_json()

    fichaRem = admin.get(f'/cliente/{remitente["id"]}').get_json()['content']
    assert fichaRem['estadisticas']['enviados'] == 1
    assert fichaRem['estadisticas']['enCurso'] == 1
    fichaDest = admin.get(f'/cliente/{destinatario["id"]}').get_json()['content']
    assert fichaDest['estadisticas']['recibidos'] == 1
    assert len(fichaDest['direcciones']) == 1 and fichaDest['direcciones'][0]['esPrincipal'] is True

    hist = admin.get(f'/cliente/{remitente["id"]}/pedidos?rol=todos').get_json()
    assert hist['content'][0]['rolCliente'] == 'remitente'
    assert hist['content'][0]['contraparte'] == destinatario['nombre']
    assert admin.get(f'/cliente/{remitente["id"]}/pedidos?rol=destinatario').get_json()['content'] == []

    # Con un envio en curso no se puede desactivar
    assert admin.post(f'/cliente/{destinatario["id"]}/desactivar').status_code == 409
    # Ni cambiar la calle de la direccion que usa ese envio
    assert admin.put(f'/direccion-cliente/{escenario["direccion"]["id"]}',
                     {'calle': 'Otra calle 123'}).status_code == 409
    assert admin.post(f'/direccion-cliente/{escenario["direccion"]["id"]}/desactivar').status_code == 409

    lista = admin.get('/clientes?pagina=1&orden=actividad').get_json()['content']
    porId = {c['id']: c for c in lista}
    assert porId[remitente['id']]['totalEnvios'] == 1 and porId[destinatario['id']]['enviosEnCurso'] == 1


def test_direcciones_principal_y_baja(admin, escenario):
    c = _crear(admin, dni='45678912').get_json()['content']
    zona = escenario['zona']['id']
    d1 = admin.post('/direccion-cliente', {'clienteId': c['id'], 'calle': 'Av. Uno 100', 'zonaId': zona}).get_json()['content']
    assert d1['esPrincipal'] is True  # la primera siempre es principal
    d2 = admin.post('/direccion-cliente', {'clienteId': c['id'], 'calle': 'Av. Dos 200'}).get_json()['content']
    assert d2['esPrincipal'] is False

    assert admin.post(f'/direccion-cliente/{d2["id"]}/principal').status_code == 200
    lista = admin.get(f'/cliente/{c["id"]}/direcciones').get_json()['content']
    assert [d['id'] for d in lista] == [d2['id'], d1['id']]
    assert [d['esPrincipal'] for d in lista] == [True, False]

    r = admin.put(f'/direccion-cliente/{d1["id"]}', {'referencia': 'Frente al parque'})
    assert r.status_code == 200 and r.get_json()['content']['referencia'] == 'Frente al parque'

    # Al eliminar la principal, la siguiente pasa a serlo
    assert admin.post(f'/direccion-cliente/{d2["id"]}/desactivar').status_code == 200
    lista = admin.get(f'/cliente/{c["id"]}/direcciones').get_json()['content']
    assert len(lista) == 1 and lista[0]['id'] == d1['id'] and lista[0]['esPrincipal'] is True


def test_exportar_solo_admin_y_seguro(client, admin):
    _crear(admin, nombre='=HYPERLINK("x")', dni='45678912')
    r = admin.get('/clientes/exportar')
    assert r.status_code == 200
    contenido = r.data.decode('utf-8-sig')
    assert "'=HYPERLINK" in contenido  # no se interpreta como formula en Excel
    assert 'Documento' in contenido.splitlines()[0]

    admin.post('/usuario', {'nombre': 'Op', 'usuario': 'opera', 'email': 'op@test.pe', 'dni': '40000002',
                            'celular': '987654321', 'password': 'ClaveSegura123', 'rol': 'operador'})
    op = iniciarSesion(client, 'opera')
    assert op.get('/clientes/exportar').status_code == 403
