from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class HistorialEstadoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False)
    estadoId = Column(ForeignKey(column='estados_pedido.id'), name='estado_id', type_=types.Integer, nullable=False)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())
    latitud = Column(type_=types.Float, nullable=True)
    longitud = Column(type_=types.Float, nullable=True)
    comentario = Column(type_=types.Text)

    __tablename__ = 'historial_estados'