import { useEffect, useRef, useState } from 'react'

// Firma con el dedo (o mouse) sobre un canvas. Entrega la firma como PNG en
// base64 via onChange, o null si se borra. Usa pointer events: funciona igual
// con touch, lapiz y mouse.
export default function FirmaPad({ onChange, alto = 160 }) {
  const canvasRef = useRef(null)
  const dibujando = useRef(false)
  const [vacia, setVacia] = useState(true)

  // Ajusta la resolucion del canvas a la pantalla (nitido en celulares)
  useEffect(() => {
    const canvas = canvasRef.current
    const escala = window.devicePixelRatio || 1
    const ancho = canvas.parentElement.clientWidth
    canvas.width = ancho * escala
    canvas.height = alto * escala
    canvas.style.width = `${ancho}px`
    canvas.style.height = `${alto}px`
    const ctx = canvas.getContext('2d')
    ctx.scale(escala, escala)
    ctx.lineWidth = 2.2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#111'
  }, [alto])

  function punto(e) {
    const r = canvasRef.current.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  function iniciar(e) {
    e.preventDefault()
    canvasRef.current.setPointerCapture(e.pointerId)
    dibujando.current = true
    const { x, y } = punto(e)
    const ctx = canvasRef.current.getContext('2d')
    ctx.beginPath()
    ctx.moveTo(x, y)
  }

  function mover(e) {
    if (!dibujando.current) return
    const { x, y } = punto(e)
    const ctx = canvasRef.current.getContext('2d')
    ctx.lineTo(x, y)
    ctx.stroke()
    if (vacia) setVacia(false)
  }

  function terminar() {
    if (!dibujando.current) return
    dibujando.current = false
    if (!vacia) onChange(canvasRef.current.toDataURL('image/png'))
  }

  function borrar() {
    const canvas = canvasRef.current
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
    setVacia(true)
    onChange(null)
  }

  return (
    <div className="firma-pad">
      <canvas
        ref={canvasRef}
        onPointerDown={iniciar}
        onPointerMove={mover}
        onPointerUp={terminar}
        onPointerLeave={terminar}
        role="img"
        aria-label="Área de firma: firma con el dedo"
      />
      {vacia && <span className="firma-guia">Firme aquí</span>}
      <button type="button" className="btn-xs" onClick={borrar} disabled={vacia}>Borrar firma</button>
    </div>
  )
}
