"""ficha completa de clientes: tipo de cliente y documento, telefono
alternativo, notas internas, fecha de consentimiento, motivo de baja,
quien lo registro, direccion principal e indices de busqueda

Revision ID: e4b8c2d1f905
Revises: d8f2b6c47e13
Create Date: 2026-11-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4b8c2d1f905'
down_revision = 'd8f2b6c47e13'
branch_labels = None
depends_on = None


def _soloDigitos(columna, largo):
    if op.get_bind().dialect.name == 'sqlite':
        return f"LENGTH({columna}) = {largo} AND {columna} NOT GLOB '*[^0-9]*'"
    return f"{columna} REGEXP '^[0-9]{{{largo}}}$'"


def upgrade():
    with op.batch_alter_table('clientes') as tabla:
        tabla.add_column(sa.Column('tipo_cliente', sa.String(10), nullable=False, server_default='persona'))
        tabla.add_column(sa.Column('tipo_documento', sa.String(10), nullable=True))
        tabla.add_column(sa.Column('telefono_alternativo', sa.String(20), nullable=True))
        tabla.add_column(sa.Column('notas', sa.Text(), nullable=True))
        tabla.add_column(sa.Column('fecha_consentimiento', sa.DateTime(), nullable=True))
        tabla.add_column(sa.Column('motivo_desactivacion', sa.String(200), nullable=True))
        tabla.add_column(sa.Column('creado_por_id', sa.Integer(), nullable=True))
        tabla.create_foreign_key('fk_clientes_creado_por', 'usuarios', ['creado_por_id'], ['id'])
        tabla.create_index('ix_clientes_dni', ['dni'])
        tabla.create_index('ix_clientes_telefono', ['telefono'])

    # Los documentos ya registrados se clasifican por su forma: 8 digitos es
    # DNI y 11 digitos es RUC (los RUC 20 son empresas).
    for tipo, largo in (('DNI', 8), ('RUC', 11)):
        op.execute(f"UPDATE clientes SET tipo_documento = '{tipo}' WHERE {_soloDigitos('dni', largo)}")
    op.execute("UPDATE clientes SET tipo_cliente = 'empresa' WHERE tipo_documento = 'RUC' AND dni LIKE '20%'")
    # El consentimiento vigente se fecha con el alta del cliente (mejor dato disponible).
    op.execute('UPDATE clientes SET fecha_consentimiento = fecha_creacion')

    with op.batch_alter_table('direcciones') as tabla:
        tabla.add_column(sa.Column('es_principal', sa.Boolean(), nullable=False, server_default='0'))

    # La direccion activa mas antigua de cada cliente pasa a ser la principal.
    op.execute(
        'UPDATE direcciones SET es_principal = 1 WHERE id IN ('
        ' SELECT id FROM (SELECT MIN(id) AS id FROM direcciones WHERE activo = 1 GROUP BY cliente_id) AS primeras)'
    )


def downgrade():
    with op.batch_alter_table('direcciones') as tabla:
        tabla.drop_column('es_principal')

    with op.batch_alter_table('clientes') as tabla:
        tabla.drop_index('ix_clientes_telefono')
        tabla.drop_index('ix_clientes_dni')
        tabla.drop_constraint('fk_clientes_creado_por', type_='foreignkey')
        for columna in ('creado_por_id', 'motivo_desactivacion', 'fecha_consentimiento', 'notas',
                        'telefono_alternativo', 'tipo_documento', 'tipo_cliente'):
            tabla.drop_column(columna)
