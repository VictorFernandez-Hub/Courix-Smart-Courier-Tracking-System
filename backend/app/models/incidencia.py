from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class IncidenciaModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    # tipo: reclamo | producto_danado | direccion_incorrecta | retraso | otro
    tipo = Column(type_=types.String(30), nullable=False)
    descripcion = Column(type_=types.Text, nullable=False)
    # estado: abierta | en_proceso | resuelta
    estado = Column(type_=types.String(20), server_default='abierta')
    resolucion = Column(type_=types.Text, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaResolucion = Column(name='fecha_resolucion', type_=types.DateTime, nullable=True)

    __tablename__ = 'incidencias'
