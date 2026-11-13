import { useEffect, useId, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  listarClientes, listarAlmacenes, listarZonas, listarDireccionesCliente,
  crearCliente, crearDireccionCliente, crearPedido, ingresarAlmacen,
  cotizarEnvio, obtenerPedido, getUsuario, obtenerRecojo,
} from '../../api'
import { comprimirImagen } from '../../utils/imagen'

// Admision de un envio en agencia (pasos 2 a 5 del proceso):
//   registro (remitente / destinatario) -> bultos (peso y medidas)
//   -> inspeccion -> cotizacion -> guia y etiqueta
// Con /pedidos/:id/recibir se usa para recibir un envio pre-registrado:
// solo se piden bultos e inspeccion.

const CLIENTE_VACIO = { nombre: '', dni: '', telefono: '', email: '' }
const DIRECCION_VACIA = { etiqueta: '', calle: '', referencia: '', zonaId: '' }
const BULTO_VACIO = { pesoKg: '', largoCm: '', anchoCm: '', altoCm: '', descripcion: '' }
const ENVIO_VACIO = {
  almacenId: '', tipoServicio: 'estandar', modalidadPago: 'contra_entrega', prioridad: 'normal',
  valorDeclarado: '', descripcionProducto: '', notas: '', precioManual: false, monto: '', motivoMonto: '', entregaConPin: false, montoRecaudo: '',
}
const INSPECCION_VACIA = {
  estadoProducto: 'bueno', embalaje: 'adecuado', declaraSinProhibidos: false,
  observacionesInspeccion: '', fotoInspeccion: null,
}

const SERVICIOS = { estandar: 'Estándar', express: 'Express' }
const MODALIDADES = { contra_entrega: 'Contra entrega (cobra el repartidor)', prepagado: 'Prepagado (paga en agencia)', credito: 'Crédito (cliente corporativo)' }
const ESTADOS_PRODUCTO = { bueno: 'Bueno', con_detalles: 'Con detalles (rayones, caja usada)', danado: 'Dañado' }
const EMBALAJES = { adecuado: 'Adecuado', reforzado: 'Reforzado en agencia', rechazado: 'Rechazado (no se admite)' }

const soles = (v) => `S/ ${Number(v || 0).toFixed(2)}`
const numeroValido = (v) => v !== '' && Number(v) > 0
const bultoCompleto = (b) => ['pesoKg', 'largoCm', 'anchoCm', 'altoCm'].every((c) => numeroValido(b[c]))

function SelectorCliente({ titulo, ayuda, clientes, estado, setEstado }) {
  const uid = useId()
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{titulo}</h2>
        <div className="segmented">
          <button type="button" className={estado.modo === 'existente' ? 'active' : ''}
            onClick={() => setEstado((s) => ({ ...s, modo: 'existente' }))}>Registrado</button>
          <button type="button" className={estado.modo === 'nuevo' ? 'active' : ''}
            onClick={() => setEstado((s) => ({ ...s, modo: 'nuevo', id: '' }))}>Nuevo</button>
        </div>
      </div>
      {ayuda && <p className="cell-secondary panel-ayuda">{ayuda}</p>}
      {estado.modo === 'existente' ? (
        <div className="field">
          <label htmlFor={`${uid}-1`}>Cliente</label>
          <select id={`${uid}-1`} required value={estado.id} onChange={(e) => setEstado((s) => ({ ...s, id: e.target.value }))}>
            <option value="">Selecciona…</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>{c.nombre}{c.dni ? ` · ${c.dni}` : ''} · {c.telefono}</option>
            ))}
          </select>
        </div>
      ) : (
        <>
          <div className="field">
            <label htmlFor={`${uid}-2`}>Nombre completo o razón social</label>
            <input id={`${uid}-2`} required maxLength={100} value={estado.nuevo.nombre}
              onChange={(e) => setEstado((s) => ({ ...s, nuevo: { ...s.nuevo, nombre: e.target.value } }))} />
          </div>
          <div className="form-2col">
            <div className="field">
              <label htmlFor={`${uid}-3`}>DNI / RUC</label>
              <input id={`${uid}-3`} maxLength={15} value={estado.nuevo.dni}
                onChange={(e) => setEstado((s) => ({ ...s, nuevo: { ...s.nuevo, dni: e.target.value } }))} />
            </div>
            <div className="field">
              <label htmlFor={`${uid}-4`}>Teléfono</label>
              <input id={`${uid}-4`} required type="tel" maxLength={20} value={estado.nuevo.telefono}
                onChange={(e) => setEstado((s) => ({ ...s, nuevo: { ...s.nuevo, telefono: e.target.value } }))} />
            </div>
          </div>
        </>
      )}
    </section>
  )
}

