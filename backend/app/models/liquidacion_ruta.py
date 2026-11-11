from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class LiquidacionRutaModel(conexion.Model):
    """Cierre de caja de una ruta: el efectivo que el repartidor cobro en la
    calle (esperado) contra el que realmente entrego en caja."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    rutaId = Column(ForeignKey(column='rutas.id'), name='ruta_id', type_=types.Integer, nullable=False, unique=True)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=False)
    montoEsperado = Column(name='monto_esperado', type_=types.Numeric(10, 2), nullable=False)
    montoEntregado = Column(name='monto_entregado', type_=types.Numeric(10, 2), nullable=False)
    diferencia = Column(type_=types.Numeric(10, 2), nullable=False)
    observacion = Column(type_=types.Text, nullable=True)
    recibidoPorId = Column(ForeignKey(column='usuarios.id'), name='recibido_por_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'liquidaciones_ruta'
