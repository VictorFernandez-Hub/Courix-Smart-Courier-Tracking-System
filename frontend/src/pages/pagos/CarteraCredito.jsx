// Cuentas por cobrar: clientes con credito, su deuda y lo vencido. Desde
// aqui se registra la cobranza (paga todos sus envios pendientes).
import { useCallback, useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { carteraCredito, cobrarCredito } from '../../api'

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`
const METODOS = { transferencia: 'Transferencia', yape: 'Yape', plin: 'Plin', efectivo: 'Efectivo', tarjeta: 'Tarjeta' }

export default function CarteraCredito({ onAviso }) {
  const [cartera, setCartera] = useState([])
  const [totales, setTotales] = useState(null)
  const [aCobrar, setACobrar] = useState(null)
  const [form, setForm] = useState({ metodo: 'transferencia', referencia: '' })
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = useCallback(() => {
    carteraCredito().then((r) => { setCartera(r.content); setTotales(r.totales) }).catch(() => setCartera([]))
  }, [])
  useEffect(() => { cargar() }, [cargar])

  async function cobrar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await cobrarCredito(aCobrar.clienteId, { metodo: form.metodo, referencia: form.referencia.trim() || undefined })
      setACobrar(null)
      onAviso?.(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  if (cartera.length === 0) return null
  const columnas = { gridTemplateColumns: '1fr 120px 120px 120px 110px' }
  return (
    <>
      <div className="section-title">
        Cuentas por cobrar (crédito) {totales && <span className="cell-secondary">· {soles(totales.deuda)}{Number(totales.vencido) > 0 && `, ${soles(totales.vencido)} vencido`}</span>}
      </div>
      <div className="manifest" style={{ marginBottom: 24 }}>
        <div className="manifest-row head" style={columnas}>
          <span>Cliente</span><span>Deuda</span><span>Vencido</span><span>Disponible</span><span>Acción</span>
        </div>
        {cartera.map((c) => (
          <div className="manifest-row" key={c.clienteId} style={columnas}>
            <div data-label="Cliente">
              <div className="cell-primary">{c.nombre}</div>
              <div className="cell-secondary">{c.pedidos} envío(s) · {c.diasCredito} días · límite {soles(c.limiteCredito)}</div>
            </div>
            <span className="amount" data-label="Deuda">{soles(c.deuda)}</span>
            <span className="amount" data-label="Vencido" style={{ color: Number(c.vencido) > 0 ? 'var(--danger)' : undefined }}>
              {Number(c.vencido) > 0 ? soles(c.vencido) : '—'}
            </span>
            <span className="cell-secondary" data-label="Disponible">{soles(c.disponible)}</span>
            <div className="row-actions" data-label="Acción">
              {Number(c.deuda) > 0 && (
                <button className="btn-xs" onClick={() => { setForm({ metodo: 'transferencia', referencia: '' }); setError(''); setACobrar(c) }}>
                  Cobrar
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {aCobrar && (
        <Modal title={`Cobrar crédito — ${aCobrar.nombre}`} onClose={() => setACobrar(null)}>
          {error && <div className="error-banner">{error}</div>}
          <p className="cli-hint">Se registra el pago de sus {aCobrar.pedidos} envío(s) pendientes por {soles(aCobrar.deuda)}.</p>
          <form onSubmit={cobrar}>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="cr-metodo">Método</label>
                <select id="cr-metodo" value={form.metodo} onChange={(e) => setForm((f) => ({ ...f, metodo: e.target.value }))}>
                  {Object.entries(METODOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="cr-ref">N.º de operación</label>
                <input id="cr-ref" maxLength={60} required={form.metodo !== 'efectivo'} value={form.referencia}
                  onChange={(e) => setForm((f) => ({ ...f, referencia: e.target.value }))} />
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setACobrar(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>Registrar cobro de {soles(aCobrar.deuda)}</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
