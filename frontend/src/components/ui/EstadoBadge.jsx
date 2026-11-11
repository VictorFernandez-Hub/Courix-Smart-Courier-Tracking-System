const ETIQUETAS = {
  pendiente: 'Pendiente',
  en_almacen: 'En almacén',
  asignado: 'Asignado',
  recogido: 'Recogido',
  en_camino: 'En camino',
  entregado: 'Entregado',
  no_entregado: 'No entregado',
  devuelto: 'Devuelto',
  cancelado: 'Cancelado',
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
