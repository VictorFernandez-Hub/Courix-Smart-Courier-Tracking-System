from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class BultoModel(conexion.Model):
    """Cada caja/paquete fisico de un envio. Un envio (una guia) puede tener
    varios bultos; cada uno lleva su propia etiqueta: CE-7K3M-9QX2-1, -2..."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    numero = Column(type_=types.Integer, nullable=False)
    codigo = Column(type_=types.String(40), nullable=True, unique=True)
    pesoKg = Column(name='peso_kg', type_=types.Numeric(10, 2), nullable=False)
    # NULL solo en los bultos migrados de pedidos anteriores a la admision
    largoCm = Column(name='largo_cm', type_=types.Numeric(10, 2), nullable=True)
    anchoCm = Column(name='ancho_cm', type_=types.Numeric(10, 2), nullable=True)
    altoCm = Column(name='alto_cm', type_=types.Numeric(10, 2), nullable=True)
    pesoVolumetricoKg = Column(name='peso_volumetrico_kg', type_=types.Numeric(10, 2), nullable=True)
    pesoFacturableKg = Column(name='peso_facturable_kg', type_=types.Numeric(10, 2), nullable=False)
    descripcion = Column(type_=types.String(120), nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'bultos'
