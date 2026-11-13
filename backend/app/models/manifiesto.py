from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey, UniqueConstraint


class ManifiestoModel(conexion.Model):
    """Lote de bultos que viaja de una agencia a otra con un transportista.
    abierto -> en_transito -> recibido | recibido_con_diferencias"""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigo = Column(type_=types.String(20), unique=True, nullable=True)
    agenciaOrigenId = Column(ForeignKey(column='almacenes.id'), name='agencia_origen_id', type_=types.Integer, nullable=False)
    agenciaDestinoId = Column(ForeignKey(column='almacenes.id'), name='agencia_destino_id', type_=types.Integer, nullable=False)
    estado = Column(type_=types.String(30), nullable=False, server_default='abierto', default='abierto', index=True)
    transportista = Column(type_=types.String(100), nullable=True)
    placa = Column(type_=types.String(15), nullable=True)
    # Numero del precinto de seguridad del vehiculo/saco: si llega roto, se nota
    precinto = Column(type_=types.String(40), nullable=True)
    observaciones = Column(type_=types.Text, nullable=True)
    creadoPorId = Column(ForeignKey(column='usuarios.id'), name='creado_por_id', type_=types.Integer, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    despachadoPorId = Column(ForeignKey(column='usuarios.id'), name='despachado_por_id', type_=types.Integer, nullable=True)
    fechaDespacho = Column(name='fecha_despacho', type_=types.DateTime, nullable=True)
    recibidoPorId = Column(ForeignKey(column='usuarios.id'), name='recibido_por_id', type_=types.Integer, nullable=True)
    fechaRecepcion = Column(name='fecha_recepcion', type_=types.DateTime, nullable=True)

    __tablename__ = 'manifiestos'


class ManifiestoBultoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    manifiestoId = Column(ForeignKey(column='manifiestos.id'), name='manifiesto_id', type_=types.Integer, nullable=False, index=True)
    bultoId = Column(ForeignKey(column='bultos.id'), name='bulto_id', type_=types.Integer, nullable=False, index=True)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    recibido = Column(type_=types.Boolean, nullable=False, server_default='0', default=False)
    fechaRecepcion = Column(name='fecha_recepcion', type_=types.DateTime, nullable=True)
    recibidoPorId = Column(ForeignKey(column='usuarios.id'), name='recibido_por_id', type_=types.Integer, nullable=True)
    fechaAgregado = Column(name='fecha_agregado', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'manifiesto_bultos'
    __table_args__ = (UniqueConstraint('manifiesto_id', 'bulto_id', name='uq_manifiesto_bulto'),)


class EventoBultoModel(conexion.Model):
    """Trazabilidad fisica: cada vez que alguien toca un bulto (quien, donde,
    cuando). El historial de estados es por envio; esto es por caja."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    bultoId = Column(ForeignKey(column='bultos.id'), name='bulto_id', type_=types.Integer, nullable=False, index=True)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    tipo = Column(type_=types.String(30), nullable=False)
    agenciaId = Column(ForeignKey(column='almacenes.id'), name='agencia_id', type_=types.Integer, nullable=True)
    manifiestoId = Column(ForeignKey(column='manifiestos.id'), name='manifiesto_id', type_=types.Integer, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'eventos_bulto'
