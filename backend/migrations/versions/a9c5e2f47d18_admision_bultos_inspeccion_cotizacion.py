"""admision de envios: remitente, bultos, inspeccion, servicio y cotizacion

Revision ID: a9c5e2f47d18
Revises: f8a4c1d36b25
Create Date: 2026-11-11 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'a9c5e2f47d18'
down_revision = 'f8a4c1d36b25'
branch_labels = None
depends_on = None

TextoLargo = sa.Text().with_variant(mysql.LONGTEXT(), 'mysql')


def upgrade():
    # ---------- tarifas: por tipo de servicio, con minimo y plazo ----------
    op.add_column('tarifas_zona', sa.Column('tipo_servicio', sa.String(20), nullable=False, server_default='estandar'))
    op.add_column('tarifas_zona', sa.Column('precio_minimo', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
    op.add_column('tarifas_zona', sa.Column('dias_entrega', sa.Integer(), nullable=True))

    # ---------- pedidos: remitente, servicio, cotizacion e inspeccion ----------
    op.add_column('pedidos', sa.Column('remitente_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pedidos_remitente', 'pedidos', 'clientes', ['remitente_id'], ['id'])
    op.add_column('pedidos', sa.Column('tipo_servicio', sa.String(20), nullable=False, server_default='estandar'))
    op.add_column('pedidos', sa.Column('peso_facturable_kg', sa.Numeric(10, 2), nullable=True))
    op.add_column('pedidos', sa.Column('valor_declarado', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
    op.add_column('pedidos', sa.Column('costo_seguro', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
    op.add_column('pedidos', sa.Column('detalle_cotizacion', sa.Text(), nullable=True))
    op.add_column('pedidos', sa.Column('estado_producto', sa.String(20), nullable=True))
    op.add_column('pedidos', sa.Column('embalaje', sa.String(20), nullable=True))
    op.add_column('pedidos', sa.Column('declara_sin_prohibidos', sa.Boolean(), nullable=True))
    op.add_column('pedidos', sa.Column('observaciones_inspeccion', sa.Text(), nullable=True))
    op.add_column('pedidos', sa.Column('inspeccionado_por_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pedidos_inspeccionado_por', 'pedidos', 'usuarios', ['inspeccionado_por_id'], ['id'])
    op.add_column('pedidos', sa.Column('fecha_inspeccion', sa.DateTime(), nullable=True))
    op.add_column('pedidos', sa.Column('foto_inspeccion', TextoLargo, nullable=True))

    # ---------- bultos ----------
    op.create_table(
        'bultos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(40), nullable=True, unique=True),
        sa.Column('peso_kg', sa.Numeric(10, 2), nullable=False),
        sa.Column('largo_cm', sa.Numeric(10, 2), nullable=True),
        sa.Column('ancho_cm', sa.Numeric(10, 2), nullable=True),
        sa.Column('alto_cm', sa.Numeric(10, 2), nullable=True),
        sa.Column('peso_volumetrico_kg', sa.Numeric(10, 2), nullable=True),
        sa.Column('peso_facturable_kg', sa.Numeric(10, 2), nullable=False),
        sa.Column('descripcion', sa.String(120), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_bultos_pedido_id', 'bultos', ['pedido_id'])

    # Pedidos que ya estaban en almacen o mas adelante: un bulto con su peso
    # registrado (sin medidas, que antes no se tomaban). Los "pendiente" se
    # pesan y miden cuando se reciban.
    conexion = op.get_bind()
    filas = conexion.execute(sa.text(
        "SELECT p.id, p.codigo_guia, p.peso_kg FROM pedidos p "
        "JOIN estados_pedido e ON e.id = p.estado_id WHERE e.nombre <> 'pendiente'"
    )).fetchall()
    for fila in filas:
        peso = round(float(fila.peso_kg or 0), 2)
        conexion.execute(sa.text(
            'INSERT INTO bultos (pedido_id, numero, codigo, peso_kg, peso_facturable_kg) '
            'VALUES (:pedido, 1, :codigo, :peso, :peso)'
        ), {'pedido': fila.id, 'codigo': f'{fila.codigo_guia}-1' if fila.codigo_guia else None, 'peso': peso})
    conexion.execute(sa.text('UPDATE pedidos SET peso_facturable_kg = peso_kg WHERE peso_kg IS NOT NULL'))


def downgrade():
    op.drop_index('ix_bultos_pedido_id', table_name='bultos')
    op.drop_table('bultos')
    op.drop_constraint('fk_pedidos_inspeccionado_por', 'pedidos', type_='foreignkey')
    op.drop_constraint('fk_pedidos_remitente', 'pedidos', type_='foreignkey')
    for columna in ('foto_inspeccion', 'fecha_inspeccion', 'inspeccionado_por_id', 'observaciones_inspeccion',
                    'declara_sin_prohibidos', 'embalaje', 'estado_producto', 'detalle_cotizacion', 'costo_seguro',
                    'valor_declarado', 'peso_facturable_kg', 'tipo_servicio', 'remitente_id'):
        op.drop_column('pedidos', columna)
    for columna in ('dias_entrega', 'precio_minimo', 'tipo_servicio'):
        op.drop_column('tarifas_zona', columna)
