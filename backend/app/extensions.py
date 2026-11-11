"""Instancias unicas de las extensiones de Flask. Se crean aqui sin app y se
enlazan en crear_app() (patron "application factory")."""
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# La conexion del ORM con la base de datos (una sola para toda la app).
conexion = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
