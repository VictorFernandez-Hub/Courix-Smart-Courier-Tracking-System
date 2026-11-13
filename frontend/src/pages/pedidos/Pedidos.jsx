import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import EscanerQR from '../../components/ui/EscanerQR'
import ComprobanteModal from './ComprobanteModal'
import { DevolucionModal, RedireccionModal, ReembolsoModal } from './AccionesExcepcion'
import EstadoBadge from '../../components/ui/EstadoBadge'
import Modal from '../../components/ui/Modal'
import {
  listarPedidos, listarEstados, listarClientes, getUsuario,
  cambiarEstadoPedido, crearPago, historialPedido,
  crearIncidencia, pedidosConPagoRegistrado, trazabilidadPedido,
  constanciaEntrega, regenerarPin, reporteSla, avisosDelPedido,
} from '../../api'

const FORM_PAGO_VACIO = { monto: '', metodo: 'efectivo', referencia: '', yaCobrado: true }

const ESTADOS_FINALES = ['entregado', 'devuelto', 'cancelado', 'extraviado']
const PUEDEN_EXTRAVIARSE = ['en_almacen', 'en_transito', 'en_agencia_destino', 'por_devolver']
// Donde se puede corregir la direccion (ver /pedido/<id>/redireccionar)
const REDIRECCIONABLES = ['pendiente', 'en_almacen', 'en_agencia_destino']
// Igual que TRANSICIONES_VALIDAS del backend: en transito, en camino o en
// devolucion el paquete existe fisicamente y no se "cancela"
const CANCELABLES = ['pendiente', 'en_almacen', 'en_agencia_destino', 'asignado', 'recogido', 'no_entregado']

const RELACIONES = { titular: 'El destinatario', familiar: 'Familiar', trabajador: 'Trabajador', porteria: 'Portería', otro: 'Otra persona' }

const AVISOS = { registrado: 'Envío registrado', en_camino: 'Sale a reparto', entregado: 'Entregado', no_entregado: 'No se pudo entregar' }

const MOVIMIENTOS = {
  admitido: 'Admitido en agencia',
  manifestado: 'Cargado en manifiesto',
  retirado_de_manifiesto: 'Retirado del manifiesto',
  despachado: 'Despachado',
  recibido_en_destino: 'Recibido en destino',
  faltante: 'Faltante en destino',
  recibido_tarde: 'Llegó después del cierre',
}

const MODALIDADES = {
  contra_entrega: 'Contra entrega',
  prepagado: 'Prepagado',
  credito: 'Crédito',
}

