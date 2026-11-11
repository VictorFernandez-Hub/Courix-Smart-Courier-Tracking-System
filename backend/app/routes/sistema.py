"""Raiz y health check."""
import logging

from flask import Blueprint
from sqlalchemy import text

from app.extensions import conexion, limiter


bp = Blueprint('sistema', __name__)


@bp.route('/')
def inicio():
    return {'message': 'API de Courrier Express funcionando'}


@bp.route('/health')
@limiter.exempt
def salud():
    """Para el balanceador / monitoreo: confirma que la base responde."""
    try:
        conexion.session.execute(text('SELECT 1'))
        return {'status': 'ok'}, 200
    except Exception:
        conexion.session.rollback()
        logging.getLogger('courrier').exception('Health check fallo')
        return {'status': 'error'}, 503
