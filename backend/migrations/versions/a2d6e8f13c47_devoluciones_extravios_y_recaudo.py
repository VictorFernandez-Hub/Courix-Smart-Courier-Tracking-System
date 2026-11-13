"""logistica inversa (por_devolver, retorno al origen), envios extraviados y
contra entrega de mercaderia (recaudos y su liquidacion al remitente)

Revision ID: a2d6e8f13c47
Revises: f1c7a3e92b58
Create Date: 2026-11-12 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a2d6e8f13c47'
down_revision = 'f1c7a3e92b58'
branch_labels = None
depends_on = None

ESTADOS = [
    ('pendiente', 1), ('en_almacen', 2), ('en_transito', 3), ('en_agencia_destino', 4),
    ('asignado', 5), ('recogido', 6), ('en_camino', 7), ('entregado', 8),
    ('no_entregado', 9), ('por_devolver', 10), ('devuelto', 11), ('cancelado', 12), ('extraviado', 13),
]


def upgrade():
    with op.batch_alter_table('pedidos') as tabla:
        tabla.add_column(sa.Column('retorno_al_origen', sa.Boolean(), nullable=False, server_default='0'))
        tabla.add_column(sa.Column('monto_recaudo', sa.Numeric(10, 2), nullable=False, server_default='0.00'))

    op.create_table(
        'liquidaciones_recaudo',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(20), nullable=True, unique=True),
        sa.Column('remitente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=False),
        sa.Column('envios', sa.Integer(), nullable=False),
        sa.Column('monto_recaudado', sa.Numeric(10, 2), nullable=False),
        sa.Column('porcentaje_comision', sa.Numeric(5, 2), nullable=False),
        sa.Column('comision', sa.Numeric(10, 2), nullable=False),
        sa.Column('monto_pagado', sa.Numeric(10, 2), nullable=False),
        sa.Column('metodo', sa.String(20), nullable=False),
        sa.Column('referencia', sa.String(60), nullable=True),
        sa.Column('observacion', sa.Text(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'recaudos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False, unique=True),
        sa.Column('remitente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=False),
        sa.Column('monto', sa.Numeric(10, 2), nullable=False),
        sa.Column('metodo', sa.String(20), nullable=False),
        sa.Column('referencia', sa.String(60), nullable=True),
        sa.Column('repartidor_id', sa.Integer(), sa.ForeignKey('repartidores.id'), nullable=True),
        sa.Column('ruta_id', sa.Integer(), sa.ForeignKey('rutas.id'), nullable=True),
        sa.Column('registrado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_cobro', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('liquidacion_id', sa.Integer(), sa.ForeignKey('liquidaciones_recaudo.id'), nullable=True),
    )
    op.create_index('ix_recaudos_remitente_liquidacion', 'recaudos', ['remitente_id', 'liquidacion_id'])

    conexion = op.get_bind()
    for nombre, orden in ESTADOS:
        existe = conexion.execute(sa.text('SELECT id FROM estados_pedido WHERE nombre = :n'), {'n': nombre}).first()
        if existe:
            conexion.execute(sa.text('UPDATE estados_pedido SET orden = :o WHERE nombre = :n'), {'o': orden, 'n': nombre})
        else:
            conexion.execute(sa.text('INSERT INTO estados_pedido (nombre, orden) VALUES (:n, :o)'), {'n': nombre, 'o': orden})


def downgrade():
    conexion = op.get_bind()
    usados = conexion.execute(sa.text(
        "SELECT COUNT(*) FROM pedidos p JOIN estados_pedido e ON e.id = p.estado_id "
        "WHERE e.nombre IN ('por_devolver', 'extraviado')")).scalar()
    if usados:
        raise RuntimeError('Hay envios en "por_devolver" o "extraviado": resuelvelos antes de revertir')
    conexion.execute(sa.text("DELETE FROM historial_estados WHERE estado_id IN "
                             "(SELECT id FROM estados_pedido WHERE nombre IN ('por_devolver', 'extraviado'))"))
    conexion.execute(sa.text("DELETE FROM estados_pedido WHERE nombre IN ('por_devolver', 'extraviado')"))
    for nombre, orden in (('devuelto', 10), ('cancelado', 11)):
        conexion.execute(sa.text('UPDATE estados_pedido SET orden = :o WHERE nombre = :n'), {'o': orden, 'n': nombre})

    op.drop_index('ix_recaudos_remitente_liquidacion', table_name='recaudos')
    op.drop_table('recaudos')
    op.drop_table('liquidaciones_recaudo')
    with op.batch_alter_table('pedidos') as tabla:
        tabla.drop_column('monto_recaudo')
        tabla.drop_column('retorno_al_origen')
