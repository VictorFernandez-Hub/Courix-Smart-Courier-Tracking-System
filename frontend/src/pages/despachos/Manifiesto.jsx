import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getUsuario, obtenerManifiesto, escanearEnManifiesto, quitarDeManifiesto,
  despacharManifiesto, recibirEnManifiesto, cerrarRecepcion,
} from '../../api'
import { BadgeManifiesto } from './Despachos.jsx'
import EscanerQR from '../../components/ui/EscanerQR.jsx'

// Pistola lectora USB/Bluetooth = teclado: escribe el codigo y pulsa Enter.
// Por eso el campo de escaneo recupera el foco despues de cada lectura.

// Pitido corto: en el almacen nadie mira la pantalla en cada escaneo.
function pitido(ok) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator()
    const vol = ctx.createGain()
    osc.frequency.value = ok ? 1200 : 220
    vol.gain.value = 0.08
    osc.connect(vol).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + (ok ? 0.08 : 0.35))
  } catch { /* sin audio: no pasa nada */ }
}

const fecha = (iso) => (iso ? new Date(iso).toLocaleString('es-PE') : '—')

export default function Manifiesto() {
  const { id } = useParams()
  const usuario = getUsuario()
  const [m, setM] = useState(null)
  const [error, setError] = useState('')
  const [codigo, setCodigo] = useState('')
  const [aviso, setAviso] = useState(null) // { ok, texto }
  const [procesando, setProcesando] = useState(false)
  const [despacho, setDespacho] = useState({ transportista: '', placa: '', precinto: '' })
  const [observaciones, setObservaciones] = useState('')
  const campoEscaneo = useRef(null)

  const cargar = useCallback(() => {
    obtenerManifiesto(id).then((r) => setM(r.content)).catch((err) => setError(err.message))
  }, [id])
  useEffect(cargar, [cargar])

  const miAgencia = usuario?.agenciaId
  const puedeArmar = m?.estado === 'abierto' && (!miAgencia || miAgencia === m.agenciaOrigen.id)
  const esDestino = !miAgencia || miAgencia === m?.agenciaDestino.id
  const puedeRecibir = m?.estado === 'en_transito' && esDestino
  // Cerrado con faltantes: el bulto que aparece despues se escanea igual
  const recibeTarde = m?.estado === 'recibido_con_diferencias' && esDestino &&
    (m?.bultos || []).some((b) => !b.recibido)
  const modoEscaneo = puedeArmar ? 'armar' : (puedeRecibir || recibeTarde) ? 'recibir' : null

  // El foco vuelve al campo al terminar cada lectura: con una pistola
  // lectora el operador no toca el mouse entre un bulto y otro.
  useEffect(() => {
    if (modoEscaneo && !procesando) campoEscaneo.current?.focus()
  }, [modoEscaneo, procesando])

  // Bultos agrupados por envio, para ver de un vistazo si alguno va incompleto
  const envios = useMemo(() => {
    const grupos = new Map()
    for (const b of m?.bultos || []) {
      if (!grupos.has(b.pedidoId)) grupos.set(b.pedidoId, { ...b, lista: [] })
      grupos.get(b.pedidoId).lista.push(b)
    }
    return [...grupos.values()]
  }, [m])
  const incompletos = envios.filter((e) => e.lista.length < e.totalDelEnvio)
  const faltantes = (m?.bultos || []).filter((b) => !b.recibido)

  const [camara, setCamara] = useState(false)

  // Lo usan el lector/teclado (formulario) y la camara (cada QR leido)
  const procesarCodigo = useCallback(async (valor) => {
    setProcesando(true)
    try {
      const r = modoEscaneo === 'armar'
        ? await escanearEnManifiesto(id, valor)
        : await recibirEnManifiesto(id, valor)
      setM(r.content)
      setAviso({ ok: true, texto: r.message })
      pitido(true)
    } catch (err) {
      setAviso({ ok: false, texto: err.message })
      pitido(false)
    } finally {
      setCodigo('')
      setProcesando(false)
    }
  }, [id, modoEscaneo])

  function escanear(e) {
    e.preventDefault()
    const valor = codigo.trim()
    if (valor) procesarCodigo(valor)
  }

  async function quitar(b) {
    try {
      const r = await quitarDeManifiesto(id, b.bultoId)
      setM(r.content)
      setAviso({ ok: true, texto: `Bulto ${b.codigo} retirado` })
    } catch (err) {
      setAviso({ ok: false, texto: err.message })
    }
  }

  async function despachar(e) {
    e.preventDefault()
    if (!window.confirm(`¿Despachar ${m.totalBultos} bulto(s) a ${m.agenciaDestino.nombre}? Después no se podrá modificar el manifiesto.`)) return
    setProcesando(true)
    try {
      const r = await despacharManifiesto(id, { ...despacho, precinto: despacho.precinto || undefined })
      setM(r.content)
      setAviso({ ok: true, texto: r.message })
    } catch (err) {
      setAviso({ ok: false, texto: err.message })
    } finally {
      setProcesando(false)
    }
  }

  async function cerrar(e) {
    e.preventDefault()
    const texto = faltantes.length
      ? `Faltan ${faltantes.length} bulto(s). Se registrará una incidencia por cada envío incompleto. ¿Cerrar la recepción?`
      : '¿Cerrar la recepción del manifiesto?'
    if (!window.confirm(texto)) return
    setProcesando(true)
    try {
      const r = await cerrarRecepcion(id, observaciones)
      setM(r.content)
      setAviso({ ok: faltantes.length === 0, texto: r.message })
    } catch (err) {
      setAviso({ ok: false, texto: err.message })
    } finally {
      setProcesando(false)
    }
  }

  if (error) return <div className="error-banner">{error}</div>
  if (!m) return <p className="loading-text">Cargando manifiesto…</p>

  const progreso = m.totalBultos ? Math.round((m.bultosRecibidos / m.totalBultos) * 100) : 0

  return (
    <div className="manifiesto-pagina">
      <div className="page-header">
        <div>
          <h1>Manifiesto {m.codigo} <BadgeManifiesto estado={m.estado} /></h1>
          <p className="page-sub">{m.agenciaOrigen.nombre} → {m.agenciaDestino.nombre}</p>
        </div>
        <div className="no-imprimir" style={{ display: 'flex', gap: 8 }}>
          <Link to="/despachos" className="btn btn-secondary">← Despachos</Link>
          {m.estado !== 'abierto' && (
            <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir manifiesto</button>
          )}
        </div>
      </div>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="dato-lista dato-lista-grid">
          <div><span>Envíos</span><strong>{m.totalEnvios}</strong></div>
          <div><span>Bultos</span><strong>{m.totalBultos}</strong></div>
          <div><span>Transportista</span><strong>{m.transportista || '—'}</strong></div>
          <div><span>Placa</span><strong className="cell-mono">{m.placa || '—'}</strong></div>
          <div><span>Precinto</span><strong className="cell-mono">{m.precinto || '—'}</strong></div>
          <div><span>Despachado</span><strong>{fecha(m.fechaDespacho)}</strong></div>
          <div><span>Recepción cerrada</span><strong>{fecha(m.fechaRecepcion)}</strong></div>
        </div>
        {m.observaciones && <p className="cell-secondary">Observaciones: {m.observaciones}</p>}
      </section>

      {modoEscaneo && (
        <section className="panel escaneo no-imprimir">
          <h2>{modoEscaneo === 'armar' ? 'Escanea los bultos que suben al vehículo' : 'Escanea los bultos que bajan del vehículo'}</h2>
          <form onSubmit={escanear} className="escaneo-form">
            <label htmlFor="codigoBulto" className="sr-only">Código del bulto</label>
            {/* readOnly (no disabled): un campo deshabilitado pierde el foco */}
            <input id="codigoBulto" ref={campoEscaneo} value={codigo} readOnly={procesando}
              onChange={(e) => setCodigo(e.target.value.toUpperCase())}
              placeholder="CE-XXXX-XXXX-1 (lector o teclado + Enter)" autoComplete="off" spellCheck={false} />
            <button className="btn btn-primary" type="submit" disabled={procesando || !codigo.trim()}>
              {modoEscaneo === 'armar' ? 'Agregar' : 'Recibir'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setCamara(true)}
              title="Leer los QR con la cámara del celular">📷 Cámara</button>
          </form>
          {aviso && <div className={aviso.ok ? 'success-banner' : 'error-banner'} role="status">{aviso.texto}</div>}
          {modoEscaneo === 'recibir' && (
            <div className="progreso" aria-label={`${m.bultosRecibidos} de ${m.totalBultos} bultos recibidos`}>
              <div className="progreso-barra" style={{ width: `${progreso}%` }} />
              <span>{m.bultosRecibidos} / {m.totalBultos} bultos recibidos</span>
            </div>
          )}
        </section>
      )}
      {!modoEscaneo && aviso && <div className={aviso.ok ? 'success-banner' : 'error-banner'}>{aviso.texto}</div>}

      <section className="panel" style={{ margin: '16px 0' }}>
        <h2>Contenido</h2>
        {envios.length === 0 ? (
          <p className="cell-secondary">Sin bultos todavía.</p>
        ) : (
          <table className="tabla-manifiesto">
            <thead>
              <tr><th>Guía</th><th>Destinatario</th><th>Bulto</th><th>Peso fact.</th><th>{m.estado === 'abierto' ? '' : 'Llegada'}</th></tr>
            </thead>
            <tbody>
              {envios.map((env) => env.lista.map((b, i) => (
                <tr key={b.bultoId} className={!b.recibido && m.estado !== 'abierto' && m.estado !== 'en_transito' ? 'fila-faltante' : ''}>
                  {i === 0 && (
                    <>
                      <td rowSpan={env.lista.length} className="cell-mono">
                        {env.codigoGuia}
                        {env.lista.length < env.totalDelEnvio && (
                          <div className="texto-alerta">Incompleto: {env.lista.length} de {env.totalDelEnvio}</div>
                        )}
                      </td>
                      <td rowSpan={env.lista.length}>{env.destinatario}</td>
                    </>
                  )}
                  <td className="cell-mono">{b.codigo} <span className="cell-secondary">({b.numero}/{b.totalDelEnvio})</span></td>
                  <td>{b.pesoFacturableKg} kg</td>
                  <td>
                    {m.estado === 'abierto' ? (
                      puedeArmar && <button className="btn-xs danger no-imprimir" onClick={() => quitar(b)}>Quitar</button>
                    ) : b.recibido ? '✓ Recibido' : m.estado === 'en_transito' ? 'Pendiente' : '✗ Faltante'}
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        )}
      </section>

      {puedeArmar && (
        <section className="panel no-imprimir">
          <h2>Despachar</h2>
          {incompletos.length > 0 && (
            <div className="error-banner">
              {incompletos.length} envío(s) incompleto(s): escanea todos sus bultos o quítalos. Un envío debe viajar completo.
            </div>
          )}
          <form onSubmit={despachar}>
            <div className="form-2col">
              <div className="field">
                <label htmlFor="desTransp">Transportista</label>
                <input id="desTransp" required minLength={3} maxLength={100} value={despacho.transportista}
                  onChange={(e) => setDespacho((d) => ({ ...d, transportista: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="desPlaca">Placa del vehículo</label>
                <input id="desPlaca" required minLength={5} maxLength={15} value={despacho.placa}
                  onChange={(e) => setDespacho((d) => ({ ...d, placa: e.target.value.toUpperCase() }))} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="desPrecinto">N.° de precinto <span className="cell-secondary">(opcional; si llega roto, se nota)</span></label>
              <input id="desPrecinto" maxLength={40} value={despacho.precinto}
                onChange={(e) => setDespacho((d) => ({ ...d, precinto: e.target.value }))} />
            </div>
            <button className="btn btn-primary" type="submit"
              disabled={procesando || m.totalBultos === 0 || incompletos.length > 0}>
              Despachar {m.totalBultos} bulto(s)
            </button>
          </form>
        </section>
      )}

      {recibeTarde && (
        <p className="cli-hint no-imprimir">
          Si llega un bulto faltante, escanéalo arriba: el envío se completa y su incidencia se cierra sola.
        </p>
      )}

      {puedeRecibir && (
        <section className="panel no-imprimir">
          <h2>Cerrar recepción</h2>
          <p className="cell-secondary panel-ayuda">
            {faltantes.length === 0
              ? 'Llegaron todos los bultos.'
              : `Faltan ${faltantes.length} bulto(s). Al cerrar se registra una incidencia "faltante" por cada envío incompleto.`}
          </p>
          <form onSubmit={cerrar}>
            <div className="field">
              <label htmlFor="recObs">Observaciones {faltantes.length > 0 ? '(obligatorio)' : '(opcional)'}</label>
              <textarea id="recObs" maxLength={1000} required={faltantes.length > 0} value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                placeholder="Ej. precinto intacto; el chofer indica que un bulto quedó en origen" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={procesando}>Cerrar recepción</button>
          </form>
        </section>
      )}

      {camara && (
        <EscanerQR continuo onLeer={procesarCodigo} onCerrar={() => setCamara(false)}
          titulo={modoEscaneo === 'armar' ? 'Cargar bultos con la cámara' : 'Recibir bultos con la cámara'}>
          {aviso && <div className={aviso.ok ? 'success-banner' : 'error-banner'} role="status">{aviso.texto}</div>}
          {modoEscaneo === 'recibir' && <p className="cell-secondary">{m.bultosRecibidos} / {m.totalBultos} bultos recibidos</p>}
        </EscanerQR>
      )}

      {/* Solo en papel: constancia de entrega/recepcion con firmas */}
      <div className="solo-imprimir firmas">
        <div><span>Entregó (agencia origen)</span></div>
        <div><span>Transportista · DNI</span></div>
        <div><span>Recibió (agencia destino)</span></div>
      </div>
    </div>
  )
}
