// Alta y edicion de clientes, con validacion de documento en vivo y aviso
// de duplicados antes de guardar.
import { useEffect, useState } from 'react'
import Modal from '../../components/ui/Modal'
import { crearCliente, editarCliente, verificarDuplicados } from '../../api'

const VACIO = {
  tipoCliente: 'persona', tipoDocumento: 'DNI', dni: '', nombre: '',
  telefono: '', telefonoAlternativo: '', email: '', notas: '', recibeAvisos: true,
}

const REGLAS_DOC = {
  DNI: { patron: /^\d{8}$/, ayuda: '8 dígitos', max: 8, modo: 'numeric' },
  RUC: { patron: /^(10|15|16|17|20)\d{9}$/, ayuda: '11 dígitos (10…, 20…)', max: 11, modo: 'numeric' },
  CE: { patron: /^[A-Z0-9]{8,12}$/, ayuda: '8 a 12 letras o números', max: 12, modo: 'text' },
  PASAPORTE: { patron: /^[A-Z0-9]{6,12}$/, ayuda: '6 a 12 letras o números', max: 12, modo: 'text' },
}

// Mismo calculo que el backend (modulo 11): avisa del error antes de enviar.
export function rucValido(ruc) {
  if (!REGLAS_DOC.RUC.patron.test(ruc)) return false
  const pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
  const suma = pesos.reduce((acc, p, i) => acc + p * Number(ruc[i]), 0)
  let dv = 11 - (suma % 11)
  if (dv >= 10) dv -= 10
  return dv === Number(ruc[10])
}

function problemaDocumento(tipo, numero) {
  if (!numero) return ''
  const regla = REGLAS_DOC[tipo]
  if (!regla) return ''
  if (!regla.patron.test(numero)) return `Formato: ${regla.ayuda}`
  if (tipo === 'RUC' && !rucValido(numero)) return 'El dígito verificador no coincide: revisa el RUC'
  return ''
}