export default function Admision() {
  const { id: pedidoId } = useParams()
  // Admision de lo recogido a domicilio: /pedidos/nuevo?recojo=ID
  const [params] = useSearchParams()
  const recojoId = params.get('recojo')
  const [recojo, setRecojo] = useState(null)
  const modoRecepcion = Boolean(pedidoId)
  const navigate = useNavigate()

  const [clientes, setClientes] = useState([])
  const [almacenes, setAlmacenes] = useState([])
  const [zonas, setZonas] = useState([])
  const [pedido, setPedido] = useState(null)

  // Desde la ficha del cliente: /pedidos/nuevo?remitente=ID o ?destinatario=ID
  const [remitente, setRemitente] = useState({ modo: 'existente', id: params.get('remitente') || '', nuevo: CLIENTE_VACIO })
  const [destinatario, setDestinatario] = useState({ modo: 'existente', id: params.get('destinatario') || '', nuevo: CLIENTE_VACIO })
  const [direcciones, setDirecciones] = useState([])
  const [direccionId, setDireccionId] = useState('')
  const [direccionNueva, setDireccionNueva] = useState(DIRECCION_VACIA)
  // Un operador de agencia solo admite en la suya
  const agenciaFija = getUsuario()?.agenciaId || null
  const [envio, setEnvio] = useState(() => ({ ...ENVIO_VACIO, almacenId: agenciaFija ? String(agenciaFija) : '' }))
  const [bultos, setBultos] = useState([{ ...BULTO_VACIO }])
  const [inspeccion, setInspeccion] = useState(INSPECCION_VACIA)

  const [cotizacion, setCotizacion] = useState(null)
  const [cotizando, setCotizando] = useState(false)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    listarAlmacenes().then((r) => setAlmacenes(r.content)).catch(() => {})
    listarZonas().then((r) => setZonas(r.content)).catch(() => {})
    if (recojoId) {
      obtenerRecojo(recojoId).then((r) => {
        setRecojo(r.content)
        // El remitente es el cliente del recojo y se admite en la agencia que lo recogio
        setRemitente((s) => ({ ...s, modo: 'existente', id: String(r.content.remitente.id) }))
        setEnvio((s) => ({ ...s, almacenId: String(r.content.agencia.id) }))
      }).catch((e) => setError(e.message))
    }
    if (modoRecepcion) {
      obtenerPedido(pedidoId).then((r) => setPedido(r.content)).catch((e) => setError(e.message))
    } else {
      listarClientes().then((r) => setClientes(r.content)).catch(() => {})
    }
  }, [modoRecepcion, pedidoId, recojoId])

  // Direcciones del destinatario registrado
  useEffect(() => {
    setDireccionId('')
    if (destinatario.modo === 'existente' && destinatario.id) {
      listarDireccionesCliente(destinatario.id).then((r) => {
        setDirecciones(r.content)
        // Se propone la direccion principal del cliente
        const principal = r.content.find((d) => d.esPrincipal)
        if (principal) setDireccionId(String(principal.id))
      }).catch(() => setDirecciones([]))
    } else {
      setDirecciones([])
    }
  }, [destinatario.modo, destinatario.id])

  const usaDireccionNueva = destinatario.modo === 'nuevo' || direccionId === 'nueva'

  // ---------- Cotizacion en vivo (no guarda nada) ----------
  const consulta = useMemo(() => {
    const listos = bultos.filter(bultoCompleto)
    if (listos.length === 0) return null
    const base = {
      bultos: listos.map(({ pesoKg, largoCm, anchoCm, altoCm }) => ({ pesoKg, largoCm, anchoCm, altoCm })),
    }
    if (modoRecepcion) {
      if (!pedido) return null
      return { ...base, almacenId: pedido.almacenId, direccionEntregaId: pedido.direccionEntregaId,
        tipoServicio: pedido.tipoServicio, valorDeclarado: pedido.valorDeclarado }
    }
    if (!envio.almacenId) return null
    const destino = usaDireccionNueva
      ? (direccionNueva.zonaId ? { zonaDestinoId: Number(direccionNueva.zonaId) } : null)
      : (direccionId ? { direccionEntregaId: Number(direccionId) } : null)
    if (!destino) return null
    return { ...base, ...destino, almacenId: Number(envio.almacenId), tipoServicio: envio.tipoServicio,
      valorDeclarado: envio.valorDeclarado || undefined,
      ...(recojo ? { solicitudRecojoId: recojo.id, remitenteId: recojo.remitente.id } : {}) }
  }, [bultos, modoRecepcion, pedido, envio.almacenId, envio.tipoServicio, envio.valorDeclarado,
    usaDireccionNueva, direccionNueva.zonaId, direccionId, recojo])

  useEffect(() => {
    if (!consulta) {
      setCotizacion(null)
      return undefined
    }
    setCotizando(true)
    const t = setTimeout(() => {
      cotizarEnvio(consulta)
        .then((r) => setCotizacion(r.content))
        .catch(() => setCotizacion(null))
        .finally(() => setCotizando(false))
    }, 400)
    return () => clearTimeout(t)
  }, [consulta])

  // ---------- Bultos ----------
  function cambiarBulto(i, campo, valor) {
    setBultos((lista) => lista.map((b, j) => (j === i ? { ...b, [campo]: valor } : b)))
  }
  const agregarBulto = () => setBultos((lista) => [...lista, { ...BULTO_VACIO }])
  const quitarBulto = (i) => setBultos((lista) => lista.filter((_, j) => j !== i))

  function manejarFoto(e) {
    const archivo = e.target.files?.[0]
    if (!archivo) return
    comprimirImagen(archivo)
      .then((foto) => setInspeccion((s) => ({ ...s, fotoInspeccion: foto })))
      .catch(() => setError('No se pudo procesar la foto, intenta con otra'))
  }

  const payloadBultos = () => bultos.map((b) => ({
    pesoKg: b.pesoKg, largoCm: b.largoCm, anchoCm: b.anchoCm, altoCm: b.altoCm,
    descripcion: b.descripcion || undefined,
  }))

  const payloadInspeccion = () => ({
    estadoProducto: inspeccion.estadoProducto,
    embalaje: inspeccion.embalaje,
    declaraSinProhibidos: inspeccion.declaraSinProhibidos,
    observacionesInspeccion: inspeccion.observacionesInspeccion || undefined,
    fotoInspeccion: inspeccion.fotoInspeccion || undefined,
  })

  // Si se crea un cliente y luego falla el envio, queda seleccionado como
  // "registrado": reintentar no lo duplica.
  async function asegurarCliente(estado, setEstado) {
    if (estado.modo === 'existente') return Number(estado.id)
    const datos = { ...estado.nuevo }
    Object.keys(datos).forEach((k) => { if (!datos[k]) delete datos[k] })
    const r = await crearCliente(datos)
    const id = r.content.id
    setClientes((lista) => [...lista, r.content])
    setEstado((s) => ({ ...s, modo: 'existente', id: String(id) }))
    return id
  }

  async function manejarEnvio(e) {
    e.preventDefault()
    setError('')
    if (inspeccion.embalaje === 'rechazado') {
      setError('Con el embalaje rechazado el envío no se puede admitir. Pide al cliente que lo reembale.')
      return
    }
    setEnviando(true)
    try {
      if (modoRecepcion) {
        await ingresarAlmacen(pedidoId, { bultos: payloadBultos(), ...payloadInspeccion() })
        navigate(`/pedidos/${pedidoId}/etiqueta`, { replace: true })
        return
      }
      const remitenteId = await asegurarCliente(remitente, setRemitente)
      const destinatarioId = await asegurarCliente(destinatario, setDestinatario)
      let direccionEntregaId = Number(direccionId)
      if (usaDireccionNueva) {
        const r = await crearDireccionCliente({
          ...direccionNueva, clienteId: destinatarioId,
          zonaId: direccionNueva.zonaId ? Number(direccionNueva.zonaId) : undefined,
        })
        direccionEntregaId = r.content.id
        setDirecciones((lista) => [...lista, r.content])
        setDireccionId(String(direccionEntregaId))
      }
      const r = await crearPedido({
        remitenteId,
        clienteId: destinatarioId,
        direccionEntregaId,
        almacenId: Number(envio.almacenId),
        tipoServicio: envio.tipoServicio,
        modalidadPago: envio.modalidadPago,
        montoRecaudo: Number(envio.montoRecaudo) > 0 ? envio.montoRecaudo : undefined,
        prioridad: envio.prioridad,
        valorDeclarado: envio.valorDeclarado || undefined,
        entregaConPin: envio.entregaConPin,
        solicitudRecojoId: recojo ? recojo.id : undefined,
        descripcionProducto: envio.descripcionProducto || undefined,
        notas: envio.notas || undefined,
        monto: envio.precioManual && envio.monto !== '' ? envio.monto : undefined,
        motivoMonto: envio.precioManual ? envio.motivoMonto.trim() || undefined : undefined,
        yaEnAlmacen: true,
        bultos: payloadBultos(),
        ...payloadInspeccion(),
      })
      // El PIN se muestra UNA vez, en la pantalla de etiqueta (no se guarda en el navegador)
      navigate(`/pedidos/${r.content.id}/etiqueta`, { replace: true, state: { pinEntrega: r.content.pinEntrega } })
    } catch (err) {
      setError(err.message)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setEnviando(false)
    }
  }

  const cot = cotizacion?.cotizacion
  const pesos = cotizacion?.pesos

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{modoRecepcion ? 'Recibir envío en agencia' : 'Admisión de envío'}</h1>
          <p className="page-sub">
            {modoRecepcion
              ? 'Pesa, mide e inspecciona el paquete pre-registrado.'
              : 'Registro, inspección y cotización. Al terminar se genera la guía y la etiqueta.'}
          </p>
        </div>
        <Link to="/pedidos" className="btn btn-secondary">← Volver a pedidos</Link>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {recojo && (
        <div className="success-banner">
          Admitiendo lo recogido en <strong>{recojo.codigo}</strong> ({recojo.remitente.nombre},{' '}
          {recojo.bultosRecogidos ?? recojo.bultosEstimados} bulto/s). Registra un envío por cada destinatario.
        </div>
      )}

      <form className="admision-grid" onSubmit={manejarEnvio}>
        <div className="admision-form">
          {modoRecepcion ? (
            <section className="panel">
              <h2>Envío pre-registrado</h2>
              {pedido ? (
                <div className="dato-lista">
                  <div><span>Guía</span><strong className="cell-mono">{pedido.codigoGuia}</strong></div>
                  <div><span>Servicio</span><strong>{SERVICIOS[pedido.tipoServicio] || pedido.tipoServicio}</strong></div>
                  <div><span>Peso estimado</span><strong>{pedido.pesoKg ?? '—'} kg</strong></div>
                  <div><span>Monto actual</span><strong>{soles(pedido.monto)}</strong></div>
                </div>
              ) : <p className="loading-text">Cargando…</p>}
            </section>
          ) : (
            <>
              <SelectorCliente titulo="1. Remitente" ayuda="Quien envía el paquete."
                clientes={clientes} estado={remitente} setEstado={setRemitente} />

              <SelectorCliente titulo="2. Destinatario" ayuda="Quien recibe. El repartidor verá su nombre y teléfono."
                clientes={clientes} estado={destinatario} setEstado={setDestinatario} />

              <section className="panel">
                <h2>Dirección de entrega</h2>
                {destinatario.modo === 'existente' && (
                  <div className="field">
                    <label htmlFor="adm-1">Dirección del destinatario</label>
                    <select id="adm-1" required value={direccionId} onChange={(e) => setDireccionId(e.target.value)}
                      disabled={!destinatario.id}>
                      <option value="">{destinatario.id ? 'Selecciona…' : 'Primero elige el destinatario'}</option>
                      {direcciones.map((d) => (
                        <option key={d.id} value={d.id}>{d.etiqueta ? `${d.etiqueta}: ` : ''}{d.calle}</option>
                      ))}
                      {destinatario.id && <option value="nueva">+ Nueva dirección…</option>}
                    </select>
                  </div>
                )}
                {usaDireccionNueva && (
                  <>
                    <div className="field">
                      <label htmlFor="adm-2">Calle, número y distrito</label>
                      <input id="adm-2" required maxLength={300} value={direccionNueva.calle}
                        onChange={(e) => setDireccionNueva((d) => ({ ...d, calle: e.target.value }))} />
                    </div>
                    <div className="form-2col">
                      <div className="field">
                        <label htmlFor="adm-3">Zona de reparto</label>
                        <select id="adm-3" required value={direccionNueva.zonaId}
                          onChange={(e) => setDireccionNueva((d) => ({ ...d, zonaId: e.target.value }))}>
                          <option value="">Selecciona…</option>
                          {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
                        </select>
                      </div>
                      <div className="field">
                        <label htmlFor="adm-4">Referencia <span className="cell-secondary">(opcional)</span></label>
                        <input id="adm-4" maxLength={300} value={direccionNueva.referencia}
                          onChange={(e) => setDireccionNueva((d) => ({ ...d, referencia: e.target.value }))} />
                      </div>
                    </div>
                  </>
                )}
              </section>

              <section className="panel">
                <h2>3. Servicio y pago</h2>
                <div className="form-2col">
                  <div className="field">
                    <label htmlFor="adm-5">Agencia de origen</label>
                    <select id="adm-5" required value={envio.almacenId} disabled={!!agenciaFija}
                      onChange={(e) => setEnvio((s) => ({ ...s, almacenId: e.target.value }))}>
                      <option value="">Selecciona…</option>
                      {almacenes.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="adm-6">Tipo de servicio</label>
                    <select id="adm-6" value={envio.tipoServicio}
                      onChange={(e) => setEnvio((s) => ({ ...s, tipoServicio: e.target.value }))}>
                      {Object.entries(SERVICIOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-2col">
                  <div className="field">
                    <label htmlFor="adm-7">Modalidad de pago</label>
                    <select id="adm-7" value={envio.modalidadPago}
                      onChange={(e) => setEnvio((s) => ({ ...s, modalidadPago: e.target.value }))}>
                      {Object.entries(MODALIDADES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="adm-8">Valor declarado (S/) <span className="cell-secondary">(opcional)</span></label>
                    <input id="adm-8" type="number" min="0" step="0.01" value={envio.valorDeclarado} placeholder="Para el seguro"
                      onChange={(e) => setEnvio((s) => ({ ...s, valorDeclarado: e.target.value }))} />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="adm-rec">Cobrar el producto al destinatario (S/) <span className="cell-secondary">(opcional)</span></label>
                  <input id="adm-rec" type="number" min="0" step="0.01" value={envio.montoRecaudo} placeholder="Ej. venta de tienda online"
                    onChange={(e) => setEnvio((s) => ({ ...s, montoRecaudo: e.target.value }))} />
                  <p className="cli-hint">
                    Contra entrega de mercadería: el repartidor cobra este monto (además del envío, si es contra entrega)
                    y se le paga al remitente en Caja → Recaudos.
                  </p>
                </div>
                <div className="form-2col">
                  <div className="field">
                    <label htmlFor="adm-9">Contenido <span className="cell-secondary">(uso interno, no va en la etiqueta)</span></label>
                    <input id="adm-9" maxLength={500} value={envio.descripcionProducto}
                      onChange={(e) => setEnvio((s) => ({ ...s, descripcionProducto: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label htmlFor="adm-10">Prioridad</label>
                    <select id="adm-10" value={envio.prioridad}
                      onChange={(e) => setEnvio((s) => ({ ...s, prioridad: e.target.value }))}>
                      <option value="normal">Normal</option>
                      <option value="urgente">Urgente</option>
                    </select>
                  </div>
                </div>
              </section>
            </>
          )}

          <section className="panel">
            <div className="panel-head">
              <h2>{modoRecepcion ? '1.' : '4.'} Bultos</h2>
              <button type="button" className="btn btn-secondary btn-sm" onClick={agregarBulto}>+ Agregar bulto</button>
            </div>
            <p className="cell-secondary panel-ayuda">
              Pesa cada caja en la balanza y mide sus lados. Se cobra el mayor entre el peso real y el volumétrico.
            </p>
            {bultos.map((b, i) => {
              const calc = cotizacion?.bultos?.[bultos.slice(0, i).filter(bultoCompleto).length]
              return (
                <div className="bulto-fila" key={i}>
                  <div className="bulto-num">#{i + 1}</div>
                  <div className="bulto-campos">
                    {[['pesoKg', 'Peso (kg)', 500], ['largoCm', 'Largo (cm)', 300], ['anchoCm', 'Ancho (cm)', 300], ['altoCm', 'Alto (cm)', 300]].map(([campo, etiqueta, max]) => (
                      <div className="field" key={campo}>
                        <label htmlFor={`bulto-${i}-${campo}`}>{etiqueta}</label>
                        <input id={`bulto-${i}-${campo}`} type="number" inputMode="decimal" min="0.01" max={max} step="0.01" required
                          value={b[campo]} onChange={(e) => cambiarBulto(i, campo, e.target.value)} />
                      </div>
                    ))}
                  </div>
                  <div className="bulto-calc">
                    {bultoCompleto(b) && calc ? (
                      <>
                        <span>Vol. {calc.pesoVolumetricoKg} kg</span>
                        <strong>Cobra {calc.pesoFacturableKg} kg</strong>
                      </>
                    ) : <span className="cell-secondary">—</span>}
                  </div>
                  {bultos.length > 1 && (
                    <button type="button" className="btn-xs danger" onClick={() => quitarBulto(i)} aria-label={`Quitar bulto ${i + 1}`}>Quitar</button>
                  )}
                </div>
              )
            })}
          </section>

          <section className="panel">
            <h2>{modoRecepcion ? '2.' : '5.'} Inspección</h2>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="adm-11">Estado del producto</label>
                <select id="adm-11" value={inspeccion.estadoProducto}
                  onChange={(e) => setInspeccion((s) => ({ ...s, estadoProducto: e.target.value }))}>
                  {Object.entries(ESTADOS_PRODUCTO).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="adm-12">Embalaje</label>
                <select id="adm-12" value={inspeccion.embalaje}
                  onChange={(e) => setInspeccion((s) => ({ ...s, embalaje: e.target.value }))}>
                  {Object.entries(EMBALAJES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </div>
            </div>
            {inspeccion.embalaje === 'rechazado' && (
              <div className="error-banner">El paquete no cumple las condiciones de transporte: no se puede admitir hasta que se reembale.</div>
            )}
            <div className="field">
              <label htmlFor="adm-13">
                Observaciones {inspeccion.estadoProducto === 'bueno'
                  ? <span className="cell-secondary">(opcional)</span>
                  : <span className="cell-secondary">(obligatorio: describe los detalles)</span>}
              </label>
              <textarea id="adm-13" maxLength={1000} required={inspeccion.estadoProducto !== 'bueno'}
                value={inspeccion.observacionesInspeccion}
                onChange={(e) => setInspeccion((s) => ({ ...s, observacionesInspeccion: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="adm-14">
                Foto del producto {inspeccion.estadoProducto === 'danado'
                  ? <span className="cell-secondary">(obligatoria si está dañado)</span>
                  : <span className="cell-secondary">(opcional)</span>}
              </label>
              <input id="adm-14" type="file" accept="image/*" capture="environment" onChange={manejarFoto}
                required={inspeccion.estadoProducto === 'danado' && !inspeccion.fotoInspeccion} />
              {inspeccion.fotoInspeccion && <img src={inspeccion.fotoInspeccion} alt="Foto de inspección" className="foto-preview" />}
            </div>
            <label className="check-line">
              <input type="checkbox" required checked={inspeccion.declaraSinProhibidos}
                onChange={(e) => setInspeccion((s) => ({ ...s, declaraSinProhibidos: e.target.checked }))} />
              <span>
                El remitente declara que el envío <strong>no contiene artículos prohibidos</strong>: explosivos,
                inflamables, dinero en efectivo, drogas, armas o animales vivos.
              </span>
            </label>
          </section>
        </div>

        <aside className="admision-resumen">
          <section className="panel resumen-sticky">
            <h2>Cotización</h2>
            {!cotizacion ? (
              <p className="cell-secondary">
                {cotizando ? 'Calculando…' : modoRecepcion
                  ? 'Ingresa el peso y las medidas de los bultos.'
                  : 'Completa la agencia, la dirección de entrega y al menos un bulto.'}
              </p>
            ) : (
              <>
                <div className="dato-lista">
                  <div><span>Peso real</span><strong>{pesos.pesoRealKg} kg</strong></div>
                  <div><span>Peso volumétrico</span><strong>{pesos.pesoVolumetricoKg} kg</strong></div>
                  <div><span>Peso facturable</span><strong>{pesos.pesoFacturableKg} kg</strong></div>
                </div>
                {cot?.recargoRecojo && (
                  <div className="dato-lista">
                    <div><span>Recargo por recojo a domicilio</span><strong>{soles(cot.recargoRecojo)}</strong></div>
                  </div>
                )}
                {cotizacion.sinCobertura && (
                  <div className="error-banner">Sin cobertura: ninguna agencia reparte en la zona de esa dirección.</div>
                )}
                {cotizacion.agenciaDestino && (
                  <div className="dato-lista separador">
                    <div><span>Reparte</span><strong>{cotizacion.agenciaDestino.esLocal
                      ? 'Esta agencia (local)' : cotizacion.agenciaDestino.nombre}</strong></div>
                  </div>
                )}
                {cot ? (
                  <>
                    <div className="dato-lista separador">
                      <div><span>Base</span><strong>{soles(cot.precioBase)}</strong></div>
                      <div><span>{cot.pesoFacturableKg} kg × {soles(cot.precioPorKg)}</span>
                        <strong>{soles(Number(cot.fleteCalculado) - Number(cot.precioBase))}</strong></div>
                      {cot.minimoAplicado && (
                        <div><span>Se aplica el precio mínimo</span><strong>{soles(cot.precioMinimo)}</strong></div>
                      )}
                      {Number(cot.seguro) > 0 && (
                        <div><span>Seguro ({cot.porcentajeSeguro}% de {soles(cot.valorDeclarado)})</span><strong>{soles(cot.seguro)}</strong></div>
                      )}
                    </div>
                    <div className="total-linea"><span>Total</span><strong>{soles(cot.total)}</strong></div>
                    {cotizacion.fechaEntregaEstimada && (
                      <p className="cell-secondary">
                        Entrega estimada: {new Date(cotizacion.fechaEntregaEstimada).toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' })}
                      </p>
                    )}
                  </>
                ) : (
                  <div className="error-banner">
                    No hay tarifa {SERVICIOS[modoRecepcion ? pedido?.tipoServicio : envio.tipoServicio]?.toLowerCase()} para esta ruta.
                    Regístrala en Configuración → Tarifas o usa un precio pactado.
                  </div>
                )}
              </>
            )}

            {!modoRecepcion && (
              <>
                <label className="check-line">
                  <input type="checkbox" checked={envio.entregaConPin}
                    onChange={(e) => setEnvio((s) => ({ ...s, entregaConPin: e.target.checked }))} />
                  <span>Entrega con código (PIN): el repartidor solo entrega si el destinatario dicta el código. Recomendado para envíos de valor.</span>
                </label>
                <label className="check-line">
                  <input type="checkbox" checked={envio.precioManual}
                    onChange={(e) => setEnvio((s) => ({ ...s, precioManual: e.target.checked, monto: '' }))} />
                  <span>Precio pactado (manual)</span>
                </label>
                {envio.precioManual && (
                  <div className="field">
                    <label htmlFor="adm-15">Monto a cobrar (S/)</label>
                    <input id="adm-15" type="number" min="0" step="0.01" required value={envio.monto}
                      onChange={(e) => setEnvio((s) => ({ ...s, monto: e.target.value }))} />
                  </div>
                )}
                {envio.precioManual && (
                  <div className="field">
                    <label htmlFor="adm-16">Motivo del precio manual</label>
                    <input id="adm-16" required minLength={5} maxLength={200} value={envio.motivoMonto}
                      placeholder="Ej. convenio corporativo, sin tarifa a esa zona"
                      onChange={(e) => setEnvio((s) => ({ ...s, motivoMonto: e.target.value }))} />
                    <p className="cell-secondary">
                      Queda en la auditoría. Un operador puede rebajar hasta 10% de la tarifa; más, lo autoriza un administrador.
                    </p>
                  </div>
                )}
              </>
            )}

            <button className="btn btn-primary btn-block" type="submit"
              disabled={enviando || inspeccion.embalaje === 'rechazado'}>
              {enviando ? 'Guardando…' : modoRecepcion ? 'Confirmar recepción e imprimir etiqueta' : 'Registrar envío y generar guía'}
            </button>
          </section>
        </aside>
      </form>
    </div>
  )
}
