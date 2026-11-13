"""avisos al cliente (outbox) y comprobantes electronicos

Revision ID: d8f2b6c47e13
Revises: c5e8a1b3d920
Create Date: 2026-11-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8f2b6c47e13'
down_revision = 'c5e8a1b3d920'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clientes', sa.Column('recibe_avisos', sa.Boolean(), nullable=False, server_default='1'))

    op.create_table(
        'notificaciones',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('evento', sa.String(30), nullable=False),
        sa.Column('canal', sa.String(20), nullable=False),
        sa.Column('destino', sa.String(120), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='pendiente'),
        sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.String(500), nullable=True),
        sa.Column('id_proveedor', sa.String(120), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('fecha_envio', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_notificaciones_pedido_id', 'notificaciones', ['pedido_id'])
    op.create_index('ix_notificaciones_estado', 'notificaciones', ['estado'])

    op.create_table(
        'series_comprobante',
        sa.Column('serie', sa.String(4), primary_key=True),
        sa.Column('tipo', sa.String(10), nullable=False),
        sa.Column('ultimo_numero', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_table(
        'comprobantes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('tipo', sa.String(10), nullable=False),
        sa.Column('serie', sa.String(4), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('cliente_tipo_doc', sa.String(1), nullable=False),
        sa.Column('cliente_num_doc', sa.String(15), nullable=True),
        sa.Column('cliente_nombre', sa.String(150), nullable=False),
        sa.Column('cliente_direccion', sa.String(200), nullable=True),
        sa.Column('cliente_email', sa.String(120), nullable=True),
        sa.Column('descripcion', sa.String(250), nullable=False),
        sa.Column('gravada', sa.Numeric(10, 2), nullable=False),
        sa.Column('igv', sa.Numeric(10, 2), nullable=False),
        sa.Column('total', sa.Numeric(10, 2), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False, server_default='pendiente'),
        sa.Column('mensaje_sunat', sa.String(500), nullable=True),
        sa.Column('enlace_pdf', sa.String(300), nullable=True),
        sa.Column('codigo_hash', sa.String(100), nullable=True),
        sa.Column('emitido_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_emision', sa.Date(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('serie', 'numero', name='uq_comprobante_serie_numero'),
    )
    op.create_index('ix_comprobantes_pedido_id', 'comprobantes', ['pedido_id'])


def downgrade():
    op.drop_table('comprobantes')
    op.drop_table('series_comprobante')
    op.drop_table('notificaciones')
    op.drop_column('clientes', 'recibe_avisos')
