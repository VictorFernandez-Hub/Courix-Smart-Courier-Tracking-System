from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import deferred

TextoLargo = types.Text().with_variant(mysql.LONGTEXT(), 'mysql')


class EntregaModel(conexion.Model):
    """Constancia de entrega: quien recibio, con que documento, su firma y si
    se verifico el PIN. Es el respaldo ante un "nunca me llego"."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, unique=True)
    nombreReceptor = Column(name='nombre_receptor', type_=types.String(100), nullable=False)
    dniReceptor = Column(name='dni_receptor', type_=types.String(15), nullable=False)
    # titular | familiar | trabajador | porteria | otro
    relacion = Column(type_=types.String(20), nullable=False)
    firma = deferred(Column(type_=TextoLargo, nullable=True))
    pinVerificado = Column(name='pin_verificado', type_=types.Boolean, nullable=False, server_default='0', default=False)
    latitud = Column(type_=types.Float, nullable=True)
    longitud = Column(type_=types.Float, nullable=True)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=True)
    fecha = Column(type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'entregas'


class SolicitudRecojoModel(conexion.Model):
    """Recojo a domicilio (paso 1 del proceso): el cliente pide que pasen a
    buscar sus paquetes. Un recojo puede originar varios envios."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigo = Column(type_=types.String(20), unique=True, nullable=True)
    remitenteId = Column(ForeignKey(column='clientes.id'), name='remitente_id', type_=types.Integer, nullable=False)
    direccionId = Column(ForeignKey(column='direcciones.id'), name='direccion_id', type_=types.Integer, nullable=False)
    zonaId = Column(ForeignKey(column='zonas.id'), name='zona_id', type_=types.Integer, nullable=False)
    # Agencia que recibe lo recogido (la de la zona de recojo)
    agenciaId = Column(ForeignKey(column='almacenes.id'), name='agencia_id', type_=types.Integer, nullable=False)
    fechaProgramada = Column(name='fecha_programada', type_=types.Date, nullable=False, index=True)
    franja = Column(type_=types.String(10), nullable=False)
    bultosEstimados = Column(name='bultos_estimados', type_=types.Integer, nullable=False, default=1)
    pesoEstimadoKg = Column(name='peso_estimado_kg', type_=types.Numeric(10, 2), nullable=True)
    notas = Column(type_=types.Text, nullable=True)
    estado = Column(type_=types.String(20), nullable=False, server_default='pendiente', default='pendiente', index=True)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    bultosRecogidos = Column(name='bultos_recogidos', type_=types.Integer, nullable=True)
    fechaRecojo = Column(name='fecha_recojo', type_=types.DateTime, nullable=True)
    motivoFallo = Column(name='motivo_fallo', type_=types.String(30), nullable=True)
    comentario = Column(type_=types.Text, nullable=True)
    creadoPorId = Column(ForeignKey(column='usuarios.id'), name='creado_por_id', type_=types.Integer, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'solicitudes_recojo'
