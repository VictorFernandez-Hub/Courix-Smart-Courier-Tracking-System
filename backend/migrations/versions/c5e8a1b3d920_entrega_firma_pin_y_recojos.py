"""entrega con firma, DNI y PIN; solicitudes de recojo a domicilio

Revision ID: c5e8a1b3d920
Revises: b3d7f9a21c64
Create Date: 2026-11-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'c5e8a1b3d920'
down_revision = 'b3d7f9a21c64'
branch_labels = None
depends_on = None

TextoLargo = sa.Text().with_variant(mysql.LONGTEXT(), 'mysql')


def upgrade():
    op.create_table(
        'solicitudes_recojo',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(20), nullable=True, unique=True),
        sa.Column('remitente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=False),
        sa.Column('direccion_id', sa.Integer(), sa.ForeignKey('direcciones.id'), nullable=False),
        sa.Column('zona_id', sa.Integer(), sa.ForeignKey('zonas.id'), nullable=False),
        sa.Column('agencia_id', sa.Integer(), sa.ForeignKey('almacenes.id'), nullable=False),
        sa.Column('fecha_programada', sa.Date(), nullable=False),
        sa.Column('franja', sa.String(10), nullable=False),
        sa.Column('bultos_estimados', sa.Integer(), nullable=False),
        sa.Column('peso_estimado_kg', sa.Numeric(10, 2), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='pendiente'),
        sa.Column('repartidor_id', sa.Integer(), sa.ForeignKey('repartidores.id'), nullable=True),
        sa.Column('bultos_recogidos', sa.Integer(), nullable=True),
        sa.Column('fecha_recojo', sa.DateTime(), nullable=True),
        sa.Column('motivo_fallo', sa.String(30), nullable=True),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_solicitudes_recojo_fecha_programada', 'solicitudes_recojo', ['fecha_programada'])
    op.create_index('ix_solicitudes_recojo_estado', 'solicitudes_recojo', ['estado'])

    op.add_column('pedidos', sa.Column('requiere_pin', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('pedidos', sa.Column('pin_hash', sa.String(64), nullable=True))
    op.add_column('pedidos', sa.Column('pin_intentos', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('pedidos', sa.Column('solicitud_recojo_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pedidos_solicitud_recojo', 'pedidos', 'solicitudes_recojo',
                          ['solicitud_recojo_id'], ['id'])

    op.create_table(
        'entregas',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False, unique=True),
        sa.Column('nombre_receptor', sa.String(100), nullable=False),
        sa.Column('dni_receptor', sa.String(15), nullable=False),
        sa.Column('relacion', sa.String(20), nullable=False),
        sa.Column('firma', TextoLargo, nullable=True),
        sa.Column('pin_verificado', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('latitud', sa.Float(), nullable=True),
        sa.Column('longitud', sa.Float(), nullable=True),
        sa.Column('repartidor_id', sa.Integer(), sa.ForeignKey('repartidores.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('entregas')
    op.drop_constraint('fk_pedidos_solicitud_recojo', 'pedidos', type_='foreignkey')
    for columna in ('solicitud_recojo_id', 'pin_intentos', 'pin_hash', 'requiere_pin'):
        op.drop_column('pedidos', columna)
    op.drop_table('solicitudes_recojo')
