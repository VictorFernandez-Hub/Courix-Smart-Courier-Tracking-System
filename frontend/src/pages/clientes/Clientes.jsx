// Gestion de clientes: indicadores, busqueda con filtros, listado paginado
// con actividad de cada cliente, ficha 360 y exportacion.
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ClienteForm from './ClienteForm'
import FichaCliente from './FichaCliente'
import { buscarClientes, exportarClientes, listarZonas, getUsuario } from '../../api'
import { ETIQUETA_DOC, fechaCorta, haceCuanto, enlaceWhatsApp, iniciales } from './formato'

const POR_PAGINA = 20

export default function Clientes() {
  const esAdmin = getUsuario()?.rol === 'admin'
  // Filtros en la URL: se pueden compartir y sobreviven al recargar
  const [params, setParams] = useSearchParams()
  const filtros = {
    q: params.get('q') || '',
    estado: params.get('estado') || 'activos',
    tipo: params.get('tipo') || '',
    avisos: params.get('avisos') || '',
    orden: params.get('orden') || 'actividad',
    pagina: Number(params.get('pagina')) || 1,
  }
  const fichaId = Number(params.get('ficha')) || null

  const [busqueda, setBusqueda] = useState(filtros.q)
  const [datos, setDatos] = useState({ content: [], paginacion: {}, resumen: null })
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [zonas, setZonas] = useState([])
  const [form, setForm] = useState(null) // null cerrado | { cliente?: {...} }
  const [versionFicha, setVersionFicha] = useState(0)
  const [exportando, setExportando] = useState(false)

  const cambiarFiltros = useCallback((cambios, reiniciarPagina = true) => {
    setParams((actual) => {
      const nuevo = new URLSearchParams(actual)
      Object.entries({ ...cambios, ...(reiniciarPagina ? { pagina: 1 } : {}) }).forEach(([k, v]) => {
        if (v === '' || v === null || v === undefined || (k === 'pagina' && v === 1)) nuevo.delete(k)
        else nuevo.set(k, v)
      })
      return nuevo
    }, { replace: true })
  }, [setParams])

  const { q, estado, tipo, avisos, orden, pagina } = filtros
  const cargar = useCallback(() => {
    setCargando(true)
    setError('')
    return buscarClientes({ q, estado, tipo, avisos, orden, pagina, por_pagina: POR_PAGINA })
      .then(setDatos)
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false))
  }, [q, estado, tipo, avisos, orden, pagina])

  useEffect(() => { cargar() }, [cargar])
  useEffect(() => { listarZonas().then((r) => setZonas(r.content)).catch(() => {}) }, [])

  // Busqueda con espera: no se consulta en cada tecla
  useEffect(() => {
    const t = setTimeout(() => { if (busqueda.trim() !== q) cambiarFiltros({ q: busqueda.trim() }) }, 350)
    return () => clearTimeout(t)
  }, [busqueda, q, cambiarFiltros])

  function avisar(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  async function exportar() {
    setExportando(true)
    setError('')
    try {
      await exportarClientes({ q, estado, tipo, avisos })
    } catch (e) {
      setError(e.message)
    } finally {
      setExportando(false)
    }
  }

  const { content: clientes, paginacion, resumen } = datos
  const hayFiltros = q || estado !== 'activos' || tipo || avisos
  const abrirFicha = (id) => cambiarFiltros({ ficha: id }, false)

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Clientes</h1>
          <p className="page-sub">Remitentes y destinatarios: datos, direcciones, envíos y cobranza</p>
        </div>
        <div className="cli-header-actions">
          {esAdmin && (
            <button className="btn btn-secondary" onClick={exportar} disabled={exportando} title="Descarga la vista actual en CSV (queda registrado)">
              {exportando ? 'Exportando…' : '⭳ Exportar CSV'}
            </button>
          )}
          <button className="btn btn-primary" onClick={() => setForm({})}>+ Nuevo cliente</button>
        </div>
      </div>

      {resumen && (
        <div className="cli-kpis cli-kpis-top">
          <button className={`cli-kpi${estado === 'activos' && !tipo && !avisos ? ' active' : ''}`} onClick={() => cambiarFiltros({ estado: 'activos', tipo: '', avisos: '' })}>
            <span>Activos</span><strong>{resumen.activos}</strong>
          </button>
          <button className={`cli-kpi${tipo === 'empresa' ? ' active' : ''}`} onClick={() => cambiarFiltros({ tipo: tipo === 'empresa' ? '' : 'empresa' })}>
            <span>Empresas</span><strong>{resumen.empresas}</strong>
          </button>
          <button className={`cli-kpi${avisos === 'no' ? ' active' : ''}`} onClick={() => cambiarFiltros({ avisos: avisos === 'no' ? '' : 'no' })} title="Clientes que no aceptaron avisos por WhatsApp o correo">
            <span>Sin avisos</span><strong>{resumen.sinAvisos}</strong>
          </button>
          <div className={`cli-kpi${resumen.sinDocumento > 0 ? ' alerta' : ''}`} title="Sin documento no se les puede emitir comprobante con su nombre">
            <span>Sin documento</span><strong>{resumen.sinDocumento}</strong>
          </div>
          <button className={`cli-kpi${estado === 'inactivos' ? ' active' : ''}`} onClick={() => cambiarFiltros({ estado: estado === 'inactivos' ? 'activos' : 'inactivos' })}>
            <span>Inactivos</span><strong>{resumen.inactivos}</strong>
          </button>
        </div>
      )}

      <div className="cli-toolbar">
        <input type="search" className="cli-buscar" aria-label="Buscar clientes"
          placeholder="Buscar por nombre, DNI/RUC, teléfono o correo…"
          value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
        <select aria-label="Estado" value={estado} onChange={(e) => cambiarFiltros({ estado: e.target.value })}>
          <option value="activos">Activos</option>
          <option value="inactivos">Inactivos</option>
          <option value="todos">Todos</option>
        </select>
        <select aria-label="Tipo de cliente" value={tipo} onChange={(e) => cambiarFiltros({ tipo: e.target.value })}>
          <option value="">Personas y empresas</option>
          <option value="persona">Solo personas</option>
          <option value="empresa">Solo empresas</option>
        </select>
        <select aria-label="Ordenar" value={orden} onChange={(e) => cambiarFiltros({ orden: e.target.value })}>
          <option value="actividad">Actividad reciente</option>
          <option value="nombre">Nombre (A–Z)</option>
          <option value="recientes">Registrados recientemente</option>
        </select>
        {hayFiltros && (
          <button className="btn-xs" onClick={() => { setBusqueda(''); cambiarFiltros({ q: '', estado: '', tipo: '', avisos: '' }) }}>Limpiar filtros</button>
        )}
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando && clientes.length === 0 ? (
        <p className="loading-text">Cargando clientes…</p>
      ) : clientes.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>{hayFiltros ? 'Ningún cliente coincide' : 'Todavía no hay clientes'}</h3>
            <p>{hayFiltros ? 'Prueba con otro término o limpia los filtros.' : 'Registra el primero con "Nuevo cliente".'}</p>
          </div>
        </div>
      ) : (
        <div className={`manifest cli-tabla${cargando ? ' cargando' : ''}`}>
          <div className="manifest-row head">
            <span>Cliente</span>
            <span>Contacto</span>
            <span>Envíos</span>
            <span>Última actividad</span>
            <span />
          </div>
          {clientes.map((c) => (
            <div key={c.id} className={`manifest-row${c.activo ? '' : ' inactivo'}`}>
              <button className="cli-nombre" data-label="Cliente" onClick={() => abrirFicha(c.id)}>
                <span className={`cli-avatar${c.tipoCliente === 'empresa' ? ' empresa' : ''}`} aria-hidden="true">{iniciales(c.nombre)}</span>
                <span style={{ minWidth: 0 }}>
                  <span className="cell-primary cli-ellipsis">{c.nombre}</span>
                  <span className="cell-secondary">
                    {c.dni ? <>{ETIQUETA_DOC[c.tipoDocumento] || 'Doc.'} <span className="cell-mono">{c.dni}</span></> : 'Sin documento'}
                  </span>
                  <span className="cli-chips">
                    {c.tipoCliente === 'empresa' && <span className="cli-chip empresa">Empresa</span>}
                    {!c.activo && <span className="cli-chip inactivo">Inactivo</span>}
                    {!c.recibeAvisos && <span className="cli-chip" title="No aceptó avisos">Sin avisos</span>}
                  </span>
                </span>
              </button>
              <span data-label="Contacto" style={{ minWidth: 0 }}>
                <a className="cell-mono" href={enlaceWhatsApp(c.telefono)} target="_blank" rel="noreferrer" title="Escribir por WhatsApp">{c.telefono}</a>
                {c.email && <span className="cell-secondary cli-ellipsis">{c.email}</span>}
              </span>
              <span data-label="Envíos">
                <strong>{c.totalEnvios}</strong>
                {c.enviosEnCurso > 0 && <span className="cli-chip curso" style={{ marginLeft: 6 }}>{c.enviosEnCurso} en curso</span>}
              </span>
              <span data-label="Última actividad" className="cell-secondary">
                {c.ultimaActividad ? <span title={fechaCorta(c.ultimaActividad, true)}>{haceCuanto(c.ultimaActividad)}</span> : 'Sin envíos'}
              </span>
              <span className="row-actions">
                <button className="btn-xs" onClick={() => abrirFicha(c.id)}>Ver ficha</button>
                <button className="btn-xs" onClick={() => setForm({ cliente: c })}>Editar</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {clientes.length > 0 && (
        <div className="cli-paginacion">
          <span className="cell-secondary">
            {(pagina - 1) * POR_PAGINA + 1}–{(pagina - 1) * POR_PAGINA + clientes.length} de {paginacion.totalRegistros}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" disabled={pagina <= 1} onClick={() => cambiarFiltros({ pagina: pagina - 1 }, false)}>← Anterior</button>
            <button className="btn btn-secondary" disabled={pagina >= (paginacion.totalPaginas || 1)} onClick={() => cambiarFiltros({ pagina: pagina + 1 }, false)}>Siguiente →</button>
          </div>
        </div>
      )}

      {fichaId && (
        <FichaCliente
          clienteId={fichaId}
          zonas={zonas}
          pausado={Boolean(form)}
          version={versionFicha}
          onClose={() => cambiarFiltros({ ficha: '' }, false)}
          onEditar={(c) => setForm({ cliente: c })}
          onCambio={cargar}
        />
      )}

      {form && (
        <ClienteForm
          cliente={form.cliente}
          onClose={() => setForm(null)}
          onGuardado={(c, texto) => {
            setForm(null)
            avisar(texto)
            cargar()
            if (fichaId === c.id) setVersionFicha((v) => v + 1)
            else if (!form.cliente) abrirFicha(c.id) // recien creado: se abre su ficha para agregar direccion
          }}
        />
      )}
    </div>
  )
}
