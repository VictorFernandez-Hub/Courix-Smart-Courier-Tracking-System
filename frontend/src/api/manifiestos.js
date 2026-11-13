// Red de agencias: clasificacion, manifiestos de despacho y recepcion por escaneo.
import { apiFetch } from './cliente'

const post = (url, body) => apiFetch(url, { method: 'POST', body: JSON.stringify(body || {}) })

export const pendientesDeDespacho = (agenciaId) =>
  apiFetch(`/despachos/pendientes${agenciaId ? `?agencia_id=${agenciaId}` : ''}`)

export const listarManifiestos = ({ tipo, estado } = {}) => {
  const params = new URLSearchParams()
  if (tipo) params.set('tipo', tipo)
  if (estado) params.set('estado', estado)
  return apiFetch(`/manifiestos?${params.toString()}`)
}

export const obtenerManifiesto = (id) => apiFetch(`/manifiesto/${id}`)

export const crearManifiesto = (payload) => post('/manifiesto', payload)

export const escanearEnManifiesto = (id, codigo) => post(`/manifiesto/${id}/bultos`, { codigo })

export const quitarDeManifiesto = (id, bultoId) =>
  apiFetch(`/manifiesto/${id}/bultos/${bultoId}`, { method: 'DELETE' })

export const despacharManifiesto = (id, payload) => post(`/manifiesto/${id}/despachar`, payload)

export const recibirEnManifiesto = (id, codigo) => post(`/manifiesto/${id}/recibir`, { codigo })

export const cerrarRecepcion = (id, observaciones) =>
  post(`/manifiesto/${id}/cerrar-recepcion`, observaciones ? { observaciones } : {})

export const trazabilidadPedido = (id) => apiFetch(`/pedido/${id}/trazabilidad`)
