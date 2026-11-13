import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import Recaudos from './Recaudos'
import CierreCaja from './CierreCaja'
import CarteraCredito from './CarteraCredito'
import { listarPagos, marcarPagoComoPagado, liquidacionesPendientes, liquidarRuta } from '../../api'

export default function Pagos() {
  const [pagos, setPagos] = useState([])
  const [totalCobrado, setTotalCobrado] = useState('0')
  const [filtro, setFiltro] = useState('')
  const [pagina, setPagina] = useState(1)
  const [paginacion, setPaginacion] = useState({ totalPaginas: 1, totalRegistros: 0 })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [pendientes, setPendientes] = useState([])
  const [rutaALiquidar, setRutaALiquidar] = useState(null)
  const [formLiquidacion, setFormLiquidacion] = useState({ montoEntregado: '', observacion: '' })
  const [errorLiquidacion, setErrorLiquidacion] = useState('')
  const [liquidando, setLiquidando] = useState(false)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro, pagina])

  useEffect(() => {
    cargarPendientes()
  }, [])

  function cargarPendientes() {
    liquidacionesPendientes().then((r) => setPendientes(r.content)).catch(() => setPendientes([]))
  }

  function abrirLiquidacion(ruta) {
    setFormLiquidacion({ montoEntregado: ruta.montoEsperado, observacion: '' })
    setErrorLiquidacion('')
    setRutaALiquidar(ruta)
  }

  async function manejarLiquidar(e) {
    e.preventDefault()
    setErrorLiquidacion('')
    setLiquidando(true)
    try {
      const res = await liquidarRuta(rutaALiquidar.rutaId, formLiquidacion.montoEntregado, formLiquidacion.observacion || undefined)
      setRutaALiquidar(null)
      mostrarMensaje(res.message)
      cargarPendientes()
    } catch (err) {
      setErrorLiquidacion(err.message)
    } finally {
      setLiquidando(false)
    }
  }

  const diferenciaLiquidacion = rutaALiquidar
    ? Number(formLiquidacion.montoEntregado || 0) - Number(rutaALiquidar.montoEsperado)
    : 0

  function cambiarFiltro(nuevo) {
    setPagina(1)
    setFiltro(nuevo)
  }

  function cargar() {
    setCargando(true)
    listarPagos(filtro || undefined, pagina)
      .then((r) => {
        setPagos(r.content)
        setTotalCobrado(r.totalCobrado)
        setPaginacion(r.paginacion)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3000)
  }

  async function manejarMarcarPagado(id) {
    setError('')
    try {
      await marcarPagoComoPagado(id)
      mostrarMensaje(`Pago #${id} marcado como pagado`)
      cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Pagos</h1>
          <p className="page-sub">Total cobrado: S/ {Number(totalCobrado).toFixed(2)}</p>
        </div>
      </div>

      <div className="section-title" style={{ marginTop: 0 }}>Liquidación de caja de repartidores</div>
      {pendientes.length === 0 ? (
        <p className="cell-secondary" style={{ marginBottom: 20 }}>No hay rutas con efectivo pendiente de entregar en caja.</p>
      ) : (
        <div className="manifest" style={{ marginBottom: 24 }}>
          <div className="manifest-row head" style={{ gridTemplateColumns: '120px 1fr 140px 140px 120px' }}>
            <span>Ruta</span>
            <span>Repartidor</span>
            <span>Fecha</span>
            <span>Efectivo esperado</span>
            <span>Acción</span>
          </div>
          {pendientes.map((r) => (
            <div className="manifest-row" key={r.rutaId} style={{ gridTemplateColumns: '120px 1fr 140px 140px 120px' }}>
              <span className="tag-id" data-label="Ruta">{r.codigo}</span>
              <span className="cell-primary" data-label="Repartidor">{r.repartidorNombre || `#${r.repartidorId}`}</span>
              <span className="cell-mono" data-label="Fecha">{r.fecha ? new Date(r.fecha).toLocaleDateString('es-PE') : '—'}</span>
              <span className="amount" data-label="Esperado">S/ {Number(r.montoEsperado).toFixed(2)}</span>
              <div className="row-actions" data-label="Acción">
                <button className="btn-xs" onClick={() => abrirLiquidacion(r)}>Liquidar</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Recaudos onAviso={mostrarMensaje} />
      <CarteraCredito onAviso={mostrarMensaje} />
      <CierreCaja key={mensaje ? 'tras-aviso' : 'base'} onAviso={mostrarMensaje} />

      <div className="filters">
        <button className={`filter-pill${filtro === '' ? ' active' : ''}`} onClick={() => cambiarFiltro('')}>Todos</button>
        <button className={`filter-pill${filtro === 'pendiente' ? ' active' : ''}`} onClick={() => cambiarFiltro('pendiente')}>Pendientes</button>
        <button className={`filter-pill${filtro === 'pagado' ? ' active' : ''}`} onClick={() => cambiarFiltro('pagado')}>Pagados</button>
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando pagos…</p>
      ) : pagos.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>No hay pagos aquí todavía</h3>
            <p>Se registran desde la página de Pedidos cuando un pedido ya fue entregado.</p>
          </div>
        </div>
      ) : (
        <div className="manifest">
          <div className="manifest-row head" style={{ gridTemplateColumns: '90px 1fr 120px 120px 130px 130px' }}>
            <span>Pago</span>
            <span>Pedido</span>
            <span>Monto</span>
            <span>Método</span>
            <span>Estado</span>
            <span>Acción</span>
          </div>
          {pagos.map((pago) => (
            <div className="manifest-row" key={pago.id} style={{ gridTemplateColumns: '90px 1fr 120px 120px 130px 130px' }}>
              <span className="tag-id" data-label="Pago">#{pago.id}</span>
              <span className="cell-mono" data-label="Pedido">#{String(pago.pedidoId).padStart(5, '0')}</span>
              <span className="amount" data-label="Monto">S/ {Number(pago.monto).toFixed(2)}</span>
              <span data-label="Método" style={{ textTransform: 'capitalize' }}>{pago.metodo}</span>
              <span data-label="Estado">
                <span className="badge" style={{
                  color: pago.estadoPago === 'pagado' ? 'var(--st-entregado)' : 'var(--st-en_almacen)',
                  background: pago.estadoPago === 'pagado' ? 'var(--accent-soft)' : '#FBF3DC'
                }}>
                  {pago.estadoPago}
                </span>
              </span>
              <div className="row-actions" data-label="Acción">
                {pago.estadoPago === 'pendiente' && (
                  <button className="btn-xs" onClick={() => manejarMarcarPagado(pago.id)}>Marcar pagado</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!cargando && pagos.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
          <span className="cell-secondary">
            Página {paginacion.pagina || pagina} de {paginacion.totalPaginas || 1} · {paginacion.totalRegistros ?? pagos.length} pago(s) en total
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" disabled={pagina <= 1} onClick={() => setPagina((p) => Math.max(1, p - 1))}>
              ← Anterior
            </button>
            <button
              className="btn btn-secondary"
              disabled={pagina >= (paginacion.totalPaginas || 1)}
              onClick={() => setPagina((p) => p + 1)}
            >
              Siguiente →
            </button>
          </div>
        </div>
      )}

      {rutaALiquidar && (
        <Modal title={`Liquidar ruta ${rutaALiquidar.codigo}`} onClose={() => setRutaALiquidar(null)}>
          {errorLiquidacion && <div className="error-banner">{errorLiquidacion}</div>}
          <form onSubmit={manejarLiquidar}>
            <p className="cell-secondary">
              Efectivo cobrado según el sistema: <strong>S/ {Number(rutaALiquidar.montoEsperado).toFixed(2)}</strong>
            </p>
            <div className="field">
              <label htmlFor="montoEntregado">Efectivo que entregó el repartidor (S/)</label>
              <input
                id="montoEntregado" type="number" step="0.01" min="0" required
                value={formLiquidacion.montoEntregado}
                onChange={(e) => setFormLiquidacion((f) => ({ ...f, montoEntregado: e.target.value }))}
              />
            </div>
            {Math.abs(diferenciaLiquidacion) >= 0.005 && (
              <div className="error-banner">
                Diferencia de S/ {diferenciaLiquidacion.toFixed(2)}: explica el motivo abajo.
              </div>
            )}
            <div className="field">
              <label htmlFor="observacionLiquidacion">Observación</label>
              <textarea
                id="observacionLiquidacion" maxLength={1000}
                required={Math.abs(diferenciaLiquidacion) >= 0.005}
                value={formLiquidacion.observacion}
                onChange={(e) => setFormLiquidacion((f) => ({ ...f, observacion: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setRutaALiquidar(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={liquidando}>
                {liquidando ? 'Guardando…' : 'Registrar liquidación'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
