from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class CargoAdicionalModel(conexion.Model):
    """Cobro que no es el flete original: devolucion al remitente o
    redireccion a otra zona. El flete sigue en pagos (uno por envio)."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    # devolucion | redireccion
    concepto = Column(type_=types.String(20), nullable=False)
    monto = Column(type_=types.Numeric(10, 2), nullable=False)
    descripcion = Column(type_=types.String(200), nullable=True)
    # pendiente | pagado | anulado
    estado = Column(type_=types.String(20), nullable=False, server_default='pendiente', default='pendiente')
    metodo = Column(type_=types.String(20), nullable=True)
    referencia = Column(type_=types.String(60), nullable=True)
    fechaPago = Column(name='fecha_pago', type_=types.DateTime, nullable=True)
    registradoPorId = Column(ForeignKey(column='usuarios.id'), name='registrado_por_id', type_=types.Integer, nullable=True)
    cobradoPorId = Column(ForeignKey(column='usuarios.id'), name='cobrado_por_id', type_=types.Integer, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'cargos_adicionales'


class ReembolsoModel(conexion.Model):
    """Dinero que sale hacia el cliente: devolucion del flete de un envio que
    no se presto (cancelado/extraviado) o indemnizacion por perdida o dano."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    # devolucion_flete | indemnizacion
    tipo = Column(type_=types.String(20), nullable=False)
    monto = Column(type_=types.Numeric(10, 2), nullable=False)
    metodo = Column(type_=types.String(20), nullable=False)
    referencia = Column(type_=types.String(60), nullable=True)
    motivo = Column(type_=types.String(500), nullable=False)
    beneficiarioId = Column(ForeignKey(column='clientes.id'), name='beneficiario_id', type_=types.Integer, nullable=True)
    incidenciaId = Column(ForeignKey(column='incidencias.id'), name='incidencia_id', type_=types.Integer, nullable=True)
    # Nota de credito emitida por la devolucion del flete (si habia comprobante)
    comprobanteId = Column(ForeignKey(column='comprobantes.id'), name='comprobante_id', type_=types.Integer, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'reembolsos'


class CierreCajaModel(conexion.Model):
    """Arqueo del cajero al terminar su turno: lo que el sistema dice que
    debe tener (cobros de mostrador + efectivo rendido por repartidores -
    pagos que salieron) contra lo que cuenta en la gaveta."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigo = Column(type_=types.String(20), unique=True, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=False, index=True)
    agenciaId = Column(ForeignKey(column='almacenes.id'), name='agencia_id', type_=types.Integer, nullable=True)
    desde = Column(type_=types.DateTime, nullable=True)
    hasta = Column(type_=types.DateTime, nullable=False)
    efectivoEsperado = Column(name='efectivo_esperado', type_=types.Numeric(10, 2), nullable=False)
    efectivoContado = Column(name='efectivo_contado', type_=types.Numeric(10, 2), nullable=False)
    diferencia = Column(type_=types.Numeric(10, 2), nullable=False)
    # JSON: totales por metodo (yape, plin, tarjeta...) para conciliar con el banco
    detalle = Column(type_=types.Text, nullable=True)
    observacion = Column(type_=types.Text, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'cierres_caja'
