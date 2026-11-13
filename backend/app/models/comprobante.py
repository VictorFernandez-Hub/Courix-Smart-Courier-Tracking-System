from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey, UniqueConstraint


class SerieComprobanteModel(conexion.Model):
    """Correlativo por serie (B001, F001...). SUNAT exige numeracion sin
    saltos: el numero se toma bloqueando esta fila."""
    serie = Column(type_=types.String(4), primary_key=True)
    tipo = Column(type_=types.String(10), nullable=False)  # boleta | factura | nota (de credito)
    # Nota de credito: comprobante que modifica y motivo (catalogo SUNAT 09)
    comprobanteRefId = Column(ForeignKey(column='comprobantes.id'), name='comprobante_ref_id', type_=types.Integer,
                              nullable=True)
    motivoNota = Column(name='motivo_nota', type_=types.String(200), nullable=True)
    ultimoNumero = Column(name='ultimo_numero', type_=types.Integer, nullable=False, server_default='0', default=0)

    __tablename__ = 'series_comprobante'


class ComprobanteModel(conexion.Model):
    """Boleta o factura electronica por el servicio de un envio. Solo es
    valida cuando el PSE/OSE (Nubefact) la acepta y SUNAT la recibe."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    tipo = Column(type_=types.String(10), nullable=False)  # boleta | factura | nota (de credito)
    # Nota de credito: comprobante que modifica y motivo (catalogo SUNAT 09)
    comprobanteRefId = Column(ForeignKey(column='comprobantes.id'), name='comprobante_ref_id', type_=types.Integer,
                              nullable=True)
    motivoNota = Column(name='motivo_nota', type_=types.String(200), nullable=True)
    serie = Column(type_=types.String(4), nullable=False)
    numero = Column(type_=types.Integer, nullable=False)
    # Catalogo SUNAT 06: 1 = DNI, 6 = RUC, - = sin documento
    clienteTipoDoc = Column(name='cliente_tipo_doc', type_=types.String(1), nullable=False)
    clienteNumDoc = Column(name='cliente_num_doc', type_=types.String(15), nullable=True)
    clienteNombre = Column(name='cliente_nombre', type_=types.String(150), nullable=False)
    clienteDireccion = Column(name='cliente_direccion', type_=types.String(200), nullable=True)
    clienteEmail = Column(name='cliente_email', type_=types.String(120), nullable=True)
    descripcion = Column(type_=types.String(250), nullable=False)
    gravada = Column(type_=types.Numeric(10, 2), nullable=False)
    igv = Column(type_=types.Numeric(10, 2), nullable=False)
    total = Column(type_=types.Numeric(10, 2), nullable=False)
    # pendiente | aceptado | rechazado | error | sin_configurar
    estado = Column(type_=types.String(20), nullable=False, server_default='pendiente', default='pendiente')
    mensajeSunat = Column(name='mensaje_sunat', type_=types.String(500), nullable=True)
    enlacePdf = Column(name='enlace_pdf', type_=types.String(300), nullable=True)
    codigoHash = Column(name='codigo_hash', type_=types.String(100), nullable=True)
    emitidoPorId = Column(ForeignKey(column='usuarios.id'), name='emitido_por_id', type_=types.Integer, nullable=True)
    fechaEmision = Column(name='fecha_emision', type_=types.Date, nullable=False)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'comprobantes'
    __table_args__ = (UniqueConstraint('serie', 'numero', name='uq_comprobante_serie_numero'),)
