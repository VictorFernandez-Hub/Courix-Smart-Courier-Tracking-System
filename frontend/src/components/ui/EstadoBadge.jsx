const ETIQUETAS = {
  pendiente: 'Pendiente',
  en_almacen: 'En almacén',
  en_transito: 'En tránsito',
  en_agencia_destino: 'En agencia destino',
  asignado: 'Asignado',
  recogido: 'Recogido',
  en_camino: 'En camino',
  entregado: 'Entregado',
  no_entregado: 'No entregado',
  por_devolver: 'Por devolver',
  devuelto: 'Devuelto al remitente',
  cancelado: 'Cancelado',
  extraviado: 'Extraviado',
}

export default function EstadoBadge({ estado }) {
  const color = `var(--st-${estado}, var(--ink-faint))`
  const texto = ETIQUETAS[estado] || estado

  return (
    <span className="badge" style={{ color, background: `color-mix(in srgb, ${color} 14%, white)` }}>
      {texto}
    </span>
  )
}
