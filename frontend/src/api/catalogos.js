// Catalogos del negocio: estados, zonas y tarifas (agencias en almacenes.js).
import { apiFetch } from './cliente'

export const listarEstados = () => apiFetch('/estados')

export const listarZonas = (incluirInactivas = false) =>
  apiFetch(`/zonas${incluirInactivas ? '?incluir_inactivas=true' : ''}`)

export const crearZona = (payload) =>
  apiFetch('/zona', { method: 'POST', body: JSON.stringify(payload) })

export const editarZona = (id, payload) =>
  apiFetch(`/zona/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const desactivarZona = (id) => apiFetch(`/zona/${id}/desactivar`, { method: 'POST' })

export const activarZona = (id) => apiFetch(`/zona/${id}/activar`, { method: 'POST' })

export const listarTarifas = () => apiFetch('/tarifas')

export const crearTarifa = (payload) =>
  apiFetch('/tarifa', { method: 'POST', body: JSON.stringify(payload) })

export const editarTarifa = (id, payload) =>
  apiFetch(`/tarifa/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const eliminarTarifa = (id) => apiFetch(`/tarifa/${id}`, { method: 'DELETE' })
