// Rutas de reparto.
import { apiFetch } from './cliente'

export const crearRuta = (repartidorId) =>
  apiFetch('/ruta', { method: 'POST', body: JSON.stringify({ repartidorId }) })

export const agregarPedidoARuta = (rutaId, pedidoId) =>
  apiFetch(`/ruta/${rutaId}/agregar-pedido`, { method: 'POST', body: JSON.stringify({ pedidoId }) })

export const quitarPedidoDeRuta = (rutaId, pedidoId) =>
  apiFetch(`/ruta/${rutaId}/quitar-pedido/${pedidoId}`, { method: 'POST' })

export const rutaActivaDeRepartidor = (repartidorId) =>
  apiFetch(`/repartidor/${repartidorId}/ruta-activa`)

export const iniciarRuta = (rutaId) =>
  apiFetch(`/ruta/${rutaId}/iniciar`, { method: 'POST' })

export const completarRuta = (rutaId) =>
  apiFetch(`/ruta/${rutaId}/completar`, { method: 'POST' })

export const listarRutas = () => apiFetch('/rutas')

export const detalleRuta = (id) => apiFetch(`/ruta/${id}/detalle`)
