import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import Modal from '../ui/Modal'
import { getUsuario, cerrarSesion, cambiarMiPassword, guardarSesion } from '../../api'

const FORM_PASSWORD_VACIO = { actual: '', nueva: '', confirmacion: '' }

export default function Layout() {
  const navigate = useNavigate()
  const usuario = getUsuario()

  const [mostrarPassword, setMostrarPassword] = useState(false)
  const [formPassword, setFormPassword] = useState(FORM_PASSWORD_VACIO)
  const [errorPassword, setErrorPassword] = useState('')
  const [okPassword, setOkPassword] = useState('')
  const [guardando, setGuardando] = useState(false)

  function salir() {
    cerrarSesion()
    navigate('/login', { replace: true })
  }

  function abrirPassword() {
    setFormPassword(FORM_PASSWORD_VACIO)
    setErrorPassword('')
    setOkPassword('')
    setMostrarPassword(true)
  }

  async function manejarCambioPassword(e) {
    e.preventDefault()
    setErrorPassword('')
    if (formPassword.nueva !== formPassword.confirmacion) {
      setErrorPassword('La confirmación no coincide con la nueva contraseña')
      return
    }
    setGuardando(true)
    try {
      const res = await cambiarMiPassword(formPassword.actual, formPassword.nueva)
      // El backend cierra las demas sesiones y devuelve tokens nuevos para esta.
      guardarSesion(res.accessToken, res.usuario, res.refreshToken)
      setOkPassword('Contraseña actualizada. Se cerraron tus sesiones en otros dispositivos.')
      setFormPassword(FORM_PASSWORD_VACIO)
    } catch (err) {
      setErrorPassword(err.message)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          Courrier<span className="dot">Express</span>
        </div>
        <nav className="sidebar-nav">
          {usuario?.rol === 'repartidor' ? (
            <NavLink to="/mi-ruta" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
              Mi Ruta
            </NavLink>
          ) : (
            <>
              <NavLink to="/pedidos" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Pedidos
              </NavLink>
              <NavLink to="/recojos" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Recojos
              </NavLink>
              <NavLink to="/despachos" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Despachos
              </NavLink>
              <NavLink to="/clientes" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Clientes
              </NavLink>
              <NavLink to="/almacenes" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Almacenes
              </NavLink>
              <NavLink to="/rutas" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Rutas
              </NavLink>
              <NavLink to="/pagos" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Pagos y caja
              </NavLink>
              <NavLink to="/incidencias" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Incidencias
              </NavLink>
              <NavLink to="/reportes" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                Reportes
              </NavLink>
              {usuario?.rol === 'admin' && (
                <NavLink to="/configuracion" className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
                  Configuración
                </NavLink>
              )}
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <button className="btn btn-ghost btn-block" onClick={abrirPassword} style={{ marginBottom: 8 }}>
            Cambiar contraseña
          </button>
          <button className="btn btn-secondary btn-block" onClick={salir}>Cerrar sesión</button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div />
          <div className="topbar-user">
            <div className="user-chip">
              <span className="name">{usuario?.nombre}</span>
              <span className="role">{usuario?.rol}</span>
            </div>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>

      {mostrarPassword && (
        <Modal title="Cambiar contraseña" onClose={() => setMostrarPassword(false)}>
          {errorPassword && <div className="error-banner">{errorPassword}</div>}
          {okPassword && <div className="success-banner">{okPassword}</div>}
          <form onSubmit={manejarCambioPassword}>
            <div className="field">
              <label htmlFor="pwActual">Contraseña actual</label>
              <input id="pwActual" type="password" required autoComplete="current-password"
                value={formPassword.actual}
                onChange={(e) => setFormPassword((f) => ({ ...f, actual: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="pwNueva">Nueva contraseña</label>
              <input id="pwNueva" type="password" required minLength={10} maxLength={128} autoComplete="new-password"
                value={formPassword.nueva}
                onChange={(e) => setFormPassword((f) => ({ ...f, nueva: e.target.value }))} />
              <p className="cell-secondary" style={{ marginTop: 4 }}>Mínimo 10 caracteres, con letras y números.</p>
            </div>
            <div className="field">
              <label htmlFor="pwConfirmacion">Repite la nueva contraseña</label>
              <input id="pwConfirmacion" type="password" required minLength={10} autoComplete="new-password"
                value={formPassword.confirmacion}
                onChange={(e) => setFormPassword((f) => ({ ...f, confirmacion: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setMostrarPassword(false)}>Cerrar</button>
              <button type="submit" className="btn btn-primary" disabled={guardando}>
                {guardando ? 'Guardando…' : 'Actualizar contraseña'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
