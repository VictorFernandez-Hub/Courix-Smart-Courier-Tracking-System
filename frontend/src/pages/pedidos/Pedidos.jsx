import { useEffect, useState } from 'react'
import EstadoBadge from '../../components/ui/EstadoBadge'
import Modal from '../../components/ui/Modal'
import {
  listarPedidos, crearPedido, listarEstados, listarClientes,
  listarAlmacenes, listarDireccionesCliente,
  crearCliente, crearDireccionCliente, getUsuario,
  ingresarAlmacen, cambiarEstadoPedido, crearPago, historialPedido,
  crearIncidencia, crearAlmacen, listarZonas, pedidosConPagoRegistrado,
} from '../../api'

const FORM_VACIO = {
  clienteId: '', direccionEntregaId: '', almacenId: '',
  monto: '', pesoKg: '', modalidadPago: 'contra_entrega',
  descripcionProducto: '', notas: '', yaEnAlmacen: false,
}

const CLIENTE_NUEVO_VACIO = { nombre: '', dni: '', telefono: '', email: '' }
const DIRECCION_NUEVA_VACIA = { etiqueta: '', calle: '', referencia: '', zonaId: '' }
const FORM_PAGO_VACIO = { monto: '', metodo: 'efectivo', referencia: '', yaCobrado: true }

const ESTADOS_FINALES = ['entregado', 'devuelto', 'cancelado']

const MODALIDADES = {
  contra_entrega: 'Contra entrega',
  prepagado: 'Prepagado',
  credito: 'Crédito',
}

