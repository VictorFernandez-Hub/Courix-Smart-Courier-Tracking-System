"""seguridad (revocacion de tokens, bloqueo de login), modalidad de pago,
intentos de entrega, liquidacion de caja por ruta y tabla de auditoria

Revision ID: d5e2a8f41c07
Revises: c91d4e7a2f68
Create Date: 2026-11-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e2a8f41c07'
down_revision = 'c91d4e7a2f68'
branch_labels = None
depends_on = None


def upgrade():
    # ---------- usuarios: revocacion de sesiones y bloqueo por intentos ----------
    op.add_column('usuarios', sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
    op.add_column('usuarios', sa.Column('intentos_fallidos', sa.Integer(), server_default='0', nullable=False))
    op.add_column('usuarios', sa.Column('bloqueado_hasta', sa.DateTime(), nullable=True))
    op.add_column('usuarios', sa.Column('ultimo_login', sa.DateTime(), nullable=True))

    # ---------- pedidos: modalidad de pago, tarifa aplicada, intentos ----------
    # Los pedidos existentes quedan como contra_entrega (el unico modo que
    # existia hasta ahora).
    op.add_column('pedidos', sa.Column('modalidad_pago', sa.String(20), server_default='contra_entrega', nullable=False))
    op.add_column('pedidos', sa.Column('tarifa_id', sa.Integer(), nullable=True))
    op.add_column('pedidos', sa.Column('intentos_entrega', sa.Integer(), server_default='0', nullable=False))
    op.add_column('pedidos', sa.Column('motivo_no_entrega', sa.String(40), nullable=True))
    op.add_column('pedidos', sa.Column('fecha_entrega', sa.DateTime(), nullable=True))
    op.create_foreign_key('fk_pedidos_tarifa', 'pedidos', 'tarifas_zona', ['tarifa_id'], ['id'])

    # ---------- pagos: referencia y trazabilidad del cobro ----------
    op.add_column('pagos', sa.Column('referencia', sa.String(60), nullable=True))
    op.add_column('pagos', sa.Column('repartidor_id', sa.Integer(), nullable=True))
    op.add_column('pagos', sa.Column('ruta_id', sa.Integer(), nullable=True))
    op.add_column('pagos', sa.Column('registrado_por_id', sa.Integer(), nullable=True))
    op.add_column('pagos', sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    op.create_foreign_key('fk_pagos_repartidor', 'pagos', 'repartidores', ['repartidor_id'], ['id'])
    op.create_foreign_key('fk_pagos_ruta', 'pagos', 'rutas', ['ruta_id'], ['id'])
    op.create_foreign_key('fk_pagos_registrado_por', 'pagos', 'usuarios', ['registrado_por_id'], ['id'])
    op.create_index('ix_pagos_ruta_id', 'pagos', ['ruta_id'])

    # ---------- liquidaciones de caja por ruta ----------
    op.create_table('liquidaciones_ruta',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ruta_id', sa.Integer(), nullable=False),
        sa.Column('repartidor_id', sa.Integer(), nullable=False),
        sa.Column('monto_esperado', sa.Numeric(10, 2), nullable=False),
        sa.Column('monto_entregado', sa.Numeric(10, 2), nullable=False),
        sa.Column('diferencia', sa.Numeric(10, 2), nullable=False),
        sa.Column('observacion', sa.Text(), nullable=True),
        sa.Column('recibido_por_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['ruta_id'], ['rutas.id']),
        sa.ForeignKeyConstraint(['repartidor_id'], ['repartidores.id']),
        sa.ForeignKeyConstraint(['recibido_por_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ruta_id', name='uq_liquidaciones_ruta_ruta_id'),
    )

    # Las rutas que ya estaban completadas antes de existir el control de caja
    # se dan por liquidadas; si no, bloquearian a sus repartidores para tomar
    # pedidos nuevos (regla MAX_RUTAS_SIN_LIQUIDAR).
    op.execute(
        "INSERT INTO liquidaciones_ruta (ruta_id, repartidor_id, monto_esperado, monto_entregado, diferencia, observacion) "
        "SELECT id, repartidor_id, 0, 0, 0, 'Ruta anterior al control de caja' FROM rutas WHERE estado = 'completada'"
    )

    # ---------- auditoria ----------
    op.create_table('auditoria',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('accion', sa.String(60), nullable=False),
        sa.Column('entidad', sa.String(40), nullable=False),
        sa.Column('entidad_id', sa.Integer(), nullable=True),
        sa.Column('detalle', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('fecha', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_auditoria_entidad', 'auditoria', ['entidad', 'entidad_id'])
    op.create_index('ix_rutas_repartidor_estado', 'rutas', ['repartidor_id', 'estado'])


def downgrade():
    op.drop_index('ix_rutas_repartidor_estado', table_name='rutas')
    op.drop_index('ix_auditoria_entidad', table_name='auditoria')
    op.drop_table('auditoria')
    op.drop_table('liquidaciones_ruta')

    op.drop_index('ix_pagos_ruta_id', table_name='pagos')
    op.drop_constraint('fk_pagos_registrado_por', 'pagos', type_='foreignkey')
    op.drop_constraint('fk_pagos_ruta', 'pagos', type_='foreignkey')
    op.drop_constraint('fk_pagos_repartidor', 'pagos', type_='foreignkey')
    for columna in ('fecha_creacion', 'registrado_por_id', 'ruta_id', 'repartidor_id', 'referencia'):
        op.drop_column('pagos', columna)

    op.drop_constraint('fk_pedidos_tarifa', 'pedidos', type_='foreignkey')
    for columna in ('fecha_entrega', 'motivo_no_entrega', 'intentos_entrega', 'tarifa_id', 'modalidad_pago'):
        op.drop_column('pedidos', columna)

    for columna in ('ultimo_login', 'bloqueado_hasta', 'intentos_fallidos', 'token_version'):
        op.drop_column('usuarios', columna)
