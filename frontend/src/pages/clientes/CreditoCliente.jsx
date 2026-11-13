// Credito del cliente: condiciones (solo admin) y estado de cuenta con los
// envios pendientes de pago, su vencimiento y lo disponible.
import { useCallback, useEffect, useState } from 'react'
import { configurarCredito, cuentaCliente, getUsuario } from '../../api'

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`

export default function CreditoCliente({ clienteId, onCambio }) {
  const esAdmin = getUsuario()?.rol === 'admin'
  const [cuenta, setCuenta] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const cargar = useCallback(() => {
    cuentaCliente(clienteId).then((r) => {
      setCuenta(r.content)
      setForm({ creditoHabilitado: r.content.creditoHabilitado, limiteCredito: r.content.limiteCredito,
                diasCredito: String(r.content.diasCredito) })
    }).catch((e) => setError(e.message))
  }, [clienteId])
  useEffect(() => { cargar() }, [cargar])

  async function guardar(e) {
    e.preventDefault()
    setError('')
    try {
      const r = await configurarCredito(clienteId, { ...form, diasCredito: Number(form.diasCredito) })
      setCuenta(r.content)
      setMensaje('Condiciones de crédito guardadas')
      setTimeout(() => setMensaje(''), 3000)
      onCambio?.()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!cuenta || !form) return error ? <div className="error-banner">{error}</div> : <p className="loading-text">Cargando…</p>
  return (
    <div>
      {error && <div className="error-banner">{error}</div>}
      {mensaje && <div className="success-banner">{mensaje}</div>}
      <div className="cli-kpis" style={{ marginBottom: 12 }}>
        <div className="cli-kpi"><span>Deuda</span><strong>{soles(cuenta.deuda)}</strong></div>
        <div className={`cli-kpi${Number(cuenta.vencido) > 0 ? ' alerta' : ''}`}><span>Vencido</span><strong>{soles(cuenta.vencido)}</strong></div>
        <div className="cli-kpi"><span>Disponible</span><strong>{soles(cuenta.disponible)}</strong><small>de {soles(cuenta.limiteCredito)}</small></div>
      </div>
      {!cuenta.creditoHabilitado && <p className="cli-hint">Sin crédito: sus envíos se cobran prepagados o contra entrega.</p>}

      {esAdmin && (
        <form onSubmit={guardar} className="panel" style={{ marginBottom: 16 }}>
          <label className="check-line">
            <input type="checkbox" checked={form.creditoHabilitado}
              onChange={(e) => setForm((f) => ({ ...f, creditoHabilitado: e.target.checked }))} />
            <span>Puede enviar a crédito</span>
          </label>
          <div className="form-2col">
            <div className="field">
              <label htmlFor="cr-limite">Límite (S/)</label>
              <input id="cr-limite" type="number" min="0" step="0.01" value={form.limiteCredito}
                onChange={(e) => setForm((f) => ({ ...f, limiteCredito: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="cr-dias">Plazo de pago (días)</label>
              <input id="cr-dias" type="number" min="1" max="120" value={form.diasCredito}
                onChange={(e) => setForm((f) => ({ ...f, diasCredito: e.target.value }))} />
            </div>
          </div>
          <button className="btn btn-primary" type="submit">Guardar condiciones</button>
        </form>
      )}

      {cuenta.pedidos.length > 0 ? (
        <div className="manifest">
          {cuenta.pedidos.map((p) => (
            <div className="manifest-row" key={p.pedidoId} style={{ gridTemplateColumns: '1fr 110px 140px' }}>
              <span className="tag-id" data-label="Guía">{p.codigoGuia}</span>
              <span className="amount" data-label="Monto">{soles(p.monto)}</span>
              <span className={p.vencido ? 'cli-hint error' : 'cell-secondary'} data-label="Vence">
                {p.vencido ? `Vencido hace ${p.diasAtraso} día(s)` : `Vence ${new Date(p.vence).toLocaleDateString('es-PE')}`}
              </span>
            </div>
          ))}
        </div>
      ) : <p className="cell-secondary">No tiene envíos a crédito pendientes de pago.</p>}
      <p className="cell-secondary" style={{ marginTop: 8 }}>La cobranza se registra en Pagos y caja → Cuentas por cobrar.</p>
    </div>
  )
}
