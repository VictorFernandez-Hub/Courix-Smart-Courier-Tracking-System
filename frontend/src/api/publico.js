// Rastreo publico por codigo de guia (sin login).
import { apiFetch } from './cliente'

export const rastrearPorCodigoGuia = (codigo) => apiFetch(`/rastreo/${encodeURIComponent(codigo)}`)
