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
