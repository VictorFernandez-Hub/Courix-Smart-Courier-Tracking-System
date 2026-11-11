"""Fabrica de la aplicacion Flask (application factory).

Uso:
    from app import crear_app
    app = crear_app()
"""
import logging
import os

from dotenv import load_dotenv
from flask import Flask, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

DIRECTORIO_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# El .env vive en backend/, sin importar desde que carpeta se ejecute.
load_dotenv(os.path.join(DIRECTORIO_BACKEND, '.env'))


def crear_app():
    from app.config import cargarConfiguracion
    from app.extensions import conexion, migrate, jwt, limiter
    from app.core.seguridad import registrarSeguridadHttp
    from app import models  # noqa: F401  (registra todas las tablas)
    from app.cli import comandoSembrar, comandoCrearAdmin
    from app.routes import BLUEPRINTS

    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    # static_folder=None: la especificacion OpenAPI solo se publica cuando las
    # docs estan habilitadas (ver _registrarDocs), no por la ruta estatica de Flask.
    app = Flask(__name__, static_folder=None)
    cargarConfiguracion(app)

    if app.config['PROXY_SALTOS'] > 0:
        # Detras de Nginx/Cloudflare: sin esto, request.remote_addr seria la IP
        # del proxy y el rate limit bloquearia a todos los usuarios a la vez.
        saltos = app.config['PROXY_SALTOS']
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos, x_host=saltos)

    CORS(
        app,
        origins=app.config['ORIGENES_PERMITIDOS'] or '*',
        allow_headers=['Content-Type', 'Authorization', 'X-Request-ID'],
        expose_headers=['X-Request-ID'],
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        max_age=600,
    )

    conexion.init_app(app)
    migrate.init_app(app, conexion, directory=os.path.join(DIRECTORIO_BACKEND, 'migrations'))
    jwt.init_app(app)
    limiter.init_app(app)
    registrarSeguridadHttp(app)

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    if app.config['DOCS_HABILITADOS']:
        _registrarDocs(app)

    app.cli.add_command(comandoSembrar)
    app.cli.add_command(comandoCrearAdmin)
    return app


def _registrarDocs(app):
    from flask_swagger_ui import get_swaggerui_blueprint

    app.register_blueprint(
        get_swaggerui_blueprint('/docs', '/static/openapi.json', config={'app_name': 'Courrier Express API'}),
        url_prefix='/docs',
    )

    @app.route('/static/openapi.json')
    def openapiSpec():
        return send_from_directory(os.path.join(app.root_path, 'static'), 'openapi.json')
