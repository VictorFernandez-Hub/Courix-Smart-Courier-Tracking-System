"""datos personales del usuario: dni, celular y direccion

Revision ID: f8a4c1d36b25
Revises: e7f3b9c25a14
Create Date: 2026-11-11 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a4c1d36b25'
down_revision = 'e7f3b9c25a14'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: los usuarios que ya existen no tienen estos datos todavia.
    op.add_column('usuarios', sa.Column('dni', sa.String(15), nullable=True))
    op.add_column('usuarios', sa.Column('celular', sa.String(20), nullable=True))
    op.add_column('usuarios', sa.Column('direccion', sa.String(200), nullable=True))
    op.create_unique_constraint('uq_usuarios_dni', 'usuarios', ['dni'])


def downgrade():
    op.drop_constraint('uq_usuarios_dni', 'usuarios', type_='unique')
    op.drop_column('usuarios', 'direccion')
    op.drop_column('usuarios', 'celular')
    op.drop_column('usuarios', 'dni')
