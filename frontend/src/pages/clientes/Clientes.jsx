import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import EstadoBadge from '../../components/ui/EstadoBadge'
import {
  listarClientes, crearCliente, listarZonas,
  listarDireccionesCliente, crearDireccionCliente,
  listarPedidos, listarEstados,
} from '../../api'

const FORM_CLIENTE_VACIO = { nombre: '', dni: '', telefono: '', email: '' }
const FORM_DIRECCION_VACIO = { etiqueta: '', calle: '', referencia: '', zonaId: '' }

export default function Clientes() {
  const [clientes, setClientes] = useState([])
  const [zonas, setZonas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  const [mostrarModalCliente, setMostrarModalCliente] = useState(false)
  const [formCliente, setFormCliente] = useState(FORM_CLIENTE_VACIO)
  const [enviandoCliente, setEnviandoCliente] = useState(false)
  const [errorCliente, setErrorCliente] = useState('')

  const [clienteDireccion, setClienteDireccion] = useState(null) // cliente sobre el que se agrega direccion
  const [direccionesVistas, setDireccionesVistas] = useState({}) // { clienteId: [direcciones] }
  const [formDireccion, setFormDireccion] = useState(FORM_DIRECCION_VACIO)
  const [enviandoDireccion, setEnviandoDireccion] = useState(false)

  const [clienteHistorial, setClienteHistorial] = useState(null)
  const [pedidosHistorial, setPedidosHistorial] = useState([])
  const [estados, setEstados] = useState([])
  const [cargandoHistorial, setCargandoHistorial] = useState(false)

  useEffect(() => {
    cargarClientes()
    listarZonas().then((r) => setZonas(r.content)).catch(() => {})
    listarEstados().then((r) => setEstados(r.content)).catch(() => {})
  }, [])

  function cargarClientes() {
    setCargando(true)
    listarClientes()
      .then((r) => setClientes(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function abrirModalCliente() {
    setFormCliente(FORM_CLIENTE_VACIO)
    setErrorCliente('')
    setMostrarModalCliente(true)
  }

  async function manejarEnvioCliente(e) {
    e.preventDefault()
    setErrorCliente('')
    setEnviandoCliente(true)
    try {
      await crearCliente(formCliente)
      setMostrarModalCliente(false)
      cargarClientes()
    } catch (err) {
      setErrorCliente(err.message)
    } finally {
      setEnviandoCliente(false)
    }
  }

  function verDirecciones(cliente) {
    if (direccionesVistas[cliente.id]) {
      setDireccionesVistas((d) => {
        const copia = { ...d }
        delete copia[cliente.id]
        return copia
      })
      return
    }
    listarDireccionesCliente(cliente.id).then((r) => {
      setDireccionesVistas((d) => ({ ...d, [cliente.id]: r.content }))
    })
  }

  function abrirModalDireccion(cliente) {
    setFormDireccion(FORM_DIRECCION_VACIO)
    setClienteDireccion(cliente)
  }

  function nombreEstado(estadoId) {
    const e = estados.find((e) => e.id === estadoId)
    return e ? e.nombre : 'pendiente'
  }

  function abrirHistorial(cliente) {
    setClienteHistorial(cliente)
    setCargandoHistorial(true)
    listarPedidos(undefined, 1, cliente.id)
      .then((r) => setPedidosHistorial(r.content))
      .catch(() => setPedidosHistorial([]))
      .finally(() => setCargandoHistorial(false))
  }

  async function manejarEnvioDireccion(e) {
    e.preventDefault()
    setEnviandoDireccion(true)
    try {
      await crearDireccionCliente({ ...formDireccion, clienteId: clienteDireccion.id })
      setClienteDireccion(null)
      delete direccionesVistas[clienteDireccion.id]
      verDirecciones(clienteDireccion)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviandoDireccion(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Clientes</h1>
          <p className="page-sub">{clientes.length} cliente{clientes.length !== 1 ? 's' : ''} registrado{clientes.length !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn btn-primary" onClick={abrirModalCliente}>+ Nuevo cliente</button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando clientes…</p>
      ) : clientes.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>Todavía no hay clientes</h3>
            <p>Registra el primero con "Nuevo cliente".</p>
          </div>
        </div>
      ) : (
        <div className="card-grid">
          {clientes.map((c) => (
            <div className="mini-card" key={c.id}>
              <div className="mini-card-name">{c.nombre}</div>
              <div className="mini-card-line"><span>DNI</span><span className="cell-mono">{c.dni || '—'}</span></div>
              <div className="mini-card-line"><span>Teléfono</span><span className="cell-mono">{c.telefono}</span></div>

              {direccionesVistas[c.id] && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                  {direccionesVistas[c.id].length === 0 ? (
                    <p className="cell-secondary">Sin direcciones registradas.</p>
                  ) : (
                    direccionesVistas[c.id].map((d) => (
                      <div key={d.id} className="cell-secondary" style={{ marginBottom: 4 }}>
                        {d.etiqueta ? `${d.etiqueta}: ` : ''}{d.calle}
                      </div>
                    ))
                  )}
                </div>
              )}

              <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => verDirecciones(c)}>
                  {direccionesVistas[c.id] ? 'Ocultar' : 'Ver'} direcciones
                </button>
                <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => abrirModalDireccion(c)}>
                  + Dirección
                </button>
              </div>
              <button className="btn btn-secondary btn-block" style={{ fontSize: 12.5, marginTop: 6 }} onClick={() => abrirHistorial(c)}>
                Ver historial de pedidos
              </button>
            </div>
          ))}
        </div>
      )}

      {mostrarModalCliente && (
        <Modal title="Nuevo cliente" onClose={() => setMostrarModalCliente(false)}>
          {errorCliente && <div className="error-banner">{errorCliente}</div>}
          <form onSubmit={manejarEnvioCliente}>
            <div className="field">
              <label htmlFor="nombre">Nombre completo</label>
              <input id="nombre" required value={formCliente.nombre}
                onChange={(e) => setFormCliente((f) => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="dni">DNI</label>
              <input id="dni" value={formCliente.dni}
                onChange={(e) => setFormCliente((f) => ({ ...f, dni: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="telefono">Teléfono</label>
              <input id="telefono" required value={formCliente.telefono}
                onChange={(e) => setFormCliente((f) => ({ ...f, telefono: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="clienteEmail">Correo (opcional)</label>
              <input id="clienteEmail" type="email" value={formCliente.email}
                onChange={(e) => setFormCliente((f) => ({ ...f, email: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setMostrarModalCliente(false)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoCliente}>
                {enviandoCliente ? 'Guardando…' : 'Registrar cliente'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {clienteDireccion && (
        <Modal title={`Nueva dirección — ${clienteDireccion.nombre}`} onClose={() => setClienteDireccion(null)}>
          <form onSubmit={manejarEnvioDireccion}>
            <div className="field">
              <label htmlFor="etiqueta">Etiqueta</label>
              <input id="etiqueta" placeholder="Ej. Casa, Trabajo" value={formDireccion.etiqueta}
                onChange={(e) => setFormDireccion((f) => ({ ...f, etiqueta: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="calle">Calle / dirección</label>
              <input id="calle" required value={formDireccion.calle}
                onChange={(e) => setFormDireccion((f) => ({ ...f, calle: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="referencia">Referencia</label>
              <input id="referencia" value={formDireccion.referencia}
                onChange={(e) => setFormDireccion((f) => ({ ...f, referencia: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="zona">Zona</label>
              <select id="zona" value={formDireccion.zonaId}
                onChange={(e) => setFormDireccion((f) => ({ ...f, zonaId: e.target.value }))}>
                <option value="">Sin especificar</option>
                {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
              </select>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setClienteDireccion(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoDireccion}>
                {enviandoDireccion ? 'Guardando…' : 'Agregar dirección'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {clienteHistorial && (
        <Modal title={`Historial — ${clienteHistorial.nombre}`} onClose={() => setClienteHistorial(null)}>
          {cargandoHistorial ? (
            <p className="loading-text">Cargando historial…</p>
          ) : pedidosHistorial.length === 0 ? (
            <p className="cell-secondary">Este cliente todavía no tiene pedidos registrados.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {pedidosHistorial.map((p) => (
                <div key={p.id} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className="tag-id">#{String(p.id).padStart(5, '0')}</span>
                    <EstadoBadge estado={nombreEstado(p.estadoId)} />
                  </div>
                  <div className="cell-primary" style={{ marginBottom: 2 }}>{p.descripcionProducto || 'Sin descripción'}</div>
                  <div className="cell-secondary">
                    S/ {Number(p.monto).toFixed(2)} · {new Date(p.fechaCreacion).toLocaleDateString('es-PE')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
