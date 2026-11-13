// Agencias / almacenes de la red: panel, ficha, inventario y kardex.
import { apiFetch, apiDescargar } from './cliente'

function aParams(filtros = {}) {
  const params = new URLSearchParams()
  Object.entries(filtros).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) params.set(k, v)
  })
  return params.toString()
}

const json = (method, payload) => ({ method, body: JSON.stringify(payload ?? {}) })

// Lista simple para selectores (admision, manifiestos, usuarios)
export const listarAlmacenes = (incluirInactivos = false) =>
  apiFetch(`/almacenes${incluirInactivos ? '?incluir_inactivos=true' : ''}`)

export const panelAlmacenes = (incluirInactivos = false) =>
  apiFetch(`/almacenes/panel${incluirInactivos ? '?incluir_inactivos=true' : ''}`)

export const obtenerAlmacen = (id) => apiFetch(`/almacen/${id}`)

export const crearAlmacen = (payload) => apiFetch('/almacen', json('POST', payload))

export const editarAlmacen = (id, payload) => apiFetch(`/almacen/${id}`, json('PUT', payload))

export const desactivarAlmacen = (id, motivo) => apiFetch(`/almacen/${id}/desactivar`, json('POST', { motivo }))

export const activarAlmacen = (id) => apiFetch(`/almacen/${id}/activar`, { method: 'POST' })

export const inventarioAlmacen = (id, filtros) => apiFetch(`/almacen/${id}/inventario?${aParams(filtros)}`)

export const exportarInventario = (id, filtros) =>
  apiDescargar(`/almacen/${id}/inventario/exportar?${aParams(filtros)}`, 'inventario.csv')

export const movimientosAlmacen = (id, filtros) => apiFetch(`/almacen/${id}/movimientos?${aParams(filtros)}`)

export const actividadAlmacen = (id) => apiFetch(`/almacen/${id}/actividad`)
