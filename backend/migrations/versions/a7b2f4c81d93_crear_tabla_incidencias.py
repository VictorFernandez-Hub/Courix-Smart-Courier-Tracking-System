"""crear tabla incidencias

Revision ID: a7b2f4c81d93
Revises: f3a1c9d02b47
Create Date: 2026-07-29 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b2f4c81d93'
down_revision = 'f3a1c9d02b47'
branch_labels = None
depends_on = None


def upgrade():

    op.create_table('incidencias',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=20), server_default='abierta', nullable=True),
        sa.Column('resolucion', sa.Text(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('fecha_resolucion', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedidos.id'], ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('incidencias')
