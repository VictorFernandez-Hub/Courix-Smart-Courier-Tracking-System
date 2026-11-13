from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class AlmacenModel(conexion.Model):
    """Agencia / almacen de la red: donde se admiten, guardan, despachan y
    reparten los envios. Un operador trabaja en una sola agencia."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    nombre = Column(type_=types.String(100), nullable=False)  # ej. "Tienda Centro"
    # Codigo corto que se imprime en etiquetas y manifiestos (ej. LIM01)
    codigo = Column(type_=types.String(10), nullable=True, unique=True)
    calle = Column(type_=types.Text, nullable=False)
    referencia = Column(type_=types.String(300), nullable=True)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=True)
    telefono = Column(type_=types.String(20))
    email = Column(type_=types.String(120), nullable=True)
    # Texto libre que se muestra al cliente: "Lun-Vie 8:00-19:00, Sab 9:00-13:00"
    horario = Column(type_=types.String(200), nullable=True)
    # Jefe de agencia: a quien se llama cuando hay un problema
    responsableId = Column(ForeignKey(column='usuarios.id', use_alter=True, name='fk_almacenes_responsable'),
                           name='responsable_id', type_=types.Integer, nullable=True)
    # Bultos que caben fisicamente; NULL = no se controla la ocupacion
    capacidadBultos = Column(name='capacidad_bultos', type_=types.Integer, nullable=True)
    latitud = Column(type_=types.Float, nullable=True)
    longitud = Column(type_=types.Float, nullable=True)
    activo = Column(type_=types.Boolean, server_default='1')
    motivoDesactivacion = Column(name='motivo_desactivacion', type_=types.String(200), nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'almacenes'
