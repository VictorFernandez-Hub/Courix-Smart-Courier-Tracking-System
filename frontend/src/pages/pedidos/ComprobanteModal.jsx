import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { comprobantesDelPedido, emitirComprobante, reenviarComprobante } from '../../api'

// Boleta o factura electronica del envio (via Nubefact). Solo se emite si la
// facturacion esta configurada: no se genera ningun documento "de mentira".
const ESTADOS = {
  aceptado: '✓ Aceptado por SUNAT',
  pendiente: 'Enviado, esperando a SUNAT',
  error: '✗ Error al enviar: se puede reintentar',
  rechazado: '✗ Rechazado por SUNAT',
}

export default function ComprobanteModal({ pedido, onCerrar }) {
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState({ tipo: 'boleta', numDoc: '', nombre: '', direccion: '', email: '' })
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [enviando, setEnviando] = useState(false)

  function cargar() {
    comprobantesDelPedido(pedido.id).then((r) => {
      setInfo(r.content)
      setForm((f) => ({ ...f, nombre: f.nombre || r.content.sugerido.nombre, numDoc: f.numDoc || r.content.sugerido.numDoc,
        email: f.email || r.content.sugerido.email }))
    }).catch((err) => setError(err.message))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(cargar, [pedido.id])

  const cambiar = (campo) => (e) => setForm((f) => ({ ...f, [campo]: e.target.value }))
  const vigente = info?.comprobantes.find((c) => c.estado !== 'rechazado')

  async function emitir(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await emitirComprobante(pedido.id, {
        tipo: form.tipo, numDoc: form.numDoc.trim() || undefined, nombre: form.nombre.trim(),
        direccion: form.direccion.trim() || undefined, email: form.email.trim() || undefined,
      })
      setMensaje(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function reenviar(c) {
    setError('')
    try {
      const r = await reenviarComprobante(c.id)
      setMensaje(r.message)
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Modal title={`Comprobante — ${pedido.codigoGuia}`} onClose={onCerrar}>
      {error && <div className="error-banner">{error}</div>}
      {mensaje && <div className="success-banner">{mensaje}</div>}
      {!info ? <p className="loading-text">Cargando…</p> : (
        <>
          {info.comprobantes.map((c) => (
            <div className="dato-lista separador" key={c.id}>
              <div><span>{c.tipo === 'factura' ? 'Factura' : 'Boleta'}</span><strong className="cell-mono">{c.numeroCompleto}</strong></div>
              <div><span>Cliente</span><strong>{c.clienteNombre}{c.clienteNumDoc ? ` · ${c.clienteNumDoc}` : ''}</strong></div>
              <div><span>Total (IGV incluido)</span><strong>S/ {c.total} <span className="cell-secondary">(IGV S/ {c.igv})</span></strong></div>
              <div><span>Estado</span><strong>{ESTADOS[c.estado] || c.estado}</strong></div>
              {c.mensajeSunat && <div className="cell-secondary">{c.mensajeSunat}</div>}
              <div style={{ justifyContent: 'flex-end', gap: 8 }}>
                {c.enlacePdf && <a className="btn btn-secondary" href={c.enlacePdf} target="_blank" rel="noopener noreferrer">Ver PDF</a>}
                {['error', 'pendiente'].includes(c.estado) && <button className="btn btn-secondary" onClick={() => reenviar(c)}>Reintentar</button>}
              </div>
            </div>
          ))}

          {!vigente && (
            !info.facturacionConfigurada ? (
              <div className="error-banner">
                La facturación electrónica no está configurada (NUBEFACT_URL y NUBEFACT_TOKEN en el backend).
                No se emite ningún comprobante hasta conectarla.
              </div>
            ) : (
              <form onSubmit={emitir}>
                <p className="cell-secondary">Monto pagado: <strong>S/ {Number(info.totalPagado).toFixed(2)}</strong> (incluye IGV)</p>
                <div className="form-2col">
                  <div className="field">
                    <label htmlFor="cpTipo">Tipo</label>
                    <select id="cpTipo" value={form.tipo} onChange={cambiar('tipo')}>
                      <option value="boleta">Boleta</option>
                      <option value="factura">Factura</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="cpDoc">{form.tipo === 'factura' ? 'RUC' : 'DNI / CE'} {form.tipo === 'boleta' && Number(info.totalPagado) < 700 && <span className="cell-secondary">(opcional)</span>}</label>
                    <input id="cpDoc" inputMode="numeric" maxLength={form.tipo === 'factura' ? 11 : 12}
                      required={form.tipo === 'factura' || Number(info.totalPagado) >= 700}
                      pattern={form.tipo === 'factura' ? '(10|15|16|17|20)[0-9]{9}' : '[A-Za-z0-9]{8,12}'}
                      value={form.numDoc} onChange={cambiar('numDoc')} />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="cpNombre">{form.tipo === 'factura' ? 'Razón social' : 'Nombre'}</label>
                  <input id="cpNombre" required minLength={3} maxLength={150} value={form.nombre} onChange={cambiar('nombre')} />
                </div>
                {form.tipo === 'factura' && (
                  <div className="field">
                    <label htmlFor="cpDir">Dirección fiscal</label>
                    <input id="cpDir" required maxLength={200} value={form.direccion} onChange={cambiar('direccion')} />
                  </div>
                )}
                <div className="field">
                  <label htmlFor="cpEmail">Enviar al correo <span className="cell-secondary">(opcional)</span></label>
                  <input id="cpEmail" type="email" maxLength={120} value={form.email} onChange={cambiar('email')} />
                </div>
                <div className="modal-actions">
                  <button type="button" className="btn btn-secondary" onClick={onCerrar}>Cerrar</button>
                  <button type="submit" className="btn btn-primary" disabled={enviando}>{enviando ? 'Emitiendo…' : `Emitir ${form.tipo}`}</button>
                </div>
              </form>
            )
          )}
        </>
      )}
    </Modal>
  )
}
