import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout.jsx'
import { ProtectedRoute, SoloStaff, SoloAdmin, DestinoSegunRol } from './routes/guards.jsx'

import Login from './pages/auth/Login.jsx'
import RecuperarPassword from './pages/auth/RecuperarPassword.jsx'
import RestablecerPassword from './pages/auth/RestablecerPassword.jsx'
import RastreoPublico from './pages/publico/RastreoPublico.jsx'
import Pedidos from './pages/pedidos/Pedidos.jsx'
import Admision from './pages/pedidos/Admision.jsx'
import Etiqueta from './pages/pedidos/Etiqueta.jsx'
import Clientes from './pages/clientes/Clientes.jsx'
import Almacenes from './pages/almacenes/Almacenes.jsx'
import Rutas from './pages/rutas/Rutas.jsx'
import Pagos from './pages/pagos/Pagos.jsx'
import Incidencias from './pages/incidencias/Incidencias.jsx'
import Reportes from './pages/reportes/Reportes.jsx'
import Configuracion from './pages/configuracion/Configuracion.jsx'
import MiRuta from './pages/repartidor/MiRuta.jsx'
import Despachos from './pages/despachos/Despachos.jsx'
import Manifiesto from './pages/despachos/Manifiesto.jsx'
import Recojos from './pages/recojos/Recojos.jsx'

export default function App() {
  return (
    <Routes>
      {/* Publicas */}
      <Route path="/login" element={<Login />} />
      <Route path="/recuperar" element={<RecuperarPassword />} />
      <Route path="/restablecer" element={<RestablecerPassword />} />
      <Route path="/rastreo" element={<RastreoPublico />} />

      {/* Etiqueta: pagina completa, sin menu, lista para imprimir */}
      <Route path="/pedidos/:id/etiqueta" element={<ProtectedRoute><SoloStaff><Etiqueta /></SoloStaff></ProtectedRoute>} />

      {/* Requieren sesion */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DestinoSegunRol />} />
        <Route path="pedidos" element={<SoloStaff><Pedidos /></SoloStaff>} />
        <Route path="pedidos/nuevo" element={<SoloStaff><Admision /></SoloStaff>} />
        <Route path="pedidos/:id/recibir" element={<SoloStaff><Admision /></SoloStaff>} />
        <Route path="recojos" element={<SoloStaff><Recojos /></SoloStaff>} />
        <Route path="despachos" element={<SoloStaff><Despachos /></SoloStaff>} />
        <Route path="despachos/:id" element={<SoloStaff><Manifiesto /></SoloStaff>} />
        <Route path="clientes" element={<SoloStaff><Clientes /></SoloStaff>} />
        <Route path="almacenes" element={<SoloStaff><Almacenes /></SoloStaff>} />
        <Route path="rutas" element={<SoloStaff><Rutas /></SoloStaff>} />
        <Route path="pagos" element={<SoloStaff><Pagos /></SoloStaff>} />
        <Route path="incidencias" element={<SoloStaff><Incidencias /></SoloStaff>} />
        <Route path="reportes" element={<SoloStaff><Reportes /></SoloStaff>} />
        <Route path="configuracion" element={<SoloAdmin><Configuracion /></SoloAdmin>} />
        <Route path="mi-ruta" element={<MiRuta />} />
      </Route>

      <Route path="*" element={<DestinoSegunRol />} />
    </Routes>
  )
}
