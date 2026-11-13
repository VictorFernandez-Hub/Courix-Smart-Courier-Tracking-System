import { useEffect, useState } from 'react'
import { resumenReportes, reporteSla } from '../../api'

const ETIQUETAS_ESTADO = {
  pendiente: 'Pendiente',
  en_almacen: 'En almacén',
  asignado: 'Asignado',
  recogido: 'Recogido',
  en_camino: 'En camino',
  entregado: 'Entregado',
  no_entregado: 'No entregado',
  por_devolver: 'Por devolver',
  devuelto: 'Devuelto',
  extraviado: 'Extraviado',
  cancelado: 'Cancelado',
}

export default function Reportes() {
  const [resumen, setResumen] = useState(null)
  const [sla, setSla] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    reporteSla().then((r) => setSla(r.content)).catch(() => {})
    resumenReportes()
      .then((r) => setResumen(r.content))
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [])

  if (cargando) return <p className="loading-text">Cargando reportes…</p>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Reportes</h1>
          <p className="page-sub">Resumen general del negocio</p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {resumen && (
        <>
          {sla && (
            <>
              <div className="section-title" style={{ marginTop: 0 }}>Cumplimiento del plazo comprometido</div>
              <div className="card-grid" style={{ marginBottom: 24 }}>
                {[
                  ['Envíos atrasados', sla.atrasados, sla.atrasados > 0 ? 'var(--danger)' : undefined],
                  ['Vencen hoy', sla.vencenHoy],
                  ['Entregados a tiempo', sla.porcentajeATiempo == null ? '—' : `${sla.porcentajeATiempo}%`],
                  ['Envíos activos', sla.activos],
                ].map(([titulo, valor, color]) => (
                  <div className="mini-card" key={titulo}>
                    <div className="mini-card-line"><span>{titulo}</span></div>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, color }}>{valor}</div>
                  </div>
                ))}
              </div>
            </>
          )}
          <div className="card-grid" style={{ marginBottom: 24 }}>
            <div className="mini-card">
              <div className="mini-card-line"><span>Total de pedidos</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>{resumen.totalPedidos}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Clientes registrados</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>{resumen.totalClientes}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Repartidores</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>
                {resumen.repartidoresDisponibles} <span style={{ fontSize: 14, color: 'var(--ink-faint)', fontWeight: 500 }}>/ {resumen.totalRepartidores} disponibles</span>
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Rutas activas</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>{resumen.rutasActivas}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Total cobrado</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--st-entregado)' }}>
                S/ {Number(resumen.totalCobrado).toFixed(2)}
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Por cobrar</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--st-en_almacen)' }}>
                S/ {Number(resumen.totalPorCobrar).toFixed(2)}
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Efectivo en manos de repartidores</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--st-no_entregado, var(--ink))' }}>
                S/ {Number(resumen.efectivoPorLiquidar || 0).toFixed(2)}
              </div>
            </div>
            <div className="mini-card" title="Precio de productos cobrados por cuenta de remitentes y aún no pagados a ellos">
              <div className="mini-card-line"><span>Recaudo por pagar a remitentes</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 700, color: 'var(--st-por_devolver, var(--ink))' }}>
                S/ {Number(resumen.recaudoPorLiquidar || 0).toFixed(2)}
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Entregas al primer intento</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>
                {resumen.tasaEntregaPrimerIntento == null ? '—' : `${resumen.tasaEntregaPrimerIntento}%`}
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-line"><span>Incidencias sin resolver</span></div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700 }}>{resumen.incidenciasAbiertas ?? 0}</div>
            </div>
          </div>

          <div className="section-title" style={{ marginTop: 0 }}>Pedidos por estado</div>
          <div className="manifest">
            {Object.entries(resumen.pedidosPorEstado).map(([estado, cantidad]) => (
              <div key={estado} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 18px', borderBottom: '1px solid var(--border)' }}>
                <span>{ETIQUETAS_ESTADO[estado] || estado}</span>
                <span className="cell-mono" style={{ fontWeight: 600 }}>{cantidad}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
