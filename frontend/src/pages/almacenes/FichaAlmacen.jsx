// Ficha de una agencia en panel lateral: carga de trabajo, inventario fisico
// con antiguedad, kardex de bultos, personal y bitacora.
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EstadoBadge from '../../components/ui/EstadoBadge'
import {
  obtenerAlmacen, inventarioAlmacen, exportarInventario, movimientosAlmacen, actividadAlmacen,
  activarAlmacen, desactivarAlmacen,
} from '../../api'
import { fechaCorta, haceCuanto, enlaceWhatsApp, iniciales } from '../clientes/formato'

export const SECCIONES = {
  por_ingresar: { titulo: 'Por ingresar', ayuda: 'Admitidos aquí; el paquete aún no llega al mostrador' },
  por_despachar: { titulo: 'Por despachar', ayuda: 'En la agencia; deben viajar a otra en un manifiesto' },
  para_reparto: { titulo: 'Para reparto', ayuda: 'En la agencia; se reparten desde aquí' },
  por_llegar: { titulo: 'Por llegar', ayuda: 'Vienen en camino desde otra agencia' },
  en_reparto: { titulo: 'En reparto', ayuda: 'Salieron con un repartidor de esta agencia' },
  por_devolver: { titulo: 'Por devolver', ayuda: 'En la agencia; deben volver al remitente (entregarlo o despacharlo de regreso)' },
}

const MOVIMIENTOS = {
  admitido: 'Ingresó (admisión)',
  manifestado: 'Cargado a manifiesto',
  retirado_de_manifiesto: 'Retirado del manifiesto',
  despachado: 'Salió (despacho)',
  recibido_en_destino: 'Llegó (recepción)',
  faltante: 'Faltante en recepción',
  recibido_tarde: 'Llegó tarde (faltante regularizado)',
}

const ACCIONES = {
  almacen_creado: 'Creó la agencia',
  almacen_editado: 'Editó datos',
  almacen_desactivado: 'Desactivó la agencia',
  almacen_activado: 'Reactivó la agencia',
  inventario_exportado: 'Descargó la hoja de inventario',
}

const CAMPOS = {
  nombre: 'nombre', codigo: 'código', calle: 'dirección', referencia: 'referencia', zonaId: 'zona',
  telefono: 'teléfono', email: 'correo', horario: 'horario', responsableId: 'responsable',
  capacidadBultos: 'capacidad', latitud: 'ubicación', longitud: 'ubicación',
}

function detalleActividad(a) {
  try {
    const d = JSON.parse(a.detalle || 'null')
    if (d?.campos) return [...new Set(d.campos.map((c) => CAMPOS[c] || c))].join(', ')
    if (d?.motivo) return `Motivo: ${d.motivo}`
    if (d?.bultos != null) return `${d.envios} envío(s), ${d.bultos} bulto(s)`
  } catch { /* detalle libre */ }
  return ''
}

const POR_PAGINA = 25

