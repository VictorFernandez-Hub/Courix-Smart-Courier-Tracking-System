// Clientes y sus direcciones.
import { apiFetch } from './cliente'

export const listarClientes = (q) => {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  return apiFetch(`/clientes?${params.toString()}`)
}

export const crearCliente = (payload) =>
  apiFetch('/cliente', { method: 'POST', body: JSON.stringify(payload) })

export const desactivarCliente = (id) => apiFetch(`/cliente/${id}/desactivar`, { method: 'POST' })

export const activarCliente = (id) => apiFetch(`/cliente/${id}/activar`, { method: 'POST' })

export const listarDireccionesCliente = (clienteId) =>
  apiFetch(`/cliente/${clienteId}/direcciones`)

export const crearDireccionCliente = (payload) =>
  apiFetch('/direccion-cliente', { method: 'POST', body: JSON.stringify(payload) })
