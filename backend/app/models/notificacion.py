from app.extensions import conexion
from sqlalchemy import Column, types, ForeignKey


class NotificacionModel(conexion.Model):
    """Bandeja de salida (outbox) de avisos al cliente. Se guarda en la MISMA
    transaccion que el cambio de estado y se envia despues: si el proveedor
    falla, el aviso queda registrado y se puede reintentar."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    pedidoId = Column(ForeignKey(column='pedidos.id'), name='pedido_id', type_=types.Integer, nullable=False, index=True)
    # registrado | en_camino | entregado | no_entregado
    evento = Column(type_=types.String(30), nullable=False)
    # email | whatsapp
    canal = Column(type_=types.String(20), nullable=False)
    destino = Column(type_=types.String(120), nullable=False)
    # pendiente | enviado | fallido
    estado = Column(type_=types.String(20), nullable=False, server_default='pendiente', default='pendiente', index=True)
    intentos = Column(type_=types.Integer, nullable=False, server_default='0', default=0)
    error = Column(type_=types.String(500), nullable=True)
    idProveedor = Column(name='id_proveedor', type_=types.String(120), nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())
    fechaEnvio = Column(name='fecha_envio', type_=types.DateTime, nullable=True)

    __tablename__ = 'notificaciones'
