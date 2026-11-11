"""Comandos de consola: flask sembrar, flask crear-admin."""

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from app.extensions import conexion
from app.models import (
    UsuarioModel, EstadoPedidoModel,
)
from app.core.validacion import (
    ErrorValidacion, validarPassword,
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
@click.option('--email', 'correo', prompt='Email del administrador')
@click.option('--nombre', prompt='Nombre')
def comandoCrearAdmin(correo, nombre):
    """Crea un administrador. La contrasena se pide por consola (no queda en
    el historial de la terminal ni en ningun archivo)."""
    correo = correo.strip().lower()
    if conexion.session.query(UsuarioModel).filter_by(email=correo).first():
        raise click.ClickException(f'Ya existe un usuario con el email {correo}')
    password = click.prompt('Contrasena', hide_input=True, confirmation_prompt=True)
    try:
        validarPassword(password)
    except ErrorValidacion as error:
        raise click.ClickException(error.mensaje)
    conexion.session.add(UsuarioModel(
        nombre=nombre.strip(), email=correo, passwordHash=generate_password_hash(password), rol='admin'
    ))
    conexion.session.commit()
    click.echo(f'Administrador {correo} creado')
