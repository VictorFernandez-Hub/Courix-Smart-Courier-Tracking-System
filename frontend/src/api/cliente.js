// Cliente HTTP comun: URL del backend, sesion (tokens) y renovacion automatica.
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000'

// Se usa sessionStorage (no localStorage) a proposito: la sesion se cierra
// sola cuando se cierra el navegador o la pestana, sin necesidad de que
// el usuario le de clic manualmente a "Cerrar sesion".
export function getToken() {
  return sessionStorage.getItem('token')
}

export function getUsuario() {
  const raw = sessionStorage.getItem('usuario')
  return raw ? JSON.parse(raw) : null
}

export function guardarSesion(accessToken, usuario, refreshToken) {
  sessionStorage.setItem('token', accessToken)
  if (refreshToken) sessionStorage.setItem('refreshToken', refreshToken)
  if (usuario) sessionStorage.setItem('usuario', JSON.stringify(usuario))
}

export function cerrarSesion() {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('refreshToken')
  sessionStorage.removeItem('usuario')
}

// El access token dura poco (30 min). Cuando vence, se pide uno nuevo con el
// refresh token una sola vez (aunque varias peticiones fallen a la vez) y se
// reintenta la peticion original, sin que el usuario note nada.
let renovacionEnCurso = null

async function renovarToken() {
  const refreshToken = sessionStorage.getItem('refreshToken')
  if (!refreshToken) return false
  if (!renovacionEnCurso) {
    renovacionEnCurso = fetch(`${API_URL}/token/refresh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${refreshToken}` },
    })
      .then(async (res) => {
        if (!res.ok) return false
        const data = await res.json()
        sessionStorage.setItem('token', data.accessToken)
        return true
      })
      .catch(() => false)
      .finally(() => { renovacionEnCurso = null })
  }
  return renovacionEnCurso
}

export async function apiFetch(path, options = {}, reintento = true) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })
  const data = await res.json().catch(() => ({}))

  if (res.status === 401 && token && reintento && data.codigo === 'token_expirado') {
    if (await renovarToken()) return apiFetch(path, options, false)
  }

  if (!res.ok) {
    // 401 con un token ya guardado = la sesion expiro o el token quedo
    // invalido (por ejemplo, el usuario fue desactivado). En vez de dejar
    // que cada pantalla muestre un error crudo y se quede "colgada", se
    // cierra la sesion y se manda al login con un aviso claro.
    if (res.status === 401 && token) {
      cerrarSesion()
      sessionStorage.setItem('avisoLogin', data.message || 'Tu sesion expiro, vuelve a iniciar sesion')
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    const error = new Error(data.message || 'Ocurrio un error inesperado')
    error.status = res.status
    error.data = data
    throw error
  }
  return data
}
