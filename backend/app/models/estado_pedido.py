from app.extensions import conexion
from sqlalchemy import Column, types


class EstadoPedidoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(30), nullable=False, unique=True)
    orden = Column(type_=types.Integer, nullable=False)

    __tablename__ = 'estados_pedido'
