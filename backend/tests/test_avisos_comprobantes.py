"""Fase 4 - Avisos al cliente (WhatsApp/correo, outbox) y comprobantes
electronicos (Nubefact). Los proveedores se simulan: nunca sale nada a internet."""
import sys
from decimal import Decimal

import pytest

from conftest import ENTREGA_OK

import app.notificaciones as modAvisos
import app.routes.comprobantes  # noqa: F401
from app.notificaciones import telefonoInternacional
modComprobantes = sys.modules['app.routes.comprobantes']
from app.routes.comprobantes import desglosarIgv, rucValido  # noqa: E402

RUC_VALIDO = '20131312955'


# ------------------------------------------------------- reglas puras ----

def test_telefono_internacional():
    assert telefonoInternacional('987 654 321', '51') == '51987654321'
    assert telefonoInternacional('+51 987654321', '51') == '51987654321'
    assert telefonoInternacional('01-4567890', '51') is None  # fijo de Lima: no tiene WhatsApp


def test_ruc_y_desglose_de_igv():
    assert rucValido(RUC_VALIDO) and rucValido('20100047218')
    assert not rucValido('20131312956') and not rucValido('12345678901') and not rucValido('2013131295')
    assert desglosarIgv(Decimal('11.80'), '18') == (Decimal('10.00'), Decimal('1.80'), Decimal('11.80'))
    gravada, igv, total = desglosarIgv(Decimal('26.00'), '18')
    assert gravada + igv == total == Decimal('26.00')


# ------------------------------------------------------- avisos ----

@pytest.fixture
def whatsapp(app, monkeypatch):
    """WhatsApp 'configurado', envio sincrono y la API de Meta simulada."""
    monkeypatch.setitem(app.config, 'WHATSAPP_TOKEN', 'token-prueba')
    monkeypatch.setitem(app.config, 'WHATSAPP_PHONE_ID', '123456')
    monkeypatch.setitem(app.config, 'AVISOS_SINCRONOS', True)
    enviados = []

    def postFalso(url, cuerpo, cabeceras, timeout=10):
        enviados.append({'url': url, 'cuerpo': cuerpo, 'auth': cabeceras.get('Authorization')})
        return {'messages': [{'id': f'wamid.{len(enviados)}'}]}
    monkeypatch.setattr(modAvisos, '_postJson', postFalso)
    return enviados


def test_aviso_por_whatsapp_en_cada_etapa(escenario, admin, whatsapp):
    pedido = escenario['nuevoPedido']()
    assert len(whatsapp) == 1
    msg = whatsapp[0]
    assert msg['cuerpo']['to'] == '51987654321'  # telefono del cliente del escenario
    assert msg['cuerpo']['template']['name'] == 'envio_registrado'
    variables = [p['text'] for p in msg['cuerpo']['template']['components'][0]['parameters']]
    assert pedido['codigoGuia'] in variables and any('/rastreo?guia=' in v for v in variables)
    assert msg['auth'] == 'Bearer token-prueba' and '/123456/messages' in msg['url']

    repa = escenario['repa']
    repa.post(f"/pedido/{pedido['id']}/tomar", {'repartidorId': escenario['repartidor']['id']})
    assert len(whatsapp) == 1  # asignar no avisa
    repa.post(f"/pedido/{pedido['id']}/estado", {'estado': 'en_camino'})
    repa.post(f"/pedido/{pedido['id']}/entregar-y-cobrar", {'monto': pedido['monto'], **ENTREGA_OK})
    assert [m['cuerpo']['template']['name'] for m in whatsapp] == ['envio_registrado', 'envio_en_camino', 'envio_entregado']
    receptor = [p['text'] for p in whatsapp[2]['cuerpo']['template']['components'][0]['parameters']]
    assert 'Ana Torres' in receptor

    avisos = admin.get(f"/pedido/{pedido['id']}/avisos").get_json()['content']
    assert [(a['evento'], a['canal'], a['estado']) for a in avisos] == [
        ('registrado', 'whatsapp', 'enviado'), ('en_camino', 'whatsapp', 'enviado'), ('entregado', 'whatsapp', 'enviado')]


def test_cliente_que_no_quiere_avisos_no_los_recibe(escenario, admin, whatsapp):
    r = admin.post(f"/cliente/{escenario['cliente']['id']}/avisos", {'recibeAvisos': False})
    assert r.status_code == 200 and r.get_json()['content']['recibeAvisos'] is False
    escenario['nuevoPedido']()
    assert whatsapp == []


