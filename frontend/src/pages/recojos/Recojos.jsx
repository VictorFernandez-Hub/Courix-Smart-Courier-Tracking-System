import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Modal from '../../components/ui/Modal'
import {
  listarRecojos, crearRecojo, asignarRecojo, reprogramarRecojo, cancelarRecojo,
  listarClientes, listarDireccionesCliente, listarRepartidores,
} from '../../api'

// Paso 1 del proceso: el cliente pide que pasen a recoger sus paquetes.
// Se programa, se asigna a un repartidor de la zona, y lo recogido se admite
// en la agencia (bultos, inspeccion y cobro) desde "Admitir".

const FRANJAS = { manana: 'Mañana (9–13 h)', tarde: 'Tarde (14–18 h)' }
const ESTADOS = {
  pendiente: { texto: 'Por asignar', color: 'var(--st-pendiente)' },
  asignada: { texto: 'Asignado', color: 'var(--st-asignado)' },
  recogida: { texto: 'Recogido: admitir', color: 'var(--st-en_almacen)' },
  admitida: { texto: 'Admitido', color: 'var(--st-entregado)' },
  fallida: { texto: 'No se pudo recoger', color: 'var(--st-no_entregado)' },
  cancelada: { texto: 'Cancelado', color: 'var(--st-cancelado)' },
}
const MOTIVOS = {
  cliente_ausente: 'cliente ausente', direccion_incorrecta: 'dirección incorrecta',
  paquete_no_listo: 'paquete no estaba listo', otro: 'otro motivo',
}
const FILTROS = [
  { id: 'abiertos', label: 'Por atender', estado: 'pendiente,asignada,fallida,recogida' },
  { id: 'historial', label: 'Historial', estado: 'admitida,cancelada' },
]

const hoyLocal = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const FORM_VACIO = { remitenteId: '', direccionId: '', fechaProgramada: hoyLocal(), franja: 'manana', bultosEstimados: '1', pesoEstimadoKg: '', notas: '' }

function Badge({ estado }) {
  const e = ESTADOS[estado] || { texto: estado, color: 'var(--ink-faint)' }
  return <span className="badge" style={{ color: e.color, background: `color-mix(in srgb, ${e.color} 14%, white)` }}>{e.texto}</span>
}

