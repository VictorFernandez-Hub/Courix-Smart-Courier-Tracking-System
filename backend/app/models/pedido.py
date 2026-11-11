from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import deferred

# LONGTEXT solo existe en MySQL; en otros motores (SQLite de los tests) cae a Text.
TextoLargo = types.Text().with_variant(mysql.LONGTEXT(), 'mysql')


class PedidoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigoGuia = Column(name='codigo_guia', type_=types.String(30), unique=True, nullable=True)
    clienteId = Column(ForeignKey(column='clientes.id'), name='cliente_id', type_=types.Integer, nullable=False)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=False)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    almacenId = Column(ForeignKey(column='almacenes.id'), name='almacen_id', type_=types.Integer, nullable=False)
    direccionEntregaId = Column(ForeignKey(column='direcciones.id'), name='direccion_entrega_id', type_=types.Integer, nullable=False)
    rutaId = Column(ForeignKey(column='rutas.id'), name='ruta_id', type_=types.Integer, nullable=True)
    estadoId = Column(ForeignKey(column='estados_pedido.id'), name='estado_id', type_=types.Integer, nullable=False)
    prioridad = Column(type_=types.String(20), server_default='normal')
    monto = Column(type_=types.Numeric(10, 2), server_default='0.00')
    # modalidad_pago: contra_entrega | prepagado | credito
    modalidadPago = Column(name='modalidad_pago', type_=types.String(20), nullable=False,
                           server_default='contra_entrega', default='contra_entrega')
    # Tarifa con la que se calculo el monto (NULL = monto ingresado a mano).
    tarifaId = Column(ForeignKey(column='tarifas_zona.id'), name='tarifa_id', type_=types.Integer, nullable=True)
    intentosEntrega = Column(name='intentos_entrega', type_=types.Integer, nullable=False, server_default='0', default=0)
    motivoNoEntrega = Column(name='motivo_no_entrega', type_=types.String(40), nullable=True)
    pesoKg = Column(name='peso_kg', type_=types.Float)
    descripcionProducto = Column(name='descripcion_producto', type_=types.Text)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaEntregaEstimada = Column(name='fecha_entrega_estimada', type_=types.DateTime, nullable=True)
    fechaEntrega = Column(name='fecha_entrega', type_=types.DateTime, nullable=True)
    notas = Column(type_=types.Text)
    # deferred: la foto (cientos de KB) no se lee de la base en los listados,
    # solo cuando se accede explicitamente al atributo.
    evidenciaEntrega = deferred(Column(name='evidencia_entrega', type_=TextoLargo, nullable=True))

    __tablename__ = 'pedidos'
