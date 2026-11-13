// Inicio de sesion, captcha, recuperacion de contrasena y cuenta del usuario actual.
import { apiFetch } from './cliente'

export const obtenerCaptcha = () => apiFetch('/captcha').then((r) => r.content)

// captcha = { captchaId, captchaRespuesta }
export const login = (usuario, password, captcha) =>
  apiFetch('/login', { method: 'POST', body: JSON.stringify({ usuario, password, ...captcha }) })

export const solicitarRecuperacion = (identificador, captcha) =>
  apiFetch('/password/olvide', { method: 'POST', body: JSON.stringify({ identificador, ...captcha }) })

export const restablecerConToken = (token, passwordNueva) =>
  apiFetch('/password/restablecer', { method: 'POST', body: JSON.stringify({ token, passwordNueva }) })

export const cambiarMiPassword = (passwordActual, passwordNueva) =>
  apiFetch('/usuario/me/password', { method: 'POST', body: JSON.stringify({ passwordActual, passwordNueva }) })
