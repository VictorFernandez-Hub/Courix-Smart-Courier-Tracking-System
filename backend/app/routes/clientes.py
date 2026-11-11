"""Clientes y sus direcciones de entrega."""

from flask import Blueprint, request

from app.extensions import conexion
from app.models import (
    ClienteModel, DireccionModel,
)
from app.core.seguridad import (
    requiereRol, auditar, ROLES_STAFF,
)
from app.core.validacion import (
    ErrorValidacion, cuerpoJson, texto, entero, coordenada, email, telefono,
    dni,
)
from app.schemas import (
    ClienteDto, DireccionDto,
)
from app.servicios import (
    exigirZonaActiva, obtener, patronBusqueda,
)


bp = Blueprint('clientes', __name__)


@bp.route('/clientes', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarClientes():
    query = conexion.session.query(ClienteModel)
    if request.args.get('incluir_inactivos') != 'true':
        query = query.filter_by(activo=True)

    buscar = request.args.get('q')
    if buscar:
        patron = patronBusqueda(buscar)
        query = query.filter(
            ClienteModel.nombre.ilike(patron, escape='\\') |
            ClienteModel.telefono.ilike(patron, escape='\\') |
            ClienteModel.dni.ilike(patron, escape='\\')
        )

    resultado = query.order_by(ClienteModel.nombre).limit(500).all()
    return {'content': ClienteDto().dump(resultado, many=True)}, 200


@bp.route('/cliente', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearCliente():
    data = cuerpoJson()
    nuevo = ClienteModel(
        nombre=texto(data, 'nombre', requerido=True, maximo=100, minimo=2),
        dni=dni(data),
        telefono=telefono(data, requerido=True),
        email=email(data, requerido=False),
    )
    conexion.session.add(nuevo)
    conexion.session.commit()
    return {'content': ClienteDto().dump(nuevo)}, 201


@bp.route('/cliente/<int:id>/desactivar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def desactivarCliente(id):
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    cliente.activo = False
    auditar('cliente_desactivado', 'cliente', id)
    conexion.session.commit()
    return {'message': 'Cliente desactivado exitosamente'}, 200


@bp.route('/cliente/<int:id>/activar', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def activarCliente(id):
    cliente = obtener(ClienteModel, id, 'Cliente no existe')
    cliente.activo = True
    conexion.session.commit()
    return {'message': 'Cliente activado exitosamente'}, 200


# ---------- DIRECCIONES DEL CLIENTE ----------

@bp.route('/direccion-cliente', methods=['POST'])
@requiereRol(*ROLES_STAFF)
def crearDireccionCliente():
    data = cuerpoJson()
    clienteId = entero(data, 'clienteId', requerido=True)
    cliente = obtener(ClienteModel, clienteId, 'El cliente no existe')
    if not cliente.activo:
        raise ErrorValidacion('El cliente esta desactivado')
    zonaId = entero(data, 'zonaId')
    exigirZonaActiva(zonaId)

    nueva = DireccionModel(
        clienteId=clienteId,
        zonaId=zonaId,
        etiqueta=texto(data, 'etiqueta', maximo=50),
        calle=texto(data, 'calle', requerido=True, maximo=300, minimo=3),
        referencia=texto(data, 'referencia', maximo=500),
        latitud=coordenada(data, 'latitud', 'lat'),
        longitud=coordenada(data, 'longitud', 'lon'),
    )
    conexion.session.add(nueva)
    conexion.session.commit()
    return {'content': DireccionDto().dump(nueva)}, 201


@bp.route('/cliente/<int:clienteId>/direcciones', methods=['GET'])
@requiereRol(*ROLES_STAFF)
def listarDireccionesCliente(clienteId):
    resultado = conexion.session.query(DireccionModel).filter_by(clienteId=clienteId, activo=True).all()
    return {'content': DireccionDto().dump(resultado, many=True)}, 200
