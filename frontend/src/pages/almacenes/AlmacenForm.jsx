// Alta y edicion de una agencia (solo administradores).
import { useState } from 'react'
import Modal from '../../components/ui/Modal'
import { crearAlmacen, editarAlmacen } from '../../api'

const VACIO = {
  nombre: '', codigo: '', zonaId: '', calle: '', referencia: '', telefono: '', email: '',
  horario: '', responsableId: '', capacidadBultos: '', latitud: '', longitud: '',
}

export default function AlmacenForm({ almacen, zonas, usuarios, onClose, onGuardado }) {
  const editando = Boolean(almacen)
  const [form, setForm] = useState(() => (almacen
    ? Object.fromEntries(Object.keys(VACIO).map((k) => [k, almacen[k] ?? '']))
    : VACIO))
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [ubicando, setUbicando] = useState(false)

  const set = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }))

  // Solo personal activo de esta agencia (o sin agencia) puede ser responsable
  const candidatos = usuarios.filter((u) => u.activo && (u.rol === 'admin' ||
    (u.rol === 'operador' && (!u.agenciaId || u.agenciaId === almacen?.id))))

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
    if ((form.latitud === '') !== (form.longitud === '')) { setError('Indica latitud y longitud juntas (o ninguna)'); return }
    setEnviando(true)
    const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() : v]))
    for (const k of ['zonaId', 'responsableId', 'capacidadBultos', 'latitud', 'longitud']) {
      payload[k] = payload[k] === '' ? null : Number(payload[k])
    }
    if (!payload.codigo) delete payload.codigo // se genera uno provisional
    try {
      const r = editando ? await editarAlmacen(almacen.id, payload) : await crearAlmacen(payload)
      onGuardado(r.content, editando ? 'Agencia actualizada' : `Agencia "${r.content.nombre}" creada (código ${r.content.codigo})`)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal title={editando ? `Editar agencia — ${almacen.nombre}` : 'Nueva agencia'} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={guardar}>
        <div className="form-2col alm-nombre-codigo">
          <div className="field">
            <label htmlFor="alm-nombre">Nombre</label>
            <input id="alm-nombre" required minLength={3} maxLength={100} placeholder="Ej. Agencia Lima Centro"
              value={form.nombre} onChange={set('nombre')} />
          </div>
          <div className="field">
            <label htmlFor="alm-codigo">Código</label>
            <input id="alm-codigo" className="cell-mono" maxLength={10} placeholder={editando ? '' : 'Automático'}
              required={editando} pattern="[A-Za-z0-9\-]{2,10}" title="2 a 10 letras, números o guiones"
              value={form.codigo} onChange={(e) => setForm((f) => ({ ...f, codigo: e.target.value.toUpperCase().replace(/\s/g, '') }))} />
          </div>
        </div>
        <p className="cli-hint">El código sale en etiquetas y manifiestos: corto y fácil de leer (ej. LIM01, ARE-02).</p>

        <div className="field">
          <label htmlFor="alm-zona">Zona que atiende</label>
          <select id="alm-zona" required value={form.zonaId} onChange={set('zonaId')}>
            <option value="">Selecciona una zona</option>
            {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
          </select>
          {zonas.length === 0 && <p className="cli-hint">Todavía no hay zonas: créalas primero en Configuración.</p>}
        </div>
        <div className="field">
          <label htmlFor="alm-calle">Dirección</label>
          <input id="alm-calle" required minLength={3} maxLength={300} value={form.calle} onChange={set('calle')} />
        </div>
        <div className="field">
          <label htmlFor="alm-ref">Referencia</label>
          <input id="alm-ref" maxLength={300} placeholder="Frente al mercado, 2do piso…" value={form.referencia} onChange={set('referencia')} />
        </div>

        <div className="form-2col">
          <div className="field">
            <label htmlFor="alm-tel">Teléfono</label>
            <input id="alm-tel" inputMode="tel" value={form.telefono} onChange={set('telefono')} />
          </div>
          <div className="field">
            <label htmlFor="alm-email">Correo</label>
            <input id="alm-email" type="email" value={form.email} onChange={set('email')} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="alm-horario">Horario de atención</label>
          <input id="alm-horario" maxLength={200} placeholder="Lun–Vie 8:00–19:00 · Sáb 9:00–13:00" value={form.horario} onChange={set('horario')} />
        </div>

        <div className="form-2col">
          <div className="field">
            <label htmlFor="alm-resp">Responsable</label>
            <select id="alm-resp" value={form.responsableId} onChange={set('responsableId')}>
              <option value="">Sin asignar</option>
              {candidatos.map((u) => <option key={u.id} value={u.id}>{u.nombre} ({u.rol})</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="alm-cap">Capacidad (bultos)</label>
            <input id="alm-cap" type="number" min={1} inputMode="numeric" placeholder="Sin límite"
              value={form.capacidadBultos} onChange={set('capacidadBultos')} />
          </div>
        </div>

        <div className="form-2col">
          <div className="field">
            <label htmlFor="alm-lat">Latitud</label>
            <input id="alm-lat" inputMode="decimal" placeholder="-12.0464" value={form.latitud} onChange={set('latitud')} />
          </div>
          <div className="field">
            <label htmlFor="alm-lon">Longitud</label>
            <input id="alm-lon" inputMode="decimal" placeholder="-77.0428" value={form.longitud} onChange={set('longitud')} />
          </div>
        </div>
        <button type="button" className="btn-xs" onClick={usarMiUbicacion} disabled={ubicando} style={{ marginBottom: 12 }}>
          {ubicando ? 'Obteniendo ubicación…' : '📍 Usar mi ubicación actual'}
        </button>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear agencia'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
