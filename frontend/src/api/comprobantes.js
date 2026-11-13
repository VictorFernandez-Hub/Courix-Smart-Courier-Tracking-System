// Comprobantes electronicos (Nubefact) y avisos al cliente.
import { apiFetch } from './cliente'

const post = (url, body) => apiFetch(url, { method: 'POST', body: JSON.stringify(body || {}) })

export const comprobantesDelPedido = (pedidoId) => apiFetch(`/pedido/${pedidoId}/comprobantes`)
export const emitirComprobante = (pedidoId, payload) => post(`/pedido/${pedidoId}/comprobante`, payload)
export const reenviarComprobante = (id) => post(`/comprobante/${id}/reenviar`)
export const avisosDelPedido = (pedidoId) => apiFetch(`/pedido/${pedidoId}/avisos`)
export const preferenciaAvisos = (clienteId, recibeAvisos) => post(`/cliente/${clienteId}/avisos`, { recibeAvisos })
