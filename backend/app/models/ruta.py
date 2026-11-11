from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class RutaModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigo = Column(type_=types.String(20), unique=True, nullable=True)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=False)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=False)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())
    # estado: planificada | en_curso | completada | cancelada
    estado = Column(type_=types.String(20), server_default='planificada')
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'rutas'