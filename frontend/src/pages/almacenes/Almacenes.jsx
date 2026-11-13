// Red de agencias: tablero con la carga de cada agencia (stock, despachos,
// reparto, llegadas, paquetes estancados) y ficha con inventario y kardex.
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AlmacenForm from './AlmacenForm'
import FichaAlmacen, { BarraOcupacion, SECCIONES } from './FichaAlmacen'
import { getUsuario, panelAlmacenes, listarZonas, listarUsuarios } from '../../api'
import { enlaceWhatsApp, iniciales } from '../clientes/formato'

export default function Almacenes() {
  const usuario = getUsuario()
  const esAdmin = usuario?.rol === 'admin'
  const [params, setParams] = useSearchParams()
  const fichaId = Number(params.get('ficha')) || null
  const seccionFicha = params.get('seccion') || null
  const verInactivas = params.get('inactivas') === '1'

  const [datos, setDatos] = useState({ content: [], resumen: null })
  const [zonas, setZonas] = useState([])
  const [usuarios, setUsuarios] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [form, setForm] = useState(null) // null cerrado | { almacen?: {...} }
  const [versionFicha, setVersionFicha] = useState(0)
  const [busqueda, setBusqueda] = useState('')

  const cambiarParams = useCallback((cambios) => {
    setParams((actual) => {
      const nuevo = new URLSearchParams(actual)
      Object.entries(cambios).forEach(([k, v]) => (v ? nuevo.set(k, v) : nuevo.delete(k)))
      return nuevo
    }, { replace: true })
  }, [setParams])

  const cargar = useCallback(() => {
    setError('')
    return panelAlmacenes(verInactivas)
      .then(setDatos)
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false))
  }, [verInactivas])

  useEffect(() => { cargar() }, [cargar])
  useEffect(() => {
    listarZonas().then((r) => setZonas(r.content)).catch(() => {})
    if (esAdmin) listarUsuarios().then((r) => setUsuarios(r.content)).catch(() => {})
  }, [esAdmin])

  function avisar(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  const abrirFicha = (id, seccion) => cambiarParams({ ficha: id, seccion })
  const { content: almacenes, resumen } = datos
  const filtro = busqueda.trim().toLowerCase()
  const visibles = filtro
    ? almacenes.filter((a) => [a.nombre, a.codigo, a.zona, a.calle].some((v) => v?.toLowerCase().includes(filtro)))
    : almacenes
  const esMiAgencia = almacenes.length === 1 && !esAdmin

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{esMiAgencia ? 'Mi agencia' : 'Almacenes y agencias'}</h1>
          <p className="page-sub">
            {esMiAgencia
              ? 'Lo que tienes en el local, lo que debes despachar y lo que te está llegando'
              : 'Carga de trabajo de cada agencia en tiempo real: stock, despachos, reparto y llegadas'}
          </p>
        </div>
        {esAdmin && (
          <div className="cli-header-actions">
            <button className="btn btn-primary" onClick={() => setForm({})}>+ Nueva agencia</button>
          </div>
        )}
      </div>

      {resumen && almacenes.length > 0 && (
        <div className="cli-kpis cli-kpis-top">
          <div className="cli-kpi" title="Bultos físicamente en las agencias (por despachar + para reparto)">
            <span>En agencias</span><strong>{resumen.stockBultos}</strong><small>bultos en el local</small>
          </div>
          <div className="cli-kpi"><span>Por despachar</span><strong>{resumen.porDespachar}</strong><small>bultos</small></div>
          <div className="cli-kpi"><span>Para reparto</span><strong>{resumen.paraReparto}</strong><small>bultos</small></div>
          <div className="cli-kpi"><span>Por llegar</span><strong>{resumen.porLlegar}</strong><small>bultos</small></div>
          <div className="cli-kpi"><span>En reparto</span><strong>{resumen.enReparto}</strong><small>bultos</small></div>
          {resumen.porDevolver > 0 && (
            <div className="cli-kpi alerta" title="Paquetes que deben volver a su remitente">
              <span>Por devolver</span><strong>{resumen.porDevolver}</strong><small>bultos</small>
            </div>
          )}
          <div className={`cli-kpi${resumen.estancados > 0 ? ' alerta' : ''}`} title={`Envíos con ${resumen.diasEstancado} o más días sin moverse`}>
            <span>Estancados</span><strong>{resumen.estancados}</strong><small>envíos</small>
          </div>
        </div>
      )}

      {esAdmin && almacenes.length > 0 && (
        <div className="cli-toolbar">
          <input type="search" className="cli-buscar" aria-label="Buscar agencia" placeholder="Buscar por nombre, código, zona o dirección…"
            value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
          <label className="check-line" style={{ margin: 0 }}>
            <input type="checkbox" checked={verInactivas} onChange={(e) => cambiarParams({ inactivas: e.target.checked ? '1' : '' })} />
            <span>Mostrar desactivadas</span>
          </label>
        </div>
      )}

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando agencias…</p>
      ) : almacenes.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>Todavía no hay agencias</h3>
            <p>
              {esAdmin
                ? 'Crea la primera con "+ Nueva agencia": sin al menos una no se pueden admitir envíos.'
                : 'Pide a un administrador que cree una agencia: sin al menos una no se pueden admitir envíos.'}
            </p>
          </div>
        </div>
      ) : visibles.length === 0 ? (
        <p className="cell-secondary">Ninguna agencia coincide con “{busqueda}”.</p>
      ) : (
        <div className="alm-grid">
          {visibles.map((a) => {
            const m = a.metricas
            return (
              <article key={a.id} className={`alm-card${a.activo ? '' : ' inactivo'}${m.estancados ? ' con-alerta' : ''}`}>
                <button className="alm-card-head" onClick={() => abrirFicha(a.id)}>
                  <span className="cli-avatar alm-avatar" aria-hidden="true">{iniciales(a.nombre)}</span>
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span className="cell-primary cli-ellipsis">{a.nombre}</span>
                    <span className="cell-secondary cli-ellipsis">
                      <span className="cell-mono">{a.codigo}</span>{a.zona ? ` · ${a.zona}` : ''}
                    </span>
                  </span>
                  {!a.activo && <span className="cli-chip inactivo">Inactiva</span>}
                </button>

                <div className="alm-card-flujo">
                  {['por_despachar', 'para_reparto', 'por_llegar', 'en_reparto'].map((s) => (
                    <button key={s} onClick={() => abrirFicha(a.id, s)} title={SECCIONES[s].ayuda}>
                      <strong>{m.secciones[s].bultos}</strong>
                      <span>{SECCIONES[s].titulo}</span>
                    </button>
                  ))}
                </div>

                <div className="alm-card-stock">
                  <div className="alm-ocupacion-top">
                    <span><strong>{m.stockBultos}</strong> bulto(s) en el local</span>
                    {m.ocupacion != null ? <span>{m.ocupacion}% de {a.capacidadBultos}</span> : <span className="cell-secondary">Sin capacidad definida</span>}
                  </div>
                  {m.ocupacion != null && <BarraOcupacion valor={m.ocupacion} />}
                </div>

                {m.secciones.por_devolver?.bultos > 0 && (
                  <button className="cli-hint alm-link" onClick={() => abrirFicha(a.id, 'por_devolver')}>
                    ↩ {m.secciones.por_devolver.envios} envío(s) por devolver al remitente
                  </button>
                )}
                {m.estancados > 0 && (
                  <button className="cli-hint error alm-link" onClick={() => abrirFicha(a.id, 'stock')}>
                    ⚠ {m.estancados} envío(s) con {resumen.diasEstancado}+ días sin moverse
                  </button>
                )}

                <div className="alm-card-pie">
                  <span className="cli-ellipsis" title={a.calle}>{a.calle}</span>
                  <span className="cell-secondary">
                    {a.telefono ? <a href={`tel:${a.telefono}`}>{a.telefono}</a> : 'Sin teléfono'}
                    {' · '}{a.personal} persona(s){a.responsable ? ` · Resp.: ${a.responsable}` : ''}
                  </span>
                  {a.horario && <span className="cell-secondary cli-ellipsis">🕒 {a.horario}</span>}
                </div>

                <div className="row-actions alm-card-acciones">
                  <button className="btn-xs" onClick={() => abrirFicha(a.id)}>Ver ficha</button>
                  <button className="btn-xs" onClick={() => abrirFicha(a.id, 'stock')}>Inventario</button>
                  {esAdmin && <button className="btn-xs" onClick={() => setForm({ almacen: a })}>Editar</button>}
                  {a.latitud != null && a.longitud != null && (
                    <a className="btn-xs" href={`https://www.google.com/maps?q=${a.latitud},${a.longitud}`} target="_blank" rel="noreferrer">Mapa</a>
                  )}
                  {a.telefono && <a className="btn-xs" href={enlaceWhatsApp(a.telefono)} target="_blank" rel="noreferrer">WhatsApp</a>}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {fichaId && (
        <FichaAlmacen
          key={`${fichaId}-${seccionFicha || ''}`}
          almacenId={fichaId}
          esAdmin={esAdmin}
          pausado={Boolean(form)}
          version={versionFicha}
          seccionInicial={seccionFicha}
          onClose={() => cambiarParams({ ficha: '', seccion: '' })}
          onEditar={(a) => setForm({ almacen: a })}
          onCambio={cargar}
        />
      )}

      {form && (
        <AlmacenForm
          almacen={form.almacen}
          zonas={zonas}
          usuarios={usuarios}
          onClose={() => setForm(null)}
          onGuardado={(a, texto) => {
            setForm(null)
            avisar(texto)
            cargar()
            if (fichaId === a.id) setVersionFicha((v) => v + 1)
          }}
        />
      )}
    </div>
  )
}
