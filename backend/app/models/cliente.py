from app.extensions import conexion
from sqlalchemy import Column, types


class ClienteModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(100), nullable=False)
    dni = Column(type_=types.String(15))
    telefono = Column(type_=types.String(20), nullable=False)
    email = Column(type_=types.String(120))
    activo = Column(type_=types.Boolean, server_default='1')
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'clientes'