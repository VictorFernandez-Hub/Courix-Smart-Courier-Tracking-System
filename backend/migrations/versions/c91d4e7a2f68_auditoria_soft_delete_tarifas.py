"""auditoria, soft-delete, coordenadas y tabla de tarifas

Revision ID: c91d4e7a2f68
Revises: a7b2f4c81d93
Create Date: 2026-07-29 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c91d4e7a2f68'
down_revision = 'a7b2f4c81d93'
branch_labels = None
depends_on = None


def upgrade():
    # ---------- Auditoria (fecha_creacion / fecha_actualizacion) ----------
    # server_default=now() para que las filas existentes no queden en NULL,
    # y onupdate lo maneja SQLAlchemy en el propio UPDATE (no a nivel de MySQL).
    for tabla in ('zonas', 'clientes', 'direcciones', 'almacenes', 'repartidores', 'usuarios'):
        op.add_column(tabla, sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
        op.add_column(tabla, sa.Column('fecha_actualizacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True))

    op.add_column('rutas', sa.Column('fecha_actualizacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True))

    # ---------- Soft-delete (activo) ----------
    # usuarios y repartidores ya tenian su propio campo de estado (activo /
    # disponible) desde el inicio; estos son los que faltaban.
    for tabla in ('zonas', 'clientes', 'direcciones', 'almacenes'):
        op.add_column(tabla, sa.Column('activo', sa.Boolean(), server_default='1', nullable=True))

    # ---------- Coordenadas (para mapas / calculo de rutas a futuro) ----------
    op.add_column('almacenes', sa.Column('latitud', sa.Float(), nullable=True))
    op.add_column('almacenes', sa.Column('longitud', sa.Float(), nullable=True))
    op.add_column('direcciones', sa.Column('latitud', sa.Float(), nullable=True))
    op.add_column('direcciones', sa.Column('longitud', sa.Float(), nullable=True))

    # ---------- Tabla de tarifas por zona ----------
    op.create_table('tarifas_zona',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('zona_origen_id', sa.Integer(), nullable=False),
        sa.Column('zona_destino_id', sa.Integer(), nullable=False),
        sa.Column('precio_base', sa.Numeric(10, 2), server_default='0.00', nullable=False),
        sa.Column('precio_por_kg', sa.Numeric(10, 2), server_default='0.00', nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('fecha_actualizacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['zona_origen_id'], ['zonas.id'], ),
        sa.ForeignKeyConstraint(['zona_destino_id'], ['zonas.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ---------- Indices para las consultas mas frecuentes ----------
    # pedidos crece rapido en produccion real; estas son las columnas por las
    # que se filtra en casi todos los endpoints (pool de disponibles, ruta de
    # un repartidor, listado por estado).
    op.create_index('ix_pedidos_estado_id', 'pedidos', ['estado_id'])
    op.create_index('ix_pedidos_repartidor_id', 'pedidos', ['repartidor_id'])
    op.create_index('ix_pedidos_ruta_id', 'pedidos', ['ruta_id'])
    op.create_index('ix_pedidos_cliente_id', 'pedidos', ['cliente_id'])


def downgrade():
    op.drop_index('ix_pedidos_cliente_id', table_name='pedidos')
    op.drop_index('ix_pedidos_ruta_id', table_name='pedidos')
    op.drop_index('ix_pedidos_repartidor_id', table_name='pedidos')
    op.drop_index('ix_pedidos_estado_id', table_name='pedidos')

    op.drop_table('tarifas_zona')

    op.drop_column('direcciones', 'longitud')
    op.drop_column('direcciones', 'latitud')
    op.drop_column('almacenes', 'longitud')
    op.drop_column('almacenes', 'latitud')

    for tabla in ('zonas', 'clientes', 'direcciones', 'almacenes'):
        op.drop_column(tabla, 'activo')

    op.drop_column('rutas', 'fecha_actualizacion')

    for tabla in ('zonas', 'clientes', 'direcciones', 'almacenes', 'repartidores', 'usuarios'):
        op.drop_column(tabla, 'fecha_actualizacion')
        op.drop_column(tabla, 'fecha_creacion')
