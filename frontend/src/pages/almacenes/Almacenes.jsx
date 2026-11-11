import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { getUsuario, listarAlmacenes, crearAlmacen, editarAlmacen, listarZonas } from '../../api'

const FORM_VACIO = { nombre: '', calle: '', zonaId: '', telefono: '' }

export default function Almacenes() {
  const usuario = getUsuario()
  const esAdmin = usuario?.rol === 'admin'

  const [almacenes, setAlmacenes] = useState([])
  const [zonas, setZonas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [mensaje, setMensaje] = useState('')

  const [modalAbierto, setModalAbierto] = useState(false)
  const [modoEdicion, setModoEdicion] = useState(false)
  const [idEditando, setIdEditando] = useState(null)
  const [form, setForm] = useState(FORM_VACIO)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')

  useEffect(() => {
    cargarTodo()
  }, [])

  function cargarTodo() {
    setCargando(true)
    setError('')
    Promise.all([listarAlmacenes(), listarZonas()])
      .then(([a, z]) => {
        setAlmacenes(a.content)
        setZonas(z.content)
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
    return z ? z.nombre : (id ? `Zona #${id}` : 'Sin zona')
  }

  function abrirModalCrear() {
    setErrorForm('')
    setModoEdicion(false)
    setIdEditando(null)
    setForm(FORM_VACIO)
    setModalAbierto(true)
  }

  function abrirModalEditar(a) {
    setErrorForm('')
    setModoEdicion(true)
    setIdEditando(a.id)
    setForm({ nombre: a.nombre, calle: a.calle, zonaId: a.zonaId || '', telefono: a.telefono || '' })
    setModalAbierto(true)
  }

  async function guardar(e) {
    e.preventDefault()
    setErrorForm('')
    setEnviando(true)
    try {
      const payload = { ...form, zonaId: form.zonaId ? Number(form.zonaId) : undefined }
      if (modoEdicion) {
        await editarAlmacen(idEditando, payload)
        mostrarMensaje('Almacén actualizado')
      } else {
        await crearAlmacen(payload)
        mostrarMensaje(`Almacén "${form.nombre}" creado`)
      }
      setModalAbierto(false)
      cargarTodo()
    } catch (err) {
      setErrorForm(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Almacenes</h1>
          <p className="page-sub">
            {almacenes.length} almacén{almacenes.length !== 1 ? 'es' : ''} registrado{almacenes.length !== 1 ? 's' : ''}
            {!esAdmin && ' · Solo un administrador puede crear o editar almacenes'}
          </p>
        </div>
        {esAdmin && (
          <button className="btn btn-primary" onClick={abrirModalCrear}>+ Nuevo almacén</button>
        )}
      </div>

      {mensaje && <div className="success-banner">{mensaje}</div>}
      {error && <div className="error-banner">{error}</div>}

      {cargando ? (
        <p className="loading-text">Cargando almacenes…</p>
      ) : almacenes.length === 0 ? (
        <div className="manifest">
          <div className="empty-state">
            <h3>Todavía no hay almacenes creados</h3>
            <p>
              {esAdmin
                ? 'Crea el primero con "+ Nuevo almacén" — sin al menos uno no se pueden registrar pedidos.'
                : 'Pide a un administrador que cree al menos un almacén — sin uno no se pueden registrar pedidos.'}
            </p>
          </div>
        </div>
      ) : (
        <div className="card-grid">
          {almacenes.map((a) => (
            <div className="mini-card" key={a.id}>
              <div className="mini-card-name">{a.nombre}</div>
              <div className="mini-card-line"><span>Dirección</span><span>{a.calle}</span></div>
              <div className="mini-card-line"><span>Zona</span><span>{nombreZona(a.zonaId)}</span></div>
              <div className="mini-card-line"><span>Teléfono</span><span className="cell-mono">{a.telefono || '—'}</span></div>
              {esAdmin && (
                <button className="btn btn-secondary btn-block" style={{ marginTop: 10, fontSize: 12.5 }} onClick={() => abrirModalEditar(a)}>
                  Editar
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {modalAbierto && (
        <Modal title={modoEdicion ? 'Editar almacén' : 'Nuevo almacén'} onClose={() => setModalAbierto(false)}>
          {errorForm && <div className="error-banner">{errorForm}</div>}
          <form onSubmit={guardar}>
            <div className="field">
              <label htmlFor="aNombre">Nombre</label>
              <input id="aNombre" required placeholder="Ej. Almacén Central" value={form.nombre}
                onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="aCalle">Dirección</label>
              <input id="aCalle" required value={form.calle}
                onChange={(e) => setForm((f) => ({ ...f, calle: e.target.value }))} />
            </div>
            <div className="field">
              <label htmlFor="aZona">Zona</label>
              <select id="aZona" required value={form.zonaId}
                onChange={(e) => setForm((f) => ({ ...f, zonaId: e.target.value }))}>
                <option value="">Selecciona una zona</option>
                {zonas.map((z) => <option key={z.id} value={z.id}>{z.nombre}</option>)}
              </select>
              {zonas.length === 0 && (
                <p className="cell-secondary" style={{ marginTop: 4 }}>
                  Todavía no hay zonas creadas — créalas primero en Configuración.
                </p>
              )}
            </div>
            <div className="field">
              <label htmlFor="aTelefono">Teléfono</label>
              <input id="aTelefono" value={form.telefono}
                onChange={(e) => setForm((f) => ({ ...f, telefono: e.target.value }))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setModalAbierto(false)}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={enviando}>
                {enviando ? 'Guardando…' : modoEdicion ? 'Guardar cambios' : 'Crear almacén'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
