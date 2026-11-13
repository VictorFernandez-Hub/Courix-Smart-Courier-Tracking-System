from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import deferred

# LONGTEXT solo existe en MySQL; en otros motores (SQLite de los tests) cae a Text.
TextoLargo = types.Text().with_variant(mysql.LONGTEXT(), 'mysql')


class PedidoModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    codigoGuia = Column(name='codigo_guia', type_=types.String(30), unique=True, nullable=True)
    # clienteId = DESTINATARIO (quien recibe; la direccion de entrega es suya)
    clienteId = Column(ForeignKey(column='clientes.id'), name='cliente_id', type_=types.Integer, nullable=False)
    # REMITENTE: quien envia (y normalmente paga). NULL en pedidos antiguos.
    remitenteId = Column(ForeignKey(column='clientes.id'), name='remitente_id', type_=types.Integer, nullable=True)
    usuarioId = Column(ForeignKey(column='usuarios.id'), name='usuario_id', type_=types.Integer, nullable=False)
    repartidorId = Column(ForeignKey(column='repartidores.id'), name='repartidor_id', type_=types.Integer, nullable=True)
    # almacenId = agencia de ORIGEN (donde se admitio el envio)
    almacenId = Column(ForeignKey(column='almacenes.id'), name='almacen_id', type_=types.Integer, nullable=False)
    # Agencia que hace el reparto final. Igual a la de origen = envio local
    # (no viaja). NULL en pedidos antiguos = se reparte desde el origen.
    agenciaDestinoId = Column(ForeignKey(column='almacenes.id'), name='agencia_destino_id', type_=types.Integer,
                              nullable=True)
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
    pesoKg = Column(name='peso_kg', type_=types.Float)  # peso real (suma de los bultos)
    # ---- Admision: servicio, cotizacion e inspeccion ----
    tipoServicio = Column(name='tipo_servicio', type_=types.String(20), nullable=False,
                          server_default='estandar', default='estandar')
    pesoFacturableKg = Column(name='peso_facturable_kg', type_=types.Numeric(10, 2), nullable=True)
    valorDeclarado = Column(name='valor_declarado', type_=types.Numeric(10, 2), nullable=False,
                            server_default='0.00', default=0)
    costoSeguro = Column(name='costo_seguro', type_=types.Numeric(10, 2), nullable=False,
                         server_default='0.00', default=0)
    # JSON con el desglose del calculo (base, kg, minimo, seguro): auditable
    detalleCotizacion = Column(name='detalle_cotizacion', type_=types.Text, nullable=True)
    estadoProducto = Column(name='estado_producto', type_=types.String(20), nullable=True)
    embalaje = Column(type_=types.String(20), nullable=True)
    declaraSinProhibidos = Column(name='declara_sin_prohibidos', type_=types.Boolean, nullable=True)
    observacionesInspeccion = Column(name='observaciones_inspeccion', type_=types.Text, nullable=True)
    inspeccionadoPorId = Column(ForeignKey(column='usuarios.id'), name='inspeccionado_por_id',
                                type_=types.Integer, nullable=True)
    fechaInspeccion = Column(name='fecha_inspeccion', type_=types.DateTime, nullable=True)
    descripcionProducto = Column(name='descripcion_producto', type_=types.Text)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaEntregaEstimada = Column(name='fecha_entrega_estimada', type_=types.DateTime, nullable=True)
    fechaEntrega = Column(name='fecha_entrega', type_=types.DateTime, nullable=True)
    notas = Column(type_=types.Text)
    # deferred: la foto (cientos de KB) no se lee de la base en los listados,
    # solo cuando se accede explicitamente al atributo.
    evidenciaEntrega = deferred(Column(name='evidencia_entrega', type_=TextoLargo, nullable=True))
    # ---- Entrega con codigo (PIN) ----
    # El remitente recibe el PIN al admitir el envio y se lo pasa al
    # destinatario; sin el, el repartidor no puede cerrar la entrega.
    requierePin = Column(name='requiere_pin', type_=types.Boolean, nullable=False, server_default='0', default=False)
    pinHash = Column(name='pin_hash', type_=types.String(64), nullable=True)
    pinIntentos = Column(name='pin_intentos', type_=types.Integer, nullable=False, server_default='0', default=0)
    # Recojo a domicilio del que salio este envio (si aplica)
    solicitudRecojoId = Column(ForeignKey(column='solicitudes_recojo.id'), name='solicitud_recojo_id',
                               type_=types.Integer, nullable=True)
    # ---- Logistica inversa ----
    # True = el paquete esta (o viaja) del lado de la agencia de ORIGEN en una
    # devolucion: se usa para saber donde esta un "por_devolver" y a donde
    # llega un "en_transito" de regreso.
    retornoAlOrigen = Column(name='retorno_al_origen', type_=types.Boolean, nullable=False,
                             server_default='0', default=False)
    # ---- Contra entrega de mercaderia (recaudo) ----
    # Precio del producto que se cobra al destinatario POR CUENTA DEL REMITENTE
    # (aparte del flete). Se le paga al remitente en una liquidacion de recaudos.
    montoRecaudo = Column(name='monto_recaudo', type_=types.Numeric(10, 2), nullable=False,
                          server_default='0.00', default=0)
    # Foto del producto al recibirlo (obligatoria si llega danado)
    fotoInspeccion = deferred(Column(name='foto_inspeccion', type_=TextoLargo, nullable=True))

    __tablename__ = 'pedidos'
