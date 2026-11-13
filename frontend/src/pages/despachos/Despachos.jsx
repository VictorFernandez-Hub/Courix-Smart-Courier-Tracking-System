import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  getUsuario, listarAlmacenes, pendientesDeDespacho, listarManifiestos, crearManifiesto,
} from '../../api'

// Pasos 6-8 del proceso: clasificar por agencia destino, despachar con un
// manifiesto y recibir en destino escaneando cada bulto.

export const ESTADOS_MANIFIESTO = {
  abierto: { texto: 'Abierto', color: 'var(--st-en_almacen)' },
  en_transito: { texto: 'En tránsito', color: 'var(--st-en_transito)' },
  recibido: { texto: 'Recibido', color: 'var(--st-entregado)' },
  recibido_con_diferencias: { texto: 'Con faltantes', color: 'var(--st-no_entregado)' },
}

export function BadgeManifiesto({ estado }) {
  const e = ESTADOS_MANIFIESTO[estado] || { texto: estado, color: 'var(--ink-faint)' }
  return (
    <span className="badge" style={{ color: e.color, background: `color-mix(in srgb, ${e.color} 14%, white)` }}>
      {e.texto}
    </span>
  )
}

function TablaManifiestos({ manifiestos, vacio }) {
  if (manifiestos.length === 0) return <p className="cell-secondary">{vacio}</p>
  return (
    <div className="manifest">
      <div className="manifest-row head manifest-row-6">
        <span>Manifiesto</span><span>Ruta</span><span>Estado</span><span>Bultos</span><span>Transportista</span><span />
      </div>
      {manifiestos.map((m) => (
        <div className="manifest-row manifest-row-6" key={m.id}>
          <span className="tag-id" data-label="Manifiesto">{m.codigo}</span>
          <span data-label="Ruta">{m.agenciaOrigen.nombre} → {m.agenciaDestino.nombre}</span>
          <span data-label="Estado"><BadgeManifiesto estado={m.estado} /></span>
          <span data-label="Bultos">
            {m.estado === 'abierto' || (m.estado === 'en_transito' && m.bultosRecibidos === 0)
              ? `${m.totalBultos} (${m.totalEnvios} envío/s)`
              : `${m.bultosRecibidos} / ${m.totalBultos} recibidos`}
          </span>
          <span data-label="Transportista" className="cell-secondary">
            {m.transportista ? `${m.transportista} · ${m.placa}` : '—'}
          </span>
          <div className="row-actions">
            <Link className="btn-xs" to={`/despachos/${m.id}`}>Abrir</Link>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Despachos() {
  const usuario = getUsuario()
  const navigate = useNavigate()
  const agenciaFija = usuario?.agenciaId || null

  const [agencias, setAgencias] = useState([])
  const [agenciaId, setAgenciaId] = useState(agenciaFija ? String(agenciaFija) : '')
  const [vista, setVista] = useState('salidas')
  const [pendientes, setPendientes] = useState([])
  const [salidas, setSalidas] = useState([])
  const [llegadas, setLlegadas] = useState([])
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    listarAlmacenes().then((r) => {
      setAgencias(r.content)
      if (!agenciaFija && r.content.length > 0) setAgenciaId((actual) => actual || String(r.content[0].id))
    }).catch(() => {})
  }, [agenciaFija])

  useEffect(() => {
    if (!agenciaId) return
    setCargando(true)
    setError('')
    const id = Number(agenciaId)
    Promise.all([
      pendientesDeDespacho(agenciaFija ? undefined : id),
      listarManifiestos(),
    ])
      .then(([p, m]) => {
        setPendientes(p.content.destinos)
        setSalidas(m.content.filter((x) => x.agenciaOrigen.id === id))
        setLlegadas(m.content.filter((x) => x.agenciaDestino.id === id))
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [agenciaId, agenciaFija])

  async function abrirManifiesto(destinoId) {
    setError('')
    try {
      const r = await crearManifiesto({
        agenciaDestinoId: destinoId,
        ...(agenciaFija ? {} : { agenciaOrigenId: Number(agenciaId) }),
      })
      navigate(`/despachos/${r.content.id}`)
    } catch (err) {
      setError(err.message)
    }
  }

  const abiertos = salidas.filter((m) => m.estado === 'abierto')
  const porLlegar = llegadas.filter((m) => m.estado === 'en_transito')
  const nombreAgencia = agencias.find((a) => String(a.id) === String(agenciaId))?.nombre

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Despachos</h1>
          <p className="page-sub">Clasificación por destino, manifiestos de salida y recepción en agencia.</p>
        </div>
        {agenciaFija ? (
          <span className="cell-secondary">Agencia: <strong>{nombreAgencia || '…'}</strong></span>
        ) : (
          <div className="field" style={{ marginBottom: 0, minWidth: 220 }}>
            <label htmlFor="desAgencia">Agencia</label>
            <select id="desAgencia" value={agenciaId} onChange={(e) => setAgenciaId(e.target.value)}>
              {agencias.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="filters">
        <button className={`filter-pill${vista === 'salidas' ? ' active' : ''}`} onClick={() => setVista('salidas')}>
          Salidas {abiertos.length > 0 && `(${abiertos.length} abierto/s)`}
        </button>
        <button className={`filter-pill${vista === 'llegadas' ? ' active' : ''}`} onClick={() => setVista('llegadas')}>
          Llegadas {porLlegar.length > 0 && `(${porLlegar.length} en camino)`}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {cargando && <p className="loading-text">Cargando…</p>}

      {!cargando && vista === 'salidas' && (
        <>
          <section className="panel" style={{ marginBottom: 16 }}>
            <h2>Por despachar</h2>
            <p className="cell-secondary panel-ayuda">
              Envíos admitidos en esta agencia que viajan a otra. Abre un manifiesto por destino y escanea los bultos.
            </p>
            {pendientes.length === 0 ? (
              <p className="cell-secondary">No hay envíos esperando despacho.</p>
            ) : (
              <div className="card-grid">
                {pendientes.map((g) => (
                  <div className="mini-card" key={g.agenciaDestino.id}>
                    <div className="mini-card-name">→ {g.agenciaDestino.nombre}</div>
                    <div className="mini-card-line"><span>Envíos</span><strong>{g.envios}</strong></div>
                    <div className="mini-card-line"><span>Bultos</span><strong>{g.bultos}</strong></div>
                    {g.devoluciones > 0 && (
                      <div className="mini-card-line">
                        <span>↩ Devoluciones al origen</span><strong>{g.devoluciones}</strong>
                      </div>
                    )}
                    {g.pendientesDePago > 0 && (
                      <div className="mini-card-line" style={{ color: 'var(--danger)' }}>
                        <span>Prepagados sin pago</span><strong>{g.pendientesDePago}</strong>
                      </div>
                    )}
                    <button className="btn btn-primary btn-block" style={{ marginTop: 10, fontSize: 12.5 }}
                      onClick={() => abrirManifiesto(g.agenciaDestino.id)}>
                      Abrir manifiesto
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <h2 className="section-title">Manifiestos de salida</h2>
          <TablaManifiestos manifiestos={salidas} vacio="Todavía no hay manifiestos de salida." />
        </>
      )}

      {!cargando && vista === 'llegadas' && (
        <>
          <h2 className="section-title">Manifiestos que llegan a esta agencia</h2>
          <TablaManifiestos manifiestos={llegadas} vacio="No hay manifiestos hacia esta agencia." />
        </>
      )}
    </div>
  )
}
