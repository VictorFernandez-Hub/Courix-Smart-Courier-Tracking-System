"""Comandos de consola: flask sembrar, flask crear-admin."""

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from app.extensions import conexion
from app.models import (
    UsuarioModel, EstadoPedidoModel,
)
from app.core.validacion import (
    ErrorValidacion, validarPassword, nombreUsuario,
)
from app.reglas import (
    ESTADOS_CATALOGO,
)


def sembrarEstados():
    for nombre, orden in ESTADOS_CATALOGO:
        existe = conexion.session.query(EstadoPedidoModel).filter_by(nombre=nombre).first()
        if existe:
            existe.orden = orden
        else:
            conexion.session.add(EstadoPedidoModel(nombre=nombre, orden=orden))
    conexion.session.commit()


@click.command('sembrar')
@with_appcontext
def comandoSembrar():
    """Crea o actualiza el catalogo de estados de pedido."""
    sembrarEstados()
    click.echo('Catalogo de estados sembrado')


@click.command('crear-admin')
@with_appcontext
@click.option('--usuario', 'login', prompt='Usuario (para iniciar sesion)')
@click.option('--email', 'correo', prompt='Email del administrador (para recuperar la contrasena)')
@click.option('--nombre', prompt='Nombre')
def comandoCrearAdmin(login, correo, nombre):
    """Crea un administrador. La contrasena se pide por consola (no queda en
    el historial de la terminal ni en ningun archivo)."""
    try:
        login = nombreUsuario({'usuario': login})
    except ErrorValidacion as error:
        raise click.ClickException(error.mensaje)
    correo = correo.strip().lower()
    if conexion.session.query(UsuarioModel).filter_by(nombreUsuario=login).first():
        raise click.ClickException(f'Ya existe el usuario {login}')
    if conexion.session.query(UsuarioModel).filter_by(email=correo).first():
        raise click.ClickException(f'Ya existe un usuario con el email {correo}')
    password = click.prompt('Contrasena', hide_input=True, confirmation_prompt=True)
    try:
        validarPassword(password)
    except ErrorValidacion as error:
        raise click.ClickException(error.mensaje)
    conexion.session.add(UsuarioModel(
        nombre=nombre.strip(), nombreUsuario=login, email=correo, passwordHash=generate_password_hash(password), rol='admin'
    ))
    conexion.session.commit()
    click.echo(f'Administrador "{login}" creado. Inicia sesion con ese usuario.')


@click.command('reenviar-avisos')
@with_appcontext
def comandoReenviarAvisos():
    """Reintenta los avisos pendientes o fallidos (programalo con cron)."""
    from app.models import NotificacionModel
    from app.notificaciones import MAX_INTENTOS_AVISO, procesarAvisos
    ids = [n.id for n in conexion.session.query(NotificacionModel.id).filter(
        NotificacionModel.estado.in_(('pendiente', 'fallido')),
        NotificacionModel.intentos < MAX_INTENTOS_AVISO).limit(500).all()]
    click.echo(f'Avisos procesados: {procesarAvisos(ids)}')
