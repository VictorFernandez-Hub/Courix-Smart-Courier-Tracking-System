"""ficha de agencias: codigo corto, referencia, correo, horario de atencion,
responsable, capacidad en bultos y motivo de baja

Revision ID: f1c7a3e92b58
Revises: e4b8c2d1f905
Create Date: 2026-11-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1c7a3e92b58'
down_revision = 'e4b8c2d1f905'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('almacenes') as tabla:
        tabla.add_column(sa.Column('codigo', sa.String(10), nullable=True))
        tabla.add_column(sa.Column('referencia', sa.String(300), nullable=True))
        tabla.add_column(sa.Column('email', sa.String(120), nullable=True))
        tabla.add_column(sa.Column('horario', sa.String(200), nullable=True))
        tabla.add_column(sa.Column('responsable_id', sa.Integer(), nullable=True))
        tabla.add_column(sa.Column('capacidad_bultos', sa.Integer(), nullable=True))
        tabla.add_column(sa.Column('motivo_desactivacion', sa.String(200), nullable=True))
        tabla.create_foreign_key('fk_almacenes_responsable', 'usuarios', ['responsable_id'], ['id'])

    # Las agencias existentes reciben un codigo provisional (AG01, AG02...)
    # que el administrador puede cambiar luego.
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("UPDATE almacenes SET codigo = printf('AG%02d', id) WHERE codigo IS NULL")
    else:
        op.execute("UPDATE almacenes SET codigo = CONCAT('AG', LPAD(id, 2, '0')) WHERE codigo IS NULL")

    with op.batch_alter_table('almacenes') as tabla:
        tabla.create_index('ux_almacenes_codigo', ['codigo'], unique=True)


def downgrade():
    with op.batch_alter_table('almacenes') as tabla:
        tabla.drop_index('ux_almacenes_codigo')
        tabla.drop_constraint('fk_almacenes_responsable', type_='foreignkey')
        tabla.drop_column('motivo_desactivacion')
        tabla.drop_column('capacidad_bultos')
        tabla.drop_column('responsable_id')
        tabla.drop_column('horario')
        tabla.drop_column('email')
        tabla.drop_column('referencia')
        tabla.drop_column('codigo')
