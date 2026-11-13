// Dialogos de los caminos de excepcion de un envio: entregar la devolucion
// al remitente (cobrando lo pendiente), corregir la direccion de entrega y
// devolver dinero (flete o indemnizacion).
import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import {
  cambiarEstadoPedido, listarDireccionesCliente, listarIncidenciasDePedido, redireccionarPedido,
  reembolsosDelPedido, registrarReembolso, saldoDevolucion,
} from '../../api'

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`
const METODOS = { efectivo: 'Efectivo', yape: 'Yape', plin: 'Plin', tarjeta: 'Tarjeta', transferencia: 'Transferencia' }

function CamposPago({ form, setForm, etiqueta = 'Método de pago' }) {
  return (
    <div className="form-2col">
      <div className="field">
        <label htmlFor="exc-metodo">{etiqueta}</label>
        <select id="exc-metodo" value={form.metodo} onChange={(e) => setForm((f) => ({ ...f, metodo: e.target.value }))}>
          {Object.entries(METODOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="exc-ref">N.º de operación</label>
        <input id="exc-ref" maxLength={60} required={form.metodo !== 'efectivo'} value={form.referencia}
          onChange={(e) => setForm((f) => ({ ...f, referencia: e.target.value }))} />
      </div>
    </div>
  )
}

function useEnvio(onHecho) {
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function enviar(fn) {
    setError('')
    setEnviando(true)
    try {
      const r = await fn()
      onHecho(r.message)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }
  return { error, enviando, enviar }
}

export function DevolucionModal({ pedido, onClose, onHecho }) {
  const [saldo, setSaldo] = useState(null)
  const [form, setForm] = useState({ comentario: '', metodo: 'efectivo', referencia: '' })
  const { error, enviando, enviar } = useEnvio(onHecho)
  useEffect(() => { saldoDevolucion(pedido.id).then((r) => setSaldo(r.content)).catch(() => setSaldo(null)) }, [pedido.id])
  const debeCobrar = saldo && Number(saldo.total) > 0

  return (
    <Modal title={`Entregar devolución — ${pedido.codigoGuia}`} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={(e) => {
        e.preventDefault()
        enviar(() => cambiarEstadoPedido(pedido.id, {
          estado: 'devuelto', comentario: form.comentario.trim(),
          ...(debeCobrar ? { metodo: form.metodo, referencia: form.referencia.trim() || undefined } : {}),
        }))
      }}>
        {saldo && (debeCobrar ? (
          <div className="dato-lista" style={{ marginBottom: 12 }}>
            {Number(saldo.flete) > 0 && <div><span>Flete no pagado (era contra entrega)</span><strong>{soles(saldo.flete)}</strong></div>}
            {Number(saldo.cargos) > 0 && <div><span>Cargo por devolución</span><strong>{soles(saldo.cargos)}</strong></div>}
            <div><span>Cobrar al remitente</span><strong>{soles(saldo.total)}</strong></div>
          </div>
        ) : <p className="cli-hint">No hay nada pendiente de cobro: solo registra quién lo recibe.</p>)}
        <div className="field">
          <label htmlFor="dev-quien">¿Quién recibe? (nombre y DNI)</label>
          <input id="dev-quien" required minLength={5} maxLength={500} value={form.comentario}
            onChange={(e) => setForm((f) => ({ ...f, comentario: e.target.value }))} placeholder="Ej. Juan Pérez, DNI 44556677" />
        </div>
        {debeCobrar && <CamposPago form={form} setForm={setForm} />}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando || !saldo}>
            {debeCobrar ? `Cobrar ${soles(saldo.total)} y entregar` : 'Registrar entrega'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function RedireccionModal({ pedido, onClose, onHecho }) {
  const [direcciones, setDirecciones] = useState([])
  const [form, setForm] = useState({ direccionEntregaId: '', motivo: '' })
  const { error, enviando, enviar } = useEnvio(onHecho)
  useEffect(() => {
    listarDireccionesCliente(pedido.clienteId)
      .then((r) => setDirecciones(r.content.filter((d) => d.activo !== false && d.id !== pedido.direccionEntregaId)))
      .catch(() => setDirecciones([]))
  }, [pedido.clienteId, pedido.direccionEntregaId])

  return (
    <Modal title={`Corregir dirección — ${pedido.codigoGuia}`} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      <p className="cli-hint">
        Antes de que salga de la agencia de origen se puede cambiar a cualquier zona (se recalcula el flete).
        Si ya está en la agencia de reparto, solo a una dirección que reparta esa misma agencia.
      </p>
      <form onSubmit={(e) => {
        e.preventDefault()
        enviar(() => redireccionarPedido(pedido.id, { direccionEntregaId: Number(form.direccionEntregaId), motivo: form.motivo.trim() }))
      }}>
        <div className="field">
          <label htmlFor="red-dir">Nueva dirección del destinatario</label>
          <select id="red-dir" required value={form.direccionEntregaId}
            onChange={(e) => setForm((f) => ({ ...f, direccionEntregaId: e.target.value }))}>
            <option value="">Selecciona…</option>
            {direcciones.map((d) => <option key={d.id} value={d.id}>{d.etiqueta ? `${d.etiqueta}: ` : ''}{d.calle}</option>)}
          </select>
          {direcciones.length === 0 && (
            <p className="cli-hint">El destinatario no tiene otra dirección: agrégala en su ficha (Clientes) y vuelve.</p>
          )}
        </div>
        <div className="field">
          <label htmlFor="red-motivo">Motivo</label>
          <input id="red-motivo" required minLength={5} maxLength={300} value={form.motivo}
            onChange={(e) => setForm((f) => ({ ...f, motivo: e.target.value }))} placeholder="Ej. el remitente corrigió el número de casa" />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>Guardar nueva dirección</button>
        </div>
      </form>
    </Modal>
  )
}

export function ReembolsoModal({ pedido, estado, onClose, onHecho }) {
  const [info, setInfo] = useState(null)
  const [incidencias, setIncidencias] = useState([])
  const servicioNoPrestado = estado === 'cancelado' || estado === 'extraviado'
  const [form, setForm] = useState({
    tipo: servicioNoPrestado ? 'devolucion_flete' : 'indemnizacion', monto: '', metodo: 'transferencia', referencia: '',
    motivo: '', incidenciaId: '',
  })
  const { error, enviando, enviar } = useEnvio(onHecho)
  useEffect(() => {
    reembolsosDelPedido(pedido.id).then((r) => setInfo(r.content)).catch(() => setInfo(null))
    listarIncidenciasDePedido(pedido.id).then((r) => setIncidencias(r.content)).catch(() => setIncidencias([]))
  }, [pedido.id])
  const s = info?.saldos
  const disponible = s ? (form.tipo === 'devolucion_flete' ? s.devolucionDisponible : s.indemnizacionDisponible) : 0

  return (
    <Modal title={`Devolver dinero — ${pedido.codigoGuia}`} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      {s && (
        <div className="dato-lista" style={{ marginBottom: 12 }}>
          <div><span>Cobrado por el servicio</span><strong>{soles(s.cobrado)}</strong></div>
          <div><span>Ya devuelto / indemnizado</span><strong>{soles(s.devuelto)} / {soles(s.indemnizado)}</strong></div>
          <div><span>Tope de indemnización {info.conSeguro ? '(valor declarado, con seguro)' : '(sin seguro)'}</span>
            <strong>{soles(s.topeIndemnizacion)}</strong></div>
        </div>
      )}
      <form onSubmit={(e) => {
        e.preventDefault()
        enviar(() => registrarReembolso(pedido.id, {
          tipo: form.tipo, monto: form.monto, metodo: form.metodo, referencia: form.referencia.trim() || undefined,
          motivo: form.motivo.trim(), incidenciaId: form.incidenciaId ? Number(form.incidenciaId) : undefined,
        }))
      }}>
        <div className="form-2col">
          <div className="field">
            <label htmlFor="ree-tipo">Tipo</label>
            <select id="ree-tipo" value={form.tipo} onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))}>
              <option value="devolucion_flete" disabled={!servicioNoPrestado}>Devolver el flete (servicio no prestado)</option>
              <option value="indemnizacion">Indemnización (pérdida o daño)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="ree-monto">Monto (máx. {soles(disponible)})</label>
            <input id="ree-monto" type="number" min="0.01" step="0.01" max={disponible} required value={form.monto}
              onChange={(e) => setForm((f) => ({ ...f, monto: e.target.value }))} />
          </div>
        </div>
        {form.tipo === 'indemnizacion' && estado !== 'extraviado' && (
          <div className="field">
            <label htmlFor="ree-inc">Incidencia de daño o faltante</label>
            <select id="ree-inc" required value={form.incidenciaId}
              onChange={(e) => setForm((f) => ({ ...f, incidenciaId: e.target.value }))}>
              <option value="">Selecciona…</option>
              {incidencias.filter((i) => ['producto_danado', 'faltante'].includes(i.tipo))
                .map((i) => <option key={i.id} value={i.id}>#{i.id} {i.tipo.replace('_', ' ')}</option>)}
            </select>
          </div>
        )}
        <CamposPago form={form} setForm={setForm} etiqueta="Cómo se devuelve" />
        <div className="field">
          <label htmlFor="ree-motivo">Motivo</label>
          <input id="ree-motivo" required minLength={5} maxLength={500} value={form.motivo}
            onChange={(e) => setForm((f) => ({ ...f, motivo: e.target.value }))} />
        </div>
        {form.tipo === 'devolucion_flete' && (
          <p className="cli-hint">Si el envío tiene boleta o factura, se emite automáticamente la nota de crédito.</p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando || Number(disponible) <= 0}>Registrar</button>
        </div>
      </form>
    </Modal>
  )
}
