// Gestion de usuarios (admin).
import { apiFetch } from './cliente'

export const listarUsuarios = () => apiFetch('/usuarios?por_pagina=100')

export const crearUsuario = (payload) =>
  apiFetch('/usuario', { method: 'POST', body: JSON.stringify(payload) })

export const editarUsuario = (id, payload) =>
  apiFetch(`/usuario/${id}`, { method: 'PUT', body: JSON.stringify(payload) })

export const desactivarUsuario = (id) =>
  apiFetch(`/usuario/${id}/desactivar`, { method: 'POST' })

export const activarUsuario = (id) =>
  apiFetch(`/usuario/${id}/activar`, { method: 'POST' })

export const restablecerPassword = (id, passwordNueva) =>
  apiFetch(`/usuario/${id}/password`, { method: 'POST', body: JSON.stringify({ passwordNueva }) })
