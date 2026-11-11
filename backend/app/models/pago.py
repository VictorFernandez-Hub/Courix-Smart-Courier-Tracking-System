from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class PagoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, unique=True)
    monto = Column(type_=types.Numeric(10, 2), nullable=False)
    # metodo: efectivo | yape | plin | tarjeta | transferencia
    metodo = Column(type_=types.String(20), nullable=False)
    # Numero de operacion (Yape/Plin/tarjeta/transferencia) para conciliar.
    referencia = Column(type_=types.String(60), nullable=True)
    # estado_pago: pendiente | pagado
    estadoPago = Column(name='estado_pago', type_=types.String(20), server_default='pendiente')
    fechaPago = Column(name='fecha_pago', type_=types.DateTime, nullable=True)
    # Si lo cobro un repartidor en la calle: quien y en que ruta (para la
    # liquidacion de caja al cerrar el dia).
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    rutaId = Column(ForeignKey(column='rutas.id'), name='ruta_id', type_=types.Integer, nullable=True)
    registradoPorId = Column(ForeignKey(column='usuarios.id'), name='registrado_por_id', type_=types.Integer, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'pagos'
