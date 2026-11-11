"""Crea un usuario administrador directamente en la base de datos.

La contrasena se pide por consola (oculta): nunca queda escrita en este
archivo ni en el historial de la terminal.

Uso (desde la carpeta backend; equivalente a `flask crear-admin`):
    python scripts/crear_admin.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import crear_app  # noqa: E402
from app.cli import comandoCrearAdmin  # noqa: E402

if __name__ == '__main__':
    with crear_app().app_context():
        comandoCrearAdmin.main(standalone_mode=True)