export default function Pedidos() {
  const usuario = getUsuario()
  const [pedidos, setPedidos] = useState([])
  const [estados, setEstados] = useState([])
  const [clientes, setClientes] = useState([])
  const [filtroEstado, setFiltroEstado] = useState('')
  // ?q= permite llegar ya filtrado desde otras pantallas (ej. inventario de agencia)
  const [params] = useSearchParams()
  const [busqueda, setBusqueda] = useState(() => params.get('q') || '')
  const [busquedaAplicada, setBusquedaAplicada] = useState(() => params.get('q') || '')
  const [pagina, setPagina] = useState(1)
  const [paginacion, setPaginacion] = useState({ totalPaginas: 1, totalRegistros: 0 })
  const [pedidosConPago, setPedidosConPago] = useState(new Set())
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const navigate = useNavigate()

  const [pedidoHistorial, setPedidoHistorial] = useState(null)
  const [eventosHistorial, setEventosHistorial] = useState([])
  const [cargandoHistorial, setCargandoHistorial] = useState(false)
  const [trazabilidad, setTrazabilidad] = useState([])
  const [soloAtrasados, setSoloAtrasados] = useState(false)
  const [sla, setSla] = useState(null)
  const [constancia, setConstancia] = useState(null)
  const [camara, setCamara] = useState(false)
  const [pedidoComprobante, setPedidoComprobante] = useState(null)
  const [excepcion, setExcepcion] = useState(null) // { tipo: devolucion|redireccion|reembolso, pedido, estado? }
  const [avisos, setAvisos] = useState([])
  // El QR trae el codigo del bulto (CE-XXXX-XXXX-2): se busca por la guia
  const buscarPorQr = useCallback((valor) => {
    setCamara(false)
    setBusqueda(valor.replace(/-\d+$/, ''))
  }, [])

  const [pedidoIncidencia, setPedidoIncidencia] = useState(null)
  const [formIncidencia, setFormIncidencia] = useState({ tipo: 'reclamo', descripcion: '' })
  const [errorIncidencia, setErrorIncidencia] = useState('')
  const [enviandoIncidencia, setEnviandoIncidencia] = useState(false)

  const [pedidoPago, setPedidoPago] = useState(null)
  const [formPago, setFormPago] = useState(FORM_PAGO_VACIO)
  const [enviandoPago, setEnviandoPago] = useState(false)
  const [errorPago, setErrorPago] = useState('')

  useEffect(() => {
    cargarListasBase()
  }, [])

  // Debounce: espera 400ms sin que el usuario escriba antes de disparar la
  // busqueda real, para no golpear el backend en cada tecla.
  useEffect(() => {
    const temporizador = setTimeout(() => {
      setPagina(1)
      setBusquedaAplicada(busqueda.trim())
    }, 400)
    return () => clearTimeout(temporizador)
  }, [busqueda])

  useEffect(() => {
    cargarPedidos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado, pagina, busquedaAplicada, soloAtrasados])

  // Auto-refresco: si dos personas tienen la pantalla abierta a la vez (un
  // operador y un repartidor moviendo el mismo pedido, por ejemplo), esto
  // evita que uno se quede viendo datos desactualizados por mucho tiempo
  // sin tener que recargar la pagina a mano.
  useEffect(() => {
    const intervalo = setInterval(cargarPedidos, 45000)
    return () => clearInterval(intervalo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado, pagina, busquedaAplicada])

  function cambiarFiltroEstado(nuevoEstado) {
    setPagina(1)
    setFiltroEstado(nuevoEstado)
  }

  function cargarListasBase() {
    listarEstados().then((r) => setEstados(r.content)).catch(() => {})
    listarClientes().then((r) => setClientes(r.content)).catch(() => {})
  }

  function cargarPedidos() {
    setCargando(true)
    setError('')
    reporteSla().then((r) => setSla(r.content)).catch(() => {})
    listarPedidos(filtroEstado || undefined, pagina, undefined, busquedaAplicada || undefined, soloAtrasados)
      .then((r) => {
        setPedidos(r.content)
        setPaginacion(r.paginacion)

        const idsConsultar = r.content.map((p) => p.id)
        if (idsConsultar.length > 0) {
          pedidosConPagoRegistrado(idsConsultar)
            .then((res) => setPedidosConPago(new Set(res.content)))
            .catch(() => {})
        } else {
          setPedidosConPago(new Set())
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function clienteNombre(id) {
    const c = clientes.find((c) => c.id === id)
    return c ? c.nombre : `Cliente #${id}`
  }

  function nombreEstado(estadoId) {
    const e = estados.find((e) => e.id === estadoId)
    return e ? e.nombre : filtroEstado || 'pendiente'
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  // Cambios de estado de la logistica inversa. Los que cierran el caso
  // (devuelto, extraviado) piden una constancia escrita.
  const ACCIONES = {
    asignado: { confirmar: (g) => `¿Reprogramar la entrega del envío ${g} con el mismo repartidor (en su ruta de hoy)?`, ok: 'Entrega reprogramada' },
    por_devolver: { confirmar: (g) => `¿Iniciar la devolución del envío ${g} al remitente? Ya no saldrá a reparto.`, ok: 'Devolución iniciada' },
    extraviado: { pedir: (g) => `Declarar ${g} como EXTRAVIADO (cierra el envío; corresponde indemnizar). ¿Qué se sabe del paquete?`, ok: 'Envío declarado extraviado' },
  }

  async function cambiarEstadoManual(p, destino) {
    const guia = p.codigoGuia || '#' + p.id
    const accion = ACCIONES[destino]
    let comentario
    if (accion.pedir) {
      comentario = window.prompt(accion.pedir(guia))
      if (comentario == null) return
      if (comentario.trim().length < 5) { setError('Escribe una constancia de al menos 5 caracteres'); return }
    } else if (!window.confirm(accion.confirmar(guia))) return
    setError('')
    try {
      await cambiarEstadoPedido(p.id, { estado: destino, comentario: comentario?.trim() || undefined })
      mostrarMensaje(accion.ok)
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  async function manejarCancelar(p) {
    if (!window.confirm(`¿Cancelar el pedido #${p.id}? Esta acción quedará registrada en su historial.`)) return
    setError('')
    try {
      await cambiarEstadoPedido(p.id, { estado: 'cancelado', comentario: 'Cancelado desde el panel de administración' })
      mostrarMensaje(`Pedido #${p.id} cancelado`)
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  function abrirModalPago(p) {
    setFormPago({ ...FORM_PAGO_VACIO, monto: String(p.monto) })
    setErrorPago('')
    setPedidoPago(p)
  }

  async function manejarEnvioPago(e) {
    e.preventDefault()
    setErrorPago('')
    setEnviandoPago(true)
    try {
      await crearPago({
        pedidoId: pedidoPago.id,
        monto: formPago.monto,
        metodo: formPago.metodo,
        referencia: formPago.referencia || undefined,
        estadoPago: formPago.yaCobrado ? 'pagado' : 'pendiente',
      })
      setPedidoPago(null)
      mostrarMensaje(`Pago registrado para el pedido #${pedidoPago.id}`)
      cargarPedidos()
    } catch (err) {
      setErrorPago(err.message)
    } finally {
      setEnviandoPago(false)
    }
  }

  function abrirHistorial(p) {
    setPedidoHistorial(p)
    setCargandoHistorial(true)
    setTrazabilidad([])
    setAvisos([])
    trazabilidadPedido(p.id).then((r) => setTrazabilidad(r.content)).catch(() => {})
    avisosDelPedido(p.id).then((r) => setAvisos(r.content)).catch(() => {})
    historialPedido(p.id)
      .then((r) => setEventosHistorial(r.content))
      .catch(() => setEventosHistorial([]))
      .finally(() => setCargandoHistorial(false))
  }

  async function verConstancia(p) {
    try {
      const r = await constanciaEntrega(p.id)
      setConstancia({ pedido: p, ...r.content })
    } catch (err) {
      setError(err.message)
    }
  }

  async function nuevoPin(p) {
    if (!window.confirm(`¿Generar un nuevo código de entrega para ${p.codigoGuia}? El anterior dejará de servir.`)) return
    try {
      const r = await regenerarPin(p.id)
      window.alert(`Nuevo código de entrega para ${p.codigoGuia}: ${r.content.pinEntrega}\n\nDáselo al remitente o al destinatario. No se volverá a mostrar.`)
      cargarPedidos()
    } catch (err) {
      setError(err.message)
    }
  }

  function abrirIncidencia(p) {
    setFormIncidencia({ tipo: 'reclamo', descripcion: '' })
    setErrorIncidencia('')
    setPedidoIncidencia(p)
  }

  async function manejarEnvioIncidencia(e) {
    e.preventDefault()
    setErrorIncidencia('')
    setEnviandoIncidencia(true)
    try {
      await crearIncidencia(pedidoIncidencia.id, formIncidencia)
      setPedidoIncidencia(null)
      mostrarMensaje(`Incidencia registrada para el pedido #${pedidoIncidencia.id}`)
    } catch (err) {
      setErrorIncidencia(err.message)
    } finally {
      setEnviandoIncidencia(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Pedidos</h1>
          <p className="page-sub">{pedidos.length} pedido{pedidos.length !== 1 ? 's' : ''} en esta vista</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/pedidos/nuevo')}>+ Nuevo envío</button>
      </div>

      <div className="filters">
        <button
          className={`filter-pill${filtroEstado === '' ? ' active' : ''}`}
          onClick={() => cambiarFiltroEstado('')}
        >
          Todos
        </button>
        {estados.map((e) => (
          <button
            key={e.id}
            className={`filter-pill${filtroEstado === e.nombre ? ' active' : ''}`}
            onClick={() => cambiarFiltroEstado(e.nombre)}
          >
            {e.nombre.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="field buscador-con-camara" style={{ maxWidth: 420, marginBottom: 12 }}>
        <button type="button" className="btn btn-secondary" onClick={() => setCamara(true)} title="Buscar escaneando el QR de la etiqueta">📷</button>
        <input
          type="search" aria-label="Buscar pedidos"
          placeholder="Buscar por código de guía, cliente o teléfono…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
      </div>

      {sla && sla.atrasados > 0 && (
        <div className="error-banner sla-aviso">
          <span><strong>{sla.atrasados}</strong> envío(s) pasaron su fecha comprometida de entrega
            {sla.vencenHoy > 0 && <> · <strong>{sla.vencenHoy}</strong> vencen hoy</>}.</span>
          <button className="btn-xs" onClick={() => { setPagina(1); setSoloAtrasados((v) => !v) }}>
            {soloAtrasados ? 'Ver todos' : 'Ver atrasados'}
          </button>
        </div>
      )}
      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando pedidos…</p>
      ) : pedidos.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>No hay pedidos aquí todavía</h3>
            <p>{busquedaAplicada || filtroEstado
              ? 'Nadie coincide con este filtro o búsqueda. Prueba con otro término.'
              : 'Registra el primero con "Nuevo envío".'}</p>
          </div>
        </div>
      ) : (
        <div className="manifest">
          <div className="manifest-row head">
            <span>Pedido</span>
            <span>Destinatario</span>
            <span>Producto</span>
            <span>Estado</span>
            <span>Monto</span>
            <span>Fecha</span>
            <span>Acciones</span>
          </div>
          {pedidos.map((p) => {
            const nombre = nombreEstado(p.estadoId)
            const esFinal = ESTADOS_FINALES.includes(nombre)
            return (
              <div className="manifest-row" key={p.id}>
                <span className="tag-id" data-label="Pedido">{p.codigoGuia || `#${String(p.id).padStart(5, '0')}`}</span>
                <span className="cell-primary" data-label="Destinatario">{clienteNombre(p.clienteId)}</span>
                <div data-label="Producto">
                  <div>{p.descripcionProducto || '—'}</div>
                  {p.notas && <div className="cell-secondary">{p.notas}</div>}
                </div>
                <span data-label="Estado"><EstadoBadge estado={nombre} /></span>
                <div data-label="Monto">
                  <div className="amount">S/ {Number(p.monto).toFixed(2)}</div>
                  <div className="cell-secondary">{MODALIDADES[p.modalidadPago] || p.modalidadPago}</div>
                  {Number(p.montoRecaudo) > 0 && (
                    <div className="cell-secondary" title="Precio del producto que se cobra por cuenta del remitente">
                      + Recaudo S/ {Number(p.montoRecaudo).toFixed(2)}
                    </div>
                  )}
                </div>
                <span className="cell-mono" data-label="Fecha">{new Date(p.fechaCreacion).toLocaleDateString('es-PE')}</span>
                <div className="row-actions">
                  {nombre === 'pendiente' && (
                    <button className="btn-xs" onClick={() => navigate(`/pedidos/${p.id}/recibir`)}>Recibir en agencia</button>
                  )}
                  {nombre === 'no_entregado' && (
                    <>
                      <button className="btn-xs" onClick={() => cambiarEstadoManual(p, 'asignado')}>Reprogramar</button>
                      <button className="btn-xs" onClick={() => cambiarEstadoManual(p, 'por_devolver')}>Devolver al remitente</button>
                    </>
                  )}
                  {(nombre === 'en_almacen' || nombre === 'en_agencia_destino') && (
                    <button className="btn-xs" onClick={() => cambiarEstadoManual(p, 'por_devolver')}>Devolver al remitente</button>
                  )}
                  {(REDIRECCIONABLES.includes(nombre) || (nombre === 'por_devolver' && !p.retornoAlOrigen)) && (
                    <button className="btn-xs" onClick={() => setExcepcion({ tipo: 'redireccion', pedido: p })}>Corregir dirección</button>
                  )}
                  {usuario?.rol === 'admin' && ['cancelado', 'extraviado', 'entregado'].includes(nombre) && (
                    <button className="btn-xs" onClick={() => setExcepcion({ tipo: 'reembolso', pedido: p, estado: nombre })}>
                      {nombre === 'entregado' ? 'Indemnizar' : 'Devolver dinero'}
                    </button>
                  )}
                  {nombre === 'por_devolver' && (p.retornoAlOrigen || (p.agenciaDestinoId ?? p.almacenId) === p.almacenId ? (
                    <button className="btn-xs" onClick={() => setExcepcion({ tipo: 'devolucion', pedido: p })}>Entregar al remitente</button>
                  ) : (
                    <button className="btn-xs" onClick={() => navigate('/despachos')} title="Debe volver a la agencia de origen en un manifiesto">
                      Despachar de regreso
                    </button>
                  ))}
                  {usuario?.rol === 'admin' && PUEDEN_EXTRAVIARSE.includes(nombre) && (
                    <button className="btn-xs danger" onClick={() => cambiarEstadoManual(p, 'extraviado')}>Extraviado</button>
                  )}
                  {pedidosConPago.has(p.id) ? (
                    <span className="cell-secondary">✓ Pago registrado</span>
                  ) : nombre !== 'cancelado' && (nombre === 'entregado' || p.modalidadPago !== 'contra_entrega') && (
                    <button className="btn-xs" onClick={() => abrirModalPago(p)}>Registrar pago</button>
                  )}
                  {usuario?.rol === 'admin' && CANCELABLES.includes(nombre) && (
                    <button className="btn-xs danger" onClick={() => manejarCancelar(p)}>Cancelar</button>
                  )}
                  {nombre !== 'pendiente' && nombre !== 'cancelado' && (
                    <button className="btn-xs" onClick={() => navigate(`/pedidos/${p.id}/etiqueta`)}>Etiqueta</button>
                  )}
                  {nombre === 'entregado' && (
                    <button className="btn-xs" onClick={() => verConstancia(p)}>Constancia</button>
                  )}
                  {pedidosConPago.has(p.id) && (
                    <button className="btn-xs" onClick={() => setPedidoComprobante(p)}>Comprobante</button>
                  )}
                  {p.requierePin && !esFinal && (
                    <button className="btn-xs" onClick={() => nuevoPin(p)}>Nuevo PIN</button>
                  )}
                  <button className="btn-xs" onClick={() => abrirHistorial(p)}>Historial</button>
                  <button className="btn-xs" onClick={() => abrirIncidencia(p)}>Reportar incidencia</button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!cargando && pedidos.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
          <span className="cell-secondary">
            Página {paginacion.pagina || pagina} de {paginacion.totalPaginas || 1} · {paginacion.totalRegistros ?? pedidos.length} pedido(s) en total
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-secondary"
              disabled={pagina <= 1}
              onClick={() => setPagina((p) => Math.max(1, p - 1))}
            >
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

      {pedidoPago && (
        <Modal title={`Registrar pago — Pedido #${pedidoPago.id}`} onClose={() => setPedidoPago(null)}>
          {errorPago && <div className="error-banner">{errorPago}</div>}
          <form onSubmit={manejarEnvioPago}>
            <div className="field">
              <label htmlFor="montoPago">Monto (S/)</label>
              <input
                id="montoPago" type="number" step="0.01" min="0" required
                value={formPago.monto}
                onChange={(e) => setFormPago((f) => ({ ...f, monto: e.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="metodoPago">Método de pago</label>
              <select
                id="metodoPago"
                value={formPago.metodo}
                onChange={(e) => setFormPago((f) => ({ ...f, metodo: e.target.value }))}
              >
                <option value="efectivo">Efectivo</option>
                <option value="yape">Yape</option>
                <option value="plin">Plin</option>
                <option value="tarjeta">Tarjeta</option>
                <option value="transferencia">Transferencia</option>
              </select>
            </div>
            {formPago.metodo !== 'efectivo' && (
              <div className="field">
                <label htmlFor="referenciaPago">N.º de operación</label>
                <input
                  id="referenciaPago" maxLength={60} required={formPago.yaCobrado}
                  value={formPago.referencia}
                  onChange={(e) => setFormPago((f) => ({ ...f, referencia: e.target.value }))}
                />
              </div>
            )}
            <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <input
                id="yaCobrado" type="checkbox"
                style={{ width: 'auto' }}
                checked={formPago.yaCobrado}
                onChange={(e) => setFormPago((f) => ({ ...f, yaCobrado: e.target.checked }))}
              />
              <label htmlFor="yaCobrado" style={{ margin: 0 }}>El dinero ya se recibió</label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoPago(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoPago}>
                {enviandoPago ? 'Guardando…' : 'Registrar pago'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pedidoHistorial && (
        <Modal title={`Historial — Pedido #${pedidoHistorial.id}`} onClose={() => setPedidoHistorial(null)}>
          {cargandoHistorial ? (
            <p className="loading-text">Cargando historial…</p>
          ) : eventosHistorial.length === 0 ? (
            <p className="cell-secondary">Sin eventos registrados.</p>
          ) : (
            <div>
              {eventosHistorial.map((ev) => (
                <div className="timeline-item" key={ev.id}>
                  <div className="timeline-dot" />
                  <div>
                    <div className="cell-secondary">{new Date(ev.fecha).toLocaleString('es-PE')}</div>
                    {ev.comentario && <div style={{ marginTop: 2 }}>{ev.comentario}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {avisos.length > 0 && (
            <>
              <div className="section-title">Avisos al destinatario</div>
              <table className="tabla-manifiesto">
                <thead><tr><th>Aviso</th><th>Canal</th><th>Estado</th></tr></thead>
                <tbody>
                  {avisos.map((a, i) => (
                    <tr key={i}>
                      <td>{AVISOS[a.evento] || a.evento}</td>
                      <td>{a.canal === 'whatsapp' ? 'WhatsApp' : 'Correo'}</td>
                      <td title={a.error || ''}>
                        {a.estado === 'enviado' ? `✓ Enviado${a.fecha ? ' ' + new Date(a.fecha).toLocaleString('es-PE') : ''}`
                          : a.estado === 'fallido' ? `✗ Falló (${a.intentos} intento/s)` : 'Pendiente'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {trazabilidad.length > 0 && (
            <>
              <div className="section-title">Movimientos de los bultos</div>
              <table className="tabla-manifiesto">
                <thead><tr><th>Fecha</th><th>Bulto</th><th>Movimiento</th><th>Dónde</th></tr></thead>
                <tbody>
                  {trazabilidad.map((t, i) => (
                    <tr key={i}>
                      <td className="cell-secondary">{new Date(t.fecha).toLocaleString('es-PE')}</td>
                      <td className="cell-mono">{t.bulto}</td>
                      <td>{MOVIMIENTOS[t.tipo] || t.tipo}{t.manifiesto ? ` (${t.manifiesto})` : ''}</td>
                      <td>{t.agencia || '—'}{t.usuario ? <span className="cell-secondary"> · {t.usuario}</span> : null}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </Modal>
      )}

      {camara && <EscanerQR onLeer={buscarPorQr} onCerrar={() => setCamara(false)} titulo="Buscar envío por QR" />}
      {pedidoComprobante && <ComprobanteModal pedido={pedidoComprobante} onCerrar={() => setPedidoComprobante(null)} />}
      {excepcion && (() => {
        const props = {
          pedido: excepcion.pedido, estado: excepcion.estado, onClose: () => setExcepcion(null),
          onHecho: (texto) => { setExcepcion(null); mostrarMensaje(texto); cargarPedidos() },
        }
        if (excepcion.tipo === 'devolucion') return <DevolucionModal {...props} />
        if (excepcion.tipo === 'redireccion') return <RedireccionModal {...props} />
        return <ReembolsoModal {...props} />
      })()}

      {constancia && (
        <Modal title={`Constancia de entrega — ${constancia.pedido.codigoGuia}`} onClose={() => setConstancia(null)}>
          <div className="dato-lista">
            <div><span>Recibió</span><strong>{constancia.nombreReceptor}</strong></div>
            <div><span>Documento</span><strong className="cell-mono">{constancia.dniReceptor}</strong></div>
            <div><span>Relación</span><strong>{RELACIONES[constancia.relacion] || constancia.relacion}</strong></div>
            <div><span>Código (PIN)</span><strong>{constancia.pinVerificado ? '✓ Verificado' : 'No aplicaba'}</strong></div>
            <div><span>Fecha</span><strong>{constancia.fecha ? new Date(constancia.fecha).toLocaleString('es-PE') : '—'}</strong></div>
            {constancia.latitud != null && (
              <div><span>Ubicación</span><a href={`https://www.google.com/maps?q=${constancia.latitud},${constancia.longitud}`}
                target="_blank" rel="noopener noreferrer">Ver en el mapa</a></div>
            )}
          </div>
          {constancia.firma && (
            <>
              <div className="section-title">Firma</div>
              <img src={constancia.firma} alt={`Firma de ${constancia.nombreReceptor}`} className="firma-imagen" />
            </>
          )}
          {constancia.foto && (
            <>
              <div className="section-title">Foto de evidencia</div>
              <img src={constancia.foto} alt="Foto de la entrega" style={{ maxWidth: '100%', borderRadius: 6 }} />
            </>
          )}
        </Modal>
      )}

      {pedidoIncidencia && (
        <Modal title={`Reportar incidencia — Pedido #${pedidoIncidencia.id}`} onClose={() => setPedidoIncidencia(null)}>
          {errorIncidencia && <div className="error-banner">{errorIncidencia}</div>}
          <form onSubmit={manejarEnvioIncidencia}>
            <div className="field">
              <label htmlFor="tipoIncidencia">Tipo</label>
              <select
                id="tipoIncidencia"
                value={formIncidencia.tipo}
                onChange={(e) => setFormIncidencia((f) => ({ ...f, tipo: e.target.value }))}
              >
                <option value="reclamo">Reclamo</option>
                <option value="producto_danado">Producto dañado</option>
                <option value="direccion_incorrecta">Dirección incorrecta</option>
                <option value="retraso">Retraso</option>
                <option value="otro">Otro</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="descripcionIncidencia">Descripción</label>
              <textarea
                id="descripcionIncidencia" required
                placeholder="Ej. El cliente reporta que el paquete llegó abierto"
                value={formIncidencia.descripcion}
                onChange={(e) => setFormIncidencia((f) => ({ ...f, descripcion: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoIncidencia(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviandoIncidencia}>
                {enviandoIncidencia ? 'Guardando…' : 'Reportar'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
