// Arqueo del cajero: lo que el sistema dice que debe haber en la gaveta
// desde su ultimo cierre, contra lo que cuenta. Lo digital (Yape, Plin,
// tarjeta, transferencia) se lista aparte para conciliarlo con el banco.
import { useCallback, useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { arqueoCaja, cerrarCaja, listarCierresCaja } from '../../api'

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`
const METODOS = { efectivo: 'Efectivo', yape: 'Yape', plin: 'Plin', tarjeta: 'Tarjeta', transferencia: 'Transferencia' }
const fecha = (v) => (v ? new Date(v).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'short' }) : '—')

export default function CierreCaja({ onAviso }) {
  const [arqueo, setArqueo] = useState(null)
  const [cierres, setCierres] = useState([])
  const [abierto, setAbierto] = useState(false)
  const [verDetalle, setVerDetalle] = useState(false)
  const [form, setForm] = useState({ efectivoContado: '', observacion: '' })
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = useCallback(() => {
    arqueoCaja().then((r) => setArqueo(r.content)).catch(() => setArqueo(null))
    listarCierresCaja().then((r) => setCierres(r.content)).catch(() => setCierres([]))
  }, [])
  useEffect(() => { cargar() }, [cargar])

  const diferencia = arqueo && form.efectivoContado !== ''
    ? Number(form.efectivoContado) - Number(arqueo.efectivoEsperado) : 0

  async function cerrar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await cerrarCaja({ efectivoContado: form.efectivoContado, observacion: form.observacion.trim() || undefined })
      setAbierto(false)
      onAviso?.(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  if (!arqueo) return null
  const digitales = Object.entries(arqueo.porMetodo).filter(([m]) => m !== 'efectivo')

  return (
    <>
      <div className="section-title">Mi caja <span className="cell-secondary">· desde {arqueo.desde ? fecha(arqueo.desde) : 'el inicio'}</span></div>
      <div className="cli-kpis" style={{ marginBottom: 10 }}>
        <div className="cli-kpi"><span>Efectivo que debes tener</span><strong>{soles(arqueo.efectivoEsperado)}</strong><small>en gaveta</small></div>
        {digitales.map(([m, v]) => (
          <div className="cli-kpi" key={m}><span>{METODOS[m] || m}</span><strong>{soles(v)}</strong><small>conciliar con banco</small></div>
        ))}
        <div className="cli-kpi"><span>Movimientos</span><strong>{arqueo.movimientos.length}</strong><small>desde el último cierre</small></div>
      </div>
      <div className="row-actions" style={{ marginBottom: 20 }}>
        <button className="btn btn-primary" onClick={() => { setForm({ efectivoContado: '', observacion: '' }); setError(''); setAbierto(true) }}>
          Cerrar mi caja
        </button>
        {arqueo.movimientos.length > 0 && (
          <button className="btn-xs" onClick={() => setVerDetalle((v) => !v)}>{verDetalle ? 'Ocultar' : 'Ver'} movimientos</button>
        )}
        {cierres.length > 0 && <span className="cell-secondary">Último cierre: {cierres[0].codigo} · {fecha(cierres[0].hasta)}</span>}
      </div>
      {verDetalle && (
        <div className="manifest" style={{ marginBottom: 20 }}>
          {arqueo.movimientos.map((m, i) => (
            <div className="manifest-row" key={i} style={{ gridTemplateColumns: '1fr 130px 120px' }}>
              <span data-label="Concepto">{m.concepto}</span>
              <span className="cell-secondary" data-label="Método">{METODOS[m.metodo] || m.metodo}</span>
              <span className="amount" data-label="Monto" style={{ color: Number(m.monto) < 0 ? 'var(--danger)' : undefined }}>{soles(m.monto)}</span>
            </div>
          ))}
        </div>
      )}

      {abierto && (
        <Modal title="Cierre de caja" onClose={() => setAbierto(false)}>
          {error && <div className="error-banner">{error}</div>}
          <form onSubmit={cerrar}>
            <div className="dato-lista" style={{ marginBottom: 12 }}>
              <div><span>Efectivo según el sistema</span><strong>{soles(arqueo.efectivoEsperado)}</strong></div>
              {form.efectivoContado !== '' && (
                <div><span>Diferencia</span><strong style={{ color: diferencia ? 'var(--danger)' : 'var(--st-entregado)' }}>
                  {diferencia > 0 ? '+' : ''}{soles(diferencia)}</strong></div>
              )}
            </div>
            <div className="field">
              <label htmlFor="cj-contado">Efectivo contado en gaveta</label>
              <input id="cj-contado" type="number" min="0" step="0.01" required autoFocus value={form.efectivoContado}
                onChange={(e) => setForm((f) => ({ ...f, efectivoContado: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="cj-obs">Observación {diferencia ? '(obligatoria: hay diferencia)' : '(opcional)'}</label>
              <textarea id="cj-obs" maxLength={1000} required={Boolean(diferencia)} value={form.observacion}
                onChange={(e) => setForm((f) => ({ ...f, observacion: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setAbierto(false)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>Cerrar caja</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
