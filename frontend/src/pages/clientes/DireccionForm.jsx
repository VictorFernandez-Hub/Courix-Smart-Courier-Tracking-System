// Alta y edicion de direcciones de un cliente.
import { useState } from 'react'
import Modal from '../../components/ui/Modal'
import { crearDireccionCliente, editarDireccionCliente } from '../../api'

const VACIA = { etiqueta: '', calle: '', referencia: '', zonaId: '', latitud: '', longitud: '', esPrincipal: false }

export default function DireccionForm({ cliente, direccion, zonas, onClose, onGuardada }) {
  const editando = Boolean(direccion)
  const [form, setForm] = useState(() => (direccion ? {
    ...VACIA,
    ...Object.fromEntries(Object.keys(VACIA).map((k) => [k, direccion[k] ?? VACIA[k]])),
  } : VACIA))
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [ubicando, setUbicando] = useState(false)

  const set = (campo) => (e) => {
    const valor = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [campo]: valor }))
  }

  // Util cuando se registra la direccion estando en el lugar (recojo, visita)
  function usarMiUbicacion() {
    if (!navigator.geolocation) { setError('Este navegador no permite obtener la ubicación'); return }
    setUbicando(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({ ...f, latitud: pos.coords.latitude.toFixed(6), longitud: pos.coords.longitude.toFixed(6) }))
        setUbicando(false)
      },
      () => { setError('No se pudo obtener la ubicación (permiso denegado o sin señal)'); setUbicando(false) },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  async function guardar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const payload = { ...form, zonaId: form.zonaId || null, latitud: form.latitud || null, longitud: form.longitud || null }
      const r = editando
        ? await editarDireccionCliente(direccion.id, payload)
        : await crearDireccionCliente({ ...payload, clienteId: cliente.id })
      onGuardada(r.content)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal title={`${editando ? 'Editar' : 'Nueva'} dirección — ${cliente.nombre}`} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={guardar}>
        <div className="form-2col">
          <div className="field">
            <label htmlFor="dir-etiqueta">Etiqueta</label>
            <input id="dir-etiqueta" maxLength={50} placeholder="Casa, Tienda, Oficina…" value={form.etiqueta} onChange={set('etiqueta')} />
          </div>
          <div className="field">
            <label htmlFor="dir-zona">Zona de reparto</label>
            <select id="dir-zona" value={form.zonaId ?? ''} onChange={set('zonaId')}>
              <option value="">Sin especificar</option>
              {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="dir-calle">Calle / dirección</label>
          <input id="dir-calle" required minLength={3} maxLength={300} placeholder="Av. Arequipa 1234, Dpto 501, Lince"
            value={form.calle} onChange={set('calle')} />
        </div>
        <div className="field">
          <label htmlFor="dir-ref">Referencia</label>
          <input id="dir-ref" maxLength={500} placeholder="Frente al parque, portón verde…" value={form.referencia} onChange={set('referencia')} />
        </div>
        <div className="form-2col">
          <div className="field">
            <label htmlFor="dir-lat">Latitud</label>
            <input id="dir-lat" inputMode="decimal" value={form.latitud ?? ''} onChange={set('latitud')} placeholder="-12.0464" />
          </div>
          <div className="field">
            <label htmlFor="dir-lon">Longitud</label>
            <input id="dir-lon" inputMode="decimal" value={form.longitud ?? ''} onChange={set('longitud')} placeholder="-77.0428" />
          </div>
        </div>
        <button type="button" className="btn-xs" onClick={usarMiUbicacion} disabled={ubicando} style={{ marginBottom: 12 }}>
          {ubicando ? 'Obteniendo ubicación…' : '📍 Usar mi ubicación actual'}
        </button>
        {!direccion?.esPrincipal && (
          <label className="check-line">
            <input type="checkbox" checked={form.esPrincipal} onChange={set('esPrincipal')} />
            <span>Usar como dirección principal (se propone al crear envíos)</span>
          </label>
        )}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? 'Guardando…' : editando ? 'Guardar cambios' : 'Agregar dirección'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
