from app.extensions import conexion
from sqlalchemy import Column, ForeignKey, types


class UsuarioModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(100), nullable=False)
    # Nombre de usuario con el que se inicia sesion (minusculas, unico).
    nombreUsuario = Column(name='nombre_usuario', type_=types.String(30), nullable=False, unique=True)
    email = Column(type_=types.String(120), nullable=False, unique=True)
    # Datos personales (opcionales en la base: los usuarios creados antes no los tienen)
    dni = Column(type_=types.String(15), nullable=True, unique=True)
    celular = Column(type_=types.String(20), nullable=True)
    direccion = Column(type_=types.String(200), nullable=True)
    passwordHash = Column(name='password_hash', type_=types.String(255), nullable=False)
    # rol: admin | operador | repartidor
    rol = Column(type_=types.String(20), nullable=False)
    # Agencia donde trabaja un operador: solo ve y opera los envios que salen
    # o llegan ahi. NULL = sin restriccion (administradores).
    agenciaId = Column(ForeignKey(column='almacenes.id'), name='agencia_id', type_=types.Integer, nullable=True)
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
