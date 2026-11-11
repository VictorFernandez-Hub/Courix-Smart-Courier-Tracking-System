import { useState } from 'react'
import { Link } from 'react-router-dom'
import { rastrearPorCodigoGuia } from '../../api'

const ETIQUETAS = {
  pendiente: 'Pendiente',
  en_almacen: 'En almacén',
  asignado: 'Asignado a un repartidor',
  recogido: 'Recogido',
  en_camino: 'En camino',
  entregado: 'Entregado',
  no_entregado: 'Intento de entrega fallido',
  devuelto: 'Devuelto',
  cancelado: 'Cancelado',
}

export default function RastreoPublico() {
  const [codigo, setCodigo] = useState('')
  const [resultado, setResultado] = useState(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState('')

  async function manejarEnvio(e) {
    e.preventDefault()
    if (!codigo.trim()) return
    setError('')
    setResultado(null)
    setCargando(true)
    try {
      const data = await rastrearPorCodigoGuia(codigo.trim().toUpperCase())
      setResultado(data)
    } catch (err) {
      setError(err.status === 404
        ? 'No encontramos ningún envío con ese código de guía. Revisa que esté bien escrito.'
        : err.message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card" style={{ maxWidth: 480 }}>
        <div className="login-brand">
          Courrier<span className="dot">Express</span>
        </div>
        <p className="login-sub">Rastrea tu envío con el código de guía (ej. CE-7K3M-9QX2).</p>

        <form onSubmit={manejarEnvio} style={{ display: 'flex', gap: 8 }}>
          <input
            aria-label="Código de guía"
            placeholder="CE-7K3M-9QX2"
            maxLength={30}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" type="submit" disabled={cargando}>
            {cargando ? 'Buscando…' : 'Rastrear'}
          </button>
        </form>

        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}

        {resultado && (
          <div style={{ marginTop: 20 }}>
            <div className="ruta-header" style={{ marginBottom: 12 }}>
              <div>
                <div className="ruta-codigo">{resultado.codigoGuia}</div>
                <div className="ruta-estado-label">
                  Estado actual: {ETIQUETAS[resultado.estadoActual] || resultado.estadoActual}
                </div>
              </div>
            </div>

            {resultado.historial.length === 0 ? (
              <p className="cell-secondary">Todavía no hay eventos registrados para este envío.</p>
            ) : (
              <div>
                {resultado.historial.map((ev, i) => (
                  <div className="timeline-item" key={i}>
                    <div className="timeline-dot" />
                    <div>
                      <div className="cell-secondary">{new Date(ev.fecha).toLocaleString('es-PE')}</div>
                      <div style={{ marginTop: 2 }}>{ev.mensaje || ETIQUETAS[ev.estado] || ev.estado}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <p style={{ marginTop: 20, textAlign: 'center' }}>
          <Link to="/login" className="cell-secondary">¿Eres parte del equipo? Inicia sesión aquí</Link>
        </p>
      </div>
    </div>
  )
}
