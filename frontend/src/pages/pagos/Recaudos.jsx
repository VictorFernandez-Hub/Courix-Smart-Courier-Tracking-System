// Contra entrega de mercaderia: lo cobrado a los destinatarios por cuenta de
// cada remitente (tienda) y su pago. Solo se paga lo que ya esta en caja: el
// efectivo que aun tiene un repartidor se libera al liquidar su ruta.
import { useCallback, useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { getUsuario, liquidacionesRecaudo, liquidarRecaudos, recaudosPendientes } from '../../api'

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`
const METODOS = { transferencia: 'Transferencia', yape: 'Yape', plin: 'Plin', efectivo: 'Efectivo', tarjeta: 'Tarjeta' }

export default function Recaudos({ onAviso }) {
  const esAdmin = getUsuario()?.rol === 'admin'
  const [pendientes, setPendientes] = useState([])
  const [historial, setHistorial] = useState([])
  const [verHistorial, setVerHistorial] = useState(false)
  const [aPagar, setAPagar] = useState(null)
  const [form, setForm] = useState({ metodo: 'transferencia', referencia: '', observacion: '' })
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = useCallback(() => {
    recaudosPendientes().then((r) => setPendientes(r.content)).catch(() => setPendientes([]))
    liquidacionesRecaudo().then((r) => setHistorial(r.content)).catch(() => setHistorial([]))
  }, [])
  useEffect(() => { cargar() }, [cargar])

  function abrir(p) {
    setForm({ metodo: 'transferencia', referencia: '', observacion: '' })
    setError('')
    setAPagar(p)
  }

  async function pagar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await liquidarRecaudos({
        remitenteId: aPagar.remitente.id, metodo: form.metodo,
        referencia: form.referencia.trim() || undefined, observacion: form.observacion.trim() || undefined,
      })
      setAPagar(null)
      onAviso?.(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const columnas = { gridTemplateColumns: '1fr 80px 120px 120px 130px 120px' }
  const totalDeuda = pendientes.reduce((s, p) => s + Number(p.total), 0)

  return (
    <>
      <div className="section-title">
        Recaudos por pagar a remitentes {totalDeuda > 0 && <span className="cell-secondary">· {soles(totalDeuda)} en total</span>}
      </div>
      {pendientes.length === 0 ? (
        <p className="cell-secondary" style={{ marginBottom: 20 }}>No se le debe nada a ningún remitente.</p>
      ) : (
        <div className="manifest" style={{ marginBottom: 12 }}>
          <div className="manifest-row head" style={columnas}>
            <span>Remitente</span><span>Envíos</span><span>Recaudado</span><span>Con repartidor</span>
            <span>A pagar hoy</span><span>Acción</span>
          </div>
          {pendientes.map((p) => (
            <div className="manifest-row" key={p.remitente.id} style={columnas}>
              <div data-label="Remitente">
                <div className="cell-primary">{p.remitente.nombre}</div>
                {p.remitente.telefono && <div className="cell-secondary cell-mono">{p.remitente.telefono}</div>}
              </div>
              <span data-label="Envíos">{p.envios}</span>
              <span className="amount" data-label="Recaudado">{soles(p.total)}</span>
              <span className="cell-secondary" data-label="Con repartidor"
                title="Efectivo que todavía no se rinde en caja: se libera al liquidar la ruta">
                {Number(p.conRepartidor) > 0 ? soles(p.conRepartidor) : '—'}
              </span>
              <div data-label="A pagar hoy">
                <div className="amount">{soles(p.aPagar)}</div>
                {Number(p.comision) > 0 && <div className="cell-secondary">comisión {p.porcentajeComision}%: {soles(p.comision)}</div>}
              </div>
              <div className="row-actions" data-label="Acción">
                {esAdmin && Number(p.enCaja) > 0
                  ? <button className="btn-xs" onClick={() => abrir(p)}>Pagar</button>
                  : <span className="cell-secondary">{Number(p.enCaja) > 0 ? 'Lo paga un admin' : 'Esperando caja'}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      {historial.length > 0 && (
        <button className="btn-xs" style={{ marginBottom: 20 }} onClick={() => setVerHistorial((v) => !v)}>
          {verHistorial ? 'Ocultar' : 'Ver'} pagos a remitentes ({historial.length})
        </button>
      )}
      {verHistorial && (
        <div className="manifest" style={{ marginBottom: 24 }}>
          {historial.map((l) => (
            <div className="manifest-row" key={l.id} style={{ gridTemplateColumns: '110px 1fr 90px 120px 1fr' }}>
              <span className="tag-id" data-label="Código">{l.codigo}</span>
              <span className="cell-primary" data-label="Remitente">{l.remitente.nombre}</span>
              <span data-label="Envíos">{l.envios} envío(s)</span>
              <span className="amount" data-label="Pagado">{soles(l.montoPagado)}</span>
              <span className="cell-secondary" data-label="Detalle">
                {METODOS[l.metodo] || l.metodo}{l.referencia ? ` · ${l.referencia}` : ''} · {l.fecha ? new Date(l.fecha).toLocaleDateString('es-PE') : ''}
              </span>
            </div>
          ))}
        </div>
      )}

      {aPagar && (
        <Modal title={`Pagar recaudos — ${aPagar.remitente.nombre}`} onClose={() => setAPagar(null)}>
          {error && <div className="error-banner">{error}</div>}
          <div className="cli-kpis" style={{ marginBottom: 12 }}>
            <div className="cli-kpi"><span>Recaudado en caja</span><strong>{soles(aPagar.enCaja)}</strong></div>
            <div className="cli-kpi"><span>Comisión</span><strong>{soles(aPagar.comision)}</strong></div>
            <div className="cli-kpi"><span>A pagar</span><strong>{soles(aPagar.aPagar)}</strong></div>
          </div>
          {Number(aPagar.conRepartidor) > 0 && (
            <p className="cli-hint">{soles(aPagar.conRepartidor)} siguen con un repartidor: se pagarán en la próxima liquidación.</p>
          )}
          <form onSubmit={pagar}>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="rec-metodo">Cómo se le paga</label>
                <select id="rec-metodo" value={form.metodo} onChange={(e) => setForm((f) => ({ ...f, metodo: e.target.value }))}>
                  {Object.entries(METODOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rec-ref">N.º de operación</label>
                <input id="rec-ref" maxLength={60} required={form.metodo !== 'efectivo'} value={form.referencia}
                  onChange={(e) => setForm((f) => ({ ...f, referencia: e.target.value }))} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="rec-obs">Observación <span className="cell-secondary">(opcional)</span></label>
              <input id="rec-obs" maxLength={1000} value={form.observacion}
                onChange={(e) => setForm((f) => ({ ...f, observacion: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setAPagar(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Registrando…' : `Registrar pago de ${soles(aPagar.aPagar)}`}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
