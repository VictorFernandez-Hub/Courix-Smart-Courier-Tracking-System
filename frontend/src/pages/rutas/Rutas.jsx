import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import EstadoBadge from '../../components/ui/EstadoBadge'
import {
  listarRutas, detalleRuta, listarRepartidores, listarZonas,
  crearRuta, listarPedidosDisponibles, agregarPedidoARuta, cambiarEstadoPedido, entregarYCobrar,
} from '../../api'

const ESTADO_RUTA_LABEL = {
  planificada: 'Planificada',
  en_curso: 'En curso',
  completada: 'Completada',
  cancelada: 'Cancelada',
}

// Que boton(es) mostrar segun el estado actual del pedido. "asignado" salta
// directo a "en_camino" (ya no exige el paso intermedio de "recogido").
function accionesDisponibles(estado) {
  switch (estado) {
    case 'asignado':
      return [{ label: 'Salir a entregar', destino: 'en_camino' }]
    case 'recogido': // compatibilidad con pedidos antiguos
      return [{ label: 'Salir a entregar', destino: 'en_camino' }]
    case 'no_entregado':
      return [{ label: 'Reintentar', destino: 'asignado' }]
    default:
      return []
  }
}

export default function Rutas() {
  const [rutas, setRutas] = useState([])
  const [repartidores, setRepartidores] = useState([])
  const [zonas, setZonas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [rutaSeleccionada, setRutaSeleccionada] = useState(null)
  const [detalle, setDetalle] = useState(null)
  const [pool, setPool] = useState([])
  const [cargandoDetalle, setCargandoDetalle] = useState(false)
  const [procesando, setProcesando] = useState(false)

  const [mostrarModalCrear, setMostrarModalCrear] = useState(false)
  const [repartidorNuevaRuta, setRepartidorNuevaRuta] = useState('')
  const [errorCrear, setErrorCrear] = useState('')
  const [creando, setCreando] = useState(false)

  const [pedidoACobrar, setPedidoACobrar] = useState(null)
  const [formCobro, setFormCobro] = useState({ monto: '', metodo: 'efectivo', foto: null })
  const [errorCobro, setErrorCobro] = useState('')

  useEffect(() => {
    cargarTodo()
  }, [])

  function cargarTodo() {
    setCargando(true)
    Promise.all([listarRutas(), listarRepartidores(), listarZonas()])
      .then(([resRutas, resRepartidores, resZonas]) => {
        setRutas(resRutas.content)
        setRepartidores(resRepartidores.content)
        setZonas(resZonas.content)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  function nombreRepartidor(repartidorId) {
    const r = repartidores.find((r) => r.id === repartidorId)
    return r ? `Repartidor #${r.id} (${r.telefono || 'sin teléfono'})` : `Repartidor #${repartidorId}`
  }

  function nombreZona(zonaId) {
    const z = zonas.find((z) => z.id === zonaId)
    return z ? z.nombre : `Zona #${zonaId}`
  }

  function abrirDetalle(ruta) {
    setRutaSeleccionada(ruta)
    cargarDetalle(ruta)
  }

  function cargarDetalle(ruta) {
    setCargandoDetalle(true)
    detalleRuta(ruta.id)
      .then((r) => {
        setDetalle(r.content)
        return listarPedidosDisponibles(r.content.zonaId)
      })
      .then((r) => setPool(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargandoDetalle(false))
  }

  async function manejarCrearRuta(e) {
    e.preventDefault()
    setErrorCrear('')
    setCreando(true)
    try {
      await crearRuta(Number(repartidorNuevaRuta))
      setMostrarModalCrear(false)
      setRepartidorNuevaRuta('')
      cargarTodo()
      mostrarMensaje('Ruta creada exitosamente')
    } catch (err) {
      setErrorCrear(err.message)
    } finally {
      setCreando(false)
    }
  }

  async function manejarAgregarPedido(pedidoId) {
    setProcesando(true)
    setError('')
    try {
      await agregarPedidoARuta(rutaSeleccionada.id, pedidoId)
      cargarDetalle(rutaSeleccionada)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarCambioEstado(pedidoId, nuevoEstado) {
    setProcesando(true)
    setError('')
    try {
      await cambiarEstadoPedido(pedidoId, { estado: nuevoEstado })
      cargarDetalle(rutaSeleccionada)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  function abrirCobro(pedido) {
    setFormCobro({ monto: pedido.monto, metodo: 'efectivo', foto: null })
    setErrorCobro('')
    setPedidoACobrar(pedido)
  }

  function manejarSeleccionFoto(e) {
    const archivo = e.target.files?.[0]
    if (!archivo) return
    const lector = new FileReader()
    lector.onload = () => setFormCobro((f) => ({ ...f, foto: lector.result }))
    lector.readAsDataURL(archivo)
  }

  async function manejarEntregarYCobrar(e) {
    e.preventDefault()
    setErrorCobro('')
    setProcesando(true)
    try {
      await entregarYCobrar(pedidoACobrar.pedidoId, {
        monto: Number(formCobro.monto),
        metodo: formCobro.metodo,
        evidenciaEntrega: formCobro.foto || undefined,
      })
      setPedidoACobrar(null)
      cargarDetalle(rutaSeleccionada)
    } catch (err) {
      setErrorCobro(err.message)
    } finally {
      setProcesando(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Rutas</h1>
          <p className="page-sub">{rutas.length} ruta{rutas.length !== 1 ? 's' : ''} registrada{rutas.length !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setErrorCrear(''); setRepartidorNuevaRuta(''); setMostrarModalCrear(true) }}>
          + Crear ruta
        </button>
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando rutas…</p>
      ) : rutas.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>Todavía no hay rutas creadas</h3>
            <p>Créala con "+ Crear ruta", o espera a que un repartidor cree la suya desde su celular.</p>
          </div>
        </div>
      ) : (
        <div className="card-grid">
          {rutas.map((r) => (
            <div className="mini-card" key={r.id}>
              <div className="mini-card-name cell-mono">{r.codigo}</div>
              <div className="mini-card-line"><span>Estado</span><span>{ESTADO_RUTA_LABEL[r.estado] || r.estado}</span></div>
              <div className="mini-card-line"><span>Repartidor</span><span className="cell-mono">#{r.repartidorId}</span></div>
              <div className="mini-card-line"><span>Fecha</span><span className="cell-mono">{new Date(r.fecha).toLocaleDateString('es-PE')}</span></div>
              <button className="btn btn-secondary btn-block" style={{ marginTop: 10, fontSize: 12.5 }} onClick={() => abrirDetalle(r)}>
                Ver y gestionar pedidos
              </button>
            </div>
          ))}
        </div>
      )}

      {mostrarModalCrear && (
        <Modal title="Crear ruta manualmente" onClose={() => setMostrarModalCrear(false)}>
          {errorCrear && <div className="error-banner">{errorCrear}</div>}
          {repartidores.length === 0 ? (
            <p className="cell-secondary">No hay repartidores creados. Ve a Configuración para crear uno primero.</p>
          ) : (
            <form onSubmit={manejarCrearRuta}>
              <div className="field">
                <label htmlFor="repartidorRuta">Repartidor</label>
                <select id="repartidorRuta" required value={repartidorNuevaRuta}
                  onChange={(e) => setRepartidorNuevaRuta(e.target.value)}>
                  <option value="">Selecciona un repartidor</option>
                  {repartidores.map((r) => (
                    <option key={r.id} value={r.id}>
                      Repartidor #{r.id} — {r.telefono || 'sin teléfono'} ({nombreZona(r.zonaId)}){!r.disponible ? ' — no disponible' : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setMostrarModalCrear(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={creando}>
                  {creando ? 'Creando…' : 'Crear ruta'}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}

      {rutaSeleccionada && (
        <Modal title={`Ruta ${rutaSeleccionada.codigo}`} onClose={() => setRutaSeleccionada(null)}>
          {cargandoDetalle ? (
            <p className="loading-text">Cargando detalle…</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <p className="cell-secondary">Asignada a: {nombreRepartidor(detalle?.repartidorId)}</p>

              {(!detalle || detalle.pedidos.length === 0) ? (
                <p className="cell-secondary">Esta ruta todavía no tiene pedidos asignados.</p>
              ) : (
                detalle.pedidos.map((p) => (
                  <div key={p.pedidoId} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <span className="tag-id">#{String(p.pedidoId).padStart(5, '0')}</span>
                      <EstadoBadge estado={p.estado} />
                    </div>
                    <div className="cell-primary">{p.cliente?.nombre}</div>
                    <div className="cell-secondary">{p.direccionEntrega?.calle}</div>
                    <div className="cell-secondary">{p.descripcionProducto || 'Sin descripción'} · S/ {Number(p.monto).toFixed(2)}</div>
                    {accionesDisponibles(p.estado).length > 0 && (
                      <div className="row-actions" style={{ marginTop: 8 }}>
                        {accionesDisponibles(p.estado).map((accion) => (
                          <button
                            key={accion.destino}
                            className={`btn-xs ${accion.clase || ''}`}
                            disabled={procesando}
                            onClick={() => manejarCambioEstado(p.pedidoId, accion.destino)}
                          >
                            {accion.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {p.estado === 'en_camino' && (
                      <div className="row-actions" style={{ marginTop: 8 }}>
                        <button className="btn-xs" style={{ color: 'var(--st-entregado)', borderColor: 'var(--st-entregado)' }} disabled={procesando} onClick={() => abrirCobro(p)}>
                          Entregar y cobrar
                        </button>
                        <button className="btn-xs danger" disabled={procesando} onClick={() => manejarCambioEstado(p.pedidoId, 'no_entregado')}>
                          No entregado
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}

              <div className="section-title">Pedidos disponibles en esta zona</div>
              {pool.length === 0 ? (
                <p className="cell-secondary">No hay pedidos esperando en esta zona.</p>
              ) : (
                pool.map((p) => (
                  <div className="pool-item" key={p.id}>
                    <div>
                      <div className="cell-primary">{p.descripcionProducto || `Pedido #${p.id}`}</div>
                      <div className="cell-secondary">S/ {Number(p.monto).toFixed(2)}</div>
                    </div>
                    <button className="btn btn-secondary" disabled={procesando} onClick={() => manejarAgregarPedido(p.id)}>
                      + Agregar
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </Modal>
      )}

      {pedidoACobrar && (
        <Modal title={`Entregar y cobrar — Pedido #${pedidoACobrar.pedidoId}`} onClose={() => setPedidoACobrar(null)}>
          {errorCobro && <div className="error-banner">{errorCobro}</div>}
          <form onSubmit={manejarEntregarYCobrar}>
            <div className="field">
              <label htmlFor="montoCobroRuta">Monto cobrado (S/)</label>
              <input
                id="montoCobroRuta" type="number" step="0.01" min="0" required
                value={formCobro.monto}
                onChange={(e) => setFormCobro((f) => ({ ...f, monto: e.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="metodoCobroRuta">Método de pago</label>
              <select
                id="metodoCobroRuta"
                value={formCobro.metodo}
                onChange={(e) => setFormCobro((f) => ({ ...f, metodo: e.target.value }))}
              >
                <option value="efectivo">Efectivo</option>
                <option value="yape">Yape</option>
                <option value="plin">Plin</option>
                <option value="tarjeta">Tarjeta</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="fotoEvidenciaRuta">Foto de evidencia (opcional)</label>
              <input id="fotoEvidenciaRuta" type="file" accept="image/*" onChange={manejarSeleccionFoto} />
              {formCobro.foto && <p className="cell-secondary" style={{ marginTop: 4 }}>✓ Foto lista para adjuntar</p>}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoACobrar(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={procesando}>
                {procesando ? 'Guardando…' : 'Confirmar entrega'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