export default function FichaAlmacen({ almacenId, esAdmin, pausado, version, seccionInicial, onClose, onEditar, onCambio }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState(seccionInicial ? 'inventario' : 'resumen')
  const [ficha, setFicha] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')

  const [filtroInv, setFiltroInv] = useState({ seccion: seccionInicial || 'stock', q: '', estancados: false, pagina: 1 })
  const [busquedaInv, setBusquedaInv] = useState('')
  const [inventario, setInventario] = useState(null)
  const [exportando, setExportando] = useState(false)
  const [movs, setMovs] = useState(null)
  const [paginaMovs, setPaginaMovs] = useState(1)
  const [actividad, setActividad] = useState(null)

  const cargarFicha = useCallback(() => {
    setError('')
    return obtenerAlmacen(almacenId).then((r) => setFicha(r.content)).catch((e) => setError(e.message))
  }, [almacenId])

  useEffect(() => { setFicha(null); setActividad(null); setMovs(null); cargarFicha() }, [cargarFicha])
  useEffect(() => { if (version) cargarFicha() }, [version, cargarFicha])

  useEffect(() => {
    if (tab !== 'inventario') return
    inventarioAlmacen(almacenId, { ...filtroInv, por_pagina: POR_PAGINA })
      .then(setInventario).catch((e) => setError(e.message))
  }, [tab, almacenId, filtroInv])

  // Busqueda del inventario con espera (acepta guia, codigo de bulto o nombre)
  useEffect(() => {
    const t = setTimeout(() => {
      setFiltroInv((f) => (f.q === busquedaInv.trim() ? f : { ...f, q: busquedaInv.trim(), pagina: 1 }))
    }, 350)
    return () => clearTimeout(t)
  }, [busquedaInv])

  useEffect(() => {
    if (tab !== 'movimientos') return
    movimientosAlmacen(almacenId, { pagina: paginaMovs, por_pagina: POR_PAGINA }).then(setMovs).catch((e) => setError(e.message))
  }, [tab, almacenId, paginaMovs])

  useEffect(() => {
    if (tab === 'actividad') actividadAlmacen(almacenId).then((r) => setActividad(r.content)).catch((e) => setError(e.message))
  }, [tab, almacenId])

  useEffect(() => {
    const alPulsar = (e) => { if (e.key === 'Escape' && !pausado) onClose() }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [onClose, pausado])

  function avisar(texto) {
    setAviso(texto)
    setTimeout(() => setAviso(''), 3000)
  }

  async function ejecutar(accion, mensaje) {
    setError('')
    try {
      await accion()
      await cargarFicha()
      setActividad(null)
      if (tab === 'actividad') actividadAlmacen(almacenId).then((r) => setActividad(r.content)).catch(() => {})
      onCambio?.()
      if (mensaje) avisar(mensaje)
    } catch (e) {
      setError(e.message)
    }
  }

  async function descargarInventario() {
    setExportando(true)
    setError('')
    try {
      const { pagina, ...filtros } = filtroInv // la hoja lleva todo, sin paginar
      await exportarInventario(almacenId, filtros)
      if (tab === 'actividad') setActividad(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setExportando(false)
    }
  }

  const cambiarFiltro = (cambios) => setFiltroInv((f) => ({ ...f, ...cambios, pagina: cambios.pagina ?? 1 }))

  if (!ficha) {
    return (
      <div className="drawer-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
        <aside className="drawer drawer-ancho" aria-label="Ficha de la agencia">
          {error ? <div className="error-banner">{error}</div> : <p className="loading-text">Cargando agencia…</p>}
        </aside>
      </div>
    )
  }

  const { almacen: a, metricas: m, personal, manifiestos, responsable } = ficha
  const secc = m.secciones

  function toggleActivo() {
    if (a.activo) {
      const motivo = window.prompt(`¿Desactivar "${a.nombre}"? No podrá admitir ni recibir envíos.\n\nMotivo (opcional):`, '')
      if (motivo === null) return
      ejecutar(() => desactivarAlmacen(a.id, motivo || undefined), 'Agencia desactivada')
    } else {
      ejecutar(() => activarAlmacen(a.id), 'Agencia reactivada')
    }
  }

  const irAPedido = (fila) => navigate(`/pedidos?q=${encodeURIComponent(fila.codigoGuia || fila.id)}`)

  return (
    <div className="drawer-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="drawer drawer-ancho" aria-label={`Ficha de ${a.nombre}`}>
        <header className="drawer-head">
          <div className="cli-avatar lg alm-avatar" aria-hidden="true">{iniciales(a.nombre)}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 className="drawer-title">{a.nombre}</h2>
            <div className="cli-chips">
              <span className="cli-chip cell-mono">{a.codigo}</span>
              {ficha.zona && <span className="cli-chip">{ficha.zona}</span>}
              {!a.activo && <span className="cli-chip inactivo">Inactiva</span>}
              {m.estancados > 0 && <span className="cli-chip alerta">{m.estancados} estancado(s)</span>}
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Cerrar ficha">✕</button>
        </header>

        <div className="drawer-actions">
          {a.activo && <button className="btn btn-primary btn-sm" onClick={() => navigate('/despachos')}>Ir a despachos</button>}
          {a.activo && <button className="btn btn-secondary btn-sm" onClick={() => navigate('/pedidos/nuevo')}>+ Admitir envío</button>}
          {esAdmin && <button className="btn btn-secondary btn-sm" onClick={() => onEditar(a)}>Editar</button>}
          {esAdmin && (
            <button className={`btn btn-sm ${a.activo ? 'btn-ghost texto-alerta' : 'btn-success'}`} onClick={toggleActivo}>
              {a.activo ? 'Desactivar' : 'Reactivar'}
            </button>
          )}
        </div>

        {aviso && <div className="success-banner">{aviso}</div>}
        {error && <div className="error-banner">{error}</div>}
        {!a.activo && a.motivoDesactivacion && <div className="error-banner">Desactivada: {a.motivoDesactivacion}</div>}

        <nav className="cli-tabs" role="tablist">
          {[['resumen', 'Resumen'], ['inventario', `Inventario (${m.stockEnvios})`], ['movimientos', 'Movimientos'], ['actividad', 'Actividad']].map(([id, txt]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{txt}</button>
          ))}
        </nav>

        {tab === 'resumen' && (
          <div className="drawer-body">
            <h3 className="section-title" style={{ marginTop: 0 }}>Carga de trabajo ahora</h3>
            <div className="cli-kpis alm-flujo">
              {Object.entries(SECCIONES).map(([id, s]) => (
                <button key={id} className={`cli-kpi${id === 'por_despachar' && secc[id].estancados ? ' alerta' : ''}`} title={s.ayuda}
                  onClick={() => { cambiarFiltro({ seccion: id, estancados: false }); setTab('inventario') }}>
                  <span>{s.titulo}</span>
                  <strong>{secc[id].envios}</strong>
                  <small>{secc[id].bultos} bulto(s)</small>
                </button>
              ))}
            </div>

            <div className="alm-ocupacion-bloque">
              <div className="alm-ocupacion-top">
                <span>En la agencia: <strong>{m.stockBultos}</strong> bulto(s) de {m.stockEnvios} envío(s)</span>
                {m.ocupacion != null && <span>{m.ocupacion}% de {a.capacidadBultos}</span>}
              </div>
              {m.ocupacion != null && <BarraOcupacion valor={m.ocupacion} />}
              {m.estancados > 0 && (
                <button className="cli-hint error alm-link" onClick={() => { cambiarFiltro({ seccion: 'stock', estancados: true }); setTab('inventario') }}>
                  ⚠ {m.estancados} envío(s) llevan {m.diasEstancado}+ días sin moverse: revisar →
                </button>
              )}
            </div>

            <h3 className="section-title">Hoy</h3>
            <div className="cli-kpis">
              <div className="cli-kpi"><span>Admitidos</span><strong>{m.admitidosHoy}</strong></div>
              <div className="cli-kpi"><span>Entregados</span><strong>{m.entregadosHoy}</strong></div>
              <div className="cli-kpi"><span>Manifiestos despachados</span><strong>{m.manifiestosDespachadosHoy}</strong></div>
              <div className="cli-kpi"><span>Recojos pendientes</span><strong>{m.recojosPendientes}</strong></div>
            </div>

            {manifiestos.length > 0 && (
              <>
                <h3 className="section-title">Manifiestos en curso</h3>
                {manifiestos.map((x) => (
                  <button key={x.id} className="cli-envio alm-manifiesto" onClick={() => navigate(`/despachos/${x.id}`)}>
                    <div className="cli-envio-top">
                      <span className="tag-id">{x.codigo || `#${x.id}`}</span>
                      <span className={`cli-chip ${x.estado === 'en_transito' ? 'curso' : ''}`}>{x.estado === 'en_transito' ? 'En tránsito' : 'Abierto'}</span>
                    </div>
                    <div className="cell-secondary">
                      {x.sentido === 'salida' ? `↗ Sale hacia ${x.contraparte}` : `↙ Llega desde ${x.contraparte}`} · {x.bultos} bulto(s)
                      {x.transportista ? ` · ${x.transportista}` : ''}
                    </div>
                  </button>
                ))}
              </>
            )}

            <h3 className="section-title">Datos de la agencia</h3>
            <div className="dato-lista">
              <div>
                <span>Dirección</span>
                <strong>
                  {a.calle}
                  {a.latitud != null && a.longitud != null && (
                    <> · <a href={`https://www.google.com/maps?q=${a.latitud},${a.longitud}`} target="_blank" rel="noreferrer">Ver en mapa</a></>
                  )}
                </strong>
              </div>
              {a.referencia && <div><span>Referencia</span><strong>{a.referencia}</strong></div>}
              <div><span>Teléfono</span><strong className="cell-mono">{a.telefono ? <a href={`tel:${a.telefono}`}>{a.telefono}</a> : '—'}</strong></div>
              <div><span>Correo</span><strong>{a.email ? <a href={`mailto:${a.email}`}>{a.email}</a> : '—'}</strong></div>
              <div><span>Horario</span><strong>{a.horario || '—'}</strong></div>
              <div>
                <span>Responsable</span>
                <strong>
                  {responsable ? responsable.nombre : 'Sin asignar'}
                  {responsable?.celular && <> · <a href={enlaceWhatsApp(responsable.celular)} target="_blank" rel="noreferrer">WhatsApp</a></>}
                </strong>
              </div>
              <div><span>Capacidad</span><strong>{a.capacidadBultos ? `${a.capacidadBultos} bultos` : 'Sin límite definido'}</strong></div>
              <div><span>Creada</span><strong>{fechaCorta(a.fechaCreacion)}</strong></div>
            </div>

            <h3 className="section-title">Personal ({personal.filter((p) => p.activo).length})</h3>
            {personal.length === 0 ? (
              <p className="cell-secondary">Nadie tiene esta agencia asignada. Asígnala a los operadores en Configuración → Usuarios.</p>
            ) : (
              <div className="dato-lista">
                {personal.map((p) => (
                  <div key={p.id} style={p.activo ? undefined : { opacity: 0.55 }}>
                    <span>{p.nombre} <span className="cell-mono">@{p.usuario}</span>{!p.activo && ' (inactivo)'}</span>
                    <strong>{p.ultimoLogin ? `Entró ${haceCuanto(p.ultimoLogin)}` : 'Nunca entró'}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'inventario' && (
          <div className="drawer-body">
            <div className="alm-secciones" role="group" aria-label="Sección del inventario">
              {[['stock', 'En la agencia'], ...Object.entries(SECCIONES).map(([id, s]) => [id, s.titulo])].map(([id, txt]) => {
                const n = id === 'stock' ? m.stockEnvios : inventario?.conteos?.[id] ?? secc[id].envios
                return (
                  <button key={id} className={filtroInv.seccion === id ? 'active' : ''} onClick={() => cambiarFiltro({ seccion: id })}>
                    {txt} <span>{n}</span>
                  </button>
                )
              })}
            </div>
            <div className="cli-toolbar">
              <input type="search" className="cli-buscar" aria-label="Buscar en el inventario"
                placeholder="Guía, código de bulto o cliente…" value={busquedaInv} onChange={(e) => setBusquedaInv(e.target.value)} />
              <label className="check-line" style={{ margin: 0 }}>
                <input type="checkbox" checked={filtroInv.estancados} onChange={(e) => cambiarFiltro({ estancados: e.target.checked })} />
                <span>Solo estancados ({m.diasEstancado}+ días)</span>
              </label>
              <button className="btn-xs" onClick={descargarInventario} disabled={exportando} title="Una fila por bulto, con columna para marcar lo encontrado en el estante">
                {exportando ? 'Generando…' : '⭳ Hoja de conteo (CSV)'}
              </button>
            </div>
            <p className="cell-secondary alm-ayuda">{filtroInv.seccion === 'stock' ? 'Lo que está físicamente en la agencia.' : SECCIONES[filtroInv.seccion]?.ayuda} Primero lo urgente y lo más antiguo.</p>

            {!inventario ? <p className="loading-text">Cargando inventario…</p> : inventario.content.length === 0 ? (
              <p className="cell-secondary">No hay envíos en esta sección{filtroInv.q || filtroInv.estancados ? ' con esos filtros' : ''}.</p>
            ) : (
              <>
                {inventario.content.map((f) => (
                  <button key={f.id} className={`cli-envio alm-item${f.estancado ? ' estancado' : ''}`} onClick={() => irAPedido(f)} title="Abrir en Pedidos">
                    <div className="cli-envio-top">
                      <span className="tag-id">{f.codigoGuia || `#${String(f.id).padStart(5, '0')}`}</span>
                      <EstadoBadge estado={f.estado} />
                      {f.prioridad === 'urgente' && <span className="cli-chip alerta">Urgente</span>}
                      {filtroInv.seccion === 'stock' && <span className="cli-chip">{SECCIONES[f.seccion]?.titulo}</span>}
                    </div>
                    <div className="cell-primary">{f.destinatario || 'Sin destinatario'}</div>
                    <div className="cell-secondary">
                      {f.bultos} bulto(s){f.pesoKg ? ` · ${Number(f.pesoKg).toFixed(1)} kg` : ''}
                      {f.agenciaReparto && f.seccion === 'por_despachar' ? ` · va a ${f.agenciaReparto}` : ''}
                      {f.remitente ? ` · de ${f.remitente}` : ''}
                    </div>
                    <div className={`alm-antiguedad${f.estancado ? ' alerta' : ''}`} title={fechaCorta(f.desde, true)}>
                      {f.dias === 0 ? 'Hoy' : `${f.dias} día(s)`} en esta etapa
                    </div>
                  </button>
                ))}
                <Paginacion datos={inventario.paginacion} onCambiar={(p) => cambiarFiltro({ pagina: p })} />
              </>
            )}
          </div>
        )}

        {tab === 'movimientos' && (
          <div className="drawer-body">
            <p className="cell-secondary alm-ayuda">Kardex: cada bulto que entró, se cargó, salió, llegó o faltó en esta agencia.</p>
            {!movs ? <p className="loading-text">Cargando movimientos…</p> : movs.content.length === 0 ? (
              <p className="cell-secondary">Todavía no hay movimientos de bultos en esta agencia.</p>
            ) : (
              <>
                {movs.content.map((x) => (
                  <div key={x.id} className="timeline-item">
                    <div className={`timeline-dot alm-mov-${x.tipo}`} />
                    <div>
                      <div className="cell-primary">
                        {MOVIMIENTOS[x.tipo] || x.tipo} · <span className="cell-mono">{x.bulto || x.codigoGuia}</span>
                      </div>
                      <div className="cell-secondary">
                        {fechaCorta(x.fecha, true)} · {x.usuario || 'Sistema'}{x.manifiesto ? ` · ${x.manifiesto}` : ''}
                      </div>
                    </div>
                  </div>
                ))}
                <Paginacion datos={movs.paginacion} onCambiar={setPaginaMovs} />
              </>
            )}
          </div>
        )}

        {tab === 'actividad' && (
          <div className="drawer-body">
            {!actividad ? <p className="loading-text">Cargando actividad…</p> : actividad.length === 0 ? (
              <p className="cell-secondary">Sin cambios registrados (agencia anterior a la bitácora).</p>
            ) : actividad.map((x) => (
              <div key={x.id} className="timeline-item">
                <div className="timeline-dot" />
                <div>
                  <div className="cell-primary">{ACCIONES[x.accion] || x.accion}</div>
                  <div className="cell-secondary">
                    {fechaCorta(x.fecha, true)} · {x.usuario || 'Sistema'}
                    {detalleActividad(x) && <> · {detalleActividad(x)}</>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  )
}

export function BarraOcupacion({ valor }) {
  const nivel = valor >= 90 ? 'alto' : valor >= 70 ? 'medio' : 'bajo'
  return (
    <div className={`alm-barra ${nivel}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={valor} aria-label="Ocupación">
      <span style={{ width: `${Math.min(valor, 100)}%` }} />
    </div>
  )
}

function Paginacion({ datos, onCambiar }) {
  if (!datos || (datos.totalPaginas || 1) <= 1) return null
  return (
    <div className="cli-paginacion">
      <span className="cell-secondary">Página {datos.pagina} de {datos.totalPaginas} · {datos.totalRegistros} registros</span>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-secondary btn-sm" disabled={datos.pagina <= 1} onClick={() => onCambiar(datos.pagina - 1)}>←</button>
        <button className="btn btn-secondary btn-sm" disabled={datos.pagina >= datos.totalPaginas} onClick={() => onCambiar(datos.pagina + 1)}>→</button>
      </div>
    </div>
  )
}
