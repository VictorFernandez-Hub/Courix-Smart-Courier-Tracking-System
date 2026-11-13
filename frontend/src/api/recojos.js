// Recojo a domicilio, constancia de entrega, PIN y cumplimiento de plazos.
import { apiFetch } from './cliente'

const post = (url, body) => apiFetch(url, { method: 'POST', body: JSON.stringify(body || {}) })

export const listarRecojos = ({ estado, fecha } = {}) => {
  const params = new URLSearchParams()
  if (estado) params.set('estado', estado)
  if (fecha) params.set('fecha', fecha)
  return apiFetch(`/recojos?${params.toString()}`)
}
export const obtenerRecojo = (id) => apiFetch(`/recojo/${id}`)
export const crearRecojo = (payload) => post('/recojo', payload)
export const asignarRecojo = (id, repartidorId) => post(`/recojo/${id}/asignar`, { repartidorId })
export const reprogramarRecojo = (id, payload) => post(`/recojo/${id}/reprogramar`, payload)
export const cancelarRecojo = (id, motivo) => post(`/recojo/${id}/cancelar`, { motivo })
export const misRecojos = () => apiFetch('/mis-recojos')
export const marcarRecogido = (id, payload) => post(`/recojo/${id}/recoger`, payload)
export const marcarRecojoFallido = (id, payload) => post(`/recojo/${id}/fallido`, payload)

export const constanciaEntrega = (pedidoId) => apiFetch(`/pedido/${pedidoId}/entrega`)
export const regenerarPin = (pedidoId) => post(`/pedido/${pedidoId}/pin`)
export const reporteSla = () => apiFetch('/reportes/sla')
