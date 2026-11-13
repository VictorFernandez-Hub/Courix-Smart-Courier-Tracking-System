// Pedidos: registro, estados, entrega, historial y evidencia.
import { apiFetch } from './cliente'

export const listarPedidos = (estado, pagina = 1, clienteId, q, atrasados) => {
  const params = new URLSearchParams({ pagina, por_pagina: 20 })
  if (atrasados) params.set('atrasados', '1')
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

// ---- Admision (Fase 1) ----
export const cotizarEnvio = (payload) =>
  apiFetch('/cotizar', { method: 'POST', body: JSON.stringify(payload) })

export const obtenerPedido = (id) => apiFetch(`/pedido/${id}`)

export const etiquetaPedido = (id) => apiFetch(`/pedido/${id}/etiqueta`)

// ---- Excepciones: devolucion, redireccion, cargos y reembolsos ----
export const saldoDevolucion = (id) => apiFetch(`/pedido/${id}/saldo-devolucion`)

export const redireccionarPedido = (id, payload) =>
  apiFetch(`/pedido/${id}/redireccionar`, { method: 'POST', body: JSON.stringify(payload) })

export const cargosDelPedido = (id) => apiFetch(`/pedido/${id}/cargos`)

export const cobrarCargo = (id, payload) =>
  apiFetch(`/cargo/${id}/cobrar`, { method: 'POST', body: JSON.stringify(payload) })

export const reembolsosDelPedido = (id) => apiFetch(`/pedido/${id}/reembolsos`)

export const registrarReembolso = (id, payload) =>
  apiFetch(`/pedido/${id}/reembolso`, { method: 'POST', body: JSON.stringify(payload) })
