import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { misRecojos, marcarRecogido, marcarRecojoFallido } from '../../api'

const FRANJAS = { manana: 'Mañana', tarde: 'Tarde' }
const MOTIVOS = {
  cliente_ausente: 'Cliente ausente',
  direccion_incorrecta: 'Dirección incorrecta',
  paquete_no_listo: 'El paquete no estaba listo',
  otro: 'Otro',
}

// Recojos a domicilio asignados al repartidor (paso 1 del proceso).
export default function RecojosRepartidor() {
  const [recojos, setRecojos] = useState([])
  const [accion, setAccion] = useState(null) // { tipo: 'recoger' | 'fallido', recojo }
  const [form, setForm] = useState({ bultos: '', motivo: 'cliente_ausente', comentario: '' })
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = () => misRecojos().then((r) => setRecojos(r.content)).catch(() => {})
  useEffect(() => { cargar() }, [])

  function abrir(tipo, recojo) {
    setForm({ bultos: String(recojo.bultosEstimados), motivo: 'cliente_ausente', comentario: '' })
    setError('')
    setAccion({ tipo, recojo })
  }

  async function confirmar(e) {
    e.preventDefault()
    setEnviando(true)
    setError('')
    try {
      const r = accion.tipo === 'recoger'
        ? await marcarRecogido(accion.recojo.id, { bultosRecogidos: Number(form.bultos), comentario: form.comentario || undefined })
        : await marcarRecojoFallido(accion.recojo.id, { motivo: form.motivo, comentario: form.comentario || undefined })
      setMensaje(r.message)
      setAccion(null)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  if (recojos.length === 0 && !mensaje) return null

  return (
    <>
      <div className="section-title" style={{ marginTop: 0 }}>Recojos a domicilio</div>
      {mensaje && <div className="success-banner">{mensaje}</div>}
      {recojos.map((r) => (
        <div className="route-card recojo-card" key={r.id}>
          <div className="route-card-top">
            <div>
              <div className="route-card-cliente">Recoger: {r.remitente.nombre}</div>
              <div className="cell-secondary cell-mono">{r.codigo} · {new Date(r.fechaProgramada + 'T12:00').toLocaleDateString('es-PE')} · {FRANJAS[r.franja]}</div>
            </div>
            <span className="badge">{r.bultosEstimados} bulto(s)</span>
          </div>
          <div className="route-card-info">
            <div>📍 {r.direccion.calle}{r.direccion.referencia ? ` — ${r.direccion.referencia}` : ''}</div>
            <div>📞 <span className="cell-mono">{r.remitente.telefono}</span></div>
            {r.notas && <div className="cell-secondary">Nota: {r.notas}</div>}
          </div>
          <div className="route-card-actions">
            <button className="btn btn-success btn-lg" onClick={() => abrir('recoger', r)}>Recogí los paquetes</button>
            <button className="btn btn-warning btn-lg" onClick={() => abrir('fallido', r)}>No pude recoger</button>
          </div>
        </div>
      ))}

      {accion && (
        <Modal title={`${accion.tipo === 'recoger' ? 'Confirmar recojo' : 'Recojo no realizado'} — ${accion.recojo.codigo}`}
          onClose={() => setAccion(null)}>
          {error && <div className="error-banner">{error}</div>}
          <form onSubmit={confirmar}>
            {accion.tipo === 'recoger' ? (
              <div className="field">
                <label htmlFor="bultosRecogidos">¿Cuántos bultos recogiste?</label>
                <input id="bultosRecogidos" type="number" min="1" max="50" required value={form.bultos}
                  onChange={(e) => setForm((f) => ({ ...f, bultos: e.target.value }))} />
                <p className="cell-secondary" style={{ marginTop: 4 }}>Llévalos a la agencia: allí se pesan, se inspeccionan y se cobran.</p>
              </div>
            ) : (
              <div className="field">
                <label htmlFor="motivoRecojo">Motivo</label>
                <select id="motivoRecojo" value={form.motivo} onChange={(e) => setForm((f) => ({ ...f, motivo: e.target.value }))}>
                  {Object.entries(MOTIVOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </div>
            )}
            <div className="field">
              <label htmlFor="comentarioRecojo">Comentario (opcional)</label>
              <input id="comentarioRecojo" maxLength={500} value={form.comentario}
                onChange={(e) => setForm((f) => ({ ...f, comentario: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setAccion(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>{enviando ? 'Guardando…' : 'Confirmar'}</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
