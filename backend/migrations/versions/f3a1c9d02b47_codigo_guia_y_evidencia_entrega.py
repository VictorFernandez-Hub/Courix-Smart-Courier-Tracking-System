"""codigo guia y evidencia entrega

Revision ID: f3a1c9d02b47
Revises: ee5059ab8276
Create Date: 2026-07-29 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'f3a1c9d02b47'
down_revision = 'ee5059ab8276'
branch_labels = None
depends_on = None


def upgrade():
    # El modelo (models/pedido.py) ya declaraba estas dos columnas
    # (codigoGuia y evidenciaEntrega), pero nunca se genero la migracion
    # que las agrega a la tabla real - por eso "Unknown column
    # 'pedidos.codigo_guia' in 'field list'" al crear un pedido.
    with op.batch_alter_table('pedidos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('codigo_guia', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('evidencia_entrega', mysql.LONGTEXT(), nullable=True))
        batch_op.create_unique_constraint('uq_pedidos_codigo_guia', ['codigo_guia'])


def downgrade():
    with op.batch_alter_table('pedidos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_pedidos_codigo_guia', type_='unique')
        batch_op.drop_column('evidencia_entrega')
        batch_op.drop_column('codigo_guia')
