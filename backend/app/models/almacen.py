from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class AlmacenModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(100), nullable=False)  # ej. "Tienda Centro"
    calle = Column(type_=types.Text, nullable=False)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=True)
    telefono = Column(type_=types.String(20))
    latitud = Column(type_=types.Float, nullable=True)
    longitud = Column(type_=types.Float, nullable=True)
    activo = Column(type_=types.Boolean, server_default='1')
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'almacenes'