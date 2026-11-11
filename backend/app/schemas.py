"""Serializacion (modelo -> JSON) con marshmallow."""


from app.models import (
    UsuarioModel, ZonaModel, ClienteModel, DireccionModel, AlmacenModel, RepartidorModel,
    EstadoPedidoModel, TarifaZonaModel, RutaModel, PedidoModel, HistorialEstadoModel,
    PagoModel, IncidenciaModel, LiquidacionRutaModel,
)
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema


class UsuarioDto(SQLAlchemyAutoSchema):
    class Meta:
        model = UsuarioModel
        include_fk = True
        exclude = ('passwordHash', 'tokenVersion', 'intentosFallidos')


class ZonaDto(SQLAlchemyAutoSchema):
    class Meta:
        model = ZonaModel
        include_fk = True


class ClienteDto(SQLAlchemyAutoSchema):
    class Meta:
        model = ClienteModel
        include_fk = True


class DireccionDto(SQLAlchemyAutoSchema):
    class Meta:
        model = DireccionModel
        include_fk = True


class AlmacenDto(SQLAlchemyAutoSchema):
    class Meta:
        model = AlmacenModel
        include_fk = True


class RepartidorDto(SQLAlchemyAutoSchema):
    class Meta:
        model = RepartidorModel
        include_fk = True


class EstadoPedidoDto(SQLAlchemyAutoSchema):
    class Meta:
        model = EstadoPedidoModel
        include_fk = True


class PedidoDto(SQLAlchemyAutoSchema):
    class Meta:
        model = PedidoModel
        include_fk = True
        # La foto en base64 puede pesar cientos de KB: nunca va en listados.
        # Se pide aparte con GET /pedido/<id>/evidencia.
        exclude = ('evidenciaEntrega',)


class RutaDto(SQLAlchemyAutoSchema):
    class Meta:
        model = RutaModel
        include_fk = True


class HistorialEstadoDto(SQLAlchemyAutoSchema):
    class Meta:
        model = HistorialEstadoModel
        include_fk = True


class PagoDto(SQLAlchemyAutoSchema):
    class Meta:
        model = PagoModel
        include_fk = True


class IncidenciaDto(SQLAlchemyAutoSchema):
    class Meta:
        model = IncidenciaModel
        include_fk = True


class TarifaZonaDto(SQLAlchemyAutoSchema):
    class Meta:
        model = TarifaZonaModel
        include_fk = True


class LiquidacionRutaDto(SQLAlchemyAutoSchema):
    class Meta:
        model = LiquidacionRutaModel
        include_fk = True
