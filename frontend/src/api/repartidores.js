// Perfiles de repartidor y disponibilidad.
import { apiFetch } from './cliente'

export const listarRepartidores = () => apiFetch('/repartidores')

export const crearRepartidorPerfil = (payload) =>
  apiFetch('/repartidor', { method: 'POST', body: JSON.stringify(payload) })

export const editarRepartidor = (id, payload) =>
  apiFetch(`/repartidor/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const cambiarDisponibilidadRepartidor = (id, disponible) =>
  apiFetch(`/repartidor/${id}/disponibilidad`, { method: 'POST', body: JSON.stringify({ disponible }) })
