import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import {
  getUsuario, listarRepartidores, rutaActivaDeRepartidor,
  listarPedidosDisponibles, agregarPedidoARuta, tomarPedido, quitarPedidoDeRuta,
  cambiarEstadoPedido, entregarYCobrar, iniciarRuta, completarRuta,
  cambiarDisponibilidadRepartidor,
} from '../../api'
import { comprimirImagen } from '../../utils/imagen'
import FirmaPad from '../../components/ui/FirmaPad.jsx'
import RecojosRepartidor from './RecojosRepartidor.jsx'

// Que boton(es) mostrar segun el estado actual del pedido. "asignado" salta
// directo a "en_camino" (ya no exige el paso intermedio de "recogido").
function accionesDisponibles(estado) {
  switch (estado) {
    case 'asignado':
      return [{ label: 'Salir a entregar', destino: 'en_camino', clase: 'btn-primary' }]
    case 'recogido': // por compatibilidad con pedidos antiguos que ya estaban en este paso
      return [{ label: 'Salir a entregar', destino: 'en_camino', clase: 'btn-primary' }]
    case 'no_entregado':
      return [{ label: 'Reintentar entrega', destino: 'asignado', clase: 'btn-primary' }]
    default:
      return []
  }
}

const MOTIVOS_NO_ENTREGA = {
  cliente_ausente: 'Cliente ausente',
  direccion_incorrecta: 'Dirección incorrecta',
  rechazado: 'El cliente rechazó el paquete',
  zona_inaccesible: 'Zona inaccesible / insegura',
  reprogramado: 'El cliente pidió otra fecha',
  otro: 'Otro motivo',
}

// Constancia de entrega: quien recibe, su DNI y su firma (y el PIN si el envio lo exige)
const COBRO_VACIO = {
  metodo: 'efectivo', referencia: '', foto: null,
  nombreReceptor: '', dniReceptor: '', relacion: 'titular', firma: null, pin: '',
}
const RELACIONES = { titular: 'El destinatario', familiar: 'Familiar', trabajador: 'Trabajador / compañero', porteria: 'Portería / conserje', otro: 'Otra persona' }

function obtenerUbicacion() {
  // La ubicacion acompana la constancia; si el celular no la da, se entrega igual
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({})
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitud: pos.coords.latitude, longitud: pos.coords.longitude }),
      () => resolve({}),
      { timeout: 4000, maximumAge: 60000 },
    )
  })
}

