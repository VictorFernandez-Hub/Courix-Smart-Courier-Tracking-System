import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { asignarIncidencia, getUsuario, listarIncidencias, listarUsuarios, marcarIncidenciaEnProceso, resolverIncidencia } from '../../api'

const TIPO_LABEL = {
  reclamo: 'Reclamo',
  producto_danado: 'Producto dañado',
  direccion_incorrecta: 'Dirección incorrecta',
  retraso: 'Retraso',
  faltante: 'Bulto faltante',
  otro: 'Otro',
}

const PRIORIDAD_COLOR = { alta: 'var(--danger)', media: 'var(--st-en_almacen)', baja: 'var(--ink-faint)' }
const fechaHora = (v) => (v ? new Date(v).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'short' }) : '')

const ESTADO_COLOR = {
  abierta: 'var(--st-no_entregado)',
  en_proceso: 'var(--st-en_almacen)',
  resuelta: 'var(--st-entregado)',
}

export default function Incidencias() {
  const [incidencias, setIncidencias] = useState([])
  const [filtro, setFiltro] = useState('')
  const usuario = getUsuario()
  const esAdmin = usuario?.rol === 'admin'
  const [personal, setPersonal] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [incidenciaAResolver, setIncidenciaAResolver] = useState(null)
  const [textoResolucion, setTextoResolucion] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro])
  useEffect(() => {
    if (esAdmin) listarUsuarios().then((r) => setPersonal(r.content.filter((u) => u.activo && u.rol !== 'repartidor'))).catch(() => {})
  }, [esAdmin])

  function cargar() {
    setCargando(true)
    const especial = { mias: filtro === 'mias', vencidas: filtro === 'vencidas' }
    listarIncidencias(['mias', 'vencidas'].includes(filtro) ? 'abierta,en_proceso' : (filtro || undefined), especial)
      .then((r) => setIncidencias(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3000)
  }

  async function manejarEnProceso(id) {
    setError('')
    try {
      await marcarIncidenciaEnProceso(id)
      mostrarMensaje(`Incidencia #${id} marcada en proceso`)
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  async function asignar(inc, responsableId) {
    setError('')
    try {
      const r = await asignarIncidencia(inc.id, { responsableId: Number(responsableId) })
      mostrarMensaje(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  function abrirResolver(incidencia) {
    setTextoResolucion('')
    setIncidenciaAResolver(incidencia)
  }

  async function manejarResolver(e) {
    e.preventDefault()
    setEnviando(true)
    try {
      await resolverIncidencia(incidenciaAResolver.id, textoResolucion)
      setIncidenciaAResolver(null)
      mostrarMensaje(`Incidencia #${incidenciaAResolver.id} resuelta`)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Incidencias</h1>
          <p className="page-sub">Reclamos y problemas reportados en las entregas</p>
        </div>
      </div>

      <div className="filters">
        <button className={`filter-pill${filtro === '' ? ' active' : ''}`} onClick={() => setFiltro('')}>Todas</button>
        <button className={`filter-pill${filtro === 'abierta' ? ' active' : ''}`} onClick={() => setFiltro('abierta')}>Abiertas</button>
        <button className={`filter-pill${filtro === 'en_proceso' ? ' active' : ''}`} onClick={() => setFiltro('en_proceso')}>En proceso</button>
        <button className={`filter-pill${filtro === 'resuelta' ? ' active' : ''}`} onClick={() => setFiltro('resuelta')}>Resueltas</button>
        <button className={`filter-pill${filtro === 'mias' ? ' active' : ''}`} onClick={() => setFiltro('mias')}>Asignadas a mí</button>
        <button className={`filter-pill${filtro === 'vencidas' ? ' active' : ''}`} onClick={() => setFiltro('vencidas')}>Fuera de plazo</button>
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando incidencias…</p>
      ) : incidencias.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>No hay incidencias aquí</h3>
            <p>Se reportan desde la página de Pedidos con el botón "Reportar incidencia".</p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {incidencias.map((inc) => (
            <div key={inc.id} className="mini-card" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div className="mini-card-name">Pedido #{String(inc.pedidoId).padStart(5, '0')} — {TIPO_LABEL[inc.tipo] || inc.tipo}</div>
                  <div className="cell-secondary" style={{ marginTop: 4 }}>{inc.descripcion}</div>
                  <div className="cell-secondary" style={{ marginTop: 6, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ color: PRIORIDAD_COLOR[inc.prioridad], fontWeight: 600 }}>Prioridad {inc.prioridad}</span>
                    <span>Responsable: {inc.responsable || 'sin asignar'}</span>
                    {inc.fechaLimite && inc.estado !== 'resuelta' && (
                      <span style={{ color: inc.vencida ? 'var(--danger)' : undefined, fontWeight: inc.vencida ? 600 : undefined }}>
                        {inc.vencida ? '⚠ Venció' : 'Vence'} {fechaHora(inc.fechaLimite)}
                      </span>
                    )}
                    {inc.compensacion && Number(inc.compensacion) > 0 && <span>Compensado: S/ {Number(inc.compensacion).toFixed(2)}</span>}
                  </div>
                  {inc.resolucion && (
                    <div className="cell-secondary" style={{ marginTop: 6, fontStyle: 'italic' }}>
                      Resolución: {inc.resolucion}
                    </div>
                  )}
                </div>
                <span className="badge" style={{ color: ESTADO_COLOR[inc.estado], background: `color-mix(in srgb, ${ESTADO_COLOR[inc.estado]} 14%, white)`, whiteSpace: 'nowrap' }}>
                  {inc.estado.replace('_', ' ')}
                </span>
              </div>
              {inc.estado !== 'resuelta' && (
                <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                  {inc.estado === 'abierta' && !inc.responsableId && (
                    <button className="btn-xs" onClick={() => manejarEnProceso(inc.id)}>Tomarla</button>
                  )}
                  {esAdmin && (
                    <select className="btn-xs" aria-label="Asignar responsable" value={inc.responsableId || ''}
                      onChange={(e) => e.target.value && asignar(inc, e.target.value)}>
                      <option value="">Asignar a…</option>
                      {personal.map((u) => <option key={u.id} value={u.id}>{u.nombre}</option>)}
                    </select>
                  )}
                  <button className="btn-xs" style={{ color: 'var(--st-entregado)', borderColor: 'var(--st-entregado)' }} onClick={() => abrirResolver(inc)}>
                    Resolver
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {incidenciaAResolver && (
        <Modal title={`Resolver incidencia #${incidenciaAResolver.id}`} onClose={() => setIncidenciaAResolver(null)}>
          <form onSubmit={manejarResolver}>
            <div className="field">
              <label htmlFor="resolucion">¿Cómo se resolvió?</label>
              <textarea
                id="resolucion" required
                placeholder="Ej. Se coordinó reemplazo del producto sin costo adicional"
                value={textoResolucion}
                onChange={(e) => setTextoResolucion(e.target.value)}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setIncidenciaAResolver(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : 'Marcar como resuelta'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
