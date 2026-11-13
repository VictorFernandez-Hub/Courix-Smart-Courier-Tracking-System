import { useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'
import Modal from './Modal'

// Lee el QR de la etiqueta con la camara trasera del celular.
// - Usa BarcodeDetector (nativo, rapido) si el navegador lo trae (Chrome Android).
// - Si no, decodifica los cuadros del video con jsQR (funciona en cualquiera).
// La camara solo se puede usar en HTTPS o en localhost (regla del navegador).
// continuo = true: sigue leyendo (cargar un camion caja por caja); si no, se cierra al leer.
export default function EscanerQR({ onLeer, onCerrar, titulo = 'Escanear QR', continuo = false, children }) {
  const videoRef = useRef(null)
  const lienzoRef = useRef(null)
  const [error, setError] = useState('')
  const [modo, setModo] = useState('')

  useEffect(() => {
    let stream = null
    let activo = true
    let marco = null
    let detector = null
    let pausadoHasta = 0
    let ultimo = null
    let ultimoEn = 0

    async function iniciar() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Este navegador no permite usar la cámara. Usa el lector o escribe el código.')
        return
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }, audio: false,
        })
      } catch (e) {
        setError(e.name === 'NotAllowedError'
          ? 'Permiso de cámara denegado. Actívalo en la configuración del navegador.'
          : 'No se pudo abrir la cámara (¿la app se abrió con https?).')
        return
      }
      if (!activo) return
      const video = videoRef.current
      video.srcObject = stream
      await video.play().catch(() => {})

      if ('BarcodeDetector' in window) {
        try {
          const formatos = await window.BarcodeDetector.getSupportedFormats()
          if (formatos.includes('qr_code')) detector = new window.BarcodeDetector({ formats: ['qr_code'] })
        } catch { detector = null }
      }
      setModo(detector ? 'nativo' : 'jsqr')
      buscar()
    }

    async function buscar() {
      if (!activo) return
      const video = videoRef.current
      if (video && video.readyState >= 2) {
        let texto = null
        if (detector) {
          const codigos = await detector.detect(video).catch(() => [])
          texto = codigos[0]?.rawValue || null
        } else {
          const lienzo = lienzoRef.current
          const ancho = Math.min(640, video.videoWidth)
          const alto = Math.round((video.videoHeight / video.videoWidth) * ancho) || 480
          lienzo.width = ancho
          lienzo.height = alto
          const ctx = lienzo.getContext('2d', { willReadFrequently: true })
          ctx.drawImage(video, 0, 0, ancho, alto)
          texto = jsQR(ctx.getImageData(0, 0, ancho, alto).data, ancho, alto, { inversionAttempts: 'dontInvert' })?.data || null
        }
        const ahora = Date.now()
        if (texto && activo && ahora >= pausadoHasta) {
          const valor = texto.trim().toUpperCase()
          // En modo continuo se ignora el mismo QR durante unos segundos:
          // la camara lo sigue viendo mientras el operador mueve la caja.
          if (!(continuo && valor === ultimo && ahora - ultimoEn < 4000)) {
            if (navigator.vibrate) navigator.vibrate(80)
            ultimo = valor
            ultimoEn = ahora
            if (!continuo) {
              activo = false
              onLeer(valor)
              return
            }
            pausadoHasta = ahora + 1200
            onLeer(valor)
          }
        }
      }
      marco = requestAnimationFrame(buscar)
    }

    iniciar()
    return () => {
      activo = false
      if (marco) cancelAnimationFrame(marco)
      stream?.getTracks().forEach((t) => t.stop())  // apaga la camara al cerrar
    }
  }, [onLeer, continuo])

  return (
    <Modal title={titulo} onClose={onCerrar}>
      {error ? (
        <div className="error-banner">{error}</div>
      ) : (
        <div className="escaner">
          <video ref={videoRef} playsInline muted aria-label="Vista de la cámara" />
          <div className="escaner-marco" aria-hidden="true" />
          <canvas ref={lienzoRef} hidden />
        </div>
      )}
      {children}
      <p className="cell-secondary" style={{ marginTop: 8 }}>
        Apunta al QR de la etiqueta. {modo === 'nativo' ? 'Lector nativo del navegador.' : modo === 'jsqr' ? 'Lector compatible.' : 'Abriendo cámara…'}
      </p>
      <div className="modal-actions">
        <button type="button" className="btn btn-secondary" onClick={onCerrar}>Cerrar</button>
      </div>
    </Modal>
  )
}
