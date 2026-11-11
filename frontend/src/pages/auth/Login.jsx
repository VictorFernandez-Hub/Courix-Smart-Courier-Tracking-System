import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login, guardarSesion } from '../../api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const navigate = useNavigate()

  // Si api.js cerro la sesion sola porque el token expiro/es invalido, deja
  // este aviso guardado para que el usuario entienda por que volvio aqui
  // (en vez de ver solo un formulario de login sin ninguna explicacion).
  // Se lee en el inicializador y se borra en un efecto: si se borrara en el
  // inicializador, React StrictMode (que lo ejecuta dos veces) perdia el aviso.
  const [aviso] = useState(() => sessionStorage.getItem('avisoLogin'))
  useEffect(() => {
    sessionStorage.removeItem('avisoLogin')
  }, [])

  async function manejarEnvio(e) {
    e.preventDefault()
    setError('')
    setCargando(true)
    try {
      const data = await login(email, password)
      guardarSesion(data.accessToken, data.usuario, data.refreshToken)
      navigate(data.usuario.rol === 'repartidor' ? '/mi-ruta' : '/pedidos', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          Courrier<span className="dot">Express</span>
        </div>
        <p className="login-sub">Ingresa con tu cuenta para gestionar los pedidos.</p>

        {error && <div className="error-banner">{error}</div>}
        {!error && aviso && <div className="error-banner">{aviso}</div>}

        <form onSubmit={manejarEnvio}>
          <div className="field">
            <label htmlFor="email">Correo</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Contraseña</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button className="btn btn-primary btn-block" type="submit" disabled={cargando}>
            {cargando ? 'Ingresando…' : 'Ingresar'}
          </button>
        </form>

        <p style={{ marginTop: 16, textAlign: 'center' }}>
          <Link to="/rastreo" className="cell-secondary">¿Eres cliente? Rastrea tu envío sin iniciar sesión</Link>
        </p>
      </div>
    </div>
  )
}
