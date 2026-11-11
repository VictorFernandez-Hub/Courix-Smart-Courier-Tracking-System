"""Endpoints de la API agrupados por dominio (un blueprint por archivo).
Las URLs no tienen prefijo: son las mismas que usa el frontend."""
from app.routes.sistema import bp as sistema
from app.routes.auth import bp as auth
from app.routes.usuarios import bp as usuarios
from app.routes.catalogos import bp as catalogos
from app.routes.clientes import bp as clientes
from app.routes.repartidores import bp as repartidores
from app.routes.pedidos import bp as pedidos
from app.routes.publico import bp as publico
from app.routes.rutas import bp as rutas
from app.routes.caja import bp as caja
from app.routes.reportes import bp as reportes
from app.routes.incidencias import bp as incidencias

BLUEPRINTS = [
    sistema, auth, usuarios, catalogos, clientes, repartidores,
    pedidos, publico, rutas, caja, reportes, incidencias,
]
