"""tesoreria: cargos adicionales, reembolsos con nota de credito, cierres de
caja; credito de clientes; responsable, prioridad y plazo de incidencias

Revision ID: b5f1d9c27e83
Revises: a2d6e8f13c47
Create Date: 2026-11-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b5f1d9c27e83'
down_revision = 'a2d6e8f13c47'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clientes') as tabla:
        tabla.add_column(sa.Column('credito_habilitado', sa.Boolean(), nullable=False, server_default='0'))
        tabla.add_column(sa.Column('limite_credito', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
        tabla.add_column(sa.Column('dias_credito', sa.Integer(), nullable=False, server_default='30'))

    with op.batch_alter_table('comprobantes') as tabla:
        tabla.add_column(sa.Column('comprobante_ref_id', sa.Integer(), nullable=True))
        tabla.add_column(sa.Column('motivo_nota', sa.String(200), nullable=True))
        tabla.create_foreign_key('fk_comprobantes_ref', 'comprobantes', ['comprobante_ref_id'], ['id'])

    with op.batch_alter_table('incidencias') as tabla:
        tabla.add_column(sa.Column('responsable_id', sa.Integer(), nullable=True))
        tabla.add_column(sa.Column('prioridad', sa.String(10), nullable=False, server_default='media'))
        tabla.add_column(sa.Column('fecha_limite', sa.DateTime(), nullable=True))
        tabla.add_column(sa.Column('compensacion', sa.Numeric(10, 2), nullable=True))
        tabla.create_foreign_key('fk_incidencias_responsable', 'usuarios', ['responsable_id'], ['id'])

    op.create_table(
        'cargos_adicionales',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False, index=True),
        sa.Column('concepto', sa.String(20), nullable=False),
        sa.Column('monto', sa.Numeric(10, 2), nullable=False),
        sa.Column('descripcion', sa.String(200), nullable=True),
        sa.Column('estado', sa.String(20), nullable=False, server_default='pendiente'),
        sa.Column('metodo', sa.String(20), nullable=True),
        sa.Column('referencia', sa.String(60), nullable=True),
        sa.Column('fecha_pago', sa.DateTime(), nullable=True),
        sa.Column('registrado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('cobrado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'reembolsos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pedido_id', sa.Integer(), sa.ForeignKey('pedidos.id'), nullable=False, index=True),
        sa.Column('tipo', sa.String(20), nullable=False),
        sa.Column('monto', sa.Numeric(10, 2), nullable=False),
        sa.Column('metodo', sa.String(20), nullable=False),
        sa.Column('referencia', sa.String(60), nullable=True),
        sa.Column('motivo', sa.String(500), nullable=False),
        sa.Column('beneficiario_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=True),
        sa.Column('incidencia_id', sa.Integer(), sa.ForeignKey('incidencias.id'), nullable=True),
        sa.Column('comprobante_id', sa.Integer(), sa.ForeignKey('comprobantes.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'cierres_caja',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(20), nullable=True, unique=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False, index=True),
        sa.Column('agencia_id', sa.Integer(), sa.ForeignKey('almacenes.id'), nullable=True),
        sa.Column('desde', sa.DateTime(), nullable=True),
        sa.Column('hasta', sa.DateTime(), nullable=False),
        sa.Column('efectivo_esperado', sa.Numeric(10, 2), nullable=False),
        sa.Column('efectivo_contado', sa.Numeric(10, 2), nullable=False),
        sa.Column('diferencia', sa.Numeric(10, 2), nullable=False),
        sa.Column('detalle', sa.Text(), nullable=True),
        sa.Column('observacion', sa.Text(), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.func.now()),
    )
    # Las incidencias abiertas existentes reciben el plazo de prioridad media (72 h)
    op.execute("UPDATE incidencias SET prioridad = 'alta' WHERE tipo IN ('faltante', 'producto_danado')")


def downgrade():
    op.drop_table('cierres_caja')
    op.drop_table('reembolsos')
    op.drop_table('cargos_adicionales')
    with op.batch_alter_table('incidencias') as tabla:
        tabla.drop_constraint('fk_incidencias_responsable', type_='foreignkey')
        tabla.drop_column('compensacion')
        tabla.drop_column('fecha_limite')
        tabla.drop_column('prioridad')
        tabla.drop_column('responsable_id')
    with op.batch_alter_table('comprobantes') as tabla:
        tabla.drop_constraint('fk_comprobantes_ref', type_='foreignkey')
        tabla.drop_column('motivo_nota')
        tabla.drop_column('comprobante_ref_id')
    with op.batch_alter_table('clientes') as tabla:
        tabla.drop_column('dias_credito')
        tabla.drop_column('limite_credito')
        tabla.drop_column('credito_habilitado')
