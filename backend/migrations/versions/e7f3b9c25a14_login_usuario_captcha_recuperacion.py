"""login por nombre de usuario, captcha y recuperacion de contrasena

Revision ID: e7f3b9c25a14
Revises: d5e2a8f41c07
Create Date: 2026-11-11 18:00:00.000000

"""
import re

from alembic import op
import sqlalchemy as sa


revision = 'e7f3b9c25a14'
down_revision = 'd5e2a8f41c07'
branch_labels = None
depends_on = None


def _usuarioDesdeEmail(email, usados):
    """Para los usuarios que ya existen: el usuario inicial es la parte del
    email antes de la @ (jperez@empresa.pe -> jperez), sin repetidos."""
    base = re.sub(r'[^a-z0-9._-]', '', (email or '').split('@')[0].lower()).strip('._-')[:26] or 'usuario'
    if len(base) < 3:
        base = (base + 'usr')[:3]
    candidato, n = base, 2
    while candidato in usados:
        candidato, n = f'{base}{n}', n + 1
    usados.add(candidato)
    return candidato


def upgrade():
    op.add_column('usuarios', sa.Column('nombre_usuario', sa.String(30), nullable=True))

    conexion = op.get_bind()
    usados = set()
    for fila in conexion.execute(sa.text('SELECT id, email FROM usuarios ORDER BY id')).fetchall():
        conexion.execute(sa.text('UPDATE usuarios SET nombre_usuario = :u WHERE id = :id'),
                         {'u': _usuarioDesdeEmail(fila.email, usados), 'id': fila.id})

    with op.batch_alter_table('usuarios') as tabla:
        tabla.alter_column('nombre_usuario', existing_type=sa.String(30), nullable=False)
        tabla.create_unique_constraint('uq_usuarios_nombre_usuario', ['nombre_usuario'])

    op.create_table(
        'captchas',
        sa.Column('id', sa.String(43), primary_key=True),
        sa.Column('respuesta_hash', sa.String(64), nullable=False),
        sa.Column('expira', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_captchas_expira', 'captchas', ['expira'])

    op.create_table(
        'recuperaciones_password',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expira', sa.DateTime(), nullable=False),
        sa.Column('usado_en', sa.DateTime(), nullable=True),
        sa.Column('ip_solicitud', sa.String(45), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_recuperaciones_password_usuario_id', 'recuperaciones_password', ['usuario_id'])


def downgrade():
    op.drop_index('ix_recuperaciones_password_usuario_id', table_name='recuperaciones_password')
    op.drop_table('recuperaciones_password')
    op.drop_index('ix_captchas_expira', table_name='captchas')
    op.drop_table('captchas')
    with op.batch_alter_table('usuarios') as tabla:
        tabla.drop_constraint('uq_usuarios_nombre_usuario', type_='unique')
        tabla.drop_column('nombre_usuario')
