import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { etiquetaPedido } from '../../api'

// Etiqueta de envio: una por bulto, formato 10 x 15 cm (impresoras termicas
// de courier). El QR lleva el codigo del bulto (CE-XXXX-XXXX-1) para
// escanearlo en despacho y recepcion. No se imprime el contenido del
// paquete ni el DNI: una etiqueta que dice "celular" invita al robo.

const SERVICIOS = { estandar: 'ESTÁNDAR', express: 'EXPRESS' }
const MODALIDADES = { contra_entrega: 'Pagado', prepagado: 'Prepagado', credito: 'Crédito' }

export default function Etiqueta() {
  const { id } = useParams()
  const [datos, setDatos] = useState(null)
  const [qrs, setQrs] = useState({})
  const [error, setError] = useState('')
  // Solo llega justo despues de admitir. Se copia al estado del componente y
  // se borra del historial del navegador: si no, seguiria visible al recargar
  // o al volver con "atras" (history.state sobrevive a la recarga).
  const location = useLocation()
  const navigate = useNavigate()
  const [pinEntrega] = useState(() => location.state?.pinEntrega || null)
  useEffect(() => {
    if (location.state?.pinEntrega) navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  useEffect(() => {
    etiquetaPedido(id)
      .then(async (r) => {
        const contenido = r.content
        const imagenes = {}
        for (const b of contenido.bultos) {
          imagenes[b.codigo] = await QRCode.toDataURL(b.codigo, { margin: 1, width: 220, errorCorrectionLevel: 'M' })
        }
        setQrs(imagenes)
        setDatos(contenido)
      })
      .catch((err) => setError(err.message))
  }, [id])

  const fecha = (iso) => (iso ? new Date(iso).toLocaleDateString('es-PE') : '—')

  return (
    <div className="etiqueta-pagina">
      <div className="etiqueta-barra no-imprimir">
        <Link to="/pedidos" className="btn btn-secondary">← Volver a pedidos</Link>
        {datos && (
          <>
            <span className="cell-secondary">
              Guía <strong className="cell-mono">{datos.codigoGuia}</strong> · {datos.bultos.length} etiqueta(s) de 10 × 15 cm
            </span>
            <button className="btn btn-primary" onClick={() => window.print()}>Imprimir</button>
          </>
        )}
      </div>

      {pinEntrega && (
        <div className="pin-aviso no-imprimir" role="alert">
          <div>Código de entrega (PIN)</div>
          <strong>{pinEntrega}</strong>
          <p>Entrégaselo al remitente para que se lo pase al destinatario. <b>No se volverá a mostrar</b> ni se imprime en la etiqueta.</p>
        </div>
      )}
      {error && <div className="error-banner no-imprimir">{error}</div>}
      {!datos && !error && <p className="loading-text no-imprimir">Generando etiquetas…</p>}

      {datos && datos.bultos.map((b) => (
        <article className="etiqueta" key={b.codigo}>
          <header className="etq-cabecera">
            <div className="etq-marca">Courrier<span>Express</span></div>
            <div className={`etq-servicio ${datos.tipoServicio}`}>{SERVICIOS[datos.tipoServicio] || datos.tipoServicio}</div>
          </header>

          <div className="etq-guia">
            <img src={qrs[b.codigo]} alt={`QR ${b.codigo}`} />
            <div>
              <div className="etq-rotulo">Guía</div>
              <div className="etq-codigo">{datos.codigoGuia}</div>
              <div className="etq-bulto">Bulto {b.numero} de {b.total}</div>
              <div className="etq-peso">{b.pesoFacturableKg} kg</div>
            </div>
          </div>

          {/* Lo primero que mira quien clasifica: a que agencia va */}
          <div className={`etq-ruta${datos.agenciaDestino?.esLocal ? ' local' : ''}`}>
            {datos.agenciaDestino?.esLocal ? 'REPARTO LOCAL' : `→ ${datos.agenciaDestino?.nombre || ''}`}
          </div>

          <section className="etq-bloque etq-destino">
            <div className="etq-rotulo">Destinatario</div>
            <div className="etq-nombre">{datos.destinatario.nombre}</div>
            <div>{datos.destinatario.calle}</div>
            {datos.destinatario.referencia && <div className="etq-ref">Ref.: {datos.destinatario.referencia}</div>}
            <div className="etq-fila">
              <span>Tel. {datos.destinatario.telefono}</span>
              {datos.destinatario.zona && <strong className="etq-zona">{datos.destinatario.zona}</strong>}
            </div>
          </section>

          <section className="etq-bloque">
            <div className="etq-rotulo">Remitente</div>
            <div>{datos.remitente ? `${datos.remitente.nombre} · Tel. ${datos.remitente.telefono}` : '—'}</div>
            <div className="etq-fila">
              <span>Origen: {datos.origen.agencia}</span>
              <span>Admitido: {fecha(datos.fechaCreacion)}</span>
            </div>
          </section>

          <footer className="etq-pie">
            {/* Lo que importa al repartidor es si cobra o no; "PAGADO" afirmaria
                algo que la etiqueta no sabe (un prepagado puede no estar pagado aun). */}
            {datos.montoACobrar ? (
              <div className="etq-cobrar">COBRAR S/ {Number(datos.montoACobrar).toFixed(2)}</div>
            ) : (
              <div className="etq-pagado">NO COBRAR · {MODALIDADES[datos.modalidadPago] || 'Pagado'}</div>
            )}
            <div className="etq-fila">
              {datos.prioridad === 'urgente' && <strong>URGENTE</strong>}
              <span>Entrega estimada: {fecha(datos.fechaEntregaEstimada)}</span>
            </div>
          </footer>
        </article>
      ))}
    </div>
  )
}
