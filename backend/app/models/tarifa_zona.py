from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class TarifaZonaModel(conexion.Model):
    """Precio de referencia para un envio entre dos zonas (puede ser la misma
    zona en origen y destino, para reparto local). Se usa para sugerir el
    monto de un pedido cuando no se especifica uno manualmente:
        monto = precioBase + pesoKg * precioPorKg
    No reemplaza la posibilidad de escribir un monto a mano (convenios
    especiales, descuentos, etc.), solo evita que el operador tenga que
    inventarse un precio cada vez."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    zonaOrigenId = Column(ForeignKey(column='zonas.id'), name='zona_origen_id', type_=types.Integer, nullable=False)
    zonaDestinoId = Column(ForeignKey(column='zonas.id'), name='zona_destino_id', type_=types.Integer, nullable=False)
    precioBase = Column(name='precio_base', type_=types.Numeric(10, 2), nullable=False, server_default='0.00')
    precioPorKg = Column(name='precio_por_kg', type_=types.Numeric(10, 2), nullable=False, server_default='0.00')
    activo = Column(type_=types.Boolean, server_default='1')
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'tarifas_zona'
