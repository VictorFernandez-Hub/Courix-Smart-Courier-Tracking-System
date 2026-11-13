import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from 'react'
import { obtenerCaptcha } from '../../api'

// Captcha de imagen generado por el backend. Cada codigo sirve UNA vez:
// despues de cada envio (acierte o no) el formulario llama a ref.recargar().
//   const captchaRef = useRef()
//   <Captcha ref={captchaRef} valor={respuesta} onCambio={setRespuesta} />
//   captchaRef.current.datos()  -> { captchaId, captchaRespuesta }
const Captcha = forwardRef(function Captcha({ valor, onCambio }, ref) {
  const [desafio, setDesafio] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const recargar = useCallback(async () => {
    setCargando(true)
    setError('')
    onCambio('')
    try {
      setDesafio(await obtenerCaptcha())
    } catch (err) {
      setDesafio(null)
      setError(err.message || 'No se pudo cargar el código de seguridad')
    } finally {
      setCargando(false)
    }
  }, [onCambio])

  useEffect(() => {
    recargar()
  }, [recargar])

  // Vence a los pocos minutos: se renueva solo para que no falle al enviar
  useEffect(() => {
    if (!desafio) return undefined
    const t = setTimeout(recargar, Math.max(30, desafio.expiraEnSegundos - 20) * 1000)
    return () => clearTimeout(t)
  }, [desafio, recargar])

  useImperativeHandle(ref, () => ({
    recargar,
    datos: () => ({ captchaId: desafio?.captchaId, captchaRespuesta: valor }),
  }), [recargar, desafio, valor])

  return (
    <div className="field">
      <label htmlFor="captcha">Código de seguridad</label>
      <div className="captcha-box">
        {desafio ? (
          <img src={desafio.imagen} alt="Código de seguridad: escribe los caracteres de la imagen" className="captcha-img" />
        ) : (
          <div className="captcha-img captcha-vacio">{cargando ? 'Cargando…' : 'Sin código'}</div>
        )}
        <button type="button" className="btn btn-secondary captcha-recargar" onClick={recargar}
          disabled={cargando} title="Generar otro código" aria-label="Generar otro código">
          ↻
        </button>
      </div>
      <input
        id="captcha"
        value={valor}
        onChange={(e) => onCambio(e.target.value.toUpperCase())}
        placeholder="Escribe los caracteres de la imagen"
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        maxLength={10}
        required
      />
      {error && <p className="cell-secondary" style={{ marginTop: 4, color: 'var(--danger, #c0392b)' }}>{error}</p>}
    </div>
  )
})

export default Captcha