export default function MiRuta() {
  const usuario = getUsuario()
  const [miRepartidor, setMiRepartidor] = useState(null)
  const [ruta, setRuta] = useState(null)
  const [pool, setPool] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [procesando, setProcesando] = useState(false)

  const [pedidoACobrar, setPedidoACobrar] = useState(null)
  const [formCobro, setFormCobro] = useState(COBRO_VACIO)
  const [errorCobro, setErrorCobro] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [pedidoNoEntregado, setPedidoNoEntregado] = useState(null)
  const [formNoEntregado, setFormNoEntregado] = useState({ motivo: 'cliente_ausente', comentario: '' })
  const [cambiandoDisponibilidad, setCambiandoDisponibilidad] = useState(false)

  async function manejarToggleDisponibilidad() {
    setCambiandoDisponibilidad(true)
    setError('')
    try {
      const res = await cambiarDisponibilidadRepartidor(miRepartidor.id, !miRepartidor.disponible)
      setMiRepartidor(res.content)
    } catch (err) {
      setError(err.message)
    } finally {
      setCambiandoDisponibilidad(false)
    }
  }

  useEffect(() => {
    inicializar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // El pool de pedidos disponibles cambia todo el tiempo (otros repartidores
  // van tomando pedidos); refrescar solo al montar dejaria la vista
  // desactualizada durante todo el turno.
  useEffect(() => {
    if (!miRepartidor) return
    const intervalo = setInterval(() => cargarRuta(miRepartidor), 30000)
    return () => clearInterval(intervalo)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [miRepartidor])

  async function inicializar() {
    setCargando(true)
    setError('')
    try {
      const resRepartidores = await listarRepartidores()
      const perfil = resRepartidores.content.find((r) => r.usuarioId === usuario.id)

      if (!perfil) {
        setError('Tu perfil de repartidor todavia no ha sido configurado. Contacta a un administrador.')
        return
      }
      setMiRepartidor(perfil)
      await cargarRuta(perfil)
    } catch (err) {
      setError(err.message)
    } finally {
      setCargando(false)
    }
  }

  async function cargarRuta(perfil) {
    try {
      const res = await rutaActivaDeRepartidor(perfil.id)
      setRuta(res.content)
    } catch (err) {
      if (err.status === 404) {
        setRuta(null)
      } else {
        setError(err.message)
      }
    }
    if (perfil.zonaId) {
      listarPedidosDisponibles(perfil.zonaId).then((r) => setPool(r.content)).catch(() => setPool([]))
    }
  }

  // Simplificacion: ya no hace falta "crear mi ruta" como paso aparte.
  // Si todavia no tienes una ruta activa, tomar tu primer pedido la crea sola.
  async function manejarTomarPedido(pedidoId) {
    setProcesando(true)
    setError('')
    try {
      if (ruta) {
        await agregarPedidoARuta(ruta.rutaId, pedidoId)
      } else {
        await tomarPedido(pedidoId, miRepartidor.id)
      }
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarQuitarPedido(pedidoId) {
    setProcesando(true)
    setError('')
    try {
      await quitarPedidoDeRuta(ruta.rutaId, pedidoId)
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarCambioEstado(pedidoId, nuevoEstado) {
    setProcesando(true)
    setError('')
    try {
      await cambiarEstadoPedido(pedidoId, { estado: nuevoEstado })
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarNoEntregado(e) {
    e.preventDefault()
    setProcesando(true)
    setError('')
    try {
      await cambiarEstadoPedido(pedidoNoEntregado.pedidoId, {
        estado: 'no_entregado',
        motivo: formNoEntregado.motivo,
        comentario: formNoEntregado.comentario || undefined,
      })
      setPedidoNoEntregado(null)
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
      setPedidoNoEntregado(null)
    } finally {
      setProcesando(false)
    }
  }

  function abrirCobro(pedido) {
    setFormCobro({ ...COBRO_VACIO, nombreReceptor: pedido.cliente?.nombre || '' })
    setErrorCobro('')
    setPedidoACobrar(pedido)
  }

  // Lo que se cobra en la puerta: flete contra entrega + precio del producto (recaudo)
  const totalCobro = (p) => Number(p?.totalACobrar ?? (p?.modalidadPago === 'contra_entrega' ? p?.monto : 0)) || 0
  const debeCobrar = totalCobro(pedidoACobrar) > 0
  const recaudoCobro = Number(pedidoACobrar?.montoRecaudo) || 0

  function manejarSeleccionFoto(e) {
    const archivo = e.target.files?.[0]
    if (!archivo) return
    comprimirImagen(archivo)
      .then((dataUrl) => setFormCobro((f) => ({ ...f, foto: dataUrl })))
      .catch(() => setErrorCobro('No se pudo procesar la foto, intenta con otra'))
  }

  async function manejarEntregarYCobrar(e) {
    e.preventDefault()
    setErrorCobro('')
    setProcesando(true)
    try {
      if (!formCobro.firma) {
        setErrorCobro('Falta la firma de quien recibe')
        return
      }
      const constancia = {
        nombreReceptor: formCobro.nombreReceptor.trim(),
        dniReceptor: formCobro.dniReceptor.trim(),
        relacionReceptor: formCobro.relacion,
        firma: formCobro.firma,
        pin: pedidoACobrar.requierePin ? formCobro.pin.trim() : undefined,
        evidenciaEntrega: formCobro.foto || undefined,
        ...(await obtenerUbicacion()),
      }
      await entregarYCobrar(pedidoACobrar.pedidoId, debeCobrar ? {
        ...constancia,
        monto: pedidoACobrar.monto,
        montoRecaudo: recaudoCobro > 0 ? pedidoACobrar.montoRecaudo : undefined,
        metodo: formCobro.metodo,
        referencia: formCobro.referencia || undefined,
      } : constancia)
      setPedidoACobrar(null)
      await cargarRuta(miRepartidor)
    } catch (err) {
      setErrorCobro(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarIniciar() {
    setProcesando(true)
    try {
      await iniciarRuta(ruta.rutaId)
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  async function manejarCompletar() {
    setProcesando(true)
    try {
      const res = await completarRuta(ruta.rutaId)
      setMensaje(res.message)
      setRuta(null)
      await cargarRuta(miRepartidor)
    } catch (err) {
      setError(err.message)
    } finally {
      setProcesando(false)
    }
  }

  if (cargando) return <p className="loading-text">Cargando tu ruta…</p>

  if (error && !miRepartidor) {
    return (
      <div>
        <h1>Mi Ruta</h1>
        <div className="error-banner" style={{ marginTop: 14 }}>{error}</div>
      </div>
    )
  }

  // Los "no entregado" no impiden cerrar: al completar la ruta vuelven a la agencia
  const pedidosPendientesDeEntrega = ruta
    ? ruta.pedidos.filter((p) => ['asignado', 'recogido', 'en_camino'].includes(p.estado)).length
    : 0
  const noEntregadosEnRuta = ruta ? ruta.pedidos.filter((p) => p.estado === 'no_entregado').length : 0

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Mi Ruta</h1>
          <p className="page-sub">Zona asignada: #{miRepartidor?.zonaId}</p>
        </div>
        {miRepartidor && (
          <button
            className={`btn ${miRepartidor.disponible ? 'btn-secondary' : 'btn-primary'}`}
            onClick={manejarToggleDisponibilidad}
            disabled={cambiandoDisponibilidad}
            title="Mientras estés 'no disponible' no te llegarán pedidos nuevos, pero conservas los que ya tienes asignados"
          >
            {miRepartidor.disponible ? '🟢 Disponible — tocar para pausar' : '⚪ No disponible — tocar para activarte'}
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {mensaje && <div className="success-banner">{mensaje}</div>}

      {miRepartidor && !miRepartidor.disponible && (
        <div className="error-banner" style={{ background: 'color-mix(in srgb, var(--ink-faint) 10%, white)', color: 'var(--ink)' }}>
          Estás marcado como <strong>no disponible</strong>: no puedes tomar pedidos nuevos del pool hasta que te actives de nuevo. Aún puedes seguir entregando los que ya tenías asignados.
        </div>
      )}

      <RecojosRepartidor />

      {ruta && (
        <div className="ruta-header">
          <div>
            <div className="ruta-codigo">{ruta.codigo}</div>
            <div className="ruta-estado-label">
              {ruta.estado.replace('_', ' ')} · {ruta.totalPedidos} pedido{ruta.totalPedidos !== 1 ? 's' : ''}
              {Number(ruta.efectivoCobrado) > 0 && <> · Efectivo cobrado: S/ {Number(ruta.efectivoCobrado).toFixed(2)}</>}
            </div>
          </div>
          {ruta.estado === 'planificada' ? (
            <button className="btn btn-primary" onClick={manejarIniciar} disabled={procesando}>Iniciar ruta</button>
          ) : (
            <button
              className="btn btn-secondary"
              onClick={manejarCompletar}
              disabled={procesando || pedidosPendientesDeEntrega > 0}
              title={pedidosPendientesDeEntrega > 0 ? 'Todavia hay pedidos sin entregar'
                : noEntregadosEnRuta > 0 ? `Al completar, entrega ${noEntregadosEnRuta} paquete(s) no entregado(s) en la agencia` : ''}
            >
              Completar ruta
            </button>
          )}
        </div>
      )}

      {ruta && ruta.pedidos.length > 0 && ruta.pedidos.map((p) => (
        <div className="route-card" key={p.pedidoId}>
          <div className="route-card-top">
            <div>
              <div className="route-card-cliente">{p.cliente?.nombre}</div>
              <div className="cell-secondary cell-mono">
                {p.codigoGuia}
                {p.intentosEntrega > 0 && <> · Intentos fallidos: {p.intentosEntrega}</>}
              </div>
            </div>
            <span className="badge" style={{ color: `var(--st-${p.estado}, var(--ink-faint))`, background: `color-mix(in srgb, var(--st-${p.estado}, var(--ink-faint)) 14%, white)` }}>
              {p.estado?.replace('_', ' ')}
            </span>
          </div>
          <div className="route-card-info">
            <div>📍 {p.direccionEntrega?.calle}{p.direccionEntrega?.referencia ? ` — ${p.direccionEntrega.referencia}` : ''}</div>
            <div>📞 <span className="cell-mono">{p.cliente?.telefono}</span></div>
            <div>📦 {p.descripcionProducto || 'Sin descripción'}{p.bultos > 1 && <> · <strong>{p.bultos} bultos</strong></>}</div>
            {p.requierePin && <div>🔐 Entrega con código: pide el PIN al destinatario</div>}
            <div>💵 {totalCobro(p) > 0
              ? <>Cobrar <strong>S/ {totalCobro(p).toFixed(2)}</strong> al entregar
                {Number(p.montoRecaudo) > 0 && <span className="cell-secondary"> (incluye S/ {Number(p.montoRecaudo).toFixed(2)} del producto)</span>}</>
              : 'Ya pagado / a crédito — no cobrar'}</div>
            {p.notas && <div className="cell-secondary">Nota: {p.notas}</div>}
          </div>
          <div className="route-card-actions">
            {accionesDisponibles(p.estado).map((accion) => (
              <button
                key={accion.destino}
                className={`btn ${accion.clase} btn-lg`}
                disabled={procesando}
                onClick={() => manejarCambioEstado(p.pedidoId, accion.destino)}
              >
                {accion.label}
              </button>
            ))}
            {p.estado === 'en_camino' && (
              <>
                <button className="btn btn-success btn-lg" disabled={procesando} onClick={() => abrirCobro(p)}>
                  {totalCobro(p) > 0 ? 'Entregar y cobrar' : 'Entregar'}
                </button>
                <button
                  className="btn btn-warning btn-lg" disabled={procesando}
                  onClick={() => { setFormNoEntregado({ motivo: 'cliente_ausente', comentario: '' }); setPedidoNoEntregado(p) }}
                >
                  No pude entregar
                </button>
              </>
            )}
            {p.estado === 'asignado' && (
              <button className="btn btn-ghost" disabled={procesando} onClick={() => manejarQuitarPedido(p.pedidoId)}>
                Quitar de mi ruta
              </button>
            )}
          </div>
        </div>
      ))}

      <div className="section-title" style={{ marginTop: ruta ? undefined : 0 }}>Pedidos disponibles en tu zona</div>
      {pool.length === 0 ? (
        <p className="cell-secondary">No hay pedidos esperando en tu zona por ahora.</p>
      ) : (
        pool.map((p) => (
          <div className="pool-item" key={p.id}>
            <div>
              <div className="cell-primary">{p.descripcionProducto || `Pedido #${p.id}`}</div>
              <div className="cell-secondary">S/ {Number(p.monto).toFixed(2)}</div>
            </div>
            <button
              className="btn btn-primary"
              disabled={procesando || !miRepartidor?.disponible}
              title={!miRepartidor?.disponible ? 'Actívate como disponible para poder tomar pedidos' : ''}
              onClick={() => manejarTomarPedido(p.id)}
            >
              + Tomar
            </button>
          </div>
        ))
      )}

      {pedidoACobrar && (
        <Modal
          title={`${debeCobrar ? 'Entregar y cobrar' : 'Registrar entrega'} — ${pedidoACobrar.codigoGuia || '#' + pedidoACobrar.pedidoId}`}
          onClose={() => setPedidoACobrar(null)}
        >
          {errorCobro && <div className="error-banner">{errorCobro}</div>}
          <form onSubmit={manejarEntregarYCobrar}>
            {debeCobrar ? (
              <>
                <div className="field">
                  <label>Monto a cobrar</label>
                  <div className="amount" style={{ fontSize: 24 }}>S/ {totalCobro(pedidoACobrar).toFixed(2)}</div>
                  {recaudoCobro > 0 && (
                    <p className="cell-secondary" style={{ marginTop: 4 }}>
                      Producto (por cuenta del remitente): S/ {recaudoCobro.toFixed(2)}
                      {totalCobro(pedidoACobrar) > recaudoCobro && <> · Envío: S/ {(totalCobro(pedidoACobrar) - recaudoCobro).toFixed(2)}</>}
                    </p>
                  )}
                  <p className="cell-secondary" style={{ marginTop: 4 }}>
                    Cobra el monto exacto. Si el cliente no puede pagarlo, no confirmes la entrega y reporta el problema.
                  </p>
                </div>
                <div className="field">
                  <label htmlFor="metodoCobro">Método de pago</label>
                  <select
                    id="metodoCobro"
                    value={formCobro.metodo}
                    onChange={(e) => setFormCobro((f) => ({ ...f, metodo: e.target.value }))}
                  >
                    <option value="efectivo">Efectivo</option>
                    <option value="yape">Yape</option>
                    <option value="plin">Plin</option>
                    <option value="tarjeta">Tarjeta</option>
                    <option value="transferencia">Transferencia</option>
                  </select>
                </div>
                {formCobro.metodo !== 'efectivo' && (
                  <div className="field">
                    <label htmlFor="referenciaCobro">N.º de operación</label>
                    <input
                      id="referenciaCobro" required maxLength={60}
                      value={formCobro.referencia}
                      onChange={(e) => setFormCobro((f) => ({ ...f, referencia: e.target.value }))}
                    />
                  </div>
                )}
              </>
            ) : (
              <p className="cell-secondary">Este pedido ya está pagado o es a crédito: no cobres nada al cliente.</p>
            )}
            <div className="section-title">Quién recibe</div>
            <div className="field">
              <label htmlFor="relacionReceptor">Recibe</label>
              <select id="relacionReceptor" value={formCobro.relacion}
                onChange={(e) => setFormCobro((f) => ({
                  ...f, relacion: e.target.value,
                  nombreReceptor: e.target.value === 'titular' ? (pedidoACobrar.cliente?.nombre || '') : '',
                }))}>
                {Object.entries(RELACIONES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </div>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="nombreReceptor">Nombre de quien recibe</label>
                <input id="nombreReceptor" required minLength={3} maxLength={100} value={formCobro.nombreReceptor}
                  onChange={(e) => setFormCobro((f) => ({ ...f, nombreReceptor: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="dniReceptor">DNI / documento</label>
                <input id="dniReceptor" required inputMode="numeric" minLength={6} maxLength={15}
                  pattern="[A-Za-z0-9]{6,15}" value={formCobro.dniReceptor}
                  onChange={(e) => setFormCobro((f) => ({ ...f, dniReceptor: e.target.value }))} />
              </div>
            </div>
            {pedidoACobrar.requierePin && (
              <div className="field">
                <label htmlFor="pinEntrega">Código de entrega (PIN)</label>
                <input id="pinEntrega" required inputMode="numeric" autoComplete="one-time-code"
                  pattern="[0-9]{6}" maxLength={6} className="input-pin" value={formCobro.pin}
                  onChange={(e) => setFormCobro((f) => ({ ...f, pin: e.target.value.replace(/\D/g, '') }))} />
                <p className="cell-secondary" style={{ marginTop: 4 }}>
                  Pídeselo al destinatario: lo recibió el remitente al enviar el paquete. Sin el código no se puede entregar.
                </p>
              </div>
            )}
            <div className="field">
              <span className="field-label">Firma de quien recibe</span>
              <FirmaPad onChange={(firma) => setFormCobro((f) => ({ ...f, firma }))} />
            </div>
            <div className="field">
              <label htmlFor="fotoEvidencia">Foto de evidencia (opcional)</label>
              <input
                id="fotoEvidencia" type="file" accept="image/*" capture="environment"
                onChange={manejarSeleccionFoto}
              />
              {formCobro.foto && <p className="cell-secondary" style={{ marginTop: 4 }}>✓ Foto lista para adjuntar</p>}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoACobrar(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={procesando}>
                {procesando ? 'Guardando…' : 'Confirmar entrega'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pedidoNoEntregado && (
        <Modal title={`No pude entregar — ${pedidoNoEntregado.codigoGuia || '#' + pedidoNoEntregado.pedidoId}`} onClose={() => setPedidoNoEntregado(null)}>
          <form onSubmit={manejarNoEntregado}>
            <div className="field">
              <label htmlFor="motivoNoEntrega">Motivo</label>
              <select
                id="motivoNoEntrega"
                value={formNoEntregado.motivo}
                onChange={(e) => setFormNoEntregado((f) => ({ ...f, motivo: e.target.value }))}
              >
                {Object.entries(MOTIVOS_NO_ENTREGA).map(([valor, etiqueta]) => (
                  <option key={valor} value={valor}>{etiqueta}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="comentarioNoEntrega">Comentario (opcional)</label>
              <textarea
                id="comentarioNoEntrega" maxLength={500}
                value={formNoEntregado.comentario}
                onChange={(e) => setFormNoEntregado((f) => ({ ...f, comentario: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setPedidoNoEntregado(null)}>Cancelar</button>
              <button type="submit" className="btn btn-warning" disabled={procesando}>Registrar intento fallido</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
