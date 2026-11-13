// Incidencias y reclamos.
import { apiFetch } from './cliente'

export const crearIncidencia = (pedidoId, payload) =>
  apiFetch(`/pedido/${pedidoId}/incidencia`, { method: 'POST', body: JSON.stringify(payload) })

export const listarIncidencias = (estado, { mias, vencidas } = {}) => {
  const params = new URLSearchParams()
  if (estado) params.set('estado', estado)
  if (mias) params.set('mias', '1')
  if (vencidas) params.set('vencidas', '1')
  return apiFetch(`/incidencias?${params.toString()}`)
}

export const listarIncidenciasDePedido = (pedidoId) => apiFetch(`/pedido/${pedidoId}/incidencias`)

export const marcarIncidenciaEnProceso = (id) =>
  apiFetch(`/incidencia/${id}/en-proceso`, { method: 'POST' })

export const resolverIncidencia = (id, resolucion) =>
  apiFetch(`/incidencia/${id}/resolver`, { method: 'POST', body: JSON.stringify({ resolucion }) })

export const asignarIncidencia = (id, payload) =>
  apiFetch(`/incidencia/${id}/asignar`, { method: 'POST', body: JSON.stringify(payload) })
