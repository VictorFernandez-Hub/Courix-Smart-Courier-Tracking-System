from app.extensions import conexion
from sqlalchemy import Column, ForeignKey, types


class CaptchaModel(conexion.Model):
    """Desafio de captcha de un solo uso. Se guarda en la base (no en memoria)
    para que funcione igual con varios workers de gunicorn/waitress."""
    # id aleatorio (no secuencial): es lo que el navegador devuelve junto a la respuesta
    id = Column(type_=types.String(43), primary_key=True)
    # HMAC de la respuesta: el texto del captcha nunca se guarda en claro
    respuestaHash = Column(name='respuesta_hash', type_=types.String(64), nullable=False)
    expira = Column(type_=types.DateTime, nullable=False, index=True)

    __tablename__ = 'captchas'


class RecuperacionPasswordModel(conexion.Model):
    """Enlace de recuperacion de contrasena enviado por correo."""
    id = Column(primary_key=True, autoincrement=True, type_=types.Integer)
    usuarioId = Column(ForeignKey('usuarios.id'), name='usuario_id', type_=types.Integer, nullable=False, index=True)
    # SHA-256 del token: quien lea la base no puede usar los enlaces pendientes
    tokenHash = Column(name='token_hash', type_=types.String(64), nullable=False, unique=True)
    expira = Column(type_=types.DateTime, nullable=False)
    usadoEn = Column(name='usado_en', type_=types.DateTime, nullable=True)
    ipSolicitud = Column(name='ip_solicitud', type_=types.String(45), nullable=True)
    fechaCreacion = Column(name='fecha_creacion', type_=types.DateTime, server_default=conexion.func.now())

    __tablename__ = 'recuperaciones_password'
