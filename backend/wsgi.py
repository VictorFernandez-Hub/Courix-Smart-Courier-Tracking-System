"""Punto de entrada de la aplicacion.

Desarrollo:  flask run            (Flask encuentra este archivo solo)
Linux:       gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
Windows:     waitress-serve --listen=127.0.0.1:8000 wsgi:app
"""
import os

from app import crear_app

app = crear_app()

if __name__ == '__main__':
    # Solo para desarrollo local. En produccion: gunicorn / waitress.
    app.run(debug=not app.config['ES_PRODUCCION'], port=int(os.environ.get('PORT', 5000)))
