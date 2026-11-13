// Pagos y liquidacion de caja.
import { apiFetch } from './cliente'

export const listarPagos = (estadoPago, pagina = 1) => {
  const params = new URLSearchParams({ pagina, por_pagina: 20 })
  if (estadoPago) params.set('estado_pago', estadoPago)
  return apiFetch(`/pagos?${params.toString()}`)
}

export const crearPago = (payload) =>
  apiFetch('/pago', { method: 'POST', body: JSON.stringify(payload) })

export const marcarPagoComoPagado = (id) =>
  apiFetch(`/pago/${id}/marcar-pagado`, { method: 'POST' })

export const pedidosConPagoRegistrado = (pedidoIds) =>
  apiFetch(`/pagos/existentes?pedido_ids=${pedidoIds.join(',')}`)

export const liquidacionesPendientes = () => apiFetch('/liquidaciones/pendientes')

export const liquidarRuta = (rutaId, montoEntregado, observacion) =>
  apiFetch(`/ruta/${rutaId}/liquidar`, { method: 'POST', body: JSON.stringify({ montoEntregado, observacion }) })

// ---- Contra entrega de mercaderia (recaudos que se le deben a cada remitente) ----
export const recaudosPendientes = () => apiFetch('/recaudos/pendientes')

export const listarRecaudos = ({ remitenteId, estado } = {}) => {
  const params = new URLSearchParams()
  if (remitenteId) params.set('remitente_id', remitenteId)
  if (estado) params.set('estado', estado)
  return apiFetch(`/recaudos?${params.toString()}`)
}

export const liquidarRecaudos = (payload) =>
  apiFetch('/recaudos/liquidar', { method: 'POST', body: JSON.stringify(payload) })

export const liquidacionesRecaudo = () => apiFetch('/liquidaciones-recaudo')

// ---- Cierre de caja (arqueo del cajero) ----
export const arqueoCaja = () => apiFetch('/caja/arqueo')

export const cerrarCaja = (payload) =>
  apiFetch('/caja/cierre', { method: 'POST', body: JSON.stringify(payload) })

export const listarCierresCaja = () => apiFetch('/caja/cierres')

// ---- Credito: cuentas por cobrar ----
export const carteraCredito = () => apiFetch('/creditos/cartera')

export const cuentaCliente = (id) => apiFetch(`/cliente/${id}/cuenta`)

export const configurarCredito = (id, payload) =>
  apiFetch(`/cliente/${id}/credito`, { method: 'PUT', body: JSON.stringify(payload) })

export const cobrarCredito = (id, payload) =>
  apiFetch(`/cliente/${id}/cobrar-credito`, { method: 'POST', body: JSON.stringify(payload) })