def test_aviso_fallido_se_reintenta(escenario, admin, app, monkeypatch, whatsapp):
    def caido(*args, **kwargs):
        raise RuntimeError('HTTP 503: servicio no disponible')
    monkeypatch.setattr(modAvisos, '_postJson', caido)
    pedido = escenario['nuevoPedido']()  # la admision NO falla aunque Meta este caido
    aviso = admin.get(f"/pedido/{pedido['id']}/avisos").get_json()['content'][0]
    assert aviso['estado'] == 'fallido' and '503' in aviso['error']

    monkeypatch.setattr(modAvisos, '_postJson', lambda *a, **k: {'messages': [{'id': 'wamid.ok'}]})
    resultado = app.test_cli_runner().invoke(args=['reenviar-avisos'])
    assert 'Avisos procesados: 1' in resultado.output
    aviso = admin.get(f"/pedido/{pedido['id']}/avisos").get_json()['content'][0]
    assert aviso['estado'] == 'enviado' and aviso['intentos'] == 2


def test_aviso_por_correo(escenario, admin, app, monkeypatch):
    monkeypatch.setitem(app.config, 'SMTP_HOST', 'smtp.prueba.pe')
    monkeypatch.setitem(app.config, 'AVISOS_SINCRONOS', True)
    correos = []
    monkeypatch.setattr(modAvisos, '_enviarCorreo', lambda config, destino, asunto, texto: correos.append((destino, asunto, texto)))
    cliente = admin.post('/cliente', {'nombre': 'Rosa Diaz', 'telefono': '988111222', 'email': 'rosa@correo.pe'}).get_json()['content']
    direccion = admin.post('/direccion-cliente', {'clienteId': cliente['id'], 'zonaId': escenario['zona']['id'],
                                                  'calle': 'Av. Sol 1'}).get_json()['content']
    pedido = escenario['nuevoPedido'](clienteId=cliente['id'], direccionEntregaId=direccion['id'])
    assert correos and correos[0][0] == 'rosa@correo.pe' and pedido['codigoGuia'] in correos[0][1]


def test_sin_canales_configurados_no_se_encola_nada(escenario, admin):
    pedido = escenario['nuevoPedido']()
    assert admin.get(f"/pedido/{pedido['id']}/avisos").get_json()['content'] == []


# ------------------------------------------------------- comprobantes ----

@pytest.fixture
def nubefact(app, monkeypatch):
    monkeypatch.setitem(app.config, 'NUBEFACT_URL', 'https://api.nubefact.test/ruta/123')
    monkeypatch.setitem(app.config, 'NUBEFACT_TOKEN', 'tok')
    enviados = []

    def postFalso(url, cuerpo, cabeceras, timeout=10):
        enviados.append(cuerpo)
        return {'aceptada_por_sunat': True, 'enlace_del_pdf': f"https://nubefact.test/{cuerpo['serie']}-{cuerpo['numero']}.pdf",
                'sunat_description': 'La Boleta ha sido aceptada', 'codigo_hash': 'abc='}
    monkeypatch.setattr(modComprobantes, '_postJson', postFalso)
    return enviados


def pedidoPagado(escenario, admin, **extra):
    pedido = escenario['nuevoPedido'](modalidadPago='prepagado', **extra)
    r = admin.post('/pago', {'pedidoId': pedido['id'], 'monto': pedido['monto'], 'metodo': 'efectivo', 'estadoPago': 'pagado'})
    assert r.status_code == 201, r.get_json()
    return pedido


def test_sin_configurar_no_se_emite_ni_se_consume_numero(escenario, admin, app, monkeypatch):
    pedido = pedidoPagado(escenario, admin)
    r = admin.post(f"/pedido/{pedido['id']}/comprobante", {'tipo': 'boleta', 'numDoc': '12345678', 'nombre': 'Ana Torres'})
    assert r.status_code == 409 and 'no esta configurada' in r.get_json()['message']
    info = admin.get(f"/pedido/{pedido['id']}/comprobantes").get_json()['content']
    assert info['comprobantes'] == [] and info['facturacionConfigurada'] is False


