from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class RepartidorModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=False, unique=True)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=True)
    telefono = Column(type_=types.String(20))
    vehiculo = Column(type_=types.String(50))
    placa = Column(type_=types.String(20))
    disponible = Column(type_=types.Boolean, server_default='1')
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'repartidores'