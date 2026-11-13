// Ficha 360 del cliente en un panel lateral: resumen comercial, direcciones,
// envios (como remitente y destinatario) y bitacora de cambios.
import CreditoCliente from './CreditoCliente'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EstadoBadge from '../../components/ui/EstadoBadge'
import DireccionForm from './DireccionForm'
import {
  obtenerCliente, pedidosDelCliente, actividadCliente, preferenciaAvisos,
  activarCliente, desactivarCliente, marcarDireccionPrincipal, eliminarDireccionCliente,
} from '../../api'
import { fechaCorta, haceCuanto, soles, enlaceWhatsApp, iniciales, ETIQUETA_DOC } from './formato'

const ACCIONES = {
  cliente_creado: 'Registró al cliente',
  cliente_editado: 'Editó datos',
  cliente_desactivado: 'Desactivó al cliente',
  cliente_activado: 'Reactivó al cliente',
  avisos_activados: 'Cliente aceptó avisos',
  avisos_desactivados: 'Cliente retiró su consentimiento de avisos',
  direccion_creada: 'Agregó una dirección',
  direccion_editada: 'Editó una dirección',
  direccion_principal: 'Cambió la dirección principal',
  direccion_eliminada: 'Eliminó una dirección',
}

const CAMPOS = {
  tipoCliente: 'tipo', nombre: 'nombre', tipoDocumento: 'tipo de doc.', dni: 'documento', telefono: 'teléfono',
  telefonoAlternativo: 'teléfono alterno', email: 'correo', notas: 'notas', recibeAvisos: 'avisos',
  calle: 'calle', referencia: 'referencia', zonaId: 'zona', etiqueta: 'etiqueta', latitud: 'ubicación',
  longitud: 'ubicación', esPrincipal: 'principal',
}

function detalleActividad(a) {
  try {
    const d = JSON.parse(a.detalle || 'null')
    if (d?.campos) return [...new Set(d.campos.map((c) => CAMPOS[c] || c))].join(', ')
    if (d?.motivo) return `Motivo: ${d.motivo}`
  } catch { /* detalle libre */ }
  return ''
}

