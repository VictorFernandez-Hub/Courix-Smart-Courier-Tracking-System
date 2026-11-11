import { Navigate } from 'react-router-dom'
import { getToken, getUsuario } from '../api'

// Sin sesion -> al login.
export function ProtectedRoute({ children }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />
  }
  return children
}

// Pedidos/clientes/rutas/pagos/incidencias/reportes son solo para admin y
// operador. Si un repartidor intenta entrar por URL directa, va a su vista.
// (El backend igual rechaza estas llamadas: esto es solo navegacion.)
export function SoloStaff({ children }) {
  const usuario = getUsuario()
  if (usuario?.rol === 'repartidor') {
    return <Navigate to="/mi-ruta" replace />
  }
  return children
}

// Configuracion (usuarios/zonas/repartidores) es solo admin.
export function SoloAdmin({ children }) {
  const usuario = getUsuario()
  if (usuario?.rol !== 'admin') {
    return <Navigate to={usuario?.rol === 'repartidor' ? '/mi-ruta' : '/pedidos'} replace />
  }
  return children
}

export function DestinoSegunRol() {
  const usuario = getUsuario()
  return <Navigate to={usuario?.rol === 'repartidor' ? '/mi-ruta' : '/pedidos'} replace />
}
