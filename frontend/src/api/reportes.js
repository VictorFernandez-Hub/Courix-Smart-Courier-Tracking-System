// Indicadores del negocio.
import { apiFetch } from './cliente'

export const resumenReportes = () => apiFetch('/reportes/resumen')