export default function ClienteForm({ cliente, onClose, onGuardado }) {
  const editando = Boolean(cliente)
  const [form, setForm] = useState(() => (cliente ? {
    ...VACIO,
    ...Object.fromEntries(Object.keys(VACIO).map((k) => [k, cliente[k] ?? VACIO[k]])),
    tipoDocumento: cliente.tipoDocumento || (cliente.dni ? '' : 'DNI'),
  } : VACIO))
  const [duplicados, setDuplicados] = useState({ documento: [], telefono: [], email: [] })
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const set = (campo) => (e) => {
    const valor = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [campo]: valor }))
  }

  function cambiarTipoCliente(tipo) {
    setForm((f) => ({ ...f, tipoCliente: tipo, tipoDocumento: tipo === 'empresa' ? 'RUC' : (f.tipoDocumento === 'RUC' ? 'DNI' : f.tipoDocumento) }))
  }

  const docLimpio = form.dni.replace(/[\s.-]/g, '').toUpperCase()
  const errorDoc = problemaDocumento(form.tipoDocumento, docLimpio)

  // Verificacion de duplicados con espera (no consulta en cada tecla)
  useEffect(() => {
    const t = setTimeout(() => {
      const telefono = form.telefono.replace(/[\s()-]/g, '')
      if (!docLimpio && telefono.length < 6 && !form.email) return
      verificarDuplicados({
        dni: errorDoc ? '' : docLimpio,
        telefono: telefono.length >= 6 ? telefono : '',
        email: form.email.includes('@') ? form.email : '',
        excluir: cliente?.id,
      }).then((r) => setDuplicados(r.content)).catch(() => {})
    }, 400)
    return () => clearTimeout(t)
  }, [docLimpio, errorDoc, form.telefono, form.email, cliente?.id])

  const docDuplicado = duplicados.documento[0]

  async function guardar(e) {
    e.preventDefault()
    setError('')
    if (errorDoc) { setError(errorDoc); return }
    if (docDuplicado) { setError(`Ese documento ya pertenece a ${docDuplicado.nombre} (#${docDuplicado.id})`); return }
    setEnviando(true)
    const payload = {
      ...form,
      dni: docLimpio,
      tipoDocumento: docLimpio ? form.tipoDocumento : '',
    }
    try {
      const r = editando ? await editarCliente(cliente.id, payload) : await crearCliente(payload)
      onGuardado(r.content, editando ? 'Cliente actualizado' : 'Cliente registrado')
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const regla = REGLAS_DOC[form.tipoDocumento]
  const esEmpresa = form.tipoCliente === 'empresa'

  return (
    <Modal title={editando ? `Editar cliente — ${cliente.nombre}` : 'Nuevo cliente'} onClose={onClose}>
      {error && <div className="error-banner">{error}</div>}
      <form onSubmit={guardar} noValidate>
        <div className="field">
          <span className="field-label">Tipo de cliente</span>
          <div className="segmented" role="group" aria-label="Tipo de cliente">
            <button type="button" className={!esEmpresa ? 'active' : ''} onClick={() => cambiarTipoCliente('persona')}>Persona</button>
            <button type="button" className={esEmpresa ? 'active' : ''} onClick={() => cambiarTipoCliente('empresa')}>Empresa</button>
          </div>
        </div>

        <div className="form-2col cli-doc">
          <div className="field">
            <label htmlFor="cli-tipodoc">Documento</label>
            <select id="cli-tipodoc" value={form.tipoDocumento} disabled={esEmpresa} onChange={set('tipoDocumento')}>
              {!form.tipoDocumento && <option value="">Sin especificar</option>}
              <option value="DNI">DNI</option>
              <option value="RUC">RUC</option>
              <option value="CE">Carné de extranjería</option>
              <option value="PASAPORTE">Pasaporte</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="cli-dni">Número {esEmpresa ? '' : '(opcional)'}</label>
            <input id="cli-dni" className="cell-mono" value={form.dni} required={esEmpresa}
              inputMode={regla?.modo === 'numeric' ? 'numeric' : 'text'} maxLength={regla ? regla.max + 2 : 15}
              placeholder={regla?.ayuda} aria-invalid={Boolean(errorDoc || docDuplicado)}
              onChange={set('dni')} />
          </div>
        </div>
        {errorDoc && <p className="cli-hint error">{errorDoc}</p>}
        {docDuplicado && (
          <p className="cli-hint error">
            Ya registrado como <strong>{docDuplicado.nombre}</strong> (#{docDuplicado.id}){!docDuplicado.activo && ' — está desactivado, puedes reactivarlo'}.
          </p>
        )}

        <div className="field">
          <label htmlFor="cli-nombre">{esEmpresa ? 'Razón social' : 'Nombre completo'}</label>
          <input id="cli-nombre" required minLength={2} maxLength={100} value={form.nombre} onChange={set('nombre')} />
        </div>

        <div className="form-2col">
          <div className="field">
            <label htmlFor="cli-tel">Teléfono / celular</label>
            <input id="cli-tel" required inputMode="tel" value={form.telefono} onChange={set('telefono')} placeholder="987 654 321" />
          </div>
          <div className="field">
            <label htmlFor="cli-tel2">Teléfono alterno</label>
            <input id="cli-tel2" inputMode="tel" value={form.telefonoAlternativo} onChange={set('telefonoAlternativo')} />
          </div>
        </div>
        {duplicados.telefono.length > 0 && (
          <p className="cli-hint">
            Este teléfono también lo usa {duplicados.telefono.map((c) => `${c.nombre} (#${c.id})`).join(', ')}. ¿Es la misma persona?
          </p>
        )}

        <div className="field">
          <label htmlFor="cli-email">Correo (opcional)</label>
          <input id="cli-email" type="email" value={form.email} onChange={set('email')} />
        </div>
        {duplicados.email.length > 0 && (
          <p className="cli-hint">Este correo ya figura en {duplicados.email.map((c) => c.nombre).join(', ')}.</p>
        )}

        <div className="field">
          <label htmlFor="cli-notas">Notas internas</label>
          <textarea id="cli-notas" rows={2} maxLength={1000} value={form.notas} onChange={set('notas')}
            placeholder="Ej. Solo recibe por las tardes, pedir a portería…" />
        </div>

        <label className="check-line">
          <input type="checkbox" checked={form.recibeAvisos} onChange={set('recibeAvisos')} />
          <span>El cliente acepta recibir avisos de sus envíos por WhatsApp o correo (Ley 29733).</span>
        </label>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? 'Guardando…' : editando ? 'Guardar cambios' : 'Registrar cliente'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
