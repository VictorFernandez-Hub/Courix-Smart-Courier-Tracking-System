// Pedidos: registro, estados, entrega, historial y evidencia.
import { apiFetch } from './cliente'

export const listarPedidos = (estado, pagina = 1, clienteId, q) => {
  const params = new URLSearchParams({ pagina, por_pagina: 20 })
  if (estado) params.set('estado', estado)
  if (clienteId) params.set('cliente_id', clienteId)
  if (q) params.set('q', q)
  return apiFetch(`/pedidos?${params.toString()}`)
}

export const crearPedido = (payload) =>
  apiFetch('/pedido', { method: 'POST', body: JSON.stringify(payload) })

export const cambiarEstadoPedido = (id, payload) =>
  apiFetch(`/pedido/${id}/estado`, { method: 'POST', body: JSON.stringify(payload) })

export const tomarPedido = (id, repartidorId) =>
  apiFetch(`/pedido/${id}/tomar`, { method: 'POST', body: JSON.stringify({ repartidorId }) })

export const entregarYCobrar = (id, payload) =>
  apiFetch(`/pedido/${id}/entregar-y-cobrar`, { method: 'POST', body: JSON.stringify(payload) })

export const ingresarAlmacen = (id, payload) =>
  apiFetch(`/pedido/${id}/ingresar-almacen`, { method: 'POST', body: JSON.stringify(payload) })

export const historialPedido = (id) => apiFetch(`/pedido/${id}/historial`)

export const evidenciaPedido = (id) => apiFetch(`/pedido/${id}/evidencia`)

export const listarPedidosDisponibles = (zonaId) =>
  apiFetch(`/pedidos/disponibles?zona_id=${zonaId}`)
