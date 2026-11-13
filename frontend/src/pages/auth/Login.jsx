import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { login, guardarSesion } from '../../api'
import Captcha from '../../components/ui/Captcha.jsx'

export default function Login() {
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [captcha, setCaptcha] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const captchaRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()
  // Mensaje de exito que deja la pantalla de restablecer contrasena
  const exito = location.state?.mensaje

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
      const data = await login(usuario.trim(), password, captchaRef.current.datos())
      guardarSesion(data.accessToken, data.usuario, data.refreshToken)
      navigate(data.usuario.rol === 'repartidor' ? '/mi-ruta' : '/pedidos', { replace: true })
    } catch (err) {
      setError(err.message)
      // El codigo se consume en cada intento: siempre se pide uno nuevo
      captchaRef.current?.recargar()
      setCargando(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          Courrier<span className="dot">Express</span>
        </div>
        <p className="login-sub">Ingresa con tu usuario para gestionar los pedidos.</p>

        {exito && !error && <div className="success-banner">{exito}</div>}
        {error && <div className="error-banner">{error}</div>}
        {!error && !exito && aviso && <div className="error-banner">{aviso}</div>}

        <form onSubmit={manejarEnvio}>
          <div className="field">
            <label htmlFor="usuario">Usuario</label>
            <input
              id="usuario"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={30}
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
          <Captcha ref={captchaRef} valor={captcha} onCambio={setCaptcha} />
          <button className="btn btn-primary btn-block" type="submit" disabled={cargando}>
            {cargando ? 'Ingresando…' : 'Ingresar'}
          </button>
        </form>

        <div className="login-links">
          <Link to="/recuperar">¿Olvidaste tu contraseña?</Link>
          <Link to="/rastreo" className="cell-secondary">¿Eres cliente? Rastrea tu envío sin iniciar sesión</Link>
        </div>
      </div>
    </div>
  )
}
