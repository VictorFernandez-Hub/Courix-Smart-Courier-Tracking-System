// Incidencias y reclamos.
import { apiFetch } from './cliente'

export const crearIncidencia = (pedidoId, payload) =>
  apiFetch(`/pedido/${pedidoId}/incidencia`, { method: 'POST', body: JSON.stringify(payload) })

export const listarIncidencias = (estado) => {
  const params = new URLSearchParams()
  if (estado) params.set('estado', estado)
  return apiFetch(`/incidencias?${params.toString()}`)
}

export const listarIncidenciasDePedido = (pedidoId) => apiFetch(`/pedido/${pedidoId}/incidencias`)

export const marcarIncidenciaEnProceso = (id) =>
  apiFetch(`/incidencia/${id}/en-proceso`, { method: 'POST' })

export const resolverIncidencia = (id, resolucion) =>
  apiFetch(`/incidencia/${id}/resolver`, { method: 'POST', body: JSON.stringify({ resolucion }) })
