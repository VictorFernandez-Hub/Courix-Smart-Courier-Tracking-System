"""SOLO PARA DESARROLLO LOCAL: crea las tablas directamente (sin migraciones)
y siembra el catalogo de estados.

Uso (desde la carpeta backend):
    python scripts/seed.py

En produccion usa:
    flask db upgrade     # crea/actualiza las tablas con las migraciones
    flask sembrar        # siembra el catalogo de estados
    flask crear-admin    # crea el primer administrador
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import crear_app  # noqa: E402
from app.cli import sembrarEstados  # noqa: E402
from app.extensions import conexion  # noqa: E402

app = crear_app()
with app.app_context():
    if app.config['ES_PRODUCCION']:
        raise SystemExit('seed.py no se usa en produccion: corre "flask db upgrade" y "flask sembrar"')
    conexion.create_all()
    print('Tablas creadas')
    sembrarEstados()
    print('Catalogo de estados sembrado')
