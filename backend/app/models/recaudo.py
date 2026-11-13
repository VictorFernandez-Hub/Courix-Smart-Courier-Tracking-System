from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class RecaudoModel(conexion.Model):
    """Dinero del producto cobrado al destinatario por cuenta del remitente
    (contra entrega de mercaderia). No es ingreso del courier: es una deuda
    con el remitente hasta que se le liquida."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, unique=True)
    remitenteId = Column(ForeignKey(column='clientes.id'), name='remitente_id', type_=types.Integer, nullable=False)
    monto = Column(type_=types.Numeric(10, 2), nullable=False)
    metodo = Column(type_=types.String(20), nullable=False)
    referencia = Column(type_=types.String(60), nullable=True)
    # Quien lo cobro en la calle (el efectivo se rinde en la liquidacion de la ruta)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    rutaId = Column(ForeignKey(column='rutas.id'), name='ruta_id', type_=types.Integer, nullable=True)
    registradoPorId = Column(ForeignKey(column='usuarios.id'), name='registrado_por_id', type_=types.Integer, nullable=True)
    fechaCobro = Column(name='fecha_cobro', type_=types.DateTime, server_default=conexion.func.now())
    # NULL = todavia se le debe al remitente
    liquidacionId = Column(ForeignKey(column='liquidaciones_recaudo.id'), name='liquidacion_id',
                           type_=types.Integer, nullable=True)

    __tablename__ = 'recaudos'


class LiquidacionRecaudoModel(conexion.Model):
    """Pago al remitente de lo recaudado a su nombre, menos la comision."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigo = Column(type_=types.String(20), unique=True, nullable=True)
    remitenteId = Column(ForeignKey(column='clientes.id'), name='remitente_id', type_=types.Integer, nullable=False)
    envios = Column(type_=types.Integer, nullable=False)
    montoRecaudado = Column(name='monto_recaudado', type_=types.Numeric(10, 2), nullable=False)
    porcentajeComision = Column(name='porcentaje_comision', type_=types.Numeric(5, 2), nullable=False)
    comision = Column(type_=types.Numeric(10, 2), nullable=False)
    montoPagado = Column(name='monto_pagado', type_=types.Numeric(10, 2), nullable=False)
    metodo = Column(type_=types.String(20), nullable=False)
    referencia = Column(type_=types.String(60), nullable=True)
    observacion = Column(type_=types.Text, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'liquidaciones_recaudo'
