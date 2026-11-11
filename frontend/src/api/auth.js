// Inicio de sesion y cuenta del usuario actual.
import { apiFetch } from './cliente'

export const login = (email, password) =>
  apiFetch('/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const cambiarMiPassword = (passwordActual, passwordNueva) =>
  apiFetch('/usuario/me/password', { method: 'POST', body: JSON.stringify({ passwordActual, passwordNueva }) })
