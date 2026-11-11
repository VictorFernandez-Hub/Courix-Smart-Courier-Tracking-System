from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class AuditoriaModel(conexion.Model):
    """Registro inmutable de acciones sensibles: quien hizo que, sobre que
    entidad y desde que IP (cambios de rol, cancelaciones, montos manuales,
    pagos, liquidaciones, restablecimiento de contrasenas...)."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    accion = Column(type_=types.String(60), nullable=False)
    entidad = Column(type_=types.String(40), nullable=False)
    entidadId = Column(name='entidad_id', type_=types.Integer, nullable=True)
    detalle = Column(type_=types.Text, nullable=True)
    ip = Column(type_=types.String(45), nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'auditoria'
