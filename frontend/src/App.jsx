import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout.jsx'
import { ProtectedRoute, SoloStaff, SoloAdmin, DestinoSegunRol } from './routes/guards.jsx'

import Login from './pages/auth/Login.jsx'
import RastreoPublico from './pages/publico/RastreoPublico.jsx'
import Pedidos from './pages/pedidos/Pedidos.jsx'
import Clientes from './pages/clientes/Clientes.jsx'
import Almacenes from './pages/almacenes/Almacenes.jsx'
import Rutas from './pages/rutas/Rutas.jsx'
import Pagos from './pages/pagos/Pagos.jsx'
import Incidencias from './pages/incidencias/Incidencias.jsx'
import Reportes from './pages/reportes/Reportes.jsx'
import Configuracion from './pages/configuracion/Configuracion.jsx'
import MiRuta from './pages/repartidor/MiRuta.jsx'

export default function App() {
  return (
    <Routes>
      {/* Publicas */}
      <Route path="/login" element={<Login />} />
      <Route path="/rastreo" element={<RastreoPublico />} />

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
