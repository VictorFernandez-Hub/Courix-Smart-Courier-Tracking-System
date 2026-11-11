from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class DireccionModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    clienteId = Column(ForeignKey(column='clientes.id'), name='cliente_id', type_=types.Integer, nullable=False)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=True)
    etiqueta = Column(type_=types.String(50))  # ej. "Casa", "Tienda"
    calle = Column(type_=types.Text, nullable=False)
    referencia = Column(type_=types.Text)
    latitud = Column(type_=types.Float, nullable=True)
    longitud = Column(type_=types.Float, nullable=True)
    activo = Column(type_=types.Boolean, server_default='1')
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'direcciones'