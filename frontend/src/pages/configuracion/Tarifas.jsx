import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { listarTarifas, crearTarifa, editarTarifa, eliminarTarifa } from '../../api'

// Tarifario: precio entre dos zonas por tipo de servicio.
//   flete = max(precio minimo, base + kg facturables x precio/kg)
//   total = flete + seguro (% del valor declarado, configurable en el backend)

const SERVICIOS = { estandar: 'Estándar', express: 'Express' }
const FORM_VACIO = {
  zonaOrigenId: '', zonaDestinoId: '', tipoServicio: 'estandar',
  precioBase: '', precioPorKg: '', precioMinimo: '', diasEntrega: '',
}

export default function Tarifas({ zonas, onMensaje }) {
  const [tarifas, setTarifas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [modal, setModal] = useState(null) // null | { id?: number }
  const [form, setForm] = useState(FORM_VACIO)
  const [errorForm, setErrorForm] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = () => {
    setCargando(true)
    listarTarifas()
      .then((r) => setTarifas(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }
  useEffect(cargar, [])

  const nombreZona = (id) => zonas.find((z) => z.id === id)?.nombre || `Zona #${id}`
  const cambiar = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }))

  function abrirCrear() {
    setForm(FORM_VACIO)
    setErrorForm('')
    setModal({})
  }

  function abrirEditar(t) {
    setForm({
      zonaOrigenId: t.zonaOrigenId, zonaDestinoId: t.zonaDestinoId, tipoServicio: t.tipoServicio,
      precioBase: t.precioBase, precioPorKg: t.precioPorKg, precioMinimo: t.precioMinimo,
      diasEntrega: t.diasEntrega ?? '',
    })
    setErrorForm('')
    setModal({ id: t.id })
  }

  async function guardar(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    const precios = {
      precioBase: form.precioBase,
      precioPorKg: form.precioPorKg,
      precioMinimo: form.precioMinimo || '0',
      diasEntrega: form.diasEntrega === '' ? null : Number(form.diasEntrega),
    }
    try {
      if (modal.id) {
        await editarTarifa(modal.id, precios)
        onMensaje('Tarifa actualizada')
      } else {
        await crearTarifa({
          ...precios, zonaOrigenId: Number(form.zonaOrigenId), zonaDestinoId: Number(form.zonaDestinoId),
          tipoServicio: form.tipoServicio,
        })
        onMensaje('Tarifa creada')
      }
      setModal(null)
      cargar()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function eliminar(t) {
    if (!window.confirm(`¿Desactivar la tarifa ${SERVICIOS[t.tipoServicio]} ${nombreZona(t.zonaOrigenId)} → ${nombreZona(t.zonaDestinoId)}?`)) return
    try {
      await eliminarTarifa(t.id)
      onMensaje('Tarifa desactivada')
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <button className="btn btn-primary" style={{ marginBottom: 12 }} onClick={abrirCrear}>+ Nueva tarifa</button>
      <p className="cell-secondary" style={{ marginBottom: 16 }}>
        Flete = el mayor entre el precio mínimo y (base + kg facturables × precio por kg). El seguro sobre el valor
        declarado se suma aparte.
      </p>
      {error && <div className="error-banner">{error}</div>}
      {cargando ? <p className="loading-text">Cargando…</p> : tarifas.length === 0 ? (
        <div className="manifest"><div className="empty-state"><h3>Sin tarifas</h3>
          <p>Sin tarifas, cada envío necesita un precio manual. Crea al menos una por cada ruta que atiendes.</p></div></div>
      ) : (
        <div className="card-grid">
          {tarifas.map((t) => (
            <div className="mini-card" key={t.id}>
              <div className="mini-card-name">{nombreZona(t.zonaOrigenId)} → {nombreZona(t.zonaDestinoId)}</div>
              <div className="mini-card-line"><span>Servicio</span><strong>{SERVICIOS[t.tipoServicio] || t.tipoServicio}</strong></div>
              <div className="mini-card-line"><span>Base</span><span className="cell-mono">S/ {t.precioBase}</span></div>
              <div className="mini-card-line"><span>Por kg</span><span className="cell-mono">S/ {t.precioPorKg}</span></div>
              <div className="mini-card-line"><span>Mínimo</span><span className="cell-mono">S/ {t.precioMinimo}</span></div>
              <div className="mini-card-line"><span>Plazo</span><span>{t.diasEntrega == null ? '—' : t.diasEntrega === 0 ? 'Mismo día' : `${t.diasEntrega} día(s)`}</span></div>
              <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => abrirEditar(t)}>Editar</button>
                <button className="btn btn-secondary" style={{ fontSize: 12.5 }} onClick={() => eliminar(t)}>Desactivar</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <Modal title={modal.id ? 'Editar tarifa' : 'Nueva tarifa'} onClose={() => setModal(null)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={guardar}>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="tOrigen">Zona de origen</label>
                <select id="tOrigen" required disabled={!!modal.id} value={form.zonaOrigenId} onChange={cambiar('zonaOrigenId')}>
                  <option value="">Selecciona…</option>
                  {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="tDestino">Zona de destino</label>
                <select id="tDestino" required disabled={!!modal.id} value={form.zonaDestinoId} onChange={cambiar('zonaDestinoId')}>
                  <option value="">Selecciona…</option>
                  {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="tServicio">Servicio</label>
              <select id="tServicio" disabled={!!modal.id} value={form.tipoServicio} onChange={cambiar('tipoServicio')}>
                {Object.entries(SERVICIOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </div>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="tBase">Precio base (S/)</label>
                <input id="tBase" type="number" min="0" step="0.01" required value={form.precioBase} onChange={cambiar('precioBase')} />
              </div>
              <div className="field">
                <label htmlFor="tKg">Precio por kg (S/)</label>
                <input id="tKg" type="number" min="0" step="0.01" required value={form.precioPorKg} onChange={cambiar('precioPorKg')} />
              </div>
            </div>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="tMin">Precio mínimo (S/)</label>
                <input id="tMin" type="number" min="0" step="0.01" placeholder="0.00" value={form.precioMinimo} onChange={cambiar('precioMinimo')} />
              </div>
              <div className="field">
                <label htmlFor="tDias">Plazo de entrega (días)</label>
                <input id="tDias" type="number" min="0" max="60" step="1" placeholder="0 = mismo día" value={form.diasEntrega} onChange={cambiar('diasEntrega')} />
              </div>
            </div>
            {modal.id && <p className="cell-secondary">Para cambiar las zonas o el servicio, desactiva esta tarifa y crea otra.</p>}
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : modal.id ? 'Guardar cambios' : 'Crear tarifa'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