export default function Pedidos() {
  const usuario = getUsuario()
  const [pedidos, setPedidos] = useState([])
  const [estados, setEstados] = useState([])
  const [clientes, setClientes] = useState([])
  const [almacenes, setAlmacenes] = useState([])
  const [direcciones, setDirecciones] = useState([])
  const [zonas, setZonas] = useState([])
  const [filtroEstado, setFiltroEstado] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [busquedaAplicada, setBusquedaAplicada] = useState('')
  const [pagina, setPagina] = useState(1)
  const [paginacion, setPaginacion] = useState({ totalPaginas: 1, totalRegistros: 0 })
  const [pedidosConPago, setPedidosConPago] = useState(new Set())
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [mostrarModal, setMostrarModal] = useState(false)
  const [modoCliente, setModoCliente] = useState('existente')
  const [form, setForm] = useState(FORM_VACIO)
  const [clienteNuevo, setClienteNuevo] = useState(CLIENTE_NUEVO_VACIO)
  const [direccionNueva, setDireccionNueva] = useState(DIRECCION_NUEVA_VACIA)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')

  const [pedidoHistorial, setPedidoHistorial] = useState(null)
  const [eventosHistorial, setEventosHistorial] = useState([])
  const [cargandoHistorial, setCargandoHistorial] = useState(false)

  const [pedidoIncidencia, setPedidoIncidencia] = useState(null)
  const [formIncidencia, setFormIncidencia] = useState({ tipo: 'reclamo', descripcion: '' })
  const [errorIncidencia, setErrorIncidencia] = useState('')
  const [enviandoIncidencia, setEnviandoIncidencia] = useState(false)

  const [pedidoPago, setPedidoPago] = useState(null)
  const [formPago, setFormPago] = useState(FORM_PAGO_VACIO)
  const [enviandoPago, setEnviandoPago] = useState(false)
  const [errorPago, setErrorPago] = useState('')

  useEffect(() => {
    cargarListasBase()
  }, [])

  // Debounce: espera 400ms sin que el usuario escriba antes de disparar la
  // busqueda real, para no golpear el backend en cada tecla.
  useEffect(() => {
    const temporizador = setTimeout(() => {
      setPagina(1)
      setBusquedaAplicada(busqueda.trim())
    }, 400)
    return () => clearTimeout(temporizador)
  }, [busqueda])

  useEffect(() => {
    cargarPedidos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado, pagina, busquedaAplicada])

  // Auto-refresco: si dos personas tienen la pantalla abierta a la vez (un
  // operador y un repartidor moviendo el mismo pedido, por ejemplo), esto
  // evita que uno se quede viendo datos desactualizados por mucho tiempo
  // sin tener que recargar la pagina a mano.
  useEffect(() => {
    const intervalo = setInterval(cargarPedidos, 45000)
    return () => clearInterval(intervalo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado, pagina, busquedaAplicada])

  function cambiarFiltroEstado(nuevoEstado) {
    setPagina(1)
    setFiltroEstado(nuevoEstado)
  }

  function cargarListasBase() {
    listarEstados().then((r) => setEstados(r.content)).catch(() => {})
    listarClientes().then((r) => setClientes(r.content)).catch(() => {})
    listarAlmacenes().then((r) => setAlmacenes(r.content)).catch(() => {})
    listarZonas().then((r) => setZonas(r.content)).catch(() => {})
  }

  function cargarPedidos() {
    setCargando(true)
    setError('')
    listarPedidos(filtroEstado || undefined, pagina, undefined, busquedaAplicada || undefined)
      .then((r) => {
        setPedidos(r.content)
        setPaginacion(r.paginacion)

        const idsConsultar = r.content.map((p) => p.id)
        if (idsConsultar.length > 0) {
          pedidosConPagoRegistrado(idsConsultar)
            .then((res) => setPedidosConPago(new Set(res.content)))
            .catch(() => {})
        } else {
          setPedidosConPago(new Set())
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function clienteNombre(id) {
    const c = clientes.find((c) => c.id === id)
    return c ? c.nombre : `Cliente #${id}`
  }

  function nombreEstado(estadoId) {
    const e = estados.find((e) => e.id === estadoId)
    return e ? e.nombre : filtroEstado || 'pendiente'
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  function abrirModal() {
    setForm(FORM_VACIO)
    setClienteNuevo(CLIENTE_NUEVO_VACIO)
    setDireccionNueva(DIRECCION_NUEVA_VACIA)
    setDirecciones([])
    setModoCliente('existente')
    setErrorForm('')
    setMostrarModal(true)
  }

  function manejarCambioCliente(e) {
    const clienteId = e.target.value
    setForm((f) => ({ ...f, clienteId, direccionEntregaId: '' }))
    if (clienteId) {
      listarDireccionesCliente(clienteId).then((r) => setDirecciones(r.content)).catch(() => setDirecciones([]))
    } else {
      setDirecciones([])
    }
  }

  async function manejarEnvioForm(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      let clienteId = form.clienteId
      let direccionEntregaId = form.direccionEntregaId

      if (modoCliente === 'nuevo') {
        const resCliente = await crearCliente(clienteNuevo)
        clienteId = resCliente.content.id

        const resDireccion = await crearDireccionCliente({
          ...direccionNueva,
          zonaId: direccionNueva.zonaId ? Number(direccionNueva.zonaId) : undefined,
          clienteId,
        })
        direccionEntregaId = resDireccion.content.id
      }

      // monto vacio -> el backend lo calcula con la tarifa de las zonas.
      await crearPedido({
        clienteId: Number(clienteId),
        direccionEntregaId: Number(direccionEntregaId),
        almacenId: Number(form.almacenId),
        monto: form.monto !== '' ? form.monto : undefined,
        pesoKg: form.pesoKg !== '' ? form.pesoKg : undefined,
        modalidadPago: form.modalidadPago,
        descripcionProducto: form.descripcionProducto || undefined,
        notas: form.notas || undefined,
        yaEnAlmacen: form.yaEnAlmacen,
      })

      setMostrarModal(false)
      cargarListasBase()
      cargarPedidos()
      mostrarMensaje(form.yaEnAlmacen ? 'Pedido registrado y confirmado en almacén' : 'Pedido registrado exitosamente')
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function manejarIngresarAlmacen(p) {
    setError('')
    try {
      const peso = window.prompt('Peso real en kg (déjalo vacío si no cambió):', p.pesoKg ?? '')
      if (peso === null) return
      await ingresarAlmacen(p.id, peso.trim() ? { pesoKg: peso.trim() } : {})
      mostrarMensaje(`Pedido ${p.codigoGuia || '#' + p.id} confirmado en almacén`)
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  async function manejarNoEntregado(p, destino) {
    const texto = destino === 'devuelto'
      ? `¿Confirmas que el paquete ${p.codigoGuia || '#' + p.id} volvió físicamente al almacén?`
      : `¿Reprogramar la entrega del pedido ${p.codigoGuia || '#' + p.id} con el mismo repartidor?`
    if (!window.confirm(texto)) return
    setError('')
    try {
      await cambiarEstadoPedido(p.id, { estado: destino })
      mostrarMensaje(destino === 'devuelto' ? 'Devolución registrada' : 'Entrega reprogramada')
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  async function manejarCancelar(p) {
    if (!window.confirm(`¿Cancelar el pedido #${p.id}? Esta acción quedará registrada en su historial.`)) return
    setError('')
    try {
      await cambiarEstadoPedido(p.id, { estado: 'cancelado', comentario: 'Cancelado desde el panel de administración' })
      mostrarMensaje(`Pedido #${p.id} cancelado`)
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  function abrirModalPago(p) {
    setFormPago({ ...FORM_PAGO_VACIO, monto: String(p.monto) })
    setErrorPago('')
    setPedidoPago(p)
  }

  async function manejarEnvioPago(e) {
    e.preventDefault()
    setErrorPago('')
    setEnviandoPago(true)
    try {
      await crearPago({
        pedidoId: pedidoPago.id,
        monto: formPago.monto,
        metodo: formPago.metodo,
        referencia: formPago.referencia || undefined,
        estadoPago: formPago.yaCobrado ? 'pagado' : 'pendiente',
      })
      setPedidoPago(null)
      mostrarMensaje(`Pago registrado para el pedido #${pedidoPago.id}`)
      cargarPedidos()
    } catch (err) {
      setErrorPago(err.message)
    } finally {
      setEnviandoPago(false)
    }
  }

  function abrirHistorial(p) {
    setPedidoHistorial(p)
    setCargandoHistorial(true)
    historialPedido(p.id)
      .then((r) => setEventosHistorial(r.content))
      .catch(() => setEventosHistorial([]))
      .finally(() => setCargandoHistorial(false))
  }

  function abrirIncidencia(p) {
    setFormIncidencia({ tipo: 'reclamo', descripcion: '' })
    setErrorIncidencia('')
    setPedidoIncidencia(p)
  }

  async function manejarEnvioIncidencia(e) {
    e.preventDefault()
    setErrorIncidencia('')
    setEnviandoIncidencia(true)
    try {
      await crearIncidencia(pedidoIncidencia.id, formIncidencia)
      setPedidoIncidencia(null)
      mostrarMensaje(`Incidencia registrada para el pedido #${pedidoIncidencia.id}`)
    } catch (err) {
      setErrorIncidencia(err.message)
    } finally {
      setEnviandoIncidencia(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Pedidos</h1>
          <p className="page-sub">{pedidos.length} pedido{pedidos.length !== 1 ? 's' : ''} en esta vista</p>
        </div>
        <button className="btn btn-primary" onClick={abrirModal}>+ Nuevo pedido</button>
      </div>

      <div className="filters">
        <button
          className={`filter-pill${filtroEstado === '' ? ' active' : ''}`}
          onClick={() => cambiarFiltroEstado('')}
        >
          Todos
        </button>
        {estados.map((e) => (
          <button
            key={e.id}
            className={`filter-pill${filtroEstado === e.nombre ? ' active' : ''}`}
            onClick={() => cambiarFiltroEstado(e.nombre)}
          >
            {e.nombre.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="field" style={{ maxWidth: 360, marginBottom: 12 }}>
        <input
          type="search"
          placeholder="Buscar por código de guía, cliente o teléfono…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando pedidos…</p>
      ) : pedidos.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>No hay pedidos aquí todavía</h3>
            <p>{busquedaAplicada || filtroEstado
              ? 'Nadie coincide con este filtro o búsqueda. Prueba con otro término.'
              : 'Registra el primero con "Nuevo pedido".'}</p>
          </div>
        </div>
      ) : (
        <div className="manifest">
          <div className="manifest-row head">
            <span>Pedido</span>
            <span>Cliente</span>
            <span>Producto</span>
            <span>Estado</span>
            <span>Monto</span>
            <span>Fecha</span>
            <span>Acciones</span>
          </div>
          {pedidos.map((p) => {
            const nombre = nombreEstado(p.estadoId)
            const esFinal = ESTADOS_FINALES.includes(nombre)
            return (
              <div className="manifest-row" key={p.id}>
                <span className="tag-id" data-label="Pedido">{p.codigoGuia || `#${String(p.id).padStart(5, '0')}`}</span>
                <span className="cell-primary" data-label="Cliente">{clienteNombre(p.clienteId)}</span>
                <div data-label="Producto">
                  <div>{p.descripcionProducto || '—'}</div>
                  {p.notas && <div className="cell-secondary">{p.notas}</div>}
                </div>
                <span data-label="Estado"><EstadoBadge estado={nombre} /></span>
                <div data-label="Monto">
                  <div className="amount">S/ {Number(p.monto).toFixed(2)}</div>
                  <div className="cell-secondary">{MODALIDADES[p.modalidadPago] || p.modalidadPago}</div>
                </div>
                <span className="cell-mono" data-label="Fecha">{new Date(p.fechaCreacion).toLocaleDateString('es-PE')}</span>
                <div className="row-actions">
                  {nombre === 'pendiente' && (
                    <button className="btn-xs" onClick={() => manejarIngresarAlmacen(p)}>Confirmar en almacén</button>
                  )}
                  {nombre === 'no_entregado' && (
                    <>
                      <button className="btn-xs" onClick={() => manejarNoEntregado(p, 'devuelto')}>Recibir devolución</button>
                      <button className="btn-xs" onClick={() => manejarNoEntregado(p, 'asignado')}>Reprogramar</button>
                    </>
                  )}
                  {pedidosConPago.has(p.id) ? (
                    <span className="cell-secondary">✓ Pago registrado</span>
                  ) : nombre !== 'cancelado' && (nombre === 'entregado' || p.modalidadPago !== 'contra_entrega') && (
                    <button className="btn-xs" onClick={() => abrirModalPago(p)}>Registrar pago</button>
                  )}
                  {usuario?.rol === 'admin' && !esFinal && (
                    <button className="btn-xs danger" onClick={() => manejarCancelar(p)}>Cancelar</button>
                  )}
                  <button className="btn-xs" onClick={() => abrirHistorial(p)}>Historial</button>
                  <button className="btn-xs" onClick={() => abrirIncidencia(p)}>Reportar incidencia</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!cargando && pedidos.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
          <span className="cell-secondary">
            Página {paginacion.pagina || pagina} de {paginacion.totalPaginas || 1} · {paginacion.totalRegistros ?? pedidos.length} pedido(s) en total
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-secondary"
              disabled={pagina <= 1}
              onClick={() => setPagina((p) => Math.max(1, p - 1))}
            >
              ← Anterior
            </button>
            <button
              className="btn btn-secondary"
              disabled={pagina >= (paginacion.totalPaginas || 1)}
              onClick={() => setPagina((p) => p + 1)}
            >
              Siguiente →
            </button>
          </div>
        </div>
      )}

      {mostrarModal && (
        <Modal title="Registrar nuevo pedido" onClose={() => setMostrarModal(false)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={manejarEnvioForm}>

            <div className="section-title" style={{ marginTop: 0 }}>Datos del cliente</div>
            <div className="field">
              <div style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
                <button
                  type="button"
                  className={`filter-pill${modoCliente === 'existente' ? ' active' : ''}`}
                  onClick={() => setModoCliente('existente')}
                >
                  Cliente existente
                </button>
                <button
                  type="button"
                  className={`filter-pill${modoCliente === 'nuevo' ? ' active' : ''}`}
                  onClick={() => setModoCliente('nuevo')}
                >
                  Cliente nuevo
                </button>
              </div>
            </div>

            {modoCliente === 'existente' ? (
              <div className="field">
                <label htmlFor="cliente">Selecciona el cliente</label>
                <select id="cliente" value={form.clienteId} onChange={manejarCambioCliente} required>
                  <option value="">Selecciona un cliente</option>
                  {clientes.map((c) => (
                    <option key={c.id} value={c.id}>{c.nombre}</option>
                  ))}
                </select>
              </div>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="nuevoNombre">Nombre completo</label>
                  <input
                    id="nuevoNombre" required
                    value={clienteNuevo.nombre}
                    onChange={(e) => setClienteNuevo((c) => ({ ...c, nombre: e.target.value }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="nuevoDni">DNI</label>
                  <input
                    id="nuevoDni"
                    value={clienteNuevo.dni}
                    onChange={(e) => setClienteNuevo((c) => ({ ...c, dni: e.target.value }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="nuevoTelefono">Teléfono</label>
                  <input
                    id="nuevoTelefono" required
                    value={clienteNuevo.telefono}
                    onChange={(e) => setClienteNuevo((c) => ({ ...c, telefono: e.target.value }))}
                  />
                </div>
              </>
            )}

            <div className="section-title">Dirección de destino</div>
            {modoCliente === 'existente' ? (
              <div className="field">
                <label htmlFor="direccion">Dirección de entrega</label>
                <select
                  id="direccion"
                  value={form.direccionEntregaId}
                  onChange={(e) => setForm((f) => ({ ...f, direccionEntregaId: e.target.value }))}
                  required
                  disabled={!form.clienteId}
                >
                  <option value="">{form.clienteId ? 'Selecciona una dirección' : 'Primero elige un cliente'}</option>
                  {direcciones.map((d) => (
                    <option key={d.id} value={d.id}>{d.etiqueta ? `${d.etiqueta} — ` : ''}{d.calle}</option>
                  ))}
                </select>
              </div>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="nuevaCalle">Calle y número</label>
                  <input
                    id="nuevaCalle" required
                    placeholder="Ej. Jr. Bolívar 456"
                    value={direccionNueva.calle}
                    onChange={(e) => setDireccionNueva((d) => ({ ...d, calle: e.target.value }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="nuevaReferencia">Referencia</label>
                  <input
                    id="nuevaReferencia"
                    placeholder="Ej. Frente al parque"
                    value={direccionNueva.referencia}
                    onChange={(e) => setDireccionNueva((d) => ({ ...d, referencia: e.target.value }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="nuevaZona">Zona de destino</label>
                  <select
                    id="nuevaZona" required
                    value={direccionNueva.zonaId}
                    onChange={(e) => setDireccionNueva((d) => ({ ...d, zonaId: e.target.value }))}
                  >
                    <option value="">Selecciona la zona</option>
                    {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
                  </select>
                </div>
              </>
            )}

            <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input
                id="yaEnAlmacen" type="checkbox"
                style={{ width: 'auto' }}
                checked={form.yaEnAlmacen}
                onChange={(e) => setForm((f) => ({ ...f, yaEnAlmacen: e.target.checked }))}
              />
              <label htmlFor="yaEnAlmacen" style={{ margin: 0 }}>El paquete ya está físicamente en el almacén</label>
            </div>

            <div className="section-title">Dirección de origen</div>
            <div className="field">
              <label htmlFor="almacen">Almacén desde donde sale el envío</label>
              <select
                id="almacen"
                value={form.almacenId}
                onChange={(e) => setForm((f) => ({ ...f, almacenId: e.target.value }))}
                required
              >
                <option value="">Selecciona un almacén</option>
                {almacenes.map((a) => (
                  <option key={a.id} value={a.id}>{a.nombre}</option>
                ))}
              </select>
              {almacenes.length === 0 && (
                <p className="cell-secondary" style={{ marginTop: 4 }}>
                  Todavía no hay almacenes creados. {usuario?.rol === 'admin'
                    ? 'Ve a la sección "Almacenes" del menú para crear el primero.'
                    : 'Pide a un administrador que cree uno en la sección "Almacenes" del menú.'}
                </p>
              )}
            </div>

            <div className="section-title">Detalles del envío</div>
            <div className="field">
              <label htmlFor="descripcion">Descripción del producto</label>
              <input
                id="descripcion"
                placeholder="Ej. Caja mediana - zapatillas talla 40"
                value={form.descripcionProducto}
                onChange={(e) => setForm((f) => ({ ...f, descripcionProducto: e.target.value }))}
              />
            </div>

            <div className="field">
              <label htmlFor="pesoKg">Peso (kg)</label>
              <input
                id="pesoKg" type="number" step="0.01" min="0.01" max="1000"
                value={form.pesoKg}
                onChange={(e) => setForm((f) => ({ ...f, pesoKg: e.target.value }))}
              />
            </div>

            <div className="field">
              <label htmlFor="modalidadPago">Modalidad de pago</label>
              <select
                id="modalidadPago"
                value={form.modalidadPago}
                onChange={(e) => setForm((f) => ({ ...f, modalidadPago: e.target.value }))}
              >
                {Object.entries(MODALIDADES).map(([valor, etiqueta]) => (
                  <option key={valor} value={valor}>{etiqueta}</option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="monto">Monto (S/)</label>
              <input
                id="monto" type="number" step="0.01" min="0"
                placeholder="Vacío = se calcula con la tarifa de la zona"
                value={form.monto}
                onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))}
              />
              <p className="cell-secondary" style={{ marginTop: 4 }}>
                Déjalo vacío para usar la tarifa. Si escribes un precio distinto, queda registrado en la auditoría.
              </p>
            </div>

            <div className="field">
              <label htmlFor="notas">Notas</label>
              <textarea
                id="notas"
                placeholder="Ej. Tocar timbre dos veces"
                value={form.notas}
                onChange={(e) => setForm((f) => ({ ...f, notas: e.target.value }))}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setMostrarModal(false)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : 'Registrar pedido'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pedidoPago && (
        <Modal title={`Registrar pago — Pedido #${pedidoPago.id}`} onClose={() => setPedidoPago(null)}>
          {errorPago && <div className="error-banner">{errorPago}</div>}
          <form onSubmit={manejarEnvioPago}>
            <div className="field">
              <label htmlFor="montoPago">Monto (S/)</label>
              <input
                id="montoPago" type="number" step="0.01" min="0" required
                value={formPago.monto}
                onChange={(e) => setFormPago((f) => ({ ...f, monto: e.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="metodoPago">Método de pago</label>
              <select
                id="metodoPago"
                value={formPago.metodo}
                onChange={(e) => setFormPago((f) => ({ ...f, metodo: e.target.value }))}
              >
                <option value="efectivo">Efectivo</option>
                <option value="yape">Yape</option>
                <option value="plin">Plin</option>
                <option value="tarjeta">Tarjeta</option>
                <option value="transferencia">Transferencia</option>
              </select>
            </div>
            {formPago.metodo !== 'efectivo' && (
              <div className="field">
                <label htmlFor="referenciaPago">N.º de operación</label>
                <input
                  id="referenciaPago" maxLength={60} required={formPago.yaCobrado}
                  value={formPago.referencia}
                  onChange={(e) => setFormPago((f) => ({ ...f, referencia: e.target.value }))}
                />
              </div>
            )}
            <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input
                id="yaCobrado" type="checkbox"
                style={{ width: 'auto' }}
                checked={formPago.yaCobrado}
                onChange={(e) => setFormPago((f) => ({ ...f, yaCobrado: e.target.checked }))}
              />
              <label htmlFor="yaCobrado" style={{ margin: 0 }}>El dinero ya se recibió</label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoPago(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoPago}>
                {enviandoPago ? 'Guardando…' : 'Registrar pago'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pedidoHistorial && (
        <Modal title={`Historial — Pedido #${pedidoHistorial.id}`} onClose={() => setPedidoHistorial(null)}>
          {cargandoHistorial ? (
            <p className="loading-text">Cargando historial…</p>
          ) : eventosHistorial.length === 0 ? (
            <p className="cell-secondary">Sin eventos registrados.</p>
          ) : (
            <div>
              {eventosHistorial.map((ev) => (
                <div className="timeline-item" key={ev.id}>
                  <div className="timeline-dot" />
                  <div>
                    <div className="cell-secondary">{new Date(ev.fecha).toLocaleString('es-PE')}</div>
                    {ev.comentario && <div style={{ marginTop: 2 }}>{ev.comentario}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}

      {pedidoIncidencia && (
        <Modal title={`Reportar incidencia — Pedido #${pedidoIncidencia.id}`} onClose={() => setPedidoIncidencia(null)}>
          {errorIncidencia && <div className="error-banner">{errorIncidencia}</div>}
          <form onSubmit={manejarEnvioIncidencia}>
            <div className="field">
              <label htmlFor="tipoIncidencia">Tipo</label>
              <select
                id="tipoIncidencia"
                value={formIncidencia.tipo}
                onChange={(e) => setFormIncidencia((f) => ({ ...f, tipo: e.target.value }))}
              >
                <option value="reclamo">Reclamo</option>
                <option value="producto_danado">Producto dañado</option>
                <option value="direccion_incorrecta">Dirección incorrecta</option>
                <option value="retraso">Retraso</option>
                <option value="otro">Otro</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="descripcionIncidencia">Descripción</label>
              <textarea
                id="descripcionIncidencia" required
                placeholder="Ej. El cliente reporta que el paquete llegó abierto"
                value={formIncidencia.descripcion}
                onChange={(e) => setFormIncidencia((f) => ({ ...f, descripcion: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoIncidencia(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoIncidencia}>
                {enviandoIncidencia ? 'Guardando…' : 'Reportar'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