export default function FichaCliente({ clienteId, zonas, pausado, version, onClose, onEditar, onCambio }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState('resumen')
  const [ficha, setFicha] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')

  const [envios, setEnvios] = useState({ content: [], paginacion: {} })
  const [rolEnvios, setRolEnvios] = useState('todos')
  const [paginaEnvios, setPaginaEnvios] = useState(1)
  const [cargandoEnvios, setCargandoEnvios] = useState(false)
  const [actividad, setActividad] = useState(null)
  const [direccionEditar, setDireccionEditar] = useState(undefined) // undefined = cerrado, null = nueva

  const cargarFicha = useCallback(() => {
    setError('')
    return obtenerCliente(clienteId).then((r) => setFicha(r.content)).catch((e) => setError(e.message))
  }, [clienteId])

  useEffect(() => { setFicha(null); setTab('resumen'); setActividad(null); cargarFicha() }, [cargarFicha])

  useEffect(() => {
    if (tab !== 'envios') return
    setCargandoEnvios(true)
    pedidosDelCliente(clienteId, { rol: rolEnvios, pagina: paginaEnvios })
      .then(setEnvios).catch((e) => setError(e.message)).finally(() => setCargandoEnvios(false))
  }, [tab, clienteId, rolEnvios, paginaEnvios])

  useEffect(() => {
    if (tab === 'actividad') actividadCliente(clienteId).then((r) => setActividad(r.content)).catch((e) => setError(e.message))
  }, [tab, clienteId])

  useEffect(() => {
    // Escape cierra la ficha, salvo que haya un formulario abierto encima
    const alPulsar = (e) => { if (e.key === 'Escape' && direccionEditar === undefined && !pausado) onClose() }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [onClose, direccionEditar, pausado])

  // El padre sube `version` cuando edita al cliente desde fuera de la ficha
  useEffect(() => { if (version) cargarFicha() }, [version, cargarFicha])

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
      if (tab === 'actividad') actividadCliente(clienteId).then((r) => setActividad(r.content)).catch(() => {})
      onCambio?.()
      if (mensaje) avisar(mensaje)
    } catch (e) {
      setError(e.message)
    }
  }

  if (!ficha) {
    return (
      <div className="drawer-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
        <aside className="drawer" aria-label="Ficha del cliente">
          {error ? <div className="error-banner">{error}</div> : <p className="loading-text">Cargando ficha…</p>}
        </aside>
      </div>
    )
  }

  const { cliente: c, estadisticas: st, direcciones } = ficha

  function toggleActivo() {
    if (c.activo) {
      const motivo = window.prompt(`¿Desactivar a ${c.nombre}? Ya no aparecerá al crear envíos.\n\nMotivo (opcional):`, '')
      if (motivo === null) return
      ejecutar(() => desactivarCliente(c.id, motivo || undefined), 'Cliente desactivado')
    } else {
      ejecutar(() => activarCliente(c.id), 'Cliente reactivado')
    }
  }

  function toggleAvisos() {
    const texto = c.recibeAvisos
      ? '¿El cliente pidió dejar de recibir avisos? Se registrará el retiro de su consentimiento.'
      : '¿El cliente aceptó recibir avisos de sus envíos? Se registrará su consentimiento.'
    if (window.confirm(texto)) ejecutar(() => preferenciaAvisos(c.id, !c.recibeAvisos), 'Preferencia de avisos actualizada')
  }

  function eliminarDireccion(d) {
    if (window.confirm(`¿Eliminar la dirección "${d.etiqueta || d.calle}"? Los envíos anteriores la conservan.`)) {
      ejecutar(() => eliminarDireccionCliente(d.id), 'Dirección eliminada')
    }
  }

  const nombreZona = (id) => zonas.find((z) => z.id === id)?.nombre

  return (
    <div className="drawer-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="drawer" aria-label={`Ficha de ${c.nombre}`}>
        <header className="drawer-head">
          <div className={`cli-avatar lg${c.tipoCliente === 'empresa' ? ' empresa' : ''}`} aria-hidden="true">{iniciales(c.nombre)}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 className="drawer-title">{c.nombre}</h2>
            <div className="cli-chips">
              <span className={`cli-chip ${c.tipoCliente}`}>{c.tipoCliente === 'empresa' ? 'Empresa' : 'Persona'}</span>
              {!c.activo && <span className="cli-chip inactivo">Inactivo</span>}
              {st.enCurso > 0 && <span className="cli-chip curso">{st.enCurso} en curso</span>}
              {st.incidenciasAbiertas > 0 && <span className="cli-chip alerta">{st.incidenciasAbiertas} incidencia(s)</span>}
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Cerrar ficha">✕</button>
        </header>

        <div className="drawer-actions">
          {c.activo && (
            <>
              <button className="btn btn-primary btn-sm" onClick={() => navigate(`/pedidos/nuevo?remitente=${c.id}`)}>+ Envío como remitente</button>
              <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/pedidos/nuevo?destinatario=${c.id}`)}>+ Envío para él/ella</button>
            </>
          )}
          <button className="btn btn-secondary btn-sm" onClick={() => onEditar(c)}>Editar</button>
          <button className={`btn btn-sm ${c.activo ? 'btn-ghost texto-alerta' : 'btn-success'}`} onClick={toggleActivo}>
            {c.activo ? 'Desactivar' : 'Reactivar'}
          </button>
        </div>

        {aviso && <div className="success-banner">{aviso}</div>}
        {error && <div className="error-banner">{error}</div>}
        {!c.activo && c.motivoDesactivacion && (
          <div className="error-banner">Desactivado: {c.motivoDesactivacion}</div>
        )}

        <nav className="cli-tabs" role="tablist">
          {[['resumen', 'Resumen'], ['direcciones', `Direcciones (${direcciones.length})`], ['envios', `Envíos (${st.total})`], ['credito', 'Crédito'], ['actividad', 'Actividad']].map(([id, txt]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{txt}</button>
          ))}
        </nav>

        {tab === 'resumen' && (
          <div className="drawer-body">
            <div className="cli-kpis">
              <div className="cli-kpi"><span>Enviados</span><strong>{st.enviados}</strong></div>
              <div className="cli-kpi"><span>Recibidos</span><strong>{st.recibidos}</strong></div>
              <div className="cli-kpi"><span>Entrega exitosa</span><strong>{st.tasaEntrega == null ? '—' : `${st.tasaEntrega}%`}</strong></div>
              <div className="cli-kpi"><span>Facturado</span><strong>{soles(st.montoFacturado)}</strong></div>
              <div className="cli-kpi"><span>Cobrado</span><strong>{soles(st.montoCobrado)}</strong></div>
              <div className={`cli-kpi${Number(st.saldoPendiente) > 0 ? ' alerta' : ''}`}><span>Por cobrar</span><strong>{soles(st.saldoPendiente)}</strong></div>
            </div>

            <h3 className="section-title">Datos de contacto</h3>
            <div className="dato-lista">
              <div><span>{ETIQUETA_DOC[c.tipoDocumento] || 'Documento'}</span><strong className="cell-mono">{c.dni || '—'}</strong></div>
              <div>
                <span>Teléfono</span>
                <strong className="cell-mono">
                  <a href={`tel:${c.telefono}`}>{c.telefono}</a>
                  {' · '}<a href={enlaceWhatsApp(c.telefono)} target="_blank" rel="noreferrer">WhatsApp</a>
                </strong>
              </div>
              {c.telefonoAlternativo && <div><span>Teléfono alterno</span><strong className="cell-mono"><a href={`tel:${c.telefonoAlternativo}`}>{c.telefonoAlternativo}</a></strong></div>}
              <div><span>Correo</span><strong>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}</strong></div>
              <div>
                <span>Avisos de envío</span>
                <strong>
                  {c.recibeAvisos ? 'Sí, acepta' : 'No acepta'}{' '}
                  <button className="btn-xs" onClick={toggleAvisos}>{c.recibeAvisos ? 'Retirar' : 'Activar'}</button>
                </strong>
              </div>
              {c.fechaConsentimiento && <div><span>Consentimiento registrado</span><strong>{fechaCorta(c.fechaConsentimiento, true)}</strong></div>}
            </div>

            {c.notas && (
              <>
                <h3 className="section-title">Notas internas</h3>
                <p className="cli-notas">{c.notas}</p>
              </>
            )}

            <h3 className="section-title">Historial</h3>
            <div className="dato-lista">
              <div><span>Cliente desde</span><strong>{fechaCorta(c.fechaCreacion)}{ficha.creadoPor ? ` · por ${ficha.creadoPor}` : ''}</strong></div>
              <div><span>Primer envío</span><strong>{fechaCorta(st.primerEnvio)}</strong></div>
              <div><span>Último envío</span><strong>{st.ultimoEnvio ? `${fechaCorta(st.ultimoEnvio)} (${haceCuanto(st.ultimoEnvio)})` : '—'}</strong></div>
              <div><span>Entregados / devueltos / cancelados</span><strong>{st.entregados} / {st.devueltos} / {st.cancelados}</strong></div>
            </div>
          </div>
        )}

        {tab === 'direcciones' && (
          <div className="drawer-body">
            {c.activo && (
              <button className="btn btn-secondary btn-block" onClick={() => setDireccionEditar(null)} style={{ marginBottom: 12 }}>+ Agregar dirección</button>
            )}
            {direcciones.length === 0 ? (
              <p className="cell-secondary">Sin direcciones registradas. Agrega una para poder enviarle paquetes.</p>
            ) : direcciones.map((d) => (
              <div key={d.id} className={`cli-dir${d.esPrincipal ? ' principal' : ''}`}>
                <div className="cli-dir-top">
                  <strong>{d.etiqueta || 'Dirección'}</strong>
                  {d.esPrincipal && <span className="cli-chip curso">Principal</span>}
                  {d.zonaId && <span className="cli-chip">{nombreZona(d.zonaId) || `Zona ${d.zonaId}`}</span>}
                </div>
                <div>{d.calle}</div>
                {d.referencia && <div className="cell-secondary">Ref.: {d.referencia}</div>}
                <div className="row-actions" style={{ marginTop: 8 }}>
                  {d.latitud != null && d.longitud != null && (
                    <a className="btn-xs" href={`https://www.google.com/maps?q=${d.latitud},${d.longitud}`} target="_blank" rel="noreferrer">Ver en mapa</a>
                  )}
                  <button className="btn-xs" onClick={() => setDireccionEditar(d)}>Editar</button>
                  {!d.esPrincipal && <button className="btn-xs" onClick={() => ejecutar(() => marcarDireccionPrincipal(d.id), 'Dirección principal actualizada')}>Hacer principal</button>}
                  <button className="btn-xs texto-alerta" onClick={() => eliminarDireccion(d)}>Eliminar</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'envios' && (
          <div className="drawer-body">
            <div className="segmented" role="group" aria-label="Rol del cliente" style={{ marginBottom: 12 }}>
              {[['todos', 'Todos'], ['remitente', 'Enviados'], ['destinatario', 'Recibidos']].map(([v, t]) => (
                <button key={v} className={rolEnvios === v ? 'active' : ''} onClick={() => { setRolEnvios(v); setPaginaEnvios(1) }}>{t}</button>
              ))}
            </div>
            {cargandoEnvios ? <p className="loading-text">Cargando envíos…</p> : envios.content.length === 0 ? (
              <p className="cell-secondary">No hay envíos en esta vista.</p>
            ) : (
              <>
                {envios.content.map((p) => (
                  <div key={p.id} className="cli-envio">
                    <div className="cli-envio-top">
                      <span className="tag-id">{p.codigoGuia || `#${String(p.id).padStart(5, '0')}`}</span>
                      <EstadoBadge estado={p.estado || 'pendiente'} />
                    </div>
                    <div className="cell-primary">{p.descripcionProducto || 'Sin descripción'}</div>
                    <div className="cell-secondary">
                      {p.rolCliente === 'remitente' ? '↗ Enviado' : '↙ Recibido'}
                      {p.contraparte ? (p.rolCliente === 'remitente' ? ` a ${p.contraparte}` : ` de ${p.contraparte}`) : ''}
                      {' · '}{soles(p.monto)} · {fechaCorta(p.fechaCreacion)}
                    </div>
                  </div>
                ))}
                {(envios.paginacion.totalPaginas || 1) > 1 && (
                  <div className="cli-paginacion">
                    <button className="btn btn-secondary btn-sm" disabled={paginaEnvios <= 1} onClick={() => setPaginaEnvios((n) => n - 1)}>←</button>
                    <span className="cell-secondary">{paginaEnvios} / {envios.paginacion.totalPaginas}</span>
                    <button className="btn btn-secondary btn-sm" disabled={paginaEnvios >= envios.paginacion.totalPaginas} onClick={() => setPaginaEnvios((n) => n + 1)}>→</button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {tab === 'credito' && <CreditoCliente clienteId={clienteId} onCambio={onCambio} />}

        {tab === 'actividad' && (
          <div className="drawer-body">
            {!actividad ? <p className="loading-text">Cargando actividad…</p> : actividad.length === 0 ? (
              <p className="cell-secondary">Sin movimientos registrados (cliente anterior a la bitácora).</p>
            ) : actividad.map((a) => (
              <div key={a.id} className="timeline-item">
                <div className="timeline-dot" />
                <div>
                  <div className="cell-primary">{ACCIONES[a.accion] || a.accion}</div>
                  <div className="cell-secondary">
                    {fechaCorta(a.fecha, true)} · {a.usuario || 'Sistema'}
                    {detalleActividad(a) && <> · {detalleActividad(a)}</>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {direccionEditar !== undefined && (
          <DireccionForm
            cliente={c}
            direccion={direccionEditar}
            zonas={zonas}
            onClose={() => setDireccionEditar(undefined)}
            onGuardada={() => {
              const eraNueva = direccionEditar === null
              setDireccionEditar(undefined)
              ejecutar(() => Promise.resolve(), eraNueva ? 'Dirección agregada' : 'Dirección actualizada')
            }}
          />
        )}
      </aside>
    </div>
  )
}
