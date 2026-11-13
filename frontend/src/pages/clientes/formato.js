// Formatos compartidos por las pantallas de clientes.

export const ETIQUETA_DOC = { DNI: 'DNI', RUC: 'RUC', CE: 'Carné ext.', PASAPORTE: 'Pasaporte' }

export function fechaCorta(iso, conHora = false) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('es-PE', conHora
    ? { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: 'short', year: 'numeric' })
}

export function haceCuanto(iso) {
  if (!iso) return ''
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (dias <= 0) return 'hoy'
  if (dias === 1) return 'ayer'
  if (dias < 30) return `hace ${dias} días`
  const meses = Math.floor(dias / 30)
  if (meses < 12) return `hace ${meses} ${meses === 1 ? 'mes' : 'meses'}`
  const anios = Math.floor(meses / 12)
  return `hace ${anios} ${anios === 1 ? 'año' : 'años'}`
}

export const soles = (monto) =>
  `S/ ${Number(monto || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// Celulares peruanos de 9 digitos sin prefijo: se agrega el 51.
export function enlaceWhatsApp(telefono) {
  let numero = String(telefono || '').replace(/[^\d]/g, '')
  if (numero.length === 9 && numero.startsWith('9')) numero = `51${numero}`
  return `https://wa.me/${numero}`
}

export function iniciales(nombre) {
  return String(nombre || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
}
