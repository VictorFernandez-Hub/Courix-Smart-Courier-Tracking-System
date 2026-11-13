// Utilidades de imagen compartidas (foto de entrega, foto de inspeccion).

// Una foto de celular sin comprimir puede pesar varios MB; eso vuelve
// lenta la subida en una conexion movil y engorda innecesariamente el
// registro en la base de datos. Se redimensiona a un maximo de 1280px de
// lado y se reexporta en JPEG calidad 0.7, que para "evidencia de que se
// entrego el paquete" es mas que suficiente.
export function comprimirImagen(archivo, maxLado = 1280, calidad = 0.7) {
  return new Promise((resolve, reject) => {
    const lector = new FileReader()
    lector.onerror = () => reject(new Error('No se pudo leer la imagen'))
    lector.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('No se pudo procesar la imagen'))
      img.onload = () => {
        let { width, height } = img
        if (width > height && width > maxLado) {
          height = Math.round((height * maxLado) / width)
          width = maxLado
        } else if (height > maxLado) {
          width = Math.round((width * maxLado) / height)
          height = maxLado
        }
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        canvas.getContext('2d').drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', calidad))
      }
      img.src = lector.result
    }
    lector.readAsDataURL(archivo)
  })
}