def test_boleta_con_correlativo_e_igv(escenario, admin, nubefact):
    sinPago = escenario['nuevoPedido'](modalidadPago='prepagado')
    r = admin.post(f"/pedido/{sinPago['id']}/comprobante", {'tipo': 'boleta', 'nombre': 'Ana Torres'})
    assert r.status_code == 409 and 'pago' in r.get_json()['message']

    p1 = pedidoPagado(escenario, admin)
    c1 = admin.post(f"/pedido/{p1['id']}/comprobante", {'tipo': 'boleta', 'numDoc': '12345678', 'nombre': 'Ana Torres'}).get_json()['content']
    assert c1['numeroCompleto'] == 'B001-00000001' and c1['estado'] == 'aceptado' and c1['enlacePdf'].endswith('.pdf')
    assert (c1['gravada'], c1['igv'], c1['total']) == ('9.32', '1.68', '11.00')
    enviado = nubefact[0]
    assert enviado['tipo_de_comprobante'] == 2 and enviado['cliente_tipo_de_documento'] == '1'
    assert enviado['items'][0]['unidad_de_medida'] == 'ZZ' and p1['codigoGuia'] in enviado['items'][0]['descripcion']

    assert admin.post(f"/pedido/{p1['id']}/comprobante", {'tipo': 'boleta', 'nombre': 'Ana Torres'}).status_code == 409
    p2 = pedidoPagado(escenario, admin)
    c2 = admin.post(f"/pedido/{p2['id']}/comprobante", {'tipo': 'boleta', 'nombre': 'Cliente varios'}).get_json()['content']
    assert c2['numeroCompleto'] == 'B001-00000002' and c2['clienteTipoDoc'] == '-'  # menos de S/ 700: sin documento


def test_reglas_sunat_de_factura_y_boleta(escenario, admin, nubefact):
    pedido = pedidoPagado(escenario, admin)
    url = f"/pedido/{pedido['id']}/comprobante"
    assert admin.post(url, {'tipo': 'factura', 'numDoc': '20131312956', 'nombre': 'Empresa SAC', 'direccion': 'Av. 1'}).status_code == 400
    assert admin.post(url, {'tipo': 'factura', 'numDoc': RUC_VALIDO, 'nombre': 'Empresa SAC'}).status_code == 400  # sin direccion
    assert admin.post(url, {'tipo': 'boleta', 'numDoc': '123', 'nombre': 'Ana'}).status_code == 400
    r = admin.post(url, {'tipo': 'factura', 'numDoc': RUC_VALIDO, 'nombre': 'Empresa SAC', 'direccion': 'Av. Garcilaso 315'})
    assert r.status_code == 201 and r.get_json()['content']['numeroCompleto'] == 'F001-00000001'
    assert nubefact[-1]['tipo_de_comprobante'] == 1 and nubefact[-1]['cliente_tipo_de_documento'] == '6'


def test_boleta_de_700_o_mas_exige_documento(escenario, admin, nubefact):
    pedido = pedidoPagado(escenario, admin, monto='750.00', motivoMonto='Envio corporativo')
    url = f"/pedido/{pedido['id']}/comprobante"
    r = admin.post(url, {'tipo': 'boleta', 'nombre': 'Cliente varios'})
    assert r.status_code == 400 and '700' in r.get_json()['message']
    assert admin.post(url, {'tipo': 'boleta', 'numDoc': '12345678', 'nombre': 'Ana Torres'}).status_code == 201


def test_error_del_proveedor_se_reintenta_con_el_mismo_numero(escenario, admin, nubefact, monkeypatch):
    monkeypatch.setattr(modComprobantes, '_postJson', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('timeout')))
    pedido = pedidoPagado(escenario, admin)
    c = admin.post(f"/pedido/{pedido['id']}/comprobante", {'tipo': 'boleta', 'numDoc': '12345678', 'nombre': 'Ana Torres'}).get_json()['content']
    assert c['estado'] == 'error' and c['numeroCompleto'] == 'B001-00000001'

    monkeypatch.setattr(modComprobantes, '_postJson', lambda *a, **k: {'aceptada_por_sunat': True, 'enlace_del_pdf': 'https://x/1.pdf'})
    r = admin.post(f"/comprobante/{c['id']}/reenviar").get_json()['content']
    assert r['estado'] == 'aceptado' and r['numeroCompleto'] == 'B001-00000001'
    assert admin.post(f"/comprobante/{c['id']}/reenviar").status_code == 409  # ya aceptado
