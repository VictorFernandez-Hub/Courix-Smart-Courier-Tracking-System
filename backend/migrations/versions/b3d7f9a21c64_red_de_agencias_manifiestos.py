"""red de agencias: agencia destino, operador por agencia, manifiestos y eventos de bulto

Revision ID: b3d7f9a21c64
Revises: a9c5e2f47d18
Create Date: 2026-11-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3d7f9a21c64'
down_revision = 'a9c5e2f47d18'
branch_labels = None
depends_on = None

ESTADOS = [
    ('pendiente', 1), ('en_almacen', 2), ('en_transito', 3), ('en_agencia_destino', 4),
    ('asignado', 5), ('recogido', 6), ('en_camino', 7), ('entregado', 8),
    ('no_entregado', 9), ('devuelto', 10), ('cancelado', 11),
]


def upgrade():
    op.add_column('pedidos', sa.Column('agencia_destino_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pedidos_agencia_destino', 'pedidos', 'almacenes', ['agencia_destino_id'], ['id'])
    # Los envios existentes se repartian desde su agencia de origen: siguen igual.
    op.execute('UPDATE pedidos SET agencia_destino_id = almacen_id')

    op.add_column('usuarios', sa.Column('agencia_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_usuarios_agencia', 'usuarios', 'almacenes', ['agencia_id'], ['id'])

    op.create_table(
        'manifiestos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(20), nullable=True, unique=True),
        sa.Column('agencia_origen_id', sa.Integer(), sa.ForeignKey('almacenes.id'), nullable=False),
        sa.Column('agencia_destino_id', sa.Integer(), sa.ForeignKey('almacenes.id'), nullable=False),
        sa.Column('estado', sa.String(30), nullable=False, server_default='abierto'),
        sa.Column('transportista', sa.String(100), nullable=True),
        sa.Column('placa', sa.String(15), nullable=True),
        sa.Column('precinto', sa.String(40), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('despachado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_despacho', sa.DateTime(), nullable=True),
        sa.Column('recibido_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_recepcion', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_manifiestos_estado', 'manifiestos', ['estado'])

    op.create_table(
        'manifiesto_bultos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('manifiesto_id', sa.Integer(), sa.ForeignKey('manifiestos.id'), nullable=False),
        sa.Column('bulto_id', sa.Integer(), sa.ForeignKey('bultos.id'), nullable=False),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('recibido', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('fecha_recepcion', sa.DateTime(), nullable=True),
        sa.Column('recibido_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_agregado', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('manifiesto_id', 'bulto_id', name='uq_manifiesto_bulto'),
    )
    for col in ('manifiesto_id', 'bulto_id', 'pedido_id'):
        op.create_index(f'ix_manifiesto_bultos_{col}', 'manifiesto_bultos', [col])

    op.create_table(
        'eventos_bulto',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bulto_id', sa.Integer(), sa.ForeignKey('bultos.id'), nullable=False),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('agencia_id', sa.Integer(), sa.ForeignKey('almacenes.id'), nullable=True),
        sa.Column('manifiesto_id', sa.Integer(), sa.ForeignKey('manifiestos.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_eventos_bulto_bulto_id', 'eventos_bulto', ['bulto_id'])
    op.create_index('ix_eventos_bulto_pedido_id', 'eventos_bulto', ['pedido_id'])

    # Catalogo de estados: agrega en_transito y en_agencia_destino y reordena
    # (equivale a correr `flask sembrar`, para que el despliegue no dependa de recordarlo).
    conexion = op.get_bind()
    for nombre, orden in ESTADOS:
        existe = conexion.execute(sa.text('SELECT id FROM estados_pedido WHERE nombre = :n'), {'n': nombre}).first()
        if existe:
            conexion.execute(sa.text('UPDATE estados_pedido SET orden = :o WHERE nombre = :n'), {'o': orden, 'n': nombre})
        else:
            conexion.execute(sa.text('INSERT INTO estados_pedido (nombre, orden) VALUES (:n, :o)'), {'n': nombre, 'o': orden})


def downgrade():
    op.drop_table('eventos_bulto')
    op.drop_table('manifiesto_bultos')
    op.drop_table('manifiestos')
    op.drop_constraint('fk_usuarios_agencia', 'usuarios', type_='foreignkey')
    op.drop_column('usuarios', 'agencia_id')
    op.drop_constraint('fk_pedidos_agencia_destino', 'pedidos', type_='foreignkey')
    op.drop_column('pedidos', 'agencia_destino_id')
