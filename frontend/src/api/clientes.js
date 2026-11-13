// Clientes y sus direcciones.
import { apiFetch, apiDescargar } from './cliente'

const post = (url, body) => apiFetch(url, { method: 'POST', body: JSON.stringify(body || {}) })
const put = (url, body) => apiFetch(url, { method: 'PUT', body: JSON.stringify(body || {}) })

const aParams = (filtros = {}) => {
  const params = new URLSearchParams()
  Object.entries(filtros).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') params.set(k, v)
  })
  return params.toString()
}

// Lista simple (hasta 500, solo activos) para selectores de otras pantallas.
export const listarClientes = (q) => apiFetch(`/clientes?${aParams({ q })}`)

// Listado de gestion: { pagina, por_pagina, q, estado, tipo, avisos, orden }
// -> { content, paginacion, resumen }
export const buscarClientes = (filtros) => apiFetch(`/clientes?${aParams({ pagina: 1, ...filtros })}`)

export const verificarDuplicados = (datos) => apiFetch(`/clientes/verificar?${aParams(datos)}`)

export const exportarClientes = (filtros) =>
  apiDescargar(`/clientes/exportar?${aParams(filtros)}`, 'clientes.csv')

export const obtenerCliente = (id) => apiFetch(`/cliente/${id}`)

export const crearCliente = (payload) => post('/cliente', payload)

export const editarCliente = (id, payload) => put(`/cliente/${id}`, payload)

export const desactivarCliente = (id, motivo) => post(`/cliente/${id}/desactivar`, { motivo })

export const activarCliente = (id) => post(`/cliente/${id}/activar`)

export const pedidosDelCliente = (id, { rol, pagina, estado } = {}) =>
  apiFetch(`/cliente/${id}/pedidos?${aParams({ rol, pagina, estado, por_pagina: 10 })}`)

export const actividadCliente = (id) => apiFetch(`/cliente/${id}/actividad`)

export const listarDireccionesCliente = (clienteId) =>
  apiFetch(`/cliente/${clienteId}/direcciones`)

export const crearDireccionCliente = (payload) => post('/direccion-cliente', payload)

export const editarDireccionCliente = (id, payload) => put(`/direccion-cliente/${id}`, payload)

export const marcarDireccionPrincipal = (id) => post(`/direccion-cliente/${id}/principal`)

export const eliminarDireccionCliente = (id) => post(`/direccion-cliente/${id}/desactivar`)
