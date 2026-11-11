import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { getUsuario } from '../../api'
import {
  listarUsuarios, crearUsuario, editarUsuario, desactivarUsuario, activarUsuario, restablecerPassword,
  listarZonas, crearZona, editarZona,
  listarRepartidores, crearRepartidorPerfil, editarRepartidor, cambiarDisponibilidadRepartidor,
} from '../../api'

const SECCIONES = [
  { id: 'usuarios', label: 'Usuarios' },
  { id: 'zonas', label: 'Zonas' },
  { id: 'repartidores', label: 'Repartidores' },
]

const FORM_USUARIO_VACIO = { nombre: '', email: '', password: '', rol: 'operador' }
const FORM_ZONA_VACIO = { nombre: '', referencia: '' }
const FORM_REPARTIDOR_VACIO = { usuarioId: '', zonaId: '', telefono: '', vehiculo: '', placa: '' }

export default function Configuracion() {
  const miUsuario = getUsuario()
  const [seccion, setSeccion] = useState('usuarios')

  const [usuarios, setUsuarios] = useState([])
  const [zonas, setZonas] = useState([])
  const [repartidores, setRepartidores] = useState([])

  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [modalAbierto, setModalAbierto] = useState(null) // 'usuario' | 'zona' | 'repartidor'
  const [modoEdicion, setModoEdicion] = useState(false)
  const [idEditando, setIdEditando] = useState(null)

  const [formUsuario, setFormUsuario] = useState(FORM_USUARIO_VACIO)
  const [formZona, setFormZona] = useState(FORM_ZONA_VACIO)
  const [formRepartidor, setFormRepartidor] = useState(FORM_REPARTIDOR_VACIO)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')

  const [usuarioReset, setUsuarioReset] = useState(null)
  const [passwordReset, setPasswordReset] = useState('')
  const [errorReset, setErrorReset] = useState('')

  async function manejarReset(e) {
    e.preventDefault()
    setErrorReset('')
    setEnviando(true)
    try {
      await restablecerPassword(usuarioReset.id, passwordReset)
      mostrarMensaje(`Contraseña de "${usuarioReset.nombre}" restablecida. Comunícasela por un canal seguro.`)
      setUsuarioReset(null)
    } catch (err) {
      setErrorReset(err.message)
    } finally {
      setEnviando(false)
    }
  }

  useEffect(() => {
    cargarTodo()
  }, [])

  function cargarTodo() {
    setCargando(true)
    setError('')
    Promise.all([listarUsuarios(), listarZonas(), listarRepartidores()])
      .then(([u, z, r]) => {
        setUsuarios(u.content)
        setZonas(z.content)
        setRepartidores(r.content)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }

  function mostrarMensaje(texto) {
    setMensaje(texto)
    setTimeout(() => setMensaje(''), 3500)
  }

  function nombreZona(id) {
    const z = zonas.find((z) => z.id === id)
    return z ? z.nombre : `Zona #${id}`
  }

  // ---------- Crear (modo normal) ----------

  function abrirModalCrear(tipo) {
    setErrorForm('')
    setModoEdicion(false)
    setIdEditando(null)
    if (tipo === 'usuario') setFormUsuario(FORM_USUARIO_VACIO)
    if (tipo === 'zona') setFormZona(FORM_ZONA_VACIO)
    if (tipo === 'repartidor') setFormRepartidor(FORM_REPARTIDOR_VACIO)
    setModalAbierto(tipo)
  }

  // ---------- Editar (precarga los datos existentes) ----------

  function abrirModalEditar(tipo, item) {
    setErrorForm('')
    setModoEdicion(true)
    setIdEditando(item.id)
    if (tipo === 'usuario') setFormUsuario({ nombre: item.nombre, email: item.email, password: '', rol: item.rol })
    if (tipo === 'zona') setFormZona({ nombre: item.nombre, referencia: item.referencia || '' })
    if (tipo === 'repartidor') setFormRepartidor({ usuarioId: item.usuarioId, zonaId: item.zonaId || '', telefono: item.telefono || '', vehiculo: item.vehiculo || '', placa: item.placa || '' })
    setModalAbierto(tipo)
  }

  async function guardarUsuario(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      if (modoEdicion) {
        await editarUsuario(idEditando, { nombre: formUsuario.nombre, rol: formUsuario.rol })
        mostrarMensaje('Usuario actualizado')
      } else {
        await crearUsuario(formUsuario)
        mostrarMensaje(`Usuario "${formUsuario.nombre}" creado`)
      }
      setModalAbierto(null)
      cargarTodo()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function manejarToggleActivo(u) {
    setError('')
    try {
      if (u.activo) {
        await desactivarUsuario(u.id)
        mostrarMensaje(`Usuario "${u.nombre}" desactivado`)
      } else {
        await activarUsuario(u.id)
        mostrarMensaje(`Usuario "${u.nombre}" activado`)
      }
      cargarTodo()
    } catch (err) {
      setError(err.message)
    }
  }

  async function manejarToggleDisponible(r) {
    setError('')
    try {
      await cambiarDisponibilidadRepartidor(r.id, !r.disponible)
      mostrarMensaje(`Repartidor #${r.id} ahora está ${r.disponible ? 'no disponible' : 'disponible'}`)
      cargarTodo()
    } catch (err) {
      setError(err.message)
    }
  }

  async function guardarZona(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      if (modoEdicion) {
        await editarZona(idEditando, formZona)
        mostrarMensaje('Zona actualizada')
      } else {
        await crearZona(formZona)
        mostrarMensaje(`Zona "${formZona.nombre}" creada`)
      }
      setModalAbierto(null)
      cargarTodo()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function guardarRepartidor(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      if (modoEdicion) {
        await editarRepartidor(idEditando, {
          zonaId: formRepartidor.zonaId ? Number(formRepartidor.zonaId) : undefined,
          telefono: formRepartidor.telefono,
          vehiculo: formRepartidor.vehiculo,
          placa: formRepartidor.placa,
        })
        mostrarMensaje('Repartidor actualizado')
      } else {
        await crearRepartidorPerfil({
          ...formRepartidor,
          usuarioId: Number(formRepartidor.usuarioId),
          zonaId: formRepartidor.zonaId ? Number(formRepartidor.zonaId) : undefined,
        })
        mostrarMensaje('Perfil de repartidor creado')
      }
      setModalAbierto(null)
      cargarTodo()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const usuariosRepartidorSinPerfil = usuarios.filter(
    (u) => u.rol === 'repartidor' && (modoEdicion || !repartidores.some((r) => r.usuarioId === u.id))
  )

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Configuración</h1>
          <p className="page-sub">Usuarios, zonas y repartidores del negocio</p>
        </div>
      </div>

      <div className="filters">
        {SECCIONES.map((s) => (
          <button
            key={s.id}
            className={`filter-pill${seccion === s.id ? ' active' : ''}`}
            onClick={() => setSeccion(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando…</p>
      ) : (
        <>
          {seccion === 'usuarios' && (
            <>
              <button className="btn btn-primary" style={{ marginBottom: 16 }} onClick={() => abrirModalCrear('usuario')}>
                + Nuevo usuario
              </button>
              <div className="card-grid">
                {usuarios.map((u) => (
                  <div className="mini-card" key={u.id}>
                    <div className="mini-card-name">{u.nombre}</div>
                    <div className="mini-card-line"><span>Email</span><span className="cell-mono">{u.email}</span></div>
                    <div className="mini-card-line"><span>Rol</span><span style={{ textTransform: 'capitalize' }}>{u.rol}</span></div>
                    <div className="mini-card-line"><span>Estado</span><span>{u.activo ? 'Activo' : 'Inactivo'}</span></div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                      <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => abrirModalEditar('usuario', u)}>
                        Editar
                      </button>
                      {u.id !== miUsuario?.id && (
                        <button
                          className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }}
                          onClick={() => { setPasswordReset(''); setErrorReset(''); setUsuarioReset(u) }}
                        >
                          Clave
                        </button>
                      )}
                      {u.id !== miUsuario?.id && (
                        <button
                          className={`btn ${u.activo ? 'btn-secondary' : 'btn-primary'}`}
                          style={{ flex: 1, fontSize: 12.5 }}
                          onClick={() => manejarToggleActivo(u)}
                        >
                          {u.activo ? 'Desactivar' : 'Activar'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {seccion === 'zonas' && (
            <>
              <button className="btn btn-primary" style={{ marginBottom: 16 }} onClick={() => abrirModalCrear('zona')}>
                + Nueva zona
              </button>
              <div className="card-grid">
                {zonas.map((z) => (
                  <div className="mini-card" key={z.id}>
                    <div className="mini-card-name">{z.nombre}</div>
                    <div className="mini-card-line"><span>Referencia</span><span>{z.referencia || '—'}</span></div>
                    <button className="btn btn-secondary btn-block" style={{ marginTop: 10, fontSize: 12.5 }} onClick={() => abrirModalEditar('zona', z)}>
                      Editar
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}

          {seccion === 'repartidores' && (
            <>
              <button className="btn btn-primary" style={{ marginBottom: 16 }} onClick={() => abrirModalCrear('repartidor')}>
                + Nuevo perfil de repartidor
              </button>
              {usuariosRepartidorSinPerfil.length === 0 && repartidores.length === 0 && (
                <p className="cell-secondary" style={{ marginBottom: 12 }}>
                  Primero crea un usuario con rol "repartidor" en la pestaña Usuarios.
                </p>
              )}
              <div className="card-grid">
                {repartidores.map((r) => (
                  <div className="mini-card" key={r.id}>
                    <div className="mini-card-name">Repartidor #{r.id}</div>
                    <div className="mini-card-line"><span>Zona</span><span>{nombreZona(r.zonaId)}</span></div>
                    <div className="mini-card-line"><span>Teléfono</span><span className="cell-mono">{r.telefono || '—'}</span></div>
                    <div className="mini-card-line"><span>Vehículo</span><span>{r.vehiculo || '—'}</span></div>
                    <div className="mini-card-line"><span>Disponible</span><span>{r.disponible ? 'Sí' : 'No'}</span></div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                      <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={() => abrirModalEditar('repartidor', r)}>
                        Editar
                      </button>
                      <button
                        className={`btn ${r.disponible ? 'btn-secondary' : 'btn-primary'}`}
                        style={{ flex: 1, fontSize: 12.5 }}
                        onClick={() => manejarToggleDisponible(r)}
                      >
                        {r.disponible ? 'Marcar no disponible' : 'Marcar disponible'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {modalAbierto === 'usuario' && (
        <Modal title={modoEdicion ? 'Editar usuario' : 'Nuevo usuario'} onClose={() => setModalAbierto(null)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={guardarUsuario}>
            <div className="field">
              <label htmlFor="uNombre">Nombre completo</label>
              <input id="uNombre" required value={formUsuario.nombre}
                onChange={(e) => setFormUsuario((f) => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="uEmail">Correo</label>
              <input id="uEmail" type="email" required disabled={modoEdicion} value={formUsuario.email}
                onChange={(e) => setFormUsuario((f) => ({ ...f, email: e.target.value }))} />
              {modoEdicion && <p className="cell-secondary" style={{ marginTop: 4 }}>El correo no se puede cambiar.</p>}
            </div>
            {!modoEdicion && (
              <div className="field">
                <label htmlFor="uPassword">Contraseña</label>
                <input id="uPassword" type="password" required minLength={10} maxLength={128} autoComplete="new-password"
                  value={formUsuario.password}
                  onChange={(e) => setFormUsuario((f) => ({ ...f, password: e.target.value }))} />
                <p className="cell-secondary" style={{ marginTop: 4 }}>Mínimo 10 caracteres, con letras y números.</p>
              </div>
            )}
            <div className="field">
              <label htmlFor="uRol">Rol</label>
              <select id="uRol" value={formUsuario.rol}
                onChange={(e) => setFormUsuario((f) => ({ ...f, rol: e.target.value }))}>
                <option value="admin">Admin</option>
                <option value="operador">Operador</option>
                <option value="repartidor">Repartidor</option>
              </select>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModalAbierto(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : modoEdicion ? 'Guardar cambios' : 'Crear usuario'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modalAbierto === 'zona' && (
        <Modal title={modoEdicion ? 'Editar zona' : 'Nueva zona'} onClose={() => setModalAbierto(null)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={guardarZona}>
            <div className="field">
              <label htmlFor="zNombre">Nombre</label>
              <input id="zNombre" required placeholder="Ej. Trujillo Centro" value={formZona.nombre}
                onChange={(e) => setFormZona((f) => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="zReferencia">Referencia</label>
              <input id="zReferencia" placeholder="Ej. Casco histórico" value={formZona.referencia}
                onChange={(e) => setFormZona((f) => ({ ...f, referencia: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModalAbierto(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : modoEdicion ? 'Guardar cambios' : 'Crear zona'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {modalAbierto === 'repartidor' && (
        <Modal title={modoEdicion ? 'Editar repartidor' : 'Nuevo perfil de repartidor'} onClose={() => setModalAbierto(null)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          {!modoEdicion && usuariosRepartidorSinPerfil.length === 0 ? (
            <p className="cell-secondary">
              No hay usuarios con rol "repartidor" disponibles. Crea uno primero en la pestaña Usuarios.
            </p>
          ) : (
            <form onSubmit={guardarRepartidor}>
              <div className="field">
                <label htmlFor="rUsuario">Usuario (cuenta de repartidor)</label>
                <select id="rUsuario" required disabled={modoEdicion} value={formRepartidor.usuarioId}
                  onChange={(e) => setFormRepartidor((f) => ({ ...f, usuarioId: e.target.value }))}>
                  <option value="">Selecciona un usuario</option>
                  {usuariosRepartidorSinPerfil.map((u) => (
                    <option key={u.id} value={u.id}>{u.nombre} ({u.email})</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rZona">Zona asignada</label>
                <select id="rZona" required value={formRepartidor.zonaId}
                  onChange={(e) => setFormRepartidor((f) => ({ ...f, zonaId: e.target.value }))}>
                  <option value="">Selecciona la zona (obligatoria para tomar pedidos)</option>
                  {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rTelefono">Teléfono</label>
                <input id="rTelefono" value={formRepartidor.telefono}
                  onChange={(e) => setFormRepartidor((f) => ({ ...f, telefono: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="rVehiculo">Vehículo</label>
                <input id="rVehiculo" placeholder="Ej. moto" value={formRepartidor.vehiculo}
                  onChange={(e) => setFormRepartidor((f) => ({ ...f, vehiculo: e.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="rPlaca">Placa</label>
                <input id="rPlaca" value={formRepartidor.placa}
                  onChange={(e) => setFormRepartidor((f) => ({ ...f, placa: e.target.value }))} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setModalAbierto(null)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={enviando}>
                  {enviando ? 'Guardando…' : modoEdicion ? 'Guardar cambios' : 'Crear perfil'}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}

      {usuarioReset && (
        <Modal title={`Restablecer contraseña — ${usuarioReset.nombre}`} onClose={() => setUsuarioReset(null)}>
          {errorReset && <div className="error-banner">{errorReset}</div>}
          <form onSubmit={manejarReset}>
            <p className="cell-secondary">
              Se cerrarán todas las sesiones abiertas de este usuario y se desbloqueará su cuenta si estaba bloqueada.
            </p>
            <div className="field">
              <label htmlFor="pwReset">Nueva contraseña temporal</label>
              <input id="pwReset" type="password" required minLength={10} maxLength={128} autoComplete="new-password"
                value={passwordReset} onChange={(e) => setPasswordReset(e.target.value)} />
              <p className="cell-secondary" style={{ marginTop: 4 }}>Pídele que la cambie al entrar (menú “Cambiar contraseña”).</p>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setUsuarioReset(null)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>Restablecer</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
