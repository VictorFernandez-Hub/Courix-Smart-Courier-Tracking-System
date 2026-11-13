import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { restablecerConToken } from '../../api'

// Paso 2: pantalla a la que lleva el enlace del correo (/restablecer?token=...).
export default function RestablecerPassword() {
  // El token se lee una vez y se quita de la barra de direcciones: asi no
  // queda en el historial ni se comparte por error al copiar la URL.
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '')
  useEffect(() => {
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  const [nueva, setNueva] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const navigate = useNavigate()

  async function manejarEnvio(e) {
    e.preventDefault()
    setError('')
    if (nueva !== confirmacion) {
      setError('Las contraseñas no coinciden')
      return
    }
    setCargando(true)
    try {
      const data = await restablecerConToken(token, nueva)
      navigate('/login', { replace: true, state: { mensaje: data.message } })
    } catch (err) {
      setError(err.message)
      setCargando(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          Courrier<span className="dot">Express</span>
        </div>
        <p className="login-sub">Crea una nueva contraseña.</p>

        {!token ? (
          <div className="error-banner">
            El enlace está incompleto. Ábrelo directamente desde el correo o solicita uno nuevo.
          </div>
        ) : (
          <>
            {error && <div className="error-banner">{error}</div>}
            <form onSubmit={manejarEnvio}>
              <div className="field">
                <label htmlFor="nueva">Nueva contraseña</label>
                <input id="nueva" type="password" value={nueva} onChange={(e) => setNueva(e.target.value)}
                  autoComplete="new-password" minLength={10} maxLength={128} required />
                <p className="cell-secondary" style={{ marginTop: 4 }}>Mínimo 10 caracteres, con letras y números.</p>
              </div>
              <div className="field">
                <label htmlFor="confirmacion">Repite la nueva contraseña</label>
                <input id="confirmacion" type="password" value={confirmacion}
                  onChange={(e) => setConfirmacion(e.target.value)} autoComplete="new-password" required />
              </div>
              <button className="btn btn-primary btn-block" type="submit" disabled={cargando}>
                {cargando ? 'Guardando…' : 'Guardar contraseña'}
              </button>
            </form>
          </>
        )}

        <div className="login-links">
          <Link to="/recuperar">Solicitar un enlace nuevo</Link>
          <Link to="/login">Volver al inicio de sesión</Link>
        </div>
      </div>
    </div>
  )
}
