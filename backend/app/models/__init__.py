"""Modelos (una clase por tabla). Importarlos aqui registra todas las tablas
en el metadata de SQLAlchemy (necesario para las migraciones)."""
from app.models.usuario import UsuarioModel
from app.models.zona import ZonaModel
from app.models.cliente import ClienteModel
from app.models.direccion import DireccionModel
from app.models.almacen import AlmacenModel
from app.models.repartidor import RepartidorModel
from app.models.estado_pedido import EstadoPedidoModel
from app.models.tarifa_zona import TarifaZonaModel
from app.models.ruta import RutaModel
from app.models.pedido import PedidoModel
from app.models.historial_estado import HistorialEstadoModel
from app.models.pago import PagoModel
from app.models.incidencia import IncidenciaModel
from app.models.liquidacion_ruta import LiquidacionRutaModel
from app.models.auditoria import AuditoriaModel
from app.models.seguridad_acceso import CaptchaModel, RecuperacionPasswordModel
from app.models.bulto import BultoModel
from app.models.manifiesto import ManifiestoModel, ManifiestoBultoModel, EventoBultoModel
from app.models.entrega import EntregaModel, SolicitudRecojoModel
from app.models.notificacion import NotificacionModel
from app.models.comprobante import SerieComprobanteModel, ComprobanteModel
from app.models.recaudo import RecaudoModel, LiquidacionRecaudoModel
from app.models.caja import CargoAdicionalModel, ReembolsoModel, CierreCajaModel

__all__ = [
    'UsuarioModel', 'ZonaModel', 'ClienteModel', 'DireccionModel', 'AlmacenModel',
    'RepartidorModel', 'EstadoPedidoModel', 'TarifaZonaModel', 'RutaModel', 'PedidoModel',
    'HistorialEstadoModel', 'PagoModel', 'IncidenciaModel', 'LiquidacionRutaModel', 'AuditoriaModel',
    'CaptchaModel', 'RecuperacionPasswordModel', 'BultoModel',
    'ManifiestoModel', 'ManifiestoBultoModel', 'EventoBultoModel', 'EntregaModel', 'SolicitudRecojoModel',
    'NotificacionModel', 'SerieComprobanteModel', 'ComprobanteModel', 'RecaudoModel', 'LiquidacionRecaudoModel',
    'CargoAdicionalModel', 'ReembolsoModel', 'CierreCajaModel',
]
