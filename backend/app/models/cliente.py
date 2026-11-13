from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class ClienteModel(conexion.Model):
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    # persona | empresa. Una empresa factura con RUC y se muestra por razon social.
    tipoCliente = Column(name='tipo_cliente', type_=types.String(10), nullable=False,
                         server_default='persona', default='persona')
    nombre = Column(type_=types.String(100), nullable=False)  # nombre completo o razon social
    # Catalogo SUNAT 06 simplificado: DNI | RUC | CE | PASAPORTE. NULL = sin documento
    # o registrado antes de que existiera el campo.
    tipoDocumento = Column(name='tipo_documento', type_=types.String(10), nullable=True)
    dni = Column(type_=types.String(15), index=True)  # numero de documento (cualquier tipo)
    telefono = Column(type_=types.String(20), nullable=False, index=True)
    telefonoAlternativo = Column(name='telefono_alternativo', type_=types.String(20), nullable=True)
    email = Column(type_=types.String(120))
    # Notas internas del personal (horarios, trato preferente...). Nunca se
    # muestran al repartidor ni en el rastreo publico.
    notas = Column(type_=types.Text, nullable=True)
    # Consentimiento para avisos de su envio (Ley 29733 de datos personales)
    recibeAvisos = Column(name='recibe_avisos', type_=types.Boolean, nullable=False, server_default='1', default=True)
    # Cuando se dio (o retiro) el consentimiento: evidencia ante un reclamo.
    fechaConsentimiento = Column(name='fecha_consentimiento', type_=types.DateTime, nullable=True)
    # ---- Credito (cuenta corriente) ----
    # Solo clientes aprobados envian "a credito": se les factura despues,
    # hasta un limite y con un plazo de pago.
    creditoHabilitado = Column(name='credito_habilitado', type_=types.Boolean, nullable=False,
                               server_default='0', default=False)
    limiteCredito = Column(name='limite_credito', type_=types.Numeric(10, 2), nullable=False,
                           server_default='0.00', default=0)
    diasCredito = Column(name='dias_credito', type_=types.Integer, nullable=False, server_default='30', default=30)
    activo = Column(type_=types.Boolean, server_default='1')
    motivoDesactivacion = Column(name='motivo_desactivacion', type_=types.String(200), nullable=True)
    creadoPorId = Column(ForeignKey(column='usuarios.id'), name='creado_por_id', type_=types.Integer, nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaActualizacion = Column(name='fecha_actualizacion', type_=types.DateTime,
                                 server_default=conexion.func.now(), onupdate=conexion.func.now())

    __tablename__ = 'clientes'
