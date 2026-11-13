import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { solicitarRecuperacion } from '../../api'
import Captcha from '../../components/ui/Captcha.jsx'

// Paso 1: el usuario escribe su usuario o correo y recibe un enlace por correo.
// La respuesta del backend es siempre la misma (no revela si la cuenta existe).
export default function RecuperarPassword() {
  const [identificador, setIdentificador] = useState('')
  const [captcha, setCaptcha] = useState('')
  const [error, setError] = useState('')
  const [enviado, setEnviado] = useState('')
  const [cargando, setCargando] = useState(false)
  const captchaRef = useRef(null)

  async function manejarEnvio(e) {
    e.preventDefault()
    setError('')
    setCargando(true)
    try {
      const data = await solicitarRecuperacion(identificador.trim(), captchaRef.current.datos())
      setEnviado(data.message)
    } catch (err) {
      setError(err.message)
      captchaRef.current?.recargar()
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
        <p className="login-sub">Recupera el acceso a tu cuenta.</p>

        {enviado ? (
          <>
            <div className="success-banner">{enviado}</div>
            <p className="cell-secondary" style={{ fontSize: 13 }}>
              El enlace vence en 30 minutos y solo sirve una vez. Si no te llega, pide ayuda al administrador.
            </p>
          </>
        ) : (
          <>
            {error && <div className="error-banner">{error}</div>}
            <form onSubmit={manejarEnvio}>
              <div className="field">
                <label htmlFor="identificador">Usuario o correo registrado</label>
                <input
                  id="identificador"
                  value={identificador}
                  onChange={(e) => setIdentificador(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  maxLength={120}
                  required
                />
              </div>
              <Captcha ref={captchaRef} valor={captcha} onCambio={setCaptcha} />
              <button className="btn btn-primary btn-block" type="submit" disabled={cargando}>
                {cargando ? 'Enviando…' : 'Enviar enlace de recuperación'}
              </button>
            </form>
          </>
        )}

        <div className="login-links">
          <Link to="/login">Volver al inicio de sesión</Link>
        </div>
      </div>
    </div>
  )
}
