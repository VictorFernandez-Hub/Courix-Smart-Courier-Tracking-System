from app.extensions import conexion
from sqlalchemy import Column, types


class UsuarioModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(100), nullable=False)
    email = Column(type_=types.String(120), nullable=False, unique=True)
    passwordHash = Column(name='password_hash', type_=types.String(255), nullable=False)
    # rol: admin | operador | repartidor
    rol = Column(type_=types.String(20), nullable=False)
    activo = Column(type_=types.Boolean, server_default='1')
    # Se incrementa al desactivar, cambiar rol o cambiar contrasena: todos los
    # tokens emitidos antes dejan de ser validos de inmediato.
    tokenVersion = Column(name='token_version', type_=types.Integer, nullable=False, server_default='0', default=0)
    intentosFallidos = Column(name='intentos_fallidos', type_=types.Integer, nullable=False, server_default='0', default=0)
    bloqueadoHasta = Column(name='bloqueado_hasta', type_=types.DateTime, nullable=True)
    ultimoLogin = Column(name='ultimo_login', type_=types.DateTime, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'usuarios'
