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

__all__ = [
    'UsuarioModel', 'ZonaModel', 'ClienteModel', 'DireccionModel', 'AlmacenModel',
    'RepartidorModel', 'EstadoPedidoModel', 'TarifaZonaModel', 'RutaModel', 'PedidoModel',
    'HistorialEstadoModel', 'PagoModel', 'IncidenciaModel', 'LiquidacionRutaModel', 'AuditoriaModel',
]