export default function Recojos() {
  const navigate = useNavigate()
  const [filtro, setFiltro] = useState('abiertos')
  const [recojos, setRecojos] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [clientes, setClientes] = useState([])
  const [direcciones, setDirecciones] = useState([])
  const [repartidores, setRepartidores] = useState([])

  const [modal, setModal] = useState(null) // 'nuevo' | { tipo: 'asignar'|'reprogramar', recojo }
  const [form, setForm] = useState(FORM_VACIO)
  const [errorForm, setErrorForm] = useState('')
  const [enviando, setEnviando] = useState(false)

  function cargar() {
    setCargando(true)
    setError('')
    listarRecojos({ estado: FILTROS.find((f) => f.id === filtro).estado })
      .then((r) => setRecojos(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(cargar, [filtro])
  useEffect(() => {
    listarClientes().then((r) => setClientes(r.content)).catch(() => {})
    listarRepartidores().then((r) => setRepartidores(r.content)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!form.remitenteId) { setDirecciones([]); return }
    listarDireccionesCliente(form.remitenteId).then((r) => setDirecciones(r.content)).catch(() => setDirecciones([]))
  }, [form.remitenteId])

  const avisar = (texto) => { setMensaje(texto); setTimeout(() => setMensaje(''), 4000) }
  const cambiar = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }))

  function abrirNuevo() {
    setForm(FORM_VACIO)
    setErrorForm('')
    setModal('nuevo')
  }

  function abrirAccion(tipo, recojo) {
    setErrorForm('')
    setForm({ ...FORM_VACIO, repartidorId: '', fechaProgramada: recojo.fechaProgramada < hoyLocal() ? hoyLocal() : recojo.fechaProgramada, franja: recojo.franja })
    setModal({ tipo, recojo })
  }

  async function guardar(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      let r
      if (modal === 'nuevo') {
        r = await crearRecojo({
          remitenteId: Number(form.remitenteId), direccionId: Number(form.direccionId),
          fechaProgramada: form.fechaProgramada, franja: form.franja,
          bultosEstimados: Number(form.bultosEstimados),
          pesoEstimadoKg: form.pesoEstimadoKg || undefined, notas: form.notas || undefined,
        })
      } else if (modal.tipo === 'asignar') {
        r = await asignarRecojo(modal.recojo.id, Number(form.repartidorId))
      } else {
        r = await reprogramarRecojo(modal.recojo.id, { fechaProgramada: form.fechaProgramada, franja: form.franja })
      }
      setModal(null)
      avisar(r.message)
      cargar()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function cancelar(recojo) {
    const motivo = window.prompt(`¿Por qué se cancela el recojo ${recojo.codigo}?`)
    if (motivo === null) return
    try {
      const r = await cancelarRecojo(recojo.id, motivo || undefined)
      avisar(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  const repartidoresDeZona = (zonaId) => repartidores.filter((r) => r.zonaId === zonaId && r.disponible)

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Recojos a domicilio</h1>
          <p className="page-sub">Programa el recojo, asígnalo a un repartidor de la zona y admite los paquetes cuando lleguen.</p>
        </div>
        <button className="btn btn-primary" onClick={abrirNuevo}>+ Nuevo recojo</button>
      </div>

      <div className="filters">
        {FILTROS.map((f) => (
          <button key={f.id} className={`filter-pill${filtro === f.id ? ' active' : ''}`} onClick={() => setFiltro(f.id)}>{f.label}</button>
        ))}
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? <p className="loading-text">Cargando…</p> : recojos.length === 0 ? (
        <div className="manifest"><div className="empty-state"><h3>Sin recojos</h3><p>Registra uno con "Nuevo recojo".</p></div></div>
      ) : (
        <div className="card-grid">
          {recojos.map((r) => (
            <div className="mini-card" key={r.id}>
              <div className="mini-card-name" style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span>{r.remitente.nombre}</span><Badge estado={r.estado} />
              </div>
              <div className="mini-card-line"><span>Código</span><span className="cell-mono">{r.codigo}</span></div>
              <div className="mini-card-line"><span>Cuándo</span><span>{new Date(r.fechaProgramada + 'T12:00').toLocaleDateString('es-PE', { weekday: 'short', day: 'numeric', month: 'short' })} · {r.franja === 'manana' ? 'Mañana' : 'Tarde'}</span></div>
              <div className="mini-card-line"><span>Dirección</span><span style={{ textAlign: 'right' }}>{r.direccion.calle}</span></div>
              <div className="mini-card-line"><span>Bultos</span><span>{r.bultosRecogidos ?? r.bultosEstimados}{r.bultosRecogidos == null ? ' (estimado)' : ' recogidos'}</span></div>
              {r.bultosAdmitidos != null && (
                <div className="mini-card-line" style={{ color: r.conDiferencia ? 'var(--danger)' : undefined }}
                  title={r.conDiferencia ? 'Se recogió hace más de un día y faltan bultos por admitir: verifica con el repartidor' : ''}>
                  <span>Admitidos</span>
                  <span>{r.bultosAdmitidos} de {r.bultosRecogidos}{r.pendientesDeAdmitir > 0 ? ` · faltan ${r.pendientesDeAdmitir}` : ' ✓'}</span>
                </div>
              )}
              <div className="mini-card-line"><span>Repartidor</span><span>{r.repartidor?.nombre || '—'}</span></div>
              {r.estado === 'fallida' && <div className="mini-card-line" style={{ color: 'var(--danger)' }}><span>Motivo</span><span>{MOTIVOS[r.motivoFallo] || r.motivoFallo}</span></div>}
              {r.envios.length > 0 && <div className="mini-card-line"><span>Envíos</span><span className="cell-mono">{r.envios.join(', ')}</span></div>}
              <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                {['pendiente', 'asignada'].includes(r.estado) && (
                  <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => abrirAccion('asignar', r)}>
                    {r.estado === 'pendiente' ? 'Asignar' : 'Reasignar'}
                  </button>
                )}
                {['recogida', 'admitida'].includes(r.estado) && (
                  <button className="btn btn-primary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => navigate(`/pedidos/nuevo?recojo=${r.id}`)}>
                    {r.estado === 'recogida' ? 'Admitir paquetes' : '+ Otro envío'}
                  </button>
                )}
                {['pendiente', 'asignada', 'fallida'].includes(r.estado) && (
                  <>
                    <button className="btn btn-secondary" style={{ fontSize: 12.5 }} onClick={() => abrirAccion('reprogramar', r)}>Reprogramar</button>
                    <button className="btn-xs danger" onClick={() => cancelar(r)}>Cancelar</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <Modal
          title={modal === 'nuevo' ? 'Nuevo recojo' : modal.tipo === 'asignar' ? `Asignar ${modal.recojo.codigo}` : `Reprogramar ${modal.recojo.codigo}`}
          onClose={() => setModal(null)}
        >
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={guardar}>
            {modal === 'nuevo' && (
              <>
                <div className="field">
                  <label htmlFor="rcCliente">Cliente (remitente)</label>
                  <select id="rcCliente" required value={form.remitenteId}
                    onChange={(e) => setForm((f) => ({ ...f, remitenteId: e.target.value, direccionId: '' }))}>
                    <option value="">Selecciona…</option>
                    {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre} · {c.telefono}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="rcDireccion">Dirección de recojo</label>
                  <select id="rcDireccion" required value={form.direccionId} onChange={cambiar('direccionId')} disabled={!form.remitenteId}>
                    <option value="">{form.remitenteId ? (direcciones.length ? 'Selecciona…' : 'El cliente no tiene direcciones: regístrala en Clientes') : 'Primero elige el cliente'}</option>
                    {direcciones.map((d) => <option key={d.id} value={d.id}>{d.etiqueta ? `${d.etiqueta}: ` : ''}{d.calle}</option>)}
                  </select>
                </div>
              </>
            )}
            {modal?.tipo === 'asignar' ? (
              <div className="field">
                <label htmlFor="rcRepartidor">Repartidor de la zona</label>
                <select id="rcRepartidor" required value={form.repartidorId} onChange={cambiar('repartidorId')}>
                  <option value="">Selecciona…</option>
                  {repartidoresDeZona(modal.recojo.zonaId).map((r) => (
                    <option key={r.id} value={r.id}>Repartidor #{r.id}{r.vehiculo ? ` · ${r.vehiculo}` : ''}{r.placa ? ` (${r.placa})` : ''}</option>
                  ))}
                </select>
                {repartidoresDeZona(modal.recojo.zonaId).length === 0 && (
                  <p className="cell-secondary" style={{ marginTop: 4 }}>No hay repartidores disponibles en la zona de este recojo.</p>
                )}
              </div>
            ) : (
              <div className="form-2col">
                <div className="field">
                  <label htmlFor="rcFecha">Fecha</label>
                  <input id="rcFecha" type="date" required min={hoyLocal()} value={form.fechaProgramada} onChange={cambiar('fechaProgramada')} />
                </div>
                <div className="field">
                  <label htmlFor="rcFranja">Franja</label>
                  <select id="rcFranja" value={form.franja} onChange={cambiar('franja')}>
                    {Object.entries(FRANJAS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                  </select>
                </div>
              </div>
            )}
            {modal === 'nuevo' && (
              <>
                <div className="form-2col">
                  <div className="field">
                    <label htmlFor="rcBultos">Bultos estimados</label>
                    <input id="rcBultos" type="number" min="1" max="50" required value={form.bultosEstimados} onChange={cambiar('bultosEstimados')} />
                  </div>
                  <div className="field">
                    <label htmlFor="rcPeso">Peso estimado (kg) <span className="cell-secondary">(opcional)</span></label>
                    <input id="rcPeso" type="number" min="0.1" step="0.1" value={form.pesoEstimadoKg} onChange={cambiar('pesoEstimadoKg')} />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="rcNotas">Notas para el repartidor <span className="cell-secondary">(opcional)</span></label>
                  <input id="rcNotas" maxLength={500} placeholder="Ej. preguntar por recepción, 2.º piso" value={form.notas} onChange={cambiar('notas')} />
                </div>
              </>
            )}
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
